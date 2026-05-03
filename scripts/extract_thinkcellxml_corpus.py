#!/usr/bin/env python3
"""Bulk-extract think-cellXML from every CFB blob in every .pptx/.potx in the corpus.

Walks input roots, finds OOXML files, unzips, locates ppt/embeddings/oleObject*.bin,
parses each CFB, dumps the think-cellXML stream + Package stream.

Outputs:
  state/thinkcell_bridge/thinkcellxml_corpus/<ts>/
    extraction_index.json   — per-deck, per-chart manifest
    by_deck/<deck-name>/
      ole_<N>_think-cellXML.xml
      ole_<N>_Package.zip
      ole_<N>_child_layout.xml
    schema_inventory.json   — element/attribute frequencies across all charts
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import sys
import time
import zipfile
from collections import Counter
from pathlib import Path

try:
    import olefile  # type: ignore
except ImportError:
    print("Run: pip install olefile", file=sys.stderr)
    sys.exit(1)


ROOT = Path(__file__).resolve().parent.parent


def _safe_name(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]", "_", s)[:120]


def _extract_one_cfb(blob: bytes) -> dict:
    out = {
        "size": len(blob),
        "sha256": hashlib.sha256(blob).hexdigest(),
        "is_cfb": blob.startswith(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"),
        "streams": [],
        "thinkcell_xml": None,
        "thinkcell_xml_size": 0,
        "thinkcell_child_xml": None,
        "thinkcell_child_xml_size": 0,
        "package_size": 0,
        "package_present": False,
        "error": None,
    }
    if not out["is_cfb"]:
        out["error"] = "not CFB"
        return out
    try:
        ole = olefile.OleFileIO(io.BytesIO(blob))
        for entry in ole.listdir(streams=True, storages=False):
            path = "/".join(entry)
            try:
                with ole.openstream(entry) as s:
                    data = s.read()
            except Exception as e:
                out["streams"].append({"path": path, "error": str(e)})
                continue
            stream_info = {"path": path, "size": len(data)}
            out["streams"].append(stream_info)
            if path == "think-cellXML":
                out["thinkcell_xml"] = data.decode("utf-8", errors="replace")
                out["thinkcell_xml_size"] = len(data)
            elif path.endswith("/think-cellXML"):
                out["thinkcell_child_xml"] = data.decode("utf-8", errors="replace")
                out["thinkcell_child_xml_size"] = len(data)
            elif path.endswith("/Package"):
                out["package_size"] = len(data)
                out["package_present"] = True
                out["package_bytes"] = data  # may carry through
        ole.close()
    except Exception as e:
        out["error"] = f"{type(e).__name__}: {e}"
    return out


def _process_deck(deck_path: Path, output_root: Path) -> dict:
    deck_out = output_root / "by_deck" / _safe_name(deck_path.stem)
    deck_out.mkdir(parents=True, exist_ok=True)
    info = {
        "deck": str(deck_path),
        "deck_size": deck_path.stat().st_size,
        "sha256": hashlib.sha256(deck_path.read_bytes()).hexdigest(),
        "ole_objects": [],
        "thinkcellxml_count": 0,
        "thinkcellxml_total_bytes": 0,
        "tc_tag_count": 0,
        "tc_alternate_content_count": 0,
        "error": None,
    }
    try:
        with zipfile.ZipFile(deck_path) as z:
            parts = z.namelist()
            embeddings = sorted(
                [
                    p
                    for p in parts
                    if p.startswith("ppt/embeddings/oleObject") and p.endswith(".bin")
                ]
            )
            tag_parts = [p for p in parts if p.startswith("ppt/tags/tag") and p.endswith(".xml")]
            slide_parts = [
                p for p in parts if p.startswith("ppt/slides/slide") and p.endswith(".xml")
            ]

            # Count tag parts containing think-cell content
            for tp in tag_parts:
                content = z.read(tp).decode("utf-8", errors="replace")
                if "THINKCELL" in content.upper():
                    info["tc_tag_count"] += 1

            # Count AlternateContent blocks in slides referring to think-cell
            for sp in slide_parts:
                content = z.read(sp).decode("utf-8", errors="replace")
                blocks = re.findall(
                    r"<mc:AlternateContent[^>]*>.*?</mc:AlternateContent>", content, re.DOTALL
                )
                for b in blocks:
                    if "TCLayout" in b or "think-cell" in b:
                        info["tc_alternate_content_count"] += 1

            # Process each OLE blob
            for emb in embeddings:
                blob = z.read(emb)
                cfb = _extract_one_cfb(blob)
                idx = re.search(r"oleObject(\d+)\.bin", emb).group(1)
                ole_record = {
                    "ole_path": emb,
                    "ole_index": idx,
                    "size": cfb["size"],
                    "sha256": cfb["sha256"],
                    "is_cfb": cfb["is_cfb"],
                    "stream_count": len(cfb["streams"]),
                    "stream_paths": [s["path"] for s in cfb["streams"]],
                    "has_thinkcell_xml": cfb["thinkcell_xml"] is not None,
                    "thinkcell_xml_size": cfb["thinkcell_xml_size"],
                    "thinkcell_child_xml_size": cfb["thinkcell_child_xml_size"],
                    "package_size": cfb["package_size"],
                    "error": cfb["error"],
                }
                if cfb["thinkcell_xml"]:
                    out_path = deck_out / f"ole_{idx}_think-cellXML.xml"
                    out_path.write_text(cfb["thinkcell_xml"], encoding="utf-8")
                    ole_record["thinkcell_xml_dump"] = str(out_path)
                    info["thinkcellxml_count"] += 1
                    info["thinkcellxml_total_bytes"] += cfb["thinkcell_xml_size"]
                if cfb["thinkcell_child_xml"]:
                    out_path = deck_out / f"ole_{idx}_child_layout.xml"
                    out_path.write_text(cfb["thinkcell_child_xml"], encoding="utf-8")
                    ole_record["child_xml_dump"] = str(out_path)
                if cfb.get("package_bytes"):
                    out_path = deck_out / f"ole_{idx}_Package.zip"
                    out_path.write_bytes(cfb["package_bytes"])
                    ole_record["package_dump"] = str(out_path)
                info["ole_objects"].append(ole_record)
    except Exception as e:
        info["error"] = f"{type(e).__name__}: {e}"
    return info


def _build_schema_inventory(deck_records: list[dict]) -> dict:
    elements = Counter()
    attributes = Counter()
    versioning_hits = []
    chart_classes = Counter()
    member_prefixes = Counter()
    namespace_set = set()

    for d in deck_records:
        for ole in d.get("ole_objects", []):
            if not ole.get("thinkcell_xml_dump"):
                continue
            xml_path = Path(ole["thinkcell_xml_dump"])
            xml = xml_path.read_text(encoding="utf-8", errors="replace")
            for m in re.finditer(r"<([A-Za-z_][\w-]*)\b", xml):
                elements[m.group(1)] += 1
                if m.group(1).startswith("C") and len(m.group(1)) > 2 and m.group(1)[1].isupper():
                    chart_classes[m.group(1)] += 1
                if m.group(1).startswith("m_"):
                    # Hungarian prefix: m_ + 1-2 letters
                    pm = re.match(r"m_([a-z]{1,3})", m.group(1))
                    if pm:
                        member_prefixes[pm.group(1)] += 1
            for m in re.finditer(r"\s([a-zA-Z][\w-]*)\s*=", xml):
                attributes[m.group(1)] += 1
            for m in re.finditer(r"\b(reqver|endver)\s*=\s*\"(\d+)\"", xml):
                versioning_hits.append({"attr": m.group(1), "build": int(m.group(2))})
            for m in re.finditer(r'xmlns(?::[\w-]+)?\s*=\s*"([^"]+)"', xml):
                namespace_set.add(m.group(1))

    return {
        "element_count": len(elements),
        "element_top_30": elements.most_common(30),
        "all_elements_sorted": [e for e, _ in elements.most_common()],
        "attribute_count": len(attributes),
        "attributes": attributes.most_common(),
        "chart_class_count": len(chart_classes),
        "chart_classes_top_30": chart_classes.most_common(30),
        "member_prefix_count": len(member_prefixes),
        "member_prefixes": member_prefixes.most_common(),
        "version_gate_count": len(versioning_hits),
        "version_gate_distinct_builds": sorted(set(v["build"] for v in versioning_hits)),
        "namespaces": sorted(namespace_set),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input-roots",
        nargs="+",
        default=[
            str(ROOT / "assets"),
            str(ROOT / "state" / "thinkcell_bridge" / "slide_corpus"),
        ],
    )
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--max-decks", type=int, default=200)
    args = parser.parse_args()

    output = args.output
    if output is None:
        stamp = time.strftime("%Y%m%d-%H%M%S")
        output = ROOT / "state" / "thinkcell_bridge" / "thinkcellxml_corpus" / stamp
    output.mkdir(parents=True, exist_ok=True)

    decks = []
    for root in args.input_roots:
        rp = Path(root).expanduser().resolve()
        if not rp.exists():
            print(f"[corpus] skip non-existent root: {rp}")
            continue
        for ext in ("*.pptx", "*.potx", "*.pptm"):
            for d in rp.rglob(ext):
                if d.is_file() and not d.name.startswith("~$"):
                    decks.append(d)
    decks = sorted(set(decks))[: args.max_decks]
    print(f"[corpus] processing {len(decks)} decks", flush=True)

    deck_records = []
    for i, d in enumerate(decks, 1):
        print(f"[corpus] {i}/{len(decks)}: {d.name}", flush=True)
        rec = _process_deck(d, output)
        deck_records.append(rec)

    schema = _build_schema_inventory(deck_records)

    extraction_index = {
        "schema": "simcorp-thinkcell-thinkcellxml-corpus/v1",
        "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "input_roots": args.input_roots,
        "deck_count": len(decks),
        "decks": deck_records,
        "summary": {
            "total_decks": len(decks),
            "decks_with_thinkcell": sum(1 for d in deck_records if d["thinkcellxml_count"] > 0),
            "total_charts_extracted": sum(d["thinkcellxml_count"] for d in deck_records),
            "total_thinkcellxml_bytes": sum(d["thinkcellxml_total_bytes"] for d in deck_records),
            "total_tc_tags": sum(d["tc_tag_count"] for d in deck_records),
            "total_tc_alternatecontents": sum(
                d["tc_alternate_content_count"] for d in deck_records
            ),
        },
    }
    (output / "extraction_index.json").write_text(
        json.dumps(extraction_index, indent=2), encoding="utf-8"
    )
    (output / "schema_inventory.json").write_text(json.dumps(schema, indent=2), encoding="utf-8")

    print("\n[corpus] === SUMMARY ===")
    print(f"  decks: {extraction_index['summary']['total_decks']}")
    print(f"  decks_with_charts: {extraction_index['summary']['decks_with_thinkcell']}")
    print(f"  charts_extracted: {extraction_index['summary']['total_charts_extracted']}")
    print(f"  total_xml_bytes: {extraction_index['summary']['total_thinkcellxml_bytes']:,}")
    print("\n[corpus] === SCHEMA INVENTORY ===")
    print(f"  distinct elements: {schema['element_count']}")
    print(f"  distinct attributes: {schema['attribute_count']}")
    print(f"  C++ chart classes: {schema['chart_class_count']}")
    print(f"  member prefixes: {schema['member_prefix_count']}")
    print(f"  version-gate builds: {schema['version_gate_distinct_builds']}")
    print("\n  top 20 chart classes:")
    for cls, c in schema["chart_classes_top_30"][:20]:
        print(f"    {cls:40s}  {c}")
    print("\n  top member prefixes:")
    for p, c in schema["member_prefixes"][:15]:
        print(f"    m_{p:6s}  {c}")
    print(f"\n[corpus] wrote {output}/extraction_index.json")
    print(f"[corpus] wrote {output}/schema_inventory.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
