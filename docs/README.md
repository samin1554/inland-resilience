# Inland Resilience Agent: design docs

Start here. Source spec: `Inland_Resilience_Agent_Project_Spec.md` (Sep 23, 2026).

## Diagrams (`diagrams/`, open the `.html` in a browser; `.svg` for slides and docs)
| Diagram | Shows |
|---|---|
| [architecture](diagrams/architecture.html) | Three apps, stores, providers, trust boundaries |
| [request-lifecycle](diagrams/request-lifecycle.html) | One analysis request, end to end |
| [agent-workflow](diagrams/agent-workflow.html) | Controlled agent flow + confidence vocabulary |
| [database-schema](diagrams/database-schema.html) | Core PostGIS tables and FKs |
| [job-state-machine](diagrams/job-state-machine.html) | `analysis_jobs.status` transitions |
| [ingestion-pipeline](diagrams/ingestion-pipeline.html) | Hybrid ingestion through the connector kit |
| [team-ownership](diagrams/team-ownership.html) | Which section owns which component |

## For everyone
- [Sections: who builds what](sections/README.md): ownership, order of work, pairing, definition of done
- [Architecture decisions](adr/README.md)

## For data work
- [Connector guide](connectors/connector-guide.md): how to add a provider and how to read data
- [Provider spec template](connectors/provider-spec-template.md) and [provider specs](connectors/providers/)
