#!/usr/bin/env python3
"""Probe Getty + Canto + Brandfolder public OAuth metadata.

These three are direct-API stock providers (no think-cell proxy). Standard
OAuth 2.0 — we should be able to authenticate directly with our own dev
registration, no think-cell auth dependency.

Verifies: discovery endpoints exist, authorization URL pattern, token URL
pattern, what scopes/grant types are supported.

Outputs to state/thinkcell_bridge/stockprovider_oauth_probe/<TS>/.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import json
import sys
from pathlib import Path

import httpx


ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "state" / "thinkcell_bridge" / "stockprovider_oauth_probe"
UA = "tc-toolkit-recon/0.1"


PROBES = [
    # --- Getty Images ---
    # Public docs: https://api.gettyimages.com/oauth2/token (Client Credentials grant)
    {"id": "getty_root", "method": "GET", "url": "https://api.gettyimages.com/"},
    {
        "id": "getty_v3",
        "method": "GET",
        "url": "https://api.gettyimages.com/v3/search/images/creative",
    },
    {
        "id": "getty_oauth_token",
        "method": "POST",
        "url": "https://api.gettyimages.com/oauth2/token",
        "body": b"grant_type=client_credentials&client_id=invalid&client_secret=invalid",
        "ct": "application/x-www-form-urlencoded",
    },
    {
        "id": "getty_oauth_meta",
        "method": "GET",
        "url": "https://api.gettyimages.com/.well-known/oauth-authorization-server",
    },
    {
        "id": "getty_oidc_meta",
        "method": "GET",
        "url": "https://api.gettyimages.com/.well-known/openid-configuration",
    },
    {"id": "getty_devcenter", "method": "GET", "url": "https://developers.gettyimages.com/api/"},
    # --- Canto ---
    # think-cell-confirmed paths from binary: oauth.canto.com/oauth/api/oauth2/{authorize,tenant/,token}
    {"id": "canto_oauth_root", "method": "GET", "url": "https://oauth.canto.com/oauth/api/oauth2/"},
    {
        "id": "canto_oauth_token",
        "method": "POST",
        "url": "https://oauth.canto.com/oauth/api/oauth2/token",
        "body": b"grant_type=client_credentials&app_id=invalid&app_secret=invalid",
        "ct": "application/x-www-form-urlencoded",
    },
    {
        "id": "canto_oauth_authz",
        "method": "GET",
        "url": "https://oauth.canto.com/oauth/api/oauth2/authorize?response_type=code&app_id=invalid&redirect_uri=urn:ietf:wg:oauth:2.0:oob",
    },
    {
        "id": "canto_oauth_tenant",
        "method": "GET",
        "url": "https://oauth.canto.com/oauth/api/oauth2/tenant/",
    },
    {
        "id": "canto_oauth_meta",
        "method": "GET",
        "url": "https://oauth.canto.com/.well-known/oauth-authorization-server",
    },
    {
        "id": "canto_oidc_meta",
        "method": "GET",
        "url": "https://oauth.canto.com/.well-known/openid-configuration",
    },
    # --- Brandfolder ---
    # Per-tenant API key auth. Public API: https://brandfolder.com/api
    {"id": "bf_root", "method": "GET", "url": "https://brandfolder.com/api"},
    {"id": "bf_v4", "method": "GET", "url": "https://brandfolder.com/api/v4/"},
    {
        "id": "bf_v4_brandfolders",
        "method": "GET",
        "url": "https://brandfolder.com/api/v4/brandfolders",
    },
    {
        "id": "bf_oauth_meta",
        "method": "GET",
        "url": "https://brandfolder.com/.well-known/oauth-authorization-server",
    },
    {
        "id": "bf_oidc_meta",
        "method": "GET",
        "url": "https://brandfolder.com/.well-known/openid-configuration",
    },
    {"id": "bf_dev_docs", "method": "GET", "url": "https://developers.brandfolder.com/"},
]


async def run_one(client: httpx.AsyncClient, probe: dict) -> dict:
    started = dt.datetime.now(tz=dt.timezone.utc)
    headers = {"User-Agent": UA}
    if probe.get("ct"):
        headers["Content-Type"] = probe["ct"]
    try:
        resp = await client.request(
            probe["method"],
            probe["url"],
            headers=headers,
            content=probe.get("body"),
            timeout=15.0,
            follow_redirects=False,
        )
        body_head = resp.content[:800]
        try:
            body_text = body_head.decode("utf-8")
        except UnicodeDecodeError:
            body_text = repr(body_head)
        return {
            "id": probe["id"],
            "method": probe["method"],
            "url": probe["url"],
            "status": resp.status_code,
            "reason": resp.reason_phrase,
            "headers": dict(resp.headers),
            "auth_challenge": resp.headers.get("www-authenticate"),
            "redirect": resp.headers.get("location"),
            "body_size": len(resp.content),
            "body_head_text": body_text,
            "elapsed_seconds": (dt.datetime.now(tz=dt.timezone.utc) - started).total_seconds(),
        }
    except Exception as e:
        return {
            "id": probe["id"],
            "method": probe["method"],
            "url": probe["url"],
            "error": f"{type(e).__name__}: {e}",
            "elapsed_seconds": (dt.datetime.now(tz=dt.timezone.utc) - started).total_seconds(),
        }


async def main() -> int:
    ts = dt.datetime.now(tz=dt.timezone.utc).strftime("%Y%m%d-%H%M%S")
    out_dir = OUT_DIR / ts
    out_dir.mkdir(parents=True, exist_ok=True)

    results = []
    print(f"=== Stock-provider OAuth probe ({len(PROBES)} requests) ===")
    async with httpx.AsyncClient(http2=False, verify=True) as client:
        for i, probe in enumerate(PROBES, 1):
            r = await run_one(client, probe)
            results.append(r)
            tag = (
                "ERR " + r["error"][:40]
                if "error" in r
                else (
                    f"{r['status']:3} ct={(r['headers'].get('content-type') or '?')[:25]:25} "
                    f"size={r['body_size']:6}B"
                    + (f" -> {r['redirect'][:40]}" if r.get("redirect") else "")
                    + (f"  AUTH={r['auth_challenge'][:40]}" if r.get("auth_challenge") else "")
                )
            )
            print(f"  [{i:02}/{len(PROBES)}] {probe['method']:5} {probe['url'][:70]:70} {tag}")
            await asyncio.sleep(0.25)

    out_path = out_dir / "results.json"
    out_path.write_text(
        json.dumps(
            {
                "schema": "tc-stockprovider-oauth-probe/v1",
                "timestamp_utc": ts,
                "results": results,
            },
            indent=2,
        )
    )
    print(f"\nWrote {out_path}\n")

    print("=== Discovery endpoints ===")
    for r in results:
        if "error" in r:
            continue
        if "well-known" in r["url"] and r["status"] == 200:
            print(f"  ✓ {r['url']}")
            try:
                meta = json.loads(r["body_head_text"])
                for k in (
                    "authorization_endpoint",
                    "token_endpoint",
                    "issuer",
                    "scopes_supported",
                    "grant_types_supported",
                    "response_types_supported",
                ):
                    if k in meta:
                        print(f"      {k}: {meta[k]}")
            except json.JSONDecodeError:
                print(f"      (response is not JSON: {r['body_head_text'][:80]})")

    print("\n=== Token endpoint behavior (grant_type=client_credentials with bogus creds) ===")
    for r in results:
        if "error" in r:
            continue
        if "/token" in r["url"]:
            print(f"  [{r['status']}] {r['url']}")
            for line in (r["body_head_text"] or "").splitlines()[:6]:
                print(f"    | {line[:200]}")

    print("\n=== Other interesting non-404 responses ===")
    for r in results:
        if "error" in r or r["status"] == 404 or r["status"] == 405:
            continue
        if "/token" in r["url"] or "well-known" in r["url"]:
            continue  # already covered above
        first_line = (r["body_head_text"].splitlines() or [""])[0][:120]
        print(f"  [{r['status']}] {r['id']:25}  {first_line}")

    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
