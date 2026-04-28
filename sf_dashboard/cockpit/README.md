# Sales Ops — Commercial Health & Governance

Live Salesforce Lightning dashboard mirroring the daily Sales Ops cockpit
brief (KPI strip + critical alerts + pipeline detail + owner/account
concentration). Same numbers Andre sees in `reports/YYYY-MM-DD.md` each
morning, but interactive in the Salesforce UI.

## What's deployed

- Folder: `Sales Ops Commercial Health` (Reports + Dashboards)
- Dashboard: `Sales Ops — Commercial Health & Governance` — id `01ZTb00000FxX2YMAV`
  - URL: <https://simcorp.lightning.force.com/lightning/r/Dashboard/01ZTb00000FxX2YMAV/view>
- 16 reports (one per widget; widget cap 20 — we ship 16)

## How to redeploy

```bash
python3 deploy_cockpit_dashboard.py
```

The script is idempotent: it re-uses existing reports/dashboard if found.
To wipe and rebuild from scratch:

```bash
python3 deploy_cockpit_dashboard.py --rebuild
```

## Deploy mechanism

Salesforce Metadata API requires `ModifyAllData` / `ModifyMetadata`, which
`apro@simcorp.com` does NOT have. The script uses the Analytics REST API
instead:

- `POST /services/data/v66.0/folders` — create report + dashboard folders
- `POST /services/data/v66.0/analytics/reports` — create each report
- `POST /services/data/v66.0/analytics/dashboards` — create the dashboard

Auth comes from `sf org display --target-org apro@simcorp.com`.

## Hard rules baked in

- ARR vs ACV are kept separate. Land+Expand widgets use
  `APTS_Opportunity_ARR__c`, Renewal widgets use `APTS_Renewal_ACV__c`.
  No widget blends them.
- Test-artifact filter (mirrors `scripts/_filters.py`) is applied to every
  report. `FULL_NAME` (Owner.Name) is intentionally NOT filtered because
  FlexTable widgets fail dashboard "viewing as" validation when a filter
  references User.Name in this org. Maria Sabiniewicz's test-bot opps are
  caught by the Account-name patterns (`CLM_SimCorp QtC%`, `QtC %`).
- All chart widgets use horizontal Bar viz (`visualizationType: Bar`).
  No FlexTable — that viz type is blocked in this org for reports backed
  by these custom-field heavy queries.
- Boolean filter values use lower-case `true`/`false` (Analytics API
  convention; the metadata-XML capital-case `True`/`False` rule applies
  to the Metadata API path, which is unavailable here).

## Widget layout (16 widgets, 12-col grid, 4 widgets per row)

| Section                 | Widget                                   | Report DeveloperName                     |
| ----------------------- | ---------------------------------------- | ---------------------------------------- |
| KPI Strip               | Open Pipeline ARR (Land+Expand, FY)      | `Open_Pipeline_ARR_Land_Expand_FY`       |
|                         | Commit Forecast — Stage 5+6 ARR (CFQ)    | `Commit_Forecast_Stage_5_6_ARR_CFQ`      |
|                         | Open Opps Count (Land+Expand, FY)        | `Open_Opps_Count_Land_Expand_FY`         |
|                         | Renewal ACV — Current Quarter            | `Renewal_ACV_Current_Quarter`            |
| Pipeline Detail         | Top Open Accounts by Land+Expand ARR     | `Top_Open_Accounts_by_Land_Expand_ARR`   |
|                         | Pipeline by Stage — Land+Expand ARR      | `Pipeline_by_Stage_Land_Expand_ARR`      |
|                         | Renewal ACV by Fiscal Quarter            | `Renewal_ACV_by_Fiscal_Quarter`          |
|                         | Open ARR by Type — Land vs Expand        | `Open_ARR_by_Type_Land_vs_Expand`        |
| Critical Alerts         | Stage 3+ ≥$500k no Commercial Approval   | `Stage_3_500k_no_Commercial_Approval`    |
|                         | Land Stage 3+ no Commercial Approval     | `Land_Stage_3_no_Commercial_Approval`    |
|                         | Alert: Stage 5+ Land/Expand without KYC  | `Alert_Stage_5_Land_Expand_without_KYC`  |
|                         | Alert: Open Opps with Past CloseDate     | `Alert_Open_Opps_with_Past_CloseDate`    |
| Hygiene & Concentration | Alert: Stage 3+ Dec 31 Placeholder Dates | `Alert_Stage_3_Dec_31_Placeholder_Dates` |
|                         | Alert: Stage 3+ No Activity 60+ Days     | `Alert_Stage_3_No_Activity_60_Days`      |
|                         | Owner Concentration — Flagged ARR        | `Owner_Concentration_Flagged_ARR`        |
|                         | Account Concentration — Flagged ARR      | `Account_Concentration_Flagged_ARR`      |

(Salesforce auto-appends a numeric suffix to DeveloperName on create; the
actual deployed names are `*5` / `*6` — see `sf data query` for the
canonical list.)

## How to delete cleanly

```bash
# Delete all reports in the folder
TOKEN=$(sf org display --target-org apro@simcorp.com --json | python3 -c 'import sys,json;print(json.load(sys.stdin)["result"]["accessToken"])')
sf data query --target-org apro@simcorp.com \
  --query "SELECT Id FROM Report WHERE FolderName='Sales Ops Commercial Health'" \
  --result-format csv 2>/dev/null | tail -n +2 | while read rid; do
    curl -sS -o /dev/null -X DELETE \
      "https://simcorp.my.salesforce.com/services/data/v66.0/analytics/reports/$rid" \
      -H "Authorization: Bearer $TOKEN"
done

# Delete the dashboard
curl -sS -o /dev/null -X DELETE \
  "https://simcorp.my.salesforce.com/services/data/v66.0/analytics/dashboards/01ZTb00000FxX2YMAV" \
  -H "Authorization: Bearer $TOKEN"

# Folders themselves stay (delete via UI if needed; folder-delete via API
# requires admin perms).
```

## Known caveats

- Dashboard runs as `apro@simcorp.com` (`SpecifiedUser` running-user mode).
  Other viewers see the same numbers Andre would see.
- Currency conversion: report values render in EUR (org default). The daily
  brief queries raw `APTS_Opportunity_ARR__c` (per-opp currency) without
  conversion — so Critical-alert ARR shows as ~€130M in the dashboard vs
  ~$141.8M in the brief. Counts also differ slightly (60-70 vs 104) because
  the threshold filter compares converted-to-EUR values; deals worth
  $500k–$580k drop below the €500k threshold after FX conversion.
  This is inherent to Reports vs raw SOQL and matches what users see in
  every other SF report in this org.
- Filters at the dashboard level (Region, Product) were de-scoped: the
  dashboardFilter Analytics-API surface was returning JSON_PARSER_ERROR
  for our payload shape and the precedent (`deploy_coo_dashboard.py`)
  doesn't deploy them either. Add via UI if needed.
