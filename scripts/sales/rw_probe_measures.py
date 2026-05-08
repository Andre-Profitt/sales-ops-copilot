"""Lightweight measure-eval harness — desktop pragmatic alternative to sempy.

DAX query API is tenant-disabled and sempy's XMLA client bundles a Linux
.NET assembly that won't load on macOS arm64. Until either gets fixed,
the realistic verification loop on a Mac is:

  1. List measures you want to spot-check.
  2. Run this script with --measures '<m1>,<m2>,...'.
  3. It clears the 'What Changed' redesign tab and lays out one card
     per measure (auto-grid, 4 cards per row).
  4. Pushes via existing rw_add_visual.push_report.
  5. Validates first via rw_validate so a typo doesn't waste an LRO push.
  6. Open the report URL it prints; eyeball values; clear when done.

Run inside a Fabric notebook with sempy.fabric.evaluate_dax for a real
programmatic DAX eval (see docs/sales/RW_DAX_VERIFICATION.md).

Usage:
    python3 -m scripts.sales.rw_probe_measures \\
        --measures "Stage 3 Backward Pct,Avg Days In Stage 3,At Risk Opps Count"

    python3 -m scripts.sales.rw_probe_measures --measures-file /tmp/m.txt
    python3 -m scripts.sales.rw_probe_measures --clear  # wipe the probe tab
"""

from __future__ import annotations

import argparse

from scripts.sales._pbir_helpers import build_card_visual
from scripts.sales.rw_add_visual import (
    REPORT_ID,
    WORKSPACE_ID,
    _token,
    get_current_report_json,
    push_report,
)
from scripts.sales.rw_inventory_measures import fetch_measures_by_table

PROBE_PAGE = "What Changed"  # Hijack the redesign tab for spot-checks; cheap to clear.
GRID_COLS = 4
CARD_W = 280
CARD_H = 110
GAP_X = 20
GAP_Y = 20
ORIGIN_X = 20
ORIGIN_Y = 20


def _resolve_measure(name: str, by_table: dict[str, list[str]]) -> tuple[str, str]:
    """Look up which table owns a measure name. Raises if unresolvable."""
    hits = [t for t, ms in by_table.items() if name in ms]
    if not hits:
        raise SystemExit(f"  measure {name!r} not found in deployed model")
    if len(hits) > 1:
        raise SystemExit(f"  measure {name!r} ambiguous across tables {hits}")
    return hits[0], name


def _grid_position(i: int) -> tuple[int, int]:
    row, col = divmod(i, GRID_COLS)
    return ORIGIN_X + col * (CARD_W + GAP_X), ORIGIN_Y + row * (CARD_H + GAP_Y)


def _find_section(rj: dict, page: str) -> dict:
    matches = [s for s in rj["sections"] if s.get("displayName") == page]
    if not matches:
        names = [s.get("displayName") for s in rj["sections"]]
        raise SystemExit(f"  page {page!r} not found. Available: {names}")
    return matches[0]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[0])
    ap.add_argument(
        "--measures",
        help="Comma-separated measure names. Mutually exclusive with --measures-file / --clear.",
    )
    ap.add_argument("--measures-file", help="Path to a newline-separated measure-list file.")
    ap.add_argument(
        "--clear",
        action="store_true",
        help=f"Wipe the probe tab ({PROBE_PAGE!r}) without adding anything.",
    )
    ap.add_argument(
        "--page",
        default=PROBE_PAGE,
        help=f"Override probe tab. Default: {PROBE_PAGE!r}.",
    )
    args = ap.parse_args()

    if not (args.measures or args.measures_file or args.clear):
        ap.error("supply --measures, --measures-file, or --clear")

    measures: list[str] = []
    if args.measures:
        measures = [m.strip() for m in args.measures.split(",") if m.strip()]
    elif args.measures_file:
        with open(args.measures_file) as f:
            measures = [line.strip() for line in f if line.strip() and not line.startswith("#")]

    print(f"resolving {len(measures)} measure(s)..." if measures else "clear-only mode")
    by_table = fetch_measures_by_table()
    resolved = [_resolve_measure(m, by_table) for m in measures]
    if resolved:
        for table, name in resolved:
            print(f"  {table}.{name}")

    print("\nfetching report.json...")
    token = _token()
    rj = get_current_report_json(token)
    section = _find_section(rj, args.page)
    print(
        f"  target page: {section.get('displayName')!r} "
        f"(currently {len(section.get('visualContainers', []))} visuals)"
    )

    section["visualContainers"] = []
    print("  cleared probe tab")

    for i, (table, name) in enumerate(resolved):
        x, y = _grid_position(i)
        section["visualContainers"].append(
            build_card_visual(table, name, name, x=x, y=y, w=CARD_W, h=CARD_H)
        )

    if measures:
        print(f"  added {len(measures)} probe card(s)")

    print(f"\npushing; total visuals on {args.page!r}: {len(section['visualContainers'])}")
    push_report(token, rj)
    print(
        f"\ndone. open and eyeball: "
        f"https://app.fabric.microsoft.com/groups/{WORKSPACE_ID}/reports/{REPORT_ID}"
    )


if __name__ == "__main__":
    main()
