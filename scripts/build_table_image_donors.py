#!/usr/bin/env python3
"""Build named think-cell Table-as-Image donor PPTX files.

The base donor is a real Excel-created think-cell "Table as Image" object.
Each output PPTX is the same donor with the embedded think-cellXML
``m_strName`` rewritten to one LAND table target name.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from ppttc_template import template_named_elements
from thinkcell_cfb import CfbStreamEdit, replace_cfb_stream_data


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_BASE = ROOT / "assets" / "LAND_thinkcell_table_image_donor.pptx"
DEFAULT_OUTPUT_DIR = ROOT / "state" / "thinkcell_bridge" / "table_image_donors"

TABLE_IMAGE_TARGETS = (
    "S04_ReviewDeltaTargets",
    "S05_ForecastQualityTable",
    "S06_HygieneSignals",
    "S07_TopDealsLand",
    "S08_TopDealsExpand",
    "S09_PendingCommercialApproval",
    "S11_RenewalPipeline",
    "S12_GRRProxyTable",
    "S13_ForecastCategoryDetail",
    "S16_OwnerCoaching",
    "S18_QTDLossSpine",
    "S19_DealHygieneSignals",
    "S21_ConcentrationTable",
    "S22_NamedRiskTriage",
    "S23_OperatingRhythm",
    "S24_AccountExpansion",
    "S25_Next14DaysCadence",
    "S26_ActionItems",
    "S27_DecisionChecklist",
)


def build_donor(base: Path, output: Path, name: str) -> None:
    old = b"<m_strName>ProbeTableImage</m_strName>"
    new = f"<m_strName>{name}</m_strName>".encode("utf-8")
    touched = 0
    replacements = 0

    output.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(base) as zin, ZipFile(output, "w", ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            data = zin.read(item.filename)
            if item.filename.startswith("ppt/embeddings/") and item.filename.endswith(".bin"):
                result = replace_cfb_stream_data(
                    data,
                    (
                        CfbStreamEdit(
                            name="think-cellXML",
                            replacements=((old, new),),
                        ),
                    ),
                )
                data = result.data
                touched += result.streams_touched
                replacements += result.replacements_made
            zout.writestr(item, data)

    names = template_named_elements(output)
    if name not in names or touched != 1 or replacements != 1:
        raise SystemExit(
            f"failed to build named donor {name}: "
            f"touched={touched} replacements={replacements} names={sorted(names)}"
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", type=Path, default=DEFAULT_BASE)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()

    if not args.base.exists():
        raise SystemExit(f"missing base donor: {args.base}")

    for name in TABLE_IMAGE_TARGETS:
        output = args.output_dir / f"{name}.pptx"
        build_donor(args.base, output, name)
        print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
