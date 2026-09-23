# Architecture Decision Records

| ADR | Title | Status |
|---|---|---|
| [001](ADR-001-hybrid-ingestion.md) | Hybrid ingestion through a worker `--mode=ingest` | Proposed, agreed in discussion |
| [002](ADR-002-progress-events-and-sse.md) | Progress events stream and SSE delivery | Proposed |
| [003](ADR-003-job-retries-and-cancellation.md) | Job retries, dead-letter and cancellation | Proposed |
| [004](ADR-004-job-status-single-writer.md) | Single writer for `analysis_jobs.status` | Proposed |
| [005](ADR-005-gee-tile-access.md) | Earth Engine tile access through the API | Proposed |
| [006](ADR-006-cache-and-snapshots.md) | Cache and last-known-good snapshot tables | Proposed |
| [007](ADR-007-llm-provider.md) | LLM provider for the agent | **Open** |
| [008](ADR-008-authentication.md) | Authentication | **Open** |

"Proposed" means a recommendation ready for the lead to accept. "Open" means options only; no recommendation is final.
Spec §26 says the core architecture must not change without an explicit decision. These records are those decisions.
