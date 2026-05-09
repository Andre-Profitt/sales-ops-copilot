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
    # Non-passthrough families implemented in Task 8.
    return [src_vc]
