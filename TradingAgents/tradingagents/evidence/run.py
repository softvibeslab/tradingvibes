"""Opt-in graph inputs, external boundaries and offline run replay."""
import hashlib
import json
import re
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path

from tradingagents.evidence.capture import EvidenceCaptureError
from tradingagents.evidence.llm import RecordedModel, _pack, _request_pack, _unpack, replay_llm
from tradingagents.evidence.store import EvidenceStore, _encode

_CAPTURE = ContextVar("graph_capture", default=None)
_REPLAY = ContextVar("graph_replay", default=None)


class RunReplayError(RuntimeError):
    """A complete, compatible archived run is required."""


@contextmanager
def graph_capture(config, manifest, checkpoint, lock):
    enabled = config.get("evidence_graph_replay", False)
    if type(enabled) is not bool:
        raise ValueError("evidence_graph_replay must be boolean")
    if enabled and (not config.get("evidence_llm_responses") or config.get("checkpoint_enabled")):
        raise ValueError("graph capture requires LLM evidence and checkpointing disabled")
    manifest["graph_evidence"] = []
    token = _CAPTURE.set((EvidenceStore(Path(config["results_dir"]) / "evidence"),
                          manifest, checkpoint, lock) if enabled else None)
    try:
        yield
    finally:
        _CAPTURE.reset(token)


def _save(payload):
    session = _CAPTURE.get()
    if session is None:
        return
    store, manifest, checkpoint, lock = session
    try:
        with lock:
            evidence_id = store.put(run_id=manifest["run_id"], tool="graph_replay", payload=payload)
            manifest["graph_evidence"].append(evidence_id)
            checkpoint()
    except Exception as exc:
        raise EvidenceCaptureError("could not persist graph evidence") from exc


def graph_boundary(name, inputs, call):
    """Replay external inputs before executing any provider code."""
    if _CAPTURE.get() is None and _REPLAY.get() is None:
        return call()
    key = hashlib.sha256(_encode({"name": name, "input": _request_pack(inputs)})).hexdigest()
    replay = _REPLAY.get()
    if replay is not None:
        if key not in replay:
            raise RunReplayError("external boundary absent from run evidence: " + name)
        return _unpack(replay[key])
    result = call()
    _save({"schema_version": 1, "kind": "boundary", "key": key, "response": _pack(result)})
    return result


def save_graph_state(kind, state):
    if _CAPTURE.get() is None:
        return
    _, manifest, _, _ = _CAPTURE.get()

    _save({"schema_version": 1, "kind": kind, "state": _pack(state),
           "settings": manifest["settings"], "analysts": manifest["analysts"]})


class _OfflineModel(RecordedModel):
    def __init__(self, identity, schemas):
        super().__init__(None, identity)
        self.schemas = schemas

    def with_structured_output(self, schema, **kwargs):
        if schema.model_json_schema() not in self.schemas:
            raise NotImplementedError("structured binding absent from original run")
        return super().with_structured_output(schema, **kwargs)


def replay_run(results_dir, run_id):
    """Reexecute a completed graph; never settle memory or construct API clients.

    Returns the replay state and exact state comparison (excluding run/message IDs).
    Missing evidence or incompatible code fails closed. No original files are changed.
    """
    from tradingagents.dataflows.config import run_config
    from tradingagents.graph.conditional_logic import ConditionalLogic
    from tradingagents.graph.setup import GraphSetup
    from tradingagents.runs.manifest import source_metadata

    if not re.fullmatch(r"[0-9a-f]{32}", run_id):
        raise RunReplayError("invalid run_id")
    root = Path(results_dir)
    manifest = json.loads((root / "runs" / run_id / "manifest.json").read_text())
    if manifest.get("status") != "completed" or manifest.get("run_id") != run_id:
        raise RunReplayError("replay requires a completed run")
    source = source_metadata()
    if any(manifest["source"].get(k) != source.get(k)
           for k in ("package_source_sha256", "lock_sha256")):
        raise RunReplayError("source or dependency lock differs from recorded run")
    store = EvidenceStore(root / "evidence")
    states, boundaries = {}, {}
    for evidence_id in manifest.get("graph_evidence", []):
        record = store.get(evidence_id)
        payload = record["payload"]
        if record["tool"] != "graph_replay" or payload.get("schema_version") != 1:
            raise RunReplayError("unsupported graph evidence")
        kind = payload["kind"]
        if kind == "boundary":
            key, response = payload["key"], payload["response"]
            if key in boundaries and boundaries[key] != response:
                raise RunReplayError("conflicting external responses")
            boundaries[key] = response
        elif kind in {"initial", "final"}:
            if kind in states:
                raise RunReplayError("ambiguous graph state")
            states[kind] = payload
        else:
            raise RunReplayError("unknown graph artifact")
    if set(states) != {"initial", "final"}:
        raise RunReplayError("initial/final graph evidence missing; record a new opted-in run")
    ids = [ref["evidence_id"] for ref in manifest.get("llm_evidence", [])]
    identities, schemas = {}, {"quick": [], "deep": []}
    for evidence_id in ids:
        request = store.get(evidence_id)["payload"]["request"]
        identity = request["identity"]
        role = identity["role"]
        if role in identities and identities[role] != identity:
            raise RunReplayError("conflicting model identities")
        identities[role] = identity
        if "schema" in request["binding"]:
            schemas[role].append(request["binding"]["schema"])
    if set(identities) != {"quick", "deep"}:
        raise RunReplayError("model evidence missing")
    cfg = states["initial"]["settings"]
    token = _REPLAY.set(boundaries)
    try:
        with run_config(cfg), replay_llm(store, ids):
            setup = GraphSetup(_OfflineModel(identities["quick"], schemas["quick"]),
                               _OfflineModel(identities["deep"], schemas["deep"]),
                               ConditionalLogic(cfg["max_debate_rounds"], cfg["max_risk_discuss_rounds"]),
                               cfg["max_tool_rounds"])
            graph = setup.setup_graph(states["initial"]["analysts"]).compile()
            actual = graph.invoke(_unpack(states["initial"]["state"]),
                                  config={"recursion_limit": cfg["max_recur_limit"]})
    finally:
        _REPLAY.reset(token)
    expected = _unpack(states["final"]["state"])
    expected.pop("run_id", None)
    matches = _request_pack(actual) == _request_pack(expected)
    return {"run_id": run_id, "matches": matches, "state": actual}
