"""Recompute a formula-driven workbook in Python (no LibreOffice needed).

Wraps the `formulas` library (https://pypi.org/project/formulas/) to load
an xlsx, evaluate every formula, and emit a structured JSON report:

  {
    "workbook": "<path>",
    "ok": <bool>,
    "n_cells_computed": <int>,
    "errors": [
      {"sheet": "...", "cell": "...", "error": "#REF!", "formula": "..."},
      ...
    ],
    "kpis": {
      "Pipeline_Total!B2": 25000.0,
      "Pipeline_Total!B3": 27220000.0,
      ...
    }
  }

Mirrors the structured output of Anthropic's official `xlsx` Agent Skill
recalc.py (catches every #REF!/#DIV/0!/#VALUE!/#N/A/#NAME? with a cell
address). Use as a CI gate on land.model.xlsx after every build.

CLI:
    python3 scripts/model_recalc.py <path/to/workbook.xlsx>
    python3 scripts/model_recalc.py --help
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

import formulas  # type: ignore[import-untyped]
from formulas.tokens.operand import XlError  # type: ignore[import-untyped]


# Cells worth surfacing in the JSON output as a quick-look "did the
# headlines compute" panel. Add to this list if Phase 2 sheets join the
# formula-driven model.
HEADLINE_CELLS = [
    ("Pipeline_Total", "B2"),  # CFQ closeable Land+Expand
    ("Pipeline_Total", "B3"),  # Open beyond CFQ
    ("Pipeline_Total", "B4"),  # CFQ renewal ACV
    ("Pipeline_By_Stage", "B10"),  # Total ARR (after 8 stage rows + header)
]


_KEY_RE = re.compile(r"'?\[(?P<file>[^\]]+)\](?P<sheet>[^']+)'?!(?P<cell>.+)")


def _parse_key(key: str) -> tuple[str, str, str] | None:
    """formulas.calculate() keys look like:
    "'[file.xlsx]SHEET'!B2"  ->  ("file.xlsx", "SHEET", "B2")
    """
    m = _KEY_RE.match(str(key))
    if not m:
        return None
    return m.group("file"), m.group("sheet"), m.group("cell")


def _unwrap(val: Any) -> Any:
    """formulas returns values as schedula Range/Array objects sometimes
    and as plain scalars/XlError other times. Normalize to a JSON-safe
    Python value (int/float/str/None or stays as XlError sentinel)."""
    if val is None:
        return None
    # XlError is a str subclass — preserve its #ERROR! formatting.
    if isinstance(val, XlError):
        return str(val)
    # numpy / schedula array-like
    if hasattr(val, "item") and not isinstance(val, str):
        try:
            return val.item()
        except Exception:
            pass
    if hasattr(val, "value"):
        try:
            inner = val.value
            if hasattr(inner, "item"):
                return inner.item()
            if hasattr(inner, "tolist"):
                lst = inner.tolist()
                # Common shape: [[scalar]] for single-cell formulas
                if isinstance(lst, list) and len(lst) == 1:
                    inner_lst = lst[0]
                    if isinstance(inner_lst, list) and len(inner_lst) == 1:
                        return inner_lst[0]
                return lst
            return inner
        except Exception:
            pass
    if isinstance(val, (int, float, str, bool)):
        return val
    return str(val)


def recalc(path: Path) -> dict:
    """Load + compute the workbook, return structured report."""
    if not path.exists():
        return {"workbook": str(path), "ok": False, "errors": [{"error": "FileNotFound"}]}

    xl = formulas.ExcelModel().loads(str(path)).finish()
    sol = xl.calculate()

    sheet_cells: dict[tuple[str, str], Any] = {}
    for k, v in sol.items():
        parsed = _parse_key(str(k))
        if parsed is None:
            continue
        _, sheet, cell = parsed
        sheet_cells[(sheet, cell)] = _unwrap(v)

    # Surface error cells (XlError instances → strings starting with '#')
    errors = []
    for (sheet, cell), val in sorted(sheet_cells.items()):
        if isinstance(val, str) and val.startswith("#") and val.endswith("!"):
            errors.append({"sheet": sheet, "cell": cell, "error": val})

    # Headline KPI panel
    kpis: dict[str, Any] = {}
    for sheet, cell in HEADLINE_CELLS:
        # formulas uppercases sheet names internally; check both cases.
        for key_sheet in (sheet.upper(), sheet):
            v = sheet_cells.get((key_sheet, cell))
            if v is not None:
                kpis[f"{sheet}!{cell}"] = v
                break

    return {
        "workbook": str(path),
        "ok": len(errors) == 0,
        "n_cells_computed": len(sheet_cells),
        "errors": errors,
        "kpis": kpis,
    }


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Recompute a formula-driven xlsx and emit structured JSON."
    )
    ap.add_argument("path", type=Path, help="Path to workbook.xlsx")
    ap.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress JSON output; exit 0 on no errors, 1 otherwise.",
    )
    args = ap.parse_args()

    report = recalc(args.path)
    if not args.quiet:
        print(json.dumps(report, indent=2, default=str))
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
