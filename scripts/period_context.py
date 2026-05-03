#!/usr/bin/env python3
"""Shared period labels for the Sales Director monthly deck factory.

This is deliberately conservative. The May 2026/Q2 lane is the only fully
validated production lane today; unsupported periods should fail loudly instead
of silently producing stale meeting artifacts.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path


DEFAULT_PERIOD = "2026-Q2"


@dataclass(frozen=True)
class PeriodContext:
    period: str
    month_label: str
    quarter_folder: str
    snapshot_date: str
    kickoff_date: str
    kickoff_date_long: str
    review_package_dir: Path
    required_deck_text: tuple[str, ...]
    apac_strict_slug: str

    @property
    def meeting_spine_pattern(self) -> str:
        return f"*-LAND-{self.period}-meeting-spine.pptx"

    @property
    def production_summary_title(self) -> str:
        return f"{self.month_label} Regional Production Line"

    @property
    def sharepoint_folder(self) -> str:
        return f"General/Book of Business/Sales Director Reporting/{self.quarter_folder}/{self.month_label}"

    @property
    def sharepoint_month_slug(self) -> str:
        return self.month_label.lower().replace(" ", "_")

    @property
    def sharepoint_warning_filename(self) -> str:
        return f"README_DO_NOT_USE_{self.month_label.replace(' ', '_')}_decks_pending_QA.txt"

    @property
    def sharepoint_upload_manifest_name(self) -> str:
        return f"sharepoint_{self.sharepoint_month_slug}_upload_manifest.json"

    @property
    def sharepoint_validation_manifest_name(self) -> str:
        return f"sharepoint_{self.sharepoint_month_slug}_validation_manifest.json"

    @property
    def sharepoint_containment_manifest_name(self) -> str:
        return "sharepoint_containment_manifest.json"

    @property
    def sharepoint_publish_suffixes(self) -> tuple[str, ...]:
        return (
            f"LAND Territory Review - {self.month_label}.pptx",
            f"Connected Excel Source - {self.month_label}.xlsx",
            f"LAND Meeting Spine - {self.month_label}.pptx",
            f"Connected Excel Audit Workbook - {self.month_label}.xlsx",
            f"PowerPoint Table Source Workbook - {self.month_label}.xlsx",
        )


def quarter_bounds(period: str) -> tuple[date, date]:
    """Return inclusive quarter start and exclusive quarter end for YYYY-Qn."""

    if "-Q" not in period:
        raise ValueError(f"period missing '-Q' separator: {period!r}")
    year_s, quarter_s = period.split("-Q", 1)
    year = int(year_s)
    quarter = int(quarter_s)
    if quarter not in {1, 2, 3, 4}:
        raise ValueError(f"quarter must be 1..4: {period!r}")
    start_month = (quarter - 1) * 3 + 1
    end_year = year + (1 if quarter == 4 else 0)
    end_month = 1 if quarter == 4 else start_month + 3
    return date(year, start_month, 1), date(end_year, end_month, 1)


def quarter_end_inclusive(period: str) -> date:
    """Return the last calendar day inside YYYY-Qn."""

    _, period_end_exclusive = quarter_bounds(period)
    return period_end_exclusive - timedelta(days=1)


def default_snapshot_date(period: str, *, today: date | None = None) -> date:
    """Best-known as-of date for a period.

    Validated monthly lanes can pin this to an explicit Salesforce extract
    date. Other periods fall back to today's date, clamped to the quarter end,
    because they are not yet certified as repeatable production lanes.
    """

    if period == DEFAULT_PERIOD:
        return date.fromisoformat(context_for_period(period).snapshot_date)
    today_value = today or date.today()
    return min(today_value, quarter_end_inclusive(period))


def period_anchor(period: str, *, as_of_date: date | None = None, today: date | None = None) -> date:
    """Anchor rolling windows and aging logic to the requested as-of date."""

    if as_of_date is not None:
        return min(as_of_date, quarter_end_inclusive(period))
    return default_snapshot_date(period, today=today)


def context_for_period(period: str = DEFAULT_PERIOD) -> PeriodContext:
    """Return the validated operating context for a period.

    The next quarter-roll work item is to add a real calendar-driven context
    builder and update the upstream SFDC extraction windows. Until then, only
    the lane that has been built and audited is accepted.
    """

    normalized = period.strip()
    if normalized != "2026-Q2":
        raise ValueError(
            f"{normalized!r} is not wired for the regional deck production line yet; "
            "only 2026-Q2 / May 2026 has validated dates, gates, and package naming."
        )
    return PeriodContext(
        period="2026-Q2",
        month_label="May 2026",
        quarter_folder="Q2 2026",
        snapshot_date="2026-04-30",
        kickoff_date="2026-05-01",
        kickoff_date_long="Friday, May 1, 2026",
        review_package_dir=Path.home() / "Downloads" / "May 2026 Meeting Spine Candidates",
        required_deck_text=("May 2026", "Land+Expand", "Renewal ACV", "unweighted"),
        apac_strict_slug="Jesper-Tyrer",
    )
