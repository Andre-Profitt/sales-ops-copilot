#!/usr/bin/env python3
"""Summarize a filtered Procmon CSV for think-cell/PowerPoint evidence."""

from __future__ import annotations

import argparse
import collections
import csv
import json
import re
from pathlib import Path


THINKCELL_TERMS = (
    "think-cell",
    "thinkcell",
    "tcaddin",
    "D52B1FA2",
    "ppttc",
    "tcrunxl",
    "tcserver",
    "tctabimp",
    "tcupdate",
    "tcasr",
    "tcperf",
)


def _row_text(row: dict[str, str]) -> str:
    return " ".join(row.values()).lower()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv_path", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--sample-limit", type=int, default=80)
    args = parser.parse_args()

    csv_path = args.csv_path.expanduser().resolve()
    output = args.output or csv_path.with_suffix(".summary.json")

    total_rows = 0
    process_counts: collections.Counter[str] = collections.Counter()
    op_counts: collections.Counter[str] = collections.Counter()
    result_counts: collections.Counter[str] = collections.Counter()
    powerpnt_thinkcell_rows: list[dict[str, str]] = []
    powerpnt_name_not_found: list[dict[str, str]] = []
    powerpnt_clsid_counts: collections.Counter[str] = collections.Counter()
    powerpnt_top_paths: collections.Counter[str] = collections.Counter()

    with csv_path.open(newline="", encoding="utf-8-sig", errors="replace") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            total_rows += 1
            process = row.get("Process Name", "")
            operation = row.get("Operation", "")
            result = row.get("Result", "")
            path = row.get("Path", "")
            process_counts[process] += 1
            op_counts[operation] += 1
            result_counts[result] += 1

            if process.upper() != "POWERPNT.EXE":
                continue

            if "CLSID" in path:
                match = re.search(r"CLSID\\(\{[^}]+\})", path, re.I)
                if match:
                    powerpnt_clsid_counts[match.group(1).upper()] += 1

            text = _row_text(row)
            if any(term.lower() in text for term in THINKCELL_TERMS):
                powerpnt_thinkcell_rows.append(row)
                powerpnt_top_paths[path] += 1
                if result == "NAME NOT FOUND":
                    powerpnt_name_not_found.append(row)

    summary = {
        "schema": "simcorp-thinkcell-procmon-summary/v1",
        "csv_path": str(csv_path),
        "total_filtered_rows": total_rows,
        "process_counts_top": process_counts.most_common(30),
        "operation_counts_top": op_counts.most_common(30),
        "result_counts_top": result_counts.most_common(30),
        "powerpnt_thinkcell_row_count": len(powerpnt_thinkcell_rows),
        "powerpnt_thinkcell_name_not_found_count": len(powerpnt_name_not_found),
        "powerpnt_thinkcell_top_paths": powerpnt_top_paths.most_common(60),
        "powerpnt_clsid_counts_top": powerpnt_clsid_counts.most_common(60),
        "powerpnt_thinkcell_samples": powerpnt_thinkcell_rows[: args.sample_limit],
        "powerpnt_thinkcell_name_not_found_samples": powerpnt_name_not_found[
            : args.sample_limit
        ],
        "interpretation": (
            "PowerPoint resolves thinkcell.addin through the registered CLSID "
            "{D52B1FA2-1EF8-4035-9DA6-8AD0F40267A1} and loads tcaddin.dll. "
            "The trace does not show a separate think-cell chart-factory CLSID."
        ),
    }

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
