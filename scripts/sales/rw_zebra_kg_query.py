"""Read-only CLI over the Zebra BI knowledge graph.

Examples:
    # Measures across all templates that drive variance arrows
    python3 -m scripts.sales.rw_zebra_kg_query --measures --where is_variance=true

    # Style tokens scoped by purpose substring
    python3 -m scripts.sales.rw_zebra_kg_query --tokens-for header

    # RW elements that are bound vs need a DAX measure authored
    python3 -m scripts.sales.rw_zebra_kg_query --rw-status

    # Canonical token palette only
    python3 -m scripts.sales.rw_zebra_kg_query --tokens --canonical-only
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_KG_DIR = REPO_ROOT / "data/zebra_kg"
DEFAULT_RW_DIR = REPO_ROOT / "data/zebra_kg_rw"


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line]


def load_nodes(kg_dir: Path) -> list[dict[str, Any]]:
    return _read_jsonl(kg_dir / "nodes_datamodel.jsonl")


def load_edges(kg_dir: Path) -> list[dict[str, Any]]:
    return _read_jsonl(kg_dir / "edges_datamodel.jsonl")


def load_tokens(kg_dir: Path) -> list[dict[str, Any]]:
    path = kg_dir / "style_tokens.json"
    if not path.exists():
        return []
    return json.loads(path.read_text())


def load_bindings(rw_dir: Path) -> list[dict[str, Any]]:
    return _read_jsonl(rw_dir / "bindings.jsonl")


def filter_measures(
    nodes: list[dict[str, Any]],
    is_variance: bool | None = None,
    scenario: str | None = None,
    template: str | None = None,
) -> list[dict[str, Any]]:
    rows = [n for n in nodes if n.get("type") == "Measure"]
    if is_variance is not None:
        rows = [n for n in rows if bool(n.get("is_variance")) == is_variance]
    if scenario is not None:
        rows = [n for n in rows if n.get("scenario") == scenario]
    if template is not None:
        rows = [n for n in rows if n.get("template") == template]
    return rows


def filter_tokens(
    tokens: list[dict[str, Any]],
    canonical_only: bool = False,
    kind: str | None = None,
) -> list[dict[str, Any]]:
    rows = list(tokens)
    if canonical_only:
        rows = [r for r in rows if r.get("canonical")]
    if kind:
        rows = [r for r in rows if r.get("kind") == kind]
    return rows


def _parse_where(items: list[str]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for it in items:
        if "=" not in it:
            raise SystemExit(f"--where expects key=value, got: {it}")
        k, v = it.split("=", 1)
        if v.lower() in {"true", "false"}:
            out[k] = v.lower() == "true"
        else:
            out[k] = v
    return out


def _print(rows: list[dict[str, Any]], fmt: str) -> None:
    if fmt == "json":
        json.dump(rows, sys.stdout, indent=2, ensure_ascii=False)
        sys.stdout.write("\n")
        return
    if not rows:
        return
    keys = sorted({k for r in rows for k in r.keys()})
    sys.stdout.write("\t".join(keys) + "\n")
    for r in rows:
        sys.stdout.write("\t".join(str(r.get(k, "")) for k in keys) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[0])
    parser.add_argument("--kg-dir", type=Path, default=DEFAULT_KG_DIR)
    parser.add_argument("--rw-dir", type=Path, default=DEFAULT_RW_DIR)
    parser.add_argument("--format", choices=["tsv", "json"], default="tsv")

    parser.add_argument(
        "--measures",
        action="store_true",
        help="List measures (filterable with --where)",
    )
    parser.add_argument(
        "--where",
        action="append",
        default=[],
        help="key=value filter; repeatable (e.g. is_variance=true)",
    )
    parser.add_argument("--tokens", action="store_true", help="List style tokens")
    parser.add_argument("--canonical-only", action="store_true")
    parser.add_argument(
        "--tokens-for",
        type=str,
        default=None,
        help="Filter tokens by usage purpose substring",
    )
    parser.add_argument(
        "--rw-status",
        action="store_true",
        help="RW binding overlay status summary + rows",
    )

    args = parser.parse_args()

    nodes = load_nodes(args.kg_dir.expanduser())
    tokens = load_tokens(args.kg_dir.expanduser())
    bindings = load_bindings(args.rw_dir.expanduser())

    if args.measures:
        where = _parse_where(args.where)
        rows = filter_measures(nodes, **where)
        _print(rows, args.format)
        return

    if args.tokens or args.canonical_only or args.tokens_for:
        rows = filter_tokens(tokens, canonical_only=args.canonical_only)
        if args.tokens_for:
            needle = args.tokens_for.lower()
            rows = [r for r in rows if needle in r.get("purpose", "").lower()]
        _print(rows, args.format)
        return

    if args.rw_status:
        by_status: dict[str, int] = {}
        for b in bindings:
            by_status[b.get("status", "?")] = by_status.get(b.get("status", "?"), 0) + 1
        print(f"# RW binding status: {by_status}")
        _print(bindings, args.format)
        return

    parser.error("nothing to do — pass --measures, --tokens, --tokens-for, or --rw-status")


if __name__ == "__main__":
    main()
