#!/usr/bin/env python3
"""
Phase 2 — live SF refresh of the workforce DuckDB.

Replaces the 4-month-stale static pack with live queries against
simcorp.my.salesforce.com. Maps SF events into the same fact shape
Phase 1's static pack used, so `wf.py` keeps working unchanged.

Scope (v1):
- Tasks (calls, emails, custom — Task object)
- Events (meetings — Event object)
- Opportunity stage changes (OpportunityHistory — last 90 days)
- KYC: deferred (snapshot-only via Account.KYC_Approval_Status__c)
- Quotes & Proposals: deferred (Apttus + Axioma both need separate auth)

Segment tagging:
- 'SimCorp' for everything from simcorp.my.salesforce.com
- 'Axioma' deferred until we have a confirmed data source

This script is idempotent: drops + recreates `fact_activity_live` and
related tables on each run. Phase 1's static pack tables (`fact_activity_clean`,
`fact_activity_unified`, etc.) are NOT touched — they remain the
historical baseline.

Per AGENTS.md SimCorp rules: read-only against SF, no LLM calls,
data stays local in DuckDB.
"""

from __future__ import annotations

import datetime as dt
import json
import pathlib
import subprocess
import sys
from typing import Any

import duckdb

THIS_DIR = pathlib.Path(__file__).resolve().parent
DB_PATH = THIS_DIR.parent.parent / "workforce" / "state" / "wf.duckdb"


def _sf(soql: str) -> list[dict[str, Any]]:
    """Run SOQL via sf CLI, return records list. Same pattern as brief.py."""
    out = subprocess.run(
        ["sf", "data", "query", "--query", soql, "--target-org", "preprod", "--json"],
        capture_output=True,
        text=True,
        check=False,
    )
    if out.returncode != 0:
        raise RuntimeError(f"sf query failed: {out.stderr.strip()}")
    return json.loads(out.stdout).get("result", {}).get("records", [])


def _week_start(iso_dt: str | None) -> str | None:
    """Convert ISO datetime to Monday-of-week ISO date (YYYY-MM-DD)."""
    if not iso_dt:
        return None
    d = dt.date.fromisoformat(iso_dt[:10])
    return (d - dt.timedelta(days=d.weekday())).isoformat()


# Effort weights mirror _effort.py — kept here too so refresh stays
# self-contained.
EFFORT = {
    "Activities": 0.5,
    "Opportunities": 1.0,
    "Quotes & Proposals": 2.0,
    "KYC": 3.0,
}


def pull_tasks(window_days: int = 365) -> list[dict[str, Any]]:
    """Tasks (calls, emails, custom) created in the last N days."""
    soql = (
        "SELECT Id, CreatedDate, ActivityDate, Type, Subject, Status, "
        "Owner.Name, AccountId, Account.Name, WhatId, What.Type "
        "FROM Task "
        f"WHERE CreatedDate >= LAST_N_DAYS:{window_days}"
    )
    rows = _sf(soql)
    out = []
    for r in rows:
        ts = r.get("CreatedDate") or ""
        out.append(
            {
                "event_id": f"TSK|{r.get('Id')}",
                "event_ts": ts,
                "event_week_start": _week_start(ts),
                "segment": "SimCorp",
                "process_family": "Activities",
                "process_subtype": r.get("Type") or "Other",
                "actor_name_raw": (r.get("Owner") or {}).get("Name"),
                "actor_role": None,
                "record_type": "Task",
                "record_id": r.get("Id"),
                "opportunity_id": (
                    r.get("WhatId") if (r.get("What") or {}).get("Type") == "Opportunity" else None
                ),
                "opportunity_name": None,
                "sales_owner_name": None,
                "account_name": (r.get("Account") or {}).get("Name"),
                "value_amount": None,
                "effort_units": EFFORT["Activities"],
                "source_file": "live:Task",
            }
        )
    return out


def pull_events(window_days: int = 365) -> list[dict[str, Any]]:
    """Events (meetings) created in the last N days."""
    soql = (
        "SELECT Id, CreatedDate, ActivityDate, Type, Subject, "
        "Owner.Name, AccountId, Account.Name, WhatId, What.Type "
        "FROM Event "
        f"WHERE CreatedDate >= LAST_N_DAYS:{window_days}"
    )
    rows = _sf(soql)
    out = []
    for r in rows:
        ts = r.get("CreatedDate") or ""
        out.append(
            {
                "event_id": f"EVT|{r.get('Id')}",
                "event_ts": ts,
                "event_week_start": _week_start(ts),
                "segment": "SimCorp",
                "process_family": "Activities",
                "process_subtype": r.get("Type") or "Meeting",
                "actor_name_raw": (r.get("Owner") or {}).get("Name"),
                "actor_role": None,
                "record_type": "Event",
                "record_id": r.get("Id"),
                "opportunity_id": (
                    r.get("WhatId") if (r.get("What") or {}).get("Type") == "Opportunity" else None
                ),
                "opportunity_name": None,
                "sales_owner_name": None,
                "account_name": (r.get("Account") or {}).get("Name"),
                "value_amount": None,
                "effort_units": EFFORT["Activities"],
                "source_file": "live:Event",
            }
        )
    return out


def pull_opp_history(window_days: int = 90) -> list[dict[str, Any]]:
    """Opportunity stage transitions in the last N days.

    Only Stage changes — not all field history. Per AGENTS.md the
    8-stage process is the governance model so stage changes are the
    'Opportunities' process-family events.
    """
    soql = (
        "SELECT Id, OpportunityId, Opportunity.Name, Opportunity.Type, "
        "Opportunity.Owner.Name, Opportunity.Account.Name, StageName, "
        "CreatedDate "
        "FROM OpportunityHistory "
        f"WHERE CreatedDate >= LAST_N_DAYS:{window_days}"
    )
    rows = _sf(soql)
    out = []
    for r in rows:
        ts = r.get("CreatedDate") or ""
        opp = r.get("Opportunity") or {}
        out.append(
            {
                "event_id": f"OPH|{r.get('Id')}",
                "event_ts": ts,
                "event_week_start": _week_start(ts),
                "segment": "SimCorp",
                "process_family": "Opportunities",
                "process_subtype": f"Stage→{r.get('StageName') or '?'}",
                "actor_name_raw": ((opp.get("Owner") or {}).get("Name")),
                "actor_role": None,
                "record_type": "OpportunityHistory",
                "record_id": r.get("Id"),
                "opportunity_id": r.get("OpportunityId"),
                "opportunity_name": opp.get("Name"),
                "sales_owner_name": (opp.get("Owner") or {}).get("Name"),
                "account_name": (opp.get("Account") or {}).get("Name"),
                "value_amount": None,
                "effort_units": EFFORT["Opportunities"],
                "source_file": "live:OpportunityHistory",
            }
        )
    return out


def main() -> int:
    if not DB_PATH.parent.exists():
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    print(f"[1/4] Connecting to {DB_PATH}")
    con = duckdb.connect(str(DB_PATH))

    print("\n[2/4] Pulling live SF data (read-only, simcorp.my.salesforce.com)")
    print("  → Task (last 365 days)")
    tasks = pull_tasks(window_days=365)
    print(f"    {len(tasks):>6d} task events")
    print("  → Event (last 365 days)")
    events = pull_events(window_days=365)
    print(f"    {len(events):>6d} event events")
    print("  → OpportunityHistory (last 90 days)")
    opph = pull_opp_history(window_days=90)
    print(f"    {len(opph):>6d} stage-change events")

    all_rows = tasks + events + opph
    if not all_rows:
        print("[FATAL] no rows pulled")
        return 1

    # Write to a fresh `fact_activity_live` table. Don't touch the
    # static pack's `fact_activity_clean` — that's the historical
    # baseline.
    print(f"\n[3/4] Writing {len(all_rows):,} rows to fact_activity_live")
    con.execute("DROP TABLE IF EXISTS fact_activity_live")
    cols = list(all_rows[0].keys())
    placeholders = ", ".join(["?"] * len(cols))
    con.execute(
        """
        CREATE TABLE fact_activity_live (
            event_id          VARCHAR,
            event_ts          VARCHAR,
            event_week_start  VARCHAR,
            segment           VARCHAR,
            process_family    VARCHAR,
            process_subtype   VARCHAR,
            actor_name_raw    VARCHAR,
            actor_role        VARCHAR,
            record_type       VARCHAR,
            record_id         VARCHAR,
            opportunity_id    VARCHAR,
            opportunity_name  VARCHAR,
            sales_owner_name  VARCHAR,
            account_name      VARCHAR,
            value_amount      DOUBLE,
            effort_units      DOUBLE,
            source_file       VARCHAR
        )
        """
    )
    con.executemany(
        f"INSERT INTO fact_activity_live ({', '.join(cols)}) VALUES ({placeholders})",
        [tuple(r[c] for c in cols) for r in all_rows],
    )

    # Build a per-person × week rollup matching `weekly_person_kpis`
    # shape so the same wf.py team-week / person verbs work against
    # live data when pointed at fact_activity_live.
    con.execute("DROP TABLE IF EXISTS weekly_person_kpis_live")
    con.execute(
        """
        CREATE TABLE weekly_person_kpis_live AS
        SELECT
            actor_name_raw                    AS canonical_name,
            event_week_start,
            COUNT(*)                          AS actions,
            COUNT(*)                          AS actions_adj,
            COUNT(DISTINCT record_id)         AS unique_records,
            SUM(effort_units)                 AS effort_units,
            SUM(effort_units)                 AS effort_adj,
            1.0                               AS availability_factor
        FROM fact_activity_live
        WHERE actor_name_raw IS NOT NULL
          AND event_week_start IS NOT NULL
        GROUP BY actor_name_raw, event_week_start
        """
    )

    # Verify
    n = con.execute("SELECT COUNT(*) FROM fact_activity_live").fetchone()[0]
    n_w = con.execute("SELECT COUNT(*) FROM weekly_person_kpis_live").fetchone()[0]
    minmax = con.execute("SELECT MIN(event_ts), MAX(event_ts) FROM fact_activity_live").fetchone()
    print(f"  fact_activity_live: {n:,} rows")
    print(f"  weekly_person_kpis_live: {n_w:,} rows (person × week)")
    print(f"  date range: {minmax[0]} → {minmax[1]}")

    print("\n[4/4] Done. Phase 1 static pack untouched.")
    print(
        "      Query live: duckdb workforce/state/wf.duckdb "
        '"SELECT * FROM weekly_person_kpis_live ORDER BY effort_units DESC LIMIT 10"'
    )
    con.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
