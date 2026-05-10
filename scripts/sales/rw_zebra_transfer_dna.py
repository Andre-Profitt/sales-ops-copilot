"""Extract reusable Zebra BI visual DNA from mined Power BI report.json files.

The transfer path keeps Zebra's useful grammar (scenario roles, variance-pair
intent, zones, static furniture) while making the rebuild stage emit native
Power BI visuals only.
"""

from __future__ import annotations

import json
import zipfile
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SOURCE_DIR = Path("/Users/test/Downloads/rw-zebra-bi-template-research-20260509/pbix-extracted")
TRANSFER_DIR = REPO_ROOT / "data/zebra_kg/transfer"

ZEBRA_TABLES = "ZebraBITables"
ZEBRA_CARDS = "zebraBiCards"
ZEBRA_CHARTS = "ZebraBICharts"
ZEBRA_WATERFALL = "waterfall"

_SCENARIO_BY_ROLE = {
    "Values": "AC",
    "Y": "AC",
    "Measures": "AC",
    "Actual": "AC",
    "PreviousYear": "PY",
    "Plan": "PL",
    "Forecast": "FC",
}
_VARIANCE_PAIRS = (
    ("AC", "PY", "actual-previousYear"),
    ("AC", "PL", "actual-plan"),
    ("AC", "FC", "actual-forecast"),
    ("FC", "PL", "forecast-plan"),
)


def _decode_config(vc: dict) -> dict:
    raw = vc.get("config", {})
    if isinstance(raw, str):
        return json.loads(raw) if raw else {}
    return raw or {}


def _bbox(vc: dict) -> dict[str, float]:
    return {
        "x": float(vc.get("x", 0) or 0),
        "y": float(vc.get("y", 0) or 0),
        "w": float(vc.get("width", vc.get("w", 0)) or 0),
        "h": float(vc.get("height", vc.get("h", 0)) or 0),
    }


def page_zone(bbox: dict, *, width: float = 1280, height: float = 720) -> str:
    """Return coarse page zone: header/body/footer × left/center/right."""
    x = float(bbox.get("x", 0) or 0)
    y = float(bbox.get("y", 0) or 0)
    w = float(bbox.get("w", bbox.get("width", 0)) or 0)
    h = float(bbox.get("h", bbox.get("height", 0)) or 0)
    cx = x + w / 2

    if y < height * 0.12:
        row = "header"
    elif y + h > height * 0.86 or y > height * 0.76:
        row = "footer"
    else:
        row = "body"

    if cx < width / 3:
        col = "left"
    elif cx < 2 * width / 3:
        col = "center"
    else:
        col = "right"
    return f"{row}_{col}"


def zebra_derived_variance_columns(scenarios: set[str]) -> list[dict]:
    """Return native variance columns implied by Zebra scenario pair grammar."""
    columns: list[dict] = []
    for left, right, key in _VARIANCE_PAIRS:
        if {left, right} <= scenarios:
            label = f"{left}-{right}"
            pair = [left, right]
            columns.append(
                {"key": key, "label": label, "scenario_pair": pair, "role": "delta", "format": 1}
            )
            columns.append(
                {
                    "key": f"{key}-percent",
                    "label": f"{label} %",
                    "scenario_pair": pair,
                    "role": "relative",
                    "format": 2,
                }
            )
    return columns


def _projection_roles(single_visual: dict) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for role, projections in (single_visual.get("projections") or {}).items():
        refs = [p.get("queryRef") for p in projections if isinstance(p, dict) and p.get("queryRef")]
        if refs:
            out[role] = refs
    return out


def _scenarios_from_roles(roles: dict[str, list[str]]) -> set[str]:
    scenarios: set[str] = set()
    for role, scenario in _SCENARIO_BY_ROLE.items():
        if roles.get(role):
            scenarios.add(scenario)
    return scenarios


def _scenario_pairing(roles: dict[str, list[str]]) -> list[str]:
    scenarios = _scenarios_from_roles(roles)
    if "AC" in scenarios:
        for candidate in ("PY", "PL", "FC"):
            if candidate in scenarios:
                return ["AC", candidate]
    if {"FC", "PL"} <= scenarios:
        return ["FC", "PL"]
    return sorted(scenarios)


def _visual_family(visual_type: str) -> str:
    if visual_type.startswith(ZEBRA_TABLES):
        return "Tables"
    if visual_type.startswith(ZEBRA_CARDS):
        return "Cards"
    if visual_type.startswith(ZEBRA_CHARTS):
        return "Charts"
    if visual_type.startswith(ZEBRA_WATERFALL):
        return "Waterfall"
    return "Other"


def _column_settings(objects: dict) -> dict:
    for entry in objects.get("chartSettings") or []:
        props = entry.get("properties") if isinstance(entry, dict) else None
        settings = props.get("columnSettings") if isinstance(props, dict) else None
        if isinstance(settings, dict):
            return settings
    return {}


def _style(objects: dict) -> dict:
    title = {}
    for entry in objects.get("titleSettings") or []:
        props = entry.get("properties") if isinstance(entry, dict) else None
        if isinstance(props, dict):
            title = dict(props)
            break
    data_label = {}
    for entry in objects.get("dataLabelSettings") or []:
        props = entry.get("properties") if isinstance(entry, dict) else None
        if isinstance(props, dict):
            data_label = dict(props)
            break
    grid = {}
    for group in ("grid", "multipleLayout"):
        if objects.get(group):
            grid[group] = [entry.get("properties", {}) for entry in objects[group] if isinstance(entry, dict)]
    return {
        "title": title,
        "data_labels": data_label,
        "grid": grid,
        "border": {"coreSettings": [entry.get("properties", {}) for entry in objects.get("coreSettings", []) if isinstance(entry, dict)]},
        "background": {"designSettings": [entry.get("properties", {}) for entry in objects.get("designSettings", []) if isinstance(entry, dict)]},
        "accent": {"chartSettings": [entry.get("properties", {}) for entry in objects.get("chartSettings", []) if isinstance(entry, dict)]},
        "typography": {"titleSettings": title, "dataLabelSettings": data_label},
    }


def _sanitized_objects(objects: dict) -> dict:
    """Preserve visual grammar without persisting Zebra license/activation blobs."""
    return {
        group: entries
        for group, entries in (objects or {}).items()
        if "license" not in group.lower() and "activation" not in group.lower()
    }


def _column_markers(column_settings: dict) -> dict:
    markers = {}
    for key, cfg in column_settings.items():
        table_view = cfg.get("tableView", {}) if isinstance(cfg, dict) else {}
        chart_view = cfg.get("chartView", {}) if isinstance(cfg, dict) else {}
        markers[key] = {
            "markerStyle": table_view.get("markerStyle", chart_view.get("markerStyle")),
            "showAsTable": table_view.get("showAsTable", chart_view.get("showAsTable")),
            "scaleGroup": cfg.get("scaleGroup") if isinstance(cfg, dict) else None,
            "format": cfg.get("format") if isinstance(cfg, dict) else None,
            "hidden": table_view.get("hidden", chart_view.get("hidden")),
        }
    return markers


def _literal_text_runs(node: Any) -> list[str]:
    chunks: list[str] = []
    if isinstance(node, dict):
        if "textRuns" in node and isinstance(node["textRuns"], list):
            for run in node["textRuns"]:
                if not isinstance(run, dict):
                    continue
                value = run.get("value", "")
                if isinstance(value, str):
                    chunks.append(value)
        for value in node.values():
            chunks.extend(_literal_text_runs(value))
    elif isinstance(node, list):
        for item in node:
            chunks.extend(_literal_text_runs(item))
    return chunks


def _textbox_text(vc: dict) -> str:
    cfg = _decode_config(vc)
    return "".join(_literal_text_runs(cfg.get("singleVisual", {}).get("objects", {}))).strip()


def _decode_report_payload(raw: bytes, member_name: str) -> dict:
    encoding = "utf-16-le" if member_name == "Report/Layout" else "utf-8"
    return json.loads(raw.decode(encoding))


def load_report_from_pbix(path: Path) -> dict:
    """Load a Power BI report layout from a PBIX/PBIT zip or extracted directory."""
    path = path.expanduser()
    if path.is_dir():
        candidates = [
            ("Report/Layout", path / "Report" / "Layout"),
            ("Report/report.json", path / "Report" / "report.json"),
            ("report.json", path / "report.json"),
            ("Layout", path / "Layout"),
        ]
        for member_name, candidate in candidates:
            if candidate.exists():
                return _decode_report_payload(candidate.read_bytes(), member_name)
        raise FileNotFoundError(f"No report layout found under {path}")
    with zipfile.ZipFile(path) as archive:
        for member in ("Report/Layout", "Report/report.json", "report.json"):
            try:
                return _decode_report_payload(archive.read(member), member)
            except KeyError:
                continue
    raise FileNotFoundError(f"No report layout member found in {path}")


def _static_furniture(section: dict, page_width: float, page_height: float) -> list[dict]:
    furniture: list[dict] = []
    for vc in section.get("visualContainers", []):
        cfg = _decode_config(vc)
        sv = cfg.get("singleVisual") or {}
        if sv.get("visualType") != "textbox":
            continue
        box = _bbox(vc)
        furniture.append(
            {
                "visual_id": cfg.get("name", ""),
                "visual_type": "textbox",
                "text": _textbox_text(vc),
                "bounding_box": box,
                "page_zone": page_zone(box, width=page_width, height=page_height),
            }
        )
    return furniture


def _visual_intent(family: str, scenarios: set[str]) -> str:
    if family == "Tables" and len(scenarios) >= 2:
        return "variance table"
    if family == "Cards":
        return "KPI strip"
    if family == "Waterfall":
        return "waterfall"
    if family == "Charts":
        return "chart"
    return "unknown"


def extract_visual_dna_from_report(template_slug: str, report: dict) -> dict:
    """Extract Zebra visual grammar and nearby static furniture from a report."""
    visuals: list[dict] = []
    for section in report.get("sections", []):
        page_width = float(section.get("width") or report.get("width") or 1280)
        page_height = float(section.get("height") or report.get("height") or 720)
        furniture = _static_furniture(section, page_width, page_height)
        for vc in section.get("visualContainers", []):
            cfg = _decode_config(vc)
            sv = cfg.get("singleVisual") or {}
            visual_type = str(sv.get("visualType", ""))
            family = _visual_family(visual_type)
            if family == "Other":
                continue
            roles = _projection_roles(sv)
            scenarios = _scenarios_from_roles(roles)
            box = _bbox(vc)
            col_settings = _column_settings(sv.get("objects") or {})
            visuals.append(
                {
                    "visual_id": cfg.get("name", ""),
                    "template_slug": template_slug,
                    "page_name": section.get("name", ""),
                    "page_display_name": section.get("displayName", section.get("name", "")),
                    "visual_family": family,
                    "visual_type_full": visual_type,
                    "bounding_box": box,
                    "page_zone": page_zone(box, width=page_width, height=page_height),
                    "projection_roles": roles,
                    "scenario_pairing": _scenario_pairing(roles),
                    "derived_variance_columns": zebra_derived_variance_columns(scenarios),
                    "column_settings": col_settings,
                    "column_markers": _column_markers(col_settings),
                    "objects": _sanitized_objects(sv.get("objects") or {}),
                    "style": _style(sv.get("objects") or {}),
                    "static_furniture": furniture,
                    "visual_intent": _visual_intent(family, scenarios),
                }
            )
    return {"template_slug": template_slug, "visual_count": len(visuals), "visuals": visuals}


def build_page_patterns(dna: dict) -> dict:
    pages: dict[tuple[str, str], dict] = {}
    furniture_seen: dict[tuple[str, str], set[str]] = defaultdict(set)
    for visual in dna.get("visuals", []):
        key = (visual.get("page_name", ""), visual.get("page_display_name", ""))
        page = pages.setdefault(
            key,
            {
                "page_name": key[0],
                "page_display_name": key[1],
                "visual_family_counts": Counter(),
                "intent_counts": Counter(),
                "scenario_pairings": set(),
                "static_furniture_count": 0,
            },
        )
        page["visual_family_counts"][visual.get("visual_family", "Other")] += 1
        page["intent_counts"][visual.get("visual_intent", "unknown")] += 1
        pairing = tuple(visual.get("scenario_pairing") or [])
        if pairing:
            page["scenario_pairings"].add(pairing)
        for item in visual.get("static_furniture", []):
            fid = item.get("visual_id") or item.get("text") or repr(item)
            if fid not in furniture_seen[key]:
                furniture_seen[key].add(fid)
                page["static_furniture_count"] += 1

    normalized = []
    for page in pages.values():
        normalized.append(
            {
                **page,
                "visual_family_counts": dict(page["visual_family_counts"]),
                "intent_counts": dict(page["intent_counts"]),
                "scenario_pairings": [list(pair) for pair in sorted(page["scenario_pairings"])],
            }
        )
    normalized.sort(key=lambda item: item["page_display_name"])
    return {"template_slug": dna.get("template_slug", ""), "page_count": len(normalized), "pages": normalized}


def extract_visual_dna_from_pbix(template_slug: str, pbix_path: Path) -> dict:
    return extract_visual_dna_from_report(template_slug, load_report_from_pbix(pbix_path))


def persist_transfer_artifacts(template_slug: str, dna: dict, patterns: dict, out_dir: Path = TRANSFER_DIR) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    dna_path = out_dir / f"visual_dna_{template_slug}.json"
    patterns_path = out_dir / f"page_patterns_{template_slug}.json"
    dna_path.write_text(json.dumps(dna, indent=2, ensure_ascii=False) + "\n")
    patterns_path.write_text(json.dumps(patterns, indent=2, ensure_ascii=False) + "\n")
    return dna_path, patterns_path


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Extract granular Zebra visual DNA transfer artifacts.")
    parser.add_argument("--template", default="sales-funnel-power-bi-template")
    parser.add_argument("--source-dir", type=Path, default=DEFAULT_SOURCE_DIR)
    parser.add_argument("--out-dir", type=Path, default=TRANSFER_DIR)
    args = parser.parse_args()
    pbix_path = args.source_dir.expanduser() / f"{args.template}.pbix"
    dna = extract_visual_dna_from_pbix(args.template, pbix_path)
    patterns = build_page_patterns(dna)
    dna_path, patterns_path = persist_transfer_artifacts(args.template, dna, patterns, args.out_dir)
    print(json.dumps({"template_slug": args.template, "visuals": dna["visual_count"], "dna_path": str(dna_path), "patterns_path": str(patterns_path)}, indent=2))


if __name__ == "__main__":
    main()
