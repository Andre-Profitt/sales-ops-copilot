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
