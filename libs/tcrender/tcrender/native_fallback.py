"""Native-PowerPoint fallback layer for the LAND deck factory.

Why this exists
~~~~~~~~~~~~~~~

The LAND deck `.ppttc` ships 14 multi-row tabular bindings (S04, S05, S06,
S07, S08, S09, S11, S12, S13, S15, S16, S17, S18, S19, S21_table, S22, S24,
S25, S26). When the donor template lacks a think-cell chart anchor for one
of those binding names, ``ppttc.exe`` silently leaves the slide showing the
template author's instruction text (e.g. "[think-cell TABLE WITH FORMATTING
- datalinked]"). The rendered deck looks empty for that director.

This module runs as a SECOND PASS over the rendered deck: it walks each
chart/table slide, removes the placeholder instruction shapes, and adds
native PowerPoint chart/table shapes populated with data pulled from the
director's ``.ppttc``. The output deck shows REAL data on every slide.

Architecturally
~~~~~~~~~~~~~~~

* ``tcrender.render`` stays clean -- this fallback is opt-in.
* The fallback NEVER mutates the input deck. Output goes to a new path.
* Numbers + colors + sort orders + axis treatment are encoded once in
  ``BRAND_PALETTE`` + small format helpers; every renderer reuses them so
  the deck has a consistent look.
* For chart binding shapes (S04..S25 except tables), we add a native
  python-pptx chart. For tabular bindings (S07/S08/S09/S11/S12/S21_t/S24/
  S26), we add a native PowerPoint table. For S16 (Mekko), we draw raw
  rectangles + text because python-pptx cannot give us per-column variable
  widths.

Public API
~~~~~~~~~~

* :data:`BRAND_PALETTE` -- swappable palette dict.
* :class:`EnhanceResult` -- frozen result dataclass.
* :func:`enhance_deck` -- run the second pass; return EnhanceResult.

Pure stdlib + lxml + python-pptx (already a venv dep). ASCII-only.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from lxml import etree
from pptx import Presentation
from pptx.chart.data import CategoryChartData
from pptx.dml.color import RGBColor
from pptx.enum.chart import XL_CHART_TYPE, XL_LABEL_POSITION, XL_LEGEND_POSITION
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import PP_ALIGN
from pptx.oxml.ns import qn
from pptx.util import Emu, Pt

# -------------------------------------------------------------------- palette


BRAND_PALETTE: dict[str, str] = {
    # Real SimCorp 2026 brand palette extracted from theme1.xml of
    # assets/LAND_thinkcell_seed.pptx (theme name: "1_Simcorp"). Verified
    # against the .pptx's <a:clrScheme> on 2026-05-03.
    "primary": "#083EA7",  # SimCorp navy (accent1) -- primary fill on bars/headers
    "accent": "#1A1D31",  # near-black (accent2) -- title color, dark text
    "success": "#3F8F5F",  # green (Win) -- gains, won, low risk (kept consulting standard)
    "warning": "#EF3E4A",  # SimCorp coral (accent4) -- losses, lost, high risk
    "highlight": "#FB9B2A",  # SimCorp orange (accent5) -- callouts, medium risk
    "tertiary": "#F0CF61",  # SimCorp gold (accent6) -- tertiary highlights
    "purple": "#4B17B6",  # SimCorp purple (accent3) -- alt accent
    "hyperlink": "#0A7BD7",  # SimCorp link blue (hlink) -- interactive
    "neutral_dark": "#1A1D31",  # body text
    "neutral_mid": "#9CA3AF",  # axis lines
    "neutral_light": "#E3E3E3",  # alternating row stripe (lt2 from theme)
}

# Stage palette for the Mekko -- gradient from SimCorp navy to lighter shades,
# then warning + highlight at the late-stage end so high-stage cells pop.
_STAGE_PALETTE: tuple[str, ...] = (
    "#083EA7",  # SimCorp navy primary
    "#3060B5",
    "#5A82C4",
    "#85A4D4",
    "#B0C5E2",
    "#D4DEEC",
    "#D4A93A",  # highlight tail
    "#C45F4F",  # warning tail
)

DEFAULT_FONT = "Calibri"

# ----------------------------------------------------------------- result API


@dataclass(frozen=True)
class EnhanceResult:
    """Outcome of :func:`enhance_deck`.

    Attributes:
        enhanced_path: Path to the enhanced .pptx (newly written).
        bindings_inserted: Names of bindings whose data was rendered as
            native chart/table. Order = order of insertion.
        skipped: Pairs of (binding_name, reason) for bindings the renderer
            chose not to insert (no slide match, scalar bindings the donor
            already handled, unsupported shape).
    """

    enhanced_path: Path
    bindings_inserted: list[str] = field(default_factory=list)
    skipped: list[tuple[str, str]] = field(default_factory=list)


# --------------------------------------------------------------- binding map


# Map binding-name -> (slide_index_1based, render_kind). The slide index is
# stable per LAND template. Render kind drives the renderer dispatch.
_BINDING_TO_SLIDE: dict[str, tuple[int, str]] = {
    "S04_PipeMovement": (4, "waterfall"),
    "S05_PipelineByStage": (5, "stage_bar"),
    "S06_PipelineAging": (6, "aging_bar"),
    "S07_TopDealsLand": (7, "table"),
    "S08_TopDealsExpand": (8, "table"),
    "S09_PendingCommercialApproval": (9, "table"),
    "S11_RenewalPipeline": (11, "table_risk"),
    "S12_GRRProxyTable": (12, "table_metric"),
    "S13_ForecastCategory": (13, "forecast_bar"),
    "S15_ByOwner": (15, "owner_bar"),
    "S16_StageByIndustry": (16, "mekko"),
    "S17_TerritoryPerformance": (17, "territory_bar"),
    "S18_WinsLossesQTD": (18, "wl_bar"),
    "S19_Velocity": (19, "velocity_bar"),
    "S21_ConcentrationRiskChart": (21, "concentration_bar"),
    "S22_StaleActivity": (22, "stale_bar"),
    "S24_AccountExpansion": (24, "table"),
    "S25_PipelineCreationVelocity": (25, "line"),
    "S26_ActionItems": (26, "table_priority"),
}

# Binding name -> human-readable slide title (used as native-chart title).
_BINDING_TITLES: dict[str, str] = {
    "S04_PipeMovement": "Pipe movement (ARR mEUR)",
    "S05_PipelineByStage": "Pipeline by stage",
    "S06_PipelineAging": "Pipeline aging",
    "S07_TopDealsLand": "Top deals - Land",
    "S08_TopDealsExpand": "Top deals - Expand",
    "S09_PendingCommercialApproval": "Pending Commercial Approval",
    "S11_RenewalPipeline": "Renewal pipeline (at-risk)",
    "S12_GRRProxyTable": "GRR proxy",
    "S13_ForecastCategory": "Forecast category",
    "S15_ByOwner": "Open ARR by owner",
    "S16_StageByIndustry": "Stage by industry (mekko)",
    "S17_TerritoryPerformance": "Territory performance",
    "S18_WinsLossesQTD": "Wins / losses QTD",
    "S19_Velocity": "Velocity (median age by stage)",
    "S21_ConcentrationRiskChart": "Concentration risk",
    "S22_StaleActivity": "Stale activity by stage",
    "S24_AccountExpansion": "Account expansion (top motions)",
    "S25_PipelineCreationVelocity": "Pipeline creation velocity",
    "S26_ActionItems": "Action items",
}

# Default chart canvas inside the LAND template (left chart area, no comment
# panel overlap). Coordinates verified against the Jesper deck XML on
# 2026-05-02; the comment column starts at x=8455234.
_CANVAS_LEFT = Emu(457_200)
_CANVAS_TOP = Emu(1_557_338)
_CANVAS_WIDTH = Emu(7_750_000)
_CANVAS_HEIGHT = Emu(4_700_000)

# Shapes whose text contains any of these phrases are template instruction
# placeholders that we should remove BEFORE drawing the native chart/table.
_INSTRUCTION_PHRASES: tuple[str, ...] = (
    "[think-cell TABLE WITH FORMATTING",
    "[think-cell TABLE",
    "[think-cell text",
    "This slide contains a",
    "Insert chart title here",
    "Insert your desired text",
    "tc_columnhead",
    "Lorem ipsum",
    "Keywords: column",
    "Item comparison",
    "Structure, composition",
    "Contribution to change",
)

# Boilerplate shape names emitted by the donor that we strip wholesale on
# chart slides so the native chart isn't crowded by decorative scaffolding.
_BOILERPLATE_SHAPE_NAMES: frozenset[str] = frozenset(
    {
        "Rectangle 18",
        "Rectangle 5",
        "Rectangle 124",
        "Rechteck 137",
        "Text Placeholder 15",
    }
)

# Boilerplate name PREFIXES (e.g. "Text Placeholder 2" appears with multiple
# instances numbered the same way; the donor uses these for axis labels and
# legend entries that are no longer accurate once we replace the chart).
_BOILERPLATE_NAME_PREFIXES: tuple[str, ...] = (
    "Text Placeholder 2",
    "tc_columnhead",
    "Arrow: Right",
    "tcfield",
)


# ------------------------------------------------------------- main entrypoint


def enhance_deck(
    deck_path: Path,
    ppttc_path: Path,
    output_path: Path | None = None,
    *,
    palette: dict[str, str] | None = None,
    font: str = DEFAULT_FONT,
) -> EnhanceResult:
    """Walk a rendered LAND deck and replace placeholder text with native chart/table shapes.

    Args:
        deck_path: Source .pptx (rendered by ppttc.exe). NEVER mutated.
        ppttc_path: The .ppttc that produced ``deck_path``. Used for the
            director-specific data tables.
        output_path: Where to write the enhanced .pptx. When ``None``,
            defaults to ``<deck_path stem>-enhanced-<ts>.pptx`` alongside
            the input.
        palette: Optional palette override; keys mirror :data:`BRAND_PALETTE`.
        font: Font name applied to all rendered text (default ``Calibri``).

    Returns:
        :class:`EnhanceResult`.

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

    pal = dict(BRAND_PALETTE)
    if palette:
        pal.update(palette)

    if output_path is None:
        ts = time.strftime("%Y%m%d-%H%M%S")
        output_path = deck_path.with_name(f"{deck_path.stem}-enhanced-{ts}.pptx")
    else:
        output_path = output_path.expanduser().resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)

    # Load .ppttc -> {binding_name: table}
    bindings = _load_bindings(ppttc_path)
    director, period, scope = _scalar_context(bindings)
    subtitle = f"{period} LAND review - {scope}".strip(" -")

    # Open with python-pptx (loads from deck_path; saves to output_path so the
    # input is preserved).
    prs = Presentation(str(deck_path))

    inserted: list[str] = []
    skipped: list[tuple[str, str]] = []

    for binding_name, (slide_idx, kind) in _BINDING_TO_SLIDE.items():
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

        try:
            _strip_instruction_shapes(slide)
            _render_one(
                slide=slide,
                kind=kind,
                table=table,
                title=_BINDING_TITLES.get(binding_name, binding_name),
                subtitle=subtitle,
                palette=pal,
                font=font,
            )
            inserted.append(binding_name)
        except Exception as exc:  # noqa: BLE001 - keep one bad slide from breaking the run
            skipped.append((binding_name, f"render error: {type(exc).__name__}: {exc}"))

    prs.save(str(output_path))
    return EnhanceResult(
        enhanced_path=output_path,
        bindings_inserted=inserted,
        skipped=skipped,
    )


# ------------------------------------------------------------- ppttc loading


def _load_bindings(ppttc_path: Path) -> dict[str, list[Any]]:
    """Return ``{binding_name: table}`` for every binding in the .ppttc."""
    parsed = json.loads(ppttc_path.read_text(encoding="utf-8"))
    if not isinstance(parsed, list) or not parsed:
        raise ValueError(f".ppttc must be a non-empty JSON array: {ppttc_path}")
    out: dict[str, list[Any]] = {}
    for entry in parsed:
        if not isinstance(entry, dict):
            continue
        data = entry.get("data")
        if not isinstance(data, list):
            continue
        for b in data:
            if not isinstance(b, dict):
                continue
            name = b.get("name")
            table = b.get("table")
            if isinstance(name, str) and isinstance(table, list):
                out[name] = table
    return out


def _scalar_context(bindings: dict[str, list[Any]]) -> tuple[str, str, str]:
    """Pull director / period / scope scalars; empty strings if missing."""

    def _scalar(name: str) -> str:
        t = bindings.get(name)
        if not (isinstance(t, list) and t and isinstance(t[0], list) and t[0]):
            return ""
        cell = t[0][0]
        if isinstance(cell, dict):
            v = cell.get("string")
            if isinstance(v, str):
                return v
        return ""

    return (
        _scalar("S01_DirectorName"),
        _scalar("S01_Period"),
        _scalar("S01_ScopeLabel"),
    )


# -------------------------------------------------------------- shape helpers


def _strip_instruction_shapes(slide: Any) -> None:
    """Remove instruction-text, donor-chart, and tcfield placeholder shapes.

    Removes:
        * Shapes whose text matches any of ``_INSTRUCTION_PHRASES``.
        * Shapes whose name is in ``_BOILERPLATE_SHAPE_NAMES``.
        * ``tcfield_S*`` shapes (think-cell binding placeholders that
          ppttc.exe failed to populate).
        * Native chart graphicFrames inherited from the donor template
          (the empty chart shells the template ships).
        * The think-cell OLE data graphicFrame ("think-cell data - do not
          delete") -- without the native chart the OLE shell is also stale.

    Header titles and the slide title are NOT touched -- they live in
    ``Title`` placeholder shapes that the donor template controls.
    """
    spTree = slide.shapes._spTree  # type: ignore[attr-defined]
    to_remove: list[Any] = []
    chart_uri = "http://schemas.openxmlformats.org/drawingml/2006/chart"
    ole_uri = "http://schemas.openxmlformats.org/presentationml/2006/ole"

    for sp in list(spTree.iterchildren()):
        tag = etree.QName(sp).localname
        if tag == "sp":
            # Read shape name
            name = ""
            nvSpPr = sp.find(qn("p:nvSpPr"))
            if nvSpPr is not None:
                cNvPr = nvSpPr.find(qn("p:cNvPr"))
                if cNvPr is not None:
                    name = cNvPr.get("name", "")
            # Read shape text
            text = "".join((t.text or "") for t in sp.iter(qn("a:t")))
            remove = False
            if name in _BOILERPLATE_SHAPE_NAMES:
                remove = True
            elif any(name.startswith(p) for p in _BOILERPLATE_NAME_PREFIXES):
                remove = True
            elif text and any(p in text for p in _INSTRUCTION_PHRASES):
                remove = True
            if remove:
                to_remove.append(sp)
        elif tag == "graphicFrame":
            # Strip donor charts + think-cell OLE shells. The native chart we
            # add downstream replaces them; leaving them in stacks two empty
            # charts plus stale OLE data on the slide.
            graphic = sp.find(f"{qn('a:graphic')}/{qn('a:graphicData')}")
            uri = graphic.get("uri", "") if graphic is not None else ""
            if uri == chart_uri or uri == ole_uri:
                to_remove.append(sp)

    for sp in to_remove:
        spTree.remove(sp)


def _hex_to_rgb(hex_color: str) -> RGBColor:
    h = hex_color.lstrip("#")
    return RGBColor(int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


def _set_run_font(
    run: Any, *, font: str, size_pt: float, bold: bool = False, hex_color: str | None = None
) -> None:
    run.font.name = font
    run.font.size = Pt(size_pt)
    run.font.bold = bold
    if hex_color is not None:
        run.font.color.rgb = _hex_to_rgb(hex_color)


def _add_subtitle(
    slide: Any,
    *,
    subtitle: str,
    palette: dict[str, str],
    font: str,
    left: Any = None,
    top: Any = None,
    width: Any = None,
) -> None:
    """Add a small subtitle textbox above the chart/table area."""
    if not subtitle:
        return
    tx = slide.shapes.add_textbox(
        left or _CANVAS_LEFT,
        top or Emu(1_350_000),
        width or _CANVAS_WIDTH,
        Emu(200_000),
    )
    tf = tx.text_frame
    tf.word_wrap = True
    p = tf.paragraphs[0]
    p.alignment = PP_ALIGN.LEFT
    run = p.add_run()
    run.text = subtitle
    _set_run_font(run, font=font, size_pt=10.0, hex_color=palette["accent"])


# ---------------------------------------------------------- formatting helpers


def _fmt_eur(value: float) -> str:
    """Format ``value`` (raw EUR) with thousand separators or M abbreviation."""
    if value is None:
        return ""
    av = abs(value)
    if av >= 1_000_000:
        return f"EUR {value / 1_000_000:.1f}M"
    if av >= 1_000:
        # EUR 5,123,456 (no decimals, comma thousands)
        return f"EUR {int(round(value)):,}"
    return f"EUR {value:.0f}"


def _fmt_meur(value: float) -> str:
    """Format a value already in mEUR (small floats)."""
    if value is None:
        return ""
    return f"{value:.1f} M"


def _fmt_pct(value: float) -> str:
    """Format a fraction (0..1) or pre-multiplied (0..100) percentage value."""
    if value is None:
        return ""
    if -1.5 <= value <= 1.5:
        return f"{value * 100:.1f}%"
    return f"{value:.1f}%"


def _fmt_int(value: float | int) -> str:
    if value is None:
        return ""
    return f"{int(round(float(value))):,}"


def _truncate(s: str, n: int = 18) -> str:
    if not isinstance(s, str):
        return ""
    return s if len(s) <= n else s[: n - 1] + "…"


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


# -------------------------------------------------------------- renderer hub


def _render_one(
    slide: Any,
    *,
    kind: str,
    table: list[Any],
    title: str,
    subtitle: str,
    palette: dict[str, str],
    font: str,
) -> None:
    """Dispatch to the per-kind renderer."""
    _add_subtitle(slide, subtitle=subtitle, palette=palette, font=font)
    if kind == "waterfall":
        _render_waterfall(slide, table=table, title=title, palette=palette, font=font)
    elif kind in {
        "stage_bar",
        "aging_bar",
        "owner_bar",
        "territory_bar",
        "stale_bar",
        "concentration_bar",
        "velocity_bar",
        "forecast_bar",
    }:
        _render_simple_bar(slide, table=table, title=title, palette=palette, font=font, kind=kind)
    elif kind == "wl_bar":
        _render_winloss_bar(slide, table=table, title=title, palette=palette, font=font)
    elif kind == "mekko":
        _render_mekko(slide, table=table, title=title, palette=palette, font=font)
    elif kind == "line":
        _render_line(slide, table=table, title=title, palette=palette, font=font)
    elif kind == "table":
        _render_table(slide, table=table, title=title, palette=palette, font=font)
    elif kind == "table_metric":
        _render_table_metric(slide, table=table, title=title, palette=palette, font=font)
    elif kind == "table_risk":
        _render_table_risk(slide, table=table, title=title, palette=palette, font=font)
    elif kind == "table_priority":
        _render_table_priority(slide, table=table, title=title, palette=palette, font=font)
    else:
        raise ValueError(f"unknown render kind: {kind}")


# ============================================================================
#                              CHART RENDERERS
# ============================================================================


# ---- shared chart styling ----


def _style_chart(
    chart: Any,
    *,
    palette: dict[str, str],
    font: str,
    title: str | None = None,
    hide_legend: bool = True,
) -> None:
    """Apply consistent font, title, and axis treatment to a python-pptx chart."""
    # Title
    if title is not None:
        chart.has_title = True
        ttl = chart.chart_title
        ttl.text_frame.text = title
        for para in ttl.text_frame.paragraphs:
            for run in para.runs:
                _set_run_font(
                    run, font=font, size_pt=14.0, bold=True, hex_color=palette["neutral_dark"]
                )
    # Legend
    if hide_legend:
        chart.has_legend = False
    else:
        chart.has_legend = True
        chart.legend.position = XL_LEGEND_POSITION.BOTTOM
        chart.legend.include_in_layout = False
    # Plot area font
    try:
        for axis in (chart.category_axis, chart.value_axis):
            for para in axis.tick_labels.font._element.getparent().iter():  # noqa: SLF001
                pass
            axis.tick_labels.font.name = font
            axis.tick_labels.font.size = Pt(9.0)
            axis.tick_labels.font.color.rgb = _hex_to_rgb(palette["neutral_dark"])
    except (AttributeError, ValueError):  # some chart types don't have both axes
        pass


def _color_series_solid(series: Any, hex_color: str) -> None:
    """Force every datapoint in ``series`` to a solid fill of ``hex_color``."""
    fill = series.format.fill
    fill.solid()
    fill.fore_color.rgb = _hex_to_rgb(hex_color)


def _color_points(series: Any, hex_colors: list[str]) -> None:
    """Color each datapoint of ``series`` individually (one color per index)."""
    for i, hex_color in enumerate(hex_colors):
        try:
            pt = series.points[i]
        except (IndexError, AttributeError):
            continue
        fill = pt.format.fill
        fill.solid()
        fill.fore_color.rgb = _hex_to_rgb(hex_color)


def _add_value_labels(plot: Any, *, palette: dict[str, str], font: str, suffix: str = "") -> None:
    """Show value labels on every datapoint."""
    plot.has_data_labels = True
    dl = plot.data_labels
    dl.show_value = True
    try:
        dl.position = XL_LABEL_POSITION.OUTSIDE_END
    except (ValueError, AttributeError):
        pass
    dl.font.name = font
    dl.font.size = Pt(9.0)
    dl.font.color.rgb = _hex_to_rgb(palette["neutral_dark"])
    if suffix:
        dl.number_format = f'0.0"{suffix}"'
        dl.number_format_is_linked = False


# ---- S04 waterfall -----------------------------------------------------------


def _render_waterfall(
    slide: Any, *, table: list[Any], title: str, palette: dict[str, str], font: str
) -> None:
    """Bar-chart approximation of a waterfall.

    Renders 5 anchored bars (Opening / New+Advanced / Won / Lost / Closing).
    Gains use ``palette['success']``; losses use ``palette['warning']``; the
    opening + closing anchors use ``palette['primary']``. Value labels (mEUR)
    sit above each bar.
    """
    headers, values = _split_chart_table(table)
    if not headers:
        return
    cd = CategoryChartData()
    cd.categories = headers
    cd.add_series("ARR (mEUR)", values)

    chart = slide.shapes.add_chart(
        XL_CHART_TYPE.COLUMN_CLUSTERED,
        _CANVAS_LEFT,
        _CANVAS_TOP,
        _CANVAS_WIDTH,
        _CANVAS_HEIGHT,
        cd,
    ).chart
    _style_chart(chart, palette=palette, font=font, title=title)
    series = chart.plots[0].series[0]
    # Color bars: anchors primary, gains success, losses warning.
    colors: list[str] = []
    for i, val in enumerate(values):
        if i in (0, len(values) - 1):
            colors.append(palette["primary"])
        elif val is not None and val < 0:
            colors.append(palette["warning"])
        else:
            colors.append(palette["success"])
    _color_points(series, colors)
    _add_value_labels(chart.plots[0], palette=palette, font=font, suffix="M")


# ---- shared simple-bar (S05/S06/S13/S15/S17/S19/S21/S22) ---------------------


def _render_simple_bar(
    slide: Any,
    *,
    table: list[Any],
    title: str,
    palette: dict[str, str],
    font: str,
    kind: str,
) -> None:
    """Single-series clustered column with consistent treatment.

    * `stage_bar`: x-axis already in stage order (1..8).
    * `aging_bar`: x-axis already in age-bucket order.
    * `owner_bar`: top-10 by descending ARR; truncate names >18 chars.
    * `territory_bar`: top countries already sorted descending.
    * `velocity_bar`: median age in days; bars >365d use warning color.
    * `concentration_bar`: top-1/3/5/10 share %; bars > 80 use warning color.
    * `stale_bar`: same look as stage_bar.
    * `forecast_bar`: stage-ordered; commit/best/pipeline color-coded.
    """
    headers, values = _split_chart_table(table)
    if not headers:
        return

    if kind == "owner_bar":
        # Sort descending by value, take top 10, truncate names.
        pairs = sorted(zip(headers, values, strict=False), key=lambda p: -(p[1] or 0))[:10]
        headers = [_truncate(h, 18) for h, _ in pairs]
        values = [v for _, v in pairs]

    cd = CategoryChartData()
    cd.categories = headers
    cd.add_series(title, values)

    chart = slide.shapes.add_chart(
        XL_CHART_TYPE.COLUMN_CLUSTERED,
        _CANVAS_LEFT,
        _CANVAS_TOP,
        _CANVAS_WIDTH,
        _CANVAS_HEIGHT,
        cd,
    ).chart
    _style_chart(chart, palette=palette, font=font, title=title)
    series = chart.plots[0].series[0]
    _color_series_solid(series, palette["primary"])

    # Per-bar warning highlights.
    if kind == "velocity_bar":
        colors = [
            palette["warning"] if (v is not None and v > 365) else palette["primary"]
            for v in values
        ]
        _color_points(series, colors)
    elif kind == "concentration_bar":
        colors = [
            palette["warning"] if (v is not None and v > 80) else palette["primary"] for v in values
        ]
        _color_points(series, colors)
    elif kind == "forecast_bar":
        cat_palette = {
            "Pipeline": palette["accent"],
            "Best Case": palette["highlight"],
            "Commit": palette["primary"],
            "Closed": palette["success"],
            "Omitted": palette["neutral_mid"],
            "(unset)": palette["neutral_mid"],
        }
        colors = [cat_palette.get(h, palette["primary"]) for h in headers]
        _color_points(series, colors)

    suffix = (
        " M"
        if kind
        in {"stage_bar", "aging_bar", "owner_bar", "territory_bar", "stale_bar", "forecast_bar"}
        else ""
    )
    if kind == "velocity_bar":
        suffix = " d"
    if kind == "concentration_bar":
        suffix = "%"
    _add_value_labels(chart.plots[0], palette=palette, font=font, suffix=suffix)

    # Add axis title for the unit
    try:
        if kind in {
            "stage_bar",
            "aging_bar",
            "owner_bar",
            "territory_bar",
            "stale_bar",
            "forecast_bar",
        }:
            chart.value_axis.has_title = True
            chart.value_axis.axis_title.text_frame.text = "ARR (EUR M)"
        elif kind == "velocity_bar":
            chart.value_axis.has_title = True
            chart.value_axis.axis_title.text_frame.text = "Median age (days)"
        elif kind == "concentration_bar":
            chart.value_axis.has_title = True
            chart.value_axis.axis_title.text_frame.text = "Share (%)"
        for run in chart.value_axis.axis_title.text_frame.paragraphs[0].runs:
            _set_run_font(run, font=font, size_pt=10.0, hex_color=palette["accent"])
    except (AttributeError, ValueError):
        pass


# ---- S18 wins/losses ---------------------------------------------------------


def _render_winloss_bar(
    slide: Any, *, table: list[Any], title: str, palette: dict[str, str], font: str
) -> None:
    """Won (green) vs Lost (coral) grouped bar; row-grouped if both ARR and ACV present."""
    if len(table) < 2 or not isinstance(table[0], list):
        return
    cats: list[str] = []
    for cell in table[0][1:]:
        s = _cell_str(cell)
        if s:
            cats.append(s)
    if not cats:
        return
    cd = CategoryChartData()
    cd.categories = cats
    for row in table[1:]:
        if not isinstance(row, list) or not row:
            continue
        label = _cell_str(row[0])
        nums: list[float | None] = [_cell_num(c) for c in row[1:]]
        if any(n is not None for n in nums):
            cd.add_series(label or "Series", nums)

    chart = slide.shapes.add_chart(
        XL_CHART_TYPE.COLUMN_CLUSTERED,
        _CANVAS_LEFT,
        _CANVAS_TOP,
        _CANVAS_WIDTH,
        _CANVAS_HEIGHT,
        cd,
    ).chart
    _style_chart(chart, palette=palette, font=font, title=title, hide_legend=False)
    # Color each series based on category (Won=success, Lost=warning).
    cat_colors = [
        palette["success"] if c.lower().startswith("won") else palette["warning"] for c in cats
    ]
    for series in chart.plots[0].series:
        _color_points(series, cat_colors)
    _add_value_labels(chart.plots[0], palette=palette, font=font, suffix=" M")


# ---- S25 line ---------------------------------------------------------------


def _render_line(
    slide: Any, *, table: list[Any], title: str, palette: dict[str, str], font: str
) -> None:
    """Time-series line with markers; weeks on x, mEUR on y."""
    headers, values = _split_chart_table(table)
    if not headers:
        return
    cd = CategoryChartData()
    cd.categories = headers
    cd.add_series("New ARR (mEUR)", values)
    chart = slide.shapes.add_chart(
        XL_CHART_TYPE.LINE_MARKERS,
        _CANVAS_LEFT,
        _CANVAS_TOP,
        _CANVAS_WIDTH,
        _CANVAS_HEIGHT,
        cd,
    ).chart
    _style_chart(chart, palette=palette, font=font, title=title)
    series = chart.plots[0].series[0]
    # Line color
    line = series.format.line
    line.color.rgb = _hex_to_rgb(palette["primary"])
    line.width = Pt(2.0)
    _add_value_labels(chart.plots[0], palette=palette, font=font, suffix=" M")
    try:
        chart.value_axis.has_title = True
        chart.value_axis.axis_title.text_frame.text = "ARR (EUR M)"
        for run in chart.value_axis.axis_title.text_frame.paragraphs[0].runs:
            _set_run_font(run, font=font, size_pt=10.0, hex_color=palette["accent"])
    except (AttributeError, ValueError):
        pass


# ---- S16 Mekko (raw rectangles) ---------------------------------------------


def _render_mekko(
    slide: Any, *, table: list[Any], title: str, palette: dict[str, str], font: str
) -> None:
    """True Mekko: column WIDTH proportional to industry total; HEIGHT 100%-stacked.

    python-pptx native stacked bars give equal-width columns, which lies
    about column-total magnitude. We draw N rectangles side-by-side, each
    with width = (industry_total / grand_total) * canvas_width. Within each
    column we stack one rectangle per stage with HEIGHT = (stage / column)
    of the canvas height. Labels: industry name + total above column,
    percentage inside cells where >= 5%.
    """
    if not table or not isinstance(table[0], list):
        return
    industries = [_cell_str(c) for c in table[0][1:] if _cell_str(c)]
    n_industries = len(industries)
    if n_industries == 0:
        return
    stages: list[str] = []
    matrix: list[list[float]] = []  # rows = stages, cols = industries
    for row in table[1:]:
        if not isinstance(row, list) or not row:
            continue
        stages.append(_cell_str(row[0]))
        nums = [_cell_num(c) or 0.0 for c in row[1:]]
        # Pad/truncate to industry count
        if len(nums) < n_industries:
            nums = nums + [0.0] * (n_industries - len(nums))
        nums = nums[:n_industries]
        matrix.append(nums)
    if not stages:
        return

    # Column totals
    col_totals = [sum(matrix[s][i] for s in range(len(stages))) for i in range(n_industries)]
    grand_total = sum(col_totals) or 1.0

    # Title
    title_box = slide.shapes.add_textbox(_CANVAS_LEFT, _CANVAS_TOP, _CANVAS_WIDTH, Emu(280_000))
    tf = title_box.text_frame
    tf.paragraphs[0].text = title
    for run in tf.paragraphs[0].runs:
        _set_run_font(run, font=font, size_pt=14.0, bold=True, hex_color=palette["neutral_dark"])

    # Mekko canvas (below title, above bottom)
    mekko_top = _CANVAS_TOP.emu + 600_000  # leave space for top labels (industry + total)
    mekko_height = _CANVAS_HEIGHT.emu - 800_000
    mekko_left = _CANVAS_LEFT.emu
    mekko_width = _CANVAS_WIDTH.emu - 200_000  # tiny right margin

    cur_x = mekko_left
    for i, industry in enumerate(industries):
        col_total = col_totals[i]
        col_w = (
            max(int((col_total / grand_total) * mekko_width), 100_000)
            if grand_total
            else mekko_width // n_industries
        )
        # Top label: industry + total
        lbl = slide.shapes.add_textbox(
            Emu(cur_x), Emu(_CANVAS_TOP.emu + 320_000), Emu(col_w), Emu(280_000)
        )
        ltf = lbl.text_frame
        ltf.word_wrap = True
        p = ltf.paragraphs[0]
        p.alignment = PP_ALIGN.CENTER
        r = p.add_run()
        r.text = f"{_truncate(industry, 14)}\n{col_total:.1f}M"
        _set_run_font(r, font=font, size_pt=8.0, bold=True, hex_color=palette["neutral_dark"])

        # Stack stages
        stage_palette = list(_STAGE_PALETTE)
        cur_y = mekko_top
        for s_idx, stage in enumerate(stages):
            stage_val = matrix[s_idx][i]
            frac = stage_val / col_total if col_total > 0 else 0.0
            seg_h = int(frac * mekko_height)
            if seg_h <= 0:
                continue
            color_hex = stage_palette[s_idx % len(stage_palette)]
            rect = slide.shapes.add_shape(
                MSO_SHAPE.RECTANGLE,
                Emu(cur_x),
                Emu(cur_y),
                Emu(col_w - 30_000),  # gutter between columns
                Emu(seg_h),
            )
            rect.fill.solid()
            rect.fill.fore_color.rgb = _hex_to_rgb(color_hex)
            rect.line.color.rgb = _hex_to_rgb("#FFFFFF")
            rect.line.width = Pt(0.75)
            # Inner percentage label if >= 5%
            if frac >= 0.05 and seg_h > 220_000:
                rtf = rect.text_frame
                rtf.margin_left = Emu(36_000)
                rtf.margin_right = Emu(36_000)
                rtf.margin_top = Emu(18_000)
                rtf.margin_bottom = Emu(18_000)
                rtf.paragraphs[0].alignment = PP_ALIGN.CENTER
                run = rtf.paragraphs[0].add_run()
                run.text = f"{frac * 100:.0f}%"
                # Pick label color based on background lightness
                _set_run_font(
                    run,
                    font=font,
                    size_pt=9.0,
                    bold=True,
                    hex_color="#FFFFFF" if s_idx <= 2 else palette["neutral_dark"],
                )
            cur_y += seg_h
        cur_x += col_w

    # Legend strip at the bottom: stage name + color swatch
    legend_top = mekko_top + mekko_height + 80_000
    legend_left = mekko_left
    swatch_w = Emu(140_000)
    legend_box_w = Emu(int((mekko_width) / max(len(stages), 1)))
    for s_idx, stage in enumerate(stages):
        color_hex = list(_STAGE_PALETTE)[s_idx % len(_STAGE_PALETTE)]
        sw = slide.shapes.add_shape(
            MSO_SHAPE.RECTANGLE,
            Emu(legend_left + s_idx * legend_box_w.emu),
            Emu(legend_top),
            swatch_w,
            Emu(140_000),
        )
        sw.fill.solid()
        sw.fill.fore_color.rgb = _hex_to_rgb(color_hex)
        sw.line.fill.background()
        lbl = slide.shapes.add_textbox(
            Emu(legend_left + s_idx * legend_box_w.emu + swatch_w.emu + 30_000),
            Emu(legend_top - 10_000),
            Emu(legend_box_w.emu - swatch_w.emu - 60_000),
            Emu(180_000),
        )
        ltf = lbl.text_frame
        p = ltf.paragraphs[0]
        run = p.add_run()
        run.text = _truncate(stage, 16)
        _set_run_font(run, font=font, size_pt=8.0, hex_color=palette["neutral_dark"])


# ---- chart-table helpers -----------------------------------------------------


def _split_chart_table(table: list[Any]) -> tuple[list[str], list[float | None]]:
    """Split a 2-row "headers | values" table into ``(categories, values)``.

    Tolerates ``None`` in the corner cell (common in ppttc shapes). Returns
    ``([], [])`` if the shape is unexpected.
    """
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
    vals: list[float | None] = []
    for cell in value_row[1 : len(cats) + 1]:
        vals.append(_cell_num(cell))
    return cats, vals


# ============================================================================
#                              TABLE RENDERERS
# ============================================================================


def _render_table(
    slide: Any,
    *,
    table: list[Any],
    title: str,
    palette: dict[str, str],
    font: str,
    max_rows: int = 10,
    fmt_overrides: dict[int, str] | None = None,
) -> None:
    """Native PowerPoint table; consulting-style header + alternating rows."""
    if not isinstance(table, list) or not table or not isinstance(table[0], list):
        return
    header = [_cell_str(c) or "" for c in table[0]]
    body_rows = []
    for row in table[1 : 1 + max_rows]:
        if not isinstance(row, list):
            continue
        body_rows.append(row)
    if not body_rows:
        # Render the header row only with a small placeholder
        body_rows = [[{"string": "(no rows)"} for _ in header]]

    n_cols = len(header)
    n_rows = len(body_rows) + 1  # +header

    # Title above
    title_box = slide.shapes.add_textbox(_CANVAS_LEFT, _CANVAS_TOP, _CANVAS_WIDTH, Emu(280_000))
    p = title_box.text_frame.paragraphs[0]
    run = p.add_run()
    run.text = title
    _set_run_font(run, font=font, size_pt=14.0, bold=True, hex_color=palette["neutral_dark"])

    # Table
    tb_top = Emu(_CANVAS_TOP.emu + 360_000)
    tb_height = Emu(min(_CANVAS_HEIGHT.emu - 360_000, 280_000 * n_rows + 60_000))
    table_shape = slide.shapes.add_table(
        n_rows, n_cols, _CANVAS_LEFT, tb_top, _CANVAS_WIDTH, tb_height
    )
    tbl = table_shape.table

    # Header
    for c, val in enumerate(header):
        cell = tbl.cell(0, c)
        cell.fill.solid()
        cell.fill.fore_color.rgb = _hex_to_rgb(palette["primary"])
        tf = cell.text_frame
        tf.text = ""
        para = tf.paragraphs[0]
        para.alignment = PP_ALIGN.LEFT if c <= 3 else PP_ALIGN.RIGHT
        r = para.add_run()
        r.text = val
        _set_run_font(r, font=font, size_pt=9.0, bold=True, hex_color="#FFFFFF")

    # Body
    for r_idx, row in enumerate(body_rows, start=1):
        stripe = r_idx % 2 == 0
        for c in range(n_cols):
            cell = tbl.cell(r_idx, c)
            if stripe:
                cell.fill.solid()
                cell.fill.fore_color.rgb = _hex_to_rgb(palette["neutral_light"])
            raw = row[c] if c < len(row) else None
            text, align = _format_table_cell(raw, header[c], fmt_overrides, c)
            tf = cell.text_frame
            tf.text = ""
            para = tf.paragraphs[0]
            para.alignment = align
            run = para.add_run()
            run.text = text
            _set_run_font(run, font=font, size_pt=9.0, hex_color=palette["neutral_dark"])

    # Force narrow # column if first header is "#"
    if header and header[0].strip() == "#":
        tbl.columns[0].width = Emu(420_000)


def _format_table_cell(
    raw: Any,
    header: str,
    fmt_overrides: dict[int, str] | None,
    col_idx: int,
) -> tuple[str, Any]:
    """Format ``raw`` based on the column header; return (text, alignment)."""
    h = (header or "").lower()
    if isinstance(raw, dict) and "string" in raw and isinstance(raw["string"], str):
        # String columns: left-align unless it's a numeric-looking header.
        return raw["string"], PP_ALIGN.LEFT
    if isinstance(raw, dict) and "number" in raw and isinstance(raw["number"], (int, float)):
        n = float(raw["number"])
        if "arr" in h and "eur" in h:
            return _fmt_eur(n), PP_ALIGN.RIGHT
        if "ac v" in h or "acv" in h:
            return _fmt_eur(n), PP_ALIGN.RIGHT
        if "share" in h or "%" in h or "pct" in h:
            return _fmt_pct(n), PP_ALIGN.RIGHT
        if "age" in h or "day" in h:
            return _fmt_int(n), PP_ALIGN.RIGHT
        if "score" in h:
            return f"{n:.1f}", PP_ALIGN.RIGHT
        if "#" == h or h.startswith("# "):
            return _fmt_int(n), PP_ALIGN.CENTER
        if "motion" in h:
            return _fmt_int(n), PP_ALIGN.CENTER
        # Default: integer
        return _fmt_int(n), PP_ALIGN.RIGHT
    if raw is None:
        return "", PP_ALIGN.LEFT
    return str(raw), PP_ALIGN.LEFT


def _render_table_metric(
    slide: Any,
    *,
    table: list[Any],
    title: str,
    palette: dict[str, str],
    font: str,
) -> None:
    """2-col Metric/Value table; percent values formatted with %."""
    _render_table(slide, table=table, title=title, palette=palette, font=font, max_rows=10)


def _render_table_risk(
    slide: Any,
    *,
    table: list[Any],
    title: str,
    palette: dict[str, str],
    font: str,
) -> None:
    """Renewal-pipeline table; risk-score column gets color-graded fill."""
    if not isinstance(table, list) or not table or not isinstance(table[0], list):
        return
    header = [_cell_str(c) or "" for c in table[0]]
    body_rows = [r for r in table[1:11] if isinstance(r, list)]

    # Find risk-score column (last numeric col with "score" in header)
    risk_col = None
    for i, h in enumerate(header):
        if "score" in h.lower():
            risk_col = i
            break

    # Render via the standard renderer first
    _render_table(slide, table=table, title=title, palette=palette, font=font, max_rows=10)
    # Now post-fill the risk col with a graded color.
    if risk_col is None or not body_rows:
        return
    # Find the just-added table
    last_table = None
    for shape in reversed(slide.shapes):
        if shape.has_table:
            last_table = shape.table
            break
    if last_table is None:
        return
    for r_idx, row in enumerate(body_rows, start=1):
        if risk_col >= len(row):
            continue
        cell_data = row[risk_col]
        score = _cell_num(cell_data)
        if score is None:
            continue
        if score >= 3.0:
            color = palette["warning"]
        elif score >= 2.0:
            color = palette["highlight"]
        else:
            color = palette["success"]
        try:
            tcell = last_table.cell(r_idx, risk_col)
            tcell.fill.solid()
            tcell.fill.fore_color.rgb = _hex_to_rgb(color)
            for para in tcell.text_frame.paragraphs:
                for run in para.runs:
                    run.font.color.rgb = _hex_to_rgb("#FFFFFF")
                    run.font.bold = True
        except (IndexError, AttributeError):
            continue


def _render_table_priority(
    slide: Any,
    *,
    table: list[Any],
    title: str,
    palette: dict[str, str],
    font: str,
) -> None:
    """Action items; priority column gets HIGH=coral / MED=amber / LOW=neutral fill."""
    if not isinstance(table, list) or not table or not isinstance(table[0], list):
        return
    header = [_cell_str(c) or "" for c in table[0]]
    body_rows = [r for r in table[1:11] if isinstance(r, list)]

    pri_col = None
    for i, h in enumerate(header):
        if h.lower().startswith("priority"):
            pri_col = i
            break

    _render_table(slide, table=table, title=title, palette=palette, font=font, max_rows=10)
    if pri_col is None or not body_rows:
        return

    last_table = None
    for shape in reversed(slide.shapes):
        if shape.has_table:
            last_table = shape.table
            break
    if last_table is None:
        return

    for r_idx, row in enumerate(body_rows, start=1):
        if pri_col >= len(row):
            continue
        v = _cell_str(row[pri_col]).upper()
        if v.startswith("HIGH"):
            color = palette["warning"]
            text_color = "#FFFFFF"
        elif v.startswith("MED"):
            color = palette["highlight"]
            text_color = palette["neutral_dark"]
        elif v.startswith("LOW"):
            color = palette["neutral_light"]
            text_color = palette["neutral_dark"]
        else:
            continue
        try:
            tcell = last_table.cell(r_idx, pri_col)
            tcell.fill.solid()
            tcell.fill.fore_color.rgb = _hex_to_rgb(color)
            for para in tcell.text_frame.paragraphs:
                for run in para.runs:
                    run.font.color.rgb = _hex_to_rgb(text_color)
                    run.font.bold = True
        except (IndexError, AttributeError):
            continue


__all__ = [
    "BRAND_PALETTE",
    "EnhanceResult",
    "enhance_deck",
]
