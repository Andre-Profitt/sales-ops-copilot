r"""Run think-cell .ppttc generation on the local Windows VM.

The bridge uses the Parallels Mac share (``\\Mac\Home``) to stage inputs into
``C:\tcw`` on the VM, runs Windows-only ``ppttc.exe``, and copies the output
PPTX back to macOS. It is the automation transport; the template still must
contain real named think-cell elements.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import time
import uuid
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_HOST = "Windows-VM"
DEFAULT_REMOTE_DIR = r"C:\tcw\sales-ops-copilot-thinkcell"
BRIDGE_PS1 = ROOT / "scripts" / "thinkcell_windows_bridge.ps1"


def _ps_quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _windows_name(path: Path) -> str:
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", path.name)
    if not safe:
        raise SystemExit(f"Cannot derive a Windows-safe file name for {path}")
    return safe


def _to_unc(path: Path) -> str:
    resolved = path.expanduser().resolve()
    home = Path.home().resolve()
    try:
        rel = resolved.relative_to(home)
    except ValueError as exc:
        raise SystemExit(
            f"{resolved} is outside {home}; this wrapper stages files through \\\\Mac\\Home."
        ) from exc
    return r"\\Mac\Home" + "\\" + "\\".join(rel.parts)


def _run_ssh(host: str, command: str) -> None:
    completed = subprocess.run(["ssh", host, command], text=True)
    if completed.returncode != 0:
        raise SystemExit(completed.returncode)


def _write_stage_script(
    *,
    ppttc: Path,
    template: Path,
    output: Path,
    host_output: str,
    remote_dir: str,
    expect_text: list[str],
    stage_dir: Path,
) -> Path:
    timestamp = time.strftime("%Y%m%d-%H%M%S")
    stage_path = stage_dir / f"thinkcell_bridge_{timestamp}_{uuid.uuid4().hex[:8]}.ps1"
    stage_dir.mkdir(parents=True, exist_ok=True)

    remote_bridge = remote_dir + r"\thinkcell_windows_bridge.ps1"
    remote_ppttc = remote_dir + "\\" + _windows_name(ppttc)
    remote_template = remote_dir + "\\" + _windows_name(template)
    remote_output = remote_dir + "\\" + host_output

    expect_line = ""
    output_line_suffix = ""
    if expect_text:
        expect_array = "@(" + ", ".join(_ps_quote(item) for item in expect_text) + ")"
        output_line_suffix = " `"
        expect_line = f"    -ExpectText {expect_array}\n"
    stage = f"""$ErrorActionPreference = "Stop"
$remoteDir = {_ps_quote(remote_dir)}
New-Item -ItemType Directory -Path $remoteDir -Force | Out-Null
Copy-Item -LiteralPath {_ps_quote(_to_unc(BRIDGE_PS1))} -Destination {_ps_quote(remote_bridge)} -Force
Copy-Item -LiteralPath {_ps_quote(_to_unc(ppttc))} -Destination {_ps_quote(remote_ppttc)} -Force
Copy-Item -LiteralPath {_ps_quote(_to_unc(template))} -Destination {_ps_quote(remote_template)} -Force
& {_ps_quote(remote_bridge)} `
    -PpttcPath {_ps_quote(remote_ppttc)} `
    -TemplatePath {_ps_quote(remote_template)} `
    -OutputPptx {_ps_quote(remote_output)}{output_line_suffix}
{expect_line}
Copy-Item -LiteralPath {_ps_quote(remote_output)} -Destination {_ps_quote(_to_unc(output))} -Force
"""
    stage_path.write_text(stage)
    return stage_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Run think-cell ppttc.exe on Windows-VM.")
    parser.add_argument("--host", default=DEFAULT_HOST, help="SSH host for the Windows VM.")
    parser.add_argument("--remote-dir", default=DEFAULT_REMOTE_DIR, help="Windows staging folder.")
    parser.add_argument("--ppttc", type=Path, required=True, help="Local .ppttc input.")
    parser.add_argument("--template", type=Path, required=True, help="Local wired PPTX template.")
    parser.add_argument("--output", type=Path, required=True, help="Local output PPTX path.")
    parser.add_argument(
        "--expect-text",
        action="append",
        default=[],
        help="Text that must appear in the generated PPTX XML. Repeatable.",
    )
    args = parser.parse_args()

    ppttc = args.ppttc.expanduser().resolve()
    template = args.template.expanduser().resolve()
    output = args.output.expanduser().resolve()
    for label, path in ((".ppttc", ppttc), ("template", template), ("bridge", BRIDGE_PS1)):
        if not path.exists():
            raise SystemExit(f"{label} not found: {path}")

    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        output.unlink()

    remote_root = args.remote_dir.rstrip("\\/")
    run_remote_dir = remote_root + "\\" + f"run-{time.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:8]}"

    stage_path = _write_stage_script(
        ppttc=ppttc,
        template=template,
        output=output,
        host_output=_windows_name(output),
        remote_dir=run_remote_dir,
        expect_text=args.expect_text,
        stage_dir=ROOT / "state" / "thinkcell_bridge",
    )
    stage_unc = _to_unc(stage_path)
    remote_command = f'powershell -NoProfile -ExecutionPolicy Bypass -File "{stage_unc}"'

    print(f"staging script: {stage_path}", flush=True)
    print(f"remote staging dir: {run_remote_dir}", flush=True)
    _run_ssh(args.host, remote_command)

    if not output.exists() or output.stat().st_size == 0:
        raise SystemExit(f"Windows bridge finished but output is missing or empty: {output}")
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
