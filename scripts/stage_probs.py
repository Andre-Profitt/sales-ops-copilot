#!/usr/bin/env python3
"""
Empirical stage probabilities — probability of reaching Won from each
SimCorp 8-stage opportunity stage, computed from the last N quarters of
OpportunityFieldHistory transitions.

Strategy: forward-rate per stage = (transitions to higher stage) /
(transitions out). Then prob_of_win(stage) = product of forward-rates
from this stage to Won.

Cached at `state/stage_probabilities.json` with 30-day TTL. Naive priors
are used as a fallback when no history is available.

Lifted from `~/code/apps/account-drilldown/scripts/forecast.py` so the
copilot can compute its own weighted forecast without a cross-repo dep.
"""

from __future__ import annotations

import datetime as dt
import json
import subprocess
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CACHE_PATH = ROOT / "state" / "stage_probabilities.json"
CACHE_TTL_DAYS = 30

NAIVE_STAGE_PROBABILITY: dict[str, float] = {
    "1 - Prospecting": 0.05,
    "2 - Discovery": 0.15,
    "3 - Engagement": 0.30,
    "4 - Shortlisted": 0.50,
    "5 - Preferred": 0.75,
    "6 - Contracting": 0.90,
    "7 - Opt-out": 0.95,
    "8 - Won": 1.00,
}

STAGE_LABEL = {
    "1": "1 - Prospecting",
    "2": "2 - Discovery",
    "3": "3 - Engagement",
    "4": "4 - Shortlisted",
    "5": "5 - Preferred",
    "6": "6 - Contracting",
    "7": "7 - Opt-out",
    "8": "8 - Won",
}


_session_cache: tuple[dict[str, float], str] | None = None


def _compute_empirical(quarters_back: int = 4) -> dict[str, float]:
    soql = (
        "SELECT OldValue, NewValue FROM OpportunityFieldHistory "
        f"WHERE Field = 'StageName' AND CreatedDate >= LAST_N_QUARTERS:{quarters_back}"
    )
    p = subprocess.run(
        ["sf", "data", "query", "--query", soql, "--json"],
        capture_output=True,
        text=True,
        check=False,
    )
    if p.returncode != 0:
        return {}
    try:
        rows = json.loads(p.stdout).get("result", {}).get("records", [])
    except json.JSONDecodeError:
        return {}

    transitions: dict[tuple[str, str], int] = defaultdict(int)
    for r in rows:
        old = (r.get("OldValue") or "").split(" ")[0]
        new = (r.get("NewValue") or "").split(" ")[0]
        if old and new and old != new and old.isdigit() and new.isdigit():
            transitions[(old, new)] += 1

    forward_rate: dict[str, float] = {}
    for stage in ("1", "2", "3", "4", "5", "6", "7"):
        out_total = sum(c for (f, _), c in transitions.items() if f == stage)
        out_forward = sum(c for (f, t), c in transitions.items() if f == stage and t > stage)
        forward_rate[stage] = (out_forward / out_total) if out_total > 0 else 0.0

    cumulative: dict[str, float] = {"8": 1.0}
    running = 1.0
    for s in ("7", "6", "5", "4", "3", "2", "1"):
        running *= forward_rate.get(s, 0.0)
        cumulative[s] = running

    return {STAGE_LABEL[s]: cumulative[s] for s in STAGE_LABEL}


def get_stage_probabilities() -> tuple[dict[str, float], str]:
    """Return (stage→prob_of_win, source_label). Caches per-process and on disk."""
    global _session_cache
    if _session_cache is not None:
        return _session_cache

    if CACHE_PATH.exists():
        try:
            cache = json.loads(CACHE_PATH.read_text())
            cached_at = dt.date.fromisoformat(cache["computed_on"])
            age = (dt.date.today() - cached_at).days
            if age <= CACHE_TTL_DAYS:
                probs: dict[str, float] = cache["probabilities"]
                _session_cache = (probs, f"empirical, cached {age}d ago")
                return _session_cache
        except Exception:
            pass

    empirical = _compute_empirical()
    if not empirical or all(v == 0 for v in empirical.values()):
        _session_cache = (NAIVE_STAGE_PROBABILITY, "naive priors (no history)")
        return _session_cache

    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    CACHE_PATH.write_text(
        json.dumps(
            {"computed_on": dt.date.today().isoformat(), "probabilities": empirical},
            indent=2,
        )
    )
    _session_cache = (empirical, "empirical (computed today)")
    return _session_cache


def weighted(by_stage: list[dict], amount_key: str) -> float:
    """Sum of arr/acv * stage_probability across a by_stage rollup."""
    probs, _ = get_stage_probabilities()
    return sum((row.get(amount_key) or 0) * probs.get(row.get("stage", ""), 0) for row in by_stage)


if __name__ == "__main__":
    probs, source = get_stage_probabilities()
    print(f"Source: {source}\n")
    for stage, p in probs.items():
        print(f"  {stage:<22} {p * 100:5.1f}%")
