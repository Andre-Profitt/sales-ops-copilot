#!/usr/bin/env python3
"""
Persist daily SF snapshot to state/snapshots/YYYY-MM-DD.json.
Compute Δ vs latest stored snapshot.

Direction A from HANDOFF §8.

Usage:
    python3 scripts/snapshot_diff.py
    # → writes state/snapshots/<today>.json + prints diff vs latest
"""

from __future__ import annotations

import datetime as dt
import json
import pathlib
import sys

# Make scripts/ importable
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from brief import pull_salesforce_snapshot

ROOT = pathlib.Path(__file__).resolve().parent.parent
SNAP_DIR = ROOT / "state" / "snapshots"


def _latest_prior_snapshot(today: dt.date) -> pathlib.Path | None:
    if not SNAP_DIR.exists():
        return None
    files = sorted(p for p in SNAP_DIR.glob("*.json") if "_diff" not in p.name)
    candidates = [f for f in files if f.stem != today.isoformat()]
    return candidates[-1] if candidates else None


def diff(today_snap: dict, prior_snap: dict) -> dict:
    """Compute Δ between two snapshots."""
    t_totals = today_snap.get("totals", {})
    p_totals = prior_snap.get("totals", {})
    t_arr = t_totals.get("new_business_arr_open_this_quarter", 0) or 0
    p_arr = p_totals.get("new_business_arr_open_this_quarter", 0) or 0
    t_acv = t_totals.get("renewal_acv_open_this_quarter", 0) or 0
    p_acv = p_totals.get("renewal_acv_open_this_quarter", 0) or 0
    return {
        "new_business_arr": {"today": t_arr, "prior": p_arr, "delta": t_arr - p_arr},
        "renewal_acv": {"today": t_acv, "prior": p_acv, "delta": t_acv - p_acv},
    }


def main() -> int:
    today = dt.date.today()
    SNAP_DIR.mkdir(parents=True, exist_ok=True)

    print("→ Pulling SF snapshot...")
    snap = pull_salesforce_snapshot()
    today_path = SNAP_DIR / f"{today.isoformat()}.json"
    today_path.write_text(json.dumps(snap, indent=2, default=str))
    print(f"  Wrote {today_path}")

    prior_path = _latest_prior_snapshot(today)
    if not prior_path:
        print("  No prior snapshot found — diff section will be empty in tomorrow's brief.")
        return 0

    prior = json.loads(prior_path.read_text())
    d = diff(snap, prior)
    print(f"  Δ vs {prior_path.stem}:")
    print(f"    New-business ARR: {d['new_business_arr']['delta']:+,.0f}")
    print(f"    Renewal ACV:     {d['renewal_acv']['delta']:+,.0f}")

    diff_path = SNAP_DIR / f"{today.isoformat()}_diff.json"
    diff_path.write_text(
        json.dumps(
            {
                "today": today.isoformat(),
                "prior": prior_path.stem,
                "diff": d,
            },
            indent=2,
            default=str,
        )
    )
    print(f"  Wrote {diff_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
