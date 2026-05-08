"""Capture a live visual's PBIR shape from rpt_vp_ops_scorecard.

The browser is the source of truth for unfamiliar visualType shapes
(conditional formatting, custom themes, drill paths, sync slicers).
This CLI bridges browser-configured visuals into reusable Python code.

Workflow:

  1. Open rpt_vp_ops_scorecard in the browser editor.
  2. Configure the visual you want to canonicalize — e.g., a card with
     conditional formatting (Win Rate <0.25 red).
  3. Note the visual's title or rough position.
  4. Save the report.
  5. Run this CLI; it lists all visuals across all sections with
     enough metadata to identify the one you want.
  6. Use --extract to pull that visual's config and pretty-print it.
  7. Copy the relevant `singleVisual.objects` / `prototypeQuery` block
     into a new builder in _pbir_helpers.py — or add an entry to
     _pbir_shapes.py.

Usage:
    python3 -m scripts.sales.rw_capture_visual --list
    python3 -m scripts.sales.rw_capture_visual --list --page "Stage Hygiene"
    python3 -m scripts.sales.rw_capture_visual --extract <visual-name>
    python3 -m scripts.sales.rw_capture_visual --extract <visual-name> --raw
"""

from __future__ import annotations

import argparse
import json
import sys

from scripts.sales.rw_validate import fetch_live_report


def _summarize(vc: dict) -> dict:
    cfg = json.loads(vc["config"]) if isinstance(vc["config"], str) else vc["config"]
    sv = cfg.get("singleVisual", {})
    select = sv.get("prototypeQuery", {}).get("Select", [])
    fields = []
    for s in select:
        if "Measure" in s:
            fields.append(f"M:{s['Measure'].get('Property')}")
        elif "Column" in s:
            fields.append(f"C:{s['Column'].get('Property')}")
    return {
        "name": cfg.get("name"),
        "type": sv.get("visualType"),
        "fields": fields,
        "x": vc.get("x"),
        "y": vc.get("y"),
        "w": vc.get("width"),
        "h": vc.get("height"),
        "has_objects": bool(sv.get("objects")),
    }


def cmd_list(rj: dict, page_filter: str | None) -> None:
    for section in rj.get("sections", []):
        page = section.get("displayName")
        if page_filter and page != page_filter:
            continue
        vcs = section.get("visualContainers", [])
        print(f"\n[{page}] {len(vcs)} visuals")
        for vc in vcs:
            s = _summarize(vc)
            objs = " *cf*" if s["has_objects"] else ""
            fields = ", ".join(s["fields"][:3]) + ("..." if len(s["fields"]) > 3 else "")
            pos = f"({int(s['x'])},{int(s['y'])} {int(s['w'])}x{int(s['h'])})"
            print(f"  {s['name'][:20]:20s}  {s['type']:14s} {pos:24s} {fields}{objs}")


def cmd_extract(rj: dict, name: str, raw: bool) -> None:
    for section in rj.get("sections", []):
        for vc in section.get("visualContainers", []):
            cfg = json.loads(vc["config"]) if isinstance(vc["config"], str) else vc["config"]
            if cfg.get("name", "").startswith(name) or cfg.get("name") == name:
                if raw:
                    print(json.dumps(vc, indent=2))
                else:
                    out = {
                        "page": section.get("displayName"),
                        "container": {
                            "x": vc.get("x"),
                            "y": vc.get("y"),
                            "width": vc.get("width"),
                            "height": vc.get("height"),
                            "z": vc.get("z"),
                            "filters": vc.get("filters"),
                        },
                        "singleVisual": cfg.get("singleVisual"),
                        "_objects_present": list(
                            cfg.get("singleVisual", {}).get("objects", {}).keys()
                        ),
                    }
                    print(json.dumps(out, indent=2))
                return
    raise SystemExit(f"  no visual with name starting {name!r}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[0])
    grp = ap.add_mutually_exclusive_group(required=True)
    grp.add_argument("--list", action="store_true", help="List all visuals across all pages")
    grp.add_argument("--extract", metavar="NAME", help="Extract a visual by name (or prefix)")
    ap.add_argument("--page", help="Filter --list to a single page (displayName)")
    ap.add_argument(
        "--raw",
        action="store_true",
        help="With --extract: dump the full visualContainer dict, not the structured summary",
    )
    args = ap.parse_args()

    print("fetching live report...", file=sys.stderr)
    rj = fetch_live_report()

    if args.list:
        cmd_list(rj, args.page)
    elif args.extract:
        cmd_extract(rj, args.extract, args.raw)


if __name__ == "__main__":
    main()
