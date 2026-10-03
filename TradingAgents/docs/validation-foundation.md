# Foundation validation — 2026-10-03

Baseline source: workspace commit b71c5e2 (upstream snapshot 8b22d43).
Host: macOS arm64. No authenticated market-data or LLM calls.

## Baseline

Python 3.13: 1,138 passed, 2 failed, 1 integration test deselected, 91 subtests.
Both failures used `errno.EDEADLOCK` while mocking Windows locks on macOS.
Replaced it with the portable `EDEADLK` constant in implementation and tests.
Baseline Ruff passed.

## Foundation checks

- Full suite: Python 3.11, 3.12 and 3.14 each passed 1,148 tests and 91 subtests.
- Python 3.13 full suite with `TZ=America/New_York`: 1,148 passed and 91 subtests.
- One integration test deselected in each run; existing model-catalog warnings remain.
- Final asset-type propagation change: 33 relevant tests passed.
- Ruff passed; diff whitespace check passed; workflow YAML parsed.
- Clean non-editable core installation imports `tradingagents` and `cli.main`.
- pip-audit on locked application/dev/Bedrock dependencies: no known vulnerabilities.

These are local checks. Linux GitHub Actions status must be checked separately.
The lock resolves platform-specific packages; a local macOS pass does not establish
Windows behavior or vendor API compatibility. The audit reflects its database at
execution time, not a security guarantee.

## Scope delivered

Root CI, lock, audit group, run manifests, failure/cancellation tracking,
context isolation, config allowlisting, source/environment provenance and report IDs.

## Still pending in F1 and later phases

Effective runtime prompt hashes, resolved provider model versions and automatic
parent linkage on checkpoint resume are explicitly unknown in schema v1.
The manifest is not an evidence archive. F2 typed provider contracts, shared price
access, F3 replay, evaluation tooling and all new providers/brokers remain pending.
