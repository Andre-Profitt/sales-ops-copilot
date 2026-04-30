"""Pydantic schema for the trends.json envelope (sales-ops-copilot side).

VERBATIM MIRROR of the consumer-side schema at:
    ~/projects/brand-deck-agent-py/agent/land_input_schema.py

Source of truth is the consumer; bump in BOTH places when the contract
changes. Keep field-by-field parity. Per
`feedback_simcorp_enterprise_claude_per_deal_2026-04-30`, per-deal
context (top_deals_named, pending_commercial_approval_named,
at_risk_renewals_named) is allowed in the envelope.
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class Director(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    book_codes: list[str]
    scope: Optional[Literal["global", "us_only"]] = None
    scope_label: Optional[str] = None  # human-readable territory


class KPI(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    value: float
    unit: Literal["EUR", "pct", "count", "days"]
    narrative_priority: Literal["high", "medium", "low"]
    stage_label: Optional[str] = None
    num_opps: Optional[int] = None
    display_label: Optional[str] = None


class Insight(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kpi_name: str
    claim: str
    rule: str
    evidence: list[str] = Field(default_factory=list)


class EdgeCaseFlags(BaseModel):
    model_config = ConfigDict(extra="forbid")

    insufficient_history: bool = False
    fy_boundary_span: bool = False
    director_inactive: bool = False
    extraction_partial: bool = False


class NamedDeal(BaseModel):
    """Per-deal entry — allowed under SimCorp enterprise Claude contract."""

    model_config = ConfigDict(extra="ignore")

    account: Optional[str] = None
    name: Optional[str] = None
    owner: Optional[str] = None
    stage: Optional[str] = None
    close_date: Optional[str] = None
    arr_eur: Optional[float] = None
    acv_eur: Optional[float] = None
    type: Optional[str] = None
    risk_level: Optional[str] = None


class ActionItem(BaseModel):
    """Rule-fired monthly action — slide 19 (formerly 26 after polish) consumes these."""

    model_config = ConfigDict(extra="ignore")

    rule_id: str
    priority: Literal["high", "medium", "low"]
    claim: str
    suggested_action: str
    due_date: Optional[str] = None
    owner: Optional[str] = None


class TrendsEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["2.0"]
    director: Director
    period: str
    period_end: str
    currency: Literal["EUR", "USD"] = "EUR"
    currency_format: Literal["mEUR", "kEUR", "EUR"] = "mEUR"
    kpis: list[KPI]
    highlights: list[Insight] = Field(default_factory=list)
    risks: list[Insight] = Field(default_factory=list)
    context_quotes: list[str] = Field(default_factory=list)
    edge_case_flags: EdgeCaseFlags
    top_deals_named: list[NamedDeal] = Field(default_factory=list)
    pending_commercial_approval_named: list[NamedDeal] = Field(default_factory=list)
    at_risk_renewals_named: list[NamedDeal] = Field(default_factory=list)
    action_items: list[ActionItem] = Field(default_factory=list)
