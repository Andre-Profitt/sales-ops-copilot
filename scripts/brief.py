#!/usr/bin/env python3
"""
sales-ops-copilot — Daily Sales Ops AI brief.

Pulls a Salesforce pipeline snapshot, lists Fabric/Power BI workspaces relevant
to Sales Ops, sends both to apro-openai for synthesis, writes a markdown report.

Usage:
    python3 scripts/brief.py              # default: gpt-5.3-chat
    python3 scripts/brief.py --model gpt-5.4-mini
    python3 scripts/brief.py --no-llm     # skip synthesis (data only)
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib
import subprocess
import sys
from typing import Any

from azure.identity import AzureCliCredential
from openai import AzureOpenAI

# Make scripts/ importable for `from alerts import ...`
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

# --- Config -----------------------------------------------------------------

ROOT = pathlib.Path(__file__).resolve().parent.parent
REPORTS_DIR = ROOT / "reports"

OPENAI_ENDPOINT = "https://apro-openai.openai.azure.com/"
OPENAI_API_VERSION = "2025-04-01-preview"
DEFAULT_MODEL = "gpt53chat"  # deployment name (Azure), not the OpenAI model name

# Power BI workspace IDs that matter for Sales Ops, from verified inventory.
SALES_OPS_WORKSPACES = {
    "Salesforce Analytics - Sales Manager": "b66233d5-9d4a-44ba-89a8-b70206d98ae7",
    "Microsoft Copilot Dashboard (Preview)": "6aa22f35-a160-48ae-8733-da150888c854",
    "People Analytics": "034fb371-4f05-46f9-bc85-ce8f6c846c4d",
    "Product Development": "d3fff9d2-93e9-40b1-86ce-3eaea615b8dc",
    "Client Services": "3a610325-4a4e-47fd-b692-57490811dcdc",
    "Standard Platform Prod": "195f979b-8661-49c6-b95b-c6cd09def971",
    "Axioma PD": "340af898-d16d-4b40-a29e-3dbb02d0ea50",
    "SimCorp General": "7c2d3684-3746-4dca-a9b6-21f20ed9aa21",
}


# --- Helpers ----------------------------------------------------------------


def run(cmd: list[str]) -> str:
    """Run a shell command, return stdout, raise on non-zero."""
    p = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if p.returncode != 0:
        raise RuntimeError(f"`{' '.join(cmd)}` failed: {p.stderr.strip()}")
    return p.stdout.strip()


def az_rest_pbi(uri: str) -> dict[str, Any]:
    """Call a Power BI / Fabric REST endpoint via az."""
    raw = run(
        [
            "az",
            "rest",
            "--method",
            "get",
            "--resource",
            "https://analysis.windows.net/powerbi/api",
            "--uri",
            uri,
            "-o",
            "json",
        ]
    )
    return json.loads(raw)


# --- Data pulls -------------------------------------------------------------


def _sf_query(soql: str) -> list[dict[str, Any]]:
    raw = run(["sf", "data", "query", "--query", soql, "--json"])
    return json.loads(raw).get("result", {}).get("records", [])


def _quarter_bounds(today: dt.date, offset: int) -> tuple[dt.date, dt.date, str]:
    """Return (start_date, end_date, label) for the calendar quarter `offset`
    quarters from today's quarter (0 = current, 1 = next, etc.). Calendar
    quarters: Q1 Jan-Mar, Q2 Apr-Jun, Q3 Jul-Sep, Q4 Oct-Dec."""
    q_idx = (today.month - 1) // 3  # 0..3 zero-based
    total = q_idx + offset
    new_year = today.year + total // 4
    new_q = total % 4  # 0..3
    start_month = new_q * 3 + 1
    end_month = start_month + 2
    start = dt.date(new_year, start_month, 1)
    if end_month == 12:
        end = dt.date(new_year, 12, 31)
    else:
        end = dt.date(new_year, end_month + 1, 1) - dt.timedelta(days=1)
    label = f"{new_year}-Q{new_q + 1}"
    return start, end, label


def _pull_quarter_rollup(
    start: dt.date, end: dt.date, label: str, stage_probs: dict[str, float]
) -> dict[str, Any]:
    """Pull new-business + renewal stage rollup for a single quarter window."""
    from stage_probs import weighted  # type: ignore[import-not-found]

    where_window = (
        f"IsClosed = false AND CloseDate >= {start.isoformat()} AND CloseDate <= {end.isoformat()}"
    )

    new_arr_q = (
        "SELECT StageName, COUNT(Id) num_opps, SUM(APTS_Opportunity_ARR__c) arr "
        "FROM Opportunity "
        f"WHERE {where_window} AND Type IN ('Land', 'Expand') "
        "GROUP BY StageName ORDER BY StageName"
    )
    new_business_by_stage = [
        {
            "stage": r.get("StageName"),
            "num_opps": r.get("num_opps") or 0,
            "arr": r.get("arr") or 0,
        }
        for r in _sf_query(new_arr_q)
    ]

    renewal_acv_q = (
        "SELECT StageName, COUNT(Id) num_opps, SUM(APTS_Renewal_ACV__c) acv "
        "FROM Opportunity "
        f"WHERE {where_window} AND Type = 'Renewal' "
        "GROUP BY StageName ORDER BY StageName"
    )
    renewals_by_stage = [
        {
            "stage": r.get("StageName"),
            "num_opps": r.get("num_opps") or 0,
            "acv": r.get("acv") or 0,
        }
        for r in _sf_query(renewal_acv_q)
    ]

    for row in new_business_by_stage:
        p = stage_probs.get(row.get("stage", ""), 0.0)
        row["stage_probability"] = p
        row["weighted_arr"] = (row.get("arr") or 0) * p
    for row in renewals_by_stage:
        p = stage_probs.get(row.get("stage", ""), 0.0)
        row["stage_probability"] = p
        row["weighted_acv"] = (row.get("acv") or 0) * p

    return {
        "label": label,
        "start": start.isoformat(),
        "end": end.isoformat(),
        "new_business_by_stage": new_business_by_stage,
        "renewals_by_stage": renewals_by_stage,
        "open_new_business_arr": sum(r.get("arr") or 0 for r in new_business_by_stage),
        "weighted_new_business_arr": weighted(new_business_by_stage, "arr"),
        "open_renewal_acv": sum(r.get("acv") or 0 for r in renewals_by_stage),
        "weighted_renewal_acv": weighted(renewals_by_stage, "acv"),
    }


def pull_salesforce_snapshot() -> dict[str, Any]:
    """
    Pipeline snapshot via sf CLI. Aggregates only — no client-level detail.

    SimCorp metric convention (do not blend):
      - Land + Expand deals report ARR via APTS_Opportunity_ARR__c
      - Renewal deals report ACV via APTS_Renewal_ACV__c
      - The default `Amount` field is a blended number and not used here.

    Pulls THIS_QUARTER (full Type breakdown + stage rollup) plus weighted
    multi-quarter view for Q+1 and Q+2 — same empirical stage probabilities.
    """
    today = dt.date.today()

    from stage_probs import get_stage_probabilities  # type: ignore[import-not-found]

    stage_probs, prob_source = get_stage_probabilities()

    # By Type — current quarter only (the canonical ARR vs ACV split)
    by_type_q = (
        "SELECT Type, COUNT(Id) num_opps, "
        "SUM(APTS_Opportunity_ARR__c) total_arr, "
        "SUM(APTS_Renewal_ACV__c) total_renewal_acv "
        "FROM Opportunity "
        "WHERE IsClosed = false AND CloseDate = THIS_QUARTER "
        "GROUP BY Type ORDER BY Type"
    )
    by_type = []
    for r in _sf_query(by_type_q):
        by_type.append(
            {
                "type": r.get("Type") or "(unset)",
                "num_opps": r.get("num_opps") or 0,
                "arr": r.get("total_arr") or 0,
                "renewal_acv": r.get("total_renewal_acv") or 0,
            }
        )

    # Multi-quarter rollup: current + next 2 (Q, Q+1, Q+2)
    quarters: list[dict[str, Any]] = []
    for offset in (0, 1, 2):
        start, end, label = _quarter_bounds(today, offset)
        quarters.append(_pull_quarter_rollup(start, end, label, stage_probs))

    current = quarters[0]
    next_q = quarters[1]
    q_plus_2 = quarters[2]

    return {
        "by_type": by_type,
        # Backward-compatible top-level fields = current quarter
        "new_business_by_stage": current["new_business_by_stage"],
        "renewals_by_stage": current["renewals_by_stage"],
        # Multi-quarter forecast
        "quarters": quarters,
        "totals": {
            "new_business_arr_open_this_quarter": current["open_new_business_arr"],
            "renewal_acv_open_this_quarter": current["open_renewal_acv"],
            "weighted_new_business_arr": current["weighted_new_business_arr"],
            "weighted_renewal_acv": current["weighted_renewal_acv"],
            "stage_probability_source": prob_source,
            # Forward-quarter weighted forecasts
            "weighted_new_business_arr_q_plus_1": next_q["weighted_new_business_arr"],
            "weighted_renewal_acv_q_plus_1": next_q["weighted_renewal_acv"],
            "weighted_new_business_arr_q_plus_2": q_plus_2["weighted_new_business_arr"],
            "weighted_renewal_acv_q_plus_2": q_plus_2["weighted_renewal_acv"],
        },
    }


def pull_fabric_workspace_summary() -> list[dict[str, Any]]:
    """List datasets and reports per Sales-Ops-relevant workspace."""
    out = []
    for name, ws_id in SALES_OPS_WORKSPACES.items():
        entry: dict[str, Any] = {"workspace": name, "id": ws_id}
        try:
            ds = az_rest_pbi(f"https://api.powerbi.com/v1.0/myorg/groups/{ws_id}/datasets")
            entry["datasets"] = [d.get("name") for d in ds.get("value", [])]
        except Exception as e:
            entry["datasets_error"] = str(e)[:150]
        try:
            rp = az_rest_pbi(f"https://api.powerbi.com/v1.0/myorg/groups/{ws_id}/reports")
            entry["reports"] = [r.get("name") for r in rp.get("value", [])]
        except Exception as e:
            entry["reports_error"] = str(e)[:150]
        out.append(entry)
    return out


# --- LLM synthesis ----------------------------------------------------------


def synthesize(
    sf_snapshot: dict,
    fabric_summary: list,
    alerts: list,
    owner_concentration: list,
    account_concentration: list,
    model: str,
) -> str:
    """Send aggregated metadata to apro-openai for a Sales Ops brief."""
    cred = AzureCliCredential()
    token_provider = lambda: cred.get_token("https://cognitiveservices.azure.com/.default").token

    client = AzureOpenAI(
        azure_endpoint=OPENAI_ENDPOINT,
        azure_ad_token_provider=token_provider,
        api_version=OPENAI_API_VERSION,
    )

    system = (
        "You are a Sales Operations Copilot for SimCorp. "
        "You receive (1) a Salesforce pipeline snapshot for the current quarter, "
        "(2) a list of Fabric/Power BI workspaces accessible to the user, "
        "(3) governance + hygiene alerts detected from open pipeline, "
        "(4) owner_concentration_top10 — top 10 sales reps ranked by total "
        "ARR they own that hits ANY alert category. Use this to flag "
        "concentration risk: name the top 1-2 owners by ARR and what % of "
        "the alert population they hold, and "
        "(5) account_concentration_top15 — same flagged-opp population pivoted "
        "to Account. Use this to call out the 1-2 accounts where governance "
        "debt is most concentrated (e.g. 'UBS holds X% of flagged ARR across "
        "Y deals'). Account view is what directors think in.\n\n"
        "CRITICAL metric convention — never blend these:\n"
        "- Land + Expand deals are measured in ARR (annual recurring revenue) "
        "via APTS_Opportunity_ARR__c.\n"
        "- Renewal deals are measured in ACV (annual contract value) "
        "via APTS_Renewal_ACV__c.\n"
        "- New-business pipeline ($ARR) and renewal pipeline ($ACV) are different "
        "shapes — report them separately, never sum them.\n"
        "- Always label every dollar figure as either 'ARR' (Land/Expand) or "
        "'ACV' (Renewal).\n\n"
        "SimCorp's 8-stage process: Prospecting → Discovery → Engagement → "
        "Shortlisted → Preferred → Contracting → Opt-out → Won. Per the Commercial "
        "Handbook, Commercial Approval is mandatory for ALL Land deals and for "
        "Expand deals with AER >€500k.\n\n"
        "WEIGHTED FORECAST: `totals.weighted_new_business_arr` and "
        "`totals.weighted_renewal_acv` are computed using empirical stage→Won "
        "probabilities derived from the last 4 quarters of OpportunityFieldHistory "
        "transitions (source labelled in `totals.stage_probability_source`). "
        "Use these as the realistic forecast number, NOT the raw open-pipeline "
        "total. Always show both: open ARR vs weighted ARR (= empirical likely close).\n\n"
        "MULTI-QUARTER VIEW: `quarters` is a 3-element list — current quarter, "
        "Q+1, Q+2 — each with open and weighted ARR/ACV. Use this to show the "
        "forward shape of the book. Flag if a forward quarter is suspiciously "
        "front-loaded (e.g., Q4 renewal ACV inflated by Dec 31 placeholder dates). "
        "Always cite the quarter label (e.g., 2026-Q3) when comparing.\n\n"
        "Produce a tight executive brief — 300-500 words max — with these sections:\n"
        "1) Current-quarter state — open vs weighted ARR (Land+Expand) and ACV (Renewal)\n"
        "2) **Forward forecast (Q+1, Q+2) — weighted ARR and ACV per quarter, "
        "with one sentence on the shape (front-loaded? back-loaded? Dec-31 inflated?)**\n"
        "3) **Top 3 governance/hygiene alerts to act on this week** "
        "(rank by impact, name specific deals from the samples when relevant)\n"
        "4) What to focus on this week per motion\n"
        "5) Which Fabric workspaces help most\n"
        "No fluff. Lead with the insight. Cite specific dollar amounts and deal names."
    )

    user = json.dumps(
        {
            "salesforce_pipeline_thisquarter": sf_snapshot,
            "alerts": alerts,
            "owner_concentration_top10": owner_concentration,
            "account_concentration_top15": account_concentration,
            "fabric_workspaces_available": fabric_summary,
            "today": dt.date.today().isoformat(),
        },
        indent=2,
        default=str,
    )

    # GPT-5.x family rejects non-default temperature; omit it.
    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        max_completion_tokens=1500,
    )
    return resp.choices[0].message.content or ""


# --- Render -----------------------------------------------------------------


def render_report(
    sf_snapshot: dict,
    fabric_summary: list,
    alerts: list,
    owner_concentration: list,
    account_concentration: list,
    synthesis: str | None,
    model: str,
) -> str:
    today = dt.date.today().isoformat()
    lines = [
        f"# Sales Ops Brief — {today}",
        "",
        f"*Generated by sales-ops-copilot. Model: `{model}` (apro-openai, Sweden Central).*",
        "",
    ]

    if synthesis:
        lines += ["## Synthesis", "", synthesis, ""]

    # Δ since last run (if snapshot_diff has produced one)
    diff_path = ROOT / "state" / "snapshots" / f"{dt.date.today().isoformat()}_diff.json"
    if diff_path.exists():
        diff_data = json.loads(diff_path.read_text())["diff"]
        lines += [
            "## Δ since last run",
            "",
            f"- New-business ARR: **{diff_data['new_business_arr']['delta']:+,.0f}** "
            f"(today {diff_data['new_business_arr']['today']:,.0f}, prior {diff_data['new_business_arr']['prior']:,.0f})",
            f"- Renewal ACV: **{diff_data['renewal_acv']['delta']:+,.0f}** "
            f"(today {diff_data['renewal_acv']['today']:,.0f}, prior {diff_data['renewal_acv']['prior']:,.0f})",
            "",
        ]

    # Owner concentration — single highest-leverage view of who owns the risk
    if owner_concentration:
        lines += [
            "## Owner concentration on alert population",
            "",
            "*Open opps that hit ANY alert category, rolled up by owner.*",
            "",
            "| # | Owner | # Deals | $ARR | % of top-10 |",
            "|---|---|---:|---:|---:|",
        ]
        total_top = sum(o["total_arr"] for o in owner_concentration) or 1
        for i, o in enumerate(owner_concentration, 1):
            arr = o.get("total_arr") or 0
            pct = (arr / total_top * 100) if total_top else 0
            lines.append(
                f"| {i} | {o.get('owner', '—')} | {o.get('deal_count', 0)} | "
                f"${arr:,.0f} | {pct:.0f}% |"
            )
        lines.append("")

    # Account concentration — pivots the same flagged-opp population to the
    # account dimension. Directors think in accounts, not reps.
    if account_concentration:
        lines += [
            "## Account concentration on alert population",
            "",
            "*Same flagged-opp set as above, rolled up by account. Drill in via `/account-drill <name>`.*",
            "",
            "| # | Account | # Deals | $ARR | % of top-15 |",
            "|---|---|---:|---:|---:|",
        ]
        total_top = sum(a["total_arr"] for a in account_concentration) or 1
        for i, a in enumerate(account_concentration, 1):
            arr = a.get("total_arr") or 0
            pct = (arr / total_top * 100) if total_top else 0
            lines.append(
                f"| {i} | {a.get('account', '—')} | {a.get('deal_count', 0)} | "
                f"${arr:,.0f} | {pct:.0f}% |"
            )
        lines.append("")

    # Alerts go BEFORE the data tables — these are the actionable signals
    if alerts:
        lines += ["## Active alerts", ""]
        critical = [a for a in alerts if a.get("severity") == "critical"]
        important = [a for a in alerts if a.get("severity") == "important"]
        for bucket_name, bucket in [("Critical", critical), ("Important", important)]:
            if not bucket:
                continue
            lines += [f"### {bucket_name}", ""]
            for a in bucket:
                arr = a.get("total_arr") or 0
                arr_s = f"${arr:,.0f}" if arr else "—"
                lines += [
                    f"**{a['name']}** — {a['count']} opps, {arr_s} ARR",
                    f"_{a.get('rule', '')}_",
                    "",
                ]
                samples = a.get("samples") or []
                if samples:
                    lines += [
                        "| Top deals | Stage | $ARR | Owner | Also flagged in |",
                        "|---|---|---:|---|---|",
                    ]
                    for s in samples[:3]:
                        amt = s.get("$arr") or 0
                        amt_s = f"${amt:,.0f}" if amt else "—"
                        also = s.get("also_flagged_in") or []
                        also_s = f"+{len(also)}" if also else "—"
                        lines.append(
                            f"| {s.get('name', '?')} | {s.get('stage', '—')} | "
                            f"{amt_s} | {s.get('owner', '—')} | {also_s} |"
                        )
                    lines.append("")
        lines.append("")

    totals = sf_snapshot.get("totals", {})
    new_arr = totals.get("new_business_arr_open_this_quarter") or 0
    ren_acv = totals.get("renewal_acv_open_this_quarter") or 0

    lines += [
        "## Pipeline this quarter — open, by motion",
        "",
        "*Land + Expand reported in ARR. Renewals reported in ACV. Never blended.*",
        "",
        f"- **New-business ARR** (Land + Expand): ${new_arr:,.0f}",
        f"- **Renewal ACV**: ${ren_acv:,.0f}",
        "",
        "### By Type (canonical split)",
        "",
        "| Type | # Opps | ARR | Renewal ACV |",
        "|---|---:|---:|---:|",
    ]
    for t in sf_snapshot.get("by_type", []):
        arr = t.get("arr") or 0
        acv = t.get("renewal_acv") or 0
        arr_s = f"${arr:,.0f}" if arr else "—"
        acv_s = f"${acv:,.0f}" if acv else "—"
        lines.append(f"| {t['type']} | {t['num_opps']} | {arr_s} | {acv_s} |")

    totals = sf_snapshot.get("totals", {})
    open_arr = totals.get("new_business_arr_open_this_quarter", 0) or 0
    weighted_arr = totals.get("weighted_new_business_arr", 0) or 0
    open_acv = totals.get("renewal_acv_open_this_quarter", 0) or 0
    weighted_acv = totals.get("weighted_renewal_acv", 0) or 0
    prob_source = totals.get("stage_probability_source", "—")

    lines += [
        "",
        "### Weighted forecast (empirical)",
        "",
        f"Stage probabilities: *{prob_source}*",
        "",
        "| Motion | Open | Weighted (= empirical likely close) |",
        "|---|---:|---:|",
        f"| New-business (Land+Expand) ARR | ${open_arr:,.0f} | ${weighted_arr:,.0f} |",
        f"| Renewal ACV | ${open_acv:,.0f} | ${weighted_acv:,.0f} |",
        "",
        "### Multi-quarter weighted view (Q, Q+1, Q+2)",
        "",
        "| Quarter | Open ARR | Weighted ARR | Open Renewal ACV | Weighted ACV |",
        "|---|---:|---:|---:|---:|",
    ]
    for q in sf_snapshot.get("quarters", []):
        lines.append(
            f"| {q.get('label', '—')} "
            f"| ${(q.get('open_new_business_arr') or 0):,.0f} "
            f"| ${(q.get('weighted_new_business_arr') or 0):,.0f} "
            f"| ${(q.get('open_renewal_acv') or 0):,.0f} "
            f"| ${(q.get('weighted_renewal_acv') or 0):,.0f} |"
        )

    lines += [
        "",
        "### New-business ARR by stage (Land + Expand) — current quarter",
        "",
        "| Stage | # Opps | ARR | Stage Prob | Weighted ARR |",
        "|---|---:|---:|---:|---:|",
    ]
    for r in sf_snapshot.get("new_business_by_stage", []):
        arr = r.get("arr") or 0
        arr_s = f"${arr:,.0f}" if arr else "—"
        prob = r.get("stage_probability", 0) or 0
        warr = r.get("weighted_arr", 0) or 0
        warr_s = f"${warr:,.0f}" if warr else "—"
        lines.append(f"| {r['stage']} | {r['num_opps']} | {arr_s} | {prob * 100:.1f}% | {warr_s} |")

    lines += [
        "",
        "### Renewal ACV by stage",
        "",
        "| Stage | # Opps | ACV | Stage Prob | Weighted ACV |",
        "|---|---:|---:|---:|---:|",
    ]
    for r in sf_snapshot.get("renewals_by_stage", []):
        acv = r.get("acv") or 0
        acv_s = f"${acv:,.0f}" if acv else "—"
        prob = r.get("stage_probability", 0) or 0
        wacv = r.get("weighted_acv", 0) or 0
        wacv_s = f"${wacv:,.0f}" if wacv else "—"
        lines.append(f"| {r['stage']} | {r['num_opps']} | {acv_s} | {prob * 100:.1f}% | {wacv_s} |")
    lines.append("")

    lines += ["## Fabric / Power BI workspaces inspected", ""]
    for ws in fabric_summary:
        ds = ws.get("datasets") or []
        rp = ws.get("reports") or []
        lines.append(f"### {ws['workspace']}")
        lines.append(f"- workspace ID: `{ws['id']}`")
        lines.append(f"- datasets: {', '.join(ds) if ds else '_none_'}")
        lines.append(f"- reports: {', '.join(rp) if rp else '_none_'}")
        if "datasets_error" in ws:
            lines.append(f"- datasets error: `{ws['datasets_error']}`")
        if "reports_error" in ws:
            lines.append(f"- reports error: `{ws['reports_error']}`")
        lines.append("")

    return "\n".join(lines)


# --- Main -------------------------------------------------------------------


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help="Azure OpenAI deployment name (default: gpt53chat)",
    )
    ap.add_argument("--no-llm", action="store_true", help="Skip LLM synthesis (data-only run)")
    ap.add_argument("--out", help="Output path; defaults to reports/YYYY-MM-DD.md")
    ap.add_argument(
        "--html",
        action="store_true",
        help="Also render a standalone HTML version alongside the .md",
    )
    ap.add_argument(
        "--open",
        dest="auto_open",
        action="store_true",
        help="Open the rendered HTML in the default browser after writing (implies --html)",
    )
    ap.add_argument(
        "--onedrive-publish",
        action="store_true",
        help="Atomic-write the rendered HTML to OneDrive folder for Power Automate Flow pickup.",
    )
    args = ap.parse_args()

    REPORTS_DIR.mkdir(exist_ok=True)
    out_path = (
        pathlib.Path(args.out) if args.out else REPORTS_DIR / f"{dt.date.today().isoformat()}.md"
    )

    print("→ Pulling Salesforce snapshot...")
    sf = pull_salesforce_snapshot()
    t = sf.get("totals", {})
    print(
        f"  Current Q new-business ARR: ${t.get('new_business_arr_open_this_quarter', 0):,.0f} "
        f"(weighted ${t.get('weighted_new_business_arr', 0):,.0f}) | "
        f"Renewal ACV: ${t.get('renewal_acv_open_this_quarter', 0):,.0f} "
        f"(weighted ${t.get('weighted_renewal_acv', 0):,.0f})"
    )
    print(
        f"  Forward weighted ARR — Q+1: ${t.get('weighted_new_business_arr_q_plus_1', 0):,.0f} | "
        f"Q+2: ${t.get('weighted_new_business_arr_q_plus_2', 0):,.0f} | "
        f"prob source: {t.get('stage_probability_source', '—')}"
    )

    print("→ Pulling Fabric workspace summary...")
    fabric = pull_fabric_workspace_summary()
    print(f"  Workspaces inspected: {len(fabric)}")

    print("→ Detecting governance + hygiene alerts...")
    # Deferred import keeps formatters from stripping it before sys.path is set.
    from alerts import pull_account_concentration as _pull_accounts  # type: ignore[reportMissingImports]
    from alerts import pull_all_alerts as _pull_alerts  # type: ignore[reportMissingImports]
    from alerts import pull_owner_concentration as _pull_owners  # type: ignore[reportMissingImports]

    alerts = _pull_alerts()
    crit = sum(1 for a in alerts if a.get("severity") == "critical")
    imp = sum(1 for a in alerts if a.get("severity") == "important")
    print(f"  Alerts: {crit} critical, {imp} important")

    print("→ Computing owner concentration on alert population...")
    owners = _pull_owners(top_n=10)
    if owners:
        top = owners[0]
        total = sum(o["total_arr"] for o in owners)
        pct = (top["total_arr"] / total * 100) if total else 0
        print(
            f"  Top 10 owners total: ${total:,.0f} ARR · "
            f"#1 {top['owner']}: ${top['total_arr']:,.0f} ({pct:.0f}%)"
        )

    print("→ Computing account concentration on alert population...")
    accounts = _pull_accounts(top_n=15)
    if accounts:
        top_a = accounts[0]
        total_a = sum(a["total_arr"] for a in accounts)
        pct_a = (top_a["total_arr"] / total_a * 100) if total_a else 0
        print(
            f"  Top 15 accounts total: ${total_a:,.0f} ARR · "
            f"#1 {top_a['account']}: ${top_a['total_arr']:,.0f} ({pct_a:.0f}%)"
        )

    synthesis = None
    if not args.no_llm:
        print(f"→ Synthesizing via apro-openai/{args.model}...")
        try:
            synthesis = synthesize(sf, fabric, alerts, owners, accounts, args.model)
            print(f"  Synthesis: {len(synthesis)} chars")
        except Exception as e:
            print(f"  ⚠ Synthesis failed: {e}")
            synthesis = f"_Synthesis failed: {e}_"

    report = render_report(sf, fabric, alerts, owners, accounts, synthesis, args.model)
    out_path.write_text(report, encoding="utf-8")
    print(f"\n✓ Wrote {out_path}")

    if args.html or args.auto_open or args.onedrive_publish:
        from brief_html import render_file as _render_html  # type: ignore[import-not-found]

        html_path = _render_html(out_path)
        print(f"✓ Wrote {html_path}")
        if args.auto_open:
            try:
                subprocess.run(["open", str(html_path)], check=False)
            except Exception as e:
                print(f"  ⚠ open failed: {e}")
        if args.onedrive_publish:
            # Atomic publish: copy to .tmp then os.replace — Power Automate's
            # "When a file is created" trigger fires on partial files otherwise.
            import os as _os
            import shutil as _shutil

            try:
                target_dir = (
                    pathlib.Path.home()
                    / "Library"
                    / "CloudStorage"
                    / "OneDrive-SimCorp"
                    / "Sales Ops Briefs"
                )
                target_dir.mkdir(parents=True, exist_ok=True)
                target = target_dir / html_path.name
                tmp = target.with_suffix(target.suffix + ".tmp")
                _shutil.copyfile(html_path, tmp)
                _os.replace(tmp, target)
                print(f"✓ Published to OneDrive: {target}")
            except Exception as e:
                print(f"  ⚠ OneDrive publish failed: {e}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
