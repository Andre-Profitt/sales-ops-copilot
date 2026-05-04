"""Narrative-template extraction + style-guide library for the LAND deck.

Mines the prior shipped Sales-Director-Monthly Outlook decks (e.g.
``/Users/test/Library/Group Containers/UBF8T346G9.Office/Outlook/Outlook 15
Profiles/Main Profile/Files/S0/2/Attachments/0/Sales_Director_Monthly_-
_Jesper_Tyrer__APAC_[9464078].pptx``) for repeatable narrative patterns
and exposes them as a "style guide" the existing :mod:`tcrender.narrative`
Claude prompts can reference. The narrative generator stays the same;
this module only seeds the prompt with concrete examples of the prior
shipped tone (terse, specific, number-led).

Public API
----------
:data:`NARRATIVE_TEMPLATES`
    Dict of pattern-key -> example/template string. Hand-curated from
    the prior shipped decks (see ``_SEED_TEMPLATES``).
:func:`extract_templates_from_deck`
    Walk a .pptx, return the candidate template strings (number-led
    sentences with placeholders extracted). Used to refresh the seed
    library when a new shipped deck lands.
:func:`populate_narrative`
    Fill a single template with a director-context dict.
:func:`render_style_guide`
    Render a compact ASCII style-guide block suitable for injection
    into a Claude prompt (used by :mod:`tcrender.narrative`).

Hard constraints
----------------
* python-pptx + lxml + zipfile + stdlib only.
* ASCII-only on output. Inputs may carry Unicode (e.g. EUR sign U+20AC,
  EM dash) which we downgrade to ASCII via the same rules
  ``narrative._ascii_only`` uses.
* No network, no LLM calls. Pure deterministic mining + rendering.
"""

from __future__ import annotations

import re
import zipfile
from pathlib import Path

# ---------------------------------------------------------------------------
# Seed templates (curated 2026-05-03 from the 9 shipped Outlook decks)
# ---------------------------------------------------------------------------
#
# Each entry pairs a "pattern key" -> "fill-in-the-blank template".  The
# templates are mined from the actual shipped slides (see slide-XML probes
# in the design notes) and represent the verbatim style we want generated
# narrative to match. Placeholders use ``{name}`` for the LLM-filled slot.
#
# These are EXAMPLES the prompt shows to Claude, NOT runtime f-strings.
# That is why ``populate_narrative`` is the only callable that fills them.

_SEED_TEMPLATES: dict[str, str] = {
    # Slide 2: Executive summary - mined from Jesper APAC 2026 deck
    "exec_pipeline": (
        "Pipeline: EUR {open_arr} open. {top_stage_share}% in {top_stage} - "
        "conversion to later stages is key. {pending_count} deals "
        "(EUR {pending_arr}) missing commercial approval."
    ),
    "exec_winloss": (
        "Win/Loss: {won_count} won (EUR {won_arr}) vs {lost_count} lost "
        "(EUR {lost_arr}) this quarter. ARR win rate {win_rate}% - "
        "{trend_note}."
    ),
    "exec_commit": (
        "Commit forecast: EUR {commit_arr} committed, EUR {best_case_arr} "
        "best case, EUR {pipeline_arr} in pipeline. EUR {renewal_acv} "
        "renewal ACV due."
    ),
    "exec_risk": (
        "Risk: {pushed_count} deals pushed 5+ times (EUR {pushed_arr} ARR). "
        "{owner_name} owns {owner_pushed_count} of the most-pushed deals."
    ),
    # Slide 4: Q1 promised vs delivered
    "q1_slipped": ("EUR {slipped_arr} slipped out of Q1 across {slipped_count} deals."),
    # Slide 5: Pipeline overview
    "pipeline_top_stage": (
        "{top_stage_share}% of pipeline (EUR {top_stage_arr}) sits in {top_stage}."
    ),
    # Slide 8: Commercial approval
    "approval_status": (
        "Deals with commercial approval. {approved_count} approved YTD totaling EUR {approved_arr}."
    ),
    "approval_pending": (
        "Deals pending approval. {pending_count} at Land Stage 3 worth "
        "EUR {pending_arr} need immediate attention."
    ),
    "approval_action": (
        "These deals are in Engagement stage without Go/No-Go approval. "
        "Action: escalate to approval committee."
    ),
    # Slide 11: Renewals
    "renewals_quarter": (
        "Renewals worth EUR {renewal_acv} due this quarter. Review probability and timing below."
    ),
    # Slide 15: Pushed deals summary
    "pushed_summary": (
        "{open_pushed_count} open deals pushed. {top_owner} owns "
        "{top_owner_pushed_count} of the top pushed deals - "
        "pattern review recommended."
    ),
    "pushed_critical": (
        "Critical: {critical_count} at 5+ pushes. Watch: {watch_count} "
        "at 3-4 pushes (EUR {watch_arr}). Early: {early_count} at "
        "1-2 pushes (EUR {early_arr})."
    ),
    # Slide 17: Forecast accuracy
    "forecast_won": (
        "{won_count} deals closed-won this quarter. Low won ARR signals "
        "early-quarter timing or delayed closes."
    ),
    "forecast_loss_warn": (
        "{lost_count} deals closed-lost. Lost ARR significantly exceeds "
        "won ARR - review loss reasons."
    ),
    # Slide 18: Forecast category
    "forecast_floor": (
        "Total open: EUR {total_arr}. Commit (EUR {commit_arr}) is the "
        "floor; Best Case + Pipeline is the upside."
    ),
    # S27 risks/outlook (mined from Sarah Central Europe shipped deck)
    "s27_renewal_pressure": (
        "Open renewal ACV: EUR {renewal_acv}. Risk: execution pressure "
        "remains elevated with EUR {stale_arr} stale ARR and "
        "{aged_count} aging 365+ ARR opportunities."
    ),
    "s27_stage5_coverage": ("{stage5_count} deals at Stage 5+ - quarter coverage at risk."),
    "s27_concentration": (
        "Top deal: {largest_account} - EUR {largest_arr} {motion_type}. "
        "Concentration share: {largest_share}%."
    ),
    # Generic chart-insight templates for native_fallback subtitles
    "insight_top_cell": ("{label} leads at EUR {value} ({share}% of total)."),
    "insight_trend": (
        "{metric_name} fell {pct_change}% from prior {period_unit} - {direction_note}."
    ),
}


# ---------------------------------------------------------------------------
# Public mutable view (callers may extend)
# ---------------------------------------------------------------------------

NARRATIVE_TEMPLATES: dict[str, str] = dict(_SEED_TEMPLATES)


# ---------------------------------------------------------------------------
# ASCII downgrade (matches narrative._ascii_only)
# ---------------------------------------------------------------------------


def _ascii_only(text: str) -> str:
    """Best-effort ASCII downgrade for mined slide text."""
    if not isinstance(text, str):
        text = str(text)
    return (
        text.replace("—", "-")  # em dash
        .replace("–", "-")  # en dash
        .replace("−", "-")  # minus sign
        .replace("’", "'")  # right single quote
        .replace("‘", "'")  # left single quote
        .replace("“", '"')  # left double quote
        .replace("”", '"')  # right double quote
        .replace("…", "...")  # ellipsis
        .replace("€", "EUR ")  # euro sign
        .replace("≥", ">=")
        .replace("≤", "<=")
        .replace("&amp;", "&")
        .replace("&apos;", "'")
        .replace("&quot;", '"')
        .replace("&lt;", "<")
        .replace("&gt;", ">")
        .encode("ascii", "ignore")
        .decode("ascii")
    )


# ---------------------------------------------------------------------------
# Mining: extract candidate patterns from a shipped deck
# ---------------------------------------------------------------------------

# Regex matches text inside <a:t> elements; runs are concatenated per slide.
_AT_RE = re.compile(r"<a:t[^>]*>([^<]+)</a:t>")

# A "candidate" sentence is number-led: starts with EUR, a digit, or a stage
# number. We also accept sentences that end with "this quarter" / "below" /
# "rate" -- these are the recurring shipped-deck patterns.
_NUMBER_LED_RE = re.compile(
    r"^(?:EUR\s|\d|\d+%|Stage\s\d|Win\s/\sLoss|Pipeline:|Renewals?\b|Risk:|"
    r"Commit|Forecast|Top|Open|Total)",
    re.IGNORECASE,
)

# Convert literal numeric runs to {placeholder} tokens. Order matters --
# longest patterns first so EUR amounts beat bare digits.
_PLACEHOLDER_RULES: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"EUR\s\d[\d,.]*\s*[Mk]?"), "EUR {amount}"),
    (re.compile(r"\d{1,3}\.\d%"), "{rate}%"),
    (re.compile(r"\b\d{1,3}%"), "{rate}%"),
    (re.compile(r"\b\d{1,4}\b\s+(deals|opps|opportunities)"), r"{count} \1"),
    (re.compile(r"\b\d{1,3}\b"), "{count}"),
)


def _normalize_to_template(sentence: str) -> str:
    """Replace concrete numbers in a sentence with placeholder tokens."""
    s = sentence
    for pattern, replacement in _PLACEHOLDER_RULES:
        s = pattern.sub(replacement, s)
    return s


def extract_templates_from_deck(
    pptx_path: Path,
    *,
    min_chars: int = 18,
    max_chars: int = 240,
) -> list[str]:
    """Mine narrative-style template strings from a shipped .pptx deck.

    Args:
        pptx_path: a shipped Sales-Director-Monthly .pptx (e.g. one of the
            9 in the Outlook attachments cache).
        min_chars: skip very short labels (column headers etc.).
        max_chars: skip large blocks (table cell dumps).

    Returns:
        Ordered list of normalized template strings (placeholders inserted
        for concrete numbers / amounts). Duplicates removed; order preserved.
    """
    path = Path(pptx_path)
    if not path.exists():
        raise FileNotFoundError(f"deck missing: {path}")
    if not zipfile.is_zipfile(path):
        raise ValueError(f"not a valid .pptx (zip): {path}")

    candidates: list[str] = []
    seen: set[str] = set()

    with zipfile.ZipFile(path) as zf:
        slide_names = sorted(
            (n for n in zf.namelist() if n.startswith("ppt/slides/slide") and n.endswith(".xml")),
            key=lambda n: int(re.search(r"slide(\d+)", n).group(1)),  # type: ignore[union-attr]
        )
        for slide_name in slide_names:
            xml = zf.read(slide_name).decode("utf-8", errors="replace")
            for raw_run in _AT_RE.findall(xml):
                run = _ascii_only(raw_run).strip()
                if not run:
                    continue
                if len(run) < min_chars or len(run) > max_chars:
                    continue
                # Drop column headers and bare labels.
                if " " not in run.strip(":."):
                    continue
                # Only keep number-led narrative.
                if not _NUMBER_LED_RE.match(run):
                    continue
                normalized = _normalize_to_template(run)
                if normalized in seen:
                    continue
                seen.add(normalized)
                candidates.append(normalized)

    return candidates


# ---------------------------------------------------------------------------
# Populate (fill template with director context)
# ---------------------------------------------------------------------------


_PLACEHOLDER_RE = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}")


def populate_narrative(template: str, ctx: dict[str, object]) -> str:
    """Fill ``{key}`` placeholders in ``template`` from ``ctx`` mapping.

    Missing keys are left as ``[?]`` markers so reviewers can spot the gap.
    The output is downgraded to ASCII for parity with the rest of the
    narrative pipeline.

    Args:
        template: e.g. ``"Pipeline: EUR {open_arr} open."``
        ctx: e.g. ``{"open_arr": "6.6M"}``

    Returns:
        Filled ASCII-only sentence.
    """

    def _fill(match: re.Match[str]) -> str:
        key = match.group(1)
        value = ctx.get(key)
        if value is None:
            return "[?]"
        return _ascii_only(str(value))

    out = _PLACEHOLDER_RE.sub(_fill, template)
    return _ascii_only(out)


# ---------------------------------------------------------------------------
# Style-guide rendering for prompt injection
# ---------------------------------------------------------------------------


def render_style_guide(*, max_examples: int = 8) -> str:
    """Render a compact ASCII style-guide block for prompt injection.

    The output is a numbered list of curated example sentences from
    :data:`NARRATIVE_TEMPLATES` with placeholders left intact -- Claude
    sees the *shape* and *cadence* we want, not concrete numbers.

    Args:
        max_examples: cap on the number of examples shown. Default 8 keeps
            the prompt prefix short.
    """
    keys = list(NARRATIVE_TEMPLATES)[:max_examples]
    lines = ["Style examples from prior shipped Sales-Director-Monthly decks:"]
    for i, key in enumerate(keys, start=1):
        # _ascii_only on the template (defensive; templates are already ASCII).
        lines.append(f"  {i}. {_ascii_only(NARRATIVE_TEMPLATES[key])}")
    lines.append(
        "Tone: terse, specific, number-led. Lead with EUR figures or counts. "
        "No preamble. No bullet markers. ASCII only."
    )
    return "\n".join(lines)


__all__ = [
    "NARRATIVE_TEMPLATES",
    "extract_templates_from_deck",
    "populate_narrative",
    "render_style_guide",
]
