#!/usr/bin/env python3
"""Month-over-month contact-sheet design gate (skeleton CLI).

Subcommands:

- ``compare``      compare current vs prior contact sheets and emit JSON+md
- ``acknowledge``  record an operator acknowledgement for a director's drift
- ``status``       show current pass/needs_ack/baseline status

This is the W8 skeleton. It is not yet wired into the publish gate; running
``status`` simply reports what is on disk. The acknowledgement file is the
operator's declaration that drift on a director is intentional and should not
block publish.
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
from scripts.sd_factory.design_gate import (  # noqa: E402
    DEFAULT_DRIFT_THRESHOLD,
    compare_contact_sheets,
    gate_output_dir,
    gate_report_path,
    report_to_markdown,
    write_acknowledgement,
)


def _cmd_compare(args: argparse.Namespace) -> int:
    report = compare_contact_sheets(
        args.period,
        prior_period=args.prior_period,
        root=REPO_ROOT,
        drift_threshold=args.drift_threshold,
    )
    payload = dataclasses.asdict(report)
    if args.format == "json":
        sys.stdout.write(json.dumps(payload, indent=2) + "\n")
    else:
        sys.stdout.write(report_to_markdown(report))
    if not args.print_only:
        out_dir = gate_output_dir(args.period, root=REPO_ROOT)
        out_dir.mkdir(parents=True, exist_ok=True)
        json_path = gate_report_path(args.period, root=REPO_ROOT)
        md_path = json_path.with_suffix(".md")
        json_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        md_path.write_text(report_to_markdown(report), encoding="utf-8")
        print(f"json={json_path}", file=sys.stderr)
        print(f"markdown={md_path}", file=sys.stderr)
    return 0 if report.status in {"pass", "baseline", "warn"} else 1


def _cmd_acknowledge(args: argparse.Namespace) -> int:
    path = write_acknowledgement(
        args.period,
        args.director_slug,
        root=REPO_ROOT,
        actor=args.actor,
        reason=args.reason,
    )
    print(f"ack_file={path}")
    return 0


def _cmd_status(args: argparse.Namespace) -> int:
    json_path = gate_report_path(args.period, root=REPO_ROOT)
    if not json_path.exists():
        print(f"no gate report at {json_path}; run `compare` first.", file=sys.stderr)
        return 2
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    sys.stdout.write(
        json.dumps(
            {
                "period": payload.get("period"),
                "status": payload.get("status"),
                "directors_requiring_ack": payload.get("directors_requiring_ack", []),
                "drift_threshold": payload.get("drift_threshold"),
                "generated_at_utc": payload.get("generated_at_utc"),
            },
            indent=2,
        )
        + "\n"
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    compare_p = sub.add_parser("compare", help="compare current vs prior contact sheets")
    compare_p.add_argument("--period", default=DEFAULT_PERIOD)
    compare_p.add_argument("--prior-period", default=None)
    compare_p.add_argument("--drift-threshold", type=float, default=DEFAULT_DRIFT_THRESHOLD)
    compare_p.add_argument("--format", choices=("markdown", "json"), default="markdown")
    compare_p.add_argument("--print-only", action="store_true")
    compare_p.set_defaults(func=_cmd_compare)

    ack_p = sub.add_parser("acknowledge", help="record acknowledgement for a director's drift")
    ack_p.add_argument("--period", default=DEFAULT_PERIOD)
    ack_p.add_argument("--director-slug", required=True)
    ack_p.add_argument("--actor", required=True)
    ack_p.add_argument("--reason", required=True)
    ack_p.set_defaults(func=_cmd_acknowledge)

    status_p = sub.add_parser("status", help="show last gate status")
    status_p.add_argument("--period", default=DEFAULT_PERIOD)
    status_p.set_defaults(func=_cmd_status)

    args = parser.parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
