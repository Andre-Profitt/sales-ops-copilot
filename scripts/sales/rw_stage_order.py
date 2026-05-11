"""Canonical SimCorp sales-stage ordering for RW reporting."""

from __future__ import annotations

import re
from typing import Any

STAGE_ORDER: tuple[tuple[int, str, str], ...] = (
    (1, "1 - Prospecting", "Prospecting"),
    (2, "2 - Discovery", "Discovery"),
    (3, "3 - Engagement", "Engagement"),
    (4, "4 - Shortlisted", "Shortlisted"),
    (5, "5 - Preferred", "Preferred"),
    (6, "6 - Contracting", "Contracting"),
    (7, "0 - Opt-out", "Opt-out"),
    (8, "7 - Won", "Won"),
    (99, "Unknown", "Unknown"),
)
_STAGE_DISPLAY_BY_ORDER = {order: name for order, name, _short_name in STAGE_ORDER}

_STAGE_RE = re.compile(r"^\s*(\d+)\s*[-–—.]\s*(.+?)\s*$")


def stage_dimension_rows() -> list[dict[str, Any]]:
    """Return the reusable d_stage rows in handbook business order."""
    return [
        {
            "stage_order": order,
            "stage_name": name,
            "stage_short_name": short_name,
            "is_terminal": order in {7, 8},
        }
        for order, name, short_name in STAGE_ORDER
    ]


def stage_display_for_order(order: object) -> str:
    """Return the canonical report label for a parsed stage order."""
    try:
        key = int(order)
    except (TypeError, ValueError):
        return "Unknown"
    return _STAGE_DISPLAY_BY_ORDER.get(key, "Unknown")


def stage_display_for_label(value: object) -> str:
    """Normalize raw Salesforce stage text into canonical handbook labels."""
    return stage_display_for_order(stage_order_for_label(value))


def parse_stage_label(value: object) -> tuple[int | None, str | None]:
    """Parse a Salesforce stage label into its numeric prefix and clean name."""
    if value is None:
        return None, None
    text = str(value).strip()
    if not text or text.lower() in {"nan", "none", "null"}:
        return None, None
    match = _STAGE_RE.match(text)
    if not match:
        return None, text
    return int(match.group(1)), match.group(2).strip()


def stage_order_for_label(value: object) -> int:
    """Return handbook display order: 1-6, Opt-out, Won, then unknown."""
    raw_num, raw_name = parse_stage_label(value)
    normalized = (raw_name or str(value or "")).lower()

    if "prospect" in normalized:
        return 1
    if "discover" in normalized:
        return 2
    if "engagement" in normalized:
        return 3
    if "shortlist" in normalized:
        return 4
    if "prefer" in normalized:
        return 5
    if "contract" in normalized:
        return 6
    if "opt" in normalized or "lost" in normalized:
        return 7
    if "won" in normalized or "sales ops qc" in normalized:
        return 8

    if raw_num is None:
        return 99
    if 1 <= raw_num <= 6:
        return raw_num
    if raw_num == 0:
        return 7
    if raw_num >= 7:
        return 8
    return 99
