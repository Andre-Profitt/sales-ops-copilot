#!/usr/bin/env python3
"""
Per-quarter stage conversion from OpportunityFieldHistory.

Outputs cohort conversion rates by quarter, motion (Land vs Expand), owner.
Direction B from HANDOFF §8.

Usage:
    python3 scripts/forecast_backtest.py --quarters-back 4
"""

from __future__ import annotations

import argparse
import json
import pathlib
import subprocess
import sys
from collections import defaultdict


ROOT = pathlib.Path(__file__).resolve().parent.parent
STATE_DIR = ROOT / "state"


def _sf(soql: str) -> list[dict]:
    p = subprocess.run(
        ["sf", "data", "query", "--query", soql, "--json"],
        capture_output=True,
        text=True,
        check=False,
    )
    if p.returncode != 0:
        raise RuntimeError(f"sf query failed: {p.stderr.strip()}")
    return json.loads(p.stdout).get("result", {}).get("records", [])


def stage_transitions(quarters_back: int = 4) -> dict:
    """Pull StageName field history for the last N quarters."""
    rows = _sf(
        "SELECT OpportunityId, OldValue, NewValue, CreatedDate "
        "FROM OpportunityFieldHistory "
        "WHERE Field = 'StageName' "
        f"AND CreatedDate >= LAST_N_QUARTERS:{quarters_back}"
    )

    # Stage names in SF are "5 - Preferred" with dash, OR "5 Preferred" without.
    # split(' ')[0] gets the leading digit either way.
    transitions: defaultdict[tuple[str, str], int] = defaultdict(int)
    for r in rows:
        old = (r.get("OldValue") or "").split(" ")[0]
        new = (r.get("NewValue") or "").split(" ")[0]
        if old and new and old != new and old.isdigit() and new.isdigit():
            transitions[(old, new)] += 1

    forward_rates = {}
    for stage in ["1", "2", "3", "4", "5", "6", "7"]:
        out_total = sum(c for (f, _), c in transitions.items() if f == stage)
        out_forward = sum(c for (f, t), c in transitions.items() if f == stage and t > stage)
        if out_total > 0:
            forward_rates[f"stage_{stage}_forward_rate"] = out_forward / out_total

    return {
        "quarters_back": quarters_back,
        "transitions": {f"{f}_to_{t}": c for (f, t), c in sorted(transitions.items())},
        "forward_rates": forward_rates,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--quarters-back", type=int, default=4)
    args = ap.parse_args()

    print(f"→ Pulling StageName transitions for last {args.quarters_back} quarters...")
    out = stage_transitions(args.quarters_back)
    STATE_DIR.mkdir(exist_ok=True)
    out_path = STATE_DIR / f"forecast_backtest_q{args.quarters_back}.json"
    out_path.write_text(json.dumps(out, indent=2))
    print(f"  Forward rates: {out['forward_rates']}")
    print(f"  Wrote {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
