"""Build a programmatic LAND seed template with real named think-cell objects.

This creates an object-bank seed, not the final visual placement. The source is
the validated PowerPoint/COM-created deck that already contains think-cell's
official named sample slide. Each copied bank slide contains two native
think-cell chart objects and three automation text fields; names are patched
inside slide XML and the embedded CFB `think-cellXML` stream without corrupting
the OLE container.
"""

from __future__ import annotations

import argparse
import json
import posixpath
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts.ppttc_template import (  # noqa: E402
    CT_NS,
    P_NS,
    PKG_REL_NS,
    R_NS,
    _patch_cfb_stream,
    template_named_elements,
)


DEFAULT_BASE = ROOT / "assets" / "LAND_template.pptx"
DEFAULT_DONOR = ROOT / "_windows_test" / "LAND_template_with_official_tc_slide.pptx"
DEFAULT_RAW_BANK = ROOT / "_windows_test" / "LAND_seed_bank_raw.pptx"
DEFAULT_OUTPUT = ROOT / "assets" / "LAND_seed_thinkcell.pptx"
DEFAULT_VALIDATION_PPTTC = ROOT / "_windows_test" / "land-seed-validation.ppttc"

TEXT_NAMES = [
    "S01_DirectorName",
    "S01_Period",
    "S01_ScopeLabel",
    "S02_ExecSummaryLeft",
    "S02_ExecSummaryRight",
    "S12_GRRProxyFootnote",
    "S21_LargestAccount",
    "S21_LargestArr",
    "S21_LargestShare",
    "S21_ThresholdFlag",
    "S22_StaleActivityFootnote",
    "S23_AvgCycleDaysNote",
    "S23_AvgCycleDaysValue",
    "S23_AvgDealSizeNote",
    "S23_AvgDealSizeValue",
    "S23_OpenOppsNote",
    "S23_OpenOppsValue",
    "S23_VelocityNote",
    "S23_VelocityValue",
    "S23_WinRateNote",
    "S23_WinRateValue",
    "S27_RisksOutlook",
]

DATA_NAMES = [
    "S04_PipeMovement",
    "S05_PipelineByStage",
    "S06_PipelineAging",
    "S07_TopDealsLand",
    "S08_TopDealsExpand",
    "S09_PendingCommercialApproval",
    "S11_RenewalPipeline",
    "S12_GRRProxyTable",
    "S13_ForecastCategory",
    "S15_ByOwner",
    "S16_StageByIndustry",
    "S17_TerritoryPerformance",
    "S18_WinsLossesQTD",
    "S19_Velocity",
    "S21_ConcentrationRiskChart",
    "S21_ConcentrationTable",
    "S22_StaleActivity",
    "S24_AccountExpansion",
    "S25_PipelineCreationVelocity",
    "S26_ActionItems",
]

EXPECTED_NAMES = TEXT_NAMES + DATA_NAMES

TEXT_SOURCE_NAMES = ["SlideTitle", "LeftChartTitle", "RightChartTitle"]
DATA_SOURCE_NAMES = ["LeftChart", "RightChart"]


@dataclass(frozen=True)
class SlideAssignment:
    slide_number: int
    text_names: list[str]
    data_names: list[str]


def _chunk(values: list[str], size: int) -> list[list[str]]:
    return [values[index : index + size] for index in range(0, len(values), size)]


def _assignments(start_slide_number: int) -> list[SlideAssignment]:
    text_chunks = _chunk(TEXT_NAMES, 3)
    data_chunks = _chunk(DATA_NAMES, 2)
    slide_count = max(len(text_chunks), len(data_chunks))
    return [
        SlideAssignment(
            slide_number=start_slide_number + index,
            text_names=text_chunks[index] if index < len(text_chunks) else [],
            data_names=data_chunks[index] if index < len(data_chunks) else [],
        )
        for index in range(slide_count)
    ]


def _rels_part(part_name: str) -> str:
    directory, filename = posixpath.split(part_name)
    return posixpath.join(directory, "_rels", f"{filename}.rels")


def _resolve_target(base_part_name: str, target: str) -> str:
    base_dir = posixpath.dirname("/" + base_part_name)
    return posixpath.normpath(posixpath.join(base_dir, target)).lstrip("/")


def _relative_target(from_part_name: str, to_part_name: str) -> str:
    from_dir = posixpath.dirname("/" + from_part_name)
    return posixpath.relpath("/" + to_part_name, from_dir)


def _next_relationship_id(rels_root: ET.Element) -> str:
    max_id = 0
    for rel in rels_root.findall(f".//{{{PKG_REL_NS}}}Relationship"):
        rel_id = rel.get("Id", "")
        if rel_id.startswith("rId") and rel_id[3:].isdigit():
            max_id = max(max_id, int(rel_id[3:]))
    return f"rId{max_id + 1}"


def _next_available_name(entries: dict[str, bytes], preferred_part_name: str) -> str:
    if preferred_part_name not in entries:
        return preferred_part_name
    directory, filename = posixpath.split(preferred_part_name)
    stem, suffix = filename.rsplit(".", 1)
    counter = 1
    while True:
        candidate = posixpath.join(directory, f"{stem}_seed{counter}.{suffix}")
        if candidate not in entries:
            return candidate
        counter += 1


def _copy_content_type(
    target_ct_root: ET.Element,
    donor_ct_root: ET.Element,
    donor_part_name: str,
    target_part_name: str,
) -> None:
    donor_override = donor_ct_root.find(
        f".//{{{CT_NS}}}Override[@PartName='/{donor_part_name}']"
    )
    if donor_override is not None:
        existing = target_ct_root.find(f".//{{{CT_NS}}}Override[@PartName='/{target_part_name}']")
        if existing is None:
            override = ET.SubElement(target_ct_root, f"{{{CT_NS}}}Override")
            override.set("PartName", f"/{target_part_name}")
            override.set("ContentType", donor_override.get("ContentType", ""))
        return

    extension = target_part_name.rsplit(".", 1)[-1]
    if target_ct_root.find(f".//{{{CT_NS}}}Default[@Extension='{extension}']") is not None:
        return
    donor_default = donor_ct_root.find(f".//{{{CT_NS}}}Default[@Extension='{extension}']")
    if donor_default is not None:
        default = ET.SubElement(target_ct_root, f"{{{CT_NS}}}Default")
        default.set("Extension", extension)
        default.set("ContentType", donor_default.get("ContentType", ""))


def _patch_slide_text_fields(slide_xml: bytes, assignment: SlideAssignment) -> bytes:
    text = slide_xml.decode("utf-8")
    replacements = {
        source: assignment.text_names[index] if index < len(assignment.text_names) else f"SeedUnusedText{assignment.slide_number}_{index}"
        for index, source in enumerate(TEXT_SOURCE_NAMES)
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
        text = text.replace(f"&lt;{old}&gt;", f"&lt;{new}&gt;")
        text = text.replace(f"<{old}>", f"<{new}>")
    return text.encode("utf-8")


def _patch_ole_data_names(data: bytes, assignment: SlideAssignment) -> bytes:
    replacements = {
        source.encode("utf-8"): (
            assignment.data_names[index]
            if index < len(assignment.data_names)
            else f"SeedUnusedData{assignment.slide_number}_{index}"
        ).encode("utf-8")
        for index, source in enumerate(DATA_SOURCE_NAMES)
    }
    if b"<m_strName>" not in data:
        return data
    return _patch_cfb_stream(data, "think-cellXML", replacements)


class _PartCopier:
    def __init__(
        self,
        *,
        target_entries: dict[str, bytes],
        donor_entries: dict[str, bytes],
        target_ct_root: ET.Element,
        donor_ct_root: ET.Element,
        assignment: SlideAssignment,
    ) -> None:
        self.target_entries = target_entries
        self.donor_entries = donor_entries
        self.target_ct_root = target_ct_root
        self.donor_ct_root = donor_ct_root
        self.assignment = assignment
        self.memo: dict[str, str] = {}

    def copy_part(self, donor_part_name: str, preferred_part_name: str | None = None) -> str:
        donor_part_name = donor_part_name.lstrip("/")
        if donor_part_name in self.memo:
            return self.memo[donor_part_name]
        target_part_name = _next_available_name(
            self.target_entries,
            preferred_part_name or donor_part_name,
        )
        data = self.donor_entries[donor_part_name]
        if donor_part_name.endswith(".bin"):
            data = _patch_ole_data_names(data, self.assignment)
        elif donor_part_name.startswith("ppt/slides/") and donor_part_name.endswith(".xml"):
            data = _patch_slide_text_fields(data, self.assignment)

        self.target_entries[target_part_name] = data
        self.memo[donor_part_name] = target_part_name
        _copy_content_type(self.target_ct_root, self.donor_ct_root, donor_part_name, target_part_name)

        donor_rels_name = _rels_part(donor_part_name)
        if donor_rels_name in self.donor_entries:
            donor_rels_root = ET.fromstring(self.donor_entries[donor_rels_name])
            for rel in donor_rels_root.findall(f".//{{{PKG_REL_NS}}}Relationship"):
                if rel.get("TargetMode") == "External":
                    continue
                donor_child = _resolve_target(donor_part_name, rel.get("Target", ""))
                target_child = self.copy_part(donor_child)
                rel.set("Target", _relative_target(target_part_name, target_child))
            self.target_entries[_rels_part(target_part_name)] = ET.tostring(
                donor_rels_root,
                encoding="utf-8",
                xml_declaration=True,
            )
        return target_part_name


def _append_slide_to_presentation(
    *,
    entries: dict[str, bytes],
    slide_part_name: str,
) -> None:
    pres_root = ET.fromstring(entries["ppt/presentation.xml"])
    pres_rels_root = ET.fromstring(entries["ppt/_rels/presentation.xml.rels"])
    slide_id_list = pres_root.find(f".//{{{P_NS}}}sldIdLst")
    if slide_id_list is None:
        raise RuntimeError("ppt/presentation.xml is missing p:sldIdLst")

    rel_id = _next_relationship_id(pres_rels_root)
    rel = ET.SubElement(pres_rels_root, f"{{{PKG_REL_NS}}}Relationship")
    rel.set("Id", rel_id)
    rel.set("Type", "http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide")
    rel.set("Target", _relative_target("ppt/presentation.xml", slide_part_name))

    max_slide_id = 255
    for slide_id in slide_id_list.findall(f".//{{{P_NS}}}sldId"):
        value = slide_id.get("id", "")
        if value.isdigit():
            max_slide_id = max(max_slide_id, int(value))
    slide_id = ET.SubElement(slide_id_list, f"{{{P_NS}}}sldId")
    slide_id.set("id", str(max_slide_id + 1))
    slide_id.set(f"{{{R_NS}}}id", rel_id)

    entries["ppt/presentation.xml"] = ET.tostring(pres_root, encoding="utf-8", xml_declaration=True)
    entries["ppt/_rels/presentation.xml.rels"] = ET.tostring(
        pres_rels_root,
        encoding="utf-8",
        xml_declaration=True,
    )


def _build_validation_ppttc(template_path: Path, output_path: Path) -> None:
    data: list[dict[str, object]] = []
    for name in TEXT_NAMES:
        data.append({"name": name, "table": [[{"string": f"VAL_{name}"}]]})
    for name in DATA_NAMES:
        data.append(
            {
                "name": name,
                "table": [
                    [None, {"string": f"CAT_{name}_A"}, {"string": f"CAT_{name}_B"}],
                    [{"string": f"SER_{name}"}, {"number": 1}, {"number": 2}],
                ],
            }
        )
    output_path.write_text(json.dumps([{"template": str(template_path.resolve()), "data": data}], indent=2))


def build_seed(base_path: Path, donor_path: Path, output_path: Path, validation_ppttc_path: Path) -> None:
    with ZipFile(base_path) as base_zip:
        target_entries = {name: base_zip.read(name) for name in base_zip.namelist()}
    with ZipFile(donor_path) as donor_zip:
        donor_entries = {name: donor_zip.read(name) for name in donor_zip.namelist()}

    target_ct_root = ET.fromstring(target_entries["[Content_Types].xml"])
    donor_ct_root = ET.fromstring(donor_entries["[Content_Types].xml"])

    base_slide_count = sum(
        1
        for name in target_entries
        if name.startswith("ppt/slides/slide") and name.endswith(".xml")
    )
    donor_slide = "ppt/slides/slide29.xml"
    for assignment in _assignments(base_slide_count + 1):
        copier = _PartCopier(
            target_entries=target_entries,
            donor_entries=donor_entries,
            target_ct_root=target_ct_root,
            donor_ct_root=donor_ct_root,
            assignment=assignment,
        )
        target_slide = f"ppt/slides/slide{assignment.slide_number}.xml"
        copied_slide = copier.copy_part(donor_slide, preferred_part_name=target_slide)
        _append_slide_to_presentation(entries=target_entries, slide_part_name=copied_slide)

    target_entries["[Content_Types].xml"] = ET.tostring(
        target_ct_root,
        encoding="utf-8",
        xml_declaration=True,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(output_path, "w", ZIP_DEFLATED) as out_zip:
        for name, data in target_entries.items():
            out_zip.writestr(name, data)

    names = template_named_elements(output_path)
    missing = sorted(set(EXPECTED_NAMES) - names)
    if missing:
        raise RuntimeError(f"seed template missing names: {', '.join(missing)}")
    _build_validation_ppttc(output_path, validation_ppttc_path)


def patch_seed_bank(raw_bank_path: Path, output_path: Path, validation_ppttc_path: Path) -> None:
    with ZipFile(raw_bank_path) as raw_zip:
        entries = {name: raw_zip.read(name) for name in raw_zip.namelist()}

    patched_bins: set[str] = set()
    for assignment in _assignments(29):
        slide_part = f"ppt/slides/slide{assignment.slide_number}.xml"
        rels_part = _rels_part(slide_part)
        if slide_part not in entries:
            raise RuntimeError(f"raw bank is missing {slide_part}")
        entries[slide_part] = _patch_slide_text_fields(entries[slide_part], assignment)
        if rels_part not in entries:
            continue
        rels_root = ET.fromstring(entries[rels_part])
        for rel in rels_root.findall(f".//{{{PKG_REL_NS}}}Relationship"):
            target = rel.get("Target", "")
            target_part = _resolve_target(slide_part, target)
            if not target_part.endswith(".bin") or target_part in patched_bins:
                continue
            entries[target_part] = _patch_ole_data_names(entries[target_part], assignment)
            patched_bins.add(target_part)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(output_path, "w", ZIP_DEFLATED) as out_zip:
        for name, data in entries.items():
            out_zip.writestr(name, data)

    names = template_named_elements(output_path)
    missing = sorted(set(EXPECTED_NAMES) - names)
    if missing:
        raise RuntimeError(f"seed template missing names: {', '.join(missing)}")
    _build_validation_ppttc(output_path, validation_ppttc_path)


def main() -> int:
    parser = argparse.ArgumentParser(description="Build programmatic LAND think-cell seed template.")
    parser.add_argument("--base", type=Path, default=DEFAULT_BASE)
    parser.add_argument("--donor", type=Path, default=DEFAULT_DONOR)
    parser.add_argument(
        "--raw-bank",
        type=Path,
        default=DEFAULT_RAW_BANK,
        help="PowerPoint/COM-created raw bank deck with 10 inserted official think-cell sample slides.",
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--validation-ppttc", type=Path, default=DEFAULT_VALIDATION_PPTTC)
    args = parser.parse_args()

    if args.raw_bank.exists():
        patch_seed_bank(
            raw_bank_path=args.raw_bank.resolve(),
            output_path=args.output.resolve(),
            validation_ppttc_path=args.validation_ppttc.resolve(),
        )
    else:
        build_seed(
            base_path=args.base.resolve(),
            donor_path=args.donor.resolve(),
            output_path=args.output.resolve(),
            validation_ppttc_path=args.validation_ppttc.resolve(),
        )
    print(args.output.resolve())
    print(args.validation_ppttc.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
