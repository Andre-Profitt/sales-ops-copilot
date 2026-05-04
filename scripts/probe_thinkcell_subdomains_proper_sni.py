#!/usr/bin/env python3
"""Probe the 60 wildcard-DNS-resolved *.prod.ai.think-cell.com subdomains
with PROPER DNS+SNI (not Host-header injection on the IP).

Round 2 found 60 subdomains under prod.ai.think-cell.com and appcom.think-cell.com
that all resolve to think-cell IPs (wildcard DNS). Vhost discovery via Host-header
injection on the IP showed only app.prod.ai. is configured. But that probe
went via IP-direct connection — meaning SNI was the IP, certificate was wrong.

This probe goes via real DNS resolution → SNI matches the subdomain → cert is
the wildcard cert → nginx sees the real Host header. If any of the 60 has a
distinct vhost configured, this probe sees it.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import json
import sys
from pathlib import Path

import httpx


ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "state" / "thinkcell_bridge" / "subdomain_proper_sni"


def load_round2_subdomains() -> list[str]:
    """Pull resolved subdomains from the latest round 2 results."""
    base = ROOT / "state" / "thinkcell_bridge" / "ai_round2"
    latest = sorted(base.iterdir())[-1] / "results.json"
    data = json.loads(latest.read_text())
    return [
        r["host"]
        for r in data.get("subdomain_brute", [])
        if r.get("ips") and "think-cell.com" in r["host"]
    ]


async def probe_one(client: httpx.AsyncClient, host: str) -> dict:
    """GET / on the subdomain via real DNS resolution (proper SNI)."""
    started = dt.datetime.now(tz=dt.timezone.utc)
    try:
        resp = await client.get(
            f"https://{host}/",
            headers={"User-Agent": "tc-sni/0.1"},
            timeout=10.0,
        )
        return {
            "host": host,
            "status": resp.status_code,
            "body_size": len(resp.content),
            "server": resp.headers.get("server"),
            "content_type": resp.headers.get("content-type"),
            "body_head": resp.content[:200].decode("utf-8", errors="replace"),
            "redirect": resp.headers.get("location"),
            "elapsed_seconds": (dt.datetime.now(tz=dt.timezone.utc) - started).total_seconds(),
        }
    except httpx.ConnectError as e:
        return {"host": host, "error": f"connect: {str(e)[:80]}"}
    except httpx.TimeoutException:
        return {"host": host, "error": "timeout"}
    except Exception as e:
        return {"host": host, "error": f"{type(e).__name__}: {str(e)[:80]}"}


async def main() -> int:
    ts = dt.datetime.now(tz=dt.timezone.utc).strftime("%Y%m%d-%H%M%S")
    out_dir = OUT_DIR / ts
    out_dir.mkdir(parents=True, exist_ok=True)

    subdomains = load_round2_subdomains()
    print(f"=== Probing {len(subdomains)} resolved subdomains via proper SNI ===\n")

    # Always include the known-good baseline as control
    if "app.prod.ai.think-cell.com" not in subdomains:
        subdomains = ["app.prod.ai.think-cell.com"] + subdomains

    results = []
    async with httpx.AsyncClient(http2=False, timeout=10.0, verify=True) as client:
        for i, host in enumerate(subdomains, 1):
            r = await probe_one(client, host)
            results.append(r)
            if "error" in r:
                tag = f"ERR  {r['error'][:50]}"
            else:
                tag = f"{r['status']:3} {r['body_size']:6}B server={(r.get('server') or '?')[:15]:15} ct={(r.get('content_type') or '?')[:25]:25}"
            print(f"  [{i:02}/{len(subdomains)}] {host[:55]:55} {tag}")
            await asyncio.sleep(0.2)

    out_path = out_dir / "results.json"
    out_path.write_text(
        json.dumps(
            {
                "schema": "tc-subdomain-proper-sni/v1",
                "timestamp_utc": ts,
                "results": results,
            },
            indent=2,
        )
    )

    # ---------- Anomaly extraction ----------
    print(f"\nWrote {out_path}\n")
    print("=== Status code distribution ===")
    counts: dict = {}
    for r in results:
        if "error" in r:
            counts["error"] = counts.get("error", 0) + 1
            continue
        key = (r["status"], r.get("server", "?"), r["body_size"])
        counts[key] = counts.get(key, 0) + 1
    for k, c in sorted(counts.items(), key=lambda x: -x[1]):
        print(f"  {c:4}× {k}")

    print("\n=== Anomalies (anything NOT matching baseline) ===")
    # Baseline = app.prod.ai → we know that's 403 nginx 146B
    baseline_key = (403, "nginx", 146)
    anomalies = [
        r
        for r in results
        if "error" not in r and (r["status"], r.get("server", "?"), r["body_size"]) != baseline_key
    ]
    for r in anomalies:
        head_oneline = (r["body_head"].splitlines() or [""])[0][:120]
        print(
            f"  [{r['status']}] {r['host'][:55]:55} server={(r.get('server') or '?')[:15]:15} {r['body_size']:6}B  {head_oneline}"
        )

    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
