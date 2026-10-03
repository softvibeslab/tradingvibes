"""Atomic, credential-free manifests for CLI and programmatic analysis attempts."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import platform
import subprocess
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import UTC, datetime
from importlib.metadata import distributions
from pathlib import Path
from uuid import uuid4

logger = logging.getLogger(__name__)
_CURRENT: ContextVar[dict | None] = ContextVar("tradingagents_manifest", default=None)
_SETTING_KEYS = (
    "llm_provider", "deep_think_llm", "quick_think_llm", "output_language",
    "temperature", "max_tokens", "llm_max_retries", "max_debate_rounds",
    "max_risk_discuss_rounds", "max_tool_rounds", "max_recur_limit",
    "google_thinking_level", "openai_reasoning_effort", "anthropic_effort",
    "checkpoint_enabled", "holding_period_days", "benchmark_ticker",
    "price_max_missing_sessions",
)


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _public_value(value):
    # Only simple configuration values, never arbitrary objects or endpoints.
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str) and "://" not in value and len(value) <= 256:
        return value
    return None


def safe_settings(config: dict) -> dict:
    """Allowlist operational settings; do not serialize config or environment wholesale."""
    result = {key: _public_value(config[key]) for key in _SETTING_KEYS if key in config}
    for key in ("data_vendors", "tool_vendors", "benchmark_map", "price_calendars"):
        result[key] = {
            name: _public_value(value) for name, value in (config.get(key) or {}).items()
            if isinstance(name, str) and not any(
                part in name.lower() for part in ("secret", "password", "token", "api_key", "url")
            )
        }
    return result


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def source_metadata() -> dict:
    """Identify source content even when Git metadata is missing or nested.

    Git provenance uses the outer repository when this is a vendored checkout.
    Hashes describe source templates, not the effective runtime prompts.
    """
    package = Path(__file__).resolve().parents[1]
    project = package.parent
    result = {"commit": None, "dirty": None, "lock_sha256": None}
    lock = project / "uv.lock"
    if lock.is_file():
        result["lock_sha256"] = _digest(lock.read_bytes())
    digest = hashlib.sha256()
    for path in sorted(package.rglob("*.py")):
        digest.update(path.relative_to(package).as_posix().encode() + b"\0")
        digest.update(path.read_bytes() + b"\0")
    result["package_source_sha256"] = digest.hexdigest()
    root = project.parent if (project.parent / ".git").exists() else project
    if not (root / ".git").exists():
        return result
    try:
        result["commit"] = subprocess.check_output(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            stderr=subprocess.DEVNULL, text=True, timeout=3,
        ).strip()
        result["dirty"] = bool(subprocess.check_output(
            ["git", "-C", str(root), "status", "--porcelain", "--untracked-files=normal"],
            stderr=subprocess.DEVNULL, text=True, timeout=3,
        ).strip())
    except (OSError, subprocess.SubprocessError):
        pass
    return result


def current_run() -> dict | None:
    """The manifest of this context's analysis attempt, never process-global state."""
    return _CURRENT.get()


def _write(path: Path, manifest: dict) -> None:
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        with temporary.open("x", encoding="utf-8") as handle:
            json.dump(manifest, handle, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


@contextmanager
def analysis_run(config: dict, ticker: str, trade_date: str, analysts, portfolio=None, *, asset_type="stock"):
    """Track one attempt; interrupted processes retain a running manifest.

    A resumed graph starts a new attempt, not a fabricated continuation of the
    old manifest. Parent linkage is reserved for a future explicit resume API.
    """
    run_id = uuid4().hex
    path = Path(config["results_dir"]) / "runs" / run_id / "manifest.json"
    path.parent.mkdir(parents=True, exist_ok=False)
    manifest = {
        "schema_version": 1, "run_id": run_id, "parent_run_id": None,
        "status": "running", "started_at": _now(), "finished_at": None,
        "ticker": ticker, "analysis_date": trade_date, "asset_type": asset_type,
        "analysts": list(analysts),
        "settings": safe_settings(config), "source": source_metadata(),
        "python": platform.python_version(), "platform": platform.system(),
        "dependencies": dict(sorted(
            (d.metadata["Name"], d.version) for d in distributions() if d.metadata["Name"]
        )),
        "portfolio_sha256": (
            _digest(portfolio.model_dump_json().encode()) if portfolio is not None else None
        ),
        "memory_context_sha256": None, "initial_memory_context_sha256": None,
        "resolved_models": None, "effective_prompt_hashes": None,
    }
    _write(path, manifest)
    token = _CURRENT.set(manifest)
    try:
        from tradingagents.evidence.capture import capture_run

        with capture_run(config, manifest, lambda: _write(path, manifest)):
            yield manifest
    except BaseException as exc:
        manifest["status"] = "cancelled" if isinstance(exc, (KeyboardInterrupt, GeneratorExit)) else "failed"
        # Error messages can contain API keys, request headers and endpoints.
        manifest["error_type"] = type(exc).__name__
        manifest["finished_at"] = _now()
        try:
            _write(path, manifest)
        except OSError:
            logger.warning("Could not finalize run manifest %s", run_id)
        raise
    else:
        manifest["status"] = "completed"
        manifest["finished_at"] = _now()
        _write(path, manifest)
    finally:
        _CURRENT.reset(token)
