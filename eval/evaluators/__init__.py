"""Local Phase-1 evaluators for the daily Sales Ops brief.

Phase 3 (deferred): swap these out for `azure-ai-evaluation` SDK evaluators
running against an AI Foundry project. The interface here (run() returning a
score 0..1 + per-fact detail dict) maps cleanly onto Foundry's evaluator
contract, so the wiring is mechanical when we get there.
"""

from __future__ import annotations

from .numeric_recall import NumericFactRecallEvaluator
from .groundedness_judge import GroundednessLLMJudgeEvaluator

__all__ = ["NumericFactRecallEvaluator", "GroundednessLLMJudgeEvaluator"]
