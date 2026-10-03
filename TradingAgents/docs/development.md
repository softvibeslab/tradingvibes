# Development and run manifests

From the workspace root:

```sh
cd TradingAgents
uv sync --locked --extra dev --extra bedrock
uv run --no-sync pytest -q
uv run --no-sync ruff check .
```

`uv.lock` covers optional extras and the `security` group. `--locked` refuses a
stale lock; update intentionally with `uv lock`, inspect the diff and run checks.
CI uses uv 0.11.21 and tests supported Python versions separately. Local validation
on one interpreter does not substitute for that matrix.

To audit the resolved application dependencies (including development and Bedrock):

```sh
uv export --locked --all-extras --no-group security --no-hashes --no-emit-project --output-file /tmp/tradingagents-audit.txt
uv run --locked --group security pip-audit --disable-pip --no-deps -r /tmp/tradingagents-audit.txt
```

The audit queries a vulnerability service; it does not call financial or LLM APIs.
No vulnerabilities are suppressed by default. Audit failures need investigation,
not an automatic `--fix` or a blanket exception.

## Analysis attempts

The CLI and `TradingAgentsGraph.propagate()` automatically save:

```text
<results_dir>/runs/<run_id>/manifest.json
```

Manifests have schema version 1, timestamps in UTC, unique attempt IDs, status,
selected analysts, a configuration allowlist, Python/platform and installed package
versions, source/lock hashes, Git commit/dirty status when available, and context
fingerprints. A completed decision/report includes its run ID. Credentials,
provider URLs, local paths and exception messages are not metadata fields.

Failed attempts retain the exception class; interrupted attempts record cancellation.
A process killed without cleanup can leave `running`. Checkpoints still handle graph
resume; resume-to-parent linkage, resolved model versions and exact rendered prompt
hashes are not implemented yet and remain null. Direct use of low-level `stream_run`
is not automatically an analysis attempt; callers needing metadata can use the
`analysis_run` context manager around their complete custom lifecycle.

Manifests do not archive tool evidence or LLM responses. They are the first step
toward replay, not a claim of full reproducibility. Keep run artifacts out of Git.
