"""Phase 8 — improve dashboard layout grid for readability.

The previous rebuilds focused on report data quality and widget composition
but inherited the existing layout grid (mixed colspans 3/5/6/7/9). Result:
tables truncated their columns, donuts had cramped legend space.

Auto-sizes each widget by visualizationType, then flows them into the
12-col grid:

  Tables / TABULAR reports     → colspan=12 (full width — show all columns)
  Funnel / Bar / Column / Line → colspan=6  (half — pair them)
  Pie / Donut / Gauge          → colspan=4  (third — they're small)
  Default                      → colspan=6

Rows are sized:
  Tables       → rowspan=10 (taller for more rows visible)
  Charts       → rowspan=8

Layout strategy: greedy 12-col packer. For each widget, pick the next
position where its colspan fits in the current row; if it doesn't fit,
start a new row.

Per Phase 2.8 memory: dashboard layout PATCH via Analytics API works.

Usage:
  python3 -m scripts.sf_audit.improve_dashboard_layout 01ZTb00000FSP7hMAH
  python3 -m scripts.sf_audit.improve_dashboard_layout 01ZTb00000FSP9JMAX --dry-run
"""

from __future__ import annotations

import argparse
import logging
import sys
from typing import Any

import requests

from scripts.sf_audit.reports import sf_session

logger = logging.getLogger("sf_audit.improve_layout")


def widget_size(viz_type: str, report_format: str) -> tuple[int, int]:
    """Return (colspan, rowspan) for a widget based on its visualization.

    Strategy: tables (FlexTable) need horizontal space because they show
    multiple columns; donuts/metrics are compact; bar/funnel charts pair
    naturally at half-width.
    """
    v = (viz_type or "").lower()
    rf = (report_format or "").lower()
    # Any table-shaped widget — full width (most exec dashboards have wide
    # tables and otherwise truncate column text).
    if v in ("flextable", "table") or rf == "tabular":
        return (12, 10)
    # KPI tiles — 4-across at 3 cols each
    if v == "metric":
        return (3, 4)
    # Compact widgets — donuts, pies
    if v in ("pie", "donut", "gauge"):
        return (4, 8)
    # Mid-size charts pair at half-width
    if v in ("funnel", "bar", "column", "line", "scatter"):
        return (6, 8)
    return (6, 8)  # default


def pack_layout(component_sizes: list[tuple[int, int]]) -> list[dict[str, Any]]:
    """Greedy 12-col grid packer — for each (colspan, rowspan), find the
    next slot. Tables (col=12) always start their own row."""
    GRID_WIDTH = 12
    layout: list[dict[str, Any]] = []
    row_cursor = 0
    col_cursor = 0
    row_height = 0
    for colspan, rowspan in component_sizes:
        # Tables (full-width) always force a new row + take the whole row
        if colspan >= GRID_WIDTH:
            if col_cursor > 0:
                row_cursor += row_height
                col_cursor = 0
                row_height = 0
            layout.append(
                {"colspan": GRID_WIDTH, "column": 0, "row": row_cursor, "rowspan": rowspan}
            )
            row_cursor += rowspan
            row_height = 0
            continue
        # Check if it fits in current row
        if col_cursor + colspan > GRID_WIDTH:
            row_cursor += row_height
            col_cursor = 0
            row_height = 0
        layout.append(
            {"colspan": colspan, "column": col_cursor, "row": row_cursor, "rowspan": rowspan}
        )
        col_cursor += colspan
        row_height = max(row_height, rowspan)
    return layout


def main() -> int:
    parser = argparse.ArgumentParser(description="Improve dashboard layout grid")
    parser.add_argument("dashboard_id", help="Dashboard ID, e.g. 01ZTb00000FSP7hMAH")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    instance, token, _ = sf_session()
    headers = {"Authorization": f"Bearer {token}"}
    url = f"{instance}/services/data/v65.0/analytics/dashboards/{args.dashboard_id}"

    r = requests.get(url + "/describe", headers=headers, timeout=30)
    if r.status_code != 200:
        print(f"GET failed: {r.status_code}", file=sys.stderr)
        return 2
    md = r.json()
    components = list(md.get("components") or [])
    print(f"Dashboard: {md.get('name')}")
    print(f"  components: {len(components)}\n")

    # Determine each component's intended size
    sizes = []
    for c in components:
        props = c.get("properties") or {}
        viz = props.get("visualizationType") or ""
        rf = props.get("reportFormat") or ""
        cs, rs = widget_size(viz, rf)
        sizes.append((cs, rs))
        title = (c.get("title") or c.get("header") or "")[:40]
        print(f"  [{viz or '?':10s} / {rf or '?':8s}] colspan={cs} rowspan={rs}  {title}")

    new_layout = pack_layout(sizes)
    print(
        f"\nNew grid spans rows 0..{max((lc['row'] + lc['rowspan'] for lc in new_layout), default=0)}"
    )

    if args.dry_run:
        return 0

    md["layout"] = {
        "components": new_layout,
        "gridLayout": (md.get("layout") or {}).get("gridLayout"),
    }
    for ro in (
        "id",
        "createdById",
        "createdDate",
        "lastModifiedDate",
        "namespace",
        "type",
        "developerName",
        "folderId",
        "folderName",
        "url",
        "labels",
        "ownerId",
    ):
        md.pop(ro, None)

    r2 = requests.patch(
        url,
        headers={**headers, "Content-Type": "application/json"},
        json=md,
        timeout=60,
    )
    if r2.status_code in (200, 201):
        print(f"\n✓ Layout improved: {args.dashboard_id}")
        print(f"  {instance}/lightning/r/Dashboard/{args.dashboard_id}/view")
        return 0
    print(f"\n✗ PATCH failed: {r2.status_code}")
    print(r2.text[:600])
    return 1


if __name__ == "__main__":
    sys.exit(main())
