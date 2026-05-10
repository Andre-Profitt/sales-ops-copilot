"""Shared compact slicer controls for native RW Power BI pages."""

from __future__ import annotations

from scripts.sales._pbir_helpers import build_slicer_visual


COMMON_FILTERS: tuple[tuple[str, str, str], ...] = (
    ("d_region", "region", "Region"),
    ("d_calendar", "fiscal_quarter", "Fiscal qtr"),
    ("f_opportunity", "motion_type", "Motion"),
)

EXPLORER_FILTERS: tuple[tuple[str, str, str], ...] = COMMON_FILTERS + (
    ("f_opportunity", "stage_name", "Stage"),
)


def filter_bar_visuals(
    *,
    filters: tuple[tuple[str, str, str], ...] = COMMON_FILTERS,
    x: float = 790,
    y: float = 10,
    w: float = 142,
    h: float = 48,
    gap: float = 10,
) -> list[dict]:
    """Build a compact top-right slicer strip.

    The controls are intentionally small and neutral so they add slice/dice
    utility without turning every page into a filter-heavy worksheet.
    """
    return [
        build_slicer_visual(
            table,
            column,
            title,
            x=x + i * (w + gap),
            y=y,
            w=w,
            h=h,
            font_size=8,
        )
        for i, (table, column, title) in enumerate(filters)
    ]


def append_filter_bar(section: dict, *, explorer: bool = False) -> None:
    section.setdefault("visualContainers", []).extend(
        filter_bar_visuals(
            filters=EXPLORER_FILTERS if explorer else COMMON_FILTERS,
            x=638 if explorer else 790,
            w=142,
        )
    )
