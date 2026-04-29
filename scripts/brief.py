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


def _sf_access_token_and_instance() -> tuple[str, str]:
    """Get a Salesforce access token + instance URL via the sf CLI."""
    raw = run(["sf", "org", "display", "--target-org", "preprod", "--json"])
    d = json.loads(raw).get("result", {})
    return d.get("accessToken", ""), d.get("instanceUrl", "")


def _sf_analytics_get(path: str) -> dict[str, Any]:
    """GET an SF Analytics REST endpoint (e.g. /analytics/reports/<id>).

    Used to fetch FX-correct grand totals + per-cell ARR from existing
    SF reports. Per AGENTS.md SimCorp rules, prefer report-side
    aggregation over raw SOQL SUM (multi-currency unconverted).
    """
    import urllib.error
    import urllib.request

    token, instance = _sf_access_token_and_instance()
    url = f"{instance}/services/data/v66.0{path}"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        raise RuntimeError(
            f"SF Analytics GET {path} failed: HTTP {e.code} {e.read().decode()[:300]}"
        ) from e


# Live SF report IDs for FX-correct pulls used in the brief.
PIPELINE_AGE_REPORT_ID = "00OTb000008ndGjMAI"  # Scorecard · Pipeline Age Distribution
PIPELINE_AGE_BY_REP_REPORT_ID = "00OTb000008nfTdMAI"  # Scorecard · Pipeline Age by Rep


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

    product_family_breakdown = pull_product_family_breakdown()
    # FX-correct via SF report aggregation (per AGENTS.md SimCorp rules:
    # never raw SOQL SUM on currency fields; trust report-side `s!field`).
    try:
        pipeline_age = pull_pipeline_age()
        zombie_owners = pull_zombie_owners(top_n=5)
    except Exception as e:
        # Don't fail the whole brief if these reports can't be reached.
        print(f"  [WARN] pipeline-age pull failed: {e}", file=sys.stderr)
        pipeline_age = {}
        zombie_owners = []

    return {
        "by_type": by_type,
        "product_family_breakdown": product_family_breakdown,
        "pipeline_age": pipeline_age,
        "zombie_owners": zombie_owners,
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


def pull_product_family_breakdown(top_n: int = 12) -> list[dict[str, Any]]:
    from _filters import EXCLUDE_TEST_ARTIFACTS  # type: ignore[import-not-found,import-untyped]

    try:
        from ack import soql_exclusion  # type: ignore[import-not-found]

        ack_excl = soql_exclusion()
    except Exception:
        ack_excl = ""

    soql = (
        "SELECT Id, APTS_RH_Product_Family__c, APTS_Opportunity_ARR__c "
        "FROM Opportunity "
        "WHERE IsClosed = false AND Type IN ('Land', 'Expand') "
        "AND APTS_RH_Product_Family__c != null "
        f"{EXCLUDE_TEST_ARTIFACTS}{ack_excl} "
        "LIMIT 5000"
    )
    records = _sf_query(soql)

    agg: dict[str, dict[str, float]] = {}
    for r in records:
        raw = r.get("APTS_RH_Product_Family__c") or ""
        arr = r.get("APTS_Opportunity_ARR__c") or 0
        for fam in (f.strip() for f in raw.split(";") if f.strip()):
            entry = agg.setdefault(fam, {"num_opps": 0, "arr_open": 0.0})
            entry["num_opps"] += 1
            entry["arr_open"] += arr

    rows = [
        {"family": fam, "num_opps": int(v["num_opps"]), "arr_open": float(v["arr_open"])}
        for fam, v in agg.items()
    ]
    rows.sort(key=lambda x: x["arr_open"], reverse=True)
    return rows[:top_n]


def pull_pipeline_age() -> dict[str, Any]:
    """Pull org-level open Land+Expand pipeline by deal-age bucket.

    FX-correct via SF report aggregation (`s!APTS_Opportunity_ARR__c`
    is converted to org currency by the report engine). Returns:

        {
          "buckets": [{"label": "0-90d", "count": ..., "arr": ...}, ...],
          "total_arr": ...,
          "total_count": ...,
          "zombie_arr": ...,   # >2yr bucket
          "zombie_pct": ...,
          "stale_1yr_plus_arr": ...,  # 1-2yr + 2yr+
          "stale_1yr_plus_pct": ...,
        }
    """
    r = _sf_analytics_get(f"/analytics/reports/{PIPELINE_AGE_REPORT_ID}?includeDetails=false")
    fact = r.get("factMap", {})
    gd = r.get("groupingsDown", {}).get("groupings", [])
    buckets = []
    for g in gd:
        key = g.get("key")
        label = g.get("label", "?")
        cell = fact.get(f"{key}!T", {}).get("aggregates", [])
        arr = cell[0].get("value", 0) if len(cell) > 0 else 0
        cnt = cell[1].get("value", 0) if len(cell) > 1 else 0
        buckets.append({"label": label, "count": cnt, "arr": arr})
    total = fact.get("T!T", {}).get("aggregates", [])
    total_arr = total[0].get("value", 0) if len(total) > 0 else 0
    total_cnt = total[1].get("value", 0) if len(total) > 1 else 0
    by_label = {b["label"]: b for b in buckets}
    zombie_arr = (by_label.get("2yr+") or {}).get("arr", 0)
    one_yr_plus = zombie_arr + (by_label.get("1-2yr") or {}).get("arr", 0)
    return {
        "buckets": buckets,
        "total_arr": total_arr,
        "total_count": int(total_cnt),
        "zombie_arr": zombie_arr,
        "zombie_pct": (zombie_arr / total_arr * 100) if total_arr else 0,
        "stale_1yr_plus_arr": one_yr_plus,
        "stale_1yr_plus_pct": (one_yr_plus / total_arr * 100) if total_arr else 0,
    }


def pull_zombie_owners(top_n: int = 5) -> list[dict[str, Any]]:
    """Top N reps by absolute >2yr open Land+Expand ARR.

    FX-correct via SF report aggregation. Each row shows the rep's
    total open ARR + their >2yr (zombie) cut + the ratio.
    """
    r = _sf_analytics_get(
        f"/analytics/reports/{PIPELINE_AGE_BY_REP_REPORT_ID}?includeDetails=false"
    )
    fact = r.get("factMap", {})
    gd = r.get("groupingsDown", {}).get("groupings", [])
    ga = r.get("groupingsAcross", {}).get("groupings", [])
    zombie_key = next((ag.get("key") for ag in ga if ag.get("label") == "2yr+"), None)
    if not zombie_key:
        return []
    rows = []
    for g in gd:
        key = g.get("key")
        owner = g.get("label", "?")
        total_cell = fact.get(f"{key}!T", {}).get("aggregates", [])
        total_arr = total_cell[0].get("value", 0) if total_cell else 0
        zombie_cell = fact.get(f"{key}!{zombie_key}", {}).get("aggregates", [])
        zombie_arr = zombie_cell[0].get("value", 0) if zombie_cell else 0
        rows.append(
            {
                "owner": owner,
                "total_arr": total_arr,
                "zombie_arr": zombie_arr,
                "zombie_pct": (zombie_arr / total_arr * 100) if total_arr else 0,
            }
        )
    rows.sort(key=lambda x: x["zombie_arr"], reverse=True)
    return rows[:top_n]


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
        "PRODUCT FAMILY BREAKDOWN: `product_family_breakdown` lists open "
        "Land+Expand ARR aggregated by `APTS_RH_Product_Family__c`. The field is "
        "a multipicklist — opps with multiple families are counted toward each, "
        "so the sum across families OVERSTATES total open ARR. Call out the top "
        "1-2 families by ARR and any concentration concerns (e.g., a single "
        "family carrying the bulk of pipeline).\n\n"
        "PIPELINE AGE / ZOMBIES: `pipeline_age` is the FX-correct age "
        "distribution of open Land+Expand pipeline (sourced from the SF report, "
        "not raw SOQL — multi-currency-converted). Key fields: `zombie_arr` and "
        "`zombie_pct` are the >2yr-old slice (deals that should have closed long "
        "ago — likely indefinitely-pushed losses hidden in pipeline). "
        "`stale_1yr_plus_pct` is the >1yr cumulative. Win rate is GAMEABLE — "
        "deals indefinitely pushed never enter the denominator — so the zombie "
        "ratio is the antidote metric. If `zombie_pct` is >25%, call it a "
        "forecast-hygiene crisis and recommend a force-reconciliation review.\n\n"
        "ZOMBIE OWNERS: `zombie_owners` lists the top 5 reps by absolute >2yr "
        "ARR exposure, with `total_arr`, `zombie_arr`, `zombie_pct` per rep. "
        "These are the highest-leverage 1:1 coaching priorities. Call out the "
        "single worst by `zombie_pct` (gaming ratio) AND the worst by "
        "`zombie_arr` (absolute exposure) — usually different reps.\n\n"
        "Produce a tight executive brief — 300-500 words max — with these sections:\n"
        "1) Current-quarter state — open vs weighted ARR (Land+Expand) and ACV (Renewal); "
        "include a one-line sub-callout on where the ARR sits by product line (top 1-2 families)\n"
        "2) **Forward forecast (Q+1, Q+2) — weighted ARR and ACV per quarter, "
        "with one sentence on the shape (front-loaded? back-loaded? Dec-31 inflated?)**\n"
        "3) **Pipeline health — zombie %, top zombie owner, what % of book is >1yr.** "
        "Frame this as the pipeline-quality counterweight to win-rate (which is gameable).\n"
        "4) **Top 3 governance/hygiene alerts to act on this week** "
        "(rank by impact, name specific deals from the samples when relevant)\n"
        "5) What to focus on this week per motion\n"
        "6) Which Fabric workspaces help most\n"
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


# --- Alert trend persistence (7-day trailing) -------------------------------


def _alert_snap_path(date: dt.date) -> pathlib.Path:
    return ROOT / "state" / "snapshots" / f"{date.isoformat()}_alerts.json"


def _persist_alert_counts_today(alerts: list[dict[str, Any]]) -> None:
    today = dt.date.today()
    path = _alert_snap_path(today)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload: dict[str, Any] = {
        "date": today.isoformat(),
        "counts": {a.get("name", ""): int(a.get("count") or 0) for a in alerts},
        "total_arr": {a.get("name", ""): float(a.get("total_arr") or 0) for a in alerts},
    }
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2))
    tmp.replace(path)


def _load_trailing_alert_counts(days: int = 7, exclude_today: bool = True) -> dict[str, list[int]]:
    """Return {alert_name: [count, count, ...]} from up to `days` prior sidecar files."""
    today = dt.date.today()
    out: dict[str, list[int]] = {}
    for offset in range(1 if exclude_today else 0, days + 1):
        d = today - dt.timedelta(days=offset)
        p = _alert_snap_path(d)
        if not p.exists():
            continue
        try:
            data = json.loads(p.read_text())
        except Exception:
            continue
        for name, count in (data.get("counts") or {}).items():
            out.setdefault(name, []).append(int(count))
    return out


def _trend_callout(name: str, today_count: int, trailing: dict[str, list[int]]) -> str:
    history = trailing.get(name) or []
    if len(history) < 3:
        return ""
    avg = sum(history) / len(history)
    if avg <= 0:
        return f"7-day avg: {avg:.1f} ◆"
    delta_ratio = (today_count - avg) / avg
    if abs(delta_ratio) <= 0.05:
        glyph = "◆"
    elif delta_ratio > 0:
        glyph = "▲"
    else:
        glyph = "▼"
    return f"7-day avg: {avg:.1f} {glyph}"


# --- Render -----------------------------------------------------------------


def render_report(
    sf_snapshot: dict,
    fabric_summary: list,
    alerts: list,
    owner_concentration: list,
    account_concentration: list,
    synthesis: str | None,
    model: str,
    radar_recs: list | None = None,
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
        _persist_alert_counts_today(alerts)
        trailing = _load_trailing_alert_counts(days=7, exclude_today=True)
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
                trend_s = _trend_callout(a.get("name", ""), int(a.get("count") or 0), trailing)
                head = f"**{a['name']}** — {a['count']} opps, {arr_s} ARR"
                if trend_s:
                    head = f"{head} ({trend_s})"
                lines += [
                    head,
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

    pfb = sf_snapshot.get("product_family_breakdown") or []
    if pfb:
        lines += [
            "",
            "### Open Land+Expand ARR by Product Family",
            "",
            "*Multipicklist field — opps with multiple families count toward each. "
            "Sum across families exceeds total open ARR by design.*",
            "",
            "| # | Product Family | # Opps | ARR |",
            "|---|---|---:|---:|",
        ]
        for i, p in enumerate(pfb, 1):
            arr = p.get("arr_open") or 0
            lines.append(f"| {i} | {p.get('family', '—')} | {p.get('num_opps', 0)} | ${arr:,.0f} |")

    # Pipeline health — FX-correct via SF report aggregation.
    # The antidote to gameable win-rate metrics: deals indefinitely
    # pushed never enter the won/lost denominator; the >2yr zombie
    # cohort surfaces them.
    pipeline_age = sf_snapshot.get("pipeline_age") or {}
    zombie_owners = sf_snapshot.get("zombie_owners") or []
    if pipeline_age:
        total_arr = pipeline_age.get("total_arr", 0) or 0
        zombie_arr = pipeline_age.get("zombie_arr", 0) or 0
        zombie_pct = pipeline_age.get("zombie_pct", 0) or 0
        stale_pct = pipeline_age.get("stale_1yr_plus_pct", 0) or 0
        lines += [
            "",
            "### Pipeline health — zombie detection (FX-correct)",
            "",
            f"**EUR {total_arr:,.0f} open Land+Expand pipeline · "
            f"{zombie_pct:.0f}% (EUR {zombie_arr:,.0f}) is >2 years old.**",
            "",
            f"_{stale_pct:.0f}% of the open book is >1 year old. "
            f"Indefinitely-pushed deals never enter the win/loss denominator — "
            f"the zombie ratio is the antidote to gameable win-rate metrics._",
            "",
            "| Age band | # Opps | ARR | % of total |",
            "|---|---:|---:|---:|",
        ]
        for b in pipeline_age.get("buckets", []):
            arr = b.get("arr") or 0
            cnt = b.get("count") or 0
            pct = (arr / total_arr * 100) if total_arr else 0
            lines.append(f"| {b.get('label', '—')} | {cnt} | EUR {arr:,.0f} | {pct:.1f}% |")
    if zombie_owners:
        lines += [
            "",
            "### Top zombie owners — coaching 1:1 priority",
            "",
            "*Reps ranked by absolute >2yr ARR exposure. `Zombie %` shows "
            "how much of their book is over 2 years old — the gaming ratio.*",
            "",
            "| # | Owner | Total open ARR | >2yr ARR | Zombie % |",
            "|---|---|---:|---:|---:|",
        ]
        for i, z in enumerate(zombie_owners, 1):
            tot = z.get("total_arr") or 0
            zar = z.get("zombie_arr") or 0
            zpct = z.get("zombie_pct") or 0
            lines.append(
                f"| {i} | {z.get('owner', '—')} | EUR {tot:,.0f} | EUR {zar:,.0f} | {zpct:.0f}% |"
            )

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

    # Tooling/ecosystem signals from radar — actionable recs (must_try +
    # should_try, status=proposed). Sidebar to the SF pipeline; closes the
    # "notice → decide" half of the radar outcome loop. nice_to_know is
    # filtered out (clamped behind verification gate).
    if radar_recs:
        must = [r for r in radar_recs if r.get("severity") == "must_try"]
        should = [r for r in radar_recs if r.get("severity") == "should_try"]
        lines += [
            "## Tooling/ecosystem signals (radar)",
            "",
            f"*{len(radar_recs)} actionable recommendation"
            f"{'' if len(radar_recs) == 1 else 's'} from the radar capability scout — "
            f"{len(must)} must_try, {len(should)} should_try (status=proposed). "
            "Source: `~/code/apps/radar/state/radar.db`. "
            "To act: `radar reevaluate-recs --rec-id <id>` after verifying claims, "
            "or upcoming `/radar-triage` to decide accept/reject/snooze.*",
            "",
        ]
        for bucket_name, bucket in [("Must try", must), ("Should try", should)]:
            if not bucket:
                continue
            lines += [f"### {bucket_name}", ""]
            for rec in bucket:
                summary = rec.get("summary", "—")
                lines += [
                    f"**{summary}**",
                    f"- Type: `{rec.get('type', '—')}` · "
                    f"Entity: `{rec.get('entity', '—')}` · "
                    f"Confidence: {rec.get('confidence', 0):.2f} · "
                    f"Evidence: {rec.get('evidence_strength', '—')} · "
                    f"Blast: {rec.get('blast_radius', '—')} · "
                    f"{rec.get('citation_count', 0)} citation"
                    f"{'' if rec.get('citation_count', 0) == 1 else 's'}",
                    f"- Rec ID: `{rec.get('rec_id', '?')}`",
                    "",
                ]

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
    ap.add_argument(
        "--pdf",
        action="store_true",
        help="Also render a memo-grade PDF version alongside the .md (via WeasyPrint).",
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

    print("→ Pulling actionable radar recommendations...")
    from radar_recs import pull_actionable_recs as _pull_recs  # type: ignore[reportMissingImports]

    radar_recs = _pull_recs()
    if radar_recs:
        must = sum(1 for r in radar_recs if r.get("severity") == "must_try")
        should = len(radar_recs) - must
        print(f"  Actionable recs: {must} must_try, {should} should_try")
    else:
        print("  No actionable recs (radar.db missing or empty actionable surface)")

    synthesis = None
    if not args.no_llm:
        print(f"→ Synthesizing via apro-openai/{args.model}...")
        try:
            synthesis = synthesize(sf, fabric, alerts, owners, accounts, args.model)
            print(f"  Synthesis: {len(synthesis)} chars")
        except Exception as e:
            print(f"  ⚠ Synthesis failed: {e}")
            synthesis = f"_Synthesis failed: {e}_"

    report = render_report(
        sf, fabric, alerts, owners, accounts, synthesis, args.model, radar_recs=radar_recs
    )
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

    if args.pdf:
        try:
            from brief_pdf import render_file as _render_pdf  # type: ignore[import-not-found]

            pdf_path = _render_pdf(out_path)
            print(f"✓ Wrote {pdf_path}")
        except Exception as e:
            print(f"  ⚠ PDF render failed: {e}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
