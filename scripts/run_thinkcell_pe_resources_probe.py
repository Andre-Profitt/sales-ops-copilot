#!/usr/bin/env python3
"""Run the think-cell PE-resource enumeration probe on the Windows VM.

Dumps every PE resource (RT_RCDATA, RT_HTML, etc.) from tcaddin.dll plus
sibling binaries under <output_dir>/dumps/<binary>/, with structured
metadata in the JSON output.
"""

from __future__ import annotations

import argparse
import base64
import subprocess
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
PROBE_PS1 = ROOT / "scripts" / "probe_thinkcell_pe_resources.ps1"


def _to_unc(path: Path) -> str:
    resolved = path.expanduser().resolve()
    home = Path.home().resolve()
    rel = resolved.relative_to(home)
    return r"\\Mac\Home" + "\\" + "\\".join(rel.parts)


def _encoded_powershell(script: str) -> str:
    return base64.b64encode(script.encode("utf-16le")).decode("ascii")


def _run(command: list[str], *, timeout: int = 600) -> subprocess.CompletedProcess[str]:
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
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument(
        "--dll-path",
        default=r"C:\Program Files (x86)\think-cell\arm64\tcaddin.dll",
        help="Primary DLL to enumerate. Sibling binaries are auto-discovered.",
    )
    parser.add_argument("--max-per-type", type=int, default=100)
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
            / "pe_resources"
            / stamp
            / "thinkcell_pe_resources_probe.json"
        )
    output = output.expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    dump_dir = output.parent / "dumps"

    ps = "\n".join(
        [
            '$ErrorActionPreference = "Stop"',
            '$ProgressPreference = "SilentlyContinue"',
            (
                f'& "{_to_unc(PROBE_PS1)}" '
                f'-OutputPath "{_to_unc(output)}" '
                f'-DllPath "{args.dll_path}" '
                f'-DumpDir "{_to_unc(dump_dir)}" '
                f"-MaxResourcesPerType {args.max_per_type}"
            ),
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
        timeout=720,
    )
    if result.stdout.strip():
        print(result.stdout[-6000:])
    if result.stderr.strip():
        print(result.stderr[-6000:], file=sys.stderr)
    if result.returncode != 0:
        raise SystemExit(result.returncode)
    if not output.exists() or output.stat().st_size == 0:
        raise SystemExit(f"probe completed but output missing: {output}")
    print(f"\nwrote {output}", flush=True)
    if dump_dir.exists():
        dumps = list(dump_dir.rglob("*"))
        print(f"resource dumps: {len([d for d in dumps if d.is_file()])} files in {dump_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
