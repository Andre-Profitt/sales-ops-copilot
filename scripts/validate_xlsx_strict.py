#!/usr/bin/env python3
"""Strict OOXML SpreadsheetML validator — gate 1 of the deck-factory harness.

Goal: catch xlsx files that openpyxl produced and Excel will refuse to open
cleanly (open-repair-close), BEFORE we ship them to the VM for ppttc render.

Spec references (ECMA-376 / ISO 29500-1):
- §18.2     Workbook
- §18.2.6   definedNames
- §18.2.20  sheets
- §22.9.2.19 ST_Xstring (definedName/@name grammar)

Pre-write usage:
    python3 scripts/validate_xlsx_strict.py path/to/land.model.xlsx
    python3 scripts/validate_xlsx_strict.py --json path/to/*.xlsx

Exit codes:
    0   clean (no fail-level findings)
    1   fail-level findings (ship-blocking)
    2   warn-level findings (review before ship)
    3   could not open file at all
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import zipfile
from dataclasses import asdict, dataclass, field
from pathlib import Path

try:
    from lxml import etree  # type: ignore[import-untyped]
except ImportError:
    sys.stderr.write("missing dep: pip install lxml\n")
    sys.exit(3)

NS_MAIN = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
NS = {"x": NS_MAIN}

# ECMA-376 §18.2 child-order of <workbook>: relative order matters for Excel
# even though the schema is xsd:choice. Excel's own serializer always emits
# this order; deviating triggers a repair pass on some Excel builds.
WORKBOOK_CHILD_ORDER = [
    "fileVersion",
    "fileSharing",
    "workbookPr",
    "workbookProtection",
    "bookViews",
    "sheets",
    "functionGroups",
    "externalReferences",
    "definedNames",
    "calcPr",
    "oleSize",
    "customWorkbookViews",
    "pivotCaches",
    "smartTagPr",
    "smartTagTypes",
    "webPublishing",
    "fileRecoveryPr",
    "webPublishObjects",
    "extLst",
]

# §22.9.2.19 + name grammar in [MS-XLSX] §2.2.2.
# Names: must start with letter or underscore, then letters / digits / period /
# underscore. Single-letter names allowed (R, C, etc. except those that look
# like cell refs in A1/R1C1 are treated as names per §18.2.5 if outside grid).
NAME_RE = re.compile(r"^[A-Za-z_\\][A-Za-z0-9_.]*$")
# Cell-ref range Excel reserves (A1..XFD1048576).
CELLREF_RE = re.compile(r"^[A-Z]{1,3}[1-9][0-9]*$")
# R1C1 forms that Excel reserves.
R1C1_RE = re.compile(r"^R[0-9]+C[0-9]+$|^R[0-9]+$|^C[0-9]+$", re.IGNORECASE)


@dataclass
class Finding:
    level: str  # "fail" | "warn" | "info"
    rule: str
    message: str
    location: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Report:
    path: str
    sheets: list[str] = field(default_factory=list)
    defined_names_count: int = 0
    findings: list[Finding] = field(default_factory=list)

    def add(self, level: str, rule: str, message: str, location: str = "") -> None:
        self.findings.append(Finding(level, rule, message, location))

    @property
    def fails(self) -> list[Finding]:
        return [f for f in self.findings if f.level == "fail"]

    @property
    def warns(self) -> list[Finding]:
        return [f for f in self.findings if f.level == "warn"]

    def to_dict(self) -> dict:
        return {
            "path": self.path,
            "sheets": self.sheets,
            "defined_names_count": self.defined_names_count,
            "fail_count": len(self.fails),
            "warn_count": len(self.warns),
            "findings": [f.to_dict() for f in self.findings],
        }


def _open_workbook_xml(zf: zipfile.ZipFile) -> etree._Element:
    with zf.open("xl/workbook.xml") as fh:
        return etree.parse(fh).getroot()


def _check_zip_structure(zf: zipfile.ZipFile, rep: Report) -> None:
    names = set(zf.namelist())
    required = {
        "[Content_Types].xml",
        "_rels/.rels",
        "xl/workbook.xml",
        "xl/_rels/workbook.xml.rels",
    }
    for r in required:
        if r not in names:
            rep.add("fail", "opc.required-part", f"missing required part: {r}")


def _check_workbook_child_order(root: etree._Element, rep: Report) -> None:
    children = [etree.QName(c).localname for c in root if isinstance(c.tag, str)]
    seen_indexes: list[tuple[str, int]] = []
    for c in children:
        if c in WORKBOOK_CHILD_ORDER:
            seen_indexes.append((c, WORKBOOK_CHILD_ORDER.index(c)))
    for i in range(1, len(seen_indexes)):
        prev_name, prev_idx = seen_indexes[i - 1]
        cur_name, cur_idx = seen_indexes[i]
        if cur_idx < prev_idx:
            rep.add(
                "warn",
                "workbook.child-order",
                f"<{cur_name}> appears after <{prev_name}> "
                f"(expected order: {' -> '.join(WORKBOOK_CHILD_ORDER)})",
                location="xl/workbook.xml",
            )


def _check_sheets(root: etree._Element, rep: Report) -> list[str]:
    sheets = root.find("x:sheets", NS)
    if sheets is None:
        rep.add("fail", "workbook.sheets.missing", "no <sheets> element")
        return []
    names: list[str] = []
    sheet_ids: set[str] = set()
    for s in sheets.findall("x:sheet", NS):
        name = s.get("name")
        sid = s.get("sheetId")
        if not name:
            rep.add("fail", "sheet.name.missing", "<sheet> missing @name")
            continue
        if sid in sheet_ids:
            rep.add(
                "fail", "sheet.id.duplicate", f"duplicate sheetId={sid}", location=f"sheet:{name}"
            )
        sheet_ids.add(sid)
        names.append(name)
    return names


def _check_defined_names(root: etree._Element, sheet_names: list[str], rep: Report) -> int:
    block = root.find("x:definedNames", NS)
    if block is None:
        return 0
    entries = block.findall("x:definedName", NS)
    n = len(entries)
    if n == 0:
        return 0

    seen: set[tuple[str, str | None]] = set()
    prev_key: str | None = None
    for dn in entries:
        name = dn.get("name") or ""
        local_sheet_id = dn.get("localSheetId")
        refers_to = (dn.text or "").strip()
        loc = f"definedName:{name}"

        # Required: name + non-empty refersTo
        if not name:
            rep.add("fail", "definedName.name.missing", "<definedName> has no @name", location=loc)
            continue
        if not refers_to:
            rep.add("fail", "definedName.refersTo.empty", "empty <definedName> body", location=loc)

        # Name grammar
        if not NAME_RE.match(name):
            rep.add(
                "fail",
                "definedName.name.grammar",
                f"name does not match Excel name grammar: {name!r}",
                location=loc,
            )

        # Names that look like cell refs are reserved
        if CELLREF_RE.match(name) or R1C1_RE.match(name):
            rep.add(
                "fail",
                "definedName.name.cellref-conflict",
                f"name {name!r} collides with cell reference space (A1/R1C1)",
                location=loc,
            )

        # localSheetId must be a 0-based integer < len(sheet_names)
        if local_sheet_id is not None:
            try:
                lsi = int(local_sheet_id)
                if lsi < 0 or lsi >= len(sheet_names):
                    rep.add(
                        "fail",
                        "definedName.localSheetId.range",
                        f"localSheetId={lsi} out of range (sheets={len(sheet_names)})",
                        location=loc,
                    )
            except ValueError:
                rep.add(
                    "fail",
                    "definedName.localSheetId.type",
                    f"localSheetId must be int, got {local_sheet_id!r}",
                    location=loc,
                )

        # refersTo: detect #REF!
        if "#REF!" in refers_to:
            rep.add(
                "fail",
                "definedName.refersTo.broken",
                f"refersTo contains #REF!: {refers_to!r}",
                location=loc,
            )

        # refersTo: sheet-name with non-alphanumeric must be quoted
        # very-rough heuristic — split on '!' and check the prefix
        if "!" in refers_to:
            prefix = refers_to.split("!", 1)[0]
            # Allow $ for absolute prefix on whole-row/whole-col, but for
            # sheet-prefixed refs this is purely the sheet-name portion.
            if not prefix.startswith("'"):
                inner = prefix.lstrip("=")
                if inner and not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", inner):
                    rep.add(
                        "warn",
                        "definedName.refersTo.unquoted-sheet",
                        f"sheet name in refersTo not single-quoted: {refers_to!r}",
                        location=loc,
                    )

        # Duplicate (name, localSheetId) pair → Excel rejects on load
        key = (name, local_sheet_id)
        if key in seen:
            rep.add(
                "fail",
                "definedName.duplicate",
                f"duplicate definedName (name={name!r}, localSheetId={local_sheet_id})",
                location=loc,
            )
        seen.add(key)

        # Ordering: Excel-Win 2024 emits names case-insensitive ascending;
        # openpyxl preserves insertion order. Verified on baseline xlsx —
        # insertion-order files open clean in Excel, so this is INFO only.
        cur_key = name.lower()
        if prev_key is not None and cur_key < prev_key:
            rep.add(
                "info",
                "definedName.order",
                f"insertion order, not alphabetical: {name!r} after {prev_key!r}",
                location=loc,
            )
        prev_key = cur_key

    return n


def validate(path: Path) -> Report:
    rep = Report(path=str(path))
    if not path.exists():
        rep.add("fail", "file.missing", f"file not found: {path}")
        return rep
    try:
        zf = zipfile.ZipFile(path, "r")
    except zipfile.BadZipFile as e:
        rep.add("fail", "zip.invalid", f"not a valid zip: {e}")
        return rep
    with zf:
        _check_zip_structure(zf, rep)
        try:
            root = _open_workbook_xml(zf)
        except (KeyError, etree.XMLSyntaxError) as e:
            rep.add("fail", "workbook.xml.parse", f"could not parse xl/workbook.xml: {e}")
            return rep

        _check_workbook_child_order(root, rep)
        rep.sheets = _check_sheets(root, rep)
        rep.defined_names_count = _check_defined_names(root, rep.sheets, rep)
    return rep


def _format_text(rep: Report) -> str:
    lines = [f"== {rep.path}"]
    lines.append(f"   sheets: {len(rep.sheets)}   defined_names: {rep.defined_names_count}")
    if not rep.findings:
        lines.append("   clean")
        return "\n".join(lines)
    lines.append(f"   FAIL: {len(rep.fails)}   WARN: {len(rep.warns)}")
    for f in rep.findings:
        prefix = {"fail": "  [FAIL]", "warn": "  [warn]", "info": "  [info]"}[f.level]
        loc = f" ({f.location})" if f.location else ""
        lines.append(f"{prefix} {f.rule}: {f.message}{loc}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    p.add_argument("paths", nargs="+", type=Path, help="xlsx files to validate")
    p.add_argument("--json", action="store_true", help="emit JSON instead of text")
    p.add_argument("--quiet", action="store_true", help="only emit failures (text mode)")
    args = p.parse_args(argv)

    reports = [validate(path) for path in args.paths]
    worst = 0
    if args.json:
        out = {"reports": [r.to_dict() for r in reports]}
        print(json.dumps(out, indent=2))
    else:
        for r in reports:
            if args.quiet and not r.fails:
                continue
            print(_format_text(r))
    for r in reports:
        if r.fails:
            worst = max(worst, 1)
        elif r.warns:
            worst = max(worst, 2)
    return worst


if __name__ == "__main__":
    sys.exit(main())
