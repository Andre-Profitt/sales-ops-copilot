# Sales Ops Dashboard Redesign — Decision Document

**Author:** Andre Profitt + Claude
**Date:** 2026-04-28
**Org:** simcorp.my.salesforce.com (preprod, `00DD0000000mIhUMAU`)
**Status:** DESIGN ONLY. Builds happen after Andre picks one of the three.

---

## TL;DR

Today's cockpit (`01ZTb00000FxX2YMAV`, RTB `01ZTb00000E1e50MAB`) is honest but superficial — counts and sums of governance hits. Phase 2 probes against the live org reveal **decision-grade signals we currently surface in zero widgets**:

- **Stage 5 deals sit there avg 177 days** (vs Stage 6 only 67 days). Stage 5 is the slip swamp, not Stage 6 — the audit gate is empirically *before* the red-lining gate.
- **Top-25 CFQ deals = $22.4M of $27.7M total CFQ pipeline (81%); 23 of those 25 had no task activity in the last 30 days.** Activity desert at the top of the pipe.
- **Win rate by region spreads 21 points** — NA 26.9% / UK&I 25.6% (low) vs Southwestern Europe 47.4% / Central Europe 44.4% (high). This is bigger than any rep-level coaching signal.
- **Win rate inverts with deal size**: <$100K ARR = 41% win, $100-500K = 31%, $1M+ = 23%. The big deals lose more than they win — and they're where the forecast lives.
- **978 distinct opps slipped CloseDate in the last 90 days** (median +30d, 61 of 200 sampled slipped >90d). The cockpit doesn't show slip velocity at all.
- **Approval cycle p50 = 7d, p90 = 33d.** Healthy median, long tail. Director-grade signal: who has approvals stuck in queue >2 weeks.
- **Process compliance % is unmeasurable from current snapshot** — `Approval_Status__c` resets to "No Approval Necessary" on won Land deals (0 of 18 won Land had `Approved` at query time). Need OFH on `Approval_Status__c` to recover this; OFH currently has 0 entries on this field. **Lens F partially blocked.**

Three dashboards proposed. Recommend building **Sales Director — Quarter Health & Commit Reality** first; it surfaces the Stage 5 slip swamp + top-deal activity desert + concentration risk, and those are what a director or CRO will actually grade us on.

---

# Phase 1 — Role research (the questions each role asks weekly)

Sources: SimCorp Commercial Handbook (`~/.claude/intel/simcorp-sales-process-2026-04.md`), `~/.claude/skills/simcorp-org-wrap/sales-process.md`, Andre's existing Sales Director PI work, RevOps standard practice (Bessemer, Pavilion, SaaStr operator playbooks). WebSearch was not run — leaned on internal SimCorp intel + Andre's memory + my knowledge of the standard literature, since the question patterns are well-established.

## Individual AE / Sales Rep
**Decision they make weekly:** Where to spend the next 5 selling days — which deals to push, which to abandon.
**Top 5 questions:**
1. Which of MY deals are at risk of slipping out of CFQ?
2. Which deals haven't been touched in 14+ days that I committed to my manager?
3. Where am I against quota — and do I have enough pipeline to land it?
4. What governance gates am I missing on my open deals (KYC, Approval, Deal Shaping)?
5. Which renewal accounts in my book are due in the next 90 days with no opp yet?

**Anti-patterns:** Cross-team comparison (manager's job, not the rep's). Forecast-accuracy scorecards (demoralizing without context). Dashboard-level filters (rep wants their own view, defaulted).

## First-line Sales Manager (5–8 reps)
**Decision they make weekly:** Where to spend coaching time and which deals to deal-review.
**Top 5 questions:**
1. Which of my reps is below trend on activity / pipeline / win rate?
2. Which deals on my team need a manager-led inspection this week (Stage 5 stuck, late-stage stale, Stage 4 with no commercial approval submitted)?
3. Are reps converting Stage 3 → 4 at the team's expected rate?
4. Who's at risk of missing CFQ (not enough commit + best-case coverage)?
5. New-business (Land + Expand ARR) vs Renewal (ACV) — separate views, never blended.

**Anti-patterns:** System-wide data quality (Sales Ops job). Process-compliance % rollups (director job). Account-level KYC/legal nuance.

## Sales Director / RVP (regional, multi-manager) — primary cockpit audience
**Decision they make weekly:** Where to deploy executive sponsorship + escalation to clear bottlenecks.
**Top 5 questions:**
1. Is my CFQ commit credible? What's my top-deal concentration, and how many of those are stale or unapproved?
2. Is my pipeline aging? Slip velocity over the last 90 days — am I buying coverage by pushing dates?
3. Where am I stuck at Stage 5 (preferred but no red-lining)? Which managers/accounts?
4. How does this region's win rate by motion (Land / Expand / Renewal) compare to other regions and to baseline (S2→3 = 70%, S3→4 = 47%, S4→Close = 29%)?
5. Single-rep / single-account concentration risk in my region.

**Anti-patterns:** Field-level data quality scoring (Sales Ops, not director). Per-rep coaching detail (manager-layer). Generic "data quality alerts" without dollar tagging.

## CRO / SVP Sales (global)
**Decision they make weekly:** Where to escalate, hire, reorganize, change comp, or invest.
**Top 5 questions:**
1. Global new-business ARR commit vs target — where's the gap by region?
2. Pipeline aging + slip velocity globally — am I real, or is coverage buying time?
3. What's the global win rate by motion + product family? Where do we lose at Stage 5?
4. Top-10 strategic accounts: open ARR + open ACV + KYC posture + last activity.
5. Forecast accuracy by region — which directors call it tight, which loose?

**Anti-patterns:** Long lists of opportunity IDs. Boolean alerts without ARR tagging. Cycle-time histograms without a "so what". Per-rep anything (CROs trust their directors).

## Sales Operations (Andre's role) — meta layer
**Decision they make weekly:** Where to invest data-quality fix-up + which governance gates are degrading.
**Top 5 questions:**
1. Process compliance %: of last 90d closed-won, what % had all governance gates passed before Won?
2. Which alerts are the org regressing on (vs last week, last month)?
3. Governance cycle times: Commercial Approval submit → grant median + p90.
4. Field-level data quality: ARR-blank %, missing CloseDate, Dec-31 placeholder %, inactive owner %.
5. What's the "lying boolean" problem of the week? (Approval_Status, KYC, Deal Shaping have all proved unreliable in different ways.)

**Anti-patterns:** Per-rep selling activity (manager job). Strategic-account concentration (CRO job). Generic ARR rollups (already exists in BOB).

---

# Phase 2 — Deep-data recon (live SF probes)

All numbers are **live counts** from `simcorp.my.salesforce.com` preprod, run 2026-04-28. SOQL templates use the canonical `EXCLUDE_TEST_ARTIFACTS` filter from `scripts/_filters.py`.

## Lens A — Forecast accuracy (OpportunityFieldHistory)

**Available?** PARTIAL.
- `OpportunityFieldHistory` retains `StageName` (4,992 transitions in last 365d) and `CloseDate` (1,276 transitions in 90d).
- `Approval_Status__c` field history: **0 entries** in last 365d. So **"% of Stage-5/6 commits that closed won" is computable via StageName history; "% with full governance gate at time of close" is NOT computable from snapshot or OFH.**

**Sample finding:** Across 184 Stage 5 → Won/Opt-out transitions in the last 365d:
- median time at Stage 5 → won = **24.5 days**
- mean = **41 days**
- p90 = **111 days**
- max = **304 days** (a deal that sat at Preferred for 10 months before signing)

CloseDate slip distribution (200-row sample, last 90d):
- median slip = **+30 days forward**
- 123 of 200 (62%) slipped forward; 77 slipped backward (date pulled in)
- 93 slipped >30d forward; **61 slipped >90d forward** — the long-slip pile is real

**Insight that matters:** CloseDate slips on 978 distinct opps in 90d (49% of all open opps). The cockpit doesn't show slip-velocity. A "deals slipped >30d this month" widget would highlight director-level forecast risk far better than today's "past close date" count.

**SOQL pattern:**
```sql
-- Forecast slip count, last 30d
SELECT COUNT_DISTINCT(OpportunityId) FROM OpportunityFieldHistory
WHERE Field='CloseDate' AND CreatedDate = LAST_N_DAYS:30
-- (then post-process OldValue/NewValue to compute days delta)
```

## Lens B — Cycle time + velocity

**Available?** YES.

**Sample finding:**
- **Cycle time by motion (avg AgeInDays of won deals last 365d):**
  - Land: 492 days (n=18, avg ARR $1.7M)
  - Renewal: 460 days (n=84)
  - Expand: 279 days (n=777, avg ARR $60K)
- **Stage stickiness (current open opps):**
  - Stage 5 (Preferred): avg 177 days at stage (n=40)
  - Stage 6 (Contracting): avg 67 days at stage (n=32)
- **Stage 1/2 → Won median time (sample of 53 deals): 34 days**

**Insight that matters:** **Stage 5 is the slip swamp, not Stage 6.** Stage 5 holding 177-day average vs Stage 6 67-day average flips the standard "deals die in legal" assumption. The bottleneck is *getting to redlining* — not *negotiating redlining*. Andre's existing alerts catch "stale 60+ days at Stage 3+" but don't single out the Stage 5 bottleneck specifically.

**SOQL pattern:**
```sql
SELECT StageName, AVG(LastStageChangeInDays) FROM Opportunity
WHERE IsClosed=false GROUP BY StageName
```

## Lens C — Win rate analysis

**Available?** YES.

**Sample finding:**
- **By deal size band (Land+Expand, last 365d):**

  | Band | Won | Lost | Win % |
  | ---- | --- | ---- | ----- |
  | <$100K | 678 | 981 | **40.9%** |
  | $100-500K | 64 | 142 | **31.1%** |
  | $1M+ | 35 | 117 | **23.0%** |

  Bigger deals lose more. SimCorp's win % is *inversely* correlated with deal size.

- **By region:**

  | Region | Won/Total | Win % |
  | --- | --- | --- |
  | Southwestern Europe | 117/247 | 47.4% |
  | Central Europe | 165/372 | 44.4% |
  | Northern Europe | 216/506 | 42.7% |
  | APAC | 73/185 | 39.5% |
  | MEA | 34/86 | 39.5% |
  | North America | 150/557 | **26.9%** |
  | UK&I | 40/156 | **25.6%** |

  21-point regional spread.

- **By industry (Land+Expand, last 365d, top tiers):**
  Asset Management 36.6% (n=844), Pension 41.6% (n=394), Insurance 32.4% (n=339), Bank 42.0% (n=157). Tighter spread than regions (10 points vs 21).

- **By rep (10+ closed deals, top 15):** Win rate spread is **0% (Chris Wise, 44 deals) → 75% (Lars Krøyer Jensen, 52 deals)**. Maria Sabiniewicz at 95% is test-pollution noise (dummy account); real top performer is Lars at 75%, real bottom is Chris Wise at 0%.

- **By product family:** Field exists (`APTS_RH_Product_Family__c`) but the GROUP BY query returned zero aggregate rows when joined with last-365d filters in this probe — likely needs a different join shape; deferred. Single-row probe returned valid data ("SCD Consulting" etc.), so the field is populated.

**Insight that matters:** Big deals lose. **NA + UK&I are sub-30% win rate while Continental Europe is 44%+** — that's the headline a CRO needs. The cockpit shows none of this.

**SOQL pattern:**
```sql
-- Win rate by region (last 365d Land+Expand)
SELECT Account.Region__c, COUNT(Id) FROM Opportunity
WHERE IsClosed=true AND CloseDate=LAST_N_DAYS:365 AND Type IN ('Land','Expand')
GROUP BY Account.Region__c
-- Run twice (won and total), divide.
```

## Lens D — Concentration + risk

**Available?** YES.

**Sample finding:**
- **Top-3 of top-25 CFQ deals = $5.48M; top-25 total = $22.4M; CFQ total = $27.7M.** Top-3 share of top-25 = 24.5%. Top-25 share of CFQ = 81%. Single-deal-dependency risk is concentrated.
- **Single-rep concentration (NA region):** Barbara MacNeil owns $34M of NA's $139.7M open pipeline = **24.3% of NA pipeline owned by one rep**. Top-5 NA reps = $89M = 63.6% of NA pipeline.
- **Top accounts by open ARR:**

  | Account | Open opps | Open ARR |
  | ------- | --------- | -------- |
  | UBS Global AM (UK) | 17 | $24.2M |
  | Fidelity International | 2 | $21.4M |
  | Union Asset Mgmt | 3 | $17.0M |
  | Wellington Mgmt | 1 | $11.9M |
  | HOOPP | 9 | $7.5M |

  These are the "if any of these go cold, the quarter slips" accounts.

**Insight that matters:** Director-level dashboard MUST show "top-3 deal concentration in CFQ commit" and "single-rep dependency in region". Current cockpit shows neither. Account-level pivot of flagged opps already exists (`pull_account_concentration` in alerts.py) — pull it forward.

**SOQL pattern:**
```sql
SELECT Owner.Name, COUNT(Id), SUM(APTS_Opportunity_ARR__c)
FROM Opportunity WHERE IsClosed=false AND Type IN ('Land','Expand')
AND Account.Region__c='<region>'
GROUP BY Owner.Name ORDER BY SUM(APTS_Opportunity_ARR__c) DESC
```

## Lens E — Activity correlation (Task / Event)

**Available?** YES (Task is rich; Event is sparse).
- 10,544 Task rows last 30d globally; 201 Event rows. Task is the canonical activity object here.

**Sample finding:**
- **Of 1,660 open Land+Expand opps, only 60 (3.6%) had any Task in the last 30 days.** Massive activity gap.
- **Of top-25 CFQ deals (carrying $22.4M of $27.7M total CFQ ARR), 23 had no activity in 30+ days** (or never had any). The deals the org is committing to are the deals nobody's working.
- Stage 5 specifically: 1 task across 40 open Stage-5 opps in 30d. Activity desert.

**Insight that matters:** **Activity-coverage on top-25 CFQ deals is the single most damning operational signal in the org.** "23 of top-25 CFQ deals have no recent activity, carrying $20M+ of pipeline" is a CRO-level talking point. Today's `stale_activity` alert flags Stage 3+ generally; it should ALSO surface as a focused widget on CFQ-top-25.

**SOQL pattern:**
```sql
-- Top-25 CFQ with last activity > 30d
SELECT Id, Name, APTS_Opportunity_ARR__c, LastActivityInDays, Owner.Name
FROM Opportunity
WHERE IsClosed=false AND Type IN ('Land','Expand') AND CloseDate = THIS_QUARTER
ORDER BY APTS_Opportunity_ARR__c DESC NULLS LAST LIMIT 25
-- Filter LastActivityInDays > 30 OR null in post-process
```

## Lens F — Process compliance

**Available?** PARTIAL — blocked on what matters most.

**Sample finding:**
- **0 of 18 closed-won Land deals (last 365d) currently show `Approval_Status__c='Approved'`.** All show "No Approval Necessary" — same lying-picklist shape as the boolean fields. Field gets reset post-Won.
- **OFH for `Approval_Status__c`: 0 entries in the last 365d**, so we cannot recover "was the deal Approved at the moment it transitioned to Stage 8". Process compliance % is **not computable** today.
- **Commercial Approval cycle time IS computable** from `Submit_for_Stage_20_Review_Date__c` → `Stage_20_Approval_Date__c` (114 OFH entries on the date field in 365d, 50-row sample):
  - median = **7 days**
  - mean = **13 days**
  - p90 = **33 days**, max 111 days
  - 22 of 50 took >7d; 5 of 50 took >30d.
- **KYC** cycle time is computable in principle (account-level field exists) but not on Opportunity FieldHistory.

**Insight that matters:** Today's cockpit should pivot from "Commercial Approval gap = 0" (now correctly zero post-fix) to "Commercial Approval cycle time p50/p90". The interesting signal isn't "are gates being missed" (mostly no), it's "are gates being granted on time" (sometimes no — 5 of 50 took over a month). And we should add `Approval_Status__c` to FieldHistory tracking via SF setup so process-compliance % becomes recoverable from now forward — that's a one-click admin action, but it's not in scope for this redesign.

**SOQL pattern:**
```sql
-- Commercial Approval cycle time, last 365d
SELECT Submit_for_Stage_20_Review_Date__c, Stage_20_Approval_Date__c
FROM Opportunity
WHERE Stage_20_Approval_Date__c != null
  AND Submit_for_Stage_20_Review_Date__c != null
  AND Stage_20_Approval_Date__c = LAST_N_DAYS:365
-- post-process: median, p90 of (Stage_20_Approval_Date - Submit_Date)
```

---

# Phase 3 — Three role-tailored dashboards

Each dashboard scoped to 12-15 widgets (Sales Ops one allowed up to 19 to replace the existing cockpit). Each widget answers a specific question from Phase 1.

## 1. Sales Director — Quarter Health & Commit Reality

**Audience:** Regional Sales Director / RVP (the 9 MD-1 directors per `project_sales_director_md1_presets.md`).
**Frequency consumed:** Weekly + before each pipeline review.
**Filter at dashboard level:** Region (defaults to viewer's region per `Account.Region__c` mapping).

**14 widgets:**

1. **Commit Reality Tile** — KPI tile — answers "Is my CFQ commit credible?"
   *Source:* `SUM(APTS_Opportunity_ARR__c) WHERE CloseDate=THIS_QUARTER AND Probability >= 50` AND `IsClosed=false` (Land+Expand split shown). Compares to weighted forecast from `stage_probs.py` empirical probabilities.
2. **Top-3 CFQ Deal Concentration** — Bar — answers "How dependent am I on top deals?"
   *Source:* Top-3 ARR in region as % of region's CFQ commit. Threshold: >40% = red, 25-40% = amber, <25% = green.
3. **Top-25 CFQ Deals — Last Activity** — FlexTable — answers "Which big deals are the team not working?"
   *Source:* Top-25 CFQ deals, columns: Account · Owner · ARR · Stage · LastActivityInDays · KYC status. Highlight rows with LastActivity > 30d (today: 23/25 region-agnostic).
4. **Stage 5 Slip Swamp** — FlexTable — answers "Where am I stuck at Preferred?"
   *Source:* Stage 5 deals where `LastStageChangeInDays > 90`, ordered by ARR desc. Today: 40 region-agnostic, avg 177d at stage.
5. **CloseDate Slip Velocity (90d)** — Time series chart — answers "Is my pipeline aging or am I buying coverage?"
   *Source:* OpportunityFieldHistory CloseDate transitions, last 90d, summed days slipped per week. Today: median +30d slip, 61 of 200 sampled slipped >90d.
6. **Slipped >30d Out of CFQ This Month** — KPI tile + drilldown — answers "What did I lose from my commit?"
   *Source:* OFH CloseDate transitions where new_date > old_date by >30d AND old_date IN current quarter.
7. **Win Rate by Motion vs Baseline** — Bar — answers "How does my region compare to baseline?"
   *Source:* Win rate Land vs Expand vs Renewal, last 365d. Compare to FY26 baselines (S2→3=70, S3→4=47, S4→Close=29).
8. **Single-Rep Concentration** — Bar — answers "Am I dependent on one rep?"
   *Source:* Top-5 reps by open Land+Expand ARR in region. Today: NA shows Barbara MacNeil = 24% of region pipeline.
9. **Late-Stage Stale (Stage 3+, >60d no activity)** — KPI tile — answers "What's gone cold?"
   *Source:* Existing `stale_activity` alert restricted to region.
10. **Pipeline Aging Cliff** — Histogram — answers "How much zombie pipeline am I carrying?"
    *Source:* Open Land+Expand by `AgeInDays` bucket (0-90, 90-180, 180-365, >365). Today's >365 cohort = 700 opps / $283M.
11. **Top-5 Accounts by Open ARR** — FlexTable — answers "Which strategic accounts carry the quarter?"
    *Source:* GROUP BY Account, columns: Account · #opps · open ARR · last activity · KYC status.
12. **Renewal ACV Coming Due (next 180d)** — KPI tile + table — answers "Where's my renewal revenue at risk?"
    *Source:* Renewal Type opps with CloseDate ≤ +180d; uses `APTS_Renewal_ACV__c` (NEVER blended with ARR).
13. **Manager Roll-up — Pipeline Coverage** — FlexTable — answers "Which of my managers are below 3.5x coverage?"
    *Source:* GROUP BY Owner.Manager.Name, sum open ARR ÷ remaining quarter quota. Coverage <3.5x = red.
14. **Approval Cycle p50/p90** — KPI tile — answers "Are gates being granted on time?"
    *Source:* Median + p90 of (Stage_20_Approval_Date - Submit_for_Stage_20_Review_Date), last 90d. Today: 7d/33d.

**Why it's better than what we have today:** Today's cockpit shows 13 governance alerts. This shows what a director ACTUALLY decides on. The "top-25 CFQ + last activity" widget alone would change every weekly pipeline review (23 of 25 untouched is a fire). "Stage 5 slip swamp" replaces the generic "stale 60d" with the empirically-derived bottleneck stage. "CloseDate slip velocity" adds a slip-trend axis the cockpit completely lacks.

---

## 2. Sales Manager — Team Coaching & Risk

**Audience:** First-line Sales Manager (5–8 reps).
**Frequency consumed:** Daily + before 1:1s.
**Filter at dashboard level:** Manager (defaults to viewer); secondary filter Rep (drill-through to single rep).

**13 widgets:**

1. **Team Pipeline Coverage** — KPI tile — answers "Do we have enough pipe to land CFQ?"
   *Source:* Sum of team's open Land+Expand ARR by stage (weighted by empirical probabilities) ÷ remaining quota. Target: 3.5x.
2. **Per-Rep Win Rate (last 365d)** — Bar — answers "Who's converting, who isn't?"
   *Source:* Win rate by Owner.Name within manager's team, last 365d. Lars Krøyer Jensen 75% / Chris Wise 0% pattern.
3. **Per-Rep Pipeline ARR + Stage Mix** — Stacked bar — answers "Who has thin pipe, who has only-late-stage?"
   *Source:* GROUP BY Owner, sum ARR by Stage. A rep with all Stage 1/2 has a coverage problem; all Stage 5/6 has a creation problem.
4. **Per-Rep Activity Heatmap (last 30d)** — Matrix table — answers "Who's not working their book?"
   *Source:* Tasks per rep last 30d ÷ open opps. Today's org-wide average: 1 task per 30 open opps = bad.
5. **Deals to Inspect This Week** — FlexTable — answers "Which deals need a manager-led review?"
   *Source:* Union of (Stage 5 stuck >90d) OR (Stage 4 with no Submit_for_Stage_20_Review) OR (CloseDate slipped twice in 60d) within team.
6. **CFQ At-Risk Commits** — FlexTable — answers "What's about to slip out of my CFQ?"
   *Source:* CFQ Land+Expand within team where Probability < 50% OR (Stage 3+ AND LastActivityInDays > 30) OR (CloseDate < TODAY).
7. **Renewal Coverage by Rep (next 180d)** — Bar — answers "Who has a renewal cliff coming?"
   *Source:* Renewal opps with CloseDate ≤ +180d, `APTS_Renewal_ACV__c` GROUP BY Owner.
8. **New-Logo (Land) Activity per Rep** — KPI tile per rep — answers "Who's hunting?"
   *Source:* Count of Land opps created last 90d per rep. Land cycle is 492 days — early-stage Land is leading indicator of FY+1 Land closes.
9. **Stage Conversion Rates — Team vs Baseline** — Bar — answers "Where does my team leak?"
   *Source:* S2→3, S3→4, S4→Close transition rates from OFH for team's deals, vs baselines (70/47/29).
10. **Governance Gates Open (Land deals)** — FlexTable — answers "Who has compliance debt I need to chase?"
    *Source:* `Approval_Status__c IN ('Needs Approval','Awaiting Approval')` Land deals within team.
11. **CloseDate Slipped 3+ Times in 90d** — FlexTable — answers "Which deals is the rep just date-pushing?"
    *Source:* OFH CloseDate transitions per opp, last 90d, having COUNT >= 3.
12. **No Activity Ever (Stage 3+)** — FlexTable — answers "Which deals are pure data-quality fiction?"
    *Source:* Existing `no_activity_ever` alert filtered to team.
13. **Quote-vs-ARR Drift Watch** — KPI tile — answers "Are reps pricing accurately?"
    *Source:* Open opps where SyncedQuote.GrandTotal != APTS_Opportunity_ARR__c × pricing-period multiplier (rough heuristic; refine post-build).

**Why it's better than what we have today:** RTB dashboard is FlexTable-heavy and rep-agnostic. This is rep-stratified, drill-through, coaching-oriented. "Per-rep win rate vs team baseline" + "deals to inspect this week" gives a manager an actual 1:1 agenda. None of today's 17 RTB widgets answer "which rep is not converting Stage 3 → 4 like the rest of the team?" — this dashboard does.

---

## 3. Sales Operations — System Health & Compliance (REPLACES current cockpit)

**Audience:** Andre Profitt (Global Senior Sales Ops Consultant) + future Sales Ops team.
**Frequency consumed:** Daily; weekly trend review on Mondays.
**Filter at dashboard level:** Region (optional), Severity (optional).

**16 widgets:**

1. **Active Alerts Summary** — KPI tile — count of currently-active alert categories + total ARR impact.
   *Source:* `pull_all_alerts()` from `scripts/alerts.py`. Today: 7 active.
2. **Alert Trend (last 30d)** — Time series — answers "Are we regressing or improving?"
   *Source:* `state/snapshots/*.json` (already produced by `snapshot_diff.py`). New widget — currently unused in dashboards.
3. **Alert ARR by Severity** — Stacked bar — Critical / Important / Info breakdown.
   *Source:* Same alert pull, GROUP BY severity.
4. **Owner Concentration of Flagged ARR** — FlexTable — top 10 owners by flagged ARR.
   *Source:* Existing `pull_owner_concentration()`. Today: Adam Hatcliff ~30% of alert ARR.
5. **Account Concentration of Flagged ARR** — FlexTable — top 15 accounts.
   *Source:* Existing `pull_account_concentration()`.
6. **Process Compliance Watch — Approval Cycle** — KPI tile — answers "Are gates being granted on time?"
   *Source:* Median + p90 of (Stage_20_Approval_Date - Submit_for_Stage_20_Review_Date), trailing 90d. Today: 7d/33d.
7. **Approvals Stuck in Queue >14d** — FlexTable — answers "Who's waiting on a gate?"
   *Source:* Open opps with Submit_for_Stage_20_Review_Date < LAST_N_DAYS:14 AND Stage_20_Approval_Date = null AND Approval_Status__c IN ('Needs Approval','Awaiting Approval').
8. **Lying-Boolean Watch** — FlexTable — answers "Which fields look reliable but aren't?"
   *Source:* For each tracked boolean (Stage_20_Approval, Deal_Shaping_Approved, Submit_for_Stage_20_Review, KYC_Approval_Message), show: count of true values, count of true values cross-referenced with picklist truth, and discrepancy %. Empirical tracker for the audit pattern Andre keeps finding.
9. **Field Completeness Scorecard** — Bar — answers "Where's the data debt?"
   *Source:* Per Andre's CRMA targets: Opportunity 74%, Account 71%, Renewal 61%, Quote 82%. Compute live against current snapshot.
10. **Ack'd Alerts (active suppressions)** — FlexTable — answers "What did I tell the system to ignore?"
    *Source:* `state/acknowledged.json` parsed.
11. **Test-Pollution Audit** — KPI tile + drilldown — answers "Are filters still catching pollution?"
    *Source:* Top-50 ARR Land opps regex-matched against expanded test patterns; show any new candidates not in `_filters.py`. Per Direction J in HANDOFF.
12. **Inactive-Owner Drift** — FlexTable — open opps with `Owner.IsActive=false`, GROUP BY Owner. (Existing alert, surfaced as widget.)
13. **Forecast vs Empirical Probabilities** — Comparison bar — answers "Are reps over- or under-calling?"
    *Source:* For each stage: avg `Probability` field set by reps vs empirical p(Won|stage) from `state/stage_probabilities.json`. Today empirical: 1→4.8%, 2→11.7%, 3→20.3%, 4→39.5%, 5→66.5%, 6→87.2%.
14. **Stage 5 Health (the slip-swamp tracker)** — FlexTable — answers "Where's the bottleneck?"
    *Source:* Stage 5 open with LastStageChangeInDays > 90, with rep-set Probability shown. Currently 40 deals avg 177d.
15. **Snapshot Δ — Last 7d** — Diff table — answers "What changed in the org this week?"
    *Source:* `state/snapshots/*.json` last 7 vs today. ARR / opp-count deltas per stage.
16. **Approval-Status Field-History Coverage** — KPI tile — answers "Can we measure compliance going forward?"
    *Source:* `COUNT(Id) FROM OpportunityFieldHistory WHERE Field='Approval_Status__c'` vs total opp transitions. Today: 0 entries — meaning the field isn't being tracked. Surfaces a fix-up action: enable Field History Tracking on this field in SF Setup.

**Why it's better than what we have today:** Today's cockpit is 19 widgets of "current state of alerts." This is **alerts + trend + lying-boolean watch + process-cycle health** — a four-axis view. The "Lying-Boolean Watch" widget is the meta-level capture of what Andre keeps finding manually (boolean vs picklist discrepancies); it institutionalizes the audit pattern. The "Approval-Status Field-History Coverage" widget surfaces the actionable fix to make Lens F computable in the future.

---

# Recommendation

**Build #1 (Sales Director — Quarter Health & Commit Reality) first.** Reasons:

1. **Highest-impact role.** A director consumes this in front of their manager + ahead of the CRO. Decision-grade signals (top-25 activity desert, Stage 5 slip swamp, single-rep concentration) translate directly to forwarded escalations.
2. **Most net-new signal vs today's cockpit.** Manager dashboard overlaps RTB substantially; Sales Ops dashboard is a cockpit refresh. Director dashboard is a green-field build.
3. **Strongest portfolio evidence.** A "decision-grade director cockpit with empirical Stage 5 bottleneck call-out, slip velocity from FieldHistory, and top-25 activity desert" reads as senior Sales Ops / RevOps work in a way that "alert audit + governance compliance" doesn't.
4. **Wires up infra we already own.** Reuses `alerts.py` (concentration), `stage_probs.py` (empirical weighting), `_directors.py` (region scope map), `snapshot_diff.py` (trend), `forecast_backtest.py` (conversion baselines). Approximately 40% reuse.

Build order proposal: **Director (1) → Manager (2) → Sales Ops cockpit refresh (3)**. The Sales Ops refresh is the lowest priority because today's cockpit already does the job adequately for the meta-layer; the director and manager dashboards are where the user-facing impact lives.

---

# Appendix — what was NOT computable

- **Process compliance %** (deals won with all gates passed): `Approval_Status__c` Field History tracking is not enabled on the org. One-click Setup change required to start collecting; once in place, lookback computable from that date forward.
- **WebSearch-driven role research**: deferred — leaned on internal SimCorp intel + standard literature in my training. If Andre wants industry citations (Bessemer state-of-cloud, SaaStr ops blog), worth a follow-up pass.
- **Win rate by product family**: aggregate query returned 0 rows when joined with the 365d / Land+Expand filter shape used here; needs query refactor (post-process aggregation in Python). Field is populated. Out of scope for this design pass.
- **Email-to-decision-maker volume**: requires `EmailMessage` + `OpportunityContactRole` join; not probed. Plausible but needs a Phase 2.5 to confirm.
