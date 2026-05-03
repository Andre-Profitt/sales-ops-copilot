#!/usr/bin/env python3
"""Run the tc_com_driver VM smoke test on Windows-VM.

Pre-conditions on VM (Andre's interactive desktop session):
- PowerPoint open
- think-cell ribbon visible (add-in active)
- An empty .pptx is fine

This wrapper SSH-fires the PowerShell probe, ferries the JSON verdict back,
and prints the summary. Mirrors the existing run_thinkcell_*_probe.py pattern.
"""

from __future__ import annotations

import argparse
import base64
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROBE = ROOT / "scripts" / "probe_tc_com_driver_vm_smoke.ps1"


def _to_unc(p: Path) -> str:
    r = p.expanduser().resolve()
    return r"\\Mac\Home" + "\\" + "\\".join(r.relative_to(Path.home().resolve()).parts)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--host", default="Windows-VM")
    p.add_argument("--output", type=Path, default=None)
    p.add_argument("--ssh-timeout", type=int, default=180)
    a = p.parse_args()

    out = a.output or (
        ROOT
        / "state"
        / "thinkcell_bridge"
        / "tc_com_driver_vm_smoke"
        / time.strftime("%Y%m%d-%H%M%S")
        / "vm_smoke.json"
    )
    out = out.expanduser().resolve()
    out.parent.mkdir(parents=True, exist_ok=True)

    ps = "\n".join(
        [
            '$ErrorActionPreference = "Continue"',
            '$ProgressPreference = "SilentlyContinue"',
            f'& "{_to_unc(PROBE)}" -OutputPath "{_to_unc(out)}"',
        ]
    )
    enc = base64.b64encode(ps.encode("utf-16le")).decode("ascii")

    print(f"[runner] firing on {a.host} (timeout {a.ssh_timeout}s)")
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
        timeout=a.ssh_timeout,
        check=False,
    )

    if r.stderr.strip():
        print(r.stderr[-3000:], file=sys.stderr)
    print(r.stdout[-3000:])

    if not out.exists() or out.stat().st_size == 0:
        print(f"[runner] output missing: {out}", file=sys.stderr)
        return 1

    state = json.loads(out.read_text(encoding="utf-8-sig"))
    print()
    print("=== VERDICT ===")
    for k in (
        "overall_verdict",
        "python_ok",
        "pywin32_ok",
        "tc_com_driver_install_ok",
        "powerpoint_running",
        "powerpoint_pid",
        "thinkcell_addin_found",
        "thinkcell_addin_progid",
        "pytest_ran",
        "pytest_passed",
        "pytest_failed",
    ):
        print(f"  {k}: {state.get(k)}")
    print()
    print(f"output: {out}")

    if state.get("overall_verdict") == "smoke_passed":
        return 0
    return r.returncode or 1


if __name__ == "__main__":
    sys.exit(main())
