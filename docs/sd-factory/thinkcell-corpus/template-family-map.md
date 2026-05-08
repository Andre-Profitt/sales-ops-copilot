# think-cell Template Family Map

Date: 2026-05-01

This file interprets the stock think-cell pre-populated templates through a
SimCorp lens. The stock template names are from
`/Library/Application Support/Microsoft/think-cell/templates`.

## Highest-Fit Families

### Bar, Column

Stock template:
`think-cell Charts/Bar, Column/Bar, Column.potx`

Evidence: 9 slides, 14 chart references, 25 OLE parts, 301 tag files. Slide
archetypes include stacked column, 100% stacked column, clustered column,
combination, bar, stacked bar, and butterfly/tornado.

SimCorp use:

- Open ARR by sales stage.
- Forecast category mix.
- Owner ranking.
- Country or territory ranking.
- Stale activity volume.
- Pipeline creation by week or month.
- QTD won/lost grouped comparison when a bridge is not valid.

Eligibility gate:

- Categories should be sorted or follow a meaningful business order.
- Avoid more than 8-10 categories unless the slide is explicitly a ranked
  appendix.
- Label ARR versus ACV directly in the subtitle or axis.

Avoid:

- Using stacked bars to hide exact Land, Expand, and Renewal separation.
- Using a bar chart where named deal inspection is the actual question.

### Waterfall

Stock template:
`think-cell Charts/Waterfall/Waterfall.potx`

Evidence: 3 slides, 3 chart references, 8 OLE parts, 124 tag files. Slide
archetypes include build-down, build-up, and a pipeline/funnel-like waterfall.

SimCorp use:

- Opening pipe plus new, won, lost, slipped, pulled-in, and closing.
- Q1 promised versus delivered movement.
- QTD wins and losses when signs are auditable.
- Forecast bridge from prior review to current review.

Eligibility gate:

- Must have a real start value, movement components, and end value.
- Closed-lost must subtract from the bridge.
- The bridge basis must say unweighted ARR, weighted ARR, or ACV.

Avoid:

- Independent snapshots masquerading as movement.
- Renewal ACV and ARR in the same bridge.

### Line, Area

Stock template:
`think-cell Charts/Line, Area/Line, Area.potx`

Evidence: 8 slides, 11 chart references, 21 OLE parts, 319 tag files. Slide
archetypes include line, combination, area, 100% area, football field,
box-and-whisker, and candlestick.

SimCorp use:

- Multi-week pipeline creation trend.
- Activity or opportunity creation trend.
- Close-date movement trend.
- Sales velocity trend when every period is comparable.

Eligibility gate:

- X-axis must be real time.
- At least three points are needed for a trend claim.
- Forecast and actual should be visually distinct.

Avoid:

- Single-period snapshots.
- Trends where a few backfilled records create false movement.

### Scatter, Bubble

Stock template:
`think-cell Charts/Scatter, Bubble/Scatter, Bubble.potx`

Evidence: 2 slides, 2 chart references, 6 OLE parts, 67 tag files. Slide
archetypes include scatter and bubble.

2026-Q2 proof: QTR04 is L5-proven by patching the stock scatter donor's empty
`m_strName`, binding Q2 Salesforce readiness rows, asserting bound package
terms, and rendering the output.

SimCorp use:

- Named deal inspection by ARR and probability.
- ARR versus age or days since activity.
- Risk score versus close date proximity.
- Concentration outlier map.

Eligibility gate:

- Each point must be a named deal or account.
- Both x and y axes must have at least two distinct meaningful values.
- Bubble size must add decision value; otherwise use scatter.

Avoid:

- Anonymous aggregated points.
- Decorative quadrant charts without an action rule.

### Timeline, Gantt

Stock template:
`think-cell Charts/Timeline, Gantt/Timeline, Gantt.potx`

Evidence: 3 slides, 0 chart XML refs, 5 OLE parts, 225 tag files. Slide
archetypes include Gantt I, Gantt II, and Gantt III.

2026-Q2 proof: QTR05 and QTR06 are L5-proven by patching the stock Gantt
donor's empty `m_strName` values, binding Renewal ACV timeline rows, asserting
the surviving Gantt package terms, and rendering the output.

SimCorp use:

- Close-plan milestones with real deal-specific dates.
- Approval due dates for Stage 3+ Land deals.
- Renewal decision windows.
- Implementation or enablement roadmap only when leadership is deciding timing.

Eligibility gate:

- Rows need materially different dates.
- Date source must be explicit.
- Generic month-end action lists should stay as a decision register table.

Avoid:

- Turning every action item into a Gantt.
- Using timeline art for undated process explanation.

### Tables

Stock templates:

- `Tables/Tables.potx`
- `Useful Elements/Tables/Tables.potx`

Evidence: `Tables/Tables.potx` has 5 slides and 3 OLE parts. `Useful
Elements/Tables/Tables.potx` has 3 slides and 5 OLE parts. The useful-elements
version includes box table, automatic table, and think-cell table examples.

SimCorp use:

- Named deal readiness.
- Commercial approval exceptions.
- Renewal ACV watchlist.
- Owner coaching actions.
- Decision register.
- Data-quality or hygiene issue log.

Eligibility gate:

- Header must state ARR or ACV basis where relevant.
- Row height and type size must survive director-meeting projection.
- Every row should support a decision, exception, or follow-up.

Automation posture:

- Native think-cell table naming remains blocked.
- Use native PowerPoint tables or table-image donors until a real named
  data-backed think-cell table donor exists.

Avoid:

- Tables as a dumping ground for weak narrative.
- Tables that blend Type universes or omit metric basis.

### Dashboards, Statistics

Stock template:
`Dashboards, Statistics/Dashboards, Statistics.potx`

Evidence: 5 slides, 8 chart references, 13 OLE parts, 67 tag files. Slide
archetypes include dashboard, traffic-light dashboard, management summary, and
stats dashboard.

SimCorp use:

- KPI strip inspiration for executive summary.
- Small set of headline operating metrics with clear basis.
- Operating-rhythm summary when paired with named evidence.

Eligibility gate:

- Use as a restrained strip, not a full cloned dashboard.
- Each tile needs a metric basis: unweighted ARR, weighted ARR, ACV, count,
  days, or rate.

Avoid:

- Traffic-light dashboards for headline financials.
- More than 4-5 KPI tiles on a leadership summary.

### Annotations

Stock template:
`think-cell Charts/Annotations/Annotations.potx`

Evidence: 7 slides, 7 chart references, 16 OLE parts, 192 tag files. Slide
archetypes include CAGR arrow, multiple CAGR arrows, total difference arrow,
level difference arrow, and value line.

SimCorp use:

- Label one or two drivers in a movement bridge.
- Mark forecast gap versus target.
- Call out stale threshold, approval gate, or concentration threshold.

Eligibility gate:

- Annotation must be mathematically valid and source-backed.
- No more than two annotations on a director-facing analytical slide.

Avoid:

- Narrative labels that simply repeat the title.
- CAGR arrows on short or irregular time periods.

## Conditional-Fit Families

### Mekko

Stock template:
`think-cell Charts/Mekko/Mekko.potx`

Use only for a true two-dimensional mix question, such as stage by industry,
where segment width and stack composition both matter. If the matrix is sparse
or the audience needs exact values, use a stacked column or table.

2026-Q2 proof: QTR07 is L5-proven as a native chart automation lane by
renaming the LAND seed `S16_StageByIndustry` surface and binding it through
`.ppttc`.

### Agendas, Schedules, Timetables

Useful for meeting-spine agenda and operating cadence pages. Keep it quiet and
functional. Avoid using it as generic page furniture inside analytical sections.

### Timelines, Milestones, Project Planning

Useful for roadmap, historical timeline, sprint planning, or leadership cadence
only when the story is genuinely chronological. For deal execution, prefer the
think-cell Gantt family when rows are tied to dates.

### Matrices, SWOT Analyses

Useful for portfolio triage, risk heat map, account segmentation, or operating
model choices. Use when two axes create a decision. Avoid generic SWOT in
Commercial pipeline reporting unless leadership explicitly needs a strategy
frame.

### Processes, Flow Charts, Phases

Useful for governance, handoff, and operating-process explanation. In SimCorp
Sales Ops, use for Commercial Approval workflow or forecast operating cadence.
Do not use as the visual for the 8-stage sales process when the metric is ARR
by stage; use an explicit stage bar.

### Maps

Useful only when geography is the decision variable. For most director books,
ranked bars outperform maps because the audience needs value, owner, and deal
evidence rather than location decoration.

## Low-Fit or Avoid-by-Default Families

- Pie and doughnut: only for simple 2-3 part shares with direct labels.
- Funnels: avoid for the SimCorp 8-stage process.
- Gauges, thermometers, traffic lights: avoid for headline financial metrics.
- Venn, cubes, pyramids, generic symbols, ratings, hand-drawn elements, quotes:
  avoid in operating decks unless the slide is explicitly conceptual.
- Team/profile slides: useful for enablement or org decks, not pipeline reviews.

## Selection Rule

The correct chart is the one that answers the operating question with the least
interpretive burden. A stock template is valid for SimCorp only after it passes
three gates:

- Business basis: ARR, ACV, count, rate, or date basis is explicit.
- Eligibility: the data shape actually fits the chart family.
- Automation: the object can be built, linked, refreshed, and validated without
  manual repair.
