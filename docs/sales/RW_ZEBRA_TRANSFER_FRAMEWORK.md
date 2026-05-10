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
- raw `chartSettings.columnSettings`;
- normalized marker fields: markerStyle, showAsTable, scaleGroup, format, hidden;
- title, data-label, grid, border, background, accent, typography object groups;
- static furniture around the visual: textboxes/shapes/section headers;
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
  "rebuilt_visuals": 107,
  "visual_count_delta": 3,
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

The rebuilt visual count can exceed source count because Zebra Cards expand into native composites.

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

### ColumnSettings grammar

`chartSettings.columnSettings` is treated as the IBCS rendering grammar, not incidental style.  The transfer layer preserves the raw block and normalizes these fields per column:

- `markerStyle` -> native data bar / marker intent;
- `showAsTable` -> table vs chart representation intent;
- `scaleGroup` -> shared axis/databar scale hint;
- `format` -> integer, signed variance, percent variance format intent;
- `hidden` -> whether the native column should be suppressed or only used as support.

### Static furniture

The extractor records nearby textboxes/shapes/section headers because Zebra template readability depends on the surrounding frame.  Rebuilders must normalize that furniture into native Power BI containers.  Dropping it is considered a failed transfer even when all data visuals convert.

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
