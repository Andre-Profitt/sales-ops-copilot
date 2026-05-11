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


def _sensitive_key(key: str) -> bool:
    key_l = str(key).lower()
    return "license" in key_l or "activation" in key_l or ("key" in key_l and "legend" not in key_l)


def _sanitize_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _sanitize_value(v) for k, v in value.items() if not _sensitive_key(str(k))}
    if isinstance(value, list):
        return [_sanitize_value(item) for item in value]
    return value


def _sanitized_objects(objects: dict) -> dict:
    """Preserve visual grammar without persisting Zebra license/activation blobs."""
    return {
        group: _sanitize_value(entries)
        for group, entries in (objects or {}).items()
        if not _sensitive_key(group)
    }


SAFE_OBJECT_GROUPS = {
    "chartSettings",
    "designSettings",
    "dataLabelSettings",
    "titleSettings",
    "grid",
    "multipleLayout",
    "coreSettings",
}


def _safe_property_subset(properties: dict) -> dict:
    allowed_fragments = (
        "alignment",
        "background",
        "border",
        "color",
        "columnsettings",
        "font",
        "format",
        "grid",
        "hidden",
        "label",
        "layout",
        "marker",
        "text",
        "padding",
        "scale",
        "show",
        "spacing",
        "table",
        "title",
        "transparency",
        "width",
    )
    safe = {}
    for key, value in (properties or {}).items():
        key_l = str(key).lower()
        if "license" in key_l or "activation" in key_l or "key" in key_l and "legend" not in key_l:
            continue
        if any(fragment in key_l for fragment in allowed_fragments):
            safe[key] = value
    return safe


def _visual_object_grammar(objects: dict) -> dict:
    groups = {}
    for group in SAFE_OBJECT_GROUPS:
        entries = objects.get(group) or []
        normalized_entries = []
        for idx, entry in enumerate(entries):
            if not isinstance(entry, dict):
                continue
            props = entry.get("properties") if isinstance(entry.get("properties"), dict) else {}
            safe_props = _safe_property_subset(props)
            if safe_props:
                normalized_entries.append(
                    {
                        "selector": entry.get("selector") or entry.get("objectName") or "general",
                        "index": idx,
                        "properties": safe_props,
                    }
                )
        if normalized_entries:
            groups[group] = normalized_entries
    return {
        "schema": "rw-zebra-native-transfer.visualObjectGrammar.v1",
        "safe_groups": sorted(groups),
        "groups": groups,
    }


def _column_intent(marker_style, show_as_table, fmt) -> str:
    if marker_style in {5, "5", "bar", "dataBar"}:
        return "data_bar"
    if marker_style in {2, 3, "2", "3", "bullet", "variance"}:
        return "bullet_or_variance_marker"
    if show_as_table in {0, "0", False}:
        return "chart_value"
    if fmt in {1, "1"}:
        return "variance_delta"
    if fmt in {2, "2"}:
        return "variance_percent"
    return "table_value"


def _column_grammar(column_settings: dict, derived_columns: list[dict]) -> dict:
    columns = []
    for order, (key, cfg) in enumerate((column_settings or {}).items()):
        if not isinstance(cfg, dict):
            continue
        table_view = cfg.get("tableView") or {}
        chart_view = cfg.get("chartView") or {}
        marker = table_view.get("markerStyle", chart_view.get("markerStyle"))
        show_as_table = table_view.get("showAsTable", chart_view.get("showAsTable"))
        fmt = cfg.get("format")
        hidden = bool(table_view.get("hidden", chart_view.get("hidden", False)))
        columns.append(
            {
                "key": key,
                "order": order,
                "markerStyle": marker,
                "showAsTable": show_as_table,
                "scaleGroup": cfg.get("scaleGroup"),
                "format": fmt,
                "hidden": hidden,
                "intent": _column_intent(marker, show_as_table, fmt),
                "support_column": hidden or str(key).startswith("_") or "support" in str(key).lower(),
            }
        )
    existing = {c["key"] for c in columns}
    for variance in derived_columns or []:
        key = variance.get("key")
        if not key or key in existing:
            continue
        fmt = variance.get("format")
        columns.append(
            {
                "key": key,
                "order": len(columns),
                "markerStyle": 5 if variance.get("role") == "delta" else None,
                "showAsTable": True,
                "scaleGroup": None,
                "format": fmt,
                "hidden": False,
                "intent": "variance_percent" if variance.get("role") == "relative" else "variance_delta",
                "scenario_pair": variance.get("scenario_pair"),
                "support_column": False,
                "synthesized_by_zebra": True,
            }
        )
    return {
        "schema": "rw-zebra-native-transfer.columnGrammar.v1",
        "columns": columns,
        "hidden_support_columns": [c["key"] for c in columns if c.get("support_column")],
        "ordered_keys": [c["key"] for c in columns],
        "intents": sorted({c["intent"] for c in columns}),
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


def _distance_band(a: dict, b: dict) -> tuple[str, float]:
    ax1, ay1 = float(a.get("x", 0)), float(a.get("y", 0))
    ax2, ay2 = ax1 + float(a.get("w", 0)), ay1 + float(a.get("h", 0))
    bx1, by1 = float(b.get("x", 0)), float(b.get("y", 0))
    bx2, by2 = bx1 + float(b.get("w", 0)), by1 + float(b.get("h", 0))
    overlap_w = max(0.0, min(ax2, bx2) - max(ax1, bx1))
    overlap_h = max(0.0, min(ay2, by2) - max(ay1, by1))
    min_area = max(1.0, min((ax2 - ax1) * (ay2 - ay1), (bx2 - bx1) * (by2 - by1)))
    if (overlap_w * overlap_h) / min_area >= 0.1:
        return "overlap", 0.0
    dx = max(bx1 - ax2, ax1 - bx2, 0.0)
    dy = max(by1 - ay2, ay1 - by2, 0.0)
    distance = (dx**2 + dy**2) ** 0.5
    if distance <= 24:
        return "adjacent", distance
    if distance <= 96:
        return "nearby", distance
    return "distant", distance


def _furniture_intent(text: str, box: dict, page_width: float, page_height: float) -> str:
    text_l = text.lower()
    if box.get("y", 0) < page_height * 0.14:
        if any(token in text_l for token in ("back", "home", "menu", "filter", "reset")):
            return "nav_button"
        return "page_header"
    if box.get("x", 0) < page_width * 0.12 and any(token in text_l for token in ("logo", "©", "copyright")):
        return "logo_or_brand"
    if any(token in text_l for token in ("click", "select", "reset", "back")):
        return "button_or_instruction"
    return "analytic_annotation"


def _furniture_relationship(box: dict, visual_box: dict, page_height: float) -> tuple[str, str, float]:
    band, distance = _distance_band(box, visual_box)
    y = float(box.get("y", 0) or 0)
    h = float(box.get("h", 0) or 0)
    if band in {"overlap", "adjacent"}:
        return "visual_furniture", band, distance
    if y < page_height * 0.14:
        return "page_furniture", band, distance
    if y + h > page_height * 0.82:
        return "page_furniture", band, distance
    if band == "nearby":
        return "visual_furniture", band, distance
    return "page_furniture", band, distance


def _static_furniture(section: dict, page_width: float, page_height: float, visual_box: dict | None = None) -> list[dict]:
    furniture: list[dict] = []
    for vc in section.get("visualContainers", []):
        cfg = _decode_config(vc)
        sv = cfg.get("singleVisual") or {}
        if sv.get("visualType") != "textbox":
            continue
        box = _bbox(vc)
        text = _textbox_text(vc)
        relationship, band, distance = _furniture_relationship(box, visual_box or box, page_height)
        furniture.append(
            {
                "visual_id": cfg.get("name", ""),
                "visual_type": "textbox",
                "text": text,
                "bounding_box": box,
                "page_zone": page_zone(box, width=page_width, height=page_height),
                "relationship": relationship,
                "proximity_band": band,
                "distance_px": round(distance, 2),
                "intent": _furniture_intent(text, box, page_width, page_height),
            }
        )
    return furniture


def _group_containers(section: dict, visual_box: dict) -> list[dict]:
    groups: list[dict] = []
    for vc in section.get("visualContainers", []):
        cfg = _decode_config(vc)
        if "singleVisualGroup" not in cfg:
            continue
        box = _bbox(vc)
        band, distance = _distance_band(box, visual_box)
        if band == "distant":
            continue
        groups.append(
            {
                "visual_id": cfg.get("name", ""),
                "bounding_box": box,
                "relationship": "group_container",
                "proximity_band": band,
                "distance_px": round(distance, 2),
            }
        )
    return groups


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
            objects = sv.get("objects") or {}
            col_settings = _column_settings(objects)
            derived_columns = zebra_derived_variance_columns(scenarios)
            safe_objects = _sanitized_objects(objects)
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
                    "derived_variance_columns": derived_columns,
                    "column_settings": col_settings,
                    "column_markers": _column_markers(col_settings),
                    "column_grammar": _column_grammar(col_settings, derived_columns),
                    "objects": safe_objects,
                    "safe_object_groups": sorted(safe_objects),
                    "visual_object_grammar": _visual_object_grammar(objects),
                    "style": _style(objects),
                    "static_furniture": _static_furniture(section, page_width, page_height, box),
                    "group_containers": _group_containers(section, box),
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
