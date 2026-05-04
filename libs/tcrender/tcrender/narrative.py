"""Claude-grounded narrative augmentation for the LAND deck factory.

Replaces the canned, rule-based bullet text in S02_ExecSummaryLeft /
S02_ExecSummaryRight / S27_RisksOutlook with Claude-generated 2-3 sentence
director-specific narrative grounded in actual chart data + per-director
context. Adds per-chart insight captions, anomaly watch, ranked actions,
director-specific cover subtitle, and per-section subtitles.

Design constraints (per ~/.claude/projects/-Users-test/memory/MEMORY.md):
    - Use the ``claude -p "<prompt>"`` CLI (Andre's Max subscription) via
      subprocess. NOT the paid Anthropic API. The CLI is at
      ``/Users/test/.local/bin/claude``.
    - Per-deal data (account names + ARR) is allowed in narrative because
      SimCorp has an enterprise Claude contract; do not include personal
      contact info in prompts or output.
    - Honest reporting: declining numbers stated as declining.
    - Per-director scope respected (Jesper sees APAC, Sarah sees CE).

Public API:
    DirectorContext              -- dataclass capturing director identity +
                                    the chart data summaries the prompt
                                    synthesizes from.
    NarrativeError               -- raised when the claude CLI fails or
                                    returns junk.
    generate_exec_summary(ctx)   -- LEFT (highlights/wins) + RIGHT (risks)
                                    bullets for S02_ExecSummary{Left,Right}.
    generate_risks_outlook(ctx)  -- multi-line bullet body for S27.
    generate_chart_insight(...)  -- 1-line takeaway (used by native_fallback
                                    to set chart subtitles, and by the
                                    rich-narrative pass below).
    generate_chart_insights(ctx, ppttc_entries)
                                 -- batch insights for known chart bindings
                                    present in ``ppttc_entries``; returns
                                    ``binding_name -> insight`` for the
                                    S{NN}_Insight text bindings. Skips
                                    bindings whose data is missing/empty.
                                    Errors per binding are caught.
    generate_anomaly_watch(ctx)  -- 3-5 anomaly bullets for S98_AnomalyWatch.
    generate_ranked_actions(ctx) -- top-5 ranked actions for S26.
    generate_cover_subtitle(ctx) -- 1-line director framing for S01_Subtitle.
    generate_section_subtitles(ctx)
                                 -- 1-line subtitles per section header
                                    keyed by section_name (Pipeline /
                                    Renewals / Risk / Velocity).
    DEFAULT_INSIGHT_BINDINGS     -- ordered list of (binding_name,
                                    source_kind) pairs that the chart-
                                    insights pass walks.

Schema-grounding primer:
    Each prompt embeds a compact, ASCII vocabulary primer derived from
    ``state/thinkcell_bridge/thinkcellxml_corpus_extended/<latest>/
    schema_inventory.json`` so Claude phrases insights in the same
    vocabulary the rest of the deck uses (chart-class names, "Stage 1-8",
    "Land/Expand/Renewal", etc.).

Caching:
    Each call hashes (prompt + ctx_summary) under SHA-256 and writes/reads
    ``<cache_dir>/<director-slug>-<period>-<binding_kind>-<hash16>.txt``.
    Identical inputs always reuse the cached output without re-invoking the
    CLI. Default cache_dir = repo_root/state/narrative_cache when present;
    callers can override.
"""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

__all__ = [
    "DEFAULT_CLAUDE_BIN",
    "DEFAULT_INSIGHT_BINDINGS",
    "DEFAULT_TIMEOUT_SECONDS",
    "DirectorContext",
    "NarrativeError",
    "generate_anomaly_watch",
    "generate_chart_insight",
    "generate_chart_insights",
    "generate_cover_subtitle",
    "generate_exec_summary",
    "generate_ranked_actions",
    "generate_risks_outlook",
    "generate_section_subtitles",
    "load_thinkcell_vocabulary_primer",
]

# ---------------------------------------------------------------------------
# Constants & errors
# ---------------------------------------------------------------------------

DEFAULT_CLAUDE_BIN = "/Users/test/.local/bin/claude"
DEFAULT_TIMEOUT_SECONDS = 60.0

# Maximum bullet/word counts (post-processing caps; Claude is also instructed
# in-prompt to stay under these).
EXEC_BULLET_WORDS_MAX = 22
EXEC_BULLETS_PER_SIDE = 3
RISKS_BULLET_WORDS_MAX = 25
RISKS_BULLETS_MAX = 5
# Per-chart caption insights are tighter than the legacy chart_insight cap so
# they fit comfortably below the chart shape.
INSIGHT_WORDS_MAX = 28
RICH_INSIGHT_WORDS_MAX = 25
ANOMALY_BULLET_WORDS_MAX = 25
ANOMALY_BULLETS_MAX = 5
ANOMALY_BULLETS_MIN = 3
RANKED_ACTIONS_WORDS_MAX = 28
RANKED_ACTIONS_MAX = 5
COVER_SUBTITLE_WORDS_MAX = 8
SECTION_SUBTITLE_WORDS_MAX = 14

# Strip ANSI escape sequences (the claude CLI prepends "\x1b]0;claude\x07"
# as a terminal title escape, even when stdout is piped).
_ANSI_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]|\x1b\][^\x07]*\x07")

# Patterns we reject as prompt-instruction echo / preamble.
_BANNED_PREFIXES: tuple[str, ...] = (
    "here's",
    "here is",
    "here are",
    "below is",
    "below are",
    "sure,",
    "certainly,",
    "of course,",
    "i'll",
    "i will",
    "let me",
    "as requested",
    "based on",
    "**left",
    "**right",
    "left column",
    "right column",
    "highlights:",
    "risks:",
    "summary:",
)


class NarrativeError(RuntimeError):
    """Raised when Claude CLI invocation or output validation fails."""


# ---------------------------------------------------------------------------
# DirectorContext
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DirectorContext:
    """Per-director, per-period context fed into narrative prompts.

    The fields here are deliberately the *summaries* the prompts need, not
    raw workbook rows -- the caller (build_ppttc.py) is responsible for
    extracting these from trends.json + the model workbook.

    Required identity fields:
        name        -- e.g. "Jesper Tyrer"
        slug        -- e.g. "Jesper-Tyrer"
        period      -- e.g. "2026-Q2"
        scope_label -- e.g. "APAC"

    Numerical signals (all EUR unless suffixed):
        closeable_arr_eur        -- in-quarter Land+Expand close ARR
        renewal_acv_eur          -- in-quarter renewal ACV
        beyond_quarter_arr_eur   -- open Land+Expand beyond the quarter
        stage5_plus_share_pct    -- % of pipeline ARR in Stage 5+ (cover.)
        largest_account_share_pct-- concentration top-account share %

    Lists (already trimmed, ASCII):
        risk_claims         -- from trends.json risks[].claim
        action_items        -- from trends.json action_items[].claim (top 5)
        top_deals           -- list of dicts with at minimum
                                {account, stage, arr_eur, owner}
        top_industry        -- e.g. "Pension" / "Asset Management"
        wins_qtd_eur, losses_qtd_eur (optional)
        stale_activity_arr_eur (optional, EUR sum of >30d-stale this-Q ARR)
    """

    name: str
    slug: str
    period: str
    scope_label: str
    closeable_arr_eur: float = 0.0
    renewal_acv_eur: float = 0.0
    beyond_quarter_arr_eur: float = 0.0
    stage5_plus_share_pct: float | None = None
    largest_account_share_pct: float | None = None
    risk_claims: tuple[str, ...] = ()
    action_items: tuple[str, ...] = ()
    top_deals: tuple[dict[str, Any], ...] = ()
    top_industry: str | None = None
    wins_qtd_eur: float | None = None
    losses_qtd_eur: float | None = None
    stale_activity_arr_eur: float | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    # ---- prompt-friendly summary -----------------------------------------

    def numbers_block(self) -> str:
        """Compact, ASCII-only numbers block for prompt grounding."""
        lines: list[str] = [
            f"Director: {self.name}",
            f"Scope: {self.scope_label}",
            f"Period: {self.period}",
            f"Closeable Land+Expand ARR ({self.period}): {_fmt_eur(self.closeable_arr_eur)}",
            f"Renewal ACV ({self.period}): {_fmt_eur(self.renewal_acv_eur)}",
            f"Open Land+Expand beyond quarter: {_fmt_eur(self.beyond_quarter_arr_eur)}",
        ]
        if self.stage5_plus_share_pct is not None:
            lines.append(f"Stage 5+ share of pipeline ARR: {self.stage5_plus_share_pct:.0f}%")
        if self.largest_account_share_pct is not None:
            lines.append(
                f"Largest-account concentration share: {self.largest_account_share_pct:.0f}%"
            )
        if self.top_industry:
            lines.append(f"Top industry: {self.top_industry}")
        if self.stale_activity_arr_eur is not None:
            lines.append(f"Stale (>30d) this-quarter ARR: {_fmt_eur(self.stale_activity_arr_eur)}")
        if self.wins_qtd_eur is not None:
            lines.append(f"Wins QTD (ARR): {_fmt_eur(self.wins_qtd_eur)}")
        if self.losses_qtd_eur is not None:
            lines.append(f"Losses QTD (ARR): {_fmt_eur(self.losses_qtd_eur)}")
        return "\n".join(lines)

    def context_summary(self) -> str:
        """Full prompt-context block: numbers + lists + top deals."""
        parts: list[str] = [self.numbers_block()]
        if self.top_deals:
            parts.append("Top deals (account, stage, ARR EUR):")
            for deal in self.top_deals[:6]:
                parts.append(
                    "  - "
                    + _ascii_only(
                        f"{deal.get('account', '?')} | "
                        f"{deal.get('stage', '?')} | "
                        f"{_fmt_eur(deal.get('arr_eur', 0.0))}"
                    )
                )
        if self.action_items:
            parts.append("Action items (rule-based):")
            for item in self.action_items[:5]:
                parts.append(f"  - {_ascii_only(item)}")
        if self.risk_claims:
            parts.append("Detected risks:")
            for risk in self.risk_claims[:5]:
                parts.append(f"  - {_ascii_only(risk)}")
        return "\n".join(parts)


# ---------------------------------------------------------------------------
# CLI invocation
# ---------------------------------------------------------------------------


def _strip_ansi(text: str) -> str:
    return _ANSI_RE.sub("", text)


def _ascii_only(text: str) -> str:
    """Best-effort ASCII downgrade: replace common Unicode dashes / quotes."""
    if not isinstance(text, str):
        text = str(text)
    return (
        text.replace("—", "-")
        .replace("–", "-")
        .replace("−", "-")
        .replace("’", "'")
        .replace("‘", "'")
        .replace("“", '"')
        .replace("”", '"')
        .replace("…", "...")
        .replace("≥", ">=")
        .replace("≤", "<=")
        .encode("ascii", "ignore")
        .decode("ascii")
    )


def _fmt_eur(value: float | int | None) -> str:
    if value is None:
        return "EUR 0"
    try:
        v = float(value)
    except (TypeError, ValueError):
        return "EUR 0"
    abs_v = abs(v)
    if abs_v >= 1_000_000:
        return f"EUR {v / 1_000_000:.1f}M"
    if abs_v >= 1_000:
        return f"EUR {v / 1_000:.0f}k"
    return f"EUR {v:.0f}"


def _resolve_claude_bin(claude_bin: str | os.PathLike[str] | None) -> str:
    if claude_bin is None:
        return DEFAULT_CLAUDE_BIN
    return str(claude_bin)


def _cache_path(
    *,
    cache_dir: Path,
    slug: str,
    period: str,
    binding_kind: str,
    digest: str,
) -> Path:
    safe_slug = re.sub(r"[^A-Za-z0-9._-]", "_", slug)
    safe_period = re.sub(r"[^A-Za-z0-9._-]", "_", period)
    safe_kind = re.sub(r"[^A-Za-z0-9._-]", "_", binding_kind)
    return cache_dir / f"{safe_slug}-{safe_period}-{safe_kind}-{digest[:16]}.txt"


def _hash_inputs(prompt: str, ctx_summary: str) -> str:
    h = hashlib.sha256()
    h.update(prompt.encode("utf-8"))
    h.update(b"\n----\n")
    h.update(ctx_summary.encode("utf-8"))
    return h.hexdigest()


def _invoke_claude(
    prompt: str,
    *,
    claude_bin: str,
    timeout: float,
) -> str:
    """Run ``claude -p <prompt>``, return decoded stdout (ANSI-stripped)."""
    if not Path(claude_bin).exists() and shutil.which(claude_bin) is None:
        raise NarrativeError(f"claude CLI not found at {claude_bin}")
    try:
        completed = subprocess.run(
            [claude_bin, "-p", prompt],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise NarrativeError(f"claude CLI timed out after {timeout:.0f}s") from exc
    except OSError as exc:
        raise NarrativeError(f"claude CLI invocation failed: {exc}") from exc
    if completed.returncode != 0:
        stderr_tail = (completed.stderr or "").strip()[-400:]
        raise NarrativeError(f"claude CLI exit={completed.returncode}: {stderr_tail!r}")
    raw = completed.stdout or ""
    return _strip_ansi(raw).strip()


def _run_with_cache(
    *,
    prompt: str,
    ctx: DirectorContext,
    binding_kind: str,
    cache_dir: Path | None,
    claude_bin: str | None,
    timeout: float,
) -> str:
    """Hash, look up cache, invoke if miss, persist on success."""
    bin_path = _resolve_claude_bin(claude_bin)
    digest = _hash_inputs(prompt, ctx.context_summary())
    cache_file: Path | None = None
    if cache_dir is not None:
        cache_dir.mkdir(parents=True, exist_ok=True)
        cache_file = _cache_path(
            cache_dir=cache_dir,
            slug=ctx.slug,
            period=ctx.period,
            binding_kind=binding_kind,
            digest=digest,
        )
        if cache_file.exists():
            return cache_file.read_text(encoding="utf-8")
    output = _invoke_claude(prompt, claude_bin=bin_path, timeout=timeout)
    if cache_file is not None:
        cache_file.write_text(output, encoding="utf-8")
    return output


# ---------------------------------------------------------------------------
# Output validation / extraction
# ---------------------------------------------------------------------------


def _looks_like_preamble(line: str) -> bool:
    lower = line.lower().lstrip("- *#>• ").strip()
    if not lower:
        return False
    return any(lower.startswith(p) for p in _BANNED_PREFIXES)


def _looks_like_json(text: str) -> bool:
    s = text.strip()
    if not s:
        return False
    if s.startswith("{") or s.startswith("["):
        return True
    if "```" in s and ("json" in s.lower() or "{" in s):
        return True
    return False


def _truncate_words(text: str, max_words: int) -> str:
    words = text.split()
    if len(words) <= max_words:
        return text
    return " ".join(words[:max_words]).rstrip(",;.:") + "."


def _extract_bullets(
    text: str,
    *,
    max_words: int,
    max_bullets: int,
) -> list[str]:
    """Pick bullet lines out of Claude's freeform output, drop preambles."""
    if _looks_like_json(text):
        raise NarrativeError("Claude returned JSON-shaped output instead of bullets")
    bullets: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if _looks_like_preamble(line):
            continue
        # Strip leading bullet markers / numbering.
        stripped = re.sub(
            r"^(?:[-*•]|[0-9]{1,2}[.)])\s+",
            "",
            line,
        ).strip()
        # Drop bold prefix labels like "**Risk:**" / "Highlight:"
        stripped = re.sub(r"^\*\*[^*]+\*\*\s*[:\-]?\s*", "", stripped)
        stripped = re.sub(r"^[A-Za-z][A-Za-z ]{0,18}:\s+", "", stripped)
        stripped = _ascii_only(stripped).strip()
        if not stripped or len(stripped.split()) < 4:
            continue
        if _looks_like_preamble(stripped):
            continue
        bullets.append(_truncate_words(stripped, max_words))
        if len(bullets) >= max_bullets:
            break
    if not bullets:
        raise NarrativeError(f"No usable bullets extracted from Claude output: {text!r}")
    return bullets


def _split_left_right(text: str) -> tuple[str, str]:
    """Split exec-summary output into LEFT / RIGHT halves on the section markers."""
    upper = text.upper()
    # Try the explicit headings we instruct Claude to emit.
    for left_marker in ("LEFT (HIGHLIGHTS)", "LEFT (HIGHLIGHTS/WINS)", "LEFT:", "HIGHLIGHTS:"):
        if left_marker in upper:
            l_idx = upper.index(left_marker)
            for right_marker in ("RIGHT (RISKS)", "RIGHT (RISKS/CONCERNS)", "RIGHT:", "RISKS:"):
                if right_marker in upper and upper.index(right_marker) > l_idx:
                    r_idx = upper.index(right_marker)
                    left_body = text[l_idx + len(left_marker) : r_idx].strip(" :\n\r\t-")
                    right_body = text[r_idx + len(right_marker) :].strip(" :\n\r\t-")
                    return left_body, right_body
    raise NarrativeError("Could not locate LEFT/RIGHT section markers in Claude output")


# ---------------------------------------------------------------------------
# Public API: prompts + generation
# ---------------------------------------------------------------------------

_SYSTEM_GUIDANCE = (
    "You are a sales-ops analyst writing a SimCorp Sales Director monthly LAND review. "
    "Your output goes directly into PowerPoint -- no preamble, no markdown headings, "
    "no JSON, no code fences. Be specific with EUR figures. Be honest -- if a number "
    "is declining or a risk is real, say so plainly. ASCII only. Do not invent figures: "
    "use only the numbers given."
)


def _style_guide_block() -> str:
    """Return the prior-shipped style-guide block (lazy import to avoid cycles)."""
    try:
        from .narrative_templates import render_style_guide  # noqa: PLC0415
    except Exception:  # noqa: BLE001 - style guide is best-effort
        return ""
    return render_style_guide(max_examples=8)


def _build_exec_summary_prompt(ctx: DirectorContext) -> str:
    style_guide = _style_guide_block()
    style_block = f"\n{style_guide}\n" if style_guide else "\n"
    return (
        f"{_SYSTEM_GUIDANCE}\n"
        f"{style_block}\n"
        f"Context for {ctx.name}'s {ctx.scope_label} {ctx.period} LAND review:\n"
        f"{ctx.context_summary()}\n\n"
        f"Write a {EXEC_BULLETS_PER_SIDE}-bullet LEFT column (highlights / wins / "
        f"on-track signals) and a {EXEC_BULLETS_PER_SIDE}-bullet RIGHT column (risks / "
        "concerns / where attention is needed). Each bullet must be a single short "
        f"sentence under {EXEC_BULLET_WORDS_MAX} words, lead with a specific number when "
        "possible, and contain no bullet markers (the deck adds them). Match the cadence "
        "of the style examples above.\n\n"
        "Format your reply EXACTLY like this, no preamble, no closing remarks:\n"
        "LEFT (HIGHLIGHTS):\n"
        "<bullet 1>\n"
        "<bullet 2>\n"
        "<bullet 3>\n"
        "RIGHT (RISKS):\n"
        "<bullet 1>\n"
        "<bullet 2>\n"
        "<bullet 3>\n"
    )


def _build_risks_prompt(ctx: DirectorContext) -> str:
    style_guide = _style_guide_block()
    style_block = f"\n{style_guide}\n" if style_guide else "\n"
    return (
        f"{_SYSTEM_GUIDANCE}\n"
        f"{style_block}\n"
        f"Context for {ctx.name}'s {ctx.scope_label} {ctx.period} LAND review:\n"
        f"{ctx.context_summary()}\n\n"
        "Write 3 to 5 risk / outlook bullets for this director's review. Lead with the "
        "highest-impact risk. Each bullet must be a single short sentence under "
        f"{RISKS_BULLET_WORDS_MAX} words and lead with a specific number where possible. "
        "Match the terse number-led cadence of the style examples above. "
        "Do not include bullet markers; do not include any preamble or closing line. "
        "Output ONLY the bullets, one per line."
    )


def _build_chart_insight_prompt(
    binding_name: str,
    table_data: list[list[Any]],
    ctx: DirectorContext,
) -> str:
    table_preview = "\n".join(
        "  | ".join("" if cell is None else str(cell) for cell in row[:8]) for row in table_data[:8]
    )
    return (
        f"{_SYSTEM_GUIDANCE}\n\n"
        f"Director {ctx.name} ({ctx.scope_label}) {ctx.period}. Chart: {binding_name}.\n"
        f"Data preview (first rows):\n{table_preview}\n\n"
        f"Write ONE sentence (under {INSIGHT_WORDS_MAX} words) that names the largest "
        "specific cell or the clearest trend in this chart. Lead with the number / "
        "category. No preamble, no markdown, no bullet marker, just the sentence."
    )


def generate_exec_summary(
    ctx: DirectorContext,
    *,
    cache_dir: Path | None = None,
    claude_bin: str | None = None,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
) -> tuple[list[str], list[str]]:
    """Generate (left_bullets, right_bullets) for S02_ExecSummary{Left,Right}.

    Args:
        ctx: per-director context with numbers + lists.
        cache_dir: directory for content-hashed cache files; ``None`` disables.
        claude_bin: path to claude CLI; defaults to ``DEFAULT_CLAUDE_BIN``.
        timeout: subprocess timeout in seconds.

    Returns:
        Tuple of (left_bullets, right_bullets), each a list of ``<= EXEC_BULLETS_PER_SIDE``
        ASCII-only sentences. Each sentence is capped at ``EXEC_BULLET_WORDS_MAX`` words.

    Raises:
        NarrativeError on CLI failure, timeout, or unparseable output.
    """
    prompt = _build_exec_summary_prompt(ctx)
    output = _run_with_cache(
        prompt=prompt,
        ctx=ctx,
        binding_kind="exec_summary",
        cache_dir=cache_dir,
        claude_bin=claude_bin,
        timeout=timeout,
    )
    left_body, right_body = _split_left_right(output)
    left = _extract_bullets(
        left_body, max_words=EXEC_BULLET_WORDS_MAX, max_bullets=EXEC_BULLETS_PER_SIDE
    )
    right = _extract_bullets(
        right_body, max_words=EXEC_BULLET_WORDS_MAX, max_bullets=EXEC_BULLETS_PER_SIDE
    )
    return left, right


def generate_risks_outlook(
    ctx: DirectorContext,
    *,
    cache_dir: Path | None = None,
    claude_bin: str | None = None,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
) -> str:
    """Generate the multi-line bullet body for S27_RisksOutlook.

    Returns:
        Newline-joined bullet body, each line prefixed with ``"- "`` so it
        slots into the existing template binding shape.
    """
    prompt = _build_risks_prompt(ctx)
    output = _run_with_cache(
        prompt=prompt,
        ctx=ctx,
        binding_kind="risks_outlook",
        cache_dir=cache_dir,
        claude_bin=claude_bin,
        timeout=timeout,
    )
    bullets = _extract_bullets(
        output, max_words=RISKS_BULLET_WORDS_MAX, max_bullets=RISKS_BULLETS_MAX
    )
    return "\n".join(f"- {b}" for b in bullets)


def generate_chart_insight(
    binding_name: str,
    table_data: Iterable[Iterable[Any]],
    ctx: DirectorContext,
    *,
    cache_dir: Path | None = None,
    claude_bin: str | None = None,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
) -> str:
    """One-line takeaway for a chart binding (used as subtitle by native_fallback).

    Args:
        binding_name: e.g. "S16_StageByIndustry".
        table_data: chart matrix (list of rows). First row is treated as header.
        ctx: director context.
    """
    rows = [list(r) for r in table_data]
    prompt = _build_chart_insight_prompt(binding_name, rows, ctx)
    output = _run_with_cache(
        prompt=prompt,
        ctx=ctx,
        binding_kind=f"insight_{binding_name}",
        cache_dir=cache_dir,
        claude_bin=claude_bin,
        timeout=timeout,
    )
    cleaned = _ascii_only(output.strip())
    if not cleaned:
        raise NarrativeError(f"Empty insight for {binding_name}")
    if _looks_like_json(cleaned):
        raise NarrativeError(f"JSON-shaped insight rejected for {binding_name}")
    # Take only the first non-empty, non-preamble line.
    for line in cleaned.splitlines():
        candidate = re.sub(
            r"^(?:[-*•]|[0-9]{1,2}[.)])\s+",
            "",
            line.strip(),
        ).strip()
        if not candidate or _looks_like_preamble(candidate):
            continue
        return _truncate_words(candidate, INSIGHT_WORDS_MAX)
    raise NarrativeError(f"No usable insight line found for {binding_name}: {output!r}")


# ---------------------------------------------------------------------------
# Schema-grounding vocabulary primer (rich-narrative pass)
# ---------------------------------------------------------------------------
#
# Sourced from
# ``state/thinkcell_bridge/thinkcellxml_corpus_extended/<latest-ts>/
# schema_inventory.json`` -- the corpus dump captures the chart-class names
# think-cell uses internally (CSequenceChartDataScalar, CGanttVectorTile,
# CScatterChartDataVector, etc.). Embedding the top-N classes plus the LAND-
# review canonical phrasing primes Claude to phrase insights in the same
# vocabulary the rest of the deck uses.

# Canonical SimCorp / LAND vocabulary that the rest of the deck uses. Kept
# small so it's cheap to inline in every prompt.
_LAND_VOCABULARY: tuple[str, ...] = (
    "Stage 1 Prospecting",
    "Stage 2 Discovery",
    "Stage 3 Engagement",
    "Stage 4 Shortlisted",
    "Stage 5 Preferred",
    "Stage 6 Contracting",
    "Stage 7 Won",
    "Stage 8 Opt-out",
    "Land",
    "Expand",
    "Renewal",
    "ARR",
    "ACV",
    "Commercial Approval",
    "Forecast Category (Commit/Best Case/Pipeline/Omitted)",
)


def _resolve_schema_inventory_path(repo_root: Path | None = None) -> Path | None:
    """Return the most-recent schema_inventory.json under the corpus dir.

    Walks ``state/thinkcell_bridge/thinkcellxml_corpus_extended/`` for
    timestamped subdirs and picks the latest by lexicographic name (the
    timestamps are zero-padded ISO-style ``YYYYMMDD-HHMMSS``).
    """
    if repo_root is None:
        # default = sales-ops-copilot repo root, two levels above this file
        # libs/tcrender/tcrender/narrative.py -> libs/tcrender -> repo root
        repo_root = Path(__file__).resolve().parents[3]
    base = repo_root / "state" / "thinkcell_bridge" / "thinkcellxml_corpus_extended"
    if not base.is_dir():
        return None
    candidates = sorted(
        (p for p in base.iterdir() if p.is_dir()),
        key=lambda p: p.name,
        reverse=True,
    )
    for cand in candidates:
        inv = cand / "schema_inventory.json"
        if inv.exists():
            return inv
    return None


def load_thinkcell_vocabulary_primer(
    *,
    repo_root: Path | None = None,
    chart_classes_max: int = 8,
) -> str:
    """Compact ASCII vocabulary primer for prompt grounding.

    Reads the latest ``schema_inventory.json`` and returns a short
    multi-line block listing the top-N chart class names + the canonical
    SimCorp LAND vocabulary. Falls back to a static block if the corpus
    file isn't reachable (so the module stays runnable in test envs that
    don't ship the corpus).
    """
    chart_classes: list[str] = []
    inv_path = _resolve_schema_inventory_path(repo_root=repo_root)
    if inv_path is not None:
        try:
            import json  # noqa: PLC0415

            data = json.loads(inv_path.read_text(encoding="utf-8"))
            entries = data.get("chart_classes_top_30", [])
            for row in entries[:chart_classes_max]:
                if isinstance(row, list) and row and isinstance(row[0], str):
                    chart_classes.append(row[0])
        except (OSError, ValueError):
            chart_classes = []

    if not chart_classes:
        chart_classes = [
            "CSequenceChartDataScalar",
            "CSequenceChartDataVector",
            "CScatterChartDataVector",
            "CSmartGrid",
            "CGanttVectorTile",
            "CPieChartDataScalarAnchor",
            "CDataAxisLabel",
            "CTextVariable",
        ]

    parts = [
        "think-cell vocabulary primer (use this phrasing when relevant):",
        "  chart classes: " + ", ".join(chart_classes),
        "  LAND vocabulary: " + ", ".join(_LAND_VOCABULARY),
    ]
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# DEFAULT_INSIGHT_BINDINGS -- canonical chart-insight bindings
# ---------------------------------------------------------------------------
#
# Each tuple is (insight_binding_name, source_binding_name, chart_kind).
# ``source_binding_name`` is the existing chart/table binding whose data
# the prompt grounds in. ``chart_kind`` is a short hint embedded in the
# prompt so Claude knows the chart shape (e.g. "waterfall", "bar by stage",
# "Mekko 2D"). Maintained alongside scripts/build_ppttc.py.
DEFAULT_INSIGHT_BINDINGS: tuple[tuple[str, str, str], ...] = (
    ("S04_Insight", "S04_PipeMovement", "waterfall ARR movement"),
    ("S05_Insight", "S05_PipelineByStage", "bar by Stage 1-8"),
    ("S06_Insight", "S06_PipelineAging", "bar by age bucket"),
    ("S07_Insight", "S07_TopDealsLand", "top-deals table"),
    ("S13_Insight", "S13_ForecastCategory", "bar by Forecast Category"),
    ("S15_Insight", "S15_ByOwner", "bar by owner"),
    ("S16_Insight", "S16_StageByIndustry", "Mekko 2D Stage x Industry"),
    ("S17_Insight", "S17_TerritoryPerformance", "bar by country"),
    ("S18_Insight", "S18_WinsLossesQTD", "wins vs losses bar"),
    ("S19_Insight", "S19_Velocity", "bar of median age days by Stage"),
    ("S21_Insight", "S21_ConcentrationTable", "concentration tiers table"),
    ("S22_Insight", "S22_StaleActivity", "stale activity bar"),
    ("S25_Insight", "S25_PipelineCreationVelocity", "ARR creation by week"),
)


# ---------------------------------------------------------------------------
# Helpers shared by the rich-narrative generators
# ---------------------------------------------------------------------------


def _ppttc_table_for(binding_name: str, ppttc_entries: Iterable[Any]) -> list[list[Any]] | None:
    """Pick the ``table`` payload for a binding from a ``.ppttc`` data list.

    ``ppttc_entries`` is the list of ``{"name", "table"}`` dicts that
    ``build_ppttc.py`` emits per director. Cells in the table are either
    ``None`` or single-key wrapper dicts (``{"string": ...}`` /
    ``{"number": ...}`` / etc.); we unwrap them to their bare value so the
    prompt preview is human-readable.
    """
    for entry in ppttc_entries:
        if not isinstance(entry, dict):
            continue
        if entry.get("name") != binding_name:
            continue
        table = entry.get("table")
        if not isinstance(table, list):
            return None
        unwrapped: list[list[Any]] = []
        for row in table:
            if not isinstance(row, list):
                return None
            unwrapped.append([_unwrap_ppttc_cell(cell) for cell in row])
        return unwrapped
    return None


def _unwrap_ppttc_cell(cell: Any) -> Any:
    if cell is None:
        return None
    if isinstance(cell, dict):
        for key in ("string", "number", "percentage", "date"):
            if key in cell:
                return cell[key]
        return None
    return cell


def _table_is_empty(table: list[list[Any]] | None) -> bool:
    if not table:
        return True
    # First row is headers; if every other row's data column is None/blank,
    # treat as empty.
    if len(table) <= 1:
        return True
    body = table[1:]
    for row in body:
        for cell in row[1:]:  # skip the leading category label
            if cell not in (None, "", 0, 0.0):
                return False
    return False


def _format_table_preview(table: list[list[Any]], *, max_rows: int = 8, max_cols: int = 8) -> str:
    rows = []
    for row in table[:max_rows]:
        rendered_cells: list[str] = []
        for cell in row[:max_cols]:
            if cell is None:
                rendered_cells.append("")
            elif isinstance(cell, float):
                rendered_cells.append(f"{cell:g}")
            else:
                rendered_cells.append(_ascii_only(str(cell)))
        rows.append("  | ".join(rendered_cells))
    return "\n".join(rows)


def _enforce_word_cap(text: str, max_words: int) -> str:
    cleaned = _ascii_only(text).strip()
    cleaned = re.sub(r"^(?:[-*•]|[0-9]{1,2}[.)])\s+", "", cleaned).strip()
    return _truncate_words(cleaned, max_words)


# ---------------------------------------------------------------------------
# Public API: rich-narrative generators
# ---------------------------------------------------------------------------


def _build_rich_chart_insight_prompt(
    binding_name: str,
    chart_kind: str,
    table: list[list[Any]],
    ctx: DirectorContext,
    *,
    primer: str,
) -> str:
    preview = _format_table_preview(table)
    return (
        f"{_SYSTEM_GUIDANCE}\n\n"
        f"{primer}\n\n"
        f"Director {ctx.name} ({ctx.scope_label}) {ctx.period}. "
        f"Chart: {binding_name} ({chart_kind}).\n"
        f"Director numbers (for grounding only):\n{ctx.numbers_block()}\n\n"
        f"Chart data:\n{preview}\n\n"
        f"Write ONE caption sentence (under {RICH_INSIGHT_WORDS_MAX} words) that names "
        "the largest specific cell or the clearest trend. Lead with the number / "
        "category / EUR figure. Use only numbers visible above. No spin, no preamble, "
        "no markdown, no bullet marker, no quotes -- just the caption."
    )


def generate_chart_insights(
    ctx: DirectorContext,
    ppttc_entries: Iterable[Any],
    *,
    cache_dir: Path | None = None,
    claude_bin: str | None = None,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
    bindings: Iterable[tuple[str, str, str]] | None = None,
    primer: str | None = None,
) -> dict[str, str]:
    """Generate per-chart insight captions for every chart in DEFAULT_INSIGHT_BINDINGS.

    ``ppttc_entries`` is the ``data`` array build_ppttc.py builds (list of
    ``{"name", "table"}`` dicts). Returns a mapping
    ``insight_binding_name -> caption``. Bindings whose source table is
    missing or empty are silently skipped (no error, no key in the result).
    Per-binding ``NarrativeError`` is also caught -- one bad insight does
    not block the rest -- the failing key is omitted.
    """
    chosen = tuple(bindings) if bindings is not None else DEFAULT_INSIGHT_BINDINGS
    primer_text = primer if primer is not None else load_thinkcell_vocabulary_primer()

    out: dict[str, str] = {}
    entries_list = list(ppttc_entries)
    for insight_name, source_name, chart_kind in chosen:
        table = _ppttc_table_for(source_name, entries_list)
        if _table_is_empty(table):
            continue
        prompt = _build_rich_chart_insight_prompt(
            insight_name, chart_kind, table or [], ctx, primer=primer_text
        )
        try:
            output = _run_with_cache(
                prompt=prompt,
                ctx=ctx,
                binding_kind=f"rich_insight_{insight_name}",
                cache_dir=cache_dir,
                claude_bin=claude_bin,
                timeout=timeout,
            )
        except NarrativeError:
            continue
        cleaned = _ascii_only(output.strip())
        if not cleaned or _looks_like_json(cleaned):
            continue
        # Take the first non-preamble line.
        chosen_line: str | None = None
        for line in cleaned.splitlines():
            candidate = re.sub(r"^(?:[-*•]|[0-9]{1,2}[.)])\s+", "", line.strip()).strip()
            candidate = re.sub(r"^[\"'`]+|[\"'`]+$", "", candidate).strip()
            if not candidate or _looks_like_preamble(candidate):
                continue
            chosen_line = candidate
            break
        if chosen_line is None:
            continue
        out[insight_name] = _enforce_word_cap(chosen_line, RICH_INSIGHT_WORDS_MAX)
    return out


def _build_anomaly_watch_prompt(ctx: DirectorContext, *, primer: str) -> str:
    return (
        f"{_SYSTEM_GUIDANCE}\n\n"
        f"{primer}\n\n"
        f"Context for {ctx.name}'s {ctx.scope_label} {ctx.period} LAND review:\n"
        f"{ctx.context_summary()}\n\n"
        f"Surface {ANOMALY_BULLETS_MIN} to {ANOMALY_BULLETS_MAX} anomaly watch items "
        "for this director. Detect: stale deals over threshold, concentration spikes, "
        "win-rate decline vs prior period, industry over-concentration, pipeline-age "
        ">180d ratio. Format every line EXACTLY: "
        '"EUR <arr>M / <count> deals / <category> - <action>". '
        f"Each line must stay under {ANOMALY_BULLET_WORDS_MAX} words. Lead with the "
        "highest-impact anomaly. No preamble, no closing remarks, no bullet marker, "
        "no markdown -- output ONLY the lines, one per line."
    )


def generate_anomaly_watch(
    ctx: DirectorContext,
    *,
    cache_dir: Path | None = None,
    claude_bin: str | None = None,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
    primer: str | None = None,
) -> str:
    """Generate the multi-line bullet body for ``S98_AnomalyWatch``."""
    primer_text = primer if primer is not None else load_thinkcell_vocabulary_primer()
    prompt = _build_anomaly_watch_prompt(ctx, primer=primer_text)
    output = _run_with_cache(
        prompt=prompt,
        ctx=ctx,
        binding_kind="anomaly_watch",
        cache_dir=cache_dir,
        claude_bin=claude_bin,
        timeout=timeout,
    )
    bullets = _extract_bullets(
        output, max_words=ANOMALY_BULLET_WORDS_MAX, max_bullets=ANOMALY_BULLETS_MAX
    )
    if len(bullets) < ANOMALY_BULLETS_MIN:
        raise NarrativeError(
            f"Anomaly watch returned only {len(bullets)} bullet(s), need >= {ANOMALY_BULLETS_MIN}"
        )
    return "\n".join(f"- {b}" for b in bullets)


def _build_ranked_actions_prompt(ctx: DirectorContext, *, primer: str) -> str:
    return (
        f"{_SYSTEM_GUIDANCE}\n\n"
        f"{primer}\n\n"
        f"Context for {ctx.name}'s {ctx.scope_label} {ctx.period} LAND review:\n"
        f"{ctx.context_summary()}\n\n"
        f"Rank the top {RANKED_ACTIONS_MAX} actions by (impact x urgency). "
        "Each line MUST follow the shape: "
        '"<rank>. <Action> - <target> (<why>) - Due: <date>". '
        f"Each line under {RANKED_ACTIONS_WORDS_MAX} words. Lead with the highest-"
        "impact action. Use only the action items, risks, and stale flags from the "
        "context above; do not invent items. No preamble, no closing remarks, no "
        "markdown. Output ONLY the ranked lines, one per line."
    )


def generate_ranked_actions(
    ctx: DirectorContext,
    *,
    cache_dir: Path | None = None,
    claude_bin: str | None = None,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
    primer: str | None = None,
) -> str:
    """Generate the multi-line bullet body for ``S26_ActionsRanked``."""
    primer_text = primer if primer is not None else load_thinkcell_vocabulary_primer()
    prompt = _build_ranked_actions_prompt(ctx, primer=primer_text)
    output = _run_with_cache(
        prompt=prompt,
        ctx=ctx,
        binding_kind="ranked_actions",
        cache_dir=cache_dir,
        claude_bin=claude_bin,
        timeout=timeout,
    )
    cleaned = _ascii_only(output)
    if _looks_like_json(cleaned):
        raise NarrativeError("Ranked actions returned JSON")
    lines: list[str] = []
    for raw_line in cleaned.splitlines():
        line = raw_line.strip()
        if not line or _looks_like_preamble(line):
            continue
        # Drop any leading bullet/number-bullet so we can rebuild "1. ..."
        stripped = re.sub(r"^(?:[-*•])\s+", "", line).strip()
        # Keep "1. ..." numbering exactly.
        if not re.match(r"^[1-9][0-9]?[.)]\s+", stripped):
            stripped = f"{len(lines) + 1}. {stripped}"
        stripped = _truncate_words(stripped, RANKED_ACTIONS_WORDS_MAX)
        lines.append(stripped)
        if len(lines) >= RANKED_ACTIONS_MAX:
            break
    if not lines:
        raise NarrativeError(f"Ranked actions parse empty: {output!r}")
    return "\n".join(lines)


def _build_cover_subtitle_prompt(ctx: DirectorContext, *, primer: str) -> str:
    return (
        f"{_SYSTEM_GUIDANCE}\n\n"
        f"{primer}\n\n"
        f"Director: {ctx.name} ({ctx.scope_label}). Period: {ctx.period}.\n"
        f"Numbers:\n{ctx.numbers_block()}\n\n"
        "Reduce this director's situation to ONE short cover-page subtitle, "
        f"under {COVER_SUBTITLE_WORDS_MAX} words. Examples (DO NOT copy verbatim): "
        '"Pipeline Health Focus", "Renewal Cycle Push", "Concentration Risk Watch", '
        '"APAC Coverage Build". '
        "Lead with the dominant theme. Title Case. No quotes, no preamble, no period "
        "at the end -- output ONLY the subtitle text, on a single line."
    )


def generate_cover_subtitle(
    ctx: DirectorContext,
    *,
    cache_dir: Path | None = None,
    claude_bin: str | None = None,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
    primer: str | None = None,
) -> str:
    """Generate a short, director-specific cover-page subtitle for S01_Subtitle."""
    primer_text = primer if primer is not None else load_thinkcell_vocabulary_primer()
    prompt = _build_cover_subtitle_prompt(ctx, primer=primer_text)
    output = _run_with_cache(
        prompt=prompt,
        ctx=ctx,
        binding_kind="cover_subtitle",
        cache_dir=cache_dir,
        claude_bin=claude_bin,
        timeout=timeout,
    )
    cleaned = _ascii_only(output.strip())
    if not cleaned or _looks_like_json(cleaned):
        raise NarrativeError("Cover subtitle returned empty or JSON output")
    for line in cleaned.splitlines():
        candidate = re.sub(r"^[\"'`]+|[\"'`]+$", "", line.strip()).strip().rstrip(".")
        candidate = re.sub(r"^(?:[-*•]|[0-9]{1,2}[.)])\s+", "", candidate).strip()
        if not candidate or _looks_like_preamble(candidate):
            continue
        return _enforce_word_cap(candidate, COVER_SUBTITLE_WORDS_MAX).rstrip(".")
    raise NarrativeError(f"No usable cover subtitle line: {output!r}")


# Section names are emitted as bindings prefixed with ``S03/S10/S20/S25``
# (the existing slide numbering for section dividers in the LAND template).
# The mapping below is the contract between this module and build_ppttc.py.
SECTION_HEADERS: tuple[tuple[str, str], ...] = (
    ("S03_Header", "Pipeline"),
    ("S10_Header", "Renewals"),
    ("S20_Header", "Risk"),
    ("S25_Header", "Velocity"),
)


def _build_section_subtitles_prompt(ctx: DirectorContext, *, primer: str) -> str:
    section_lines = "\n".join(f"  {name}" for _, name in SECTION_HEADERS)
    return (
        f"{_SYSTEM_GUIDANCE}\n\n"
        f"{primer}\n\n"
        f"Director: {ctx.name} ({ctx.scope_label}). Period: {ctx.period}.\n"
        f"Numbers:\n{ctx.numbers_block()}\n\n"
        "For EACH of the four section headers below, write a single 1-line subtitle "
        f"(under {SECTION_SUBTITLE_WORDS_MAX} words) that tells the story for THIS "
        "director. Lead with the dominant number for that section.\n"
        "Sections:\n"
        f"{section_lines}\n\n"
        "Format your reply EXACTLY:\n"
        "Pipeline: <subtitle>\n"
        "Renewals: <subtitle>\n"
        "Risk: <subtitle>\n"
        "Velocity: <subtitle>\n"
        "No preamble, no closing remarks, no markdown."
    )


def generate_section_subtitles(
    ctx: DirectorContext,
    *,
    cache_dir: Path | None = None,
    claude_bin: str | None = None,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
    primer: str | None = None,
) -> dict[str, str]:
    """Generate one-line subtitles per section divider.

    Returns a dict keyed by binding name (e.g. ``S03_Header``) -> subtitle.
    Sections that fail to parse (or arrive empty) are simply omitted.
    """
    primer_text = primer if primer is not None else load_thinkcell_vocabulary_primer()
    prompt = _build_section_subtitles_prompt(ctx, primer=primer_text)
    output = _run_with_cache(
        prompt=prompt,
        ctx=ctx,
        binding_kind="section_subtitles",
        cache_dir=cache_dir,
        claude_bin=claude_bin,
        timeout=timeout,
    )
    cleaned = _ascii_only(output)
    if _looks_like_json(cleaned):
        raise NarrativeError("Section subtitles returned JSON")
    by_section: dict[str, str] = {}
    for raw_line in cleaned.splitlines():
        line = raw_line.strip()
        if not line or _looks_like_preamble(line):
            continue
        match = re.match(
            r"^(?:[-*•]\s*)?(?P<key>[A-Za-z][A-Za-z ]{2,32}?)\s*[:\-]\s*(?P<body>.+)$", line
        )
        if not match:
            continue
        key = match.group("key").strip().rstrip(":").strip()
        body = match.group("body").strip().strip('"').strip("'")
        if not body:
            continue
        by_section[key.lower()] = _enforce_word_cap(body, SECTION_SUBTITLE_WORDS_MAX)

    out: dict[str, str] = {}
    for binding, section in SECTION_HEADERS:
        body = by_section.get(section.lower())
        if body:
            out[binding] = body
    return out
