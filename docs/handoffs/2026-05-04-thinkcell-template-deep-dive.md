# Think-Cell Template Deep Dive — LAND Review Deck Factory

## Executive recommendation

Build a new `LAND_review_full_28.tcseed.pptx` as a governed Think-Cell automation template, not as another patched output deck. The template should contain the reusable visual intelligence: SimCorp layouts, chart positions, chart types, automation text fields, named Think-Cell elements, source-note fields, and table-image placeholders. The monthly run should only supply data, titles, source notes, and action text.

The best production pattern is:

```text
clean SimCorp LAND skeleton
  + manual Think-Cell wiring pass on Windows
  + binding registry
  + template contract/preflight
  + ppttc JSON for charts/text
  + Excel UpdateBatch/AddRangeImage for formatted tables
  + binding-level verification
```

## Decision: clean skeleton + certified manual Think-Cell wiring

The existing `assets/LAND_thinkcell_seed.pptx` should not be repaired further. It is contaminated with visible dev instructions, orphan shapes, off-canvas artifacts, and history from several failed polish/master-transplant passes. Start from `assets/golden/LAND_canonical.pptx` for brand/layout fidelity, then wire Think-Cell elements once in PowerPoint using the Think-Cell UI. Do not build production Think-Cell anchors by OLE XML splicing.

The one-time manual wiring pass is acceptable because it creates a reusable factory asset. The factory remains automated after the seed is certified.

## Template asset set

Recommended directory:

```text
assets/templates/land_review_full_28/
  LAND_review_full_28.clean_skeleton.pptx
  LAND_review_full_28.tcseed.pptx
  LAND_review_full_28.canary_output.pptx
  LAND_review_full_28.seed_contract.yml
  LAND_review_full_28.named_element_inventory.json
  simcorp_land_review.thinkcell_style.xml
  README.md
```

Recommended config:

```text
config/thinkcell/land_review_full_28.binding_registry.yml
config/thinkcell/land_review_full_28.visual_rules.yml
config/thinkcell/land_review_full_28.template_gates.yml
schemas/thinkcell_binding_registry.schema.json
schemas/deck_plan.schema.json
```

## Four rendering lanes

### Lane A — `.ppttc` Think-Cell chart binding

Use for editable Think-Cell charts:

- S04 Pipe movement waterfall
- S05 Pipeline by stage bar
- S06 Pipeline aging bar
- S13 Forecast category bar/column
- S15 By owner bar
- S16 Stage × Industry stacked bar for V1, Mekko variant for P1
- S17 Territory performance bar
- S18 Wins/Losses QTD grouped column
- S19 Velocity bar
- S21 Concentration risk chart
- S22 Stale activity bar
- S25 Pipeline creation velocity line/column

### Lane B — `.ppttc` automation text fields

Use for all dynamic text:

- slide titles
- subtitles
- director name
- period/scope labels
- KPI cards
- insight bullets
- footnotes
- source notes
- risk/outlook narrative

### Lane C — Excel `UpdateBatch` / `AddRangeImage`

Use for table-shaped artifacts that need exact formatting:

- S07 Top deals — Land
- S08 Top deals — Expand
- S09 Pending Commercial Approval
- S11 Renewal pipeline
- S12 GRR proxy table
- S21 concentration table
- S24 Account expansion
- S26 Action items

For per-row Salesforce links, use separate hyperlink buttons or native text overlays; table images will not preserve per-cell Excel hyperlinks as interactive row links in PowerPoint.

### Lane D — static master/layout slides

Use for:

- cover frame
- section dividers
- closing/legal slide

These should rely on the canonical SimCorp master/layout, not hand-painted rectangles.

## Naming convention

Use readable, slide-local names. Avoid positional names such as `S00_TitleSlide04`.

Examples:

```text
S01_DirectorName
S01_Period
S01_ScopeLabel
S02_Title
S02_ExecSummaryLeft
S02_ExecSummaryRight
S04_Title
S04_PipeMovement
S04_Source
S05_Title
S05_PipelineByStage
S05_Source
S07_Title
S07_TopDealsLand_Image
S07_Source
S21_Title
S21_ConcentrationRiskChart
S21_ConcentrationTable_Image
S21_LargestAccount
S21_Source
```

Rules:

- Every dynamic element has exactly one name.
- Names are stable across directors and periods.
- No director/account names in template element names.
- Every analytic slide has `S##_Title` and `S##_Source`.
- Every table image ends in `_Image`.
- Every chart name matches the business concept, not the chart type.

## Binding registry structure

Example:

```yaml
slides:
  - slide_id: S05
    title: Pipeline by stage
    layout: analytic_one_chart
    elements:
      - name: S05_Title
        kind: automation_text
        lane: ppttc
        required: true
        source: insight_titles.S05
        evidence: exact_text

      - name: S05_PipelineByStage
        kind: thinkcell_chart
        chart_type: horizontal_bar
        lane: ppttc
        required: true
        source: workbook.named_ranges.S05_PipelineByStage
        data_shape:
          series: 1
          categories_min: 1
          categories_max: 8
        units: EUR_M
        evidence: category_labels_and_values

      - name: S05_Source
        kind: automation_text
        lane: ppttc
        required: true
        source: source_notes.S05
        evidence: exact_text
```

## Template build process

### 1. Build a clean skeleton

Generate a 28-slide skeleton from `assets/golden/LAND_canonical.pptx` layouts. Keep official cover, divider, and closing layouts. Add only PowerPoint placeholders at this stage.

Output:

```text
LAND_review_full_28.clean_skeleton.pptx
```

### 2. Manual Think-Cell wiring pass

On the Windows VM with PowerPoint + Think-Cell installed:

1. Open the clean skeleton.
2. Insert each Think-Cell chart object in its final slot.
3. Configure axes, labels, legends, annotations, and data layout.
4. Set AddRangeData names for charts.
5. Insert automation text fields and assign AddRangeData names.
6. Insert table-image placeholders and assign AddRangeImage names.
7. Configure Use Datasheet Fill where semantic chart colors need to come from the data payload.
8. Save as `LAND_review_full_28.tcseed.pptx`.

### 3. Inventory and certify

Run:

```bash
python scripts/inventory_pptx_thinkcell.py \
  assets/templates/land_review_full_28/LAND_review_full_28.tcseed.pptx \
  --json > LAND_review_full_28.named_element_inventory.json

python scripts/verify_thinkcell_template_contract.py \
  --template assets/templates/land_review_full_28/LAND_review_full_28.tcseed.pptx \
  --registry config/thinkcell/land_review_full_28.binding_registry.yml
```

The template fails if a required element is missing, duplicated, hidden, off-canvas, or contaminated with dev/debris text.

### 4. Canary render

Use a synthetic canary payload with unique values per element. This catches wrong-name and wrong-slide bugs.

Example canary tokens:

```text
CANARY_S05_TITLE_9831
CANARY_S05_CAT_STAGE3_9831
CANARY_S21_LARGEST_ACCOUNT_9831
```

Render:

```bash
python scripts/build_ppttc.py --canary --registry config/thinkcell/land_review_full_28.binding_registry.yml
python -m tcrender render state/canary/LAND_review_full_28.canary.ppttc
python scripts/verify_render_bindings.py --canary --pptx state/canary/LAND_review_full_28.canary_output.pptx
```

## Chart design standard

- Use full-sentence insight titles.
- Keep chart titles in PowerPoint/automation text fields, not inside the chart object.
- Use source notes on every analytic slide.
- Use SimCorp navy for primary Land/Expand ARR, tint/pattern for Expand where shown beside Land, gold/orange/coral for risk states only.
- Use Renewal ACV colors only on renewal slides.
- Use `Use Datasheet Fill` only for semantic risk/category colors, not for arbitrary design variation.
- Keep think-cell chart objects editable after render.
- Do not use gradients inside Think-Cell charts.
- Do not put unbounded tables into Think-Cell chart/table objects; use AddRangeImage for exact tables.

## Verification gates

### Template preflight

Must pass before rendering:

- all required named elements exist
- no duplicate names in same target scope unless intentionally reused
- no dev instruction text
- no Lorem ipsum
- no visible placeholder brackets
- no off-canvas debris
- no old failed-variant artifacts
- official cover and closing layouts preserved
- brand font/theme detected

### `.ppttc` validation

Must pass before Think-Cell render:

- all data names exist in registry
- all required registry names bound
- all cell types valid
- all numeric units correct
- chart data shape matches template datasheet shape
- every title has evidence reference
- every source note bound

### Render verification

Must pass after render:

- exact text evidence for title/source/scalars
- chart category evidence for every chart
- table-image presence and dimensions
- no dev/debris text in rendered XML
- no PowerPoint repair prompt
- PDF export passes

## Where repo code should change

1. Move the current seed to legacy and block it from production.
2. Add a binding registry and make `build_ppttc.py` iterate over it.
3. Add `verify_thinkcell_template_contract.py` before render.
4. Replace global string-ratio verification with binding-level verification.
5. Add a canary payload/render test for the template itself.
6. Split chart/text `.ppttc` render from table-image `UpdateBatch` refresh.
7. Keep XML/OLE splice scripts in `experiments/`, not the production path.

## Definition of done

For Patrick canary:

```text
required template elements missing: 0
required ppttc bindings missing: 0
required table image bindings missing: 0
forbidden/debris text findings: 0
numeric unit failures: 0
PowerPoint repair prompts: 0
PDF export: pass
```

For production:

```text
9/9 directors render from the same tcseed
9/9 directors have pptx, pdf, ppttc, deck_plan.json, evidence_manifest.json, qa_report.json
No deck uses the legacy seed
No analytic slide lacks source note or insight title
No Land+Expand ARR is blended with Renewal ACV
```
