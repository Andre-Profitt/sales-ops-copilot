"""SimCorp sales-process knowledge graph.

Single source of truth for the SimCorp commercial motion: stages, governance
gates, motions, rules, metrics, and stage-exit qualifiers. Designed to be
imported across projects (sales-ops-copilot, brand-deck-agent-py, future
account-drill skill, daily brief synthesis, alert generators).

Data shape — 6 typed dataclasses + 1 ProcessGraph aggregator:

  Stage              The 8 SimCorp sales stages, with handbook descriptions +
                     exit qualifiers + typical role driving each.
  GovernanceGate     The 5 mandatory deal reviews (Commercial Approval,
                     Margin Review, Deal Services Design, Deal Review,
                     Due Diligence) + which stages they apply at.
  Motion             LAND / EXPAND / RENEWAL — what they are, which stages
                     apply, which revenue field reports them.
  Metric             Every named metric used across surfaces. Distinguishes
                     raw / proxy / derived so consumers know caveats.
  Rule               The 8 action-item rules. Each ties to stages, gates,
                     metrics, and threshold semantics — so adding a rule
                     elsewhere is a graph entry, not a Python rewrite.
  Qualifier          Stage-exit qualifiers (PAIC, TAS, RFP completion,
                     red-lining received, etc.) verbatim from the handbook.

Source-of-truth handbook:
  ~/.claude/intel/simcorp-sales-process-2026-04.md
  (verbatim from Commercial-Handbook-for-Simlink — pulled 2026-04-28)

Source-of-truth brand palette:
  ~/projects/brand-deck-agent-py/assets/simcorp-2024.json

Cross-project consumers (current and intended):
  - sales-ops-copilot/scripts/excel_companion.py  (Process_Standards sheet)
  - sales-ops-copilot/scripts/land_brief.py       (action-item rule wiring)
  - brand-deck-agent-py/agent/land_system_prompt.py (handbook section)
  - sales-ops-copilot/scripts/brief.py            (daily-brief methodology)
  - future Claude / Anthropic SDK skills          (account-drill, owner-drill)

Versioning:
  SCHEMA_VERSION 1 (2026-04-29). Bump when entity shapes change in a way
  that breaks downstream consumers. Adding fields is backward-compatible if
  they have defaults; removing or renaming is breaking.

Usage:
  from sales_process_graph import GRAPH, gates_at_stage, to_llm_context

  for gate in gates_at_stage(3):
      print(gate.name, gate.purpose)

  prompt_block = to_llm_context()  # ~3KB markdown for LLM prompts
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Literal

SCHEMA_VERSION = 1

# Source of brand palette (cross-reference, not copied — read from this file
# at the consumer if exact hex codes are needed).
BRAND_PALETTE_SOURCE = "~/projects/brand-deck-agent-py/assets/simcorp-2024.json"

# Source of handbook intel (cross-reference; same warning).
HANDBOOK_SOURCE = "~/.claude/intel/simcorp-sales-process-2026-04.md"


# ──────────────────────────────────────────────────────────────────────────
# Entity dataclasses
# ──────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Stage:
    """A SimCorp sales-process stage. 8 of them, numbered 1-8."""

    number: int
    name: str
    description: str
    typical_role: str | None = None  # who drives this stage
    exit_qualifier_ids: tuple[str, ...] = ()  # references Qualifier.qid


@dataclass(frozen=True)
class GovernanceGate:
    """Mandatory deal review at one or more stages."""

    name: str
    trigger: str
    when_stages: tuple[int, ...]
    purpose: str


@dataclass(frozen=True)
class Motion:
    """LAND / EXPAND / RENEWAL deal motions."""

    name: Literal["LAND", "EXPAND", "RENEWAL"]
    description: str
    applicable_stages: tuple[int, ...]  # which stage numbers apply
    revenue_field: str  # APTS_Opportunity_ARR__c or APTS_Renewal_ACV__c
    process_notes: str


@dataclass(frozen=True)
class Metric:
    """Named metric. type='raw' = direct field aggregate; 'proxy' = stand-in
    for a metric we can't compute today; 'derived' = formula on raw inputs."""

    name: str
    type: Literal["raw", "proxy", "derived"]
    formula: str
    captures: str
    does_not_capture: str
    how_to_read: str
    deferred_replacement: str | None = None  # if proxy, what would replace it


@dataclass(frozen=True)
class Rule:
    """Action-item rule — fires when a threshold is tripped on a metric for
    a director's territory. The graph defines what; the runner (e.g.
    land_brief.py) implements how."""

    rule_id: str  # stable key, e.g. 'approval_gap'
    title: str
    threshold_summary: str  # human-readable e.g. "Stage 3+ L+E ≥ EUR 500k"
    priority: Literal["high", "medium", "low"]
    applies_at_stages: tuple[int, ...]
    related_gates: tuple[str, ...] = ()
    metrics_used: tuple[str, ...] = ()
    suggested_action: str = ""


@dataclass(frozen=True)
class Qualifier:
    """Stage-exit qualifier (verbatim from handbook). Operational checkbox
    that should be true to advance from one stage to the next."""

    qid: str  # short identifier, e.g. 'paic_assessment'
    label: str  # human label
    description: str  # 1-line context
    from_stage: int  # exit qualifier from this stage
    to_stage: int  # to this stage


@dataclass(frozen=True)
class ProcessGraph:
    """Aggregate of the 6 entity collections."""

    stages: tuple[Stage, ...]
    gates: tuple[GovernanceGate, ...]
    motions: tuple[Motion, ...]
    metrics: tuple[Metric, ...]
    rules: tuple[Rule, ...]
    qualifiers: tuple[Qualifier, ...]


# ──────────────────────────────────────────────────────────────────────────
# The graph data — verbatim from the handbook + this session's metric defs
# ──────────────────────────────────────────────────────────────────────────


_QUALIFIERS = (
    # 1 → 2 Prospecting → Discovery
    Qualifier(
        "engagement_init",
        "Prospect Engagement Initiation",
        "BDRs/SMs proactively engaged high-priority prospects",
        1,
        2,
    ),
    Qualifier(
        "interest_assessment",
        "Prospect Interest Assessment",
        "Key indicators of interest identified; current systems + investment considerations established",
        1,
        2,
    ),
    # 2 → 3 Discovery → Engagement
    Qualifier("relationship_in_person", "Relationship Established (in-person)", "", 2, 3),
    Qualifier("compelling_event", "Compelling Event Identified", "", 2, 3),
    Qualifier(
        "paic_assessment",
        "PAIC assessment completed",
        "Decision process + timeline clear",
        2,
        3,
    ),
    Qualifier(
        "decision_makers",
        "Decision-makers identified + engaged",
        "",
        2,
        3,
    ),
    Qualifier(
        "tom_scope",
        "Target Operating Model + functional/services scope identified",
        "",
        2,
        3,
    ),
    Qualifier(
        "price_guidance",
        "Price guidance or proposal provided",
        "Due diligence continues",
        2,
        3,
    ),
    Qualifier(
        "technical_validation",
        "Technical Validation Completed",
        "Initial concerns addressed",
        2,
        3,
    ),
    Qualifier("on_long_list", "SimCorp on prospect's long list", "", 2, 3),
    # 3 → 4 Engagement → Shortlisted
    Qualifier(
        "tas_completed",
        "TAS assessment completed",
        "Sales Strategy + Project Alignment confirmed",
        3,
        4,
    ),
    Qualifier(
        "decision_criteria",
        "Decision criteria + project scope aligned",
        "",
        3,
        4,
    ),
    Qualifier("buying_roles_mapped", "Key buying roles identified (relationship map)", "", 3, 4),
    Qualifier("initial_quote", "Initial quote created", "", 3, 4),
    Qualifier(
        "rfp_completed",
        "RFP completion or confirmation of intent",
        "",
        3,
        4,
    ),
    Qualifier("on_short_list", "On the short-list", "", 3, 4),
    Qualifier(
        "competitive_position",
        "Competitive Position Established",
        "Effectively positioned vs competitors; prospect investment evident",
        3,
        4,
    ),
    # 4 → 5 Shortlisted → Preferred
    Qualifier(
        "specs_received",
        "Customer Specifications Received (written project specs)",
        "",
        4,
        5,
    ),
    Qualifier("final_scope", "Final Project Scope agreed", "", 4, 5),
    Qualifier(
        "competitive_advantage",
        "Competitive Advantage Recognized by key player",
        "",
        4,
        5,
    ),
    Qualifier("preferred_status", "Preferred vendor status achieved", "", 4, 5),
    Qualifier(
        "close_plan",
        "Close Plan Created",
        "Timelines + legal/commercial workshops agreed",
        4,
        5,
    ),
    # 5 → 6 Preferred → Contracting
    Qualifier(
        "redlining_received",
        "Prospect has provided full set of red-lining",
        "",
        5,
        6,
    ),
    # 6 → 7/8 Contracting → Opt-out / Won
    Qualifier(
        "contract_aligned",
        "Contract Fully Aligned (legal review + first redline returned)",
        "",
        6,
        8,
    ),
    Qualifier("final_price", "Final price agreed", "", 6, 8),
    Qualifier(
        "terms_implementation",
        "Terms and Implementation Defined",
        "Responsibilities outlined",
        6,
        8,
    ),
)


_STAGES = (
    Stage(
        1,
        "Prospecting",
        "Passive stage; BDRs work highest-engagement leads",
        typical_role="BDR",
        exit_qualifier_ids=("engagement_init", "interest_assessment"),
    ),
    Stage(
        2,
        "Discovery",
        "Prospect active; BDR/Sales meetings; price guidance given while scoping",
        typical_role="BDR + Sales",
        exit_qualifier_ids=(
            "relationship_in_person",
            "compelling_event",
            "paic_assessment",
            "decision_makers",
            "tom_scope",
            "price_guidance",
            "technical_validation",
            "on_long_list",
        ),
    ),
    Stage(
        3,
        "Engagement",
        "Sales Manager driving; due diligence continues; PAIC assessment, decision-makers identified, competitive position established",
        typical_role="Sales Manager",
        exit_qualifier_ids=(
            "tas_completed",
            "decision_criteria",
            "buying_roles_mapped",
            "initial_quote",
            "rfp_completed",
            "on_short_list",
            "competitive_position",
        ),
    ),
    Stage(
        4,
        "Shortlisted",
        "Close plan validated with prospect; scope finalized for commercial negotiation; still in competition",
        typical_role="Sales Manager + PS input",
        exit_qualifier_ids=(
            "specs_received",
            "final_scope",
            "competitive_advantage",
            "preferred_status",
            "close_plan",
        ),
    ),
    Stage(
        5,
        "Preferred",
        "Named preferred; no longer in competition; exit when full red-lining received",
        typical_role="Sales Manager",
        exit_qualifier_ids=("redlining_received",),
    ),
    Stage(
        6,
        "Contracting",
        "Finalize legal review + price; agree terms + implementation",
        typical_role="Sales + Legal + PS",
        exit_qualifier_ids=("contract_aligned", "final_price", "terms_implementation"),
    ),
    Stage(
        7,
        "Opt-out",
        "Won but with opt-out clause active; held in stage until clause expires",
        typical_role="Sales (post-Won)",
        exit_qualifier_ids=(),
    ),
    Stage(
        8,
        "Won",
        "Contract signed; INSfile generated; handover; transition to delivery / SaaS / CSM teams",
        typical_role="CSM + Delivery",
        exit_qualifier_ids=(),
    ),
)


_GATES = (
    GovernanceGate(
        "Commercial Approval",
        "LAND = ALL deals; AER >€500k for others",
        when_stages=(3, 4),
        purpose="Go/No-Go on whether SimCorp engages; cost/resource assessment",
    ),
    GovernanceGate(
        "Margin Review",
        "Each iteration of scope, discount, payment schedule",
        when_stages=(4, 5, 6),
        purpose="Before any price proposal to customer",
    ),
    GovernanceGate(
        "Deal Services Design",
        "Early stage",
        when_stages=(3, 4),
        purpose="Implementation costs, risks, timelines",
    ),
    GovernanceGate(
        "Deal Review",
        "Final",
        when_stages=(5, 6),
        purpose="Final review before final contracting",
    ),
    GovernanceGate(
        "Due Diligence",
        "All services + contractual",
        when_stages=(1, 2, 3, 4, 5, 6, 7, 8),
        purpose="Continuous",
    ),
)


_MOTIONS = (
    Motion(
        "LAND",
        "New business",
        applicable_stages=(1, 2, 3, 4, 5, 6, 7, 8),
        revenue_field="APTS_Opportunity_ARR__c",
        process_notes="Full 8-stage process applies; Commercial Approval mandatory for ALL Land deals",
    ),
    Motion(
        "EXPAND",
        "Existing customer growth",
        applicable_stages=(1, 2, 3, 4, 5, 6, 7, 8),
        revenue_field="APTS_Opportunity_ARR__c",
        process_notes='Same 8 stages but steps "may vary"; Commercial Approval triggers at AER >€500k',
    ),
    Motion(
        "RENEWAL",
        "Re-up of existing contract",
        applicable_stages=(1, 2, 3, 4, 5, 6),
        revenue_field="APTS_Renewal_ACV__c",
        process_notes="Different motion entirely; simpler workflow; field reported as ACV not ARR",
    ),
)


_METRICS = (
    Metric(
        name="open_pipeline_arr",
        type="raw",
        formula="SUM(convertCurrency(APTS_Opportunity_ARR__c)) WHERE IsClosed=false AND Type IN ('Land','Expand')",
        captures="FX-correct open Land+Expand pipeline ARR in EUR",
        does_not_capture="Renewal pipeline (use renewal_acv); closed-won bookings (use booked_arr)",
        how_to_read="Headline pipeline number for LAND deck Pipeline_Total slide. Always FX-converted via per-record convertCurrency (raw SUM is forbidden by the cardinal SimCorp multi-currency rule).",
    ),
    Metric(
        name="renewal_acv",
        type="raw",
        formula="SUM(convertCurrency(APTS_Renewal_ACV__c)) WHERE IsClosed=false AND Type='Renewal'",
        captures="FX-correct open Renewal pipeline ACV in EUR",
        does_not_capture="Auto-renewals that never become Renewal-typed opps; expansion-on-existing-account uplift",
        how_to_read="Companion to open_pipeline_arr — never blend the two. Use ACV not ARR for renewals per the cardinal SimCorp rule.",
    ),
    Metric(
        name="grr_proxy",
        type="proxy",
        formula="(won Renewal ACV last 12mo) / (won + lost Renewal ACV last 12mo)",
        captures="At-risk renewal save rate — when a renewal becomes a tracked opp, what fraction is won",
        does_not_capture="Auto-renewals (likely majority of true renewal volume); expansion uplift (NRR territory)",
        how_to_read="Directional indicator only, not the org's true GRR. Typical enterprise SaaS GRR is 90%+; this proxy appears lower because the denominator is biased toward at-risk situations.",
        deferred_replacement="True GRR via cohort math against historical Pipeline_Snapshot__c records — needs 12+ months of snapshot history accumulated.",
    ),
    Metric(
        name="weighted_forecast",
        type="derived",
        formula="SUM(open_arr_at_stage_N × backtest_forward_rate_for_stage_N) for each stage",
        captures="Probability-weighted forecast applying empirical population-level forward rates",
        does_not_capture="Director-specific stage-progression rates (the rates are org-wide); deal-specific risk factors",
        how_to_read="Use as an empirical sanity check vs the rep's commit forecast — large gaps either way warrant a 1:1.",
    ),
    Metric(
        name="late_stage_concentration",
        type="derived",
        formula="(open_arr_at_stage_5 + open_arr_at_stage_6) / open_pipeline_arr × 100",
        captures="% of pipeline ARR sitting in 'closeable' stages",
        does_not_capture="Quality of those late-stage opps (a deal stuck 90 days in Stage 5 = same weight as a fresh arrival)",
        how_to_read="< 30% = quarter coverage at risk; > 70% = strong near-term close potential. Empirical thresholds.",
    ),
    Metric(
        name="zombie_arr",
        type="raw",
        formula="SUM(convertCurrency(APTS_Opportunity_ARR__c)) WHERE Type IN ('Land','Expand') AND CreatedDate <= LAST_N_DAYS:730 AND no Task/Event activity in last 60d",
        captures="Stale L+E pipeline ARR that's neither closing nor being worked",
        does_not_capture="Whether the opp is intentionally paused (e.g., customer in M&A integration)",
        how_to_read="> EUR 1M trips MEDIUM action; > EUR 5M trips HIGH. Top-owner exposure called out in suggested_action.",
    ),
    Metric(
        name="approval_gap_arr",
        type="raw",
        formula="SUM(convertCurrency(APTS_Opportunity_ARR__c)) WHERE Type IN ('Land','Expand') AND APTS_Opportunity_ARR__c >= 500000 AND StageName IN ('3','4','5','6') AND Stage_20_Approval__c IN (false,null)",
        captures="ARR exposure on policy violations under the SimCorp Commercial Approval gate",
        does_not_capture="Whether the missing flag is data-entry lag vs. real policy violation",
        how_to_read="Per the handbook: Commercial Approval is mandatory for ALL Land deals + AER >€500k Expand. Any matching opp without the flag must be reviewed.",
    ),
    Metric(
        name="simcorp_one_attach_rate",
        type="derived",
        formula="(opps with 'Standard Platform' line item) / (total open Land+Expand opps in scope) × 100",
        captures="How often the SimCorp One platform anchor is in the deal vs. modules-only opps",
        does_not_capture="Whether modules-only opps are intentional (e.g., SP customer adding modules) vs. missed platform-led opportunity",
        how_to_read="< 30% = thin platform anchor; review platform-led selling motion. Strategic signal.",
    ),
    Metric(
        name="coverage_gap_count",
        type="derived",
        formula="COUNT(Tier-1 accounts in scope NOT IN (accounts with open Land/Expand opp created last 90d))",
        captures="Tier-1 accounts with stalled new-business pipeline-creation activity",
        does_not_capture="Renewal-only customers (they don't need Land/Expand pipeline to be 'covered')",
        how_to_read="≥ 5 starved Tier-1 accounts trips MEDIUM. UKI typically runs 100+ — that's a real territory pattern, not a quirk.",
    ),
    Metric(
        name="activity_drought_count",
        type="derived",
        formula="COUNT(open L+E opps WHERE CloseDate=THIS_QUARTER AND no Task/Event activity in last 30d)",
        captures="Forecast-credibility signal for current-quarter-closing deals",
        does_not_capture="Renewal opps (the field zeros for Renewals; would need a separate Renewal-side rule)",
        how_to_read="≥ 5 opps trips MEDIUM. Shorter window than zombie (30d vs 60d) to surface near-term forecast risk.",
    ),
)


_RULES = (
    Rule(
        rule_id="zombie_arr",
        title="Zombie ARR exposure",
        threshold_summary="open L+E opps > 730d old AND no activity 60d, sum > EUR 1M (MED) / EUR 5M (HIGH)",
        priority="medium",
        applies_at_stages=(1, 2, 3, 4, 5),
        related_gates=(),
        metrics_used=("zombie_arr",),
        suggested_action="Review zombie deals 1:1 with each rep; decide close/disqualify by EOM. Top owner exposure named.",
    ),
    Rule(
        rule_id="coverage_gap",
        title="Coverage Gap on Tier-1 accounts",
        threshold_summary="Tier-1 accounts with no open L+E opp 90d, count ≥ 5",
        priority="medium",
        applies_at_stages=(1, 2),  # gap is at the lead-creation stage
        related_gates=(),
        metrics_used=("coverage_gap_count",),
        suggested_action="Run an account-coverage review with reps; assign opener responsibility for each starved Tier-1.",
    ),
    Rule(
        rule_id="approval_gap",
        title="Stage 3+ deals missing Commercial Approval",
        threshold_summary="Stage 3+ L+E opps ≥ EUR 500k where Stage_20_Approval__c IN (false, null), count > 0",
        priority="high",
        applies_at_stages=(3, 4, 5, 6),
        related_gates=("Commercial Approval",),
        metrics_used=("approval_gap_arr",),
        suggested_action="Submit each opp for Commercial Approval before EOM. Mandatory for ALL Land deals per the 8-stage process.",
    ),
    Rule(
        rule_id="simcorp_one_attach_low",
        title="Thin SimCorp One platform attach rate",
        threshold_summary="< 30% of open L+E opps attach Standard Platform AND total ≥ 5",
        priority="medium",
        applies_at_stages=(2, 3, 4),
        related_gates=(),
        metrics_used=("simcorp_one_attach_rate",),
        suggested_action="Review platform-led selling motion with reps; identify 5-10 module-only opps where Standard Platform should be added before next stage gate.",
    ),
    Rule(
        rule_id="late_stage_concentration",
        title="Late-stage concentration at risk",
        threshold_summary="(stage 5+6 ARR) / total open L+E ARR < 30%",
        priority="medium",
        applies_at_stages=(3, 4),  # remediation happens by progressing 3→4 deals
        related_gates=(),
        metrics_used=("late_stage_concentration",),
        suggested_action="Schedule Stage 3 → 4 progression workshops with each rep; identify the 3-5 deals most likely to advance.",
    ),
    Rule(
        rule_id="activity_drought",
        title="Activity drought on current-quarter pipeline",
        threshold_summary="this-Q closing L+E opps with no activity 30d, count ≥ 5",
        priority="medium",
        applies_at_stages=(2, 3, 4, 5, 6),
        related_gates=(),
        metrics_used=("activity_drought_count",),
        suggested_action="Reset 14-day activity SLA with reps; require one logged Task/Event per opp every 14 days.",
    ),
    Rule(
        rule_id="renewal_thin",
        title="Renewal pipeline thin",
        threshold_summary="total open renewal ACV < EUR 100K",
        priority="low",
        applies_at_stages=(1, 2, 3, 4, 5, 6),
        related_gates=(),
        metrics_used=("renewal_acv",),
        suggested_action="Verify renewal-eligible accounts are surfaced. CSM team to validate cohort coverage with the data team.",
    ),
    Rule(
        rule_id="slippage",
        title="Forecast credibility — repeated CloseDate pushes",
        threshold_summary="≥ 3 CFQ-closing L+E opps pushed ≥ 1 time in last 90d (rule deferred — needs OFH wiring)",
        priority="medium",
        applies_at_stages=(4, 5, 6),
        related_gates=(),
        metrics_used=(),  # would add 'slippage_count' once shipped
        suggested_action="Pull OpportunityFieldHistory for CloseDate changes; 1:1 with reps on slipped deals; reset close-date discipline.",
    ),
)


GRAPH = ProcessGraph(
    stages=_STAGES,
    gates=_GATES,
    motions=_MOTIONS,
    metrics=_METRICS,
    rules=_RULES,
    qualifiers=_QUALIFIERS,
)


# ──────────────────────────────────────────────────────────────────────────
# Query helpers — deterministic graph queries from anywhere
# ──────────────────────────────────────────────────────────────────────────


def stage(number: int) -> Stage:
    """Look up a stage by 1-8 number. Raises if not found."""
    return next(s for s in GRAPH.stages if s.number == number)


def gate(name: str) -> GovernanceGate:
    return next(g for g in GRAPH.gates if g.name == name)


def motion(name: str) -> Motion:
    return next(m for m in GRAPH.motions if m.name == name)


def metric(name: str) -> Metric:
    return next(m for m in GRAPH.metrics if m.name == name)


def rule(rule_id: str) -> Rule:
    return next(r for r in GRAPH.rules if r.rule_id == rule_id)


def gates_at_stage(stage_number: int) -> tuple[GovernanceGate, ...]:
    """Return all governance gates that apply at a given stage."""
    return tuple(g for g in GRAPH.gates if stage_number in g.when_stages)


def rules_at_stage(stage_number: int) -> tuple[Rule, ...]:
    return tuple(r for r in GRAPH.rules if stage_number in r.applies_at_stages)


def qualifiers_for_stage_exit(from_stage: int) -> tuple[Qualifier, ...]:
    return tuple(q for q in GRAPH.qualifiers if q.from_stage == from_stage)


def proxy_metrics() -> tuple[Metric, ...]:
    """Metrics flagged as 'proxy' — these need caveat language wherever surfaced."""
    return tuple(m for m in GRAPH.metrics if m.type == "proxy")


# ──────────────────────────────────────────────────────────────────────────
# Serialization — for LLM prompt context + JSON dumps
# ──────────────────────────────────────────────────────────────────────────


def to_json() -> dict:
    """Serialize the whole graph to a plain dict (JSON-safe). Useful for
    cache files, REST payloads, deck-agent input augmentation."""
    return {
        "schema_version": SCHEMA_VERSION,
        "stages": [s.__dict__ for s in GRAPH.stages],
        "gates": [g.__dict__ for g in GRAPH.gates],
        "motions": [m.__dict__ for m in GRAPH.motions],
        "metrics": [m.__dict__ for m in GRAPH.metrics],
        "rules": [r.__dict__ for r in GRAPH.rules],
        "qualifiers": [q.__dict__ for q in GRAPH.qualifiers],
    }


def to_llm_context() -> str:
    """Compact markdown summary for LLM prompt inclusion (~3KB).

    Use case: drop into a Claude / GPT system prompt so the LLM has the
    canonical SimCorp process model in context without us hand-curating
    the prompt block. Update the graph -> all consumers see the change.
    """
    lines: list[str] = [
        f"# SimCorp Sales Process — canonical model (schema v{SCHEMA_VERSION})",
        "",
        f"Source: {HANDBOOK_SOURCE}",
        "",
        "## 8 stages",
        "",
    ]
    for s in GRAPH.stages:
        lines.append(f"  {s.number}. {s.name} — {s.description}")
    lines += ["", "## 5 governance gates (deal reviews)", ""]
    for g in GRAPH.gates:
        stages_str = ",".join(str(n) for n in g.when_stages)
        lines.append(f"  - {g.name}  (Stages {stages_str}) — {g.purpose}")
    lines += ["", "## 3 motions", ""]
    for m in GRAPH.motions:
        lines.append(
            f"  - {m.name}: {m.description}. Reports via {m.revenue_field}. {m.process_notes}"
        )
    lines += ["", "## Action-item rules", ""]
    for r in GRAPH.rules:
        gates = (" Gates: " + ", ".join(r.related_gates)) if r.related_gates else ""
        lines.append(
            f"  - {r.rule_id} ({r.priority.upper()}): {r.title} — {r.threshold_summary}.{gates}"
        )
    lines += ["", "## Metric caveats — proxy / derived", ""]
    for m in proxy_metrics():
        lines.append(f"  - {m.name} (PROXY): {m.formula}. Caveat: {m.does_not_capture}")
    lines += [
        "",
        "Never blend ARR and ACV. Always FX-convert at the per-record level.",
        "When the LLM cites any of the above, use the EXACT names — no paraphrasing.",
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    # Smoke test: print the LLM context + a sample query
    print(to_llm_context())
    print()
    print("=== Sample queries ===")
    print(f"Gates at stage 3: {[g.name for g in gates_at_stage(3)]}")
    print(f"Rules at stage 4: {[r.rule_id for r in rules_at_stage(4)]}")
    print(f"Proxy metrics: {[m.name for m in proxy_metrics()]}")
    print(f"\nJSON schema_version: {to_json()['schema_version']}")
    print(f"JSON size: {len(json.dumps(to_json())):,} chars")
