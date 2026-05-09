"""Per-visual dispatcher: source Zebra visualContainer config -> native PBIR visualContainer.

Both rw_zebra_kg_native_emit.emit_native_visuals (report.json path) and
rw_zebra_kg_swap_pbix.swap_layout (PBIX path) call translate_visual so per-family
logic lives in one place.

Spec: docs/superpowers/specs/2026-05-09-rw-zebra-kg-translator-design.md §4.3
"""

from __future__ import annotations
