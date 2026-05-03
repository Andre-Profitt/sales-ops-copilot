"""Read-only factory plan model for the Sales Director monthly factory.

This module exposes a canonical list of stages the regional production line
runs for the proven monthly lane. It is intentionally declarative: it does not
import or execute the production line. Every stage advertises:

- a stable ``id`` (snake_case)
- a ``phase`` (source, finalize, gate, package, publish, evidence)
- a human ``name`` and ``description``
- the canonical ``command`` template (with ``{period}`` and optional
  ``{director_slug}`` placeholders)
- ``produces`` artifact paths (relative to repo root, with placeholders)
- ``gates`` referenced (governance contracts, not script names)
- ``requires_office`` to flag stages that need the Windows VM or Office COM
- ``runs_on_publish_only`` to mark publish-only stages

The plan can be rendered for any period; whether the period is certified for
production is enforced separately by ``period_context.context_for_period`` and
by the period-roll certification harness. ``factory_plan_for_period`` emits a
``period_status`` field so callers can present "planned" vs "ready".
"""

from __future__ import annotations

import datetime as dt
from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class FactoryStage:
    id: str
    phase: str
    name: str
    description: str
    command: tuple[str, ...]
    produces: tuple[str, ...] = ()
    gates: tuple[str, ...] = ()
    requires_office: bool = False
    runs_on_publish_only: bool = False
    runs_on_full_refresh_only: bool = False
    runs_on_source_only: bool = False
    notes: tuple[str, ...] = ()


PHASES: tuple[str, ...] = (
    "source",
    "finalize",
    "gate",
    "package",
    "evidence",
    "publish",
)


CANONICAL_STAGES: tuple[FactoryStage, ...] = (
    FactoryStage(
        id="source_refresh",
        phase="source",
        name="Salesforce source refresh",
        description=(
            "Refresh trends.json, brief.md, land.xlsx, and land.model.xlsx "
            "from Salesforce using the pinned snapshot date."
        ),
        command=(
            ".venv/bin/python",
            "scripts/land_brief.py",
            "--period",
            "{period}",
            "--snapshot-date",
            "{snapshot_date}",
            "--all-directors",
        ),
        produces=(
            "state/{period}/<DirectorSlug>/source/trends.json",
            "state/{period}/<DirectorSlug>/source/brief.md",
            "state/{period}/<DirectorSlug>/source/land.xlsx",
            "state/{period}/<DirectorSlug>/source/land.model.xlsx",
        ),
        gates=(
            "ARR uses APTS_Opportunity_ARR__c with Type IN ('Land','Expand')",
            "ACV uses APTS_Renewal_ACV__c with Type = 'Renewal'",
            "Internal/test/SimCorp pollution filtered",
        ),
        runs_on_full_refresh_only=True,
        runs_on_source_only=True,
    ),
    FactoryStage(
        id="source_envelope_validation",
        phase="source",
        name="Source envelope validation",
        description="Validate refreshed Salesforce envelopes without regenerating decks.",
        command=(
            ".venv/bin/python",
            "scripts/run_land_to_deck.py",
            "--period",
            "{period}",
            "--snapshot-date",
            "{snapshot_date}",
            "--skip-regen",
            "--validate-only",
            "--all-directors",
        ),
        gates=(
            "Snapshot dates align with period_context.snapshot_date",
            "Required deck text tokens present in source",
        ),
        runs_on_full_refresh_only=True,
        runs_on_source_only=True,
    ),
    FactoryStage(
        id="connected_factory_rebuild",
        phase="source",
        name="Connected factory workbook rebuild",
        description="Rebuild connected Excel factory workbooks from refreshed source.",
        command=(
            ".venv/bin/python",
            "scripts/build_connected_factory_workbook.py",
            "--period",
            "{period}",
            "--all-directors",
        ),
        produces=(
            "factory/connected/connected_factory.xlsx",
            "factory/connected/connected_factory_table_images.xlsx",
        ),
        gates=(
            "Workbook formulas match source ARR/ACV totals",
            "Audit tabs present with named ranges",
        ),
        runs_on_full_refresh_only=True,
        runs_on_source_only=True,
    ),
    FactoryStage(
        id="full_table_image_refresh",
        phase="finalize",
        name="Regional table-image factory refresh",
        description=(
            "Drive the Windows VM/PowerPoint COM bridge to refresh linked "
            "table images for every director."
        ),
        command=(
            ".venv/bin/python",
            "scripts/run_regional_table_image_factory.py",
            "--period",
            "{period}",
            "--host",
            "{host}",
            "--refresh-existing",
            "--finalize-close",
        ),
        gates=(
            "Windows VM bridge reachable",
            "Each director's linked deck refresh emits a per-run manifest",
        ),
        requires_office=True,
        runs_on_full_refresh_only=True,
    ),
    FactoryStage(
        id="regional_intelligence_specs",
        phase="finalize",
        name="Regional intelligence specs",
        description="Build per-director intelligence spec JSON inputs for slide assembly.",
        command=(
            ".venv/bin/python",
            "scripts/build_regional_intelligence_specs.py",
            "--period",
            "{period}",
        ),
    ),
    FactoryStage(
        id="ai_deck_builder_review_workbook",
        phase="finalize",
        name="AI deck-builder review workbook",
        description=(
            "Build per-director Excel control packs tying together the "
            "think-cell lane contract, AI artifact requirements, deck paths, "
            "and publish evidence."
        ),
        command=(
            ".venv/bin/python",
            "scripts/build_ai_deck_builder_review_workbook.py",
            "--period",
            "{period}",
        ),
        produces=(
            "state/{period}/<DirectorSlug>/factory/ai-review/<slug>-{period}-AI-Deck-Builder-Review.xlsx",
        ),
        gates=(
            "AI text slots have evidence-ref/source-metric artifact requirements",
            "think-cell slot lanes trace to the render-lane contract",
        ),
    ),
    FactoryStage(
        id="source_aware_text_polish",
        phase="finalize",
        name="Source-aware deck text polish",
        description="Polish linked-deck text using source-aware prompts; no chart edits.",
        command=(
            ".venv/bin/python",
            "scripts/polish_regional_linked_deck_text.py",
            "--period",
            "{period}",
        ),
    ),
    FactoryStage(
        id="table_image_aspect_fix",
        phase="finalize",
        name="Table-image aspect ratio fix",
        description="Normalize aspect ratios for refreshed table images.",
        command=(
            ".venv/bin/python",
            "scripts/fix_table_image_aspect_ratios.py",
            "--period",
            "{period}",
            "--linked-decks",
        ),
    ),
    FactoryStage(
        id="meeting_spine_build",
        phase="finalize",
        name="Regional meeting-spine deck build",
        description="Assemble each director's 16-slide meeting spine deck.",
        command=(
            ".venv/bin/python",
            "scripts/build_regional_meeting_spine_decks.py",
            "--period",
            "{period}",
        ),
        produces=(
            "state/{period}/<DirectorSlug>/factory/meeting-spine/<slug>-LAND-{period}-meeting-spine.pptx",
        ),
        gates=("Meeting spine slide count and required-text gates pass.",),
    ),
    FactoryStage(
        id="meeting_spine_smoke",
        phase="gate",
        name="Meeting-spine smoke check",
        description="In-process meeting-spine sanity check (placeholder/text/etc).",
        command=(),
        notes=("Internal check; no external command. Asserts forbidden tokens are absent.",),
    ),
    FactoryStage(
        id="regional_publish_gate",
        phase="gate",
        name="Regional deck publish gate",
        description=(
            "Run the freshness, forbidden-text, ARR/ACV, and packaging gate "
            "across all linked + meeting-spine decks."
        ),
        command=(
            ".venv/bin/python",
            "scripts/run_regional_deck_publish_gate.py",
            "--period",
            "{period}",
        ),
        produces=(
            "state/{period}/__regional__/publish_gate/publish_gate.json",
            "state/{period}/__regional__/publish_gate/publish_gate.md",
        ),
        gates=(
            "ARR/ACV not blended",
            "Type filters mandatory",
            "Forbidden tokens absent (test/SimCorp/internal SC, #NAME, #NULL, etc.)",
            "PowerPoint links not stale relative to source",
        ),
    ),
    FactoryStage(
        id="apac_intel_audit_linked",
        phase="gate",
        name="APAC strict intel coverage (linked deck)",
        description="Strict APAC original-intel coverage audit on the linked deck.",
        command=(
            ".venv/bin/python",
            "scripts/audit_jesper_apac_intel_coverage.py",
            "--period",
            "{period}",
            "--target",
            "linked",
        ),
    ),
    FactoryStage(
        id="apac_intel_audit_spine",
        phase="gate",
        name="APAC strict intel coverage (meeting spine)",
        description="Strict APAC original-intel coverage audit on the meeting-spine deck.",
        command=(
            ".venv/bin/python",
            "scripts/audit_jesper_apac_intel_coverage.py",
            "--period",
            "{period}",
            "--target",
            "meeting_spine",
        ),
    ),
    FactoryStage(
        id="regional_goal_audit",
        phase="gate",
        name="Regional goal audit",
        description="Audit regional decks against documented goals/contracts.",
        command=(
            ".venv/bin/python",
            "scripts/audit_regional_decks_against_goals.py",
            "--period",
            "{period}",
        ),
    ),
    FactoryStage(
        id="downloads_review_package_copy",
        phase="package",
        name="Downloads review package copy",
        description=(
            "Copy meeting-spine decks plus connected and table-source workbooks "
            "into the Downloads review folder."
        ),
        command=(),
        produces=("~/Downloads/{month_label} Meeting Spine Candidates/",),
        notes=("Internal copy step; no separate CLI.",),
    ),
    FactoryStage(
        id="review_package_validation",
        phase="gate",
        name="Downloads review package validation",
        description="Validate the Downloads package contains the expected 9 spines and audit workbooks.",
        command=(
            ".venv/bin/python",
            "scripts/validate_may_review_package.py",
            "--period",
            "{period}",
        ),
    ),
    FactoryStage(
        id="review_package_visual_gate",
        phase="gate",
        name="Review package visual gate",
        description="Render-based visual gate for every packaged meeting-spine deck.",
        command=(
            ".venv/bin/python",
            "scripts/run_review_package_visual_gate.py",
            "--period",
            "{period}",
        ),
        produces=(
            "state/{period}/__regional__/visual_gate/review_package/review_package_visual_gate.json",
        ),
    ),
    FactoryStage(
        id="sharepoint_containment",
        phase="publish",
        name="SharePoint containment",
        description=(
            "Quarantine prior top-level assets in the SharePoint folder so only "
            "the new run's assets are exposed."
        ),
        command=(
            ".venv/bin/python",
            "scripts/contain_may_sharepoint_uploads.py",
            "--execute",
        ),
        gates=("SharePoint folder name from period_context.sharepoint_folder",),
        runs_on_publish_only=True,
        requires_office=False,
    ),
    FactoryStage(
        id="sharepoint_upload",
        phase="publish",
        name="SharePoint upload",
        description="Upload final per-director decks plus audit/source workbooks.",
        command=(
            ".venv/bin/python",
            "scripts/upload_may_regional_assets_sharepoint.py",
            "--period",
            "{period}",
        ),
        runs_on_publish_only=True,
    ),
    FactoryStage(
        id="sharepoint_validate",
        phase="publish",
        name="SharePoint upload validation",
        description="Validate SharePoint expected/missing/stale/size-mismatch counts.",
        command=(
            ".venv/bin/python",
            "scripts/validate_may_sharepoint_upload.py",
            "--period",
            "{period}",
            "--upload-manifest",
        ),
        produces=("state/{period}/__regional__/{sharepoint_validation_manifest_name}",),
        runs_on_publish_only=True,
    ),
    FactoryStage(
        id="status_report",
        phase="evidence",
        name="Production status report",
        description="Generate the regional production-line status report.",
        command=(
            ".venv/bin/python",
            "scripts/report_regional_production_status.py",
            "--period",
            "{period}",
        ),
        produces=(
            "state/{period}/__regional__/production_status/regional_production_status.json",
            "state/{period}/__regional__/production_status/regional_production_status.md",
        ),
    ),
    FactoryStage(
        id="sharepoint_evidence_refresh",
        phase="evidence",
        name="SharePoint evidence refresh",
        description="Re-upload mutable evidence files after the status report is regenerated.",
        command=(
            ".venv/bin/python",
            "scripts/upload_may_sharepoint_evidence.py",
            "--period",
            "{period}",
        ),
        runs_on_publish_only=True,
    ),
)


@dataclass
class FactoryPlan:
    schema: str
    period: str
    period_status: str
    month_label: str | None
    snapshot_date: str | None
    sharepoint_folder: str | None
    generated_at_utc: str
    stages: list[dict[str, Any]]
    counts: dict[str, int]
    director_slug: str | None = None
    constraints: list[str] = field(default_factory=list)
    blockers: list[str] = field(default_factory=list)


def _materialize_stage(
    stage: FactoryStage,
    *,
    period: str,
    snapshot_date: str | None,
    month_label: str | None,
    host: str = "Windows-VM",
    sharepoint_validation_manifest_name: str | None = None,
) -> dict[str, Any]:
    def _fmt(value: str) -> str:
        return value.format(
            period=period,
            host=host,
            snapshot_date=snapshot_date or "<unset>",
            month_label=month_label or "<unset>",
            sharepoint_validation_manifest_name=sharepoint_validation_manifest_name or "<unset>",
        )

    raw = asdict(stage)
    raw["command"] = [_fmt(part) for part in stage.command]
    raw["produces"] = [_fmt(part) for part in stage.produces]
    raw["gates"] = list(stage.gates)
    raw["notes"] = list(stage.notes)
    return raw


def factory_plan_for_period(
    period: str,
    *,
    director_slug: str | None = None,
    include_publish: bool = True,
    include_full_refresh: bool = True,
    include_source_only: bool = True,
    host: str = "Windows-VM",
) -> FactoryPlan:
    """Return a structured plan for the given period.

    Uncertified periods produce a plan with ``period_status="uncertified"`` and
    a non-empty ``blockers`` list. The plan still describes the canonical
    stages so callers can use it to drive the certification harness.
    """

    from scripts.period_context import context_for_period

    blockers: list[str] = []
    period_status = "ready"
    snapshot_date: str | None = None
    month_label: str | None = None
    sharepoint_folder: str | None = None
    sharepoint_validation_manifest_name: str | None = None

    try:
        ctx = context_for_period(period)
        snapshot_date = ctx.snapshot_date
        month_label = ctx.month_label
        sharepoint_folder = ctx.sharepoint_folder
        sharepoint_validation_manifest_name = ctx.sharepoint_validation_manifest_name
    except ValueError as exc:
        period_status = "uncertified"
        blockers.append(str(exc))

    materialized: list[dict[str, Any]] = []
    for stage in CANONICAL_STAGES:
        if stage.runs_on_full_refresh_only and not include_full_refresh:
            continue
        if stage.runs_on_source_only and not include_source_only and not include_full_refresh:
            continue
        if stage.runs_on_publish_only and not include_publish:
            continue
        materialized.append(
            _materialize_stage(
                stage,
                period=period,
                snapshot_date=snapshot_date,
                month_label=month_label,
                host=host,
                sharepoint_validation_manifest_name=sharepoint_validation_manifest_name,
            )
        )

    counts: dict[str, int] = {phase: 0 for phase in PHASES}
    office = 0
    publish_only = 0
    for entry in materialized:
        counts[entry["phase"]] = counts.get(entry["phase"], 0) + 1
        if entry["requires_office"]:
            office += 1
        if entry["runs_on_publish_only"]:
            publish_only += 1
    counts["total"] = len(materialized)
    counts["requires_office"] = office
    counts["publish_only"] = publish_only

    constraints = [
        "ARR = Land+Expand via APTS_Opportunity_ARR__c.",
        "ACV = Renewal via APTS_Renewal_ACV__c.",
        "Type filters are mandatory and never blended.",
        "Internal/test/SimCorp/SC pollution stays filtered.",
        "Weighted vs unweighted is labelled explicitly.",
        "--refresh-source must be paired with --source-only or --full-table-image-refresh.",
        "Uncertified periods must fail closed for refresh and publish.",
    ]

    if period_status == "uncertified":
        blockers.append(
            "Run the period-roll certification harness "
            "(scripts/sd_factory_period_roll_certification.py) before publish."
        )

    return FactoryPlan(
        schema="sales-director-factory-plan/v1",
        period=period,
        period_status=period_status,
        month_label=month_label,
        snapshot_date=snapshot_date,
        sharepoint_folder=sharepoint_folder,
        generated_at_utc=dt.datetime.now(dt.timezone.utc).isoformat(),
        stages=materialized,
        counts=counts,
        director_slug=director_slug,
        constraints=constraints,
        blockers=blockers,
    )


def plan_to_markdown(plan: FactoryPlan) -> str:
    lines: list[str] = [
        f"# Sales Director Factory Plan - {plan.period}",
        "",
        f"- Status: `{plan.period_status}`",
        f"- Month label: `{plan.month_label or 'n/a'}`",
        f"- Snapshot date: `{plan.snapshot_date or 'n/a'}`",
        f"- SharePoint folder: `{plan.sharepoint_folder or 'n/a'}`",
        f"- Generated UTC: `{plan.generated_at_utc}`",
    ]
    if plan.director_slug:
        lines.append(f"- Director slug filter: `{plan.director_slug}`")
    lines.extend(["", "## Counts", ""])
    for key, value in plan.counts.items():
        lines.append(f"- {key}: {value}")
    if plan.blockers:
        lines.extend(["", "## Blockers", ""])
        for item in plan.blockers:
            lines.append(f"- {item}")
    lines.extend(["", "## Constraints", ""])
    for item in plan.constraints:
        lines.append(f"- {item}")
    lines.extend(
        [
            "",
            "## Stages",
            "",
            "| # | Phase | Stage | Office? | Publish only? | Refresh only? |",
            "|---:|---|---|:---:|:---:|:---:|",
        ]
    )
    for idx, stage in enumerate(plan.stages, 1):
        lines.append(
            "| {idx} | {phase} | {name} | {office} | {publish} | {refresh} |".format(
                idx=idx,
                phase=stage["phase"],
                name=stage["name"],
                office="yes" if stage["requires_office"] else "no",
                publish="yes" if stage["runs_on_publish_only"] else "no",
                refresh="yes" if stage["runs_on_full_refresh_only"] else "no",
            )
        )
    lines.extend(["", "## Stage Detail", ""])
    for stage in plan.stages:
        lines.extend(
            [
                f"### {stage['phase']} / {stage['name']}",
                "",
                f"- ID: `{stage['id']}`",
                f"- Description: {stage['description']}",
            ]
        )
        if stage["command"]:
            lines.append("- Command:")
            lines.append("  ```")
            lines.append("  " + " ".join(stage["command"]))
            lines.append("  ```")
        if stage["produces"]:
            lines.append("- Produces:")
            for item in stage["produces"]:
                lines.append(f"  - `{item}`")
        if stage["gates"]:
            lines.append("- Gates:")
            for item in stage["gates"]:
                lines.append(f"  - {item}")
        if stage["notes"]:
            lines.append("- Notes:")
            for item in stage["notes"]:
                lines.append(f"  - {item}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


__all__ = [
    "CANONICAL_STAGES",
    "FactoryPlan",
    "FactoryStage",
    "PHASES",
    "factory_plan_for_period",
    "plan_to_markdown",
]
