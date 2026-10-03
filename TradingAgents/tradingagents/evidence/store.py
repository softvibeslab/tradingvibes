"""Content-addressed JSON evidence with atomic writes and purpose isolation.

Callers must have permission to archive a payload. No network, credentials or
provider configuration are captured automatically. This is data replay, not LLM
or whole-graph replay.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path
from uuid import uuid4

from tradingagents.dataflows.files import locked

_ID = re.compile(r"[0-9a-f]{64}\Z")
_RUN = re.compile(r"[A-Za-z0-9_-]{1,128}\Z")
_PURPOSES = {"analysis", "outcome"}


def _validate_json(value):
    if isinstance(value, dict):
        for key, child in value.items():
            if not isinstance(key, str):
                raise TypeError("JSON object keys must be strings")
            _validate_json(child)
    elif isinstance(value, list):
        for child in value:
            _validate_json(child)
    elif value is not None and not isinstance(value, (str, bool, int, float)):
        raise TypeError("evidence values must be native JSON types")


def _encode(value: dict) -> bytes:
    _validate_json(value)
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
                      allow_nan=False).encode("utf-8")


def _hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class EvidenceStore:
    """A local store; run references are separate immutable files, never a shared index."""

    def __init__(self, root: str | Path):
        self.root = Path(root)

    def _object(self, evidence_id: str) -> Path:
        if not isinstance(evidence_id, str) or not _ID.fullmatch(evidence_id):
            raise ValueError("invalid evidence ID")
        return self.root / "objects" / evidence_id[:2] / f"{evidence_id}.json"

    def _run(self, run_id: str) -> Path:
        if not isinstance(run_id, str) or not _RUN.fullmatch(run_id):
            raise ValueError("invalid run ID")
        return self.root / "runs" / run_id

    @staticmethod
    def _write_once(path: Path, data: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with locked(path):
            if path.exists():
                if path.read_bytes() != data:
                    raise ValueError("existing evidence differs; refusing to overwrite")
                return
            temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
            try:
                with temporary.open("xb") as handle:
                    handle.write(data)
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(temporary, path)
            finally:
                temporary.unlink(missing_ok=True)

    def put(self, *, run_id: str, tool: str, payload: dict, purpose: str = "analysis") -> str:
        """Archive an explicitly supplied JSON payload and attach it to a run.

        Identical content deduplicates. A crash between writes can leave an
        unreferenced complete object; retrying the same put safely links it.
        """
        run_path = self._run(run_id)
        if purpose not in _PURPOSES:
            raise ValueError("purpose must be analysis or outcome")
        if not isinstance(tool, str) or not tool.strip():
            raise ValueError("tool name must be nonempty")
        if not isinstance(payload, dict):
            raise TypeError("payload must be a JSON object")
        data = _encode({"schema_version": 1, "purpose": purpose, "tool": tool, "payload": payload})
        evidence_id = _hash(data)
        self._write_once(self._object(evidence_id), data)
        reference = _encode({"schema_version": 1, "run_id": run_id, "evidence_id": evidence_id})
        self._write_once(run_path / f"{evidence_id}.json", reference)
        return evidence_id

    def get(self, evidence_id: str, *, purpose: str = "analysis") -> dict:
        """Read and verify stored bytes; never fall back to a live provider."""
        if purpose not in _PURPOSES:
            raise ValueError("purpose must be analysis or outcome")
        data = self._object(evidence_id).read_bytes()
        if _hash(data) != evidence_id:
            raise ValueError("evidence integrity check failed")
        record = json.loads(data)
        if record.get("schema_version") != 1:
            raise ValueError("unsupported evidence schema")
        if record.get("purpose") != purpose:
            raise ValueError("evidence purpose mismatch")
        return record

    def for_run(self, run_id: str, *, purpose: str = "analysis") -> list[dict]:
        """Verified records of one purpose, ordered by ID (not invocation order)."""
        if purpose not in _PURPOSES:
            raise ValueError("purpose must be analysis or outcome")
        records = []
        for path in sorted(self._run(run_id).glob("*.json")):
            reference = json.loads(path.read_bytes())
            if reference != {"schema_version": 1, "run_id": run_id, "evidence_id": path.stem}:
                raise ValueError("invalid run evidence reference")
            # Validate integrity even for records of a different purpose.
            data = self._object(path.stem).read_bytes()
            if _hash(data) != path.stem:
                raise ValueError("evidence integrity check failed")
            record = json.loads(data)
            if record.get("schema_version") != 1 or record.get("purpose") not in _PURPOSES:
                raise ValueError("unsupported evidence record")
            if record["purpose"] == purpose:
                records.append(record)
        return records
