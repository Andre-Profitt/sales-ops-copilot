"""Audit RW dashboard measures that should not silently render as zero.

The DAX execute endpoint is disabled in this tenant, so this gate validates the
Lakehouse source cohorts behind Renewal ACV and Growth Mix before the report
surface can hide a data/model problem behind `0.0`.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

import pandas as pd

WORKSPACE_ID = "b66233d5-9d4a-44ba-89a8-b70206d98ae7"
LAKEHOUSE_ID = "50f1721e-6b2e-44db-a1a7-7b8209c7a77b"
ONELAKE_TABLES = (
    f"abfss://{WORKSPACE_ID}@onelake.dfs.fabric.microsoft.com/{LAKEHOUSE_ID}/Tables"
)

DEFAULT_JSON = Path("output") / "rw_dashboard_harness" / "zero_value_audit.json"
DEFAULT_MARKDOWN = Path("docs") / "sales" / "RW_ZERO_VALUE_AUDIT.md"

Severity = Literal["info", "low", "medium", "high", "critical"]
SEVERITY_RANK: dict[Severity, int] = {
    "info": 0,
    "low": 1,
    "medium": 2,
    "high": 3,
    "critical": 4,
}

OPPORTUNITY_COLUMNS = [
    "opp_id",
    "opp_name",
    "motion_type",
    "is_closed",
    "is_won",
    "lead_source",
    "arr_org_ccy",
    "acv_org_ccy",
    "saas_acv_org_ccy",
    "axioma_order_inflow_org_ccy",
    "ps_recurring_acv_org_ccy",
]


@dataclass(frozen=True)
class MetricSpec:
    measure: str
    page: str
    family: str
    value_column: str
    nullable_zero_allowed: bool = False


def _bool_series(series: pd.Series) -> pd.Series:
    if series.dtype == bool:
        return series.fillna(False)
    return series.fillna("").astype(str).str.lower().isin({"true", "1", "yes"})


def _money(value: Any) -> float:
    if pd.isna(value):
        return 0.0
    return float(value)


def _metric_row(df: pd.DataFrame, spec: MetricSpec, mask: pd.Series) -> dict[str, Any]:
    cohort = df.loc[mask]
    values = cohort[spec.value_column] if spec.value_column in cohort else pd.Series(dtype=float)
    non_null_values = values.dropna()
    total = float(non_null_values.fillna(0).sum()) if not non_null_values.empty else 0.0
    non_zero_rows = int((non_null_values.abs() > 0.000001).sum()) if not non_null_values.empty else 0
    row_count = int(len(cohort))
    non_null_count = int(len(non_null_values))
    severity: Severity = "info"
    finding_id = ""
    message = "Source cohort has non-zero value."
    next_action = "Keep the measure on the BI surface."

    if row_count == 0:
        severity = "medium"
        finding_id = "empty_source_cohort"
        message = f"{spec.measure} has no source rows in its current source cohort."
        next_action = "Confirm the KPI should be visible for this period, or label it as no source cohort."
    elif non_null_count == 0:
        severity = "high"
        finding_id = "blank_source_field"
        message = f"{spec.measure} has {row_count} source rows but no populated {spec.value_column} values."
        next_action = f"Stage or remap the Salesforce field feeding {spec.value_column}."
    elif abs(total) <= 0.000001 and not spec.nullable_zero_allowed:
        severity = "high"
        finding_id = "zero_source_value"
        message = f"{spec.measure} sums to zero across {non_null_count} populated source values."
        next_action = "Treat the BI zero as a data/source issue until the source field is confirmed correct."

    return {
        "measure": spec.measure,
        "page": spec.page,
        "family": spec.family,
        "value_column": spec.value_column,
        "row_count": row_count,
        "non_null_value_rows": non_null_count,
        "non_zero_value_rows": non_zero_rows,
        "source_value_eur": total,
        "source_value_eur_m": total / 1_000_000,
        "severity": severity,
        "finding_id": finding_id,
        "message": message,
        "next_action": next_action,
    }


def audit_opportunity_zero_values(opportunity: pd.DataFrame) -> dict[str, Any]:
    df = opportunity.copy()
    for column in OPPORTUNITY_COLUMNS:
        if column not in df:
            df[column] = None
    is_closed = _bool_series(df["is_closed"])
    is_won = _bool_series(df["is_won"])
    motion = df["motion_type"].fillna("").astype(str)
    land_expand = motion.isin(["Land", "Expand"])
    renewal = motion.eq("Renewal")
    lead_source = df["lead_source"].fillna("").astype(str).str.lower()

    rows = [
        _metric_row(
            df,
            MetricSpec("Total Open Renewal ACV", "Renewals", "renewal_acv", "acv_org_ccy"),
            renewal & ~is_closed,
        ),
        _metric_row(
            df,
            MetricSpec("Total Renewal ACV Due", "Renewals", "renewal_acv", "acv_org_ccy"),
            renewal,
        ),
        _metric_row(
            df,
            MetricSpec("Total Renewal ACV Won", "Renewals", "renewal_acv", "acv_org_ccy"),
            renewal & is_won,
        ),
        _metric_row(
            df,
            MetricSpec("Total Renewal ACV Lost", "Renewals", "renewal_acv", "acv_org_ccy"),
            renewal & is_closed & ~is_won,
        ),
        _metric_row(
            df,
            MetricSpec("Open Land ARR", "Growth Mix", "land_expand_arr", "arr_org_ccy"),
            motion.eq("Land") & ~is_closed,
        ),
        _metric_row(
            df,
            MetricSpec("Open Expand ARR", "Growth Mix", "land_expand_arr", "arr_org_ccy"),
            motion.eq("Expand") & ~is_closed,
        ),
        _metric_row(
            df,
            MetricSpec("Partner ARR", "Growth Mix", "growth_mix", "arr_org_ccy"),
            land_expand & ~is_closed & lead_source.str.contains("partner", na=False),
        ),
        _metric_row(
            df,
            MetricSpec(
                "Cross Sell To Acquired ARR",
                "Growth Mix",
                "growth_mix",
                "axioma_order_inflow_org_ccy",
            ),
            land_expand,
        ),
        _metric_row(
            df,
            MetricSpec("SaaS ARR", "Growth Mix", "growth_mix", "saas_acv_org_ccy"),
            pd.Series(True, index=df.index),
        ),
        _metric_row(
            df,
            MetricSpec("PS Recurring ACV", "Growth Mix", "growth_mix", "ps_recurring_acv_org_ccy"),
            land_expand,
        ),
    ]

    counts = {severity: 0 for severity in SEVERITY_RANK}
    for row in rows:
        counts[row["severity"]] += 1
    findings = [row for row in rows if row["severity"] != "info"]

    return {
        "schema": "rw-zero-value-audit.v1",
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "summary": {
            "audited_metrics": len(rows),
            "finding_count": len(findings),
            "severity_counts": counts,
            "opportunity_rows": int(len(df)),
            "renewal_rows": int(renewal.sum()),
            "land_expand_rows": int(land_expand.sum()),
        },
        "metrics": rows,
        "findings": findings,
    }


def load_opportunity_from_lakehouse() -> pd.DataFrame:
    from azure.identity import AzureCliCredential
    from deltalake import DeltaTable

    token = AzureCliCredential().get_token("https://storage.azure.com/.default").token
    table = DeltaTable(
        f"{ONELAKE_TABLES}/f_opportunity",
        storage_options={"bearer_token": token, "use_fabric_endpoint": "true"},
    )
    return table.to_pyarrow_table(columns=OPPORTUNITY_COLUMNS).to_pandas()


def write_markdown(result: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    summary = result["summary"]
    lines = [
        "# RW Zero Value Audit",
        "",
        f"- Generated: `{result['generated_at']}`",
        f"- Opportunity rows inspected: `{summary['opportunity_rows']}`",
        f"- Renewal rows: `{summary['renewal_rows']}`",
        f"- Land + Expand rows: `{summary['land_expand_rows']}`",
        f"- Findings: `{summary['finding_count']}`",
        "",
        "## Metric Source Check",
        "",
        "| Severity | Page | Measure | Rows | Non-zero rows | EUR M | Finding | Next action |",
        "| --- | --- | --- | ---: | ---: | ---: | --- | --- |",
    ]
    for row in result["metrics"]:
        lines.append(
            "| "
            f"`{row['severity']}` | {row['page']} | `{row['measure']}` | "
            f"{row['row_count']} | {row['non_zero_value_rows']} | "
            f"{row['source_value_eur_m']:.1f} | {row['message']} | {row['next_action']} |"
        )
    if not result["findings"]:
        lines.extend(["", "No zero-value source findings."])
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[0])
    parser.add_argument("--csv", type=Path, help="Optional f_opportunity CSV instead of OneLake.")
    parser.add_argument("--json", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--markdown", type=Path, default=DEFAULT_MARKDOWN)
    parser.add_argument("--fail-on", choices=tuple(SEVERITY_RANK), default="critical")
    args = parser.parse_args()

    opportunity = (
        pd.read_csv(args.csv.expanduser()) if args.csv else load_opportunity_from_lakehouse()
    )
    result = audit_opportunity_zero_values(opportunity)
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    write_markdown(result, args.markdown)
    counts = result["summary"]["severity_counts"]
    print(
        f"zero-value-audit: findings={result['summary']['finding_count']} "
        + " ".join(f"{severity}={counts[severity]}" for severity in SEVERITY_RANK)
    )
    print(f"json={args.json}")
    print(f"markdown={args.markdown}")
    threshold = SEVERITY_RANK[args.fail_on]
    blocking = [
        finding
        for finding in result["findings"]
        if SEVERITY_RANK[finding["severity"]] >= threshold
    ]
    if blocking:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
