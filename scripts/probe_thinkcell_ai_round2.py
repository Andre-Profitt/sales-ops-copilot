#!/usr/bin/env python3
"""Round-2 AI recon — followups based on round-1 findings.

Round-1 confirmed:
  - The edge is nginx (not Cloud Armor — nginx Server header)
  - 548B vs 146B difference is just nginx browser-friendly padding (cosmetic)
  - Reverse PTR is bc.googleusercontent.com → behind GCP HTTPS LB
  - Sibling IPs returned EMPTY error strings (silent failure or 0-byte body)
  - GitHub search returned valid 200 HTML pages but we didn't extract results
  - crt.sh returned only 1 expired wildcard cert — suspicious undercount

Round 2 pursues:
  A. crt.sh follow-up via the proper LIKE syntax + censys-style fallback
  B. Subdomain wordlist brute force on *.prod.ai.think-cell.com
  C. Proper sibling-IP probing with captured status (not just empty errors)
  D. Vhost discovery on 34.159.52.56 (try multiple Host values)
  E. GitHub code-search HTML parsing (extract actual hits)
  F. Wayback Machine probe for the AI URL
  G. DNS query via 1.1.1.1 directly (cross-check vs system resolver)
"""

from __future__ import annotations

import asyncio
import datetime as dt
import json
import re
import socket
import sys
from pathlib import Path
from typing import Any

import httpx


ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "state" / "thinkcell_bridge" / "ai_round2"

AI_HOST = "app.prod.ai.think-cell.com"
AI_IP = "34.159.52.56"


async def crt_sh_better() -> dict[str, Any]:
    """Try crt.sh with both URL-encoded and bare wildcard, plus pagination + a deeper query."""
    out: dict[str, Any] = {"queries": []}
    queries = [
        ("https://crt.sh/?q=%25.think-cell.com&output=json", "wildcard %"),
        ("https://crt.sh/?q=think-cell.com&output=json", "exact"),
        ("https://crt.sh/?q=%25.prod.ai.think-cell.com&output=json", "wildcard prod.ai"),
        ("https://crt.sh/?q=%25.appcom.think-cell.com&output=json", "wildcard appcom"),
    ]
    async with httpx.AsyncClient(timeout=60.0) as client:
        for url, label in queries:
            try:
                resp = await client.get(url, headers={"User-Agent": "tc-recon-r2/0.1"})
                if resp.status_code == 200 and resp.text.strip().startswith("["):
                    data = resp.json()
                    names: set[str] = set()
                    for entry in data:
                        for name in (entry.get("name_value") or "").splitlines():
                            name = name.strip().lower()
                            if name.endswith(".think-cell.com") or name == "think-cell.com":
                                names.add(name)
                    out["queries"].append(
                        {
                            "label": label,
                            "url": url,
                            "rows": len(data),
                            "unique_names": sorted(names),
                        }
                    )
                else:
                    out["queries"].append(
                        {
                            "label": label,
                            "url": url,
                            "status": resp.status_code,
                            "body_head": resp.text[:200],
                        }
                    )
            except Exception as e:
                out["queries"].append({"label": label, "url": url, "error": str(e)})
            await asyncio.sleep(1.0)
    # Aggregate union of all unique names
    all_names: set[str] = set()
    for q in out["queries"]:
        for n in q.get("unique_names", []) or []:
            all_names.add(n)
    out["all_unique_names"] = sorted(all_names)
    return out


async def subdomain_brute() -> list[dict[str, Any]]:
    """Try a wordlist of likely subdomains under prod.ai.think-cell.com."""
    words = [
        "api",
        "admin",
        "auth",
        "beta",
        "dev",
        "edge",
        "gateway",
        "grpc",
        "internal",
        "lb",
        "loadbalancer",
        "metadata",
        "metrics",
        "monitoring",
        "ops",
        "prod",
        "staging",
        "stg",
        "test",
        "v1",
        "v2",
        "v3",
        "web",
        "ws",
        "wss",
        "console",
        "dashboard",
        "health",
        "status",
        "diag",
        "diagnostics",
        "openapi",
        "swagger",
        "docs",
        "support",
        "billing",
        "license",
        "telemetry",
        "logs",
        "trace",
        "audit",
        "secrets",
        "key",
        "keys",
        "cert",
        "certs",
        "model",
        "models",
        "embedding",
        "embeddings",
        "vector",
        "search",
        "index",
        "ingest",
        "egress",
        "redis",
        "db",
        "sql",
        "store",
        "cache",
    ]
    results = []
    for w in words:
        for parent in ["prod.ai.think-cell.com", "appcom.think-cell.com"]:
            host = f"{w}.{parent}"
            row = {"host": host, "ips": []}
            try:
                infos = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
                row["ips"] = sorted({i[4][0] for i in infos})
            except socket.gaierror as e:
                row["error"] = str(e)
            except Exception as e:
                row["error"] = f"{type(e).__name__}: {e}"
            results.append(row)
    return results


async def sibling_ip_probe() -> list[dict[str, Any]]:
    """Probe sibling IPs in the GCP /29 with proper Host header + capture full response."""
    base = AI_IP.rsplit(".", 1)[0]
    last = int(AI_IP.rsplit(".", 1)[1])
    targets = [f"{base}.{last + d}" for d in range(-4, 5) if d != 0]
    results = []
    async with httpx.AsyncClient(http2=False, timeout=8.0, verify=False) as client:
        for ip in targets:
            for host_value in [AI_HOST, "app.prod.ai.think-cell.com", "default", ""]:
                row = {"ip": ip, "host_header": host_value}
                try:
                    headers = {"User-Agent": "tc-sib/0.1"}
                    if host_value:
                        headers["Host"] = host_value
                    resp = await client.get(f"https://{ip}/", headers=headers)
                    row["status"] = resp.status_code
                    row["body_size"] = len(resp.content)
                    row["server"] = resp.headers.get("server")
                    row["body_head"] = resp.content[:200].decode("utf-8", errors="replace")
                except httpx.ConnectError as e:
                    row["error"] = f"connect: {str(e)[:60]}"
                except httpx.TimeoutException:
                    row["error"] = "timeout"
                except Exception as e:
                    row["error"] = f"{type(e).__name__}: {str(e)[:60]}"
                results.append(row)
                await asyncio.sleep(0.15)
    return results


async def vhost_discovery() -> list[dict[str, Any]]:
    """Probe 34.159.52.56 with various Host headers — see what vhosts the LB serves."""
    hosts_to_try = [
        AI_HOST,
        "prod.ai.think-cell.com",
        "ai.think-cell.com",
        "ai.appcom.think-cell.com",
        "core.think-cell.com",
        "api.think-cell.com",
        "default.think-cell.com",
        "thinkcell.googleusercontent.com",
        "thinkcell.run.app",
        "thinkcell-prod.uc.r.appspot.com",
    ]
    results = []
    async with httpx.AsyncClient(http2=False, timeout=8.0, verify=False) as client:
        for h in hosts_to_try:
            try:
                resp = await client.get(
                    f"https://{AI_IP}/",
                    headers={"Host": h, "User-Agent": "tc-vhost/0.1"},
                )
                results.append(
                    {
                        "host_header": h,
                        "status": resp.status_code,
                        "body_size": len(resp.content),
                        "server": resp.headers.get("server"),
                        "body_head": resp.content[:200].decode("utf-8", errors="replace"),
                    }
                )
            except Exception as e:
                results.append({"host_header": h, "error": f"{type(e).__name__}: {str(e)[:60]}"})
            await asyncio.sleep(0.15)
    return results


async def github_extract() -> dict[str, Any]:
    """Re-run GitHub search and ACTUALLY extract result counts + file paths."""
    queries = [
        "app.prod.ai.think-cell.com",
        "PpAICoreURL",
        "aiauthentication.appcom",
        '"thinkcell.addin"',
    ]
    out: dict[str, Any] = {"queries": []}
    async with httpx.AsyncClient(timeout=20.0) as client:
        for q in queries:
            try:
                resp = await client.get(
                    "https://github.com/search",
                    params={"q": q, "type": "code"},
                    headers={"User-Agent": "Mozilla/5.0 tc-recon/0.1"},
                )
                html = resp.text
                # Look for the JSON-LD search-results block or repo links
                repo_hits = re.findall(r'href="/([^"]+/[^"]+)/blob/[^"]+"', html)
                noresult_marker = "We couldn't find any" in html or "No results matched" in html
                # Also check for the React-rendered count
                count_m = re.search(r"(\d+)\s+code result", html, re.IGNORECASE)
                out["queries"].append(
                    {
                        "q": q,
                        "status": resp.status_code,
                        "looks_like_no_results": noresult_marker,
                        "result_count_in_html": int(count_m.group(1)) if count_m else None,
                        "repo_hits_unique": sorted(set(repo_hits))[:20],
                        "html_size": len(html),
                    }
                )
            except Exception as e:
                out["queries"].append({"q": q, "error": str(e)})
            await asyncio.sleep(2.5)
    return out


async def wayback_probe() -> dict[str, Any]:
    """Check Wayback Machine for any indexed snapshots of the AI URL."""
    targets = [
        f"https://{AI_HOST}/",
        f"https://{AI_HOST}/core/",
        "https://aiauthentication.appcom.think-cell.com/",
        "https://schemas.think-cell.com/",
    ]
    out: dict[str, Any] = {"targets": []}
    async with httpx.AsyncClient(timeout=15.0) as client:
        for url in targets:
            try:
                # Wayback CDX API gives all snapshots
                resp = await client.get(
                    "https://web.archive.org/cdx/search/cdx",
                    params={"url": url, "output": "json", "limit": 25},
                )
                if resp.status_code == 200:
                    data = resp.json()
                    out["targets"].append(
                        {
                            "url": url,
                            "snapshot_count": max(len(data) - 1, 0),
                            "first_snapshot": data[1] if len(data) > 1 else None,
                            "last_snapshot": data[-1] if len(data) > 1 else None,
                        }
                    )
                else:
                    out["targets"].append({"url": url, "status": resp.status_code})
            except Exception as e:
                out["targets"].append({"url": url, "error": str(e)})
            await asyncio.sleep(1.0)
    return out


async def dns_cross_check() -> dict[str, Any]:
    """Resolve via 1.1.1.1 directly (DNS-over-HTTPS) as a cross-check vs system resolver."""
    out: dict[str, Any] = {"queries": []}
    targets = [
        AI_HOST,
        "prod.ai.think-cell.com",
        "ai.think-cell.com",
        "ai.appcom.think-cell.com",
        "aiauthentication.appcom.think-cell.com",
    ]
    async with httpx.AsyncClient(timeout=10.0) as client:
        for host in targets:
            for qtype in ("A", "AAAA", "CNAME", "TXT", "MX", "SRV"):
                try:
                    resp = await client.get(
                        "https://1.1.1.1/dns-query",
                        params={"name": host, "type": qtype},
                        headers={"Accept": "application/dns-json"},
                    )
                    if resp.status_code == 200:
                        d = resp.json()
                        ans = d.get("Answer", []) or []
                        if ans:
                            out["queries"].append(
                                {
                                    "host": host,
                                    "type": qtype,
                                    "answers": [
                                        {"name": a.get("name"), "data": a.get("data")} for a in ans
                                    ],
                                }
                            )
                except Exception as e:
                    out["queries"].append({"host": host, "type": qtype, "error": str(e)})
                await asyncio.sleep(0.1)
    return out


async def main() -> int:
    ts = dt.datetime.now(tz=dt.timezone.utc).strftime("%Y%m%d-%H%M%S")
    out_dir = OUT_DIR / ts
    out_dir.mkdir(parents=True, exist_ok=True)

    print("=== Round 2 AI recon ===\n")
    bundle: dict[str, Any] = {"timestamp_utc": ts, "schema": "tc-ai-round2/v1"}

    print("A. crt.sh follow-up...")
    bundle["crt_sh_better"] = await crt_sh_better()
    print(
        f"   Total unique *.think-cell.com names: {len(bundle['crt_sh_better']['all_unique_names'])}"
    )

    print("\nB. Subdomain wordlist brute force...")
    sb = await subdomain_brute()
    bundle["subdomain_brute"] = sb
    hits = [r for r in sb if r.get("ips")]
    print(f"   Resolved {len(hits)} of {len(sb)} candidate subdomains")
    for h in hits[:20]:
        print(f"     {h['host']:55} -> {h['ips']}")

    print("\nC. Sibling IP probing (with proper response capture)...")
    bundle["sibling_ip_probe"] = await sibling_ip_probe()
    interesting_sibs = [r for r in bundle["sibling_ip_probe"] if "status" in r]
    print(f"   Got responses from {len(interesting_sibs)} of {len(bundle['sibling_ip_probe'])}")
    for r in interesting_sibs[:10]:
        print(
            f"     {r['ip']:16} host={r['host_header'][:40]:40} -> {r['status']} {r['body_size']}B server={r.get('server')}"
        )

    print("\nD. Vhost discovery on 34.159.52.56...")
    bundle["vhost_discovery"] = await vhost_discovery()
    for r in bundle["vhost_discovery"]:
        if "error" in r:
            print(f"     {r['host_header'][:40]:40} ERR {r['error'][:50]}")
        else:
            print(
                f"     {r['host_header'][:40]:40} -> {r['status']} {r['body_size']}B server={r.get('server')}"
            )

    print("\nE. GitHub code-search extraction...")
    bundle["github_extract"] = await github_extract()
    for q in bundle["github_extract"]["queries"]:
        if "error" in q:
            print(f"     q={q['q']:40} ERR")
        else:
            tag = (
                "NO RESULTS"
                if q.get("looks_like_no_results")
                else f"hits={q.get('result_count_in_html', '?')}"
            )
            print(f"     q={q['q']:40} {tag} repos={len(q.get('repo_hits_unique', []))}")
            for repo in q.get("repo_hits_unique", [])[:3]:
                print(f"       repo: {repo}")

    print("\nF. Wayback Machine snapshots...")
    bundle["wayback"] = await wayback_probe()
    for t in bundle["wayback"]["targets"]:
        if "error" in t:
            print(f"     {t['url']:60} ERR {t['error'][:40]}")
        else:
            print(f"     {t['url']:60} snapshots={t.get('snapshot_count')}")
            if t.get("first_snapshot"):
                print(f"       first: {t['first_snapshot']}")

    print("\nG. DNS cross-check via 1.1.1.1 DoH...")
    bundle["dns_cross"] = await dns_cross_check()
    for q in bundle["dns_cross"]["queries"]:
        if "answers" in q:
            for a in q["answers"]:
                print(f"     {q['type']:5} {q['host']:50} -> {a['data'][:60]}")

    out_path = out_dir / "results.json"
    out_path.write_text(json.dumps(bundle, indent=2, default=str))
    print(f"\nWrote {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
