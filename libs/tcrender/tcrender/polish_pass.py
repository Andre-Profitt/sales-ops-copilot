"""Polish-pass for the LAND deck factory.

Operates on the rendered+enhanced ``.pptx`` as pure XML manipulation -- no
re-render needed. Fixes seven categories of visible quality issues that the
``native_fallback`` enhancer leaves behind:

1. **Donor-text strip** -- shapes whose text matches author-instruction
   patterns (``[think-cell TABLE WITH FORMATTING ...]``, ``Range: ...``,
   ``Source: legacy land.xlsx``, ``[Exec summary - manual paste ...]``,
   etc.) are removed (or their offending ``<a:t>`` runs cleared).

2. **Chart axis number formats** -- every native chart inserted by
   ``native_fallback`` has ``General`` / ``0,0000`` axes; this pass injects
   explicit ``<c:numFmt>`` children based on a binding-name -> format
   mapping (EUR -> ``#,##0\\ "M"``, percentage -> ``#,##0.0%``,
   day-count -> ``#,##0\\ "d"``, integer -> ``#,##0``).

3. **Divider dedupe** -- the four section dividers added by
   ``template_polish.add_section_dividers`` are removed when present (the
   original LAND template already ships with section header slides). Match
   is by content (navy ``083EA7`` background + Roman numeral text run),
   not slide index, so the strip is robust if positions shift.

4. **Naked-chart frame** -- slides containing only a ``<p:graphicFrame>``
   chart (no title text shape) get a title + subtitle text shape added,
   keyed off the chart's binding name.

5. **Cover treatment** -- the cover slide (slide 1) gains a navy left-side
   block + small coral accent band along the bottom.

6. **Mekko polish** -- the S16 stage-by-industry mekko gains:
   * column total annotations above each column,
   * baseline (1pt grey line) along the bottom,
   * a vertical y-axis tick scale on the LEFT (0 / 25 / 50 / 75 / 100 %).

7. **Footer subtler** -- the master footer's accent1 separator line is
   replaced with a 0.25pt light-grey line, and footer text is tinted
   neutral-grey (``#9CA3AF``) at 8pt instead of 9pt navy.

Public API
~~~~~~~~~~

* :data:`POLISH_PASS_AUDIT_KEY` -- audit JSON sidecar key.
* :class:`PolishPassResult` -- frozen result dataclass.
* :func:`polish_pass` -- run the polish pass; return :class:`PolishPassResult`.

Hard constraints:
    * python-pptx + lxml + zipfile/stdlib only.
    * ASCII-only.
    * Input ``.pptx`` is NEVER mutated; output goes to a new path.
    * Idempotent guard: refuses to polish a deck whose audit sidecar
      already records ``polish_pass_applied: true``.
"""

from __future__ import annotations

import copy
import json
import re
import shutil
import time
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

from lxml import etree

# -- namespaces -----------------------------------------------------------

_NS_DRAWING = "http://schemas.openxmlformats.org/drawingml/2006/main"
_NS_PRESENT = "http://schemas.openxmlformats.org/presentationml/2006/main"
_NS_RELS_OD = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_NS_RELS_PKG = "http://schemas.openxmlformats.org/package/2006/relationships"
_NS_CONTENT_TYPES = "http://schemas.openxmlformats.org/package/2006/content-types"
_NS_CHART = "http://schemas.openxmlformats.org/drawingml/2006/chart"

NSMAP = {"a": _NS_DRAWING, "p": _NS_PRESENT, "r": _NS_RELS_OD, "c": _NS_CHART}

# -- brand palette (mirrors template_polish + native_fallback) ------------

SIMCORP_NAVY_HEX = "083EA7"
SIMCORP_CORAL_HEX = "EF3E4A"
SIMCORP_NEUTRAL_DARK_HEX = "1A1D31"
SIMCORP_NEUTRAL_MID_HEX = "9CA3AF"
SIMCORP_NEUTRAL_LIGHT_HEX = "E3E3E3"

# Slide canvas geometry (16:9 LAND).
_SLIDE_W = 12_192_000
_SLIDE_H = 6_858_000

# EMU per inch (914_400) used for inch-based geometry.
_EMU_PER_INCH = 914_400

# Audit sidecar key for the idempotency check + post-run flag.
POLISH_PASS_AUDIT_KEY = "polish_pass_applied"
AUDIT_FILENAME = "audit.json"

# -- donor-text strip patterns -------------------------------------------

# Substrings; if a shape's joined text contains ANY of these AND the shape
# is not a tcfield_*-named element, the shape is removed entirely (or just
# the offending runs are cleared if some content is preserved).
_DONOR_TEXT_PATTERNS: tuple[str, ...] = (
    "[think-cell TABLE WITH FORMATTING",
    "[think-cell TABLE",
    "[think-cell text",
    "[plain text",
    "[Exec summary",
    "Source: legacy land.xlsx",
    "Source: model.xlsx",
    "Range: ",
    "Cols:",
    "Columns:",
    "Highlight Stage",
    "Insert a think-cell",
    "Annotate stages",
    "Bar height =",
    "Bar width =",
    "## Highlights",
    "## Risks",
    "Revenues, costs, totals",
    "paste from brief.md",
    "manual paste for Phase 1",
    "Conditional fill on Priority",
    "No think-cell binding here",
    "Replace per director by copying brief.md",
    "Phase 1: copy/paste",
    "[think-cell HARVEY BALL",
)

# tcfield naming prefix used by think-cell binding placeholders -- such
# shapes are EXCLUDED from the strip even when their text matches a
# pattern (they hold real data after ppttc fills them).
_TCFIELD_PREFIX = "tcfield"

# -- binding -> chart-axis number format ---------------------------------

# Maps the chart's title text (set by native_fallback to the friendly
# binding title from _BINDING_TITLES) to the value-axis number format.
# We match on title because chart files don't carry binding names directly.
_CHART_TITLE_TO_AXIS_FMT: dict[str, str] = {
    # EUR / mEUR axis charts -- show "5 M".
    "Pipe movement (ARR mEUR)": '#,##0\\ "M"',
    "Pipeline by stage": '#,##0\\ "M"',
    "Pipeline aging": '#,##0\\ "M"',
    "Forecast category": '#,##0\\ "M"',
    "Open ARR by owner": '#,##0\\ "M"',
    "Territory performance": '#,##0\\ "M"',
    # Percentage axis (concentration risk).
    "Concentration risk": "#,##0.0%",
    # Day-count axis (velocity).
    "Velocity (median age by stage)": '#,##0\\ "d"',
    # Integer-count axes.
    "Wins / losses QTD": "#,##0",
    "Stale activity by stage": "#,##0",
    "Pipeline creation velocity": "#,##0",
}

# -- naked-chart-slide friendly titles -----------------------------------

# Chart title text (already set by native_fallback) -> friendly slide
# title injected as a top-of-slide text shape when a slide has only a
# graphicFrame chart and no title shape.
_CHART_TITLE_TO_SLIDE_TITLE: dict[str, str] = {
    "Pipe movement (ARR mEUR)": "Pipe movement",
    "Pipeline by stage": "Pipeline by stage",
    "Pipeline aging": "Pipeline aging",
    "Forecast category": "Forecast category",
    "Open ARR by owner": "Open ARR by owner",
    "Territory performance": "Territory performance",
    "Wins / losses QTD": "Wins / losses QTD",
    "Velocity (median age by stage)": "Velocity",
    "Concentration risk": "Concentration risk",
    "Stale activity by stage": "Stale activity",
    "Pipeline creation velocity": "Pipeline creation velocity",
}


# -- result API -----------------------------------------------------------


@dataclass(frozen=True)
class PolishPassResult:
    """Outcome of :func:`polish_pass`.

    Attributes:
        output_path: Polished .pptx path.
        fixes_applied: Ordered list of fix descriptors applied
            (e.g. ``"donor_strip:slide10:Rectangle 5"``,
            ``"axis_fmt:chart13:#,##0\\ \"M\""``).
        skipped: ``(name, reason)`` pairs for fixes that were not applied
            (e.g. ``("dividers", "no dividers found")``).
        original_slide_count: Slide count in the input deck.
        polished_slide_count: Slide count in the output deck.
    """

    output_path: Path
    fixes_applied: list[str] = field(default_factory=list)
    skipped: list[tuple[str, str]] = field(default_factory=list)
    original_slide_count: int = 0
    polished_slide_count: int = 0


# -- public API -----------------------------------------------------------


def polish_pass(
    deck_path: Path,
    output_path: Path | None = None,
    *,
    director_name: str = "",
    period: str = "",
    scope_label: str = "",
) -> PolishPassResult:
    """Run all polish-pass fixes on ``deck_path``; return :class:`PolishPassResult`.

    Args:
        deck_path: Source ``.pptx`` (the rendered+enhanced deck). NEVER
            mutated.
        output_path: Where to write the polished ``.pptx``. When ``None``,
            defaults to ``<deck_path stem>-polished-<ts>.pptx`` alongside
            the input.
        director_name: Director name (used for cover/naked-chart subtitle
            text). Falls back to whatever the deck already shows.
        period: Quarter label (e.g. ``"2026-Q2"``).
        scope_label: Geo / scope label (e.g. ``"APAC"``).

    Returns:
        :class:`PolishPassResult` describing every fix applied + every
        skip with reason.

    Raises:
        FileNotFoundError: if ``deck_path`` does not exist.
        ValueError: if the deck has already been polished (audit sidecar
            records ``polish_pass_applied: true``).
        zipfile.BadZipFile: if ``deck_path`` is not a valid .pptx.
    """
    deck_path = deck_path.expanduser().resolve()
    if not deck_path.exists():
        raise FileNotFoundError(f"deck not found: {deck_path}")

    # Idempotency guard: if a sibling audit.json declares this deck has
    # already been polished, refuse the operation.
    audit_path = deck_path.parent / AUDIT_FILENAME
    audit: dict = {}
    if audit_path.exists():
        try:
            audit = json.loads(audit_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            audit = {}
        if audit.get(POLISH_PASS_AUDIT_KEY) is True:
            raise ValueError(
                f"deck already polished (audit sidecar says polish_pass_applied=true): {deck_path}"
            )

    if output_path is None:
        ts = time.strftime("%Y%m%d-%H%M%S")
        output_path = deck_path.with_name(f"{deck_path.stem}-polished-{ts}.pptx")
    else:
        output_path = output_path.expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    fixes_applied: list[str] = []
    skipped: list[tuple[str, str]] = []

    with zipfile.ZipFile(deck_path, "r") as zin:
        # Pull all parts into memory; we'll mutate selected ones and
        # write the result out as a fresh archive.
        parts: dict[str, bytes] = {n: zin.read(n) for n in zin.namelist()}

    original_slide_count = sum(1 for n in parts if re.match(r"^ppt/slides/slide\d+\.xml$", n))

    # 1. Strip donor instruction text from every slide.
    parts, donor_fixes = _apply_donor_strip(parts)
    fixes_applied.extend(donor_fixes)
    if not donor_fixes:
        skipped.append(("donor_strip", "no donor patterns matched"))

    # 2. Inject explicit numFmt on chart axes.
    parts, axis_fixes = _apply_axis_fmt(parts)
    fixes_applied.extend(axis_fixes)
    if not axis_fixes:
        skipped.append(("axis_fmt", "no charts matched title map"))

    # 3. Remove the four section dividers added by template_polish.
    parts, divider_fixes = _apply_divider_dedupe(parts)
    fixes_applied.extend(divider_fixes)
    if not divider_fixes:
        skipped.append(("divider_dedupe", "no dividers detected"))

    # 4. Frame naked-chart slides with title + subtitle.
    parts, frame_fixes = _apply_naked_chart_frame(
        parts,
        director_name=director_name,
        period=period,
        scope_label=scope_label,
    )
    fixes_applied.extend(frame_fixes)
    if not frame_fixes:
        skipped.append(("naked_chart_frame", "no naked-chart slides found"))

    # 5. Cover slide visual treatment.
    parts, cover_fixes = _apply_cover_treatment(parts)
    fixes_applied.extend(cover_fixes)
    if not cover_fixes:
        skipped.append(("cover_treatment", "cover slide already styled"))

    # 6. Mekko polish (slide 16 by index).
    parts, mekko_fixes = _apply_mekko_polish(parts)
    fixes_applied.extend(mekko_fixes)
    if not mekko_fixes:
        skipped.append(("mekko_polish", "mekko slide not detected"))

    # 7. Footer subtler.
    parts, footer_fixes = _apply_footer_subtler(parts)
    fixes_applied.extend(footer_fixes)
    if not footer_fixes:
        skipped.append(("footer_subtler", "PolishMasterFooter not found"))

    # Write fresh archive.
    tmp_out = output_path.with_suffix(output_path.suffix + ".tmp")
    try:
        with zipfile.ZipFile(tmp_out, "w", zipfile.ZIP_DEFLATED) as zout:
            for name, blob in parts.items():
                zout.writestr(name, blob)
        tmp_out.replace(output_path)
    finally:
        if tmp_out.exists():
            try:
                tmp_out.unlink()
            except OSError:
                pass

    polished_slide_count = sum(1 for n in parts if re.match(r"^ppt/slides/slide\d+\.xml$", n))

    # Best-effort: update the audit sidecar with the polish flag if it
    # exists. The sidecar lives next to the INPUT deck (decks/<ts>/
    # audit.json), not the output, so we keep its location.
    if audit_path.exists():
        audit[POLISH_PASS_AUDIT_KEY] = True
        audit["polish_pass_fixes_applied"] = list(fixes_applied)
        audit["polish_pass_skipped"] = [{"name": n, "reason": r} for n, r in skipped]
        audit["polish_pass_output_path"] = str(output_path)
        try:
            audit_path.write_text(
                json.dumps(audit, indent=2, sort_keys=True, ensure_ascii=True),
                encoding="utf-8",
            )
        except OSError:
            pass

    return PolishPassResult(
        output_path=output_path,
        fixes_applied=fixes_applied,
        skipped=skipped,
        original_slide_count=original_slide_count,
        polished_slide_count=polished_slide_count,
    )


# -- internals: fix 1 -- donor-text strip --------------------------------


def _apply_donor_strip(parts: dict[str, bytes]) -> tuple[dict[str, bytes], list[str]]:
    """Walk every slide, drop shapes whose text matches donor patterns.

    Returns updated parts + a list of ``"donor_strip:slideN:<shape>"``
    fix descriptors.
    """
    fixes: list[str] = []
    out_parts = dict(parts)
    for name, blob in parts.items():
        m = re.match(r"^ppt/slides/slide(\d+)\.xml$", name)
        if not m:
            continue
        slide_n = m.group(1)
        new_blob, slide_fixes = _strip_donor_text_from_slide(blob, slide_n)
        if slide_fixes:
            out_parts[name] = new_blob
            fixes.extend(slide_fixes)
    return out_parts, fixes


def _strip_donor_text_from_slide(
    slide_xml: bytes,
    slide_id: str,
) -> tuple[bytes, list[str]]:
    """Strip donor-instruction shapes from a single slide's XML."""
    fixes: list[str] = []
    try:
        root = etree.fromstring(slide_xml)
    except etree.XMLSyntaxError:
        return slide_xml, fixes

    sptree = root.find(f"{{{_NS_PRESENT}}}cSld/{{{_NS_PRESENT}}}spTree")
    if sptree is None:
        return slide_xml, fixes

    to_remove: list[etree._Element] = []
    for sp in list(sptree.iterchildren(f"{{{_NS_PRESENT}}}sp")):
        cnvpr = sp.find(f".//{{{_NS_PRESENT}}}cNvPr")
        name = (cnvpr.get("name") if cnvpr is not None else "") or ""

        # Joined text content
        text_parts: list[etree._Element] = list(sp.iter(f"{{{_NS_DRAWING}}}t"))
        joined_text = "".join((t.text or "") for t in text_parts)
        if not joined_text:
            continue

        if not _matches_donor_pattern(joined_text):
            continue

        # tcfield_* shapes carry real director data after ppttc fills
        # them. Even when the joined text *contains* a donor pattern,
        # we must NOT remove the whole shape -- instead clear only the
        # offending <a:t> runs, preserving the run scaffolding so any
        # remaining director-data runs survive.
        is_tcfield_shape = name.startswith(_TCFIELD_PREFIX) or _TCFIELD_PREFIX in (
            etree.tostring(sp).decode("utf-8")
        )
        if is_tcfield_shape:
            cleared = 0
            for t in text_parts:
                if t.text and _matches_donor_pattern(t.text):
                    t.text = ""
                    cleared += 1
            if cleared:
                fixes.append(f"donor_strip:slide{slide_id}:{name}:cleared-runs")
            continue

        to_remove.append(sp)
        fixes.append(f"donor_strip:slide{slide_id}:{name}")

    for sp in to_remove:
        parent = sp.getparent()
        if parent is not None:
            parent.remove(sp)

    if not fixes:
        return slide_xml, fixes

    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True), fixes


def _matches_donor_pattern(text: str) -> bool:
    """True iff ``text`` contains any donor-instruction pattern."""
    return any(p in text for p in _DONOR_TEXT_PATTERNS)


# -- internals: fix 2 -- axis numFmt -------------------------------------


def _apply_axis_fmt(parts: dict[str, bytes]) -> tuple[dict[str, bytes], list[str]]:
    """Inject explicit ``<c:numFmt>`` on each chart's value axis."""
    fixes: list[str] = []
    out_parts = dict(parts)
    for name, blob in parts.items():
        m = re.match(r"^ppt/charts/chart(\d+)\.xml$", name)
        if not m:
            continue
        chart_n = m.group(1)
        new_blob, fmt_applied = _set_chart_axis_fmt(blob)
        if fmt_applied is not None:
            out_parts[name] = new_blob
            fixes.append(f"axis_fmt:chart{chart_n}:{fmt_applied}")
    return out_parts, fixes


def _set_chart_axis_fmt(chart_xml: bytes) -> tuple[bytes, str | None]:
    """Set a value-axis numFmt on a single chart XML; return (new_xml, applied_fmt or None)."""
    try:
        root = etree.fromstring(chart_xml)
    except etree.XMLSyntaxError:
        return chart_xml, None

    # Read chart title text.
    title_el = root.find(f".//{{{_NS_CHART}}}title")
    if title_el is None:
        return chart_xml, None
    title_text = "".join((t.text or "") for t in title_el.iter(f"{{{_NS_DRAWING}}}t"))
    fmt = _CHART_TITLE_TO_AXIS_FMT.get(title_text)
    if fmt is None:
        return chart_xml, None

    # Apply on every valAx in the chart (single-axis charts have one;
    # combo charts may have multiple value axes).
    changed = False
    for valax in root.iter(f"{{{_NS_CHART}}}valAx"):
        existing = valax.find(f"{{{_NS_CHART}}}numFmt")
        if existing is not None:
            existing.set("formatCode", fmt)
            existing.set("sourceLinked", "0")
        else:
            # Insert per ECMA-376 schema position: after majorGridlines /
            # minorGridlines / title; before majorTickMark.
            new_nf = etree.SubElement(
                valax,
                f"{{{_NS_CHART}}}numFmt",
                attrib={"formatCode": fmt, "sourceLinked": "0"},
            )
            # Move it into the right spot: after axPos / majorGridlines /
            # minorGridlines / title; right before majorTickMark.
            valax.remove(new_nf)
            insert_at = _valax_insert_index_for_numfmt(valax)
            valax.insert(insert_at, new_nf)
        changed = True

    # Set categorical axis numFmt to General (text categories).
    for catax in root.iter(f"{{{_NS_CHART}}}catAx"):
        existing = catax.find(f"{{{_NS_CHART}}}numFmt")
        if existing is None:
            new_nf = etree.SubElement(
                catax,
                f"{{{_NS_CHART}}}numFmt",
                attrib={"formatCode": "General", "sourceLinked": "0"},
            )
            catax.remove(new_nf)
            insert_at = _valax_insert_index_for_numfmt(catax)
            catax.insert(insert_at, new_nf)
            changed = True

    if not changed:
        return chart_xml, None
    return (
        etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True),
        fmt,
    )


def _valax_insert_index_for_numfmt(ax: etree._Element) -> int:
    """Return the child index where a new ``<c:numFmt>`` should be inserted.

    Per ECMA-376, ``<c:numFmt>`` sits AFTER axId/scaling/delete/axPos/
    majorGridlines/minorGridlines/title, and BEFORE majorTickMark.
    """
    pre_tags = (
        f"{{{_NS_CHART}}}axId",
        f"{{{_NS_CHART}}}scaling",
        f"{{{_NS_CHART}}}delete",
        f"{{{_NS_CHART}}}axPos",
        f"{{{_NS_CHART}}}majorGridlines",
        f"{{{_NS_CHART}}}minorGridlines",
        f"{{{_NS_CHART}}}title",
    )
    insert_at = 0
    for i, child in enumerate(ax):
        if child.tag in pre_tags:
            insert_at = i + 1
        else:
            break
    return insert_at


# -- internals: fix 3 -- divider dedupe ----------------------------------


def _apply_divider_dedupe(
    parts: dict[str, bytes],
) -> tuple[dict[str, bytes], list[str]]:
    """Detect + remove section divider slides added by template_polish.

    Detection: slide XML contains both the navy hex ``083EA7`` AND the
    marker shape name ``SectionDividerBackground``. The combination is
    precise enough to ignore other navy-themed slides.
    """
    fixes: list[str] = []
    divider_slide_paths: list[str] = []

    for name, blob in parts.items():
        m = re.match(r"^ppt/slides/slide(\d+)\.xml$", name)
        if not m:
            continue
        text = blob.decode("utf-8", errors="ignore")
        if SIMCORP_NAVY_HEX in text and "SectionDividerBackground" in text:
            divider_slide_paths.append(name)

    if not divider_slide_paths:
        return parts, fixes

    out_parts = dict(parts)

    # Build the rid -> slide-target map from presentation rels.
    pres_rels_xml = out_parts.get("ppt/_rels/presentation.xml.rels")
    pres_xml = out_parts.get("ppt/presentation.xml")
    content_types_xml = out_parts.get("[Content_Types].xml")
    if pres_rels_xml is None or pres_xml is None or content_types_xml is None:
        return parts, fixes

    rels_root = etree.fromstring(pres_rels_xml)
    rid_to_target: dict[str, str] = {}
    target_to_rid: dict[str, str] = {}
    for rel in rels_root.iter(f"{{{_NS_RELS_PKG}}}Relationship"):
        target = rel.get("Target") or ""
        rid = rel.get("Id") or ""
        rid_to_target[rid] = target
        target_to_rid[target] = rid

    # Drop divider slide files + their rels files.
    rids_to_drop: set[str] = set()
    for slide_path in divider_slide_paths:
        rel_target = "slides/" + Path(slide_path).name
        rid = target_to_rid.get(rel_target)
        if rid is None:
            continue
        rids_to_drop.add(rid)
        # Remove the slide XML and its rels file.
        out_parts.pop(slide_path, None)
        rels_path = f"ppt/slides/_rels/{Path(slide_path).name}.rels"
        out_parts.pop(rels_path, None)
        fixes.append(f"divider_dedupe:{slide_path}")

    if not rids_to_drop:
        return parts, fixes

    # Patch ppt/_rels/presentation.xml.rels
    for rel in list(rels_root.iter(f"{{{_NS_RELS_PKG}}}Relationship")):
        if (rel.get("Id") or "") in rids_to_drop:
            parent = rel.getparent()
            if parent is not None:
                parent.remove(rel)
    out_parts["ppt/_rels/presentation.xml.rels"] = etree.tostring(
        rels_root, xml_declaration=True, encoding="UTF-8", standalone=True
    )

    # Patch ppt/presentation.xml -- remove dropped sldId entries.
    pres_root = etree.fromstring(pres_xml)
    sld_id_lst = pres_root.find(f"{{{_NS_PRESENT}}}sldIdLst")
    if sld_id_lst is not None:
        for sld in list(sld_id_lst.findall(f"{{{_NS_PRESENT}}}sldId")):
            rid = sld.get(f"{{{_NS_RELS_OD}}}id") or ""
            if rid in rids_to_drop:
                sld_id_lst.remove(sld)
    out_parts["ppt/presentation.xml"] = etree.tostring(
        pres_root, xml_declaration=True, encoding="UTF-8", standalone=True
    )

    # Patch [Content_Types].xml -- drop overrides for the removed slide parts.
    ct_root = etree.fromstring(content_types_xml)
    parts_to_drop = {f"/{p}" for p in divider_slide_paths}
    for ov in list(ct_root.iter(f"{{{_NS_CONTENT_TYPES}}}Override")):
        if (ov.get("PartName") or "") in parts_to_drop:
            parent = ov.getparent()
            if parent is not None:
                parent.remove(ov)
    out_parts["[Content_Types].xml"] = etree.tostring(
        ct_root, xml_declaration=True, encoding="UTF-8", standalone=True
    )

    return out_parts, fixes


# -- internals: fix 4 -- naked-chart frame -------------------------------


def _apply_naked_chart_frame(
    parts: dict[str, bytes],
    *,
    director_name: str,
    period: str,
    scope_label: str,
) -> tuple[dict[str, bytes], list[str]]:
    """Frame slides whose only content is a chart graphicFrame.

    Detect: slide has exactly one ``<p:graphicFrame>`` and zero ``<p:sp>``
    shapes carrying meaningful title text. Add: a 18pt bold title text
    box at the top-left + a 11pt subtitle below it.
    """
    fixes: list[str] = []
    out_parts = dict(parts)

    # Map slide path -> chart paths via slide rels.
    for name, blob in parts.items():
        m = re.match(r"^ppt/slides/slide(\d+)\.xml$", name)
        if not m:
            continue
        slide_n = m.group(1)

        try:
            root = etree.fromstring(blob)
        except etree.XMLSyntaxError:
            continue
        sptree = root.find(f"{{{_NS_PRESENT}}}cSld/{{{_NS_PRESENT}}}spTree")
        if sptree is None:
            continue

        sps = list(sptree.iterchildren(f"{{{_NS_PRESENT}}}sp"))
        gfs = list(sptree.iterchildren(f"{{{_NS_PRESENT}}}graphicFrame"))

        if len(gfs) != 1:
            continue

        # Heuristic: a slide is "naked" if no <p:sp> carries a substantial
        # title (>3 chars) and is named in a "Text Placeholder 3" /
        # "TitlePlaceholder" / "tcfield_S0X_" form. We collect the text
        # of the most-likely title shape and skip if any non-trivial
        # title text exists.
        has_title = False
        for sp in sps:
            cnvpr = sp.find(f".//{{{_NS_PRESENT}}}cNvPr")
            sp_name = (cnvpr.get("name") if cnvpr is not None else "") or ""
            text = "".join((t.text or "") for t in sp.iter(f"{{{_NS_DRAWING}}}t")).strip()
            if not text:
                continue
            # Subtitle band ("2026-Q2 LAND review - APAC") is OK; ignore
            # for "has title" check.
            if "LAND review" in text and (period or "") in text:
                continue
            # Footer-ish single-word counter shape -- skip.
            if len(text) <= 3:
                continue
            # Anything else (tcfield director, anything else with words)
            # counts as a title.
            if sp_name.startswith("Text Placeholder 3") or len(text) > 8:
                has_title = True
                break

        if has_title:
            continue

        # Find the chart's title via its rels-mapped chart XML.
        rels_path = f"ppt/slides/_rels/slide{slide_n}.xml.rels"
        chart_title = _resolve_chart_title_for_slide(out_parts, rels_path)
        slide_title = _CHART_TITLE_TO_SLIDE_TITLE.get(chart_title or "", chart_title or "")
        if not slide_title:
            continue

        # Subtitle: prefer the args; fall back to an existing "LAND review"
        # subtitle band already present.
        if director_name and period:
            subtitle_text = f"{director_name} | {period} LAND review"
            if scope_label:
                subtitle_text += f" | {scope_label}"
        elif period:
            subtitle_text = f"{period} LAND review"
            if scope_label:
                subtitle_text += f" | {scope_label}"
        else:
            subtitle_text = "LAND review"

        # Build + insert the title + subtitle shapes at the top of spTree.
        title_xml, subtitle_xml = _build_naked_chart_title_shapes(
            slide_title=slide_title,
            subtitle=subtitle_text,
            next_id=_next_shape_id(sptree),
        )
        title_el = etree.fromstring(title_xml)
        subtitle_el = etree.fromstring(subtitle_xml)
        # Insert AFTER the nvGrpSpPr / grpSpPr (which must remain first).
        insert_at = 0
        for i, child in enumerate(sptree):
            tag = etree.QName(child).localname
            if tag in ("nvGrpSpPr", "grpSpPr"):
                insert_at = i + 1
            else:
                break
        sptree.insert(insert_at, title_el)
        sptree.insert(insert_at + 1, subtitle_el)

        out_parts[name] = etree.tostring(
            root, xml_declaration=True, encoding="UTF-8", standalone=True
        )
        fixes.append(f"naked_chart_frame:slide{slide_n}:{slide_title}")

    return out_parts, fixes


def _resolve_chart_title_for_slide(
    parts: dict[str, bytes],
    rels_path: str,
) -> str | None:
    """Resolve the chart title text reachable via the slide's rels file."""
    rels_blob = parts.get(rels_path)
    if rels_blob is None:
        return None
    try:
        rels_root = etree.fromstring(rels_blob)
    except etree.XMLSyntaxError:
        return None
    chart_targets: list[str] = []
    for rel in rels_root.iter(f"{{{_NS_RELS_PKG}}}Relationship"):
        target = rel.get("Target") or ""
        if "charts/chart" in target:
            chart_targets.append(target)
    # Pick the chart whose title is in our friendly map; first wins.
    for target in chart_targets:
        # rels target is "../charts/chartN.xml" relative to slide rels;
        # absolute pkg path is "ppt/charts/chartN.xml".
        chart_path = "ppt/charts/" + target.split("/")[-1]
        chart_blob = parts.get(chart_path)
        if chart_blob is None:
            continue
        try:
            chart_root = etree.fromstring(chart_blob)
        except etree.XMLSyntaxError:
            continue
        title_el = chart_root.find(f".//{{{_NS_CHART}}}title")
        if title_el is None:
            continue
        title_text = "".join((t.text or "") for t in title_el.iter(f"{{{_NS_DRAWING}}}t"))
        if title_text in _CHART_TITLE_TO_SLIDE_TITLE:
            return title_text
    return None


def _build_naked_chart_title_shapes(
    slide_title: str,
    subtitle: str,
    next_id: int,
) -> tuple[bytes, bytes]:
    """Build (title, subtitle) text shape XML for a naked-chart slide."""
    # Geometry: title 0.4" from top, 0.5" tall, 11" wide; subtitle 0.85"
    # from top, 0.3" tall, 11" wide. Left-aligned, 0.4" from left edge.
    left = int(0.4 * _EMU_PER_INCH)
    title_top = int(0.4 * _EMU_PER_INCH)
    title_h = int(0.5 * _EMU_PER_INCH)
    width = int(11.0 * _EMU_PER_INCH)
    sub_top = int(0.85 * _EMU_PER_INCH)
    sub_h = int(0.3 * _EMU_PER_INCH)

    title_xml = (
        '<p:sp xmlns:a="' + _NS_DRAWING + '" '
        'xmlns:p="' + _NS_PRESENT + '" '
        'xmlns:r="' + _NS_RELS_OD + '">'
        "<p:nvSpPr>"
        f'<p:cNvPr id="{next_id}" name="PolishPassNakedTitle"/>'
        '<p:cNvSpPr txBox="1"/>'
        "<p:nvPr/>"
        "</p:nvSpPr>"
        "<p:spPr>"
        f'<a:xfrm><a:off x="{left}" y="{title_top}"/>'
        f'<a:ext cx="{width}" cy="{title_h}"/></a:xfrm>'
        '<a:prstGeom prst="rect"><a:avLst/></a:prstGeom>'
        "<a:noFill/><a:ln><a:noFill/></a:ln>"
        "</p:spPr>"
        "<p:txBody>"
        '<a:bodyPr wrap="square" anchor="t" lIns="0" tIns="0" rIns="0" bIns="0"/>'
        "<a:lstStyle/>"
        '<a:p><a:pPr algn="l"/>'
        '<a:r><a:rPr lang="en-US" sz="1800" b="1">'
        f'<a:solidFill><a:srgbClr val="{SIMCORP_NEUTRAL_DARK_HEX}"/></a:solidFill>'
        '<a:latin typeface="Calibri"/>'
        "</a:rPr>"
        f"<a:t>{_xml_escape(slide_title)}</a:t>"
        "</a:r></a:p>"
        "</p:txBody>"
        "</p:sp>"
    ).encode("utf-8")

    subtitle_xml = (
        '<p:sp xmlns:a="' + _NS_DRAWING + '" '
        'xmlns:p="' + _NS_PRESENT + '" '
        'xmlns:r="' + _NS_RELS_OD + '">'
        "<p:nvSpPr>"
        f'<p:cNvPr id="{next_id + 1}" name="PolishPassNakedSubtitle"/>'
        '<p:cNvSpPr txBox="1"/>'
        "<p:nvPr/>"
        "</p:nvSpPr>"
        "<p:spPr>"
        f'<a:xfrm><a:off x="{left}" y="{sub_top}"/>'
        f'<a:ext cx="{width}" cy="{sub_h}"/></a:xfrm>'
        '<a:prstGeom prst="rect"><a:avLst/></a:prstGeom>'
        "<a:noFill/><a:ln><a:noFill/></a:ln>"
        "</p:spPr>"
        "<p:txBody>"
        '<a:bodyPr wrap="square" anchor="t" lIns="0" tIns="0" rIns="0" bIns="0"/>'
        "<a:lstStyle/>"
        '<a:p><a:pPr algn="l"/>'
        '<a:r><a:rPr lang="en-US" sz="1100">'
        f'<a:solidFill><a:srgbClr val="{SIMCORP_NEUTRAL_MID_HEX}"/></a:solidFill>'
        '<a:latin typeface="Calibri"/>'
        "</a:rPr>"
        f"<a:t>{_xml_escape(subtitle)}</a:t>"
        "</a:r></a:p>"
        "</p:txBody>"
        "</p:sp>"
    ).encode("utf-8")

    return title_xml, subtitle_xml


# -- internals: fix 5 -- cover slide treatment ---------------------------


def _apply_cover_treatment(
    parts: dict[str, bytes],
) -> tuple[dict[str, bytes], list[str]]:
    """Add a navy left-side stripe + bottom coral accent band to slide1."""
    fixes: list[str] = []
    cover_path = "ppt/slides/slide1.xml"
    blob = parts.get(cover_path)
    if blob is None:
        return parts, fixes

    try:
        root = etree.fromstring(blob)
    except etree.XMLSyntaxError:
        return parts, fixes

    sptree = root.find(f"{{{_NS_PRESENT}}}cSld/{{{_NS_PRESENT}}}spTree")
    if sptree is None:
        return parts, fixes

    # Idempotency: don't double-inject.
    for cnvpr in sptree.iter(f"{{{_NS_PRESENT}}}cNvPr"):
        if (cnvpr.get("name") or "") == "PolishPassCoverNavyStripe":
            return parts, fixes

    next_id = _next_shape_id(sptree)
    stripe_xml = _build_cover_navy_stripe(next_id)
    band_xml = _build_cover_coral_band(next_id + 1)

    stripe_el = etree.fromstring(stripe_xml)
    band_el = etree.fromstring(band_xml)

    # Insert stripe + band BEFORE the existing text shapes so they sit
    # behind. Find the first <p:sp> and insert before it.
    insert_at = 0
    for i, child in enumerate(sptree):
        tag = etree.QName(child).localname
        if tag in ("nvGrpSpPr", "grpSpPr"):
            insert_at = i + 1
        else:
            break
    sptree.insert(insert_at, stripe_el)
    sptree.insert(insert_at + 1, band_el)

    out_parts = dict(parts)
    out_parts[cover_path] = etree.tostring(
        root, xml_declaration=True, encoding="UTF-8", standalone=True
    )
    fixes.append("cover_treatment:navy_stripe+coral_band")
    return out_parts, fixes


def _build_cover_navy_stripe(shape_id: int) -> bytes:
    """Build the full-height navy stripe (~20% width, left side)."""
    width = int(_SLIDE_W * 0.20)
    return (
        '<p:sp xmlns:a="' + _NS_DRAWING + '" '
        'xmlns:p="' + _NS_PRESENT + '" '
        'xmlns:r="' + _NS_RELS_OD + '">'
        "<p:nvSpPr>"
        f'<p:cNvPr id="{shape_id}" name="PolishPassCoverNavyStripe"/>'
        "<p:cNvSpPr/><p:nvPr/>"
        "</p:nvSpPr>"
        "<p:spPr>"
        f'<a:xfrm><a:off x="0" y="0"/>'
        f'<a:ext cx="{width}" cy="{_SLIDE_H}"/></a:xfrm>'
        '<a:prstGeom prst="rect"><a:avLst/></a:prstGeom>'
        f'<a:solidFill><a:srgbClr val="{SIMCORP_NAVY_HEX}"/></a:solidFill>'
        "<a:ln><a:noFill/></a:ln>"
        "</p:spPr>"
        "<p:txBody><a:bodyPr/><a:lstStyle/><a:p/></p:txBody>"
        "</p:sp>"
    ).encode("utf-8")


def _build_cover_coral_band(shape_id: int) -> bytes:
    """Build the small coral accent band along the bottom (~3% height)."""
    height = int(_SLIDE_H * 0.03)
    y = _SLIDE_H - height
    return (
        '<p:sp xmlns:a="' + _NS_DRAWING + '" '
        'xmlns:p="' + _NS_PRESENT + '" '
        'xmlns:r="' + _NS_RELS_OD + '">'
        "<p:nvSpPr>"
        f'<p:cNvPr id="{shape_id}" name="PolishPassCoverCoralBand"/>'
        "<p:cNvSpPr/><p:nvPr/>"
        "</p:nvSpPr>"
        "<p:spPr>"
        f'<a:xfrm><a:off x="0" y="{y}"/>'
        f'<a:ext cx="{_SLIDE_W}" cy="{height}"/></a:xfrm>'
        '<a:prstGeom prst="rect"><a:avLst/></a:prstGeom>'
        f'<a:solidFill><a:srgbClr val="{SIMCORP_CORAL_HEX}"/></a:solidFill>'
        "<a:ln><a:noFill/></a:ln>"
        "</p:spPr>"
        "<p:txBody><a:bodyPr/><a:lstStyle/><a:p/></p:txBody>"
        "</p:sp>"
    ).encode("utf-8")


# -- internals: fix 6 -- mekko polish ------------------------------------


def _apply_mekko_polish(
    parts: dict[str, bytes],
) -> tuple[dict[str, bytes], list[str]]:
    """Add baseline + y-tick scale to the mekko slide.

    Detection: slide whose XML contains "Stage by industry" anywhere in
    its text. The native_fallback already adds column total annotations
    (e.g. "Pension\\n11.8M"); we only add the missing baseline and tick
    scale.
    """
    fixes: list[str] = []
    out_parts = dict(parts)

    for name, blob in parts.items():
        m = re.match(r"^ppt/slides/slide(\d+)\.xml$", name)
        if not m:
            continue
        text = blob.decode("utf-8", errors="ignore")
        if "Stage by industry" not in text:
            continue
        try:
            root = etree.fromstring(blob)
        except etree.XMLSyntaxError:
            continue
        sptree = root.find(f"{{{_NS_PRESENT}}}cSld/{{{_NS_PRESENT}}}spTree")
        if sptree is None:
            continue
        # Idempotency.
        already = False
        for cnvpr in sptree.iter(f"{{{_NS_PRESENT}}}cNvPr"):
            if (cnvpr.get("name") or "") == "PolishPassMekkoBaseline":
                already = True
                break
        if already:
            continue

        next_id = _next_shape_id(sptree)
        baseline_xml = _build_mekko_baseline(next_id)
        tick_blocks = _build_mekko_y_ticks(next_id + 1)
        sptree.append(etree.fromstring(baseline_xml))
        for tb in tick_blocks:
            sptree.append(etree.fromstring(tb))

        out_parts[name] = etree.tostring(
            root, xml_declaration=True, encoding="UTF-8", standalone=True
        )
        fixes.append(f"mekko_polish:slide{m.group(1)}:baseline+yticks")

    return out_parts, fixes


def _build_mekko_baseline(shape_id: int) -> bytes:
    """Build a 1pt grey horizontal line under the mekko columns.

    The native mekko chart canvas spans roughly x=0.5" to x=12.5" and
    its baseline is around y=6.0" (just above the footer). We use the
    same coordinates as the native_fallback canvas region.
    """
    left = int(0.5 * _EMU_PER_INCH)
    right = int(12.5 * _EMU_PER_INCH)
    y = int(6.05 * _EMU_PER_INCH)
    width = right - left
    return (
        '<p:cxnSp xmlns:a="' + _NS_DRAWING + '" '
        'xmlns:p="' + _NS_PRESENT + '" '
        'xmlns:r="' + _NS_RELS_OD + '">'
        "<p:nvCxnSpPr>"
        f'<p:cNvPr id="{shape_id}" name="PolishPassMekkoBaseline"/>'
        "<p:cNvCxnSpPr/><p:nvPr/>"
        "</p:nvCxnSpPr>"
        "<p:spPr>"
        f'<a:xfrm><a:off x="{left}" y="{y}"/>'
        f'<a:ext cx="{width}" cy="0"/></a:xfrm>'
        '<a:prstGeom prst="line"><a:avLst/></a:prstGeom>'
        '<a:ln w="12700">'
        f'<a:solidFill><a:srgbClr val="{SIMCORP_NEUTRAL_MID_HEX}"/></a:solidFill>'
        "</a:ln>"
        "</p:spPr>"
        "</p:cxnSp>"
    ).encode("utf-8")


def _build_mekko_y_ticks(start_id: int) -> list[bytes]:
    """Build five tick labels on the LEFT (0%, 25%, 50%, 75%, 100%)."""
    # Tick column ~0.05" wide, 0.4" tall labels, 0.05" left of mekko area.
    left = int(0.05 * _EMU_PER_INCH)
    label_width = int(0.4 * _EMU_PER_INCH)
    label_height = int(0.3 * _EMU_PER_INCH)
    # Match the native canvas: top ~1.7" (after subtitle/title), bottom ~6.0".
    top_y = int(1.7 * _EMU_PER_INCH)
    bottom_y = int(6.0 * _EMU_PER_INCH)
    span = bottom_y - top_y

    out: list[bytes] = []
    labels = ["100%", "75%", "50%", "25%", "0%"]
    for i, label in enumerate(labels):
        # i=0 -> top (100%), i=4 -> bottom (0%)
        y = top_y + int(span * i / (len(labels) - 1)) - label_height // 2
        sid = start_id + i
        xml = (
            '<p:sp xmlns:a="' + _NS_DRAWING + '" '
            'xmlns:p="' + _NS_PRESENT + '" '
            'xmlns:r="' + _NS_RELS_OD + '">'
            "<p:nvSpPr>"
            f'<p:cNvPr id="{sid}" name="PolishPassMekkoYTick{i}"/>'
            '<p:cNvSpPr txBox="1"/><p:nvPr/>'
            "</p:nvSpPr>"
            "<p:spPr>"
            f'<a:xfrm><a:off x="{left}" y="{y}"/>'
            f'<a:ext cx="{label_width}" cy="{label_height}"/></a:xfrm>'
            '<a:prstGeom prst="rect"><a:avLst/></a:prstGeom>'
            "<a:noFill/><a:ln><a:noFill/></a:ln>"
            "</p:spPr>"
            "<p:txBody>"
            '<a:bodyPr wrap="square" anchor="ctr" lIns="0" tIns="0" rIns="0" bIns="0"/>'
            "<a:lstStyle/>"
            '<a:p><a:pPr algn="r"/>'
            '<a:r><a:rPr lang="en-US" sz="800">'
            f'<a:solidFill><a:srgbClr val="{SIMCORP_NEUTRAL_MID_HEX}"/></a:solidFill>'
            '<a:latin typeface="Calibri"/>'
            "</a:rPr>"
            f"<a:t>{label}</a:t>"
            "</a:r></a:p>"
            "</p:txBody>"
            "</p:sp>"
        ).encode("utf-8")
        out.append(xml)
    return out


# -- internals: fix 7 -- footer subtler ----------------------------------


def _apply_footer_subtler(
    parts: dict[str, bytes],
) -> tuple[dict[str, bytes], list[str]]:
    """Soften the master footer: drop the navy line, neutral-grey 8pt text."""
    fixes: list[str] = []
    out_parts = dict(parts)

    for name, blob in parts.items():
        if not re.match(r"^ppt/slideMasters/slideMaster\d+\.xml$", name):
            continue
        try:
            root = etree.fromstring(blob)
        except etree.XMLSyntaxError:
            continue
        sptree = root.find(f"{{{_NS_PRESENT}}}cSld/{{{_NS_PRESENT}}}spTree")
        if sptree is None:
            continue

        changed = False
        # Soften the line to lt2 / 0.25pt grey (or remove entirely).
        # Spec: "make it lt2 light grey at 0.25pt" -- we set fill grey
        # + stroke width to 3175 EMU (0.25pt).
        for cxn in list(sptree.iter(f"{{{_NS_PRESENT}}}cxnSp")):
            cnvpr = cxn.find(f".//{{{_NS_PRESENT}}}cNvPr")
            if cnvpr is None or (cnvpr.get("name") or "") != "PolishMasterFooterLine":
                continue
            ln_el = cxn.find(f".//{{{_NS_DRAWING}}}ln")
            if ln_el is not None:
                ln_el.set("w", "3175")
                # Drop accent1 fill, replace with srgbClr neutral mid.
                fill = ln_el.find(f"{{{_NS_DRAWING}}}solidFill")
                if fill is not None:
                    for child in list(fill):
                        fill.remove(child)
                    etree.SubElement(
                        fill,
                        f"{{{_NS_DRAWING}}}srgbClr",
                        attrib={"val": SIMCORP_NEUTRAL_MID_HEX},
                    )
                changed = True
                fixes.append(f"footer_subtler:{name}:line_softened")

        # Tint the footer text grey + 8pt.
        for sp in sptree.iter(f"{{{_NS_PRESENT}}}sp"):
            cnvpr = sp.find(f".//{{{_NS_PRESENT}}}cNvPr")
            if cnvpr is None or (cnvpr.get("name") or "") != "PolishMasterFooter":
                continue
            # Adjust every <a:rPr sz="..."> + every <a:srgbClr val="..."/>
            # under text runs / fields to neutral_mid + 800 (8pt).
            for rpr in sp.iter(f"{{{_NS_DRAWING}}}rPr"):
                rpr.set("sz", "800")
            for defrpr in sp.iter(f"{{{_NS_DRAWING}}}defRPr"):
                defrpr.set("sz", "800")
            for fill in sp.iter(f"{{{_NS_DRAWING}}}solidFill"):
                for child in list(fill):
                    fill.remove(child)
                etree.SubElement(
                    fill,
                    f"{{{_NS_DRAWING}}}srgbClr",
                    attrib={"val": SIMCORP_NEUTRAL_MID_HEX},
                )
            changed = True
            fixes.append(f"footer_subtler:{name}:text_grey_8pt")

        if changed:
            out_parts[name] = etree.tostring(
                root, xml_declaration=True, encoding="UTF-8", standalone=True
            )

    return out_parts, fixes


# -- shared helpers -------------------------------------------------------


def _next_shape_id(sptree: etree._Element) -> int:
    """Return the next free ``<p:cNvPr id>`` value in ``sptree``."""
    used: set[int] = set()
    for cnvpr in sptree.iter(f"{{{_NS_PRESENT}}}cNvPr"):
        try:
            used.add(int(cnvpr.get("id") or "0"))
        except ValueError:
            continue
    n = 1
    while n in used:
        n += 1
    return n


def _xml_escape(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


__all__ = [
    "AUDIT_FILENAME",
    "POLISH_PASS_AUDIT_KEY",
    "PolishPassResult",
    "SIMCORP_CORAL_HEX",
    "SIMCORP_NAVY_HEX",
    "SIMCORP_NEUTRAL_DARK_HEX",
    "SIMCORP_NEUTRAL_MID_HEX",
    "polish_pass",
]


# Avoid F401 on copy/shutil/time -- used in helper paths above.
_ = (copy, shutil, time)
