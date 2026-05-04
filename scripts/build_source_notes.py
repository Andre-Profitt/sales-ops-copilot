"""Emit per-slide source notes for one director.

Source notes are deterministic strings citing the underlying
worksheet/range and metric basis (Land+Expand ARR · EUR, etc.).
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

DEFAULT_NOTES = {
    "S02": "Source: brief.md exec_summary · Salesforce snapshot {snapshot}",
    "S04": "Source: model.xlsx S04_PipeMovement · Land+Expand ARR · EUR",
    "S05": "Source: model.xlsx S05_PipelineByStage · Land+Expand ARR · EUR",
    "S06": "Source: model.xlsx S06_PipelineAging · Land+Expand ARR · EUR",
    "S07": "Source: model.xlsx Top_Deals_Land · Land+Expand ARR · EUR",
    "S08": "Source: model.xlsx Top_Deals_Expand · Land+Expand ARR · EUR",
    "S09": "Source: model.xlsx Pending_Commercial_Approval · Land+Expand ARR · EUR",
    "S11": "Source: model.xlsx At_Risk_Renewals · Renewal ACV · EUR",
    "S12_footnote": "GRR proxy: Won/(Won+Lost) Renewal ACV; auto-renewals in datasheet · EUR",
    "S13": "Source: model.xlsx S13_ForecastCategory · Land+Expand ARR · EUR",
    "S15": "Source: model.xlsx S15_ByOwner · Land+Expand ARR · EUR",
    "S16": "Source: model.xlsx S16_StageByIndustry · Land+Expand ARR · EUR",
    "S17": "Source: model.xlsx S17_TerritoryPerformance · Land+Expand ARR · EUR",
    "S18": "Source: model.xlsx S18_WinsLossesQTD · Land+Expand ARR · EUR",
    "S19": "Source: model.xlsx S19_Velocity · days · Land+Expand",
    "S21": "Source: model.xlsx S21_ConcentrationRiskChart · Land+Expand ARR · EUR",
    "S22": "Source: model.xlsx S22_StaleActivity · count + ARR · Land+Expand",
    "S23": "Source: model.xlsx S23_SalesVelocity · composite formula",
    "S24": "Source: model.xlsx S24_AccountExpansion · Land+Expand ARR · EUR",
    "S25": "Source: model.xlsx S25_PipelineCreationVelocity · Land+Expand ARR · EUR",
    "S26": "Source: trends.json action_items",
    "S27": "Source: brief.md Risks",
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", default="2026-04-30")
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    notes = {k: v.format(snapshot=args.snapshot) for k, v in DEFAULT_NOTES.items()}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(notes, indent=2))
    print(f"OK: wrote {len(notes)} source notes to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
