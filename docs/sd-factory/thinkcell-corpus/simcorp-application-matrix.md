# SimCorp Application Matrix

Date: 2026-05-01

This matrix maps think-cell template families to SimCorp use cases.

## Sales Director Monthly Review

Recommended lanes:

- KPI strip from Dashboard/Statistics: S02 highlights, with ARR and ACV
  separated.
- Waterfall: movement from prior review to current review.
- Bar/Column: stage, owner, country, forecast category, aging, stale activity.
- Tables: named deals, approval exceptions, renewal watchlist, action register.
- Scatter/Bubble pilot: deal risk inspection by value, probability, age, or
  activity recency.
- Timeline/Gantt pilot: approval and renewal milestone dates only.

Avoid:

- Funnel for the 8-stage sales process.
- Pie/doughnut for pipeline mix unless there are only 2-3 categories.
- Full dashboard clone with traffic lights.

Key SimCorp adaptation:

- The meeting spine should be 12-16 decision slides plus appendix, not a
  28-slide template dump.
- Slide titles should be operating questions, not data-object captions.
- Tables remain high-value because Sales Directors need named account and owner
  evidence.

## Regional QBR

Recommended lanes:

- Waterfall for quarter movement and forecast variance.
- Bar/Column for stage, region, owner, segment, and forecast category.
- Line/Area for quarter-over-quarter or multi-week changes.
- Tables for top deals, pushes, approvals, renewals, and risk exceptions.
- Annotations for target gap, lost movement, or approval threshold.

Avoid:

- Mekko unless both dimensions are dense and useful.
- Maps unless geography is central to the decision.

Key SimCorp adaptation:

- Use separate ARR and renewal ACV sections. Do not bridge them together.
- Preserve stage names verbatim from the Commercial Handbook.

## Commercial ExCo Update

Recommended lanes:

- KPI strip for leadership orientation.
- Waterfall for movement and variance.
- Bar/Column for ranked drivers and forecast mix.
- Scatter/Bubble for material deal risk or concentration if the points are
  named.
- Tables only for the few rows that require an executive decision.

Avoid:

- Dense table pages without a clear ask.
- Decorative process or matrix pages.

Key SimCorp adaptation:

- ExCo needs fewer rows and stronger claim discipline than director packs.
- Every number should carry metric basis and date basis in a quiet footer or
  subtitle.

## CRO Keynote or Commercial Narrative

Recommended lanes:

- Bar/Column for growth, mix, or operating proof.
- Waterfall for transformation progress or forecast bridge.
- Timeline for strategic milestones.
- Process/Phases for operating model and governance narrative.
- Annotations for one visible insight per chart.

Avoid:

- Overusing stock infographic process slides.
- Template-heavy dashboard pages.

Key SimCorp adaptation:

- Use the visual family to support the thesis, not to enumerate every KPI.
- Keep Axioma and SimCorp reporting boundaries explicit where applicable.

## Pipeline Hygiene and Deal Inspection

Recommended lanes:

- Scatter/Bubble for risk/outlier inspection.
- Ranked Bar for stale activity, aging, push count, and owner exposure.
- Tables for named deals and required action.
- Callouts/Annotations for thresholds and rule breaches.

Avoid:

- Traffic lights as the main evidence.
- Aggregated charts without rows behind them.

Key SimCorp adaptation:

- Deal hygiene slides should trace to Salesforce fields and rule IDs.
- Use `Stage_20_Approval__c` and submit date evidence for Commercial Approval
  exceptions.

## Renewal and Retention

Recommended lanes:

- Tables for renewal ACV watchlist.
- Timeline/Gantt for renewal decision windows when dates are real.
- Bar/Column for renewal ACV by period, owner, or risk category.
- KPI strip for renewal count and ACV exposure.

Avoid:

- Showing renewal ACV in ARR pipeline totals.
- Mixing Renewal rows into Land+Expand pipeline counts.

Key SimCorp adaptation:

- ACV is not ARR. Renewal visuals need their own section, labels, and filters.

## Territory and Account Expansion

Recommended lanes:

- Ranked Bar for country, account, owner, and motion exposure.
- Table for account x motion evidence.
- Mekko only for true account or segment mix where width and composition both
  carry insight.
- Map only when leadership is deciding territory coverage or geographic focus.

Avoid:

- Map-as-decoration.
- Sparse Mekko charts.

Key SimCorp adaptation:

- Axioma coverage may need explicit source/entity labels.
- Existing account expansion should not be blended with net-new Land motion
  unless the metric is explicitly Land+Expand ARR.

## Business Process and Governance

Recommended lanes:

- Processes/Flow Charts for Commercial Approval flow, forecast cadence, and
  operating handoffs.
- Agendas/Schedules for meeting rhythm.
- Matrices for ownership or decision-rights clarity.
- Timeline for implementation or rollout sequence.

Avoid:

- Process art when the slide is actually a metric trend.
- Generic SWOT unless the audience is making a strategy choice.

Key SimCorp adaptation:

- Governance pages should name fields, owners, systems, and outputs.
- Use process visuals to clarify responsibilities, not to decorate analytics.

## Visual Eligibility Gates

| Visual family | Pass condition | Fallback |
|---|---|---|
| KPI strip | 3-5 trusted metrics with explicit basis | Short executive table |
| Waterfall | Real start, movements, end; signed values audited | Movement table |
| Bar/Column | Comparable categories or business-ordered stages | Table |
| Line/Area | Real time axis with 3+ comparable points | Column or table |
| Scatter/Bubble | Named points with non-collapsed axes | Ranked table |
| Timeline/Gantt | Distinct real dates per row | Decision register |
| Mekko | Dense two-dimensional mix | Stacked column or heat table |
| Table | Row-level evidence supports a decision | Simplify rows or split appendix |
| Map | Geography is the decision variable | Ranked geography bar |
