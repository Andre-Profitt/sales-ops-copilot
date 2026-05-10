# RW Zebra Transfer Framework

Generated: 2026-05-10

## Purpose

This framework shifts the RW/Zebra work from dashboard QA and blind custom-visual conversion to granular transfer engineering.  The unit of transfer is not a page screenshot or a generic visual type.  It is a Zebra visual DNA record: semantic roles, scenario pairings, synthesized IBCS columns, columnSettings, visual styling, static furniture, and page-zone context.

The first exemplar is `sales-funnel-power-bi-template`.  Its extracted artifacts are:

- `data/zebra_kg/transfer/visual_dna_sales-funnel-power-bi-template.json`
- `data/zebra_kg/transfer/page_patterns_sales-funnel-power-bi-template.json`
- `data/zebra_kg/transfer/native_rebuild_sales-funnel-power-bi-template.report.json`
- `data/zebra_kg/transfer/rw_page_transfer_patterns.json`
- `output/rw_zebra_transfer/transfer_gate_sales-funnel-power-bi-template.json`
- `output/rw_zebra_transfer/transfer_gate_sales-funnel-power-bi-template.md`

## Scripts

### `scripts/sales/rw_zebra_transfer_dna.py`

Extracts one JSON record per Zebra visual from a full PBIX `Report/Layout`.

Each record captures:

- visual family: Tables, Cards, Charts, Waterfall;
- bounding box and page zone;
- projection roles: Category, Group, Values, PreviousYear, Plan, Forecast, Comments;
- scenario pairing: AC/PY/PL/FC;
- derived variance columns Zebra synthesizes, such as `actual-previousYear`, `actual-previousYear-percent`, `actual-plan`, `forecast-plan`;
- raw safe Zebra object groups, excluding license/activation material;
- normalized visual object grammar for `chartSettings`, `designSettings`, `dataLabelSettings`, `titleSettings`, `grid`, `multipleLayout`, and `coreSettings`;
- normalized column grammar: column order, markerStyle, showAsTable, scaleGroup, format, hidden/support-column behavior, and inferred native intent;
- title, data-label, grid, border, background, accent, typography object groups;
- page-level and visual-local furniture with proximity/overlap bands instead of all textboxes on the page;
- nearby `singleVisualGroup` containers;
- intent classification: KPI strip, movement table, variance table, waterfall, bridge chart, detail ledger.

Run locally:

```bash
uv run python -m scripts.sales.rw_zebra_transfer_dna --template sales-funnel-power-bi-template
```

### `scripts/sales/rw_zebra_transfer_rebuilder.py`

Consumes visual DNA and emits native Power BI report JSON.  It starts from the source report frame, removes custom visual packages, and replaces Zebra visuals with reusable native emitters.

Emitters:

- Zebra Card -> composite KPI tile: textbox header + value card + comparator card.  This is intentionally not a single generic card.
- Zebra Table -> native `tableEx` with IBCS order: Category/Group, AC, PY, PL, FC, then synthesized variance columns and variance %.  `columnSettings` markerStyle/showAsTable/scaleGroup/format/hidden drives compact table behavior and data bars.
- Zebra Chart -> native chart preserving category/value semantic roles, title hierarchy, colors, and spacing where available.
- Zebra Waterfall -> native `waterfallChart`/bridge equivalent with Category axis and Y/value projection.
- Static page furniture is normalized into native textboxes/shapes and kept with the page.

Run locally:

```bash
uv run python -m scripts.sales.rw_zebra_transfer_rebuilder --template sales-funnel-power-bi-template
```

Current exemplar gate writes separate QA artifacts under `output/rw_zebra_transfer/` and fails hard unless `--no-fail-on-gate` is passed.  The gate blocks lost Zebra visuals, custom leftovers, custom resource packages, fallback textboxes, blank visual types, unknown visual types, unresolved measure references, and page-count drift.  Total visual-count delta is reported for review because native rebuilds can legitimately normalize template furniture while expanding Zebra cards into composites.

```json
{
  "source_pages": 6,
  "rebuilt_pages": 6,
  "source_visuals": 104,
  "rebuilt_visuals": 101,
  "visual_count_delta": -3,
  "custom_visual_leftovers": 0,
  "custom_resource_packages": 0,
  "fallback_textboxes": 0,
  "lost_zebra_visuals": 0,
  "blank_visual_types": 0,
  "unknown_visual_types": 0,
  "unresolved_measure_refs": 0,
  "failures": [],
  "passed": true
}
```

The rebuilt visual count can differ from source count because Zebra Cards can expand into native composites while visual-local furniture and blank template containers are normalized away instead of being re-emitted as generic fallback textboxes.

## Transfer rules encoded

### Scenario grammar

Zebra roles map to scenarios as follows:

| Zebra role | Scenario |
|---|---|
| Values / Y / Measures | AC |
| PreviousYear | PY |
| Plan | PL |
| Forecast | FC |

Zebra synthesizes comparison columns from projected scenario pairs:

| Pair | Native columns |
|---|---|
| AC + PY | `AC-PY`, `AC-PY %` |
| AC + PL | `AC-PL`, `AC-PL %` |
| AC + FC | `AC-FC`, `AC-FC %` |
| FC + PL | `FC-PL`, `FC-PL %` |

The native rebuild requires these measures to exist in the target model before projecting them.  Missing synthesized measures are omitted instead of converted into fallback textboxes.

### Visual object grammar

The extractor now writes `visual_object_grammar.schema = rw-zebra-native-transfer.visualObjectGrammar.v1`.  This is a documented, safe subset of Zebra object groups rather than a blind raw-object dump.  The safe groups are:

- `chartSettings`
- `designSettings`
- `dataLabelSettings`
- `titleSettings`
- `grid`
- `multipleLayout`
- `coreSettings`

Within those groups, the extractor keeps only non-license/non-activation properties that describe transferable design behavior: color, font, title, label, grid, layout, padding, width, format, marker, scale, table/show/hidden, border/background, and transparency properties.  The raw sanitized `objects` block is still retained for auditability, but native emitters should consume the normalized grammar first.

### ColumnSettings grammar

`chartSettings.columnSettings` is treated as the IBCS rendering grammar, not incidental style.  The transfer layer preserves the raw block and normalizes these fields per column:

- `order` -> Zebra column display order;
- `markerStyle` -> native data bar / marker / variance intent;
- `showAsTable` -> table vs chart representation intent;
- `scaleGroup` -> shared axis/databar scale hint;
- `format` -> integer, signed variance, percent variance format intent;
- `hidden` -> whether the native column should be suppressed or only used as support;
- `support_column` -> hidden/helper behavior for columns that should not be displayed directly;
- `intent` -> one of `data_bar`, `bullet_or_variance_marker`, `chart_value`, `variance_delta`, `variance_percent`, or `table_value`.

Zebra-synthesized variance columns are appended to the same grammar when they are implied by scenario roles but absent from explicit column settings.  This lets the native rebuilder keep IBCS order, skip hidden support columns, and add native data-bar conditional formatting without falling back to textboxes.

### Static furniture

The extractor records page furniture and visual-local furniture separately.  Each item has `relationship`, `proximity_band`, `distance_px`, `page_zone`, and `intent`.  Proximity bands are `overlap`, `adjacent`, `nearby`, and `distant`; page headers/footers remain page furniture even when physically near an analytic visual.  Visual-local labels are preserved in DNA for analysis, but the native rebuilder does not re-emit them as generic standalone fallback textboxes.

Nearby `singleVisualGroup` containers are captured as `group_containers` with their own bounding boxes and proximity bands.  Rebuilders can use them as layout hints, while gate checks still reject blank/unknown/custom visual leftovers.

### Intent classification

Intent is inferred from family, projection roles, scenario set, and column settings:

- Cards with Group/Category -> KPI strip / KPI tile;
- Tables with multiple scenarios or comparison keys -> variance table;
- Tables with Comments -> detail ledger;
- Tables with Category + Group -> movement table;
- Waterfall with Group -> bridge chart;
- Waterfall without Group -> waterfall;
- Charts preserve chart semantics while adopting native visual types.

## Application to RW pages

The sales-funnel exemplar patterns are applied to these RW dashboard pages via `data/zebra_kg/transfer/rw_page_transfer_patterns.json`:

- VP Ops Scorecard
- What Changed
- Forecast
- Stage Hygiene
- Renewals
- Growth Mix

The RW page mapping uses the learned native equivalents:

- KPI strips use composite Zebra-card-style patterns instead of flat unstyled generic cards.
- Movement/variance sections use tableEx/pivotTable with IBCS ordering and variance/data-bar style objects.
- Charts retain semantic role and spacing rather than being used as decorative approximations.
- Static section furniture remains a first-class transfer artifact.


### Applied RW proof: What Changed

The first RW-native application is deliberately narrow: the `What Changed` page.  It uses the sales-funnel Zebra DNA as grammar, not as a direct visual copy:

- top exception-band cards keep the existing RW measures (`At Risk`, `Watch`, `Healthy` count/ARR) but use Zebra-card-style native object metadata and RAG treatment so they are auditable as `composite-risk-kpi-card` rather than plain cards;
- the 7-day movement section remains one native `tableEx` movement ledger, preserving Zebra table principles: deterministic column order, compact grid/header styling, and data-bar/scale hints via `columnGrammar.v1`;
- the opportunity queue remains a detail ledger with dense table styling, not a replacement card stack;
- no custom visual types, custom visual packages, fallback textboxes, or cross-motion ARR/Renewal blends are introduced.

### Applied RW proof: Stage Hygiene

The second RW-native application is also deliberately one page: `Stage Hygiene`.  The page keeps its original RW KPI contract and measures, including the Stage 3 forward proxy label, but now applies the Zebra-native grammar where it maps to real process diagnostics:

- the seven hero/process KPI cards use object-bearing native card grammar with `stage-hygiene-process-kpi-card` lineage, preserving RAG/accent treatment without custom visuals;
- the stage conversion/time-in-stage section is a native `tableEx` in deterministic IBCS order: stage, forward %, backward %, average days, move count, and 7-day ARR moved;
- the 7-day ARR moved measure carries native data-bar metadata to represent Zebra `markerStyle`/`scaleGroup` intent only where an actual measure supports it;
- the Stage 4 bottleneck detail stays a dense native detail ledger, not another card stack;
- no Forecast, Renewals, or Growth Mix page behavior is changed in this pass.

Reusable helpers live in `scripts/sales/rw_zebra_kg_ibcs_synth.py`:

- `zebra_native_card_objects()`
- `zebra_compact_movement_ledger_objects()`
- `zebra_stage_hygiene_table_objects()`
- `zebra_detail_table_objects()`

These helpers attach only safe lineage metadata (`stylePreset`, `zebraGrammar`) and native Power BI object groups.  They do not persist raw Zebra object payloads or license/activation material.

## Business guardrails

These are encoded in visual QA and repeated in transfer artifacts:

- ARR = Land + Expand only.
- Renewal ACV = Renewal only.
- Do not blend ARR and Renewal ACV except when explicitly labeled `Total Open Pipeline Value`.

## Validation path

Minimum local validation for this lane:

```bash
uv run pytest tests/sales/test_rw_zebra_transfer_dna.py tests/sales/test_rw_zebra_transfer_rebuilder.py -q
uv run pytest tests/sales/test_rw_zebra_kg_translator.py tests/sales/test_rw_zebra_kg_ibcs_synth.py tests/sales/test_rw_zebra_kg_native_layout_publish.py -q
uv run python -m scripts.sales.rw_zebra_transfer_dna --template sales-funnel-power-bi-template
uv run python -m scripts.sales.rw_zebra_transfer_rebuilder --template sales-funnel-power-bi-template
uv run python -m scripts.sales.rw_dashboard_visual_qa --report-json /Users/test/code/apps/sales-ops-copilot-rw/data/zebra_kg/transfer/native_rebuild_sales-funnel-power-bi-template.report.json --fail-on high
```

For the RW local lab PBIP, continue to use the existing dashboard harness and visual QA gates against:

`/Users/test/Downloads/rw-pbi-format-lab/rpt_vp_ops_scorecard_zebra_lab_20260509_pbip/rpt_vp_ops_scorecard.Report/report.json`

No Fabric publish is part of this framework.  All outputs are local report JSON/PBIP artifacts.
