"""Mine the Zebra DAX corpus for canonical patterns. Reads
data/zebra_kg/measure_catalog.csv (produced by rw_zebra_kg_datamodel),
extracts a feature signature per measure via regex, clusters by signature,
and emits data/zebra_kg/dax_patterns.json with per-pattern: signature,
match_count, templates, canonical example, sample measure list.

Usage:
    python3 -m scripts.sales.rw_zebra_kg_dax_atlas \\
      --catalog data/zebra_kg/measure_catalog.csv \\
      --out data/zebra_kg/dax_patterns.json
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CATALOG = REPO_ROOT / "data/zebra_kg/measure_catalog.csv"
DEFAULT_OUT = REPO_ROOT / "data/zebra_kg/dax_patterns.json"

# Feature tag definitions. More-specific tags listed first.
_FEATURE_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("time:dates_in_period", re.compile(r"\bDATESINPERIOD\b", re.IGNORECASE)),
    ("time:date_add", re.compile(r"\bDATEADD\b", re.IGNORECASE)),
    ("time:sameperiodlastyear", re.compile(r"\bSAMEPERIODLASTYEAR\b", re.IGNORECASE)),
    ("time:datesytd", re.compile(r"\bDATESYTD\b", re.IGNORECASE)),
    ("time:datesbetween", re.compile(r"\bDATESBETWEEN\b", re.IGNORECASE)),
    ("time:today_arithmetic", re.compile(r"\bTODAY\s*\(\s*\)\s*(?:[-+]|,\s*-)")),
    ("agg:sum", re.compile(r"\bSUM\s*\(", re.IGNORECASE)),
    ("agg:countrows", re.compile(r"\bCOUNTROWS\s*\(", re.IGNORECASE)),
    ("agg:divide", re.compile(r"\bDIVIDE\s*\(", re.IGNORECASE)),
    ("agg:sumx", re.compile(r"\bSUMX\s*\(", re.IGNORECASE)),
    ("agg:countx", re.compile(r"\bCOUNTX\s*\(", re.IGNORECASE)),
    ("agg:averagex", re.compile(r"\bAVERAGEX\s*\(", re.IGNORECASE)),
    ("filter:calculate", re.compile(r"\bCALCULATE\s*\(", re.IGNORECASE)),
    ("filter:filter", re.compile(r"\bFILTER\s*\(", re.IGNORECASE)),
    ("filter:keepfilters", re.compile(r"\bKEEPFILTERS\s*\(", re.IGNORECASE)),
    ("filter:all", re.compile(r"\bALL\s*\(", re.IGNORECASE)),
    ("filter:allexcept", re.compile(r"\bALLEXCEPT\s*\(", re.IGNORECASE)),
    ("filter:removefilters", re.compile(r"\bREMOVEFILTERS\s*\(", re.IGNORECASE)),
    ("cond:if", re.compile(r"\bIF\s*\(", re.IGNORECASE)),
    ("cond:switch", re.compile(r"\bSWITCH\s*\(", re.IGNORECASE)),
    ("var", re.compile(r"\bVAR\b", re.IGNORECASE)),
    ("lookup:related", re.compile(r"\bRELATED\s*\(", re.IGNORECASE)),
    ("lookup:lookupvalue", re.compile(r"\bLOOKUPVALUE\s*\(", re.IGNORECASE)),
]

_PRETTY_NAMES = {
    frozenset({"time:dates_in_period", "agg:sum", "filter:calculate"}): "time_window_calculate_sum",
    frozenset({"time:sameperiodlastyear", "filter:calculate"}): "yoy_via_sameperiodlastyear",
    frozenset({"time:datesytd", "filter:calculate"}): "ytd_via_datesytd",
    frozenset({"agg:divide"}): "safe_ratio",
    frozenset({"filter:calculate", "filter:filter"}): "filter_calculate_predicate",
    frozenset({"cond:if", "filter:calculate"}): "conditional_aggregate",
    frozenset({"agg:countrows", "filter:calculate"}): "filtered_row_count",
}


def extract_feature_tags(dax: str | None) -> frozenset[str]:
    """Return the set of feature tags for a DAX expression."""
    if not isinstance(dax, str) or not dax.strip():
        return frozenset()
    tags: set[str] = set()
    for tag, pat in _FEATURE_PATTERNS:
        if pat.search(dax):
            tags.add(tag)
    return frozenset(tags)


def pattern_name_for_signature(sig: frozenset[str]) -> str:
    """Deterministic pattern name from a tag set."""
    if not sig:
        return "pattern_no_features"
    if sig in _PRETTY_NAMES:
        return _PRETTY_NAMES[sig]
    return "+".join(sorted(sig))


@dataclass
class Pattern:
    name: str
    signature: list = field(default_factory=list)
    match_count: int = 0
    templates: list = field(default_factory=list)
    canonical_example: dict = field(default_factory=dict)
    samples: list = field(default_factory=list)


def build_atlas(rows: Iterable[dict]) -> dict:
    """Cluster measures by feature signature into atlas dict."""
    by_sig: dict[frozenset, list[dict]] = defaultdict(list)
    for row in rows:
        dax = row.get("expression", "") or ""
        sig = extract_feature_tags(dax)
        by_sig[sig].append(row)

    patterns: dict[str, dict] = {}
    misc: list[dict] = []
    for sig, measures in by_sig.items():
        if len(measures) <= 2:
            misc.extend(measures)
            continue
        name = pattern_name_for_signature(sig)
        templates = sorted({m["template_slug"] for m in measures})
        canonical = max(measures, key=lambda m: len(m.get("expression", "") or ""))
        patterns[name] = {
            "signature": sorted(sig),
            "match_count": len(measures),
            "templates": templates,
            "canonical_example": {
                "name": canonical["name"],
                "table": canonical.get("table", ""),
                "template": canonical["template_slug"],
                "expression": canonical.get("expression", "") or "",
                "format_string": canonical.get("format_string", "") or "",
            },
            "samples": [{"name": m["name"], "template": m["template_slug"]} for m in measures[:8]],
        }

    if misc:
        patterns["pattern_misc"] = {
            "signature": [],
            "match_count": len(misc),
            "templates": sorted({m["template_slug"] for m in misc}),
            "canonical_example": {},
            "samples": [{"name": m["name"], "template": m["template_slug"]} for m in misc[:8]],
        }

    return {
        "total_measures": sum(p["match_count"] for p in patterns.values()),
        "pattern_count": len(patterns),
        "patterns": patterns,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[0])
    parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()

    catalog = args.catalog.expanduser()
    rows = list(csv.DictReader(catalog.open()))
    atlas_obj = build_atlas(rows)

    out = args.out.expanduser()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(atlas_obj, indent=2, ensure_ascii=False) + "\n")

    print(f"measures: {atlas_obj['total_measures']}")
    print(f"patterns: {atlas_obj['pattern_count']}")
    print("top 8 by match_count:")
    for name, p in sorted(
        atlas_obj["patterns"].items(),
        key=lambda kv: -kv[1]["match_count"],
    )[:8]:
        print(f"  {name:48} {p['match_count']:4}  templates={len(p['templates'])}")
    print(f"out: {out}")


if __name__ == "__main__":
    main()
