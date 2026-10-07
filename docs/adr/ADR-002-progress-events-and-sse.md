# ADR-002: Progress events stream and SSE delivery

## Status
Accepted (Sep 23, 2026)

## Context
Spec §7: Python publishes progress, and Go streams it to React via SSE. The spec names Redis Streams but not the stream layout, and doesn't say how SSE works if more than one Go instance runs, or how a browser that reconnects catches up.

## Decision
- Two streams: `jobs` (Go → worker commands) and `job-events` (worker → Go progress). A per-job stream (`job-events:{job_id}`) was considered; see below.
- Every event matches a versioned JSON Schema `contracts/job-event.schema.json`: `{job_id, seq, status, progress, stage, message, at}`.
- Each Go instance reads `job-events` with **plain `XREAD` (fan-out, no consumer group)** and forwards events to its own SSE subscribers for that `job_id`. Every instance sees every event, so any instance can serve any browser.
- SSE `id:` = `seq`. On reconnect with `Last-Event-ID`, Go first replays from `analysis_jobs` (current status) and any events newer than that ID, then resumes live.
- `job-events` is trimmed with `MAXLEN ~ 100000`.

## Alternatives considered
- **Per-job streams:** easy replay per job, but many small streams and a key-cleanup chore.
- **Postgres LISTEN/NOTIFY:** fewer moving parts, but payload limits and no replay.
- **WebSockets:** rejected by the spec (one-way progress is enough).

## Consequences
- Positive: horizontal scaling of Go is safe; browser reconnects are lossless within the trim window.
- Negative: every Go instance processes all events (fine at this scale; revisit at thousands of concurrent jobs).

## Amendment (Oct 2026): event order on (re)connect
The API sends, all in increasing `seq`: (1) events from `job-events` the client hasn't seen (after `Last-Event-ID`,
older than the database state), (2) the current state from the database as an event with `id` = its
`last_event_seq`, (3) live events newer than that, closing the stream after a terminal status. Clients keep the
highest `seq` and ignore repeats. The worker bumps `analysis_jobs.last_event_seq` in the same UPDATE as each
status change, so the snapshot and the stream always agree.

