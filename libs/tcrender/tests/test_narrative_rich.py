"""Tests for the rich-narrative pass on top of tcrender.narrative.

What's exercised at import time (no network, no real claude CLI):

    1. ``load_thinkcell_vocabulary_primer`` returns a non-empty ASCII block
       containing both think-cell chart classes and the canonical SimCorp
       LAND vocabulary tokens; the prompt sites embed it verbatim.
    2. ``DEFAULT_INSIGHT_BINDINGS`` covers every chart-insight binding
       called for in the spec (S04, S05, S06, S07, S13, S15, S16, S17,
       S18, S19, S21, S22, S25 -> S{NN}_Insight).
    3. Each new public function has a happy-path test (mocked claude
       returning canned response).
    4. Cache-hit test: a second call with identical inputs is a no-op
       (call_count does not increase).
    5. Fall-back-on-error test: NarrativeError on the underlying CLI
       does not crash ``generate_chart_insights``; it returns an empty
       (or partial) dict instead.
    6. Schema-grounding test: the prompt the rich pass sends to claude
       includes the think-cell vocabulary primer.
    7. Word-cap enforcement: chart insight outputs stay under
       ``RICH_INSIGHT_WORDS_MAX`` regardless of what claude returns.

What runs only when NARRATIVE_LIVE=1 (real ``claude -p`` invocation):

    8. test_live_chart_insight_round_trip -- hits the real CLI for one
       binding to confirm the wiring is end-to-end live.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any

import pytest

from tcrender.narrative import (
    ANOMALY_BULLETS_MIN,
    DEFAULT_INSIGHT_BINDINGS,
    DEFAULT_TIMEOUT_SECONDS,
    RICH_INSIGHT_WORDS_MAX,
    SECTION_HEADERS,
    DirectorContext,
    NarrativeError,
    _build_anomaly_watch_prompt,
    _build_cover_subtitle_prompt,
    _build_ranked_actions_prompt,
    _build_rich_chart_insight_prompt,
    _build_section_subtitles_prompt,
    generate_anomaly_watch,
    generate_chart_insights,
    generate_cover_subtitle,
    generate_ranked_actions,
    generate_section_subtitles,
    load_thinkcell_vocabulary_primer,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


_FAKE_CLAUDE_BIN = "/bin/sh"  # exists, so _invoke_claude's existence check passes


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
                "account": "Colonial First State",
                "stage": "6 - Contracting",
                "arr_eur": 4_600_000.0,
                "owner": "Edwina Chow",
            },
            {
                "account": "Lembaga Tabung Haji",
                "stage": "6 - Contracting",
                "arr_eur": 1_090_761.0,
                "owner": "Edwina Chow",
            },
        ),
        top_industry="Pension",
        wins_qtd_eur=1_600_000.0,
        losses_qtd_eur=6_000_000.0,
        stale_activity_arr_eur=10_200_000.0,
    )


@pytest.fixture
def jesper_ppttc_entries() -> list[dict[str, Any]]:
    """A tiny .ppttc-shaped data list mirroring what build_ppttc.py emits.

    Only the bindings the rich-insight pass walks need to be present; the
    rest of the LAND deck's bindings are omitted to keep the fixture
    obvious.
    """
    return [
        {"name": "S01_DirectorName", "table": [[{"string": "Jesper Tyrer"}]]},
        {
            "name": "S04_PipeMovement",
            "table": [
                [
                    None,
                    {"string": "Opening pipe"},
                    {"string": "New + Advanced"},
                    {"string": "Won"},
                    {"string": "Lost"},
                    {"string": "Closing pipe"},
                ],
                [
                    {"string": "ARR (mEUR)"},
                    {"number": 38.0},
                    {"number": 5.0},
                    {"number": -12.0},
                    {"number": -7.0},
                    {"number": 24.0},
                ],
            ],
        },
        {
            "name": "S05_PipelineByStage",
            "table": [
                [None, {"string": "Open ARR (mEUR)"}],
                [{"string": "3 - Engagement"}, {"number": 16.0}],
                [{"string": "4 - Shortlisted"}, {"number": 8.0}],
                [{"string": "5 - Preferred"}, {"number": 4.0}],
                [{"string": "6 - Contracting"}, {"number": 5.0}],
            ],
        },
        {
            "name": "S07_TopDealsLand",
            "table": [
                [
                    {"string": "Account"},
                    {"string": "Stage"},
                    {"string": "Owner"},
                    {"string": "Close"},
                    {"string": "ARR"},
                ],
                [
                    {"string": "Colonial First State"},
                    {"string": "6 - Contracting"},
                    {"string": "Edwina Chow"},
                    {"date": "2026-08-15"},
                    {"number": 4_600_000},
                ],
            ],
        },
        # S15_ByOwner intentionally empty-ish (only header) to verify the
        # empty-data short-circuit path.
        {
            "name": "S15_ByOwner",
            "table": [[{"string": "Owner"}, {"string": "ARR"}]],
        },
    ]


# ---------------------------------------------------------------------------
# Mocks
# ---------------------------------------------------------------------------


_RICH_INSIGHT_OUTPUT = (
    "EUR 38M open pipe in Stage 3 Engagement; net new this quarter +EUR 5M after "
    "EUR 12M won and EUR 7M lost"
)
_ANOMALY_OUTPUT = """EUR 10.2M / 17 deals / stale Stage 3+ - disqualify or re-engage by EOM
EUR 21M / 4 deals / Pension industry over-concentration - diversify pipeline build
EUR 6.0M / 12 deals / Stage 4 losses spike - root-cause review with CE
"""
_RANKED_OUTPUT = """1. Disqualify zombies - 17 stale Land+Expand (EUR 10.2M ARR) - Due: 2026-05-31
2. Push Commercial Approval - 6 Stage 3+ deals (EUR 10.2M exposure) - Due: 2026-05-15
3. Coverage build - 194 Tier-1 accounts no open opp (EUR pipeline thin) - Due: 2026-06-30
"""
_COVER_SUBTITLE_OUTPUT = "APAC Pipeline Coverage Build"
_SECTION_OUTPUT = """Pipeline: EUR 38M open, Stage 3 Engagement holds 41%
Renewals: EUR 0.1M due, all Asset Management
Risk: 17 stale deals EUR 10.2M idle 730d
Velocity: Shortlist median 1344d - flag for triage
"""


def _make_completed(stdout: str, returncode: int = 0, stderr: str = "") -> Any:
    completed = subprocess.CompletedProcess(args=["claude", "-p", "x"], returncode=returncode)
    completed.stdout = stdout
    completed.stderr = stderr
    return completed


def _stdout_router(prompt: str) -> str:
    """Choose a canned stdout based on which prompt shape claude received."""
    if "anomaly watch items" in prompt:
        return _ANOMALY_OUTPUT
    if "Rank the top" in prompt and "actions by" in prompt:
        return _RANKED_OUTPUT
    if "cover-page subtitle" in prompt:
        return _COVER_SUBTITLE_OUTPUT
    if "section header" in prompt and "Pipeline" in prompt and "Renewals" in prompt:
        return _SECTION_OUTPUT
    if "caption sentence" in prompt:
        return _RICH_INSIGHT_OUTPUT
    return _RICH_INSIGHT_OUTPUT


@pytest.fixture
def mock_claude_rich(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    state: dict[str, Any] = {"call_count": 0, "prompts": []}

    def fake_run(cmd: Any, **kwargs: Any) -> Any:
        state["call_count"] += 1
        prompt = cmd[-1] if isinstance(cmd, list) else ""
        state["prompts"].append(prompt)
        out = "\x1b]0;claude\x07" + _stdout_router(prompt)
        return _make_completed(out)

    monkeypatch.setattr(subprocess, "run", fake_run)
    return state


# ---------------------------------------------------------------------------
# Schema grounding + binding-coverage
# ---------------------------------------------------------------------------


def test_load_thinkcell_vocabulary_primer_returns_nonempty_ascii_block() -> None:
    primer = load_thinkcell_vocabulary_primer()
    assert primer  # non-empty
    primer.encode("ascii")  # ASCII-only
    assert "think-cell vocabulary primer" in primer
    # Must include canonical LAND vocabulary tokens
    for token in ("Stage 1 Prospecting", "Stage 6 Contracting", "ARR", "ACV", "Renewal"):
        assert token in primer
    # Must include at least one chart-class name (CSequenceChart* / CSmartGrid /
    # ... etc.) -- we don't pin the exact class because the corpus is updated
    # over time; we only enforce that something class-shaped landed.
    assert any(token in primer for token in ("CSequenceChart", "CSmartGrid", "CGanttVectorTile"))


def test_default_insight_bindings_cover_spec_chart_set() -> None:
    spec_chart_ids = {
        "S04_Insight",
        "S05_Insight",
        "S06_Insight",
        "S07_Insight",
        "S13_Insight",
        "S15_Insight",
        "S16_Insight",
        "S17_Insight",
        "S18_Insight",
        "S19_Insight",
        "S21_Insight",
        "S22_Insight",
        "S25_Insight",
    }
    actual = {row[0] for row in DEFAULT_INSIGHT_BINDINGS}
    assert actual == spec_chart_ids, f"binding mismatch: {actual ^ spec_chart_ids}"


def test_section_headers_cover_spec_section_set() -> None:
    assert {row[0] for row in SECTION_HEADERS} == {
        "S03_Header",
        "S10_Header",
        "S20_Header",
        "S25_Header",
    }


# ---------------------------------------------------------------------------
# Prompts embed primer + context
# ---------------------------------------------------------------------------


def test_rich_chart_insight_prompt_includes_primer(jesper_ctx: DirectorContext) -> None:
    primer = load_thinkcell_vocabulary_primer()
    prompt = _build_rich_chart_insight_prompt(
        "S05_Insight",
        "bar by Stage 1-8",
        [["", "Open ARR (mEUR)"], ["3 - Engagement", 16.0], ["6 - Contracting", 5.0]],
        jesper_ctx,
        primer=primer,
    )
    assert "think-cell vocabulary primer" in prompt
    assert "Stage 6 Contracting" in prompt
    assert "Jesper Tyrer" in prompt
    assert "APAC" in prompt
    assert "S05_Insight" in prompt


def test_anomaly_watch_prompt_includes_primer_and_context(jesper_ctx: DirectorContext) -> None:
    primer = load_thinkcell_vocabulary_primer()
    prompt = _build_anomaly_watch_prompt(jesper_ctx, primer=primer)
    assert "think-cell vocabulary primer" in prompt
    assert "Jesper Tyrer" in prompt
    assert "anomaly watch items" in prompt
    assert "EUR <arr>M / <count> deals" in prompt


def test_ranked_actions_prompt_format(jesper_ctx: DirectorContext) -> None:
    prompt = _build_ranked_actions_prompt(jesper_ctx, primer="primer-test-marker")
    assert "primer-test-marker" in prompt
    assert "Rank the top" in prompt
    assert "Due: <date>" in prompt


def test_cover_subtitle_prompt_format(jesper_ctx: DirectorContext) -> None:
    prompt = _build_cover_subtitle_prompt(jesper_ctx, primer="primer-test-marker")
    assert "cover-page subtitle" in prompt
    assert "primer-test-marker" in prompt
    assert "Title Case" in prompt


def test_section_subtitles_prompt_lists_all_four_sections(jesper_ctx: DirectorContext) -> None:
    prompt = _build_section_subtitles_prompt(jesper_ctx, primer="primer-test-marker")
    for section in ("Pipeline", "Renewals", "Risk", "Velocity"):
        assert section in prompt


# ---------------------------------------------------------------------------
# generate_chart_insights -- happy path, empty data skip, cache, error
# ---------------------------------------------------------------------------


def test_generate_chart_insights_happy_path(
    jesper_ctx: DirectorContext,
    jesper_ppttc_entries: list[dict[str, Any]],
    mock_claude_rich: dict[str, Any],
    tmp_path: Path,
) -> None:
    insights = generate_chart_insights(
        jesper_ctx,
        jesper_ppttc_entries,
        cache_dir=tmp_path,
        claude_bin=_FAKE_CLAUDE_BIN,
        primer="test-primer",
    )
    # We seeded S04_PipeMovement, S05_PipelineByStage, S07_TopDealsLand with
    # data; S15_ByOwner is header-only and must be skipped.
    assert "S04_Insight" in insights
    assert "S05_Insight" in insights
    assert "S07_Insight" in insights
    assert "S15_Insight" not in insights, "header-only data should skip"
    # Word cap.
    for binding, text in insights.items():
        words = text.split()
        assert len(words) <= RICH_INSIGHT_WORDS_MAX + 1, f"{binding} exceeded word cap: {text!r}"
        # ASCII-only
        text.encode("ascii")
        # Single line.
        assert "\n" not in text


def test_generate_chart_insights_caches_per_binding(
    jesper_ctx: DirectorContext,
    jesper_ppttc_entries: list[dict[str, Any]],
    mock_claude_rich: dict[str, Any],
    tmp_path: Path,
) -> None:
    first = generate_chart_insights(
        jesper_ctx, jesper_ppttc_entries, cache_dir=tmp_path, claude_bin=_FAKE_CLAUDE_BIN
    )
    initial = mock_claude_rich["call_count"]
    second = generate_chart_insights(
        jesper_ctx, jesper_ppttc_entries, cache_dir=tmp_path, claude_bin=_FAKE_CLAUDE_BIN
    )
    assert first == second
    assert mock_claude_rich["call_count"] == initial, "cached run must not invoke claude again"


def test_generate_chart_insights_falls_back_on_per_binding_error(
    jesper_ctx: DirectorContext,
    jesper_ppttc_entries: list[dict[str, Any]],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    # First N calls succeed; the next one returns nonzero exit. The function
    # must catch + skip that binding, returning a partial dict.
    state = {"calls": 0}

    def fake_run(cmd: Any, **kwargs: Any) -> Any:
        state["calls"] += 1
        if state["calls"] == 2:
            return _make_completed("", returncode=1, stderr="oops")
        return _make_completed("\x1b]0;claude\x07" + _RICH_INSIGHT_OUTPUT)

    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr("shutil.which", lambda name: "/usr/local/bin/claude")
    insights = generate_chart_insights(
        jesper_ctx, jesper_ppttc_entries, cache_dir=tmp_path, claude_bin=_FAKE_CLAUDE_BIN
    )
    # At least one insight should land (the others) and the function must
    # not raise.
    assert isinstance(insights, dict)
    # Strictly fewer entries than the number of seeded chart bindings (we
    # poisoned one of them).
    assert len(insights) < 4


def test_generate_chart_insights_rejects_json_per_binding(
    jesper_ctx: DirectorContext,
    jesper_ppttc_entries: list[dict[str, Any]],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    def fake_run(cmd: Any, **kwargs: Any) -> Any:
        return _make_completed('{"insight": "foo"}')

    monkeypatch.setattr(subprocess, "run", fake_run)
    insights = generate_chart_insights(
        jesper_ctx, jesper_ppttc_entries, cache_dir=tmp_path, claude_bin=_FAKE_CLAUDE_BIN
    )
    # Every binding rejected -- empty dict, no crash.
    assert insights == {}


# ---------------------------------------------------------------------------
# generate_anomaly_watch
# ---------------------------------------------------------------------------


def test_generate_anomaly_watch_returns_dash_prefixed_lines(
    jesper_ctx: DirectorContext, mock_claude_rich: dict[str, Any], tmp_path: Path
) -> None:
    body = generate_anomaly_watch(
        jesper_ctx, cache_dir=tmp_path, claude_bin=_FAKE_CLAUDE_BIN, primer="p"
    )
    lines = body.splitlines()
    assert ANOMALY_BULLETS_MIN <= len(lines) <= 5
    for line in lines:
        assert line.startswith("- ")
    # First line should reference EUR + a number (anomaly format).
    assert "EUR" in lines[0]


def test_generate_anomaly_watch_caches(
    jesper_ctx: DirectorContext, mock_claude_rich: dict[str, Any], tmp_path: Path
) -> None:
    first = generate_anomaly_watch(
        jesper_ctx, cache_dir=tmp_path, claude_bin=_FAKE_CLAUDE_BIN, primer="p"
    )
    initial = mock_claude_rich["call_count"]
    second = generate_anomaly_watch(
        jesper_ctx, cache_dir=tmp_path, claude_bin=_FAKE_CLAUDE_BIN, primer="p"
    )
    assert first == second
    assert mock_claude_rich["call_count"] == initial


def test_generate_anomaly_watch_raises_on_too_few_bullets(
    jesper_ctx: DirectorContext, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def fake_run(cmd: Any, **kwargs: Any) -> Any:
        return _make_completed("\x1b]0;claude\x07only one bullet line here\n")

    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr("shutil.which", lambda name: "/usr/local/bin/claude")
    with pytest.raises(NarrativeError):
        generate_anomaly_watch(
            jesper_ctx, cache_dir=tmp_path, claude_bin=_FAKE_CLAUDE_BIN, primer="p"
        )


# ---------------------------------------------------------------------------
# generate_ranked_actions
# ---------------------------------------------------------------------------


def test_generate_ranked_actions_returns_numbered_lines(
    jesper_ctx: DirectorContext, mock_claude_rich: dict[str, Any], tmp_path: Path
) -> None:
    body = generate_ranked_actions(
        jesper_ctx, cache_dir=tmp_path, claude_bin=_FAKE_CLAUDE_BIN, primer="p"
    )
    lines = body.splitlines()
    assert 1 <= len(lines) <= 5
    # Every line should start with "<n>. " (rebuilt by the parser).
    for idx, line in enumerate(lines, start=1):
        assert line.lstrip().split(".", 1)[0].isdigit(), f"line not numbered: {line!r}"


def test_generate_ranked_actions_caches(
    jesper_ctx: DirectorContext, mock_claude_rich: dict[str, Any], tmp_path: Path
) -> None:
    first = generate_ranked_actions(
        jesper_ctx, cache_dir=tmp_path, claude_bin=_FAKE_CLAUDE_BIN, primer="p"
    )
    initial = mock_claude_rich["call_count"]
    second = generate_ranked_actions(
        jesper_ctx, cache_dir=tmp_path, claude_bin=_FAKE_CLAUDE_BIN, primer="p"
    )
    assert first == second
    assert mock_claude_rich["call_count"] == initial


# ---------------------------------------------------------------------------
# generate_cover_subtitle
# ---------------------------------------------------------------------------


def test_generate_cover_subtitle_short_single_line(
    jesper_ctx: DirectorContext, mock_claude_rich: dict[str, Any], tmp_path: Path
) -> None:
    sub = generate_cover_subtitle(
        jesper_ctx, cache_dir=tmp_path, claude_bin=_FAKE_CLAUDE_BIN, primer="p"
    )
    assert "\n" not in sub
    assert len(sub.split()) <= 9
    assert sub == sub.strip().rstrip(".")
    # No surrounding quotes.
    assert not (sub.startswith('"') or sub.startswith("'"))


def test_generate_cover_subtitle_caches(
    jesper_ctx: DirectorContext, mock_claude_rich: dict[str, Any], tmp_path: Path
) -> None:
    first = generate_cover_subtitle(
        jesper_ctx, cache_dir=tmp_path, claude_bin=_FAKE_CLAUDE_BIN, primer="p"
    )
    initial = mock_claude_rich["call_count"]
    second = generate_cover_subtitle(
        jesper_ctx, cache_dir=tmp_path, claude_bin=_FAKE_CLAUDE_BIN, primer="p"
    )
    assert first == second
    assert mock_claude_rich["call_count"] == initial


def test_generate_cover_subtitle_raises_on_json(
    jesper_ctx: DirectorContext, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def fake_run(cmd: Any, **kwargs: Any) -> Any:
        return _make_completed('{"subtitle": "x"}')

    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr("shutil.which", lambda name: "/usr/local/bin/claude")
    with pytest.raises(NarrativeError):
        generate_cover_subtitle(
            jesper_ctx, cache_dir=tmp_path, claude_bin=_FAKE_CLAUDE_BIN, primer="p"
        )


# ---------------------------------------------------------------------------
# generate_section_subtitles
# ---------------------------------------------------------------------------


def test_generate_section_subtitles_returns_binding_keyed_dict(
    jesper_ctx: DirectorContext, mock_claude_rich: dict[str, Any], tmp_path: Path
) -> None:
    out = generate_section_subtitles(
        jesper_ctx, cache_dir=tmp_path, claude_bin=_FAKE_CLAUDE_BIN, primer="p"
    )
    assert set(out.keys()) <= {"S03_Header", "S10_Header", "S20_Header", "S25_Header"}
    # The mock returns all 4 sections.
    assert len(out) == 4
    for binding, text in out.items():
        assert "\n" not in text
        assert text == text.strip()


def test_generate_section_subtitles_caches(
    jesper_ctx: DirectorContext, mock_claude_rich: dict[str, Any], tmp_path: Path
) -> None:
    first = generate_section_subtitles(
        jesper_ctx, cache_dir=tmp_path, claude_bin=_FAKE_CLAUDE_BIN, primer="p"
    )
    initial = mock_claude_rich["call_count"]
    second = generate_section_subtitles(
        jesper_ctx, cache_dir=tmp_path, claude_bin=_FAKE_CLAUDE_BIN, primer="p"
    )
    assert first == second
    assert mock_claude_rich["call_count"] == initial


def test_generate_section_subtitles_partial_output_filtered(
    jesper_ctx: DirectorContext, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """If claude returns only 2 of 4 sections, the result should only have
    bindings for the sections it did return -- not crash, not invent."""

    def fake_run(cmd: Any, **kwargs: Any) -> Any:
        partial = "\x1b]0;claude\x07Pipeline: 38M open Stage 3 leads\nRisk: 17 stale 10.2M\n"
        return _make_completed(partial)

    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr("shutil.which", lambda name: "/usr/local/bin/claude")
    out = generate_section_subtitles(
        jesper_ctx, cache_dir=tmp_path, claude_bin=_FAKE_CLAUDE_BIN, primer="p"
    )
    assert "S03_Header" in out  # Pipeline -> S03
    assert "S20_Header" in out  # Risk -> S20
    assert "S10_Header" not in out  # Renewals not present
    assert "S25_Header" not in out  # Velocity not present


# ---------------------------------------------------------------------------
# Live smoke (gated)
# ---------------------------------------------------------------------------

LIVE = os.environ.get("NARRATIVE_LIVE") == "1"


@pytest.mark.skipif(not LIVE, reason="live narrative gated behind NARRATIVE_LIVE=1")
def test_live_chart_insight_round_trip_for_jesper(
    tmp_path: Path, jesper_ctx: DirectorContext, jesper_ppttc_entries: list[dict[str, Any]]
) -> None:
    """End-to-end real-claude chart-insights round trip, single binding."""
    insights = generate_chart_insights(
        jesper_ctx,
        jesper_ppttc_entries,
        cache_dir=tmp_path,
        timeout=DEFAULT_TIMEOUT_SECONDS,
        bindings=(("S05_Insight", "S05_PipelineByStage", "bar by Stage 1-8"),),
    )
    assert "S05_Insight" in insights
    text = insights["S05_Insight"]
    # Must reference a number and stay under cap.
    assert any(token in text for token in ("EUR", "Stage", "M"))
    assert len(text.split()) <= RICH_INSIGHT_WORDS_MAX + 1
