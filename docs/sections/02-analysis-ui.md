# Section 2: Analysis UI

**Stack:** React, TypeScript, TanStack Query, Plotly, Vitest, a few Playwright tests · **Pairs with:** S6

## Scope
Analysis form (question, analysis type, date range, area from S1), job-progress display over SSE, evidence cards (spec §23 fields), limitations panel, charts, report view, and the typed API client wrapper. All empty, loading, partial, stale and error states.

## Owned paths
`apps/web/src/analysis/**` · `apps/web/src/api/**` (`api/generated/` comes from `openapi.yaml` and is never hand-edited)

## Contracts you consume
`openapi.yaml` (generate the client + a mock server, e.g. Prism or MSW) · `job-event.schema.json` · `evidence.schema.json`

## First tickets

**S2-1 Mocked analysis flow** (spec §16 first deliverable). *Input:* form submission. *Output:* `POST /v1/analyses` to the mock, then staged progress from mocked SSE events. *Acceptance:* all nine job states render with distinct labels. *Failure test:* `failed` shows `error_message`; `cancelled` shows a neutral state.

**S2-2 Evidence card.** *Output:* card showing category, source, observed time, retrieved time, measurements + units, quality flags, limitations, source link. *Acceptance:* `agent_inference` cards are visually distinct and labelled "Inference"; `stale_snapshot` shows a stale badge. *Empty test:* no evidence shows "Insufficient evidence", never "nothing found".

**S2-3 Confidence label chip.** Shows one of Unverified detection / Corroborated signal / Officially reported / Insufficient evidence. Never a percentage (spec §15).

**S2-4 SSE reconnect.** Uses `Last-Event-ID`; a dropped connection resumes without losing stages ([ADR-002](../adr/ADR-002-progress-events-and-sse.md)).
