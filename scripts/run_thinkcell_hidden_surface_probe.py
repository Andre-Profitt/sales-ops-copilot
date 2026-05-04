#!/usr/bin/env python3
"""Run the think-cell hidden-surface probe on the Windows VM."""

from __future__ import annotations

import argparse
import base64
import subprocess
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
PROBE_PS1 = ROOT / "scripts" / "probe_thinkcell_hidden_surface.ps1"


def _to_unc(path: Path) -> str:
    resolved = path.expanduser().resolve()
    home = Path.home().resolve()
    rel = resolved.relative_to(home)
    return r"\\Mac\Home" + "\\" + "\\".join(rel.parts)


def _encoded_powershell(script: str) -> str:
    return base64.b64encode(script.encode("utf-16le")).decode("ascii")


def _run(command: list[str], *, timeout: int = 300) -> subprocess.CompletedProcess[str]:
    print("+ " + " ".join(command), flush=True)
    return subprocess.run(
        command,
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
        timeout=timeout,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="Windows-VM")
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Local output JSON. Defaults under state/thinkcell_bridge/hidden_surface/.",
    )
    parser.add_argument("--max-binary-strings", type=int, default=600)
    parser.add_argument("--max-dispatch-candidates", type=int, default=1200)
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
            / "thinkcell_hidden_surface_probe.json"
        )
    output = output.expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)

    ps = "\n".join(
        [
            '$ErrorActionPreference = "Stop"',
            '$ProgressPreference = "SilentlyContinue"',
            f'& "{_to_unc(PROBE_PS1)}" '
            f'-OutputPath "{_to_unc(output)}" '
            f"-MaxBinaryStrings {args.max_binary_strings} "
            f"-MaxDispatchCandidates {args.max_dispatch_candidates}",
        ]
    )
    encoded = _encoded_powershell(ps)
    result = _run(
        [
            "ssh",
            "-o",
            "BatchMode=yes",
            "-o",
            "ConnectTimeout=8",
            args.host,
            f"powershell -NoProfile -ExecutionPolicy Bypass -EncodedCommand {encoded}",
        ],
        timeout=420,
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
