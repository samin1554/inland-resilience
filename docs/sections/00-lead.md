# Section 0: Lead (contracts, connector kit, agentic system)

**Owner:** Lead · **Reviewers:** S7 for kit/infra, S3 for OpenAPI

## Scope
- **Contracts:** `contracts/openapi.yaml`, `evidence.schema.json`, `analysis-job.schema.json`, `job-event.schema.json` ([ADR-002](../adr/ADR-002-progress-events-and-sse.md)), examples. Generated Pydantic models in `inland_worker/contracts/`.
- **Connector kit + `inland_data`:** see the [connector guide](../connectors/connector-guide.md). Base classes, allowlisted HTTP client, registry, cache/fixture machinery, shared test suite, `make new-connector`.
- **Job runtime:** Redis consumer, `transition()` ([ADR-004](../adr/ADR-004-job-status-single-writer.md)), progress events, retries/cancel ([ADR-003](../adr/ADR-003-job-retries-and-cancellation.md)).
- **Agentic system:** LangGraph graph (parse → validate scope → select tools → execute → verify → result/limitations), the approved-tool registry, guardrails, LLM interface ([ADR-007](../adr/ADR-007-llm-provider.md)).
- **Integration:** final merges, releases, security review.

Not in scope: the individual connectors (S4/S5), satellite math (S6), verification rule internals (S8).

## Owned paths
`contracts/**` · `apps/worker/pyproject.toml` · `apps/worker/src/inland_worker/{__main__.py,contracts,kit,data,agent,jobs}/**` · `apps/worker/config/providers.yaml` · `docs/adr/**` · `docs/connectors/connector-guide.md` · `docs/architecture.md` · `docs/safety-model.md`

## First tickets

**L-1 Contracts v0.** *Outcome:* every section can generate clients and validate payloads.
*Output:* `openapi.yaml` (§8 endpoints + cancel + tiles), three JSON Schemas, examples. *Acceptance:* examples validate in CI; TS client and Go types generate. *Failure test:* an invalid example fails CI. *Demo:* show the rendered OpenAPI and a failing validation.

**L-2 Kit skeleton + fixture mode.** *Outcome:* S4/S5 can start real connector work.
*Output:* `BaseConnector`, `ProviderQuery`, `RawResponse`, registry loading `providers.yaml`, fixture replay, and the shared suite running on a dummy connector. *Acceptance:* the dummy connector passes all suite tests offline; a non-allowlisted host is rejected. *Failure test:* timeout and 429 simulations. *Demo:* `make test-connector PROVIDER=dummy`.

**L-3 `inland_data.get_evidence` (cache-less v0).** *Outcome:* one call returns normalized evidence with `origin` and `freshness`.
*Depends on:* L-2. *Acceptance:* fixture mode returns items plus a `tool_executions` row. Cache comes with S7's tables.

**L-4 Fixture job runner.** *Outcome:* Milestone 1. A Redis job produces fixture evidence and progress events end to end.
*Depends on:* S3-1, S7-1. *Acceptance:* the job moves `queued → … → completed` with events visible over SSE.

**L-5 Agent skeleton** (after Milestone 1; spec §26 says no LangGraph before the slice works). Graph with scope validation and the approved-tool registry only; tools return fixtures.
