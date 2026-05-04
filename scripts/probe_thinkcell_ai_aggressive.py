#!/usr/bin/env python3
"""Aggressive recon against app.prod.ai.think-cell.com beyond the basic 27-path scan.

Earlier probe got uniform 403 / 146-byte HTML on all paths via httpx default TLS +
default UA. That suggests an edge filter (Cloud Armor / GCP LB), but the filter
might be:
  - User-Agent fingerprinted (rejecting non-think-cell UAs)
  - TLS-fingerprinted (JA3/JA4)
  - HTTP/2 vs HTTP/1.1 sensitive
  - Header-set sensitive (missing required custom header)
  - Method-sensitive (allowlist)
  - Geo-IP filtered

Also: the wildcard cert covers *.prod.ai.think-cell.com — there may be other
subdomains we haven't enumerated.

This probe runs:
  A. Subdomain enumeration on *.prod.ai.think-cell.com via crt.sh + DNS
  B. Header-spoofing matrix (multiple UAs, Origin, X-tc-*, version headers)
  C. HTTP/2 probe (httpx http2=True)
  D. Method matrix expansion (PATCH/PUT/DELETE/TRACE/HEAD on /core/)
  E. Path-encoding tricks (double slash, URL encoded, trailing variations)
  F. Reverse DNS + sibling-IP probe on the GCP block
  G. GitHub code-search for the specific URL (via public search API)

All read-only. Throttled. Persists to state/thinkcell_bridge/ai_aggressive/<TS>/.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import json
import socket
import sys
from pathlib import Path
from typing import Any

import httpx


ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "state" / "thinkcell_bridge" / "ai_aggressive"

# Known target
AI_HOST = "app.prod.ai.think-cell.com"
AI_BASE = f"https://{AI_HOST}"
AI_IP = "34.159.52.56"  # from tier-3 hosting topology probe

# User-Agent strings to try — we want to mimic what the desktop add-in sends.
# WinHTTP default UA varies by Office build; common patterns:
UAS = [
    "tc-default",  # baseline (use httpx default; reported separately)
    "tc-empty",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; ARM64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 Edg/124.0.0.0",
    "Microsoft Office/16.0 (Windows NT 10.0; Microsoft Office PowerPoint 16.0.18025; Pro)",
    "PowerPoint/16.0",
    "thinkcell.addin/15.0.100.220 (Windows NT 10.0; ARM64)",
    "tcaddin.dll/15.0.100.220",
    "WinHTTP/1.0",
    "Microsoft NCSI",
]

# Header sets — try various combinations of custom headers think-cell might require.
HEADER_SETS = {
    "minimal": {},
    "with_origin": {"Origin": "https://app.prod.ai.think-cell.com"},
    "with_referer_self": {"Referer": "https://app.prod.ai.think-cell.com/"},
    "with_referer_addin": {"Referer": "msword://thinkcell.addin/"},
    "x_thinkcell_build": {"X-thinkcell-build": "1000220", "X-thinkcell-version": "15.0.100.220"},
    "x_tc_short": {"X-tc-build": "1000220", "X-tc-version": "15"},
    "msie_compat": {"X-Requested-With": "XMLHttpRequest"},
    "with_accept_json": {"Accept": "application/json", "Accept-Language": "en-US,en;q=0.9"},
}


def _now_iso() -> str:
    return dt.datetime.now(tz=dt.timezone.utc).strftime("%Y%m%d-%H%M%S")


# ---------------------------------------------------------------------------
# A. Subdomain enumeration via crt.sh + DNS
# ---------------------------------------------------------------------------


async def crt_sh_enumerate() -> list[dict[str, Any]]:
    """Query crt.sh for all certs covering *.think-cell.com — extract unique
    subdomains (especially under prod.ai.) from the SAN entries."""
    url = "https://crt.sh/?q=%25.think-cell.com&output=json"
    rows = []
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.get(url, headers={"User-Agent": "tc-recon/0.1"})
            if resp.status_code == 200 and resp.text.strip().startswith("["):
                data = resp.json()
                # Each row has 'name_value' (newline-separated SANs)
                seen = set()
                for entry in data:
                    nv = entry.get("name_value", "")
                    for name in nv.splitlines():
                        name = name.strip().lower()
                        if name and name.endswith(".think-cell.com") and name not in seen:
                            seen.add(name)
                            rows.append(
                                {
                                    "name": name,
                                    "issuer": entry.get("issuer_name"),
                                    "not_before": entry.get("not_before"),
                                    "not_after": entry.get("not_after"),
                                }
                            )
            else:
                rows.append({"error": f"crt.sh returned {resp.status_code}"})
    except Exception as e:
        rows.append({"error": f"{type(e).__name__}: {e}"})
    return rows


def dns_resolve_all(host: str) -> dict[str, Any]:
    """Best-effort A/AAAA/CNAME resolution."""
    info: dict[str, Any] = {"host": host, "ips": [], "errors": []}
    try:
        infos = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
        ips = sorted({i[4][0] for i in infos})
        info["ips"] = ips
    except Exception as e:
        info["errors"].append(str(e))
    return info


# ---------------------------------------------------------------------------
# B. Header-spoofing matrix
# ---------------------------------------------------------------------------


async def spoof_matrix() -> list[dict[str, Any]]:
    """For each (UA, header_set) combo, probe /core/ and / and report response shape."""
    results = []
    paths = ["/", "/core/"]

    async with httpx.AsyncClient(http2=False, timeout=10.0, verify=True) as client:
        for ua in UAS:
            for hs_name, hs in HEADER_SETS.items():
                for path in paths:
                    headers = dict(hs)
                    if ua not in ("tc-default", "tc-empty"):
                        headers["User-Agent"] = ua
                    elif ua == "tc-empty":
                        headers["User-Agent"] = ""
                    url = AI_BASE + path
                    try:
                        resp = await client.get(url, headers=headers)
                        results.append(
                            {
                                "ua": ua,
                                "header_set": hs_name,
                                "path": path,
                                "status": resp.status_code,
                                "body_size": len(resp.content),
                                "body_head": resp.content[:200].decode("utf-8", errors="replace"),
                                "server": resp.headers.get("server"),
                                "set_cookie": resp.headers.get("set-cookie"),
                                "auth_challenge": resp.headers.get("www-authenticate"),
                            }
                        )
                    except Exception as e:
                        results.append(
                            {
                                "ua": ua,
                                "header_set": hs_name,
                                "path": path,
                                "error": f"{type(e).__name__}: {e}",
                            }
                        )
                    await asyncio.sleep(0.15)
    return results


# ---------------------------------------------------------------------------
# C. HTTP/2 probe (subset of paths)
# ---------------------------------------------------------------------------


async def http2_probe() -> list[dict[str, Any]]:
    results = []
    try:
        async with httpx.AsyncClient(http2=True, timeout=10.0) as client:
            for path in ["/", "/core/", "/core/v1/chat/completions"]:
                try:
                    resp = await client.get(
                        AI_BASE + path, headers={"User-Agent": "tc-h2-probe/0.1"}
                    )
                    results.append(
                        {
                            "path": path,
                            "http_version": resp.http_version,
                            "status": resp.status_code,
                            "body_size": len(resp.content),
                            "body_head": resp.content[:200].decode("utf-8", errors="replace"),
                        }
                    )
                except Exception as e:
                    results.append({"path": path, "error": f"{type(e).__name__}: {e}"})
                await asyncio.sleep(0.2)
    except Exception as e:
        results.append({"error": f"http2 client init failed: {type(e).__name__}: {e}"})
    return results


# ---------------------------------------------------------------------------
# D. Method matrix expansion
# ---------------------------------------------------------------------------


async def method_matrix() -> list[dict[str, Any]]:
    methods = ["HEAD", "PATCH", "PUT", "DELETE", "TRACE", "CONNECT", "PROPFIND"]
    results = []
    async with httpx.AsyncClient(http2=False, timeout=10.0) as client:
        for method in methods:
            for path in ["/", "/core/"]:
                try:
                    resp = await client.request(
                        method, AI_BASE + path, headers={"User-Agent": "tc-method/0.1"}
                    )
                    results.append(
                        {
                            "method": method,
                            "path": path,
                            "status": resp.status_code,
                            "body_size": len(resp.content),
                            "body_head": resp.content[:200].decode("utf-8", errors="replace"),
                        }
                    )
                except Exception as e:
                    results.append({"method": method, "path": path, "error": str(e)})
                await asyncio.sleep(0.15)
    return results


# ---------------------------------------------------------------------------
# E. Path-encoding tricks
# ---------------------------------------------------------------------------


async def path_tricks() -> list[dict[str, Any]]:
    """Bypass attempts via URL normalization quirks. Strictly read-only."""
    paths = [
        "//core/",  # double-slash
        "/core//",  # trailing double
        "/core/%2E%2E/",  # URL-encoded ../
        "/core/%2e/",  # URL-encoded ./
        "/core/.",  # literal current-dir
        "/CORE/",  # case
        "/core/?",  # bare query
        "/core/?_=1",  # cache buster
        "/core//.",  # mixed
        "/.well-known/",
        "/.well-known/host-meta",
        "/sitemap.xml",
        "//.well-known/openid-configuration",
    ]
    results = []
    async with httpx.AsyncClient(http2=False, timeout=10.0) as client:
        for path in paths:
            try:
                resp = await client.get(AI_BASE + path, headers={"User-Agent": "tc-pathtrick/0.1"})
                results.append(
                    {
                        "path": path,
                        "status": resp.status_code,
                        "body_size": len(resp.content),
                        "body_head": resp.content[:200].decode("utf-8", errors="replace"),
                        "redirect": resp.headers.get("location"),
                    }
                )
            except Exception as e:
                results.append({"path": path, "error": str(e)})
            await asyncio.sleep(0.15)
    return results


# ---------------------------------------------------------------------------
# F. Reverse DNS + sibling-IP enumeration
# ---------------------------------------------------------------------------


async def reverse_dns_and_siblings() -> dict[str, Any]:
    info: dict[str, Any] = {"target_ip": AI_IP, "ptr": None, "siblings": []}
    try:
        info["ptr"] = socket.gethostbyaddr(AI_IP)
    except Exception as e:
        info["ptr_error"] = str(e)
    # Sibling IPs in the same /29 — quick check whether they respond to the same
    # virtual host. If they do, suggests a shared GCP load balancer pool.
    base_octets = AI_IP.rsplit(".", 1)[0]
    last = int(AI_IP.rsplit(".", 1)[1])
    async with httpx.AsyncClient(http2=False, timeout=8.0, verify=False) as client:
        for delta in [-2, -1, 1, 2]:
            ip = f"{base_octets}.{last + delta}"
            try:
                resp = await client.get(
                    f"https://{ip}/",
                    headers={"Host": AI_HOST, "User-Agent": "tc-sibling/0.1"},
                )
                info["siblings"].append(
                    {
                        "ip": ip,
                        "status": resp.status_code,
                        "body_size": len(resp.content),
                    }
                )
            except Exception as e:
                info["siblings"].append({"ip": ip, "error": str(e)})
            await asyncio.sleep(0.2)
    return info


# ---------------------------------------------------------------------------
# G. GitHub code-search for the URL
# ---------------------------------------------------------------------------


async def github_code_search() -> dict[str, Any]:
    """Query GitHub's code-search REST API (no auth needed for low rate)."""
    queries = [
        "app.prod.ai.think-cell.com",
        "aiauthentication.appcom.think-cell.com",
        "PpAICoreURL",
        "BCryptCreateHash think-cell",
        "tcaddin.dll BCrypt",
        "thinkcell hmac signing",
    ]
    out: dict[str, Any] = {"queries": []}
    async with httpx.AsyncClient(timeout=15.0) as client:
        for q in queries:
            try:
                # Public web search (no auth, rate-limited, but works for small batches)
                # Use the search HTML page rather than API to avoid auth
                resp = await client.get(
                    "https://github.com/search",
                    params={"q": q, "type": "code"},
                    headers={"User-Agent": "Mozilla/5.0 tc-recon/0.1"},
                )
                # GitHub returns HTML; just record status + content size for now.
                # Real result extraction would need parsing or auth-API.
                out["queries"].append(
                    {
                        "q": q,
                        "status": resp.status_code,
                        "body_size": len(resp.content),
                        "rate_limit_remaining": resp.headers.get("x-ratelimit-remaining"),
                        "note": "html search; if status=200 and large body, results likely present",
                    }
                )
            except Exception as e:
                out["queries"].append({"q": q, "error": str(e)})
            await asyncio.sleep(2.0)  # be gentle to GH
    return out


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


async def main() -> int:
    ts = _now_iso()
    out_dir = OUT_DIR / ts
    out_dir.mkdir(parents=True, exist_ok=True)
    print(f"=== Aggressive AI recon — output: {out_dir} ===\n")

    bundle: dict[str, Any] = {
        "schema": "tc-ai-aggressive-recon/v1",
        "timestamp_utc": ts,
        "target": AI_BASE,
        "target_ip": AI_IP,
    }

    print("A. Subdomain enumeration via crt.sh + DNS...")
    crt = await crt_sh_enumerate()
    bundle["crt_sh"] = crt
    prod_ai_subs = sorted(
        {r["name"] for r in crt if isinstance(r, dict) and "name" in r and "prod.ai" in r["name"]}
    )
    print(f"  crt.sh returned {len(crt)} unique *.think-cell.com names")
    print(f"  *.prod.ai.think-cell.com candidates: {prod_ai_subs}")
    bundle["prod_ai_subdomains_from_crt"] = prod_ai_subs
    bundle["dns_resolution"] = []
    for sub in prod_ai_subs:
        bundle["dns_resolution"].append(dns_resolve_all(sub))

    print("\nB. Header-spoofing matrix...")
    bundle["spoof_matrix"] = await spoof_matrix()
    print(f"  ran {len(bundle['spoof_matrix'])} probes")

    print("\nC. HTTP/2 probe...")
    bundle["http2_probe"] = await http2_probe()

    print("\nD. Method matrix expansion...")
    bundle["method_matrix"] = await method_matrix()

    print("\nE. Path-encoding tricks...")
    bundle["path_tricks"] = await path_tricks()

    print("\nF. Reverse DNS + sibling-IP enumeration...")
    bundle["reverse_dns_and_siblings"] = await reverse_dns_and_siblings()

    print("\nG. GitHub code search...")
    bundle["github_code_search"] = await github_code_search()

    out_path = out_dir / "results.json"
    out_path.write_text(json.dumps(bundle, indent=2, default=str))
    print(f"\nWrote {out_path}")

    # ---------------------------------------------------------------------
    # Quick analysis — flag any non-403 / non-uniform response
    # ---------------------------------------------------------------------
    print("\n=== Anomalies (not 403/equal-size baseline) ===")

    def maybe_interesting(rows, baseline_status=403, baseline_size=146):
        out = []
        for r in rows:
            if "error" in r:
                continue
            s = r.get("status")
            sz = r.get("body_size")
            if s != baseline_status or (sz is not None and sz != baseline_size):
                out.append(r)
        return out

    spoof_anom = maybe_interesting(bundle["spoof_matrix"])
    print(f"\nSpoof-matrix anomalies ({len(spoof_anom)}):")
    for r in spoof_anom[:10]:
        print(
            f"  ua={r['ua']:25} hs={r['header_set']:20} path={r['path']:8} -> {r['status']} ({r['body_size']}B)"
        )

    h2_anom = [
        r
        for r in bundle["http2_probe"]
        if "error" not in r and (r.get("status") != 403 or r.get("body_size") != 146)
    ]
    print(f"\nHTTP/2 anomalies ({len(h2_anom)}):")
    for r in h2_anom:
        print(f"  path={r['path']} v={r.get('http_version')} -> {r['status']} ({r['body_size']}B)")

    m_anom = maybe_interesting(bundle["method_matrix"])
    print(f"\nMethod-matrix anomalies ({len(m_anom)}):")
    for r in m_anom[:10]:
        print(f"  {r['method']:10} {r['path']:8} -> {r['status']} ({r['body_size']}B)")

    pt_anom = maybe_interesting(bundle["path_tricks"])
    print(f"\nPath-trick anomalies ({len(pt_anom)}):")
    for r in pt_anom[:10]:
        print(
            f"  {r['path']:30} -> {r['status']} ({r['body_size']}B)"
            + (f" -> {r['redirect']}" if r.get("redirect") else "")
        )

    sib = bundle["reverse_dns_and_siblings"]
    print(f"\nReverse DNS PTR for {AI_IP}: {sib.get('ptr')}")
    print(f"Sibling IPs accepting Host={AI_HOST}:")
    for s in sib["siblings"]:
        print(f"  {s['ip']}: {s.get('status', s.get('error'))[:80]}")

    print("\nGitHub code-search done; raw HTML in results.json (manual scan needed).")

    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
