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
- Widget viz mix is now mixed-rhythm executive cockpit:
  `Metric: 10` (4 KPI tiles + 6 alert tiles) + `Funnel: 1` (Pipeline by
  Stage) + `Column: 1` (Renewal by Fiscal Quarter) + `Donut: 1` (Open ARR
  by Type) + `Bar: 3` (Top Accounts, Owner Concentration, Account
  Concentration top-N rankings). Re-run `python3 rebuild_viz.py` to
  re-apply if the viz mix drifts. No FlexTable — blocked in this org.
- Severity color hints (red for critical alerts, amber for important) are
  pushed via `visualizationProperties.metricFontColor` /
  `referenceLineColors`; the Analytics REST API silently drops these in
  preprod, so Metric tiles render in default text color. Alert tiles are
  still distinguishable by row position (rows 16-21) and by header text.
- Boolean filter values use lower-case `true`/`false` (Analytics API
  convention; the metadata-XML capital-case `True`/`False` rule applies
  to the Metadata API path, which is unavailable here).

## Audit + fixes (drill / row caps / sort / resize)

Post-rebuild audit (2026-04-28) found 4 issues; all fixed by `audit_fix.py`:

| # | Issue                                                                | Affected                  | Fix                                                                                       |
| - | -------------------------------------------------------------------- | ------------------------- | ----------------------------------------------------------------------------------------- |
| 1 | `properties.drillUrl: null` — chart widgets don't link to report     | 6 widgets (Funnel/Column/Donut/3 Bars) | `/lightning/r/Report/<id>/view` (modern Lightning URL — accepted)             |
| 2 | `properties.maxRows: null` — Bar charts render every row             | 3 Bar widgets             | Top Open Accounts=10, Owner Conc=10, Account Conc=15                                      |
| 3 | `groupingsDown[0].sortAggregate` unset — Top-N reports unranked      | 3 ranking reports         | `sortAggregate=s!Opportunity.APTS_Opportunity_ARR__c`, `sortOrder=Desc`                   |
| 4 | Account Concentration cell `rowspan=3` — too short for 15 bars       | 1 widget                  | `rowspan: 3 → 6` (cols 6-11, rows 19-24; no overlap, nothing else lives below)            |

Re-run idempotently:

```bash
python3 audit_fix.py --dry-run    # preview
python3 audit_fix.py              # apply + verify
```

Notes:
- Metric widgets do NOT need `drillUrl`; Lightning natively navigates from a metric tile to its source report.
- `reportMetadata.sortBy` is for TABULAR reports only; sending the aggregate
  there returns errorCode 113 ("sort column must be from a selected column")
  in this org. SUMMARY-with-grouping uses `groupingsDown[i].sortAggregate`.
- Dashboard PATCH is full-resource replace (same as `rebuild_viz.py`).

## Executive polish (`polish.py`)

Post-audit polish pass (2026-04-28) — turns the dashboard from a raw
technical report into an executive cockpit. 7 fixes in one PATCH:

| # | Fix                                                          | Status                                   |
| - | ------------------------------------------------------------ | ---------------------------------------- |
| 1 | Compact units — `displayUnits="auto"`, `decimalPrecision=1`  | shipped (16/16 widgets, charts incl.)    |
| 2 | Executive headers — short, exec-readable                     | shipped (16/16)                          |
| 3 | `metricLabel` subtitles on Metric tiles                      | shipped (10/10 Metric — Bar strips it)   |
| 4 | Layout — KPI / viz / 3-rankings / critical / important strips | shipped (16/16 cells, no overlap)        |
| 5 | Past Close Date primary aggregate → RowCount                 | rejected (silent strip — see notes)      |
| 6 | Concentration tile context (Top 10 / Top 15)                 | partial (Bar viz strips `metricLabel`)   |
| 7 | Donut scope — verifies TYPE in (Land, Expand)                | verified (no PATCH; already correct)     |

```bash
python3 polish.py --dry-run    # diff only
python3 polish.py              # apply + verify
```

Idempotent — second run = 0 component changes, 0 layout changes. Verify
loop re-GETs and reports persistence counts:

```
displayUnits='auto' persisted: 16/16
headers persisted:            16/16
metricLabel persisted:        10/10
layout cells correct:         16/16
```

### API gotchas discovered

- `displayUnits` enum is **lowercase** in this org. Sending `"Auto"` 400s
  with `JSON_PARSER_ERROR`. `"auto"` is accepted on every viz type
  (Metric, Bar, Funnel, Column, Donut). The org's UI editor writes
  capital-case, but the REST API only accepts lower.
- `metricLabel` is **Metric-only**. Setting it on a Bar widget PATCHes
  successfully but is silently stripped on re-GET. So Owner / Account
  Concentration tiles can't carry "Top N · flagged ARR" subtitles —
  the header carries the context instead.
- **Past Close Date aggregate (Fix 5) is silently stripped.** Both the
  report-level reorder (`reportMetadata.aggregates = [RowCount, ARR]`)
  and the dashboard widget-level override (`properties.aggregates[0].name
  = "RowCount"`) PATCH successfully — and the org reverts both on the
  next re-GET. Sticking with the ARR sum tile + `metricLabel="open
  opps"` so the subtitle still tells the executive that the count, not
  the €325k, is the signal.

## Re-applying viz types (post-deploy)

If the dashboard viz selection drifts (or someone edits in the UI and
saves all-bar again), re-run:

```bash
python3 rebuild_viz.py --diff      # preview viz-type counts
python3 rebuild_viz.py --dry-run   # write PATCH body to /tmp, no API call
python3 rebuild_viz.py             # PATCH the live dashboard in place
```

Idempotent. Only `componentType` and `layout.components` change — same
report IDs, same dashboard ID (`01ZTb00000FxX2YMAV`), same bookmark.

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

## Upgrade v2 — Filters + Asset Integrity + Renewal Health (`upgrade_v2.py`)

Three coordinated upgrades shipped 2026-04-28 in one atomic PATCH (script
is idempotent — second run is a no-op on the dashboard, only re-PATCHes
the four owned reports):

```bash
python3 upgrade_v2.py --dry-run    # preview
python3 upgrade_v2.py              # apply + verify
```

### A. Dashboard filters (3 picklist + free-text filters)

Top-level `filters` array on the dashboard, plus per-component
`properties.filterColumns` so each filter actually constrains the
underlying widgets. Verified shape against
`01ZTb00000FSP7hMAH` (Sales Directors Monthly) and
`01ZTb00000CcCHNMA3` (Client Accounts Pipeline).

| Filter        | dataType      | Bound column (Opp widgets)                  | Bound column (Asset widgets)        |
| ------------- | ------------- | ------------------------------------------- | ----------------------------------- |
| Region        | picklist      | `Account.Region__c`                         | not exposed on AssetWithProduct     |
| Product Family | multipicklist | `Opportunity.APTS_RH_Product_Family__c`     | not exposed on AssetWithProduct     |
| Owner         | string (contains) | `FULL_NAME` (Opportunity.Owner.Name)    | `ACCOUNT_OWNER_NAME` (best-effort)  |

API findings:

- The top-level key is `filters`, NOT `dashboardFilters`. Earlier rounds
  failed because we sent the documented Analytics-API name. The org's
  `/describe` exposes `filters`.
- Each filter object is `{dataType, name, options[], selectedOption,
  errorMessage}` — server allocates `id` + option-`id`, so we must
  OMIT those on PATCH.
- Per-widget binding lives at `components[i].properties.filterColumns`
  as `[{label, name}]` — `label` matches the filter `name`, `name` is
  the report column. Mis-bound entries (column not in the report)
  return `400 "<col> is not a valid filter column"` — so Asset widgets
  bind only to the columns AssetWithProduct actually exposes.
- 232 dashboards probed in this org for canonical shape: only ~3 use
  filters at all, and the LAND Pipeline / Sales Directors Monthly
  shape is what we mirror.

If filters get rejected for any reason in the future, `upgrade_v2.py`
auto-retries the dashboard PATCH WITHOUT filters or `filterColumns`, so
B + C ship even when A fails.

### B. Asset Integrity (3 new Metric tiles)

Three new SF Reports + three new widgets in a new bottom row (row 22,
4 cols each, side-by-side). Report type: `AssetWithProduct` (folder
`Sales Ops Commercial Health`).

| Header                        | Logic                                      | Live count today |
| ----------------------------- | ------------------------------------------ | ---------------- |
| Ghost Assets                  | `USAGE_END_DATE < TODAY`                   | **0**            |
| Duplicate Active Assets       | SUMMARY grouped by `ACCOUNT.NAME` × `PRODUCT.NAME`, RowCount | **86**           |
| Expiring · No Renewal Check   | `USAGE_END_DATE <= NEXT_90_DAYS` AND `>= TODAY` | **0**            |

Data sparsity in this preprod org:

- `Asset` SObject has 95 records; **`Status`, `UsageEndDate`,
  `InstallDate`, `PurchaseDate` are universally null** in the data.
- Therefore Ghost + Expiring read 0 — there are no records with a
  populated end date, the filter has nothing to match. This is the
  honest report; per the build rules ("Better honest than fake")
  we did not invent counts.
- Duplicate-by-product reads 86 — the grand-total RowCount across
  the SUMMARY report after the test-artifact filter (CLM_SimCorp +
  QtC excluded). All 86 sit on a single `SC Test Account` —
  surfaces the real signal that the same product appears multiple
  times for the same account.

API findings on AssetWithProduct:

- Default `standardDateFilter` is `INSTALL_DATE = THIS_FISCAL_QUARTER`.
  With `InstallDate` null on every row, this filter alone returns 0.
  Set `durationValue=CUSTOM` with `startDate="" endDate=""` (server
  normalizes to null) so null-date rows are included.
- Cannot use SUMMARY-with-no-grouping for Metric tiles — every Asset
  report needs at least one grouping (Ghost/Expiring use
  `ACCOUNT.NAME`, Duplicate uses `ACCOUNT.NAME × PRODUCT.NAME`).
- Component-level `filterColumns` MUST reference columns that exist
  on the report; AssetWithProduct doesn't expose `Account.Region__c`
  or `Opportunity.APTS_RH_Product_Family__c`, so Asset widgets bind
  only to the Owner filter (`ACCOUNT_OWNER_NAME`).
- "No Renewal Opp" join on Asset → Account → Opportunity (Type=Renewal)
  needs a Custom Report Type, which Andre cannot author via REST
  (no Metadata API perms). Shipped the simpler "Expiring ≤90d"
  variant and documented the gap in the widget header.

### C. Renewal Health donut (replaces Past Close Date tile)

Past Close Date Metric tile (€325k — trivial signal) was dropped from
the dashboard. The vacated slot at (row 16, col 9, rowspan 3,
colspan 3) is now occupied by a Donut showing **Renewal Health by
Fiscal Quarter** — open Renewal opps grouped by `FISCAL_QUARTER`,
sliced by `APTS_Renewal_ACV__c`.

Live slices today (Open Renewals, EUR ACV):

| Fiscal Quarter | ACV          | Renewal count |
| -------------- | ------------ | ------------- |
| Q2-2026        | EUR 2.4 M    | 24            |
| Q3-2026        | EUR 6.4 M    | 17            |
| Q4-2026        | EUR 145.0 M  | 42            |
| Q1-2027        | EUR 2.5 M    | 11            |
| Q2-2027        | EUR 1.2 M    | 3             |
| Q3-2027        | EUR 9.8 M    | 10            |
| Q4-2027        | EUR 7.7 M    | 14            |
| Q1-2028        | EUR 0.4 M    | 4             |
| Q2-2028        | EUR 1.5 M    | 2             |
| Q4-2028        | EUR 0.1 M    | 2             |
| **Total**      | **EUR 177.3 M** | **134**    |

This is a **simpler fallback** than the originally-spec'd On Track /
At Risk / No Opp categorization — Reports doesn't support multi-
condition CASE (rule-based bucketing requires a Custom Report Type
with formula columns, which Andre cannot author via REST). The
fiscal-quarter slicing surfaces the same business question
("when is the renewal book due, and what's overdue?") via the
implicit At-Risk-If-Past-Quarter heuristic.

Note: the Renewal Health report explicitly filters `Type='Renewal'`
and `IsClosed=false` — ARR is NOT mixed with the Open Pipeline KPI
tile (Land+Expand ARR). ACV vs ARR separation per the SimCorp
canonical rule (memory `feedback_simcorp_arr_acv_separation.md`).

### Final state

- Dashboard: 16 widgets (pre-v2) → 19 widgets (post-v2). Past Close
  Date dropped, Renewal Health donut added, 3 Asset tiles added.
- Filters: 3 declared, 3 verified on re-GET.
- All 4 new reports live in `Sales Ops Commercial Health` folder.
- Idempotent: `python3 upgrade_v2.py` second run = re-PATCHes report
  metadata (filters, date ranges) but makes 0 dashboard changes;
  third run on top of identical metadata = full no-op.
