#!/usr/bin/env python3
"""Run the think-cell clipboard-format dump probe.

Interactive-only: requires a desktop session on the VM where a think-cell
chart has been copied to the clipboard. SSH non-interactive sessions cannot
access the clipboard. The probe will return an explicit error in that case
when --require-interactive is set.

Usage on the VM (interactive):

  1. Open PowerPoint, place a think-cell chart, Ctrl+C
  2. Open PowerShell on the VM console (not via SSH)
  3. Run: powershell -ExecutionPolicy Bypass -File <path>\\probe_thinkcell_clipboard.ps1 -OutputPath <out.json>

This Python wrapper is provided as a thin runner for completeness; the
expected operational pattern is human-driven on the VM console.
"""

from __future__ import annotations

import argparse
import base64
import subprocess
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
PROBE_PS1 = ROOT / "scripts" / "probe_thinkcell_clipboard.ps1"


def _to_unc(path: Path) -> str:
    resolved = path.expanduser().resolve()
    home = Path.home().resolve()
    rel = resolved.relative_to(home)
    return r"\\Mac\Home" + "\\" + "\\".join(rel.parts)


def _encoded_powershell(script: str) -> str:
    return base64.b64encode(script.encode("utf-16le")).decode("ascii")


def _run(command: list[str], *, timeout: int = 180) -> subprocess.CompletedProcess[str]:
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
        "--require-interactive",
        action="store_true",
        help="Refuse to run in non-interactive SSH session (recommended).",
    )
    parser.add_argument(
        "--print-runbook",
        action="store_true",
        help="Print the manual runbook (interactive desktop) and exit.",
    )
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
            / "clipboard"
            / stamp
            / "thinkcell_clipboard_probe.json"
        )
    output = output.expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    dump_dir = output.parent / "dumps"

    if args.print_runbook:
        print(
            "Manual runbook (interactive desktop on Windows VM):\n"
            "  1. Open PowerPoint on the VM console.\n"
            "  2. Insert or open a slide with a think-cell chart.\n"
            "  3. Click the chart, Ctrl+A, Ctrl+C (or right-click > Copy).\n"
            "  4. Open PowerShell on the VM console (NOT via SSH).\n"
            f"  5. Run:\n"
            f"     powershell -ExecutionPolicy Bypass -File "
            f'"{_to_unc(PROBE_PS1)}" '
            f'-OutputPath "{_to_unc(output)}" '
            f'-DumpDir "{_to_unc(dump_dir)}" '
            f"-RequireInteractive\n"
            "  6. The JSON + dumped clipboard formats land back on the Mac via Mac Home share.\n"
            "\n"
            "Why interactive: the Win32 clipboard requires a desktop window station + interactive\n"
            "user. SSH sessions on Windows run in service-like sessions with no clipboard access.\n"
        )
        return 0

    require_flag = "-RequireInteractive" if args.require_interactive else ""
    ps = "\n".join(
        [
            '$ErrorActionPreference = "Stop"',
            '$ProgressPreference = "SilentlyContinue"',
            (
                f'& "{_to_unc(PROBE_PS1)}" '
                f'-OutputPath "{_to_unc(output)}" '
                f'-DumpDir "{_to_unc(dump_dir)}" {require_flag}'
            ).strip(),
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
        timeout=300,
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
    print(
        "\nNote: if running over SSH non-interactive, expected result is an empty/error JSON\n"
        "with `session.is_console = false`. Use --print-runbook for the manual desktop pattern.",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
