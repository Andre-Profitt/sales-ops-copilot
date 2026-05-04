#!/usr/bin/env python3
"""Structural OOXML diff — gate-2 partner of validate_xlsx_strict + roundtrip canary.

Compares two .xlsx (or .pptx) files at the XML-tree level, so we can see
*exactly* what Excel/PowerPoint silently rewrote during a repair pass.

Diff axes (per part):
- elements added / removed (tag path)
- attributes added / removed / modified
- text content changed
- element ordering changed (when same tag appears multiple times)

Usage:
    python3 scripts/diff_oxml.py before.xlsx after.xlsx
    python3 scripts/diff_oxml.py --json before.xlsx after.xlsx
    python3 scripts/diff_oxml.py --only xl/workbook.xml before.xlsx after.xlsx

Exit codes:
    0   identical
    1   differences found
    3   could not open one of the files
"""

from __future__ import annotations

import argparse
import json
import sys
import zipfile
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path

try:
    from lxml import etree  # type: ignore[import-untyped]
except ImportError:
    sys.stderr.write("missing dep: pip install lxml\n")
    sys.exit(3)


XML_PARTS_SUFFIX = (".xml", ".rels")


@dataclass
class PartDiff:
    part: str
    added_elements: list[str] = field(default_factory=list)
    removed_elements: list[str] = field(default_factory=list)
    attr_added: list[tuple[str, str, str]] = field(default_factory=list)  # (path, attr, value)
    attr_removed: list[tuple[str, str, str]] = field(default_factory=list)
    attr_modified: list[tuple[str, str, str, str]] = field(
        default_factory=list
    )  # (path, attr, before, after)
    text_changed: list[tuple[str, str, str]] = field(default_factory=list)  # (path, before, after)
    order_changed: list[str] = field(default_factory=list)  # parent paths

    @property
    def is_empty(self) -> bool:
        return not (
            self.added_elements
            or self.removed_elements
            or self.attr_added
            or self.attr_removed
            or self.attr_modified
            or self.text_changed
            or self.order_changed
        )

    def to_dict(self) -> dict:
        d = asdict(self)
        # tuples → lists for JSON
        d["attr_added"] = [list(t) for t in self.attr_added]
        d["attr_removed"] = [list(t) for t in self.attr_removed]
        d["attr_modified"] = [list(t) for t in self.attr_modified]
        d["text_changed"] = [list(t) for t in self.text_changed]
        return d


@dataclass
class ZipDiff:
    before: str
    after: str
    parts_added: list[str] = field(default_factory=list)
    parts_removed: list[str] = field(default_factory=list)
    binary_changed: list[str] = field(default_factory=list)
    part_diffs: list[PartDiff] = field(default_factory=list)

    @property
    def has_changes(self) -> bool:
        return bool(
            self.parts_added
            or self.parts_removed
            or self.binary_changed
            or any(not pd.is_empty for pd in self.part_diffs)
        )

    def to_dict(self) -> dict:
        return {
            "before": self.before,
            "after": self.after,
            "parts_added": self.parts_added,
            "parts_removed": self.parts_removed,
            "binary_changed": self.binary_changed,
            "part_diffs": [pd.to_dict() for pd in self.part_diffs if not pd.is_empty],
        }


def _qn(elem: etree._Element) -> str:
    """Localname (drop namespace) for a node."""
    if isinstance(elem.tag, str):
        return etree.QName(elem.tag).localname
    return str(elem.tag)


def _path(elem: etree._Element) -> str:
    """Element path from root using local names + index when siblings repeat."""
    parts: list[str] = []
    cur = elem
    while cur is not None and isinstance(cur.tag, str):
        name = _qn(cur)
        parent = cur.getparent()
        if parent is not None:
            siblings = [c for c in parent if isinstance(c.tag, str) and _qn(c) == name]
            if len(siblings) > 1:
                idx = siblings.index(cur)
                parts.append(f"{name}[{idx}]")
            else:
                parts.append(name)
        else:
            parts.append(name)
        cur = parent
    return "/" + "/".join(reversed(parts))


def _diff_attrs(before: etree._Element, after: etree._Element, path: str, pd: PartDiff) -> None:
    a_before = {etree.QName(k).localname if "{" in k else k: v for k, v in before.attrib.items()}
    a_after = {etree.QName(k).localname if "{" in k else k: v for k, v in after.attrib.items()}
    for k in a_before.keys() - a_after.keys():
        pd.attr_removed.append((path, k, a_before[k]))
    for k in a_after.keys() - a_before.keys():
        pd.attr_added.append((path, k, a_after[k]))
    for k in a_before.keys() & a_after.keys():
        if a_before[k] != a_after[k]:
            pd.attr_modified.append((path, k, a_before[k], a_after[k]))


def _diff_tree(before: etree._Element, after: etree._Element, pd: PartDiff) -> None:
    """Walk before/after pairs; record diffs.

    Pairing: by local-name + position among same-named siblings. Mirrors
    OOXML's authoring rules where order within a parent is significant.
    """
    if _qn(before) != _qn(after):
        pd.removed_elements.append(_path(before))
        pd.added_elements.append(_path(after))
        return

    path = _path(after)
    _diff_attrs(before, after, path, pd)

    t_before = (before.text or "").strip()
    t_after = (after.text or "").strip()
    if t_before != t_after:
        pd.text_changed.append((path, t_before, t_after))

    # Bucket children by local-name
    b_kids = [c for c in before if isinstance(c.tag, str)]
    a_kids = [c for c in after if isinstance(c.tag, str)]

    b_buckets: dict[str, list[etree._Element]] = {}
    a_buckets: dict[str, list[etree._Element]] = {}
    for c in b_kids:
        b_buckets.setdefault(_qn(c), []).append(c)
    for c in a_kids:
        a_buckets.setdefault(_qn(c), []).append(c)

    # Names added / removed
    for name in b_buckets.keys() - a_buckets.keys():
        for c in b_buckets[name]:
            pd.removed_elements.append(_path(c))
    for name in a_buckets.keys() - b_buckets.keys():
        for c in a_buckets[name]:
            pd.added_elements.append(_path(c))

    # Within shared name: pair by index, count gaps
    for name in b_buckets.keys() & a_buckets.keys():
        bs = b_buckets[name]
        as_ = a_buckets[name]
        n = min(len(bs), len(as_))
        for i in range(n):
            _diff_tree(bs[i], as_[i], pd)
        if len(bs) > n:
            for c in bs[n:]:
                pd.removed_elements.append(_path(c))
        if len(as_) > n:
            for c in as_[n:]:
                pd.added_elements.append(_path(c))

    # Order changes: same multiset of names, different sequence
    b_seq = [_qn(c) for c in b_kids]
    a_seq = [_qn(c) for c in a_kids]
    if Counter(b_seq) == Counter(a_seq) and b_seq != a_seq:
        pd.order_changed.append(path)


def _diff_part(part_name: str, before_bytes: bytes, after_bytes: bytes) -> PartDiff:
    pd = PartDiff(part=part_name)
    if before_bytes == after_bytes:
        return pd
    if not part_name.endswith(XML_PARTS_SUFFIX):
        # Binary part with bytes diff — can't structurally diff
        pd.text_changed.append(("/", f"<{len(before_bytes)} bytes>", f"<{len(after_bytes)} bytes>"))
        return pd
    try:
        b_root = etree.fromstring(before_bytes)
        a_root = etree.fromstring(after_bytes)
    except etree.XMLSyntaxError as e:
        pd.text_changed.append(("/", f"<unparseable: {e}>", ""))
        return pd
    _diff_tree(b_root, a_root, pd)
    return pd


def diff_zip(before_path: Path, after_path: Path, only: str | None = None) -> ZipDiff:
    zd = ZipDiff(before=str(before_path), after=str(after_path))
    with zipfile.ZipFile(before_path) as zb, zipfile.ZipFile(after_path) as za:
        b_names = set(zb.namelist())
        a_names = set(za.namelist())
        zd.parts_added = sorted(a_names - b_names)
        zd.parts_removed = sorted(b_names - a_names)
        for name in sorted(b_names & a_names):
            if only and name != only:
                continue
            b_bytes = zb.read(name)
            a_bytes = za.read(name)
            if b_bytes == a_bytes:
                continue
            if not name.endswith(XML_PARTS_SUFFIX):
                zd.binary_changed.append(name)
                continue
            zd.part_diffs.append(_diff_part(name, b_bytes, a_bytes))
    return zd


def _format_text(zd: ZipDiff) -> str:
    if not zd.has_changes:
        return f"== {zd.before} == {zd.after}\n   (identical)\n"
    lines = [f"== before: {zd.before}", f"== after:  {zd.after}", ""]
    if zd.parts_added:
        lines.append("PARTS ADDED:")
        lines.extend(f"  + {p}" for p in zd.parts_added)
    if zd.parts_removed:
        lines.append("PARTS REMOVED:")
        lines.extend(f"  - {p}" for p in zd.parts_removed)
    if zd.binary_changed:
        lines.append("BINARY PARTS CHANGED:")
        lines.extend(f"  ~ {p}" for p in zd.binary_changed)
    for pd in zd.part_diffs:
        if pd.is_empty:
            continue
        lines.append("")
        lines.append(f"PART: {pd.part}")
        for path in pd.removed_elements:
            lines.append(f"  - element {path}")
        for path in pd.added_elements:
            lines.append(f"  + element {path}")
        for path, attr, val in pd.attr_removed:
            lines.append(f"  - attr {attr}={val!r} on {path}")
        for path, attr, val in pd.attr_added:
            lines.append(f"  + attr {attr}={val!r} on {path}")
        for path, attr, before_v, after_v in pd.attr_modified:
            lines.append(f"  ~ attr {attr} on {path}: {before_v!r} -> {after_v!r}")
        for path, before_t, after_t in pd.text_changed:
            lines.append(f"  ~ text on {path}: {before_t!r} -> {after_t!r}")
        for path in pd.order_changed:
            lines.append(f"  ~ child order changed under {path}")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    p.add_argument("before", type=Path)
    p.add_argument("after", type=Path)
    p.add_argument("--json", action="store_true")
    p.add_argument("--only", help="restrict to a single part name (e.g. xl/workbook.xml)")
    args = p.parse_args(argv)

    for path in (args.before, args.after):
        if not path.exists():
            sys.stderr.write(f"file not found: {path}\n")
            return 3
    zd = diff_zip(args.before, args.after, only=args.only)
    if args.json:
        print(json.dumps(zd.to_dict(), indent=2))
    else:
        print(_format_text(zd))
    return 1 if zd.has_changes else 0


if __name__ == "__main__":
    sys.exit(main())
