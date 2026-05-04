#!/usr/bin/env python3
"""Regenerate the OOXML reference corpus — gate-3 of the deck-factory harness.

Builds known-good xlsx samples from each producer (openpyxl, Excel-Win,
Excel-Mac, LibreOffice). The Mac-side targets we can produce directly here;
the Excel-Win and Excel-Mac targets are produced via separate VM-side /
Mac-Office-side scripts that this file documents.

The corpus lets us answer: "what does each producer's serializer emit for
the same logical content?" — which is the only reliable way to identify
the openpyxl serialization deltas that Excel silently repairs.

Output dir: state/oxml_reference/

Sample matrix (logical content → producer):

    minimal              — workbook with one sheet "Data" + two cells (no defined names)
    one_definedname      — minimal + one global defined name "Total" → 'Data'!$A$1
    localsheet_dn        — minimal + one local-to-sheet-0 defined name
    hidden_dn            — minimal + one defined name with hidden=true
    multi_dn             — minimal + 5 defined names (test case-insensitive ordering)

For each sample, target producers:

    openpyxl_*.xlsx              — produced by this script (Mac, openpyxl 3.1+)
    excelwin_*.xlsx              — produced by scripts/vm/regen_oxml_corpus.ps1 (VM)
    excelmac_*.xlsx              — produced by scripts/mac/regen_oxml_corpus_mac.scpt (Mac Office)
    libreoffice_*.xlsx           — produced by scripts/regen_oxml_corpus_libreoffice.sh (CLI)

Usage:
    python3 scripts/regen_oxml_corpus.py
    python3 scripts/regen_oxml_corpus.py --out state/oxml_reference
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

try:
    from openpyxl import Workbook
    from openpyxl.workbook.defined_name import DefinedName
except ImportError:
    sys.stderr.write("missing dep: pip install openpyxl\n")
    sys.exit(3)


def _new_minimal() -> Workbook:
    wb = Workbook()
    ws = wb.active
    if ws is None:
        ws = wb.create_sheet("Data")
    else:
        ws.title = "Data"
    ws["A1"] = "Apples"
    ws["B1"] = 42
    ws["A2"] = "Pears"
    ws["B2"] = 7
    return wb


def emit_minimal(out_dir: Path) -> Path:
    wb = _new_minimal()
    p = out_dir / "openpyxl_minimal.xlsx"
    wb.save(p)
    return p


def emit_one_definedname(out_dir: Path) -> Path:
    wb = _new_minimal()
    wb.defined_names["Total"] = DefinedName(name="Total", attr_text="'Data'!$B$1:$B$2")
    p = out_dir / "openpyxl_one_definedname.xlsx"
    wb.save(p)
    return p


def emit_localsheet_dn(out_dir: Path) -> Path:
    wb = _new_minimal()
    # localSheetId=0 — bound to the first sheet only
    wb.defined_names["LocalTotal"] = DefinedName(
        name="LocalTotal",
        attr_text="'Data'!$B$1:$B$2",
        localSheetId=0,
    )
    p = out_dir / "openpyxl_localsheet_dn.xlsx"
    wb.save(p)
    return p


def emit_hidden_dn(out_dir: Path) -> Path:
    wb = _new_minimal()
    wb.defined_names["HiddenTotal"] = DefinedName(
        name="HiddenTotal",
        attr_text="'Data'!$B$1:$B$2",
        hidden=True,
    )
    p = out_dir / "openpyxl_hidden_dn.xlsx"
    wb.save(p)
    return p


def emit_multi_dn(out_dir: Path) -> Path:
    """5 names exercising case-insensitive ordering + alphanumerics + underscore.

    Order chosen so insertion-order != alphabetical-order — lets us see
    whether each producer normalizes ordering on save.
    """
    wb = _new_minimal()
    spec = [
        ("zeta_total", "'Data'!$B$1"),
        ("Alpha_Total", "'Data'!$B$2"),
        ("delta_Total", "'Data'!$A$1:$B$2"),
        ("BETA_total", "'Data'!$A$1"),
        ("gamma_total", "'Data'!$A$2"),
    ]
    for name, ref in spec:
        wb.defined_names[name] = DefinedName(name=name, attr_text=ref)
    p = out_dir / "openpyxl_multi_dn.xlsx"
    wb.save(p)
    return p


PRODUCERS = {
    "minimal": emit_minimal,
    "one_definedname": emit_one_definedname,
    "localsheet_dn": emit_localsheet_dn,
    "hidden_dn": emit_hidden_dn,
    "multi_dn": emit_multi_dn,
}


# Sister-script stubs — written if missing so the corpus is self-documenting.
VM_PS1 = r"""#requires -Version 5.1
<#
regen_oxml_corpus.ps1 — produce excelwin_* corpus via Excel COM on the VM.

For each of the five logical samples in scripts/regen_oxml_corpus.py we
recreate the same content via Excel.Application + Workbook.Names.Add and
save as .xlsx. The bytes Excel-Win emits are then ferried back to the Mac
under state/oxml_reference/excelwin_*.xlsx for diffing.

Run on the VM (same PowerShell session as ppttc render):
  pwsh -File scripts\vm\regen_oxml_corpus.ps1 -OutDir C:\share\oxml_reference

The Mac side ferries the output via SSH/SCP into state/oxml_reference/.
#>
param(
    [string]$OutDir = "$env:USERPROFILE\oxml_reference"
)

# TODO: implement once gate-1+gate-2 are confirmed wired end-to-end.
# Skeleton:
#   $excel = New-Object -ComObject Excel.Application
#   $wb = $excel.Workbooks.Add()
#   $ws = $wb.Sheets.Item(1); $ws.Name = 'Data'
#   $ws.Range('A1').Value = 'Apples'; $ws.Range('B1').Value = 42
#   $ws.Range('A2').Value = 'Pears';  $ws.Range('B2').Value = 7
#   $wb.Names.Add('Total', "='Data'!`$B`$1:`$B`$2")
#   $wb.SaveAs("$OutDir\excelwin_one_definedname.xlsx", 51)  # 51 = xlOpenXMLWorkbook
#   $wb.Close($false); $excel.Quit()

Write-Host 'regen_oxml_corpus.ps1 stub — to be wired after gate-1 + gate-2 verified end-to-end.'
"""


def write_vm_stub(repo_root: Path) -> None:
    target = repo_root / "scripts" / "vm" / "regen_oxml_corpus.ps1"
    if not target.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(VM_PS1, encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    p.add_argument(
        "--out",
        type=Path,
        default=Path("state/oxml_reference"),
        help="output directory (default: state/oxml_reference)",
    )
    args = p.parse_args(argv)
    out_dir: Path = args.out
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"writing openpyxl corpus → {out_dir}")
    for tag, fn in PRODUCERS.items():
        path = fn(out_dir)
        size = path.stat().st_size
        print(f"  {tag:18s}  {path.name:38s}  {size:6d}b")

    repo_root = Path(__file__).resolve().parent.parent
    write_vm_stub(repo_root)
    print("\nVM stub: scripts/vm/regen_oxml_corpus.ps1  (wire after gate-1+gate-2 verified)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
