#!/usr/bin/env python3
"""
Bridge: sales-ops-copilot trends.json → brand-deck-agent-py /api/generate-land-deck.

Connects Plan A's per-director output to Plan B's endpoint without Power Automate.
For local manual validation against `func host start` or against the deployed
`func-simcorp-deckgen-dev` Function App.

Usage:
    # Against local Functions runtime (default)
    python3 scripts/run_land_to_deck.py --director "Adam Steinhouse" --period 2026-Q2

    # Against the deployed Function
    python3 scripts/run_land_to_deck.py --director "Adam Steinhouse" --period 2026-Q2 \\
        --endpoint https://func-simcorp-deckgen-dev.azurewebsites.net

    # Skip the land_brief regeneration; reuse whatever's at state/<period>/<director>/trends.json
    python3 scripts/run_land_to_deck.py --director "Adam Steinhouse" --period 2026-Q2 --skip-regen

The script does NOT POST to remote SharePoint or send email — that's Plan C territory.
It downloads the PPTX locally for inspection.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib
import subprocess
import sys
import time

import requests

ROOT = pathlib.Path(__file__).resolve().parent.parent
STATE_DIR = ROOT / "state"
DEFAULT_ENDPOINT = "http://localhost:7071"
POLL_INTERVAL_S = 5
POLL_TIMEOUT_S = 600  # 10 minutes


def ensure_trends_json(director: str, period: str, *, skip_regen: bool) -> pathlib.Path:
    director_slug = director.replace(" ", "-")
    trends_path = STATE_DIR / period / director_slug / "trends.json"

    if trends_path.exists() and skip_regen:
        print(f"→ Reusing existing {trends_path}")
        return trends_path

    print(f"→ Running land_brief.py for {director} {period}...")
    venv_python = ROOT / ".venv" / "bin" / "python3"
    if not venv_python.exists():
        venv_python = pathlib.Path(sys.executable)
    p = subprocess.run(
        [
            str(venv_python),
            str(ROOT / "scripts" / "land_brief.py"),
            "--director",
            director,
            "--period",
            period,
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if p.returncode != 0:
        print(f"land_brief.py failed:\n{p.stderr}", file=sys.stderr)
        sys.exit(2)
    if not trends_path.exists():
        print(f"land_brief.py ran but did not produce {trends_path}", file=sys.stderr)
        sys.exit(2)
    print(f"  Wrote {trends_path}")
    return trends_path


def post_envelope(endpoint: str, trends: dict) -> str:
    url = f"{endpoint.rstrip('/')}/api/generate-land-deck"
    print(f"→ POST {url}")
    resp = requests.post(url, json=trends, timeout=30)
    if resp.status_code == 400:
        print("  HTTP 400 — envelope rejected by Pydantic validation:", file=sys.stderr)
        print(f"  {resp.text[:1000]}", file=sys.stderr)
        sys.exit(2)
    if resp.status_code != 202:
        print(f"  Unexpected status {resp.status_code}: {resp.text[:500]}", file=sys.stderr)
        sys.exit(2)
    job_id = resp.json()["jobId"]
    print(f"  jobId: {job_id}")
    return job_id


def poll_until_done(endpoint: str, job_id: str) -> dict:
    url = f"{endpoint.rstrip('/')}/api/generate-status?jobId={job_id}"
    started = time.time()
    last_status = None
    while time.time() - started < POLL_TIMEOUT_S:
        resp = requests.get(url, timeout=15)
        if resp.status_code != 200:
            print(f"  status poll returned {resp.status_code}: {resp.text[:300]}", file=sys.stderr)
            time.sleep(POLL_INTERVAL_S)
            continue
        data = resp.json()
        status = data.get("status")
        if status != last_status:
            elapsed = int(time.time() - started)
            print(f"  [{elapsed:3d}s] status: {status}")
            last_status = status
        if status == "complete":
            return data
        if status == "error":
            print(f"  endpoint reported error: {data.get('error', '(no detail)')}", file=sys.stderr)
            sys.exit(2)
        time.sleep(POLL_INTERVAL_S)
    print(f"  poll timeout after {POLL_TIMEOUT_S}s", file=sys.stderr)
    sys.exit(2)


def download_pptx(download_url: str, out_path: pathlib.Path) -> None:
    print(f"→ Downloading {download_url[:80]}...")
    resp = requests.get(download_url, timeout=60)
    resp.raise_for_status()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(resp.content)
    print(f"  Wrote {out_path} ({len(resp.content):,} bytes)")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--director", required=True, help="e.g., 'Adam Steinhouse'")
    ap.add_argument("--period", required=True, help="e.g., '2026-Q2'")
    ap.add_argument(
        "--endpoint",
        default=DEFAULT_ENDPOINT,
        help=f"Base URL of the Function App (default: {DEFAULT_ENDPOINT})",
    )
    ap.add_argument(
        "--skip-regen",
        action="store_true",
        help="Reuse existing trends.json instead of re-running land_brief.py",
    )
    args = ap.parse_args()

    trends_path = ensure_trends_json(args.director, args.period, skip_regen=args.skip_regen)
    trends = json.loads(trends_path.read_text())

    job_id = post_envelope(args.endpoint, trends)
    final = poll_until_done(args.endpoint, job_id)

    download_url = final.get("downloadUrl") or final.get("download_url")
    if not download_url:
        print(f"  status=complete but no downloadUrl in response: {final}", file=sys.stderr)
        return 2

    director_slug = args.director.replace(" ", "-")
    out_path = trends_path.parent / f"{director_slug}-{args.period}-LAND.pptx"
    download_pptx(download_url, out_path)

    print()
    print("Summary:")
    print(f"  Quality:  {final.get('qualityScore')}/100  ({final.get('qualityGrade', '?')})")
    print(f"  Slides:   {final.get('slideCount')}")
    print(f"  PPTX:     {out_path}")
    print(f"  jobId:    {job_id}")
    print(f"  ts:       {dt.datetime.now().isoformat(timespec='seconds')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
