#!/usr/bin/env python3
"""
Drift check — `scripts/_filters.py` must be byte-identical between the two
repos that consume it. Run before commits or in preflight.

Exits 0 on match, 1 on drift.
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

THIS_REPO = Path(__file__).resolve().parent.parent  # sales-ops-copilot
HERE = THIS_REPO / "scripts" / "_filters.py"

# Sibling repo paths to compare against. Add more here as needed.
PEER_PATHS = [
    Path.home() / "code" / "apps" / "account-drilldown" / "scripts" / "_filters.py",
]


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:12]


def main() -> int:
    if not HERE.exists():
        print(f"FAIL: {HERE} missing", file=sys.stderr)
        return 1

    here_sha = _sha(HERE)
    drift = False
    print(f"local : {HERE}  sha={here_sha}")
    for peer in PEER_PATHS:
        if not peer.exists():
            print(f"skip  : {peer}  (not present)")
            continue
        peer_sha = _sha(peer)
        status = "OK" if peer_sha == here_sha else "DRIFT"
        if peer_sha != here_sha:
            drift = True
        print(f"peer  : {peer}  sha={peer_sha}  [{status}]")

    if drift:
        print("\nFAIL: _filters.py drift detected. Re-sync before committing.", file=sys.stderr)
        return 1
    print("\nOK: all _filters.py copies match.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
