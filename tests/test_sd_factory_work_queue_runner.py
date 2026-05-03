from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.sd_factory.work_queue_runner import (
    PROTECT_LANE,
    VALID_STATUSES,
    WorkQueueRunnerError,
    initialize_run,
    list_jobs,
    show_job,
    status_summary,
    summary_to_markdown,
    transition_job,
)


@pytest.fixture
def fake_repo(tmp_path: Path) -> Path:
    period = "2026-Q9"
    queue_dir = tmp_path / "state" / "thinkcell_bridge" / "build_scaffold" / period
    queue_dir.mkdir(parents=True)
    queue = {
        "schema": "thinkcell-work-queue/v1",
        "period": period,
        "contract_count": 3,
        "job_count": 4,
        "jobs": [
            {
                "job_id": f"{period}.001.QTR_X.protect_proven_lane",
                "contract": "QTR_X",
                "role": "QA Gatekeeper",
                "priority": "P0",
                "lane": PROTECT_LANE,
                "status": "planned",
            },
            {
                "job_id": f"{period}.002.QTR_Y.seed_authoring",
                "contract": "QTR_Y",
                "role": "Think-cell Seedsmith",
                "priority": "P1",
                "lane": "L4 seed_authoring",
                "status": "planned",
            },
            {
                "job_id": f"{period}.003.QTR_Y.binding_proof",
                "contract": "QTR_Y",
                "role": "Binding Engineer",
                "priority": "P1",
                "lane": "L5 binding_proof",
                "status": "planned",
            },
            {
                "job_id": f"{period}.004.QTR_Z.seed_authoring",
                "contract": "QTR_Z",
                "role": "Think-cell Seedsmith",
                "priority": "P2",
                "lane": "L4 seed_authoring",
                "status": "planned",
            },
        ],
    }
    (queue_dir / "work_queue.json").write_text(json.dumps(queue, indent=2), encoding="utf-8")
    return tmp_path


def test_initialize_run_copies_master_into_run_directory(fake_repo: Path) -> None:
    run_dir = initialize_run("2026-Q9", "run-A", root=fake_repo)
    state = json.loads((run_dir / "state.json").read_text())

    assert run_dir.parent.name == "runner_runs"
    assert (run_dir / "events.jsonl").exists()
    assert state["period"] == "2026-Q9"
    assert state["run_id"] == "run-A"
    assert state["job_count"] == 4
    assert all(job["status"] == "planned" for job in state["jobs"])


def test_master_queue_is_not_modified_by_initialize_run(fake_repo: Path) -> None:
    master_path = (
        fake_repo / "state" / "thinkcell_bridge" / "build_scaffold" / "2026-Q9" / "work_queue.json"
    )
    before = master_path.read_text()
    initialize_run("2026-Q9", "run-B", root=fake_repo)
    after = master_path.read_text()
    assert before == after


def test_initialize_run_refuses_existing_run_directory(fake_repo: Path) -> None:
    initialize_run("2026-Q9", "run-C", root=fake_repo)
    with pytest.raises(WorkQueueRunnerError, match="already initialized"):
        initialize_run("2026-Q9", "run-C", root=fake_repo)


def test_transition_planned_to_running_to_pass_writes_evidence(fake_repo: Path) -> None:
    run_dir = initialize_run("2026-Q9", "run-pass", root=fake_repo)
    job_id = "2026-Q9.002.QTR_Y.seed_authoring"

    transition_job(run_dir, job_id, "running", actor="claude")
    job = transition_job(
        run_dir,
        job_id,
        "pass",
        actor="claude",
        note="seed names verified",
        evidence=["state/.../seed.pptx", "state/.../proof.json"],
    )

    assert job["status"] == "pass"
    assert len(job["transitions"]) == 2
    assert job["transitions"][0]["to_status"] == "running"
    assert job["transitions"][1]["to_status"] == "pass"
    assert "state/.../seed.pptx" in job["evidence"]
    events = (run_dir / "events.jsonl").read_text().strip().splitlines()
    assert len(events) == 2
    parsed = [json.loads(line) for line in events]
    assert parsed[0]["to_status"] == "running"
    assert parsed[1]["to_status"] == "pass"


def test_invalid_transition_raises(fake_repo: Path) -> None:
    run_dir = initialize_run("2026-Q9", "run-invalid", root=fake_repo)
    job_id = "2026-Q9.002.QTR_Y.seed_authoring"

    with pytest.raises(WorkQueueRunnerError, match="transition not allowed"):
        transition_job(run_dir, job_id, "pass")


def test_protect_lane_cannot_be_failed_without_explicit_flag(fake_repo: Path) -> None:
    run_dir = initialize_run("2026-Q9", "run-protect", root=fake_repo)
    job_id = "2026-Q9.001.QTR_X.protect_proven_lane"

    transition_job(run_dir, job_id, "running")
    with pytest.raises(WorkQueueRunnerError, match="protect_proven_lane"):
        transition_job(run_dir, job_id, "fail", note="oops")

    overridden = transition_job(
        run_dir,
        job_id,
        "fail",
        note="manual override",
        allow_protect_fail=True,
    )
    assert overridden["status"] == "fail"


def test_status_summary_counts_match(fake_repo: Path) -> None:
    run_dir = initialize_run("2026-Q9", "run-summary", root=fake_repo)
    transition_job(run_dir, "2026-Q9.002.QTR_Y.seed_authoring", "running")
    transition_job(run_dir, "2026-Q9.004.QTR_Z.seed_authoring", "blocked")

    summary = status_summary(run_dir)

    assert summary["counts"]["planned"] == 2
    assert summary["counts"]["running"] == 1
    assert summary["counts"]["blocked"] == 1
    assert summary["total"] == 4
    assert "by_lane" in summary
    assert "by_role" in summary

    md = summary_to_markdown(summary)
    assert "Work Queue Runner Status - 2026-Q9 - run-summary" in md


def test_list_jobs_filters_by_status_and_role(fake_repo: Path) -> None:
    run_dir = initialize_run("2026-Q9", "run-filter", root=fake_repo)
    transition_job(run_dir, "2026-Q9.002.QTR_Y.seed_authoring", "running")
    seedsmith_jobs = list_jobs(run_dir, role="Think-cell Seedsmith")
    running_jobs = list_jobs(run_dir, status="running")

    assert len(seedsmith_jobs) == 2
    assert len(running_jobs) == 1
    assert running_jobs[0]["job_id"] == "2026-Q9.002.QTR_Y.seed_authoring"


def test_show_job_returns_record(fake_repo: Path) -> None:
    run_dir = initialize_run("2026-Q9", "run-show", root=fake_repo)
    job = show_job(run_dir, "2026-Q9.001.QTR_X.protect_proven_lane")
    assert job["lane"] == PROTECT_LANE
    assert job["status"] == "planned"


def test_unblock_path_through_blocked_back_to_planned(fake_repo: Path) -> None:
    run_dir = initialize_run("2026-Q9", "run-unblock", root=fake_repo)
    job_id = "2026-Q9.004.QTR_Z.seed_authoring"
    transition_job(run_dir, job_id, "blocked", note="waiting on donor")
    transition_job(run_dir, job_id, "planned", note="donor available")
    job = show_job(run_dir, job_id)
    assert job["status"] == "planned"
    assert len(job["transitions"]) == 2


def test_valid_statuses_includes_expected_set() -> None:
    assert set(VALID_STATUSES) == {"planned", "running", "pass", "fail", "blocked"}
