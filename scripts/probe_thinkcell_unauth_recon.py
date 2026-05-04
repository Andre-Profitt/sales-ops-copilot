#!/usr/bin/env python3
"""Unauthenticated reconnaissance against three under-probed think-cell hosts.

  #2 — app.prod.ai.think-cell.com sub-paths
  #3 — aiauthentication.appcom.think-cell.com response shapes
  #5 — update.appcom.think-cell.com wire format

Strictly unauthenticated. Looks for:
  - Which auth header / scheme is expected (401 challenge body)
  - Sub-paths that DON'T require auth (admin/health/diag)
  - Token-exchange flow shape (what the auth endpoint returns to malformed input)
  - Update mechanism's payload + version-query format

Persists to state/thinkcell_bridge/unauth_recon/<TS>/results.json.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import json
import sys
from pathlib import Path

import httpx


ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "state" / "thinkcell_bridge" / "unauth_recon"
UA = "tc-recon/0.1 (+personal-recon)"


# Probe taxonomy: (name, method, base, path, body, content_type, expect_kind)
PROBES = [
    # ---------- #2: app.prod.ai.think-cell.com sub-path enumeration ----------
    {
        "id": "ai_root",
        "method": "GET",
        "base": "https://app.prod.ai.think-cell.com",
        "path": "/",
        "body": None,
        "ct": None,
    },
    {
        "id": "ai_options_root",
        "method": "OPTIONS",
        "base": "https://app.prod.ai.think-cell.com",
        "path": "/",
        "body": None,
        "ct": None,
    },
    {
        "id": "ai_core",
        "method": "GET",
        "base": "https://app.prod.ai.think-cell.com",
        "path": "/core/",
        "body": None,
        "ct": None,
    },
    {
        "id": "ai_core_options",
        "method": "OPTIONS",
        "base": "https://app.prod.ai.think-cell.com",
        "path": "/core/",
        "body": None,
        "ct": None,
    },
    {
        "id": "ai_core_post_empty",
        "method": "POST",
        "base": "https://app.prod.ai.think-cell.com",
        "path": "/core/",
        "body": b"",
        "ct": None,
    },
    {
        "id": "ai_core_post_json",
        "method": "POST",
        "base": "https://app.prod.ai.think-cell.com",
        "path": "/core/",
        "body": b'{"messages":[{"role":"user","content":"ping"}]}',
        "ct": "application/json",
    },
    {
        "id": "ai_core_v1",
        "method": "GET",
        "base": "https://app.prod.ai.think-cell.com",
        "path": "/core/v1/",
        "body": None,
        "ct": None,
    },
    {
        "id": "ai_core_v1_chat",
        "method": "POST",
        "base": "https://app.prod.ai.think-cell.com",
        "path": "/core/v1/chat/completions",
        "body": b'{"messages":[]}',
        "ct": "application/json",
    },
    {
        "id": "ai_core_chat",
        "method": "POST",
        "base": "https://app.prod.ai.think-cell.com",
        "path": "/core/chat",
        "body": b"{}",
        "ct": "application/json",
    },
    {
        "id": "ai_core_chat_completions",
        "method": "POST",
        "base": "https://app.prod.ai.think-cell.com",
        "path": "/core/chat/completions",
        "body": b'{"messages":[]}',
        "ct": "application/json",
    },
    {
        "id": "ai_core_models",
        "method": "GET",
        "base": "https://app.prod.ai.think-cell.com",
        "path": "/core/models",
        "body": None,
        "ct": None,
    },
    {
        "id": "ai_core_health",
        "method": "GET",
        "base": "https://app.prod.ai.think-cell.com",
        "path": "/core/health",
        "body": None,
        "ct": None,
    },
    {
        "id": "ai_core_healthz",
        "method": "GET",
        "base": "https://app.prod.ai.think-cell.com",
        "path": "/core/healthz",
        "body": None,
        "ct": None,
    },
    {
        "id": "ai_core_status",
        "method": "GET",
        "base": "https://app.prod.ai.think-cell.com",
        "path": "/core/status",
        "body": None,
        "ct": None,
    },
    {
        "id": "ai_core_ping",
        "method": "GET",
        "base": "https://app.prod.ai.think-cell.com",
        "path": "/core/ping",
        "body": None,
        "ct": None,
    },
    {
        "id": "ai_core_version",
        "method": "GET",
        "base": "https://app.prod.ai.think-cell.com",
        "path": "/core/version",
        "body": None,
        "ct": None,
    },
    {
        "id": "ai_core_openapi",
        "method": "GET",
        "base": "https://app.prod.ai.think-cell.com",
        "path": "/core/openapi.json",
        "body": None,
        "ct": None,
    },
    {
        "id": "ai_core_openapi_yaml",
        "method": "GET",
        "base": "https://app.prod.ai.think-cell.com",
        "path": "/core/openapi.yaml",
        "body": None,
        "ct": None,
    },
    {
        "id": "ai_core_swagger",
        "method": "GET",
        "base": "https://app.prod.ai.think-cell.com",
        "path": "/core/swagger.json",
        "body": None,
        "ct": None,
    },
    {
        "id": "ai_core_docs",
        "method": "GET",
        "base": "https://app.prod.ai.think-cell.com",
        "path": "/core/docs",
        "body": None,
        "ct": None,
    },
    {
        "id": "ai_core_metrics",
        "method": "GET",
        "base": "https://app.prod.ai.think-cell.com",
        "path": "/core/metrics",
        "body": None,
        "ct": None,
    },
    {
        "id": "ai_api",
        "method": "GET",
        "base": "https://app.prod.ai.think-cell.com",
        "path": "/api",
        "body": None,
        "ct": None,
    },
    {
        "id": "ai_api_v1",
        "method": "GET",
        "base": "https://app.prod.ai.think-cell.com",
        "path": "/api/v1",
        "body": None,
        "ct": None,
    },
    {
        "id": "ai_v1",
        "method": "GET",
        "base": "https://app.prod.ai.think-cell.com",
        "path": "/v1",
        "body": None,
        "ct": None,
    },
    {
        "id": "ai_well_known_oauth",
        "method": "GET",
        "base": "https://app.prod.ai.think-cell.com",
        "path": "/.well-known/oauth-authorization-server",
        "body": None,
        "ct": None,
    },
    {
        "id": "ai_well_known_openid",
        "method": "GET",
        "base": "https://app.prod.ai.think-cell.com",
        "path": "/.well-known/openid-configuration",
        "body": None,
        "ct": None,
    },
    {
        "id": "ai_robots",
        "method": "GET",
        "base": "https://app.prod.ai.think-cell.com",
        "path": "/robots.txt",
        "body": None,
        "ct": None,
    },
    # ---------- #3: aiauthentication.appcom.think-cell.com response-shape probes ----------
    {
        "id": "auth_root",
        "method": "GET",
        "base": "https://aiauthentication.appcom.think-cell.com",
        "path": "/",
        "body": None,
        "ct": None,
    },
    {
        "id": "auth_options_root",
        "method": "OPTIONS",
        "base": "https://aiauthentication.appcom.think-cell.com",
        "path": "/",
        "body": None,
        "ct": None,
    },
    {
        "id": "auth_post_empty",
        "method": "POST",
        "base": "https://aiauthentication.appcom.think-cell.com",
        "path": "/",
        "body": b"",
        "ct": None,
    },
    {
        "id": "auth_post_json_empty",
        "method": "POST",
        "base": "https://aiauthentication.appcom.think-cell.com",
        "path": "/",
        "body": b"{}",
        "ct": "application/json",
    },
    {
        "id": "auth_post_form_empty",
        "method": "POST",
        "base": "https://aiauthentication.appcom.think-cell.com",
        "path": "/",
        "body": b"",
        "ct": "application/x-www-form-urlencoded",
    },
    {
        "id": "auth_post_form_bogus",
        "method": "POST",
        "base": "https://aiauthentication.appcom.think-cell.com",
        "path": "/",
        "body": b"licensekeyid=00000000-0000-0000-0000-000000000000&hash=DEADBEEFDEADBEEFDEADBE",
        "ct": "application/x-www-form-urlencoded",
    },
    {
        "id": "auth_token",
        "method": "POST",
        "base": "https://aiauthentication.appcom.think-cell.com",
        "path": "/token",
        "body": b"",
        "ct": "application/x-www-form-urlencoded",
    },
    {
        "id": "auth_refresh",
        "method": "POST",
        "base": "https://aiauthentication.appcom.think-cell.com",
        "path": "/refresh",
        "body": b"",
        "ct": "application/json",
    },
    {
        "id": "auth_renew",
        "method": "POST",
        "base": "https://aiauthentication.appcom.think-cell.com",
        "path": "/renew",
        "body": b"",
        "ct": "application/json",
    },
    {
        "id": "auth_authorize",
        "method": "GET",
        "base": "https://aiauthentication.appcom.think-cell.com",
        "path": "/authorize",
        "body": None,
        "ct": None,
    },
    {
        "id": "auth_api",
        "method": "GET",
        "base": "https://aiauthentication.appcom.think-cell.com",
        "path": "/api",
        "body": None,
        "ct": None,
    },
    {
        "id": "auth_v1",
        "method": "GET",
        "base": "https://aiauthentication.appcom.think-cell.com",
        "path": "/v1",
        "body": None,
        "ct": None,
    },
    {
        "id": "auth_health",
        "method": "GET",
        "base": "https://aiauthentication.appcom.think-cell.com",
        "path": "/health",
        "body": None,
        "ct": None,
    },
    {
        "id": "auth_healthz",
        "method": "GET",
        "base": "https://aiauthentication.appcom.think-cell.com",
        "path": "/healthz",
        "body": None,
        "ct": None,
    },
    {
        "id": "auth_well_known_oauth",
        "method": "GET",
        "base": "https://aiauthentication.appcom.think-cell.com",
        "path": "/.well-known/oauth-authorization-server",
        "body": None,
        "ct": None,
    },
    {
        "id": "auth_well_known_openid",
        "method": "GET",
        "base": "https://aiauthentication.appcom.think-cell.com",
        "path": "/.well-known/openid-configuration",
        "body": None,
        "ct": None,
    },
    # ---------- #5: update.appcom.think-cell.com wire format ----------
    # We have evidence of: https://update.appcom.think-cell.com/?build=1000220&licensekey=
    # (from the auth_oauth_string_mining urls_with_path list)
    {
        "id": "update_root",
        "method": "GET",
        "base": "https://update.appcom.think-cell.com",
        "path": "/",
        "body": None,
        "ct": None,
    },
    {
        "id": "update_options",
        "method": "OPTIONS",
        "base": "https://update.appcom.think-cell.com",
        "path": "/",
        "body": None,
        "ct": None,
    },
    {
        "id": "update_query_empty",
        "method": "GET",
        "base": "https://update.appcom.think-cell.com",
        "path": "/?build=&licensekey=",
        "body": None,
        "ct": None,
    },
    {
        "id": "update_query_known_build",
        "method": "GET",
        "base": "https://update.appcom.think-cell.com",
        "path": "/?build=1000220&licensekey=",
        "body": None,
        "ct": None,
    },
    {
        "id": "update_query_old_build",
        "method": "GET",
        "base": "https://update.appcom.think-cell.com",
        "path": "/?build=900000&licensekey=",
        "body": None,
        "ct": None,
    },
    {
        "id": "update_query_future",
        "method": "GET",
        "base": "https://update.appcom.think-cell.com",
        "path": "/?build=99999999&licensekey=",
        "body": None,
        "ct": None,
    },
    {
        "id": "update_post_empty",
        "method": "POST",
        "base": "https://update.appcom.think-cell.com",
        "path": "/",
        "body": b"",
        "ct": "application/json",
    },
    {
        "id": "update_api",
        "method": "GET",
        "base": "https://update.appcom.think-cell.com",
        "path": "/api",
        "body": None,
        "ct": None,
    },
    {
        "id": "update_health",
        "method": "GET",
        "base": "https://update.appcom.think-cell.com",
        "path": "/health",
        "body": None,
        "ct": None,
    },
    {
        "id": "update_healthz",
        "method": "GET",
        "base": "https://update.appcom.think-cell.com",
        "path": "/healthz",
        "body": None,
        "ct": None,
    },
    {
        "id": "update_manifest",
        "method": "GET",
        "base": "https://update.appcom.think-cell.com",
        "path": "/manifest",
        "body": None,
        "ct": None,
    },
    {
        "id": "update_manifest_json",
        "method": "GET",
        "base": "https://update.appcom.think-cell.com",
        "path": "/manifest.json",
        "body": None,
        "ct": None,
    },
    {
        "id": "update_versions",
        "method": "GET",
        "base": "https://update.appcom.think-cell.com",
        "path": "/versions",
        "body": None,
        "ct": None,
    },
    {
        "id": "update_latest",
        "method": "GET",
        "base": "https://update.appcom.think-cell.com",
        "path": "/latest",
        "body": None,
        "ct": None,
    },
    {
        "id": "update_check",
        "method": "GET",
        "base": "https://update.appcom.think-cell.com",
        "path": "/check",
        "body": None,
        "ct": None,
    },
]


async def run_one(client: httpx.AsyncClient, probe: dict) -> dict:
    method = probe["method"]
    url = probe["base"] + probe["path"]
    headers = {"User-Agent": UA}
    if probe["ct"]:
        headers["Content-Type"] = probe["ct"]

    started = dt.datetime.now(tz=dt.timezone.utc)
    try:
        resp = await client.request(
            method,
            url,
            headers=headers,
            content=probe["body"],
            timeout=15.0,
            follow_redirects=False,
        )
        body = resp.content
        body_head = body[:600]
        try:
            body_text = body_head.decode("utf-8")
        except UnicodeDecodeError:
            body_text = repr(body_head)
        # Capture WWW-Authenticate header if present (auth challenge)
        return {
            "id": probe["id"],
            "method": method,
            "url": url,
            "ct_sent": probe["ct"],
            "body_sent_size": len(probe["body"] or b""),
            "status": resp.status_code,
            "reason": resp.reason_phrase,
            "headers": dict(resp.headers),
            "auth_challenge": resp.headers.get("www-authenticate"),
            "set_cookie": resp.headers.get("set-cookie"),
            "body_size": len(body),
            "body_head_text": body_text,
            "elapsed_seconds": (dt.datetime.now(tz=dt.timezone.utc) - started).total_seconds(),
        }
    except Exception as e:
        return {
            "id": probe["id"],
            "method": method,
            "url": url,
            "error": f"{type(e).__name__}: {e}",
            "elapsed_seconds": (dt.datetime.now(tz=dt.timezone.utc) - started).total_seconds(),
        }


async def main() -> int:
    ts = dt.datetime.now(tz=dt.timezone.utc).strftime("%Y%m%d-%H%M%S")
    out_dir = OUT_DIR / ts
    out_dir.mkdir(parents=True, exist_ok=True)
    print(f"=== Unauth recon: {len(PROBES)} probes across 3 hosts ===")

    results = []
    async with httpx.AsyncClient(http2=False, verify=True) as client:
        for i, probe in enumerate(PROBES, 1):
            r = await run_one(client, probe)
            results.append(r)
            if "error" in r:
                tag = f"ERR  {r['error'][:50]}"
            else:
                ct = (r["headers"].get("content-type") or "?")[:25]
                challenge = "AUTH" if r.get("auth_challenge") else "    "
                tag = f"{r['status']:3}  {challenge}  {ct:25}  {r['body_size']:6}B"
            print(
                f"  [{i:02}/{len(PROBES)}] {probe['method']:7} {probe['base'].replace('https://', '')[:35]:35} {probe['path']:42} {tag}"
            )
            await asyncio.sleep(0.25)

    out_path = out_dir / "results.json"
    out_path.write_text(
        json.dumps(
            {
                "schema": "tc-unauth-recon/v1",
                "timestamp_utc": ts,
                "probe_count": len(results),
                "results": results,
            },
            indent=2,
        )
    )

    # ---------- Quick analysis ----------
    print(f"\nWrote {out_path}\n")
    print("=== Status code distribution per host ===")
    by_host: dict[str, dict[int, int]] = {}
    for r in results:
        if "error" in r:
            continue
        host = r["url"].split("/")[2]
        by_host.setdefault(host, {})
        by_host[host][r["status"]] = by_host[host].get(r["status"], 0) + 1
    for h, counts in by_host.items():
        print(f"  {h}: {dict(sorted(counts.items()))}")

    print("\n=== Auth challenges (WWW-Authenticate header observed) ===")
    challenges = [
        (r["id"], r["auth_challenge"], r["status"]) for r in results if r.get("auth_challenge")
    ]
    if not challenges:
        print("  (none — endpoints don't advertise auth scheme via WWW-Authenticate)")
    else:
        for cid, c, status in challenges:
            print(f"  [{status}] {cid:30}  {c[:80]}")

    print("\n=== Set-Cookie observed ===")
    cookies = [(r["id"], r["set_cookie"], r["status"]) for r in results if r.get("set_cookie")]
    if not cookies:
        print("  (none)")
    else:
        for cid, c, status in cookies:
            print(f"  [{status}] {cid:30}  {c[:120]}")

    print("\n=== 200 responses (non-empty bodies) ===")
    twohundreds = [r for r in results if r.get("status") == 200 and r.get("body_size", 0) > 0]
    for r in twohundreds:
        first_line = r["body_head_text"].splitlines()[0][:120] if r["body_head_text"] else ""
        print(f"  [200] {r['id']:30}  {r['body_size']:6}B  {first_line}")

    print("\n=== Other interesting non-{404,405,400,empty-200} statuses ===")
    interesting = [
        r
        for r in results
        if "error" not in r
        and r["status"] not in (404, 405)
        and not (r["status"] == 200 and r["body_size"] == 0)
    ]
    seen_pairs = set()
    for r in interesting:
        key = (r["status"], r["id"].rsplit("_", 1)[0] if "_" in r["id"] else r["id"])
        if key in seen_pairs:
            continue
        seen_pairs.add(key)
        first_line = (r["body_head_text"].splitlines() or [""])[0][:160]
        print(
            f"  [{r['status']}] {r['id']:30}  ct={(r['headers'].get('content-type') or '?')[:20]:20}  {first_line}"
        )

    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
