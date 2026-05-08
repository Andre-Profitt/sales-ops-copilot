# May 2026 Template Improvement Audit

Date: 2026-05-01

## Bottom Line

The current template is functional for automation, but it is still too close to a technical build scaffold. It needs a director-facing design pass before we use it as the canonical monthly template.

The biggest change: each slide should start from the decision the Sales Director needs to make, then choose the visual. The current template often starts from a chart/table object, which is why some visuals feel forced.

## High-Impact Improvements

| Area | Current issue | Fix |
|---|---|---|
| Slide titles | Many titles read like formulas or data-object captions: "Open ARR by Account.BillingCountry", "(# opps × win rate × avg deal)..." | Rename to operating questions: "Where is Q2 close risk concentrated?", "Which owners need forecast cleanup?", "What changed since Q1?" |
| Chart eligibility | Some chart families were selected because think-cell supports them, not because the data demands them. | Add chart gates: Waterfall only with true movement, Timeline/Gantt only with real dated milestones, Scatter only with meaningful x/y axes, Mekko only with dense two-dimensional mix. |
| Action cadence | A Gantt-like view looks over-engineered when the inputs are generic action due dates. | Replace with a "May decision register" table: priority, deal/rule, evidence gap, owner, due date, next decision. Use timeline only for actual close-plan milestone dates. |
| Section dividers | Section slides previously rendered with generic title/subtitle hierarchy issues. | Use the section name as the large title: Pipeline, Retention, Territory, Risk & Actions. No placeholder-looking subtitle. |
| KPI tiles | Earlier boxed KPI cards looked generated and over-framed. | Use a thin KPI strip: small label, large number, exact metric basis, minimal separators. No heavy cards. |
| Metric basis | Weighted vs unweighted ARR and ACV separation can be missed. | Put metric basis in every slide footnote or subtitle. Label weighted ARR only when weighted. Renewal ACV never appears in ARR tiles. |
| Dense tables | Table-image lane can look stretched or inconsistent if manually carried over/resized. | Lock table row heights, header color, font sizes, and target bounds. Gate for tiny linked objects, blank rows, `#NULL`, `#NAME`, and 5000% probability errors. |
| Purple headers | Tables currently overuse purple, which can feel off-brand when repeated. | Use SimCorp blue/navy as default table header; reserve purple or coral for emphasis/risk. |
| Slide count | 28 slides is useful for an appendix but heavy for a director meeting. | Make a 12-16 slide meeting spine plus appendix. Keep the same factory outputs, but mark some slides as appendix by default. |
| Template vs production | The base template contains placeholder instructions; the built decks need polished slide shells. | Maintain two assets: an engineering/wiring template and a director-facing template shell generated from it. |

## Chart Gates

| Visual family | Use when | Avoid when |
|---|---|---|
| KPI strip | Executive orientation and metric basis clarity | It becomes a boxed mini-dashboard |
| Waterfall | There is a true start, movement, and end state | We only have independent won/lost/current snapshots |
| Bar/Column | Ranking, distribution, stage mix, owner/country comparison | More than 8-10 categories without sorting |
| Scatter/Bubble | Each point is a named deal with value and risk/probability/age | The axes do not create a real inspection decision |
| Timeline/Gantt | There are real dated milestones per deal/action | All rows share the same generic month-end due date |
| Mekko | Both dimensions matter and the matrix is dense | It is sparse or the audience needs exact values |
| Table | Named deal evidence, actions, approvals, renewals | It is used to compensate for missing narrative |

## Proposed Meeting Spine

1. May operating summary
2. Q1 accountability retained from original APAC deck
3. Q2 closeable pipe and forecast quality
4. Named Q2 deal readiness
5. Commercial approval gaps
6. Renewal ACV watchlist
7. Owner coaching focus
8. Territory / country exposure
9. QTD wins and losses
10. Concentration and deal-risk inspection
11. May decision register
12. Open decisions / asks

Appendix:

- Pipeline by stage
- Pipeline aging
- Forecast category detail
- Q1 loss drivers
- Pushed deals
- Account expansion
- Pipeline creation trend if data is strong

## Factory Changes To Make

1. Add a `visual_gate` field to the connected factory spec per object.
2. Split `visualization_lane` into `primary_visual`, `fallback_visual`, and `eligibility_rule`.
3. Add publish-gate checks for unsupported visuals:
   - Waterfall without nonzero movement components.
   - Timeline/Gantt where every due date is identical.
   - Scatter where all x or y values collapse to one value.
   - Mekko with sparse matrix.
4. Add a slide-title rewrite map so deck titles are director-facing while object IDs remain stable.
5. Create a director-facing deck shell separate from `assets/LAND_template.pptx`, which remains the wiring scaffold.

