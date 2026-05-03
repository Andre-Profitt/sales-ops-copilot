#!/usr/bin/env python3
"""Plan-only period-roll certification harness.

Validates either an already-wired period (default ``2026-Q2``) or a candidate
period spec passed via CLI flags. Emits JSON and markdown reports under
``state/<period>/__regional__/factory_plan/period_roll_certification.{json,md}``.

The harness never executes deck builds, SharePoint operations, or Salesforce
queries. It performs structural and static checks:

- folder name conventions
- snapshot date math
- Salesforce Type-filter presence in scripts/land_brief.py
- director roster from scripts/_directors
- publish blocked for periods not wired into period_context
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.period_context import DEFAULT_PERIOD  # noqa: E402
from scripts.sd_factory.certification import (  # noqa: E402
    CertificationSpec,
    certify_candidate,
    certify_existing_period,
    report_to_markdown,
)


def _default_output_dir(period: str) -> Path:
    return REPO_ROOT / "state" / period / "__regional__" / "factory_plan"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--period", default=DEFAULT_PERIOD)
    parser.add_argument(
        "--candidate",
        action="store_true",
        help="Validate a candidate spec passed via --candidate-* flags instead of an existing period.",
    )
    parser.add_argument("--candidate-month-label")
    parser.add_argument("--candidate-snapshot-date")
    parser.add_argument("--candidate-kickoff-date")
    parser.add_argument("--candidate-sharepoint-folder")
    parser.add_argument("--candidate-review-package-dir")
    parser.add_argument("--json-output", type=Path)
    parser.add_argument("--markdown-output", type=Path)
    parser.add_argument("--print-only", action="store_true")
    parser.add_argument(
        "--format",
        choices=("markdown", "json"),
        default="markdown",
        help="Choose stdout format. Files are still written unless --print-only is set.",
    )
    args = parser.parse_args()

    if args.candidate:
        missing = [
            flag
            for flag, value in (
                ("--candidate-month-label", args.candidate_month_label),
                ("--candidate-snapshot-date", args.candidate_snapshot_date),
                ("--candidate-kickoff-date", args.candidate_kickoff_date),
                ("--candidate-sharepoint-folder", args.candidate_sharepoint_folder),
            )
            if not value
        ]
        if missing:
            print(
                f"error: --candidate requires {', '.join(missing)}",
                file=sys.stderr,
            )
            return 2
        spec = CertificationSpec(
            period=args.period,
            month_label=args.candidate_month_label,
            snapshot_date=args.candidate_snapshot_date,
            kickoff_date=args.candidate_kickoff_date,
            sharepoint_folder=args.candidate_sharepoint_folder,
            review_package_dir=args.candidate_review_package_dir,
        )
        report = certify_candidate(spec)
    else:
        try:
            report = certify_existing_period(args.period)
        except ValueError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2

    payload = dataclasses.asdict(report)
    payload["status"] = report.status
    if args.format == "json":
        sys.stdout.write(json.dumps(payload, indent=2) + "\n")
    else:
        sys.stdout.write(report_to_markdown(report))

    if not args.print_only:
        output_dir = _default_output_dir(args.period)
        json_path = args.json_output or output_dir / "period_roll_certification.json"
        md_path = args.markdown_output or output_dir / "period_roll_certification.md"
        json_path.parent.mkdir(parents=True, exist_ok=True)
        json_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        md_path.write_text(report_to_markdown(report), encoding="utf-8")
        print(f"json={json_path}", file=sys.stderr)
        print(f"markdown={md_path}", file=sys.stderr)

    return 0 if report.status in {"pass", "warn"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
