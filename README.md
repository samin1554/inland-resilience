# Inland Resilience Agent

A geospatial analysis app for San Bernardino County. A user draws an area and asks a question, and gets an evidence-backed answer with map layers, charts, calculated indicators, source links and limitations. The first use case is historical wildfire impact: satellite imagery, official fire perimeters, FIRMS detections and weather.

> An analysis and research tool. **Not** an evacuation system, emergency-warning service or wildfire-prediction product.

## Architecture

![Architecture](docs/diagrams/architecture.svg)

| App | Stack | Owns |
|---|---|---|
| `apps/web` | React, TypeScript, Vite, MapLibre | Presentation |
| `apps/api` | Go, chi, pgx, SSE | Public API, validation, jobs |
| `apps/worker` | Python, LangGraph, Sentinel-2 via Earth Search | Data connectors, science, agent |

PostgreSQL + PostGIS · Redis Streams · S3-compatible storage.

### Who builds what

![Team ownership](docs/diagrams/team-ownership.svg)

### How data comes in

![Ingestion pipeline](docs/diagrams/ingestion-pipeline.svg)

All seven diagrams: [docs/README.md](docs/README.md#diagrams).

## Run it with Docker (any machine)

The only requirement is [Docker Desktop](https://docs.docker.com/get-docker/). No Python, keys or accounts are needed to start.

```bash
git clone https://github.com/<you>/inland-resilience.git   # your fork, or the main repo if you're a collaborator
cd inland-resilience
make docker-test          # all offline tests inside the container
make demo-line-fire       # real satellite demo → docs/research/line-fire-2024/output/
make docker-fetch PROVIDER=wfigs_current ARGS="--bbox=-124.5,32.5,-114.1,42.0"   # live fire perimeters
```

No `make` (e.g. Windows)? Use the same commands directly:

```bash
docker compose -f infrastructure/docker-compose.yml run --rm --build worker-test
docker compose -f infrastructure/docker-compose.yml --profile demo run --rm --build line-fire-demo
docker compose -f infrastructure/docker-compose.yml run --rm --build worker fetch wfigs_current --bbox=-124.5,32.5,-114.1,42.0
```

Optional live data that needs a key (FIRMS): copy `.env.example` to `.env`, add **your own** free key, then `make docker-test-live`. See [who needs a key](docs/guides/start-here.md#6-api-keys-who-needs-one).

## Start here

- **New teammate? → [docs/guides/start-here.md](docs/guides/start-here.md)**
- **[Data catalog](docs/data-catalog.md):** every data source and how to get it
- **[Design docs](docs/README.md):** diagrams, ADRs, connector guide
- **[Sections: who builds what](docs/sections/README.md):** find your section, owned paths and first tickets
- **[Contributing](CONTRIBUTING.md)**

## Status
Design complete. Code starts at Milestone 0 (repo skeleton, `make dev`, contracts v0).
