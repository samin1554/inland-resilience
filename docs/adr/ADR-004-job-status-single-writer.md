# ADR-004: Single writer for `analysis_jobs.status`

## Status
Accepted (Sep 23, 2026)

## Context
Go creates the job row; Python advances it. If both update `status`, the result is race conditions and states that go backwards.

## Decision
- **Go writes exactly once:** it inserts the row with `status='queued'`. After that it only reads, except for setting `cancel_requested_at` ([ADR-003](ADR-003-job-retries-and-cancellation.md)).
- **The worker owns all transitions after `queued`**, performed by one function `transition(job_id, from, to)` that runs `UPDATE ... WHERE status = :from` and fails if 0 rows change. Legal transitions follow the [state machine](../diagrams/job-state-machine.html).
- Every transition also publishes a `job-events` message ([ADR-002](ADR-002-progress-events-and-sse.md)), in that order: DB first, then the event.

## Consequences
- The DB is the source of truth; events are notifications. A lost event is repaired on SSE reconnect from the DB.
- The Go team never needs worker logic; the worker team never needs HTTP logic.
