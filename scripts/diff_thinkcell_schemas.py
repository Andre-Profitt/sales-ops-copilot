#!/usr/bin/env python3
"""Diff the embedded `next/tcstyle` schema against the install's XSDs.

Inputs:
- The dumped baseline-style XML embedded in tcaddin.dll (RT_RCDATA #4001),
  located at:
  state/thinkcell_bridge/pe_resources/<run>/dumps/tcaddin.dll/ID10_RT_RCDATA_ID4001.xml
- The install's published XSD schemas at C:\\Program Files (x86)\\think-cell\\xml-schemas\\
  snapshot-pulled to:
  state/thinkcell_bridge/install_xml_schemas/snapshot-<date>/all_schemas.txt

Output: state/thinkcell_bridge/schema_diff/<run>/diff_report.md
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
PE_ROOT = ROOT / "state" / "thinkcell_bridge" / "pe_resources"
XSD_ROOT = ROOT / "state" / "thinkcell_bridge" / "install_xml_schemas"


def _newest(p: Path) -> Path | None:
    candidates = [c for c in p.iterdir() if c.is_dir()] if p.exists() else []
    return sorted(candidates, reverse=True)[0] if candidates else None


def _extract_xml_features(text: str) -> dict[str, object]:
    return {
        "namespaces": sorted(set(re.findall(r'xmlns(?::\w+)?\s*=\s*"([^"]+)"', text))),
        "root_elements": sorted(set(re.findall(r"<\s*([A-Za-z][\w\-]+)[\s>]", text)))[:200],
        "element_counts": Counter(re.findall(r"<\s*([A-Za-z][\w\-]+)[\s>/]", text)).most_common(50),
        "attribute_names": sorted(set(re.findall(r'\s([a-zA-Z_][\w\-]+)\s*=\s*"', text)))[:200],
        "size_chars": len(text),
        "schema_locations": sorted(set(re.findall(r'schemaLocation\s*=\s*"([^"]+)"', text))),
    }


def _split_install_schemas(blob: str) -> dict[str, str]:
    parts: dict[str, str] = {}
    current_name = None
    current_buf: list[str] = []
    for line in blob.splitlines():
        m = re.match(r"^==\s*(.+?)\s*==\s*$", line)
        if m:
            if current_name is not None:
                parts[current_name] = "\n".join(current_buf)
            current_name = m.group(1)
            current_buf = []
        else:
            current_buf.append(line)
    if current_name is not None:
        parts[current_name] = "\n".join(current_buf)
    return parts


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pe-run", type=Path, default=None)
    parser.add_argument("--xsd-snapshot", type=Path, default=None)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()

    pe_run = args.pe_run or _newest(PE_ROOT)
    xsd_snap = args.xsd_snapshot or _newest(XSD_ROOT)
    if not pe_run or not xsd_snap:
        raise SystemExit(f"missing input dirs: pe_run={pe_run}, xsd_snap={xsd_snap}")

    embedded_path = pe_run / "dumps" / "tcaddin.dll" / "ID10_RT_RCDATA_ID4001.xml"
    if not embedded_path.exists():
        raise SystemExit(f"embedded style XML not found at {embedded_path}")

    install_blob_path = xsd_snap / "all_schemas.txt"
    if not install_blob_path.exists():
        raise SystemExit(f"installed schemas blob not found at {install_blob_path}")

    embedded_text = embedded_path.read_text(encoding="utf-8", errors="replace")
    install_blob = install_blob_path.read_text(encoding="utf-8", errors="replace")
    install_parts = _split_install_schemas(install_blob)

    embedded_feats = _extract_xml_features(embedded_text)
    install_feats = {
        name: _extract_xml_features(content)
        for name, content in install_parts.items()
        if "<" in content
    }

    # Find a comparable style XSD on disk
    candidate_xsds = [
        (name, feats)
        for name, feats in install_feats.items()
        if "tcstyle" in name.lower() or any("tcstyle" in ns for ns in feats.get("namespaces", []))
    ]
    candidate_xsds.sort(key=lambda kv: -kv[1]["size_chars"])

    out_dir = args.output or (ROOT / "state" / "thinkcell_bridge" / "schema_diff" / pe_run.name)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_md = out_dir / "diff_report.md"
    out_json = out_dir / "diff_data.json"

    embedded_ns = set(embedded_feats["namespaces"])
    embedded_attrs = set(embedded_feats["attribute_names"])
    embedded_elems = set(embedded_feats["root_elements"])

    diffs = []
    for name, feats in candidate_xsds:
        installed_ns = set(feats["namespaces"])
        installed_attrs = set(feats["attribute_names"])
        installed_elems = set(feats["root_elements"])
        diffs.append(
            {
                "install_path": name,
                "install_size": feats["size_chars"],
                "namespace_diff_only_embedded": sorted(embedded_ns - installed_ns),
                "namespace_diff_only_installed": sorted(installed_ns - embedded_ns),
                "elements_only_embedded": sorted(embedded_elems - installed_elems)[:60],
                "elements_only_installed": sorted(installed_elems - embedded_elems)[:60],
                "attributes_only_embedded": sorted(embedded_attrs - installed_attrs)[:60],
                "attributes_only_installed": sorted(installed_attrs - embedded_attrs)[:60],
            }
        )

    payload = {
        "schema": "simcorp-thinkcell-schema-diff/v1",
        "embedded": {
            "path": str(embedded_path),
            "features": embedded_feats,
        },
        "install_snapshot": {
            "path": str(xsd_snap),
            "file_count": len(install_parts),
            "candidate_tcstyle_count": len(candidate_xsds),
        },
        "diffs": diffs,
    }
    out_json.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    lines = [
        "# next/tcstyle vs install xml-schemas diff",
        "",
        f"- Embedded source: `{embedded_path}` ({embedded_feats['size_chars']} chars)",
        f"- Install snapshot: `{xsd_snap}` ({len(install_parts)} files)",
        f"- Candidate tcstyle XSDs in install: **{len(candidate_xsds)}**",
        "",
        "## Embedded baseline namespaces",
    ]
    for ns in embedded_feats["namespaces"]:
        lines.append(f"- `{ns}`")
    lines += ["", "## Per-XSD diffs", ""]
    if not diffs:
        lines.append("_No tcstyle-related XSDs found in install snapshot._")
    for d in diffs:
        lines += [
            f"### {d['install_path']}",
            f"- size: {d['install_size']} chars",
            f"- namespaces only in embedded: {d['namespace_diff_only_embedded']}",
            f"- namespaces only in installed: {d['namespace_diff_only_installed']}",
            f"- elements only in embedded ({len(d['elements_only_embedded'])}): {d['elements_only_embedded']}",
            f"- elements only in installed ({len(d['elements_only_installed'])}): {d['elements_only_installed']}",
            f"- attributes only in embedded ({len(d['attributes_only_embedded'])}): {d['attributes_only_embedded']}",
            f"- attributes only in installed ({len(d['attributes_only_installed'])}): {d['attributes_only_installed']}",
            "",
        ]
    out_md.write_text("\n".join(lines), encoding="utf-8")
    print(f"wrote {out_md}")
    print(f"wrote {out_json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
