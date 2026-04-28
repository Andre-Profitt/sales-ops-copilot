"""Phase 1 — SF data-quality scan.

For each object in the target list:
  1. Custom-field fill rate (sample 1,000 most-recent records via FIELDS(CUSTOM))
  2. Staleness buckets by LastModifiedDate (<30d / 30-180d / 180d-1y / 1-5y / >5y)
  3. Object-specific dirty-data flags (open-stale, phantom-active, missing keys, etc.)

Output:
  state/sf_audit/dq.json — per-object metrics, machine-readable
  state/sf_audit/dq.md   — human-readable report with top-line table + Top-20 fixes

Usage:
  ~/code/apps/sales-ops-copilot/.venv/bin/python -m scripts.sf_audit.dq
  python -m scripts.sf_audit.dq --objects Account,Lead

Constraints:
  - Stays under 200 SOQL queries total (≈ 1 describe + 1 fill-rate sample +
    1 count + 5 staleness buckets + ~5 dirty flags per object × 8 objects ≈ 100)
  - Reuses _sf_json envelope-unwrap pattern from scan.py
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path
from typing import Any

from scripts.sf_audit.scan import _sf_json, sobject_describe, soql_count, soql_records

DEFAULT_OBJECTS = [
    "Account",
    "Opportunity",
    "Lead",
    "Contact",
    "Apttus_Config2__AssetLineItem__c",
    "Contract",
    "Case",
    "Task",
]

# SF caps SELECT FIELDS(CUSTOM) at LIMIT 200 (MALFORMED_QUERY otherwise).
# The task description suggested 1,000 — honour the SF hard cap instead.
FILL_RATE_SAMPLE = 200
LOW_FILL_THRESHOLD = 0.20  # below 20% = suspicious

# Computed/system field types — values are derived, not user-entered, so
# missing values do not indicate "dirty" data. Skip these from low-fill flagging.
COMPUTED_FIELD_TYPES = {"summary", "calculated"}  # roll-up summary, formula


def _collect_describe(obj: str) -> dict[str, Any]:
    return sobject_describe(obj)


def _custom_editable_fields(describe: dict[str, Any]) -> list[dict[str, Any]]:
    """Custom fields excluding formulas + roll-up summaries (those are computed)."""
    out = []
    for f in describe.get("fields") or []:
        if not f.get("custom"):
            continue
        if f.get("type") in COMPUTED_FIELD_TYPES:
            continue
        if f.get("calculatedFormula"):
            continue
        out.append(f)
    return out


def _sample_fill_rate(obj: str) -> tuple[int, dict[str, dict[str, Any]]]:
    """Sample up to 1,000 most-recent records via SELECT FIELDS(CUSTOM).

    Returns (sample_size, {field_name: {"non_null": N, "rate": float}})
    """
    soql = (
        f"SELECT FIELDS(CUSTOM) FROM {obj} ORDER BY LastModifiedDate DESC LIMIT {FILL_RATE_SAMPLE}"
    )
    try:
        records = soql_records(soql)
    except RuntimeError as e:
        return 0, {"__error__": {"non_null": 0, "rate": 0.0, "error": str(e)[:200]}}

    n = len(records)
    if n == 0:
        return 0, {}

    # FIELDS(CUSTOM) returns every custom field even if all values are null —
    # iterate union of keys present across all records. attributes is the only
    # non-field key we strip.
    field_keys: set[str] = set()
    for r in records:
        field_keys.update(k for k in r.keys() if k != "attributes")

    counts: dict[str, dict[str, Any]] = {}
    for fname in sorted(field_keys):
        non_null = sum(1 for r in records if r.get(fname) not in (None, "", [], {}))
        counts[fname] = {
            "non_null": non_null,
            "sample_size": n,
            "rate": round(non_null / n, 4),
        }
    return n, counts


def _flag_low_fill(
    fill_rates: dict[str, dict[str, Any]], editable_fields: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Return list of {name, type, rate, non_null} for fields below threshold.

    Only flags fields that are user-editable custom (non-formula, non-rollup).
    """
    editable_names = {f["name"]: f for f in editable_fields}
    flagged = []
    for fname, stats in fill_rates.items():
        if fname == "__error__":
            continue
        if fname not in editable_names:
            continue
        if stats["rate"] >= LOW_FILL_THRESHOLD:
            continue
        f = editable_names[fname]
        flagged.append(
            {
                "name": fname,
                "type": f.get("type"),
                "label": f.get("label"),
                "rate": stats["rate"],
                "non_null": stats["non_null"],
                "sample_size": stats["sample_size"],
            }
        )
    flagged.sort(key=lambda x: x["rate"])
    return flagged


def _staleness_buckets(obj: str) -> dict[str, int]:
    """Return staleness counts using LastModifiedDate buckets."""
    today = dt.datetime.now(dt.UTC).date()
    cutoffs = {
        "lt_30d": today - dt.timedelta(days=30),
        "lt_180d": today - dt.timedelta(days=180),
        "lt_365d": today - dt.timedelta(days=365),
        "lt_1825d": today - dt.timedelta(days=1825),  # 5y
    }

    def _cnt(where: str) -> int:
        try:
            return soql_count(f"SELECT COUNT() FROM {obj} WHERE {where}")
        except RuntimeError:
            return -1

    # Compute monotonic counts then derive buckets.
    n_lt_30 = _cnt(f"LastModifiedDate >= {cutoffs['lt_30d'].isoformat()}T00:00:00Z")
    n_lt_180 = _cnt(f"LastModifiedDate >= {cutoffs['lt_180d'].isoformat()}T00:00:00Z")
    n_lt_365 = _cnt(f"LastModifiedDate >= {cutoffs['lt_365d'].isoformat()}T00:00:00Z")
    n_lt_5y = _cnt(f"LastModifiedDate >= {cutoffs['lt_1825d'].isoformat()}T00:00:00Z")
    total = soql_count(f"SELECT COUNT() FROM {obj}")

    return {
        "total": total,
        "bucket_lt_30d": n_lt_30,
        "bucket_30_180d": max(0, n_lt_180 - n_lt_30),
        "bucket_180d_1y": max(0, n_lt_365 - n_lt_180),
        "bucket_1_5y": max(0, n_lt_5y - n_lt_365),
        "bucket_gt_5y": max(0, total - n_lt_5y),
        "stale_gt_1y": max(0, total - n_lt_365),
    }


def _dirty_flags(obj: str) -> list[dict[str, Any]]:
    """Object-specific dirty-data counts. Each entry: {flag, count, soql}."""
    flags: list[dict[str, Any]] = []

    def _add(flag_name: str, soql: str) -> None:
        try:
            n = soql_count(soql)
        except RuntimeError as e:
            flags.append({"flag": flag_name, "count": -1, "soql": soql, "error": str(e)[:200]})
            return
        flags.append({"flag": flag_name, "count": n, "soql": soql})

    if obj == "Lead":
        _add(
            "open_stale_lead_gt_90d",
            "SELECT COUNT() FROM Lead WHERE Status IN ('Open - Not Contacted','Working - Contacted') "
            "AND LastModifiedDate < LAST_N_DAYS:90",
        )
        _add("converted_false_total", "SELECT COUNT() FROM Lead WHERE IsConverted=false")
    elif obj == "Opportunity":
        _add(
            "open_stale_opp_gt_90d",
            "SELECT COUNT() FROM Opportunity WHERE IsClosed=false "
            "AND LastModifiedDate < LAST_N_DAYS:90",
        )
        _add(
            "past_close_date_open",
            "SELECT COUNT() FROM Opportunity WHERE CloseDate < TODAY AND IsClosed=false",
        )
        _add("open_total", "SELECT COUNT() FROM Opportunity WHERE IsClosed=false")
    elif obj == "Contract":
        _add("status_created", "SELECT COUNT() FROM Contract WHERE Status='Created'")
        _add(
            "status_draft_gt_180d",
            "SELECT COUNT() FROM Contract WHERE Status='Draft' AND LastModifiedDate < LAST_N_DAYS:180",
        )
    elif obj == "Apttus_Config2__AssetLineItem__c":
        # Past EndDate, not cancelled — broad phantom-active count
        _add(
            "past_enddate_activated",
            "SELECT COUNT() FROM Apttus_Config2__AssetLineItem__c "
            "WHERE Apttus_Config2__EndDate__c < TODAY "
            "AND Apttus_Config2__AssetStatus__c='Activated'",
        )
        _add(
            "past_enddate_any_noncancelled",
            "SELECT COUNT() FROM Apttus_Config2__AssetLineItem__c "
            "WHERE Apttus_Config2__EndDate__c < TODAY "
            "AND Apttus_Config2__AssetStatus__c NOT IN ('Cancelled','Expired')",
        )
        _add(
            "missing_start_date",
            "SELECT COUNT() FROM Apttus_Config2__AssetLineItem__c "
            "WHERE Apttus_Config2__StartDate__c = NULL",
        )
    elif obj == "Account":
        _add("missing_billing_country", "SELECT COUNT() FROM Account WHERE BillingCountry = NULL")
        _add("missing_industry", "SELECT COUNT() FROM Account WHERE Industry = NULL")
        # Inactive owner — relationship traversal
        _add(
            "owner_inactive",
            "SELECT COUNT() FROM Account WHERE Owner.IsActive=false",
        )
    elif obj == "Contact":
        _add("missing_email", "SELECT COUNT() FROM Contact WHERE Email = NULL")
        _add("missing_account", "SELECT COUNT() FROM Contact WHERE AccountId = NULL")
        _add(
            "email_bounced",
            "SELECT COUNT() FROM Contact WHERE EmailBouncedDate != NULL",
        )
    elif obj == "Task":
        _add(
            "owner_inactive",
            "SELECT COUNT() FROM Task WHERE Owner.IsActive=false",
        )
    elif obj == "Case":
        _add(
            "owner_inactive",
            "SELECT COUNT() FROM Case WHERE Owner.IsActive=false",
        )

    return flags


def scan_object(obj: str) -> dict[str, Any]:
    print(f"  scanning {obj}...", flush=True)
    out: dict[str, Any] = {"name": obj}
    try:
        describe = _collect_describe(obj)
    except RuntimeError as e:
        out["error"] = f"describe failed: {str(e)[:200]}"
        return out

    editable = _custom_editable_fields(describe)
    out["custom_editable_field_count"] = len(editable)

    # 1) fill rate
    print("    fill-rate sample...", flush=True)
    sample_n, fill_rates = _sample_fill_rate(obj)
    out["fill_rate_sample_size"] = sample_n
    if "__error__" in fill_rates:
        out["fill_rate_error"] = fill_rates["__error__"].get("error")
    out["low_fill_fields"] = _flag_low_fill(fill_rates, editable)

    # 2) staleness
    print("    staleness buckets...", flush=True)
    out["staleness"] = _staleness_buckets(obj)

    # 3) dirty flags
    print("    dirty flags...", flush=True)
    out["dirty_flags"] = _dirty_flags(obj)

    return out


def _build_top20(scans: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Flatten all dirty flags + stale-gt-1y across objects, rank by count desc."""
    rows: list[dict[str, Any]] = []
    for s in scans:
        if s.get("error"):
            continue
        obj = s["name"]
        for f in s.get("dirty_flags", []):
            n = f.get("count", 0)
            if n is None or n <= 0:
                continue
            rows.append(
                {
                    "object": obj,
                    "kind": "dirty_flag",
                    "label": f["flag"],
                    "count": n,
                }
            )
        stale = s.get("staleness", {}).get("stale_gt_1y", 0)
        if stale and stale > 0:
            rows.append(
                {
                    "object": obj,
                    "kind": "staleness",
                    "label": "stale_gt_1y",
                    "count": stale,
                }
            )
    rows.sort(key=lambda r: r["count"], reverse=True)
    return rows[:20]


def render_markdown(report: dict[str, Any]) -> str:
    scanned_at = report.get("scanned_at", "?")
    org_id = report.get("org_id", "?")
    scans = report.get("objects", [])
    lines: list[str] = [
        "# Salesforce Data-Quality Scan",
        "",
        f"- **Org**: `{org_id}`",
        f"- **Scanned**: {scanned_at}",
        f"- **Objects scanned**: {len(scans)}",
        f"- **Low-fill threshold**: <{int(LOW_FILL_THRESHOLD * 100)}% on {FILL_RATE_SAMPLE}-record sample",
        "",
        "## Top-line",
        "",
        "| Object | Records | Custom (editable) | <20% fill | >1y stale | Dirty flags total |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for s in scans:
        if s.get("error"):
            lines.append(f"| {s['name']} | ERR | — | — | — | — |")
            continue
        name = s["name"]
        rec = s.get("staleness", {}).get("total", 0)
        editable = s.get("custom_editable_field_count", 0)
        low_fill = len(s.get("low_fill_fields", []))
        stale1y = s.get("staleness", {}).get("stale_gt_1y", 0)
        dirty_total = sum(max(0, f.get("count", 0)) for f in s.get("dirty_flags", []))
        lines.append(
            f"| {name} | {rec:,} | {editable} | {low_fill} | {stale1y:,} | {dirty_total:,} |"
        )

    # Top-20 fixes
    lines.append("")
    lines.append("## Top 20 fixes by record count")
    lines.append("")
    lines.append("| # | Object | Issue | Count |")
    lines.append("|---:|---|---|---:|")
    for i, r in enumerate(_build_top20(scans), 1):
        lines.append(f"| {i} | {r['object']} | {r['label']} | {r['count']:,} |")

    # Per-object detail
    lines.append("")
    lines.append("## Per-object detail")

    for s in scans:
        lines.append("")
        if s.get("error"):
            lines.append(f"### {s['name']}\n\nERROR: {s['error']}")
            continue
        name = s["name"]
        st = s.get("staleness", {})
        lines.append(f"### {name}")
        lines.append("")
        lines.append(
            f"- Records: **{st.get('total', 0):,}**  · "
            f"editable custom fields: {s.get('custom_editable_field_count', 0)}  · "
            f"fill-rate sample: {s.get('fill_rate_sample_size', 0)}"
        )
        lines.append(
            "- Staleness: "
            f"<30d {st.get('bucket_lt_30d', 0):,} · "
            f"30-180d {st.get('bucket_30_180d', 0):,} · "
            f"180d-1y {st.get('bucket_180d_1y', 0):,} · "
            f"1-5y {st.get('bucket_1_5y', 0):,} · "
            f">5y {st.get('bucket_gt_5y', 0):,}"
        )
        if s.get("fill_rate_error"):
            lines.append(f"- Fill-rate sample error: `{s['fill_rate_error']}`")

        low = s.get("low_fill_fields", [])
        if low:
            lines.append("")
            lines.append(
                f"**Bottom-fill custom fields ({len(low)} below {int(LOW_FILL_THRESHOLD * 100)}%)**"
            )
            lines.append("")
            lines.append("| Field | Type | Fill rate | Non-null / sample |")
            lines.append("|---|---|---:|---|")
            for f in low[:20]:
                pct = f"{f['rate'] * 100:.1f}%"
                lines.append(
                    f"| `{f['name']}` | {f['type']} | {pct} | {f['non_null']} / {f['sample_size']} |"
                )
            if len(low) > 20:
                lines.append(f"| … | _{len(low) - 20} more_ | | |")

        flags = s.get("dirty_flags", [])
        if flags:
            lines.append("")
            lines.append("**Dirty-data flags**")
            lines.append("")
            lines.append("| Flag | Count |")
            lines.append("|---|---:|")
            for f in flags:
                cnt = f.get("count", -1)
                cnt_str = "ERR" if cnt is None or cnt < 0 else f"{cnt:,}"
                lines.append(f"| `{f['flag']}` | {cnt_str} |")

    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="SF data-quality scan")
    parser.add_argument(
        "--objects",
        type=str,
        default=",".join(DEFAULT_OBJECTS),
        help="comma-separated SObject API names",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("state/sf_audit"),
        help="output directory (default: state/sf_audit)",
    )
    args = parser.parse_args()

    objects = [o.strip() for o in args.objects.split(",") if o.strip()]
    args.out.mkdir(parents=True, exist_ok=True)

    print(f"DQ scan over {len(objects)} objects...", flush=True)
    org_info = _sf_json(["org", "display"])
    org_id = (org_info.get("result") or {}).get("id", "unknown")

    scans = [scan_object(o) for o in objects]
    report = {
        "scanned_at": dt.datetime.now(dt.UTC).isoformat(),
        "org_id": org_id,
        "low_fill_threshold": LOW_FILL_THRESHOLD,
        "fill_rate_sample": FILL_RATE_SAMPLE,
        "objects": scans,
    }
    json_path = args.out / "dq.json"
    md_path = args.out / "dq.md"
    json_path.write_text(json.dumps(report, indent=2))
    md_path.write_text(render_markdown(report))
    print(f"\nWrote {json_path} and {md_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
