# Section 3: Go API

**Stack:** Go `net/http`, chi, pgx, OpenAPI validation, structured logging, Go testing · **Pairs with:** Lead

## Scope
Public HTTP API (spec §8), request validation (geometry inside the supported region, polygon area and date-range limits), job creation (insert `queued` only, per [ADR-004](../adr/ADR-004-job-status-single-writer.md)), Redis `XADD` to `jobs`, SSE fan-out from `job-events` ([ADR-002](../adr/ADR-002-progress-events-and-sse.md)), cancel endpoint ([ADR-003](../adr/ADR-003-job-retries-and-cancellation.md)), tile proxy ([ADR-005](../adr/ADR-005-gee-tile-access.md)), rate limiting, signed artifact URLs, `/health`.

Not in scope: any calculation, LangGraph, provider calls (other than the allowlisted Earth Engine tile proxy).

## Owned paths
`apps/api/**`

## First tickets

**S3-1 Create + get analysis** (spec §16 first deliverable). *Input:* §8 create request JSON. *Output:* `{job_id, status:"queued", created_at}`; `GET /v1/analyses/{id}` returns the row. *Acceptance:* request validated against `openapi.yaml`; row in `analysis_jobs`; message on `jobs` matches `analysis-job.schema.json`. *Failure tests:* polygon outside the county → 422 with a clear code; date range over the limit → 422; unknown `analysis_type` → 422.

**S3-2 SSE events endpoint.** `GET /v1/analyses/{id}/events` streams `job-events` for that job with `id: seq`. *Acceptance:* two Go instances both serve events; reconnect with `Last-Event-ID` replays missed events.

**S3-3 Evidence + layers read endpoints.** Paginated `GET .../evidence`; `GET .../layers` returns API-relative tile templates.

**S3-4 Rate limiting + health.** Per-session limit on `POST /v1/analyses`; `/health` checks Postgres and Redis.

Open dependency: the session model depends on [ADR-008](../adr/ADR-008-authentication.md). Build it behind middleware.
