# Evidence storage: first F3 delivery

`EvidenceStore` is an explicit local JSON archive. It is not enabled automatically
by agents, and does not capture HTTP requests, API keys or model output. Archive
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

Remaining F3 work: automatic capture with explicit retention policy, manifest
references and tool invocation ordering, raw response permissions, replay routing,
fundamental/macro payload schemas, schema migration, indexing/Parquet/DuckDB,
retention management, and full graph reproducibility. The archive does not make
unknown publication timestamps known or remove corporate-action revision bias.

Local validation: 1,195 tests and 91 subtests passed; one integration test
deselected under the offline policy. Ruff passed.
