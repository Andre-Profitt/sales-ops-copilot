# LAND deck wiring — quick-reference card

One-page companion to `docs/THINKCELL_SETUP.md`. Open this alongside PowerPoint for the click-by-click pass on Jesper. Total budget: ~30 minutes.

## Files (all 3 open in PowerPoint/Excel)

- `assets/LAND_template.pptx` — the SimCorp-branded 28-slide template
- `state/2026-Q2/Jesper-Tyrer/land.model.xlsx` — formula-driven model
- `state/2026-Q2/Jesper-Tyrer/land.xlsx` — legacy companion (named-account lists)

## Step 0 — embed brand style (once, ~30 sec)

In the open `LAND_template.pptx`:

1. Insert → think-cell → Tools → Change Style → Other...
2. Browse to `~/code/apps/sales-ops-copilot/assets/SimCorp-thinkcell-style.xml`
3. **File → Save As** → `state/2026-Q2/Jesper-Tyrer/Jesper-Tyrer-LAND-2026-Q2.pptx`

From here on, every think-cell chart you insert inherits SimCorp's brand palette via the deck's theme accents.

## Step 1 — Cover (slide 1, ~30 sec, no think-cell)

Replace placeholders:

- `{director_name}` → `Jesper Tyrer`
- `{period}` → `2026-Q2`
- `{scope_label}` → `APAC`

## Slide-by-slide click sequence (slides 2–25)

For each slide with a placeholder rectangle:

1. **Delete the placeholder rectangle** (so the slide is empty)
2. **In Excel** (model OR legacy as the table says): select the range — include header labels
3. **Excel → Insert → think-cell group → Link to PowerPoint** dropdown → pick the chart type
4. PowerPoint activates; click on the empty slide to place the chart
5. For single-cell text bindings (slide 2 + slide 23): cursor in PPT text frame → **Insert → think-cell → Elements → Text Linked to Excel**

Order doesn't matter — pick whichever is easiest first. Recommended: slides 2 → 4 → 5 → 12 → 13 → 23 (the formula-driven ones from the model) before slides 7/8/9/11/26 (legacy tables).

## Slide-to-binding cheat sheet

| Slide                         | Source     | Range                                                 | Chart type                              |
| ----------------------------- | ---------- | ----------------------------------------------------- | --------------------------------------- |
| 2 Exec summary                | n/a        | manual paste from `brief.md` ## Highlights / ## Risks | text                                    |
| 3,10,14,20 Dividers           | n/a        | text only — skip wiring                               | divider                                 |
| 4 Pipe-movement bridge        | model      | Pipe_Movement!A2:B6                                   | **Waterfall**                           |
| 5 Pipeline by stage           | model      | Pipeline_By_Stage!A2:B9                               | Bar                                     |
| 6 Pipeline aging              | model      | Pipeline_Aging!A2:E7                                  | Stacked bar                             |
| 7 Top deals — Land            | **legacy** | Top_Deals_Land!A1:H11                                 | Table                                   |
| 8 Top deals — Expand          | **legacy** | Top_Deals_Expand!A1:H11                               | Table                                   |
| 9 Pending Commercial Approval | **legacy** | Pending_Commercial_Approval!A3:H...                   | Table                                   |
| 11 Renewal Pipeline           | **legacy** | At_Risk_Renewals!A1:H...                              | Table + Harvey balls                    |
| 12 GRR proxy                  | model      | Retention!A1:B4 + A5 footnote                         | Table                                   |
| 13 Forecast Category          | model      | Forecast_Category!A1:C7                               | Column or table                         |
| 15 By owner                   | model      | By_Owner!A2:B...                                      | Horizontal bar                          |
| 16 Stage × Industry           | model      | Pivots Stage × Industry block                         | **Mekko** (variable-width 100%-stacked) |
| 17 Per-territory              | model      | Territory_Performance!A1:D...                         | Bar (X=col B, Y=col D)                  |
| 18 QTD wins+losses            | model      | Wins_Losses_QTD!A1:D3                                 | Grouped column or table                 |
| 19 Velocity                   | model      | Velocity!A3:E10                                       | Combo bar+line                          |
| 21 Concentration risk         | model      | Concentration!B5:B8 + A12:C15                         | Text + 100%-stacked                     |
| 22 Stage 3+ stale activity    | model      | Stale_Activity!A1:C5 + A7 footnote                    | Bar                                     |
| 23 Sales velocity             | model      | Sales_Velocity!B2/B3/B4/B5/B6 + col C notes           | Single-cell text bindings               |
| 24 Account expansion          | model      | Account_Expansion!A1:F16                              | Table                                   |
| 25 Pipeline creation velocity | model      | Pipeline_Creation_Velocity!A1:C13                     | Combo bar+line                          |
| 26 Action items               | **legacy** | Action_Items!A1:G... (4 rows for Jesper)              | Table                                   |
| 27 Risks & outlook            | n/a        | manual paste from `brief.md` ## Risks                 | text                                    |
| 28 Closing                    | n/a        | static disclaimer — no binding                        | text                                    |

**The 5 legacy-source slides (7/8/9/11/26) bind to `land.xlsx`. Slide 13 and the other model-driven analytical slides bind to `land.model.xlsx`.**

## Visual QA — known high-risk slides

After wiring, eyeball these specifically:

- **Slide 12 (GRR proxy):** confirm cell A5 PROXY caveat is bound as italic-gray footnote
- **Slide 17 (Territory mix):** check col D ARR values resolve to real numbers (not formula text)
- **Slide 18 (Wins/Losses):** column D is renewal ACV, NOT cycle days
- **Slide 23 (Sales Velocity):** B6 (velocity number) sits center-large; check the 5 KPI tiles are in formula order (not the old B3/B4 swap)
- **Slide 24 (Account Expansion):** 6 columns including # Motions; rows where col F = 3 highlighted

## Save + fan-out (after Jesper is wired)

1. **File → Save** the wired Jesper deck
2. For each of the other 8 directors:
   a. **File → Save As** → `state/2026-Q2/<Director>/<Director>-LAND-2026-Q2.pptx`
   b. Open `state/2026-Q2/<Director>/land.model.xlsx` AND `land.xlsx` in Excel
   c. **Insert → think-cell → Tools → Data Links** dialog
   d. Click the workbook node for `Jesper-Tyrer/land.model.xlsx` in the right panel
   e. **Data Source dropdown → "Switch to alternate data sources"** → pick `<Director>/land.model.xlsx`
   f. Repeat for `Jesper-Tyrer/land.xlsx` → `<Director>/land.xlsx`
   g. Toolbar → **Update once** → all 22 datalinks reflow
   h. Save

~60-90 sec per director. Total fan-out: ~10 min.

## Refresh next month (no wiring needed)

1. Run `python3 scripts/land_brief.py --all-directors --period 2026-Q3` (replace the period)
2. For each director: open the per-director `.pptx`, open the per-director `land.model.xlsx` + `land.xlsx`
3. **Insert → think-cell → Tools → Data Links → Update all**
4. Save

~2 min per director × 9 = ~20 min total monthly refresh.

## If something breaks

- **Datalink shows `#REF!`** — sheet/range moved. Run `python3 scripts/validate_workbook_contract.py state/2026-Q2/<Director>` to confirm the workbook contract holds. If it does, re-point the datalink in the Data Links dialog.
- **think-cell ribbon greyed out** — Office is in Rosetta. Quit, right-click PPT in Applications → Get Info → uncheck "Open using Rosetta," reopen.
- **"Datalink: not found"** — both files (xlsx + pptx) must be open in their parent apps simultaneously for refresh to work.
