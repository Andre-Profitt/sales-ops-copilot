#!/usr/bin/env python3
"""Remove visual chart frames that collide with table layers.

This is intentionally conservative: it only removes visible PowerPoint chart
frames whose bounding box overlaps a native table or a linked table-image
picture. The table layers stay intact.
"""

from __future__ import annotations

import argparse
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from ppttc_template import A_NS, P_NS, R_NS, _shape_name


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


@dataclass(frozen=True)
class Box:
    left: int
    top: int
    right: int
    bottom: int

    @property
    def area(self) -> int:
        return max(0, self.right - self.left) * max(0, self.bottom - self.top)

    def overlap_ratio(self, other: "Box") -> float:
        x1 = max(self.left, other.left)
        y1 = max(self.top, other.top)
        x2 = min(self.right, other.right)
        y2 = min(self.bottom, other.bottom)
        overlap = max(0, x2 - x1) * max(0, y2 - y1)
        return 0.0 if self.area == 0 else overlap / self.area


def _slide_xml(root: ET.Element) -> bytes:
    text = ET.tostring(root, encoding="unicode", xml_declaration=True)
    if 'Requires="v"' in text and "xmlns:v=" not in text:
        text = text.replace("<sld ", f'<sld xmlns:v="{VML_NS}" ', 1)
        text = text.replace("<p:sld ", f'<p:sld xmlns:v="{VML_NS}" ', 1)
    return text.encode("utf-8")


def _box(element: ET.Element) -> Box | None:
    xfrm = element.find(f"./{{{P_NS}}}xfrm")
    if xfrm is None:
        xfrm = element.find(f".//{{{A_NS}}}xfrm")
    if xfrm is None:
        return None
    off = xfrm.find(f"{{{A_NS}}}off")
    ext = xfrm.find(f"{{{A_NS}}}ext")
    if off is None or ext is None:
        return None
    left = int(off.get("x", "0"))
    top = int(off.get("y", "0"))
    return Box(
        left=left,
        top=top,
        right=left + int(ext.get("cx", "0")),
        bottom=top + int(ext.get("cy", "0")),
    )


def _is_table_layer(element: ET.Element) -> bool:
    if element.find(f".//{{{A_NS}}}tbl") is not None:
        return True
    return _shape_name(element) == "Pic"


def _is_visible_chart_frame(element: ET.Element) -> bool:
    return _shape_name(element).startswith("Chart ")


def _is_small_hidden_chart_data(element: ET.Element) -> bool:
    if _shape_name(element) != "think-cell data - do not delete":
        return False
    box = _box(element)
    if box is None:
        return False
    return (box.right - box.left) < 50_000 and (box.bottom - box.top) < 50_000


def _fix_slide(data: bytes) -> tuple[bytes, list[str]]:
    root = ET.fromstring(data)
    sp_tree = root.find(f".//{{{P_NS}}}spTree")
    if sp_tree is None:
        return data, []

    children = list(sp_tree)
    table_boxes = [
        box
        for child in children
        if _is_table_layer(child)
        for box in [_box(child)]
        if box is not None
    ]
    if not table_boxes:
        return data, []

    removed: list[str] = []
    remove_small_hidden = False
    for child in list(sp_tree):
        if not _is_visible_chart_frame(child):
            continue
        chart_box = _box(child)
        if chart_box is None:
            continue
        if any(chart_box.overlap_ratio(table_box) > 0.03 for table_box in table_boxes):
            removed.append(_shape_name(child))
            sp_tree.remove(child)
            remove_small_hidden = True

    if remove_small_hidden:
        for child in list(sp_tree):
            if _is_small_hidden_chart_data(child):
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
        stem = Path(name).stem
        if not stem.removeprefix("slide").isdigit():
            continue
        slide_number = int(stem.removeprefix("slide"))
        fixed, removed = _fix_slide(data)
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
        print(f"slide {slide_number}: removed {', '.join(removed)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
