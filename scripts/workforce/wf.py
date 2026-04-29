#!/usr/bin/env python3
"""
wf.py — Workforce Intelligence CLI.

Read-only against `workforce/state/wf.duckdb`. Five verbs:
  team-week  [--week YYYY-MM-DD]   Most-recent or specified week's team rollup
  person     <name> [--weeks N]    One rep, last N weeks (default 8)
  anomalies  [--since YYYY-MM-DD]  Logged anomalies + new detections
  coverage   [--top N]             Account starvation (top N starved accounts)
  process-mix [--week YYYY-MM-DD]  Effort allocation across 4 process families

Per the AP/RW Phase 1 plan + COMPLIANCE.md: aggregate descriptive
output only, never per-person prescriptive AI inference. No LLM calls
in this CLI by design.
"""

from __future__ import annotations

import argparse
import pathlib
import sys

import duckdb

THIS_DIR = pathlib.Path(__file__).resolve().parent
DB_PATH = THIS_DIR.parent.parent / "workforce" / "state" / "wf.duckdb"


def _con() -> duckdb.DuckDBPyConnection:
    if not DB_PATH.exists():
        print(
            f"FATAL: missing {DB_PATH}. Run: python3 scripts/workforce/ingest.py",
            file=sys.stderr,
        )
        sys.exit(2)
    return duckdb.connect(str(DB_PATH), read_only=True)


def _print_table(rows: list, headers: list[str]) -> None:
    if not rows:
        print("(no rows)")
        return
    widths = [max(len(str(h)), max(len(str(r[i])) for r in rows)) for i, h in enumerate(headers)]
    print("  ".join(h.ljust(w) for h, w in zip(headers, widths)))
    print("  ".join("-" * w for w in widths))
    for r in rows:
        print("  ".join(str(c).ljust(w) for c, w in zip(r, widths)))


def cmd_team_week(args: argparse.Namespace) -> int:
    con = _con()
    if args.week:
        week = args.week
    else:
        # Most-recent week with non-zero data.
        row = con.execute(
            "SELECT MAX(event_week_start) FROM weekly_person_kpis "
            "WHERE TRY_CAST(actions AS BIGINT) > 0"
        ).fetchone()
        week = row[0] if row else None
    if not week:
        print("no week data found")
        return 1
    rows = con.execute(
        """
        SELECT
            canonical_name                                          AS owner,
            CAST(actions AS BIGINT)                                 AS actions,
            CAST(actions_adj AS BIGINT)                             AS actions_adj,
            ROUND(CAST(effort_units AS DOUBLE), 1)                  AS effort,
            ROUND(CAST(utilization_index_p75 AS DOUBLE), 2)         AS util_p75
        FROM weekly_person_kpis
        WHERE event_week_start = ?
          AND TRY_CAST(actions AS BIGINT) > 0
        ORDER BY CAST(effort_units AS DOUBLE) DESC NULLS LAST
        """,
        [week],
    ).fetchall()
    print(f"Week of {week} — {len(rows)} reps with activity\n")
    _print_table(list(rows), ["Owner", "Actions", "Adj actions", "Effort", "Util p75"])
    return 0


def cmd_person(args: argparse.Namespace) -> int:
    con = _con()
    rows = con.execute(
        """
        SELECT event_week_start                              AS week,
               CAST(actions AS BIGINT)                       AS actions,
               CAST(actions_adj AS BIGINT)                   AS actions_adj,
               ROUND(CAST(effort_units AS DOUBLE), 1)        AS effort,
               ROUND(CAST(utilization_index_p75 AS DOUBLE), 2) AS util_p75
        FROM weekly_person_kpis
        WHERE canonical_name = ?
        ORDER BY event_week_start DESC
        LIMIT ?
        """,
        [args.name, args.weeks],
    ).fetchall()
    if not rows:
        print(f"no rows for '{args.name}' — try a different name (case-sensitive)")
        return 1
    print(f"{args.name} — last {len(rows)} weeks\n")
    _print_table(list(rows), ["Week", "Actions", "Adj actions", "Effort", "Util p75"])
    return 0


def cmd_anomalies(args: argparse.Namespace) -> int:
    con = _con()
    where = ""
    params: list[str] = []
    if args.since:
        where = "WHERE week_start >= ?"
        params = [args.since]
    rows = con.execute(
        f"""
        SELECT week_start,
               ROUND(CAST(effort AS DOUBLE), 1)        AS effort,
               ROUND(CAST(effort_roll8 AS DOUBLE), 1)  AS effort_roll8,
               ROUND(CAST(z_score AS DOUBLE), 2)       AS z
        FROM anomalies_log
        {where}
        ORDER BY week_start DESC
        """,
        params,
    ).fetchall()
    print(f"{len(rows)} logged anomalies (z-scored deviations from 8-week roll)\n")
    _print_table(list(rows), ["Week", "Effort", "Roll8", "Z-score"])
    return 0


def cmd_coverage(args: argparse.Namespace) -> int:
    con = _con()
    rows = con.execute(
        """
        SELECT segment, process_family,
               ROUND(CAST(total_effort AS DOUBLE), 1) AS total_effort,
               CAST(effective_contributors AS BIGINT) AS contributors,
               ROUND(CAST(top1_share AS DOUBLE) * 100, 1) AS top1_share_pct,
               top1_person_name AS top_contributor
        FROM coverage_concentration
        ORDER BY total_effort DESC NULLS LAST
        LIMIT ?
        """,
        [args.top],
    ).fetchall()
    print(
        "Coverage concentration — Herfindahl-style: high `top1_share_pct` = single-rep dependency\n"
    )
    _print_table(
        list(rows),
        ["Segment", "Process", "Total effort", "Contributors", "Top1 %", "Top contributor"],
    )
    return 0


def cmd_process_mix(args: argparse.Namespace) -> int:
    con = _con()
    if args.week:
        week = args.week
    else:
        row = con.execute(
            "SELECT MAX(week_start) FROM weekly_process_kpis WHERE TRY_CAST(effort AS DOUBLE) > 0"
        ).fetchone()
        week = row[0] if row else None
    if not week:
        print("no process-mix data found")
        return 1
    rows = con.execute(
        """
        SELECT process_family,
               ROUND(CAST(effort AS DOUBLE), 1)  AS effort,
               CAST(actions AS BIGINT)           AS actions
        FROM weekly_process_kpis
        WHERE week_start = ?
        ORDER BY effort DESC NULLS LAST
        """,
        [week],
    ).fetchall()
    print(f"Process-family mix for week of {week}\n")
    _print_table(list(rows), ["Process family", "Effort units", "Actions"])
    return 0


def main() -> int:
    p = argparse.ArgumentParser(prog="wf.py", description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)

    p_tw = sub.add_parser("team-week")
    p_tw.add_argument("--week", help="YYYY-MM-DD week_start")
    p_tw.set_defaults(func=cmd_team_week)

    p_p = sub.add_parser("person")
    p_p.add_argument("name")
    p_p.add_argument("--weeks", type=int, default=8)
    p_p.set_defaults(func=cmd_person)

    p_a = sub.add_parser("anomalies")
    p_a.add_argument("--since", help="YYYY-MM-DD")
    p_a.set_defaults(func=cmd_anomalies)

    p_c = sub.add_parser("coverage")
    p_c.add_argument("--top", type=int, default=15)
    p_c.set_defaults(func=cmd_coverage)

    p_pm = sub.add_parser("process-mix")
    p_pm.add_argument("--week", help="YYYY-MM-DD week_start")
    p_pm.set_defaults(func=cmd_process_mix)

    args = p.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
