# ADR-001: Hybrid ingestion through a worker `--mode=ingest`

## Status
Proposed. Direction agreed by the lead in discussion (Sep 23, 2026).

## Context
The spec has every provider called per job (§7, §11). With 4+ people building connectors, that means:
- Common data (county boundary, historical perimeters, FIRMS for the county) is re-fetched for every analysis.
- Every job is exposed to provider slowness and outages.
- "Preserve the last known valid dataset when an upstream refresh fails" (§15) has no natural home.

## Decision
Classify every provider as `reference`, `near_real_time`, `on_demand` or `compute` in `providers.yaml` (see the [connector guide](../connectors/connector-guide.md#2-ingestion-classes)).
- `reference` and `near_real_time` providers are refreshed on a schedule by the **same Python worker image** started with `--mode=ingest`. It writes normalized evidence to PostGIS cache/snapshot tables ([ADR-006](ADR-006-cache-and-snapshots.md)).
- Jobs read through `inland_data.get_evidence()`: cache if fresh, else a live fetch, else the last-known-good snapshot flagged stale.
- `on_demand` and `compute` providers are fetched during jobs with a TTL cache.

This is a new **run mode**, not a new service: same codebase, same connectors, same contracts (respects §26 "do not introduce additional services").

## Alternatives considered
- **On-demand only (as specced):** simplest, but slow, fragile under outages, and repeats identical calls.
- **Separate ingestion service or Airflow/Dagster:** strong scheduling, but it's a new service, another language/runtime to learn, and overkill for ~7 providers.
- **Postgres `pg_cron` calling providers:** puts network I/O in the database; rejected.

## Consequences
- Positive: faster jobs, resilience to outages, stale handling in one place, connectors reused by both paths.
- Negative: one more process to deploy and monitor (the ingest mode container); cache tables to migrate and prune.
- Scheduler choice inside the mode: APScheduler, or a simple loop driven by `ingestion.schedule` from `providers.yaml` (Section 7 decides).

## Trade-offs
Freshness is now bounded by the schedule (e.g. FIRMS ≤30 min old) unless a job forces a live fetch. That's acceptable for an analysis tool that is explicitly not a warning system.
