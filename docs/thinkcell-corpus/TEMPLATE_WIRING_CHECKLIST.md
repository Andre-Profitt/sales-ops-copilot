# TEMPLATE_WIRING_CHECKLIST — Andre's interactive task

**The single gating step for the LAND deck factory.** Until this is done, the pipeline produces empty decks regardless of how clean the data layer is. ~2-4 hours of work, all in PowerPoint on the VM. Cannot be automated (mini-toolbar interaction is required).

---

## What we're doing

For each named binding the .ppttc emits, the template needs a matching named **think-cell text field** or **think-cell chart anchor**. The name lives on the element, set via the mini-toolbar's `AddRangeData Name` field. Without these names, ppttc.exe cannot route binding values into the rendered deck — the data falls on the floor.

Two element types per binding:

| Binding pattern                      | Element type to add                                                              | Slide content                                                |
| ------------------------------------ | -------------------------------------------------------------------------------- | ------------------------------------------------------------ |
| Single-cell text (`{string: "..."}`) | think-cell **text field**                                                        | Director name, period, scope label, footnotes, scalar values |
| Multi-row table                      | think-cell **chart** (Bar / Mekko / Line / Scatter / Table) or **table element** | Charts and data tables                                       |

---

## How to set the name (PowerPoint mini-toolbar)

1. Open `assets/LAND_template.pptx` (or `_windows_test/LAND_template.pptx` if you're working on the windows-test copy) in PowerPoint **with think-cell ribbon active**.
2. Click on a chart / text field / table element you want to bind.
3. The think-cell mini-toolbar pops up next to the element.
4. Click the dropdown that says `[Name]` (sometimes labeled "Name" or "Range name").
5. Type the binding name **exactly** as listed below (case-insensitive, but match the listed casing for consistency).
6. Hit Enter. The name is now stored in the element's metadata.
7. Save the .pptx (Ctrl+S, keep `.pptx` format).

Reference: `state/thinkcell_bridge/official_docs_corpus/<latest-ts>/extraction.json` answer **E_element_naming**.

---

## Bindings to wire (32 total)

### Cover slide bindings (3) — text fields

| Binding            | Element type | Slide                                          | Notes                                  |
| ------------------ | ------------ | ---------------------------------------------- | -------------------------------------- |
| `S01_DirectorName` | text field   | Cover (slide 1)                                | Replaces `{director_name}` placeholder |
| `S01_Period`       | text field   | Cover (slide 1, header on slides 2/5/12/23/26) | Replaces `{period}`                    |
| `S01_ScopeLabel`   | text field   | Cover (slide 1)                                | Replaces `{scope_label}`               |

### Exec summary slide (2) — text fields

| Binding                | Element type | Slide        | Notes                             |
| ---------------------- | ------------ | ------------ | --------------------------------- |
| `S02_ExecSummaryLeft`  | text field   | Exec summary | Multiline bullets in LEFT column  |
| `S02_ExecSummaryRight` | text field   | Exec summary | Multiline bullets in RIGHT column |

### Pipeline movement / aging / by-stage (3) — charts

| Binding               | Element type                                      | Slide             |
| --------------------- | ------------------------------------------------- | ----------------- |
| `S04_PipeMovement`    | think-cell **waterfall chart**                    | Pipeline movement |
| `S05_PipelineByStage` | think-cell **bar chart** (categories=stages)      | Pipeline by stage |
| `S06_PipelineAging`   | think-cell **bar chart** (categories=age buckets) | Pipeline aging    |

### Top deals + pending approval (3) — tables

| Binding                         | Element type         | Slide                       |
| ------------------------------- | -------------------- | --------------------------- |
| `S07_TopDealsLand`              | think-cell **table** | Top Land deals              |
| `S08_TopDealsExpand`            | think-cell **table** | Top Expand deals            |
| `S09_PendingCommercialApproval` | think-cell **table** | Pending commercial approval |

### Renewals / GRR (3)

| Binding                | Element type                              | Slide                          |
| ---------------------- | ----------------------------------------- | ------------------------------ |
| `S11_RenewalPipeline`  | think-cell **table**                      | Renewals                       |
| `S12_GRRProxyTable`    | think-cell **table** (2-col Metric/Value) | GRR proxy                      |
| `S12_GRRProxyFootnote` | text field                                | GRR proxy (footnote at bottom) |

### Forecast + by-owner + by-industry (3)

| Binding                | Element type                                              | Slide               |
| ---------------------- | --------------------------------------------------------- | ------------------- |
| `S13_ForecastCategory` | think-cell **bar chart**                                  | Forecast categories |
| `S15_ByOwner`          | think-cell **bar chart** (categories=owners)              | Pipeline by owner   |
| `S16_StageByIndustry`  | think-cell **Mekko chart** (cols=industries, rows=stages) | Stage × Industry    |

### Territory + wins/losses + velocity (3)

| Binding                    | Element type                                               | Slide                 |
| -------------------------- | ---------------------------------------------------------- | --------------------- |
| `S17_TerritoryPerformance` | think-cell **bar chart** (categories=countries)            | Territory performance |
| `S18_WinsLossesQTD`        | think-cell **bar chart** (Won vs Lost split by ARR vs ACV) | Wins/Losses QTD       |
| `S19_Velocity`             | think-cell **bar chart** (categories=stages)               | Velocity by stage     |

### Concentration risk (5)

| Binding                      | Element type                                         | Slide                            |
| ---------------------------- | ---------------------------------------------------- | -------------------------------- |
| `S21_ConcentrationRiskChart` | think-cell **bar chart** (categories=top N accounts) | Concentration risk               |
| `S21_ConcentrationTable`     | think-cell **table**                                 | Concentration risk               |
| `S21_LargestAccount`         | text field                                           | Concentration risk (callout)     |
| `S21_LargestArr`             | text field                                           | Concentration risk (callout)     |
| `S21_LargestShare`           | text field                                           | Concentration risk (callout)     |
| `S21_ThresholdFlag`          | text field                                           | Concentration risk (yes/no flag) |

### Stale activity + cycle metrics (8)

| Binding                     | Element type             | Slide                                   |
| --------------------------- | ------------------------ | --------------------------------------- |
| `S22_StaleActivity`         | think-cell **bar chart** | Stale activity                          |
| `S22_StaleActivityFootnote` | text field               | Stale activity (footnote)               |
| `S23_AvgCycleDaysValue`     | text field               | Sales velocity scorecard                |
| `S23_AvgCycleDaysNote`      | text field               | Sales velocity scorecard (formula note) |
| `S23_AvgDealSizeValue`      | text field               | Sales velocity scorecard                |
| `S23_AvgDealSizeNote`       | text field               | Sales velocity scorecard (formula note) |
| `S23_OpenOppsValue`         | text field               | Sales velocity scorecard                |
| `S23_OpenOppsNote`          | text field               | Sales velocity scorecard (formula note) |
| `S23_VelocityValue`         | text field               | Sales velocity scorecard                |
| `S23_VelocityNote`          | text field               | Sales velocity scorecard (formula note) |
| `S23_WinRateValue`          | text field               | Sales velocity scorecard                |
| `S23_WinRateNote`           | text field               | Sales velocity scorecard (formula note) |

### Account expansion + pipeline-creation + actions / risks (4)

| Binding                        | Element type                              | Slide                               |
| ------------------------------ | ----------------------------------------- | ----------------------------------- |
| `S24_AccountExpansion`         | think-cell **table**                      | Account expansion                   |
| `S25_PipelineCreationVelocity` | think-cell **line chart** (x=week-ending) | Pipeline creation                   |
| `S26_ActionItems`              | think-cell **table**                      | Action items                        |
| `S27_RisksOutlook`             | text field                                | Risks / outlook (multiline bullets) |

---

## Suggested order

Do the **highest-leverage 5 bindings first** to validate the wiring approach before doing all 32:

1. `S01_DirectorName` — proves named-text-field binding works
2. `S01_Period`
3. `S01_ScopeLabel`
4. `S02_ExecSummaryLeft`
5. `S05_PipelineByStage` — proves named-chart-anchor binding works

After those 5 are wired, save the template and run:

```bash
cd ~/code/apps/sales-ops-copilot
TS=$(date +%Y%m%d-%H%M%S)
TCRENDER_LIVE=1 .venv/bin/python scripts/build_ppttc_demo.py \
    --ppttc state/2026-Q2/Jesper-Tyrer/Jesper-Tyrer-LAND-2026-Q2.ppttc \
    --template-override _windows_test/LAND_template.pptx \
    --out _windows_test/Jesper-Tyrer-LAND-2026-Q2-WIRED-$TS.pptx
```

Verify the rendered output contains "Jesper Tyrer" on slide 1:

```bash
unzip -p _windows_test/Jesper-Tyrer-LAND-2026-Q2-WIRED-*.pptx ppt/slides/slide1.xml | grep -c "Jesper Tyrer"
```

Should return >= 1. If yes, the wiring approach is proven — proceed with the remaining 27 bindings. If no, debug before going wider.

---

## Common mistakes

- **Naming the slide / shape, not the think-cell element.** PowerPoint has its own shape names; that's NOT the same as think-cell's `AddRangeData Name`. The mini-toolbar field is a separate metadata slot on the think-cell-aware element.
- **Setting the name on the wrong shape.** Confirm the mini-toolbar shows "think-cell" branding before typing — it should appear directly on the chart/text field anchor, not on a generic PowerPoint shape.
- **Forgetting to save.** Mini-toolbar changes are NOT auto-persisted. Ctrl+S after each binding.
- **Mismatched casing.** The docs say case-insensitive but copy the names exactly to avoid confusion.

---

## Once done

1. Save the wired template back to `assets/LAND_template.pptx` (or commit a copy at `assets/LAND_template_wired.pptx` so the unwired version stays available for diffs).
2. Update `SHIP_PLAN.md` "Current readiness" → flip the **Template <-> binding wiring** row to ✅.
3. Re-run all 9 directors:
   ```bash
   for D in Jesper-Tyrer Sarah-Pittroff Patrick-Gaughan Megan-Miceli; do
       .venv/bin/python scripts/build_ppttc.py --director $D --period 2026-Q2 \
           --template assets/LAND_template_wired.pptx
       TCRENDER_LIVE=1 .venv/bin/python scripts/build_ppttc_demo.py \
           --ppttc state/2026-Q2/$D/$D-LAND-2026-Q2.ppttc \
           --template-override assets/LAND_template_wired.pptx \
           --out _windows_test/$D-LAND-2026-Q2-WIRED-$(date +%Y%m%d-%H%M%S).pptx
   done
   ```
4. Open one of the outputs and confirm:
   - Cover slide shows the right director's name + period + scope
   - Charts have actual bars / mekko cells / table rows (not placeholder grids)
   - Footnote text fields are populated with the right caveat strings
