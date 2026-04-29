"""Rule-based numeric-fact recall evaluator.

Extracts dollar figures, percentages, and labels from the agent's markdown
brief and compares against a ground-truth facts dict within a percent
tolerance for currency values (exact match for counts and labels).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field, asdict
from typing import Any


# --- Number parsing ---------------------------------------------------------


def _to_int(s: str) -> int:
    return int(s.replace(",", "").split(".")[0])


def _within_tolerance(actual: int, expected: int, pct: float) -> bool:
    if expected == 0:
        return actual == 0
    drift = abs(actual - expected) / abs(expected) * 100.0
    return drift <= pct


# --- Per-fact extractors ----------------------------------------------------
#
# Each extractor returns the integer it found in the brief (or None). We pull
# from tables first because they have full-precision numbers; fall back to
# shorthand prose if the structured form is absent.


def _extract_quarter_row(text: str, quarter: str) -> dict[str, int] | None:
    """Parse a row like `| 2026-Q2 | $27,730,401 | $9,244,548 | ... |`."""
    # The row layout in the brief: Quarter | Open ARR | Weighted ARR | Open Renewal ACV | Weighted ACV
    pattern = (
        r"\|\s*"
        + re.escape(quarter)
        + r"\s*\|\s*\$?([\d,]+)\s*\|\s*\$?([\d,]+)\s*\|\s*\$?([\d,]+)\s*\|\s*\$?([\d,]+)\s*\|"
    )
    m = re.search(pattern, text)
    if not m:
        return None
    return {
        "open_arr": _to_int(m.group(1)),
        "weighted_arr": _to_int(m.group(2)),
        "open_renewal_acv": _to_int(m.group(3)),
        "weighted_renewal_acv": _to_int(m.group(4)),
    }


def _extract_top_owner(text: str) -> tuple[str, int, int] | None:
    """Pull the rank-1 row from the owner-concentration table.

    Row shape: `| 1 | Adam Hatcliff | 13 | $45,451,122 | 30% |`
    """
    m = re.search(
        r"##\s*Owner concentration.*?\|\s*1\s*\|\s*([^|]+?)\s*\|\s*\d+\s*\|\s*\$([\d,]+)\s*\|\s*(\d+)\s*%",
        text,
        re.DOTALL | re.IGNORECASE,
    )
    if not m:
        return None
    return m.group(1).strip(), _to_int(m.group(2)), int(m.group(3))


def _extract_top_account(text: str) -> tuple[str, int, int] | None:
    """Pull rank-1 from the account-concentration table.

    Row shape: `| 1 | UBS Global Asset Management (UK) Ltd | 13 | $24,032,948 | 20% |`
    """
    m = re.search(
        r"##\s*Account concentration.*?\|\s*1\s*\|\s*([^|]+?)\s*\|\s*(\d+)\s*\|\s*\$([\d,]+)",
        text,
        re.DOTALL | re.IGNORECASE,
    )
    if not m:
        return None
    return m.group(1).strip(), _to_int(m.group(3)), int(m.group(2))


def _count_alerts_in_section(text: str, section: str) -> int:
    """Count `**...**` alert headers under a `### Critical|Important|Info` section."""
    # Find the section, then count bold leaders before the next ### or ##
    m = re.search(
        rf"###\s+{section}\s*\n(.*?)(?=\n###\s|\n##\s|\Z)",
        text,
        re.DOTALL | re.IGNORECASE,
    )
    if not m:
        return 0
    block = m.group(1)
    return len(re.findall(r"^\*\*[^*]+\*\*\s*—", block, re.MULTILINE))


def _extract_top_product_family(text: str) -> tuple[str, int] | None:
    """Pull rank-1 from the product-family table.

    Row shape: `| 1 | SCD Software | 865 | $887,905,019 |`
    """
    m = re.search(
        r"###\s*Open Land\+Expand ARR by Product Family.*?\|\s*1\s*\|\s*([^|]+?)\s*\|\s*\d+\s*\|\s*\$([\d,]+)",
        text,
        re.DOTALL | re.IGNORECASE,
    )
    if not m:
        return None
    return m.group(1).strip(), _to_int(m.group(2))


def _extract_kyc_alert(text: str) -> tuple[int, int] | None:
    """`**Stage 5+ ... without KYC clearance** — 70 opps, $30,377,592 ARR`"""
    m = re.search(
        r"\*\*Stage 5\+.*?KYC.*?\*\*\s*—\s*(\d+)\s*opps?,\s*\$([\d,]+)",
        text,
        re.IGNORECASE,
    )
    if not m:
        return None
    return int(m.group(1)), _to_int(m.group(2))


# --- Per-fact rules ---------------------------------------------------------


@dataclass
class FactCheck:
    fact: str
    expected: Any
    actual: Any
    passed: bool
    note: str = ""


@dataclass
class NumericRecallResult:
    score: float
    passed: int
    total: int
    checks: list[FactCheck] = field(default_factory=list)
    missed: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "score": self.score,
            "passed": self.passed,
            "total": self.total,
            "missed": self.missed,
            "checks": [asdict(c) for c in self.checks],
        }


class NumericFactRecallEvaluator:
    """Compare expected facts to numbers extracted from the agent's markdown.

    Currency facts are checked within ±tolerance_pct. Counts and labels are
    exact-match.
    """

    name = "NumericFactRecallEvaluator"

    # Facts we treat as currency (apply tolerance). All others = exact.
    CURRENCY_FACTS = {
        "current_q_open_new_business_arr",
        "current_q_weighted_new_business_arr",
        "current_q_open_renewal_acv",
        "current_q_weighted_renewal_acv",
        "q_plus_1_weighted_new_business_arr",
        "q_plus_2_weighted_new_business_arr",
        "top_owner_arr",
        "top_account_arr",
        "stage_5_kyc_gap_arr",
        "top_product_family_arr",
    }

    def __init__(self, tolerance_pct: float = 5.0) -> None:
        self.tolerance_pct = tolerance_pct

    def run(self, facts: dict[str, Any], brief_md: str) -> NumericRecallResult:
        checks: list[FactCheck] = []
        extracted = self._extract_all(brief_md)

        for fact_name, expected in facts.items():
            actual = extracted.get(fact_name)
            if actual is None:
                checks.append(
                    FactCheck(
                        fact=fact_name,
                        expected=expected,
                        actual=None,
                        passed=False,
                        note="not extracted",
                    )
                )
                continue

            if fact_name in self.CURRENCY_FACTS:
                ok = _within_tolerance(int(actual), int(expected), self.tolerance_pct)
                drift = abs(int(actual) - int(expected)) / max(abs(int(expected)), 1) * 100
                note = f"drift={drift:.2f}% (tol={self.tolerance_pct}%)"
            else:
                ok = actual == expected
                note = "" if ok else f"expected {expected!r}, got {actual!r}"

            checks.append(
                FactCheck(
                    fact=fact_name,
                    expected=expected,
                    actual=actual,
                    passed=ok,
                    note=note,
                )
            )

        passed = sum(1 for c in checks if c.passed)
        total = len(checks)
        score = passed / total if total else 0.0
        missed = [c.fact for c in checks if not c.passed]
        return NumericRecallResult(
            score=score,
            passed=passed,
            total=total,
            checks=checks,
            missed=missed,
        )

    # --- Extraction orchestration -----------------------------------------

    def _extract_all(self, text: str) -> dict[str, Any]:
        out: dict[str, Any] = {}

        # Pull the three known quarter labels directly from the multi-quarter table
        labels = re.findall(r"\|\s*(20\d{2}-Q\d)\s*\|\s*\$", text)
        if len(labels) >= 1:
            out["current_quarter_label"] = labels[0]
            row = _extract_quarter_row(text, labels[0])
            if row:
                out["current_q_open_new_business_arr"] = row["open_arr"]
                out["current_q_weighted_new_business_arr"] = row["weighted_arr"]
                out["current_q_open_renewal_acv"] = row["open_renewal_acv"]
                out["current_q_weighted_renewal_acv"] = row["weighted_renewal_acv"]
        if len(labels) >= 2:
            out["q_plus_1_label"] = labels[1]
            row = _extract_quarter_row(text, labels[1])
            if row:
                out["q_plus_1_weighted_new_business_arr"] = row["weighted_arr"]
        if len(labels) >= 3:
            out["q_plus_2_label"] = labels[2]
            row = _extract_quarter_row(text, labels[2])
            if row:
                out["q_plus_2_weighted_new_business_arr"] = row["weighted_arr"]

        # Owner concentration top-1
        owner = _extract_top_owner(text)
        if owner:
            out["top_owner_name"], out["top_owner_arr"], out["top_owner_pct_of_top10"] = owner

        # Account concentration top-1
        acct = _extract_top_account(text)
        if acct:
            out["top_account_name"], out["top_account_arr"], out["top_account_deals"] = acct

        # Alert tier counts
        out["alert_count_critical"] = _count_alerts_in_section(text, "Critical")
        out["alert_count_important"] = _count_alerts_in_section(text, "Important")
        out["alert_count_info"] = _count_alerts_in_section(text, "Info")

        # KYC alert specifics
        kyc = _extract_kyc_alert(text)
        if kyc:
            out["stage_5_kyc_gap_count"], out["stage_5_kyc_gap_arr"] = kyc

        # Product family top-1
        pf = _extract_top_product_family(text)
        if pf:
            out["top_product_family_name"], out["top_product_family_arr"] = pf

        return out
