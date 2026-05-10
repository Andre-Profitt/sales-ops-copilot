"""Shared compact slicer controls for native RW Power BI pages.

Executive tabs use context slicers only. Motion and stage are analytic axes on
specific visuals unless a page is explicitly built as an exploration surface.
This avoids page-level filters that can conflict with ARR/Renewal guardrail
measures which intentionally hard-code their motion filters.
"""

from __future__ import annotations

from scripts.sales._pbir_helpers import build_slicer_visual

FilterSpec = tuple[str, str, str]

REGION_FILTER: FilterSpec = ("d_region", "region", "Region")
CLOSE_FQ_FILTER: FilterSpec = ("d_calendar", "fiscal_quarter", "Close FQ")
END_FQ_FILTER: FilterSpec = ("d_calendar", "fiscal_quarter", "End FQ")
STAGE_FILTER: FilterSpec = ("f_opportunity", "stage_name", "Stage")
MOTION_FILTER: FilterSpec = ("f_opportunity", "motion_type", "Motion")

EXEC_CONTEXT_FILTERS: tuple[FilterSpec, ...] = (
    REGION_FILTER,
    CLOSE_FQ_FILTER,
)

PAGE_FILTERS: dict[str, tuple[FilterSpec, ...]] = {
    "VP Ops Scorecard": EXEC_CONTEXT_FILTERS,
    "What Changed": EXEC_CONTEXT_FILTERS,
    "Forecast": EXEC_CONTEXT_FILTERS,
    "Stage Hygiene": EXEC_CONTEXT_FILTERS,
    "Renewals": EXEC_CONTEXT_FILTERS,
    "Product Retention": (REGION_FILTER, END_FQ_FILTER),
    "Growth Mix": EXEC_CONTEXT_FILTERS,
    "RW KPI Explorer": EXEC_CONTEXT_FILTERS + (STAGE_FILTER,),
}

# Backward-compatible names for older scripts/tests. New code should use
# PAGE_FILTERS/filter_bar_visuals_for_page.
COMMON_FILTERS: tuple[FilterSpec, ...] = EXEC_CONTEXT_FILTERS
EXPLORER_FILTERS: tuple[FilterSpec, ...] = PAGE_FILTERS["RW KPI Explorer"]

# Motion is intentionally absent from the page-level slicer policy. Cross-motion
# analysis belongs in a labeled visual such as the Forecast Stage x Motion matrix.
MOTION_SLICER_ALLOWED_PAGES: frozenset[str] = frozenset()
FORBIDDEN_MOTION_SLICER_REF = f"{MOTION_FILTER[0]}.{MOTION_FILTER[1]}"

FILTER_REFS_BY_PAGE: dict[str, frozenset[str]] = {
    page: frozenset(f"{table}.{column}" for table, column, _title in filters)
    for page, filters in PAGE_FILTERS.items()
}

FILTER_TITLES_BY_REF: dict[str, str] = {
    f"{table}.{column}": title
    for filters in PAGE_FILTERS.values()
    for table, column, title in filters
}

FILTER_RATIONALE_BY_PAGE: dict[str, str] = {
    "VP Ops Scorecard": "Region and close-quarter context only; ARR and Renewal ACV measures stay separated.",
    "What Changed": "Region and close-quarter context keep the 7-day movement window readable without a conflicting Motion slicer.",
    "Forecast": "Region and close-quarter context; motion comparison is handled by the labeled Stage x Motion matrix.",
    "Stage Hygiene": "Region and close-quarter context define the selected opportunity cohort; transition-window measures remain explicit.",
    "Renewals": "Region and close-quarter context only; Renewal ACV measures enforce Renewal motion.",
    "Product Retention": "Region and asset end-quarter context for active-base ARR; churn snapshots remain explicit when added.",
    "Growth Mix": "Region and close-quarter context only; Land + Expand mix is shown through separate ARR measures.",
    "RW KPI Explorer": "Region, close quarter, and current stage for interactive slicing; motion appears as visual columns, not a page slicer.",
}

SEMANTIC_FILTER_GAPS: tuple[dict[str, str], ...] = (
    {
        "id": "transition_date_role",
        "severity": "medium",
        "area": "date roles",
        "finding": (
            "Stage and forecast transition facts carry transition_at, but d_calendar is only "
            "related to f_opportunity close_date/created_date today."
        ),
        "impact": (
            "A close-quarter slicer selects the opportunity cohort, not the exact transition "
            "period. That is acceptable when labeled Close FQ, but not good enough for a "
            "future transition-period executive toggle."
        ),
        "next_action": (
            "Add role-specific transition-date semantics before introducing Stage Move FQ or "
            "Forecast Move FQ slicers."
        ),
    },
    {
        "id": "stage_dimension",
        "severity": "medium",
        "area": "stage order",
        "finding": (
            "f_stage_transition has numeric stage fields, but f_opportunity currently exposes "
            "stage_name without a semantic d_stage dimension."
        ),
        "impact": (
            "Opportunity-stage visuals can only use label sorting until the model grows a "
            "canonical stage order that places 1-6, Opt-out, Won in the business sequence."
        ),
        "next_action": "Add d_stage and join opportunity/stage-transition facts through canonical stage keys.",
    },
)


def filter_policy_for_page(page: str) -> tuple[FilterSpec, ...]:
    return PAGE_FILTERS.get(page, EXEC_CONTEXT_FILTERS)


def filter_bar_visuals(
    *,
    filters: tuple[FilterSpec, ...] = COMMON_FILTERS,
    x: float = 790,
    y: float = 10,
    w: float = 142,
    h: float = 48,
    gap: float = 10,
) -> list[dict]:
    """Build a compact top-right slicer strip."""
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


def filter_bar_visuals_for_page(page: str) -> list[dict]:
    return filter_bar_visuals(filters=filter_policy_for_page(page), x=790, w=142)


def append_filter_bar(section: dict, *, page: str | None = None, explorer: bool = False) -> None:
    page_name = page or section.get("displayName") or ""
    filters = EXPLORER_FILTERS if explorer else filter_policy_for_page(page_name)
    section.setdefault("visualContainers", []).extend(filter_bar_visuals(filters=filters, x=790, w=142))
