# Evidence storage: first F3 delivery

`EvidenceStore` is an explicit local JSON archive. It is disabled by default; the price-capture opt-in is described below. It does
not capture HTTP requests, API keys or model output. Archive
only payloads whose provider terms permit local retention. JSON payloads supplied
by callers are not automatically redacted; use normalized data, not HTTP headers,
provider configuration, credentials or full request URLs.

```python
from tradingagents.evidence import EvidenceStore
from tradingagents.evidence.prices import archive_prices, replay_prices

store = EvidenceStore("./results/evidence")
evidence_id = archive_prices(store, history, run_id=manifest["run_id"])
restored = replay_prices(store, evidence_id)
assert restored == history
```

Here `history` is a `PriceHistory` returned by the typed price API and `manifest`
is the current analysis manifest. No active run is assumed or created by this API.
The caller explicitly supplies the run ID. Outcome evidence must use
`purpose="outcome"` on both write and read. Default analysis reads reject outcome
objects; listing a run separates the two purposes. This is an accidental-mixing
guard, not access control or a proof of historical data availability.

Objects are canonical JSON named by SHA-256. Reads verify the stored bytes before
returning data. Full precision prices, retrieval time, cutoff and calendar metadata
survive a typed round trip. Replay never queries a provider on a cache miss;
missing/corrupt objects raise errors. This reconstructs normalized price data,
not original vendor payloads, an LLM response or an entire graph execution.

Each run has one immutable reference file per distinct object. This avoids a
shared mutable index: identical writes deduplicate, different concurrent writes
retain separate references. Files are created under an exclusive writer lock,
flushed, fsynced and atomically replaced; existing differing content is rejected.
A crash before reference creation can leave an orphan complete object; retrying
the same write links it. The implementation targets a local filesystem with
working file locks and atomic rename; directory entries are not explicitly
fsynced, so it does not claim power-loss durability on every filesystem.

The storage directory must be trusted and writable only by appropriate users.
Hashes detect accidental modification, not malicious replacement of both objects
and references. The store is not an append-only security boundary. Run IDs and
object IDs are validated to avoid path traversal through API parameters.

Remaining F3 work: capture of other families, tool invocation start ordering,
raw response permissions, replay routing,
fundamental/macro payload schemas, schema migration, indexing/Parquet/DuckDB,
retention management, and full graph reproducibility. The archive does not make
unknown publication timestamps known or remove corporate-action revision bias.

Local validation after capture integration: 1,206 tests and 91 subtests passed; one integration test
deselected under the offline policy. Ruff passed.

## Opt-in capture during analysis

To capture normalized prices automatically, set an explicit provider allowlist
on the configuration passed to `TradingAgentsGraph` (or `analysis_run`):

```python
config["evidence_price_providers"] = ["yfinance"]
```

The default is `[]`: no price payload is retained. Add a provider only when its
terms and your account permit retaining these normalized prices. This option does
not grant retention rights. Unlisted providers may still serve analyses but are
not archived. Objects and references are stored at `<results_dir>/evidence`.

Within an active analysis run, successful stock-tool, snapshot and typed-price
queries are captured after validation. The instant API records its final cutoff.
Settlement queries are tagged `outcome`, including the benchmark. The manifest
records the allowlist and a `price_evidence` sequence containing hashes, purposes,
providers and symbols. The sequence reflects capture completion order, not tool
start order. Repeated identical objects can have multiple manifest entries.

Each capture checkpoints the manifest under a run-local lock. Requested capture
failures raise `EvidenceCaptureError`, including during settlement; they do not
silently trigger another vendor or present the analysis as fully recorded. The
failed run retains its failure class. A crash after object creation but before a
manifest checkpoint can leave an orphan object or run reference; this is not a
transaction across all files. Existing evidence is not garbage-collected.

Capture context is scoped to the run and restored on exit. LangGraph propagates
context to its tool tasks; custom thread pools must explicitly copy context.
Calls outside an active analysis run continue without automatic capture. No raw
HTTP responses, other data families or LLM messages are captured in this delivery.
