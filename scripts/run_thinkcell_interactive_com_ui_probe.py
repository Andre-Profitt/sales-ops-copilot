#!/usr/bin/env python3
"""Run think-cell UI-only COM methods in the Windows console session."""

from __future__ import annotations

import argparse
import base64
import json
import subprocess
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
PROBE_PS1 = ROOT / "scripts" / "probe_thinkcell_interactive_com_ui.ps1"


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
    return subprocess.run(command, cwd=ROOT, text=True, capture_output=True, timeout=timeout)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="Windows-VM")
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--timeout-seconds", type=int, default=150)
    args = parser.parse_args()

    if args.output_dir is None:
        stamp = time.strftime("%Y%m%d-%H%M%S")
        output_dir = ROOT / "state" / "thinkcell_bridge" / "interactive_com_ui" / stamp
    else:
        output_dir = args.output_dir
    output_dir = output_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    remote_dir = r"C:\tcw\interactive_com_ui_probe"
    remote_script = remote_dir + r"\probe_thinkcell_interactive_com_ui.ps1"
    remote_wrapper = remote_dir + r"\run_probe.ps1"
    task_name = f"tc_interactive_com_ui_{int(time.time())}"
    json_path = output_dir / "thinkcell_interactive_com_ui.json"
    wrapper = f"& '{remote_script}' -OutputDir '{_to_unc(output_dir)}'\n"
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
        f"schtasks /Create /TN '{task_name}' /SC ONCE /ST $time /TR $tr /F /IT; "
        f"schtasks /Run /TN '{task_name}'"
    )
    result = _ssh(args.host, setup_ps, timeout=60)
    if result.stdout.strip():
        print(result.stdout[-3000:])
    if result.stderr.strip():
        print(result.stderr[-3000:])

    deadline = time.time() + args.timeout_seconds
    while time.time() < deadline:
        if json_path.exists() and json_path.stat().st_size > 0:
            break
        time.sleep(3)

    _ssh(args.host, f"schtasks /Delete /TN '{task_name}' /F 2>$null | Out-Null", timeout=30)

    if not json_path.exists() or json_path.stat().st_size == 0:
        raise SystemExit(f"interactive COM UI probe did not write JSON: {json_path}")

    data = json.loads(json_path.read_text(encoding="utf-8"))
    print(json_path)
    print(json.dumps(data.get("verdict", {}), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
