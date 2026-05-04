"""Consulting-grade image-based chart renderer for the LAND deck factory.

Why this exists
~~~~~~~~~~~~~~~

``native_fallback.py`` populates chart slides with python-pptx native chart
shapes (Office-default look, axis-format bugs like ``0,0000`` showing through
on numFmt linkage). Andre's prior shipped LAND decks (Sarah Pittroff bundle)
used **PNG images** of charts rendered by an external pipeline and embedded
into a python-pptx-styled deck -- 0 native charts, 17 embedded images per
director. This module reproduces that pattern.

Inputs are the same parsed ``.ppttc`` table-of-tables that ``native_fallback``
reads (``list[list[None | dict]]``). Outputs are PNGs rendered with matplotlib
under the SimCorp brand palette (verified earlier from theme1.xml of the donor
template). The PNGs are then embedded back into the deck via python-pptx,
replacing the native chart graphic-frames produced by ``native_fallback``.

Architectural rules
~~~~~~~~~~~~~~~~~~~

* Independent layer: this module **does not** import from ``native_fallback``.
  Both layers can run together (image charts replace native charts after
  fallback runs) or independently.
* Native ``native_fallback`` table renderers stay -- image-rendering tables
  doesn't make sense (the layer renders S07/S08/S09/S11/S22/S24/S26 as native
  PowerPoint tables and we keep those).
* The module never mutates the input deck. ``enhance_deck_with_images`` writes
  to a new path.
* Pure stdlib + matplotlib + python-pptx + lxml (already deps of the venv).

Public API
~~~~~~~~~~

* :data:`SIMCORP_BRAND` -- brand palette dict.
* :data:`SIMCORP_FONT` -- preferred font name (matplotlib falls back to system).
* :class:`ImageChartResult` -- frozen result of :func:`render_chart_image`.
* :func:`render_chart_image` -- main: ``binding_name`` + ``table_data`` -> PNG.
* :func:`enhance_deck_with_images` -- walk a rendered deck, render each chart
  binding's data as a PNG, embed via python-pptx.

ASCII-only, type-hinted, no chart-junk.
"""

from __future__ import annotations

import json
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")  # non-interactive backend (must be set before pyplot import)

import matplotlib.patches as mpatches  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
from lxml import etree  # noqa: E402
from pptx import Presentation  # noqa: E402
from pptx.oxml.ns import qn  # noqa: E402
from pptx.util import Emu  # noqa: E402

# ----------------------------------------------------------- brand definition


SIMCORP_BRAND: dict[str, str] = {
    "primary": "#083EA7",  # SimCorp navy -- primary fill
    "accent_dark": "#1A1D31",  # near-black -- titles
    "purple": "#4B17B6",  # accent
    "warning_coral": "#EF3E4A",  # losses, lost, high risk
    "highlight": "#FB9B2A",  # callouts, medium risk
    "tertiary_gold": "#F0CF61",  # tertiary
    "hyperlink": "#0A7BD7",  # links
    "neutral_dark": "#1A1D31",  # body text
    "neutral_mid": "#9CA3AF",  # axis lines
    "neutral_light": "#E3E3E3",  # row stripes
    "success_green": "#3F8F5F",  # gains, won (consulting standard)
}

SIMCORP_FONT: str = "Microsoft Sans Serif"

# Stage gradient: SimCorp navy -> light blue -> warm tail. Used by Mekko.
_STAGE_GRADIENT: tuple[str, ...] = (
    "#083EA7",  # navy primary
    "#2E59B4",
    "#5479C2",
    "#7A99D0",
    "#A0B9DE",
    "#C7D9EC",
    "#E0CC8C",  # warm transition
    "#D4A93A",  # gold tail
)

# Per-binding render kind (drives the dispatch in render_chart_image).
_BINDING_KIND: dict[str, str] = {
    "S04_PipeMovement": "waterfall",
    "S05_PipelineByStage": "bar_stage",
    "S06_PipelineAging": "bar_aging",
    "S13_ForecastCategory": "bar_forecast",
    "S15_ByOwner": "bar_horizontal",
    "S16_StageByIndustry": "mekko",
    "S17_TerritoryPerformance": "bar_territory",
    "S18_WinsLossesQTD": "bar_grouped_winloss",
    "S19_Velocity": "bar_velocity",
    "S21_ConcentrationRiskChart": "bar_concentration",
    "S22_StaleActivity": "bar_stale",
    "S25_PipelineCreationVelocity": "line",
}

# Per-binding human-readable title (chart title text).
_BINDING_TITLE: dict[str, str] = {
    "S04_PipeMovement": "Pipe movement (ARR EUR M)",
    "S05_PipelineByStage": "Pipeline by stage",
    "S06_PipelineAging": "Pipeline aging",
    "S13_ForecastCategory": "Forecast category",
    "S15_ByOwner": "Open ARR by owner",
    "S16_StageByIndustry": "Stage mix by industry",
    "S17_TerritoryPerformance": "Territory performance",
    "S18_WinsLossesQTD": "Wins / losses QTD",
    "S19_Velocity": "Velocity (median age by stage)",
    "S21_ConcentrationRiskChart": "Concentration risk",
    "S22_StaleActivity": "Stale activity by stage",
    "S25_PipelineCreationVelocity": "Pipeline creation velocity",
}

# Stable slide indices for chart bindings in the canonical LAND template.
_BINDING_TO_SLIDE: dict[str, int] = {
    "S04_PipeMovement": 4,
    "S05_PipelineByStage": 5,
    "S06_PipelineAging": 6,
    "S13_ForecastCategory": 13,
    "S15_ByOwner": 15,
    "S16_StageByIndustry": 16,
    "S17_TerritoryPerformance": 17,
    "S18_WinsLossesQTD": 18,
    "S19_Velocity": 19,
    "S21_ConcentrationRiskChart": 21,
    "S22_StaleActivity": 22,
    "S25_PipelineCreationVelocity": 25,
}

# Default canvas where the rendered PNG sits inside the slide. Mirrors the
# native_fallback canvas so the two layers occupy the same visual real estate.
_CANVAS_LEFT_EMU = 457_200
_CANVAS_TOP_EMU = 1_557_338
_CANVAS_WIDTH_EMU = 7_750_000
_CANVAS_HEIGHT_EMU = 4_700_000

# Render at 200 DPI for retina sharpness; matplotlib also stores logical size.
_RENDER_DPI = 200


# -------------------------------------------------------- result dataclasses


@dataclass(frozen=True)
class ImageChartResult:
    """Outcome of :func:`render_chart_image`.

    Attributes:
        image_path: Absolute path to the rendered PNG.
        dimensions_px: (width, height) of the rendered PNG in pixels.
        binding_kind: Render kind chosen ("bar", "mekko", "line", "waterfall",
            "grouped_bar"). Useful for reporting + tests.
    """

    image_path: Path
    dimensions_px: tuple[int, int]
    binding_kind: str


@dataclass(frozen=True)
class EnhanceImagesResult:
    """Outcome of :func:`enhance_deck_with_images`.

    Attributes:
        enhanced_path: Path to the new .pptx written.
        bindings_rendered: Bindings whose chart was replaced with a PNG.
        skipped: Pairs of (binding_name, reason) for bindings the renderer
            chose not to insert (no slide match, missing data, render error).
        png_paths: Mapping of binding_name -> rendered PNG path (under the
            tempdir managed by this run; cleaned up after embed).
    """

    enhanced_path: Path
    bindings_rendered: list[str] = field(default_factory=list)
    skipped: list[tuple[str, str]] = field(default_factory=list)
    png_paths: dict[str, Path] = field(default_factory=dict)


# -------------------------------------------------------- table parse helpers


def _cell_str(cell: Any) -> str:
    if isinstance(cell, dict):
        v = cell.get("string")
        if isinstance(v, str):
            return v
        v = cell.get("number")
        if isinstance(v, (int, float)):
            return f"{v}"
    return ""


def _cell_num(cell: Any) -> float | None:
    if isinstance(cell, dict):
        v = cell.get("number")
        if isinstance(v, (int, float)):
            return float(v)
    return None


def _split_chart_table(table: list[Any]) -> tuple[list[str], list[float]]:
    """Two-row table -> (categories, values). Missing nums become 0.0."""
    if not isinstance(table, list) or len(table) < 2:
        return [], []
    header_row = table[0]
    value_row = table[1]
    if not isinstance(header_row, list) or not isinstance(value_row, list):
        return [], []
    cats: list[str] = []
    for cell in header_row[1:]:
        s = _cell_str(cell)
        if s:
            cats.append(s)
    vals: list[float] = []
    for cell in value_row[1 : len(cats) + 1]:
        n = _cell_num(cell)
        vals.append(0.0 if n is None else n)
    # Pad if mismatch
    while len(vals) < len(cats):
        vals.append(0.0)
    return cats, vals


def _truncate(s: str, n: int = 18) -> str:
    if not isinstance(s, str):
        return ""
    return s if len(s) <= n else s[: n - 1] + "..."


def _fmt_eur_m(value: float) -> str:
    """Render an mEUR-scale value as ``EUR 5.1M`` (always M-suffixed)."""
    return f"EUR {value:.1f}M"


def _fmt_days(value: float) -> str:
    return f"{value:.0f} d"


def _fmt_pct(value: float) -> str:
    return f"{value:.0f}%"


# ----------------------------------------------------- common axes treatment


def _apply_consulting_axes(
    ax: Any,
    *,
    title: str,
    subtitle: str | None = None,
    y_label: str | None = None,
    show_y_grid: bool = True,
) -> None:
    """Apply title + subtitle + axis treatment shared by all renderers."""
    # Title (top-left, bold, accent_dark)
    ax.set_title(
        title,
        fontsize=14,
        fontweight="bold",
        color=SIMCORP_BRAND["accent_dark"],
        loc="left",
        pad=22 if subtitle else 8,
    )
    # Subtitle: small grey text drawn just below the title in axes-coords.
    if subtitle:
        ax.text(
            0.0,
            1.02,
            subtitle,
            transform=ax.transAxes,
            fontsize=10,
            color=SIMCORP_BRAND["neutral_mid"],
            ha="left",
            va="bottom",
        )
    # Spines: hide top + right; soften bottom + left.
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color(SIMCORP_BRAND["neutral_mid"])
    ax.spines["bottom"].set_color(SIMCORP_BRAND["neutral_mid"])
    ax.spines["left"].set_linewidth(0.6)
    ax.spines["bottom"].set_linewidth(0.6)
    # Tick labels
    ax.tick_params(
        axis="both",
        which="major",
        colors=SIMCORP_BRAND["neutral_mid"],
        labelsize=9,
        length=0,
    )
    # Y-axis grid only (light)
    if show_y_grid:
        ax.yaxis.grid(
            True,
            color=SIMCORP_BRAND["neutral_light"],
            linewidth=0.6,
            alpha=0.9,
        )
        ax.set_axisbelow(True)
    # Y-axis label
    if y_label:
        ax.set_ylabel(
            y_label,
            fontsize=9,
            color=SIMCORP_BRAND["neutral_mid"],
        )


def _new_figure(width_in: float, height_in: float) -> tuple[Any, Any]:
    """Create a matplotlib figure + axes with consulting defaults."""
    fig, ax = plt.subplots(figsize=(width_in, height_in), dpi=_RENDER_DPI)
    fig.patch.set_facecolor("white")
    ax.set_facecolor("white")
    plt.rcParams["font.family"] = ["sans-serif"]
    plt.rcParams["font.sans-serif"] = [
        SIMCORP_FONT,
        "Helvetica",
        "Arial",
        "DejaVu Sans",
    ]
    return fig, ax


def _save_figure(fig: Any, output_path: Path) -> tuple[int, int]:
    """Save fig to ``output_path`` at retina DPI; return (width_px, height_px)."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(
        str(output_path),
        dpi=_RENDER_DPI,
        bbox_inches="tight",
        pad_inches=0.18,
        facecolor="white",
    )
    plt.close(fig)
    # Read actual rendered dimensions from the PNG header (bbox_inches='tight'
    # changes the saved size relative to fig.get_size_inches()).
    return _png_actual_dims(output_path)


def _png_actual_dims(path: Path) -> tuple[int, int]:
    """Parse PNG IHDR to return the saved (width_px, height_px)."""
    import struct

    data = path.read_bytes()
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        return (0, 0)
    width = struct.unpack(">I", data[16:20])[0]
    height = struct.unpack(">I", data[20:24])[0]
    return width, height


# ============================================================================
#                          CHART RENDERERS
# ============================================================================


# ---- waterfall (S04) -------------------------------------------------------


def _render_waterfall(
    table: list[Any],
    *,
    title: str,
    subtitle: str,
    width_in: float,
    height_in: float,
    output_path: Path,
) -> tuple[int, int]:
    """Anchor + delta waterfall.

    Anchors (first + last) use SimCorp navy; gains green; losses coral.
    Connector line between bars. EUR M value labels above each bar.
    """
    cats, vals = _split_chart_table(table)
    if not cats:
        cats, vals = ["(no data)"], [0.0]
    fig, ax = _new_figure(width_in, height_in)

    # Compute running totals so connector lines join visually like a waterfall.
    n = len(vals)
    cumulative = 0.0
    rect_bottoms: list[float] = []
    rect_heights: list[float] = []
    rect_colors: list[str] = []
    for i, v in enumerate(vals):
        if i == 0 or i == n - 1:
            # Anchor: full-height bar from 0 to (cumulative + v).
            rect_bottoms.append(0.0)
            if i == 0:
                cumulative = v
                rect_heights.append(v)
            else:
                # Last anchor: ends at cumulative (which already includes prior deltas)
                rect_heights.append(cumulative)
            rect_colors.append(SIMCORP_BRAND["primary"])
        else:
            # Delta: floats between previous and new cumulative
            if v >= 0:
                rect_bottoms.append(cumulative)
                rect_heights.append(v)
                rect_colors.append(SIMCORP_BRAND["success_green"])
            else:
                rect_bottoms.append(cumulative + v)
                rect_heights.append(-v)
                rect_colors.append(SIMCORP_BRAND["warning_coral"])
            cumulative += v

    xs = list(range(n))
    bar_width = 0.62
    for x, b, h, c in zip(xs, rect_bottoms, rect_heights, rect_colors, strict=True):
        ax.bar(x, h, bottom=b, color=c, width=bar_width, edgecolor="white", linewidth=0.5)

    # Connector lines between bar tops/bottoms
    for i in range(n - 1):
        if i == 0:
            y_left = rect_heights[0]  # anchor top
        else:
            y_left = rect_bottoms[i] + rect_heights[i] if vals[i] >= 0 else rect_bottoms[i]
        if i + 1 == n - 1:
            y_right = rect_heights[i + 1]
        else:
            y_right = (
                rect_bottoms[i + 1]
                if vals[i + 1] >= 0
                else (rect_bottoms[i + 1] + rect_heights[i + 1])
            )
        ax.plot(
            [i + bar_width / 2, i + 1 - bar_width / 2],
            [y_left, y_right],
            color=SIMCORP_BRAND["neutral_mid"],
            linewidth=0.8,
            linestyle="--",
            alpha=0.7,
        )

    # Value labels above each bar
    for x, b, h, v in zip(xs, rect_bottoms, rect_heights, vals, strict=True):
        ax.text(
            x,
            b + h + 0.12 * max(rect_heights + [1.0]),
            _fmt_eur_m(v),
            ha="center",
            va="bottom",
            fontsize=9,
            color=SIMCORP_BRAND["accent_dark"],
            fontweight="semibold",
        )

    ax.set_xticks(xs)
    ax.set_xticklabels([_truncate(c, 22) for c in cats], rotation=0, fontsize=9)
    _apply_consulting_axes(ax, title=title, subtitle=subtitle, y_label="ARR (EUR M)")
    return _save_figure(fig, output_path)


# ---- single-series bar (S05/S06/S13/S17/S19/S21/S22) -----------------------


def _render_bar(
    table: list[Any],
    *,
    title: str,
    subtitle: str,
    kind: str,
    width_in: float,
    height_in: float,
    output_path: Path,
) -> tuple[int, int]:
    """Single-series clustered column with kind-specific color rules.

    kind in {bar_stage, bar_aging, bar_forecast, bar_territory,
    bar_velocity, bar_concentration, bar_stale}.
    """
    cats, vals = _split_chart_table(table)
    if not cats:
        cats, vals = ["(no data)"], [0.0]
    fig, ax = _new_figure(width_in, height_in)

    # Per-bar coloring rules
    if kind == "bar_aging":
        # bars representing buckets >365d in coral
        colors: list[str] = []
        for c in cats:
            high = any(token in c for token in (">365", ">730", "366-730"))
            colors.append(SIMCORP_BRAND["warning_coral"] if high else SIMCORP_BRAND["primary"])
    elif kind == "bar_velocity":
        colors = [
            SIMCORP_BRAND["warning_coral"] if v > 365 else SIMCORP_BRAND["primary"] for v in vals
        ]
    elif kind == "bar_concentration":
        colors = [
            SIMCORP_BRAND["warning_coral"] if v > 80 else SIMCORP_BRAND["primary"] for v in vals
        ]
    elif kind == "bar_forecast":
        cat_palette = {
            "Pipeline": SIMCORP_BRAND["primary"],
            "Best Case": SIMCORP_BRAND["highlight"],
            "Commit": SIMCORP_BRAND["tertiary_gold"],
            "Closed - Won": SIMCORP_BRAND["success_green"],
            "Closed Won": SIMCORP_BRAND["success_green"],
            "Closed": SIMCORP_BRAND["success_green"],
            "Omitted": SIMCORP_BRAND["neutral_mid"],
            "(unset)": SIMCORP_BRAND["neutral_mid"],
        }
        colors = [cat_palette.get(c, SIMCORP_BRAND["primary"]) for c in cats]
    elif kind == "bar_stale":
        colors = [SIMCORP_BRAND["warning_coral"]] * len(cats)
    else:
        colors = [SIMCORP_BRAND["primary"]] * len(cats)

    xs = list(range(len(cats)))
    ax.bar(xs, vals, color=colors, width=0.62, edgecolor="white", linewidth=0.5)

    # Value labels
    if vals:
        max_v = max(vals + [1e-6])
        for x, v in zip(xs, vals, strict=True):
            if kind == "bar_velocity":
                lbl = _fmt_days(v)
            elif kind == "bar_concentration":
                lbl = _fmt_pct(v)
            else:
                lbl = _fmt_eur_m(v)
            ax.text(
                x,
                v + 0.025 * max_v,
                lbl,
                ha="center",
                va="bottom",
                fontsize=9,
                color=SIMCORP_BRAND["accent_dark"],
                fontweight="semibold",
            )
        # Concentration: dashed 80% threshold line
        if kind == "bar_concentration" and max_v > 0:
            ax.axhline(
                80.0,
                color=SIMCORP_BRAND["neutral_mid"],
                linestyle="--",
                linewidth=0.9,
                alpha=0.8,
            )
            ax.text(
                len(xs) - 0.5,
                80.0,
                "  80% threshold",
                ha="right",
                va="bottom",
                fontsize=8,
                color=SIMCORP_BRAND["neutral_mid"],
            )

    ax.set_xticks(xs)
    rotation = 30 if any(len(c) > 10 for c in cats) else 0
    ax.set_xticklabels(
        [_truncate(c, 22) for c in cats],
        rotation=rotation,
        fontsize=9,
        ha="right" if rotation else "center",
    )

    if kind == "bar_velocity":
        y_label = "Median age (days)"
    elif kind == "bar_concentration":
        y_label = "Share (%)"
    elif kind == "bar_stale":
        y_label = "Stale opps (count)"
    else:
        y_label = "ARR (EUR M)"

    _apply_consulting_axes(ax, title=title, subtitle=subtitle, y_label=y_label)
    return _save_figure(fig, output_path)


# ---- horizontal owner bar (S15) --------------------------------------------


def _render_bar_horizontal(
    table: list[Any],
    *,
    title: str,
    subtitle: str,
    width_in: float,
    height_in: float,
    output_path: Path,
) -> tuple[int, int]:
    """Top-10 horizontal bars; names truncated, ARR labels at bar end."""
    cats, vals = _split_chart_table(table)
    if not cats:
        cats, vals = ["(no data)"], [0.0]
    pairs = sorted(zip(cats, vals, strict=False), key=lambda p: -p[1])[:10]
    cats = [_truncate(c, 18) for c, _ in pairs]
    vals = [v for _, v in pairs]

    fig, ax = _new_figure(width_in, height_in)
    ys = list(range(len(cats)))
    ax.barh(ys, vals, color=SIMCORP_BRAND["primary"], height=0.62, edgecolor="white", linewidth=0.5)
    # Reverse so top owner is at top
    ax.invert_yaxis()

    if vals:
        max_v = max(vals + [1e-6])
        for y, v in zip(ys, vals, strict=True):
            ax.text(
                v + 0.015 * max_v,
                y,
                _fmt_eur_m(v),
                ha="left",
                va="center",
                fontsize=9,
                color=SIMCORP_BRAND["accent_dark"],
                fontweight="semibold",
            )

    ax.set_yticks(ys)
    ax.set_yticklabels(cats, fontsize=9)
    # Strip vertical grid; keep none for horizontal-bar look.
    _apply_consulting_axes(ax, title=title, subtitle=subtitle, y_label=None, show_y_grid=False)
    ax.xaxis.grid(True, color=SIMCORP_BRAND["neutral_light"], linewidth=0.6, alpha=0.9)
    ax.set_axisbelow(True)
    ax.set_xlabel("ARR (EUR M)", fontsize=9, color=SIMCORP_BRAND["neutral_mid"])
    return _save_figure(fig, output_path)


# ---- grouped wins/losses bar (S18) -----------------------------------------


def _render_bar_grouped_winloss(
    table: list[Any],
    *,
    title: str,
    subtitle: str,
    width_in: float,
    height_in: float,
    output_path: Path,
) -> tuple[int, int]:
    """Won (green) vs Lost (coral) grouped bars across ARR/ACV rows."""
    if not isinstance(table, list) or len(table) < 2 or not isinstance(table[0], list):
        # Defensive: empty
        cats, group_labels, matrix = (
            ["Won", "Lost"],
            ["(no data)"],
            [[0.0, 0.0]],
        )
    else:
        cats = [_cell_str(c) for c in table[0][1:] if _cell_str(c)]
        group_labels: list[str] = []
        matrix: list[list[float]] = []
        for row in table[1:]:
            if not isinstance(row, list) or not row:
                continue
            label = _cell_str(row[0]) or "Series"
            nums = [(_cell_num(c) or 0.0) for c in row[1 : len(cats) + 1]]
            while len(nums) < len(cats):
                nums.append(0.0)
            group_labels.append(label)
            matrix.append(nums)
        if not group_labels:
            group_labels, matrix = ["(no data)"], [[0.0] * len(cats)]

    fig, ax = _new_figure(width_in, height_in)
    n_groups = len(group_labels)
    bar_w = 0.34
    xs = list(range(n_groups))

    # color per category index
    cat_colors = [
        SIMCORP_BRAND["success_green"]
        if c.lower().startswith("won")
        else SIMCORP_BRAND["warning_coral"]
        for c in cats
    ]

    max_v = 1e-6
    for c_idx, c in enumerate(cats):
        offsets = [x + (c_idx - (len(cats) - 1) / 2) * bar_w for x in xs]
        values = [matrix[g][c_idx] for g in range(n_groups)]
        ax.bar(
            offsets,
            values,
            width=bar_w,
            color=cat_colors[c_idx],
            edgecolor="white",
            linewidth=0.5,
            label=c,
        )
        max_v = max(max_v, max(values + [0.0]))
        for off, v in zip(offsets, values, strict=True):
            if v == 0:
                continue
            ax.text(
                off,
                v + 0.025 * max_v,
                _fmt_eur_m(v),
                ha="center",
                va="bottom",
                fontsize=8,
                color=SIMCORP_BRAND["accent_dark"],
                fontweight="semibold",
            )

    ax.set_xticks(xs)
    ax.set_xticklabels([_truncate(g, 24) for g in group_labels], fontsize=9)
    _apply_consulting_axes(ax, title=title, subtitle=subtitle, y_label="EUR M")
    # Inline legend (top-right)
    ax.legend(
        frameon=False,
        fontsize=9,
        loc="upper right",
        labelcolor=SIMCORP_BRAND["accent_dark"],
    )
    return _save_figure(fig, output_path)


# ---- mekko (S16) -- THE chart ----------------------------------------------


def _render_mekko(
    table: list[Any],
    *,
    title: str,
    subtitle: str,
    width_in: float,
    height_in: float,
    output_path: Path,
) -> tuple[int, int]:
    """True proportional-width Mekko via raw matplotlib rectangles.

    * Column widths = (industry total / grand total) * canvas width.
    * Within column: stages stack with HEIGHT = stage's share of column.
    * 8-shade gradient navy -> light blue -> warm tail across stages.
    * Industry name + total labelled above each column ("Pension\\n11.8M").
    * Percentages drawn inside cells where >= 5%.
    * Y-axis labelled 0..100%; subtle baseline.
    """
    if not isinstance(table, list) or not table or not isinstance(table[0], list):
        return _render_bar(
            [[None, {"string": "(no data)"}], [{"string": "Empty"}, {"number": 0.0}]],
            title=title,
            subtitle=subtitle,
            kind="bar_stage",
            width_in=width_in,
            height_in=height_in,
            output_path=output_path,
        )

    industries = [_cell_str(c) for c in table[0][1:] if _cell_str(c)]
    n_industries = len(industries)
    if n_industries == 0:
        return _render_bar(
            [[None, {"string": "(no data)"}], [{"string": "Empty"}, {"number": 0.0}]],
            title=title,
            subtitle=subtitle,
            kind="bar_stage",
            width_in=width_in,
            height_in=height_in,
            output_path=output_path,
        )

    stages: list[str] = []
    matrix: list[list[float]] = []  # rows = stages, cols = industries
    for row in table[1:]:
        if not isinstance(row, list) or not row:
            continue
        stages.append(_cell_str(row[0]))
        nums = [(_cell_num(c) or 0.0) for c in row[1:]]
        if len(nums) < n_industries:
            nums = nums + [0.0] * (n_industries - len(nums))
        nums = nums[:n_industries]
        matrix.append(nums)
    if not stages:
        stages, matrix = ["(none)"], [[0.0] * n_industries]

    # Column totals
    col_totals = [sum(matrix[s][i] for s in range(len(stages))) for i in range(n_industries)]
    grand_total = sum(col_totals) or 1.0

    fig, ax = _new_figure(width_in, height_in)

    # Draw within unit-square (x in [0,1], y in [0,1] = percent share)
    cur_x = 0.0
    min_w = 0.015  # avoid zero-width slivers
    column_widths: list[float] = []
    for i in range(n_industries):
        if grand_total > 0:
            w = max(col_totals[i] / grand_total, min_w if col_totals[i] > 0 else 0.0)
        else:
            w = 1.0 / n_industries
        column_widths.append(w)

    # Renormalize so widths sum to 1.0 even after min_w padding
    s = sum(column_widths) or 1.0
    column_widths = [w / s for w in column_widths]

    cur_x = 0.0
    for i, industry in enumerate(industries):
        col_w = column_widths[i]
        col_total = col_totals[i] if col_totals[i] > 0 else 1.0
        cur_y = 0.0
        for s_idx, _stage_name in enumerate(stages):
            stage_val = matrix[s_idx][i]
            frac = stage_val / col_total if col_total > 0 else 0.0
            if frac <= 0:
                continue
            color_hex = _STAGE_GRADIENT[s_idx % len(_STAGE_GRADIENT)]
            rect = mpatches.Rectangle(
                (cur_x, cur_y),
                col_w * 0.97,  # gutter between columns
                frac,
                facecolor=color_hex,
                edgecolor="white",
                linewidth=0.6,
            )
            # Tag for downstream test introspection -- mekko data cells only
            rect.set_gid("mekko_cell")
            ax.add_patch(rect)
            # Inline percentage label if >=5% and segment is tall enough
            if frac >= 0.05:
                pct = frac * 100
                # White label on dark stages, dark label on light stages
                label_color = "white" if s_idx <= 2 else SIMCORP_BRAND["accent_dark"]
                ax.text(
                    cur_x + (col_w * 0.97) / 2,
                    cur_y + frac / 2,
                    f"{pct:.0f}%",
                    ha="center",
                    va="center",
                    fontsize=8,
                    color=label_color,
                    fontweight="bold",
                )
            cur_y += frac
        # Industry header above column (name + total)
        ax.text(
            cur_x + (col_w * 0.97) / 2,
            1.045,
            f"{_truncate(industry, 14)}\n{_fmt_eur_m(col_totals[i])}",
            ha="center",
            va="bottom",
            fontsize=8.5,
            color=SIMCORP_BRAND["accent_dark"],
            fontweight="semibold",
        )
        cur_x += col_w

    # Axes
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.set_yticks([0, 0.25, 0.50, 0.75, 1.0])
    ax.set_yticklabels(["0%", "25%", "50%", "75%", "100%"], fontsize=9)
    ax.set_xticks([])

    # Hide all frame except left axis tick labels
    for sp in ("top", "right", "bottom"):
        ax.spines[sp].set_visible(False)
    ax.spines["left"].set_color(SIMCORP_BRAND["neutral_mid"])
    ax.spines["left"].set_linewidth(0.6)
    ax.tick_params(axis="y", colors=SIMCORP_BRAND["neutral_mid"], length=0)

    # Title + subtitle (manually -- _apply_consulting_axes layouts depend on x ticks)
    ax.set_title(
        title,
        fontsize=14,
        fontweight="bold",
        color=SIMCORP_BRAND["accent_dark"],
        loc="left",
        pad=46,
    )
    if subtitle:
        ax.text(
            0.0,
            1.18,
            subtitle,
            transform=ax.transAxes,
            fontsize=10,
            color=SIMCORP_BRAND["neutral_mid"],
            ha="left",
            va="bottom",
        )

    # Legend strip below the plot
    handles = [
        mpatches.Patch(
            color=_STAGE_GRADIENT[s_idx % len(_STAGE_GRADIENT)], label=_truncate(stages[s_idx], 16)
        )
        for s_idx in range(len(stages))
    ]
    ax.legend(
        handles=handles,
        loc="upper center",
        bbox_to_anchor=(0.5, -0.05),
        ncol=min(len(stages), 4),
        frameon=False,
        fontsize=8,
        labelcolor=SIMCORP_BRAND["accent_dark"],
    )

    return _save_figure(fig, output_path)


# ---- line (S25) ------------------------------------------------------------


def _render_line(
    table: list[Any],
    *,
    title: str,
    subtitle: str,
    width_in: float,
    height_in: float,
    output_path: Path,
) -> tuple[int, int]:
    """Single navy line with circle markers, weeks on x, EUR M on y."""
    cats, vals = _split_chart_table(table)
    if not cats:
        cats, vals = ["(no data)"], [0.0]
    fig, ax = _new_figure(width_in, height_in)
    xs = list(range(len(cats)))
    ax.plot(
        xs,
        vals,
        color=SIMCORP_BRAND["primary"],
        marker="o",
        markersize=5,
        linewidth=2.0,
        markerfacecolor=SIMCORP_BRAND["primary"],
        markeredgecolor="white",
        markeredgewidth=1.0,
    )

    if vals:
        max_v = max(vals + [1e-6])
        for x, v in zip(xs, vals, strict=True):
            if v == 0:
                continue
            ax.text(
                x,
                v + 0.04 * max_v,
                _fmt_eur_m(v),
                ha="center",
                va="bottom",
                fontsize=8,
                color=SIMCORP_BRAND["accent_dark"],
                fontweight="semibold",
            )

    ax.set_xticks(xs)
    ax.set_xticklabels(cats, fontsize=9, rotation=0)
    _apply_consulting_axes(ax, title=title, subtitle=subtitle, y_label="ARR (EUR M)")
    return _save_figure(fig, output_path)


# ============================================================================
#                          PUBLIC API DISPATCH
# ============================================================================


def render_chart_image(
    *,
    binding_name: str,
    table_data: list[Any],
    output_path: Path,
    width_in: float = 10.0,
    height_in: float = 5.5,
    director_name: str = "",
    period: str = "",
    scope_label: str = "",
    title_override: str | None = None,
) -> ImageChartResult:
    """Render a single chart binding to a PNG.

    Args:
        binding_name: One of the keys in :data:`_BINDING_KIND` (e.g.
            ``"S16_StageByIndustry"``). Bindings outside this set are not
            chart bindings and raise ``ValueError``.
        table_data: Parsed ``.ppttc`` table, ``list[list[None | dict]]`` shape.
        output_path: Where the PNG is written. Parent dir is created.
        width_in, height_in: Logical figure size in inches; rendered at 200 DPI.
        director_name: Optional, injected into the chart subtitle.
        period: Optional period label (``"2026-Q2"``).
        scope_label: Optional scope label (``"APAC"``).
        title_override: Optional override of the canonical title from
            :data:`_BINDING_TITLE`.

    Returns:
        :class:`ImageChartResult`.

    Raises:
        ValueError: if the binding isn't recognised as a chart binding.
    """
    if binding_name not in _BINDING_KIND:
        raise ValueError(
            f"binding {binding_name!r} is not a chart binding. Known: {sorted(_BINDING_KIND)}"
        )
    kind = _BINDING_KIND[binding_name]
    title = title_override or _BINDING_TITLE.get(binding_name, binding_name)
    subtitle_parts = [p for p in (period, scope_label) if p]
    subtitle = " - ".join(subtitle_parts)
    if director_name:
        subtitle = f"{subtitle} - {director_name}" if subtitle else director_name

    output_path = output_path.expanduser().resolve()

    if kind == "waterfall":
        dims = _render_waterfall(
            table_data,
            title=title,
            subtitle=subtitle,
            width_in=width_in,
            height_in=height_in,
            output_path=output_path,
        )
        kind_out = "waterfall"
    elif kind == "mekko":
        dims = _render_mekko(
            table_data,
            title=title,
            subtitle=subtitle,
            width_in=width_in,
            height_in=height_in,
            output_path=output_path,
        )
        kind_out = "mekko"
    elif kind == "line":
        dims = _render_line(
            table_data,
            title=title,
            subtitle=subtitle,
            width_in=width_in,
            height_in=height_in,
            output_path=output_path,
        )
        kind_out = "line"
    elif kind == "bar_horizontal":
        dims = _render_bar_horizontal(
            table_data,
            title=title,
            subtitle=subtitle,
            width_in=width_in,
            height_in=height_in,
            output_path=output_path,
        )
        kind_out = "bar"
    elif kind == "bar_grouped_winloss":
        dims = _render_bar_grouped_winloss(
            table_data,
            title=title,
            subtitle=subtitle,
            width_in=width_in,
            height_in=height_in,
            output_path=output_path,
        )
        kind_out = "grouped_bar"
    else:  # bar_stage / bar_aging / bar_forecast / bar_territory / bar_velocity / bar_concentration / bar_stale
        dims = _render_bar(
            table_data,
            title=title,
            subtitle=subtitle,
            kind=kind,
            width_in=width_in,
            height_in=height_in,
            output_path=output_path,
        )
        kind_out = "bar"

    return ImageChartResult(
        image_path=output_path,
        dimensions_px=dims,
        binding_kind=kind_out,
    )


# ============================================================================
#                       DECK ENHANCEMENT (PPTX EMBED)
# ============================================================================


def _load_bindings_from_ppttc(ppttc_path: Path) -> dict[str, list[Any]]:
    parsed = json.loads(ppttc_path.read_text(encoding="utf-8"))
    if not isinstance(parsed, list):
        raise ValueError(f".ppttc must be a JSON array: {ppttc_path}")
    out: dict[str, list[Any]] = {}
    for entry in parsed:
        if not isinstance(entry, dict):
            continue
        data = entry.get("data")
        if not isinstance(data, list):
            continue
        for b in data:
            if isinstance(b, dict):
                name = b.get("name")
                table = b.get("table")
                if isinstance(name, str) and isinstance(table, list):
                    out[name] = table
    return out


def _scalar_context(bindings: dict[str, list[Any]]) -> tuple[str, str, str]:
    """Pull (director, period, scope) scalars from the .ppttc bindings."""

    def _scalar(name: str) -> str:
        t = bindings.get(name)
        if not (isinstance(t, list) and t and isinstance(t[0], list) and t[0]):
            return ""
        cell = t[0][0]
        if isinstance(cell, dict) and isinstance(cell.get("string"), str):
            return cell["string"]
        return ""

    return (
        _scalar("S01_DirectorName"),
        _scalar("S01_Period"),
        _scalar("S01_ScopeLabel"),
    )


def _strip_chart_shapes(slide: Any) -> None:
    """Remove existing native chart graphicFrames and tcfield placeholders.

    This is the prep step before adding our PNG. We don't touch slide titles
    (Title placeholder shapes), tables, or text boxes.
    """
    spTree = slide.shapes._spTree  # type: ignore[attr-defined]
    chart_uri = "http://schemas.openxmlformats.org/drawingml/2006/chart"
    ole_uri = "http://schemas.openxmlformats.org/presentationml/2006/ole"
    instruction_phrases = (
        "[think-cell TABLE WITH FORMATTING",
        "[think-cell TABLE",
        "[think-cell text",
        "Insert chart title here",
        "Lorem ipsum",
        "tc_columnhead",
        "Item comparison",
        "Structure, composition",
        "Contribution to change",
    )
    boilerplate_prefixes = ("tcfield",)

    to_remove: list[Any] = []
    for sp in list(spTree.iterchildren()):
        tag = etree.QName(sp).localname
        if tag == "graphicFrame":
            graphic = sp.find(f"{qn('a:graphic')}/{qn('a:graphicData')}")
            uri = graphic.get("uri", "") if graphic is not None else ""
            if uri == chart_uri or uri == ole_uri:
                to_remove.append(sp)
        elif tag == "sp":
            name = ""
            nvSpPr = sp.find(qn("p:nvSpPr"))
            if nvSpPr is not None:
                cNvPr = nvSpPr.find(qn("p:cNvPr"))
                if cNvPr is not None:
                    name = cNvPr.get("name", "")
            text = "".join((t.text or "") for t in sp.iter(qn("a:t")))
            remove = False
            if any(name.startswith(p) for p in boilerplate_prefixes):
                remove = True
            elif text and any(p in text for p in instruction_phrases):
                remove = True
            if remove:
                to_remove.append(sp)
    for sp in to_remove:
        spTree.remove(sp)


def enhance_deck_with_images(
    deck_path: Path,
    ppttc_path: Path,
    output_path: Path | None = None,
    *,
    keep_pngs: bool = False,
    width_in: float = 10.0,
    height_in: float = 5.5,
) -> EnhanceImagesResult:
    """Walk a rendered LAND deck; render each chart binding as PNG; embed.

    Args:
        deck_path: Source .pptx (rendered by ppttc.exe and optionally enhanced
            by ``native_fallback.enhance_deck``). NEVER mutated.
        ppttc_path: The .ppttc that produced ``deck_path``.
        output_path: Where to write the enhanced deck. Defaults to
            ``<deck stem>-image-charts-<ts>.pptx`` next to ``deck_path``.
        keep_pngs: When True, the temporary PNG files are not deleted (useful
            for debugging / visual QA). Default ``False``.
        width_in, height_in: Logical chart figure size; rendered at 200 DPI.

    Returns:
        :class:`EnhanceImagesResult`.

    Raises:
        FileNotFoundError: if either path doesn't exist.
        ValueError: if the .ppttc is malformed.
    """
    deck_path = deck_path.expanduser().resolve()
    ppttc_path = ppttc_path.expanduser().resolve()
    if not deck_path.exists():
        raise FileNotFoundError(f"deck not found: {deck_path}")
    if not ppttc_path.exists():
        raise FileNotFoundError(f".ppttc not found: {ppttc_path}")

    if output_path is None:
        ts = time.strftime("%Y%m%d-%H%M%S")
        output_path = deck_path.with_name(f"{deck_path.stem}-image-charts-{ts}.pptx")
    else:
        output_path = output_path.expanduser().resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)

    bindings = _load_bindings_from_ppttc(ppttc_path)
    director, period, scope = _scalar_context(bindings)

    prs = Presentation(str(deck_path))
    rendered: list[str] = []
    skipped: list[tuple[str, str]] = []
    png_paths: dict[str, Path] = {}

    # PNGs go to a dedicated tempdir (only kept when keep_pngs=True).
    tmpdir = Path(tempfile.mkdtemp(prefix="tcrender-imgcharts-"))

    for binding_name, slide_idx in _BINDING_TO_SLIDE.items():
        if binding_name not in bindings:
            skipped.append((binding_name, "binding not in .ppttc"))
            continue
        table = bindings[binding_name]
        if not isinstance(table, list) or len(table) < 2:
            skipped.append((binding_name, "binding table too short"))
            continue
        if slide_idx > len(prs.slides):
            skipped.append((binding_name, f"slide {slide_idx} out of range"))
            continue
        slide = prs.slides[slide_idx - 1]

        png_path = tmpdir / f"{binding_name}.png"
        try:
            render_chart_image(
                binding_name=binding_name,
                table_data=table,
                output_path=png_path,
                width_in=width_in,
                height_in=height_in,
                director_name=director,
                period=period,
                scope_label=scope,
            )
        except Exception as exc:  # noqa: BLE001 - one bad chart != broken run
            skipped.append((binding_name, f"render error: {type(exc).__name__}: {exc}"))
            continue

        # Strip prior chart graphicFrames + tcfield placeholders, then embed PNG.
        try:
            _strip_chart_shapes(slide)
            slide.shapes.add_picture(
                str(png_path),
                left=Emu(_CANVAS_LEFT_EMU),
                top=Emu(_CANVAS_TOP_EMU),
                width=Emu(_CANVAS_WIDTH_EMU),
                height=Emu(_CANVAS_HEIGHT_EMU),
            )
            rendered.append(binding_name)
            png_paths[binding_name] = png_path
        except Exception as exc:  # noqa: BLE001
            skipped.append((binding_name, f"embed error: {type(exc).__name__}: {exc}"))
            continue

    prs.save(str(output_path))

    if not keep_pngs:
        # Clean up rendered PNGs; keep tempdir if nothing rendered (rare).
        for p in png_paths.values():
            try:
                p.unlink(missing_ok=True)
            except OSError:
                pass
        try:
            tmpdir.rmdir()
        except OSError:
            pass

    return EnhanceImagesResult(
        enhanced_path=output_path,
        bindings_rendered=rendered,
        skipped=skipped,
        png_paths=png_paths if keep_pngs else {},
    )


__all__ = [
    "SIMCORP_BRAND",
    "SIMCORP_FONT",
    "ImageChartResult",
    "EnhanceImagesResult",
    "render_chart_image",
    "enhance_deck_with_images",
]
