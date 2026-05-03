#!/usr/bin/env python3
"""Move table layers above think-cell chart visuals in a PPTX.

The chart donor injection appends visual chart shapes late in the slide tree.
That makes the chart layer render on top of native PowerPoint tables. This
post-process keeps the existing chart objects and simply restores the table
layer to the front.
"""

from __future__ import annotations

import argparse
import xml.etree.ElementTree as ET
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


def _slide_xml(root: ET.Element) -> bytes:
    text = ET.tostring(root, encoding="unicode", xml_declaration=True)
    if 'Requires="v"' in text and "xmlns:v=" not in text:
        text = text.replace("<sld ", f'<sld xmlns:v="{VML_NS}" ', 1)
        text = text.replace("<p:sld ", f'<p:sld xmlns:v="{VML_NS}" ', 1)
    return text.encode("utf-8")


def _is_table_layer(element: ET.Element) -> bool:
    if element.find(f".//{{{A_NS}}}tbl") is not None:
        return True
    return _shape_name(element) == "Pic"


def _fix_slide(data: bytes) -> tuple[bytes, int]:
    root = ET.fromstring(data)
    sp_tree = root.find(f".//{{{P_NS}}}spTree")
    if sp_tree is None:
        return data, 0

    children = list(sp_tree)
    fixed_prefix = children[:2]
    shape_children = children[2:]
    table_layers = [child for child in shape_children if _is_table_layer(child)]
    if not table_layers:
        return data, 0

    non_table_layers = [child for child in shape_children if not _is_table_layer(child)]
    if shape_children == non_table_layers + table_layers:
        return data, 0

    sp_tree[:] = fixed_prefix + non_table_layers + table_layers
    return _slide_xml(root), len(table_layers)


def fix_deck(input_path: Path, output_path: Path) -> dict[int, int]:
    with ZipFile(input_path) as zin:
        entries = {item.filename: zin.read(item.filename) for item in zin.infolist()}

    changed: dict[int, int] = {}
    for name, data in list(entries.items()):
        if not (name.startswith("ppt/slides/slide") and name.endswith(".xml")):
            continue
        stem = Path(name).stem
        if not stem.removeprefix("slide").isdigit():
            continue
        slide_number = int(stem.removeprefix("slide"))
        fixed, count = _fix_slide(data)
        if count:
            entries[name] = fixed
            changed[slide_number] = count

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
    for slide_number, table_count in sorted(changed.items()):
        print(f"slide {slide_number}: moved {table_count} table layer(s) to front")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
