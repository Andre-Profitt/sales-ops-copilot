"""Workforce (RW/AP) target-KPI knowledge graph.

Single source of truth for what each AP/RW workforce metric means, where
it lives in the DuckDB store, what to read it as, and what NOT to do
with it. Mirrors the KG-as-code shape used by sales_process_graph.py
(sales motion) and tc_kg.py (Think-Cell) — typed dataclasses + an
aggregator + helpers + to_llm_context() for prompt injection.

Source of truth (verbatim ingest target):
  ~/code/apps/sales-ops-copilot/docs/workforce/KPI_DEFINITIONS.md

Source DuckDB store (Phase 1 static pack thru 2025-12-15):
  ~/code/apps/sales-ops-copilot/workforce/state/wf.duckdb

Cross-project consumers (current and intended):
  - scripts/workforce/wf.py        (read-only CLI; descriptive output only)
  - scripts/brief.py               (daily-brief workforce section, future)
  - LLM prompts                    via to_llm_context()
  - downstream agents              importing GRAPH.kpis directly

Track lane: track:workforce. Stays out of cockpit / sf-audit per
docs/AGENT_COORDINATION.md.

Versioning:
  SCHEMA_VERSION 1 (2026-05-07). Bump when entity shapes change in a
  way that breaks downstream consumers.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Literal

SCHEMA_VERSION = 2  # v2 (2026-05-07): SPOF severity tiers + empirical caveats from wf_analysis.py

KPI_DEFS_SOURCE = "~/code/apps/sales-ops-copilot/docs/workforce/KPI_DEFINITIONS.md"
DUCKDB_SOURCE = "~/code/apps/sales-ops-copilot/workforce/state/wf.duckdb"


# ──────────────────────────────────────────────────────────────────────────
# Entity dataclasses
# ──────────────────────────────────────────────────────────────────────────


KPIType = Literal["raw", "derived", "proxy", "label"]
KPIFamily = Literal["effort", "person", "concentration", "anomaly", "forecast"]


@dataclass(frozen=True)
class WorkforceKPI:
    """A workforce target metric. type='raw' = direct event aggregate;
    'derived' = formula on raw inputs; 'proxy' = stand-in for a metric we
    can't compute (e.g. KYC effort with no time-tracking); 'label' =
    descriptive string column attached to a metric row, not a number."""

    kpi_id: str
    name: str
    type: KPIType
    family: KPIFamily
    formula: str
    source_table: str
    source_columns: tuple[str, ...]
    captures: str
    does_not_capture: str
    how_to_read: str
    caveats: tuple[str, ...] = ()
    related_kpi_ids: tuple[str, ...] = ()
    deferred_replacement: str | None = None  # for type='proxy' only


@dataclass(frozen=True)
class EffortWeight:
    """Weight applied per process family to convert raw event counts into
    effort_units. Lives in dim_process; replicated here so the KG is
    self-describing without a DuckDB connection."""

    process_family: str
    weight: float
    rationale: str


@dataclass(frozen=True)
class Threshold:
    """Load-state cutoff. The KG owns the semantic mapping from a metric
    value to a categorical label (OVERLOADED / SPOF / SIGNIFICANT_ANOMALY).
    wf.py and brief.py read these instead of hard-coding."""

    threshold_id: str
    metric_kpi_id: str
    op: Literal[">", "<", ">=", "<=", "=="]
    value: float
    label: str
    severity: Literal["info", "watch", "high"]
    rationale: str


@dataclass(frozen=True)
class Constraint:
    """Compliance / data-integrity rule. Documents what consumers MUST NOT
    compute or assume. Surfaced via to_llm_context() so any LLM prompt
    inheriting this graph also inherits the prohibitions."""

    constraint_id: str
    rule: str
    source: str  # citation (e.g. 'AI Code of Conduct §8')
    kind: Literal["compliance", "data_integrity", "scope"]


@dataclass(frozen=True)
class WorkforceKPIGraph:
    """Aggregate of the 4 entity collections."""

    kpis: tuple[WorkforceKPI, ...]
    effort_weights: tuple[EffortWeight, ...]
    thresholds: tuple[Threshold, ...]
    constraints: tuple[Constraint, ...]


# ──────────────────────────────────────────────────────────────────────────
# Graph data — verbatim ingest of KPI_DEFINITIONS.md (2026-05-07)
# ──────────────────────────────────────────────────────────────────────────


_EFFORT_WEIGHTS = (
    EffortWeight("Opportunities", 1.0, "Baseline"),
    EffortWeight("Quotes & Proposals", 2.0, "More work per event than an Opp update"),
    EffortWeight(
        "KYC",
        3.0,
        "Highest-friction process; snapshot-only data so this is a proxy",
    ),
    EffortWeight("Activities", 0.5, "Lowest-effort-per-event (calls/emails/meetings)"),
)


_KPIS = (
    # ── effort family ────────────────────────────────────────────────────
    WorkforceKPI(
        kpi_id="effort_units",
        name="effort_units",
        type="derived",
        family="effort",
        formula="sum(event × dim_process.weight) over person × week",
        source_table="weekly_person_kpis",
        source_columns=("effort_units",),
        captures="Weighted workload — accounts for process-family friction",
        does_not_capture="Actual time spent (no clock data exists)",
        how_to_read="Headline workload number. Sum across team for capacity totals.",
        caveats=("Weights are rationale-based, not time-calibrated.",),
        related_kpi_ids=("effort_adj", "actions"),
    ),
    WorkforceKPI(
        kpi_id="effort_adj",
        name="effort_adj",
        type="derived",
        family="effort",
        formula="effort_units excluding leave weeks (availability_factor=0)",
        source_table="weekly_person_kpis",
        source_columns=("effort_adj",),
        captures="Effort normalized for leave — fair cross-person comparison",
        does_not_capture="Partial-week leave (treated as full-week if availability_factor=0)",
        how_to_read="Use this, not effort_units, when comparing reps with different leave patterns.",
        related_kpi_ids=("effort_units", "availability_factor"),
    ),
    # ── person family ────────────────────────────────────────────────────
    WorkforceKPI(
        kpi_id="actions",
        name="actions",
        type="raw",
        family="person",
        formula="count(events) over person × week",
        source_table="weekly_person_kpis",
        source_columns=("actions",),
        captures="Raw event volume",
        does_not_capture="Process-family weight (each event counted equally)",
        how_to_read="Volume signal. Pair with effort_units for weighted view.",
        related_kpi_ids=("actions_adj", "effort_units"),
    ),
    WorkforceKPI(
        kpi_id="actions_adj",
        name="actions_adj",
        type="derived",
        family="person",
        formula="actions excluding leave weeks",
        source_table="weekly_person_kpis",
        source_columns=("actions_adj",),
        captures="Action volume normalized for leave",
        does_not_capture="Partial-week leave",
        how_to_read="Cross-person volume comparison.",
        related_kpi_ids=("actions", "availability_factor"),
    ),
    WorkforceKPI(
        kpi_id="availability_factor",
        name="availability_factor",
        type="derived",
        family="person",
        formula="available_days / 7 (capped 0.0–1.0)",
        source_table="weekly_person_kpis",
        source_columns=("availability_factor", "available_days", "leave_days"),
        captures="Fraction of week the person was working",
        does_not_capture="Half-day leave granularity (whole-day events only in dim_leave)",
        how_to_read="1.0 = full week available; 0.0 = full leave week.",
        related_kpi_ids=("available_days", "leave_days"),
    ),
    WorkforceKPI(
        kpi_id="available_days",
        name="available_days",
        type="raw",
        family="person",
        formula="7 - leave_days for the week",
        source_table="weekly_person_kpis",
        source_columns=("available_days",),
        captures="Working-day count for the week",
        does_not_capture="Weekends explicitly (treated as work-eligible)",
        how_to_read="Component of availability_factor.",
        related_kpi_ids=("availability_factor", "leave_days"),
    ),
    WorkforceKPI(
        kpi_id="leave_days",
        name="leave_days",
        type="raw",
        family="person",
        formula="dim_leave events overlapping week boundaries",
        source_table="weekly_person_kpis",
        source_columns=("leave_days",),
        captures="Leave-day count for the week",
        does_not_capture="Leave reason / type (only count is exposed)",
        how_to_read="Component of availability_factor.",
        related_kpi_ids=("availability_factor", "available_days"),
    ),
    WorkforceKPI(
        kpi_id="utilization_index_p75",
        name="utilization_index_p75",
        type="derived",
        family="person",
        formula="actions / team_p75_actions_per_available_week",
        source_table="weekly_person_kpis",
        source_columns=("utilization_index_p75",),
        captures="Workload pace relative to team's 75th percentile",
        does_not_capture="Quality / outcome of work — pure volume index",
        how_to_read="1.0 = at team P75 pace. >1.5 → OVERLOADED. <0.5 → UNDERLOADED.",
        caveats=("Compares against same-team P75; cross-team comparisons not meaningful.",),
        related_kpi_ids=("utilization_p75_4w_avg", "actions"),
    ),
    WorkforceKPI(
        kpi_id="utilization_p75_4w_avg",
        name="utilization_p75_4w_avg",
        type="derived",
        family="person",
        formula="rolling_mean(utilization_index_p75, 4)",
        source_table="weekly_person_kpis",
        source_columns=("utilization_p75_4w_avg",),
        captures="Smoothed utilization — filters single-week noise",
        does_not_capture="Sub-week swings; week-1/2 of new hires (not enough history)",
        how_to_read="Use this for trend judgment; use raw util_p75 for current-week alerting.",
        related_kpi_ids=("utilization_index_p75",),
    ),
    # ── concentration family ────────────────────────────────────────────
    WorkforceKPI(
        kpi_id="total_effort",
        name="total_effort",
        type="derived",
        family="concentration",
        formula="sum(effort_units) over segment × process_family",
        source_table="coverage_concentration",
        source_columns=("total_effort",),
        captures="Aggregate workload for a segment-process slice",
        does_not_capture="Distribution shape (use effective_contributors / top1_share)",
        how_to_read="Denominator for top1_share. Contextualizes concentration risk.",
        related_kpi_ids=("effective_contributors", "top1_share"),
    ),
    WorkforceKPI(
        kpi_id="effective_contributors",
        name="effective_contributors",
        type="derived",
        family="concentration",
        formula="Herfindahl-style: 1 / sum(person_share^2)",
        source_table="coverage_concentration",
        source_columns=("effective_contributors",),
        captures="Count of 'real' contributors after effort weighting",
        does_not_capture="Identity of contributors (use top1_person_name for that)",
        how_to_read="Lower = more concentrated. <1.5 effectively single-source.",
        caveats=("Inverse-square weighting is sensitive to long tails.",),
        related_kpi_ids=("total_effort", "top1_share"),
    ),
    WorkforceKPI(
        kpi_id="top1_share",
        name="top1_share",
        type="derived",
        family="concentration",
        formula="biggest_contributor_effort / total_effort",
        source_table="coverage_concentration",
        source_columns=("top1_share",),
        captures="Single-point-of-failure risk for a segment-process slice",
        does_not_capture="What happens when top1 leaves (no causal model)",
        how_to_read=">0.5 → SPOF. >0.9 → critical SPOF. Pair with top1_person_name.",
        caveats=(
            "Point-estimate alone is fragile on slices with few contributors. Use bootstrap 90% CI (notebooks/wf_analysis.py §3): SPOF claim is robust only when the lower CI bound is also >0.5.",
            "Empirical (2025-12-15 backtest): 12 slices tripped the point threshold; 9 robust (CI lower >0.5), 3 point-only. Map to threshold concentration_spof_robust vs concentration_spof_point.",
        ),
        related_kpi_ids=("total_effort", "effective_contributors", "top1_person_name"),
    ),
    WorkforceKPI(
        kpi_id="top1_person_name",
        name="top1_person_name",
        type="label",
        family="concentration",
        formula="argmax(person_effort) over segment × process_family",
        source_table="coverage_concentration",
        source_columns=("top1_person_name",),
        captures="Identity of the top contributor",
        does_not_capture="Performance judgment — descriptive only",
        how_to_read="Read alongside top1_share. Treat as informational, not evaluative.",
        caveats=("Per AI Code of Conduct §8: do not feed this into a per-rep AI inference.",),
        related_kpi_ids=("top1_share",),
    ),
    # ── anomaly family ───────────────────────────────────────────────────
    WorkforceKPI(
        kpi_id="z_score",
        name="z_score",
        type="derived",
        family="anomaly",
        formula="(effort - effort_roll8) / stddev(rolling_8wk)",
        source_table="anomalies_log",
        source_columns=("z_score",),
        captures="Standardized deviation of weekly effort vs 8-wk baseline",
        does_not_capture="Cause of anomaly (spike vs drop is sign-of-z; root cause unknown)",
        how_to_read="|z| > 2 = significant. Positive = spike, negative = drop.",
        related_kpi_ids=("effort_roll8",),
    ),
    WorkforceKPI(
        kpi_id="effort_roll8",
        name="effort_roll8",
        type="derived",
        family="anomaly",
        formula="rolling_mean(effort, 8)",
        source_table="anomalies_log",
        source_columns=("effort_roll8",),
        captures="8-week rolling baseline of weekly effort",
        does_not_capture="Seasonality (no decomposition; raw rolling mean)",
        how_to_read="Denominator for z_score. Treat as expected level, not target.",
        related_kpi_ids=("z_score",),
    ),
    # ── forecast family ──────────────────────────────────────────────────
    WorkforceKPI(
        kpi_id="forecast_p50",
        name="p50",
        type="derived",
        family="forecast",
        formula="median forward-looking team capacity per process_family",
        source_table="forecast_output",
        source_columns=("p50",),
        captures="Most-likely future capacity",
        does_not_capture="Per-individual prediction (forecast is process-family only)",
        how_to_read="Compare to next-quarter commit to detect capacity gaps.",
        caveats=("Per AI Code §8: do NOT extrapolate to per-rep predictions.",),
        related_kpi_ids=("forecast_p10", "forecast_p90"),
    ),
    WorkforceKPI(
        kpi_id="forecast_p10",
        name="p10",
        type="derived",
        family="forecast",
        formula="10th-percentile forward-looking capacity (pessimistic)",
        source_table="forecast_output",
        source_columns=("p10",),
        captures="Conservative capacity floor",
        does_not_capture="Tail-risk events outside training distribution",
        how_to_read="Use for capacity-shortfall risk planning.",
        related_kpi_ids=("forecast_p50", "forecast_p90"),
    ),
    WorkforceKPI(
        kpi_id="forecast_p90",
        name="p90",
        type="derived",
        family="forecast",
        formula="90th-percentile forward-looking capacity (optimistic)",
        source_table="forecast_output",
        source_columns=("p90",),
        captures="Capacity ceiling — best-case headroom",
        does_not_capture="Improvements from headcount changes (model is stationary)",
        how_to_read="Pair with p10 to read confidence interval width.",
        related_kpi_ids=("forecast_p10", "forecast_p50"),
    ),
    WorkforceKPI(
        kpi_id="forecast_mae",
        name="MAE",
        type="derived",
        family="forecast",
        formula="mean(|actual - p50|) over backtest holdout",
        source_table="forecast_backtest_metrics",
        source_columns=("mae",),
        captures="Average absolute forecast error in raw units",
        does_not_capture="Bias direction (use bias for that)",
        how_to_read="Lower is better. Same units as effort_units.",
        related_kpi_ids=("forecast_mape", "forecast_bias", "forecast_rmse"),
    ),
    WorkforceKPI(
        kpi_id="forecast_mape",
        name="MAPE",
        type="derived",
        family="forecast",
        formula="mean(|actual - p50| / actual) over backtest holdout",
        source_table="forecast_backtest_metrics",
        source_columns=("mape",),
        captures="Scale-free forecast error",
        does_not_capture="Behaves badly when actuals approach zero",
        how_to_read="<0.10 = strong; 0.10–0.25 = usable; >0.25 = unreliable.",
        caveats=(
            "Empirical (2025-12-15 backtest, notebooks/wf_analysis.py §2): 17 of 20 process-family rows have MAPE>0.25. Forecast usable for trend, not commit-grade. Don't anchor next-quarter capacity decisions on per-family p50 without checking this caveat first.",
        ),
        related_kpi_ids=("forecast_mae",),
    ),
    WorkforceKPI(
        kpi_id="forecast_rmse",
        name="RMSE",
        type="derived",
        family="forecast",
        formula="sqrt(mean((actual - p50)^2)) over backtest holdout",
        source_table="forecast_backtest_metrics",
        source_columns=("rmse",),
        captures="Forecast error penalizing big misses",
        does_not_capture="Sign of error",
        how_to_read="Compare to MAE: large gap = heavy-tailed errors.",
        related_kpi_ids=("forecast_mae",),
    ),
    WorkforceKPI(
        kpi_id="forecast_bias",
        name="Bias",
        type="derived",
        family="forecast",
        formula="mean(actual - p50) over backtest holdout",
        source_table="forecast_backtest_metrics",
        source_columns=("bias",),
        captures="Systematic over/under-prediction direction",
        does_not_capture="Magnitude of typical errors (use MAE)",
        how_to_read="Near 0 = unbiased. Positive = model under-forecasts.",
        related_kpi_ids=("forecast_mae",),
    ),
    WorkforceKPI(
        kpi_id="forecast_p10_p90_coverage",
        name="P10_P90_Coverage",
        type="derived",
        family="forecast",
        formula="fraction of holdout actuals within [p10, p90]",
        source_table="forecast_backtest_metrics",
        source_columns=("p10_p90_coverage",),
        captures="Calibration of the forecast confidence band",
        does_not_capture="Conditional calibration (only marginal)",
        how_to_read="Target ≈ 0.80 by construction. <0.65 = under-confident bands.",
        related_kpi_ids=("forecast_p10", "forecast_p90"),
    ),
)


_THRESHOLDS = (
    Threshold(
        "load_overloaded",
        "utilization_index_p75",
        ">",
        1.5,
        "OVERLOADED",
        "watch",
        "Running >150% of team P75 pace; multi-week persistence is the alert signal.",
    ),
    Threshold(
        "load_underloaded",
        "utilization_index_p75",
        "<",
        0.5,
        "UNDERLOADED",
        "info",
        "Running <50% of team P75 pace; investigate availability before action.",
    ),
    Threshold(
        "concentration_spof_point",
        "top1_share",
        ">",
        0.5,
        "POINT_SPOF",
        "watch",
        "Point estimate trips SPOF. Treat as candidate; verify with bootstrap CI before declaring load-bearing.",
    ),
    Threshold(
        "concentration_spof_robust",
        "top1_share_ci_lower_5pct",
        ">",
        0.5,
        "ROBUST_SPOF",
        "high",
        "Both point estimate AND bootstrap 90% CI lower bound exceed 0.5. Document succession plan; treat as load-bearing risk. Computed in notebooks/wf_analysis.py §3.",
    ),
    Threshold(
        "anomaly_significant",
        "z_score",
        ">",
        2.0,
        "SIGNIFICANT_ANOMALY",
        "watch",
        "Weekly effort >2σ off the 8-week rolling baseline; spike vs drop is sign-of-z.",
    ),
    Threshold(
        "forecast_mape_unreliable",
        "forecast_mape",
        ">",
        0.25,
        "FORECAST_UNRELIABLE",
        "watch",
        "Backtest MAPE >25% — don't anchor capacity decisions on this family's forecast.",
    ),
)


_CONSTRAINTS = (
    Constraint(
        "no_per_rep_ai_inference",
        "Do not use AI to draw evaluative or prescriptive conclusions about a named individual from these KPIs.",
        "AI Code of Conduct §8 (no people-related decision-making by AI)",
        "compliance",
    ),
    Constraint(
        "no_future_per_rep_prediction",
        "Do not predict future per-individual performance. Forecast is at process-family granularity only.",
        "AI Code of Conduct §8",
        "compliance",
    ),
    Constraint(
        "no_hire_fire_promote",
        "Do not generate 'recommend firing X' or 'recommend promoting Y' outputs.",
        "AI Code of Conduct §8 + COMPLIANCE.md",
        "compliance",
    ),
    Constraint(
        "no_external_benchmarks",
        "Do not compare these KPIs to non-SimCorp benchmarks — there are no benchmark data in scope.",
        "KPI_DEFINITIONS.md §What NOT to compute",
        "scope",
    ),
    Constraint(
        "roster_inferred",
        "dim_people roster is inferred from quote editors + manual additions, NOT authoritative. Replace with Workday dim_people once CA-block is resolved.",
        "KPI_DEFINITIONS.md §Caveats #1",
        "data_integrity",
    ),
    Constraint(
        "kyc_snapshot_only",
        "KYC effort and cycle-time are PROXIES. KYC export is one row per account with last-modified date — no per-event log.",
        "KPI_DEFINITIONS.md §Caveats #2",
        "data_integrity",
    ),
    Constraint(
        "axioma_quote_id_missing",
        "Axioma quotes have no quote_id; record_id is approximated as 'AXQ|<oppId>'. Do not join to quote-level tables expecting a real id.",
        "KPI_DEFINITIONS.md §Caveats #3",
        "data_integrity",
    ),
    Constraint(
        "sales_hierarchy_empty",
        "The sales-hierarchy table is empty in the Phase 1 snapshot. Coverage analysis uses Opportunity Owner / Account Owner only.",
        "KPI_DEFINITIONS.md §Caveats #4",
        "data_integrity",
    ),
    Constraint(
        "data_ends_2025_12_15",
        "Static pack data ends 2025-12-15. Treat KPIs as a frozen snapshot; the gap to today closes when Phase 2 (live SF refresh) ships.",
        "KPI_DEFINITIONS.md §Caveats #5",
        "data_integrity",
    ),
)


GRAPH = WorkforceKPIGraph(
    kpis=_KPIS,
    effort_weights=_EFFORT_WEIGHTS,
    thresholds=_THRESHOLDS,
    constraints=_CONSTRAINTS,
)


# ──────────────────────────────────────────────────────────────────────────
# Helper accessors
# ──────────────────────────────────────────────────────────────────────────


def find_kpi(kpi_id: str) -> WorkforceKPI | None:
    return next((k for k in GRAPH.kpis if k.kpi_id == kpi_id), None)


def kpis_by_family(family: KPIFamily) -> tuple[WorkforceKPI, ...]:
    return tuple(k for k in GRAPH.kpis if k.family == family)


def proxy_kpis() -> tuple[WorkforceKPI, ...]:
    return tuple(k for k in GRAPH.kpis if k.type == "proxy")


def thresholds_for(kpi_id: str) -> tuple[Threshold, ...]:
    return tuple(t for t in GRAPH.thresholds if t.metric_kpi_id == kpi_id)


def compliance_constraints() -> tuple[Constraint, ...]:
    return tuple(c for c in GRAPH.constraints if c.kind == "compliance")


def to_json() -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "source": {"kpi_defs": KPI_DEFS_SOURCE, "duckdb": DUCKDB_SOURCE},
        "kpis": [k.__dict__ for k in GRAPH.kpis],
        "effort_weights": [w.__dict__ for w in GRAPH.effort_weights],
        "thresholds": [t.__dict__ for t in GRAPH.thresholds],
        "constraints": [c.__dict__ for c in GRAPH.constraints],
    }


def to_llm_context() -> str:
    """Compact markdown summary for LLM prompt inclusion (~3KB)."""
    lines: list[str] = [
        f"# SimCorp Workforce (RW/AP) Target KPIs — canonical (schema v{SCHEMA_VERSION})",
        "",
        f"Source: {KPI_DEFS_SOURCE}",
        f"Store:  {DUCKDB_SOURCE}",
        "",
        "## Effort weights (events → effort_units)",
        "",
    ]
    for w in GRAPH.effort_weights:
        lines.append(f"  - {w.process_family}: ×{w.weight} — {w.rationale}")
    lines += ["", "## KPIs by family", ""]
    for fam in ("effort", "person", "concentration", "anomaly", "forecast"):
        lines.append(f"### {fam}")
        for k in kpis_by_family(fam):
            tag = f" [{k.type.upper()}]" if k.type != "raw" else ""
            lines.append(f"  - {k.kpi_id}{tag}: {k.captures}. Read: {k.how_to_read}")
        lines.append("")
    lines += ["## Thresholds", ""]
    for t in GRAPH.thresholds:
        lines.append(
            f"  - {t.metric_kpi_id} {t.op} {t.value} → {t.label} ({t.severity}): {t.rationale}"
        )
    lines += ["", "## Constraints — what NOT to do", ""]
    for c in GRAPH.constraints:
        lines.append(f"  - [{c.kind}] {c.rule}  (src: {c.source})")
    lines += [
        "",
        "When the LLM cites any KPI, use the EXACT kpi_id — no paraphrasing.",
        "Never assert per-individual evaluative conclusions from these KPIs.",
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    print(to_llm_context())
    print()
    print("=== Sample queries ===")
    print(f"KPIs in 'concentration' family: {[k.kpi_id for k in kpis_by_family('concentration')]}")
    print(
        f"Thresholds on utilization_index_p75: {[t.label for t in thresholds_for('utilization_index_p75')]}"
    )
    print(f"Compliance constraints: {len(compliance_constraints())}")
    print(f"\nJSON schema_version: {to_json()['schema_version']}")
    print(f"JSON size: {len(json.dumps(to_json())):,} chars")
    print(f"Total KPIs: {len(GRAPH.kpis)}")
    print(f"Total thresholds: {len(GRAPH.thresholds)}")
    print(f"Total constraints: {len(GRAPH.constraints)}")
