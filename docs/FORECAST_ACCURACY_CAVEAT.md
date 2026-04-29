# Forecast Accuracy 8Q — what the 99.8% number actually means

**Last updated:** 2026-04-29
**Report:** `00OTb000008ngO5MAI` — `FA · Forecast Accuracy 8Q`
**Live in:** sf-audit dashboard `Forecast Accuracy & Pacing` (01ZTb00000FxYcvMAF) + the daily brief

## TL;DR

The headline "99.8% forecast accuracy" looks great. **It is misleading as a forecast-trust metric.**

What it actually measures: for closed-won deals, how close is the `APTS_Forecast_ARR__c` field to the `APTS_Opportunity_ARR__c` field on the same row, after close.

What we WISH it measured: of the deals that were marked `ForecastCategoryName = Commit` at the start of a fiscal quarter, what % were `IsWon = true` by the end of that fiscal quarter.

These are different metrics. The first is trivially high in a SaaS-like sales org because ARR is contractually fixed at signing — the forecast field gets updated to match actual ARR right before close. The second is the real "can we trust the forecast" measure, and it requires `OpportunityFieldHistory` snapshots that this org doesn't yet have wired into reports.

## Why this matters

The brief, the FA dashboard, and any director who looks at this metric will see "99.8% forecast accuracy" and assume the forecast is reliable. **It is not reliable in the sense that matters operationally** — the question "if a rep says they'll commit deal X this quarter, will it actually close this quarter" is unanswered by this metric.

Combined with the gameable-win-rate caveat (deals indefinitely pushed never enter the won/lost denominator) and the cycle-length collapse (only short-cycle deals reach Won), the survivor-bias picture is:

- Win rate trend: 52% → 27.8% over the last 6 quarters (real)
- Cycle length: 694d → 143d over the same window (survivor bias — long-cycle deals don't reach Won)
- Forecast accuracy: 99.8% (artifact — measures post-close-already-decided values)
- Zombie ARR: 33% of open book is >2yr old (the real signal — these are losses-in-pipeline that never enter forecast accuracy because they never close)

The only one of those four numbers that is gameing-resistant is the zombie ratio. The others should be read with this caveat in mind.

## What real forecast accuracy looks like

The CRO / RevOps literature standard:

```
forecast_accuracy_q = (
    count(opps WHERE forecast_category_at_start_of_q = 'Commit' AND is_won_at_end_of_q = TRUE)
    /
    count(opps WHERE forecast_category_at_start_of_q = 'Commit')
)
```

Implementation requirements:

1. **`OpportunityFieldHistory` field-history tracking enabled on `ForecastCategoryName`.** Per the sf-audit findings shared in `docs/AGENT_COORDINATION.md` (Findings shared across tracks), `Approval_Status__c` already has Field History Tracking OFF; we'd need to verify the same for ForecastCategoryName and likely turn it on.
2. **Snapshot infra**: take a snapshot of every open opp's ForecastCategoryName at the start of each fiscal quarter (e.g., 2026-04-01 00:00). Store in a custom object or external store.
3. **Resolution check**: at end of fiscal quarter (e.g., 2026-06-30), check IsWon for each snapshot.
4. **Per-rep cut**: same calc grouped by Owner.
5. **Trend over 8Q**: store the historical accuracy by FQ, render as a line/bar chart.

**Effort:** ~half-day to ship the snapshot infra + alert/widget on the resulting metric. Currently parked as a Phase-2 build (per the standard-metrics audit and the AP-RW Phase 1 plan, which reuses similar OppFieldHistory infra).

## Workarounds in the meantime

Until real forecast accuracy is computable, the brief and dashboards offer these proxies:

| Proxy                                            | What it captures                                                                                 | Where it lives       |
| ------------------------------------------------ | ------------------------------------------------------------------------------------------------ | -------------------- |
| **Slippage by Push Count** (199 opps, EUR 17.9M) | Direct measure of forecast volatility — how many times have open opps had their CloseDate pushed | brief + FA dashboard |
| **Commit Deals at Risk** (30 deals, EUR 3.5M)    | Sf-audit-flagged commits that are showing slip-risk signals                                      | brief + FA dashboard |
| **Zombie ARR** (33% / EUR 147M)                  | Forecast hygiene — open ARR that's >2yr old, almost certainly never going to close               | brief + scorecard    |
| **Cycle Length 8Q trend** (694d → 143d)          | Survivor-bias signal: cycle-length collapse implies long-cycle deals are rotting in pipeline     | brief + scorecard    |

Read these together; no single one is the truth.

## Action items (deferred)

- [ ] Verify `ForecastCategoryName` Field History Tracking status (likely off, per the `Approval_Status__c` precedent)
- [ ] If off: enable via SF Setup (one-click admin change)
- [ ] Once enabled: wait 30 days for OFH to accumulate
- [ ] Build snapshot infra: launchd job at start-of-FQ that captures ForecastCategoryName for all open opps
- [ ] Build resolution job at end-of-FQ that joins snapshots × current IsWon
- [ ] Replace the existing `FA · Forecast Accuracy 8Q` metric with the new cohort-based version
- [ ] Update brief.py to swap the data source

## Communicating this to leadership

If a director asks "is the forecast accurate?", the right answer is:

> The 99.8% number on the FA dashboard measures post-close ARR vs the forecast field on the same deal — it's near-100% because ARR is set contractually at signing, not because the forecast is reliable. The metrics that DO measure forecast trust — push count distribution and zombie ARR — show a different story. Specifically: 199 opps have had their CloseDate pushed at least once, including 55 opps pushed 4+ times (EUR 3.3M). And 33% of the open pipeline is >2 years old, representing EUR 147M of likely losses-in-disguise. Real forecast accuracy (commit-called-at-start vs won-at-end) requires field-history infra we haven't built yet.

Don't quote the 99.8% number to leadership without this caveat.
