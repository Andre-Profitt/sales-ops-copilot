# RW Churn / NRR Experiment Plan

Status: tracked long-running work, not production KPI yet.

## Why this exists

Andre's churn hypothesis is viable enough to track explicitly: use Salesforce asset line history to compare what an account-product had at the prior period versus what it has now, then classify retained, churn/downsell, expansion, cross-sell, GRR, and NRR.

This must stay separate from opportunity ARR and Renewal ACV:

- Active-base ARR retention/churn uses asset line item ARR.
- Renewal opportunity ACV remains the renewal pipeline/renewal close metric.
- Land + Expand ARR remains new-business opportunity pipeline.

## Current evidence

- Current active/non-expired asset base is already staged as `f_asset_line_item`: 97,586 rows.
- Read-only Salesforce asset probe found historical/effective-dated signal since 2025-01-01: 125,419 asset rows.
- The same probe found 17,466 inactive rows since 2025-01-01, enough to test churn/downsell classification.
- Statuses observed include Activated, Superseded, Cancelled, Expired, Suspended, and On Trial.

## Experimental model target

Create a new experimental fact or snapshot table:

- `f_asset_line_item_history` or `f_asset_snapshot`
- Grain: account, product family/area/type, period, currency-normalized active-base ARR.
- Core fields: account id, product fields, region, industry/segment, start date, end date, inactive flag, asset status, active-base ARR EUR.

Derived measures:

- Starting active-base ARR
- Ending active-base ARR
- Retained active-base ARR = min(starting, ending)
- Churn/downsell ARR = max(starting - ending, 0)
- Expansion/cross-sell ARR = max(ending - starting, 0)
- GRR % = retained / starting
- NRR % = (retained + expansion) / starting

## BI surface target

Add an experimental tab after Product Retention:

- Top strip: starting active-base ARR, ending active-base ARR, churn/downsell ARR, expansion/cross-sell ARR, GRR %, NRR %.
- Heatmap: product family x region, colored by churn/downsell % and sized by starting active-base ARR.
- Heatmap: product family x segment/industry, same basis.
- Bridge: starting active-base ARR -> churn/downsell -> expansion/cross-sell -> ending active-base ARR.
- Ledger: account-product rows with prior ARR, current ARR, delta, classification, product, region, segment, renewal/end date.

## Acceptance

- The page title and KPI labels say `Experimental`.
- No Renewal ACV or Land + Expand ARR measures are used on this tab.
- Churn/NRR math is tested against deterministic fixture rows before any live publish.
- Visual QA, metric-basis, unit-policy, and semantic-filter gates pass.
- The experiment is not promoted to production until asset history reconstruction ties out against a known Finance/renewals source.
