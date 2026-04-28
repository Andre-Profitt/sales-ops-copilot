#!/usr/bin/env python3
"""Sales Ops brief evaluation runner (Phase 1 — local).

Loads a frozen ground-truth dataset and an agent brief markdown, runs the
selected evaluators, prints a summary table, and writes a per-run JSON
artifact under eval/runs/.

Phase 3 (deferred): swap the local runner for `azure-ai-evaluation`'s
`evaluate(...)` against an AI Foundry project so trends land in the Foundry
eval dashboard.

Usage:
    python3 eval/run_eval.py
    python3 eval/run_eval.py --dataset eval/datasets/2026-04-28.json
    python3 eval/run_eval.py --brief reports/agent-2026-04-28.md
    python3 eval/run_eval.py --evaluators rule
    python3 eval/run_eval.py --evaluators rule,llm
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib
import sys
from typing import Any

ROOT = pathlib.Path(__file__).resolve().parent.parent
EVAL_DIR = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(EVAL_DIR))

from evaluators import NumericFactRecallEvaluator, GroundednessLLMJudgeEvaluator  # noqa: E402


PASS_THRESHOLD = 0.9


# --- IO helpers -------------------------------------------------------------


def _latest_dataset() -> pathlib.Path:
    datasets = sorted((EVAL_DIR / "datasets").glob("*.json"))
    if not datasets:
        sys.exit("No datasets found under eval/datasets/")
    return datasets[-1]


def _today_brief() -> pathlib.Path:
    today = dt.date.today().isoformat()
    candidates = [
        ROOT / "reports" / f"agent-{today}.md",
        ROOT / "reports" / f"{today}.md",
    ]
    for c in candidates:
        if c.exists():
            return c
    # Fall back to the most recent agent-*.md
    agent_briefs = sorted((ROOT / "reports").glob("agent-*.md"))
    if agent_briefs:
        return agent_briefs[-1]
    sys.exit("No brief found under reports/ matching agent-YYYY-MM-DD.md")


def _load_dataset(path: pathlib.Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def _load_brief(path: pathlib.Path) -> str:
    return path.read_text()


# --- Pretty printer ---------------------------------------------------------


def _fmt_row(name: str, score: float, detail: str, width: int = 34) -> str:
    return f"{name.ljust(width)} {score:>5.2f}   {detail}"


def _print_summary(rows: list[tuple[str, float, str]]) -> None:
    width = 34
    print()
    print(f"{'Evaluator'.ljust(width)} {'Score':>5}   Detail")
    print("-" * 100)
    for name, score, detail in rows:
        print(_fmt_row(name, score, detail))
    print()


# --- Runner -----------------------------------------------------------------


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", type=pathlib.Path, default=None)
    ap.add_argument("--brief", type=pathlib.Path, default=None)
    ap.add_argument(
        "--evaluators",
        default="rule,llm",
        help="Comma list of: rule, llm. Default: rule,llm",
    )
    ap.add_argument(
        "--out",
        type=pathlib.Path,
        default=None,
        help="Optional explicit path for the run JSON; default eval/runs/<ts>.json",
    )
    args = ap.parse_args()

    dataset_path = args.dataset or _latest_dataset()
    brief_path = args.brief or _today_brief()
    requested = {x.strip().lower() for x in args.evaluators.split(",") if x.strip()}

    dataset = _load_dataset(dataset_path)
    brief_md = _load_brief(brief_path)
    facts = dataset["facts"]
    tolerance = float(dataset.get("tolerance_pct", 5.0))

    print(f"dataset: {dataset_path.relative_to(ROOT)}")
    print(f"brief:   {brief_path.relative_to(ROOT)}")
    print(f"evaluators: {sorted(requested)}")

    summary_rows: list[tuple[str, float, str]] = []
    run_payload: dict[str, Any] = {
        "timestamp": dt.datetime.now().isoformat(timespec="seconds"),
        "dataset": str(dataset_path.relative_to(ROOT)),
        "brief": str(brief_path.relative_to(ROOT)),
        "tolerance_pct": tolerance,
        "results": {},
    }

    if "rule" in requested:
        ev = NumericFactRecallEvaluator(tolerance_pct=tolerance)
        result = ev.run(facts, brief_md)
        missed = result.missed
        if missed:
            detail = f"{result.passed}/{result.total} facts within ±{tolerance}%; missed: {', '.join(missed)}"
        else:
            detail = f"{result.passed}/{result.total} facts within ±{tolerance}%"
        summary_rows.append((ev.name, result.score, detail))
        run_payload["results"][ev.name] = result.to_dict()

    if "llm" in requested:
        ev2 = GroundednessLLMJudgeEvaluator()
        try:
            result2 = ev2.run(facts, brief_md)
            n_un = len(result2.ungrounded_claims)
            if n_un == 0:
                detail2 = "no ungrounded claims"
            else:
                detail2 = f"{n_un} ungrounded: {result2.ungrounded_claims[0][:80]}"
                if n_un > 1:
                    detail2 += f" (+{n_un - 1} more)"
            summary_rows.append((ev2.name, result2.score, detail2))
            run_payload["results"][ev2.name] = result2.to_dict()
        except Exception as exc:  # judge failures should not crash the runner
            summary_rows.append((ev2.name, 0.0, f"ERROR: {exc}"))
            run_payload["results"][ev2.name] = {"error": str(exc)}

    _print_summary(summary_rows)

    # Persist
    runs_dir = EVAL_DIR / "runs"
    runs_dir.mkdir(parents=True, exist_ok=True)
    out_path = args.out or (runs_dir / f"{dt.datetime.now().strftime('%Y-%m-%dT%H%M%S')}.json")
    out_path.write_text(json.dumps(run_payload, indent=2, default=str))
    print(f"run artifact: {out_path.relative_to(ROOT)}")

    # Exit code: 0 iff every requested evaluator scored >= PASS_THRESHOLD
    all_passed = all(score >= PASS_THRESHOLD for _, score, _ in summary_rows)
    return 0 if all_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
