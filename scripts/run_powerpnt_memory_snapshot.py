#!/usr/bin/env python3
"""Mac-side runner for the POWERPNT.exe userland minidump probe.

SENSITIVE: Memory dumps may contain decrypted credentials, license tokens,
           AI request bodies. Local Mac path only. Never push to git.
           Never paste content.

Behaviour:
  1. SSH-fires probe_powerpnt_memory_snapshot.ps1 on Windows-VM.
  2. Tells the user to switch to the VM and trigger a chart insertion right
     after the SSH command starts (the dump is taken instantly but heap
     content reflects the moment of capture).
  3. After the dump completes, ferries the .dmp via UNC to
     state/thinkcell_bridge/powerpnt_memdumps/<ts>/.
  4. --no-ferry keeps the dump only on the VM (privacy / size mode).

Pattern matches scripts/run_thinkcell_vm_native_auth_verify.py.
"""

from __future__ import annotations

import argparse
import base64
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROBE = ROOT / "scripts" / "probe_powerpnt_memory_snapshot.ps1"


def _to_unc(p: Path) -> str:
    r = p.expanduser().resolve()
    return r"\\Mac\Home" + "\\" + "\\".join(r.relative_to(Path.home().resolve()).parts)


def _build_ps_command(
    probe_unc: str,
    output_unc: str,
    dump_dir_vm: str,
    allow_large_dump: bool,
    dry_run: bool,
) -> str:
    parts = [
        '$ErrorActionPreference = "Stop"',
        '$ProgressPreference = "SilentlyContinue"',
        f'& "{probe_unc}" -OutputPath "{output_unc}" -DumpDir "{dump_dir_vm}"'
        + (" -AllowLargeDump" if allow_large_dump else "")
        + (" -DryRun" if dry_run else ""),
    ]
    return "\n".join(parts)


def _print_capture_banner(dump_dir_vm: str) -> None:
    print("=" * 72, file=sys.stderr)
    print("ATTENTION -- POWERPNT memory snapshot is firing now.", file=sys.stderr)
    print("Switch to the VM and trigger the chart insertion immediately.", file=sys.stderr)
    print(
        "MiniDumpWriteDump captures the heap at the moment it runs, so the",
        file=sys.stderr,
    )
    print("interesting buffers must be live in memory at that instant.", file=sys.stderr)
    print(f"Dump dir on VM: {dump_dir_vm}", file=sys.stderr)
    print("=" * 72, file=sys.stderr)


def _ferry_dump(host: str, dump_dir_vm_unc_for_mac: Path, dest_dir: Path) -> Path | None:
    r"""Best-effort ferry of powerpnt.dmp from the VM via SSH+SCP fallback.

    Tries UNC-via-Mac-share first (\\Mac\Home is the VM seeing the Mac), but
    the dump is on the VM, so the realistic path is SSH+scp.
    """
    dest_dir.mkdir(parents=True, exist_ok=True)
    local_path = dest_dir / "powerpnt.dmp"
    src = f"{host}:{str(dump_dir_vm_unc_for_mac).replace(chr(92), '/')}/powerpnt.dmp"
    r = subprocess.run(
        ["scp", "-q", "-o", "BatchMode=yes", "-o", "ConnectTimeout=8", src, str(local_path)],
        text=True,
        capture_output=True,
        timeout=600,
        check=False,
    )
    if r.returncode != 0:
        print(f"scp failed: {r.stderr[-2000:]}", file=sys.stderr)
        return None
    return local_path if local_path.exists() and local_path.stat().st_size > 0 else None


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--host", default="Windows-VM")
    p.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Path for the JSON sidecar (Mac side).",
    )
    p.add_argument(
        "--allow-large-dump",
        action="store_true",
        help="Proceed even if POWERPNT working set exceeds 1 GB.",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Do not call MiniDumpWriteDump; just emit pre-flight metadata.",
    )
    p.add_argument(
        "--no-ferry",
        action="store_true",
        help="Keep the .dmp on the VM only (privacy / size mode).",
    )
    p.add_argument(
        "--ssh-timeout",
        type=int,
        default=900,
        help="Total SSH timeout in seconds (dump+ferry can be slow).",
    )
    a = p.parse_args()

    ts = time.strftime("%Y%m%d-%H%M%S")
    out = a.output or (
        ROOT
        / "state"
        / "thinkcell_bridge"
        / "powerpnt_memdumps"
        / ts
        / "powerpnt_memory_snapshot.json"
    )
    out = out.expanduser().resolve()
    out.parent.mkdir(parents=True, exist_ok=True)

    # VM-side dump dir lives on $env:USERPROFILE (C:\Users\<user>\tc_memdump\<ts>).
    # We do not write the dump under \\Mac\Home -- the Mac share would round-trip
    # 200-500 MB across SMB during MiniDumpWriteDump and tank the host. Stage on
    # the VM, ferry afterwards.
    dump_dir_vm = rf"$env:USERPROFILE\tc_memdump\{ts}"

    probe_unc = _to_unc(PROBE)
    output_unc = _to_unc(out)
    ps = _build_ps_command(
        probe_unc=probe_unc,
        output_unc=output_unc,
        dump_dir_vm=dump_dir_vm,
        allow_large_dump=a.allow_large_dump,
        dry_run=a.dry_run,
    )
    enc = base64.b64encode(ps.encode("utf-16le")).decode("ascii")

    if not a.dry_run:
        _print_capture_banner(dump_dir_vm)

    r = subprocess.run(
        [
            "ssh",
            "-o",
            "BatchMode=yes",
            "-o",
            "ConnectTimeout=8",
            a.host,
            f"powershell -NoProfile -ExecutionPolicy Bypass -EncodedCommand {enc}",
        ],
        text=True,
        capture_output=True,
        timeout=a.ssh_timeout,
        check=False,
        cwd=ROOT,
    )
    if r.stderr.strip():
        print(r.stderr[-3000:], file=sys.stderr)
    if r.returncode != 0:
        raise SystemExit(r.returncode)
    if not out.exists() or out.stat().st_size == 0:
        raise SystemExit(f"output missing: {out}")

    print(f"wrote {out}")

    # Inspect verdict to decide whether to ferry.
    try:
        # PowerShell `Set-Content -Encoding UTF8` writes a UTF-8 BOM.
        sidecar = json.loads(out.read_text(encoding="utf-8-sig"))
    except Exception as e:  # noqa: BLE001
        print(f"could not parse sidecar JSON: {e}", file=sys.stderr)
        return 0

    verdict = (sidecar.get("verdict") or {}).get("status")
    if a.dry_run or a.no_ferry or verdict != "ok":
        if verdict and verdict != "ok":
            print(
                f"verdict={verdict} -- skipping ferry. message="
                f"{sidecar['verdict'].get('message', '')}",
                file=sys.stderr,
            )
        return 0

    # Ferry .dmp Mac-side.
    dump_path_vm = (sidecar.get("dump") or {}).get("path")
    if not dump_path_vm:
        print("no dump.path in sidecar; skipping ferry", file=sys.stderr)
        return 0
    dest_dir = out.parent
    print(f"ferrying {dump_path_vm} -> {dest_dir} ...", file=sys.stderr)
    local = _ferry_dump(a.host, Path(dump_path_vm), dest_dir)
    if local:
        print(f"ferried {local} ({local.stat().st_size / 1024 / 1024:.1f} MB)")
    else:
        print(
            "ferry failed -- dump remains on VM at " + dump_path_vm,
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
