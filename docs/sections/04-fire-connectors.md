# Section 4: Fire data connectors

**Stack:** Python 3.12, Pydantic, the connector kit, pytest · **Pairs with:** S1

## Scope
Connectors on the lead's kit for: [NASA FIRMS](../connectors/providers/firms.md), [NIFC WFIGS current](../connectors/providers/wfigs.md), [CAL FIRE historical](../connectors/providers/calfire-historical.md), [SB County boundary](../connectors/providers/sb-county-boundary.md). You write `build_requests` + `parse` + fixtures + provider-specific tests; the kit handles HTTP, retries, caching and secrets. Read the [connector guide](../connectors/connector-guide.md) first.

## Owned paths
`apps/worker/src/inland_worker/connectors/fire/**` · `apps/worker/tests/connectors/fire/**` · `apps/worker/tests/fixtures/{firms,wfigs_current,calfire_historical,sb_county_boundary}/**` · `docs/connectors/providers/{firms,wfigs,calfire-historical,sb-county-boundary}.md`

## First tickets

**S4-1 FIRMS provider spec + fixtures.** Finish the TODOs in `firms.md`; record `success`, `empty`, `malformed`, `extra_fields`. *Acceptance:* the lead approves the spec; fixtures contain no key (CI secret scan passes).

**S4-2 FIRMS connector** (spec §16 first deliverable). *Input:* bbox + source + days. *Output:* `satellite_detection` evidence per row. *Acceptance:* the shared suite passes in fixture mode; `acq_date`+`acq_time` → UTC `observed_at`. *Empty test:* the `empty` fixture → `[]`. *Demo:* `make test-connector PROVIDER=firms`, then S1 renders the output.

**S4-3 SB County boundary connector.** ArcGIS JSON → GeoJSON; valid geometry; feeds `reference_layers` and the seed fixture used by S1 and S3.

**S4-4 WFIGS + CAL FIRE connectors.** Handle ArcGIS paging; store the source update time on every feature.
