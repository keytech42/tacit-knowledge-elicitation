# Cross-Cutting Behavior Testing

When adding a cross-cutting behavior (concurrency, retry, error tolerance, caching, batching) to multiple modules, test the behavior in EVERY module it touches — not just one representative example.

Each module has its own wiring and can fail independently. One "concept" test is not enough.

## Required coverage per module

For each module that gains the new behavior, write tests for:
- **Happy path**: the behavior works as intended
- **Edge cases**: n=0, n=1, boundary values
- **Failure modes**: partial failure, total failure, graceful degradation
- **The specific property**: e.g., concurrency limit is respected, retry count is honored

## Anti-pattern

Writing one test in one module and assuming the same pattern "obviously works" in sibling modules. It doesn't — gather/semaphore wiring, error handling scope, and result aggregation differ per call site.
