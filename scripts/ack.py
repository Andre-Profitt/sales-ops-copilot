#!/usr/bin/env python3
"""
Acknowledgment store — mute already-triaged opps so the morning brief
doesn't re-flag them every day.

State at `state/acknowledged.json`:
    {
      "006...": {"until": "2026-05-05", "note": "Commercial Approval submitted",
                 "acked_at": "2026-04-28"},
      ...
    }

Default TTL is 7 days. Expired entries are pruned on every read.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path
from typing import Any

STATE_DIR = Path(__file__).resolve().parent.parent / "state"
STATE_FILE = STATE_DIR / "acknowledged.json"


def _load() -> dict[str, dict[str, Any]]:
    if not STATE_FILE.exists():
        return {}
    try:
        return json.loads(STATE_FILE.read_text())
    except json.JSONDecodeError:
        return {}


def _save(data: dict[str, dict[str, Any]]) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")


def _prune(data: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    today = dt.date.today().isoformat()
    return {oid: rec for oid, rec in data.items() if rec.get("until", "") >= today}


def active_ids() -> set[str]:
    """Return set of opp IDs currently acknowledged (not expired)."""
    data = _prune(_load())
    return set(data.keys())


def add(opp_id: str, days: int = 7, note: str | None = None) -> dict[str, Any]:
    data = _prune(_load())
    today = dt.date.today()
    rec = {
        "until": (today + dt.timedelta(days=days)).isoformat(),
        "acked_at": today.isoformat(),
    }
    if note:
        rec["note"] = note
    data[opp_id] = rec
    _save(data)
    return rec


def remove(opp_id: str) -> bool:
    data = _load()
    if opp_id in data:
        del data[opp_id]
        _save(data)
        return True
    return False


def list_active() -> list[dict[str, Any]]:
    data = _prune(_load())
    out = []
    for oid, rec in sorted(data.items(), key=lambda kv: kv[1].get("until", "")):
        out.append({"id": oid, **rec})
    return out


def soql_exclusion() -> str:
    """Return ` AND Id NOT IN ('a','b',...)` or empty string if no acks."""
    ids = sorted(active_ids())
    if not ids:
        return ""
    quoted = ",".join(f"'{i}'" for i in ids)
    return f" AND Id NOT IN ({quoted})"


def _cmd_add(args: argparse.Namespace) -> int:
    rec = add(args.opp_id, days=args.days, note=args.note)
    print(
        f"acked {args.opp_id} until {rec['until']}"
        + (f" — {rec['note']}" if rec.get("note") else "")
    )
    return 0


def _cmd_rm(args: argparse.Namespace) -> int:
    if remove(args.opp_id):
        print(f"removed ack for {args.opp_id}")
        return 0
    print(f"no ack found for {args.opp_id}", file=sys.stderr)
    return 1


def _cmd_list(_: argparse.Namespace) -> int:
    rows = list_active()
    if not rows:
        print("(no active acknowledgments)")
        return 0
    print(f"{len(rows)} active acknowledgment(s):\n")
    for r in rows:
        line = f"  {r['id']}  until {r['until']}"
        if r.get("note"):
            line += f"  — {r['note']}"
        print(line)
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Acknowledge / mute alert-flagged opps.")
    sub = p.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("add", help="Acknowledge an opp ID for N days.")
    a.add_argument("opp_id")
    a.add_argument("--days", type=int, default=7)
    a.add_argument("--note", type=str, default=None)
    a.set_defaults(func=_cmd_add)

    r = sub.add_parser("rm", help="Remove an acknowledgment.")
    r.add_argument("opp_id")
    r.set_defaults(func=_cmd_rm)

    li = sub.add_parser("list", help="List active acknowledgments.")
    li.set_defaults(func=_cmd_list)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
