#!/usr/bin/env python3
"""Remove stale think-cell ownership metadata from non-native table-image slides."""

from __future__ import annotations

import argparse
import json
import posixpath
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from pptx import Presentation

from _directors import canonical_directors
from period_context import DEFAULT_PERIOD, context_for_period


ROOT = Path(__file__).resolve().parent.parent
P_NS = "http://schemas.openxmlformats.org/presentationml/2006/main"
A_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PKG_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
CT_NS = "http://schemas.openxmlformats.org/package/2006/content-types"
MC_NS = "http://schemas.openxmlformats.org/markup-compatibility/2006"
P14_NS = "http://schemas.microsoft.com/office/powerpoint/2010/main"
A14_NS = "http://schemas.microsoft.com/office/drawing/2010/main"
A16_NS = "http://schemas.microsoft.com/office/drawing/2014/main"
VML_NS = "urn:schemas-microsoft-com:vml"

ET.register_namespace("", P_NS)
ET.register_namespace("a", A_NS)
ET.register_namespace("r", R_NS)
ET.register_namespace("mc", MC_NS)
ET.register_namespace("p14", P14_NS)
ET.register_namespace("a14", A14_NS)
ET.register_namespace("a16", A16_NS)
ET.register_namespace("v", VML_NS)

TC_DATA_SHAPE_NAME = "think-cell data - do not delete"
TC_OLE_PROG_ID = "TCLayout.ActiveDocument.1"
TC_SHAPE_TAG_NAME = "THINKCELLSHAPEDONOTDELETE"
TC_UNDO_TAG_NAME = "THINKCELLUNDODONOTDELETE"

@dataclass
class SlideScrubResult:
    part: str
    removed_data_shapes: int = 0
    removed_tc_cust_data: int = 0
    pruned_relationships: int = 0


@dataclass
class DeckScrubResult:
    deck: str
    status: str
    slides_changed: int = 0
    removed_data_shapes: int = 0
    removed_tc_cust_data: int = 0
    pruned_relationships: int = 0
    removed_orphan_parts: list[str] = field(default_factory=list)
    residual_stale_tokens: dict[str, int] = field(default_factory=dict)
    slide_results: list[SlideScrubResult] = field(default_factory=list)


def _slug(value: str) -> str:
    return value.replace(" ", "-")


def _meeting_spine(period: str, slug: str) -> Path:
    return ROOT / "state" / period / slug / "factory" / "meeting-spine" / f"{slug}-LAND-{period}-meeting-spine.pptx"


def _selected_directors(director_slug: str | None) -> list[dict[str, object]]:
    directors = canonical_directors()
    if not director_slug:
        return directors
    return [director for director in directors if _slug(str(director["name"])) == director_slug]


def _shape_name(element: ET.Element) -> str:
    c_nv_pr = element.find(f".//{{{P_NS}}}cNvPr")
    return "" if c_nv_pr is None else str(c_nv_pr.get("name") or "")


def _rels_name_for_part(part_name: str) -> str:
    parent = posixpath.dirname(part_name)
    return f"{parent}/_rels/{posixpath.basename(part_name)}.rels"


def _is_scrubbable_presentation_part(name: str) -> bool:
    return name.endswith(".xml") and (
        name == "ppt/presentation.xml"
        or name.startswith("ppt/slides/slide")
        or name.startswith("ppt/slideMasters/slideMaster")
        or name.startswith("ppt/slideLayouts/slideLayout")
    )


def _part_name_for_rels(rels_name: str) -> str:
    if rels_name == "_rels/.rels":
        return ""
    parent, filename = rels_name.split("/_rels/", 1)
    return f"{parent}/{filename[:-5]}"


def _target_part(source_part: str, target: str) -> str | None:
    if target.startswith(("http://", "https://", "mailto:")):
        return None
    if target.startswith("/"):
        return target.lstrip("/")
    return posixpath.normpath(posixpath.join(posixpath.dirname(source_part), target))


def _relationship_type(rel: ET.Element) -> str:
    return str(rel.get("Type") or "")


def _relationship_id(rel: ET.Element) -> str:
    return str(rel.get("Id") or "")


def _tag_rel_ids_with_thinkcell(entries: dict[str, bytes], slide_part: str, rels_root: ET.Element) -> set[str]:
    tc_tag_rids: set[str] = set()
    for rel in rels_root.findall(f"{{{PKG_REL_NS}}}Relationship"):
        if not _relationship_type(rel).endswith("/tags"):
            continue
        target = _target_part(slide_part, str(rel.get("Target") or ""))
        if not target or target not in entries:
            continue
        data = entries[target].decode("utf-8", errors="ignore")
        if TC_SHAPE_TAG_NAME in data or TC_UNDO_TAG_NAME in data or "thinkcellActiveDocDoNotDelete" in data:
            tc_tag_rids.add(_relationship_id(rel))
    return tc_tag_rids


def _used_relationship_ids(root: ET.Element) -> set[str]:
    used: set[str] = set()
    for element in root.iter():
        for attr_name, value in element.attrib.items():
            if attr_name.startswith(f"{{{R_NS}}}") and value:
                used.add(value)
    return used


def _remove_tc_cust_data(root: ET.Element, tc_tag_rids: set[str]) -> int:
    if not tc_tag_rids:
        return 0
    removed = 0
    parent_map = {child: parent for parent in root.iter() for child in list(parent)}
    for cust_data in list(root.findall(f".//{{{P_NS}}}custDataLst")):
        tag_rids = {
            str(tags.get(f"{{{R_NS}}}id") or "")
            for tags in cust_data.findall(f"{{{P_NS}}}tags")
        }
        if tag_rids & tc_tag_rids:
            parent = parent_map.get(cust_data)
            if parent is not None:
                parent.remove(cust_data)
                removed += 1
    return removed


def _remove_tc_data_shapes(root: ET.Element) -> int:
    sp_tree = root.find(f".//{{{P_NS}}}spTree")
    if sp_tree is None:
        return 0
    removed = 0
    for child in list(sp_tree):
        text = ET.tostring(child, encoding="unicode")
        if _shape_name(child) == TC_DATA_SHAPE_NAME or TC_OLE_PROG_ID in text:
            sp_tree.remove(child)
            removed += 1
    return removed


def _prune_rels(rels_root: ET.Element, used_rids: set[str], tc_tag_rids: set[str]) -> int:
    removed = 0
    for rel in list(rels_root.findall(f"{{{PKG_REL_NS}}}Relationship")):
        rel_type = _relationship_type(rel)
        rel_id = _relationship_id(rel)
        if rel_id in used_rids:
            continue
        # Presentation-level properties such as theme, viewProps, presProps,
        # and tableStyles are valid even though presentation.xml does not carry
        # direct r:id attributes for them. Only remove relationships we know
        # became stale because we deleted think-cell ownership parts.
        if rel_id in tc_tag_rids or rel_type.endswith("/oleObject"):
            rels_root.remove(rel)
            removed += 1
    return removed


def _slide_xml(root: ET.Element) -> bytes:
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def _scrub_part(entries: dict[str, bytes], part_name: str) -> SlideScrubResult | None:
    rels_name = _rels_name_for_part(part_name)
    if rels_name not in entries:
        return None
    root = ET.fromstring(entries[part_name])
    rels_root = ET.fromstring(entries[rels_name])
    tc_tag_rids = _tag_rel_ids_with_thinkcell(entries, part_name, rels_root)
    removed_data_shapes = _remove_tc_data_shapes(root)
    removed_tc_cust_data = _remove_tc_cust_data(root, tc_tag_rids)
    pruned_relationships = 0
    if removed_data_shapes or removed_tc_cust_data or tc_tag_rids:
        pruned_relationships = _prune_rels(rels_root, _used_relationship_ids(root), tc_tag_rids)
    if removed_data_shapes or removed_tc_cust_data or pruned_relationships:
        entries[part_name] = _slide_xml(root)
        entries[rels_name] = ET.tostring(rels_root, encoding="utf-8", xml_declaration=True)
    if not (removed_data_shapes or removed_tc_cust_data or pruned_relationships):
        return None
    return SlideScrubResult(
        part=part_name,
        removed_data_shapes=removed_data_shapes,
        removed_tc_cust_data=removed_tc_cust_data,
        pruned_relationships=pruned_relationships,
    )


def _referenced_parts(entries: dict[str, bytes]) -> set[str]:
    referenced: set[str] = set()
    for name, data in entries.items():
        if not name.endswith(".rels"):
            continue
        source_part = _part_name_for_rels(name)
        try:
            root = ET.fromstring(data)
        except ET.ParseError:
            continue
        for rel in root.findall(f"{{{PKG_REL_NS}}}Relationship"):
            target = _target_part(source_part, str(rel.get("Target") or ""))
            if target:
                referenced.add(target)
    return referenced


def _remove_orphan_parts(entries: dict[str, bytes]) -> list[str]:
    referenced = _referenced_parts(entries)
    removable_prefixes = ("ppt/tags/tag", "ppt/embeddings/oleObject", "ppt/media/")
    removed: list[str] = []
    for name in sorted(list(entries)):
        if not name.startswith(removable_prefixes):
            continue
        if name in referenced:
            continue
        if not (name.startswith("ppt/tags/tag") or name.startswith("ppt/embeddings/oleObject")):
            continue
        removed.append(name)
        entries.pop(name, None)
    if removed and "[Content_Types].xml" in entries:
        root = ET.fromstring(entries["[Content_Types].xml"])
        removed_part_names = {f"/{name}" for name in removed}
        for override in list(root.findall(f"{{{CT_NS}}}Override")):
            if override.get("PartName") in removed_part_names:
                root.remove(override)
        entries["[Content_Types].xml"] = ET.tostring(root, encoding="utf-8", xml_declaration=True)
    return removed


def _residual_stale_tokens(entries: dict[str, bytes]) -> dict[str, int]:
    tokens = {
        TC_DATA_SHAPE_NAME: 0,
        TC_OLE_PROG_ID: 0,
        TC_SHAPE_TAG_NAME: 0,
        TC_UNDO_TAG_NAME: 0,
    }
    for data in entries.values():
        text = data.decode("utf-8", errors="ignore")
        for token in tokens:
            tokens[token] += text.count(token)
    return {token: count for token, count in tokens.items() if count}


def scrub_deck(path: Path) -> DeckScrubResult:
    path = path.expanduser().resolve()
    with ZipFile(path) as zin:
        entries = {item.filename: zin.read(item.filename) for item in zin.infolist()}

    slide_results: list[SlideScrubResult] = []
    for name in sorted(entries):
        if not _is_scrubbable_presentation_part(name):
            continue
        result = _scrub_part(entries, name)
        if result:
            slide_results.append(result)
    removed_orphan_parts = _remove_orphan_parts(entries)

    if slide_results or removed_orphan_parts:
        tmp_path = path.with_suffix(".scrub.tmp.pptx")
        with ZipFile(tmp_path, "w", ZIP_DEFLATED) as zout:
            for name, data in entries.items():
                zout.writestr(name, data)
        tmp_path.replace(path)
        normalized_path = path.with_suffix(".scrub.normalized.tmp.pptx")
        Presentation(path).save(normalized_path)
        normalized_path.replace(path)
        with ZipFile(path) as zin:
            entries = {item.filename: zin.read(item.filename) for item in zin.infolist()}
        removed_orphan_parts.extend(_remove_orphan_parts(entries))
        if removed_orphan_parts:
            tmp_path = path.with_suffix(".scrub.tmp.pptx")
            with ZipFile(tmp_path, "w", ZIP_DEFLATED) as zout:
                for name, data in entries.items():
                    zout.writestr(name, data)
            tmp_path.replace(path)
            normalized_path = path.with_suffix(".scrub.normalized.tmp.pptx")
            Presentation(path).save(normalized_path)
            normalized_path.replace(path)
            with ZipFile(path) as zin:
                entries = {item.filename: zin.read(item.filename) for item in zin.infolist()}

    residual = _residual_stale_tokens(entries)

    return DeckScrubResult(
        deck=str(path),
        status="pass" if not residual else "fail",
        slides_changed=len(slide_results),
        removed_data_shapes=sum(result.removed_data_shapes for result in slide_results),
        removed_tc_cust_data=sum(result.removed_tc_cust_data for result in slide_results),
        pruned_relationships=sum(result.pruned_relationships for result in slide_results),
        removed_orphan_parts=removed_orphan_parts,
        residual_stale_tokens=residual,
        slide_results=slide_results,
    )


def _deck_paths(args: argparse.Namespace) -> list[Path]:
    paths = [Path(path) for path in args.decks]
    if args.meeting_spine_decks:
        context_for_period(args.period)
        for director in _selected_directors(args.director_slug):
            paths.append(_meeting_spine(args.period, _slug(str(director["name"]))))
    if args.package_dir:
        context = context_for_period(args.period)
        paths.extend(sorted(args.package_dir.expanduser().glob(context.meeting_spine_pattern)))
    unique: list[Path] = []
    seen: set[Path] = set()
    for path in paths:
        resolved = path.expanduser().resolve()
        if resolved in seen or not resolved.exists():
            continue
        seen.add(resolved)
        unique.append(resolved)
    return unique


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("decks", nargs="*", type=Path)
    parser.add_argument("--period", default=DEFAULT_PERIOD)
    parser.add_argument("--director-slug")
    parser.add_argument("--meeting-spine-decks", action="store_true")
    parser.add_argument("--package-dir", type=Path)
    parser.add_argument("--jobs", type=int, default=1)
    parser.add_argument("--json-output", type=Path)
    args = parser.parse_args()

    paths = _deck_paths(args)
    if not paths:
        raise SystemExit("no decks selected")
    if args.jobs > 1 and len(paths) > 1:
        with ThreadPoolExecutor(max_workers=min(args.jobs, len(paths))) as executor:
            results = list(executor.map(scrub_deck, paths))
    else:
        results = [scrub_deck(path) for path in paths]
    payload = {
        "schema": "stale-thinkcell-metadata-scrub/v1",
        "status": "pass" if all(result.status == "pass" for result in results) else "fail",
        "period": args.period,
        "deck_count": len(results),
        "results": [asdict(result) for result in results],
    }
    if args.json_output:
        args.json_output.parent.mkdir(parents=True, exist_ok=True)
        args.json_output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2))
    return 0 if payload["status"] == "pass" else 2


if __name__ == "__main__":
    raise SystemExit(main())
