# Inland Resilience Agent

A geospatial analysis app for San Bernardino County. A user draws an area and asks a question, and gets an evidence-backed answer with map layers, charts, calculated indicators, source links and limitations. The first use case is historical wildfire impact: satellite imagery, official fire perimeters, FIRMS detections and weather.

> An analysis and research tool. **Not** an evacuation system, emergency-warning service or wildfire-prediction product.

## Architecture

![Architecture](docs/diagrams/architecture.svg)

| App | Stack | Owns |
|---|---|---|
| `apps/web` | React, TypeScript, Vite, MapLibre | Presentation |
| `apps/api` | Go, chi, pgx, SSE | Public API, validation, jobs |
| `apps/worker` | Python, LangGraph, Earth Engine | Data connectors, science, agent |

PostgreSQL + PostGIS · Redis Streams · S3-compatible storage.

## Start here

- **[Design docs](docs/README.md):** diagrams, ADRs, connector guide
- **[Sections: who builds what](docs/sections/README.md):** find your section, owned paths and first tickets
- **[Contributing](CONTRIBUTING.md)**

## Status
Design complete. Code starts at Milestone 0 (repo skeleton, `make dev`, contracts v0).
