"""Opt-in invocation capture and exact-match replay of supported LLM outputs."""
import hashlib
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path

from langchain_core.messages import BaseMessage, message_to_dict, messages_from_dict
from langchain_core.runnables import Runnable
from langchain_core.utils.function_calling import convert_to_openai_tool
from pydantic import BaseModel

from tradingagents.evidence.capture import EvidenceCaptureError
from tradingagents.evidence.store import EvidenceStore, _encode

_RUN = ContextVar("llm_evidence_run", default=None)
_REPLAY = ContextVar("llm_evidence_replay", default=None)


class LLMReplayError(RuntimeError):
    """No exact recorded invocation is available; live fallback is forbidden."""


def _pack(value):
    if isinstance(value, BaseMessage):
        return {"kind": "message", "data": message_to_dict(value)}
    if hasattr(value, "to_messages"):
        return _pack(value.to_messages())
    if isinstance(value, BaseModel):
        return {"kind": "model", "data": value.model_dump(mode="json")}
    if isinstance(value, (list, tuple)):
        return {"kind": "list", "data": [_pack(v) for v in value]}
    if isinstance(value, dict):
        return {"kind": "dict", "data": {k: _pack(v) for k, v in value.items()}}
    return {"kind": "json", "data": value}


def _request_pack(value):
    packed = _pack(value)

    def clean(item):
        if isinstance(item, dict):
            if item.get("kind") == "message":
                item["data"]["data"]["id"] = None
            for child in item.values():
                clean(child)
        elif isinstance(item, list):
            for child in item:
                clean(child)
    clean(packed)
    return packed


def _unpack(value, schema=None):
    kind, data = value["kind"], value["data"]
    if kind == "message":
        return messages_from_dict([data])[0]
    if kind == "model":
        if schema is None:
            raise LLMReplayError("structured replay requires the caller's schema")
        return schema.model_validate(data)
    if kind == "list":
        return [_unpack(v, schema) for v in data]
    if kind == "dict":
        return {k: _unpack(v, schema) for k, v in data.items()}
    if kind == "json":
        return data
    raise LLMReplayError("unsupported response encoding")


@contextmanager
def llm_run(config, manifest, checkpoint, lock):
    enabled = config.get("evidence_llm_responses", False)
    if type(enabled) is not bool:
        raise ValueError("evidence_llm_responses must be boolean")
    manifest["llm_evidence"] = []
    manifest["llm_evidence_enabled"] = enabled
    session = (EvidenceStore(Path(config["results_dir"]) / "evidence"), manifest, checkpoint, lock)
    token = _RUN.set(session if enabled else None)
    try:
        yield
    finally:
        _RUN.reset(token)


@contextmanager
def replay_llm(store, evidence_ids):
    responses = {}
    for evidence_id in evidence_ids:
        record = store.get(evidence_id)
        if record["tool"] != "llm_invocation" or record["payload"].get("schema_version") != 1:
            raise LLMReplayError("unsupported LLM evidence")
        payload = record["payload"]
        key = hashlib.sha256(_encode(payload["request"])).hexdigest()
        if key in responses and responses[key] != payload["response"]:
            raise LLMReplayError("conflicting responses; select explicit invocation IDs")
        responses[key] = payload["response"]
    token = _REPLAY.set(responses)
    try:
        yield
    finally:
        _REPLAY.reset(token)


class RecordedModel(Runnable):
    """Wrap invoke/bind_tools/structured output, or use delegate=None for replay.

    identity must describe the provider, model and effective model settings.
    Streams are not provider-token streams; Runnable's default invokes once.
    """

    def __init__(self, delegate, identity, binding=None, schema=None):
        self.delegate, self.identity = delegate, identity
        self.binding, self.schema = binding or {}, schema

    def bind_tools(self, tools, **kwargs):
        binding = {"parent": self.binding, "tools": [convert_to_openai_tool(t) for t in tools], "options": kwargs}
        delegate = self.delegate.bind_tools(tools, **kwargs) if self.delegate is not None else None
        return RecordedModel(delegate, self.identity, binding)

    def with_structured_output(self, schema, **kwargs):
        shape = schema.model_json_schema() if isinstance(schema, type) and issubclass(schema, BaseModel) else schema
        delegate = self.delegate.with_structured_output(schema, **kwargs) if self.delegate is not None else None
        return RecordedModel(delegate, self.identity, {"parent": self.binding, "schema": shape, "options": kwargs},
                             schema if isinstance(schema, type) and issubclass(schema, BaseModel) else None)

    def invoke(self, input, config=None, **kwargs):
        replay, session = _REPLAY.get(), _RUN.get()
        if replay is None and session is None:
            if self.delegate is None:
                raise LLMReplayError("no live delegate or replay context")
            return self.delegate.invoke(input, config=config, **kwargs)
        # Scheduler/checkpoint objects are execution plumbing, not model settings.
        configurable = {k: v for k, v in (config or {}).get("configurable", {}).items()
                        if not k.startswith("__pregel_")
                        and k not in {"thread_id", "checkpoint_id", "checkpoint_ns", "checkpoint_map"}}
        request = {"identity": self.identity, "binding": self.binding, "input": _request_pack(input),
                   "kwargs": _pack(kwargs), "configurable": _pack(configurable)}
        try:
            key = hashlib.sha256(_encode(request)).hexdigest()
        except Exception as exc:
            error = LLMReplayError if replay is not None else EvidenceCaptureError
            raise error("unsupported LLM request encoding") from exc
        if replay is not None:
            if key not in replay:
                raise LLMReplayError("invocation absent from selected evidence")
            return _unpack(replay[key], self.schema)
        if self.delegate is None:
            raise LLMReplayError("no live delegate")
        response = self.delegate.invoke(input, config=config, **kwargs)
        store, manifest, checkpoint, lock = session
        try:
            with lock:
                evidence_id = store.put(run_id=manifest["run_id"], tool="llm_invocation", payload={
                    "schema_version": 1, "request": request, "response": _pack(response),
                })
                manifest["llm_evidence"].append({"sequence": len(manifest["llm_evidence"]) + 1,
                                                 "evidence_id": evidence_id, "request_sha256": key})
                checkpoint()
        except Exception as exc:
            raise EvidenceCaptureError("could not persist requested LLM evidence") from exc
        return response
