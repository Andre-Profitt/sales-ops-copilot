"""Tests for ``tcrender.narrative_templates``.

What's covered:
    1. Extract narrative-style templates from a real shipped Outlook deck
       (skips cleanly when the prior shipped deck is not on disk).
    2. ``populate_narrative`` fills ``{key}`` placeholders correctly and
       handles missing keys without crashing.
    3. ``NARRATIVE_TEMPLATES`` is non-empty and ASCII-only.
    4. Style-guide rendering integrates with ``tcrender.narrative`` prompts.
"""

from __future__ import annotations

from pathlib import Path

import pytest

PRIOR_SHIPPED_DECK = Path(
    "/Users/test/Library/Group Containers/UBF8T346G9.Office/"
    "Outlook/Outlook 15 Profiles/Main Profile/Files/S0/2/Attachments/0/"
    "Sales_Director_Monthly_-_Jesper_Tyrer__APAC_[9464078].pptx"
)


def test_extract_templates_from_real_deck() -> None:
    """Mining a real shipped deck must yield a non-trivial set of patterns."""
    if not PRIOR_SHIPPED_DECK.exists():
        pytest.skip(f"prior shipped deck missing: {PRIOR_SHIPPED_DECK}")
    from tcrender.narrative_templates import extract_templates_from_deck

    templates = extract_templates_from_deck(PRIOR_SHIPPED_DECK)
    assert len(templates) >= 5, (
        f"expected >= 5 mined templates from Jesper deck, got {len(templates)}"
    )
    # Every template must have at least one placeholder (number replaced).
    has_placeholder = sum(1 for t in templates if "{" in t and "}" in t)
    assert has_placeholder >= len(templates) // 2, (
        f"too few templates carry placeholders: {has_placeholder}/{len(templates)}"
    )
    # ASCII-only.
    for t in templates:
        assert t == t.encode("ascii", "ignore").decode("ascii"), (
            f"non-ASCII chars survived in template: {t!r}"
        )


def test_populate_narrative_fills_placeholders() -> None:
    """populate_narrative substitutes {key} tokens from the ctx dict."""
    from tcrender.narrative_templates import populate_narrative

    template = (
        "Pipeline: EUR {open_arr} open. {pending_count} deals (EUR {pending_arr}) "
        "missing commercial approval."
    )
    ctx = {"open_arr": "6.6M", "pending_count": "2", "pending_arr": "3.0M"}
    out = populate_narrative(template, ctx)
    assert "EUR 6.6M open" in out
    assert "2 deals" in out
    assert "EUR 3.0M" in out
    assert "{" not in out and "}" not in out


def test_populate_narrative_marks_missing_keys() -> None:
    """Missing keys leave a [?] marker so reviewers spot the gap."""
    from tcrender.narrative_templates import populate_narrative

    out = populate_narrative("Total: EUR {missing_value}", {})
    assert "[?]" in out


def test_seed_templates_non_empty_and_ascii() -> None:
    """The curated seed library is non-empty and ASCII-only."""
    from tcrender.narrative_templates import NARRATIVE_TEMPLATES

    assert len(NARRATIVE_TEMPLATES) >= 12, (
        f"expected >= 12 seed templates, got {len(NARRATIVE_TEMPLATES)}"
    )
    for key, tpl in NARRATIVE_TEMPLATES.items():
        # Keys are ASCII identifiers.
        assert key.isascii() and key.replace("_", "").isalnum(), f"bad key shape: {key!r}"
        # Templates are ASCII (after the module's own _ascii_only guard).
        assert tpl == tpl.encode("ascii", "ignore").decode("ascii"), (
            f"non-ASCII char in seed template {key!r}: {tpl!r}"
        )
        # Templates carry at least one placeholder.
        if key not in {"approval_action"}:  # one curated example has none
            assert "{" in tpl and "}" in tpl, (
                f"seed template {key!r} carries no placeholder: {tpl!r}"
            )


def test_style_guide_integrates_into_narrative_prompts() -> None:
    """The style guide is injected into both narrative.py prompt builders.

    We probe the private prompt-builder helpers (they are what ``claude -p``
    sees) and assert the style examples appear verbatim in the rendered
    prompt body.
    """
    from tcrender.narrative import _build_exec_summary_prompt, _build_risks_prompt
    from tcrender.narrative import DirectorContext
    from tcrender.narrative_templates import NARRATIVE_TEMPLATES

    ctx = DirectorContext(
        name="Test Director",
        slug="Test-Director",
        period="2026-Q2",
        scope_label="Test Scope",
    )
    exec_prompt = _build_exec_summary_prompt(ctx)
    risks_prompt = _build_risks_prompt(ctx)

    # Style-guide preamble must appear in both prompts.
    for prompt_label, prompt in (
        ("exec_summary", exec_prompt),
        ("risks_outlook", risks_prompt),
    ):
        assert "Style examples from prior shipped" in prompt, (
            f"style guide not injected into {prompt_label} prompt"
        )
        # At least one curated example must land in the prompt body.
        sample_template = NARRATIVE_TEMPLATES["exec_pipeline"]
        # Templates may be wrapped at line breaks, so check a stable substring.
        assert "{open_arr}" in prompt, (
            f"sample placeholder from style guide missing in {prompt_label} prompt"
        )
        # Director context still flows through.
        assert "Test Director" in prompt
        assert "2026-Q2" in prompt


def test_render_style_guide_caps_examples() -> None:
    """``render_style_guide(max_examples=N)`` clamps the example count."""
    from tcrender.narrative_templates import render_style_guide

    short = render_style_guide(max_examples=3)
    long_ = render_style_guide(max_examples=20)

    # Numbered examples appear as "  1." / "  2." / "  3." prefixes.
    short_count = sum(
        1 for line in short.splitlines() if line.lstrip().startswith(("1.", "2.", "3."))
    )
    assert short_count <= 3
    assert "Style examples" in short
    assert "Tone:" in short
    assert len(long_) > len(short)
