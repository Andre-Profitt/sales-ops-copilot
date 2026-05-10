# RW Salesforce Gap Source Probe

Read-only probe against Salesforce via `sf` CLI and Report REST. It does not publish to Fabric.

Generated: `2026-05-10T16:00:11+00:00`

Cardinal guardrail: ARR is Land + Expand only; Renewal ACV is Renewal only. Total Open Pipeline Value is the only explicitly labeled cross-motion value.

## Answer

- Bridgeable now from Salesforce: 3 KPI groups.
- Salesforce source exists but is not solid production coverage yet: 3 KPI groups.
- Still blocked by missing/population issue: 1 KPI groups.

## Findings

| KPI(s) | Status | Source | Evidence | Implementation move |
| --- | --- | --- | --- | --- |
| `existing_arr_run_rate` | bridge_found | Apttus_Config2__AssetLineItem__c | 97,586 current active/non-expired asset rows; ARR sum 418,160,519. | Stage f_asset_line_item and add active ARR run-rate measures by account, product, region, and renewal quarter. |
| `business_at_risk` | bridge_found | AssetLineItem + Account.Risk_of_Potential_Termination__c | High/Medium risk active ARR sum 106,523,633; grain is active asset ARR, not renewal-opportunity ACV. | Replace Renewal opp-risk proxy with active-base ARR at risk, grouped by account risk and renewal/end date. |
| `one_off_revenues` | bridge_found | Opportunity one-off fields plus OpportunityLineItem revenue stream/product family | Current FY PS non-recurring sum 223,195,050; PS one-off 20,755,740; PSO one-off 6,918,580. | Stage one-off amount columns and/or f_opportunity_line_item to build a non-recurring revenue page/ledger. |
| `pipeline_coverage_3x` | source_found_but_not_current | ForecastingQuota and Opportunity Quota record type | ForecastingQuota has 36 rows through 2023-10-01; current FY Opportunity quota_count=0. | Do not use as 2026 denominator yet. Need current quota/target feed or confirmed quota object scope. |
| `forecast_accuracy` | source_found_snapshot_needed | ForecastingItem and ForecastingFact | ForecastingItem rows=42,920; ForecastingFact rows=36,979. These are current-state forecast objects, not an as-of forecast submission history. | Stage daily/weekly f_forecast_snapshot now; backtest accuracy once snapshots exist against actual closed won ARR. |
| `indexation_arr_growth` | blocked_no_populated_source | Apttus asset renewal adjustment fields | AssetLineItem renewal adjustment count=0; renewal adjustment type count=0. | Find a different uplift/indexation source or get the commercial field populated; current asset object does not close this. |
| `synergy_deals_won`, `synergy_deals_pipe` | report_found_but_not_field_grade | Existing Salesforce Synergy reports | Reports filter Opportunity Name contains 'Synergy' and currently return zero totals. Non-zero report totals found=0. | Either accept the report definition as official zero, or add/stage a trusted Synergy flag; do not count Land won as Synergy. |

## Engineering Read

- Stage `Apttus_Config2__AssetLineItem__c` next. It can replace the renewal-risk proxy with active-base ARR and unlock existing ARR run-rate.
- Stage one-off Opportunity fields or `OpportunityLineItem` next. Salesforce already has non-recurring/one-off signal; this is not a true source gap.
- Do not call pipeline coverage solid until a current 2026 quota denominator is identified. Existing quota records are stale for this dashboard.
- Start a ForecastingItem/ForecastingFact snapshot table now. True forecast accuracy needs as-of snapshots, not just current forecast state.
- Do not use Land won count as Synergy. Existing Synergy reports are name-filtered and zero today; use that definition only if RW accepts it as official.
