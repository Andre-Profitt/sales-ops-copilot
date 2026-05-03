#!/usr/bin/env python3
"""Print and persist the Sales Director monthly factory plan (read-only).

This command never executes deck builds, SharePoint operations, or Office/VM
work. It only emits the canonical stage graph for the requested period and
notes whether the period is certified for production. Uncertified periods
still produce a plan, but with ``period_status=uncertified`` and explicit
blockers; they are intended to feed the period-roll certification harness.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.period_context import DEFAULT_PERIOD  # noqa: E402
from scripts.sd_factory.plan import (  # noqa: E402
    factory_plan_for_period,
    plan_to_markdown,
)


def _default_output_dir(period: str) -> Path:
    return REPO_ROOT / "state" / period / "__regional__" / "factory_plan"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--period", default=DEFAULT_PERIOD)
    parser.add_argument(
        "--director-slug",
        default=None,
        help="Annotate the plan with a single director slug; does not filter stages.",
    )
    parser.add_argument(
        "--no-publish",
        action="store_true",
        help="Exclude SharePoint publish stages from the plan.",
    )
    parser.add_argument(
        "--no-full-refresh",
        action="store_true",
        help="Exclude full Office/VM table-image refresh stages from the plan.",
    )
    parser.add_argument(
        "--no-source",
        action="store_true",
        help="Exclude Salesforce source-refresh stages from the plan.",
    )
    parser.add_argument("--host", default="Windows-VM")
    parser.add_argument("--json-output", type=Path)
    parser.add_argument("--markdown-output", type=Path)
    parser.add_argument(
        "--print-only",
        action="store_true",
        help="Skip writing to disk; only print the plan to stdout.",
    )
    parser.add_argument(
        "--format",
        choices=("markdown", "json"),
        default="markdown",
        help="Choose stdout format. Both files are still written unless --print-only.",
    )
    args = parser.parse_args()

    plan = factory_plan_for_period(
        args.period,
        director_slug=args.director_slug,
        include_publish=not args.no_publish,
        include_full_refresh=not args.no_full_refresh,
        include_source_only=not args.no_source,
        host=args.host,
    )

    if args.format == "json":
        sys.stdout.write(json.dumps(asdict(plan), indent=2) + "\n")
    else:
        sys.stdout.write(plan_to_markdown(plan))

    if not args.print_only:
        output_dir = _default_output_dir(args.period)
        json_path = args.json_output or output_dir / "factory_plan.json"
        md_path = args.markdown_output or output_dir / "factory_plan.md"
        json_path.parent.mkdir(parents=True, exist_ok=True)
        json_path.write_text(json.dumps(asdict(plan), indent=2) + "\n", encoding="utf-8")
        md_path.write_text(plan_to_markdown(plan), encoding="utf-8")
        print(f"json={json_path}", file=sys.stderr)
        print(f"markdown={md_path}", file=sys.stderr)

    return 0 if plan.period_status == "ready" else 0


if __name__ == "__main__":
    raise SystemExit(main())
