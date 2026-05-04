"""Template polish for the LAND deck factory.

Three pure-XML mutations on ``assets/LAND_thinkcell_seed.pptx`` that lift
the visible quality of every rendered deck without touching PowerPoint:

1. :func:`embed_thinkcell_style` -- inject ``SimCorp-thinkcell-style.xml``
   as a ``customXml/itemN.xml`` part. think-cell picks the style up at
   render time once it is registered in ``[Content_Types].xml`` and
   wired into ``ppt/_rels/presentation.xml.rels`` as a
   ``customXml`` relationship.

2. :func:`add_section_dividers` -- splice 1..N full-bleed navy section
   divider slides into the deck at chosen positions. Each divider is a
   self-contained ``ppt/slides/slideN.xml`` part with its own rels file
   pointing to ``slideLayout1`` and gets registered with both
   ``[Content_Types].xml`` and ``ppt/_rels/presentation.xml.rels``. The
   ``<p:sldIdLst>`` in ``ppt/presentation.xml`` is patched to insert the
   new ``<p:sldId>`` entries at the requested positions.

3. :func:`add_footer_to_master` -- inject a footer band into
   ``ppt/slideMasters/slideMaster1.xml`` that prints the director name +
   period + ``slidenum/slidecount`` and a thin accent1 separator line.
   The cover slide and section divider slides opt out via
   ``<p:hf ftr="0" sldNum="0"/>`` overrides on their own slide XML so
   the footer does not appear there.

Composite :func:`polish_template` runs all three in sequence on a single
input -> output pair.

Hard constraints
~~~~~~~~~~~~~~~~

* python-pptx + lxml + zipfile/stdlib only. No new heavy deps.
* ASCII-only.
* Input .pptx is NEVER mutated -- always emit to a new path.
* The polished template must still pass ``tcrender.verify`` and
  ``tcrender.quality`` gates -- existing wired ``tcfield_*`` bindings
  on existing slide indices are not touched.
* Director name + period in the master footer reuse Jinja-style
  ``{director_name}`` / ``{period}`` placeholders so
  :func:`tcrender.template_prep.substitute_placeholders` (with
  ``include_masters=True``) fills them per-render.
"""

from __future__ import annotations

import copy
import re
import shutil
import tempfile
import time
import zipfile
from dataclasses import dataclass
from pathlib import Path

from lxml import etree

# -- namespaces ------------------------------------------------------------

_NS_DRAWING = "http://schemas.openxmlformats.org/drawingml/2006/main"
_NS_PRESENT = "http://schemas.openxmlformats.org/presentationml/2006/main"
_NS_RELS_OD = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_NS_RELS_PKG = "http://schemas.openxmlformats.org/package/2006/relationships"
_NS_CONTENT_TYPES = "http://schemas.openxmlformats.org/package/2006/content-types"
_NS_DS = "http://schemas.openxmlformats.org/officeDocument/2006/customXml"

NSMAP = {"a": _NS_DRAWING, "p": _NS_PRESENT, "r": _NS_RELS_OD}

# Content-type for a customXml data part and its props sidecar.
_CT_CUSTOM_XML_PROPS = "application/vnd.openxmlformats-officedocument.customXmlProperties+xml"
_CT_SLIDE = "application/vnd.openxmlformats-officedocument.presentationml.slide+xml"

# Slide content type / rels stay constant.
_REL_SLIDE = f"{_NS_RELS_OD}/slide"
_REL_CUSTOM_XML = f"{_NS_RELS_OD}/customXml"
_REL_SLIDE_LAYOUT = f"{_NS_RELS_OD}/slideLayout"

# SimCorp brand palette (from theme1.xml: 1_Simcorp / 240306 Simcorp).
SIMCORP_NAVY_HEX = "083EA7"
SIMCORP_CORAL_HEX = "EF3E4A"
SIMCORP_FOOTER_GREY_HEX = "6B7280"

# Slide canvas geometry (EMU). Default LAND template ships at 12192000 x
# 6858000 (16:9, 33.867 cm x 19.05 cm). Hard-coded here because every
# director deck inherits the same canvas; the polish step does not need
# to read this back from presentation.xml at runtime.
_SLIDE_W = 12192000
_SLIDE_H = 6858000

# Master-footer geometry (EMU). Sits ~6.6m EMU = ~0.27" up from bottom edge.
_FOOTER_BOTTOM_OFFSET = 240000  # 0.25"
_FOOTER_HEIGHT = 250000  # 0.26"
_FOOTER_LEFT_PAD = 380000  # 0.4"
_FOOTER_RIGHT_PAD = 380000  # 0.4"
_FOOTER_LINE_THICKNESS = 6350  # 0.5pt in EMU


@dataclass(frozen=True)
class SectionDivider:
    """A single section divider slide to splice into the deck.

    Attributes:
        insert_before_slide_index: 0-based index in the ORIGINAL deck of
            the slide that the new divider should appear immediately
            before. ``0`` puts the divider at the very top; values >=
            current slide count append to the end.
        roman: Roman numeral printed above the title in coral
            (e.g. ``"I"``, ``"II"``).
        title: Section title printed centered, white, large.
        subtitle: Optional one-line subtitle below the title (also
            white). Falls back to empty when omitted.
    """

    insert_before_slide_index: int
    roman: str
    title: str
    subtitle: str = ""


@dataclass(frozen=True)
class PolishResult:
    """Outcome of :func:`polish_template`.

    Attributes:
        output_path: Polished .pptx path.
        style_embedded: True iff the SimCorp think-cell style XML landed
            as a customXml part.
        section_dividers_added: Number of dividers spliced in.
        footer_added: True iff the master footer was injected.
        original_slide_count: Slides in the input .pptx.
        polished_slide_count: Slides in the output .pptx.
    """

    output_path: Path
    style_embedded: bool
    section_dividers_added: int
    footer_added: bool
    original_slide_count: int
    polished_slide_count: int


# -- public API ------------------------------------------------------------


def embed_thinkcell_style(
    pptx_path: Path,
    style_xml_path: Path,
    out_path: Path,
) -> Path:
    """Embed the think-cell style XML as a customXml part inside ``pptx_path``.

    Reads ``style_xml_path``, writes a new .pptx at ``out_path`` with
    ``customXml/itemN.xml`` (the style content) +
    ``customXml/itemProps<N>.xml`` (the datastoreItem props sidecar) +
    ``customXml/_rels/itemN.xml.rels`` (the props rel). Updates
    ``[Content_Types].xml`` Overrides for both new parts and adds a
    ``customXml`` relationship in ``ppt/_rels/presentation.xml.rels``.

    The next free ``item<N>`` index is computed from existing
    ``customXml/item*.xml`` parts. ``out_path`` parent is created if
    missing. ``pptx_path`` itself is NEVER mutated.

    Args:
        pptx_path: Source .pptx (e.g. ``LAND_thinkcell_seed.pptx``).
        style_xml_path: ``SimCorp-thinkcell-style.xml`` (or any
            think-cell .style XML).
        out_path: Destination .pptx.

    Returns:
        ``out_path``.

    Raises:
        FileNotFoundError: if either input does not exist.
        ValueError: if ``style_xml_path`` is not parseable XML.
        zipfile.BadZipFile: if ``pptx_path`` is not a valid .pptx.
    """
    pptx_path = pptx_path.expanduser().resolve()
    style_xml_path = style_xml_path.expanduser().resolve()
    out_path = out_path.expanduser().resolve()
    if not pptx_path.exists():
        raise FileNotFoundError(f"template not found: {pptx_path}")
    if not style_xml_path.exists():
        raise FileNotFoundError(f"style xml not found: {style_xml_path}")

    style_bytes = style_xml_path.read_bytes()
    # Parse to fail fast on malformed XML; we don't otherwise transform it.
    try:
        etree.fromstring(style_bytes)
    except etree.XMLSyntaxError as exc:
        raise ValueError(f"style xml is not valid XML: {exc}") from exc

    out_path.parent.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(pptx_path, "r") as zin:
        existing_names = set(zin.namelist())
        # Determine next item index. Existing customXml/item<N>.xml.
        item_idx = _next_custom_xml_item_index(existing_names)
        item_part = f"customXml/item{item_idx}.xml"
        props_part = f"customXml/itemProps{item_idx}.xml"
        item_rels = f"customXml/_rels/item{item_idx}.xml.rels"

        content_types_xml = zin.read("[Content_Types].xml")
        pres_rels_xml = zin.read("ppt/_rels/presentation.xml.rels")

        new_content_types = _content_types_add_overrides(
            content_types_xml,
            overrides=[
                (f"/{item_part}", _CT_CUSTOM_XML_PROPS_OR_XML(item_part)),
                (f"/{props_part}", _CT_CUSTOM_XML_PROPS),
            ],
        )
        new_pres_rels, _ = _presentation_rels_add(
            pres_rels_xml,
            target=f"../customXml/item{item_idx}.xml",
            rel_type=_REL_CUSTOM_XML,
        )

        props_xml = _build_item_props_xml(item_idx)
        item_rels_xml = _build_item_rels_xml(item_idx)

        tmp_out = out_path.with_suffix(out_path.suffix + ".tmp")
        try:
            with zipfile.ZipFile(tmp_out, "w", zipfile.ZIP_DEFLATED) as zout:
                for info in zin.infolist():
                    if info.filename == "[Content_Types].xml":
                        zout.writestr(info, new_content_types)
                    elif info.filename == "ppt/_rels/presentation.xml.rels":
                        zout.writestr(info, new_pres_rels)
                    else:
                        zout.writestr(info, zin.read(info.filename))
                zout.writestr(item_part, style_bytes)
                zout.writestr(props_part, props_xml)
                zout.writestr(item_rels, item_rels_xml)
            tmp_out.replace(out_path)
        finally:
            if tmp_out.exists():
                try:
                    tmp_out.unlink()
                except OSError:
                    pass

    return out_path


def add_section_dividers(
    pptx_path: Path,
    dividers: list[SectionDivider],
    out_path: Path,
) -> Path:
    """Splice section divider slides into ``pptx_path`` at requested positions.

    Each divider becomes a fresh ``ppt/slides/slide<N>.xml`` part with
    ``ppt/slides/_rels/slide<N>.xml.rels`` pointing to
    ``slideLayout1.xml``. ``[Content_Types].xml``,
    ``ppt/_rels/presentation.xml.rels``, and the ``<p:sldIdLst>`` in
    ``ppt/presentation.xml`` are all patched in one rewrite pass.

    Each divider:
        * Full-bleed SimCorp navy (``#083EA7``) background rectangle.
        * Roman numeral above the title in coral (``#EF3E4A``), 28pt.
        * Section title centered, white, 60pt, ``Microsoft Sans Serif``.
        * Optional white subtitle (24pt) below the title.
        * Bottom-left "<director_name> | <period>" mark via
          ``{director_name}`` / ``{period}`` Jinja placeholders.
        * Footer-suppression flag via ``<p:hf ftr="0" sldNum="0"/>``
          so the master-footer band does NOT print on dividers.

    Args:
        pptx_path: Source .pptx.
        dividers: Section dividers to splice. Order matters because
            ``insert_before_slide_index`` refers to the ORIGINAL deck;
            this function applies them in input order using the original
            indices (so passing two dividers with index ``5`` will land
            them adjacent at original-position-5).
        out_path: Destination .pptx.

    Returns:
        ``out_path``.

    Raises:
        FileNotFoundError: if ``pptx_path`` does not exist.
        ValueError: if any ``insert_before_slide_index`` is negative,
            or any ``roman`` / ``title`` is empty.
        zipfile.BadZipFile: if ``pptx_path`` is not a valid .pptx.
    """
    pptx_path = pptx_path.expanduser().resolve()
    out_path = out_path.expanduser().resolve()
    if not pptx_path.exists():
        raise FileNotFoundError(f"template not found: {pptx_path}")
    for d in dividers:
        if d.insert_before_slide_index < 0:
            raise ValueError(f"insert_before_slide_index must be >= 0: {d}")
        if not d.roman.strip() or not d.title.strip():
            raise ValueError(f"divider roman + title required: {d}")

    out_path.parent.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(pptx_path, "r") as zin:
        existing_names = list(zin.namelist())
        next_slide_idx = _next_slide_part_index(existing_names)

        content_types_xml = zin.read("[Content_Types].xml")
        pres_rels_xml = zin.read("ppt/_rels/presentation.xml.rels")
        presentation_xml = zin.read("ppt/presentation.xml")

        new_content_types = content_types_xml
        new_pres_rels = pres_rels_xml
        new_pres = presentation_xml
        new_parts: dict[str, bytes] = {}

        # We'll collect (relId, original_insert_before_idx) so we can
        # patch the <p:sldIdLst> in one pass at the end.
        new_slide_meta: list[tuple[str, int]] = []

        for d in dividers:
            slide_part = f"ppt/slides/slide{next_slide_idx}.xml"
            slide_rels = f"ppt/slides/_rels/slide{next_slide_idx}.xml.rels"
            slide_xml = _build_section_divider_xml(d)
            slide_rels_xml = _build_slide_rels_xml(layout_target="../slideLayouts/slideLayout1.xml")

            # 1. content-types: add Override for the slide part.
            new_content_types = _content_types_add_overrides(
                new_content_types,
                overrides=[(f"/{slide_part}", _CT_SLIDE)],
            )

            # 2. presentation rels: add a new slide relationship.
            new_pres_rels, rel_id = _presentation_rels_add(
                new_pres_rels,
                target=f"slides/slide{next_slide_idx}.xml",
                rel_type=_REL_SLIDE,
            )

            new_parts[slide_part] = slide_xml
            new_parts[slide_rels] = slide_rels_xml
            new_slide_meta.append((rel_id, d.insert_before_slide_index))
            next_slide_idx += 1

        # 3. presentation.xml: patch <p:sldIdLst>.
        new_pres = _presentation_insert_slide_ids(new_pres, new_slide_meta)

        tmp_out = out_path.with_suffix(out_path.suffix + ".tmp")
        try:
            with zipfile.ZipFile(tmp_out, "w", zipfile.ZIP_DEFLATED) as zout:
                for info in zin.infolist():
                    name = info.filename
                    if name == "[Content_Types].xml":
                        zout.writestr(info, new_content_types)
                    elif name == "ppt/_rels/presentation.xml.rels":
                        zout.writestr(info, new_pres_rels)
                    elif name == "ppt/presentation.xml":
                        zout.writestr(info, new_pres)
                    else:
                        zout.writestr(info, zin.read(name))
                for part_name, blob in new_parts.items():
                    zout.writestr(part_name, blob)
            tmp_out.replace(out_path)
        finally:
            if tmp_out.exists():
                try:
                    tmp_out.unlink()
                except OSError:
                    pass

    return out_path


def add_footer_to_master(pptx_path: Path, out_path: Path) -> Path:
    """Inject a footer band into ``ppt/slideMasters/slideMaster1.xml``.

    The footer band consists of two new shapes appended to the master's
    ``spTree``:

    1. A horizontal accent1 line (0.5pt) just above the footer text.
    2. A right-aligned text box with the literal pattern::

           {director_name} | {period} | <slidenum>/<slidecount>

       where ``{director_name}`` / ``{period}`` are Jinja placeholders
       resolved per-render by
       :func:`tcrender.template_prep.substitute_placeholders` (with
       ``include_masters=True`` so the master XML is included in the
       substitution sweep), and the slide number + total are PowerPoint
       native fields ``<a:fld type="slidenum"/>`` /
       ``<a:fld type="slidecount"/>``.

    The cover slide and any section divider slides should opt out by
    setting ``<p:hf sldNum="0" ftr="0" hdr="0" dt="0"/>`` on their own
    slide XML; :func:`add_section_dividers` already does this for new
    dividers, and :func:`polish_template` patches slide1 to suppress
    the footer on the cover.

    Args:
        pptx_path: Source .pptx (any LAND template).
        out_path: Destination .pptx.

    Returns:
        ``out_path``.

    Raises:
        FileNotFoundError: if ``pptx_path`` does not exist.
        zipfile.BadZipFile: if ``pptx_path`` is not a valid .pptx.
    """
    pptx_path = pptx_path.expanduser().resolve()
    out_path = out_path.expanduser().resolve()
    if not pptx_path.exists():
        raise FileNotFoundError(f"template not found: {pptx_path}")

    out_path.parent.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(pptx_path, "r") as zin:
        master_names = [
            n
            for n in zin.namelist()
            if n.startswith("ppt/slideMasters/slideMaster") and n.endswith(".xml")
        ]
        if not master_names:
            raise ValueError(f"no slide master found in {pptx_path}")

        master_overrides: dict[str, bytes] = {}
        for master_name in master_names:
            master_xml = zin.read(master_name)
            new_master_xml = _master_inject_footer(master_xml)
            master_overrides[master_name] = new_master_xml

        # Suppress the master footer on the cover slide (slide1) so the
        # cover stays clean. We do this by injecting a <p:hf> override on
        # the cover slide itself.
        cover_part = "ppt/slides/slide1.xml"
        slide_overrides: dict[str, bytes] = {}
        if cover_part in zin.namelist():
            cover_xml = zin.read(cover_part)
            new_cover = _slide_suppress_footer(cover_xml)
            if new_cover != cover_xml:
                slide_overrides[cover_part] = new_cover

        tmp_out = out_path.with_suffix(out_path.suffix + ".tmp")
        try:
            with zipfile.ZipFile(tmp_out, "w", zipfile.ZIP_DEFLATED) as zout:
                for info in zin.infolist():
                    name = info.filename
                    if name in master_overrides:
                        zout.writestr(info, master_overrides[name])
                    elif name in slide_overrides:
                        zout.writestr(info, slide_overrides[name])
                    else:
                        zout.writestr(info, zin.read(name))
            tmp_out.replace(out_path)
        finally:
            if tmp_out.exists():
                try:
                    tmp_out.unlink()
                except OSError:
                    pass

    return out_path


def polish_template(
    template_path: Path,
    style_xml_path: Path,
    section_dividers: list[SectionDivider],
    output_path: Path,
) -> PolishResult:
    """Run all three polish steps in sequence on ``template_path``.

    Order: embed style -> add section dividers -> add footer to master.
    Each step writes to a fresh tempfile; the final tempfile is moved to
    ``output_path``.

    Args:
        template_path: Source .pptx.
        style_xml_path: Path to the SimCorp think-cell style XML.
        section_dividers: Dividers to splice in (may be empty).
        output_path: Destination .pptx.

    Returns:
        :class:`PolishResult`.

    Raises:
        FileNotFoundError: if any input is missing.
        ValueError: on malformed style XML or invalid divider config.
        zipfile.BadZipFile: if ``template_path`` is not a valid .pptx.
    """
    template_path = template_path.expanduser().resolve()
    style_xml_path = style_xml_path.expanduser().resolve()
    output_path = output_path.expanduser().resolve()
    if not template_path.exists():
        raise FileNotFoundError(f"template not found: {template_path}")

    output_path.parent.mkdir(parents=True, exist_ok=True)

    original_slide_count = _count_slides(template_path)

    with tempfile.TemporaryDirectory(prefix="tcrender_polish_") as td:
        td_path = Path(td)
        step1 = td_path / "step1_style.pptx"
        step2 = td_path / "step2_dividers.pptx"

        embed_thinkcell_style(template_path, style_xml_path, step1)
        if section_dividers:
            add_section_dividers(step1, section_dividers, step2)
        else:
            shutil.copyfile(step1, step2)
        add_footer_to_master(step2, output_path)

    polished_slide_count = _count_slides(output_path)
    return PolishResult(
        output_path=output_path,
        style_embedded=True,
        section_dividers_added=len(section_dividers),
        footer_added=True,
        original_slide_count=original_slide_count,
        polished_slide_count=polished_slide_count,
    )


# -- internals: customXml + content-types + rels --------------------------


def _CT_CUSTOM_XML_PROPS_OR_XML(_part_name: str) -> str:
    # think-cell .style XML is plain XML, not a Microsoft customXmlProperties
    # document. The widely-deployed convention is to register the data
    # part as ``application/xml`` so consumers don't try to parse it as
    # Microsoft datastore content.
    return "application/xml"


def _next_custom_xml_item_index(names: set[str]) -> int:
    """Return the next free ``customXml/item<N>.xml`` index (>=1)."""
    used: set[int] = set()
    for n in names:
        m = re.match(r"^customXml/item(\d+)\.xml$", n)
        if m:
            used.add(int(m.group(1)))
    n = 1
    while n in used:
        n += 1
    return n


def _next_slide_part_index(names: list[str]) -> int:
    """Return the next free ``ppt/slides/slide<N>.xml`` index (>=1)."""
    used: set[int] = set()
    for n in names:
        m = re.match(r"^ppt/slides/slide(\d+)\.xml$", n)
        if m:
            used.add(int(m.group(1)))
    n = 1
    while n in used:
        n += 1
    return n


def _build_item_props_xml(item_idx: int) -> bytes:
    """Build the ``customXml/itemPropsN.xml`` payload (datastoreItem)."""
    # itemID is a fresh GUID; we don't actually need a true GUID -- any
    # 36-char hex-with-dashes is accepted. Keep it deterministic per
    # item_idx so repeated polishes produce identical output.
    item_id = f"{{TC-STYLE-{item_idx:04d}-{'0' * 4}-{'0' * 4}-{'0' * 12}}}"
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="no"?>'
        f'<ds:datastoreItem ds:itemID="{item_id}" '
        f'xmlns:ds="{_NS_DS}">'
        "<ds:schemaRefs>"
        f'<ds:schemaRef ds:uri="https://schemas.think-cell.com/36264/tcstyle"/>'
        "</ds:schemaRefs>"
        "</ds:datastoreItem>"
    ).encode("utf-8")


def _build_item_rels_xml(item_idx: int) -> bytes:
    """Build ``customXml/_rels/itemN.xml.rels`` -> itemPropsN.xml."""
    return (
        "<?xml version='1.0' encoding='UTF-8' standalone='yes'?>"
        f'<Relationships xmlns="{_NS_RELS_PKG}">'
        '<Relationship Id="rId1" '
        f'Type="{_NS_RELS_OD}/customXmlProps" '
        f'Target="itemProps{item_idx}.xml"/>'
        "</Relationships>"
    ).encode("utf-8")


def _content_types_add_overrides(
    content_types_xml: bytes,
    overrides: list[tuple[str, str]],
) -> bytes:
    """Append Override children to ``[Content_Types].xml``."""
    root = etree.fromstring(content_types_xml)
    existing_parts = {o.get("PartName") for o in root.iter(f"{{{_NS_CONTENT_TYPES}}}Override")}
    for part_name, ct in overrides:
        if part_name in existing_parts:
            continue
        etree.SubElement(
            root,
            f"{{{_NS_CONTENT_TYPES}}}Override",
            attrib={"PartName": part_name, "ContentType": ct},
        )
    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)


def _presentation_rels_add(
    pres_rels_xml: bytes,
    target: str,
    rel_type: str,
) -> tuple[bytes, str]:
    """Append a new ``<Relationship>`` to ``ppt/_rels/presentation.xml.rels``.

    Returns ``(new_xml_bytes, allocated_relId)``.
    """
    root = etree.fromstring(pres_rels_xml)
    used: set[int] = set()
    for r in root.iter(f"{{{_NS_RELS_PKG}}}Relationship"):
        rid = r.get("Id") or ""
        m = re.match(r"^rId(\d+)$", rid)
        if m:
            used.add(int(m.group(1)))
    n = 1
    while n in used:
        n += 1
    rel_id = f"rId{n}"
    etree.SubElement(
        root,
        f"{{{_NS_RELS_PKG}}}Relationship",
        attrib={"Id": rel_id, "Type": rel_type, "Target": target},
    )
    return (
        etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True),
        rel_id,
    )


# -- internals: presentation.xml / sldIdLst -------------------------------


def _presentation_insert_slide_ids(
    presentation_xml: bytes,
    new_slide_meta: list[tuple[str, int]],
) -> bytes:
    """Insert new ``<p:sldId>`` entries into the sldIdLst.

    ``new_slide_meta`` is a list of ``(relId, insert_before_original_index)``
    tuples in the order the dividers were declared. Insertions are
    relative to the ORIGINAL deck slide order; we track positional
    offsets as we splice each one so multiple inserts at the same
    original index land adjacent in declaration order.
    """
    root = etree.fromstring(presentation_xml)
    sld_id_lst = root.find(f"{{{_NS_PRESENT}}}sldIdLst")
    if sld_id_lst is None:
        return presentation_xml

    # Existing ids -- compute next free p:sldId/@id starting at 256.
    used_ids: set[int] = set()
    for s in sld_id_lst.findall(f"{{{_NS_PRESENT}}}sldId"):
        try:
            used_ids.add(int(s.get("id") or "0"))
        except ValueError:
            continue
    next_id = 256
    while next_id in used_ids:
        next_id += 1

    original_count = len(sld_id_lst)
    # Pair each new entry with a stable allocated sldId, plus an
    # adjusted insertion position that increments every time we splice.
    splices: list[tuple[int, str, int]] = []  # (effective_pos, relId, sldId)
    pos_offset = 0
    for rel_id, requested_idx in new_slide_meta:
        clamped = max(0, min(requested_idx, original_count))
        effective = clamped + pos_offset
        splices.append((effective, rel_id, next_id))
        next_id += 1
        while next_id in used_ids:
            next_id += 1
        pos_offset += 1

    # Insert in increasing effective_pos order so list indices stay
    # correct as we go.
    splices.sort(key=lambda t: t[0])
    for effective, rel_id, sld_id in splices:
        new_node = etree.Element(
            f"{{{_NS_PRESENT}}}sldId",
            attrib={"id": str(sld_id), f"{{{_NS_RELS_OD}}}id": rel_id},
        )
        if effective >= len(sld_id_lst):
            sld_id_lst.append(new_node)
        else:
            sld_id_lst.insert(effective, new_node)

    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)


def _build_slide_rels_xml(layout_target: str) -> bytes:
    """Build a slide rels XML pointing to the named slideLayout target."""
    return (
        "<?xml version='1.0' encoding='UTF-8' standalone='yes'?>"
        f'<Relationships xmlns="{_NS_RELS_PKG}">'
        '<Relationship Id="rId1" '
        f'Type="{_REL_SLIDE_LAYOUT}" '
        f'Target="{layout_target}"/>'
        "</Relationships>"
    ).encode("utf-8")


# -- internals: section divider slide XML ---------------------------------


def _build_section_divider_xml(d: SectionDivider) -> bytes:
    """Build the slide XML for a single section divider.

    Layout:
        * Full-bleed navy rectangle background (id=2).
        * Roman numeral text box, centered horizontally,
          ~22% from top, coral, 28pt (id=3).
        * Title text box, centered horizontally,
          ~38% from top, white, 60pt (id=4).
        * Optional subtitle (id=5), white, 24pt, only when
          ``d.subtitle`` is non-empty.
        * Bottom-left director/period mark (id=6),
          uses ``{director_name}`` and ``{period}`` placeholders.
    """
    # Geometry in EMU. 12192000 wide, 6858000 tall.
    bg_x, bg_y, bg_w, bg_h = 0, 0, _SLIDE_W, _SLIDE_H
    roman_w = 4000000
    roman_h = 600000
    roman_x = (_SLIDE_W - roman_w) // 2
    roman_y = int(_SLIDE_H * 0.20)

    title_w = int(_SLIDE_W * 0.85)
    title_h = 1100000
    title_x = (_SLIDE_W - title_w) // 2
    title_y = int(_SLIDE_H * 0.32)

    subtitle_w = int(_SLIDE_W * 0.65)
    subtitle_h = 500000
    subtitle_x = (_SLIDE_W - subtitle_w) // 2
    subtitle_y = title_y + title_h + 150000

    mark_x = 380000
    mark_y = _SLIDE_H - 500000
    mark_w = 6000000
    mark_h = 300000

    title_xml = _xml_escape(d.title)
    roman_xml = _xml_escape(d.roman)
    subtitle_xml = _xml_escape(d.subtitle)

    subtitle_block = ""
    if d.subtitle.strip():
        subtitle_block = (
            "<p:sp>"
            "<p:nvSpPr>"
            '<p:cNvPr id="5" name="SectionDividerSubtitle"/>'
            '<p:cNvSpPr txBox="1"/><p:nvPr/>'
            "</p:nvSpPr>"
            "<p:spPr>"
            f'<a:xfrm><a:off x="{subtitle_x}" y="{subtitle_y}"/>'
            f'<a:ext cx="{subtitle_w}" cy="{subtitle_h}"/></a:xfrm>'
            '<a:prstGeom prst="rect"><a:avLst/></a:prstGeom>'
            "<a:noFill/><a:ln><a:noFill/></a:ln>"
            "</p:spPr>"
            "<p:txBody>"
            '<a:bodyPr wrap="square" anchor="ctr"/><a:lstStyle/>'
            '<a:p><a:pPr algn="ctr"/>'
            '<a:r><a:rPr lang="en-US" sz="2400">'
            '<a:solidFill><a:srgbClr val="FFFFFF"/></a:solidFill>'
            '<a:latin typeface="Microsoft Sans Serif"/>'
            "</a:rPr>"
            f"<a:t>{subtitle_xml}</a:t>"
            "</a:r></a:p>"
            "</p:txBody>"
            "</p:sp>"
        )

    return (
        "<?xml version='1.0' encoding='UTF-8' standalone='yes'?>"
        '<p:sld xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
        'xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        # Suppress master-footer on this slide.
        '<p:cSld><p:hf sldNum="0" ftr="0" hdr="0" dt="0"/>'
        "<p:spTree>"
        "<p:nvGrpSpPr>"
        '<p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/>'
        "</p:nvGrpSpPr>"
        "<p:grpSpPr/>"
        # Background
        "<p:sp>"
        "<p:nvSpPr>"
        '<p:cNvPr id="2" name="SectionDividerBackground"/>'
        "<p:cNvSpPr/><p:nvPr/>"
        "</p:nvSpPr>"
        "<p:spPr>"
        f'<a:xfrm><a:off x="{bg_x}" y="{bg_y}"/>'
        f'<a:ext cx="{bg_w}" cy="{bg_h}"/></a:xfrm>'
        '<a:prstGeom prst="rect"><a:avLst/></a:prstGeom>'
        f'<a:solidFill><a:srgbClr val="{SIMCORP_NAVY_HEX}"/></a:solidFill>'
        "<a:ln><a:noFill/></a:ln>"
        "</p:spPr>"
        "<p:txBody>"
        "<a:bodyPr/><a:lstStyle/><a:p/>"
        "</p:txBody>"
        "</p:sp>"
        # Roman numeral
        "<p:sp>"
        "<p:nvSpPr>"
        '<p:cNvPr id="3" name="SectionDividerRoman"/>'
        '<p:cNvSpPr txBox="1"/><p:nvPr/>'
        "</p:nvSpPr>"
        "<p:spPr>"
        f'<a:xfrm><a:off x="{roman_x}" y="{roman_y}"/>'
        f'<a:ext cx="{roman_w}" cy="{roman_h}"/></a:xfrm>'
        '<a:prstGeom prst="rect"><a:avLst/></a:prstGeom>'
        "<a:noFill/><a:ln><a:noFill/></a:ln>"
        "</p:spPr>"
        "<p:txBody>"
        '<a:bodyPr wrap="square" anchor="ctr"/><a:lstStyle/>'
        '<a:p><a:pPr algn="ctr"/>'
        '<a:r><a:rPr lang="en-US" sz="2800" b="1">'
        f'<a:solidFill><a:srgbClr val="{SIMCORP_CORAL_HEX}"/></a:solidFill>'
        '<a:latin typeface="Microsoft Sans Serif"/>'
        "</a:rPr>"
        f"<a:t>{roman_xml}</a:t>"
        "</a:r></a:p>"
        "</p:txBody>"
        "</p:sp>"
        # Title
        "<p:sp>"
        "<p:nvSpPr>"
        '<p:cNvPr id="4" name="SectionDividerTitle"/>'
        '<p:cNvSpPr txBox="1"/><p:nvPr/>'
        "</p:nvSpPr>"
        "<p:spPr>"
        f'<a:xfrm><a:off x="{title_x}" y="{title_y}"/>'
        f'<a:ext cx="{title_w}" cy="{title_h}"/></a:xfrm>'
        '<a:prstGeom prst="rect"><a:avLst/></a:prstGeom>'
        "<a:noFill/><a:ln><a:noFill/></a:ln>"
        "</p:spPr>"
        "<p:txBody>"
        '<a:bodyPr wrap="square" anchor="ctr"/><a:lstStyle/>'
        '<a:p><a:pPr algn="ctr"/>'
        '<a:r><a:rPr lang="en-US" sz="6000" b="1">'
        '<a:solidFill><a:srgbClr val="FFFFFF"/></a:solidFill>'
        '<a:latin typeface="Microsoft Sans Serif"/>'
        "</a:rPr>"
        f"<a:t>{title_xml}</a:t>"
        "</a:r></a:p>"
        "</p:txBody>"
        "</p:sp>"
        f"{subtitle_block}"
        # Bottom-left mark with director/period jinja placeholders
        "<p:sp>"
        "<p:nvSpPr>"
        '<p:cNvPr id="6" name="SectionDividerMark"/>'
        '<p:cNvSpPr txBox="1"/><p:nvPr/>'
        "</p:nvSpPr>"
        "<p:spPr>"
        f'<a:xfrm><a:off x="{mark_x}" y="{mark_y}"/>'
        f'<a:ext cx="{mark_w}" cy="{mark_h}"/></a:xfrm>'
        '<a:prstGeom prst="rect"><a:avLst/></a:prstGeom>'
        "<a:noFill/><a:ln><a:noFill/></a:ln>"
        "</p:spPr>"
        "<p:txBody>"
        '<a:bodyPr wrap="square" anchor="ctr"/><a:lstStyle/>'
        '<a:p><a:pPr algn="l"/>'
        '<a:r><a:rPr lang="en-US" sz="1200">'
        '<a:solidFill><a:srgbClr val="FFFFFF"/></a:solidFill>'
        '<a:latin typeface="Microsoft Sans Serif"/>'
        "</a:rPr>"
        "<a:t>{director_name} | {period}</a:t>"
        "</a:r></a:p>"
        "</p:txBody>"
        "</p:sp>"
        "</p:spTree>"
        "</p:cSld>"
        "<p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr>"
        "</p:sld>"
    ).encode("utf-8")


# -- internals: master footer -------------------------------------------


def _master_inject_footer(master_xml: bytes) -> bytes:
    """Append a footer band (line + text) to the master spTree."""
    # Parse, find spTree, append shapes. lxml preserves namespaces.
    root = etree.fromstring(master_xml)
    sptree = root.find(f"{{{_NS_PRESENT}}}cSld/{{{_NS_PRESENT}}}spTree")
    if sptree is None:
        return master_xml

    # Don't double-inject. Look for our marker name.
    for cnvpr in sptree.iter(f"{{{_NS_PRESENT}}}cNvPr"):
        if (cnvpr.get("name") or "") == "PolishMasterFooter":
            return master_xml

    # Compute next free shape id within spTree.
    used: set[int] = set()
    for cnvpr in sptree.iter(f"{{{_NS_PRESENT}}}cNvPr"):
        try:
            used.add(int(cnvpr.get("id") or "0"))
        except ValueError:
            continue
    next_id = 1
    while next_id in used:
        next_id += 1
    line_id = next_id
    text_id = next_id + 1

    line_y = _SLIDE_H - _FOOTER_BOTTOM_OFFSET - _FOOTER_HEIGHT - 30000
    line_x = _FOOTER_LEFT_PAD
    line_w = _SLIDE_W - _FOOTER_LEFT_PAD - _FOOTER_RIGHT_PAD
    text_y = _SLIDE_H - _FOOTER_BOTTOM_OFFSET - _FOOTER_HEIGHT
    text_x = _FOOTER_LEFT_PAD
    text_w = _SLIDE_W - _FOOTER_LEFT_PAD - _FOOTER_RIGHT_PAD

    # Build a connector line shape (cxnSp) and a text shape (sp).
    fragment = (
        # Separator line
        "<p:cxnSp>"
        "<p:nvCxnSpPr>"
        f'<p:cNvPr id="{line_id}" name="PolishMasterFooterLine"/>'
        '<p:cNvCxnSpPr/><p:nvPr userDrawn="1"/>'
        "</p:nvCxnSpPr>"
        "<p:spPr>"
        f'<a:xfrm><a:off x="{line_x}" y="{line_y}"/>'
        f'<a:ext cx="{line_w}" cy="0"/></a:xfrm>'
        '<a:prstGeom prst="line"><a:avLst/></a:prstGeom>'
        f'<a:ln w="{_FOOTER_LINE_THICKNESS}">'
        '<a:solidFill><a:schemeClr val="accent1"/></a:solidFill>'
        "</a:ln>"
        "</p:spPr>"
        "</p:cxnSp>"
        # Footer text
        "<p:sp>"
        "<p:nvSpPr>"
        f'<p:cNvPr id="{text_id}" name="PolishMasterFooter"/>'
        '<p:cNvSpPr txBox="1"/><p:nvPr userDrawn="1"/>'
        "</p:nvSpPr>"
        "<p:spPr>"
        f'<a:xfrm><a:off x="{text_x}" y="{text_y}"/>'
        f'<a:ext cx="{text_w}" cy="{_FOOTER_HEIGHT}"/></a:xfrm>'
        '<a:prstGeom prst="rect"><a:avLst/></a:prstGeom>'
        "<a:noFill/><a:ln><a:noFill/></a:ln>"
        "</p:spPr>"
        "<p:txBody>"
        '<a:bodyPr wrap="square" anchor="ctr" lIns="0" tIns="0" rIns="0" bIns="0"/>'
        "<a:lstStyle/>"
        '<a:p><a:pPr algn="r"/>'
        '<a:r><a:rPr lang="en-US" sz="900">'
        f'<a:solidFill><a:srgbClr val="{SIMCORP_FOOTER_GREY_HEX}"/></a:solidFill>'
        '<a:latin typeface="Microsoft Sans Serif"/>'
        "</a:rPr>"
        "<a:t>{director_name} | {period} | </a:t>"
        "</a:r>"
        f'<a:fld id="{{B0F4D8E4-1111-4444-9999-1234567890{text_id:02d}}}" type="slidenum">'
        '<a:rPr lang="en-US" sz="900">'
        f'<a:solidFill><a:srgbClr val="{SIMCORP_FOOTER_GREY_HEX}"/></a:solidFill>'
        '<a:latin typeface="Microsoft Sans Serif"/>'
        "</a:rPr>"
        "<a:t>#</a:t>"
        "</a:fld>"
        '<a:r><a:rPr lang="en-US" sz="900">'
        f'<a:solidFill><a:srgbClr val="{SIMCORP_FOOTER_GREY_HEX}"/></a:solidFill>'
        '<a:latin typeface="Microsoft Sans Serif"/>'
        "</a:rPr>"
        "<a:t>/</a:t>"
        "</a:r>"
        f'<a:fld id="{{B0F4D8E4-2222-4444-9999-1234567890{text_id:02d}}}" type="slidecount">'
        '<a:rPr lang="en-US" sz="900">'
        f'<a:solidFill><a:srgbClr val="{SIMCORP_FOOTER_GREY_HEX}"/></a:solidFill>'
        '<a:latin typeface="Microsoft Sans Serif"/>'
        "</a:rPr>"
        "<a:t>#</a:t>"
        "</a:fld>"
        "</a:p>"
        "</p:txBody>"
        "</p:sp>"
    )

    new_nodes = etree.fromstring(
        f'<root xmlns:a="{_NS_DRAWING}" xmlns:p="{_NS_PRESENT}" '
        f'xmlns:r="{_NS_RELS_OD}">{fragment}</root>'
    )
    for child in list(new_nodes):
        sptree.append(copy.deepcopy(child))

    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)


def _slide_suppress_footer(slide_xml: bytes) -> bytes:
    """Insert a ``<p:hf>`` opt-out child into a slide's ``<p:cSld>``.

    If the slide already has ``<p:hf>``, leaves it alone.
    """
    root = etree.fromstring(slide_xml)
    csld = root.find(f"{{{_NS_PRESENT}}}cSld")
    if csld is None:
        return slide_xml
    existing_hf = csld.find(f"{{{_NS_PRESENT}}}hf")
    if existing_hf is not None:
        return slide_xml
    hf = etree.Element(
        f"{{{_NS_PRESENT}}}hf",
        attrib={"sldNum": "0", "ftr": "0", "hdr": "0", "dt": "0"},
    )
    # <p:hf> is the first child of <p:cSld> per schema.
    csld.insert(0, hf)
    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)


# -- misc helpers ---------------------------------------------------------


def _count_slides(pptx_path: Path) -> int:
    """Count ``ppt/slides/slide<N>.xml`` parts."""
    with zipfile.ZipFile(pptx_path, "r") as zf:
        return sum(1 for n in zf.namelist() if re.match(r"^ppt/slides/slide\d+\.xml$", n))


def _xml_escape(s: str) -> str:
    """Escape ``&``, ``<``, ``>`` for safe inclusion in XML text."""
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


__all__ = [
    "PolishResult",
    "SectionDivider",
    "SIMCORP_CORAL_HEX",
    "SIMCORP_FOOTER_GREY_HEX",
    "SIMCORP_NAVY_HEX",
    "add_footer_to_master",
    "add_section_dividers",
    "embed_thinkcell_style",
    "polish_template",
]


# Avoid F401 on time/tempfile -- both are used in polish_template.
_ = time
