# Reporting Snapshot — `Pipeline_Snapshot__c`

Daily aggregate snapshot of open pipeline by **Owner x Stage x Type**, materialized
into a custom SObject by Salesforce's native Reporting Snapshot ("AnalyticSnapshot").
Replaces the disk-based `snapshot_diff` hack in `scripts/brief.py` with a
SOQL-queryable, audit-trail-friendly trend store.

## What it captures

One row per (Snapshot Date, Owner, Stage, Type) bucket per day:

| Field              | Type             | Source                                            |
| ------------------ | ---------------- | ------------------------------------------------- | ----- | ----- | ----- |
| `Snapshot_Date__c` | Date (ext-id)    | Run date (auto-populated by AnalyticSnapshot)     |
| `Owner_Name__c`    | Text(80)         | `Owner.Name` on Opportunity                       |
| `Stage_Name__c`    | Text(40)         | `StageName`                                       |
| `Opp_Type__c`      | Text(20)         | `Type` — Land / Expand / Renewal                  |
| `Total_ARR__c`     | Currency(18,2)   | `s!APTS_Opportunity_ARR__c.CONVERT` (Land+Expand) |
| `Total_ACV__c`     | Currency(18,2)   | `s!APTS_Renewal_ACV__c.CONVERT` (Renewal)         |
| `Weighted_ARR__c`  | Currency(18,2)   | `s!APTS_Forecast_ARR__c.CONVERT`                  |
| `Opp_Count__c`     | Number(8,0)      | `RowCount`                                        |
| `Snapshot_Key__c`  | Formula (unique) | `TEXT(Date)                                       | Owner | Stage | Type` |

`Snapshot_Date__c` and `Snapshot_Key__c` are both **external-id indexed** for fast
LAST_N_DAYS lookups + idempotent backfill via upsert.

## Why

- **Forecast accuracy back-testing** — rolling Q-start forecast vs end-of-Q won lets
  us measure true commit-call accuracy (not the field-rewritten near-100% number;
  see `docs/FORECAST_ACCURACY_CAVEAT.md`).
- **Cohort NRR** — start-of-cohort ACV anchored in real Date-stamped rows, not in
  memory.
- **Daily delta** in the brief becomes **30/90-day trend** without the JSON-on-disk
  fragility — and director-level drilldowns become a one-line SOQL.

## How to query

```sql
-- Last 30 days, all owners, all motions
SELECT Snapshot_Date__c, Owner_Name__c, Stage_Name__c, Opp_Type__c,
       Total_ARR__c, Total_ACV__c, Weighted_ARR__c, Opp_Count__c
FROM Pipeline_Snapshot__c
WHERE Snapshot_Date__c >= LAST_N_DAYS:30
ORDER BY Snapshot_Date__c DESC, Owner_Name__c ASC

-- Daily org-level open ARR trend (Land+Expand only)
SELECT Snapshot_Date__c, SUM(Total_ARR__c) total_arr, SUM(Opp_Count__c) opps
FROM Pipeline_Snapshot__c
WHERE Snapshot_Date__c >= LAST_N_DAYS:90
  AND Opp_Type__c IN ('Land', 'Expand')
GROUP BY Snapshot_Date__c
ORDER BY Snapshot_Date__c

-- Per-stage trend for a specific rep
SELECT Snapshot_Date__c, Stage_Name__c,
       SUM(Total_ARR__c) arr, SUM(Opp_Count__c) opps
FROM Pipeline_Snapshot__c
WHERE Owner_Name__c = 'Adam Hatcliff'
  AND Snapshot_Date__c >= LAST_N_DAYS:60
GROUP BY Snapshot_Date__c, Stage_Name__c
ORDER BY Snapshot_Date__c, Stage_Name__c
```

## Compliance — SimCorp AI Code of Conduct §8

Per the whitelist (`~/.claude/intel/simcorp-ai-whitelist-2026-04-28.md`):

- **Aggregate-only** — no per-deal name, account, amount, or close date stored
  in `Pipeline_Snapshot__c`. Owner x Stage x Type buckets are large enough that
  an individual deal cannot be identified.
- **No client-level data** flows through this artifact.
- **No people-related decisions** are sole-basis on these aggregates — they
  feed advisory dashboards, not termination/promotion decisions.
- **Multi-currency** is settled at snapshot time via `s!field.CONVERT` on the
  source report; raw multi-currency values do not flow into the SObject.

## Retention / capacity math

Approx row volume:

```
~365 days x ~134 owners x ~8 stages x 3 types
= ~1.17M rows / year ceiling
```

In practice: most owner/stage/type cells are empty (most reps don't hold all
8 stages x 3 types every day), so steady-state is ~1,800 rows/day = 660K/year.
Well within free-tier custom-object limits (no storage cost — included in
each Sales Cloud license at 20 MB/user; we'd consume ~150 MB/year at the
ceiling).

If retention becomes an issue, run a quarterly **scheduled Apex** (or
`sf data delete bulk`) job to delete `Snapshot_Date__c < LAST_N_DAYS:730`.

## Data lineage

```
Opportunity (live)
   -> Snapshot Pipeline Daily v1 (SUMMARY report, FX-converted s! aggregates)
         -> Pipeline Snapshot Daily (AnalyticSnapshot, daily 06:00 UTC)
               -> Pipeline_Snapshot__c (custom SObject, queryable)
                     -> pull_snapshot_history(days=30) in scripts/brief.py
```

**Source report (shipped):**

- ID: `00OTb000008niJRMAY`
- DeveloperName: `Snapshot_Pipeline_Daily_v1`
- Folder: `Sales Ops Commercial Health` (`00lTb000006hxm9IAA`)
- Format: SUMMARY · Groupings: `FULL_NAME / STAGE_NAME / TYPE`
- Aggregates: `s!APTS_Opportunity_ARR__c.CONVERT` / `s!APTS_Renewal_ACV__c.CONVERT` / `s!APTS_Forecast_ARR__c.CONVERT` / `RowCount`
- Filter: `IsClosed = false`
- Verified live: 134 owners x buckets = 1,803 rows; ARR EUR 466.86M, ACV EUR 177.30M

## How to add a new field

1. Add a field XML under `force-app/main/default/objects/Pipeline_Snapshot__c/fields/`.
   Follow the existing pattern (FX-converted currency for monetary fields).
2. Update `Pipeline_Snapshot_Admin.permissionset-meta.xml` to grant access.
3. Update the source report (`Snapshot_Pipeline_Daily_v1`) to expose the new
   aggregate column.
4. Update `Pipeline_Snapshot_Daily.analyticSnapshot-meta.xml` mappings.
5. Redeploy:
   ```bash
   sf project deploy start --target-org preprod --source-dir force-app
   ```
6. Update `pull_snapshot_history()` in `scripts/brief.py` to hydrate the field.

## Setup status (deployment)

`apro@simcorp.com` is on profile **SC Global Sales Operations Mobile**, which
does **not** carry `ModifyAllData` or `ModifyMetadata`. Schema-tier deploys
(`CustomObject`, `AnalyticSnapshot`) require a System Administrator. The
following pieces have shipped or are admin-pending:

| Phase                                             | Status                                                                                        |
| ------------------------------------------------- | --------------------------------------------------------------------------------------------- |
| 1. SObject `Pipeline_Snapshot__c` + 8 fields + PS | **admin-pending** — XML staged in `force-app/`, deploy blocked by INSUFFICIENT_ACCESS on apro |
| 2. Source report `Snapshot_Pipeline_Daily_v1`     | **shipped** — `00OTb000008niJRMAY` (apro can write to `Sales Ops Commercial Health`)          |
| 3. AnalyticSnapshot `Pipeline_Snapshot_Daily`     | **admin-pending** — XML staged, requires SObject first                                        |
| 4. brief.py wiring                                | **shipped** — `pull_snapshot_history()` + render section, empty-graceful                      |
| 5. This runbook                                   | **shipped**                                                                                   |

### What an admin needs to do

#### Option A: Metadata API deploy (preferred — 30 seconds total)

From an account with `ModifyAllData` or `ModifyMetadata` (any SimCorp SF
sysadmin):

```bash
cd ~/code/apps/sales-ops-copilot
sf project deploy start --target-org <admin-alias> --source-dir force-app
sf user permset assign --target-org <admin-alias> \
    --name Pipeline_Snapshot_Admin --on-behalf-of apro@simcorp.com
```

This deploys:

- `Pipeline_Snapshot__c` SObject + 8 fields
- `Pipeline_Snapshot_Admin` permission set (assigns to apro@simcorp.com)
- `Pipeline_Snapshot_Daily` AnalyticSnapshot (mappings already wired)

Then **schedule the snapshot** (one-time UI step — there's no Metadata API
for AnalyticSnapshot scheduling itself):

1. Setup -> search **"Reporting Snapshots"** -> click **Pipeline Snapshot Daily**.
2. Click **Edit**.
3. **Schedule Reporting Snapshot** section -> **Frequency: Daily**.
4. **Preferred Start Time**: 06:00 (server time).
5. **Start Date**: today. **End Date**: blank (run forever).
6. **Email Reporting Snapshot to**: leave default (running user only).
7. **Save**.

#### Option B: Pure Setup UI (~5 clicks total — fallback if Metadata API path is unavailable)

Steps 1-4 below define the SObject. Steps 5-6 schedule it. Step 7 assigns
permissions.

##### 1. Create the custom object

Setup -> Object Manager -> **Create** -> **Custom Object**:

- Label: **Pipeline Snapshot**
- Plural Label: **Pipeline Snapshots**
- Object Name: `Pipeline_Snapshot`
- Record Name: **Pipeline Snapshot Name** · Data Type: **Auto Number** · Display Format: `PS-{0000000}`
- Allow Reports: yes
- Allow Bulk API Access: yes
- Allow Sharing: yes
- Deployment Status: **Deployed**
- Save.

##### 2. Add the 8 custom fields

For each row in the table at the top of this doc, **Object Manager -> Pipeline Snapshot -> Fields & Relationships -> New** with the listed type, length/precision/scale, and external-ID setting. The formula for `Snapshot_Key__c` is:

```
TEXT(Snapshot_Date__c) & "|" & Owner_Name__c & "|" & Stage_Name__c & "|" & Opp_Type__c
```

(with **Treat blanks as zeroes** = checked, and **Unique** = checked).

##### 3. Verify the source report exists

Setup -> Reports -> folder `Sales Ops Commercial Health` -> **Snapshot · Pipeline Daily v1** must be present (it is — shipped 2026-04-29).

##### 4. Create the Reporting Snapshot

Setup -> search **"Reporting Snapshots"** -> **New Reporting Snapshot**:

- Name: **Pipeline Snapshot Daily**
- Unique Name: `Pipeline_Snapshot_Daily`
- Description: see object metadata above
- **Source Report**: `Snapshot · Pipeline Daily v1`
- **Target Object**: `Pipeline Snapshot` (`Pipeline_Snapshot__c`)
- **Running User**: `apro@simcorp.com`
- Save.

##### 5. Map fields

On the new Reporting Snapshot detail page -> **Field Mappings** -> **Edit**.

Map exactly:

| Source Report Column             | Target Field       |
| -------------------------------- | ------------------ |
| Execution Date (auto)            | `Snapshot_Date__c` |
| Owner Full Name                  | `Owner_Name__c`    |
| Stage                            | `Stage_Name__c`    |
| Type                             | `Opp_Type__c`      |
| Sum of APTS_Opportunity_ARR\_\_c | `Total_ARR__c`     |
| Sum of APTS_Renewal_ACV\_\_c     | `Total_ACV__c`     |
| Sum of APTS_Forecast_ARR\_\_c    | `Weighted_ARR__c`  |
| Record Count                     | `Opp_Count__c`     |

Save.

##### 6. Schedule

On the Reporting Snapshot detail page -> **Schedule Reporting Snapshot** -> **Edit**:

- Frequency: **Daily**
- Preferred Start Time: **06:00** (server time)
- Start Date: today
- End Date: **None**
- Save.

##### 7. Permissions for `apro`

Setup -> Permission Sets -> **New** (or import the staged `Pipeline_Snapshot_Admin.permissionset-meta.xml` via Metadata API):

- Object Settings -> `Pipeline Snapshot` -> grant Read/Create/Edit/Delete + View All / Modify All.
- Field-level Security -> grant Read+Edit on all 8 custom fields (`Snapshot_Key__c` is Read-only since it's a formula).
- Manage Assignments -> assign to `apro@simcorp.com`.

### Post-deployment verification

```bash
cd ~/code/apps/sales-ops-copilot

# 1. Custom object exists with 9+ fields
sf sobject describe --sobject Pipeline_Snapshot__c --target-org preprod --json \
  | python3 -c "import json,sys; print('fields:', len(json.load(sys.stdin)['result']['fields']))"
# Expected: 9 + system fields (Id, OwnerId, CreatedDate, etc.) ~ 17-18

# 2. Snapshot has run at least once
sf data query --target-org preprod \
  --query "SELECT COUNT(Id) FROM Pipeline_Snapshot__c WHERE Snapshot_Date__c = TODAY"
# Expected: >0 the morning after enabling

# 3. brief.py picks it up
python3 scripts/brief.py --no-llm | grep -A2 "30-day pipeline trend"
# Expected: shows "N days of history" (not the empty placeholder)
```

## Phase 2 — Region snapshots (deferred, post-v1 deploy)

Andre already maintains region-level trend reports in his Private Reports
folder. Once v1 (Owner x Stage x Type) is deployed and accumulating, layer
a parallel region-keyed snapshot using these existing reports as sources —
no new report-build needed.

| Source report                    | Report ID            | Cadence | Snapshot purpose                 |
| -------------------------------- | -------------------- | ------- | -------------------------------- |
| `CRO · Open Pipeline by Region`  | `00OTb000008mvyfMAA` | Daily   | Region pipeline coverage trend   |
| `CRO · Bookings Trend Region`    | `00OTb000008mw1tMAA` | Daily   | Region bookings velocity         |
| `CRO · Won YTD by Region`        | `00OTb000008mw0HMAQ` | Daily   | Region YTD won ARR               |
| `CRO · Renewal ACV by Region`    | `00OTb000008mw3VMAQ` | Daily   | Region renewal pipeline          |
| `New Customers (Land) by Region` | `00OTb000008ekqjMAA` | Weekly  | Land-motion regional cadence     |
| `NRR Quarterly Trend`            | `00OTb000008Ti13MAC` | Weekly  | Cohort NRR (already FQ-bucketed) |
| `GRR Quarterly Trend`            | `00OTb000008ThzRMAS` | Weekly  | Cohort GRR                       |

### Why a parallel object, not the same SObject

Region reports group on `Account.Region__c` (no Owner, no Stage in some).
Forcing them into `Pipeline_Snapshot__c` would require nulling out
Owner_Name**c / Stage_Name**c, which would break the `Snapshot_Key__c`
unique formula. Cleaner: a sibling SObject `Pipeline_Region_Snapshot__c`
with `Region__c`, `Snapshot_Date__c`, `Total_ARR__c`, `Total_ACV__c`,
`Opp_Count__c`, `Source_Report__c` (discriminator).

### Why this is deferred

- v1 needs to deploy + accumulate ~7-30 days first to validate the
  Reporting Snapshot mechanism end-to-end.
- The region reports are already useful as live reports in their own
  right — snapshotting them is purely additive.
- Each new AnalyticSnapshot adds one daily SF job + storage; ship them
  one at a time, not in a bundle.

### Decision criteria for adding the region snapshots

Add Phase 2 once any one of these hits:

- Andre asks for a region trend chart that goes back >18 months (SF FieldHistory cap).
- A director asks "what was Open ARR for EMEA on every Monday for the last year".
- The brief.py daily output starts referencing region trends from in-memory snapshots and would benefit from native persistence.
