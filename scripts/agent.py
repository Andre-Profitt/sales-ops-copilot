#!/usr/bin/env python3
"""
sales-ops-copilot — Microsoft Agent Framework wrapper around brief.py.

Same daily Sales Ops brief, but produced via an Agent Framework `Agent` that
calls the existing data-pull functions as tools and lets the model orchestrate.
The intent is to mirror brief.py's output (so the launchd cron is unaffected
when Phase 2 swaps it in) while exercising the Microsoft Agent Framework SDK
on apro-foundry-project.

This file WRAPS brief.py / alerts.py / stage_probs.py — it does not replace them.

Usage:
    python3 scripts/agent.py
    python3 scripts/agent.py --model gpt53chat
    python3 scripts/agent.py --out reports/agent-2026-04-28.md

Output: reports/agent-YYYY-MM-DD.md (note `agent-` prefix).
"""

from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import json
import os
import pathlib
import shutil
import subprocess
import sys
from typing import Any

from azure.identity import AzureCliCredential

# Make scripts/ importable for the existing data-pull modules.
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

# Reuse the existing, verified data-pull + render functions from brief.py.
# These are the source of truth for SF + Fabric pulls; we expose them as tools.
from brief import (  # type: ignore[import-not-found]  # noqa: E402
    DEFAULT_MODEL,
    OPENAI_API_VERSION,
    OPENAI_ENDPOINT,
    REPORTS_DIR,
    pull_fabric_workspace_summary as _pull_fabric_summary_raw,
    pull_salesforce_snapshot as _pull_sf_snapshot_raw,
    render_report,
)
from alerts import (  # type: ignore[import-not-found]  # noqa: E402
    pull_account_concentration as _pull_account_conc_raw,
    pull_all_alerts as _pull_alerts_raw,
    pull_owner_concentration as _pull_owner_conc_raw,
)

# Agent Framework
from agent_framework.openai import OpenAIChatCompletionClient  # noqa: E402  # type: ignore[attr-defined]


# --- System prompt: lifted verbatim from brief.synthesize() ----------------
# Keep this byte-identical with brief.py's `system` so output parity holds.

SYSTEM_PROMPT = (
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
    "TOOL USE: Call `pull_salesforce_snapshot`, `pull_fabric_workspace_summary`, "
    "`pull_all_alerts`, `pull_owner_concentration`, and `pull_account_concentration` "
    "ONCE EACH at the start of the conversation to gather the data, then write "
    "the brief. Do not call any tool more than once.\n\n"
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


# --- Tool wrappers ----------------------------------------------------------
# Agent Framework discovers tools via type-annotated Python callables. We wrap
# the existing pulls with a tiny shim that returns a JSON-serializable payload
# and stash the latest pulls into TOOL_CACHE so render_report can reuse them.
#
# All tools are sync — Agent Framework runs them in a threadpool. Since `sf`
# CLI and `az rest` are subprocess calls, this is fine.

TOOL_CACHE: dict[str, Any] = {}


def pull_salesforce_snapshot() -> dict[str, Any]:
    """Pull the live Salesforce pipeline snapshot for current quarter, Q+1, and Q+2.

    Returns aggregate-only data (no client-level detail), including:
      - by_type: opp count + ARR + Renewal ACV per Type for current quarter
      - new_business_by_stage: stage rollup with empirical weighted ARR
      - renewals_by_stage: stage rollup with empirical weighted ACV
      - quarters: 3-element list (current, Q+1, Q+2) with open + weighted views
      - totals: headline numbers + stage_probability_source

    Land + Expand reported in ARR via APTS_Opportunity_ARR__c.
    Renewals reported in ACV via APTS_Renewal_ACV__c. Never blended.
    """
    snap = _pull_sf_snapshot_raw()
    TOOL_CACHE["sf_snapshot"] = snap
    return snap


def pull_fabric_workspace_summary() -> list[dict[str, Any]]:
    """List datasets and reports per Sales-Ops-relevant Power BI / Fabric workspace.

    Returns a list of {workspace, id, datasets, reports} dicts for the 8
    workspaces wired into SALES_OPS_WORKSPACES. Errors are captured per-workspace
    so a single auth failure doesn't kill the rest.
    """
    fab = _pull_fabric_summary_raw()
    TOOL_CACHE["fabric_summary"] = fab
    return fab


def pull_all_alerts() -> list[dict[str, Any]]:
    """Run all governance + hygiene alert detectors against open SF pipeline.

    Returns a list of alert dicts in the shape:
      {name, severity, rule, count, total_arr, samples}
    Severity is 'critical' or 'important'. Samples include up to 5 top-impact
    opps per alert, with deal name, stage, $arr, owner, also_flagged_in.
    Acknowledged opps are excluded from both counts and samples.
    """
    alerts = _pull_alerts_raw()
    TOOL_CACHE["alerts"] = alerts
    return alerts


def pull_owner_concentration(top_n: int = 10) -> list[dict[str, Any]]:
    """Roll the alert-flagged opp population up by Owner.

    Returns a top-N list of {owner, deal_count, total_arr} ranked by total_arr,
    so the top reps holding governance/hygiene debt surface first.
    """
    owners = _pull_owner_conc_raw(top_n=top_n)
    TOOL_CACHE["owners"] = owners
    return owners


def pull_account_concentration(top_n: int = 15) -> list[dict[str, Any]]:
    """Roll the alert-flagged opp population up by Account.

    Returns a top-N list of {account, deal_count, total_arr} ranked by total_arr.
    Directors think in accounts, not reps — this is the dimension they want.
    """
    accounts = _pull_account_conc_raw(top_n=top_n)
    TOOL_CACHE["accounts"] = accounts
    return accounts


def pull_radar_recommendations() -> list[dict[str, Any]]:
    """Pull actionable recommendations from radar's claim pipeline.

    Reads `~/code/apps/radar/state/radar.db` (override via `RADAR_DB`) and
    returns must_try + should_try recs in `status='proposed'`, ordered by
    severity then confidence. Empty list if radar isn't installed.

    Each rec: {rec_id, severity, type, entity, summary, confidence,
    evidence_strength, blast_radius, expected_benefit, do_nothing_cost,
    citation_count}. These are tooling/ecosystem signals (version upgrades,
    deprecations, security responses) about Andre's stack — sidebar to the
    Sales Ops pipeline, not a substitute for it.
    """
    from radar_recs import pull_actionable_recs as _pull  # type: ignore[reportMissingImports]

    recs = _pull()
    TOOL_CACHE["radar_recs"] = recs
    return recs


# --- Agent runner -----------------------------------------------------------


async def _run_agent(model: str) -> str:
    """Build the agent, run it once, return the synthesis text."""
    cred = AzureCliCredential()

    # Mirror brief.py's chat-completions setup: Azure endpoint + AAD creds +
    # GPT-5.x-compatible options (no temperature, max_tokens → max_completion_tokens).
    client = OpenAIChatCompletionClient(
        azure_endpoint=OPENAI_ENDPOINT,
        credential=cred,
        api_version=OPENAI_API_VERSION,
        model=model,
    )

    agent = client.as_agent(
        name="sales-ops-copilot",
        description="Daily Sales Ops brief for SimCorp Global Senior Sales Operations Consultant.",
        instructions=SYSTEM_PROMPT,
        tools=[
            pull_salesforce_snapshot,
            pull_fabric_workspace_summary,
            pull_all_alerts,
            pull_owner_concentration,
            pull_account_concentration,
            pull_radar_recommendations,
        ],
        # GPT-5.x rejects non-default temperature; do not set it. max_tokens
        # translates to max_completion_tokens in the chat-completions client.
        default_options={"max_tokens": 1500},
    )

    today = dt.date.today().isoformat()
    user_msg = (
        f"Today is {today}. Generate today's Sales Ops brief by calling each "
        "data-pull tool exactly once, then write the brief per your instructions."
    )

    response = await agent.run(user_msg)
    return str(response).strip()


def _build_agent(model: str) -> Any:
    """Construct the chat agent (shared by one-shot and interactive paths)."""
    cred = AzureCliCredential()
    client = OpenAIChatCompletionClient(
        azure_endpoint=OPENAI_ENDPOINT,
        credential=cred,
        api_version=OPENAI_API_VERSION,
        model=model,
    )
    return client.as_agent(
        name="sales-ops-copilot",
        description="Daily Sales Ops brief for SimCorp Global Senior Sales Operations Consultant.",
        instructions=SYSTEM_PROMPT,
        tools=[
            pull_salesforce_snapshot,
            pull_fabric_workspace_summary,
            pull_all_alerts,
            pull_owner_concentration,
            pull_account_concentration,
            pull_radar_recommendations,
        ],
        default_options={"max_tokens": 1500},
    )


# --- Interactive REPL -------------------------------------------------------


def _prewarm_cache() -> None:
    print("→ Pulling Salesforce snapshot...")
    TOOL_CACHE["sf_snapshot"] = _pull_sf_snapshot_raw()
    print("→ Pulling Fabric workspace summary...")
    TOOL_CACHE["fabric_summary"] = _pull_fabric_summary_raw()
    print("→ Detecting alerts...")
    TOOL_CACHE["alerts"] = _pull_alerts_raw()
    print("→ Owner concentration...")
    TOOL_CACHE["owners"] = _pull_owner_conc_raw(top_n=10)
    print("→ Account concentration...")
    TOOL_CACHE["accounts"] = _pull_account_conc_raw(top_n=15)
    print("→ Radar recommendations...")
    from radar_recs import pull_actionable_recs as _pull_recs  # type: ignore[reportMissingImports]

    TOOL_CACHE["radar_recs"] = _pull_recs()


def _summary_header() -> str:
    sf = TOOL_CACHE["sf_snapshot"]
    t = sf.get("totals", {})
    alerts = TOOL_CACHE["alerts"]
    crit = sum(1 for a in alerts if a.get("severity") == "critical")
    imp = sum(1 for a in alerts if a.get("severity") == "important")
    owners = TOOL_CACHE["owners"]
    accounts = TOOL_CACHE["accounts"]
    top_owner = owners[0] if owners else None
    top_acct = accounts[0] if accounts else None
    bar = "=" * 60
    lines = [
        "",
        bar,
        f"Sales Ops Copilot — Interactive ({dt.date.today().isoformat()})",
        bar,
        f"Open new-business ARR (Q): ${t.get('new_business_arr_open_this_quarter', 0):,.0f} "
        f"(weighted ${t.get('weighted_new_business_arr', 0):,.0f})",
        f"Open Renewal ACV (Q): ${t.get('renewal_acv_open_this_quarter', 0):,.0f} "
        f"(weighted ${t.get('weighted_renewal_acv', 0):,.0f})",
        f"Alerts: {crit} critical, {imp} important",
    ]
    if top_owner:
        lines.append(f"Top owner (alert ARR): {top_owner['owner']} ${top_owner['total_arr']:,.0f}")
    if top_acct:
        lines.append(
            f"Top account (alert ARR): {top_acct['account']} ${top_acct['total_arr']:,.0f}"
        )
    lines += [
        "",
        "Type a question. `exit`, `quit`, Ctrl-C, or Ctrl-D to leave.",
        bar,
        "",
    ]
    return "\n".join(lines)


def _cached_context_payload() -> str:
    return json.dumps(
        {
            "salesforce_pipeline_thisquarter": TOOL_CACHE["sf_snapshot"],
            "alerts": TOOL_CACHE["alerts"],
            "owner_concentration_top10": TOOL_CACHE["owners"],
            "account_concentration_top15": TOOL_CACHE["accounts"],
            "fabric_workspaces_available": TOOL_CACHE["fabric_summary"],
            "radar_recommendations_actionable": TOOL_CACHE.get("radar_recs", []),
            "today": dt.date.today().isoformat(),
        },
        indent=2,
        default=str,
    )


async def _interactive_loop(model: str) -> int:
    agent = _build_agent(model)
    session = agent.create_session()

    primer = (
        "You have a pre-warmed snapshot of today's Sales Ops data below. "
        "Use it as default context; only re-call tools if the user explicitly "
        "asks for a refresh or for data not present here. Keep answers tight "
        "(under 200 words unless asked for more). Maintain ARR/ACV separation.\n\n"
        f"CACHED_SNAPSHOT:\n{_cached_context_payload()}"
    )
    await agent.run(primer, session=session)

    while True:
        try:
            line = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nbye.")
            return 0
        if not line:
            continue
        if line.lower() in {"exit", "quit", ":q"}:
            print("bye.")
            return 0
        try:
            response = await agent.run(line, session=session)
            print(f"\n{str(response).strip()}\n")
        except Exception as e:
            print(f"  ⚠ agent error: {e}\n")


def _run_interactive(model: str) -> int:
    _prewarm_cache()
    print(_summary_header())
    try:
        return asyncio.run(_interactive_loop(model))
    except KeyboardInterrupt:
        print("\nbye.")
        return 0


# --- Main -------------------------------------------------------------------


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help="Azure OpenAI deployment name (default: gpt53chat)",
    )
    ap.add_argument("--out", help="Output path; defaults to reports/agent-YYYY-MM-DD.md")
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
        "--interactive",
        action="store_true",
        help="Drop into a multi-turn REPL after pre-warming the data cache.",
    )
    args = ap.parse_args()

    if args.interactive:
        return _run_interactive(args.model)

    REPORTS_DIR.mkdir(exist_ok=True)
    out_path = (
        pathlib.Path(args.out)
        if args.out
        else REPORTS_DIR / f"agent-{dt.date.today().isoformat()}.md"
    )

    print(f"→ Running Sales Ops agent (model={args.model}) via Microsoft Agent Framework...")
    try:
        synthesis = asyncio.run(_run_agent(args.model))
        print(f"  Synthesis: {len(synthesis)} chars")
    except Exception as e:
        print(f"  ⚠ Agent run failed: {e}")
        synthesis = f"_Agent run failed: {e}_"

    # If the agent didn't actually call all tools, fall back to direct pulls so
    # the rendered report still has the full data tables (mirror brief.py shape).
    if "sf_snapshot" not in TOOL_CACHE:
        print("  ⚠ sf_snapshot tool not called — pulling directly for render")
        TOOL_CACHE["sf_snapshot"] = _pull_sf_snapshot_raw()
    if "fabric_summary" not in TOOL_CACHE:
        print("  ⚠ fabric_summary tool not called — pulling directly for render")
        TOOL_CACHE["fabric_summary"] = _pull_fabric_summary_raw()
    if "alerts" not in TOOL_CACHE:
        print("  ⚠ alerts tool not called — pulling directly for render")
        TOOL_CACHE["alerts"] = _pull_alerts_raw()
    if "owners" not in TOOL_CACHE:
        print("  ⚠ owners tool not called — pulling directly for render")
        TOOL_CACHE["owners"] = _pull_owner_conc_raw(top_n=10)
    if "accounts" not in TOOL_CACHE:
        print("  ⚠ accounts tool not called — pulling directly for render")
        TOOL_CACHE["accounts"] = _pull_account_conc_raw(top_n=15)
    if "radar_recs" not in TOOL_CACHE:
        print("  ⚠ radar_recs tool not called — pulling directly for render")
        from radar_recs import pull_actionable_recs as _pull_recs  # type: ignore[reportMissingImports]

        TOOL_CACHE["radar_recs"] = _pull_recs()

    report = render_report(
        TOOL_CACHE["sf_snapshot"],
        TOOL_CACHE["fabric_summary"],
        TOOL_CACHE["alerts"],
        TOOL_CACHE["owners"],
        TOOL_CACHE["accounts"],
        synthesis,
        args.model,
        radar_recs=TOOL_CACHE.get("radar_recs"),
    )

    # Tag the report so it's clearly the agent-produced variant.
    report = report.replace(
        "*Generated by sales-ops-copilot.",
        "*Generated by sales-ops-copilot (Microsoft Agent Framework wrapper).",
        1,
    )

    out_path.write_text(report, encoding="utf-8")
    print(f"\n✓ Wrote {out_path}")

    # Stash a tool-call summary so we can verify the agent actually called tools.
    tool_calls = {k: (len(v) if isinstance(v, (list, dict)) else 1) for k, v in TOOL_CACHE.items()}
    print(f"  Tool cache: {json.dumps(tool_calls)}")

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
            try:
                target_dir = (
                    pathlib.Path.home()
                    / "Library"
                    / "CloudStorage"
                    / "OneDrive-SimCorp"
                    / "Sales Ops Briefs"
                )
                target_dir.mkdir(parents=True, exist_ok=True)
                # Power Automate Flow watches for `<YYYY-MM-DD>.html` — strip the
                # `agent-` prefix that this script's local report uses.
                published_name = html_path.name
                if published_name.startswith("agent-"):
                    published_name = published_name[len("agent-") :]
                target = target_dir / published_name
                tmp = target.with_suffix(target.suffix + ".tmp")
                shutil.copyfile(html_path, tmp)
                os.replace(tmp, target)
                print(f"✓ Published to OneDrive: {target}")
            except Exception as e:
                print(f"  ⚠ OneDrive publish failed: {e}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
