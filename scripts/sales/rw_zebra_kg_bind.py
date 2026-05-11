"""Build the RW binding overlay from RW_ZEBRA_BI_GRAPHRAG_ELEMENT_MAP.md.

Reads the prose element-map doc + the deployed RW semantic model (via
rw_inventory_measures.fetch_measures_by_table()) and emits per-RW-value
binding records with status: bound | unbound | needs_measure.

Usage:
    python3 -m scripts.sales.rw_zebra_kg_bind --out-dir data/zebra_kg_rw
    python3 -m scripts.sales.rw_zebra_kg_bind --out-dir data/zebra_kg_rw --skip-rw-model
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DOC = REPO_ROOT / "docs/sales/RW_ZEBRA_BI_GRAPHRAG_ELEMENT_MAP.md"

_HEADING = re.compile(r"^### \d+\.\s*(.+?)\s*-\s*(.+?)\s*$", re.MULTILINE)
_SOURCE = re.compile(r"^Source:\s*`([^`]+)`", re.MULTILINE)
_VALUE_ITEM = re.compile(r"`([^`]+)`")
_RW_ELEMENT = re.compile(r"RW element:\s*\n+\s*-\s*`([^`]+)`")


def _parse_values_block(block: str) -> list[str]:
    """Find a `- Values:` line and collect every backtick-wrapped item from
    indented sub-bullets that follow, stopping at a non-indented or empty line.
    """
    lines = block.splitlines()
    out: list[str] = []
    in_block = False
    for line in lines:
        stripped = line.strip()
        if not in_block:
            if stripped == "- Values:" or stripped.startswith("- Values:"):
                in_block = True
            continue
        # in_block — collect indented sub-bullets that contain a backticked value
        if line.startswith(" ") and stripped.startswith("- ") and "`" in stripped:
            for v in _VALUE_ITEM.findall(stripped):
                out.append(v)
            continue
        # blank line is allowed inside the block; non-indented or non-bullet ends it
        if stripped == "":
            continue
        break
    return out


@dataclass
class ElementMapSection:
    rw_tab: str
    rw_element: str
    source_template: str
    rw_values: list[str] = field(default_factory=list)


def parse_element_map(text: str) -> list[ElementMapSection]:
    sections: list[ElementMapSection] = []
    headings = list(_HEADING.finditer(text))
    for i, m in enumerate(headings):
        block_start = m.end()
        block_end = headings[i + 1].start() if i + 1 < len(headings) else len(text)
        block = text[block_start:block_end]

        rw_tab = m.group(1).strip()
        title_tail = m.group(2).strip()  # short element description from heading

        src = _SOURCE.search(block)
        source_template = src.group(1) if src else ""

        values = _parse_values_block(block)

        rw_element = title_tail
        rw_section = _RW_ELEMENT.search(block)
        if rw_section:
            rw_element = rw_section.group(1).strip()

        sections.append(
            ElementMapSection(
                rw_tab=rw_tab,
                rw_element=rw_element,
                source_template=source_template,
                rw_values=values,
            )
        )
    return sections


def classify_status(rw_value: str, rw_model: dict[str, list[str]]) -> str:
    """`rw_model` is the {table: [measure_names]} dict from
    rw_inventory_measures.fetch_measures_by_table().
    """
    name = rw_value.strip()
    for measures in rw_model.values():
        if name in measures:
            return "bound"
    return "needs_measure"


def emit_bindings(
    sections: Iterable[ElementMapSection],
    rw_model: dict[str, list[str]],
) -> Iterable[dict]:
    for sec in sections:
        for value in sec.rw_values:
            slug_tab = re.sub(r"\W+", "_", sec.rw_tab).strip("_")
            slug_val = re.sub(r"\W+", "_", value).strip("_")
            yield {
                "id": f"bind:rw:{slug_tab}:{slug_val}",
                "type": "RWBinding",
                "rw_tab": sec.rw_tab,
                "rw_element": sec.rw_element,
                "rw_field": value,
                "source_template": sec.source_template,
                "rw_measure_target": f"msr:rw:{value}",
                "status": classify_status(value, rw_model),
            }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[0])
    parser.add_argument("--doc", type=Path, default=DEFAULT_DOC)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument(
        "--skip-rw-model",
        action="store_true",
        help="Don't call Fabric — emit all status=needs_measure (offline mode)",
    )
    args = parser.parse_args()

    text = args.doc.expanduser().read_text()
    sections = parse_element_map(text)

    if args.skip_rw_model:
        rw_model: dict[str, list[str]] = {}
    else:
        from scripts.sales.rw_inventory_measures import fetch_measures_by_table

        rw_model = fetch_measures_by_table()

    rows = list(emit_bindings(sections, rw_model))

    out_dir = args.out_dir.expanduser()
    out_dir.mkdir(parents=True, exist_ok=True)
    bind_path = out_dir / "bindings.jsonl"
    targets_path = out_dir / "rw_targets.csv"

    with bind_path.open("w", encoding="utf-8") as fp:
        for row in rows:
            fp.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")

    fieldnames = [
        "rw_tab",
        "rw_element",
        "rw_field",
        "source_template",
        "rw_measure_target",
        "status",
    ]
    with targets_path.open("w", encoding="utf-8", newline="") as fp:
        writer = csv.DictWriter(fp, fieldnames=fieldnames)
        writer.writeheader()
        for r in rows:
            writer.writerow({k: r[k] for k in fieldnames})

    by_status: dict[str, int] = {}
    for r in rows:
        by_status[r["status"]] = by_status.get(r["status"], 0) + 1
    print(f"bindings: {len(rows)}  by_status: {by_status}")
    print(f"out: {bind_path}, {targets_path}")


if __name__ == "__main__":
    main()
