#!/usr/bin/env python3
"""Run advanced runtime PS probe on Windows VM."""

from __future__ import annotations
import argparse
import base64
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROBE_PS1 = ROOT / "scripts" / "probe_thinkcell_advanced_runtime.ps1"


def _to_unc(p):
    r = p.expanduser().resolve()
    return r"\\Mac\Home" + "\\" + "\\".join(r.relative_to(Path.home().resolve()).parts)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--host", default="Windows-VM")
    p.add_argument("--output", type=Path, default=None)
    p.add_argument("--deck", type=Path, default=None)
    a = p.parse_args()
    out = a.output or (
        ROOT
        / "state"
        / "thinkcell_bridge"
        / "advanced_runtime"
        / time.strftime("%Y%m%d-%H%M%S")
        / "advanced_runtime_probe.json"
    )
    out = out.expanduser().resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    deck_arg = ""
    if a.deck:
        deck_arg = f' -DeckPath "{_to_unc(a.deck.expanduser().resolve())}"'
    ps = "\n".join(
        [
            '$ErrorActionPreference = "Stop"',
            '$ProgressPreference = "SilentlyContinue"',
            f'& "{_to_unc(PROBE_PS1)}" -OutputPath "{_to_unc(out)}"' + deck_arg,
        ]
    )
    enc = base64.b64encode(ps.encode("utf-16le")).decode("ascii")
    r = subprocess.run(
        [
            "ssh",
            "-o",
            "BatchMode=yes",
            "-o",
            "ConnectTimeout=8",
            a.host,
            f"powershell -NoProfile -ExecutionPolicy Bypass -EncodedCommand {enc}",
        ],
        text=True,
        capture_output=True,
        timeout=600,
        check=False,
        cwd=ROOT,
    )
    if r.stderr.strip():
        print(r.stderr[-3000:], file=sys.stderr)
    if r.returncode != 0:
        raise SystemExit(r.returncode)
    if not out.exists() or out.stat().st_size == 0:
        raise SystemExit(f"output missing: {out}")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
