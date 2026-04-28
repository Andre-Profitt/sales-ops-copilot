"""Phase 0 — SF org ontology scan.

For each top business SObject:
  - record count
  - field counts (total / custom / nillable / required)
  - oldest + newest LastModifiedDate (data freshness window)
  - sample of high-cardinality picklists / record types

Output:
  state/sf_audit/ontology.json  — machine-readable
  state/sf_audit/ontology.md    — human-readable summary

Usage:
  python -m scripts.sf_audit.scan
  python -m scripts.sf_audit.scan --objects Account,Opportunity,Asset,Contract
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

# Top business objects most relevant for audit. Keep tight; we can expand
# later from the SObject list once we see what's there.
DEFAULT_OBJECTS = [
    "Account",
    "Contact",
    "Lead",
    "Opportunity",
    "OpportunityLineItem",
    "Asset",
    "Contract",
    "Quote",
    "QuoteLineItem",
    "Order",
    "OrderItem",
    "Task",
    "Event",
    "Case",
    "User",
]


def _sf_json(args: list[str]) -> dict[str, Any]:
    """Run an sf CLI command, parse JSON, raise on non-zero status code."""
    proc = subprocess.run(["sf", *args, "--json"], capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        raise RuntimeError(
            f"sf {' '.join(args)} failed (rc={proc.returncode}): {proc.stderr[:500]}"
        )
    # sf prints update warnings to stderr; stdout is pure JSON
    out = proc.stdout.strip()
    # Some sf commands include a leading non-JSON line in older versions;
    # find the first '{' just in case.
    idx = out.find("{")
    if idx > 0:
        out = out[idx:]
    return json.loads(out)


def sobject_describe(name: str) -> dict[str, Any]:
    """Returns the unwrapped `result` payload — the actual describe blob."""
    envelope = _sf_json(["sobject", "describe", "--sobject", name])
    return envelope.get("result") or {}


def soql_count(soql: str) -> int:
    res = _sf_json(["data", "query", "--query", soql])
    result = res.get("result") or {}
    return int(result.get("totalSize", 0))


def soql_records(soql: str) -> list[dict[str, Any]]:
    res = _sf_json(["data", "query", "--query", soql])
    result = res.get("result") or {}
    return list(result.get("records") or [])


def freshness_window(name: str) -> tuple[str | None, str | None]:
    """Return (oldest_lastmod_iso, newest_lastmod_iso) or (None, None) if N/A."""
    try:
        oldest = soql_records(
            f"SELECT LastModifiedDate FROM {name} ORDER BY LastModifiedDate ASC LIMIT 1"
        )
        newest = soql_records(
            f"SELECT LastModifiedDate FROM {name} ORDER BY LastModifiedDate DESC LIMIT 1"
        )
    except RuntimeError:
        return (None, None)
    return (
        oldest[0]["LastModifiedDate"] if oldest else None,
        newest[0]["LastModifiedDate"] if newest else None,
    )


def summarize_fields(describe: dict[str, Any]) -> dict[str, Any]:
    fields = describe.get("fields") or []
    total = len(fields)
    custom = sum(1 for f in fields if f.get("custom"))
    required = sum(1 for f in fields if not f.get("nillable") and not f.get("defaultedOnCreate"))
    nillable = sum(1 for f in fields if f.get("nillable"))
    references = [f for f in fields if f.get("type") == "reference"]
    picklists = [f for f in fields if f.get("type") == "picklist"]
    return {
        "field_count_total": total,
        "field_count_custom": custom,
        "field_count_required": required,
        "field_count_nillable": nillable,
        "reference_field_count": len(references),
        "reference_field_examples": [
            {"name": f["name"], "to": f.get("referenceTo", [])} for f in references[:8]
        ],
        "picklist_field_count": len(picklists),
        "picklist_field_examples": [
            {
                "name": f["name"],
                "options": [v["value"] for v in (f.get("picklistValues") or [])[:6]],
            }
            for f in picklists[:5]
        ],
    }


def scan_object(name: str) -> dict[str, Any]:
    print(f"  scanning {name}...", flush=True)
    try:
        desc = sobject_describe(name)
    except RuntimeError as e:
        return {"name": name, "error": str(e)[:200]}

    record_count = soql_count(f"SELECT COUNT() FROM {name}")
    oldest, newest = freshness_window(name) if record_count else (None, None)
    field_summary = summarize_fields(desc)

    return {
        "name": name,
        "label": desc.get("label", name),
        "custom": desc.get("custom", False),
        "createable": desc.get("createable", False),
        "updateable": desc.get("updateable", False),
        "record_count": record_count,
        "oldest_last_modified": oldest,
        "newest_last_modified": newest,
        **field_summary,
    }


def render_markdown(report: dict[str, Any]) -> str:
    org_id = report.get("org_id", "?")
    scanned_at = report.get("scanned_at", "?")
    objects = report.get("objects", [])
    lines = [
        "# Salesforce Org Ontology Scan",
        "",
        f"- **Org**: `{org_id}`",
        f"- **Scanned**: {scanned_at}",
        f"- **Objects scanned**: {len(objects)}",
        "",
        "## Object summary",
        "",
        "| Object | Records | Fields (custom) | Oldest mod | Newest mod | Refs |",
        "|---|---:|---:|---|---|---:|",
    ]
    for o in objects:
        if o.get("error"):
            lines.append(f"| {o['name']} | ERR | — | — | — | — |")
            continue
        rc = f"{o['record_count']:,}"
        fc = f"{o['field_count_total']} ({o['field_count_custom']})"
        oldest = (o.get("oldest_last_modified") or "")[:10]
        newest = (o.get("newest_last_modified") or "")[:10]
        refs = o.get("reference_field_count", 0)
        lines.append(f"| {o['name']} | {rc} | {fc} | {oldest} | {newest} | {refs} |")

    lines.append("")
    lines.append("## Per-object details")
    for o in objects:
        if o.get("error"):
            lines.append(f"\n### {o['name']}\n\nERROR: {o['error']}")
            continue
        lines.append(f"\n### {o['name']} ({o.get('label')})")
        lines.append(f"- Records: {o['record_count']:,}")
        lines.append(
            f"- Fields: {o['field_count_total']} total, "
            f"{o['field_count_custom']} custom, "
            f"{o['field_count_required']} required, "
            f"{o['field_count_nillable']} nillable"
        )
        lines.append(f"- References ({o['reference_field_count']}):")
        for r in o.get("reference_field_examples", []):
            lines.append(f"  - `{r['name']}` → {r['to']}")
        if o.get("picklist_field_examples"):
            lines.append(
                f"- Picklists (sample {len(o['picklist_field_examples'])} of {o['picklist_field_count']}):"
            )
            for p in o["picklist_field_examples"]:
                lines.append(f"  - `{p['name']}`: {p['options']}")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="SF org ontology scan")
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

    print(f"Scanning {len(objects)} objects...", flush=True)
    org_info = _sf_json(["org", "display"])
    org_id = (org_info.get("result") or {}).get("id", "unknown")

    scans = [scan_object(o) for o in objects]
    report = {
        "scanned_at": dt.datetime.now(dt.UTC).isoformat(),
        "org_id": org_id,
        "objects": scans,
    }
    json_path = args.out / "ontology.json"
    md_path = args.out / "ontology.md"
    json_path.write_text(json.dumps(report, indent=2))
    md_path.write_text(render_markdown(report))
    print(f"\nWrote {json_path} and {md_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
