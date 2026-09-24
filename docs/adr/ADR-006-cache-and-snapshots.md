# ADR-006: Cache and last-known-good snapshot tables

## Status
Accepted (Sep 23, 2026)

## Context
[ADR-001](ADR-001-hybrid-ingestion.md) needs somewhere to store fetched data; spec §15 requires serving the last valid dataset, labelled stale, when a refresh fails. The §10 schema has no tables for this.

## Decision

![Cache schema](../diagrams/cache-schema.svg)

Add three tables (migrations owned by Section 7, reviewed by the lead):

| Table | Purpose | Key columns |
|---|---|---|
| `provider_fetches` | One row per fetch attempt (scheduled or live) | `id, provider_id, cache_key, status, error_code, started_at, completed_at, item_count, is_last_good` |
| `cached_evidence` | Normalized evidence produced by a fetch | same columns as `evidence_items` minus `job_id`, plus `fetch_id`, `cache_key`, `expires_at` |
| `reference_layers` | Reference geometries (county boundary, historical perimeters) | `name, version, geometry, properties jsonb, fetched_at, source_updated_at` |

- A successful fetch marks itself `is_last_good=true` for its `cache_key` and clears the flag on the previous one.
- When a job uses cached data, `inland_data` **copies** the items into `evidence_items` for that job, so job evidence is immutable even after the cache is pruned.
- Pruning: keep the last-good fetch plus 7 days of history per `cache_key` (proposed).
- Geometry indexes: GiST on all geometry columns.

## Alternatives considered
- Redis as the cache: fast, but no spatial queries and no durable last-good.
- Object storage for raw responses: useful for debugging, but not queryable. Possible later addition.

## Consequences
Evidence is stored twice (cache + per-job copy). That's accepted for provenance: a finished analysis must always show exactly what it used.
