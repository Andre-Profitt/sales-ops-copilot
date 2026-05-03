"""Stateful runner for the think-cell contract work queue.

The runner is a state machine over the queue produced by
``scripts/build_thinkcell_work_queue.py``. It never executes the underlying
seed-authoring or binding-proof tasks itself, and never mutates the master
queue file. Every transition is written to an isolated run directory:

``state/thinkcell_bridge/build_scaffold/<period>/runner_runs/<run_id>/``

``state.json`` holds the per-run overlay (job records with mutable
``status``, ``transitions``, ``notes``, and ``evidence`` fields), and
``events.jsonl`` is an append-only audit log of every transition.

Allowed status values:

- ``planned``  — initial state copied from the master queue
- ``running``  — operator has started this job
- ``pass``     — operator has confirmed this job's gates are met (with evidence)
- ``fail``     — operator has confirmed this job failed gates (with note)
- ``blocked``  — job cannot progress (waiting on dependency or external action)

Allowed transitions:

- ``planned -> running, blocked``
- ``running -> pass, fail, blocked``
- ``blocked -> planned, running``  (unblock)
- ``pass -> pass``  (idempotent re-confirm with new evidence)
- ``fail -> running, blocked``  (retry path)

Protect-proven jobs (``lane=='protect_proven_lane'``) cannot be transitioned
to ``fail`` unless the caller explicitly passes ``allow_protect_fail=True``.
This guards the L5-proven contracts from being marked failed by mistake.
"""

from __future__ import annotations

import datetime as dt
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

VALID_STATUSES: tuple[str, ...] = ("planned", "running", "pass", "fail", "blocked")
PROTECT_LANE = "protect_proven_lane"

ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    "planned": {"running", "blocked"},
    "running": {"pass", "fail", "blocked"},
    "blocked": {"planned", "running"},
    "pass": {"pass"},
    "fail": {"running", "blocked"},
}


class WorkQueueRunnerError(RuntimeError):
    pass


@dataclass
class TransitionEvent:
    timestamp_utc: str
    job_id: str
    from_status: str
    to_status: str
    actor: str
    note: str | None = None
    evidence: list[str] = field(default_factory=list)


def _utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def runner_run_root(period: str, *, root: Path) -> Path:
    return root / "state" / "thinkcell_bridge" / "build_scaffold" / period / "runner_runs"


def master_queue_path(period: str, *, root: Path) -> Path:
    return root / "state" / "thinkcell_bridge" / "build_scaffold" / period / "work_queue.json"


def load_master_queue(period: str, *, root: Path) -> dict[str, Any]:
    path = master_queue_path(period, root=root)
    if not path.exists():
        raise WorkQueueRunnerError(f"master queue not found at {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def initialize_run(
    period: str,
    run_id: str,
    *,
    root: Path,
    actor: str = "operator",
) -> Path:
    """Materialize a per-run state file under runner_runs/<run_id>/state.json.

    The state mirrors the master queue but adds mutable runner fields:
    ``transitions``, ``notes``, and ``evidence`` per job. The master queue
    file is never modified.
    """

    master = load_master_queue(period, root=root)
    run_dir = runner_run_root(period, root=root) / run_id
    if (run_dir / "state.json").exists():
        raise WorkQueueRunnerError(f"run already initialized: {run_dir}/state.json")
    run_dir.mkdir(parents=True, exist_ok=True)
    state = {
        "schema": "thinkcell-work-queue-runner-state/v1",
        "period": period,
        "run_id": run_id,
        "created_at_utc": _utc_now(),
        "actor": actor,
        "master_source": str(master_queue_path(period, root=root).relative_to(root)),
        "contract_count": master.get("contract_count"),
        "job_count": master.get("job_count"),
        "jobs": [_initialize_job(job) for job in master.get("jobs", [])],
    }
    (run_dir / "state.json").write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    (run_dir / "events.jsonl").write_text("", encoding="utf-8")
    return run_dir


def _initialize_job(master_job: dict[str, Any]) -> dict[str, Any]:
    record = dict(master_job)
    record["status"] = "planned"
    record["transitions"] = []
    record["notes"] = []
    record["evidence"] = []
    return record


def _load_state(run_dir: Path) -> dict[str, Any]:
    state_path = run_dir / "state.json"
    if not state_path.exists():
        raise WorkQueueRunnerError(f"state.json not found at {state_path}")
    return json.loads(state_path.read_text(encoding="utf-8"))


def _save_state(run_dir: Path, state: dict[str, Any]) -> None:
    (run_dir / "state.json").write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")


def _append_event(run_dir: Path, event: TransitionEvent) -> None:
    (run_dir / "events.jsonl").open("a", encoding="utf-8").write(
        json.dumps(
            {
                "timestamp_utc": event.timestamp_utc,
                "job_id": event.job_id,
                "from_status": event.from_status,
                "to_status": event.to_status,
                "actor": event.actor,
                "note": event.note,
                "evidence": event.evidence,
            }
        )
        + "\n"
    )


def _find_job(state: dict[str, Any], job_id: str) -> dict[str, Any]:
    for job in state.get("jobs", []):
        if job.get("job_id") == job_id:
            return job
    raise WorkQueueRunnerError(f"job_id not found in state: {job_id}")


def _validate_transition(
    job: dict[str, Any],
    target: str,
    *,
    allow_protect_fail: bool,
) -> None:
    current = job.get("status", "planned")
    if target not in VALID_STATUSES:
        raise WorkQueueRunnerError(f"invalid target status: {target}")
    allowed = ALLOWED_TRANSITIONS.get(current, set())
    if target not in allowed:
        raise WorkQueueRunnerError(
            f"transition not allowed for {job['job_id']}: {current} -> {target} "
            f"(allowed from {current}: {sorted(allowed)})"
        )
    if target == "fail" and job.get("lane") == PROTECT_LANE and not allow_protect_fail:
        raise WorkQueueRunnerError(
            f"cannot fail protect_proven_lane job {job['job_id']} without allow_protect_fail=True"
        )


def transition_job(
    run_dir: Path,
    job_id: str,
    target: str,
    *,
    actor: str = "operator",
    note: str | None = None,
    evidence: list[str] | None = None,
    allow_protect_fail: bool = False,
) -> dict[str, Any]:
    """Apply a state transition to ``job_id`` in ``run_dir``."""

    state = _load_state(run_dir)
    job = _find_job(state, job_id)
    _validate_transition(job, target, allow_protect_fail=allow_protect_fail)
    timestamp = _utc_now()
    transition_record = {
        "timestamp_utc": timestamp,
        "from_status": job.get("status", "planned"),
        "to_status": target,
        "actor": actor,
        "note": note,
        "evidence": list(evidence or []),
    }
    job.setdefault("transitions", []).append(transition_record)
    if note:
        job.setdefault("notes", []).append(
            {"timestamp_utc": timestamp, "actor": actor, "text": note}
        )
    if evidence:
        job.setdefault("evidence", []).extend(evidence)
    job["status"] = target
    _save_state(run_dir, state)
    _append_event(
        run_dir,
        TransitionEvent(
            timestamp_utc=timestamp,
            job_id=job_id,
            from_status=transition_record["from_status"],
            to_status=target,
            actor=actor,
            note=note,
            evidence=list(evidence or []),
        ),
    )
    return job


def status_summary(run_dir: Path) -> dict[str, Any]:
    state = _load_state(run_dir)
    counts: dict[str, int] = {status: 0 for status in VALID_STATUSES}
    by_lane: dict[str, dict[str, int]] = {}
    by_role: dict[str, dict[str, int]] = {}
    by_priority: dict[str, dict[str, int]] = {}
    for job in state.get("jobs", []):
        status = job.get("status", "planned")
        counts[status] = counts.get(status, 0) + 1
        lane = job.get("lane", "unknown")
        role = job.get("role", "unknown")
        priority = job.get("priority", "unknown")
        lane_dict = by_lane.setdefault(lane, {s: 0 for s in VALID_STATUSES})
        lane_dict[status] = lane_dict.get(status, 0) + 1
        role_dict = by_role.setdefault(role, {s: 0 for s in VALID_STATUSES})
        role_dict[status] = role_dict.get(status, 0) + 1
        priority_dict = by_priority.setdefault(priority, {s: 0 for s in VALID_STATUSES})
        priority_dict[status] = priority_dict.get(status, 0) + 1
    return {
        "schema": "thinkcell-work-queue-runner-summary/v1",
        "period": state.get("period"),
        "run_id": state.get("run_id"),
        "generated_at_utc": _utc_now(),
        "counts": counts,
        "by_lane": by_lane,
        "by_role": by_role,
        "by_priority": by_priority,
        "total": len(state.get("jobs", [])),
    }


def list_jobs(
    run_dir: Path,
    *,
    status: str | None = None,
    lane: str | None = None,
    role: str | None = None,
    priority: str | None = None,
) -> list[dict[str, Any]]:
    state = _load_state(run_dir)
    out: list[dict[str, Any]] = []
    for job in state.get("jobs", []):
        if status and job.get("status") != status:
            continue
        if lane and job.get("lane") != lane:
            continue
        if role and job.get("role") != role:
            continue
        if priority and job.get("priority") != priority:
            continue
        out.append(job)
    return out


def show_job(run_dir: Path, job_id: str) -> dict[str, Any]:
    state = _load_state(run_dir)
    return _find_job(state, job_id)


def summary_to_markdown(summary: dict[str, Any]) -> str:
    lines = [
        f"# Work Queue Runner Status - {summary['period']} - {summary['run_id']}",
        "",
        f"- Generated UTC: `{summary['generated_at_utc']}`",
        f"- Total jobs: {summary['total']}",
        "",
        "## Counts",
        "",
    ]
    for status in VALID_STATUSES:
        lines.append(f"- {status}: {summary['counts'].get(status, 0)}")
    lines.extend(
        [
            "",
            "## By Lane",
            "",
            "| Lane | planned | running | pass | fail | blocked |",
            "|---|---:|---:|---:|---:|---:|",
        ]
    )
    for lane, counts in sorted(summary["by_lane"].items()):
        lines.append(
            "| {lane} | {planned} | {running} | {passed} | {failed} | {blocked} |".format(
                lane=lane,
                planned=counts.get("planned", 0),
                running=counts.get("running", 0),
                passed=counts.get("pass", 0),
                failed=counts.get("fail", 0),
                blocked=counts.get("blocked", 0),
            )
        )
    return "\n".join(lines).rstrip() + "\n"


__all__ = [
    "ALLOWED_TRANSITIONS",
    "PROTECT_LANE",
    "TransitionEvent",
    "VALID_STATUSES",
    "WorkQueueRunnerError",
    "initialize_run",
    "list_jobs",
    "load_master_queue",
    "master_queue_path",
    "runner_run_root",
    "show_job",
    "status_summary",
    "summary_to_markdown",
    "transition_job",
]
