"""Effort-unit weights — weighted-event proxy for time-tracked effort.

No time tracking exists in SimCorp's exports. The README contract
assigns these weights so events can be summed into a single 'effort'
unit comparable across people and process families.

Per the AP/RW Phase 1 plan: tunable for future calibration.
"""

from __future__ import annotations

import os

# Baseline (per README_Workforce_Intelligence_v2.txt):
EFFORT_WEIGHTS_DEFAULT: dict[str, float] = {
    "Opportunities": 1.0,
    "Quotes & Proposals": 2.0,  # SimCorp + Axioma
    "KYC": 3.0,  # snapshot-only — proxy
    "Activities": 0.5,
}


def get_effort_weights() -> dict[str, float]:
    """Return effort weights, env-var-overrideable.

    Override via WORKFORCE_EFFORT_<FAMILY>=<float>, e.g.
        WORKFORCE_EFFORT_OPPORTUNITIES=1.5
    """
    out = dict(EFFORT_WEIGHTS_DEFAULT)
    for fam in list(out):
        env_key = "WORKFORCE_EFFORT_" + fam.upper().replace(" ", "_").replace("&", "AND")
        if (v := os.environ.get(env_key)) is not None:
            try:
                out[fam] = float(v)
            except ValueError:
                pass
    return out
