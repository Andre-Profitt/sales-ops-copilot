"""Period-context facade for the Sales Director factory.

This module intentionally delegates to ``scripts.period_context`` so period
definitions stay in one place while the factory package gets a stable import
surface.
"""

from __future__ import annotations

from scripts.period_context import (
    DEFAULT_PERIOD,
    PeriodContext,
    context_for_period,
    default_snapshot_date,
    period_anchor,
    quarter_bounds,
    quarter_end_inclusive,
)

__all__ = [
    "DEFAULT_PERIOD",
    "PeriodContext",
    "context_for_period",
    "default_snapshot_date",
    "period_anchor",
    "quarter_bounds",
    "quarter_end_inclusive",
]

