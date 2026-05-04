#!/usr/bin/env python3
"""Decode all `Package` ZIP datasheets in the corpus and emit a summary.

Each think-cellXML chart embedding has a sibling `think-cellChild0/Package` stream
which is a standard xlsb (BIFF12) workbook. This probe parses every Package across
the corpus and produces a per-chart summary of the embedded datasheet shape.

Output: state/thinkcell_bridge/package_datasheet_decode/<ts>/results.json
"""

from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from pyxlsb import open_workbook

ROOT = Path(__file__).resolve().parent.parent
CORPUS_GLOB = (
    "state/thinkcell_bridge/thinkcellxml_corpus/20260502-071725/by_deck/*/ole_*_Package.zip"
)


def _decode_one(zp: Path) -> dict:
    rec: dict = {"path": str(zp.relative_to(ROOT)), "size_bytes": zp.stat().st_size}
    try:
        with open_workbook(str(zp)) as wb:
            rec["sheets"] = list(wb.sheets)
            sheet_summaries = []
            for sname in wb.sheets:
                with wb.get_sheet(sname) as s:
                    rows = list(s.rows())
                    nonempty = [[c.v for c in r if c.v is not None] for r in rows]
                    nonempty = [r for r in nonempty if r]
                    types = set()
                    for r in nonempty:
                        for v in r:
                            types.add(type(v).__name__)
                    sheet_summaries.append(
                        {
                            "name": sname,
                            "row_count": len(rows),
                            "nonempty_row_count": len(nonempty),
                            "value_types": sorted(types),
                            "first_5_nonempty_rows": nonempty[:5],
                        }
                    )
            rec["sheet_summaries"] = sheet_summaries
    except Exception as e:
        rec["error"] = f"{type(e).__name__}: {e}"
    return rec


def main():
    out_dir = (
        ROOT
        / "state"
        / "thinkcell_bridge"
        / "package_datasheet_decode"
        / time.strftime("%Y%m%d-%H%M%S")
    )
    out_dir.mkdir(parents=True, exist_ok=True)

    zips = sorted(ROOT.glob(CORPUS_GLOB))
    print(f"[pkg] {len(zips)} Package ZIPs found")

    results = []
    for zp in zips:
        rec = _decode_one(zp)
        results.append(rec)
        if "error" in rec:
            print(f"  {zp.name}: ERROR {rec['error']}")
        else:
            ss = rec.get("sheet_summaries", [{}])[0]
            print(f"  {zp.name}: rows={ss.get('nonempty_row_count')} types={ss.get('value_types')}")

    summary = {
        "schema": "thinkcell-package-datasheet-decode/v1",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "total_packages": len(results),
        "decoded_ok": sum(1 for r in results if "error" not in r),
        "errored": sum(1 for r in results if "error" in r),
        "details": results,
    }

    out_file = out_dir / "results.json"
    out_file.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    print(f"\n[pkg] wrote {out_file}")
    print(f"[pkg] decoded ok: {summary['decoded_ok']}/{summary['total_packages']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
