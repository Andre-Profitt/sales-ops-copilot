# think-cell Template Selection - May 2026 Sales Director Decks

Date: 2026-05-01

## Decision

Use the installed think-cell templates as design and donor references, not as a direct production template replacement. The catalog scan found 62 installed `.potx` files and rendered the 20 plausible Sales Director candidates into a contact sheet.

Artifacts:

- Inventory: `state/thinkcell_bridge/template_catalog/thinkcell_template_catalog.md`
- Machine-readable inventory: `state/thinkcell_bridge/template_catalog/thinkcell_template_catalog.json`
- Visual contact sheet: `state/thinkcell_bridge/template_catalog/thinkcell_template_contact_sheet.png`
- Machine-readable selection map: `config/thinkcell_template_selection.may_2026.json`

Important constraint: none of the installed `.potx` files contains named `m_strName` automation payloads. They include think-cell objects and useful formatting, but they are not drop-in `.ppttc` templates. A production `.ppttc` lane still needs named objects saved by PowerPoint with think-cell installed.

## What We Should Use

| Template family | Use in the Sales Director deck | Target slides / objects |
|---|---|---|
| Bar, Column | Default analytical chart family for stage, forecast, owner, country, stale activity, and creation volume. Use horizontal bars for ranked lists and columns for period/series comparisons. | S05, S06, S08, S10, S13, S15, S17, S19, S22, S25 |
| Waterfall | Movement bridges only: opening plus new, won, lost, slipped, pulled-in, closing. Closed-lost must always be negative. | S04/S05 movement, S18 QTD won/lost |
| Line, Area | Trend slides where the x-axis is time. Do not use for single snapshots. | S19 if velocity becomes a trend, S25 pipeline creation velocity |
| Scatter, Bubble | Deal inspection and outlier detection: ARR versus probability, age, activity recency, or risk score. This is a good upgrade for the current risk slides because it shows where to inspect, not just totals. | S09 deal risk, S21 concentration, S22 stale activity |
| Timeline, Gantt | Dated close-plan milestones, approval due dates, and renewal decision dates. Use only when rows have real distinct dates. | S12 approvals, S13 renewals; S26 only when action dates are real milestones |
| Mekko | Only for a true two-dimensional mix question, such as stage by industry where both width and stack composition matter. Otherwise use stacked columns. | S16 only |
| Useful Elements / Tables | Visual styling reference for dense named-deal tables. Do not rely on this as the live table lane until we have a clean manually named table donor. | S04, S06, S07, S08, S09, S11, S12, S13, S14, S15, S24, S26, S27 |
| Dashboards, Statistics | KPI-strip inspiration for the executive summary and formula explanation. Use the restraint, not the whole dashboard slide. | S02, S23 |
| Annotations / Callouts | Precise chart overlays: one or two labeled reasons, deltas, CAGR/difference arrows where mathematically valid. | S04, S05, S13, S18, S21, S25 |

## What We Should Avoid

- Pie and doughnut charts except for simple 2-3 category shares with direct labels.
- Funnels for the SimCorp sales process. The 8-stage process is not a generic conversion funnel and should stay stage-explicit.
- Gauges, thermometers, and traffic lights for headline financial metrics. They look dashboard-like and hide the ARR/ACV basis.
- Venn, cubes, pyramids, decorative symbols, hand-drawn elements, quotes, and generic process art.
- Maps unless geography is the decision variable. For a director with a single-region territory, a ranked bar is usually clearer.
- Full dashboard/statistics pages copied as-is. They read as templateware if not sharply constrained.

## Implication For The Factory

Keep the current table-image lane for dense tables until we have one manually named, stable think-cell table donor. It is the only table lane that has been proven repeatable across all regions without relying on undocumented table creation.

Upgrade the chart donor catalog in stages:

1. Keep Bar/Column and Waterfall as core production chart lanes.
2. Add Timeline/Gantt only for real dated milestone data: approval dates, renewal decision dates, and named close-plan dates.
3. Add Scatter/Bubble for deal-risk inspection.
4. Add Line/Area only where the workbook exposes real time-series data.
5. Keep Mekko as a rare S16 mix chart, not a default.

## Slide-Level Recommendations

| Slide | Recommended visual lane | Rationale |
|---|---|---|
| S02 Highlights | Native KPI strip styled from Dashboard/Statistics, with exact weighted/unweighted labels | High-trust executive orientation; avoid a busy dashboard clone. |
| S04/S05 Movement | Waterfall | Best fit for "what changed" as long as signs are audited. |
| S05 Pipeline by stage | Bar/Column | Stage-explicit and easier to read than a funnel. |
| S06 Aging | Bar/Column histogram or ranked bar | Shows where inspection is overdue. |
| S07-S09 Named deal tables | Current linked table-image lane, styled like Useful Elements / Tables | Dense, audit-facing, and best kept traceable to Excel. |
| S11/S13 Renewals | Table plus conditional Timeline/Gantt | Renewal ACV stays separate; use Gantt only when the date spread is meaningful. |
| S15 Owner coaching | Bar/Column plus table | Owner totals need ranking; actions need row-level support. |
| S16 Stage x industry | Mekko only if the data matrix is meaningful | If sparse, use stacked column or table. |
| S17 Territory mix | Ranked bar, map only when geography is the decision story | Avoid decorative maps. |
| S18 QTD wins/losses | Waterfall or grouped column | Lost values must subtract, not add. |
| S21/S22 Risk | Scatter/Bubble plus table | Gives a real inspection map: value, risk, age, recency. |
| S25 Pipeline creation | Line/Area or columns | Use line only for true multi-week trend. |
| S26 Action contract | Decision/action register table; Timeline/Gantt only if dates differ materially | Generic month-end due dates should not become a Gantt. |

## Next Build Change

The next safe engineering step is not a full deck rebuild. It is a one-slide or two-slide pilot:

1. Add a Timeline/Gantt donor object only for approval or renewal milestone data where the date distribution is real.
2. Add a Scatter/Bubble donor object for deal-risk inspection from named Excel ranges.
3. Run the publish gate and visual screenshot gate on one director.
4. If the objects remain stable, generalize across all regions.
