#!/usr/bin/env python3
"""Build a table-image linked LAND deck for one director.

This is the repeatable bridge for the currently proven Excel -> think-cell
path: build named Excel table-image ranges, inject named table-image donors
into the PowerPoint deck, then run Excel COM `AddRangeImage` through the
interactive Windows VM task lane.
"""

from __future__ import annotations

import argparse
import base64
import subprocess
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
WINDOWS_HOST = "Windows-VM"
REMOTE_WORK = r"C:\tcw"
UPDATE_PS1 = ROOT / "_windows_test" / "update_table_images_in_deck.ps1"
INTERACTIVE_PS1 = ROOT / "_windows_test" / "run_interactive_task.ps1"
FINALIZE_MAC = ROOT / "scripts" / "finalize_thinkcell_table_images_mac.py"


def _run(command: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    print("+ " + " ".join(command), flush=True)
    completed = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, check=False)
    output = "\n".join(part for part in (completed.stdout.strip(), completed.stderr.strip()) if part)
    if output:
        print(output)
    if check and completed.returncode != 0:
        raise SystemExit(completed.returncode)
    return completed


def _to_unc(path: Path) -> str:
    resolved = path.expanduser().resolve()
    home = Path.home().resolve()
    rel = resolved.relative_to(home)
    return r"\\Mac\Home" + "\\" + "\\".join(rel.parts)


def _ps_quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _ps_dquote(value: str) -> str:
    return '"' + value.replace('"', '`"') + '"'


def _encoded_powershell(script: str) -> str:
    return base64.b64encode(script.encode("utf-16le")).decode("ascii")


def _director_dir(period: str, slug: str) -> Path:
    return ROOT / "state" / period / slug


def _write_stage_script(
    *,
    slug: str,
    input_deck: Path,
    workbook: Path,
    output_deck: Path,
    only_name: str | None,
    reposition_after_update: bool,
) -> Path:
    stage_dir = ROOT / "state" / "thinkcell_bridge" / "table_image_updates"
    stage_dir.mkdir(parents=True, exist_ok=True)
    stage = stage_dir / f"update_table_images_{slug}.ps1"
    stage.write_text(
        "\n".join(
            [
                '$ErrorActionPreference = "Stop"',
                f"& {_ps_quote(REMOTE_WORK + r'\\update_table_images_in_deck.ps1')} `",
                f"    -InputDeck {_ps_quote(_to_unc(input_deck))} `",
                f"    -WorkbookPath {_ps_quote(_to_unc(workbook))} `",
                f"    -OutputDeck {_ps_quote(_to_unc(output_deck))} `",
                *([f"    -OnlyName {_ps_quote(only_name)} `"] if only_name else []),
                *(["    -RepositionAfterUpdate `"] if reposition_after_update else []),
                "    -SkipMissingNamedObjects",
                "    # Keep think-cell-owned geometry. PowerPoint-side resizing creates",
                "    # the 'changed without think-cell' carryover warning.",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return stage


def _wait_for_output(path: Path, timeout_seconds: int) -> None:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        if path.exists() and path.stat().st_size > 0:
            return
        time.sleep(3)
    raise SystemExit(f"timed out waiting for linked deck: {path}")


def build_one(
    period: str,
    director_slug: str,
    host: str,
    timeout_seconds: int,
    interactive_task: bool,
    refresh_existing: bool,
    finalize_mac: bool,
    finalize_close: bool,
    only_name: str | None,
    reposition_after_update: bool,
) -> Path:
    director_dir = _director_dir(period, director_slug)
    base_deck = director_dir / f"{director_slug}-LAND-{period}.pptx"
    workbook = director_dir / "factory" / "connected" / "connected_factory_table_images.xlsx"
    seeded_deck = director_dir / f"{director_slug}-LAND-{period}-table-image-seeded.pptx"
    linked_deck = director_dir / f"{director_slug}-LAND-{period}-table-image-linked.pptx"

    if refresh_existing:
        if not linked_deck.exists():
            raise SystemExit(f"missing existing linked deck: {linked_deck}")
        input_deck = linked_deck
        output_deck = director_dir / f"{director_slug}-LAND-{period}-table-image-linked-refresh.pptx"
    elif not base_deck.exists():
        raise SystemExit(f"missing base deck: {base_deck}")
    else:
        input_deck = seeded_deck
        output_deck = linked_deck

    _run(
        [
            ".venv/bin/python",
            "scripts/build_table_image_source_workbook.py",
            "--period",
            period,
            "--director-slug",
            director_slug,
        ]
    )
    if not refresh_existing:
        _run(
            [
                ".venv/bin/python",
                "scripts/inject_table_image_donors_into_deck.py",
                "--input",
                str(base_deck),
                "--output",
                str(seeded_deck),
                "--skip-missing-targets",
            ]
            + (["--only-name", only_name] if only_name else [])
        )

    if output_deck.exists():
        output_deck.unlink()

    stage = _write_stage_script(
        slug=director_slug,
        input_deck=input_deck,
        workbook=workbook,
        output_deck=output_deck,
        only_name=only_name,
        reposition_after_update=reposition_after_update,
    )

    _run(["scp", str(UPDATE_PS1), f"{host}:C:/tcw/update_table_images_in_deck.ps1"])
    if interactive_task:
        _run(["scp", str(INTERACTIVE_PS1), f"{host}:C:/tcw/run_interactive_task.ps1"])
        _run(
            [
                "ssh",
                host,
                (
                "powershell -NoProfile -ExecutionPolicy Bypass "
                f"-File C:\\tcw\\run_interactive_task.ps1 -ScriptPath {_ps_dquote(_to_unc(stage))} "
                f"-TaskName {_ps_dquote('CodexTableImage_' + director_slug)}"
                ),
            ]
        )
        _wait_for_output(output_deck, timeout_seconds)
    else:
        only_name_arg = f'-OnlyName "{only_name}" ' if only_name else ""
        reposition_arg = "-RepositionAfterUpdate " if reposition_after_update else ""
        script = (
            '$ErrorActionPreference = "Stop"; '
            '& "C:\\tcw\\update_table_images_in_deck.ps1" '
            f'-InputDeck "{_to_unc(input_deck)}" '
            f'-WorkbookPath "{_to_unc(workbook)}" '
            f'-OutputDeck "{_to_unc(output_deck)}" '
            f"{only_name_arg}"
            f"{reposition_arg}"
            "-SkipMissingNamedObjects"
        )
        _run(
            [
                "ssh",
                host,
                "powershell -NoProfile -ExecutionPolicy Bypass -EncodedCommand "
                + _encoded_powershell(script),
            ]
        )
    _run([".venv/bin/python", "scripts/powerpoint_open_smoke.py", str(output_deck), "--host", host])
    if refresh_existing:
        output_deck.replace(linked_deck)
        _run([".venv/bin/python", "scripts/powerpoint_open_smoke.py", str(linked_deck), "--host", host])
    if finalize_mac:
        command = [
            ".venv/bin/python",
            str(FINALIZE_MAC.relative_to(ROOT)),
            str(linked_deck),
        ]
        if finalize_close:
            command.append("--close")
        _run(command)
    print(linked_deck)
    return linked_deck


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--period", default="2026-Q2")
    parser.add_argument("--director-slug", required=True)
    parser.add_argument("--host", default=WINDOWS_HOST)
    parser.add_argument("--timeout-seconds", type=int, default=300)
    parser.add_argument("--interactive-task", action="store_true")
    parser.add_argument(
        "--refresh-existing",
        action="store_true",
        help="Refresh table images inside the existing linked deck instead of reinjecting donors from the base deck.",
    )
    parser.add_argument("--finalize-mac", action="store_true", help="Opt in to the legacy Mac carryover finalization pass.")
    parser.add_argument(
        "--only-name",
        help="Build or refresh only one named think-cell table-image target.",
    )
    parser.add_argument(
        "--all-table-images",
        action="store_true",
        help="Opt in to refreshing every table-image target. Default is the calibrated S07 pilot only.",
    )
    parser.add_argument(
        "--skip-finalize-mac",
        action="store_true",
        help="Compatibility flag; Mac finalization is skipped unless --finalize-mac is supplied.",
    )
    parser.add_argument(
        "--finalize-close",
        action="store_true",
        help="Close the presentation after the Mac finalization pass saves it.",
    )
    parser.add_argument(
        "--reposition-after-update",
        action="store_true",
        help="Resize refreshed table images to the slide target bounds after think-cell update.",
    )
    args = parser.parse_args()
    finalize_mac = args.finalize_mac and (not args.skip_finalize_mac) and sys.platform == "darwin"
    if args.finalize_mac and sys.platform != "darwin":
        print("warning: skipping Mac finalization because this host is not macOS")
    if args.only_name and args.all_table_images:
        raise SystemExit("--only-name and --all-table-images are mutually exclusive")
    only_name = None if args.all_table_images else (args.only_name or "S07_TopDealsLand")

    build_one(
        args.period,
        args.director_slug,
        args.host,
        args.timeout_seconds,
        args.interactive_task,
        args.refresh_existing,
        finalize_mac,
        args.finalize_close,
        only_name,
        args.reposition_after_update,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
