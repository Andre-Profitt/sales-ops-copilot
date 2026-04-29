# Role-Based Dashboard Design — Going Deep

_2026-04-28. Reset of the dashboard suite design driven by what each role actually needs, anchored on SimCorp's real data layer._

## Why this exists

The 11 dashboards built earlier today were superficial. They:

1. Were **chart-heavy** (good for stating, bad for acting). Andre's "Sales Excellence" dashboard is 14 FlexTables / 3 charts — drill-list-forward.
2. **Ignored Einstein scoring** (`IqScore` is populated on 1,000+ open opps).
3. **Ignored explicit risk fields** (`Risk_of_Potential_Termination__c` flags 146 at-risk accounts; `Risk_Assessment_Level__c` flags 178 opps).
4. **Ignored Pardot/Engagio scoring** (155 unconverted leads with `pi__score__c ≥ 100`).
5. **Had no quota/coverage anchor** (one-third of CRO/Director questions are "are we tracking?").
6. Mixed user groups (a CRO doesn't want to read 14 drill lists; an MD-1 director does).

This doc rebuilds the design role-by-role.

---

## CRO / Chief Revenue Officer

### Job-to-be-done

Hit annual revenue plan. Run weekly forecast call. Decide where to invest headcount and where to pull back. Speak to board monthly.

### Decisions made from a dashboard

- Are we tracking to plan? Where's the gap?
- Which region/segment is the leading indicator of risk?
- Whose forecast do I trust?
- Which 10 deals must close this quarter?
- Is retention healthy enough that net growth holds?

### Dashboard contents

| Widget                                                                               | Type                | Data source                                                                                                       | Why                              |
| ------------------------------------------------------------------------------------ | ------------------- | ----------------------------------------------------------------------------------------------------------------- | -------------------------------- |
| **Plan-to-actual** (single tile triple: Bookings vs Plan QTD / YTD / FY)             | Metric × 3          | `APTS_Opportunity_ARR__c` won + manual quota input or `APTS_Forecast_Quota_Retirement__c`                         | The single most-important number |
| **Forecast funnel** (Closed-Won / Commit / Best Case / Pipeline rolling to forecast) | Stacked Bar         | `ForecastCategoryName` + `APTS_Forecast_ARR__c` + ARR                                                             | What will EoQ look like          |
| **Coverage ratio by region**                                                         | Bar                 | open pipeline ARR / regional target. Need targets by region (hardcoded or from Quota_Amount\_\_c per-rep rollup)  | Where's pipeline thin            |
| **Forecast accuracy trend (8Q)**                                                     | Column              | OpportunityFieldHistory: ForecastCategory at start of Q vs IsWon at end of Q                                      | Director credibility             |
| **YoY same-period bookings**                                                         | Column (paired)     | won ARR this-Q vs same-Q-last-year                                                                                | Growth signal                    |
| **NRR trend**                                                                        | Column              | Renewed ACV / opening ACV per Q                                                                                   | Retention is half the company    |
| **Top 25 deals at risk this Q**                                                      | FlexTable (TABULAR) | open this-Q where `Risk_Assessment_Level__c IN (Medium-High, High)` OR `IqScore ≤ 4` OR (Stage ≥ 5 AND prob < 60) | Single drill list with action    |
| **Stage-progression rate (4 weeks)**                                                 | Bar                 | OpportunityHistory: % opps moving stage in last 28d                                                               | Pipeline aliveness               |

**Total: 8 widgets.** Today's CRO Cockpit has 4. **Big gap = forecast credibility, plan-to-actual, top-deals drill, NRR.**

---

## VP Sales / Regional VP (peer of CRO, runs one geo)

Same widgets as CRO but **scoped to their region** via dashboard-level filter on `Account.Region__c`. **One dashboard, multiple consumers via filter** — not 7 cloned dashboards.

---

## Sales Director (MD-1) — there are 9

### Job-to-be-done

Hit regional plan. Coach 6-15 AEs. Run monthly business review (this is what `run_monthly_director_review.py` already produces in PPTX). Make AE-level investment calls (which deal needs me).

### Decisions made from a dashboard

- Where are my reps relative to quota?
- Which deals are slipping or stuck?
- Whose pipeline is too thin?
- Which deals need approval/exec attention?
- Where are activities falling short on critical accounts?
- Are reps following the methodology (NextStep, Probability matches Stage)?

### Dashboard contents

| Widget                                           | Type                | Data source                                                                   | Why                         |
| ------------------------------------------------ | ------------------- | ----------------------------------------------------------------------------- | --------------------------- |
| **Per-rep scorecard** (FlexTable)                | FlexTable           | OwnerId roll-up: quota / open ARR / coverage / # stale / win-rate             | Single coaching view        |
| **Deals slipping (this-Q → next-Q in last 30d)** | FlexTable           | OpportunityFieldHistory: CloseDate change where prev was in CFQ, new ≥ next-Q | Direct coaching signal      |
| **Stage-progression rate per rep**               | Bar                 | OppHistory: % moving stage last 28d, grouped by Owner                         | Who's actually moving deals |
| **Pipeline by rep + stage**                      | Bar (clustered)     | open ARR by Owner × StageName                                                 | Depth visibility            |
| **Stale deals by rep**                           | FlexTable           | LastActivity > 30d, by Owner                                                  | Coaching list               |
| **Top deals to inspect**                         | FlexTable (TABULAR) | high-ARR + late stage + IqScore ≤ 5                                           | Pipeline review focus       |
| **Probability mismatch by stage**                | FlexTable           | Stage 3+ where prob < expected (S3<20, S4<50, S5<70, S6<85)                   | Forecast hygiene            |
| **Renewal pipeline by rep**                      | FlexTable           | open Type=Renewal by Owner                                                    | Adjacent rev ownership      |
| **Approvals pending in my book**                 | FlexTable           | `Submit_for_Stage_20_Review__c=true AND Stage_20_Approval__c=false`           | Bottleneck visibility       |
| **Won this Q by rep**                            | Bar                 | won ARR by Owner                                                              | Attainment                  |

**Total: 10 widgets.** The current SD Monthly has 20 widgets but most are charts, not coaching FlexTables. **Recommend: rebuild SD Monthly toward this drill-list-forward design + dashboard filter on Region for per-director scoping.**

---

## Account Executive (AE)

### Job-to-be-done

Hit individual quota. Manage 20-50 active opps. Maintain account relationships. Daily/weekly self-coordination.

### Decisions made

- What's on my plate this week?
- Which deals haven't moved in 14d?
- Where am I vs my target?
- What's stuck on approval / contract / legal?
- Who hasn't responded to my last 3 touches?

### Dashboard contents

| Widget                                | Type      | Data                                               | Why                    |
| ------------------------------------- | --------- | -------------------------------------------------- | ---------------------- |
| **My deals to close this week**       | FlexTable | CloseDate ≤ +7d AND IsClosed=false AND OwnerId=$me | This-week to-do        |
| **My pipeline by stage**              | Bar       | open ARR grouped by Stage, OwnerId=$me             | Where am I working     |
| **My quota attainment**               | Metric    | won ARR YTD / quota                                | Self-check             |
| **My stale deals (>14d no activity)** | FlexTable | LastActivityDate > 14d, OwnerId=$me                | To-do list             |
| **My approvals pending**              | FlexTable | mine + Stage_20 pending                            | What's stuck           |
| **My renewal book**                   | FlexTable | Type=Renewal, OwnerId=$me, this-FY                 | Renewal ownership      |
| **Activity heatmap (this week)**      | Bar       | Activity count by day-of-week, OwnerId=$me         | Productivity self-view |

**Note**: AE dashboards in SF are typically _user-scoped_ via `userOrHierarchyFilter` — each AE sees their own. **We don't currently have any AE-targeted dashboard.** This is a real gap.

---

## Sales Operations (Andre's team)

### Job-to-be-done

Make Sales productive. Maintain data integrity. Run forecasting/reporting cadence. Compensation calc. Methodology adherence.

### Decisions made

- Where's data quality eroding?
- Which processes are breaking?
- Are reps following the methodology?
- Where's the funnel leaking?
- What needs to be fixed before EoQ for clean comp calc?

### Dashboard contents

| Widget                                | Type       | Data                                                                             | Why                |
| ------------------------------------- | ---------- | -------------------------------------------------------------------------------- | ------------------ |
| **Pollution-trend (90d)**             | Column     | TYPE=Land/Expand opps fail-pollution-rule count by week                          | Are we improving?  |
| **Per-rep governance scorecard**      | FlexTable  | red flags per rep: missing fields + stale + late close + prob mismatch           | Accountability     |
| **Approval cycle time trend**         | Column     | days submitted-to-approved per gate, fiscal-week                                 | Operational SLA    |
| **Stage-progression velocity**        | Bar        | avg days-in-stage by Stage                                                       | Process health     |
| **Pipeline leakage funnel**           | Funnel     | leads → MQL → SQL → Opp → Won, conversion at each step                           | Where's the leak   |
| **Forecasting methodology adherence** | FlexTable  | Commit-but-Activity>14d-stale; Best-Case-with-prob<60; Land-without-CommApproval | Forecast trust     |
| **Quote-to-Cash health**              | Metric × 4 | Quote → Order → Invoice → Won transition counts                                  | Revenue ops health |
| **Comp-readiness pre-checks**         | FlexTable  | won opps missing Quota_Amount\_\_c, Owner=null, ARR=null                         | Pre-payout cleanup |
| **Probability mismatch (org-wide)**   | FlexTable  | Stage X where prob outside expected band                                         | Forecast hygiene   |
| **KYC compliance**                    | Bar        | accounts by `KYC_Approval_Status__c`                                             | Compliance gate    |

**Today's Sales Ops Quarterly KPI** has 18 widgets but most are **point-in-time counts** — almost no trend, no SLA trend, no leakage funnel. **Recommend: keep most of it but add the trend widgets above.**

---

## Deal Desk

### Job-to-be-done

Review/approve non-standard pricing, contract terms, margin. Be unblocked or unblock fast. SLA-driven team.

### Decisions made

- What's in my queue today?
- What's been waiting too long?
- Who (which approver) is the bottleneck?
- Which pricing exceptions are recurring?
- Are SLAs being met?

### Dashboard contents

| Widget                                      | Type         | Data                                                                           | Why                |
| ------------------------------------------- | ------------ | ------------------------------------------------------------------------------ | ------------------ |
| **My approval queue (Stage 3 / 4 / Final)** | 3× FlexTable | open Land where Submit*for_Stage*<N>_Review=true AND Stage_<N>\_Approval=false | Daily work         |
| **Aging in queue**                          | Bar          | days-in-queue buckets: 0-2 / 3-5 / 6-10 / 10+                                  | SLA breach risk    |
| **By approver workload**                    | Bar          | open approval count by `<Stage>_Approver__c` if exists, else Owner             | Load balance       |
| **Discount distribution**                   | Bar          | discount % buckets across pending approvals                                    | Exception flagging |
| **Approval cycle time trend**               | Column       | median days submit-to-approve, fiscal-week                                     | SLA monitoring     |
| **Acceptance rate**                         | Metric       | approved / (approved + rejected)                                               | Approval quality   |
| **Recently rejected with reasons**          | FlexTable    | Stage\_<N>\_Approval=false AND submitted_at > 30d ago                          | Feedback loop      |

**Today's Deal Desk Operations** has 1 widget after my fix. **Massive gap. ~6 widgets to add.**

---

## Marketing / Demand Gen

### Job-to-be-done

Generate qualified pipeline. Hit MQL/SQL targets. Show marketing ROI. Optimize source mix.

### Decisions made

- Are we hitting MQL/SQL targets?
- Which sources convert best end-to-end?
- What's funnel velocity?
- Where's drop-off worst?
- What's marketing-attributed pipeline value?

### Dashboard contents

| Widget                                         | Type      | Data                                                  | Why                         |
| ---------------------------------------------- | --------- | ----------------------------------------------------- | --------------------------- |
| **Lead → MQL → SQL → Opp → Won funnel**        | Funnel    | Lead status progression + Pardot score thresholds     | Full conversion picture     |
| **Velocity per stage**                         | Bar       | median days-in-status                                 | Where it slows              |
| **Source ROI (last 4Q)**                       | FlexTable | LeadSource × leads × converted × won-ARR-attributed   | Best converting sources     |
| **Pardot-hot unconverted leads (score ≥ 100)** | FlexTable | Lead where `pi__score__c ≥ 100 AND IsConverted=false` | 155 hot leads not picked up |
| **Lead aging by stage**                        | Column    | days-since-status-change buckets                      | Stuck leads                 |
| **Geographic heat**                            | Bar       | Country                                               | Where leads come from       |
| **Disqualified reason mix**                    | Pie       | `Disqualified_Reason__c`                              | Funnel-leakage cause        |
| **Campaign attribution**                       | FlexTable | open opps × CampaignId via OpportunityContactRole     | Marketing-pipeline tie      |

**Today's Marketing & Lead Funnel** has 5 widgets. **Missing: full funnel, Pardot-score-hot list, source ROI end-to-end.** Now that the scope=org fix is in (7K-53K rows visible), this dashboard becomes meaningful.

---

## CSM / Renewals Team

### Job-to-be-done

Retain logos. Drive expansion. Predict churn. Run QBRs.

### Decisions made

- Which 10 accounts need QBR / exec sponsor visit this month?
- Which renewals are at risk this quarter?
- Where's expansion potential?
- What's NRR tracking to?

### Dashboard contents

| Widget                              | Type      | Data                                                                                    | Why                       |
| ----------------------------------- | --------- | --------------------------------------------------------------------------------------- | ------------------------- |
| **NRR trend (4Q)**                  | Column    | renewed ACV / opening ACV by Q                                                          | The renewals KPI          |
| **At-risk accounts** (FlexTable)    | FlexTable | Account where `Risk_of_Potential_Termination__c IN (High, Medium)` AND has open renewal | **146 records currently** |
| **Renewal pipeline coverage**       | Metric    | open renewal ACV this-Q / target-renewal-ACV                                            | Coverage                  |
| **Expansion pipeline by account**   | FlexTable | open Type=Expand by Account                                                             | Upsell ownership          |
| **Stuck renewals (>30d)**           | FlexTable | Type=Renewal AND days-in-stage > 30                                                     | Stale renewals            |
| **Renewal uplift mix**              | Bar       | renewals by ACV-uplift bucket: downsize / flat / +10% / +25%+                           | Expansion success         |
| **Adoption-Score distribution**     | Bar       | Account.Overall_Adoption_Score\_\_c buckets                                             | Health → churn predictor  |
| **Top 10 renewals by ACV (this Q)** | FlexTable | open Type=Renewal CFQ ordered by ACV                                                    | Must-close list           |

**Today's Renewals Dashboard** has 7 widgets but lacks NRR, stuck renewals, expansion isolation, adoption-score distribution. **Big gap: no widget uses `Risk_of_Potential_Termination__c` despite 146 flagged accounts.**

---

## Finance / Strategic Finance / FP&A

### Job-to-be-done

Forecast bookings/revenue. Calc commissions. Board reporting. Cohort analysis.

### Decisions made

- What will EoQ bookings be?
- How does Commit vs Best vs Won compare to history?
- What's our forecast accuracy (rolling 8Q)?
- ARR/ACV cohort retention curves?
- Average deal size trend (pricing power)?

### Dashboard contents

| Widget                              | Type             | Data                                                             | Why                 |
| ----------------------------------- | ---------------- | ---------------------------------------------------------------- | ------------------- |
| **Bookings waterfall**              | Stacked Bar      | Land + Expand + Renewal stack, last 8Q                           | Composition         |
| **Forecast accuracy trend (8Q)**    | Column           | OpportunityFieldHistory: ForecastCategory at start vs Won at end | Calibration         |
| **Pipeline-to-bookings conversion** | Bar              | won ARR / (open ARR + won ARR) per cohort-Q                      | Predictive          |
| **Cohort retention**                | Heat-style table | by acquisition-Q, ACV retained at +12mo / +24mo                  | Long-term retention |
| **YoY bookings comparison**         | Column (paired)  | this-Q vs same-Q-last-year by motion                             | Growth              |
| **Avg deal size trend**             | Line             | rolling 4Q ARR average                                           | Pricing power       |
| **Discount-adjusted ARR**           | Metric           | ARR after Apttus discount %, this-Q                              | Net pricing reality |

**Today's Forecast Accuracy & Pacing** has 5 widgets but is missing the waterfall, cohort, YoY, and long-term retention. **Net-new audience — currently no dashboard truly serves Strategic Finance.**

---

## Strategic recommendations

### Priority order to ship

1. **Add Einstein-IqScore-driven widgets to SD Monthly + CRO Cockpit + Renewals.** Massive untapped signal (1,000+ scored opps). Ships in this session.

2. **Build the "Top 25 deals at risk" FlexTable for CRO Cockpit** — combines Einstein + explicit risk + probability mismatch. CRO's most-clicked widget will be this one.

3. **Build "At-Risk Accounts" widget on Renewals using `Risk_of_Potential_Termination__c`.** 146 accounts already flagged. Currently invisible.

4. **Build the AE personal dashboard** — the only fully-missing audience. One dashboard with `userOrHierarchyFilter=user` scope, ~7 widgets.

5. **Plug Pardot-hot leads (score ≥ 100, unconverted)** into Marketing dashboard. 155 leads currently hot and unactioned.

6. **Probability-mismatch FlexTable** — single widget, applies to SD Monthly + Sales Ops Q + Forecast Accuracy. Reuse.

7. **Approval cycle time trend** — Deal Desk's missing operational KPI.

8. **NRR trend** — needs prior-period ACV reference; complex but high-value for Renewals + CRO.

9. **Forecast accuracy 8Q trend** — needs OpportunityFieldHistory + window logic; CRO + Finance both consume.

10. **Cohort retention table** — Strategic Finance audience; nice-to-have.

### Per-dashboard verdict

| Dashboard                  | Verdict                                                                                                      | Top fix                                                                                           |
| -------------------------- | ------------------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------- |
| Sales Directors Monthly    | **Keep, but reshape** to 12 FlexTable + 8 charts. Add probability-mismatch, slipping-deals, deals-to-inspect | Drop "What was won FY26" + "Wins vs losses" (blended motions); add prob-mismatch + slipping deals |
| Sales Ops Quarterly KPI    | **Keep, add 4 trend widgets**                                                                                | Pollution-trend + approval-cycle-trend + per-rep scorecard + leakage funnel                       |
| Renewals                   | **Add 3 widgets**                                                                                            | At-risk accounts + NRR + uplift mix                                                               |
| Win/Loss Analysis          | **Add 2 widgets**                                                                                            | Win rate by ICP + Loss reasons trended                                                            |
| Deal Desk                  | **Major buildout (1 → 7 widgets)**                                                                           | All from the Deal Desk section above                                                              |
| CRO Cockpit                | **Major upgrade (4 → 8 widgets)**                                                                            | Plan-to-actual + forecast funnel + top-25 at-risk + NRR trend                                     |
| Marketing & Lead Funnel    | **Add 3 widgets**                                                                                            | Pardot-hot + full funnel + source ROI                                                             |
| Forecast Accuracy & Pacing | **Add 3 widgets**                                                                                            | 8Q accuracy + commit calibration + slip rate                                                      |
| Account Health Watch       | **Add 2 widgets**                                                                                            | Adoption score distribution + at-risk accounts                                                    |
| Activity Health            | **Add 2 widgets**                                                                                            | Last-touch age distribution + coaching alerts                                                     |
| Quarter Close Pacing       | **Add 2 widgets**                                                                                            | Daily burndown + approval bottleneck                                                              |
| **NEW: AE Personal**       | **Build**                                                                                                    | 7 widgets, user-scoped                                                                            |

### What's blocked

- **Quota / coverage** — `ForecastingQuota` is empty. Need `Quota_Amount__c` on Opp to be populated, OR a hardcoded targets table, before coverage widgets work.
- **NRR** — needs renewal-ACV-by-cohort logic. Calculable via SOQL on closed-won Renewals; complex report.
- **Stage-progression rate** — needs OpportunityFieldHistory queries. SF Reports support it; we'd build a "Historical Tracking" report type.
- **MQL/SQL formal definitions** — needs to know which Lead.Status values map to which funnel stage. Pardot score threshold is one option.
