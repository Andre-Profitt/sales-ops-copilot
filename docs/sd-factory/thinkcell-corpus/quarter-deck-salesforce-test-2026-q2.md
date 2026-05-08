# Q2 2026 Salesforce-Backed think-cell Test

Date: 2026-05-01

This test evaluates what the think-cell template corpus can actually do in the
May 2026 / 2026-Q2 Sales Director decks using live Salesforce data from
`preprod`, not only existing PowerPoint artifacts.

Runtime artifacts:

- Salesforce fit JSON:
  `state/2026-Q2/__regional__/thinkcell_sf_fit/thinkcell_quarter_salesforce_fit.json`
- Salesforce fit report:
  `state/2026-Q2/__regional__/thinkcell_sf_fit/thinkcell_quarter_salesforce_fit.md`
- Regional publish gate:
  `state/2026-Q2/__regional__/publish_gate/regional_publish_gate.md`
- Packaged deck visual gate:
  `state/2026-Q2/__regional__/visual_gate/review_package/review_package_visual_gate.md`

## Source Basis

- Salesforce target org: `preprod`
- User: `apro@simcorp.com`
- Q2 window: `2026-04-01` through `2026-06-30`
- Opportunity scope: open `Type IN ('Land','Expand','Renewal')`
- ARR source: `convertCurrency(APTS_Opportunity_ARR__c)` for Land+Expand
- Renewal source: `convertCurrency(APTS_Renewal_ACV__c)` for Renewal
- Director scope: canonical Account-field filters in `scripts/_directors.py`
- Internal/test filter: shared `sales_director_row_filters.py`

Salesforce returned 357 raw Q2 rows. After internal/test filtering, 314 rows
remain publishable. The filter removed 33 rows, concentrated in Northern Europe
and Central Europe.

## Test Result

| Family | Eligible directors | Q2 deck action |
|---|---:|---|
| Bar/Column | 9/9 | Production default for stage, forecast, owner, country, aging, and stale activity. |
| Scatter/Bubble | 8/9 | L5-proven as QTR04 stock-donor automation; Patrick Gaughan falls back to table/ranked bar. |
| FY26 Renewal Timeline/Gantt | 8/9 | L5-proven as QTR05 stock-donor automation; Adam Steinhouse falls back to table. |
| Q2-only Renewal Timeline/Gantt | 3/9 | L5-proven as QTR06 for Sarah Pittroff; do not make this a universal Q2 slide. |
| Mekko | 8/9 | L5-proven as QTR07 native-chart automation; keep rare because density alone does not prove leadership usefulness. |
| Map | 6/9 | Not a default. Use ranked geography bars unless geography is the decision. |

All nine current linked Q2 decks still pass the regional publish gate. All nine
packaged meeting-spine decks render cleanly through the visual gate.

## Director Exceptions

| Director | Exception | Deck implication |
|---|---|---|
| Patrick Gaughan | Scatter axes fail because positive ARR has only one distinct value. | Keep deal-risk as table or ranked bar unless a better y-axis is added, such as age, push count, risk score, or activity recency. |
| Adam Steinhouse | FY26 renewal dates collapse to `2026-12-31`. | Use renewal ACV table only; no renewal Gantt. |
| Christian Ebbesen | 31 raw Q2 rows removed as internal/test. | Keep internal/test filter as a blocker gate before any visual refresh. |
| Sarah Pittroff | 2 raw Q2 rows removed as internal/test. | Same filter dependency, lower volume. |

## What We Can Do This Quarter

Production-safe now:

- Keep Bar/Column as the universal analytical chart family.
- Keep table-image slides for named deals, approval gaps, renewals, owner
  coaching, and action registers.
- Keep Waterfall where the existing workbook movement bridge passes the signed
  closed-lost gate.
- Keep decision-register tables for action slides.
- Keep the 12-16 slide meeting spine as the leadership-facing package.

Conditional pilot:

- Promote Scatter/Bubble deal-risk inspection from automation proof to
  production-polished pilot for the eight directors with real probability and
  ARR spread.
- Promote FY26 Renewal Timeline/Gantt from automation proof to
  production-polished pilot for the eight directors with renewal close-date
  spread.
- Use Q2-only Renewal Timeline/Gantt only for Sarah Pittroff, Dan Peppett, and
  Christian Ebbesen unless another director's data shape changes.
- Add a Mekko only if the claim is genuinely stage-by-industry or motion mix and
  the slide can survive a leadership read without exact-value ambiguity.

Do not do this quarter:

- Do not use funnels for the SimCorp 8-stage sales process.
- Do not use action-item Gantt charts from current Salesforce fields. `NextStep`
  is text, and current action due dates imply false precision.
- Do not use native think-cell tables as a production lane until a real named
  data-backed donor is proven.
- Do not make Q2-only renewal Gantt a standard slide; only 3 of 9 directors
  qualify.

## Verification Commands

```bash
.venv/bin/python scripts/test_thinkcell_quarter_deck_salesforce_fit.py --target-org preprod
.venv/bin/python scripts/run_regional_deck_publish_gate.py --period 2026-Q2
.venv/bin/python scripts/run_review_package_visual_gate.py \
  --period 2026-Q2 \
  --package-dir "/Users/test/Downloads/May 2026 Meeting Spine Candidates" \
  --output-dir state/2026-Q2/__regional__/visual_gate/review_package
```

## Build Recommendation

The next implementation should be production-polish QA, not another automation
proof. Start with a narrow two-slide insertion candidate on Jesper or Sarah:

- Deal-risk Scatter/Bubble using named Q2 deals with probability on x-axis and
  converted ARR on y-axis.
- FY26 Renewal Timeline/Gantt using Renewal ACV rows and close-date spread.

If both survive the PowerPoint render and publish gates, generalize with
director-level eligibility fallbacks: Patrick gets table/ranked bar for risk;
Adam gets renewal table only.
