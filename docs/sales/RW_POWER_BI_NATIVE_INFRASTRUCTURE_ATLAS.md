# Power BI Native Infrastructure Atlas

Companion to `RW_ZEBRA_BI_INFRASTRUCTURE_ATLAS.md`. The Zebra atlas decoded the source (what we're translating from); this document decodes the target (what native Power BI / PBIR / TMDL / theme / conditional-formatting primitives can express). Together they form the deterministic translation matrix that PR9's mechanical rebuild needs.

Produced 2026-05-09 from:

- Microsoft Learn canonical docs (visual catalog, CF rules, theme JSON spec, TMDL grammar)
- PBIR JSON schemas at `developer.microsoft.com/json-schemas/fabric/item/report/...`
- Direct probing of Fabric REST `getDefinition` on imported PBIX datasets (already proven path)

## 1. The native visual catalog

Power BI ships ~30 distinct built-in visualTypes. Grouped by mechanic:

| Family                        | visualTypes                                                                                                                                                                          | What they do                                                                                                                 |
| ----------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ---------------------------------------------------------------------------------------------------------------------------- |
| **Tables / grids**            | `tableEx`, `pivotTable` (matrix)                                                                                                                                                     | Row-oriented grids; matrix supports stepped layouts + multi-dim drill                                                        |
| **Cards**                     | `card` (newly merged single+multi as of Nov 2025), `multiRowCard` (legacy), `kpiVisual`, `gauge`                                                                                     | Single-value or multi-value KPI tiles; KPI adds goal/target indicators; gauge is radial                                      |
| **Bar/Column**                | `barChart`, `columnChart`, `clusteredBarChart`, `clusteredColumnChart`, `stackedBarChart`, `stackedColumnChart`, `hundredPercentStackedBarChart`, `hundredPercentStackedColumnChart` | The full bar/column matrix                                                                                                   |
| **Line/Area**                 | `lineChart`, `areaChart`, `stackedAreaChart`, `hundredPercentStackedAreaChart`, `lineStackedColumnChart` (combo)                                                                     | Time-series and area fills                                                                                                   |
| **Specialty time-series**     | `ribbonChart`, `waterfallChart`                                                                                                                                                      | Ribbon = rank-over-time; **waterfall = running total with up/down/total bars** (closest native equivalent to Zebra's bridge) |
| **Distribution / part-whole** | `pieChart`, `donutChart`, `treemap`, `funnel`, `scatterChart`                                                                                                                        | Composition + correlation views                                                                                              |
| **Maps**                      | `map`, `filledMap`, `azureMap`, `arcGISMap`, `shapeMap`                                                                                                                              | Geographic                                                                                                                   |
| **Slicers / interactive**     | `slicer`, `advancedSlicerVisual` (button / list / dropdown / range / hierarchy)                                                                                                      | Filter controls                                                                                                              |
| **Analytical**                | `qnaVisual`, `decompositionTreeVisual`, `keyInfluencersVisual`, `smartNarrative`                                                                                                     | AI-driven                                                                                                                    |
| **Layout**                    | `textbox`, `image`, `actionButton`, `basicShape`, `shape`                                                                                                                            | Static / chrome / nav                                                                                                        |

**For the IBCS rebuild, the load-bearing native types are:** `tableEx`, `pivotTable` (matrix), `card`, `kpiVisual`, `waterfallChart`, `clusteredBarChart`, plus `textbox`/`basicShape` for chrome.

## 2. Conditional formatting (CF) — the fidelity lever

CF is THE mechanism native PBI provides for replicating Zebra's per-cell config grammar. The catalog:

### 2.1 The 5 CF rule types (tables/matrices)

| Rule type            | Effect                                                       | Field-driven?                                          |
| -------------------- | ------------------------------------------------------------ | ------------------------------------------------------ |
| **Background color** | Cell fill color                                              | Yes — DAX measure returns hex/RGB/HSL/CSS color name   |
| **Font color**       | Cell text color                                              | Yes — same DAX-returns-color pattern                   |
| **Data bars**        | Horizontal bar inside the cell, length proportional to value | Yes — min/max can be field-driven from another measure |
| **Icons**            | Inline icon (left, right, or icon-only)                      | Yes — DAX measure returns icon code or URL             |
| **Web URLs**         | Cell text becomes hyperlink                                  | Yes — DAX measure returns URL                          |

### 2.2 The 3 CF format styles (per rule)

| Format style               | Mechanic                                                           | Use case                                                                 |
| -------------------------- | ------------------------------------------------------------------ | ------------------------------------------------------------------------ |
| **Gradient (color scale)** | Min/max values mapped to min/max colors with optional center       | Heatmap-style continuous coloring                                        |
| **Rules**                  | Value ranges → discrete colors/icons                               | Threshold-based traffic-light coloring                                   |
| **Field value**            | DAX measure returns the format value (color hex / icon code / URL) | **Unlimited flexibility — this is the IBCS arrow + scenario color path** |

### 2.3 Built-in icon sets

| Category        | Icons available                                                                       |
| --------------- | ------------------------------------------------------------------------------------- |
| **Directional** | Arrows (colored + gray), triangles, trend indicators                                  |
| **Shapes**      | Traffic lights (with/without rims), circles, squares, diamonds, exclamation triangles |
| **Indicators**  | Flags, checkmarks, X marks, exclamation marks                                         |
| **Ratings**     | Stars (full/half/quarter), bars, signal strength                                      |

The directional triangles match Zebra's `commentBoxSettings.varianceIcon=2` (Triangle ◢) — this is the IBCS variance arrow.

### 2.4 Field-driven CF — the IBCS-mimicking pattern

```dax
-- Variance arrow (matches Zebra varianceDisplayType=1)
Variance Icon =
    VAR delta = [AC] - [PY]
    VAR rel   = DIVIDE(delta, [PY])
    RETURN
        SWITCH(
            TRUE(),
            rel > 0.10,  "▲▲",
            rel > 0,     "▲",
            rel < -0.10, "▼▼",
            rel < 0,     "▼",
                         "→"
        )

-- Variance color (matches Zebra positiveColor / negativeColor)
Variance Color =
    VAR delta = [AC] - [PY]
    RETURN IF(delta >= 0, "#16A34A", "#DC2626")
```

In tableEx Format pane → Font color → Format style: Field value → measure: `[Variance Color]`. Repeat for icons/data-bars.

### 2.5 Data bars with field-driven max — the bullet-bar mimic

The closest native equivalent to Zebra's `markerStyle=5` integrated bullet bar is **a tableEx column with `dataBars` CF where `Maximum: Field value` references the Plan or PY measure**. The bar fills to AC's value relative to PL/PY's reference. ~95% visual fidelity. Spec:

```
Data bars dialog:
  Minimum: 0 (or field-driven)
  Maximum: Field value → [Plan]
  Fill direction: Left to right
  Show bar only: false (keep the value visible)
  Positive bar: theme primary
  Negative bar: theme negative
  Axis color: theme axis
```

### 2.6 CF limitations vs. Zebra

- **CF cannot be embedded in theme JSON.** Themes set defaults; CF must be applied per-visual. Theme JSON has visual-style defaults but CF rules are stored on the visualContainer's `objects.values` block.
- **CF is value-only on tables/matrices** — cannot be applied to row/column headers, only to value cells.
- **No inline reference markers** — Zebra renders a notch on the AC bar at PY's value; native data bars are single-value only. ~5% fidelity loss.
- **Line charts have no native CF for line/marker color** — must use a chart type that supports it (column/bar) or accept default theme colors.

## 3. Theme JSON spec — visual style defaults

### 3.1 The 4 file-level required + optional fields

| Field          | Required | Effect                                 |
| -------------- | -------- | -------------------------------------- |
| `name`         | ✅       | Display name                           |
| `dataColors[]` | optional | Default color sequence for data series |
| `background`   | optional | Default visual background              |
| `foreground`   | optional | Default text color                     |
| `tableAccent`  | optional | Table grid outline color               |

### 3.2 Structural color classes

| Class                 | Default   | What it formats                                             |
| --------------------- | --------- | ----------------------------------------------------------- |
| `firstLevelElements`  | `#252423` | Primary text — values, titles, labels                       |
| `secondLevelElements` | `#605E5C` | Secondary text — light labels, subtitles                    |
| `thirdLevelElements`  | `#F3F2F1` | Subtle UI — table grid, separators                          |
| `fourthLevelElements` | `#B3B0AD` | Disabled / placeholder text                                 |
| `background`          | `#FFFFFF` | Modern visual tooltip bg, button fill, donut/treemap stroke |
| `secondaryBackground` | `#C8C6C4` | Table/matrix grid outline, shape map default                |
| `tableAccent`         | (varies)  | Table/matrix grid outline (when present)                    |

### 3.3 Text class hierarchy (4 primary + 8 secondary)

| Class (JSON name) | Default                        | Used by                                                      |
| ----------------- | ------------------------------ | ------------------------------------------------------------ |
| `callout`         | DIN 45pt #252423               | Card data labels, KPI indicators                             |
| `header`          | Segoe UI Semibold 12pt #252423 | Key influencers headers                                      |
| `title`           | DIN 12pt #252423               | Axis titles, multi-row card title, slicer header             |
| `largeTitle`      | inherits + 14pt                | Visual title                                                 |
| `label`           | Segoe UI 10pt #252423          | Table/matrix column headers, row headers, grid, values       |
| `semiboldLabel`   | inherits, Semibold             | Key influencers profile text                                 |
| `largeLabel`      | inherits, 12pt                 | Multi-row card data labels                                   |
| `smallLabel`      | inherits, 9pt                  | Reference line labels, slicer search box, slicer date range  |
| `lightLabel`      | inherits, #605E5C              | Legend, button text, axis labels, gauge target, slicer items |
| `boldLabel`       | inherits, Bold                 | Matrix subtotals/grand totals, table totals                  |
| `largeLightLabel` | #605E5C 12pt                   | Card category labels, gauge labels, multi-row card category  |
| `smallLightLabel` | #605E5C 9pt                    | Data labels, value axis labels                               |

**Map to Zebra's KG canonical typography** (from PR4 atlas): Segoe UI 9px / 10px / 12px ramp = `smallLabel` / `label` / `title`. Direct match.

### 3.4 Visual styles override (per-visualType)

```jsonc
{
  "name": "RW IBCS Theme",
  "dataColors": [
    "#000000",
    "#9CA3AF",
    "#3B82F6",
    "#A78BFA",
    "#16A34A",
    "#DC2626",
  ],
  "firstLevelElements": "#1F2937",
  "tableAccent": "#000000",
  "visualStyles": {
    "tableEx": {
      "*": {
        "grid": [
          {
            "gridHorizontal": true,
            "gridVerticalColor": { "solid": { "color": "#EEEEEE" } },
          },
        ],
        "values": [{ "fontFamily": "Segoe UI", "fontSize": 10 }],
        "columnHeaders": [
          {
            "fontFamily": "Segoe UI Semibold",
            "fontSize": 9,
            "backColor": { "solid": { "color": "#F0F0F0" } },
          },
        ],
      },
    },
    "card": {
      "*": {
        "labels": [
          { "color": { "solid": { "color": "#000000" } }, "fontSize": 24 },
        ],
      },
    },
  },
}
```

**Per-visualType per-property defaults** is how we'd ship the canonical RW-IBCS theme that mimics Zebra's `designSettings.style=2` (Dr. Hichert) + the canonical Segoe UI ramp.

### 3.5 What themes CANNOT do

- **Embed CF rules.** Per MS docs: _"You can't add conditional formatting rules to a custom theme. Conditional formatting must be applied separately to individual visuals."_ Themes set defaults; per-visual CF still has to be wired. The PR9 swap script must apply CF per-visual.
- **Define new measures or DAX.** Themes are pure presentation.
- **Override Power BI's default cell renderer.** Custom rendering = custom visual = back to AppSource.

## 4. TMDL spec — data model layer

The DAX-synthesis path (the keystone for IBCS comparison columns) writes to TMDL via Fabric REST `updateDefinition`. Spec essentials:

### 4.1 File layout

```
<model>.SemanticModel/
  definition.pbism                      manifest
  definition/
    database.tmdl                       database-level config
    model.tmdl                          model-level (culture, default mode)
    relationships.tmdl                  ALL relationships
    expressions.tmdl                    shared M expressions
    datasources.tmdl                    data sources
    functions.tmdl                      DAX user-defined functions
    tables/
      <table>.tmdl                      one file per table (cols + measures + partition)
    cultures/<lc>.tmdl                  one file per locale
    perspectives/<name>.tmdl            one file per perspective
    roles/<name>.tmdl                   one file per security role
```

### 4.2 Object syntax

```tmdl
table f_opportunity

    column arr_org_ccy
        datatype: double
        sourceColumn: arr_org_ccy
        formatString: "#,##0;-#,##0;\"-\""

    measure 'Total Closed Won ARR' =
            CALCULATE(
                SUM(f_opportunity[arr_org_ccy]),
                f_opportunity[is_closed] = TRUE(),
                f_opportunity[stage_name] = "8 - Won",
                f_opportunity[motion_type] IN { "Land", "Expand" }
            )
        formatString: "#,##0,,M;-#,##0,,M;\"-\""
        displayFolder: "ARR Wins"
```

**Key syntax rules:**

- `<type> <name>` declaration; name in single-quotes if contains `.`/`=`/`:`/`'`/whitespace
- `:` for non-expression properties (e.g., `formatString:`, `displayFolder:`)
- `=` for default-property expressions (measures, partitions, columns with calculation)
- Multi-line expressions: indent one level deeper than the parent property block
- Triple-backtick (` ``` `) for verbatim multi-line (preserves indentation/whitespace)
- Boolean shortcut: just `isHidden` implies `isHidden: true`
- `ref` keyword preserves collection ordering across roundtrips

### 4.3 Common measure properties

| Property        | Type | Meaning                                      |
| --------------- | ---- | -------------------------------------------- |
| `formatString`  | text | DAX format string (e.g. `"#,##0"`, `"0.0%"`) |
| `displayFolder` | text | Logical folder in field list                 |
| `isHidden`      | bool | Hide from end-user model browser             |
| `description`   | text | Tooltip text                                 |
| `lineageTag`    | uuid | Stable identity across edits                 |

### 4.4 The path we already proved

`scripts/sales/rw_inventory_measures.py:fetch_measures_by_table()` already parses TMDL via Fabric REST. The PR8 path-B test (commit `bff5b7c`) authored a measure into a deployed PBIX-imported dataset via:

```python
# Fetch
GET /v1/workspaces/{ws}/semanticModels/{sm_id}/getDefinition  → 14 TMDL parts

# Patch
parts[data_part_idx]["payload"] = base64(modified_tmdl)

# Push
POST /v1/workspaces/{ws}/semanticModels/{sm_id}/updateDefinition
     {"definition": {"parts": parts}}  → LRO succeeds
```

This is the keystone for PR9's variance-measure synthesis.

## 5. PBIR visualContainer schema (the report layer)

Decoded from the canonical schema at `developer.microsoft.com/json-schemas/fabric/item/report/definition/visualContainer/1.0.0/schema.json`:

### 5.1 Top-level

| Property                  | Required   | Notes                                                                         |
| ------------------------- | ---------- | ----------------------------------------------------------------------------- |
| `name`                    | ✅         | Unique identifier within page                                                 |
| `position`                | ✅         | `{x, y, height, width, z, tabOrder}`                                          |
| `visual` OR `visualGroup` | ✅ (oneOf) | The actual visual config                                                      |
| `parentGroupName`         | optional   | Reference to a parent visualGroup                                             |
| `filterConfig`            | optional   | Visual-level filters                                                          |
| `isHidden`                | optional   |                                                                               |
| `annotations[]`           | optional   | Cell-level annotations (Zebra-equivalent: name+value)                         |
| `howCreated`              | enum       | 15 enum values (`DraggedToCanvas`, `Copilot`, `CopyPaste`, `QnaAppBar`, etc.) |

### 5.2 Visual config

| Property                  | Notes                                                                                          |
| ------------------------- | ---------------------------------------------------------------------------------------------- |
| `visualType`              | string — selects the rendering engine (tableEx, matrix, card, kpiVisual, waterfallChart, etc.) |
| `query`                   | `queryState` (per-role projections) + `sortDefinition` + `options` + `isDrillDisabled`         |
| `expansionStates[]`       | drill / expand-collapse state per role                                                         |
| `objects`                 | format-pane settings (the per-property values shown in the format pane)                        |
| `visualContainerObjects`  | container-frame formatting (title, background, border, padding, dropShadow)                    |
| `syncGroup`               | shared filter group across visuals                                                             |
| `drillFilterOtherVisuals` | bool                                                                                           |

### 5.3 Container formatting objects (the visual frame)

| Object key      | Properties                                                                                                                                                |
| --------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `title`         | show, text, heading, titleWrap, fontColor, background, alignment, fontSize, bold, italic, underline, fontFamily                                           |
| `subTitle`      | (same as title minus background)                                                                                                                          |
| `divider`       | show, ignorePadding, color, style, width                                                                                                                  |
| `spacing`       | customizeSpacing, verticalSpacing, spaceBelowTitle, spaceBelowSubTitle, spaceBelowTitleArea                                                               |
| `background`    | show, color, transparency                                                                                                                                 |
| `padding`       | top, bottom, left, right                                                                                                                                  |
| `border`        | show, color, radius                                                                                                                                       |
| `dropShadow`    | show, preset, position, color, transparency, shadowSpread, shadowBlur, angle, shadowDistance                                                              |
| `general`       | x, y, width, height, altText, allowBinnedLineSample, allowOverlappingPointsSample, keepLayerOrder                                                         |
| `visualHeader`  | show, background, border, transparency, foreground, plus many `show*Button` flags (filter, focus, drill, sort, more, copyData, smart-narrative, comments) |
| `stylePreset`   | name (named theme preset)                                                                                                                                 |
| `lockAspect`    | show                                                                                                                                                      |
| `visualLink`    | show, type, bookmark, drillthroughSection, qna, suppressDefaultTooltip                                                                                    |
| `visualTooltip` | show, type, section, fontColor, valueFontColor, fontSize, bold, italic, underline, fontFamily, background, transparency                                   |

### 5.4 Filter container types

10 filter types: `Categorical`, `Range`, `Advanced`, `Passthrough`, `TopN`, `Include`, `Exclude`, `RelativeDate`, `Tuple`, `RelativeTime`. Each can be hidden/locked in view mode.

### 5.5 ProjectionState

```jsonc
{
  "queryState": {
    "Values": {
      "projections": [
        {
          "queryRef": "f_opportunity.Total Closed Won ARR",
          "displayName": "Closed Won ARR",
          "format": "#,##0,,M",
          "active": true,
          "hidden": false
        }
      ],
      "showAll": false,
      "fieldParameters": []
    }
  },
  "sortDefinition": {
    "sort": [{ "field": <expr ref>, "direction": "Descending" }],
    "isDefaultSort": false
  }
}
```

The projections array is what the swap script writes when swapping Zebra columns to native. `format` per projection is one place to do per-cell formatting without TMDL changes.

## 6. The translation matrix — every Zebra primitive → native equivalent

Cross-referencing the Zebra atlas (§7, §11, §13) with the native primitives above:

| Zebra primitive                                                                               | Native PBI equivalent                                                                         | Lever                               | Fidelity              |
| --------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------- | ----------------------------------- | --------------------- |
| `chartSettings.types=Integrated` (integrated variance)                                        | tableEx with derived measure column + dataBars CF with field-driven max                       | DAX synthesis + CF                  | ~85%                  |
| `chartSettings.types=Absolute` (variance only)                                                | tableEx column on derived `[X] - [Y]` measure                                                 | DAX synthesis                       | 100%                  |
| `chartSettings.types=Relative` (% variance only)                                              | tableEx column on derived `DIVIDE([X]-[Y], ABS([Y]))`                                         | DAX synthesis (financial calc rule) | 100%                  |
| `chartSettings.types=Responsive` (auto-switch)                                                | (no native auto-mode — pick one shape)                                                        | n/a                                 | Lost                  |
| `chartSettings.absoluteChart=1/2` (waterfall variants)                                        | native `waterfallChart` with breakdown + subtotals                                            | direct visualType swap              | ~90%                  |
| `chartSettings.valueChart=1` (overlapped bar)                                                 | tableEx with two dataBars columns at slight offset                                            | composite                           | ~70%                  |
| `chartSettings.valueChart=3` (side-by-side waterfall)                                         | two `waterfallChart` visualContainers side-by-side                                            | composite                           | ~85%                  |
| `chartSettings.relativeChart=1` (sized dots)                                                  | scatterChart with size = abs(variance)                                                        | composite                           | ~60%                  |
| `chartSettings.relativeVarianceCalculation=0` (financial calc)                                | DAX `DIVIDE([X]-[Y], ABS([Y]))`                                                               | DAX                                 | 100%                  |
| `chartSettings.showGrandTotal`                                                                | tableEx `totals: true`                                                                        | object setting                      | 100%                  |
| `chartSettings.columnSettings.<key>.markerStyle=5` (bullet bar)                               | tableEx column dataBars CF, max=Plan field-driven                                             | CF                                  | ~85%                  |
| `chartSettings.columnSettings.<key>.invert=true` (cost flip)                                  | DAX `* -1` measure or flipped CF colors                                                       | DAX                                 | 100%                  |
| `chartSettings.columnSettings.<key>.format=0/1/2` (value/abs/%)                               | DAX `formatString` per measure                                                                | TMDL                                | 100%                  |
| `chartSettings.columnSettings.<key>.tableView.hidden`                                         | projection `hidden: true`                                                                     | PBIR ProjectionState                | 100%                  |
| `chartSettings.columnSettings.<key>.tableView.showAsTable=2` (text+chart hybrid)              | (no native — pick text or bar)                                                                | n/a                                 | Lost                  |
| `chartSettings.columnSettings.<key>.scaleGroup=1` (shared axis)                               | dataBars CF where `max` = same field across columns                                           | CF                                  | 100%                  |
| `chartSettings.columnSettings.<key>.scaleGroup=-1` (excluded)                                 | tableEx column without dataBars                                                               | absence                             | 100%                  |
| `chartSettings.columnSettings.<key>.hiddenFromGroups=["MTD","YTD"]`                           | (no native conditional column hide)                                                           | n/a                                 | Lost                  |
| `chartSettings.columnSettings.<key>.calculationFormula` (custom DAX)                          | TMDL measure with the same DAX text                                                           | DAX                                 | 100%                  |
| `chartSettings.columnSettings.<key>.isQuickCalculation=true`                                  | DAX measure for the corresponding quick calc (% of grand total / Running total / etc.)        | DAX                                 | 100%                  |
| `categorySettings.topNSettings`                                                               | tableEx visual-level filter Top N                                                             | Filter container                    | 100%                  |
| `categorySettings.rowHeight` enum                                                             | tableEx `values.fontSize` + `general.height`                                                  | objects                             | ~95%                  |
| `dataLabelSettings.units` (K/M/G/P)                                                           | DAX `FORMAT()` or formatString `"#,##0,,M"`                                                   | TMDL                                | 100%                  |
| `dataLabelSettings.negativeValuesFormat=1` (parens)                                           | formatString `"#,##0;(#,##0);\"-\""`                                                          | TMDL                                | 100%                  |
| `dataLabelSettings.useBasisPointsFormat`                                                      | DAX measure with `* 10000` + `" bps"` suffix                                                  | DAX                                 | 100%                  |
| `designSettings.style=2` (Dr. Hichert)                                                        | RW-IBCS theme JSON (`firstLevelElements`, `dataColors`, `visualStyles`)                       | Theme JSON                          | 100%                  |
| `designSettings.varianceDisplayType=1` (arrow)                                                | tableEx column with DAX `[Variance Icon]` returning `▲▼→` Unicode + Font color CF Field value | CF + DAX                            | 95%                   |
| `designSettings.previousYearColor` etc.                                                       | theme `dataColors[]` indexed by series order                                                  | Theme JSON                          | 100%                  |
| `designSettings.applyPatterns` (hatch/dotted fills)                                           | (no native pattern fill)                                                                      | n/a                                 | **Lost**              |
| `commentBoxSettings` (annotation system)                                                      | composite of textbox visualContainers positioned next to data cells                           | composite                           | ~70%                  |
| `commentBoxSettings.varianceIcon=2` (Triangle)                                                | DAX returning `◢` Unicode + CF font color                                                     | CF + DAX                            | 100%                  |
| `interactionSettings.allowChartChange`                                                        | bookmark + button affordance (or accept loss)                                                 | composite                           | ~50%                  |
| `interactionSettings.allowExpandCollapseChange`                                               | matrix native drill-up/drill-down (built-in)                                                  | matrix                              | 100%                  |
| `interactionSettings.enableMeasureDrillThrough`                                               | drillthrough page (native PBI feature)                                                        | drillthroughSection                 | 100%                  |
| `interactionSettings.allowExcelExport`                                                        | visualHeader.showExportData button                                                            | visualHeader                        | 100%                  |
| `proFeaturesSettings` (CAGR arrow, axis-break, etc.)                                          | (no native CAGR / axis-break)                                                                 | n/a                                 | **Lost**              |
| `averageLineSettings`, `medianLineSettings`, `percentileLineSettings`, `constantLineSettings` | native analytics lines (Mean / Median / Min / Max / Constant)                                 | analytics object                    | ~80%                  |
| `sortSettings.chartSort` / `categorySort`                                                     | tableEx `sortDefinition`                                                                      | query                               | 100%                  |
| Tables data role: `Group` (small-multiples)                                                   | matrix with Group on Columns                                                                  | matrix                              | 100%                  |
| Tables data role: `Tooltips`                                                                  | tableEx visual tooltip with extra fields                                                      | visualTooltip                       | 100%                  |
| Tables data role: `CategoryClass` (subtotal classification)                                   | matrix subtotals/grand totals                                                                 | object                              | 80%                   |
| Cards data role: `KPI Descriptions`                                                           | textbox visualContainer                                                                       | composite                           | 100%                  |
| Tables matrix shape (cardinality: Values 21, Plan 3, Forecast 3)                              | (no native cardinality enforcement)                                                           | n/a                                 | enforcement-only loss |

**Net rebuild fidelity for an average Zebra Tables visual:** ~85-90%. Irreducible loss is concentrated in: pattern fills (`designSettings.applyPatterns`), runtime-customization toggles (`interactionSettings`), CAGR arrow, axis-break for outliers, conditional column hide (`hiddenFromGroups`).

## 7. The mechanical PR9 rebuild pipeline

With both atlases in hand, PR9's translator becomes deterministic:

```
For each Zebra PBIX:

  1. Run rw_zebra_kg_infra_miner on the source → get every visualContainer's
     full singleVisual.objects + projections

  2. Upload PBIX via Fabric REST /imports → creates dataset + report

  3. For each Zebra visualContainer:
       a. Read chartSettings.columnSettings → enumerate all derived comparison keys
       b. For each <x>-<y> and <x>-<y>-percent key, build TMDL measure text:
            measure '<X> vs <Y>' = [<X>] - [<Y>]      formatString: "#,##0"
            measure '<X> vs <Y> %' = DIVIDE([<X>]-[<Y>], ABS([<Y>]))   formatString: "0.0%"
       c. For each isCustomColumn=true: copy calculationFormula DAX text verbatim
       d. For each isQuickCalculation=true: synthesize DAX for the matching preset
            (% of grand total / % of / Running total / Running total %)

  4. Patch deployed dataset's TMDL: insert all new measures into the appropriate
     table's TMDL part, push via /semanticModels/{id}/updateDefinition

  5. Build native report.json visualContainers:
       - ZebraBITables → tableEx (or matrix when Group projected)
         · projections in IBCS column order: Category(s), AC, AC vs PY,
           AC vs PY %, PY, AC vs PL, AC vs PL %, PL, FC
         · dataBars CF on AC column, max = field-driven from Plan or PY (per
           scaleGroup=1 measures)
         · Variance arrow column = DAX [Variance Icon] returning ▲▼→
         · Font color CF Field value = DAX [Variance Color]
         · displayUnits, decimalPlaces from dataLabelSettings
         · Top N filter from categorySettings.topNSettings
       - ZebraBICards → composite: textbox header + card + variance-arrow
         textbox + sparkline (native sparkline as of 2023)
       - ZebraWaterfall → native waterfallChart with breakdown=Group,
         subtotals enabled, color-overrides from designSettings positiveColor/
         negativeColor

  6. Apply RW-IBCS theme JSON (theme set once at report level):
       - dataColors palette per scenario
       - text classes mapping Segoe UI 9/10/12 ramp
       - visualStyles overrides per visualType for IBCS conventions

  7. Push report definition via /reports/{id}/updateDefinition

  8. Smoke-check render in PBI Service
```

Every step has a known native primitive. No more guessing.

## 8. Related artifacts

- Zebra atlas (the source spec): `docs/sales/RW_ZEBRA_BI_INFRASTRUCTURE_ATLAS.md`
- Zebra raw configs (mined): `data/zebra_kg/infrastructure/raw_configs.jsonl`
- Zebra API atlas (canonical): `data/zebra_kg/infrastructure/zebra_api_atlas.json`
- DAX pattern atlas: `data/zebra_kg/dax_patterns.json` (PR4)
- Topology atlas: `data/zebra_kg/topology_patterns.json` (PR4)
- Per-template schemas: `data/zebra_kg/schemas/<slug>/` (PR5)
- Path-B proof (TMDL push works): commit `bff5b7c` test of `AC vs PL` measure synthesis into deployed dataset
