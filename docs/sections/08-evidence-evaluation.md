# Section 8: Evidence verification and evaluation

**Stack:** Python 3.12, Shapely/GeoPandas, pytest · **Pairs with:** Lead

## Scope
The rules the agent's "Verify evidence" step calls (the lead owns the graph; you own the rule functions):
- Timestamp checks (observed vs retrieved, staleness), unit consistency, cloud-coverage thresholds.
- `compare_detection_to_perimeter(detections, perimeters)`: spatial/temporal matching.
- Confidence labelling: Unverified detection / Corroborated signal (≥2 independent evidence categories) / Officially reported / Insufficient evidence. No percentages (spec §15).
- Claim ↔ source mapping for the final result; report generation (`generate_report`).
- Evaluation harness over historical San Bernardino fires with the spec §22 metrics.

## Owned paths
`apps/worker/src/inland_worker/evidence/**` · `apps/worker/src/inland_worker/reports/**` · `apps/worker/eval/**` · `docs/evaluation.md`

## First tickets

**S8-1 Confidence labeller.** *Input:* a list of `Evidence`. *Output:* label + reasons. *Acceptance:* a FIRMS point alone → Unverified; FIRMS + a compatible dNBR signal → Corroborated; match with a WFIGS/CAL FIRE perimeter → Officially reported; stale/missing/contradictory → Insufficient. *Failure test:* an `agent_inference` item never counts toward corroboration.

**S8-2 Detection ↔ perimeter comparison.** Buffered point-in-polygon + date window, in a projected CRS; outputs a `deterministic_calculation` with units.

**S8-3 Eval case set.** 3–5 historical San Bernardino fires with expected facts (dates, perimeter area) as fixtures; metric script for source completeness, the timestamps/limitations rate, and the computed-vs-official burn area difference.

**S8-4 Report generator (Markdown first, PDF later).** Follows the spec §23 result structure; every factual claim carries a source link; inferences labelled.
