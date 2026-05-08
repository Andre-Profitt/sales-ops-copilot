# think-cell Build Scaffold

Purpose: convert graph/RAG findings into buildable work units. The graph answers
what we know; the scaffold says which level of build the finding can support and
what gate proves it.

## Build Levels

| Level | Name | Meaning | Primary graph nodes |
|---|---|---|---|
| `L0` | Runtime Surface | The Windows/PowerPoint/Excel/think-cell automation surface is available. | `Runtime`, `AutomationLane` |
| `L1` | Salesforce Fit Gate | Real quarter data says which directors and chart families are eligible. | `SalesforceFit`, `SalesDirector`, `QuarterSeedContract` |
| `L2` | Template Family | A SimCorp visual contract maps to a stock think-cell family. | `TemplateFamily`, `Template` |
| `L3` | Slide Donor | Specific donor/reference slides are selected from the stock corpus. | `Slide`, `Signal`, `ThinkCellClass`, `UseClass` |
| `L4` | Named Seed Contract | The donor becomes a real named update surface in a seed PPTX. | `QuarterSeedContract`, `AutomationLane` |
| `L5` | Binding Proof | Automation binds data and proves the output contains expected values. | `Runtime`, `QuarterSeedContract`, `SalesforceFit` |

This keeps build decisions disciplined:

- `L0-L1` decides whether a build is valid for the quarter.
- `L2-L3` decides which template material to use.
- `L4` is the manual/VM authoring boundary where stock donor material becomes a named think-cell automation surface.
- `L5` is the proof boundary; exit code 0 is not enough.

## Generate Scaffolds

Refresh the graph and scaffold:

```bash
.venv/bin/python scripts/extract_thinkcell_slide_corpus.py
.venv/bin/python scripts/build_thinkcell_quarter_seed_spec.py --period 2026-Q2
.venv/bin/python scripts/build_thinkcell_knowledge_graph.py --period 2026-Q2
.venv/bin/python scripts/build_thinkcell_build_scaffold.py --period 2026-Q2
.venv/bin/python scripts/build_thinkcell_work_queue.py --period 2026-Q2
```

Write an L5 proof for a scaffold contract:

```bash
.venv/bin/python scripts/prove_thinkcell_build_scaffold_contract.py \
  --period 2026-Q2 \
  --director-slug Jesper-Tyrer \
  --contract QTR10_ActionDecisionRegister_TableImage \
  --render
```

Write native-chart and stock-donor L5 proofs:

```bash
.venv/bin/python scripts/prove_thinkcell_native_chart_contract.py \
  --period 2026-Q2 \
  --director-slug Jesper-Tyrer \
  --contract QTR07_StageIndustry_Mekko
.venv/bin/python scripts/prove_thinkcell_stock_donor_contract.py \
  --period 2026-Q2 \
  --director-slug Jesper-Tyrer \
  --contract QTR04_DealRisk_Scatter
.venv/bin/python scripts/prove_thinkcell_stock_donor_contract.py \
  --period 2026-Q2 \
  --director-slug Sarah-Pittroff \
  --contract QTR06_Q2RenewalTimeline_Gantt
```

Outputs:

- `state/thinkcell_bridge/build_scaffold/2026-Q2/thinkcell_build_scaffold.md`
- `state/thinkcell_bridge/build_scaffold/2026-Q2/thinkcell_build_scaffold.json`
- `state/thinkcell_bridge/build_scaffold/2026-Q2/contracts/*.md`
- `state/thinkcell_bridge/build_scaffold/2026-Q2/work_queue.json`
- `state/thinkcell_bridge/build_scaffold/2026-Q2/work_queue.md`

## How To Use

Start each future build from the contract scaffold, not from a blank deck.
Start each multi-agent build from `work_queue.json`, not from an open-ended
prompt. It orders protect, seed-authoring, and binding-proof jobs and records
the exact inputs, outputs, gates, dependencies, and stop conditions for each
contract.

Each contract brief includes:

- Level gate status from `L0` through `L5`.
- Candidate stock donor/reference slides.
- Salesforce-ready and fallback directors.
- The automation lane: native chart via named seed plus `.ppttc`, table image via `AddRangeImage`, or fallback.
- Artifact paths for seed PPTX, data workbook, `.ppttc`, bound PPTX, render output, and proof JSON.
- The graph query that rehydrates the supporting evidence.

## Current Interpretation

- All 12 quarter seed contracts are now L5-proven automation lanes for 2026-Q2.
- Bar/column, scatter/bubble, waterfall, timeline/Gantt, and Mekko can scaffold native chart seed work.
- Table-image contracts can scaffold proven `AddRangeImage` work now.
- `QTR01_StageMix_Bar` is L5-proven for Jesper Tyrer as a native chart
  automation proof: named seed, `.ppttc`, Windows bridge, package assertions,
  and rendered chart visibility. It is not a production visual polish proof.
- `QTR02_ForecastMix_Bar` and `QTR03_OwnerCoaching_Bar` are also L5-proven
  native chart automation proofs using the same seed-renaming and `.ppttc`
  binding pattern. Their donor-slide visuals still need production polish.
- `QTR04_DealRisk_Scatter` is L5-proven for Jesper Tyrer by patching the
  stock Scatter/Bubble donor's empty `m_strName`, binding Salesforce-derived
  Q2 readiness data through `.ppttc`, checking package terms, and rendering.
- `QTR05_FY26RenewalTimeline_Gantt` is L5-proven for Jesper Tyrer by patching
  the stock Timeline/Gantt donor's empty `m_strName` values, binding FY26
  Renewal ACV rows through `.ppttc`, checking surviving Gantt package terms,
  and rendering.
- `QTR06_Q2RenewalTimeline_Gantt` is L5-proven for Sarah Pittroff, one of the
  eligible Q2 renewal-timeline directors. This deliberately avoids proving the
  lane against a director whose Q2 renewal data shape is sparse.
- `QTR07_StageIndustry_Mekko` is L5-proven for Jesper Tyrer as a native chart
  automation proof: `S16_StageByIndustry` was renamed to the QTR07 contract
  name, bound through `.ppttc`, rendered, and checked for stage/industry terms.
- `QTR08_PipelineMovement_Waterfall` is L5-proven for Jesper Tyrer as a
  native waterfall automation proof: `S04_PipeMovement` was renamed to the
  QTR08 contract name, bound through `.ppttc`, rendered, and checked for the
  opening/closing pipe labels.
- `QTR09_Geography_RankedBar` is L5-proven for Jesper Tyrer as a native ranked
  bar automation proof: `S17_TerritoryPerformance` was renamed to the QTR09
  contract name, bound through `.ppttc`, rendered, and checked for APAC
  geography labels.
- `QTR10_ActionDecisionRegister_TableImage` is L5-proven for Jesper Tyrer:
  slides 26 and 27, table-image lane, rendered and proof-checked.
- `QTR11_CommercialApprovalGap_TableImage` is L5-proven for Jesper Tyrer:
  slide 9, `S09_PendingCommercialApproval`, rendered and proof-checked.
- `QTR12_StalePipeline_BarTable` is L5-proven as a hybrid component-lane
  proof: native `S22_StaleActivity` bar binding passed through `.ppttc`, and
  `S22_NamedRiskTriage` table-image binding passed after the Mac carryover
  finalizer repaired the tiny placeholder image on slide 22. This is still not
  a production slide-polish proof.
- Windows bridge runs are isolated per invocation. The first parallel QTR08
  and QTR09 test exposed that the shared remote staging folder caused file
  cross-talk; the bridge wrapper now creates a unique `run-*` VM folder.
- Stock Scatter/Bubble and Timeline/Gantt `.potx` donors are not direct
  production templates. The stock-donor proof copies them to `.pptx`, patches
  empty `m_strName` payloads, and then proves the resulting named surface.
- Small donor decks can render PNGs as `slide-1.png` rather than
  `slide-01.png`; the proof harness accepts both filename forms.
- Native editable think-cell tables stay below production scaffold level until the native-table proof passes.
- Stock `.potx` files are donor/reference material, not direct `.ppttc` templates.
