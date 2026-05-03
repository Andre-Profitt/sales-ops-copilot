"""Period-roll certification harness for the Sales Director factory.

The harness validates a candidate or already-wired period against the gates
that must hold before a non-May period is allowed to refresh source data or
publish to SharePoint:

- Folder name conventions (``Q<n> YYYY/<Month YYYY>``).
- Snapshot date math (date format, in-quarter, before kickoff).
- Salesforce Type-filter wiring (ARR uses ``Type IN ('Land','Expand')``,
  ACV uses ``Type = 'Renewal'``).
- Director roster (the 9 MD-1 directors).
- Publish remains blocked until ``period_context.context_for_period``
  recognizes the period.

The harness is plan-only and does not execute deck builds, SharePoint calls,
or Salesforce queries. It reads source files using a static grep for the
Type-filter check and uses ``period_context`` for everything else.
"""

from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

REPO_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class CertificationSpec:
    """A candidate period spec the harness can validate without code wiring."""

    period: str
    month_label: str
    snapshot_date: str
    kickoff_date: str
    sharepoint_folder: str
    review_package_dir: str | None = None


@dataclass
class CertificationCheck:
    name: str
    status: str  # "pass" | "fail" | "warn"
    severity: str  # "critical" | "warning" | "info"
    finding: str
    evidence: str | None = None


@dataclass
class CertificationReport:
    schema: str
    period: str
    mode: str  # "existing" | "candidate"
    period_status: str  # "ready" | "uncertified" | "candidate"
    generated_at_utc: str
    spec: dict | None
    checks: list[CertificationCheck]
    critical_failures: list[CertificationCheck] = field(default_factory=list)
    warning_failures: list[CertificationCheck] = field(default_factory=list)
    publish_allowed: bool = False

    @property
    def status(self) -> str:
        if self.critical_failures:
            return "fail"
        if self.warning_failures:
            return "warn"
        return "pass"


_PERIOD_RE = re.compile(r"^(\d{4})-Q([1-4])$")
_MONTH_LABEL_RE = re.compile(r"^[A-Z][a-z]+\s+\d{4}$")
_QUARTER_FOLDER_RE = re.compile(r"^Q[1-4]\s+\d{4}$")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


REQUIRED_DIRECTOR_NAMES: tuple[str, ...] = (
    "Megan Miceli",
    "Patrick Gaughan",
    "Jesper Tyrer",
    "Sarah Pittroff",
    "Francois Thaury",
    "Dan Peppett",
    "Christian Ebbesen",
    "Mourad",
    "Adam Steinhouse",
)


def _parse_quarter(period: str) -> tuple[int, int] | None:
    match = _PERIOD_RE.match(period)
    if not match:
        return None
    return int(match.group(1)), int(match.group(2))


def _quarter_bounds(year: int, quarter: int) -> tuple[dt.date, dt.date]:
    start_month = (quarter - 1) * 3 + 1
    end_year = year + (1 if quarter == 4 else 0)
    end_month = 1 if quarter == 4 else start_month + 3
    return dt.date(year, start_month, 1), dt.date(end_year, end_month, 1)


def check_period_format(period: str) -> CertificationCheck:
    parsed = _parse_quarter(period)
    if not parsed:
        return CertificationCheck(
            name="period_format",
            status="fail",
            severity="critical",
            finding=f"period must match YYYY-Qn (got {period!r})",
        )
    return CertificationCheck(
        name="period_format",
        status="pass",
        severity="critical",
        finding=f"period parses as {parsed[0]} Q{parsed[1]}",
    )


def check_snapshot_date(period: str, snapshot_date: str) -> CertificationCheck:
    if not _DATE_RE.match(snapshot_date):
        return CertificationCheck(
            name="snapshot_date_format",
            status="fail",
            severity="critical",
            finding=f"snapshot_date must be YYYY-MM-DD (got {snapshot_date!r})",
        )
    parsed = _parse_quarter(period)
    if not parsed:
        return CertificationCheck(
            name="snapshot_in_quarter",
            status="fail",
            severity="critical",
            finding=f"cannot validate snapshot in unknown period {period!r}",
        )
    year, quarter = parsed
    start, end = _quarter_bounds(year, quarter)
    snap = dt.date.fromisoformat(snapshot_date)
    last_day = end - dt.timedelta(days=1)
    if not (start <= snap <= last_day):
        return CertificationCheck(
            name="snapshot_in_quarter",
            status="fail",
            severity="critical",
            finding=(
                f"snapshot {snapshot_date} outside quarter "
                f"[{start.isoformat()}, {last_day.isoformat()}]"
            ),
        )
    return CertificationCheck(
        name="snapshot_in_quarter",
        status="pass",
        severity="critical",
        finding=f"snapshot {snapshot_date} is in {period}",
    )


def check_kickoff_after_snapshot(snapshot_date: str, kickoff_date: str) -> CertificationCheck:
    if not _DATE_RE.match(kickoff_date):
        return CertificationCheck(
            name="kickoff_date_format",
            status="fail",
            severity="critical",
            finding=f"kickoff_date must be YYYY-MM-DD (got {kickoff_date!r})",
        )
    if not _DATE_RE.match(snapshot_date):
        return CertificationCheck(
            name="kickoff_after_snapshot",
            status="fail",
            severity="critical",
            finding="snapshot_date format prevents comparison",
        )
    snap = dt.date.fromisoformat(snapshot_date)
    kick = dt.date.fromisoformat(kickoff_date)
    if kick <= snap:
        return CertificationCheck(
            name="kickoff_after_snapshot",
            status="fail",
            severity="critical",
            finding=f"kickoff {kickoff_date} must be after snapshot {snapshot_date}",
        )
    return CertificationCheck(
        name="kickoff_after_snapshot",
        status="pass",
        severity="critical",
        finding=f"kickoff {kickoff_date} > snapshot {snapshot_date}",
    )


def check_month_label(month_label: str) -> CertificationCheck:
    if not _MONTH_LABEL_RE.match(month_label):
        return CertificationCheck(
            name="month_label_format",
            status="fail",
            severity="critical",
            finding=f"month_label must match 'Month YYYY' (got {month_label!r})",
        )
    return CertificationCheck(
        name="month_label_format",
        status="pass",
        severity="critical",
        finding=f"month_label {month_label!r} matches 'Month YYYY'",
    )


def check_sharepoint_folder(
    period: str, month_label: str, sharepoint_folder: str
) -> CertificationCheck:
    parsed = _parse_quarter(period)
    if not parsed:
        return CertificationCheck(
            name="sharepoint_folder_format",
            status="fail",
            severity="critical",
            finding=f"cannot validate folder for unknown period {period!r}",
        )
    year, quarter = parsed
    expected_quarter_folder = f"Q{quarter} {year}"
    expected_suffix = f"{expected_quarter_folder}/{month_label}"
    if not sharepoint_folder.endswith(expected_suffix):
        return CertificationCheck(
            name="sharepoint_folder_format",
            status="fail",
            severity="critical",
            finding=(
                f"sharepoint_folder must end with {expected_suffix!r}; got {sharepoint_folder!r}"
            ),
        )
    if not _QUARTER_FOLDER_RE.match(expected_quarter_folder):
        return CertificationCheck(
            name="quarter_folder_format",
            status="fail",
            severity="critical",
            finding=f"derived quarter folder {expected_quarter_folder!r} fails regex",
        )
    return CertificationCheck(
        name="sharepoint_folder_format",
        status="pass",
        severity="critical",
        finding=f"sharepoint_folder ends with {expected_suffix!r}",
        evidence=sharepoint_folder,
    )


def check_director_roster() -> list[CertificationCheck]:
    from scripts._directors import canonical_directors

    directors = canonical_directors()
    names = {d["name"] for d in directors}
    checks: list[CertificationCheck] = []
    if len(directors) == len(REQUIRED_DIRECTOR_NAMES):
        checks.append(
            CertificationCheck(
                name="director_roster_count",
                status="pass",
                severity="critical",
                finding=f"canonical_directors() returns {len(directors)} entries",
            )
        )
    else:
        checks.append(
            CertificationCheck(
                name="director_roster_count",
                status="fail",
                severity="critical",
                finding=f"expected {len(REQUIRED_DIRECTOR_NAMES)} directors, got {len(directors)}",
            )
        )
    missing = [name for name in REQUIRED_DIRECTOR_NAMES if name not in names]
    if missing:
        checks.append(
            CertificationCheck(
                name="director_roster_required_names",
                status="fail",
                severity="critical",
                finding=f"missing directors: {', '.join(missing)}",
            )
        )
    else:
        checks.append(
            CertificationCheck(
                name="director_roster_required_names",
                status="pass",
                severity="critical",
                finding="all required director names present",
            )
        )
    return checks


def _grep_count(file_path: Path, needle: str) -> int:
    if not file_path.exists():
        return 0
    text = file_path.read_text(encoding="utf-8", errors="replace")
    return text.count(needle)


def check_arr_acv_type_filters(*, root: Path | None = None) -> list[CertificationCheck]:
    """Static check: ARR queries use Type IN ('Land','Expand'); ACV uses Type = 'Renewal'."""

    base = root or REPO_ROOT
    land_brief = base / "scripts" / "land_brief.py"
    arr_filter = "Type IN ('Land','Expand')"
    acv_filter = "Type = 'Renewal'"
    arr_count = _grep_count(land_brief, arr_filter)
    acv_count = _grep_count(land_brief, acv_filter)
    checks: list[CertificationCheck] = []
    checks.append(
        CertificationCheck(
            name="arr_filter_uses_type_in_land_expand",
            status="pass" if arr_count > 0 else "fail",
            severity="critical",
            finding=f"{arr_count} occurrence(s) of {arr_filter!r} in scripts/land_brief.py",
            evidence=str(land_brief.relative_to(base)),
        )
    )
    checks.append(
        CertificationCheck(
            name="acv_filter_uses_type_renewal",
            status="pass" if acv_count > 0 else "fail",
            severity="critical",
            finding=f"{acv_count} occurrence(s) of {acv_filter!r} in scripts/land_brief.py",
            evidence=str(land_brief.relative_to(base)),
        )
    )
    blend_pattern = "Type IN ('Land','Expand','Renewal')"
    blend_count = _grep_count(land_brief, blend_pattern)
    checks.append(
        CertificationCheck(
            name="arr_acv_blend_absent",
            status="pass" if blend_count == 0 else "fail",
            severity="critical",
            finding=(f"forbidden blended Type filter pattern occurrences: {blend_count}"),
            evidence=str(land_brief.relative_to(base)),
        )
    )
    return checks


def check_period_context_recognition(period: str) -> tuple[CertificationCheck, bool]:
    """Returns (check, recognized).

    ``recognized=True`` means ``context_for_period(period)`` succeeded; this
    period is wired and may publish if other gates pass. ``recognized=False``
    means it raised — publish must remain blocked.
    """

    from scripts.period_context import context_for_period

    try:
        context_for_period(period)
        return (
            CertificationCheck(
                name="period_context_recognition",
                status="pass",
                severity="info",
                finding=f"context_for_period({period!r}) succeeded; period is wired",
            ),
            True,
        )
    except ValueError as exc:
        return (
            CertificationCheck(
                name="period_context_recognition",
                status="warn",
                severity="info",
                finding=f"period not yet wired: {exc}",
            ),
            False,
        )


def check_publish_blocked_for_uncertified(period: str) -> CertificationCheck:
    """If the period is not the current certified lane, it must fail closed."""

    from scripts.period_context import DEFAULT_PERIOD, context_for_period

    if period == DEFAULT_PERIOD:
        return CertificationCheck(
            name="publish_blocked_for_uncertified",
            status="pass",
            severity="info",
            finding=f"{period} is the certified lane; publish is gated by other checks.",
        )
    try:
        context_for_period(period)
        return CertificationCheck(
            name="publish_blocked_for_uncertified",
            status="fail",
            severity="critical",
            finding=(
                f"{period} is recognized by period_context but is not the certified "
                f"lane ({DEFAULT_PERIOD}); publish must remain blocked until the "
                "certification harness is updated and the new lane is signed off."
            ),
        )
    except ValueError:
        return CertificationCheck(
            name="publish_blocked_for_uncertified",
            status="pass",
            severity="critical",
            finding=(
                f"{period} not recognized by period_context; refresh-source and "
                "publish remain blocked as required."
            ),
        )


def _existing_spec(period: str) -> CertificationSpec:
    from scripts.period_context import context_for_period

    ctx = context_for_period(period)
    return CertificationSpec(
        period=ctx.period,
        month_label=ctx.month_label,
        snapshot_date=ctx.snapshot_date,
        kickoff_date=ctx.kickoff_date,
        sharepoint_folder=ctx.sharepoint_folder,
        review_package_dir=str(ctx.review_package_dir),
    )


def _summarise(report: CertificationReport, *, recognized: bool) -> CertificationReport:
    report.critical_failures = [
        c for c in report.checks if c.status == "fail" and c.severity == "critical"
    ]
    report.warning_failures = [
        c for c in report.checks if c.status == "fail" and c.severity == "warning"
    ]
    if not report.critical_failures and recognized:
        report.publish_allowed = True
    return report


def certify_existing_period(period: str) -> CertificationReport:
    """Validate an already-wired period against all gates."""

    spec = _existing_spec(period)
    return _certify(spec, mode="existing")


def certify_candidate(spec: CertificationSpec) -> CertificationReport:
    """Validate a candidate period spec without requiring code wiring."""

    return _certify(spec, mode="candidate")


def _certify(spec: CertificationSpec, *, mode: str) -> CertificationReport:
    from dataclasses import asdict as _asdict

    checks: list[CertificationCheck] = []
    checks.append(check_period_format(spec.period))
    checks.append(check_snapshot_date(spec.period, spec.snapshot_date))
    checks.append(check_kickoff_after_snapshot(spec.snapshot_date, spec.kickoff_date))
    checks.append(check_month_label(spec.month_label))
    checks.append(check_sharepoint_folder(spec.period, spec.month_label, spec.sharepoint_folder))
    checks.extend(check_director_roster())
    checks.extend(check_arr_acv_type_filters())
    recognition, recognized = check_period_context_recognition(spec.period)
    checks.append(recognition)
    checks.append(check_publish_blocked_for_uncertified(spec.period))

    if mode == "existing":
        period_status = "ready" if recognized else "uncertified"
    else:
        period_status = "candidate"

    report = CertificationReport(
        schema="sales-director-period-roll-certification/v1",
        period=spec.period,
        mode=mode,
        period_status=period_status,
        generated_at_utc=dt.datetime.now(dt.timezone.utc).isoformat(),
        spec=_asdict(spec),
        checks=checks,
    )
    return _summarise(report, recognized=recognized)


def report_to_markdown(report: CertificationReport) -> str:
    lines = [
        f"# Sales Director Period-Roll Certification - {report.period}",
        "",
        f"- Mode: `{report.mode}`",
        f"- Period status: `{report.period_status}`",
        f"- Aggregate status: `{report.status}`",
        f"- Publish allowed: `{report.publish_allowed}`",
        f"- Generated UTC: `{report.generated_at_utc}`",
        "",
        "## Spec",
        "",
    ]
    if report.spec:
        for key, value in report.spec.items():
            lines.append(f"- {key}: `{value}`")
    lines.extend(
        [
            "",
            "## Checks",
            "",
            "| Check | Status | Severity | Finding |",
            "|---|---|---|---|",
        ]
    )
    for check in report.checks:
        finding = check.finding.replace("|", "/")
        lines.append(f"| {check.name} | {check.status} | {check.severity} | {finding} |")
    if report.critical_failures:
        lines.extend(["", "## Critical Failures", ""])
        for check in report.critical_failures:
            lines.append(f"- `{check.name}`: {check.finding}")
    return "\n".join(lines).rstrip() + "\n"


def iter_check_names(report: CertificationReport) -> Iterable[str]:
    for check in report.checks:
        yield check.name


__all__ = [
    "CertificationCheck",
    "CertificationReport",
    "CertificationSpec",
    "REQUIRED_DIRECTOR_NAMES",
    "certify_candidate",
    "certify_existing_period",
    "check_arr_acv_type_filters",
    "check_director_roster",
    "check_kickoff_after_snapshot",
    "check_month_label",
    "check_period_context_recognition",
    "check_period_format",
    "check_publish_blocked_for_uncertified",
    "check_sharepoint_folder",
    "check_snapshot_date",
    "iter_check_names",
    "report_to_markdown",
]
