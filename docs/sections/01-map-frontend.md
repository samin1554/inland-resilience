# Section 1: Map frontend

**Stack:** React, TypeScript, Vite, MapLibre GL JS, Tailwind, Vitest, React Testing Library · **Pairs with:** S4

## Scope
App shell, MapLibre integration, San Bernardino default view, polygon drawing, layer panel (visibility + ordering), legends, popups. Renders the layers returned by `GET /v1/analyses/{id}/layers`, including API-proxied Earth Engine tiles ([ADR-005](../adr/ADR-005-gee-tile-access.md)).

Not in scope: analysis form, progress, evidence cards (S2); any provider calls (never from the browser).

## Owned paths
`apps/web/*` (package.json, vite/ts/tailwind config) · `apps/web/src/app/**` · `apps/web/src/map/**`

## Contracts you consume
`evidence.schema.json` (GeoJSON geometry + properties) · layers response in `openapi.yaml` · fixtures in `contracts/examples/`.

## First tickets

**S1-1 Map shell.** *Outcome:* the app opens on San Bernardino County. *Input:* none. *Output:* full-width map, county boundary from `database/fixtures/sb_county_boundary.geojson`. *Acceptance:* loads at `localhost:5173`, boundary visible, zooms to extent. *Failure test:* missing fixture shows an error banner, not a blank map. *Demo:* open the app.

**S1-2 FIRMS fixture layer** (the spec §16 first deliverable). *Input:* FIRMS evidence fixture. *Output:* point layer + legend + popup showing source, observed/retrieved time, confidence, FRP, limitation. *Acceptance:* the popup shows *"A thermal anomaly is not an officially confirmed wildfire."* *Empty test:* zero points shows an "No detections in this window" legend state.

**S1-3 Draw polygon.** *Output:* drawn GeoJSON polygon handed to S2's form state. *Acceptance:* polygons outside the county boundary are visibly rejected client-side (Go re-validates). *Failure test:* self-intersecting polygon shows an error.

**S1-4 Layer panel.** Toggle and reorder boundary, FIRMS, WFIGS, CAL FIRE, and placeholder raster layers.
