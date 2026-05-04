#!/usr/bin/env python3
"""Run the think-cell COM registry/OleView-lite probe on the Windows VM."""

from __future__ import annotations

import argparse
import base64
import subprocess
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
PROBE_PS1 = ROOT / "scripts" / "probe_thinkcell_com_registry.ps1"


def _to_unc(path: Path) -> str:
    resolved = path.expanduser().resolve()
    home = Path.home().resolve()
    return r"\\Mac\Home" + "\\" + "\\".join(resolved.relative_to(home).parts)


def _encoded_powershell(script: str) -> str:
    return base64.b64encode(script.encode("utf-16le")).decode("ascii")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="Windows-VM")
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()

    if not PROBE_PS1.exists():
        raise SystemExit(f"missing probe script: {PROBE_PS1}")

    output_dir = args.output_dir
    if output_dir is None:
        stamp = time.strftime("%Y%m%d-%H%M%S")
        output_dir = ROOT / "state" / "thinkcell_bridge" / "com_registry" / stamp
    output_dir = output_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    ps = (
        '$ErrorActionPreference = "Stop"; '
        '$ProgressPreference = "SilentlyContinue"; '
        f'& "{_to_unc(PROBE_PS1)}" -OutputDir "{_to_unc(output_dir)}"'
    )
    command = [
        "ssh",
        "-o",
        "BatchMode=yes",
        "-o",
        "ConnectTimeout=8",
        args.host,
        "powershell -NoProfile -ExecutionPolicy Bypass "
        f"-EncodedCommand {_encoded_powershell(ps)}",
    ]
    print("+ " + " ".join(command), flush=True)
    result = subprocess.run(
        command,
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
        timeout=300,
    )
    if result.stdout.strip():
        print(result.stdout[-12000:])
    if result.stderr.strip():
        print(result.stderr[-8000:], file=sys.stderr)
    if result.returncode != 0:
        raise SystemExit(result.returncode)

    json_path = output_dir / "thinkcell_com_registry_probe.json"
    if not json_path.exists() or json_path.stat().st_size == 0:
        raise SystemExit(f"probe did not write JSON: {json_path}")
    print(json_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
