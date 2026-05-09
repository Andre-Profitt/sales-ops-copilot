"""IBCS column synthesis, DAX synthesis, conditional formatting + composite tile builders.

Encodes the rules documented in:
- docs/sales/RW_ZEBRA_BI_INFRASTRUCTURE_ATLAS.md §3 (column synthesis grammar)
- docs/sales/RW_ZEBRA_BI_INFRASTRUCTURE_ATLAS.md §6 (Cards rendering grammar)
- docs/sales/RW_POWER_BI_NATIVE_INFRASTRUCTURE_ATLAS.md §2 (CF reference)

This module is pure (no I/O, no network); consumed by rw_zebra_kg_translator.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ColumnSpec:
    """One synthesized IBCS column.

    role: 'absolute' (raw scenario column), 'delta' (X - Y), or 'relative' (X-Y / |Y|).
    base: scenario tuple. ('AC',) for absolute, ('AC','PY') for delta/relative.
    format_code: 0=integer, 1=signed, 2=percent, 3=signed-decimal.
    is_cost: invert sign so positive = good (AC < PY for costs).
    """

    name: str
    role: str
    base: tuple[str, ...]
    format_code: int
    is_cost: bool = False
