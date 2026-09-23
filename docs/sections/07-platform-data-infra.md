# Section 7: Platform and data infrastructure

**Stack:** Docker Compose, PostgreSQL + PostGIS, Redis, MinIO (local S3), GitHub Actions, Make · **Pairs with:** S5

## Scope
Monorepo skeleton, `make dev/test/lint/fixtures/migrate/seed`, Docker Compose (web :5173, api :8080, worker, worker `--mode=ingest`, Postgres/PostGIS, Redis, MinIO), CI (TS, Go, Python lint + tests, schema validation, secret scan), database migrations (spec §10 + [ADR-003](../adr/ADR-003-job-retries-and-cancellation.md) + [ADR-006](../adr/ADR-006-cache-and-snapshots.md) tables), seeds, the ingest scheduler mode, onboarding docs.

## Owned paths
`infrastructure/**` (incl. Dockerfiles under `infrastructure/docker/`) · `database/**` · `Makefile` · `.github/**` · `.env.example` · `apps/worker/src/inland_worker/ingest/**` · `docs/onboarding.md` · `CONTRIBUTING.md`

## First tickets

**S7-1 `make dev`** (Milestone 0 exit). *Outcome:* a new teammate runs one command. *Acceptance:* all services start; `/health` is green for api and worker; no local Postgres/Redis install needed. *Failure test:* a missing `.env` prints which variables to set.

**S7-2 First migrations + seeds.** Spec §10 tables with PostGIS `geometry(Geometry, 4326)` + GiST indexes, plus `cancel_requested_at`; seed the county boundary fixture. *Acceptance:* `make migrate && make seed` is idempotent.

**S7-3 CI.** Lint + tests for all three apps; validate `contracts/examples`; fail on secrets in fixtures; PR template with the definition of done.

**S7-4 Cache tables + ingest mode.** `provider_fetches`, `cached_evidence`, `reference_layers`; a scheduler reading `ingestion.schedule` from `providers.yaml` and calling the kit. *Acceptance:* the FIRMS fixture refresh writes a `provider_fetches` row with `is_last_good`; a simulated failure keeps the previous snapshot.
