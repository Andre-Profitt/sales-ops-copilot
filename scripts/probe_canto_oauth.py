#!/usr/bin/env python3
"""Direct probe of the 3 Canto OAuth endpoints think-cell uses.

Mining only confirmed presence of these strings in tcaddin.dll:
  /oauth.canto.com/oauth/api/oauth2/authorize
  /oauth.canto.com/oauth/api/oauth2/tenant/
  /oauth.canto.com/oauth/api/oauth2/token

This script characterizes the live endpoints via standard OAuth recon:
  1. Tenant lookup (no creds): reveals Canto tenant directory shape
  2. Authorize with empty params: error message reveals required params
  3. Token with empty body: error message reveals required params + grant types

We're only hitting Canto-public surfaces (Canto's own Help Center documents the
OAuth flow). No think-cell-private surfaces touched.

Output: state/thinkcell_bridge/canto_oauth_probe/<ts>/results.json
"""

from __future__ import annotations

import json
import sys
import time
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
TIMEOUT = 10
UA = "thinkcell-research-probe/1.0 (interoperability-research)"


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def _capture(method, url, **kwargs):
    """Hit a URL, normalize result for JSON dump."""
    headers = {"User-Agent": UA, **kwargs.pop("headers", {})}
    try:
        r = requests.request(
            method, url, headers=headers, timeout=TIMEOUT, allow_redirects=False, **kwargs
        )
        body = r.text
        try:
            body_json = r.json() if r.text else None
        except (ValueError, json.JSONDecodeError):
            body_json = None
        return {
            "url": url,
            "method": method,
            "status": r.status_code,
            "headers": dict(r.headers),
            "body_text_first_2000": body[:2000],
            "body_json": body_json,
            "redirect_target": r.headers.get("Location"),
        }
    except Exception as e:
        return {"url": url, "method": method, "error": f"{type(e).__name__}: {e}"}


def main():
    out_dir = (
        ROOT / "state" / "thinkcell_bridge" / "canto_oauth_probe" / time.strftime("%Y%m%d-%H%M%S")
    )
    out_dir.mkdir(parents=True, exist_ok=True)

    results = {
        "schema": "thinkcell-canto-oauth-probe/v1",
        "timestamp_utc": _now_iso(),
        "scope": "Canto-public OAuth surfaces only; no think-cell private endpoints",
        "probes": [],
    }

    # Probe 1: Tenant lookup endpoint with no tenant arg
    results["probes"].append(
        {
            "name": "tenant_directory_root",
            "purpose": "See what /tenant/ returns with no tenant slug",
            "result": _capture("GET", "https://oauth.canto.com/oauth/api/oauth2/tenant/"),
        }
    )

    # Probe 2: Tenant lookup with hypothetical 'thinkcell' tenant
    results["probes"].append(
        {
            "name": "tenant_thinkcell_lookup",
            "purpose": "Does Canto resolve a 'thinkcell' tenant?",
            "result": _capture("GET", "https://oauth.canto.com/oauth/api/oauth2/tenant/thinkcell"),
        }
    )

    # Probe 3: Tenant lookup variants (think-cell is hyphenated)
    for slug in ("think-cell", "thinkcellsales", "tc"):
        results["probes"].append(
            {
                "name": f"tenant_lookup_{slug}",
                "purpose": f"Try slug={slug}",
                "result": _capture(
                    "GET", f"https://oauth.canto.com/oauth/api/oauth2/tenant/{slug}"
                ),
            }
        )

    # Probe 4: Authorize endpoint with no params
    results["probes"].append(
        {
            "name": "authorize_no_params",
            "purpose": "Error message reveals required params",
            "result": _capture("GET", "https://oauth.canto.com/oauth/api/oauth2/authorize"),
        }
    )

    # Probe 5: Authorize endpoint with bogus client_id (response should reveal "unknown client")
    bogus_params = urllib.parse.urlencode(
        {
            "client_id": "thinkcell-probe-client-id-not-real",
            "response_type": "code",
            "redirect_uri": "http://localhost",
            "scope": "read",
            "state": "probe",
        }
    )
    results["probes"].append(
        {
            "name": "authorize_bogus_client",
            "purpose": "Bogus client_id — response shape reveals validation order",
            "result": _capture(
                "GET", f"https://oauth.canto.com/oauth/api/oauth2/authorize?{bogus_params}"
            ),
        }
    )

    # Probe 6: Token endpoint with no body
    results["probes"].append(
        {
            "name": "token_no_body",
            "purpose": "Error message reveals grant types + required fields",
            "result": _capture(
                "POST",
                "https://oauth.canto.com/oauth/api/oauth2/token",
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            ),
        }
    )

    # Probe 7: Token endpoint with grant_type only
    results["probes"].append(
        {
            "name": "token_grant_only",
            "purpose": "Body=grant_type=authorization_code only — reveals what fields are missing",
            "result": _capture(
                "POST",
                "https://oauth.canto.com/oauth/api/oauth2/token",
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                data="grant_type=authorization_code",
            ),
        }
    )

    # Probe 8: Discover OAuth metadata (well-known)
    for path in ("/.well-known/oauth-authorization-server", "/.well-known/openid-configuration"):
        results["probes"].append(
            {
                "name": f"well_known_{path.strip('/.')[-30:]}",
                "purpose": f"OAuth/OIDC metadata at {path}",
                "result": _capture("GET", f"https://oauth.canto.com{path}"),
            }
        )

    # Probe 9: Resolve oauth.canto.com itself (for context)
    results["probes"].append(
        {
            "name": "root_get",
            "purpose": "What does the root return?",
            "result": _capture("GET", "https://oauth.canto.com/oauth/"),
        }
    )

    # Summary
    summary = {
        "total_probes": len(results["probes"]),
        "by_status": {},
        "errored": 0,
        "key_findings": [],
    }
    for p in results["probes"]:
        r = p["result"]
        if "error" in r:
            summary["errored"] += 1
            continue
        status = r.get("status", "?")
        summary["by_status"][status] = summary["by_status"].get(status, 0) + 1

    # Specific findings to spotlight
    for p in results["probes"]:
        r = p["result"]
        if "body_text_first_2000" in r and r.get("status") in (400, 401, 403):
            body = r["body_text_first_2000"][:300]
            summary["key_findings"].append(
                {
                    "probe": p["name"],
                    "status": r["status"],
                    "snippet": body,
                }
            )

    results["summary"] = summary

    out_file = out_dir / "results.json"
    out_file.write_text(json.dumps(results, indent=2, default=str), encoding="utf-8")
    print(f"[canto] wrote {out_file}")
    print(f"[canto] probes: {summary['total_probes']}")
    print(f"[canto] by_status: {summary['by_status']}")
    print(f"[canto] errored: {summary['errored']}")
    print(f"[canto] key_findings ({len(summary['key_findings'])}):")
    for kf in summary["key_findings"][:10]:
        print(f"  {kf['probe']}  status={kf['status']}  snippet={kf['snippet'][:140]!r}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
