# ADR 0001: Reproducible research before new providers

Status: accepted for the initial implementation slice.

The root repository owns CI; the Python project lives under `TradingAgents/`.
The nested upstream checkout is local metadata, not a submodule dependency.
CI therefore lives in the root `.github/workflows/` and runs in `TradingAgents/`.

Keep the current analysis graph, default vendors and rating evaluator. Start with
locked environments and durable run metadata. Do not add broker execution or
change rating interpretation in this slice.

Use a checked-in `uv.lock` for core, development, Bedrock and audit dependencies.
Audit tooling is a dependency group, not a runtime requirement. CI tests Python
3.11–3.14, includes the existing non-UTC test and uses a separate clean core install.

Each API `propagate` or CLI analysis attempt writes a schema-v1 manifest under
`results_dir/runs/<uuid>/manifest.json`. This is independent of graph checkpoints:
a resume is a new attempt; automatic parent/resume linkage is not implemented.
Atomic replacement prevents partially written JSON. A hard process kill can leave
status `running`; do not interpret that as evidence a process is still alive.

Metadata uses an allowlist and excludes endpoints, keys, paths and exception text.
Source hashes describe Python source templates, not rendered prompts. The resolved
model and effective prompt hashes remain explicitly unknown. Installed dependency
versions plus the lock hash identify the environment but do not ensure deterministic
LLM responses. Initial and final-state memory context hashes are distinct: on checkpoint resume,
the restored graph context may differ from newly prepared memory. The actual
context hash remains unknown until returned in the final state.

Persistence failures before analysis fail visibly; finalization errors during an
analysis failure must not replace the original exception. Research outputs and
broker execution remain separate. No real or paper orders are introduced.

Next slices: a typed evidence contract, shared price access, immutable evidence
and replay, then evaluation and data-provider comparisons. Budget and provider
credentials do not block implementation against synthetic fixtures.
