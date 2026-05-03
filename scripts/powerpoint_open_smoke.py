#!/usr/bin/env python3
"""Verify a PPTX opens in Windows PowerPoint via COM."""

from __future__ import annotations

import argparse
import base64
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
OPEN_SMOKE_SCRIPT = ROOT / "_windows_test" / "open_pptx_smoke.ps1"


def _to_unc(path: Path) -> str:
    resolved = path.expanduser().resolve()
    home = Path.home().resolve()
    rel = resolved.relative_to(home)
    return r"\\Mac\Home" + "\\" + "\\".join(rel.parts)


def _run(command: list[str]) -> subprocess.CompletedProcess[str]:
    print("+ " + " ".join(command), flush=True)
    return subprocess.run(command, cwd=ROOT, text=True, capture_output=True, check=False)


def _encoded_powershell(script: str) -> str:
    return base64.b64encode(script.encode("utf-16le")).decode("ascii")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pptx", type=Path)
    parser.add_argument("--host", default="Windows-VM")
    args = parser.parse_args()

    pptx = args.pptx.expanduser().resolve()
    if not pptx.exists() or pptx.stat().st_size == 0:
        raise SystemExit(f"missing or empty deck: {pptx}")
    if not OPEN_SMOKE_SCRIPT.exists():
        raise SystemExit(f"missing smoke script: {OPEN_SMOKE_SCRIPT}")

    copy_result = _run(["scp", str(OPEN_SMOKE_SCRIPT), f"{args.host}:C:/tcw/open_pptx_smoke.ps1"])
    if copy_result.returncode != 0:
        raise SystemExit(copy_result.stderr or copy_result.stdout or "failed to copy open smoke script")

    deck = _to_unc(pptx)
    script = (
        '$ErrorActionPreference = "Stop"; '
        '$ProgressPreference = "SilentlyContinue"; '
        f'$deck = "{deck}"; '
        '& "C:\\tcw\\open_pptx_smoke.ps1" -DeckPath $deck'
    )
    encoded = _encoded_powershell(script)
    result = _run(
        [
            "ssh",
            args.host,
            f"powershell -NoProfile -ExecutionPolicy Bypass -EncodedCommand {encoded}",
        ]
    )
    output = "\n".join(part for part in (result.stdout.strip(), result.stderr.strip()) if part)
    if output:
        print(output)
    if result.returncode != 0:
        raise SystemExit(result.returncode)
    if "slides=" not in result.stdout:
        raise SystemExit("PowerPoint open smoke did not report slide count")
    return 0


if __name__ == "__main__":
    sys.exit(main())
