#!/usr/bin/env python3
"""Compare two LAND decks for the same director: shape diff + value diff.

The .ppttc IS the audit receipt: the rendered .pptx is a deterministic
function of (template + .ppttc bindings). We diff the two .ppttc inputs
that produced the two archived decks and the rendered .pptx zip layout
to surface what changed month-over-month per director.

Two modes:

* **shape diff** -- compare the rendered .pptx top-line shape: slide
  count, chart count (per zip-internal heuristic), set of binding names
  present in the .ppttc.
* **value diff** -- per-binding value diff between the two .ppttc files.
  Output is a markdown summary plus a JSON sidecar.

Two ways to specify "from" and "to":

    --director Jesper-Tyrer --from <ts1> --to <ts2>
        Compare two archived decks under
        state/<period>/<director>/decks/.
    --director Jesper-Tyrer --period 2026-Q2 --previous-period 2026-Q1
        Compare the latest archived deck of two periods.

Output: ``state/<period>/<director>/diffs/<from-ts>_vs_<to-ts>/{summary.md,diff.json}``
unless --output is set.
"""

from __future__ import annotations

import argparse
import json
import sys
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class DeckSnapshot:
    """One archived deck with its provenance .ppttc."""

    timestamp: str
    period: str
    director: str
    pptx: Path
    audit: Path
    ppttc: Path  # source .ppttc that produced ``pptx``


# -- discovery -------------------------------------------------------------


def _decks_dir(director: str, period: str, archive_root: Path) -> Path:
    return archive_root / period / director / "decks"


def _list_archived_timestamps(director: str, period: str, archive_root: Path) -> list[str]:
    d = _decks_dir(director, period, archive_root)
    if not d.is_dir():
        return []
    return sorted(p.name for p in d.iterdir() if p.is_dir())


def _load_audit(audit_path: Path) -> dict[str, Any]:
    return json.loads(audit_path.read_text(encoding="utf-8"))


def _resolve_snapshot(director: str, period: str, ts: str, archive_root: Path) -> DeckSnapshot:
    deck_dir = _decks_dir(director, period, archive_root) / ts
    if not deck_dir.is_dir():
        raise SystemExit(f"archive not found: {deck_dir}")
    audit_file = deck_dir / "audit.json"
    if not audit_file.exists():
        raise SystemExit(f"audit.json missing: {audit_file}")
    audit = _load_audit(audit_file)
    pptx_path = audit.get("output", {}).get("path")
    ppttc_path = audit.get("ppttc", {}).get("path")
    if not pptx_path or not Path(pptx_path).exists():
        # Fall back to the .pptx in the archive directory by extension scan.
        candidates = sorted(deck_dir.glob("*.pptx"))
        if not candidates:
            raise SystemExit(f"no .pptx in archive: {deck_dir}")
        pptx_path = str(candidates[0])
    if not ppttc_path or not Path(ppttc_path).exists():
        raise SystemExit(f".ppttc referenced by audit.json is missing: {ppttc_path}")
    return DeckSnapshot(
        timestamp=ts,
        period=period,
        director=director,
        pptx=Path(pptx_path),
        audit=audit_file,
        ppttc=Path(ppttc_path),
    )


def _latest_ts(director: str, period: str, archive_root: Path) -> str:
    timestamps = _list_archived_timestamps(director, period, archive_root)
    if not timestamps:
        raise SystemExit(f"no archived decks for {director}/{period}")
    return timestamps[-1]


# -- shape diff ------------------------------------------------------------


def _slide_count(pptx: Path) -> int:
    n = 0
    with zipfile.ZipFile(pptx, "r") as zf:
        for name in zf.namelist():
            if name.startswith("ppt/slides/slide") and name.endswith(".xml"):
                tail = name[len("ppt/slides/slide") : -len(".xml")]
                if tail.isdigit():
                    n += 1
    return n


def _chart_count(pptx: Path) -> int:
    """Heuristic: count ``ppt/charts/chart*.xml`` parts in the zip."""
    n = 0
    with zipfile.ZipFile(pptx, "r") as zf:
        for name in zf.namelist():
            if (
                name.startswith("ppt/charts/chart")
                and name.endswith(".xml")
                and "chart" in Path(name).stem
            ):
                tail = name[len("ppt/charts/chart") : -len(".xml")]
                if tail.isdigit():
                    n += 1
    return n


def _binding_names(ppttc: Path) -> list[str]:
    parsed = json.loads(ppttc.read_text(encoding="utf-8"))
    out: list[str] = []
    if not isinstance(parsed, list):
        return out
    for entry in parsed:
        if not isinstance(entry, dict):
            continue
        for b in entry.get("data", []):
            if isinstance(b, dict) and isinstance(b.get("name"), str):
                out.append(b["name"])
    return out


def shape_diff(a: DeckSnapshot, b: DeckSnapshot) -> dict[str, Any]:
    """Return a dict comparing slide count, chart count, binding-name set."""
    a_names = set(_binding_names(a.ppttc))
    b_names = set(_binding_names(b.ppttc))
    return {
        "slides": {
            "from": _slide_count(a.pptx),
            "to": _slide_count(b.pptx),
        },
        "charts": {
            "from": _chart_count(a.pptx),
            "to": _chart_count(b.pptx),
        },
        "bindings": {
            "from_count": len(a_names),
            "to_count": len(b_names),
            "added_names": sorted(b_names - a_names),
            "removed_names": sorted(a_names - b_names),
        },
    }


# -- value diff ------------------------------------------------------------


def _binding_table_map(ppttc: Path) -> dict[str, list[list[Any]]]:
    """Map binding name -> table for the first entry in the .ppttc."""
    parsed = json.loads(ppttc.read_text(encoding="utf-8"))
    if not isinstance(parsed, list):
        return {}
    out: dict[str, list[list[Any]]] = {}
    for entry in parsed:
        if not isinstance(entry, dict):
            continue
        for b in entry.get("data", []):
            if (
                isinstance(b, dict)
                and isinstance(b.get("name"), str)
                and isinstance(b.get("table"), list)
            ):
                # Last writer wins on collision.
                out[b["name"]] = b["table"]
    return out


def value_diff(a: DeckSnapshot, b: DeckSnapshot) -> dict[str, Any]:
    """For each binding present in both .ppttc inputs, list value differences.

    Per-cell comparison: cells are JSON-equal? -> match. Otherwise emit
    ``(from_cell, to_cell)``. Bindings missing on one side are listed
    separately.
    """
    a_map = _binding_table_map(a.ppttc)
    b_map = _binding_table_map(b.ppttc)
    common = sorted(set(a_map) & set(b_map))
    only_in_from = sorted(set(a_map) - set(b_map))
    only_in_to = sorted(set(b_map) - set(a_map))
    diffs: dict[str, list[dict[str, Any]]] = {}
    for name in common:
        cell_diffs = _table_cell_diff(a_map[name], b_map[name])
        if cell_diffs:
            diffs[name] = cell_diffs
    return {
        "common_binding_count": len(common),
        "differing_bindings": diffs,
        "only_in_from": only_in_from,
        "only_in_to": only_in_to,
    }


def _table_cell_diff(a: list[list[Any]], b: list[list[Any]]) -> list[dict[str, Any]]:
    """Return ``[{row, col, from, to}, ...]`` for cells where ``a`` != ``b``.

    If row counts differ, we still pairwise-walk the shorter prefix and
    flag the truncation as a meta diff at the end.
    """
    out: list[dict[str, Any]] = []
    common_rows = min(len(a), len(b))
    for r in range(common_rows):
        row_a = a[r] if isinstance(a[r], list) else [a[r]]
        row_b = b[r] if isinstance(b[r], list) else [b[r]]
        common_cols = min(len(row_a), len(row_b))
        for c in range(common_cols):
            if row_a[c] != row_b[c]:
                out.append({"row": r, "col": c, "from": row_a[c], "to": row_b[c]})
        if len(row_a) != len(row_b):
            out.append(
                {
                    "row": r,
                    "col": -1,
                    "from": f"<{len(row_a)} cols>",
                    "to": f"<{len(row_b)} cols>",
                }
            )
    if len(a) != len(b):
        out.append(
            {
                "row": -1,
                "col": -1,
                "from": f"<{len(a)} rows>",
                "to": f"<{len(b)} rows>",
            }
        )
    return out


# -- output ----------------------------------------------------------------


def render_markdown(
    a: DeckSnapshot,
    b: DeckSnapshot,
    shape: dict[str, Any],
    value: dict[str, Any],
) -> str:
    lines: list[str] = []
    lines.append(f"# Director deck diff -- {a.director}")
    lines.append("")
    lines.append(f"- From: `{a.period}/{a.timestamp}` ({a.pptx.name})")
    lines.append(f"- To:   `{b.period}/{b.timestamp}` ({b.pptx.name})")
    lines.append("")
    lines.append("## Shape")
    lines.append("")
    lines.append("| Metric | From | To | Delta |")
    lines.append("| --- | ---: | ---: | ---: |")
    sl = shape["slides"]
    ch = shape["charts"]
    bd = shape["bindings"]
    lines.append(f"| Slides | {sl['from']} | {sl['to']} | {sl['to'] - sl['from']:+d} |")
    lines.append(f"| Charts | {ch['from']} | {ch['to']} | {ch['to'] - ch['from']:+d} |")
    lines.append(
        f"| Bindings | {bd['from_count']} | {bd['to_count']} | "
        f"{bd['to_count'] - bd['from_count']:+d} |"
    )
    if bd["added_names"]:
        lines.append("")
        lines.append("**Added bindings:** " + ", ".join(f"`{n}`" for n in bd["added_names"]))
    if bd["removed_names"]:
        lines.append("")
        lines.append("**Removed bindings:** " + ", ".join(f"`{n}`" for n in bd["removed_names"]))
    lines.append("")
    lines.append("## Values")
    lines.append("")
    lines.append(f"- Bindings compared: {value['common_binding_count']}")
    lines.append(f"- Bindings with cell-level diffs: {len(value['differing_bindings'])}")
    if value["only_in_from"]:
        lines.append("- Only in FROM: " + ", ".join(f"`{n}`" for n in value["only_in_from"]))
    if value["only_in_to"]:
        lines.append("- Only in TO: " + ", ".join(f"`{n}`" for n in value["only_in_to"]))
    lines.append("")
    if value["differing_bindings"]:
        lines.append("### Differing bindings")
        lines.append("")
        for name, diffs in sorted(value["differing_bindings"].items()):
            lines.append(f"#### `{name}` ({len(diffs)} cell-level diffs)")
            lines.append("")
            lines.append("| row | col | from | to |")
            lines.append("| ---: | ---: | --- | --- |")
            for d in diffs[:25]:  # cap per-binding for readability
                f_str = json.dumps(d["from"], ensure_ascii=True)
                t_str = json.dumps(d["to"], ensure_ascii=True)
                lines.append(f"| {d['row']} | {d['col']} | `{f_str}` | `{t_str}` |")
            if len(diffs) > 25:
                lines.append(f"| ... | ... | ({len(diffs) - 25} more) | ... |")
            lines.append("")
    return "\n".join(lines)


# -- CLI -------------------------------------------------------------------


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="diff_director_decks",
        description=(
            "Diff two archived LAND decks for the same director (shape "
            "+ value, .ppttc as audit receipt)."
        ),
    )
    p.add_argument("--director", required=True, help="Director slug, e.g. Jesper-Tyrer.")
    p.add_argument("--period", default=None, help="Period label of TO deck, e.g. 2026-Q2.")
    p.add_argument(
        "--from-period", default=None, help="Period label of FROM deck (defaults to --period)."
    )
    p.add_argument("--from", dest="from_ts", default=None, help="FROM archive timestamp.")
    p.add_argument("--to", dest="to_ts", default=None, help="TO archive timestamp.")
    p.add_argument(
        "--previous-period",
        default=None,
        help=(
            "When set with --period, compare latest archive of previous-period vs latest of period."
        ),
    )
    p.add_argument(
        "--archive-root",
        type=Path,
        default=REPO_ROOT / "state",
        help=f"Archive root (default: {REPO_ROOT / 'state'}).",
    )
    p.add_argument(
        "--output",
        type=Path,
        default=None,
        help=(
            "Output directory (default: <archive-root>/<period>/<director>/diffs/<from>_vs_<to>/)."
        ),
    )
    return p.parse_args(argv)


def _resolve_endpoints(args: argparse.Namespace) -> tuple[DeckSnapshot, DeckSnapshot]:
    director = args.director
    archive_root = args.archive_root.expanduser().resolve()

    if args.previous_period and args.period:
        from_ts = _latest_ts(director, args.previous_period, archive_root)
        to_ts = _latest_ts(director, args.period, archive_root)
        a = _resolve_snapshot(director, args.previous_period, from_ts, archive_root)
        b = _resolve_snapshot(director, args.period, to_ts, archive_root)
        return a, b

    if not args.period:
        raise SystemExit("--period is required (used to locate archives)")

    from_period = args.from_period or args.period
    if args.from_ts and args.to_ts:
        a = _resolve_snapshot(director, from_period, args.from_ts, archive_root)
        b = _resolve_snapshot(director, args.period, args.to_ts, archive_root)
        return a, b

    raise SystemExit(
        "Either --from <ts> --to <ts> (with --period and optional --from-period) "
        "or --period <P> --previous-period <Q> is required"
    )


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    a, b = _resolve_endpoints(args)

    shape = shape_diff(a, b)
    value = value_diff(a, b)

    out_dir = args.output
    if out_dir is None:
        out_dir = (
            args.archive_root.expanduser().resolve()
            / b.period
            / a.director
            / "diffs"
            / f"{a.timestamp}_vs_{b.timestamp}"
        )
    out_dir.mkdir(parents=True, exist_ok=True)

    md = render_markdown(a, b, shape, value)
    (out_dir / "summary.md").write_text(md, encoding="utf-8")
    payload = {
        "director": a.director,
        "from": {"period": a.period, "timestamp": a.timestamp, "pptx": str(a.pptx)},
        "to": {"period": b.period, "timestamp": b.timestamp, "pptx": str(b.pptx)},
        "shape": shape,
        "value": value,
    }
    (out_dir / "diff.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=True),
        encoding="utf-8",
    )
    print(f"wrote: {out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
