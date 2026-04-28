#!/usr/bin/env python3
# pyright: reportMissingImports=false
"""
Sales Ops — Commercial Health & Governance cockpit PDF.

Two-page consulting-style dashboard rendered via WeasyPrint. Reuses
`pull_salesforce_snapshot`, `pull_all_alerts`, and `get_stage_probabilities`
from sister scripts; never re-implements a query.

Hard rules:
- ARR (Land/Expand) and ACV (Renewal) reported separately. Never blended.
- Gaps marked honestly with em-dash + footnote. No fabricated numbers.
- Output: reports/cockpit-<today>.pdf
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import pathlib
import subprocess
import sys
from typing import Any

# WeasyPrint dlopens pango/cairo via Homebrew on Apple Silicon — must set
# DYLD_FALLBACK_LIBRARY_PATH BEFORE the weasyprint import. Same pattern as
# brief_pdf.py.
_BREW_LIB = "/opt/homebrew/lib"
if os.path.isdir(_BREW_LIB):
    existing = os.environ.get("DYLD_FALLBACK_LIBRARY_PATH", "")
    if _BREW_LIB not in existing.split(":"):
        os.environ["DYLD_FALLBACK_LIBRARY_PATH"] = (
            f"{_BREW_LIB}:{existing}" if existing else _BREW_LIB
        )

# Make scripts/ importable for sibling pulls.
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from weasyprint import CSS, HTML  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent
REPORTS_DIR = ROOT / "reports"
SNAP_DIR = ROOT / "state" / "snapshots"

# Reference layout uses navy + greys + a red banner + amber/green status pills.
COLORS = {
    "navy": "#1f3a5f",
    "navy_dark": "#16273f",
    "navy_soft": "#eef2f8",
    "red": "#b22222",
    "red_soft": "#fbe9e9",
    "amber": "#d97706",
    "amber_soft": "#fef3c7",
    "green": "#1e7d3a",
    "green_soft": "#dcf2e3",
    "blue": "#2563a8",
    "muted": "#6b7280",
    "border": "#d1d5db",
    "bg_soft": "#f6f8fa",
}

# Stage 3+ pattern matches the alert module convention.
STAGE_3PLUS_LIKE = (
    "(StageName LIKE '3%' OR StageName LIKE '4%' OR StageName LIKE '5%' OR StageName LIKE '6%')"
)

STAGE_FUNNEL_BUCKETS = [
    ("Stage 1-2", ("1", "2")),
    ("Stage 3", ("3",)),
    ("Stage 4", ("4",)),
    ("Commit (5-6)", ("5", "6")),
]


# --- helpers ----------------------------------------------------------------


def _money(v: float | int | None, *, large: bool = False) -> str:
    if v is None or v == 0:
        return "—"
    v = float(v)
    if large and abs(v) >= 1_000_000:
        return f"${v / 1_000_000:.1f}M"
    if large and abs(v) >= 1_000:
        return f"${v / 1_000:.0f}K"
    return f"${v:,.0f}"


def _sf(soql: str) -> list[dict[str, Any]]:
    p = subprocess.run(
        ["sf", "data", "query", "--query", soql, "--json"],
        capture_output=True,
        text=True,
        check=False,
    )
    if p.returncode != 0:
        return []
    try:
        return json.loads(p.stdout).get("result", {}).get("records", [])
    except json.JSONDecodeError:
        return []


def _stage_bucket(stage: str | None, prefixes: tuple[str, ...]) -> bool:
    if not stage:
        return False
    return any(stage.startswith(p) for p in prefixes)


# --- field probe ------------------------------------------------------------


def probe_discount_field() -> tuple[str | None, float | None, int]:
    """Return (field_used, avg_pct, sample_n) or (None, None, 0).

    `Apttus_Proposal__Discount_Percent__c` exists on Opportunity but is not
    populated for any open FY2026 deals (verified 2026-04-28: n=0). We probe
    once and surface whatever we find — this stays honest if data lands later.
    """
    field = "Apttus_Proposal__Discount_Percent__c"
    rows = _sf(
        f"SELECT COUNT(Id) n, AVG({field}) avg_disc FROM Opportunity "
        f"WHERE IsClosed = false AND CloseDate = THIS_YEAR AND {field} != null"
    )
    if not rows:
        return None, None, 0
    n = int(rows[0].get("n") or 0)
    avg = rows[0].get("avg_disc")
    if n == 0 or avg is None:
        return field, None, 0
    return field, float(avg), n


# --- top deals --------------------------------------------------------------


def pull_top_deals(limit: int = 8) -> list[dict[str, Any]]:
    """Top open Land/Expand opps at Stage 3+ for FY (this calendar year),
    ranked by ARR. Account, ARR, Stage, CloseDate, plus governance flags
    (Commercial Approval, KYC). Discount/AUM not populated — left as '—'."""
    from _filters import EXCLUDE_TEST_ARTIFACTS  # type: ignore[import-not-found]

    soql = (
        "SELECT Id, Name, Account.Name, StageName, CloseDate, "
        "APTS_Opportunity_ARR__c, Stage_20_Approval__c, "
        "KYC_Approval_Message__c, Submit_for_Stage_20_Review__c, "
        "LastActivityDate "
        "FROM Opportunity "
        "WHERE IsClosed = false AND Type IN ('Land','Expand') "
        f"AND {STAGE_3PLUS_LIKE} AND CloseDate = THIS_YEAR "
        f"{EXCLUDE_TEST_ARTIFACTS} "
        "ORDER BY APTS_Opportunity_ARR__c DESC NULLS LAST "
        f"LIMIT {limit}"
    )
    rows = _sf(soql)
    today = dt.date.today()
    out: list[dict[str, Any]] = []
    for r in rows:
        approved = bool(r.get("Stage_20_Approval__c"))
        submitted = bool(r.get("Submit_for_Stage_20_Review__c"))
        if approved:
            approval = ("Approved", "green")
        elif submitted:
            approval = ("Pending", "amber")
        else:
            approval = ("No approval", "red")

        kyc = ("Clear", "green") if r.get("KYC_Approval_Message__c") else ("Open", "red")

        # Flag: stalled if stage >=3 and no activity 60+ days
        last_activity = r.get("LastActivityDate")
        flag = "Clean"
        if approval[0] == "No approval":
            flag = "No approval"
        elif kyc[0] == "Open" and (r.get("StageName") or "").startswith(("5", "6")):
            flag = "KYC open"
        elif last_activity:
            try:
                d = dt.date.fromisoformat(last_activity)
                age = (today - d).days
                if age >= 60:
                    flag = f"Stalled {age}d"
            except ValueError:
                pass
        elif last_activity is None:
            flag = "No activity"

        close = r.get("CloseDate") or ""
        try:
            close_lbl = dt.date.fromisoformat(close).strftime("%b") if close else "—"
        except ValueError:
            close_lbl = close[:7] if close else "—"

        out.append(
            {
                "account": (r.get("Account") or {}).get("Name") or "—",
                "arr": r.get("APTS_Opportunity_ARR__c") or 0,
                "stage": (r.get("StageName") or "").split(" ")[0] or "—",
                "close": close_lbl,
                "approval": approval,
                "kyc": kyc,
                "flag": flag,
            }
        )
    return out


# --- alert SF-logic skeletons ----------------------------------------------

# Hand-written WHERE-clause condensations matching the actual alert functions
# in alerts.py. Kept terse so the table column reads at consulting density.
ALERT_LOGIC: dict[str, str] = {
    "Land deals at Stage 3+ without Commercial Approval": (
        "Type='Land' AND Stage>=3 AND Stage_20_Approval=false"
    ),
    "Stage 3+ Land/Expand deals ≥$500k ARR without Commercial Approval": (
        "Type IN('Land','Expand') AND Stage>=3 AND ARR>=500k AND Approval=false"
    ),
    "Stage 5+ Land/Expand without KYC clearance": (
        "Type IN('Land','Expand') AND Stage>=5 AND KYC_Approval=false"
    ),
    "Open opportunities with close date in the past": ("IsClosed=false AND CloseDate<TODAY"),
    "Stage 3+ opps with December 31 close dates (placeholder)": (
        "Stage>=3 AND MONTH(CloseDate)=12 AND DAY(CloseDate)=31"
    ),
    "Stage 5+ Land/Expand without Deal Shaping approval": (
        "Type IN('Land','Expand') AND Stage>=5 AND Deal_Shaping_Approved=false"
    ),
    "Stage 3+ opportunities with no activity in 60+ days": (
        "Stage>=3 AND LastActivityDate<TODAY-60"
    ),
    "Stage 3+ opportunities with no logged activity ever": ("Stage>=3 AND LastActivityDate=null"),
    "Commercial Approval submitted but not yet granted": (
        "Stage>=3 AND Submit_for_Stage_20_Review=true AND Approval=false"
    ),
    "Open opportunities owned by inactive Salesforce user": (
        "IsClosed=false AND Owner.IsActive=false"
    ),
}


# --- KPI 5: data-quality score ---------------------------------------------


def compute_data_quality_score(
    alerts: list[dict[str, Any]], total_open_opps: int
) -> tuple[float, str]:
    """100% × (1 − sum(critical+important alert opp counts) / total open opp count).

    Note: alert counts are deduped on samples but not on counts (per alerts.py
    docstring), so a single opp hitting two categories counts twice. This
    OVERSTATES breach volume — the score is therefore conservative (pessimistic).
    Footnote text returned alongside.
    """
    if total_open_opps <= 0:
        return 0.0, "no open opps"
    flagged = sum(
        int(a.get("count") or 0) for a in alerts if a.get("severity") in ("critical", "important")
    )
    score = max(0.0, 1.0 - flagged / total_open_opps)
    return score, (
        f"100% × (1 − {flagged} flagged ÷ {total_open_opps} open). "
        "Conservative: opps in multiple categories count multiple times."
    )


# --- prior-week delta from snapshot history --------------------------------


def prior_week_open_arr() -> float | None:
    """Return prior-7-days snapshot's `new_business_arr_open_this_quarter` if
    a snapshot exists, else None. Honest gap if absent."""
    target = dt.date.today() - dt.timedelta(days=7)
    p = SNAP_DIR / f"{target.isoformat()}.json"
    if not p.exists():
        # also try ±1d
        for offset in (-1, 1, -2, 2):
            alt = SNAP_DIR / f"{(target + dt.timedelta(days=offset)).isoformat()}.json"
            if alt.exists():
                p = alt
                break
        else:
            return None
    try:
        data = json.loads(p.read_text())
        return float(data.get("totals", {}).get("new_business_arr_open_this_quarter") or 0)
    except Exception:
        return None


# --- HTML rendering ---------------------------------------------------------


def _kpi_card(value: str, label: str, delta: str | None, footnote: str | None = None) -> str:
    delta_html = ""
    if delta:
        cls = (
            "delta-up"
            if delta.startswith("↑")
            else "delta-down"
            if delta.startswith("↓")
            else "delta-flat"
        )
        delta_html = f'<div class="kpi-delta {cls}">{delta}</div>'
    foot_html = f'<div class="kpi-foot">{footnote}</div>' if footnote else ""
    return f"""
<div class="kpi">
  <div class="kpi-value">{value}</div>
  <div class="kpi-label">{label}</div>
  {delta_html}
  {foot_html}
</div>
"""


def _status_pill(text: str, color: str) -> str:
    return f'<span class="pill pill-{color}">{text}</span>'


def _bar(label: str, value_text: str, pct: float, color: str = "blue") -> str:
    pct = max(0.0, min(100.0, pct))
    return f"""
<div class="bar-row">
  <div class="bar-label">{label}</div>
  <div class="bar-track"><div class="bar-fill bar-{color}" style="width: {pct:.1f}%;"></div></div>
  <div class="bar-value">{value_text}</div>
</div>
"""


def _funnel_html(stages: list[dict[str, Any]]) -> str:
    """Horizontal bars per stage bucket using real ARR. Width relative to max."""
    buckets: list[tuple[str, float, int]] = []
    for label, prefixes in STAGE_FUNNEL_BUCKETS:
        arr = sum((r.get("arr") or 0) for r in stages if _stage_bucket(r.get("stage"), prefixes))
        n = sum(
            int(r.get("num_opps") or 0) for r in stages if _stage_bucket(r.get("stage"), prefixes)
        )
        buckets.append((label, float(arr), n))
    max_arr = max((b[1] for b in buckets), default=1.0) or 1.0
    rows = []
    for label, arr, n in buckets:
        pct = (arr / max_arr) * 100 if max_arr else 0
        val = f"{_money(arr, large=True)} · {n}"
        rows.append(_bar(label, val, pct, "navy"))
    rows.append(_bar("Closed Won (Q)", "—", 1.5, "muted"))  # gap: Won not in open snapshot
    return "\n".join(rows)


def _conversion_html(probs: dict[str, float]) -> str:
    """Conversion rates from stage_probs — show transition probabilities,
    derived as p(win|stage_n) / p(win|stage_n-1) which approximates forward
    rate at that stage."""
    transitions = [
        ("S2 → S3", "2 - Discovery", "3 - Engagement"),
        ("S3 → S4", "3 - Engagement", "4 - Shortlisted"),
        ("S4 → S5+", "4 - Shortlisted", "5 - Preferred"),
    ]
    rows = []
    for label, from_s, to_s in transitions:
        p_from = probs.get(from_s, 0.0)
        p_to = probs.get(to_s, 0.0)
        rate = (p_to / p_from) if p_from > 0 else 0.0
        rate = min(1.0, rate)
        rows.append(
            _bar(
                label,
                f"{rate * 100:.0f}%",
                rate * 100,
                "green" if rate >= 0.5 else "amber" if rate >= 0.3 else "red",
            )
        )
    return "\n".join(rows)


def _gap_bars(labels: list[str]) -> str:
    """Render a list of bar labels with em-dash values and a muted indeterminate
    bar — visually consistent with the populated bars but obviously empty."""
    return "\n".join(_bar(label, "—", 0, "muted") for label in labels)


def _renewal_acv_by_quarter_html(quarters: list[dict[str, Any]]) -> str:
    """Renewal ACV bars for the 3 quarters we already have weighted on."""
    bars = []
    max_acv = max((q.get("weighted_renewal_acv") or 0) for q in quarters) or 1.0
    for q in quarters:
        acv = float(q.get("weighted_renewal_acv") or 0)
        pct = (acv / max_acv) * 100 if max_acv else 0
        bars.append(_bar(q.get("label", "—"), _money(acv, large=True), pct, "blue"))
    return "\n".join(bars)


def _alerts_table_html(alerts: list[dict[str, Any]]) -> str:
    sev_order = {"critical": 0, "important": 1, "info": 2}
    sorted_alerts = sorted(alerts, key=lambda a: sev_order.get(a.get("severity", ""), 99))
    rows = []
    for a in sorted_alerts:
        sev = a.get("severity", "info")
        sev_color = {"critical": "red", "important": "amber", "info": "blue"}.get(sev, "muted")
        name = a.get("name", "—")
        meaning = a.get("rule", "—")
        logic = ALERT_LOGIC.get(name, "—")
        count = int(a.get("count") or 0)
        rows.append(
            f"""
<tr>
  <td>{_status_pill(sev.capitalize(), sev_color)}</td>
  <td class="alert-name">{name}</td>
  <td class="alert-meaning">{meaning}</td>
  <td class="alert-logic"><code>{logic}</code></td>
  <td class="alert-count">{count}</td>
</tr>
"""
        )
    return f"""
<table class="alerts-table">
  <thead>
    <tr>
      <th>Severity</th>
      <th>Alert</th>
      <th>What it means</th>
      <th>SF logic</th>
      <th class="alert-count">Count</th>
    </tr>
  </thead>
  <tbody>
    {"".join(rows)}
  </tbody>
</table>
"""


def _top_deals_html(deals: list[dict[str, Any]]) -> str:
    rows = []
    for d in deals:
        approval_text, approval_color = d["approval"]
        kyc_text, kyc_color = d["kyc"]
        rows.append(
            f"""
<tr>
  <td>{d["account"]}</td>
  <td class="num">{_money(d["arr"], large=True)}</td>
  <td>{d["stage"]}</td>
  <td>{d["close"]}</td>
  <td class="muted">—</td>
  <td>{_status_pill(approval_text, approval_color)}</td>
  <td>{_status_pill(kyc_text, kyc_color)}</td>
  <td class="flag">{d["flag"]}</td>
</tr>
"""
        )
    return f"""
<table class="deals-table">
  <thead>
    <tr>
      <th>Account</th>
      <th class="num">ARR</th>
      <th>Stage</th>
      <th>Close</th>
      <th>Disc%</th>
      <th>Comm. Approval</th>
      <th>KYC</th>
      <th>Flag</th>
    </tr>
  </thead>
  <tbody>
    {"".join(rows)}
  </tbody>
</table>
"""


# --- the big builder --------------------------------------------------------


def build_html(
    sf_snapshot: dict[str, Any],
    alerts: list[dict[str, Any]],
    top_deals: list[dict[str, Any]],
    stage_probs: dict[str, float],
    discount: tuple[str | None, float | None, int],
    prior_open_arr: float | None,
    today: dt.date,
) -> str:
    quarters = sf_snapshot.get("quarters", [])
    totals = sf_snapshot.get("totals", {})

    # KPI 1: total open Land+Expand ARR across Q, Q+1, Q+2 (FY-ish forward)
    total_open_arr = sum(float(q.get("open_new_business_arr") or 0) for q in quarters)
    # KPI 3: weighted forecast THIS quarter
    weighted_q = float(totals.get("weighted_new_business_arr") or 0)

    # Total open opp count (denominator for data-quality score). Sum the by_stage rollup.
    total_open_opps = sum(
        int(r.get("num_opps") or 0) for q in quarters for r in q.get("new_business_by_stage", [])
    ) + sum(int(r.get("num_opps") or 0) for q in quarters for r in q.get("renewals_by_stage", []))
    dq_score, dq_formula = compute_data_quality_score(alerts, total_open_opps)

    # vs-last-week delta on KPI 1 (open ARR this quarter only — that's what
    # snapshot stored). We display it on card 1 even though card 1 itself
    # totals 3 quarters; honest about that in the footnote.
    cur_q_open = float(totals.get("new_business_arr_open_this_quarter") or 0)
    if prior_open_arr is not None and prior_open_arr > 0:
        delta_pct = (cur_q_open - prior_open_arr) / prior_open_arr * 100
        arrow = "↑" if delta_pct >= 0 else "↓"
        kpi1_delta = f"{arrow} {abs(delta_pct):.1f}% vs last wk (Q open only)"
    else:
        kpi1_delta = "vs last wk: —"

    # KPI 4 — discount: gap unless probe found populated values
    _, disc_avg, disc_n = discount
    if disc_avg is not None:
        kpi4_value = f"{disc_avg:.1f}%"
        kpi4_foot = f"avg over n={disc_n}"
    else:
        kpi4_value = "—"
        kpi4_foot = "(field present, not populated; not yet pulled)"

    # Action banner: pick the highest-severity alert with the largest count.
    sev_rank = {"critical": 0, "important": 1, "info": 2}
    if alerts:
        banner_alert = sorted(
            alerts,
            key=lambda a: (sev_rank.get(a.get("severity", ""), 99), -int(a.get("count") or 0)),
        )[0]
        banner = (
            f"{banner_alert.get('count', 0)} deals — "
            f"{banner_alert.get('name', 'alert')} — action required"
        )
    else:
        banner = "No active critical alerts."

    kpis = (
        _kpi_card(
            _money(total_open_arr, large=True),
            "Total open pipeline · Q+Q+1+Q+2 (Land+Expand ARR)",
            kpi1_delta,
        )
        + _kpi_card(
            "—",
            "Pipeline coverage · target 3.5x",
            "vs last wk: —",
            "(quota not surfaced)",
        )
        + _kpi_card(
            _money(weighted_q, large=True),
            "Commit forecast this quarter (weighted ARR)",
            "vs last wk: —",
            f"empirical · {totals.get('stage_probability_source', '—')}",
        )
        + _kpi_card(
            kpi4_value,
            "Avg discount FY2026",
            "vs last wk: —",
            kpi4_foot,
        )
        + _kpi_card(
            f"{dq_score * 100:.0f}%",
            "CRM data quality · target 80%+",
            "vs last wk: —",
            dq_formula,
        )
    )

    funnel = _funnel_html(sf_snapshot.get("new_business_by_stage", []))
    conversion = _conversion_html(stage_probs)
    slippage = _gap_bars(["Moved 1x", "Moved 2x", "Moved 3x+"])
    discount_bands = _gap_bars(["0-10%", "11-20%", "21-30%", ">30%"])

    renewals_by_q = _renewal_acv_by_quarter_html(quarters)

    deals_table = _top_deals_html(top_deals)
    alerts_table = _alerts_table_html(alerts)

    today_str = today.strftime("%B %-d, %Y")
    today_iso = today.isoformat()

    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><title>Sales Ops Cockpit — {today_iso}</title></head>
<body>

<div class="header">
  <div class="header-title">Sales Ops — Commercial Health &amp; Governance</div>
  <div class="header-meta">FY2026 · Updated daily · {today_str}</div>
</div>
<div class="filter-row">
  <span class="chip chip-active">FY2026 ●</span>
  <span class="chip">Americas</span>
  <span class="chip">EMEA</span>
  <span class="chip">APAC</span>
  <span class="chip">SC1 only</span>
  <span class="chip">All products</span>
  <span class="chip-foot">(filters not yet wired)</span>
</div>

<div class="section-title">COMMERCIAL OVERVIEW</div>
<div class="kpi-row">
  {kpis}
</div>

<div class="action-banner">
  ▪ {banner}
</div>

<div class="section-title">PIPELINE DETAIL</div>
<div class="three-col">
  <div class="col col-wide">
    <div class="panel-title">Top deals · FY2026 · Stage 3+ · ranked by ARR</div>
    {deals_table}
  </div>
  <div class="col col-narrow">
    <div class="panel-title">Pipeline funnel — current Q (open ARR)</div>
    {funnel}
    <div class="sub-title">Conversion rates <span class="micro">(empirical)</span></div>
    {conversion}
    <div class="sub-title">Date slippage <span class="micro">(close-date history not yet pulled)</span></div>
    {slippage}
    <div class="sub-title">Discount bands <span class="micro">(field empty for FY26 — gap)</span></div>
    {discount_bands}
  </div>
</div>

<div class="section-title">RENEWALS, QUALITY &amp; APPROVALS</div>
<div class="three-col">
  <div class="col">
    <div class="panel-title">Renewals — FY2026</div>
    <div class="muted-note">Renewal-health categorization (on track / at risk / no opp) is a planned follow-up.</div>
    <div class="sub-title">Renewal ACV by quarter (weighted)</div>
    {renewals_by_q}
    <div class="sub-title">Silent ARR erosion</div>
    <div class="big-stat muted">— <span class="micro">(asset-vs-renewal ARR delta not yet pulled)</span></div>
  </div>
  <div class="col">
    <div class="panel-title">Deal QC &amp; pre-close</div>
    <div class="sub-title">QC pass rate · target 90%</div>
    <div class="big-stat muted">—</div>
    <div class="muted-note">QC fields not exposed in current pull. Why-fail breakdown is a planned follow-up.</div>
    <div class="sub-title">Approval bottleneck</div>
    {_gap_bars(["CFO", "CRO", "MD level"])}
    <div class="sub-title">Avg turnaround · target &lt;2d</div>
    <div class="big-stat muted">—</div>
  </div>
  <div class="col">
    <div class="panel-title">CRM data quality</div>
    <div class="sub-title">Composite score</div>
    <div class="big-stat">{dq_score * 100:.0f}%</div>
    <div class="muted-note">{dq_formula} Per-object breakdown (Account/Quote/Asset) pending.</div>
    <div class="sub-title">Top failures this week</div>
    {_top_failure_bars(alerts)}
  </div>
</div>

<div class="page-break"></div>

<div class="section-title">ASSET INTEGRITY — ACCOUNT LEVEL</div>
<div class="asset-gap-note">
  <strong>Gap:</strong> Asset-level integrity checks (ghost assets, duplicate active assets,
  end-date drift, asset-vs-renewal ARR mismatch) are a planned follow-up. Would require querying
  SObject <code>Asset</code> with predicates on <code>Status</code>, <code>EndDate</code>, and
  joining via <code>AccountId</code> against open renewal opps. No fabricated numbers shown.
</div>

<div class="section-title">ACTIVE ALERTS — GOVERNANCE &amp; DATA QUALITY BREACHES</div>
{alerts_table}

<div class="footer">
  <div class="footer-left">SimCorp Sales Operations · Andre Profitt · {today_str} · Internal use only</div>
</div>

</body></html>
"""


def _top_failure_bars(alerts: list[dict[str, Any]]) -> str:
    """Important-severity alerts as horizontal bars, count-scaled."""
    important = [a for a in alerts if a.get("severity") == "important"]
    important = sorted(important, key=lambda a: -int(a.get("count") or 0))[:5]
    if not important:
        return '<div class="muted-note">No important-severity alerts active.</div>'
    max_count = max(int(a.get("count") or 0) for a in important) or 1
    rows = []
    for a in important:
        c = int(a.get("count") or 0)
        # truncate label
        name = a.get("name", "—")
        if len(name) > 48:
            name = name[:45] + "…"
        pct = (c / max_count) * 100
        rows.append(_bar(name, str(c), pct, "amber"))
    return "\n".join(rows)


# --- CSS --------------------------------------------------------------------


def build_css() -> str:
    c = COLORS
    return f"""
@page {{
  size: Letter;
  margin: 0.4in 0.4in 0.5in 0.4in;
  @bottom-right {{
    content: counter(page) " / " counter(pages);
    font-family: -apple-system, "Helvetica Neue", Helvetica, Arial, sans-serif;
    font-size: 7.5pt;
    color: {c["muted"]};
  }}
}}
* {{ box-sizing: border-box; }}
html, body {{ margin: 0; padding: 0; }}
body {{
  font-family: -apple-system, "Helvetica Neue", Helvetica, Arial, sans-serif;
  font-size: 8pt;
  color: #1f2328;
  line-height: 1.3;
}}

.header {{
  background: {c["navy"]};
  color: white;
  padding: 8pt 10pt;
  display: flex;
  justify-content: space-between;
  align-items: center;
}}
.header-title {{ font-size: 12pt; font-weight: 500; }}
.header-meta {{ font-size: 8.5pt; color: #cdd6e4; }}

.filter-row {{
  display: flex;
  gap: 4pt;
  padding: 5pt 10pt;
  background: {c["bg_soft"]};
  border-bottom: 0.5pt solid {c["border"]};
  align-items: center;
}}
.chip {{
  font-size: 7.5pt;
  color: {c["muted"]};
  padding: 2pt 8pt;
  border-radius: 10pt;
  border: 0.5pt solid {c["border"]};
  background: white;
}}
.chip-active {{
  color: {c["navy"]};
  border-color: {c["navy"]};
  font-weight: 600;
}}
.chip-foot {{
  font-size: 6.5pt;
  color: {c["muted"]};
  font-style: italic;
  margin-left: auto;
}}

.section-title {{
  background: {c["navy"]};
  color: white;
  padding: 4pt 10pt;
  font-size: 8.5pt;
  font-weight: 600;
  letter-spacing: 0.05em;
  margin-top: 8pt;
}}

.kpi-row {{
  display: flex;
  gap: 6pt;
  padding: 8pt;
  border-bottom: 0.5pt solid {c["border"]};
}}
.kpi {{
  flex: 1;
  border: 0.5pt solid {c["border"]};
  border-radius: 3pt;
  padding: 8pt 10pt;
  background: white;
}}
.kpi-value {{
  font-size: 18pt;
  color: {c["navy"]};
  font-weight: 500;
  line-height: 1.05;
}}
.kpi-label {{
  font-size: 7pt;
  color: {c["muted"]};
  margin-top: 3pt;
  line-height: 1.25;
}}
.kpi-delta {{
  font-size: 6.5pt;
  margin-top: 4pt;
}}
.delta-up {{ color: {c["green"]}; }}
.delta-down {{ color: {c["red"]}; }}
.delta-flat {{ color: {c["muted"]}; }}
.kpi-foot {{
  font-size: 6pt;
  color: {c["muted"]};
  margin-top: 3pt;
  font-style: italic;
  line-height: 1.2;
}}

.action-banner {{
  margin: 0;
  padding: 6pt 12pt;
  background: {c["red_soft"]};
  color: {c["red"]};
  border-left: 3pt solid {c["red"]};
  font-size: 9pt;
  font-weight: 500;
}}

.three-col {{
  display: flex;
  gap: 6pt;
  padding: 8pt;
}}
.col {{
  flex: 1;
  border: 0.5pt solid {c["border"]};
  border-radius: 3pt;
  padding: 7pt 9pt;
  background: white;
}}
.col-wide {{ flex: 2; }}
.col-narrow {{ flex: 1; }}

.panel-title {{
  font-size: 8pt;
  font-weight: 600;
  color: {c["navy"]};
  margin-bottom: 5pt;
  padding-bottom: 3pt;
  border-bottom: 0.5pt solid {c["border"]};
}}
.sub-title {{
  font-size: 7.5pt;
  font-weight: 600;
  color: {c["navy"]};
  margin: 6pt 0 3pt;
}}
.micro {{ font-size: 6pt; color: {c["muted"]}; font-weight: 400; font-style: italic; }}
.muted-note {{
  font-size: 6.5pt;
  color: {c["muted"]};
  font-style: italic;
  margin: 3pt 0;
  line-height: 1.3;
}}

.big-stat {{
  font-size: 16pt;
  color: {c["navy"]};
  font-weight: 500;
  margin: 2pt 0;
}}
.big-stat.muted {{ color: {c["muted"]}; }}

table {{
  width: 100%;
  border-collapse: collapse;
  font-size: 7.5pt;
}}
table th {{
  background: {c["navy_soft"]};
  color: {c["navy"]};
  text-align: left;
  font-weight: 600;
  padding: 3pt 5pt;
  border-bottom: 0.5pt solid {c["border"]};
  font-size: 7pt;
}}
table td {{
  padding: 3pt 5pt;
  border-bottom: 0.25pt solid {c["border"]};
  font-variant-numeric: tabular-nums;
}}
table td.num, table th.num {{ text-align: right; }}
table td.muted {{ color: {c["muted"]}; }}

.pill {{
  display: inline-block;
  padding: 1pt 6pt;
  border-radius: 8pt;
  font-size: 6.5pt;
  font-weight: 500;
}}
.pill-green {{ background: {c["green_soft"]}; color: {c["green"]}; }}
.pill-amber {{ background: {c["amber_soft"]}; color: {c["amber"]}; }}
.pill-red {{ background: {c["red_soft"]}; color: {c["red"]}; }}
.pill-blue {{ background: {c["navy_soft"]}; color: {c["blue"]}; }}
.pill-muted {{ background: {c["bg_soft"]}; color: {c["muted"]}; }}

.bar-row {{
  display: flex;
  align-items: center;
  font-size: 7pt;
  margin: 2pt 0;
}}
.bar-label {{ width: 60pt; color: {c["muted"]}; flex-shrink: 0; }}
.bar-track {{
  flex: 1;
  background: {c["bg_soft"]};
  border-radius: 2pt;
  height: 7pt;
  margin: 0 4pt;
  overflow: hidden;
}}
.bar-fill {{ height: 100%; }}
.bar-navy {{ background: {c["navy"]}; }}
.bar-blue {{ background: {c["blue"]}; }}
.bar-green {{ background: {c["green"]}; }}
.bar-amber {{ background: {c["amber"]}; }}
.bar-red {{ background: {c["red"]}; }}
.bar-muted {{ background: {c["border"]}; }}
.bar-value {{
  width: 60pt;
  text-align: right;
  font-variant-numeric: tabular-nums;
  font-weight: 500;
  color: {c["navy"]};
  flex-shrink: 0;
}}

.alerts-table {{
  margin: 6pt 8pt 0;
  width: calc(100% - 16pt);
}}
.alert-name {{ font-weight: 500; max-width: 160pt; }}
.alert-meaning {{ color: {c["muted"]}; font-size: 7pt; max-width: 140pt; }}
.alert-logic code {{
  font-family: "SF Mono", Menlo, Consolas, monospace;
  font-size: 6.5pt;
  background: {c["bg_soft"]};
  padding: 1pt 3pt;
  border-radius: 2pt;
  color: {c["navy"]};
}}
.alert-count {{ text-align: right; font-weight: 600; color: {c["navy"]}; white-space: nowrap; }}

.deals-table {{
  font-size: 7pt;
}}
.deals-table .flag {{ font-style: italic; color: {c["muted"]}; }}

.asset-gap-note {{
  margin: 8pt;
  padding: 8pt 10pt;
  background: {c["amber_soft"]};
  border-left: 3pt solid {c["amber"]};
  font-size: 7.5pt;
  color: #6b4d00;
  line-height: 1.4;
}}
.asset-gap-note code {{
  font-family: "SF Mono", Menlo, monospace;
  background: white;
  padding: 0 3pt;
  border-radius: 2pt;
}}

.footer {{
  margin-top: 10pt;
  padding: 6pt 10pt;
  border-top: 0.5pt solid {c["border"]};
  font-size: 6.5pt;
  color: {c["muted"]};
}}

.page-break {{ page-break-before: always; }}
"""


# --- entrypoint -------------------------------------------------------------


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", help="Output PDF path", default=None)
    args = ap.parse_args()

    today = dt.date.today()
    REPORTS_DIR.mkdir(exist_ok=True)
    out_path = (
        pathlib.Path(args.out) if args.out else REPORTS_DIR / f"cockpit-{today.isoformat()}.pdf"
    )

    print("→ Pulling Salesforce snapshot (multi-quarter)...")
    from brief import pull_salesforce_snapshot  # type: ignore[import-not-found]

    sf = pull_salesforce_snapshot()
    print(
        f"  Q open ARR: {_money(sf['totals'].get('new_business_arr_open_this_quarter'), large=True)}"
    )

    print("→ Pulling alerts...")
    from alerts import pull_all_alerts  # type: ignore[import-not-found]

    alerts = pull_all_alerts()
    print(f"  {len(alerts)} alerts")

    print("→ Loading stage probabilities...")
    from stage_probs import get_stage_probabilities  # type: ignore[import-not-found]

    probs, _ = get_stage_probabilities()

    print("→ Pulling top Stage 3+ deals...")
    deals = pull_top_deals(limit=8)
    print(f"  {len(deals)} deals")

    print("→ Probing discount field...")
    discount = probe_discount_field()
    print(f"  field={discount[0]} avg={discount[1]} n={discount[2]}")

    prior_arr = prior_week_open_arr()
    print(f"  prior-week open ARR: {prior_arr}")

    html = build_html(sf, alerts, deals, probs, discount, prior_arr, today)
    css = build_css()

    print(f"→ Rendering PDF → {out_path}...")
    HTML(string=html).write_pdf(str(out_path), stylesheets=[CSS(string=css)])
    size = out_path.stat().st_size
    print(f"✓ Wrote {out_path} ({size:,} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
