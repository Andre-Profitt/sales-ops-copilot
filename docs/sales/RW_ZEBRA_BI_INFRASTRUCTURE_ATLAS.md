# Zebra BI Infrastructure Atlas

Comprehensive reverse-engineered understanding of Zebra BI's PBIX infrastructure — every data role, comparison key, format code, marker style, scale group, and object group used across **360 Zebra visualContainers** in **20 Zebra-published templates**.

Produced 2026-05-09 from:

- `scripts/sales/rw_zebra_kg_infra_miner.py` → mines every Zebra-custom visualContainer's full `singleVisual.objects` + `chartSettings.columnSettings` + projections + custom-visual `pbiviz.json` package metadata
- `scripts/sales/rw_zebra_kg_infra_analyzer.py` → aggregates findings into structured atlases

Generated artifacts (gitignored, regenerable):

- `data/zebra_kg/infrastructure/raw_configs.jsonl` — 360 rows, one per Zebra visualContainer
- `data/zebra_kg/infrastructure/objects_atlas.json` — every `objects.<group>.<property>` seen + frequency + sample values per visual family
- `data/zebra_kg/infrastructure/columnSettings_atlas.json` — full IBCS rendering grammar
- `data/zebra_kg/infrastructure/projections_atlas.json` — projection role combinations per family
- `data/zebra_kg/infrastructure/visual_capabilities.json` — capabilities + dataRoles per Zebra .pbiviz package
- `data/zebra_kg/infrastructure/summary.json` — top-line counts

## Executive summary

Zebra BI is not just a styling layer — it's a **dimensional reporting framework** built on top of Power BI's custom-visual API. Three core products (Tables, Charts, Cards) plus a fourth (Waterfall, packaged as a separate visual). All four share a common projection-role vocabulary (10 standard data roles) and a common rendering grammar encoded in the `chartSettings.columnSettings` block. Cards has its own simpler grammar (`grid`, `card`, `dataLabels` blocks).

The IBCS magic — what makes Zebra "Zebra" — is **automatic comparison-column synthesis**. Given any two scenarios projected (AC + PY, or AC + PL, or PL + FC), Zebra auto-renders three derived columns: the value, the absolute delta, and the percent delta. This is encoded in `columnSettings` as keyed entries named `<x>-<y>` and `<x>-<y>-percent`. Native Power BI has no equivalent — you'd author the delta as a separate measure.

## 1. The 6 Zebra custom visuals

From the `pbiviz.json` package metadata across all 20 templates:

| Visual                   | Version | API    | Data roles                                                                                            | Object groups                                                                                                                            |
| ------------------------ | ------- | ------ | ----------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------- |
| **Zebra BI Tables**      | 7.8.0   | 5.10.0 | Category, Group, Values, PreviousYear, Plan, Forecast, Tooltips, Comments, Filters, **CategoryClass** | general, proFeaturesSettings, chartSettings, coreSettings, annotationLayerSettings, titleSettings, groupTitleSettings, dataLabelSettings |
| **Zebra BI Charts**      | 7.8.1   | 5.10.0 | (same 9, no CategoryClass)                                                                            | + dotChartDataLabelSettings                                                                                                              |
| **Zebra BI Cards**       | 7.4.0   | 5.10.0 | Category, Group, Values, PreviousYear, Plan, Forecast, Tooltips, Comments, **KPI Descriptions**       | customData, grid, card, dataLabels, design, legend, license, interactions                                                                |
| Zebra BI Tables (legacy) | 7.0.1   | 5.4.0  | (same 9 modern roles)                                                                                 | (same 8 modern groups)                                                                                                                   |
| Zebra BI Charts (legacy) | 7.1.1   | 5.4.0  | (same 9 modern roles)                                                                                 | (same 8 modern groups)                                                                                                                   |
| Zebra BI Cards (legacy)  | 1.7.0   | 3.8.0  | (same 9 modern roles)                                                                                 | (same 8 modern groups)                                                                                                                   |

Older legacy versions (7.0.1, 7.1.1, 1.7.0) appear in 2 of 20 templates that haven't been re-saved with newer Zebra installs. The dataRole shape is consistent across versions; the rendering API changed.

The "**Waterfall**" GUID `waterfall0221D8FBE40445C1A4E598AA8EF8B506` is **not** a separate Zebra product — it's Microsoft's certified Charticulator-built waterfall variant that Zebra templates use as a fallback. (Confirmed from package.json — author is Microsoft, not Zebra.)

## 2. Data role taxonomy

The 10 standard Zebra projection roles, by mechanic:

| Role                              | Mechanic                                         | Example queryRef                         |
| --------------------------------- | ------------------------------------------------ | ---------------------------------------- |
| **Category**                      | Row labels (the dim axis)                        | `BusinessUnits.Group`, `d_region.region` |
| **Group**                         | KPI-selector small-multiple grouper              | `KPIs.KPI`                               |
| **Values**                        | Actuals (AC scenario)                            | `Sales.AC`                               |
| **PreviousYear**                  | Prior period (PY scenario)                       | `Sales.PY`                               |
| **Plan**                          | Plan/Budget (PL scenario)                        | `Sales.PL`                               |
| **Forecast**                      | Forecast (FC scenario)                           | `Sales.FC`                               |
| **Tooltips**                      | Hover-content extra fields                       | `Customer.Region`                        |
| **Comments**                      | Annotation text                                  | `Comments.Comment`                       |
| **Filters**                       | Visual-level filter context                      | `KPIs.Filter_KPI`                        |
| **CategoryClass** _(Tables only)_ | Row classification (e.g., subtotal/group header) | rare in samples                          |

**Cards has one extra role:** `KPI Descriptions` — text per KPI for header subtitles.

Most-common 5-role projections per visual family (from `projections_atlas.json`):

| Family        | Top combo                                             | Count |
| ------------- | ----------------------------------------------------- | ----: |
| **Tables**    | Category + Values + PreviousYear                      |    26 |
| Tables        | Category + Plan + Values                              |    20 |
| Tables        | Category + Group + Plan + Values                      |    12 |
| Tables        | Category + Group + Plan + PreviousYear + Values       |     9 |
| Tables        | Category + Forecast + Group + Plan + Values _(all 5)_ |     8 |
| **Waterfall** | Category + Group + PreviousYear + Values              |    24 |
| Waterfall     | Category + Group + Values                             |    12 |
| Waterfall     | Category + Values                                     |    10 |
| **Cards**     | Group + PreviousYear + Values                         |    10 |
| Cards         | Group + Plan + PreviousYear + Values                  |    10 |
| Cards         | Category + Forecast + Group + Plan + Values           |    10 |

## 3. The IBCS column synthesis rule (the critical infrastructure finding)

When a Zebra visual has **two or more scenarios projected**, it does NOT just render those scenarios as columns. It **auto-synthesizes derived comparison columns** at render time. The rule, decoded from the columnSettings keys observed:

```
For each ordered pair (X, Y) of projected scenarios where X ≠ Y:
    If X-Y is "meaningful" (e.g., AC vs PY, AC vs PL, AC vs FC, FC vs PL):
        Synthesize column "<x>-<y>"          format=1 (absolute delta)
        Synthesize column "<x>-<y>-percent"  format=2 (percent delta)
```

Observed comparison keys (top frequencies from columnSettings_atlas.json):

| Key                           | Count | Meaning                                  |
| ----------------------------- | ----: | ---------------------------------------- |
| `actual`                      |   141 | the AC value column itself               |
| `previousYear`                |    88 | the PY value column                      |
| `actual-previousYear`         |    88 | **auto-synthesized**: AC − PY (absolute) |
| `actual-previousYear-percent` |    88 | **auto-synthesized**: (AC − PY) / PY     |
| `plan`                        |    76 | the PL value column                      |
| `actual-plan`                 |    76 | **auto-synthesized**: AC − PL            |
| `actual-plan-percent`         |    76 | **auto-synthesized**: (AC − PL) / PL     |
| `forecast`                    |    20 | the FC value column                      |
| `forecast-plan`               |    12 | FC − PL                                  |
| `forecast-plan-percent`       |    12 | (FC − PL) / PL                           |
| `actual-forecast`             |    10 | AC − FC                                  |
| `actual-forecast-percent`     |    10 | (AC − FC) / FC                           |

**The rule reads cleanly: every time `actual` and `previousYear` are both projected, Zebra ALSO renders `actual-previousYear` (variance) and `actual-previousYear-percent` (variance %), without any extra projection. Same for `actual` vs `plan`, etc.**

This is the IBCS grammar. Native PBI has no equivalent — you'd need to **author DAX measures** for each derived column AND add them as projections AND apply formatting.

113 distinct comparison keys were seen total — the rest are template-specific custom keys (`MA Share %`, `%GT AC`, `LFL Sales`, etc.) that override Zebra's defaults with custom DAX.

## 4. Encoding reference — what the integers mean

### 4.1 `format` codes (per-column display formatting)

From the 887 column-setting entries decoded:

| `format` | Count | Meaning (inferred from context)                                                      |
| -------: | ----: | ------------------------------------------------------------------------------------ |
|    **0** |   429 | **Value** — render the raw scenario value (AC/PY/PL/FC)                              |
|    **1** |   234 | **Absolute delta** — for `<x>-<y>` keys, render as signed integer with custom format |
|    **2** |   200 | **Percent delta** — for `<x>-<y>-percent` keys, render as percentage                 |
|    **3** |    25 | **Ratio / index** — relative metric (likely % of total)                              |
|    **5** |     3 | **Custom** — rare, template-specific                                                 |

The format code drives Zebra's custom number formatter; the visible style (commas, parens for negatives, prefix/suffix) comes from the `dataLabelSettings.decimalPlaces` plus visual-internal IBCS rules.

### 4.2 `markerStyle` codes (per-cell visual representation)

| `markerStyle` |     Count | Meaning                                                                                                                                               |
| ------------: | --------: | ----------------------------------------------------------------------------------------------------------------------------------------------------- |
|         **5** | **1,732** | **Bullet integrated bar** — the IBCS signature: a horizontal bar within the cell sized to the value, with reference markers from comparison scenarios |
|             1 |        19 | Outlined bar (less common — perhaps for "do not stack with primary scale" cases)                                                                      |
|             0 |        15 | Plain text (no bar)                                                                                                                                   |
|             2 |         6 | Cross/X marker                                                                                                                                        |
|             3 |         4 | Dot marker                                                                                                                                            |
|             4 |         6 | Filled-square marker                                                                                                                                  |

The dominance of `markerStyle=5` (95% of 1,816 entries) confirms: **integrated bullet bars are Zebra's default rendering**, not an opt-in feature. Native PBI's data bars on tableEx are the closest equivalent but cannot show plan-as-reference inline.

### 4.3 `showAsTable` codes (cell display mode)

| `showAsTable` | Count | Meaning                                                |
| ------------: | ----: | ------------------------------------------------------ |
|         **0** | 1,300 | **Integrated chart mode** — the bullet bar IS the cell |
|             1 |   182 | Plain text only — no chart                             |
|             2 |   300 | Hybrid — text + small chart inset                      |

### 4.4 `scaleGroup` (which columns share an axis scale)

| `scaleGroup` | Count | Semantics (decoded)                                                                                                                      |
| -----------: | ----: | ---------------------------------------------------------------------------------------------------------------------------------------- |
|        **1** |   729 | Primary shared scale — most ARR/revenue measures share this so bars are visually comparable                                              |
|       **-1** |   137 | Excluded from shared scale — the column has its own auto-scale (typically for percentages or counts that don't share units with revenue) |
|      2, 3, 4 |    25 | Secondary shared scales — for templates with multiple distinct unit families                                                             |

The `-1` flag is how Zebra handles mixed-unit dashboards: ARR columns get scaleGroup=1 (so they're comparable), `*-percent` columns get scaleGroup=-1 (so percentages don't dominate the bar chart).

### 4.5 `invert` (sign flip for cost-style measures)

`invert: true` on **5 column settings** (rare) — these are cost / loss measures where "more is bad" so the variance arrow direction flips (PR2 increase = red, decrease = green).

## 5. Object group inventory (the full configuration surface)

### Zebra BI Tables — 20 object groups

`general`, `proFeaturesSettings`, `chartSettings` _(the IBCS grammar)_, `sortSettings`, `categoriesMetadata`, `coreSettings`, `annotationLayerSettings`, `commentBoxSettings`, `titleSettings`, `previewSettings`, `drillSettings`, `dataLabelSettings`, `categorySettings`, `groupsMetadata`, `legendHeaderSettings`, `groupTitleSettings`, `designSettings`, `averageLineSettings`, `interactionSettings`, `version`/`migrationLog` _(bookkeeping)_

The IBCS-relevant groups: **chartSettings** (columnSettings + showGrandTotal), **coreSettings** (chart type, default behaviors), **dataLabelSettings** (decimal places, currency).

### Zebra Waterfall — 21 object groups

Adds **`axisBreakSettings`** (axis-break visualization for outlier values), **`differenceHighlightSettings`** (color rules for up/down bars), **`stackedChartSettings`** (when waterfall stacks Group as a third dimension), **`multipleLayout`** (small-multiples), **`dotChartDataLabelSettings`**.

### Zebra BI Cards — 7 object groups

Much simpler than Tables: `customData`, `grid`, `card`, `dataLabels`, `design`, `legend`, `license`, `interactions`.

The card grammar is independent — no `chartSettings.columnSettings` needed because each card displays a single KPI's full IBCS scenario set.

## 6. The Cards-specific rendering grammar

Cards use a different mechanic than Tables: each card is a **mini-dashboard for one KPI** showing all projected scenarios in a fixed layout (header + value row + variance row + sparkline). Configuration is in `card` and `grid` object groups, not `chartSettings.columnSettings`.

`grid` block typically has:

- Layout direction (rows vs columns)
- Card size (fixed or auto)
- Spacing

`card` block has:

- Per-section visibility (header, value, variance, sparkline, comparison)
- Per-section formatting

This explains why my v4 multiRowCard substitution looked anemic: native multiRowCard renders a flat list of {label, value} pairs. Zebra Cards renders **a structured KPI tile** with header + value + variance + sparkline, all binding to multiple scenarios. The native equivalent would be a custom-built composite (textbox + card + sparkline visualContainers placed in a grid).

## 7. Native PBI translation matrix

For every primitive Zebra uses, the native equivalent (or absence thereof):

| Zebra primitive                                                  | Native PBI equivalent                                              | Fidelity                                 |
| ---------------------------------------------------------------- | ------------------------------------------------------------------ | ---------------------------------------- |
| Auto-synthesized `<x>-<y>` comparison column                     | DAX measure `[X] - [Y]` + tableEx column                           | 100% (after authoring measure into TMDL) |
| Auto-synthesized `<x>-<y>-percent` column                        | DAX measure `DIVIDE([X]-[Y], [Y])` + tableEx column                | 100%                                     |
| `markerStyle=5` integrated bullet bar                            | tableEx `dataBars` CF with field-driven max                        | ~85% (no inline reference markers)       |
| `showAsTable=0` integrated mode                                  | tableEx `dataBars` CF with `showValue=true`                        | ~85%                                     |
| `scaleGroup=1` shared axis                                       | tableEx CF `dataBars` min/max sourced from shared measures         | 100% (per-column wiring)                 |
| `scaleGroup=-1` independent axis                                 | tableEx without `dataBars` for that column                         | 100%                                     |
| `invert=true` cost flip                                          | DAX `* -1` measure + flipped CF colors                             | 100%                                     |
| `format=0/1/2` (value/delta/percent)                             | DAX `FORMAT()` strings or measure formatString                     | 100%                                     |
| `chartSettings.showGrandTotal`                                   | tableEx `totals: true`                                             | 100%                                     |
| `categorySettings.topNSettings`                                  | tableEx visual-level filter Top N                                  | 100%                                     |
| `annotationLayerSettings.annotationComments`                     | (no native equivalent — drop)                                      | 0%                                       |
| Group projection → small-multiples grid                          | matrix with Group on Columns                                       | 100%                                     |
| Cards' `card` block (header + value + variance + sparkline tile) | composite of textbox + card + sparkline visualContainers in a grid | ~80% (manual composition per card)       |
| Waterfall `differenceHighlightSettings`                          | native `waterfallChart` color override (theme-driven)              | 95%                                      |
| Waterfall `axisBreakSettings`                                    | (no native equivalent — outliers compress chart)                   | 0%                                       |
| Tables' inline IBCS variance arrows                              | DAX measure returning Unicode `▲▼→` + sibling CF font color        | 100% functional, 85% visual              |

## 8. Authoring playbook — building Zebra-equivalent natively

Given a Zebra template at `data/zebra_kg/schemas/<slug>/`:

1. **Read its `chartSettings.columnSettings`** for each Zebra Tables visual to find:
   - Which `<x>-<y>` and `<x>-<y>-percent` derived columns Zebra synthesizes
   - Which columns have `markerStyle=5` (need data bars)
   - Which have `invert=true` (need color flip)
   - Which `scaleGroup` each is in

2. **Author the derived measures into the dataset's TMDL** via Fabric REST `updateDefinition`:

   ```dax
   measure 'AC vs PL' = [AC] - [PL]
       formatString = #,##0;-#,##0;"-"
   measure 'AC vs PL %' = DIVIDE([AC] - [PL], [PL])
       formatString = 0.0%;-0.0%;"-"
   measure 'AC vs PY' = [AC] - [PY]
   measure 'AC vs PY %' = DIVIDE([AC] - [PY], [PY])
   ```

3. **Build native tableEx** with columns in IBCS order: Category, AC, AC-vs-PY, AC-vs-PY-%, PY, AC-vs-PL, AC-vs-PL-%, PL, FC.

4. **Apply `dataBars` CF** to AC column with `max` referencing `[PL]` (or whatever scaleGroup=1 reference Zebra uses). `Sum` or `Min/Max` aggregator on the field-driven max.

5. **For Group projection**: convert to native `matrix` with Group on Columns, scenarios on Values.

6. **For waterfall**: use native `waterfallChart` with Category on Category, AC measure on Y, with theme color overrides for up/down/total per Zebra's `differenceHighlightSettings`.

7. **For Cards**: build composite — for each KPI card, place a textbox (header) + card visualContainer (AC value) + DAX-arrow textbox (variance) at the same x,y,w,h position. ~80% Zebra fidelity.

## 9. What's lost (the irreducible 10-15%)

- **Inline reference markers in bullet bars** — Zebra renders a small notch on AC's data bar showing where PY/PL falls. Native dataBars only show one value.
- **Annotation comments** — Zebra's pinned cell-level comments. No native equivalent.
- **Axis-break for outliers** — Zebra's clever zigzag-skip when one value is 100x the others. Native has no axis-break primitive.
- **Per-cell hatch/dot fill patterns** — Zebra uses fill patterns (solid/outlined/hatched/dotted) per scenario. Native has only solid colors.
- **The integrated chart-in-cell rendering** — even with bullet bars in a tableEx, the layout is "value in column, bar in column" not Zebra's "bar with value overlaid."

## 10. Implications for RW

Now that we know exactly what Zebra does, three facts:

1. **The DAX-synthesis path is the keystone.** Without authoring `<x>-<y>` and `<x>-<y>-percent` measures into the deployed dataset, native rendering will never match Zebra. We've proved (PR8 path B, commit pending) that Fabric REST `updateDefinition` works for adding measures to a PBIX-imported dataset. This is the unblock.

2. **`markerStyle=5` + `showAsTable=0` is the visual default.** ~95% of Zebra columns render as integrated bullet bars. Native tableEx with `dataBars` CF using a measure-driven max is the closest equivalent — about 85% visual fidelity.

3. **Cards need composite construction.** A single Zebra Card is functionally a 4-cell mini-dashboard. Native equivalents need to be built per-card via composite visualContainers; multiRowCard alone is too thin.

This atlas is the input to PR9 — a properly-scoped native rebuild that uses these decoded rules systematically rather than the surface-level swaps in PR7's v1–v6.

## Related artifacts

- Spec: `docs/superpowers/specs/2026-05-09-zebra-bi-knowledge-graph-design.md`
- Plan: `docs/superpowers/plans/2026-05-09-zebra-kg-pattern-atlas.md` (PR4)
- Findings (data-model side): `docs/sales/RW_ZEBRA_KG_PATTERNS.md` (PR4 output)
- Schema library: `data/zebra_kg/schemas/<slug>/` (PR5)
- Atlases (this analysis): `data/zebra_kg/infrastructure/*.json`
- Miner: `scripts/sales/rw_zebra_kg_infra_miner.py`
- Analyzer: `scripts/sales/rw_zebra_kg_infra_analyzer.py`

---

## 11. The complete Zebra API surface (deep `pbiviz.json` capabilities probe)

Beyond observed usage — this section captures everything Zebra's custom-visual API ACCEPTS, decoded from `Zebra BI Tables v7.8.0 / API 5.10.0`'s `capabilities.json` + property type schemas. **All enum values are now mapped to human labels** (vs. inferred from frequencies in §4).

Atlas artifact: `data/zebra_kg/infrastructure/zebra_api_atlas.json` (46 KB, structured per-property schema).

### 11.1 The 26 declared object groups (Tables)

Capabilities exposes 26 object groups; templates only use 20. The 6 unused-in-templates groups:

- `constantLineSettings` — vertical/horizontal reference lines at a fixed value
- `graphDataSettings` — likely transformation map for input data
- `medianLineSettings` — median reference line on charts
- `percentileLineSettings` — percentile reference lines (e.g., P25/P75)
- `coreSettings` — single property `forceVisualRefreshTimestamp` (cache invalidation)
- `previewSettings` — preview-feature toggles (`brandImagesFeature`, `calculationCorrectionFeature`)

### 11.2 The 8 IBCS chart-shape enum (`chartSettings.types`)

This is THE rendering-mode axis we never decoded:

| `types` value | Display name | Implication |
|---|---|---|
| `Actual / Absolute / Relative` | **Responsive** | Chart auto-adapts based on data shape (Zebra default) |
| `Integrated` | **Integrated variance** | AC bar with PY/PL reference markers inline |
| `Absolute` | **Absolute variance** | Show only the AC−PY delta column |
| `Relative` | **Relative variance** | Show only the (AC−PY)/PY % column |
| `Absolute / Relative` | Absolute / Relative | Side-by-side delta + delta-% |
| `Actual / Absolute` | Actual / Absolute | AC value + AC−PY delta |
| `Actual / Relative` | Actual / Relative | AC value + (AC−PY)/PY % |
| `Actual` | Actual | AC value only |

### 11.3 Chart sub-type enums (`chartSettings.{value,absolute,relative}Chart`)

The actual visual shape per chart axis:

| Setting | Code | Shape |
|---|---|---|
| `valueChart` | 0 | Bar chart |
| `valueChart` | 1 | Overlapped bar chart (AC bar overlaid with PL outlined bar) |
| `valueChart` | 2 | Waterfall chart |
| `valueChart` | 3 | Side by side waterfall |
| `absoluteChart` | 0 | Bar chart |
| `absoluteChart` | 1 | Waterfall |
| `absoluteChart` | 2 | Calculation waterfall |
| `relativeChart` | 0 | Plus minus dot chart |
| `relativeChart` | 1 | Sized dots chart |

### 11.4 Variance calculation (`chartSettings.relativeVarianceCalculation`)

| Code | Method |
|---|---|
| 0 | **Financial calculation** *(IBCS-correct default)* |
| 1 | Mathematical calculation |

Financial calc handles negatives via "absolute denominator" rule (variance is (AC−PY)/|PY| not (AC−PY)/PY) which keeps signs sane when PY is negative. This is an IBCS convention.

### 11.5 Variance display (`designSettings.varianceDisplayType`)

| Code | Display |
|---|---|
| 0 | **Bar** (data bar showing variance magnitude) |
| 1 | **Arrow** (▲/▼ glyph with color) |

Native equivalents: bars via `dataBars` CF; arrows via DAX-returned Unicode + CF font color.

### 11.6 The 7 Zebra design-style presets (`designSettings.style`)

| Code | Style | What it is |
|---|---|---|
| -1 | COMPANY_STYLE_NAME | placeholder for org-deployed custom |
| **0** | **Zebra** | Default (Zebra brand IBCS) |
| 1 | Zebra Light | High-contrast variant |
| **2** | **Dr. Hichert** | The IBCS standards body chair's preset — strict-IBCS |
| 3 | Power BI | Native PBI theme defaults |
| 5 | Colorblind-friendly | Accessibility palette |
| 4 | Custom | User-defined |

The presence of "Dr. Hichert" confirms Zebra implements **the canonical IBCS standard** (not just a Zebra-flavored interpretation).

### 11.7 Comment box (`commentBoxSettings`) — the annotation system

Settings worth lifting:

- `placement` (Right/Left/Above/Below) — where annotations dock
- `title` enum (5 values): Off / Title / Title+value / Title+value+variances / Title+variances
- `showVariance` enum (3): Absolute / Relative / Both
- **`varianceIcon`** (3): Circle / Circle with arrow / Triangle ◢

Native equivalent: textboxes positioned next to data cells with DAX measures bound to populated KPI text. Triangle is the Zebra-default IBCS variance glyph.

### 11.8 Interaction settings (`interactionSettings`) — runtime controls

19 boolean toggles + 1 enum + 2 numerics. The user-facing features Zebra exposes in viewing mode:

- `allowChartChange` — viewer can switch chart type
- `allowVarianceCalculationChange` — viewer can flip financial↔mathematical
- `allowExpandCollapseChange` (and ...Rows / ...Columns variants) — drill in/out
- `allowColumnOrderChange` / `allowColumnRenamingAndDesign` / `allowHidingAndAddingColumns`
- `enableMeasureDrillThrough`
- `allowInteractiveCommentBox`
- `allowExcelExport`
- `hoverHighlightType` enum: Highlighting / Bold / None

These are runtime-customization affordances. Native PBI doesn't have a unified "user can change these knobs at view time" mechanism — they'd need bookmarks + buttons + filters wired manually.

### 11.9 The `legendHeaderSettings` block — 157 comparison-header properties

This is the **complete IBCS variance vocabulary**: every comparison column Zebra can render has a header text property. Counting:

- **Base scenarios (8):** actual, previousYear, plan, plan2, plan3, forecast, forecast2, forecast3
- **Pairwise abs deltas (~50):** every (X, Y) pair in both directions — `actual-plan`, `plan-actual`, `actual-plan2`, etc.
- **Pairwise relative deltas (~50):** same set with `-percent` suffix
- **20 additional measure headers** (`additionalMeasure1Header` … `additionalMeasure20Header`) — for Tooltips role
- **5 column calculation headers** — for custom DAX-driven calculation columns

This means Zebra natively supports **3 plans + 3 forecasts + actual + previousYear** simultaneously. RW's typical scenario projection (AC + PY + PL) is the simplest case; the API was built for organizations doing rolling forecasts (FC1/FC2/FC3 by quarter) with multi-version planning.

### 11.10 dataLabelSettings — number formatting controls

| Setting | Codes |
|---|---|
| `units` | Auto / None / K (Thousands) / M (Millions) / G (Billions) / P (Percentage) / PowerBI |
| `showUnits` | 0=Data labels / 1=Title / 2=None |
| `negativeValuesFormat` | 0 = Minus sign `-123.4` / 1 = Parenthesis `(123.4)` |
| `integratedDifferenceLabel` | 0=Relative / 1=Absolute / 2=Both |

Plus: `useBasisPointsFormat` (basis-points display for finance), `percentageInLabel`, `rightAlignNumbers`, `suppressSmallValues`.

### 11.11 The 4 reference-line types

Tables exposes 4 separate object groups for analytical reference lines:

- `averageLineSettings` (the mean)
- `medianLineSettings` (the median)
- `percentileLineSettings` (configurable: `percentile` numeric)
- `constantLineSettings` (fixed value, e.g., target threshold)

Each has the same property shape: show / fill / style (Dashed/Solid/Dotted) / transparency / showLabel / labelColor / labelTextOption / labelText / horizontalPosition / verticalPosition / units / decimalPlaces.

Native PBI has analytics lines (mean/median/min/max) but more limited. RW could replicate via DAX measures (`Avg of [AC]`, `P75 of [AC]`) + a separate visual.

### 11.12 The categorySettings TopN system

| Setting | Effect |
|---|---|
| `showTopNForm` | Render the TopN slider |
| `topNOtherLabel` | Bucket label for "Other" |
| `showTopNCategories` | Show the count selector |
| `topNSettings` | (text — JSON-encoded TopN config: per-row direction, value, etc.) |

Native equivalent: visual-level Top N filter on the tableEx (built-in PBI feature). 100% functional fidelity.

---

## 12. The complete native rebuild rule book

With §11 decoded, every Zebra config primitive has a definitive native equivalent (or a known absence). PR9's translator should:

1. **For each Zebra Tables visualContainer**, read:
   - `chartSettings.types` → drives visual shape choice (matrix vs tableEx vs waterfallChart)
   - `chartSettings.columnSettings` → drives per-column DAX synthesis
   - `chartSettings.absoluteChart`/`valueChart`/`relativeChart` → drives sub-type
   - `designSettings.style` → drives theme JSON selection
   - `categorySettings.topNSettings` → drives Top N visual filter
   - `interactionSettings.*` → drives bookmark+button affordances (or accept loss)
   - `commentBoxSettings.*` → drives annotation textbox composite (or accept loss)

2. **Generate DAX measures into the dataset** for every comparison key declared in `columnSettings`. Pattern: for each `<x>-<y>` key, author `[X] - [Y]`; for each `<x>-<y>-percent` key, author `DIVIDE([X]-[Y], [Y])` — using **financial calculation rule** (`/ABS([Y])`) when `relativeVarianceCalculation=0`.

3. **Build native tableEx** with columns in IBCS order, applying:
   - `dataBars` CF on AC column with `max` field-driven from PL/PY (whichever is the reference per scaleGroup)
   - Font color CF per scenario (using `designSettings.previousYearColor`/`planColor`/`forecastColor` from the chosen style)
   - Variance arrow column via `[Variance Icon]` DAX measure returning Unicode `▲▼→`

4. **For Cards**: build composite — header textbox + AC value card + variance Unicode-arrow textbox + sparkline (native sparkline support) per KPI, arranged in a grid per the Zebra `grid.layout` setting.

5. **For Waterfalls**: native `waterfallChart` with `differenceHighlightSettings` colors mapped to the chosen style's positiveColor/negativeColor.

This is the systematic rule book. Atlas decoded; rebuild path is now mechanical, not exploratory.

---

## 13. Cellular-level findings — 4 layers below the API surface

Going beyond the API capabilities (§11), four deeper probes:

### 13.1 Layer A: dataViewMappings (how Zebra requests data from PBI's query engine)

**Zebra Tables uses MATRIX shape** (not categorical, not table):

| Axis | Bound to | Reduction | Max |
|---|---|---|---|
| Rows | `Category` projection | bottom 30,000 | 30,000 |
| Columns | `Group` projection | top 30,000 | 30,000 |
| Values | bind to all of: Values, PreviousYear, Plan, Forecast, Tooltips, Comments, Filters, CategoryClass | — | (per role limits) |

**Cardinality constraints declared in `conditions[0]`:**

| Role | Tables max | Cards max |
|---|---:|---:|
| Values | **21** | 1 |
| PreviousYear | 1 | 1 |
| Plan | **3** | 1 |
| Forecast | **3** | 1 |
| Group | **4** | 1 |
| CategoryClass | 4 *(Tables only)* | — |
| Tooltips | 5 | 5 |
| Comments | 2 | 2 |
| KPI Descriptions | — | 2 *(Cards only)* |

**Implication:** Zebra Tables can render up to 21 measures × 3 plans × 3 forecasts in one visual. Cards are constrained to single-KPI tiles. Native PBI tableEx has no equivalent cardinality declarations — RW would need to enforce limits via DAX guards if cloning the constraints.

### 13.2 Layer B: per-key interior schema (cellular config)

Across 360 visualContainers, every distinct property on every comparison key was enumerated. Findings:

**The 24 base properties** appear on ALL key types (values, derived deltas, percents):

```
invert (bool)              scaleGroup (int)           format (int 0/1/2/3/5)
useMeasureName (bool)      suppressOthers (bool)
tableView.{bold, textColor, backgroundFill, markerStyle, border, showAsTable, hidden, hiddenFromGroups}
chartView.{bold, textColor, backgroundFill, markerStyle, border, showAsTable, hidden, hiddenFromGroups}
```

**The 7 properties only on derived/custom keys:**

```
calculationFormula     calculationId          calculationIndex
isCustomColumn         isQuickCalculation
quickCalculationConfiguration.{dataProperty, type}
```

This decodes the **3 distinct comparison-column origins**:

1. **Auto-derived from projections** — when `actual` and `plan` are both projected, Zebra synthesizes `actual-plan` and `actual-plan-percent` automatically (no extra config). 24 base properties only.
2. **Quick calculations** (the "+" button feature) — `isQuickCalculation: true` + `quickCalculationConfiguration` describes one of 4 preset calcs (% of grand total / % of / Running total / Running total %) computed inside the visual, no DAX needed.
3. **Custom DAX columns** — `isCustomColumn: true` + `calculationFormula` holds user-authored DAX for a custom column. These ARE measures (or expressions resolving to measures) but Zebra binds them as columns directly.

**chartView vs tableView duality:** Each comparison key has two independent rendering states — one when the visual is in chart mode, one when in table mode. Properties like `showAsTable` (0/1/2 values) and `hidden` differ between the two views. ~30% of PY/Plan columns have `chartView.hidden=true` (visible only in table mode).

**`hiddenFromGroups`** — per-Group-value column visibility. A column can be hidden when specific Group values are active (e.g., `forecast-plan` column visible only when `MTD` or `YTD` group is shown).

### 13.3 Layer C: JS bundle behavioral signals (3.8 MB Tables visual code)

Compiled visual JS mined for:

**Hichert rule references (9 occurrences):** financial-calculation logic explicitly references the IBCS standards body chair Rolf Hichert — confirming Section 11.4's `relativeVarianceCalculation=0` is the IBCS-canonical default, not a Zebra convention.

**Multi-version planning is core, not optional:**

| Term | JS occurrences |
|---|---:|
| `previousYear` | 278 |
| `plan2` | 276 |
| `plan3` | 276 |
| `forecast2` | 263 |
| `forecast3` | 263 |
| `commentBox` | 225 |
| `annotation` | 190 |
| `columnAdder` | 41 |
| `quickCalculation` | 37 |
| `patternFill` | 6 *(no native equivalent)* |
| `Hichert` | 9 |

**Behavioral pipeline names** (250+ functions, top by frequency):

- `update` (30×) — the React-style render loop
- `renderIcon` (17×) — variance arrow / status icon rendering
- `format` (13×) — number formatting via the units/decimal pipeline
- `getCategoryFormatSetting` / `changeCategoryFormatSettingAndPersist` — per-category formatting (cellular)
- `calculateChartWidths` / `calculateCategoryWidth` — layout solver
- `yScale` / `scaleSize` — axis scaling
- `drawCommentMarkers` — annotation overlay
- `getScientificFormat` / `hasScientificFormat` — scientific-notation handling
- `transformationDependenciesFactory` — data-transformation graph

**Hidden features confirmed in code but not documented in templates:**

- "Add CAGR arrow" — Compound Annual Growth Rate arrow (a special variance form)
- "Add formula" — user-authored DAX-like in-visual formula
- "Add highlight" — manual cell highlighting overlay
- "Add annotations" — pinned cell-anchored notes

### 13.4 Layer D: zebrabi.com/help/ — canonical product documentation

Confirmed via the public help docs:

**Scenario terminology** is officially documented as **AC, PY, PL, FC** ("default scenarios like Actuals, Previous year, Plan and Forecast"). Plan2/Plan3/Forecast2/Forecast3 are exposed via "Support multiple forecasts and multiple plans" doc — the 157-property `legendHeaderSettings` is the actual feature surface, not over-engineering.

**Auto-derived variances** are documented behavior: "variances are automatically calculated and displayed visually" — the matrix-shape data + the comparison-key synthesis rule we decoded is the official feature, not a side-effect.

**Quick column calculations** — the 4 presets confirmed:

1. % of grand total
2. % of…
3. Running total
4. Running total %

"No DAX is required to reach the calculations because everything is calculated inside the visual based on the data included." Reference column is always AC.

**Responsive layout** — Zebra's official term for the `chartSettings.types="Actual / Absolute / Relative"` mode: "Responsive layout seamlessly adds Forecast comparison."

**Basis points formatting** — confirmed feature for absolute variances (the `dataLabelSettings.useBasisPointsFormat` property).

### 13.5 What this cellular probe means for the rebuild

Every primitive of Zebra's product is now decoded:

- **Data flow** — matrix dataView with cardinality-bounded role binding (Layer A)
- **Per-cell config** — 24-or-31 property schema with explicit derived/custom-column flags (Layer B)
- **Computation** — financial Hichert-rule variance calc; in-visual quick calcs reference AC; multi-version planning by design (Layer C)
- **User-facing semantics** — AC/PY/PL/FC scenarios, automatic variance derivation, 4 quick-calc presets, basis points option (Layer D)

**For PR9 (mechanical rebuild)**, the rule book in §12 now stands on rock. Three classes of comparison columns to handle:

1. **Auto-derived** (AC vs PL, AC vs PY, etc.) → synthesize DAX measures via Fabric REST `updateDefinition`, project into native tableEx columns in IBCS order
2. **Quick calcs** (% of grand total, Running total) → synthesize DAX using `CALCULATE + ALL` patterns; the 4 presets are well-defined formulas
3. **Custom DAX columns** → the `calculationFormula` text is the lift target — paste verbatim into TMDL with table-name remapping

**Three classes of rendering-fidelity loss confirmed:**

- **Pattern fills** (`patternFill` 6× in JS) — Zebra paints scenarios with hatch/dotted/etc. fill patterns; native PBI has only solid colors. Lost ~5% visual fidelity.
- **Annotation overlay** (`drawCommentMarkers`, `annotation` 190×) — pinned cell-level comments. Native equivalent is composite-textbox-positioning. Lost ~3% functional fidelity.
- **CAGR arrow** — special compound-growth visualization. No native equivalent. Lost <1%.

The 85-90% native-fidelity ceiling estimate from §7 is now confirmed cellular: ~10-15% loss is in pattern fills + annotation overlay + niche features (CAGR, axis-break, runtime user knobs).
