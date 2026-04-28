"""Pydantic schema for the trends.json envelope.

Contract between sales-ops-copilot (producer) and
func-simcorp-deckgen-dev /api/generate-land-deck (consumer in Plan B).

Breaking changes require bumping schema_version.
"""

from __future__ import annotations
from typing import Literal, Optional
from pydantic import BaseModel, Field


class Director(BaseModel):
    name: str
    book_codes: list[str]
    scope: Optional[Literal["global", "us_only"]] = None


class KPI(BaseModel):
    name: str
    value: float
    unit: Literal["EUR", "pct", "count", "days"]
    narrative_priority: Literal["high", "medium", "low"]
    stage_label: Optional[str] = None
    num_opps: Optional[int] = None


class Insight(BaseModel):
    kpi_name: str
    claim: str
    rule: str
    evidence: list[str] = Field(default_factory=list)


class EdgeCaseFlags(BaseModel):
    insufficient_history: bool = False
    fy_boundary_span: bool = False
    director_inactive: bool = False
    extraction_partial: bool = False


class TrendsEnvelope(BaseModel):
    schema_version: Literal["1.0"]
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
