# ADR-005: Earth Engine tile access through the API

## Status
Accepted (Sep 23, 2026) · **Amended by [ADR-009](ADR-009-imagery-without-earth-engine.md)** (Sep 24, 2026): the MVP uses no Earth Engine. The API serves worker-rendered overlays from object storage; the tile route stays reserved for tiled output later. The principle stands: the browser never calls imagery providers.

## Context
Earth Engine map layers (true colour, NDVI change, dNBR) are served as tile URLs that include a temporary token and expire. The spec says the browser must not call providers directly (§6), yet it needs tiles.

## Decision
- The worker stores **layer metadata** (map ID, visualisation params, bounds, expiry) as an `artifacts` row of type `tile_layer`, not the raw URL.
- `GET /v1/analyses/{id}/layers` returns API-relative tile templates: `/v1/tiles/{layer_id}/{z}/{x}/{y}.png`.
- The Go API proxies tile requests to Earth Engine (allowlisted host only), with a short cache. If the Earth Engine map ID has expired, Go asks the worker to regenerate it (TODO: a small internal `refresh_tile_layer` job type).
- Static before/after PNG thumbnails are also saved to object storage so reports never depend on live tiles.

## Alternatives considered
- **Hand the Earth Engine URL to the browser:** simplest, but it breaks the "no browser → provider" rule, leaks tokens, and URLs expire mid-session.
- **Pre-render COG tiles to object storage:** robust but heavy; conflicts with "don't download and serve raw archives".

## Consequences
- Go gains a tile-proxy route (Section 3). Earth Engine quota usage becomes visible in one place.
- Adds latency per tile. Mitigated by caching.
