"""Translate one Zebra template's full visualContainer corpus into a native
PBIR report.json — quick test harness for the rw_zebra_kg_translator.

Loads:
- data/zebra_kg/infrastructure/raw_configs.jsonl (filtered by template_slug)
- data/zebra_kg/schemas/<slug>/measures.csv  (target measure catalog)

Emits:
- data/zebra_kg/test_dashboards/<slug>.report.json  (single-page report.json)

Usage:
    python3 -m scripts.sales.rw_zebra_kg_test_dashboard \\
      --template cost-management-power-bi-template

    # list available templates with VC counts
    python3 -m scripts.sales.rw_zebra_kg_test_dashboard --list
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path

from scripts.sales.rw_zebra_kg_translator import (
    BindMap,
    MeasureCatalog,
    translate_visual,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
RAW_PATH = REPO_ROOT / "data/zebra_kg/infrastructure/raw_configs.jsonl"
SCHEMAS_DIR = REPO_ROOT / "data/zebra_kg/schemas"
OUT_DIR = REPO_ROOT / "data/zebra_kg/test_dashboards"


def list_templates() -> list[tuple[str, int]]:
    counts: Counter = Counter()
    with RAW_PATH.open() as f:
        for line in f:
            counts[json.loads(line)["template_slug"]] += 1
    return sorted(counts.items(), key=lambda x: -x[1])


def load_catalog(slug: str) -> MeasureCatalog:
    csv_path = SCHEMAS_DIR / slug / "measures.csv"
    if not csv_path.exists():
        return MeasureCatalog()
    by_scenario: dict[str, str] = {}
    measure_to_table: dict[str, str] = {}
    with csv_path.open() as f:
        for row in csv.DictReader(f):
            name = row["name"]
            tbl = row["table"]
            by_scenario[name] = name
            measure_to_table[name] = tbl
    return MeasureCatalog(by_scenario=by_scenario, measure_to_table=measure_to_table)


def load_raw_rows(slug: str) -> list[dict]:
    rows: list[dict] = []
    with RAW_PATH.open() as f:
        for line in f:
            r = json.loads(line)
            if r["template_slug"] == slug:
                rows.append(r)
    return rows


def raw_to_layout_vc(raw: dict) -> dict:
    pos = raw["position"]
    return {
        "x": pos["x"],
        "y": pos["y"],
        "width": pos["w"],
        "height": pos["h"],
        "config": json.dumps(
            {
                "name": "raw",
                "singleVisual": {
                    "visualType": raw["visual_type_full"],
                    "projections": {
                        role: [{"queryRef": q} for q in qs]
                        for role, qs in raw.get("projections", {}).items()
                    },
                },
            }
        ),
    }


def build_report(slug: str, vcs: list[dict]) -> dict:
    return {
        "config": json.dumps(
            {
                "version": "5.43",
                "themeCollection": {"baseTheme": {"name": "CY24SU10"}},
                "activeSectionIndex": 0,
                "defaultDrillFilterOtherVisuals": True,
                "linguisticSchemaSyncVersion": 0,
                "settings": {"useStylableVisualContainerHeader": True},
            }
        ),
        "layoutOptimization": 0,
        "resourcePackages": [],
        "sections": [
            {
                "name": "TestPage",
                "displayName": f"Translated: {slug}",
                "displayOption": 1,
                "filters": "[]",
                "height": 720,
                "width": 1280,
                "ordinal": 0,
                "visualContainers": vcs,
            }
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[0])
    parser.add_argument("--template", help="Template slug to translate")
    parser.add_argument(
        "--list", action="store_true", help="List available templates with VC counts"
    )
    args = parser.parse_args()

    if args.list or not args.template:
        for slug, n in list_templates():
            print(f"  {n:4}  {slug}")
        return

    slug = args.template
    raw_rows = load_raw_rows(slug)
    if not raw_rows:
        print(f"no rows for template {slug!r}; run with --list to see available")
        return

    catalog = load_catalog(slug)
    bm = BindMap()

    family_in: Counter = Counter()
    family_out: Counter = Counter()
    translated: list[dict] = []
    for raw in raw_rows:
        family_in[raw["visual_family"]] += 1
        src = raw_to_layout_vc(raw)
        out = translate_visual(src, catalog, bm)
        for vc in out:
            cstr = vc.get("config")
            if isinstance(cstr, str):
                try:
                    cfg = json.loads(cstr)
                    vt = (cfg.get("singleVisual") or {}).get("visualType", "?")
                    family_out[vt] += 1
                except json.JSONDecodeError:
                    family_out["<parse-fail>"] += 1
            translated.extend([vc])

    report = build_report(slug, translated)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUT_DIR / f"{slug}.report.json"
    out_path.write_text(json.dumps(report, indent=2, ensure_ascii=False))

    drops = len(raw_rows) - sum(
        1
        for vc in translated
        if isinstance(vc.get("config"), str)
        and "ZebraBI" not in vc["config"]
        and "zebraBi" not in vc["config"]
    )

    print(f"\n=== {slug} ===")
    print(f"input visualContainers : {len(raw_rows)}")
    print(f"catalog measures       : {len(catalog.by_scenario)}")
    print(f"output visualContainers: {len(translated)}")
    print("\nsource families:")
    for fam, n in sorted(family_in.items(), key=lambda x: -x[1]):
        print(f"  {n:3}  {fam}")
    print("\noutput visualTypes:")
    for vt, n in sorted(family_out.items(), key=lambda x: -x[1]):
        print(f"  {n:3}  {vt}")
    print(f"\nwritten: {out_path.relative_to(REPO_ROOT)}")
    print(
        f"size: {out_path.stat().st_size:,} bytes  "
        f"(inspect with `jq '.sections[0].visualContainers | length' {out_path}`)"
    )


if __name__ == "__main__":
    main()
