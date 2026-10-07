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
- Cancel latency equals the longest single stage (a satellite imagery read). Acceptable.

## Amendment (Oct 2026): learned from the full-stack demo
- **Evidence idempotency key** is `(job_id, evidence.id)`, not `(job_id, source, source_record_id)`: computed
  evidence (dNBR, NDVI, agent inference) has no `source_record_id`, while `evidence.id` is already deterministic
  (`Evidence.stable_id`) for every item, and the agent's own inference uses one id per job.
- **Lost `jobs` messages:** if Go inserted the row but the `XADD` failed, the job would stay `queued` forever. A worker
  sweep re-enqueues `queued` jobs older than a few minutes, so Go still never writes status after the insert
  ([ADR-004](ADR-004-job-status-single-writer.md)). Duplicates are harmless: a worker skips a job another worker
  holds (fresh `updated_at` lease) or that is already terminal.
- **Leases:** while a job runs, the worker refreshes `analysis_jobs.updated_at` and `XCLAIM`s its own message, so the
  reaper only reclaims jobs whose worker really stopped. Attempts are counted in `analysis_jobs.attempts`.

