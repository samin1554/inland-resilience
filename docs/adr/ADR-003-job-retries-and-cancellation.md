# ADR-003: Job retries, dead-letter and cancellation

## Status
Accepted (Sep 23, 2026)

## Context
Redis Streams consumer groups leave unacknowledged messages "pending" if a worker crashes. The spec lists a `cancelled` state but no way to tell a running worker to stop.

## Decision
- Workers consume `jobs` via consumer group `workers` and `XACK` only after the job reaches a terminal state.
- A reaper in each worker runs `XAUTOCLAIM` for messages idle > 10 min (proposed) and retries them. Delivery count > 3 → move to stream `jobs-dead`, mark the job `failed` with `error_code=RETRIES_EXHAUSTED`.
- Job handlers must be **idempotent per stage**: evidence writes are keyed by `(job_id, source, source_record_id)`, so a retry doesn't duplicate rows.
- **Cancellation:** `POST /v1/analyses/{id}/cancel` (new endpoint, contract change) sets `analysis_jobs.cancel_requested_at`. The worker checks it between stages (and between tool calls) and stops cleanly, then transitions to `cancelled` ([ADR-004](ADR-004-job-status-single-writer.md)).
- Per-job wall-clock limit (proposed 10 min for MVP) → `failed` with `error_code=TIMEOUT`.

## Alternatives considered
- Cancel via a Redis message to the specific worker: faster, but needs worker addressing. Polling a DB flag between stages is simpler, and stages are short.

## Consequences
- Needs one migration (`cancel_requested_at`) and one OpenAPI addition.
- Cancel latency equals the longest single stage (an Earth Engine call). Acceptable.
