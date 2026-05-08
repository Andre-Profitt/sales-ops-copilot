# think-cell Automation Contract

Date: 2026-05-01

This file separates what the think-cell template corpus can automate from what
is only visual inspiration.

## Package Finding

The local installed think-cell template library has:

- 62 `.potx` files.
- 497 slides.
- 69 chart XML references.
- 337 OLE embedding parts.
- 0 named `m_strName` automation payloads.

Implication: stock templates can be copied or studied, but they cannot be used
directly as strict `.ppttc` templates.

## Working SimCorp Automation Assets

### LAND Seed

Asset: `assets/LAND_thinkcell_seed.pptx`

This contains 42 named elements:

- 12 native think-cell chart names:
  `S04_PipeMovement`, `S05_PipelineByStage`, `S06_PipelineAging`,
  `S13_ForecastCategory`, `S15_ByOwner`, `S16_StageByIndustry`,
  `S17_TerritoryPerformance`, `S18_WinsLossesQTD`, `S19_Velocity`,
  `S21_ConcentrationRiskChart`, `S22_StaleActivity`,
  `S25_PipelineCreationVelocity`.
- Text and KPI bindings for cover, executive summary, concentration risk, and
  sales velocity.
- Eight table names as contract stubs, not production-native think-cell tables.

Production meaning:

- Chart/text binding is credible.
- Native think-cell table binding is not credible yet.
- Do not describe the table stubs as working native think-cell tables.

### Table-Image Donor

Asset: `assets/LAND_thinkcell_table_image_donor.pptx`

The reusable proof name is `ProbeTableImage`. The broader donor set under
`state/thinkcell_bridge/table_image_donors/` contains one named table-image
object per donor, including `S07_TopDealsLand`, `S08_TopDealsExpand`,
`S09_PendingCommercialApproval`, `S11_RenewalPipeline`,
`S12_GRRProxyTable`, `S13_ForecastCategoryDetail`, `S16_OwnerCoaching`,
`S21_ConcentrationTable`, and `S26_ActionItems`.

Production meaning:

- Table-image refresh uses Excel COM `CreateUpdate().AddRangeImage(...)`.
- `.ppttc` JSON does not update this donor reliably.
- The table-image lane is auditable through Excel named ranges, but the final
  PowerPoint object is an image-like linked table object, not an editable
  native think-cell table.

## Donor Injection Pattern

The working chart seed path copies intact official think-cell donor slide parts
from stock `.potx` files and patches the copied OLE/CFB `think-cellXML` stream
with the SimCorp object name.

Useful source files:

- `scripts/build_thinkcell_seed_template.py`
- `scripts/ppttc_template.py`
- `scripts/thinkcell_cfb.py`

Known safe donor families:

- Bar/Column from slide 3, 4, 6, and 8.
- Waterfall from slide 1.
- Mekko from slide 1.
- Scatter/Bubble from slide 1, now proven for QTR04 deal-risk scatter.
- Timeline/Gantt from slide 1, now proven for QTR05 FY26 renewal timeline and
  QTR06 Q2 renewal timeline.

Recommended next donor pilots:

- Line/Area for true time-series pipeline creation.

## Blocked Native Table Route

The native table route remains blocked because package and UI probes found
think-cell table OLE streams without a stable exposed `m_strName`,
`AddRangeData`, datasheet, or range-link naming surface.

Known bad path:

- Raw `m_strName` injection into table-related streams such as `CSmartGrid` or
  `CContainerSE`.

Why it matters:

- A table that opens in PowerPoint is not enough.
- A table is production-ready only after it can be named, linked, refreshed,
  and validated without PowerPoint repair prompts.

## Automation Status by Visual Family

| Family | Status | Production rule |
|---|---|---|
| Bar/Column | Supported as chart donor | Use for rankings, stage, owner, category, aging |
| Waterfall | Supported as chart donor | Require signed movement gate |
| Mekko | Supported but rare | Use only for dense two-dimensional mix |
| Line/Area | Candidate donor | Add only for real time-series data |
| Scatter/Bubble | Supported as stock donor | Add for named ARR deal inspection when axes have spread |
| Timeline/Gantt | Supported as stock donor | Add for Renewal ACV milestones when dates differ materially |
| Native think-cell table | Blocked | Use native PPT table or table-image lane |
| Table as image | Proven through Excel COM | Use for dense table-image refresh |
| KPI/text | Supported | Keep metric basis explicit |
| Annotations | Visual/reference lane | Use sparingly and source-backed |

## Validation Gates

Every SimCorp think-cell object needs:

- Object name: a stable `ppt_name` or think-cell name.
- Excel range: a named range or explicit output sheet/range.
- Metric basis: ARR, ACV, count, rate, days, or date.
- Visual gate: the data shape must fit the chart.
- Render gate: output deck opens without repair and renders nonblank.
- Business gate: ARR/ACV, Type filter, stage, currency, and date basis must be
  correct.

## Current Recommended Architecture

Keep two assets separate:

- Engineering/wiring template: preserves named object contract and donor
  automation.
- Director-facing shell: removes scaffold language, writes operating-question
  titles, and keeps the final deck polished.

The stock think-cell templates should feed both assets as visual references,
but the business contract must live in SimCorp-owned config, workbook outputs,
and validation scripts.
