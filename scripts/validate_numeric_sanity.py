#!/usr/bin/env python3
"""Numeric-sanity gate for .ppttc payloads — catches the F-01/F-02 class.

We've shipped 1000x scale errors twice (F-01: kEUR vs mEUR, F-02: days x
1000). Both went undetected by structural validators because the XML and
the JSON were both syntactically clean — only the *magnitudes* were wrong.

This gate compares each numeric value in a .ppttc payload against per-
binding sanity ranges, surfacing values that are obviously off-scale.

Per-binding ranges (encoded below) reflect the *expected unit*:
  ARR/ACV bindings  -> EUR millions, [0.001, 1000]      (€1k to €1B)
  Days bindings     -> integer days, [0, 730]           (≤2 years)
  Percent bindings  -> fraction,    [-2, 2]             (-200% to 200%)
  Count bindings    -> integer,     [0, 100000]
  Date bindings     -> ISO year,    [2000, 2050]

Usage:
    python3 scripts/validate_numeric_sanity.py path.ppttc
    python3 scripts/validate_numeric_sanity.py path.ppttc --json

Exit codes:
    0  clean
    1  fail-level findings (value out of range)
    2  warn-level findings (value at extreme but plausible)
    3  could not parse
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

# Match by binding-name prefix or by substring. First match wins.
RANGE_RULES: list[dict[str, Any]] = [
    # ARR / ACV / EUR / value bindings - in millions. Zero is legit (empty
    # bucket); the bug class we're catching is *off-scale* values (mEUR
    # mislabeled as kEUR yields values in the thousands or millions).
    {
        "match": [
            "pipemovement",
            "pipelinebystage",
            "pipelineaging",
            "byowner",
            "stagebyindustry",
            "territoryperformance",
            "winslossesqtd",
            "pipelinecreationvelocity",
            "renewalpipeline",
            "concentration",
            "accountexpansion",
            "forecastcategory",
        ],
        "kind": "currency_meur",
        "min": -50.0,
        "max": 1000.0,
        "warn_min": -10.0,
        "warn_max": 500.0,
    },
    # Days metrics. Stuck enterprise deals legitimately exceed 5 years;
    # cap absolute at 10y. Warn over 2y as still notable.
    {
        "match": ["velocity", "stale", "drought", "age_days", "zombie"],
        "kind": "days",
        "min": 0,
        "max": 3650,
        "warn_min": 0,
        "warn_max": 730,
    },
    # Percentages stored as decimal fractions. Notes:
    # - "forecastcategory" is currency (mEUR), not percent — keep it out of
    #   this list (it's matched by currency_meur).
    # - "grrproxy" is heterogeneous (S12 has currency rows AND % rows in the
    #   same table). Heterogeneous bindings are deliberately skipped from
    #   classification — they need bespoke validation.
    {
        "match": ["winrate", "conversionrate", "_pct"],
        "kind": "percent_fraction",
        "min": -2.0,
        "max": 2.0,
        "warn_min": -1.0,
        "warn_max": 1.5,
    },
    # Counts (deal counts, owner counts, etc.)
    {
        "match": ["count", "_n", "actionitems"],
        "kind": "count",
        "min": 0,
        "max": 100000,
        "warn_min": 0,
        "warn_max": 5000,
    },
]


@dataclass
class Finding:
    level: str
    rule: str
    binding: str
    value: float
    expected_range: str
    location: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Report:
    path: str
    binding_count: int = 0
    number_cells_checked: int = 0
    findings: list[Finding] = field(default_factory=list)

    def add(
        self, level: str, rule: str, binding: str, value: float, expected: str, location: str = ""
    ) -> None:
        self.findings.append(Finding(level, rule, binding, value, expected, location))

    @property
    def fails(self) -> list[Finding]:
        return [f for f in self.findings if f.level == "fail"]

    @property
    def warns(self) -> list[Finding]:
        return [f for f in self.findings if f.level == "warn"]

    def to_dict(self) -> dict:
        return {
            "path": self.path,
            "binding_count": self.binding_count,
            "number_cells_checked": self.number_cells_checked,
            "fail_count": len(self.fails),
            "warn_count": len(self.warns),
            "findings": [f.to_dict() for f in self.findings],
        }


def _classify_binding(name: str) -> dict[str, Any] | None:
    n = name.lower()
    for rule in RANGE_RULES:
        for keyword in rule["match"]:
            if keyword in n:
                return rule
    return None


def _check_value(
    rule: dict[str, Any], binding: str, value: float, location: str, rep: Report
) -> None:
    rep.number_cells_checked += 1
    fmin, fmax = rule["min"], rule["max"]
    wmin, wmax = rule["warn_min"], rule["warn_max"]
    expected = f"[{fmin}, {fmax}] ({rule['kind']})"
    if value < fmin or value > fmax:
        rep.add("fail", "numeric.out-of-range", binding, value, expected, location)
    elif value < wmin or value > wmax:
        rep.add("warn", "numeric.extreme", binding, value, expected, location)


def _walk_cells(payload: list[dict[str, Any]], rep: Report) -> None:
    """Walk a .ppttc payload — top-level is `[{template, data: [...]}, ...]`.
    `data` is the list of bindings; each binding has `name` and `table` (list
    of rows, each a list of cells). Cells: {"number": x}, {"percentage": x},
    {"date": x}, {"string": s}, {"fill": s}, or {} for null.
    """
    for outer in payload:
        bindings = outer.get("data") if isinstance(outer, dict) else None
        if not isinstance(bindings, list):
            continue
        for entry in bindings:
            if not isinstance(entry, dict):
                continue
            binding = entry.get("name") or entry.get("binding") or ""
            rep.binding_count += 1
            rule = _classify_binding(binding)
            if rule is None:
                continue
            rows = entry.get("table") or entry.get("data") or entry.get("rows") or []
            for r_idx, row in enumerate(rows):
                cells = row if isinstance(row, list) else [row]
                for c_idx, cell in enumerate(cells):
                    if not isinstance(cell, dict):
                        continue
                    for cell_kind in ("number", "percentage", "date"):
                        if cell_kind not in cell:
                            continue
                        val = cell[cell_kind]
                        if not isinstance(val, (int, float)):
                            continue
                        loc = f"{binding}[{r_idx}][{c_idx}].{cell_kind}"
                        if cell_kind == "date":
                            approx_year = 1900 + int(float(val)) // 365
                            if not (2000 <= approx_year <= 2050):
                                rep.add(
                                    "fail",
                                    "date.out-of-range",
                                    binding,
                                    float(val),
                                    "[serial 36525, 54791] = 2000..2050",
                                    loc,
                                )
                            continue
                        _check_value(rule, binding, float(val), loc, rep)


def validate(path: Path) -> Report:
    rep = Report(path=str(path))
    if not path.exists():
        rep.add("fail", "file.missing", "", 0.0, "", str(path))
        return rep
    try:
        text = path.read_text(encoding="utf-8")
        payload = json.loads(text)
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        rep.add("fail", "ppttc.parse", "", 0.0, "", str(e))
        return rep
    if not isinstance(payload, list):
        rep.add("fail", "ppttc.shape", "", 0.0, "expected top-level array", "")
        return rep
    _walk_cells(payload, rep)
    return rep


def _format_text(rep: Report) -> str:
    lines = [f"== {rep.path}"]
    lines.append(
        f"   bindings: {rep.binding_count}   number_cells_checked: {rep.number_cells_checked}"
    )
    if not rep.findings:
        lines.append("   clean")
        return "\n".join(lines)
    lines.append(f"   FAIL: {len(rep.fails)}   WARN: {len(rep.warns)}")
    for f in rep.findings:
        prefix = {"fail": "  [FAIL]", "warn": "  [warn]"}.get(f.level, "  [info]")
        lines.append(
            f"{prefix} {f.rule}: binding={f.binding!r} value={f.value} "
            f"expected={f.expected_range} ({f.location})"
        )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    p.add_argument("paths", nargs="+", type=Path)
    p.add_argument("--json", action="store_true")
    args = p.parse_args(argv)
    reports = [validate(p) for p in args.paths]
    if args.json:
        print(json.dumps({"reports": [r.to_dict() for r in reports]}, indent=2))
    else:
        for r in reports:
            print(_format_text(r))
    worst = 0
    for r in reports:
        if r.fails:
            worst = max(worst, 1)
        elif r.warns:
            worst = max(worst, 2)
    return worst


if __name__ == "__main__":
    sys.exit(main())
