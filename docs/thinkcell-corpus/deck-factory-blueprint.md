# Sales Director think-cell Deck Factory Blueprint

Period: `2026-Q2`
Generated: `2026-05-03T17:39:29+00:00`

## Operating Decision

Use think-cell as a controlled update layer, not a runtime chart factory. Charts must come from named donor/seed objects and bind through `.ppttc`; dense tables stay on the Excel COM `AddRangeImage` table-image lane until native tables are proven clean.

## Current Proof State

- Contracts: `12`
- Work queue jobs: `12`
- Protect-lane jobs: `12`
- Latest `.ppttc` gate: `pass` (9/9 passing)

## Build Policy

- `P0`: Default deck spine. Use for every director when the fact-pack data shape is non-empty.
- `P1`: Promote selectively when it improves a named leadership decision and the visual gate passes.
- `P2`: Use sparingly. Require explicit data-shape fit and a clear decision question.
- `charts`: Use named think-cell donor/seed objects updated by .ppttc. Do not create missing charts at runtime.
- `tables`: Use Excel COM AddRangeImage table-image lane. Native editable think-cell tables remain blocked.

## Contract Map

| Contract | Priority | Lane | Ready directors | Fallbacks | Deck role | Production rule |
| --- | ---: | --- | ---: | ---: | --- | --- |
| QTR01_StageMix_Bar | P0 | native think-cell chart via named seed + ppttc | 9 | 0 | Stage distribution for open Land/Expand ARR. | Universal P0 chart when at least two stages survive the internal/test filter. |
| QTR02_ForecastMix_Bar | P0 | native think-cell chart via named seed + ppttc | 9 | 0 | Forecast category mix: Commit, Pipeline, Best Case where present. | Universal P0 chart; label ARR as unweighted unless a weighted range is explicitly used. |
| QTR03_OwnerCoaching_Bar | P0 | native think-cell chart via named seed + ppttc | 9 | 0 | Owner ranking and coaching focus. | Universal P0 chart paired with named action rows from the table-image lane. |
| QTR10_ActionDecisionRegister_TableImage | P0 | Excel COM AddRangeImage table-image donor | 9 | 0 | Action and decision register sourced from Excel rows. | Universal P0 table-image lane; source rows from the validated fact pack/workbook. |
| QTR11_CommercialApprovalGap_TableImage | P0 | Excel COM AddRangeImage table-image donor | 9 | 0 | Commercial Approval gaps for Land deals requiring Stage 3 governance. | Universal P0 table-image lane when gaps exist; otherwise show a short no-gap statement. |
| QTR12_StalePipeline_BarTable | P0 | native think-cell bar for summary; table-image donor for named deals | 9 | 0 | Stale activity summary plus named triage table. | Universal P0 hybrid lane after stale thresholds are computed in Excel. |
| QTR04_DealRisk_Scatter | P1 | native think-cell chart via named seed + ppttc | 8 | 1 | Named deal risk inspection map. | P1 conditional chart for directors with ARR and probability/age spread. |
| QTR05_FY26RenewalTimeline_Gantt | P1 | native think-cell chart via named seed + ppttc | 8 | 1 | FY26 Renewal ACV date spread and renewal attention. | P1 conditional chart for Renewal ACV only; never mix Land/Expand ARR. |
| QTR08_PipelineMovement_Waterfall | P1 | native think-cell chart via named seed + ppttc | 9 | 0 | Opening to closing pipeline movement bridge. | P1 chart when the signed movement gate passes; closed-lost/slips must subtract. |
| QTR06_Q2RenewalTimeline_Gantt | P2 | native think-cell chart via named seed + ppttc | 3 | 6 | Q2 Renewal ACV timing only where May/June dates are meaningful. | P2 selective chart; current fit is Sarah Pittroff, Dan Peppett, and Christian Ebbesen. |
| QTR07_StageIndustry_Mekko | P2 | native think-cell chart via named seed + ppttc | 8 | 1 | Stage by industry mix when both dimensions matter. | P2 rare chart; use only for a real two-dimensional claim. |
| QTR09_Geography_RankedBar | P2 | native think-cell bar via named seed + ppttc | 9 | 0 | Country or geography ranking. | P2 chart; use ranked bar by default and only when geography is the decision variable. |

## Required Gates

- Internal/test row filter applied before workbook and chart payload generation.
- ARR visuals use Type IN ('Land','Expand') and APTS_Opportunity_ARR__c.
- Renewal visuals use Type = 'Renewal' and APTS_Renewal_ACV__c.
- Headline currency basis is converted EUR, not raw multi-currency SOQL sums.
- Named element exists in the seed or donor before .ppttc binding.
- Strict .ppttc expected-name validation passes.
- L5 proof JSON exists and reports pass for the contract lane.
- Rendered PPTX opens without repair, is nonblank, and has no overlap/placeholder/error text.
- Regional publish gate passes before SharePoint packaging.

## Next Build Order

1. Lock P0 universal spine into the regional deck builder first: QTR01, QTR02, QTR03, QTR10, QTR11, QTR12.
2. Promote QTR08 waterfall only behind the signed movement gate.
3. Pilot QTR04 scatter and QTR05 FY26 renewal Gantt on one high-fit director, then batch eligible directors.
4. Keep QTR06, QTR07, and QTR09 conditional until the fact-pack explicitly justifies them.
5. Keep dense deal tables traceable to Excel; do not chase native editable think-cell tables for this cycle.

## Sources

- `scaffold`: `/Users/test/code/apps/sales-ops-copilot/state/thinkcell_bridge/build_scaffold/2026-Q2/thinkcell_build_scaffold.json`
- `template_selection`: `/Users/test/code/apps/sales-ops-copilot/config/thinkcell_template_selection.may_2026.json`
- `work_queue`: `/Users/test/code/apps/sales-ops-copilot/state/thinkcell_bridge/build_scaffold/2026-Q2/work_queue.json`
- `graph_manifest`: `/Users/test/code/apps/sales-ops-copilot/state/thinkcell_bridge/knowledge_graph/thinkcell_kg_manifest.json`
- `ppttc_validation`: `/Users/test/code/apps/sales-ops-copilot/state/2026-Q2/__regional__/ppttc_validation/20260503-173929Z/ppttc_factory_validation.json`
