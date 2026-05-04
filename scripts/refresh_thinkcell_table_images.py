"""Dispatch Excel COM AddRangeImage refresh on the Windows-VM.

The Mac side:
  1. Reads the registry to discover excel_table_image elements
  2. SCPs the rendered pptx + connected workbook to the VM
  3. Invokes the PS1 script with the binding map as JSON
  4. Ferries the refreshed pptx back

This script does NOT execute COM directly — that's the PS1's job.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

import yaml


def _table_image_bindings(registry: dict) -> list[dict]:
    out: list[dict] = []
    for slide in registry["slides"]:
        for el in slide.get("elements", []):
            if el["lane"] == "excel_table_image":
                out.append(
                    {
                        "slide_id": slide["slide_id"],
                        "name": el["name"],
                        "source": el["source"],
                    }
                )
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pptx", required=True, type=Path, help="rendered_stage1.pptx (input)")
    parser.add_argument("--workbook", required=True, type=Path, help="connected workbook")
    parser.add_argument("--registry", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--vm", default="Windows-VM", help="SSH host alias")
    parser.add_argument("--vm-stage-dir", default="/Users/Public/Documents/tcseed_build")
    args = parser.parse_args(argv)

    registry = yaml.safe_load(args.registry.read_text())
    bindings = _table_image_bindings(registry)
    if not bindings:
        print("no excel_table_image bindings; nothing to refresh", file=sys.stderr)
        # copy input to output unchanged
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_bytes(args.pptx.read_bytes())
        return 0

    bindings_json = json.dumps(bindings)

    # ferry inputs to VM
    subprocess.run(["ssh", args.vm, f"mkdir -p {args.vm_stage_dir}"], check=True)
    subprocess.run(["scp", str(args.pptx), f"{args.vm}:{args.vm_stage_dir}/in.pptx"], check=True)
    subprocess.run(
        ["scp", str(args.workbook), f"{args.vm}:{args.vm_stage_dir}/in.xlsx"], check=True
    )

    # run PS1
    ps1 = Path(__file__).parent / "vm" / "refresh_thinkcell_table_images.ps1"
    subprocess.run(["scp", str(ps1), f"{args.vm}:{args.vm_stage_dir}/refresh.ps1"], check=True)
    proc = subprocess.run(
        [
            "ssh",
            args.vm,
            "powershell",
            "-File",
            f"{args.vm_stage_dir}/refresh.ps1",
            "-Pptx",
            f"{args.vm_stage_dir}/in.pptx",
            "-Workbook",
            f"{args.vm_stage_dir}/in.xlsx",
            "-BindingsJson",
            json.dumps(bindings_json),
            "-Out",
            f"{args.vm_stage_dir}/out.pptx",
        ],
        capture_output=True,
        text=True,
    )
    sys.stdout.write(proc.stdout)
    sys.stderr.write(proc.stderr)
    if proc.returncode != 0:
        return proc.returncode

    # ferry back
    subprocess.run(["scp", f"{args.vm}:{args.vm_stage_dir}/out.pptx", str(args.out)], check=True)
    print(f"OK: refreshed pptx written to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
