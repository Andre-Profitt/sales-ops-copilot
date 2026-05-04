#!/usr/bin/env python3
"""Run the think-cell interactive UI probe in the Windows console session."""

from __future__ import annotations

import argparse
import base64
import json
import subprocess
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
PROBE_PS1 = ROOT / "scripts" / "probe_thinkcell_interactive_ui_path.ps1"


def _to_unc(path: Path) -> str:
    resolved = path.expanduser().resolve()
    home = Path.home().resolve()
    return r"\\Mac\Home" + "\\" + "\\".join(resolved.relative_to(home).parts)


def _encoded_powershell(script: str) -> str:
    return base64.b64encode(script.encode("utf-16le")).decode("ascii")


def _ssh(host: str, ps: str, timeout: int = 120) -> subprocess.CompletedProcess[str]:
    command = [
        "ssh",
        "-o",
        "BatchMode=yes",
        "-o",
        "ConnectTimeout=8",
        host,
        "powershell -NoProfile -ExecutionPolicy Bypass "
        f"-EncodedCommand {_encoded_powershell(ps)}",
    ]
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
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--try-invoke", action="store_true")
    parser.add_argument("--timeout-seconds", type=int, default=180)
    args = parser.parse_args()

    if not PROBE_PS1.exists():
        raise SystemExit(f"missing probe script: {PROBE_PS1}")

    output_dir = args.output_dir
    if output_dir is None:
        stamp = time.strftime("%Y%m%d-%H%M%S")
        output_dir = ROOT / "state" / "thinkcell_bridge" / "interactive_ui" / stamp
    output_dir = output_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    remote_dir = r"C:\tcw\interactive_ui_probe"
    remote_script = remote_dir + r"\probe_thinkcell_interactive_ui_path.ps1"
    remote_wrapper = remote_dir + r"\run_probe.ps1"
    task_name = f"tc_interactive_ui_probe_{int(time.time())}"
    marker = output_dir / "task_created.txt"
    json_path = output_dir / "thinkcell_interactive_ui_path.json"
    try_invoke = " -TryInvoke" if args.try_invoke else ""
    wrapper = (
        "$ErrorActionPreference='Continue'\n"
        f"& '{remote_script}' -OutputDir '{_to_unc(output_dir)}'{try_invoke}\n"
    )
    wrapper_b64 = base64.b64encode(wrapper.encode("utf-16le")).decode("ascii")

    setup_ps = (
        "$ErrorActionPreference='Stop'; "
        f"New-Item -ItemType Directory -Path '{remote_dir}' -Force | Out-Null; "
        f"Copy-Item -LiteralPath '{_to_unc(PROBE_PS1)}' -Destination '{remote_script}' -Force; "
        f"[System.IO.File]::WriteAllText('{remote_wrapper}', "
        f"[System.Text.Encoding]::Unicode.GetString([Convert]::FromBase64String('{wrapper_b64}')), "
        "[System.Text.Encoding]::Unicode); "
        "$time=(Get-Date).AddMinutes(1).ToString('HH:mm'); "
        "$tr="
        f"\"powershell.exe -WindowStyle Hidden -NoProfile -ExecutionPolicy Bypass -File '{remote_wrapper}'\"; "
        f"schtasks /Create /TN '{task_name}' /SC ONCE /ST $time /TR $tr /F /IT | Out-String | "
        f"Set-Content -LiteralPath '{_to_unc(marker)}'; "
        f"schtasks /Run /TN '{task_name}' | Out-String"
    )
    result = _ssh(args.host, setup_ps, timeout=60)
    if result.stdout.strip():
        print(result.stdout[-4000:])
    if result.stderr.strip():
        print(result.stderr[-4000:], file=sys.stderr)
    if result.returncode != 0:
        raise SystemExit(result.returncode)

    deadline = time.time() + args.timeout_seconds
    while time.time() < deadline:
        if json_path.exists() and json_path.stat().st_size > 0:
            break
        time.sleep(3)

    cleanup_ps = f"schtasks /Delete /TN '{task_name}' /F 2>$null | Out-Null"
    _ssh(args.host, cleanup_ps, timeout=30)

    if not json_path.exists() or json_path.stat().st_size == 0:
        status_ps = (
            f"schtasks /Query /TN '{task_name}' /V /FO LIST 2>$null; "
            "Get-Process POWERPNT -ErrorAction SilentlyContinue | "
            "Select ProcessName,Id,SessionId,MainWindowTitle | ConvertTo-Json -Compress"
        )
        status = _ssh(args.host, status_ps, timeout=30)
        if status.stdout.strip():
            print(status.stdout[-4000:])
        raise SystemExit(f"interactive probe did not write JSON: {json_path}")

    data = json.loads(json_path.read_text(encoding="utf-8"))
    verdict = data.get("verdict", {})
    print(json_path)
    print(json.dumps(verdict, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
