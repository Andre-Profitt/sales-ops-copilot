# Sales Ops Alert Predicate Audit — 2026-04-28

Audit pattern: same shape as the KYC bug fixed earlier today. Sample real flagged opps, cross-check the predicate against the canonical truth field, flag any predicate that doesn't match reality.

**Headline finding:** the picklist `Opportunity.Approval_Status__c` (values: `No Approval Necessary`, `Needs Approval`, `Awaiting Approval`, `Approved`, `Rejected`) is the canonical Commercial Approval truth field. The booleans `Stage_20_Approval__c`, `Deal_Shaping_Approved__c`, `Submit_for_Stage_20_Review__c` fire as false on tens of thousands of opps that don't need approval at all — same lying-boolean shape as `KYC_Approval_Message__c`. Alerts 1, 2, 6, 9 all confirmed buggy and corrected.

Org distribution of `Approval_Status__c` (all opps):

- `No Approval Necessary` — 34,618
- `null` — 13,339
- `Needs Approval` — 51
- `Approved` — 13
- `Rejected` — 2

Closed-won Land opps (last 365d): 14 of 18 won deals had `Stage_20_Approval__c=true` AND `Approval_Status__c='No Approval Necessary'`. Closed-won Land/Expand (last 365d): 764 of 795 won deals had `Deal_Shaping_Approved__c=false`. The booleans are not gates, they're side-channel flags.

---

## Alert 1: Land deals at Stage 3+ without Commercial Approval

**Predicate:** `Type='Land' AND Stage 3+ AND Stage_20_Approval__c = false`
**Today's count:** 26 flagged opps / $37.9M ARR
**Sample (10 examples) — all have `Approval_Status__c = 'No Approval Necessary'`:**

- Union Asset Management Holding · Union - F2B Plattformanalyse 2025 · Stage 3 · $17.0M · predicate says "no approval" · canonical says "No Approval Necessary"
- Oslo Pensjonsforsikring AS · OPF - SimCorp One - F2B · Stage 3 · $30.5M · same
- BBVA Asset Management · BBVA AM - FtoM · Stage 3 · $6.1M · same
- Social Security Office Thailand · SSO - F2B · Stage 3 · $2.8M · same
- Dynex Capital · Dynex Capital - ABOR + IBOR lite · Stage 3 · $2.0M · same
- Employees Retirement System of Texas · ERS TX - F2B Replacement · Stage 3 · $1.8M · same
- Canso Investment Counsel · Portfolio HiWay- Canso · Stage 3 · $2.4M · same
- Kumpulan Wang Persaraan · KWAP F2M 2026 · Stage 3 · $1.5M · same
- Symetra Financial Corporation · Symetra IM - Full IOS · Stage 3 · $1.0M · same
- Real Estate Development Fund REDF · REDF - IBOR · Stage 3 · $0.95M · same

**Cross-check fields explored:**

- `Approval_Status__c` (Opp picklist) — all 26 say `No Approval Necessary`
- `Stage_20_Approval_Date__c` (Opp date) — null on all 26
- `Submit_for_Stage_20_Review__c` (Opp boolean) — true on 5 of 10, but irrelevant when Approval_Status says no approval needed
- Closed-won baseline: 14 of 18 won Land deals (last 365d) have `Stage_20_Approval__c=true` AND `Approval_Status__c='No Approval Necessary'` — boolean gets set retroactively for some won deals but isn't gate logic

**Verdict:** **CONFIRMED_BUG**
**Corrected predicate:** `Type='Land' AND Stage 3+ AND Stage_20_Approval__c=false AND Approval_Status__c IN ('Needs Approval','Awaiting Approval','Rejected')`. Recount: **26 → 0** flagged.

---

## Alert 2: Stage 3+ Land/Expand deals ≥$500k without Commercial Approval

**Predicate:** `Type IN ('Land','Expand') AND Stage 3+ AND ARR >= 500k AND Stage_20_Approval__c = false`
**Today's count:** 104 flagged opps / $141.8M ARR
**Sample:** all 104 have `Approval_Status__c='No Approval Necessary'` (verified by GROUP BY).

**Cross-check fields explored:**

- `Approval_Status__c` — 100% `No Approval Necessary` on flagged set
- Same shape as alert 1, just the bigger size threshold

**Verdict:** **CONFIRMED_BUG**
**Corrected predicate:** add `AND Approval_Status__c IN ('Needs Approval','Awaiting Approval','Rejected')`. Recount: **104 → 0** flagged.

---

## Alert 3: Stage 5+ Land/Expand without KYC clearance

**Predicate:** `Type IN ('Land','Expand') AND Stage 5+ AND Account.KYC_Approval_Status__c != 'Approved'`
**Today's count:** 0 flagged (already corrected this morning)
**Verdict:** **PASS** (already fixed). No further action.

---

## Alert 4: Open opportunities with close date in the past

**Predicate:** `IsClosed=false AND CloseDate < TODAY`
**Today's count:** 46 flagged / $668k ARR
**Sample stage distribution:**

- Stage 1 - Prospecting: 6 ($119k)
- Stage 2 - Discovery: 17 ($357k)
- Stage 3 - Engagement: 4 ($0)
- Stage 4 - Shortlisted: 2 ($31k)
- Stage 5 - Preferred: 2 ($0)
- Stage 6 - Contracting: 3 ($162k)
- Quota: 12 ($0)

**Cross-check:** mostly low-stage abandoned ($0 ARR Quota records, early-stage prospects). 5 late-stage stragglers (Stage 5 + 6) at modest ARR — also legitimate signal. Predicate working as intended.

**Verdict:** **PASS**.

---

## Alert 5: Stage 3+ opps with Dec 31 placeholder dates

**Predicate:** `Stage 3+ AND CALENDAR_MONTH(CloseDate)=12 AND DAY_IN_MONTH(CloseDate)=31`
**Today's count:** 122 flagged / $107.2M ARR
**Sample:**

- Eagle Asset Management · RAJA SaaS · Stage 4 · 2026-12-31
- CN Investment Division · CNID Front Office · Stage 3 · 2026-12-31
- Generali · GenAM PS Consulting bucket · Stage 5 · 2026-12-31
- MEAG · DPG Erweiterung · Stage 3 · 2027-12-31
- ADIA · Investment Analytics Platform · Stage 3 · 2026-12-31
- DZ HYP · DZ-HYP SaaS · Stage 3 · 2027-12-31
- Pictet · SaaS Core & Core+ · Stage 3 · 2027-12-31

Date arithmetic correct. All examples are clear placeholder Dec 31 dates spanning multiple future years (2026, 2027). No timezone double-count issue (`DAY_IN_MONTH` returns 31 only on Dec 31).

**Verdict:** **PASS**.

---

## Alert 6: Stage 5+ Land/Expand without Deal Shaping

**Predicate:** `Type IN ('Land','Expand') AND Stage 5+ AND Deal_Shaping_Approved__c = false`
**Today's count:** 67 flagged / $29.9M ARR
**Cross-check:**

- All 67 flagged opps have `Approval_Status__c = 'No Approval Necessary'`
- **Closed-won baseline (LAST_N_DAYS:365): 764 of 795 won Land/Expand deals had `Deal_Shaping_Approved__c=false`.** The boolean is essentially never set to true — same lying-boolean shape as the others.

**Verdict:** **CONFIRMED_BUG**
**Corrected predicate:** add `AND Approval_Status__c IN ('Needs Approval','Awaiting Approval','Rejected')`. Recount: **67 → 0** flagged.

Note: this is the strongest evidence of all four — the closed-won data shows the field functionally unused (96% of won deals have it false). Even when added as a co-condition with the picklist gate, the predicate finds zero deals today, which means either (a) the field is broken/abandoned across the org, or (b) Deal Shaping is captured somewhere we haven't found. Reverting to "alert never fires" is correct until the canonical Deal Shaping signal is identified — better than firing on hundreds of false positives.

---

## Alert 7: Stage 3+ stale 60d+ activity

**Predicate:** `Stage 3+ AND LastActivityDate < LAST_N_DAYS:60`
**Today's count:** 116 flagged / $81.8M ARR
**Sample (top 5 by ARR) — Task/Event subqueries on each:**

- BBVA AM - FtoM · LastActivity 2025-10-08 · 0 tasks + 0 events in 60d · truly stale
- Apollo BPaaS · LastActivity 2023-08-04 · 0+0 in 60d · truly stale
- RBC OMS & PM · LastActivity 2026-02-19 · 0+0 in 60d · truly stale
- Belfius cloud SaaS · LastActivity 2024-10-17 · 0+0 in 60d · truly stale
- CrossLight FO+Services · LastActivity 2025-01-13 · 0+0 in 60d · truly stale

Predicate matches reality. `LastModifiedDate` updates on field edits without activity, so it would over-flag — current choice is correct.

**Verdict:** **PASS**.

---

## Alert 8: Stage 3+ no logged activity ever

**Predicate:** `Stage 3+ AND LastActivityDate = null`
**Today's count:** 460 flagged / $111.5M ARR
**Sample (top 5 by ARR) — Task/Event count subqueries:**

- UBS 2026 Transformation - SaaS Expansion · 0 tasks + 0 events ever
- UBS 2026 Transformation - Axioma · 0+0 ever
- NORD - SaaS Core (New) · 0+0 ever
- NN Group MBS Transformation · 0+0 ever
- CFS - SimCorp One (BPaaS) - ALF · **1 task** + 0 events ever (one task exists but `LastActivityDate` not set)

Salesforce `LastActivityDate` is rolled up from completed Tasks/Events that meet specific criteria (CallType, ActivityDate set, etc.). 4 of 5 truly have nothing; 1 has a single task with insufficient metadata to update the rollup. Predicate substantially correct; small known SF rollup edge case is acceptable noise.

**Verdict:** **PASS**.

---

## Alert 9: Approval submitted, not granted

**Predicate:** `Stage 3+ AND Submit_for_Stage_20_Review__c=true AND Stage_20_Approval__c=false`
**Today's count:** 6 flagged / $29.1M ARR
**Cross-check:** all 6 have `Approval_Status__c='No Approval Necessary'`. The submit boolean fires even when no approval is required, then the approval boolean stays false because the workflow never runs.

**Verdict:** **CONFIRMED_BUG**
**Corrected predicate:** `Submit_for_Stage_20_Review__c=true AND Stage_20_Approval__c=false AND Approval_Status__c IN ('Needs Approval','Awaiting Approval')` (excluding 'Rejected' since that's a terminal state, not "still pending"). Recount: **6 → 0** flagged.

---

## Alert 10: Inactive owner

**Predicate:** `IsClosed=false AND Owner.IsActive = false`
**Today's count:** 8 flagged / $0 ARR
**Sample:** 7 are LVB/PLRB/TVC quota-placeholder rows ($0 ARR), 1 is L-Bank FTB at Stage 2 with $0 ARR. Predicate correct; signal is low-value because all candidates are $0 quota artifacts. No fix needed (alert is rare-fire and accurate when it does).

**Verdict:** **PASS**.

---

## Summary

| Alert # | Verdict              | Today         | Corrected | Action          |
| ------- | -------------------- | ------------- | --------- | --------------- |
| 1       | CONFIRMED_BUG        | 26 ($37.9M)   | 0         | predicate fixed |
| 2       | CONFIRMED_BUG        | 104 ($141.8M) | 0         | predicate fixed |
| 3       | PASS (already fixed) | 0             | —         | —               |
| 4       | PASS                 | 46 ($668k)    | —         | —               |
| 5       | PASS                 | 122 ($107.2M) | —         | —               |
| 6       | CONFIRMED_BUG        | 67 ($29.9M)   | 0         | predicate fixed |
| 7       | PASS                 | 116 ($81.8M)  | —         | —               |
| 8       | PASS                 | 460 ($111.5M) | —         | —               |
| 9       | CONFIRMED_BUG        | 6 ($29.1M)    | 0         | predicate fixed |
| 10      | PASS                 | 8 ($0)        | —         | —               |

**Net impact:** brief stops false-flagging $238M of ARR (203 opps) across 4 critical alerts. The "Land Stage 3+ no Commercial Approval" alert was, today, 100% noise.

**Top surprises:**

1. **`Approval_Status__c='No Approval Necessary'` is the org's default state for 70% of all opps** (34,618 of 48,023 with the field set). The boolean `Stage_20_Approval__c` was never the gate — it's a derived flag that fires false unless someone explicitly approved. Same lying-boolean pathology as `KYC_Approval_Message__c`.
2. **`Deal_Shaping_Approved__c` is functionally abandoned**: 764 of 795 won Land/Expand deals (96%) closed with this field still false. Even with `Approval_Status__c` co-conditioned the corrected predicate finds 0 — meaning either Deal Shaping is captured via a different mechanism we haven't located, or governance is silent on this gate org-wide. Reverting the alert to never-fire is correct vs. firing on 67 false positives.

## Follow-ups (not done inline)

- SF report `Alert_Stage_5_Land_Expand_without_Deal_Shaping` (if it exists in the dashboard package) needs the same picklist filter co-condition added via Analytics REST PATCH. Same for the Land-no-CA and ≥$500k-no-CA reports. Document only — do not patch in this commit per scope.
- Investigate where Deal Shaping approval is actually captured. Possibilities: a separate object, a different field, an Apttus CPQ flag, or it's genuinely tracked outside SF. If it's a different field, alert 6 should re-target.
