"""Tests for tcrender.narrative -- Claude-grounded narrative augmentation.

What's exercised at import time (no network, no real claude CLI):
    1. DirectorContext serializes a numbers block + full context summary that
       contains the director's name, scope, period, key numbers.
    2. generate_exec_summary, generate_risks_outlook, generate_chart_insight
       parse mocked Claude output into the expected shape.
    3. Cache file path is content-hashed and a second call is a no-op.
    4. NarrativeError is raised on CLI failure / timeout / preamble / JSON.

What runs only when NARRATIVE_LIVE=1 (real ``claude -p`` invocation):
    5. test_live_smoke -- a tiny "say OK" prompt round-trips through the
       real claude CLI.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any

import pytest

from tcrender.narrative import (
    DEFAULT_TIMEOUT_SECONDS,
    DirectorContext,
    NarrativeError,
    _build_exec_summary_prompt,
    _build_risks_prompt,
    _cache_path,
    _hash_inputs,
    _strip_ansi,
    generate_chart_insight,
    generate_exec_summary,
    generate_risks_outlook,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def jesper_ctx() -> DirectorContext:
    return DirectorContext(
        name="Jesper Tyrer",
        slug="Jesper-Tyrer",
        period="2026-Q2",
        scope_label="APAC",
        closeable_arr_eur=5_132_738.0,
        renewal_acv_eur=126_671.0,
        beyond_quarter_arr_eur=37_969_921.0,
        stage5_plus_share_pct=14.0,
        largest_account_share_pct=22.0,
        risk_claims=("only 14% of pipeline in Stage 5+ -- quarter coverage at risk",),
        action_items=(
            "17 open Land+Expand opps >730 days old with no activity -- EUR 10.2M stale ARR",
            "6 Stage 3+ opps >= EUR 500k missing Commercial Approval -- EUR 10.2M ARR exposure",
        ),
        top_deals=(
            {
                "account": "Danantara",
                "stage": "3 - Engagement",
                "arr_eur": 1_783_128.0,
                "owner": "Jesper Tyrer",
            },
            {
                "account": "Lembaga Tabung Haji",
                "stage": "6 - Contracting",
                "arr_eur": 1_090_761.0,
                "owner": "Edwina Chow",
            },
        ),
        top_industry="Asset Management",
        wins_qtd_eur=420_000.0,
        losses_qtd_eur=130_000.0,
        stale_activity_arr_eur=10_200_000.0,
    )


_GOOD_EXEC_OUTPUT = """LEFT (HIGHLIGHTS):
EUR 5.1M closeable Land+Expand ARR for 2026-Q2, with EUR 2.5M already in Stage 6 Contracting.
Lembaga Tabung Haji EUR 1.1M deal in Contracting at 90% probability anchors the quarter.
EUR 38.0M open pipeline beyond 2026-Q2 gives clear forward coverage into 2026-Q3.

RIGHT (RISKS):
EUR 10.2M of stale ARR sits in 17 zombie deals with no activity in 60 days.
Only 14% of pipeline is Stage 5 or higher, leaving quarter coverage thin.
Six Stage 3+ deals over EUR 500k are missing Commercial Approval, exposing EUR 10.2M.
"""

_GOOD_RISKS_OUTPUT = """EUR 10.2M of stale ARR in 17 zombie deals -- review and disqualify by EOM.
Only 14% of pipeline ARR sits in Stage 5+, putting 2026-Q2 close coverage at risk.
Six Stage 3+ deals over EUR 500k lack Commercial Approval -- mandatory before close.
EUR 38.0M beyond-quarter pipe is healthy but skewed to Engagement; advance to Preferred.
"""

_GOOD_INSIGHT_OUTPUT = (
    "Asset Management at Stage 3 holds EUR 2.3M, the single largest open ARR cell."
)

_PREAMBLE_OUTPUT = """Sure, here is a 3-bullet exec summary:

LEFT (HIGHLIGHTS):
EUR 5.1M closeable Land+Expand ARR for 2026-Q2 with strong Contracting position.
Lembaga Tabung Haji EUR 1.1M deal at 90% probability anchors the quarter.
EUR 38.0M open pipeline gives forward coverage.

RIGHT (RISKS):
EUR 10.2M stale ARR across 17 zombie deals with no activity in 60 days.
Only 14% of pipeline is Stage 5+, leaving coverage thin.
Six deals over EUR 500k missing Commercial Approval.
"""


def _make_completed(stdout: str, returncode: int = 0, stderr: str = "") -> Any:
    completed = subprocess.CompletedProcess(args=["claude", "-p", "x"], returncode=returncode)
    completed.stdout = stdout
    completed.stderr = stderr
    return completed


# Use an existing system binary as the "claude" path so the existence
# check inside _invoke_claude passes without patching Path.exists (which
# would also accidentally satisfy cache-file reads).
_FAKE_CLAUDE_BIN = "/bin/sh"


@pytest.fixture
def mock_claude_ok(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    state: dict[str, Any] = {"call_count": 0, "last_prompt": None, "stdouts": []}

    def fake_run(cmd: Any, **kwargs: Any) -> Any:
        state["call_count"] += 1
        state["last_prompt"] = cmd[-1] if isinstance(cmd, list) else None
        state["last_cmd"] = cmd
        prompt = state["last_prompt"] or ""
        if "LEFT (HIGHLIGHTS)" in prompt and "RIGHT (RISKS)" in prompt:
            stdout = _GOOD_EXEC_OUTPUT
        elif "risk / outlook bullets" in prompt:
            stdout = _GOOD_RISKS_OUTPUT
        else:
            stdout = _GOOD_INSIGHT_OUTPUT
        # Add the ANSI title-escape prefix the real CLI emits.
        stdout = "\x1b]0;claude\x07" + stdout
        state["stdouts"].append(stdout)
        return _make_completed(stdout)

    monkeypatch.setattr(subprocess, "run", fake_run)
    return state


# ---------------------------------------------------------------------------
# DirectorContext
# ---------------------------------------------------------------------------


def test_director_context_numbers_block_contains_director_signals(
    jesper_ctx: DirectorContext,
) -> None:
    block = jesper_ctx.numbers_block()
    assert "Jesper Tyrer" in block
    assert "APAC" in block
    assert "2026-Q2" in block
    assert "EUR 5.1M" in block  # closeable
    assert "EUR 38.0M" in block  # beyond-quarter
    assert "Stage 5+ share" in block
    assert "Largest-account concentration" in block


def test_director_context_summary_contains_top_deals_and_actions(
    jesper_ctx: DirectorContext,
) -> None:
    summary = jesper_ctx.context_summary()
    assert "Danantara" in summary
    assert "Lembaga Tabung Haji" in summary
    assert "zombie" in summary.lower() or "stale ARR" in summary
    assert "Commercial Approval" in summary


def test_director_context_summary_is_ascii_only(jesper_ctx: DirectorContext) -> None:
    summary = jesper_ctx.context_summary()
    summary.encode("ascii")  # raises if any non-ASCII slipped through


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def test_strip_ansi_removes_title_prefix() -> None:
    raw = "\x1b]0;claude\x07OK\n"
    assert _strip_ansi(raw).strip() == "OK"


def test_hash_inputs_is_stable_and_input_sensitive(jesper_ctx: DirectorContext) -> None:
    p1 = "prompt-A"
    p2 = "prompt-B"
    s1 = jesper_ctx.context_summary()
    h1a = _hash_inputs(p1, s1)
    h1b = _hash_inputs(p1, s1)
    h2 = _hash_inputs(p2, s1)
    assert h1a == h1b
    assert h1a != h2
    assert len(h1a) == 64  # sha256 hex


def test_cache_path_uses_slug_period_kind_and_hash(tmp_path: Path) -> None:
    p = _cache_path(
        cache_dir=tmp_path,
        slug="Jesper-Tyrer",
        period="2026-Q2",
        binding_kind="exec_summary",
        digest="0" * 64,
    )
    assert p.parent == tmp_path
    assert p.name.startswith("Jesper-Tyrer-2026-Q2-exec_summary-")
    assert p.suffix == ".txt"
    assert "0" * 16 in p.name


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------


def test_exec_summary_prompt_grounds_in_context(jesper_ctx: DirectorContext) -> None:
    prompt = _build_exec_summary_prompt(jesper_ctx)
    assert "Jesper Tyrer" in prompt
    assert "APAC" in prompt
    assert "2026-Q2" in prompt
    assert "EUR 5.1M" in prompt
    assert "LEFT (HIGHLIGHTS)" in prompt
    assert "RIGHT (RISKS)" in prompt
    # Length cap discipline: the prompt-context block should stay under ~200 tokens.
    assert len(prompt.split()) < 600  # generous cap; real prompt is ~250 words


def test_risks_prompt_grounds_in_context(jesper_ctx: DirectorContext) -> None:
    prompt = _build_risks_prompt(jesper_ctx)
    assert "Jesper Tyrer" in prompt
    assert "APAC" in prompt
    assert "2026-Q2" in prompt
    assert "highest-impact risk" in prompt


# ---------------------------------------------------------------------------
# generate_exec_summary
# ---------------------------------------------------------------------------


def test_generate_exec_summary_returns_three_bullets_each(
    jesper_ctx: DirectorContext, mock_claude_ok: dict[str, Any], tmp_path: Path
) -> None:
    left, right = generate_exec_summary(jesper_ctx, cache_dir=tmp_path, claude_bin=_FAKE_CLAUDE_BIN)
    assert len(left) == 3
    assert len(right) == 3
    for bullet in left + right:
        assert isinstance(bullet, str)
        assert 4 <= len(bullet.split()) <= 22 + 1  # word cap + final period
    # Specific signals that should land verbatim from mocked output.
    assert any("EUR 5.1M" in b for b in left)
    assert any("EUR 10.2M" in b for b in right)


def test_generate_exec_summary_caches_by_content_hash(
    jesper_ctx: DirectorContext, mock_claude_ok: dict[str, Any], tmp_path: Path
) -> None:
    left1, right1 = generate_exec_summary(
        jesper_ctx, cache_dir=tmp_path, claude_bin=_FAKE_CLAUDE_BIN
    )
    initial = mock_claude_ok["call_count"]
    left2, right2 = generate_exec_summary(
        jesper_ctx, cache_dir=tmp_path, claude_bin=_FAKE_CLAUDE_BIN
    )
    assert mock_claude_ok["call_count"] == initial  # second call is a no-op
    assert left1 == left2
    assert right1 == right2


def test_generate_exec_summary_strips_preamble(
    jesper_ctx: DirectorContext, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def fake_run(cmd: Any, **kwargs: Any) -> Any:
        return _make_completed("\x1b]0;claude\x07" + _PREAMBLE_OUTPUT)

    monkeypatch.setattr(subprocess, "run", fake_run)

    left, right = generate_exec_summary(jesper_ctx, cache_dir=tmp_path, claude_bin=_FAKE_CLAUDE_BIN)
    for bullet in left + right:
        lower = bullet.lower()
        assert not lower.startswith("here")
        assert not lower.startswith("sure")
        assert "left (" not in lower
        assert "right (" not in lower


def test_generate_exec_summary_raises_on_missing_sections(
    jesper_ctx: DirectorContext, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def fake_run(cmd: Any, **kwargs: Any) -> Any:
        return _make_completed("just three lines\nwith no markers\nat all\n")

    monkeypatch.setattr(subprocess, "run", fake_run)

    with pytest.raises(NarrativeError):
        generate_exec_summary(jesper_ctx, cache_dir=tmp_path, claude_bin=_FAKE_CLAUDE_BIN)


def test_generate_exec_summary_raises_on_json(
    jesper_ctx: DirectorContext, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def fake_run(cmd: Any, **kwargs: Any) -> Any:
        return _make_completed(
            'LEFT (HIGHLIGHTS):\n{"left": ["a","b","c"]}\nRIGHT (RISKS):\n{"right": []}\n'
        )

    monkeypatch.setattr(subprocess, "run", fake_run)

    with pytest.raises(NarrativeError):
        generate_exec_summary(jesper_ctx, cache_dir=tmp_path, claude_bin=_FAKE_CLAUDE_BIN)


# ---------------------------------------------------------------------------
# generate_risks_outlook
# ---------------------------------------------------------------------------


def test_generate_risks_outlook_returns_dash_prefixed_bullets(
    jesper_ctx: DirectorContext, mock_claude_ok: dict[str, Any], tmp_path: Path
) -> None:
    body = generate_risks_outlook(jesper_ctx, cache_dir=tmp_path, claude_bin=_FAKE_CLAUDE_BIN)
    lines = body.splitlines()
    assert 3 <= len(lines) <= 5
    for line in lines:
        assert line.startswith("- ")
        assert len(line[2:].split()) <= 26
    assert "stale" in body.lower() or "zombie" in body.lower()


def test_generate_risks_outlook_caches(
    jesper_ctx: DirectorContext, mock_claude_ok: dict[str, Any], tmp_path: Path
) -> None:
    body1 = generate_risks_outlook(jesper_ctx, cache_dir=tmp_path, claude_bin=_FAKE_CLAUDE_BIN)
    initial = mock_claude_ok["call_count"]
    body2 = generate_risks_outlook(jesper_ctx, cache_dir=tmp_path, claude_bin=_FAKE_CLAUDE_BIN)
    assert mock_claude_ok["call_count"] == initial
    assert body1 == body2


# ---------------------------------------------------------------------------
# generate_chart_insight
# ---------------------------------------------------------------------------


def test_generate_chart_insight_returns_one_sentence(
    jesper_ctx: DirectorContext, mock_claude_ok: dict[str, Any], tmp_path: Path
) -> None:
    table = [
        ["", "Asset Management", "Pension"],
        ["3 - Engagement", 2_345_092, 1_000_000],
        ["6 - Contracting", 2_493_466, 0],
    ]
    insight = generate_chart_insight(
        "S16_StageByIndustry",
        table,
        jesper_ctx,
        cache_dir=tmp_path,
        claude_bin=_FAKE_CLAUDE_BIN,
    )
    assert isinstance(insight, str)
    assert "\n" not in insight  # single line
    assert len(insight.split()) <= 28 + 1
    assert "EUR" in insight or "Asset Management" in insight


def test_generate_chart_insight_rejects_json(
    jesper_ctx: DirectorContext, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def fake_run(cmd: Any, **kwargs: Any) -> Any:
        return _make_completed('{"insight": "x"}')

    monkeypatch.setattr(subprocess, "run", fake_run)

    with pytest.raises(NarrativeError):
        generate_chart_insight(
            "S16_StageByIndustry",
            [["a", "b"], [1, 2]],
            jesper_ctx,
            cache_dir=tmp_path,
            claude_bin=_FAKE_CLAUDE_BIN,
        )


# ---------------------------------------------------------------------------
# CLI failure paths
# ---------------------------------------------------------------------------


def test_cli_nonzero_exit_raises_narrative_error(
    jesper_ctx: DirectorContext, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def fake_run(cmd: Any, **kwargs: Any) -> Any:
        return _make_completed("", returncode=1, stderr="auth failed")

    monkeypatch.setattr(subprocess, "run", fake_run)
    # Make claude binary lookup succeed without globally lying about Path.exists
    # (which would also fool the cache miss check and raise FileNotFoundError).
    monkeypatch.setattr("shutil.which", lambda name: "/usr/local/bin/claude")

    with pytest.raises(NarrativeError) as exc:
        generate_exec_summary(jesper_ctx, cache_dir=tmp_path)
    assert "exit=1" in str(exc.value)


def test_cli_timeout_raises_narrative_error(
    jesper_ctx: DirectorContext, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def fake_run(cmd: Any, **kwargs: Any) -> Any:
        raise subprocess.TimeoutExpired(cmd=cmd, timeout=kwargs.get("timeout", 60))

    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr("shutil.which", lambda name: "/usr/local/bin/claude")

    with pytest.raises(NarrativeError) as exc:
        generate_risks_outlook(jesper_ctx, cache_dir=tmp_path, timeout=5.0)
    assert "timed out" in str(exc.value)


def test_cli_missing_binary_raises_narrative_error(
    jesper_ctx: DirectorContext, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(Path, "exists", lambda self: False, raising=False)
    monkeypatch.setattr("shutil.which", lambda name: None)
    with pytest.raises(NarrativeError) as exc:
        generate_risks_outlook(jesper_ctx, cache_dir=tmp_path, claude_bin="/nonexistent/claude")
    assert "not found" in str(exc.value)


# ---------------------------------------------------------------------------
# Live smoke (gated behind NARRATIVE_LIVE=1)
# ---------------------------------------------------------------------------

LIVE = os.environ.get("NARRATIVE_LIVE") == "1"


@pytest.mark.skipif(not LIVE, reason="live narrative gated behind NARRATIVE_LIVE=1")
def test_live_smoke(tmp_path: Path) -> None:
    """Round-trip through real ``claude -p`` with a minimal prompt."""
    from tcrender.narrative import _invoke_claude

    out = _invoke_claude(
        "Reply with exactly one word: OK",
        claude_bin="/Users/test/.local/bin/claude",
        timeout=DEFAULT_TIMEOUT_SECONDS,
    )
    assert "OK" in out.upper()


@pytest.mark.skipif(not LIVE, reason="live narrative gated behind NARRATIVE_LIVE=1")
def test_live_exec_summary_for_jesper(tmp_path: Path, jesper_ctx: DirectorContext) -> None:
    """End-to-end real-Claude exec summary for Jesper-Tyrer."""
    left, right = generate_exec_summary(jesper_ctx, cache_dir=tmp_path)
    assert len(left) >= 1 and len(left) <= 3
    assert len(right) >= 1 and len(right) <= 3
    full = " ".join(left + right)
    # Must reference at least one of the grounding numbers.
    assert any(token in full for token in ("5.1M", "10.2M", "38.0M", "Stage"))
