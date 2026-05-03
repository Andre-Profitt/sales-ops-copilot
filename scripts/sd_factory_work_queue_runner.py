#!/usr/bin/env python3
"""CLI for the think-cell work-queue runner state machine.

Subcommands:

- ``init``       initialize a new run directory from the master queue
- ``status``     print summary counts (and write a markdown summary)
- ``list``       list jobs filtered by status/lane/role/priority
- ``show``       show full record for a single job
- ``start``      planned -> running
- ``pass``       running -> pass (records evidence paths)
- ``fail``       running -> fail (records note; protected lanes require --allow-protect-fail)
- ``block``      planned/running -> blocked (records reason)
- ``unblock``    blocked -> planned (or running if --to=running)

The runner never executes the underlying tasks. It only updates state and
emits an audit log. Master queue files are read-only.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.period_context import DEFAULT_PERIOD  # noqa: E402
from scripts.sd_factory.work_queue_runner import (  # noqa: E402
    WorkQueueRunnerError,
    initialize_run,
    list_jobs,
    runner_run_root,
    show_job,
    status_summary,
    summary_to_markdown,
    transition_job,
)


def _run_dir(period: str, run_id: str) -> Path:
    return runner_run_root(period, root=REPO_ROOT) / run_id


def _cmd_init(args: argparse.Namespace) -> int:
    try:
        run_dir = initialize_run(args.period, args.run_id, root=REPO_ROOT, actor=args.actor)
    except WorkQueueRunnerError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(f"run_dir={run_dir}")
    return 0


def _cmd_status(args: argparse.Namespace) -> int:
    run_dir = _run_dir(args.period, args.run_id)
    try:
        summary = status_summary(run_dir)
    except WorkQueueRunnerError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if args.format == "json":
        sys.stdout.write(json.dumps(summary, indent=2) + "\n")
    else:
        sys.stdout.write(summary_to_markdown(summary))
    if not args.print_only:
        (run_dir / "summary.json").write_text(
            json.dumps(summary, indent=2) + "\n", encoding="utf-8"
        )
        (run_dir / "summary.md").write_text(summary_to_markdown(summary), encoding="utf-8")
    return 0


def _cmd_list(args: argparse.Namespace) -> int:
    run_dir = _run_dir(args.period, args.run_id)
    try:
        jobs = list_jobs(
            run_dir,
            status=args.status,
            lane=args.lane,
            role=args.role,
            priority=args.priority,
        )
    except WorkQueueRunnerError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    payload = [
        {
            "job_id": job["job_id"],
            "contract": job.get("contract"),
            "role": job.get("role"),
            "priority": job.get("priority"),
            "lane": job.get("lane"),
            "status": job.get("status"),
        }
        for job in jobs
    ]
    if args.format == "json":
        sys.stdout.write(json.dumps(payload, indent=2) + "\n")
    else:
        for entry in payload:
            sys.stdout.write(
                "{status:>8} {priority} {lane:<25} {role:<22} {job_id}\n".format(**entry)
            )
    return 0


def _cmd_show(args: argparse.Namespace) -> int:
    run_dir = _run_dir(args.period, args.run_id)
    try:
        job = show_job(run_dir, args.job_id)
    except WorkQueueRunnerError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    sys.stdout.write(json.dumps(job, indent=2) + "\n")
    return 0


def _cmd_transition(args: argparse.Namespace, target: str) -> int:
    run_dir = _run_dir(args.period, args.run_id)
    try:
        job = transition_job(
            run_dir,
            args.job_id,
            target,
            actor=args.actor,
            note=args.note,
            evidence=args.evidence or [],
            allow_protect_fail=getattr(args, "allow_protect_fail", False),
        )
    except WorkQueueRunnerError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(f"{job['job_id']}: status={job['status']}")
    return 0


def _cmd_start(args: argparse.Namespace) -> int:
    return _cmd_transition(args, "running")


def _cmd_pass(args: argparse.Namespace) -> int:
    return _cmd_transition(args, "pass")


def _cmd_fail(args: argparse.Namespace) -> int:
    return _cmd_transition(args, "fail")


def _cmd_block(args: argparse.Namespace) -> int:
    return _cmd_transition(args, "blocked")


def _cmd_unblock(args: argparse.Namespace) -> int:
    target = "running" if args.to == "running" else "planned"
    return _cmd_transition(args, target)


def _add_common_run_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--period", default=DEFAULT_PERIOD)
    parser.add_argument("--run-id", required=True)


def _add_transition_args(parser: argparse.ArgumentParser) -> None:
    _add_common_run_args(parser)
    parser.add_argument("job_id")
    parser.add_argument("--actor", default="operator")
    parser.add_argument("--note")
    parser.add_argument("--evidence", action="append")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    init_p = sub.add_parser("init", help="initialize a new runner run directory")
    _add_common_run_args(init_p)
    init_p.add_argument("--actor", default="operator")
    init_p.set_defaults(func=_cmd_init)

    status_p = sub.add_parser("status", help="print and persist summary counts")
    _add_common_run_args(status_p)
    status_p.add_argument("--format", choices=("markdown", "json"), default="markdown")
    status_p.add_argument("--print-only", action="store_true")
    status_p.set_defaults(func=_cmd_status)

    list_p = sub.add_parser("list", help="list filtered jobs")
    _add_common_run_args(list_p)
    list_p.add_argument("--status")
    list_p.add_argument("--lane")
    list_p.add_argument("--role")
    list_p.add_argument("--priority")
    list_p.add_argument("--format", choices=("text", "json"), default="text")
    list_p.set_defaults(func=_cmd_list)

    show_p = sub.add_parser("show", help="show one job record as JSON")
    _add_common_run_args(show_p)
    show_p.add_argument("job_id")
    show_p.set_defaults(func=_cmd_show)

    start_p = sub.add_parser("start", help="planned -> running")
    _add_transition_args(start_p)
    start_p.set_defaults(func=_cmd_start)

    pass_p = sub.add_parser("pass", help="running -> pass")
    _add_transition_args(pass_p)
    pass_p.set_defaults(func=_cmd_pass)

    fail_p = sub.add_parser("fail", help="running -> fail")
    _add_transition_args(fail_p)
    fail_p.add_argument(
        "--allow-protect-fail",
        action="store_true",
        help="Allow failing a protect_proven_lane job (default: blocked).",
    )
    fail_p.set_defaults(func=_cmd_fail)

    block_p = sub.add_parser("block", help="planned/running -> blocked")
    _add_transition_args(block_p)
    block_p.set_defaults(func=_cmd_block)

    unblock_p = sub.add_parser("unblock", help="blocked -> planned (or running)")
    _add_transition_args(unblock_p)
    unblock_p.add_argument("--to", choices=("planned", "running"), default="planned")
    unblock_p.set_defaults(func=_cmd_unblock)

    args = parser.parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
