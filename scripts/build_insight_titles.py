"""Compute evidence-backed insight titles per slide for one director.

Inputs:
  --metrics: JSON blob of computed metrics (stage_5_plus_arr_share, etc.)
  --rules:   land_review_insight_titles.yml
  --out:     JSON {S##: title} for every analytic slide

Rule semantics:
  - Each slide may have N rules, evaluated top-to-bottom.
  - First rule whose `when` evaluates truthy wins.
  - If no rule fires, fall back to defaults[slide_id].
  - Title strings use Python format: title.format(**metrics).
  - `when` is restricted-eval with metrics as namespace plus None-safe access.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import yaml


def _safe_eval(expr: str, ns: dict[str, Any]) -> bool:
    """Evaluate `when` expression in a restricted namespace."""

    class _NoneDict(dict):
        def __missing__(self, _key: str) -> None:  # type: ignore[override]
            return None

    safe_ns = _NoneDict(ns)
    try:
        return bool(eval(expr, {"__builtins__": {}}, safe_ns))
    except Exception:
        return False


def _format_title(template: str, ns: dict[str, Any]) -> str:
    class _NoneDict(dict):
        def __missing__(self, _key: str) -> str:
            return ""

    return template.format_map(_NoneDict(ns))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--metrics", required=True, type=Path)
    parser.add_argument("--rules", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args(argv)

    metrics = json.loads(args.metrics.read_text())
    rules_doc = yaml.safe_load(args.rules.read_text())
    defaults: dict[str, str] = rules_doc.get("defaults", {})
    rules: dict[str, list[dict]] = rules_doc.get("rules", {})

    titles: dict[str, str] = {}
    for slide_id, default in defaults.items():
        chosen = None
        for rule in rules.get(slide_id, []):
            if _safe_eval(rule["when"], metrics):
                chosen = _format_title(rule["title"], metrics)
                break
        titles[slide_id] = chosen or default

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(titles, indent=2))
    print(f"OK: wrote {len(titles)} titles to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
