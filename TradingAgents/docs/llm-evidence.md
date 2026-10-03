# Optional LLM invocation evidence

Set `config["evidence_llm_responses"] = True` before creating a graph to wrap its
quick/deep models. The default is false. The wrapper captures successful invocations
only inside an active `analysis_run`; it supports normal messages, tool calls and
Pydantic structured results. It does not subscribe to any service or make additional
model requests.

Prompts, message contents, tool schemas, provider response metadata and outputs
are stored in `<results_dir>/evidence`. They may include portfolio and market data;
enable this option only where retaining that material is appropriate. This is not
a redaction pipeline. Request client objects, callbacks and raw provider configuration
are not serialized. The graph identifies its configured model settings through the
manifest allowlist and hashes the endpoint instead of recording its URL. Provider
resolved-model metadata, when present, remains in the response; the wrapper does
not infer missing model versions.

The manifest's `llm_evidence` list contains hashes and capture-completion sequence
numbers. Writes share the run lock with market-data capture. Storage or unsupported
encoding failures raise `EvidenceCaptureError`; structured-output and reflection
fallbacks do not swallow these errors. Failed provider invocations themselves are
not archived, so this is not a complete provider-error trace.

## Replaying selected invocations

```python
from tradingagents.evidence import EvidenceStore
from tradingagents.evidence.llm import RecordedModel, replay_llm

store = EvidenceStore("./results/evidence")
# Use exactly the identity and bindings recorded in the request.
record = store.get(evidence_id)
request = record["payload"]["request"]
model = RecordedModel(None, request["identity"], binding=request["binding"])
with replay_llm(store, [evidence_id]):
    answer = model.invoke(original_prompt)
```

For structured responses, bind the same caller-owned Pydantic schema with
`with_structured_output`, or pass it as the constructor's `schema`. Schemas/classes
are not imported or executed from stored data. Tool-bound models must preserve the
same schemas and binding options. Text, messages and schema data reconstruct from
verified JSON; missing, conflicting or incompatible evidence fails with no live
fallback through the wrapper. Different responses to an identical request require
explicit ID selection rather than an arbitrary choice.

Matching includes input messages, invocation kwargs, identity, tool/schema bindings
and caller-configurable model options. LangGraph `__pregel_*` scheduler keys and
checkpoint identifiers are excluded; they are execution plumbing, not provider
request settings. Message IDs are retained, so equivalent prompts with different
message IDs do not currently match. Callback/tag metadata is not part of the key.
Standalone users must supply a complete identity for their model configuration.

This does **not** yet replay an entire graph from a run ID. That requires stable
message/state identity, complete data-tool coverage, initial memory/portfolio state,
provider-error paths, and graph-level routing. A normal graph still creates model
clients and may need credentials. Use `RecordedModel(None, ...)` for offline
invocation replay. Arbitrary direct provider calls are not sandboxed. Streaming
uses Runnable's single-result default, not recorded provider token chunks.

Validation uses a simulated full graph with both text and structured responses,
plus exact invocation replay, tool-schema matching, configuration matching,
context cleanup and fail-closed storage tests. No live LLM calls are made.

Local validation: 1,243 tests and 91 subtests passed; Ruff passed. One live
integration test was excluded by the offline test policy.
