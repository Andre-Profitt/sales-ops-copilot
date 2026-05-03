#!/usr/bin/env python3
"""End-to-end deck-automation demo: Excel + think-cell template -> populated .pptx.

Wires `tc_com_driver` (pywin32 wrapper around think-cell COM) and `tcxml`
(think-cellXML reader) into the canonical sales-ops-copilot deck-automation
shape: open workbook in Excel COM, generate a deck via
`PresentationFromTemplate`, refresh every named range via a single atomic
`IUpdateBatch.Send()`, save to disk.

Windows-only at runtime. On Mac the script imports cleanly and
`ThinkCellClient.connect()` raises `WrongPlatformError` (gracefully reported).

Real fixture pair (verified 2026-05-02):
    --workbook  ~/code/apps/sales-ops-copilot/_windows_test/Jesper-Tyrer-land.xlsx
    --template  ~/code/apps/sales-ops-copilot/_windows_test/LAND_template.pptx

Andre runs this interactively on the Windows VM. Mac side: `--help` shows the
CLI; the smoke test verifies platform-error handling.
"""

from __future__ import annotations

import argparse
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from tc_com_driver import ThinkCellClient, WrongPlatformError


@dataclass(frozen=True)
class DemoResult:
    """Structured summary of a single demo run."""

    workbook: Path
    template: Path
    output: Path
    charts_updated: int
    elapsed_s: float


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="build_sd_monthly_demo",
        description=(
            "Generate a think-cell deck end-to-end from an Excel workbook + "
            "template. Windows + PowerPoint + licensed think-cell required."
        ),
    )
    p.add_argument(
        "--workbook",
        type=Path,
        required=True,
        help="Path to the Excel workbook driving the deck (named ranges become chart data).",
    )
    p.add_argument(
        "--template",
        type=Path,
        required=True,
        help="Path to the think-cell-enabled .pptx template.",
    )
    p.add_argument(
        "--out-dir",
        type=Path,
        default=Path("~/Desktop/tc_demo_output").expanduser(),
        help="Directory for the saved .pptx (default: ~/Desktop/tc_demo_output).",
    )
    p.add_argument(
        "--keep-open",
        action="store_true",
        help="Leave PowerPoint open after the run for manual inspection.",
    )
    return p.parse_args(argv)


def _validate_inputs(args: argparse.Namespace) -> None:
    """Fail fast on missing inputs before we spin up COM."""
    for label, path in (("workbook", args.workbook), ("template", args.template)):
        if not path.expanduser().exists():
            raise FileNotFoundError(f"--{label} does not exist: {path}")
    args.out_dir.expanduser().mkdir(parents=True, exist_ok=True)


def _open_excel_workbook(path: Path) -> tuple[Any, Any]:
    """Launch Excel via COM and open `path`. Returns (excel_app, workbook).

    Lazy import: pywin32 is Windows-only; the surrounding script gates this
    behind `WrongPlatformError`, so the import runs only on the VM.
    """
    import win32com.client as win32com_client

    excel = win32com_client.Dispatch("Excel.Application")
    excel.Visible = False
    excel.DisplayAlerts = False
    workbook = excel.Workbooks.Open(str(path.expanduser().resolve()))
    return excel, workbook


def _iter_workbook_names(workbook: Any) -> list[Any]:
    """Return every defined name on a workbook (workbook + worksheet scopes).

    `wb.Names` covers both workbook-scoped and worksheet-scoped names; we
    filter out hidden/built-in names and broken refs (RefersToRange raises
    on dangling references).
    """
    out: list[Any] = []
    names = workbook.Names
    count = int(getattr(names, "Count", 0))
    for i in range(1, count + 1):  # COM is 1-indexed
        name = names.Item(i)
        if bool(getattr(name, "Visible", True)) is False:
            continue
        try:
            _ = name.RefersToRange  # probe: raises on #REF!
        except Exception:  # noqa: BLE001 — pywin32 surfaces COMError as anything
            continue
        out.append(name)
    return out


def _build_deck(
    client: ThinkCellClient,
    excel_app: Any,
    workbook: Any,
    template: Path,
) -> tuple[Any, int]:
    """Generate the deck and refresh every named range. Returns (presentation, n)."""
    client.attach_excel(excel_app)

    presentation = client.xl.presentation_from_template(
        workbook=workbook,
        template=str(template.expanduser().resolve()),
        powerpoint_app=client.powerpoint,
    )

    batch = client.xl.create_update()
    n = 0
    for name in _iter_workbook_names(workbook):
        chart_name = str(name.Name).split("!")[-1]  # strip 'Sheet1!' scope prefix
        batch.add_range_data(
            target=presentation,
            name=chart_name,
            range=name.RefersToRange,
        )
        n += 1
    batch.send()
    return presentation, n


def _save_and_close(
    presentation: Any,
    excel_app: Any,
    workbook: Any,
    out_dir: Path,
    template: Path,
    keep_open: bool,
) -> Path:
    """Save the deck under `out_dir/<template_stem>_<ts>.pptx`. Close Excel always."""
    ts = time.strftime("%Y%m%d-%H%M%S")
    out_path = (out_dir.expanduser() / f"{template.stem}_{ts}.pptx").resolve()
    presentation.SaveAs(str(out_path))

    workbook.Close(SaveChanges=False)
    excel_app.Quit()

    if not keep_open:
        presentation.Close()
    return out_path


def run(args: argparse.Namespace) -> DemoResult:
    """Execute the full Excel -> think-cell -> .pptx flow. Caller handles errors.

    Order matters: connect to think-cell FIRST (this raises `WrongPlatformError`
    on Mac before we touch pywin32), then open Excel, then drive the deck.
    """
    _validate_inputs(args)
    t0 = time.monotonic()
    with ThinkCellClient.connect() as client:
        excel, workbook = _open_excel_workbook(args.workbook)
        try:
            presentation, charts = _build_deck(client, excel, workbook, args.template)
            output = _save_and_close(
                presentation=presentation,
                excel_app=excel,
                workbook=workbook,
                out_dir=args.out_dir,
                template=args.template,
                keep_open=args.keep_open,
            )
        except Exception:
            try:
                workbook.Close(SaveChanges=False)
                excel.Quit()
            except Exception:  # noqa: BLE001 — best-effort teardown only
                pass
            raise
    return DemoResult(
        workbook=args.workbook.expanduser().resolve(),
        template=args.template.expanduser().resolve(),
        output=output,
        charts_updated=charts,
        elapsed_s=round(time.monotonic() - t0, 3),
    )


def _print_summary(r: DemoResult) -> None:
    print("=== build_sd_monthly_demo ===")
    print(f"  workbook       : {r.workbook}")
    print(f"  template       : {r.template}")
    print(f"  output         : {r.output}")
    print(f"  charts_updated : {r.charts_updated}")
    print(f"  elapsed_s      : {r.elapsed_s}")


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        result = run(args)
    except WrongPlatformError as exc:
        print(f"[demo] platform unsupported: {exc}", file=sys.stderr)
        return 2
    except FileNotFoundError as exc:
        print(f"[demo] input missing: {exc}", file=sys.stderr)
        return 3
    _print_summary(result)
    return 0


if __name__ == "__main__":
    sys.exit(main())
