#!/usr/bin/env python3
"""Drop a sentinel HTML into the OneDrive Sales Ops Briefs folder to verify
the Power Automate flow fires and posts to Teams self-chat.

Usage:
    python3 scripts/test_flow.py             # drop a sentinel
    python3 scripts/test_flow.py --cleanup   # remove flow-test-*.html older than 1h

See docs/POWER_AUTOMATE_FLOW_RUNBOOK.md for click-path + troubleshooting.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from datetime import datetime
from pathlib import Path

ONEDRIVE_FOLDER = Path.home() / "Library/CloudStorage/OneDrive-SimCorp/Sales Ops Briefs"


def _atomic_write(path: Path, body: str) -> None:
    """Write to .tmp then os.replace — same pattern as brief.py."""
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(body, encoding="utf-8")
    os.replace(tmp, path)


def drop_sentinel() -> Path:
    ONEDRIVE_FOLDER.mkdir(parents=True, exist_ok=True)
    ts = int(time.time())
    name = f"flow-test-{ts}.html"
    path = ONEDRIVE_FOLDER / name
    body = (
        "<!doctype html><html><head><meta charset='utf-8'>"
        f"<title>Flow test {ts}</title></head><body>"
        "<h1>Flow test</h1>"
        "<p>If you see this in Teams self-chat, the Power Automate flow "
        "is wired correctly.</p>"
        f"<p>Filename: <code>{name}</code></p>"
        f"<p>Dropped at: {datetime.now().isoformat(timespec='seconds')}</p>"
        "</body></html>"
    )
    _atomic_write(path, body)
    return path


def cleanup(max_age_seconds: int = 3600) -> int:
    if not ONEDRIVE_FOLDER.exists():
        return 0
    cutoff = time.time() - max_age_seconds
    removed = 0
    for f in ONEDRIVE_FOLDER.glob("flow-test-*.html"):
        try:
            if f.stat().st_mtime < cutoff or max_age_seconds == 0:
                f.unlink()
                removed += 1
        except OSError:
            continue
    return removed


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--cleanup",
        action="store_true",
        help="Remove flow-test-*.html files older than 1 hour and exit.",
    )
    ap.add_argument(
        "--cleanup-now",
        action="store_true",
        help="Remove ALL flow-test-*.html regardless of age (use after a manual test).",
    )
    args = ap.parse_args()

    if args.cleanup or args.cleanup_now:
        max_age = 0 if args.cleanup_now else 3600
        n = cleanup(max_age_seconds=max_age)
        print(f"Removed {n} flow-test-*.html file(s) from {ONEDRIVE_FOLDER}.")
        return 0

    path = drop_sentinel()
    print(
        f"Wrote sentinel: {path}. Watch your Teams self-chat for ~60s. "
        f"If nothing appears, see runbook §Troubleshooting "
        f"(docs/POWER_AUTOMATE_FLOW_RUNBOOK.md)."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
