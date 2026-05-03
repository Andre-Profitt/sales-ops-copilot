"""Build a think-cell seed template from intact official donor slides.

This avoids brittle PowerPoint UI automation. Each donor slide is copied as a
complete OpenXML slide, including its tags, OLE embedding, chart parts, media,
and embedded workbook relationships. Then the copied think-cell OLE stream is
renamed with the exact LAND AddRangeData name.

Current scope: native think-cell chart-bearing slides plus synthetic automation
text fields for the remaining LAND contract names. Table names are represented
as off-slide automation text-field stubs so the 42-name contract is present;
they are not native think-cell tables yet.
"""

from __future__ import annotations

import argparse
import html
import posixpath
import re
import uuid
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from thinkcell_cfb import CfbStreamEdit, replace_cfb_stream_data


ROOT = Path(__file__).resolve().parent.parent
REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
CT_NS = "http://schemas.openxmlformats.org/package/2006/content-types"
SLIDE_LAYOUT_REL = (
    "http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideLayout"
)
NOTES_SLIDE_REL = (
    "http://schemas.openxmlformats.org/officeDocument/2006/relationships/notesSlide"
)
OLE_OBJECT_REL = (
    "http://schemas.openxmlformats.org/officeDocument/2006/relationships/oleObject"
)


ET.register_namespace("", REL_NS)
ET.register_namespace("", CT_NS)


@dataclass(frozen=True)
class DonorSlideSpec:
    target_slide: int
    donor_path: Path
    donor_slide: int
    name: str
    text_replacements: tuple[tuple[str, str], ...] = ()


DONOR_DIR = ROOT / "_windows_test"
BAR_COLUMN = DONOR_DIR / "official-bar-column.potx"
WATERFALL = DONOR_DIR / "official-waterfall.potx"
MEKKO = DONOR_DIR / "official-mekko.potx"


CHART_DONORS: tuple[DonorSlideSpec, ...] = (
    DonorSlideSpec(
        4,
        WATERFALL,
        1,
        "S04_PipeMovement",
        (
            ("Revenues, costs, totals [USD m]", "ARR (mEUR)"),
            ("BU1", "Additions"),
            ("BU2", "Outflows"),
            ("Totals", "Total"),
        ),
    ),
    DonorSlideSpec(5, BAR_COLUMN, 6, "S05_PipelineByStage"),
    DonorSlideSpec(6, BAR_COLUMN, 6, "S06_PipelineAging"),
    DonorSlideSpec(
        13,
        BAR_COLUMN,
        3,
        "S13_ForecastCategory",
        (("User count [K]", "ARR (mEUR)"),),
    ),
    DonorSlideSpec(15, BAR_COLUMN, 6, "S15_ByOwner"),
    DonorSlideSpec(
        16,
        BAR_COLUMN,
        8,
        "S16_StageByIndustry",
        (("Product A", "Stage mix"),),
    ),
    DonorSlideSpec(17, BAR_COLUMN, 6, "S17_TerritoryPerformance"),
    DonorSlideSpec(
        18,
        BAR_COLUMN,
        3,
        "S18_WinsLossesQTD",
        (("User count [K]", "Value (mEUR)"),),
    ),
    DonorSlideSpec(
        19,
        BAR_COLUMN,
        3,
        "S19_Velocity",
        (("User count [K]", "Median age (days)"),),
    ),
    DonorSlideSpec(
        21,
        BAR_COLUMN,
        3,
        "S21_ConcentrationRiskChart",
        (("User count [K]", "Share (%)"),),
    ),
    DonorSlideSpec(22, BAR_COLUMN, 6, "S22_StaleActivity"),
    DonorSlideSpec(
        25,
        BAR_COLUMN,
        3,
        "S25_PipelineCreationVelocity",
        (("User count [K]", "New ARR (mEUR)"),),
    ),
)


TEXT_FIELD_NAMES_BY_SLIDE: dict[int, tuple[str, ...]] = {
    1: ("S01_DirectorName", "S01_Period", "S01_ScopeLabel"),
    2: ("S02_ExecSummaryLeft", "S02_ExecSummaryRight"),
    12: ("S12_GRRProxyFootnote",),
    21: (
        "S21_LargestAccount",
        "S21_LargestArr",
        "S21_LargestShare",
        "S21_ThresholdFlag",
    ),
    22: ("S22_StaleActivityFootnote",),
    23: (
        "S23_OpenOppsValue",
        "S23_OpenOppsNote",
        "S23_WinRateValue",
        "S23_WinRateNote",
        "S23_AvgDealSizeValue",
        "S23_AvgDealSizeNote",
        "S23_AvgCycleDaysValue",
        "S23_AvgCycleDaysNote",
        "S23_VelocityValue",
        "S23_VelocityNote",
    ),
    27: ("S27_RisksOutlook",),
}


TABLE_STUB_NAMES_BY_SLIDE: dict[int, tuple[str, ...]] = {
    7: ("S07_TopDealsLand",),
    8: ("S08_TopDealsExpand",),
    9: ("S09_PendingCommercialApproval",),
    11: ("S11_RenewalPipeline",),
    12: ("S12_GRRProxyTable",),
    21: ("S21_ConcentrationTable",),
    24: ("S24_AccountExpansion",),
    26: ("S26_ActionItems",),
}


class PackageBuilder:
    def __init__(self, base_path: Path) -> None:
        self.parts: dict[str, bytes] = {}
        with ZipFile(base_path) as zf:
            for item in zf.infolist():
                self.parts[item.filename] = zf.read(item.filename)

        self._content_type_defaults: dict[str, str] = {}
        self._content_type_overrides: dict[str, str] = {}
        self._load_content_types(self.parts["[Content_Types].xml"])

    def replace_slide_from_donor(self, spec: DonorSlideSpec) -> list[str]:
        with ZipFile(spec.donor_path) as donor:
            donor_parts = {item.filename: donor.read(item.filename) for item in donor.infolist()}
            donor_ct = _parse_content_types(donor_parts["[Content_Types].xml"])

            target_slide_part = f"ppt/slides/slide{spec.target_slide}.xml"
            donor_slide_part = f"ppt/slides/slide{spec.donor_slide}.xml"
            target_rels_part = f"ppt/slides/_rels/slide{spec.target_slide}.xml.rels"
            donor_rels_part = f"ppt/slides/_rels/slide{spec.donor_slide}.xml.rels"

            base_layout_target = self._base_slide_layout_target(target_rels_part)
            donor_slide_xml = donor_parts[donor_slide_part].decode("utf-8")
            for old, new in spec.text_replacements:
                donor_slide_xml = donor_slide_xml.replace(old, new)
            self.parts[target_slide_part] = donor_slide_xml.encode("utf-8")
            self._content_type_overrides[f"/{target_slide_part}"] = (
                "application/vnd.openxmlformats-officedocument.presentationml.slide+xml"
            )

            ole_parts: list[str] = []
            rel_root = ET.fromstring(donor_parts[donor_rels_part])
            for rel in list(rel_root):
                rel_type = rel.attrib.get("Type", "")
                target = rel.attrib.get("Target", "")
                if not target or rel.attrib.get("TargetMode") == "External":
                    continue
                if rel_type == NOTES_SLIDE_REL:
                    rel_root.remove(rel)
                    continue
                if rel_type == SLIDE_LAYOUT_REL:
                    rel.set("Target", base_layout_target)
                    continue

                donor_target_part = _resolve_part(donor_slide_part, target)
                new_target_part = self._copy_related_part(
                    donor_parts=donor_parts,
                    donor_content_types=donor_ct,
                    donor_part=donor_target_part,
                    preferred_part=donor_target_part,
                )
                rel.set("Target", _relative_target(target_slide_part, new_target_part))
                if rel_type == OLE_OBJECT_REL:
                    ole_parts.append(new_target_part)

            self.parts[target_rels_part] = ET.tostring(
                rel_root, encoding="utf-8", xml_declaration=True
            )
            return ole_parts

    def patch_thinkcell_names(self, ole_parts: list[str], name: str) -> int:
        replacements = (
            (
                b"<m_strName></m_strName>",
                f"<m_strName>{name}</m_strName>".encode("utf-8"),
            ),
        )
        count = 0
        for part in ole_parts:
            data = self.parts[part]
            if b"<m_strName></m_strName>" not in data:
                continue
            result = replace_cfb_stream_data(
                data,
                (
                    CfbStreamEdit(
                        name="think-cellXML",
                        replacements=replacements,
                    ),
                ),
            )
            self.parts[part] = result.data
            count += result.replacements_made
        return count

    def add_text_field(
        self,
        *,
        slide_number: int,
        name: str,
        left: int,
        top: int,
        width: int,
        height: int,
        font_size: int = 1400,
    ) -> None:
        slide_part = f"ppt/slides/slide{slide_number}.xml"
        text = self.parts[slide_part].decode("utf-8")
        shape_id = _next_shape_id(text)
        shape_xml = _automation_text_field_shape(
            name=name,
            shape_id=shape_id,
            left=left,
            top=top,
            width=width,
            height=height,
            font_size=font_size,
        )
        self.parts[slide_part] = text.replace(
            "</p:spTree>", f"{shape_xml}</p:spTree>", 1
        ).encode("utf-8")

    def write(self, out_path: Path) -> None:
        self.parts["[Content_Types].xml"] = self._content_types_xml()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with ZipFile(out_path, "w", ZIP_DEFLATED) as zf:
            for name, data in self.parts.items():
                zf.writestr(name, data)

    def _copy_related_part(
        self,
        *,
        donor_parts: dict[str, bytes],
        donor_content_types: tuple[dict[str, str], dict[str, str]],
        donor_part: str,
        preferred_part: str,
    ) -> str:
        new_part = self._allocate_part_name(preferred_part)
        self.parts[new_part] = donor_parts[donor_part]
        self._copy_content_type(donor_content_types, donor_part, new_part)

        donor_rels = _rels_part_name(donor_part)
        if donor_rels in donor_parts:
            new_rels = _rels_part_name(new_part)
            rel_root = ET.fromstring(donor_parts[donor_rels])
            for rel in list(rel_root):
                if rel.attrib.get("TargetMode") == "External":
                    continue
                target = rel.attrib.get("Target", "")
                if not target:
                    continue
                related_donor_part = _resolve_part(donor_part, target)
                related_new_part = self._copy_related_part(
                    donor_parts=donor_parts,
                    donor_content_types=donor_content_types,
                    donor_part=related_donor_part,
                    preferred_part=related_donor_part,
                )
                rel.set("Target", _relative_target(new_part, related_new_part))
            self.parts[new_rels] = ET.tostring(
                rel_root, encoding="utf-8", xml_declaration=True
            )
            self._content_type_defaults.setdefault(
                "rels",
                "application/vnd.openxmlformats-package.relationships+xml",
            )
        return new_part

    def _allocate_part_name(self, preferred_part: str) -> str:
        if preferred_part not in self.parts:
            return preferred_part

        folder, filename = posixpath.split(preferred_part)
        stem, ext = _split_extension(filename)
        match = re.match(r"^(.*?)(\d+)$", stem)
        prefix = match.group(1) if match else f"{stem}_seed"
        existing = set(self.parts)
        idx = 1
        while True:
            candidate = posixpath.join(folder, f"{prefix}{idx}{ext}")
            if candidate not in existing:
                return candidate
            idx += 1

    def _base_slide_layout_target(self, rels_part: str) -> str:
        root = ET.fromstring(self.parts[rels_part])
        for rel in root:
            if rel.attrib.get("Type") == SLIDE_LAYOUT_REL:
                return rel.attrib["Target"]
        return "../slideLayouts/slideLayout1.xml"

    def _load_content_types(self, data: bytes) -> None:
        defaults, overrides = _parse_content_types(data)
        self._content_type_defaults.update(defaults)
        self._content_type_overrides.update(overrides)

    def _copy_content_type(
        self,
        donor_content_types: tuple[dict[str, str], dict[str, str]],
        donor_part: str,
        new_part: str,
    ) -> None:
        donor_defaults, donor_overrides = donor_content_types
        donor_key = f"/{donor_part}"
        new_key = f"/{new_part}"
        if donor_key in donor_overrides:
            self._content_type_overrides[new_key] = donor_overrides[donor_key]
            return
        ext = donor_part.rsplit(".", 1)[-1] if "." in donor_part else ""
        if ext and ext in donor_defaults:
            self._content_type_defaults.setdefault(ext, donor_defaults[ext])

    def _content_types_xml(self) -> bytes:
        root = ET.Element(f"{{{CT_NS}}}Types")
        for ext, content_type in sorted(self._content_type_defaults.items()):
            ET.SubElement(
                root,
                f"{{{CT_NS}}}Default",
                {"Extension": ext, "ContentType": content_type},
            )
        for part_name, content_type in sorted(self._content_type_overrides.items()):
            ET.SubElement(
                root,
                f"{{{CT_NS}}}Override",
                {"PartName": part_name, "ContentType": content_type},
            )
        return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def _parse_content_types(data: bytes) -> tuple[dict[str, str], dict[str, str]]:
    root = ET.fromstring(data)
    defaults: dict[str, str] = {}
    overrides: dict[str, str] = {}
    for child in root:
        tag = child.tag.rsplit("}", 1)[-1]
        if tag == "Default":
            defaults[child.attrib["Extension"]] = child.attrib["ContentType"]
        elif tag == "Override":
            overrides[child.attrib["PartName"]] = child.attrib["ContentType"]
    return defaults, overrides


def _rels_part_name(part: str) -> str:
    folder, filename = posixpath.split(part)
    return posixpath.join(folder, "_rels", f"{filename}.rels")


def _resolve_part(owner_part: str, target: str) -> str:
    if target.startswith("/"):
        return target.lstrip("/")
    return posixpath.normpath(posixpath.join(posixpath.dirname(owner_part), target))


def _relative_target(owner_part: str, target_part: str) -> str:
    return posixpath.relpath(target_part, posixpath.dirname(owner_part))


def _split_extension(filename: str) -> tuple[str, str]:
    if "." not in filename:
        return filename, ""
    stem, ext = filename.rsplit(".", 1)
    return stem, f".{ext}"


def _next_shape_id(slide_xml: str) -> int:
    ids = [int(match) for match in re.findall(r'<p:cNvPr id="(\d+)"', slide_xml)]
    return (max(ids) + 1) if ids else 2


def _automation_text_field_shape(
    *,
    name: str,
    shape_id: int,
    left: int,
    top: int,
    width: int,
    height: int,
    font_size: int,
) -> str:
    tc_payload = (
        '<?xml version="1.0" encoding="UTF-16" standalone="yes"?>'
        '<root reqver="32687"><version val="38388"/><PersistentType>'
        '<m_varval type="5"></m_varval><m_prec><m_yearfmt>'
        '<begin val="0"/><end val="4"/></m_yearfmt></m_prec>'
        '<m_bUseExcelFont val="0"/><m_bUseExcelFontColor val="0"/>'
        f"<m_strName>{name}</m_strName>"
        "</PersistentType></root>"
    )
    escaped_payload = html.escape(tc_payload, quote=True)
    return (
        f'<p:sp><p:nvSpPr><p:cNvPr id="{shape_id}" name="tcfield_{name}"/>'
        '<p:cNvSpPr txBox="1"/><p:nvPr/></p:nvSpPr><p:spPr>'
        f'<a:xfrm><a:off x="{left}" y="{top}"/>'
        f'<a:ext cx="{width}" cy="{height}"/></a:xfrm>'
        '<a:prstGeom prst="rect"><a:avLst/></a:prstGeom>'
        '<a:noFill/><a:ln><a:noFill/></a:ln></p:spPr>'
        '<p:txBody><a:bodyPr wrap="square" rtlCol="0"><a:spAutoFit/>'
        '</a:bodyPr><a:lstStyle/><a:p>'
        f'<a:fld id="{{{uuid.uuid4()}}}" type="thinkcell{escaped_payload}">'
        f'<a:rPr lang="en-US" sz="{font_size}"/>'
        f"<a:t>&lt;{name}&gt;</a:t></a:fld>"
        f'<a:endParaRPr lang="en-US" sz="{font_size}"/></a:p></p:txBody></p:sp>'
    )


def _field_box(slide_number: int, index: int, *, off_slide: bool = False) -> tuple[int, int, int, int]:
    if off_slide:
        return 100_000, 7_200_000 + (index * 120_000), 2_000_000, 100_000
    if slide_number == 1:
        return 650_000, 1_000_000 + (index * 520_000), 8_000_000, 430_000
    if slide_number == 2:
        return 650_000 + (index * 4_600_000), 1_350_000, 4_200_000, 2_300_000
    if slide_number == 21:
        return 650_000 + ((index % 2) * 3_800_000), 4_650_000 + ((index // 2) * 420_000), 3_400_000, 330_000
    if slide_number == 23:
        return 650_000 + ((index % 2) * 4_400_000), 1_250_000 + ((index // 2) * 600_000), 3_900_000, 360_000
    if slide_number == 27:
        return 650_000, 1_300_000, 8_200_000, 3_800_000
    return 650_000, 5_900_000 + (index * 280_000), 8_200_000, 260_000


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--base",
        type=Path,
        default=ROOT / "assets" / "LAND_template.pptx",
        help="Base LAND template.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "assets" / "LAND_thinkcell_seed_charts.pptx",
        help="Output seed template path.",
    )
    args = parser.parse_args()

    for donor in {spec.donor_path for spec in CHART_DONORS}:
        if not donor.exists():
            raise SystemExit(f"missing donor template: {donor}")

    builder = PackageBuilder(args.base)
    patched: dict[str, int] = {}
    for spec in CHART_DONORS:
        ole_parts = builder.replace_slide_from_donor(spec)
        patched[spec.name] = builder.patch_thinkcell_names(ole_parts, spec.name)
        if patched[spec.name] < 1:
            raise SystemExit(f"failed to patch think-cell name for {spec.name}")

    for slide_number, names in TEXT_FIELD_NAMES_BY_SLIDE.items():
        for index, name in enumerate(names):
            left, top, width, height = _field_box(slide_number, index)
            builder.add_text_field(
                slide_number=slide_number,
                name=name,
                left=left,
                top=top,
                width=width,
                height=height,
                font_size=1800 if slide_number in {1, 23} else 1400,
            )

    for slide_number, names in TABLE_STUB_NAMES_BY_SLIDE.items():
        for index, name in enumerate(names):
            left, top, width, height = _field_box(slide_number, index, off_slide=True)
            builder.add_text_field(
                slide_number=slide_number,
                name=name,
                left=left,
                top=top,
                width=width,
                height=height,
                font_size=800,
            )

    builder.write(args.output)
    print(args.output)
    for name, count in patched.items():
        print(f"{name}: {count} m_strName replacements")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
