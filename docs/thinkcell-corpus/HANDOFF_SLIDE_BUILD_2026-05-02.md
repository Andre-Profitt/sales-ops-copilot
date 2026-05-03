# Handoff: think-cell Slide Build From Graph/RAG

Date: 2026-05-02  
Repo: `/Users/test/code/apps/sales-ops-copilot`  
Primary goal: use the think-cell graph/RAG, proven contracts, and per-director visual plan to build better Sales Director slides with tighter think-cell control.

## Mission

Do not restart think-cell discovery. The useful mapping already exists. The next session should use the graph/RAG and factory artifacts to build and polish slides.

Build target:

- Keep the current 9-region May 2026 meeting-spine package stable.
- Promote proven P1/P2 think-cell visuals into the actual slide builder only when the visual plan says they fit.
- Preserve Excel traceability and SimCorp ARR/ACV rules.
- Use screenshots/render gates before batching changes across all regions.

## Current Answer

The factory is not the final best version yet, but it is now materially better:

- The deck package passes local production gates.
- The think-cell corpus is indexed and queryable.
- 12 QTR contracts are L5-proven.
- A new visual contract planner says which visuals to include, candidate, fallback, or suppress per director.
- The remaining gap is slide construction: `build_regional_meeting_spine_decks.py` does not yet fully consume the visual plan to insert/promote every eligible P1/P2 chart.

## Start Here

```bash
cd /Users/test/code/apps/sales-ops-copilot

# Current production package gate
python3 scripts/run_may_regional_production_line.py --period 2026-Q2 --jobs 4

# Current visual decision layer
python3 scripts/build_thinkcell_visual_contract_plan.py --period 2026-Q2 --jobs 4

# Current graph/RAG entrypoints
.venv/bin/python scripts/query_thinkcell_knowledge_graph.py "QTR04 scatter L5 proof" --kind build_proof
.venv/bin/python scripts/query_thinkcell_knowledge_graph.py "QTR05 FY26 renewal Gantt L5 proof" --kind build_proof
.venv/bin/python scripts/query_thinkcell_knowledge_graph.py "QTR08 waterfall movement L5 proof" --kind build_proof
.venv/bin/python scripts/query_thinkcell_knowledge_graph.py "APAC geography ranked bar donor" --kind slide
```

Latest successful production run:

- Manifest: `state/2026-Q2/__regional__/production_runs/20260502-111802/manifest.json`
- Review package: `/Users/test/Downloads/May 2026 Meeting Spine Candidates`
- Package contents: 9 PPTX meeting-spine decks plus production, visual, and blueprint reports.
- All steps passed, including `thinkcell_visual_contract_plan`, `regional_publish_gate`, `review_package_validation`, and `review_package_visual_gate`.

## Must-Read Artifacts

Use these before touching slide code:

- `docs/thinkcell-corpus/graph-rag.md`
- `docs/thinkcell-corpus/deck-factory-blueprint.md`
- `docs/thinkcell-corpus/deck-factory-visual-plan.md`
- `docs/thinkcell-corpus/MASTER_STATE.md`
- `state/2026-Q2/__regional__/thinkcell_deck_blueprint/thinkcell_deck_factory_blueprint.json`
- `state/2026-Q2/__regional__/thinkcell_visual_plan/thinkcell_visual_contract_plan.json`
- `state/thinkcell_bridge/build_scaffold/2026-Q2/thinkcell_build_scaffold.json`
- `state/thinkcell_bridge/knowledge_graph/thinkcell_kg_manifest.json`

## Graph/RAG State

Current graph manifest reports:

- 1,136 nodes
- 6,494 edges
- build-level nodes L0-L5
- COM/runtime/API evidence nodes
- 12 contract-level proof nodes
- template, slide, donor, automation lane, Salesforce fit, and proof artifacts

Core graph/RAG docs:

- Manifest: `state/thinkcell_bridge/knowledge_graph/thinkcell_kg_manifest.json`
- Nodes: `state/thinkcell_bridge/knowledge_graph/thinkcell_kg_nodes.jsonl`
- Edges: `state/thinkcell_bridge/knowledge_graph/thinkcell_kg_edges.jsonl`
- RAG index: `state/thinkcell_bridge/knowledge_graph/thinkcell_graph_rag_index.json`
- Slide corpus: `state/thinkcell_bridge/slide_corpus/thinkcell_slide_corpus.json`

Useful queries:

```bash
.venv/bin/python scripts/query_thinkcell_knowledge_graph.py "forecast mix bar donor" --kind slide
.venv/bin/python scripts/query_thinkcell_knowledge_graph.py "owner coaching bar donor" --kind slide
.venv/bin/python scripts/query_thinkcell_knowledge_graph.py "deal risk scatter donor slide" --kind slide
.venv/bin/python scripts/query_thinkcell_knowledge_graph.py "FY26 renewal timeline Gantt donor" --kind slide
.venv/bin/python scripts/query_thinkcell_knowledge_graph.py "pipeline movement waterfall closed lost subtract" --kind build_proof
.venv/bin/python scripts/query_thinkcell_knowledge_graph.py "table image AddRangeImage proof" --kind build_proof
```

## Proven Contract Map

P0 universal spine:

| Contract | Lane | Build rule |
|---|---|---|
| `QTR01_StageMix_Bar` | native think-cell chart via named seed + `.ppttc` | Use when at least two stages survive filters. |
| `QTR02_ForecastMix_Bar` | native think-cell chart via named seed + `.ppttc` | Label ARR as unweighted unless weighted is explicitly used. |
| `QTR03_OwnerCoaching_Bar` | native think-cell chart via named seed + `.ppttc` | Pair with named action rows. |
| `QTR10_ActionDecisionRegister_TableImage` | Excel COM `AddRangeImage` table-image | Keep as register, not fake Gantt, when due dates collapse. |
| `QTR11_CommercialApprovalGap_TableImage` | Excel COM `AddRangeImage` table-image | Land approval gaps only; exclude test/internal rows. |
| `QTR12_StalePipeline_BarTable` | native bar + table-image | Chart summarizes; table names deals. |

P1 selective:

| Contract | Lane | Build rule |
|---|---|---|
| `QTR04_DealRisk_Scatter` | native think-cell chart via named seed + `.ppttc` | Use only when ARR/probability axes do not collapse and it points to named deal action. |
| `QTR05_FY26RenewalTimeline_Gantt` | native think-cell chart via named seed + `.ppttc` | Renewal ACV only. Never mix Land/Expand ARR. |
| `QTR08_PipelineMovement_Waterfall` | native think-cell chart via named seed + `.ppttc` | Closed-lost and slips must subtract. Promote only when movement is a leadership question. |

P2 rare/conditional:

| Contract | Lane | Build rule |
|---|---|---|
| `QTR06_Q2RenewalTimeline_Gantt` | native think-cell chart via named seed + `.ppttc` | Only Sarah Pittroff, Dan Peppett, Christian Ebbesen currently look eligible. |
| `QTR07_StageIndustry_Mekko` | native think-cell chart via named seed + `.ppttc` | Use only for a real two-dimensional stage/industry claim. |
| `QTR09_Geography_RankedBar` | native think-cell bar via named seed + `.ppttc` | Use ranked bar, not maps, and only when geography changes action. |

## Visual Plan Summary

Source: `state/2026-Q2/__regional__/thinkcell_visual_plan/thinkcell_visual_contract_plan.json`

Summary:

- 9 directors pass.
- 69 included visuals.
- 17 candidate visuals.
- 3 fallback visuals.
- 19 suppressed visuals.

Director plan snapshot:

| Director | Include beyond P0 | Candidate | Fallback |
|---|---|---|---|
| Megan Miceli | `QTR04` | `QTR08` | `QTR05` |
| Patrick Gaughan | `QTR05` | `QTR08` | `QTR04` |
| Jesper Tyrer | `QTR04`, `QTR05` | `QTR08`, `QTR09` | none |
| Sarah Pittroff | `QTR04`, `QTR05` | `QTR08`, `QTR06` | none |
| Francois Thaury | `QTR04`, `QTR05` | `QTR08`, `QTR09` | none |
| Dan Peppett | `QTR04`, `QTR05` | `QTR08`, `QTR06`, `QTR09` | none |
| Christian Ebbesen | `QTR04`, `QTR05` | `QTR08`, `QTR06`, `QTR09` | none |
| Mourad | `QTR04`, `QTR05` | `QTR08`, `QTR09` | none |
| Adam Steinhouse | `QTR04` | `QTR08` | `QTR05` |

Use this plan as the source of truth for slide promotion. Do not add decorative think-cell charts just because a donor exists.

## Automation Lanes

Use the VM as an update runtime, not a chart factory.

Working lanes:

- `.ppttc` strict build for named native think-cell chart/text elements.
- PowerPoint COM `PresentationFromTemplateStep3`, `UpdateBatchStep3`, `UpdateChartStep3`.
- Excel COM `CreateUpdate`, `AddRangeData`, `AddRangeImage`, `Send`.
- Table-image donors via `AddRangeImage`.
- Stock `.potx` as donor/reference material after naming/proofing.

Blocked or not production-ready:

- Creating missing native think-cell charts programmatically.
- Native editable think-cell tables.
- Blind dynamic insertion from stock template slides without naming/proof.
- Forcing action cadences into Gantt when all due dates are the same.

## Current Build Scripts

Core production:

- `scripts/run_may_regional_production_line.py`
- `scripts/build_regional_meeting_spine_decks.py`
- `scripts/build_thinkcell_visual_contract_plan.py`
- `scripts/build_thinkcell_deck_factory_blueprint.py`
- `scripts/run_ppttc_factory_validation.py`
- `scripts/run_regional_deck_publish_gate.py`
- `scripts/run_review_package_visual_gate.py`

Think-cell proof/build:

- `scripts/build_thinkcell_knowledge_graph.py`
- `scripts/build_thinkcell_build_scaffold.py`
- `scripts/prove_thinkcell_native_chart_contract.py`
- `scripts/prove_thinkcell_stock_donor_contract.py`
- `scripts/prove_thinkcell_hybrid_contract.py`
- `scripts/run_thinkcell_windows_bridge.py`
- `scripts/ppttc_template.py`
- `scripts/validate_ppttc.py`

Polish/repair:

- `scripts/polish_regional_linked_deck_text.py`
- `scripts/fix_table_image_aspect_ratios.py`
- `scripts/finalize_thinkcell_table_images_mac.py`
- `scripts/audit_regional_decks_against_goals.py`
- `scripts/audit_jesper_apac_intel_coverage.py`

## Next Build Work

Do this in this order:

1. Read `thinkcell_visual_contract_plan.json`.
2. Pick one pilot director first: `Jesper-Tyrer` is the best pilot because APAC has rich original intel and multiple eligible/candidate P1/P2 visuals.
3. Make `build_regional_meeting_spine_decks.py` consume the visual plan.
4. Promote eligible P1 visuals into the pilot deck:
   - `QTR04_DealRisk_Scatter`
   - `QTR05_FY26RenewalTimeline_Gantt`
   - `QTR08_PipelineMovement_Waterfall` only if the movement slide earns its place
   - `QTR09_Geography_RankedBar` only if it points to named country/territory action
5. Render/open the pilot deck and inspect screenshots.
6. Run all local gates for that one director.
7. Only then batch across all nine directors.

Pilot command pattern:

```bash
python3 scripts/run_may_regional_production_line.py --period 2026-Q2 --director-slug Jesper-Tyrer --jobs 4 --skip-package
python3 scripts/run_regional_deck_publish_gate.py --period 2026-Q2 --director-slug Jesper-Tyrer
python3 scripts/audit_regional_decks_against_goals.py --period 2026-Q2 --director-slug Jesper-Tyrer
```

Full package command:

```bash
python3 scripts/run_may_regional_production_line.py --period 2026-Q2 --jobs 4
```

## Slide-Build Quality Bar

Leadership-ready means:

- slide title says the management question or action, not a generic chart label
- ARR and ACV are never blended
- weighted and unweighted numbers are explicitly labeled
- charts have few enough categories to read in presentation mode
- table rows have no empty filler, `#NULL`, `#NAME`, test/internal rows, or absurd probabilities
- every visual has a traceable workbook/fact-pack source
- closed-lost and slips subtract in waterfalls
- no `Click to add subtitle`
- no `Title of the section`
- no tiny think-cell blue-window table artifacts
- no overlapping think-cell objects
- SimCorp branding stays restrained and professional

## SimCorp Fact Rules

These are hard constraints:

- ARR = Land + Expand only, sourced from `APTS_Opportunity_ARR__c`.
- ACV = Renewal only, sourced from `APTS_Renewal_ACV__c`.
- Never blend ARR and ACV in one metric.
- ARR visuals must explicitly filter `Type IN ('Land','Expand')`.
- Renewal visuals must explicitly filter `Type = 'Renewal'`.
- Headline currency basis is converted EUR. Do not use raw multi-currency SOQL sums for headlines.
- Stage 3 Commercial Approval gate uses `Stage_20_Approval__c`.
- Filter out internal/test rows: account contains `test`, `SimCorp`, `SC`, and opportunity contains `test`.

## Known Risks

- The current decks are good enough for local review but not yet the final automated factory.
- SharePoint may contain older/bad copies from previous iterations; validate before publishing or re-uploading.
- Native think-cell tables remain blocked; table-image lane is the reliable path for this cycle.
- The visual plan is currently advisory/gating; it must be wired deeper into slide construction.
- Quarter-roll logic is not certified. Current run is May 2026 / `2026-Q2`.
- Do not chase auth/cloud/private-server work for this slide-build task; it does not improve the decks tonight.

## Definition Of Done For The Next Session

Minimum useful win:

- One pilot deck uses the visual plan to promote at least `QTR04` and `QTR05` into real slides.
- Pilot deck opens without repair and passes publish/audit gates.
- Screenshots/contact sheet show the promoted visuals are readable and on brand.

Better win:

- All nine decks are rebuilt with plan-driven visual promotion/suppression.
- Downloads package is refreshed.
- `review_package_visual_gate` passes.
- Handoff notes state exactly which candidate visuals remain deferred and why.

Full win:

- `build_regional_meeting_spine_decks.py` has a durable visual-plan integration layer.
- P1/P2 inclusion is deterministic from `thinkcell_visual_contract_plan.json`.
- A new gate fails if a slide includes a suppressed visual or omits a required included visual.
- The full local production command passes.

## Suggested First Prompt After Context Clear

```text
We are in /Users/test/code/apps/sales-ops-copilot. Read docs/thinkcell-corpus/HANDOFF_SLIDE_BUILD_2026-05-02.md, docs/thinkcell-corpus/graph-rag.md, docs/thinkcell-corpus/deck-factory-blueprint.md, and docs/thinkcell-corpus/deck-factory-visual-plan.md. Then use the graph/RAG and state/2026-Q2/__regional__/thinkcell_visual_plan/thinkcell_visual_contract_plan.json to make the meeting-spine builder consume the visual plan. Pilot on Jesper-Tyrer first. Do not redo think-cell API discovery. Keep ARR/ACV rules strict. Run one-director gates before batch.
```
