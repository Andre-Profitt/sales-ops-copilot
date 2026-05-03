#!/usr/bin/env python3
"""Run a disposable dynamic trace of think-cell UI-only creation paths."""

from __future__ import annotations

import argparse
import base64
import subprocess
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
TRACE_PS1 = ROOT / "scripts" / "trace_thinkcell_ui_creation.ps1"


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

    if not TRACE_PS1.exists():
        raise SystemExit(f"missing trace script: {TRACE_PS1}")

    output_dir = args.output_dir
    if output_dir is None:
        stamp = time.strftime("%Y%m%d-%H%M%S")
        output_dir = ROOT / "state" / "thinkcell_bridge" / "dynamic_trace" / stamp
    output_dir = output_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    ps = (
        '$ErrorActionPreference = "Stop"; '
        '$ProgressPreference = "SilentlyContinue"; '
        f'& "{_to_unc(TRACE_PS1)}" -OutputDir "{_to_unc(output_dir)}"'
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
        timeout=240,
    )
    if result.stdout.strip():
        print(result.stdout[-8000:])
    if result.stderr.strip():
        print(result.stderr[-8000:], file=sys.stderr)
    if result.returncode != 0:
        raise SystemExit(result.returncode)

    json_path = output_dir / "thinkcell_ui_dynamic_trace.json"
    if not json_path.exists() or json_path.stat().st_size == 0:
        raise SystemExit(f"trace did not write JSON: {json_path}")
    print(json_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
