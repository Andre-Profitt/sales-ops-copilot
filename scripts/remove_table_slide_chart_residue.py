#!/usr/bin/env python3
"""Remove loose chart residue from table-first Sales Director slides.

The think-cell/PowerPoint bridge can leave axis labels, legends, arrows, and
data labels as normal PowerPoint shapes after the chart frame is removed. Those
residual shapes still render above native tables and linked table images. This
script removes only the known chart-residue shape ids from the current Jesper
APAC pilot deck while preserving the table layers and commentary.
"""

from __future__ import annotations

import argparse
import xml.etree.ElementTree as ET
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from ppttc_template import A_NS, P_NS, R_NS


ROOT = Path(__file__).resolve().parent.parent
MC_NS = "http://schemas.openxmlformats.org/markup-compatibility/2006"
VML_NS = "urn:schemas-microsoft-com:vml"
P14_NS = "http://schemas.microsoft.com/office/powerpoint/2010/main"
A14_NS = "http://schemas.microsoft.com/office/drawing/2010/main"
A16_NS = "http://schemas.microsoft.com/office/drawing/2014/main"
DEFAULT_DECK = (
    ROOT
    / "state"
    / "2026-Q2"
    / "Jesper-Tyrer"
    / "Jesper-Tyrer-LAND-2026-Q2-table-image-linked.pptx"
)

ET.register_namespace("", P_NS)
ET.register_namespace("a", A_NS)
ET.register_namespace("r", R_NS)
ET.register_namespace("mc", MC_NS)
ET.register_namespace("p14", P14_NS)
ET.register_namespace("a14", A14_NS)
ET.register_namespace("a16", A16_NS)


RESIDUE_IDS_BY_SLIDE: dict[int, set[int]] = {
    4: {18, 19, 20, 21, 22, 23, 24, 25, 33, 34},
    5: {37, 39, 42, 43, 44, 45, 46, 47, 48, 51, 52, 53, 54, 55, 56, 57, 58, 59},
    6: {11, 13, 16, 17, 18, 19, 20, 21, 24, 25},
    13: set(range(32, 52)),
    15: {2, 31, 32, 35, *range(39, 52)},
    16: {19, 20, 29, 30, 31, 32, 33, 34, 35, 36, 37, 38, 39, 40, 41, 42, 43, 44},
    17: {2, 36, 37, 39, *range(44, 58)},
    18: set(range(36, 51)),
    19: set(range(12, 35)),
    21: set(range(23, 45)),
    22: {13, 15, 18, 19, 20, 21, 24, 25, 26},
    25: set(range(9, 44)),
}


def _slide_xml(root: ET.Element) -> bytes:
    text = ET.tostring(root, encoding="unicode", xml_declaration=True)
    if 'Requires="v"' in text and "xmlns:v=" not in text:
        text = text.replace("<sld ", f'<sld xmlns:v="{VML_NS}" ', 1)
        text = text.replace("<p:sld ", f'<p:sld xmlns:v="{VML_NS}" ', 1)
    return text.encode("utf-8")


def _shape_id(element: ET.Element) -> int | None:
    c_nv_pr = element.find(f".//{{{P_NS}}}cNvPr")
    if c_nv_pr is None:
        return None
    raw = c_nv_pr.get("id")
    if raw is None or not raw.isdigit():
        return None
    return int(raw)


def _shape_name(element: ET.Element) -> str:
    c_nv_pr = element.find(f".//{{{P_NS}}}cNvPr")
    return "" if c_nv_pr is None else c_nv_pr.get("name", "")


def _fix_slide(data: bytes, slide_number: int) -> tuple[bytes, list[str]]:
    target_ids = RESIDUE_IDS_BY_SLIDE.get(slide_number)
    if not target_ids:
        return data, []

    root = ET.fromstring(data)
    sp_tree = root.find(f".//{{{P_NS}}}spTree")
    if sp_tree is None:
        return data, []

    removed: list[str] = []
    for child in list(sp_tree):
        shape_id = _shape_id(child)
        if shape_id not in target_ids:
            continue
        removed.append(f"{shape_id}:{_shape_name(child)}")
        sp_tree.remove(child)

    if not removed:
        return data, []
    return _slide_xml(root), removed


def fix_deck(input_path: Path, output_path: Path) -> dict[int, list[str]]:
    with ZipFile(input_path) as zin:
        entries = {item.filename: zin.read(item.filename) for item in zin.infolist()}

    changed: dict[int, list[str]] = {}
    for name, data in list(entries.items()):
        if not (name.startswith("ppt/slides/slide") and name.endswith(".xml")):
            continue
        slide = Path(name).stem.removeprefix("slide")
        if not slide.isdigit():
            continue
        slide_number = int(slide)
        fixed, removed = _fix_slide(data, slide_number)
        if removed:
            entries[name] = fixed
            changed[slide_number] = removed

    output_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = output_path.with_suffix(".tmp.pptx")
    with ZipFile(tmp_path, "w", ZIP_DEFLATED) as zout:
        for name, data in entries.items():
            zout.writestr(name, data)
    tmp_path.replace(output_path)
    return changed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_DECK)
    parser.add_argument("--output", type=Path, default=DEFAULT_DECK)
    args = parser.parse_args()

    changed = fix_deck(args.input, args.output)
    print(args.output)
    for slide_number, removed in sorted(changed.items()):
        print(f"slide {slide_number}: removed {len(removed)} chart-residue shapes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
