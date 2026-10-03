"""Versioned reconstruction of typed SEC statements and FRED observations."""
from dataclasses import asdict
from datetime import date, datetime

from tradingagents.dataflows.fundamentals import (
    FundamentalStatement,
    MacroObservation,
    MacroSeriesResult,
    StatementColumn,
    StatementRow,
)


def _json_value(value):
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, dict):
        return {k: _json_value(v) for k, v in value.items()}
    if isinstance(value, (tuple, list)):
        return [_json_value(v) for v in value]
    return value


def encode_fundamental(result):
    if isinstance(result, FundamentalStatement):
        kind = "statement"
    elif isinstance(result, MacroSeriesResult):
        kind = "macro_series"
    else:
        raise TypeError("unsupported structured evidence type")
    return {"kind": kind, "data": _json_value(asdict(result))}


def replay_fundamental(store, evidence_id, *, purpose="analysis"):
    """Rebuild the normalized object; legacy text-only evidence is not inferred."""
    record = store.get(evidence_id, purpose=purpose)
    if record["tool"] != "routed_tool_response":
        raise ValueError("not a routed tool response")
    structured = record["payload"].get("structured")
    if not structured or structured.get("kind") not in ("statement", "macro_series"):
        raise ValueError("no supported structured evidence; use text replay for legacy records")
    data = structured["data"]
    if data.get("schema_version") != 1:
        raise ValueError("unsupported structured evidence schema")
    data["as_of_date"] = date.fromisoformat(data["as_of_date"])
    data["retrieved_at"] = datetime.fromisoformat(data["retrieved_at"])
    if structured["kind"] == "statement":
        data["columns"] = tuple(StatementColumn(date.fromisoformat(c["period_end"]), c["span_label"])
                                for c in data["columns"])
        data["rows"] = tuple(StatementRow(r["label"], r["unit"], tuple(r["cells"])) for r in data["rows"])
        return FundamentalStatement(**data)
    data["vintage_date"] = date.fromisoformat(data["vintage_date"])
    data["observations"] = tuple(MacroObservation(date.fromisoformat(o["observation_date"]), o["value"])
                                 for o in data["observations"])
    return MacroSeriesResult(**data)
