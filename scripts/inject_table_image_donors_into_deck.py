#!/usr/bin/env python3
"""Inject real think-cell Table-as-Image donors into a generated LAND deck.

PowerPoint COM copy/paste does not preserve these table-image elements in a
form that Excel's think-cell `AddRangeImage` accepts. This script performs the
same operation at the OpenXML package layer: it removes the native table shapes
and off-slide table-field stubs, copies the real donor picture/data shapes plus
their relationships, and positions the visible picture over the old table area.
"""

from __future__ import annotations

import argparse
import copy
import uuid
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from ppttc_template import (
    A_NS,
    P_NS,
    R_NS,
    _PartCopier,
    _max_shape_id,
    _patch_cfb_stream,
    _relationship_map,
    _rels_part_name,
    _rewrite_relationships,
    _resolve_target,
    _set_shape_id,
    _shape_name,
    template_named_elements,
)


ROOT = Path(__file__).resolve().parent.parent
MC_NS = "http://schemas.openxmlformats.org/markup-compatibility/2006"
VML_NS = "urn:schemas-microsoft-com:vml"
P14_NS = "http://schemas.microsoft.com/office/powerpoint/2010/main"
A14_NS = "http://schemas.microsoft.com/office/drawing/2010/main"
A16_NS = "http://schemas.microsoft.com/office/drawing/2014/main"

ET.register_namespace("", P_NS)
ET.register_namespace("a", A_NS)
ET.register_namespace("r", R_NS)
ET.register_namespace("mc", MC_NS)
ET.register_namespace("p14", P14_NS)
ET.register_namespace("a14", A14_NS)
ET.register_namespace("a16", A16_NS)
DEFAULT_INPUT = ROOT / "state" / "2026-Q2" / "Jesper-Tyrer" / "Jesper-Tyrer-LAND-2026-Q2.pptx"
DEFAULT_OUTPUT = (
    ROOT
    / "state"
    / "2026-Q2"
    / "Jesper-Tyrer"
    / "Jesper-Tyrer-LAND-2026-Q2-table-image-seeded.pptx"
)
DEFAULT_DONOR_DIR = ROOT / "state" / "thinkcell_bridge" / "table_image_donors"


@dataclass(frozen=True)
class Bounds:
    left: int
    top: int
    width: int
    height: int


@dataclass(frozen=True)
class RemovedTableInfo:
    bounds: Bounds
    count: int
    insert_index: int


@dataclass(frozen=True)
class TableImageTarget:
    slide_number: int
    name: str
    table_match_text: str | None = None
    top_adjust_pt: float = 0.0
    bottom_adjust_pt: float = 0.0
    patch_ole_geometry: bool = False


TARGETS: tuple[TableImageTarget, ...] = (
    TableImageTarget(4, "S04_ReviewDeltaTargets", "Original target"),
    TableImageTarget(5, "S05_ForecastQualityTable"),
    TableImageTarget(6, "S06_HygieneSignals"),
    TableImageTarget(
        7,
        "S07_TopDealsLand",
        patch_ole_geometry=True,
    ),
    TableImageTarget(8, "S08_TopDealsExpand"),
    TableImageTarget(9, "S09_PendingCommercialApproval"),
    TableImageTarget(11, "S11_RenewalPipeline"),
    TableImageTarget(12, "S12_GRRProxyTable"),
    TableImageTarget(13, "S13_ForecastCategoryDetail"),
    TableImageTarget(16, "S16_OwnerCoaching"),
    TableImageTarget(18, "S18_QTDLossSpine"),
    TableImageTarget(19, "S19_DealHygieneSignals"),
    TableImageTarget(21, "S21_ConcentrationTable"),
    TableImageTarget(22, "S22_NamedRiskTriage"),
    TableImageTarget(23, "S23_OperatingRhythm"),
    TableImageTarget(24, "S24_AccountExpansion"),
    TableImageTarget(25, "S25_Next14DaysCadence"),
    TableImageTarget(26, "S26_ActionItems"),
    TableImageTarget(27, "S27_DecisionChecklist"),
)


def _load_package(path: Path) -> dict[str, bytes]:
    with ZipFile(path) as zf:
        return {item.filename: zf.read(item.filename) for item in zf.infolist()}


def _write_package(entries: dict[str, bytes], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    tmp = output.with_suffix(".tmp.pptx")
    with ZipFile(tmp, "w", ZIP_DEFLATED) as zf:
        for name, data in entries.items():
            zf.writestr(name, data)
    tmp.replace(output)


def _slide_xml(root: ET.Element) -> bytes:
    text = ET.tostring(root, encoding="unicode", xml_declaration=True)
    if 'Requires="v"' in text and "xmlns:v=" not in text:
        text = text.replace("<sld ", f'<sld xmlns:v="{VML_NS}" ', 1)
        text = text.replace("<p:sld ", f'<p:sld xmlns:v="{VML_NS}" ', 1)
    return text.encode("utf-8")


def _native_table_bounds_and_remove(
    sp_tree: ET.Element,
    *,
    match_text: str | None = None,
) -> RemovedTableInfo | None:
    left: int | None = None
    top: int | None = None
    right: int | None = None
    bottom: int | None = None
    removed = 0
    insert_index: int | None = None

    for index, child in enumerate(list(sp_tree)):
        if child.find(f".//{{{A_NS}}}tbl") is None:
            continue
        if match_text and match_text not in _all_text(child):
            continue
        bounds = _shape_bounds(child)
        if bounds is None:
            continue
        if insert_index is None:
            insert_index = index
        left = bounds.left if left is None else min(left, bounds.left)
        top = bounds.top if top is None else min(top, bounds.top)
        right_edge = bounds.left + bounds.width
        bottom_edge = bounds.top + bounds.height
        right = right_edge if right is None else max(right, right_edge)
        bottom = bottom_edge if bottom is None else max(bottom, bottom_edge)
        sp_tree.remove(child)
        removed += 1

    if (
        left is None
        or top is None
        or right is None
        or bottom is None
        or insert_index is None
    ):
        return None
    return RemovedTableInfo(
        bounds=Bounds(left, top, right - left, bottom - top),
        count=removed,
        insert_index=insert_index,
    )


def _remove_existing_table_names(sp_tree: ET.Element, target_name: str) -> int:
    removed = 0
    for child in list(sp_tree):
        if target_name not in _all_text(child):
            continue
        sp_tree.remove(child)
        removed += 1
    return removed


def _all_text(element: ET.Element) -> str:
    chunks: list[str] = []
    for node in element.iter():
        if node.text:
            chunks.append(node.text)
        if node.tail:
            chunks.append(node.tail)
        chunks.extend(node.attrib.values())
    return "\n".join(chunks)


def _shape_bounds(element: ET.Element) -> Bounds | None:
    xfrm = element.find(f"./{{{P_NS}}}xfrm")
    if xfrm is None:
        xfrm = element.find(f".//{{{A_NS}}}xfrm")
    if xfrm is None:
        return None
    off = xfrm.find(f"{{{A_NS}}}off")
    ext = xfrm.find(f"{{{A_NS}}}ext")
    if off is None or ext is None:
        return None
    return Bounds(
        int(off.get("x", "0")),
        int(off.get("y", "0")),
        int(ext.get("cx", "0")),
        int(ext.get("cy", "0")),
    )


def _set_shape_bounds(element: ET.Element, bounds: Bounds) -> None:
    xfrms = list(element.findall(f".//{{{P_NS}}}xfrm"))
    xfrms.extend(element.findall(f".//{{{A_NS}}}xfrm"))
    if not xfrms:
        raise RuntimeError(f"donor shape {_shape_name(element)!r} is missing xfrm")
    for xfrm in xfrms:
        off = xfrm.find(f"{{{A_NS}}}off")
        ext = xfrm.find(f"{{{A_NS}}}ext")
        if off is None or ext is None:
            continue
        off.set("x", str(bounds.left))
        off.set("y", str(bounds.top))
        ext.set("cx", str(bounds.width))
        ext.set("cy", str(bounds.height))


def _render_bounds(target: TableImageTarget, bounds: Bounds) -> Bounds:
    if not target.top_adjust_pt and not target.bottom_adjust_pt:
        return bounds
    top_delta = round(target.top_adjust_pt * 12700)
    bottom_delta = round(target.bottom_adjust_pt * 12700)
    return Bounds(
        bounds.left,
        bounds.top + top_delta,
        bounds.width,
        bounds.height + bottom_delta - top_delta,
    )


def _tc_units(value_emu: int) -> int:
    return round((value_emu / 12700) * 8)


def _tc_float(value: int) -> str:
    return f"{float(value):.20E}"


def _patch_table_image_ole_geometry(
    *,
    target_entries: dict[str, bytes],
    slide_name: str,
    target_rels_root: ET.Element,
    shape: ET.Element,
    bounds: Bounds,
) -> None:
    ole = shape.find(f".//{{{P_NS}}}oleObj")
    if ole is None:
        return
    rid = ole.get(f"{{{R_NS}}}id")
    if not rid:
        return
    rel = _relationship_map(target_rels_root).get(rid)
    if rel is None or rel.get("TargetMode") == "External":
        return
    ole_part_name = _resolve_target(slide_name, rel.get("Target", ""))
    if not ole_part_name or not ole_part_name.endswith(".bin"):
        return
    left = _tc_units(bounds.left)
    top = _tc_units(bounds.top)
    right = _tc_units(bounds.left + bounds.width)
    bottom = _tc_units(bounds.top + bounds.height)
    replacements = {
        rb"<m_rectPPTShape[^>]*/>": (
            f'<m_rectPPTShape left="{left}" top="{top}" right="{right}" bottom="{bottom}"/>'
        ).encode("utf-8"),
        rb"<m_rectnFeature[^>]*/>": (
            f'<m_rectnFeature left="{_tc_float(left)}" top="{_tc_float(top)}" '
            f'right="{_tc_float(right)}" bottom="{_tc_float(bottom)}"/>'
        ).encode("utf-8"),
        rb'(<CGridline id="13">.*?<m_gvValue val=")[^"]+(".*?</CGridline>)': (
            rb"\g<1>" + _tc_float(bottom).encode("utf-8") + rb"\g<2>"
        ),
        rb'(<CGridline id="14">.*?<m_gvValue val=")[^"]+(".*?</CGridline>)': (
            rb"\g<1>" + _tc_float(right).encode("utf-8") + rb"\g<2>"
        ),
        rb'(<CGridline id="15">.*?<m_gvValue val=")[^"]+(".*?</CGridline>)': (
            rb"\g<1>" + _tc_float(top).encode("utf-8") + rb"\g<2>"
        ),
        rb'(<CGridline id="16">.*?<m_gvValue val=")[^"]+(".*?</CGridline>)': (
            rb"\g<1>" + _tc_float(left).encode("utf-8") + rb"\g<2>"
        ),
    }
    target_entries[ole_part_name] = _patch_cfb_stream(
        target_entries[ole_part_name],
        "think-cellXML",
        replacements,
        regex=True,
    )


def _refresh_office_ids(element: ET.Element) -> None:
    for node in element.iter():
        if node.tag == f"{{{A16_NS}}}creationId" and "id" in node.attrib:
            node.set("id", f"{{{str(uuid.uuid4()).upper()}}}")
        if node.tag == f"{{{P14_NS}}}modId" and "val" in node.attrib:
            node.set("val", str(uuid.uuid4().int % 4_000_000_000))
        if node.tag == f"{{{P14_NS}}}creationId" and "val" in node.attrib:
            node.set("val", str(uuid.uuid4().int % 4_000_000_000))


def _copy_slide_creation_id(target_slide_root: ET.Element, donor_slide_root: ET.Element) -> None:
    target_csld = target_slide_root.find(f"{{{P_NS}}}cSld")
    donor_csld = donor_slide_root.find(f"{{{P_NS}}}cSld")
    if target_csld is None or donor_csld is None:
        return
    if target_csld.find(f"{{{P_NS}}}extLst") is not None:
        return
    donor_ext_lst = donor_csld.find(f"{{{P_NS}}}extLst")
    if donor_ext_lst is None:
        return
    cloned = copy.deepcopy(donor_ext_lst)
    _refresh_office_ids(cloned)
    target_csld.append(cloned)


def _inject_one(
    *,
    target_entries: dict[str, bytes],
    ct_root: ET.Element,
    donor_dir: Path,
    target: TableImageTarget,
) -> str:
    slide_name = f"ppt/slides/slide{target.slide_number}.xml"
    rels_name = _rels_part_name(slide_name)
    donor_path = donor_dir / f"{target.name}.pptx"
    if not donor_path.exists():
        raise RuntimeError(f"missing donor: {donor_path}")

    target_slide_root = ET.fromstring(target_entries[slide_name])
    target_rels_root = ET.fromstring(target_entries[rels_name])
    target_sp_tree = target_slide_root.find(f".//{{{P_NS}}}spTree")
    if target_sp_tree is None:
        raise RuntimeError(f"{slide_name} is missing spTree")

    removed_info = _native_table_bounds_and_remove(
        target_sp_tree,
        match_text=target.table_match_text,
    )
    removed_stubs = _remove_existing_table_names(target_sp_tree, target.name)
    if removed_info is None:
        raise RuntimeError(f"no native table bounds found on slide {target.slide_number}")
    bounds = _render_bounds(target, removed_info.bounds)

    with ZipFile(donor_path) as donor_zip:
        donor_ct_root = ET.fromstring(donor_zip.read("[Content_Types].xml"))
        donor_slide_name = "ppt/slides/slide1.xml"
        donor_rels_name = _rels_part_name(donor_slide_name)
        donor_slide_root = ET.fromstring(donor_zip.read(donor_slide_name))
        donor_rels_root = ET.fromstring(donor_zip.read(donor_rels_name))
        donor_rel_map = _relationship_map(donor_rels_root)
        donor_sp_tree = donor_slide_root.find(f".//{{{P_NS}}}spTree")
        if donor_sp_tree is None:
            raise RuntimeError(f"{donor_path} slide1 is missing spTree")
        _copy_slide_creation_id(target_slide_root, donor_slide_root)

        donor_shapes = [
            copy.deepcopy(child)
            for child in list(donor_sp_tree)
            if _shape_name(child) in {"think-cell data - do not delete", "Pic"}
        ]
        if len(donor_shapes) != 2:
            raise RuntimeError(f"{donor_path} did not expose the expected two donor shapes")

        copier = _PartCopier(
            target_entries=target_entries,
            ct_root=ct_root,
            donor_zip=donor_zip,
            donor_ct_root=donor_ct_root,
            chart_name=target.name,
        )
        next_shape_id = _max_shape_id(target_sp_tree) + 1
        insert_index = min(removed_info.insert_index, len(list(target_sp_tree)))
        for shape in donor_shapes:
            _refresh_office_ids(shape)
            _rewrite_relationships(
                shape,
                donor_slide_name=donor_slide_name,
                target_slide_name=slide_name,
                target_rels_root=target_rels_root,
                donor_rel_map=donor_rel_map,
                copier=copier,
            )
            _set_shape_id(shape, next_shape_id)
            next_shape_id += 1
            if _shape_name(shape) in {"think-cell data - do not delete", "Pic"}:
                _set_shape_bounds(shape, bounds)
            if _shape_name(shape) == "think-cell data - do not delete" and target.patch_ole_geometry:
                _patch_table_image_ole_geometry(
                    target_entries=target_entries,
                    slide_name=slide_name,
                    target_rels_root=target_rels_root,
                    shape=shape,
                    bounds=bounds,
                )
            target_sp_tree.insert(insert_index, shape)
            insert_index += 1

    target_entries[slide_name] = _slide_xml(target_slide_root)
    target_entries[rels_name] = ET.tostring(
        target_rels_root, encoding="utf-8", xml_declaration=True
    )
    return (
        f"{target.name}: slide={target.slide_number} "
        f"tables_removed={removed_info.count} stubs_removed={removed_stubs} "
        f"bounds={bounds.left},{bounds.top},{bounds.width},{bounds.height}"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--donor-dir", type=Path, default=DEFAULT_DONOR_DIR)
    parser.add_argument(
        "--skip-missing-targets",
        action="store_true",
        help="Skip table-image targets where the deck has no native table to replace.",
    )
    parser.add_argument(
        "--only-name",
        action="append",
        default=[],
        help="Inject only this named table-image target. May be supplied multiple times.",
    )
    args = parser.parse_args()

    if not args.input.exists():
        raise SystemExit(f"missing input deck: {args.input}")
    if not args.donor_dir.exists():
        raise SystemExit(f"missing donor dir: {args.donor_dir}")

    target_entries = _load_package(args.input)
    ct_root = ET.fromstring(target_entries["[Content_Types].xml"])
    summaries: list[str] = []
    skipped: list[str] = []
    skipped_names: set[str] = set()
    selected_names = set(args.only_name)
    if selected_names:
        known_names = {target.name for target in TARGETS}
        unknown_names = sorted(selected_names - known_names)
        if unknown_names:
            raise SystemExit(f"unknown target name(s): {', '.join(unknown_names)}")
    selected_targets = [
        target for target in TARGETS if not selected_names or target.name in selected_names
    ]
    for target in selected_targets:
        try:
            summaries.append(
                _inject_one(
                    target_entries=target_entries,
                    ct_root=ct_root,
                    donor_dir=args.donor_dir,
                    target=target,
                )
            )
        except RuntimeError as exc:
            if not args.skip_missing_targets or "no native table bounds found" not in str(exc):
                raise
            skipped.append(f"{target.name}: slide={target.slide_number} skipped_no_native_table")
            skipped_names.add(target.name)
    target_entries["[Content_Types].xml"] = ET.tostring(
        ct_root, encoding="utf-8", xml_declaration=True
    )
    _write_package(target_entries, args.output)

    names = template_named_elements(args.output)
    missing = [
        target.name
        for target in selected_targets
        if target.name not in names and target.name not in skipped_names
    ]
    if missing:
        raise SystemExit(f"seeded deck is missing names: {', '.join(missing)}")

    print(args.output)
    for summary in summaries:
        print(summary)
    for summary in skipped:
        print(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
