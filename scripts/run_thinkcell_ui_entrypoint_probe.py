#!/usr/bin/env python3
"""Run the disposable think-cell UI entrypoint probe on Windows-VM."""

from __future__ import annotations

import argparse
import base64
import subprocess
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
PROBE_PS1 = ROOT / "scripts" / "probe_thinkcell_ui_entrypoints.ps1"


def _to_unc(path: Path) -> str:
    resolved = path.expanduser().resolve()
    home = Path.home().resolve()
    return r"\\Mac\Home" + "\\" + "\\".join(resolved.relative_to(home).parts)


def _encoded_powershell(script: str) -> str:
    return base64.b64encode(script.encode("utf-16le")).decode("ascii")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="Windows-VM")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    if not PROBE_PS1.exists():
        raise SystemExit(f"missing probe script: {PROBE_PS1}")

    output = args.output
    if output is None:
        stamp = time.strftime("%Y%m%d-%H%M%S")
        output = (
            ROOT
            / "state"
            / "thinkcell_bridge"
            / "hidden_surface"
            / stamp
            / "thinkcell_ui_entrypoint_probe.json"
        )
    output = output.expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)

    ps = (
        '$ErrorActionPreference = "Stop"; '
        '$ProgressPreference = "SilentlyContinue"; '
        f'& "{_to_unc(PROBE_PS1)}" -OutputPath "{_to_unc(output)}"'
    )
    encoded = _encoded_powershell(ps)
    command = [
        "ssh",
        "-o",
        "BatchMode=yes",
        "-o",
        "ConnectTimeout=8",
        args.host,
        f"powershell -NoProfile -ExecutionPolicy Bypass -EncodedCommand {encoded}",
    ]
    print("+ " + " ".join(command), flush=True)
    result = subprocess.run(
        command,
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
        timeout=90,
    )
    if result.stdout.strip():
        print(result.stdout[-6000:])
    if result.stderr.strip():
        print(result.stderr[-6000:], file=sys.stderr)
    if result.returncode != 0:
        raise SystemExit(result.returncode)
    if not output.exists() or output.stat().st_size == 0:
        raise SystemExit(f"probe did not write output: {output}")
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
