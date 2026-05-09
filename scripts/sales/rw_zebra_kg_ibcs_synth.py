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


from scripts.sales.rw_zebra_kg_translator import MeasureCatalog  # noqa: E402

_FORMAT_STRINGS = {
    0: "#,##0",
    1: "+#,##0;-#,##0",
    2: "+0.0%;-0.0%",
    3: "+#,##0.0;-#,##0.0",
}


def format_string_for(format_code: int) -> str:
    """Map Zebra format-code enum to a Power BI format-string.

    Per Zebra atlas §4 encoding reference. Unknown codes fall back to integer.
    """
    return _FORMAT_STRINGS.get(format_code, "#,##0")


def synthesize_dax(spec: ColumnSpec, catalog: MeasureCatalog) -> str | None:
    """Generate the DAX expression for a synthesized IBCS column.

    Returns None if any base scenario isn't in the catalog.
    """
    resolved = [catalog.resolve(s) for s in spec.base]
    if any(r is None for r in resolved):
        return None
    names = [r[1] for r in resolved]
    if spec.role == "absolute":
        return f"[{names[0]}]"
    if spec.role == "delta":
        body = f"[{names[0]}] - [{names[1]}]"
        return f"({body}) * -1" if spec.is_cost else body
    if spec.role == "relative":
        body = f"DIVIDE([{names[0]}] - [{names[1]}], ABS([{names[1]}]))"
        return f"({body}) * -1" if spec.is_cost else body
    return None


_KNOWN_SCENARIOS = ("AC", "PY", "PL", "FC")
_NON_AC_ORDER = ("PY", "PL", "FC")


def synthesize_ibcs_columns(
    scenarios: set[str],
    is_cost: bool = False,
) -> list[ColumnSpec]:
    """Generate the canonical IBCS column set for a scenario combination.

    Encodes Zebra atlas §3 column synthesis rule: pair (AC, Y) projections
    auto-derive `<AC>-<Y>` (delta, format_code=1) and `<AC>-<Y> %` (relative,
    format_code=2). Variance pairs only emit when AC is present.

    Order: all known absolutes (AC, PY, PL, FC) in canonical order, then each
    (AC, Y) pair's delta + relative for Y in (PY, PL, FC).

    Unknown scenarios are silently dropped.
    """
    present = [s for s in _KNOWN_SCENARIOS if s in scenarios]
    out: list[ColumnSpec] = [
        ColumnSpec(name=s, role="absolute", base=(s,), format_code=0, is_cost=is_cost)
        for s in present
    ]
    if "AC" not in present:
        return out
    for y in _NON_AC_ORDER:
        if y in present:
            out.append(
                ColumnSpec(
                    name=f"AC-{y}",
                    role="delta",
                    base=("AC", y),
                    format_code=1,
                    is_cost=is_cost,
                )
            )
            out.append(
                ColumnSpec(
                    name=f"AC-{y} %",
                    role="relative",
                    base=("AC", y),
                    format_code=2,
                    is_cost=is_cost,
                )
            )
    return out
