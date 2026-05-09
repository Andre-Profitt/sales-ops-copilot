"""Per-visual dispatcher: source Zebra visualContainer config -> native PBIR visualContainer.

Both rw_zebra_kg_native_emit.emit_native_visuals (report.json path) and
rw_zebra_kg_swap_pbix.swap_layout (PBIX path) call translate_visual so per-family
logic lives in one place.

Spec: docs/superpowers/specs/2026-05-09-rw-zebra-kg-translator-design.md §4.3
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field


@dataclass(frozen=True)
class MeasureCatalog:
    """Available measures in the target dataset, keyed by canonical scenario.

    by_scenario: {"AC": "Total Closed Won ARR", "PY": "Closed Won ARR PY", ...}
    measure_to_table: {"Total Closed Won ARR": "Measures", ...}
    """

    by_scenario: dict[str, str] = field(default_factory=dict)
    measure_to_table: dict[str, str] = field(default_factory=dict)

    def has(self, scenario: str) -> bool:
        return scenario in self.by_scenario

    def resolve(self, scenario: str) -> tuple[str, str] | None:
        name = self.by_scenario.get(scenario)
        if name is None:
            return None
        table = self.measure_to_table.get(name)
        if table is None:
            return None
        return (table, name)


@dataclass(frozen=True)
class BindMap:
    """Zebra field-name -> RW field-name overlay (loaded from bindings.jsonl)."""

    zebra_to_rw: dict[str, str] = field(default_factory=dict)

    def lookup(self, zebra_ref: str) -> str | None:
        return self.zebra_to_rw.get(zebra_ref)


def _classify_family(visual_type: str) -> str:
    """Return one of: 'tables', 'cards', 'charts', 'waterfall', 'passthrough'.

    Native types (textbox/basicShape/slicer/actionButton/card) and unknown types
    fall through to passthrough — the translator never loses a visual.
    """
    if visual_type.startswith("ZebraBITables"):
        return "tables"
    if visual_type.startswith("zebraBiCards"):
        return "cards"
    if visual_type.startswith("ZebraBICharts"):
        return "charts"
    if visual_type.startswith("waterfall"):
        return "waterfall"
    return "passthrough"


def translate_visual(
    src_vc: dict,
    target_catalog: MeasureCatalog,
    rw_map: BindMap,
) -> list[dict]:
    """Translate one source visualContainer to one or more native ones.

    Identity pass-through for non-Zebra families and any parse failure;
    the translator must never lose visuals.
    """
    cstr = src_vc.get("config")
    if not isinstance(cstr, str):
        return [src_vc]
    try:
        cfg = json.loads(cstr)
    except json.JSONDecodeError:
        return [src_vc]
    sv = cfg.get("singleVisual") or {}
    vt = sv.get("visualType", "")
    family = _classify_family(vt)
    if family == "passthrough":
        return [src_vc]
    pos = {
        "x": src_vc.get("x", 0),
        "y": src_vc.get("y", 0),
        "w": src_vc.get("width", 0),
        "h": src_vc.get("height", 0),
    }
    projs = sv.get("projections") or {}
    if family == "tables":
        out = _translate_tables(projs, pos, target_catalog, rw_map)
    elif family == "cards":
        out = _translate_cards(projs, pos, target_catalog, rw_map)
    elif family == "charts":
        out = _translate_charts(projs, pos, target_catalog, rw_map)
    elif family == "waterfall":
        out = _translate_waterfall(projs, pos, target_catalog, rw_map)
    else:
        out = None
    if out:
        return out
    return [src_vc]


# ---------------------------------------------------------------------------
# Family helpers — imported lazily to avoid circular deps at module load time
# ---------------------------------------------------------------------------

from scripts.sales._pbir_helpers import (  # noqa: E402
    build_card_visual_with_objects,
    build_clustered_bar_chart_visual,
    build_table_visual,
)

_CAT_ROLES = ("Category", "Group", "Categories")
_VAL_ROLES = ("Values", "Y", "Measures", "PreviousYear", "Plan", "Forecast")


def _refs_for_roles(projs: dict, roles: tuple[str, ...]) -> list[str]:
    out: list[str] = []
    for r in roles:
        for p in projs.get(r) or []:
            qr = p.get("queryRef") if isinstance(p, dict) else None
            if isinstance(qr, str):
                out.append(qr)
    return out


def _resolve_ref(
    zebra_ref: str, rw_map: BindMap, catalog: MeasureCatalog
) -> tuple[str, str] | None:
    """Resolve a zebra_ref like 'Table.Field' to the live (table, field)."""
    rw_ref = rw_map.lookup(zebra_ref) or zebra_ref
    if "." not in rw_ref:
        return None
    tbl, fld = rw_ref.split(".", 1)
    tbl2 = catalog.measure_to_table.get(fld, tbl)
    return (tbl2, fld)


def _translate_tables(
    projs: dict, pos: dict, catalog: MeasureCatalog, rw_map: BindMap
) -> list[dict] | None:
    cat_refs = _refs_for_roles(projs, _CAT_ROLES)
    val_refs = _refs_for_roles(projs, _VAL_ROLES)
    if not cat_refs or not val_refs:
        return None
    columns: list[dict] = []
    for cref in cat_refs[:2]:
        if "." not in cref:
            continue
        ctbl, cfld = cref.split(".", 1)
        columns.append({"table": ctbl, "field": cfld, "kind": "column", "title": cfld})
    for vref in val_refs:
        resolved = _resolve_ref(vref, rw_map, catalog)
        if resolved is None:
            continue
        tbl, fld = resolved
        columns.append({"table": tbl, "field": fld, "kind": "measure", "title": fld})
    if not any(c["kind"] == "measure" for c in columns):
        return None
    return [
        build_table_visual(
            name=f"tbl_{int(pos['x'])}_{int(pos['y'])}",
            columns=columns,
            x=pos["x"],
            y=pos["y"],
            w=pos["w"],
            h=pos["h"],
        )
    ]


def _translate_cards(
    projs: dict, pos: dict, catalog: MeasureCatalog, rw_map: BindMap
) -> list[dict] | None:
    cat_refs = _refs_for_roles(projs, _CAT_ROLES)
    val_refs = _refs_for_roles(projs, _VAL_ROLES)
    if not val_refs:
        return None
    if not cat_refs and len(val_refs) == 1:
        resolved = _resolve_ref(val_refs[0], rw_map, catalog)
        if resolved is None:
            return None
        tbl, fld = resolved
        return [
            build_card_visual_with_objects(
                measure_table=tbl,
                measure_name=fld,
                display_title=fld,
                x=pos["x"],
                y=pos["y"],
                w=pos["w"],
                h=pos["h"],
            )
        ]
    columns: list[dict] = []
    for cref in cat_refs[:1]:
        if "." not in cref:
            continue
        ctbl, cfld = cref.split(".", 1)
        columns.append({"table": ctbl, "field": cfld, "kind": "column", "title": cfld})
    for vref in val_refs:
        resolved = _resolve_ref(vref, rw_map, catalog)
        if resolved is None:
            continue
        tbl, fld = resolved
        columns.append({"table": tbl, "field": fld, "kind": "measure", "title": fld})
    if not any(c["kind"] == "measure" for c in columns):
        return None
    scaffold = build_table_visual(
        name=f"mrc_{int(pos['x'])}_{int(pos['y'])}",
        columns=columns,
        x=pos["x"],
        y=pos["y"],
        w=pos["w"],
        h=pos["h"],
    )
    cfg = json.loads(scaffold["config"])
    cfg["singleVisual"]["visualType"] = "multiRowCard"
    scaffold["config"] = json.dumps(cfg, ensure_ascii=False)
    return [scaffold]


def _translate_charts(
    projs: dict, pos: dict, catalog: MeasureCatalog, rw_map: BindMap
) -> list[dict] | None:
    cat_refs = _refs_for_roles(projs, _CAT_ROLES)
    val_refs = _refs_for_roles(projs, _VAL_ROLES)
    if not cat_refs or not val_refs:
        return None
    cref = cat_refs[0]
    vref = val_refs[0]
    if "." not in cref:
        return None
    ctbl, cfld = cref.split(".", 1)
    resolved = _resolve_ref(vref, rw_map, catalog)
    if resolved is None:
        return None
    vtbl, vfld = resolved
    return [
        build_clustered_bar_chart_visual(
            name=f"chart_{int(pos['x'])}_{int(pos['y'])}",
            category_table=ctbl,
            category_column=cfld,
            category_title=cfld,
            measure_table=vtbl,
            measure_name=vfld,
            measure_title=vfld,
            x=pos["x"],
            y=pos["y"],
            w=pos["w"],
            h=pos["h"],
        )
    ]


def _translate_waterfall(
    projs: dict, pos: dict, catalog: MeasureCatalog, rw_map: BindMap
) -> list[dict] | None:
    cat_refs = _refs_for_roles(projs, _CAT_ROLES)
    val_refs = _refs_for_roles(projs, _VAL_ROLES)
    if not cat_refs or not val_refs:
        return None
    cref = cat_refs[0]
    vref = val_refs[0]
    if "." not in cref:
        return None
    ctbl, cfld = cref.split(".", 1)
    resolved = _resolve_ref(vref, rw_map, catalog)
    if resolved is None:
        return None
    vtbl, vfld = resolved
    columns = [
        {"table": ctbl, "field": cfld, "kind": "column", "title": cfld},
        {"table": vtbl, "field": vfld, "kind": "measure", "title": vfld},
    ]
    scaffold = build_table_visual(
        name=f"wf_{int(pos['x'])}_{int(pos['y'])}",
        columns=columns,
        x=pos["x"],
        y=pos["y"],
        w=pos["w"],
        h=pos["h"],
    )
    cfg = json.loads(scaffold["config"])
    sv2 = cfg["singleVisual"]
    sv2["visualType"] = "waterfallChart"
    vals = sv2["projections"].get("Values", [])
    cat_p, y_p = [], []
    for p in vals:
        qr = p.get("queryRef", "")
        if "." in qr:
            _, pf = qr.split(".", 1)
            if pf == cfld:
                cat_p.append(p)
            else:
                y_p.append(p)
    sv2["projections"] = {"Category": cat_p, "Y": y_p}
    scaffold["config"] = json.dumps(cfg, ensure_ascii=False)
    return [scaffold]
