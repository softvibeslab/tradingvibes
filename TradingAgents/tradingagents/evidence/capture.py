"""Run-scoped, opt-in price and tool-response capture; never infer retention permission."""
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path
from threading import RLock

_SESSION = ContextVar("price_evidence_session", default=None)
_PURPOSE = ContextVar("price_evidence_purpose", default="analysis")


class EvidenceCaptureError(RuntimeError):
    """Requested evidence could not be persisted; do not silently change vendors."""


@contextmanager
def capture_run(config, manifest, checkpoint):
    providers = config.get("evidence_price_providers", [])
    if not isinstance(providers, list) or any(
        p not in ("yfinance", "alpha_vantage") for p in providers
    ):
        raise ValueError("evidence_price_providers must list supported price providers")
    from tradingagents.evidence.tools import validate_policy

    tool_policy = validate_policy(config.get("evidence_tool_providers", {}))
    manifest["tool_evidence"] = []
    manifest["tool_evidence_policy"] = tool_policy
    manifest["price_evidence"] = []
    manifest["price_evidence_policy"] = {"providers": sorted(set(providers))}
    session = (config, manifest, checkpoint, RLock(), frozenset(providers), tool_policy) if providers or tool_policy else None
    token = _SESSION.set(session)
    purpose_token = _PURPOSE.set("analysis")
    try:
        checkpoint()
        yield
    finally:
        _PURPOSE.reset(purpose_token)
        _SESSION.reset(token)


@contextmanager
def outcome_prices():
    token = _PURPOSE.set("outcome")
    try:
        yield
    finally:
        _PURPOSE.reset(token)


def capture_prices(history):
    session = _SESSION.get()
    if session is None:
        return history
    config, manifest, checkpoint, lock, providers, _ = session
    if history.provider not in providers:
        return history
    from tradingagents.evidence.prices import archive_prices
    from tradingagents.evidence.store import EvidenceStore

    purpose = _PURPOSE.get()
    try:
        with lock:
            store = EvidenceStore(Path(config["results_dir"]) / "evidence")
            evidence_id = archive_prices(store, history, run_id=manifest["run_id"], purpose=purpose)
            manifest["price_evidence"].append({
                "sequence": len(manifest["price_evidence"]) + 1,
                "evidence_id": evidence_id, "purpose": purpose,
                "provider": history.provider, "symbol": history.symbol,
            })
            checkpoint()
    except Exception as exc:
        # Do not include exception text: paths or credentials may be present.
        raise EvidenceCaptureError("could not persist requested price evidence") from exc
    return history


def capture_tool_response(method, provider, args, kwargs, result):
    from tradingagents.dataflows.fundamentals import FundamentalStatement, MacroSeriesResult
    from tradingagents.evidence.fundamentals import encode_fundamental

    typed = result if isinstance(result, (FundamentalStatement, MacroSeriesResult)) else None
    result = typed.to_text() if typed is not None else result
    session = _SESSION.get()
    if session is None:
        return result
    config, manifest, checkpoint, lock, _, policy = session
    if provider not in policy.get(method, []):
        return result
    from datetime import UTC, datetime

    from tradingagents.evidence.store import EvidenceStore

    # Exact rendered response only. Never infer publication time from retrieval.
    if not isinstance(result, str):
        raise EvidenceCaptureError("configured tool did not return a text response")
    try:
        with lock:
            store = EvidenceStore(Path(config["results_dir"]) / "evidence")
            evidence_id = store.put(
                run_id=manifest["run_id"], tool="routed_tool_response", purpose=_PURPOSE.get(),
                payload={"schema_version": 1, "method": method, "provider": provider,
                         "args": list(args), "kwargs": kwargs, "text": result,
                         "retrieved_at": datetime.now(UTC).isoformat(),
                         "availability_basis": typed.availability_basis if typed is not None else "unknown",
                         "structured": encode_fundamental(typed) if typed is not None else None},
            )
            manifest["tool_evidence"].append({
                "sequence": len(manifest["tool_evidence"]) + 1,
                "evidence_id": evidence_id, "method": method,
                "provider": provider, "purpose": _PURPOSE.get(),
            })
            checkpoint()
    except Exception as exc:
        raise EvidenceCaptureError("could not persist requested tool evidence") from exc
    return result
