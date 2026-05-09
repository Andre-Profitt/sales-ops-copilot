"""Analyze the raw Zebra config rows into structured atlases:

- objects_atlas.json: every objects.<group>.<property> seen + frequency,
  per-visual-family, with sample values per property
- columnSettings_atlas.json: every distinct comparison-key seen, plus
  format/markerStyle/scaleGroup/showAsTable enum value distributions
- projections_atlas.json: which projection roles each visual family uses,
  combinations of roles seen
- visual_capabilities.json: capabilities + dataView mapping declarations
  per Zebra .pbiviz package
- summary.json: top-line counts and findings

Usage:
    python3 -m scripts.sales.rw_zebra_kg_infra_analyzer \\
      --infra-dir data/zebra_kg/infrastructure
"""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INFRA = REPO_ROOT / "data/zebra_kg/infrastructure"


def _read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line]


def analyze_objects(rows: list[dict]) -> dict:
    """Per-visual-family object-group atlas.

    For each visual family (ZebraBITables, ZebraBICards, etc.), enumerate
    every objects.<group> seen, every property key inside it, and the
    distinct values that property has taken (capped to 8 per property to
    avoid noise from per-cell colors / arbitrary text).
    """
    by_family: dict[str, dict[str, dict]] = defaultdict(
        lambda: defaultdict(
            lambda: {
                "entry_count": 0,
                "templates": set(),
                "properties": defaultdict(
                    lambda: {
                        "occurrences": 0,
                        "distinct_values": [],
                        "_seen": set(),  # internal: stringified values seen
                    }
                ),
            }
        )
    )

    for row in rows:
        family = row["visual_family"]
        slug = row["template_slug"]
        for group_name, entries in (row["objects"] or {}).items():
            if group_name == "licenseSettings":
                # don't capture license keys — sensitive
                continue
            grp = by_family[family][group_name]
            grp["entry_count"] += len(entries) if entries else 0
            grp["templates"].add(slug)
            for entry in entries or []:
                props = entry.get("properties") or {}
                for k, v in props.items():
                    p = grp["properties"][k]
                    p["occurrences"] += 1
                    # Stringify value for dedupe
                    try:
                        s = json.dumps(v, sort_keys=True, default=str)
                    except Exception:
                        s = str(v)
                    if s not in p["_seen"] and len(p["distinct_values"]) < 8:
                        p["_seen"].add(s)
                        # Truncate huge structured values for readability
                        if len(s) > 200:
                            v = s[:200] + "..."
                        p["distinct_values"].append(v)

    # Materialize sets/internal fields
    out: dict[str, Any] = {}
    for family, groups in by_family.items():
        out[family] = {}
        for group_name, g in groups.items():
            props_out = {}
            for k, p in g["properties"].items():
                props_out[k] = {
                    "occurrences": p["occurrences"],
                    "distinct_value_count": len(p["_seen"]),
                    "sample_values": p["distinct_values"],
                }
            out[family][group_name] = {
                "entry_count": g["entry_count"],
                "template_count": len(g["templates"]),
                "templates": sorted(g["templates"]),
                "properties": props_out,
            }
    return out


def analyze_column_settings(rows: list[dict]) -> dict:
    """Decode every chartSettings.columnSettings dict and aggregate the IBCS
    rendering grammar Zebra encodes."""
    comparison_keys: Counter = Counter()  # {key: count} where keys like "actual", "actual-plan"
    format_codes: Counter = Counter()
    marker_styles: Counter = Counter()
    show_as_table: Counter = Counter()
    scale_groups: Counter = Counter()
    invert_count = 0
    total_settings = 0
    suppress_others_count = 0
    use_measure_name_count = 0

    by_family_comparison_keys: dict[str, Counter] = defaultdict(Counter)
    samples_by_key: dict[str, list[dict]] = defaultdict(list)

    for row in rows:
        family = row["visual_family"]
        chart_entries = (row["objects"] or {}).get("chartSettings") or []
        for entry in chart_entries:
            cs = (entry.get("properties") or {}).get("columnSettings")
            if not isinstance(cs, dict):
                continue
            for key, settings in cs.items():
                comparison_keys[key] += 1
                by_family_comparison_keys[family][key] += 1
                if isinstance(settings, dict):
                    total_settings += 1
                    if settings.get("invert"):
                        invert_count += 1
                    if settings.get("suppressOthers"):
                        suppress_others_count += 1
                    if settings.get("useMeasureName"):
                        use_measure_name_count += 1
                    fmt = settings.get("format")
                    if fmt is not None:
                        format_codes[fmt] += 1
                    sg = settings.get("scaleGroup")
                    if sg is not None:
                        scale_groups[sg] += 1
                    for view in ("tableView", "chartView"):
                        v = settings.get(view) or {}
                        ms = v.get("markerStyle")
                        if ms is not None:
                            marker_styles[ms] += 1
                        sat = v.get("showAsTable")
                        if sat is not None:
                            show_as_table[sat] += 1
                    if len(samples_by_key[key]) < 3:
                        samples_by_key[key].append(
                            {
                                "template": row["template_slug"],
                                "page": row["page_display_name"],
                                "settings": settings,
                            }
                        )

    return {
        "total_columnSettings_entries": total_settings,
        "comparison_keys": dict(comparison_keys.most_common()),
        "comparison_keys_by_family": {
            f: dict(c.most_common()) for f, c in by_family_comparison_keys.items()
        },
        "format_codes": dict(format_codes.most_common()),
        "marker_styles": dict(marker_styles.most_common()),
        "show_as_table": dict(show_as_table.most_common()),
        "scale_groups": dict(scale_groups.most_common()),
        "invert_true_count": invert_count,
        "suppress_others_count": suppress_others_count,
        "use_measure_name_count": use_measure_name_count,
        "samples": {k: v for k, v in samples_by_key.items()},
    }


def analyze_projections(rows: list[dict]) -> dict:
    """Which projection roles each visual family uses + role combinations."""
    role_freq_by_family: dict[str, Counter] = defaultdict(Counter)
    combos_by_family: dict[str, Counter] = defaultdict(Counter)

    for row in rows:
        family = row["visual_family"]
        roles_used = sorted(row["projections"].keys())
        for r in roles_used:
            role_freq_by_family[family][r] += 1
        if roles_used:
            combos_by_family[family][" + ".join(roles_used)] += 1

    return {
        "role_frequency_by_family": {
            f: dict(c.most_common()) for f, c in role_freq_by_family.items()
        },
        "role_combinations_by_family": {
            f: dict(c.most_common(20)) for f, c in combos_by_family.items()
        },
    }


def analyze_visual_packages(packages: dict) -> dict:
    """Per-Zebra-visual capabilities + dataView mapping declarations."""
    by_guid: dict[str, dict] = {}
    for slug, pkgs in packages.items():
        for pkg in pkgs:
            guid = pkg.get("visual_guid", "")
            if guid in by_guid:
                continue
            summary = pkg.get("pbiviz_summary") or {}
            visual = summary.get("visual") or {}
            caps = summary.get("capabilities") or {}
            by_guid[guid] = {
                "guid": guid,
                "displayName": visual.get("displayName"),
                "name": visual.get("name"),
                "version": visual.get("version"),
                "apiVersion": summary.get("apiVersion"),
                "supportUrl": visual.get("supportUrl"),
                "dataRoles": [
                    {
                        "name": r.get("name"),
                        "kind": r.get("kind"),
                        "displayName": r.get("displayName"),
                    }
                    for r in (caps.get("dataRoles") or [])
                ],
                "object_groups": list((caps.get("objects") or {}).keys()),
                "dataViewMappings_count": len(caps.get("dataViewMappings") or []),
                "first_template": slug,
            }
    return by_guid


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[0])
    parser.add_argument("--infra-dir", type=Path, default=DEFAULT_INFRA)
    args = parser.parse_args()

    infra = args.infra_dir.expanduser()
    raw = _read_jsonl(infra / "raw_configs.jsonl")
    pkgs = json.loads((infra / "visual_packages.json").read_text())

    objects_atlas = analyze_objects(raw)
    cs_atlas = analyze_column_settings(raw)
    proj_atlas = analyze_projections(raw)
    cap_atlas = analyze_visual_packages(pkgs)

    (infra / "objects_atlas.json").write_text(
        json.dumps(objects_atlas, indent=2, ensure_ascii=False) + "\n"
    )
    (infra / "columnSettings_atlas.json").write_text(
        json.dumps(cs_atlas, indent=2, ensure_ascii=False) + "\n"
    )
    (infra / "projections_atlas.json").write_text(
        json.dumps(proj_atlas, indent=2, ensure_ascii=False) + "\n"
    )
    (infra / "visual_capabilities.json").write_text(
        json.dumps(cap_atlas, indent=2, ensure_ascii=False) + "\n"
    )

    summary = {
        "total_zebra_visuals": len(raw),
        "by_family": dict(Counter(r["visual_family"] for r in raw).most_common()),
        "objects_groups_per_family": {f: list(g.keys()) for f, g in objects_atlas.items()},
        "comparison_keys_distinct": len(cs_atlas["comparison_keys"]),
        "comparison_keys_top10": dict(list(cs_atlas["comparison_keys"].items())[:10]),
        "format_codes_seen": cs_atlas["format_codes"],
        "marker_styles_seen": cs_atlas["marker_styles"],
        "show_as_table_seen": cs_atlas["show_as_table"],
        "scale_groups_seen": cs_atlas["scale_groups"],
        "zebra_packages_distinct": len(cap_atlas),
        "package_data_roles": {
            g: [r["name"] for r in v["dataRoles"]] for g, v in cap_atlas.items()
        },
    }
    (infra / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n")

    # Print headline findings
    print("=== ZEBRA INFRASTRUCTURE — TOP-LINE FINDINGS ===\n")
    print(f"Total Zebra visualContainers analyzed: {summary['total_zebra_visuals']}")
    print(f"By family: {summary['by_family']}\n")

    print("OBJECTS GROUPS per visual family:")
    for fam, groups in summary["objects_groups_per_family"].items():
        print(f"  {fam}: {groups}")
    print()

    print("COMPARISON KEYS (top 15) — these are the IBCS-derived columns Zebra synthesizes:")
    for k, n in list(cs_atlas["comparison_keys"].items())[:15]:
        print(f"  {k:30} {n:4}")
    print(f"  ...{summary['comparison_keys_distinct']} distinct keys total")
    print()

    print("FORMAT codes seen (the integer 'format' on a column setting):")
    for k, n in cs_atlas["format_codes"].items():
        print(f"  format={k:4} → {n} occurrences")
    print()

    print("MARKER STYLES seen:")
    for k, n in cs_atlas["marker_styles"].items():
        print(f"  markerStyle={k:4} → {n} occurrences")
    print()

    print("SHOW_AS_TABLE values:")
    for k, n in cs_atlas["show_as_table"].items():
        print(f"  showAsTable={k:4} → {n} occurrences")
    print()

    print("SCALE GROUPS seen:")
    for k, n in cs_atlas["scale_groups"].items():
        print(f"  scaleGroup={k:4} → {n} occurrences")
    print()

    print(f"ZEBRA CUSTOM VISUAL PACKAGES ({len(cap_atlas)}):")
    for guid, info in cap_atlas.items():
        print(f"  {info['displayName']:25} v{info['version']}  apiVersion={info['apiVersion']}")
        print(f"    dataRoles: {[r['name'] for r in info['dataRoles']]}")
        print(f"    object_groups: {info['object_groups'][:8]}")
    print()

    print("PROJECTION ROLE COMBOS by family:")
    for fam, combos in proj_atlas["role_combinations_by_family"].items():
        print(f"  {fam}:")
        for combo, n in list(combos.items())[:5]:
            print(f"    {combo:60} {n}")
    print(
        f"\nwrote: {infra}/{{objects_atlas,columnSettings_atlas,projections_atlas,visual_capabilities,summary}}.json"
    )


if __name__ == "__main__":
    main()
