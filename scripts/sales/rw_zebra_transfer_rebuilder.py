"""Native Power BI report rebuilder driven by Zebra visual DNA artifacts.

This is the transfer layer's native emitter.  It does not blindly swap visual
kinds; it consumes the extracted Zebra design grammar and emits reusable native
patterns: composite KPI tiles, IBCS tableEx/matrix tables, native charts,
waterfall/bridge visuals, and normalized static furniture.
"""

from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
from typing import Any

from scripts.sales._pbir_helpers import (
    build_clustered_bar_chart_visual,
    build_table_style_objects,
    build_table_visual,
    build_textbox_visual,
)
from scripts.sales.rw_zebra_kg_ibcs_synth import build_composite_kpi_tile, build_databar_cf_objects
from scripts.sales.rw_zebra_kg_translator import MeasureCatalog
from scripts.sales.rw_zebra_transfer_dna import DEFAULT_SOURCE_DIR, TRANSFER_DIR, load_report_from_pbix

REPO_ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = REPO_ROOT / "data/zebra_kg/transfer"
QA_OUT_DIR = REPO_ROOT / "output/rw_zebra_transfer"
SCENARIO_ROLE_ORDER = (("Values", "AC"), ("Y", "AC"), ("Measures", "AC"), ("PreviousYear", "PY"), ("Plan", "PL"), ("Forecast", "FC"))
NATIVE_CUSTOM_PREFIXES = ("ZebraBI", "zebraBi", "waterfall0221")
DEFAULT_NATIVE_VISUAL_TYPES = {
    "actionButton",
    "areaChart",
    "basicShape",
    "card",
    "clusteredBarChart",
    "clusteredColumnChart",
    "columnChart",
    "image",
    "lineChart",
    "matrix",
    "multiRowCard",
    "singleVisualGroup",
    "slicer",
    "tableEx",
    "textbox",
    "waterfallChart",
}


class TransferGateError(RuntimeError):
    """Raised when the Zebra transfer gate is configured to fail hard."""


def _split_ref(ref: str) -> tuple[str, str] | None:
    if "." not in ref:
        return None
    table, field = ref.split(".", 1)
    return table, field


def _scenario_refs(dna: dict[str, Any]) -> dict[str, str]:
    projections = dna.get("projection_roles") or {}
    out: dict[str, str] = {}
    for role, scenario in SCENARIO_ROLE_ORDER:
        refs = projections.get(role) or []
        if refs and scenario not in out:
            out[scenario] = refs[0]
    return out


def _resolve_ref(ref: str, catalog: MeasureCatalog) -> tuple[str, str] | None:
    split = _split_ref(ref)
    if split is None:
        return None
    table, field = split
    if catalog.measure_to_table and field in catalog.measure_to_table:
        return catalog.measure_to_table[field], field
    return table, field


def _resolve_scenario(scenario: str, refs_by_scenario: dict[str, str], catalog: MeasureCatalog) -> tuple[str, str] | None:
    resolved = catalog.resolve(scenario)
    if resolved:
        return resolved
    if scenario in refs_by_scenario:
        return _resolve_ref(refs_by_scenario[scenario], catalog)
    return None


def _native_objects_from_dna(dna: dict[str, Any]) -> dict[str, Any]:
    objects: dict[str, Any] = {
        "grid": {"general": [{"properties": {"outlineWeight": 0}}]},
        "stylePreset": {"source": "zebra-transfer", "intent": dna.get("visual_intent")},
    }
    title = (dna.get("style") or {}).get("title") or {}
    if title:
        objects["title"] = [{"properties": {k: v for k, v in title.items() if k in {"text", "fontSize", "fontFamily", "fontColor", "alignment"}}}]
    grammar = dna.get("visual_object_grammar") or {}
    if grammar:
        objects["zebraGrammar"] = {"schema": grammar.get("schema"), "safe_groups": grammar.get("safe_groups", [])}
    return objects


def _furniture_to_visual(f: dict[str, Any]) -> dict[str, Any] | None:
    bbox = f.get("bounding_box") or {}
    text = f.get("text") or ""
    if f.get("visual_type") == "textbox" and text and f.get("relationship") != "visual_furniture":
        return build_textbox_visual(text=text, x=bbox.get("x", 0), y=bbox.get("y", 0), w=bbox.get("w", 200), h=bbox.get("h", 30), font_size_pt=12, color="#252423")
    return None


def _dedupe_static_furniture(visuals: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, int, int, int, int]] = set()
    out: list[dict[str, Any]] = []
    for visual in visuals:
        bbox = visual.get("bounding_box") or {}
        key = (visual.get("text", ""), int(bbox.get("x", 0)), int(bbox.get("y", 0)), int(bbox.get("w", 0)), int(bbox.get("h", 0)))
        if key in seen:
            continue
        seen.add(key)
        out.append(visual)
    return out


def _category_columns(dna: dict[str, Any]) -> list[dict[str, Any]]:
    cols: list[dict[str, Any]] = []
    for role in ("Category", "Group"):
        for ref in (dna.get("projection_roles") or {}).get(role) or []:
            split = _split_ref(ref)
            if split:
                table, field = split
                cols.append({"table": table, "field": field, "kind": "column", "title": field})
    return cols[:2]


def _zebra_column_key_to_scenario(key: str) -> str | None:
    normalized = key.replace("_", "-").lower()
    return {
        "actual": "AC",
        "ac": "AC",
        "previousyear": "PY",
        "previous-year": "PY",
        "py": "PY",
        "plan": "PL",
        "pl": "PL",
        "forecast": "FC",
        "fc": "FC",
    }.get(normalized)


def _table_columns_from_dna(dna: dict[str, Any], catalog: MeasureCatalog) -> list[dict[str, Any]]:
    columns = _category_columns(dna)
    refs_by_scenario = _scenario_refs(dna)
    projected = set(dna.get("scenario_pairing") or refs_by_scenario)
    emitted: set[tuple[str, str, str]] = set()

    def append_measure(scenario_or_label: str, title: str | None = None) -> None:
        resolved = _resolve_scenario(scenario_or_label, refs_by_scenario, catalog) or catalog.resolve(scenario_or_label)
        if not resolved:
            return
        key = (resolved[0], resolved[1], title or scenario_or_label)
        if key in emitted:
            return
        emitted.add(key)
        columns.append({"table": resolved[0], "field": resolved[1], "kind": "measure", "title": title or scenario_or_label})

    grammar_columns = (dna.get("column_grammar") or {}).get("columns") or []
    if grammar_columns:
        derived_by_key = {v.get("key"): v for v in dna.get("derived_variance_columns") or []}
        for spec in sorted(grammar_columns, key=lambda item: item.get("order", 0)):
            if spec.get("hidden") or spec.get("support_column"):
                continue
            key = str(spec.get("key") or "")
            scenario = _zebra_column_key_to_scenario(key)
            if scenario and scenario in projected:
                append_measure(scenario)
                continue
            derived = derived_by_key.get(key)
            if derived and derived.get("label"):
                append_measure(str(derived["label"]))
        if any(c.get("kind") == "measure" for c in columns):
            return columns

    for scenario in ("AC", "PY", "PL", "FC"):
        if scenario in projected:
            append_measure(scenario)
    for variance in dna.get("derived_variance_columns") or []:
        label = variance.get("label")
        if label:
            append_measure(label)
    return columns


def _table_objects_from_dna(dna: dict[str, Any], columns: list[dict[str, Any]]) -> dict[str, Any]:
    objects = build_table_style_objects(header_fill="#FFFFFF", header_text="#1A1D31", row_text="#252423", grid="#D8DEE8", font_size=9)
    objects["stylePreset"] = {"source": "zebra-transfer", "intent": dna.get("visual_intent")}
    databar_values: list[dict[str, Any]] = []
    first_measure = next((c for c in columns if c.get("kind") == "measure"), None)
    max_ref = f"{first_measure['table']}.{first_measure['field']}" if first_measure else None
    grammar_intents = set((dna.get("column_grammar") or {}).get("intents") or [])
    wants_databar = "data_bar" in grammar_intents or any(
        (cfg.get("tableView") or {}).get("markerStyle") == 5
        for cfg in (dna.get("column_settings") or {}).values()
        if isinstance(cfg, dict)
    ) or any(
        marker.get("markerStyle") == 5
        for marker in (dna.get("column_markers") or {}).values()
        if isinstance(marker, dict)
    )
    if wants_databar and max_ref:
        for c in columns:
            if c.get("kind") != "measure":
                continue
            cf = build_databar_cf_objects(c["field"], max_ref, "#252423")
            databar_values.extend(cf.get("values") or [])
    if databar_values:
        objects["dataBars"] = {"values": databar_values}
    return objects


def rebuild_visual_from_dna(dna: dict[str, Any], catalog: MeasureCatalog) -> list[dict[str, Any]]:
    bbox = dna.get("bounding_box") or {}
    x, y, w, h = bbox.get("x", 0), bbox.get("y", 0), bbox.get("w", 280), bbox.get("h", 120)
    family = dna.get("visual_family")
    refs_by_scenario = _scenario_refs(dna)
    if family == "Cards":
        value = _resolve_scenario("AC", refs_by_scenario, catalog)
        if not value:
            value_ref = next(iter((dna.get("projection_roles") or {}).get("Values") or []), "")
            value = _resolve_ref(value_ref, catalog)
        variance = None
        for scenario in ("PY", "PL", "FC"):
            variance = _resolve_scenario(scenario, refs_by_scenario, catalog)
            if variance:
                break
        if value:
            label = "KPI"
            for role in ("Group", "Category"):
                refs = (dna.get("projection_roles") or {}).get(role) or []
                if refs:
                    label = refs[0].split(".", 1)[-1]
                    break
            return build_composite_kpi_tile(label, value[0], value[1], variance[0] if variance else None, variance[1] if variance else None, x, y, w, h)
    if family == "Tables":
        columns = _table_columns_from_dna(dna, catalog)
        if any(c.get("kind") == "measure" for c in columns):
            return [build_table_visual(name=f"zbr_tbl_{int(x)}_{int(y)}", columns=columns, x=x, y=y, w=w, h=h, objects=_table_objects_from_dna(dna, columns))]
    if family == "Charts":
        cats = _category_columns(dna)
        scenario = _resolve_scenario("AC", refs_by_scenario, catalog) or _resolve_scenario("PL", refs_by_scenario, catalog) or _resolve_scenario("FC", refs_by_scenario, catalog)
        if cats and scenario:
            return [build_clustered_bar_chart_visual(cats[0]["table"], cats[0]["field"], cats[0]["title"], scenario[0], scenario[1], scenario[1], x, y, w, h)]
    if family == "Waterfall":
        cats = _category_columns(dna)
        scenario = _resolve_scenario("AC", refs_by_scenario, catalog)
        if cats and scenario:
            vc = build_table_visual(name=f"zbr_wf_{int(x)}_{int(y)}", columns=[cats[0], {"table": scenario[0], "field": scenario[1], "kind": "measure", "title": scenario[1]}], x=x, y=y, w=w, h=h, objects=_native_objects_from_dna(dna))
            cfg = json.loads(vc["config"])
            sv = cfg["singleVisual"]
            sv["visualType"] = "waterfallChart"
            vals = sv.get("projections", {}).get("Values", [])
            sv["projections"] = {"Category": vals[:1], "Y": vals[1:]}
            vc["config"] = json.dumps(cfg, ensure_ascii=False)
            return [vc]
    return []


def _strip_custom_resources(report: dict[str, Any]) -> None:
    report["resourcePackages"] = [p for p in report.get("resourcePackages") or [] if (p.get("resourcePackage") or {}).get("type") != 0]
    report["publicCustomVisuals"] = []


def _is_custom_leftover(vc: dict[str, Any]) -> bool:
    cfg = vc.get("config")
    if not isinstance(cfg, str):
        return False
    try:
        vt = (json.loads(cfg).get("singleVisual") or {}).get("visualType", "")
    except json.JSONDecodeError:
        return False
    return vt.startswith(NATIVE_CUSTOM_PREFIXES) and vt != "waterfallChart"


def _blank_visual_to_shape(vc: dict[str, Any]) -> dict[str, Any]:
    normalized = copy.deepcopy(vc)
    cfg = _decode_visual_config(normalized)
    cfg.setdefault("name", f"zbr_shape_{int(normalized.get('x', 0) or 0)}_{int(normalized.get('y', 0) or 0)}")
    cfg["singleVisual"] = {
        "visualType": "basicShape",
        "objects": {
            "shape": [{"properties": {"shapeType": "rectangle"}}],
            "fill": [{"properties": {"show": True, "fillColor": {"solid": {"color": "#FFFFFF"}}, "transparency": 100}}],
            "line": [{"properties": {"show": False}}],
        },
    }
    normalized["config"] = json.dumps(cfg, ensure_ascii=False)
    return normalized


def rebuild_native_report_from_dna(dna: dict[str, Any], source_report: dict[str, Any], catalog: MeasureCatalog) -> dict[str, Any]:
    report = copy.deepcopy(source_report)
    _strip_custom_resources(report)
    by_page: dict[str, list[dict[str, Any]]] = {}
    for visual in dna.get("visuals") or []:
        by_page.setdefault(visual.get("page_name", ""), []).append(visual)
    for page in report.get("sections") or []:
        page_name = page.get("name", "")
        new_vcs: list[dict[str, Any]] = []
        furniture: list[dict[str, Any]] = []
        for visual in by_page.get(page_name, []):
            furniture.extend(visual.get("static_furniture") or [])
            new_vcs.extend(rebuild_visual_from_dna(visual, catalog))
        for item in _dedupe_static_furniture(furniture):
            vc = _furniture_to_visual(item)
            if vc:
                new_vcs.insert(0, vc)
        # Preserve native, non-Zebra visuals from the source page, excluding static
        # furniture that was normalized from the DNA to avoid duplicates.
        for vc in page.get("visualContainers") or []:
            if _is_custom_leftover(vc):
                continue
            vt = ""
            try:
                vt = (json.loads(vc.get("config", "{}") or "{}").get("singleVisual") or {}).get("visualType", "")
            except json.JSONDecodeError:
                pass
            if not vt:
                new_vcs.append(_blank_visual_to_shape(vc))
                continue
            if vt in {"textbox", "basicShape", "shape"}:
                continue
            new_vcs.append(vc)
        page["visualContainers"] = new_vcs
    return report


def _iter_visual_containers(report: dict[str, Any]):
    for page in report.get("sections") or []:
        for vc in page.get("visualContainers") or []:
            yield page, vc


def _decode_visual_config(vc: dict[str, Any]) -> dict[str, Any]:
    raw = vc.get("config", {})
    if isinstance(raw, str):
        try:
            return json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            return {}
    return raw or {}


def _visual_type(vc: dict[str, Any]) -> str:
    config = _decode_visual_config(vc)
    if config.get("singleVisualGroup") is not None:
        return "singleVisualGroup"
    return str((config.get("singleVisual") or {}).get("visualType") or "")


def _measure_refs_in_visual(vc: dict[str, Any]) -> list[tuple[str, str]]:
    sv = _decode_visual_config(vc).get("singleVisual") or {}
    query = sv.get("prototypeQuery") or {}
    aliases = {
        entry.get("Name"): entry.get("Entity")
        for entry in query.get("From") or []
        if isinstance(entry, dict) and entry.get("Name") and entry.get("Entity")
    }
    refs: list[tuple[str, str]] = []
    for selected in query.get("Select") or []:
        measure = selected.get("Measure") if isinstance(selected, dict) else None
        if not isinstance(measure, dict):
            continue
        alias = ((measure.get("Expression") or {}).get("SourceRef") or {}).get("Source")
        field = measure.get("Property")
        if alias and field:
            refs.append((aliases.get(alias, "?"), field))
    return refs


def _unresolved_measure_refs(report: dict[str, Any], catalog: MeasureCatalog | None) -> list[str]:
    if catalog is None:
        return []
    allowed = {(table, measure) for measure, table in catalog.measure_to_table.items()}
    details: list[str] = []
    for page, vc in _iter_visual_containers(report):
        page_name = page.get("displayName") or page.get("name") or "?"
        for table, measure in _measure_refs_in_visual(vc):
            if (table, measure) not in allowed:
                details.append(f"[{page_name}] {table}.{measure!r}")
    return details


def _lost_zebra_visuals(dna: dict[str, Any] | None, catalog: MeasureCatalog | None) -> int:
    if dna is None or catalog is None:
        return 0
    lost = 0
    for visual in dna.get("visuals") or []:
        if not rebuild_visual_from_dna(visual, catalog):
            lost += 1
    return lost


def transfer_gate(
    source_report: dict[str, Any],
    rebuilt_report: dict[str, Any],
    *,
    dna: dict[str, Any] | None = None,
    catalog: MeasureCatalog | None = None,
    known_native_visual_types: set[str] | None = None,
) -> dict[str, Any]:
    def visual_count(report: dict[str, Any]) -> int:
        return sum(len(p.get("visualContainers") or []) for p in report.get("sections") or [])

    known_types = known_native_visual_types or DEFAULT_NATIVE_VISUAL_TYPES
    leftovers = sum(1 for _, vc in _iter_visual_containers(rebuilt_report) if _is_custom_leftover(vc))
    custom_packages = sum(
        1
        for package in rebuilt_report.get("resourcePackages") or []
        if (package.get("resourcePackage") or {}).get("type") == 0
    )
    fallback_textboxes = 0
    blank_visual_types = 0
    unknown_visual_types = 0
    for _, vc in _iter_visual_containers(rebuilt_report):
        cfg = _decode_visual_config(vc)
        sv = cfg.get("singleVisual") or {}
        visual_type = str(sv.get("visualType") or "")
        if not visual_type:
            blank_visual_types += 1
        elif visual_type not in known_types and not _is_custom_leftover(vc):
            unknown_visual_types += 1
        if visual_type == "textbox" and "fallback" in json.dumps(sv).lower():
            fallback_textboxes += 1
    unresolved_details = _unresolved_measure_refs(rebuilt_report, catalog)
    lost_visuals = _lost_zebra_visuals(dna, catalog)
    gate = {
        "source_pages": len(source_report.get("sections") or []),
        "rebuilt_pages": len(rebuilt_report.get("sections") or []),
        "source_visuals": visual_count(source_report),
        "rebuilt_visuals": visual_count(rebuilt_report),
        "visual_count_delta": visual_count(rebuilt_report) - visual_count(source_report),
        "custom_visual_leftovers": leftovers,
        "custom_resource_packages": custom_packages,
        "fallback_textboxes": fallback_textboxes,
        "lost_zebra_visuals": lost_visuals,
        "blank_visual_types": blank_visual_types,
        "unknown_visual_types": unknown_visual_types,
        "unresolved_measure_refs": len(unresolved_details),
        "unresolved_measure_ref_details": unresolved_details,
    }
    failures = []
    if gate["source_pages"] != gate["rebuilt_pages"]:
        failures.append(f"page_count={gate['source_pages']}->{gate['rebuilt_pages']}")
    for key in (
        "custom_visual_leftovers",
        "custom_resource_packages",
        "fallback_textboxes",
        "lost_zebra_visuals",
        "blank_visual_types",
        "unknown_visual_types",
        "unresolved_measure_refs",
    ):
        if gate[key]:
            failures.append(f"{key}={gate[key]}")
    gate["failures"] = failures
    gate["passed"] = not failures
    return gate


def write_transfer_qa_artifacts(
    gate: dict[str, Any],
    out_dir: Path,
    template_slug: str,
    *,
    fail_on_error: bool = False,
) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / f"transfer_gate_{template_slug}.json"
    md_path = out_dir / f"transfer_gate_{template_slug}.md"
    json_path.write_text(json.dumps(gate, indent=2, ensure_ascii=False) + "\n")
    lines = [f"# Zebra transfer gate: {template_slug}", "", f"Passed: {gate.get('passed')}", ""]
    if gate.get("failures"):
        lines.append("## Failures")
        lines.extend(f"- {failure}" for failure in gate["failures"])
        lines.append("")
    lines.append("## Metrics")
    for key, value in gate.items():
        if key in {"failures", "unresolved_measure_ref_details"}:
            continue
        lines.append(f"- {key}: {value}")
    if gate.get("unresolved_measure_ref_details"):
        lines.append("")
        lines.append("## Unresolved measure references")
        lines.extend(f"- {detail}" for detail in gate["unresolved_measure_ref_details"])
    md_path.write_text("\n".join(lines) + "\n")
    if fail_on_error and not gate.get("passed"):
        raise TransferGateError(f"Zebra transfer gate failed: {', '.join(gate.get('failures') or [])}")
    return json_path, md_path


def load_catalog_from_schema(template_slug: str) -> MeasureCatalog:
    measures_csv = REPO_ROOT / f"data/zebra_kg/schemas/{template_slug}/measures.csv"
    by_scenario = {"AC": "AC", "PY": "PY", "PL": "PL", "FC": "FC"}
    measure_to_table: dict[str, str] = {}
    if measures_csv.exists():
        import csv
        with measures_csv.open(newline="") as handle:
            for row in csv.DictReader(handle):
                name = row.get("name") or row.get("Name") or row.get("measure") or row.get("Measure")
                table = row.get("table") or row.get("Table") or row.get("table_name") or "Data"
                if name:
                    measure_to_table[name] = table
                    if name in by_scenario.values():
                        by_scenario[{v: k for k, v in by_scenario.items()}[name]] = name
    for name in list(by_scenario.values()):
        measure_to_table.setdefault(name, "Data")
    for label in ("AC-PY", "AC-PY %", "AC-PL", "AC-PL %", "AC-FC", "AC-FC %", "FC-PL", "FC-PL %"):
        measure_to_table.setdefault(label, "Data")
        by_scenario.setdefault(label, label)
    return MeasureCatalog(by_scenario=by_scenario, measure_to_table=measure_to_table)


def main() -> None:
    parser = argparse.ArgumentParser(description="Rebuild native Power BI report JSON from Zebra visual DNA.")
    parser.add_argument("--template", default="sales-funnel-power-bi-template")
    parser.add_argument("--source-dir", type=Path, default=DEFAULT_SOURCE_DIR)
    parser.add_argument("--dna", type=Path)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--qa-out-dir", type=Path, default=QA_OUT_DIR)
    parser.add_argument("--no-fail-on-gate", action="store_true")
    args = parser.parse_args()
    dna_path = args.dna or (TRANSFER_DIR / f"visual_dna_{args.template}.json")
    out_path = args.out or (OUT_DIR / f"native_rebuild_{args.template}.report.json")
    source_report = load_report_from_pbix(args.source_dir.expanduser() / f"{args.template}.pbix")
    dna = json.loads(dna_path.read_text())
    catalog = load_catalog_from_schema(args.template)
    report = rebuild_native_report_from_dna(dna, source_report, catalog)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    gate = transfer_gate(source_report, report, dna=dna, catalog=catalog)
    gate_json, gate_md = write_transfer_qa_artifacts(
        gate,
        args.qa_out_dir,
        args.template,
        fail_on_error=not args.no_fail_on_gate,
    )
    print(
        json.dumps(
            {
                "template_slug": args.template,
                "out": str(out_path),
                "transfer_gate_json": str(gate_json),
                "transfer_gate_markdown": str(gate_md),
                "gate": gate,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
