"""Sweep all PBIX Report/Layout files in the Zebra corpus, harvest style
tokens (color/font/border/padding), dedupe, count usages, mark canonical.

Output: data/zebra_kg/style_tokens.json with rows of:
    {kind, value, purpose, usage_count, canonical}

Deterministic: sorted by (kind, value, purpose) so md5 parity holds across
runs.

Usage:
    python3 -m scripts.sales.rw_zebra_kg_tokens \\
      --source-dir ~/Downloads/rw-zebra-bi-template-research-20260509/files \\
      --out-dir data/zebra_kg
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from scripts.sales.rw_zebra_template_miner import (
    iter_pbix_layouts,
    parse_config,
    sanitized_object_groups,
)

CANONICAL_THRESHOLD = 50


@dataclass(frozen=True)
class Token:
    kind: str
    value: str
    purpose: str


_LITERAL_VALUE = re.compile(r"^'?(.*?)'?D?$")
_HEX_COLOR = re.compile(r"^#[0-9A-F]{6,8}$")


def _literal(node: Any) -> str | None:
    try:
        raw = node["expr"]["Literal"]["Value"]
    except (KeyError, TypeError):
        return None
    m = _LITERAL_VALUE.match(str(raw))
    return m.group(1) if m else str(raw)


def _solid_color(node: Any) -> str | None:
    try:
        return str(node["solid"]["color"]).upper()
    except (KeyError, TypeError):
        return None


def extract_tokens_from_objects(
    objects: dict[str, list[dict[str, Any]]],
) -> Iterable[Token]:
    """Yield Tokens for every styling property in a single visual's `objects` dict.

    `objects` is the parsed `objects` block from a visual's config — a mapping
    of object-group names (e.g. "labels", "background", "border") to a list of
    instances, each with a "properties" dict.
    """
    for group_name, instances in (objects or {}).items():
        for inst in instances:
            props = inst.get("properties") or {}
            for prop_name, prop_value in props.items():
                if not isinstance(prop_value, dict):
                    continue

                color = _solid_color(prop_value)
                if color and _HEX_COLOR.fullmatch(color):
                    yield Token(kind="color", value=color, purpose=group_name)
                    continue

                lit = _literal(prop_value)
                if lit is None:
                    continue

                pname = prop_name.lower()
                if "font" in pname and "family" in pname:
                    yield Token(kind="font", value=lit, purpose=f"{group_name}.family")
                elif "fontsize" in pname or "textsize" in pname:
                    yield Token(kind="font", value=f"{lit}px", purpose=f"{group_name}.size")
                elif "weight" in pname and group_name == "border":
                    yield Token(kind="border", value=f"{lit}px", purpose="border.weight")
                elif "padding" in pname:
                    yield Token(
                        kind="padding",
                        value=f"{lit}px",
                        purpose=f"{group_name}.{prop_name}",
                    )


def dedupe_tokens(
    tokens: Iterable[Token],
    canonical_threshold: int = CANONICAL_THRESHOLD,
) -> list[dict[str, Any]]:
    counter: Counter[Token] = Counter(tokens)
    rows = [
        {
            "kind": tok.kind,
            "value": tok.value,
            "purpose": tok.purpose,
            "usage_count": count,
            "canonical": count >= canonical_threshold,
        }
        for tok, count in counter.items()
    ]
    rows.sort(key=lambda r: (r["kind"], r["value"], r["purpose"]))
    return rows


def sweep_corpus(source_dir: Path) -> list[dict[str, Any]]:
    layouts = iter_pbix_layouts(source_dir)
    all_tokens: list[Token] = []
    for layout in layouts:
        for section in layout.layout.get("sections", []):
            for vc in section.get("visualContainers", []):
                cfg = parse_config(vc)
                single = cfg.get("singleVisual") or {}
                objects = single.get("objects") or {}
                vc_objects = cfg.get("visualContainerObjects") or {}
                all_tokens.extend(extract_tokens_from_objects(objects))
                all_tokens.extend(extract_tokens_from_objects(vc_objects))
                # sanitized_object_groups drops Zebra license blobs — call it
                # for the side-effect of catching anomalies, output ignored.
                _ = sanitized_object_groups(single)
    return dedupe_tokens(all_tokens)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[0])
    parser.add_argument("--source-dir", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--canonical-threshold", type=int, default=CANONICAL_THRESHOLD)
    args = parser.parse_args()

    rows = sweep_corpus(args.source_dir.expanduser())
    out_path = args.out_dir.expanduser() / "style_tokens.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(rows, indent=2, ensure_ascii=False) + "\n")

    canonical = sum(1 for r in rows if r["canonical"])
    print(f"tokens: {len(rows)}  canonical: {canonical}  out: {out_path}")


if __name__ == "__main__":
    main()
