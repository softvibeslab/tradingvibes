# Offline graph replay

Enable **both** options before recording a new analysis:

```python
config["evidence_llm_responses"] = True
config["evidence_graph_replay"] = True
config["checkpoint_enabled"] = False
```

For CLI analysis, set `TRADINGAGENTS_EVIDENCE_LLM_RESPONSES=true` and
`TRADINGAGENTS_EVIDENCE_GRAPH_REPLAY=true`, and use `--no-checkpoint`.
These options authorize retention of prompts, model outputs, tool responses,
initial memory lessons, instrument identity and rendered portfolio context.
Only enable them when retention of all those inputs is permitted. They are off
by default; per-provider capture allowlists remain separate from this explicit
whole-graph retention option.

After completion:

```bash
tradingagents replay --run-id <run_id> --results-dir /path/to/results
```

The command rebuilds and executes the analyst/debate/risk graph with archived
initial state, model outputs, tool-node results and pre-fetched sentiment inputs.
It compares the complete final state, excluding run IDs and generated message
IDs; tool-call IDs and contents remain significant. Exit status is zero only
when states match. The Python API is `tradingagents.evidence.run.replay_run`.

Replay does not create provider clients, resolve identity, settle earlier trades,
or write decisions into memory. Original artifacts are read-only. Source and
lock hashes must match. Missing evidence, corrupt objects, conflicting responses
and incompatible inputs fail without a live fallback. Existing runs lacking
initial/final graph evidence cannot be upgraded retroactively.

Scope: successful fresh graph executions, validated with offline fixtures in
both free-text and structured-output modes. Resumed checkpoints are rejected.
Provider exceptions that trigger structured-output fallback are not recorded as
invocations, so some otherwise successful runs can fail replay. Settlement before
initial-state creation is not re-executed. This verifies the graph against stored
inputs; it does not independently re-fetch or validate historical market facts.
Replay is not an OS network sandbox for arbitrary custom nodes. Normalization of
message inputs changed in this version; older individual LLM invocation archives
may require their original code for exact matching.
