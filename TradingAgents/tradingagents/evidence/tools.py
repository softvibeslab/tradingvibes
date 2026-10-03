"""Replay of explicitly archived routed tool responses, never a live fallback."""
from contextlib import contextmanager
from contextvars import ContextVar

from tradingagents.evidence.store import _encode

TOOL_PROVIDERS = {
    "get_fundamentals": {"yfinance", "alpha_vantage"},
    "get_balance_sheet": {"yfinance", "alpha_vantage", "sec_edgar"},
    "get_cashflow": {"yfinance", "alpha_vantage", "sec_edgar"},
    "get_income_statement": {"yfinance", "alpha_vantage", "sec_edgar"},
    "get_macro_indicators": {"fred"},
}
_REPLAY = ContextVar("routed_tool_replay", default=None)


class EvidenceReplayError(RuntimeError):
    """A requested tool call cannot be fulfilled from the selected evidence."""


def request_key(method, args, kwargs):
    return _encode({"method": method, "args": list(args), "kwargs": kwargs})


def validate_policy(policy):
    if not isinstance(policy, dict):
        raise ValueError("evidence_tool_providers must be a method-to-provider-list mapping")
    for method, providers in policy.items():
        if method not in TOOL_PROVIDERS or not isinstance(providers, list) or any(
            p not in TOOL_PROVIDERS[method] for p in providers
        ):
            raise ValueError("unsupported evidence tool/provider policy")
    return {method: sorted(set(providers)) for method, providers in policy.items()}


@contextmanager
def replay_tools(store, evidence_ids):
    """Select exact response IDs; conflicting responses for one request are rejected.

    Arguments must match positional/keyword form, not merely meaning. This context
    intercepts routed tools; it does not sandbox arbitrary direct network calls.
    """
    responses = {}
    for evidence_id in evidence_ids:
        record = store.get(evidence_id, purpose="analysis")
        if record["tool"] != "routed_tool_response":
            raise EvidenceReplayError("not a routed tool response")
        payload = record["payload"]
        if payload.get("schema_version") != 1 or payload.get("method") not in TOOL_PROVIDERS:
            raise EvidenceReplayError("unsupported tool response schema")
        if payload.get("provider") not in TOOL_PROVIDERS[payload["method"]] or not isinstance(payload.get("text"), str):
            raise EvidenceReplayError("invalid tool response")
        key = request_key(payload["method"], payload["args"], payload["kwargs"])
        if key in responses and responses[key] != payload["text"]:
            raise EvidenceReplayError("conflicting responses; select one evidence ID per request")
        responses[key] = payload["text"]
    token = _REPLAY.set(responses)
    try:
        yield
    finally:
        _REPLAY.reset(token)


def replay_response(method, args, kwargs):
    responses = _REPLAY.get()
    if responses is None:
        return False, None
    key = request_key(method, args, kwargs)
    if key not in responses:
        raise EvidenceReplayError("tool call is absent from selected evidence; live fallback disabled")
    return True, responses[key]


def require_live_mode():
    if _REPLAY.get() is not None:
        raise EvidenceReplayError("direct vendor routing is disabled during tool replay")
