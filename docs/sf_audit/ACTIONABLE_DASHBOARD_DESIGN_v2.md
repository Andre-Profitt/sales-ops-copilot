# Actionable Dashboard Design v2 — Decision-Driven, Not Information-Driven

_2026-04-28. Built from web research (10 sources) + SimCorp data probing._

## Why Wave 1 felt boring

Wave 1 added widgets but kept them **informational**. Every widget displayed a number; none of them prescribed an action. The literature is unambiguous (Pavilion, Coefficient, Highspot, RevOps.io, DealHub, 2026 benchmarks):

> "If a metric doesn't trigger a response when it moves, delete it from the dashboard."

The CRO best-practice dashboard is **only 4 numbers**: Pipeline Coverage, Win Rate, Forecast Accuracy, NRR. Everything else feeds into them. The director's tool is a **scorecard** (rep-level, red/yellow/green, 1:1-driven), not a dashboard. The Deal Desk dashboard tracks **3 numbers**: cycle time, discount depth, SLA compliance — with a target line on each.

## What SimCorp's data actually supports

Discovered today (none of these were in any current dashboard):

| Data                                                                                | Found                               | Real numbers right now                                  |
| ----------------------------------------------------------------------------------- | ----------------------------------- | ------------------------------------------------------- |
| **`User.Annual_Revenue_Goal__c`** (quota)                                           | 29 active reps populated            | Total quota = EUR 60.6M FY                              |
| **`OpportunityFieldHistory.CloseDate`** (slip)                                      | 404 changes last 30d                | **16 deals slipped from this-Q to next-Q+ in last 30d** |
| **`Stage_20_Approval_Date__c` − `Submit_for_Stage_20_Review_Date__c`** (cycle time) | 30 closed Stage-3 approvals sampled | **Median 7 days. Max 93 days. 53% breach a 5-day SLA.** |
| **`IqScore`** (Einstein)                                                            | 1,000+ scored                       | EUR 433M scored open pipe                               |
| **`Risk_of_Potential_Termination__c`**                                              | 146 flagged accts                   | 80 High + 66 Medium                                     |
| **Task volume per rep last 30d**                                                    | Real                                | Top human rep = 1,648 tasks; lots of zeros below        |

## Coverage gap right now (real numbers)

- Open L+E this-Q ARR: **EUR 27.7M**
- Sum of Annual_Revenue_Goal across active reps: **EUR 60.6M FY**
- Quarterly target proxy (FY/4): **EUR 15.2M**
- **Coverage ratio: 1.83x**
- Best-practice target: **3.0x** (red flag below 3.0x)

**Action implied for CRO**: pipeline is at **61% of best-practice coverage** for the quarter. Either accelerate creation, accept a short, or pull in deals.

This is what an actionable dashboard widget looks like — it answers the CRO's exact Monday question.

---

## Per-Role Design (decision → threshold → widget → action)

### CRO Cockpit — 4 numbers (tier 1) + 4 drill lists (tier 2)

**Tier 1 — the Monday-morning glance**

| Widget                                        | Decision                                 | Threshold                               | Action when breached                                                      |
| --------------------------------------------- | ---------------------------------------- | --------------------------------------- | ------------------------------------------------------------------------- |
| **Pipeline Coverage Ratio (this-Q + next-Q)** | "Is pipeline thick enough to make plan?" | <3x → red, 3-4x → yellow, >4x → green   | If <3x: escalate to directors; pull in Q+1; assess marketing pipeline gap |
| **Forecast Accuracy (rolling 4Q)**            | "Can I trust the forecast?"              | <80% red, 80-90% yellow, >90% green     | If <80%: re-run pipeline review; require commit-deal evidence             |
| **Win Rate Trend (rolling 8Q)**               | "Are we winning more or less?"           | -5pt swing = red                        | If declining: focus competitive intel + win-loss interviews               |
| **NRR (rolling 4Q)**                          | "Is the install base healthy?"           | <100% red, 100-110% yellow, >110% green | If <100%: shift CSM attention to retention over expansion                 |

**Tier 2 — the drill lists when a tier-1 number is red**

| Drill list                        | Trigger               | Filter                                                                                       |
| --------------------------------- | --------------------- | -------------------------------------------------------------------------------------------- |
| Top 25 deals at risk this-Q (≥1M) | Coverage red          | (IqScore≤4 OR Risk_Assessment_Level High/Med-High OR Stage 5+ with Prob mismatch) AND ARR≥1M |
| Slipped this-Q (last 30d)         | Forecast accuracy red | OpportunityFieldHistory: 16 deals slipped this period                                        |
| Top 10 director-by-coverage       | Coverage red          | per-region coverage ratio FlexTable, sorted ascending                                        |
| Renewal at-risk above EUR 5M ACV  | NRR red               | Risk_of_Potential_Termination + ACV                                                          |

---

### Sales Director (MD-1) — Scorecard, not dashboard

The literature is unambiguous: **directors need a scorecard (rep-level red/yellow/green)**, not aggregate charts. **Highest-leverage manager activity = coaching from data, not vibe.**

**Per-Rep Scorecard FlexTable** — single widget, one row per rep, color-coded columns:

| Column                             | Threshold                    | Source                                 |
| ---------------------------------- | ---------------------------- | -------------------------------------- |
| **Quota Attainment YTD**           | <50% by Q2 = red             | Won ARR YTD / `Annual_Revenue_Goal__c` |
| **Pipeline Coverage**              | <3x of remaining quota = red | open ARR (next 2Q) / (quota − YTD-won) |
| **Slipped Deals Last 30d**         | ≥2 = red                     | OpportunityFieldHistory query          |
| **Stale Deals (>14d no activity)** | ≥3 = red                     | Task aggregation                       |
| **Approvals Stuck (>5d)**          | ≥1 = red                     | Stage_20_Approval pending              |
| **Win Rate Last 4Q**               | <20% = red                   | personal win rate                      |
| **Avg Days in Stage**              | >org P75 = red               | OpportunityHistory query               |

**Coaching trigger**: any rep with 3+ red columns → 1:1 scheduled this week.

**Supplemental drill lists on the Director dashboard**:

| Widget                                                         | Decision                              |
| -------------------------------------------------------------- | ------------------------------------- |
| **My deals slipping (this-Q → next-Q+)**                       | Which deals to push back on this week |
| **Top deals to inspect (high-ARR + late stage + low IqScore)** | Pipeline review focus                 |
| **My approvals pending >3d**                                   | Bottlenecks I need to escalate        |
| **My renewal book — at-risk**                                  | Where I need exec sponsor visit       |

---

### AE Personal Dashboard — currently doesn't exist

**Decision: "What do I work on right now?"**

| Widget                          | Filter                                          |
| ------------------------------- | ----------------------------------------------- |
| **My deals to close this week** | OwnerId=$me + CloseDate ≤ +7d                   |
| **My deals untouched >7d**      | OwnerId=$me + LastActivityDate <= today-7       |
| **My quota progress**           | (Won ARR YTD / Annual_Revenue_Goal\_\_c) Metric |
| **My approvals pending**        | OwnerId=$me + Stage_20 pending                  |
| **My renewal book this Q**      | OwnerId=$me + Type=Renewal CFQ                  |
| **My deals at risk**            | OwnerId=$me + IqScore≤4                         |
| **My next-step due**            | NextStep filled where date approaching          |

`userOrHierarchyFilter: {scope: "user"}` makes one dashboard serve every AE.

---

### Sales Ops — Data Quality + Process Compliance

The 6 dimensions of data quality (per Monte Carlo / DataKitchen / DQOps), trended:

| Dimension        | Widget                                                              | Threshold               |
| ---------------- | ------------------------------------------------------------------- | ----------------------- |
| **Completeness** | % of open opps missing critical fields (NextStep, CloseDate, Owner) | <95% = red              |
| **Consistency**  | Probability mismatch by stage (already built)                       | Count > 30 = red        |
| **Timeliness**   | % of opps with LastActivity < 30d                                   | <70% = red              |
| **Validity**     | Past-Close-Date open opps (already built)                           | Any = red               |
| **Uniqueness**   | Duplicate opp names by account                                      | Any = red (audit/clean) |
| **Accuracy**     | Opps where StageName + Probability + ForecastCategory disagree      | >0 = red                |

**Trended over 90 days** — is the org getting better or worse? This single chart drives the Sales-Ops EOQ goal.

**Approval-cycle SLA trend** — median Stage_20_Approval_Date − Submit_for_Stage_20_Review_Date by fiscal week. SLA target line at 5 days.

**Per-rep governance scorecard** — same as director scorecard but org-wide (red/yellow/green columns).

---

### Deal Desk — 3 numbers

Per RevOps.io / DealHub research, the 3 foundational KPIs:

| Widget                          | What it measures                             | Target                                   |
| ------------------------------- | -------------------------------------------- | ---------------------------------------- |
| **Cycle time trend (median)**   | Submit-to-approve days, fiscal week          | ≤5 days median (we're at 7d, missing it) |
| **Discount depth distribution** | Histogram of discount % on pending approvals | by tier; flag >threshold                 |
| **SLA compliance %**            | % approved within 5 days, fiscal week        | ≥80% (we're at 47%)                      |

**Plus drill lists**:

| Widget                              | Filter                                                       |
| ----------------------------------- | ------------------------------------------------------------ |
| **Stage 3 approval queue**          | Submit_for_Stage_20_Review=true AND Stage_20_Approval=false  |
| **Stage 4 / Final approval queues** | Same pattern for higher gates                                |
| **Aging in queue (>5d, >10d)**      | Submit_for_Stage_20_Review_Date older than 5d, still pending |
| **Approver workload**               | Pending count grouped by approver                            |

---

### Renewals / CSM

| Widget                                          | Decision                       | Threshold                       |
| ----------------------------------------------- | ------------------------------ | ------------------------------- |
| **NRR Trend (4Q)**                              | "Is retention healthy?"        | <100% red                       |
| **At-Risk Accounts FlexTable** (already built)  | "Which need exec sponsor?"     | High = exec visit; Medium = QBR |
| **Renewal Pipeline Coverage**                   | "Is renewal book covered?"     | open ACV / target               |
| **Top 10 Renewals This Q (drill list)**         | "Must-close list"              | sort by ACV desc                |
| **Adoption Score Distribution** (already built) | "Where's churn brewing?"       | <40 = red, expand exec coverage |
| **Stuck Renewals (>30d in stage)**              | "Where's the renewal blocked?" | days-in-stage > 30              |

---

### Marketing

| Widget                                                    | Decision                            |
| --------------------------------------------------------- | ----------------------------------- |
| **Lead → MQL → SQL → Opp → Win funnel with conversion %** | Where's the leak                    |
| **Source ROI (Won-ARR-attributed)**                       | Where to invest more                |
| **Pardot-Hot Unconverted** (already built)                | What needs SDR follow-up today      |
| **Lead-aging by status**                                  | Which leads are dying in the funnel |
| **Campaign-attributed pipeline**                          | Marketing's pipeline contribution   |

---

## Wave 2 ship plan (concrete + buildable)

Each of these is built on data we already have:

### Build #1: CRO Tier-1 (4 KPIs)

- **Pipeline Coverage Ratio Metric** — needs `User.Annual_Revenue_Goal__c` rollup. Computable. Currently 1.83x — RED.
- **Win Rate Trend Column** — closed-Won / (closed-Won + closed-Lost) by FQ for last 8Q. Computable.
- **Forecast Accuracy Column** — OpportunityFieldHistory: ForecastCategory at start-of-Q vs IsWon at end-of-Q. Computable.
- **NRR Metric** — Renewed ACV / opening ACV. Need cohort definition; harder but doable.

### Build #2: Per-Rep Scorecard FlexTable

Lands on **SD Monthly + Sales Ops Q**. Single FlexTable, one row per active rep with quota, columns: attainment / coverage / slip / stale / approvals stuck / win rate. Conditional formatting via SF report color rules.

### Build #3: Slipped Deals widget

**OpportunityFieldHistory query**: opps where CloseDate moved this-Q → next-Q+ in last 30d. **Currently 16 such records right now.** Drill list with Owner, ARR, old/new CloseDate, days-since-slip. Lands on CRO + SD Monthly.

### Build #4: Deal Desk SLA Trend

Median Stage_20_Approval cycle time, fiscal-week granularity, with target line at 5 days. Currently median 7 days, breaching SLA. **Plus aging-in-queue**: pending approvals grouped by 0-2/3-5/6-10/10+ day buckets.

### Build #5: AE Personal Dashboard (new)

Single user-scoped dashboard, 7 widgets. One template, every rep gets their own view. Replaces "what should I work on today" guesswork.

### Build #6: Pipeline Velocity Compound KPI

The "single most comprehensive RevOps metric" per the literature: `(# opps × avg deal value × win rate) / sales cycle length`. Single Metric tile on CRO + Sales Ops Q. When it slows, drill into which of the 4 variables changed.

### Build #7: Forecast Accuracy 8Q Chart

For CRO + Strategic Finance. OpportunityFieldHistory: ForecastCategory = Commit at start-of-Q vs IsWon at end-of-Q. Trended 8Q. <80% = red flag.

---

## What's NOT buildable (yet)

- **NRR true cohort retention** — needs starting-ACV vs renewed-ACV per cohort-Q. Calculable but heavy SOQL; defer.
- **Stage progression rate per rep** — needs OpportunityHistory + per-rep aggregation; doable but secondary.
- **Discount distribution** — depends on Apttus_Approval**Approval_Request**c queries to get discount %; doable but heavy.
- **Marketing source ROI** — needs OpportunityContactRole + Lead-Opp lineage; complex.

---

## Ship order (what I propose to build now)

If you say go, I build in this order — each independently shippable:

1. **CRO Pipeline Coverage Metric** + reds-yellow-green color rules (highest exec impact, ~30 min)
2. **Slipped Deals widget** for CRO + SD Monthly (16 real records right now, ~30 min)
3. **Deal Desk SLA trend + Aging-in-queue** (47% SLA breach today — single biggest ops insight, ~45 min)
4. **Per-Rep Scorecard FlexTable** (the director's tool, ~1 hour)
5. **AE Personal Dashboard** (new, currently zero coverage, ~45 min)
6. **Forecast Accuracy 8Q trend** (the credibility KPI, needs OppFieldHistory rollups, ~1 hour)

Total: ~4 hours of build for 6 truly actionable widgets that use data we never touched.

Sources:

- [The RevOps KPI Dashboard: 12 Metrics That Actually Matter in 2026 (Landbase)](https://www.landbase.com/blog/revops-kpi-dashboard-12-metrics-2026)
- [RevOps KPIs That Actually Move Revenue 2026 (Prospeo)](https://prospeo.io/s/revops-kpis)
- [10 B2B Sales Dashboards for RevOps Teams in 2026 (Coefficient)](https://coefficient.io/sales-operations/sales-dashboards)
- [What Is a Sales Scorecard? (ZoomInfo)](https://pipeline.zoominfo.com/sales/building-a-sales-rep-scorecard)
- [Sales Performance Dashboard (Ambition)](https://ambition.com/d/sales-performance-dashboard/)
- [Modern Sales Rep Scorecard (RevOps Impact)](https://revengine.substack.com/p/the-modern-sales-rep-scorecard)
- [Deal Desk Playbook: Faster Approvals, Less Leakage (Umbrex)](https://umbrex.com/resources/deal-desk-playbook/)
- [What Is a Deal Desk? The 2026 Operator's Guide (Prospeo)](https://prospeo.io/s/deal-desk)
- [Governed Execution for RevOps (DealHub)](https://dealhub.io/resource-center/guides/governed-execution-for-revops/)
- [The Perfect Data Quality Dashboard (Monte Carlo)](https://www.montecarlodata.com/blog-building-data-quality-dashboard/)
