# Sections: who builds what

Eight sections plus the lead. Each section owns a set of paths that **no other section edits** except by pull request with that owner's review. See the [team ownership diagram](../diagrams/team-ownership.html).

| # | Section | Doc | Builds against | First deliverable |
|---|---|---|---|---|
| 0 | Lead: contracts, connector kit, agent | [00-lead](00-lead.md) | — | OpenAPI + schemas + kit skeleton |
| 1 | Map frontend | [01-map-frontend](01-map-frontend.md) | GeoJSON fixtures | FIRMS fixture on the map with legend + popup |
| 2 | Analysis UI | [02-analysis-ui](02-analysis-ui.md) | OpenAPI mocks | Mocked job with staged progress + evidence cards |
| 3 | Go API | [03-go-api](03-go-api.md) | OpenAPI, migrations | `POST`/`GET /v1/analyses` against Postgres |
| 4 | Fire connectors | [04-fire-connectors](04-fire-connectors.md) | Connector kit, fixtures | FIRMS connector passing the shared suite |
| 5 | Weather/env connectors | [05-weather-connectors](05-weather-connectors.md) | Connector kit, fixtures | NWS forecast connector passing the suite |
| 6 | Satellite analysis | [06-satellite-analysis](06-satellite-analysis.md) | Kit `compute` path | NDVI before/after for a fixed polygon |
| 7 | Platform + data infra | [07-platform-data-infra](07-platform-data-infra.md) | — | `make dev` with all health checks green |
| 8 | Evidence + evaluation | [08-evidence-evaluation](08-evidence-evaluation.md) | Evidence schema, fixtures | Confidence-label rules over fixture evidence |

## Path ownership (no overlaps)

| Path | Owner |
|---|---|
| `contracts/**` | Lead |
| `apps/worker/pyproject.toml`, `apps/worker/src/inland_worker/{__main__.py,contracts,kit,data,agent,jobs}/**`, `apps/worker/config/providers.yaml` | Lead |
| `apps/web/*` (root config), `apps/web/src/{app,map}/**` | S1 |
| `apps/web/src/{analysis,api}/**` | S2 (`api/generated/` is generated, never hand-edited) |
| `apps/api/**` | S3 |
| `apps/worker/src/inland_worker/connectors/fire/**` + its tests and fixtures | S4 |
| `apps/worker/src/inland_worker/connectors/weather/**` + its tests and fixtures | S5 |
| `apps/worker/src/inland_worker/satellite/**`, `apps/worker/tests/satellite/**` | S6 |
| `infrastructure/**`, `database/**`, `Makefile`, `.github/**`, `.env.example`, `apps/worker/src/inland_worker/ingest/**` | S7 |
| `apps/worker/src/inland_worker/{evidence,reports}/**`, `apps/worker/eval/**`, `docs/evaluation.md` | S8 |
| `docs/adr/**`, `docs/connectors/{connector-guide,provider-spec-template}.md`, `docs/diagrams/**`, `docs/architecture.md`, `docs/safety-model.md` | Lead |
| `docs/connectors/providers/<p>.md` | That provider's section |
| `docs/onboarding.md`, `CONTRIBUTING.md` | S7 |

Shared files everyone *adds to* but the lead reviews: `providers.yaml`, `contracts/**`. Changes to either need a PR labelled `contract-change`.

## Order of work

```text
Week 1   Lead: contracts v0 + kit skeleton        S7: repo, compose, CI, first migrations
         S1, S2: build on fixtures/mocks          S3: routes on migrations
         S4, S5: provider specs + fixture recording (docs first)
         S6: Earth Engine auth + formula unit tests    S8: rules on fixture evidence
Week 2   Kit usable → S4/S5 connectors pass the shared suite
         Go ↔ Redis ↔ worker fixture job end to end (Milestone 1 exit)
Week 3+  Milestone 2 live fire data → Milestone 3 satellite → Milestone 4 agent
```

**Nobody waits on anybody.** Frontend uses OpenAPI mocks, connectors use recorded fixtures, the worker runs in `INLAND_DATA_MODE=fixture`.

## Pairing (spec §16, rotate every ~2 weeks)

- Lead + S3: public API and security boundary
- S1 + S4: normalized geography renders correctly
- S2 + S6: calculations become understandable evidence
- S5 + S7: ingest scheduling and cache tables
- S8 + Lead: verification rules inside the agent

## Every ticket uses the spec §17 format

Outcome · Input · Output · Files · Depends on · Acceptance · Fixture · Success test · Failure/empty test · 2-minute demo. Keep tickets to 1–2 days.

## Definition of done (spec §25)
Acceptance criteria pass · automated tests pass · no secrets in code, fixtures or logs · input/output match the schemas · failure and empty paths implemented · user-facing data shows source + timestamp · limitations visible · docs updated · a teammate can run and demo it · reviewed and merged.
