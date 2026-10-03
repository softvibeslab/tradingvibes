"""Run-scoped, opt-in normalized price capture; never infer retention permission."""
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
    manifest["price_evidence"] = []
    manifest["price_evidence_policy"] = {"providers": sorted(set(providers))}
    session = (config, manifest, checkpoint, RLock(), frozenset(providers)) if providers else None
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
    config, manifest, checkpoint, lock, providers = session
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
