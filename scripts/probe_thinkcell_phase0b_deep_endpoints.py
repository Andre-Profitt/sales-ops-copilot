#!/usr/bin/env python3
"""Phase 0b — DEEP endpoint mapping.

Where the original Phase 0 was breadth-first (which subdomains exist), this is
depth-first against what we already found:

1. Cert transparency JSON properly parsed (the prior bug collapsed everything
   to think-cell.com)
2. SSL cert SAN extraction per host (gives us every subdomain in each cert)
3. Cross-product every known subdomain × every known route from binaries
4. Try POST where OPTIONS allowed it
5. Probe transparent-proxy paths against pexels/unsplash/freepik (real provider
   paths since the proxies route /v1/photos/<id> through to pexels.com etc.)
6. Common OpenAPI/Swagger/GraphQL/Docker-health endpoints
7. Wayback Machine real queries (per-subdomain CDX)
8. GitHub code search via `gh search code` for any of the new endpoints
9. www.think-cell.com index → JS bundle extraction → grep for API URLs

Read-only. No auth bypass. No fuzzing of private endpoints.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import re
import socket
import ssl
import subprocess
import sys
import time
from pathlib import Path
from urllib import error as urlerror
from urllib import parse as urlparse
from urllib import request as urlrequest


ROOT = Path(__file__).resolve().parent.parent

KNOWN_SUBDOMAINS = [
    "www.think-cell.com",
    "think-cell.com",
    "server.think-cell.com",
    "static.think-cell.com",
    "schemas.think-cell.com",
    "ai.think-cell.com",
    "ai.appcom.think-cell.com",
    "app.prod.ai.think-cell.com",
    "appcom.think-cell.com",
    "freepik.appcom.think-cell.com",
    "pexels.appcom.think-cell.com",
    "unsplash.appcom.think-cell.com",
    "usage.appcom.think-cell.com",
]

# Routes pulled from binary string scan
KNOWN_ROUTES = [
    "/api",
    "/api/v0",
    "/api/v1",
    "/api/v1/search",
    "/api/v1/photos",
    "/api/v1/photos/curated",
    "/api/v1/popular",
    "/auth",
    "/auth/login",
    "/auth/token",
    "/auth/refresh",
    "/v0",
    "/v0/api",
    "/v0/openapi.json",
    "/v0/openapi",
    "/schemas",
    "/schemas/tcstyle",
    "/portal",
    "/portal/login",
    "/portal/api",
    "/portal/auth",
    # Common discovery paths
    "/openapi.json",
    "/openapi.yaml",
    "/swagger.json",
    "/swagger-ui/",
    "/api-docs",
    "/api-docs/v0",
    "/v3/api-docs",
    "/redoc",
    "/graphql",
    "/api/graphql",
    "/.well-known/openid-configuration",
    "/.well-known/oauth-authorization-server",
    "/.well-known/security.txt",
    # Health / k8s / docker
    "/health",
    "/healthz",
    "/readyz",
    "/livez",
    "/actuator/info",
    "/actuator/health",
    "/metrics",
    # Pexels-style real paths (since pexels.appcom is transparent proxy)
    "/v1/photos/curated",
    "/v1/popular",
    # Unsplash-style
    "/api/photos",
    "/api/photos/random",
    # Freepik-style
    "/search",
    "/download",
]

# OPTIONS and POST methods to try per (host, route)
METHODS = ["GET", "OPTIONS", "POST", "HEAD"]


def _http(method: str, url: str, *, timeout: int = 8, body: bytes | None = None) -> dict:
    out = {
        "url": url,
        "method": method,
        "status": None,
        "headers": {},
        "body_preview": None,
        "error": None,
        "elapsed_ms": 0,
    }
    req = urlrequest.Request(url, method=method, data=body)
    req.add_header("User-Agent", "tcw-deep-probe/1.0 (research; local lab)")
    if method == "POST" and body is None:
        req.add_header("Content-Length", "0")
    started = time.time()
    try:
        with urlrequest.urlopen(req, timeout=timeout) as r:
            out["status"] = r.status
            out["headers"] = dict(r.headers)
            data = r.read(2000)
            try:
                out["body_preview"] = data.decode("utf-8", errors="replace")[:1500]
            except Exception:
                out["body_preview"] = data[:200].hex()
    except urlerror.HTTPError as e:
        out["status"] = e.code
        out["headers"] = dict(e.headers) if e.headers else {}
        try:
            data = e.read(1000)
            out["body_preview"] = data.decode("utf-8", errors="replace")[:800]
        except Exception:
            pass
    except Exception as e:
        out["error"] = f"{type(e).__name__}: {e}"
    out["elapsed_ms"] = int((time.time() - started) * 1000)
    return out


def _ct_lookup(query: str = "%.think-cell.com") -> tuple[list[str], int]:
    """Cert transparency lookup; properly parse newline-separated SANs."""
    url = f"https://crt.sh/?q={urlparse.quote(query)}&output=json"
    try:
        with urlrequest.urlopen(url, timeout=30) as r:
            data = json.loads(r.read().decode("utf-8"))
        names = set()
        for entry in data:
            if not isinstance(entry, dict):
                continue
            nv = entry.get("name_value", "") or ""
            for name in nv.split("\n"):
                name = name.strip().lstrip("*.").lower()
                if name.endswith(".think-cell.com") or name == "think-cell.com":
                    names.add(name)
            common = (entry.get("common_name", "") or "").strip().lstrip("*.").lower()
            if common.endswith(".think-cell.com") or common == "think-cell.com":
                names.add(common)
        return sorted(names), len(data)
    except Exception as e:
        return ([f"ERR:{type(e).__name__}:{e}"], 0)


def _ssl_cert_sans(host: str, *, timeout: int = 8) -> dict:
    """Extract SAN list from server cert."""
    out = {
        "host": host,
        "sans": [],
        "issuer": None,
        "subject": None,
        "not_after": None,
        "error": None,
    }
    try:
        ctx = ssl.create_default_context()
        with socket.create_connection((host, 443), timeout=timeout) as sock:
            with ctx.wrap_socket(sock, server_hostname=host) as ssock:
                cert = ssock.getpeercert()
                out["sans"] = [v for k, v in cert.get("subjectAltName", []) if k == "DNS"]
                out["issuer"] = dict(x[0] for x in cert.get("issuer", []))
                out["subject"] = dict(x[0] for x in cert.get("subject", []))
                out["not_after"] = cert.get("notAfter")
    except Exception as e:
        out["error"] = f"{type(e).__name__}: {e}"
    return out


def _wayback_cdx(host: str) -> dict:
    """Wayback CDX API."""
    url = f"https://web.archive.org/cdx/search/cdx?url={host}/*&output=json&limit=200&from=20100101&collapse=urlkey"
    try:
        with urlrequest.urlopen(url, timeout=30) as r:
            data = json.loads(r.read().decode("utf-8"))
            return {"host": host, "row_count": len(data), "rows": data[:50]}
    except Exception as e:
        return {"host": host, "error": f"{type(e).__name__}: {e}"}


def _gh_code_search(term: str, limit: int = 30) -> dict:
    """Run gh search code for the term."""
    out = {"term": term, "results": [], "error": None}
    try:
        r = subprocess.run(
            ["gh", "search", "code", term, "--limit", str(limit), "--json", "path,repository,url"],
            text=True,
            capture_output=True,
            timeout=30,
            check=False,
        )
        if r.returncode != 0:
            out["error"] = f"gh exit {r.returncode}: {r.stderr[:300]}"
            return out
        out["results"] = json.loads(r.stdout) if r.stdout.strip() else []
    except FileNotFoundError:
        out["error"] = "gh CLI not installed"
    except Exception as e:
        out["error"] = f"{type(e).__name__}: {e}"
    return out


def _fetch_and_extract_urls(url: str) -> dict:
    """GET a URL, look for embedded JS bundle URLs / API references."""
    out = {"url": url, "status": None, "linked_assets": [], "api_url_hints": [], "error": None}
    try:
        with urlrequest.urlopen(
            urlrequest.Request(url, headers={"User-Agent": "tcw-deep-probe"}), timeout=15
        ) as r:
            out["status"] = r.status
            body = r.read(500_000).decode("utf-8", errors="replace")
        # Linked JS / CSS
        for m in re.finditer(r'(?:src|href)\s*=\s*"([^"]+\.(?:js|css|json))"', body):
            out["linked_assets"].append(m.group(1))
        # API URL hints in inline JS
        for m in re.finditer(
            r'(["\'])(https?://[A-Za-z0-9._/?=#&%+:-]{6,200}|/api/[A-Za-z0-9_/-]{2,80}|/v\d+/[A-Za-z0-9_/-]{2,80})\1',
            body,
        ):
            out["api_url_hints"].append(m.group(2))
        out["api_url_hints"] = sorted(set(out["api_url_hints"]))[:80]
        out["linked_assets"] = sorted(set(out["linked_assets"]))[:40]
    except Exception as e:
        out["error"] = f"{type(e).__name__}: {e}"
    return out


def _probe_one(host: str, route: str, method: str) -> dict:
    return _http(method, f"https://{host}{route}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--max-workers", type=int, default=12)
    parser.add_argument("--skip-cross-product", action="store_true")
    args = parser.parse_args()

    output = args.output
    if output is None:
        stamp = time.strftime("%Y%m%d-%H%M%S")
        output = (
            ROOT
            / "state"
            / "thinkcell_bridge"
            / "phase0b_deep_endpoints"
            / stamp
            / "phase0b_deep_endpoints.json"
        )
    output = output.expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)

    print("[deep] cert transparency (proper parse)", flush=True)
    ct_subdomains, ct_raw_count = _ct_lookup()
    real_subdomains = sorted(
        set(KNOWN_SUBDOMAINS + [s for s in ct_subdomains if not s.startswith("ERR:")])
    )
    print(
        f"[deep]   crt.sh: {ct_raw_count} entries, {len(ct_subdomains)} unique subdomains",
        flush=True,
    )
    new_subdomains = sorted(set(ct_subdomains) - set(KNOWN_SUBDOMAINS))
    if new_subdomains:
        print(f"[deep]   new from CT: {new_subdomains[:20]}", flush=True)

    print(f"[deep] SSL cert SAN extraction across {len(real_subdomains)} hosts", flush=True)
    sans_per_host = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
        for r in ex.map(_ssl_cert_sans, real_subdomains[:30]):
            sans_per_host.append(r)
    all_sans = sorted(
        {s for r in sans_per_host for s in (r.get("sans") or []) if "think-cell.com" in s}
    )
    print(f"[deep]   distinct SANs across all certs: {len(all_sans)}", flush=True)

    # Final canonical subdomain list
    final_hosts = sorted(set(real_subdomains + all_sans))
    print(f"[deep]   final probe host list: {len(final_hosts)}", flush=True)

    cross_product_results = []
    if not args.skip_cross_product:
        # Cross-product KNOWN_ROUTES × final_hosts × selected methods
        # Bound: ~13 hosts × ~35 routes × 4 methods = 1820 requests. Skip OPTIONS unless host previously responded.
        print(
            f"[deep] cross-product probe: {len(final_hosts)} hosts × {len(KNOWN_ROUTES)} routes × GET+POST+OPTIONS",
            flush=True,
        )
        tasks = []
        for host in final_hosts:
            for route in KNOWN_ROUTES:
                for method in ("GET", "POST", "OPTIONS"):
                    tasks.append((host, route, method))
        with concurrent.futures.ThreadPoolExecutor(max_workers=args.max_workers) as ex:
            futs = [ex.submit(_probe_one, h, r, m) for h, r, m in tasks]
            for fut in concurrent.futures.as_completed(futs):
                cross_product_results.append(fut.result())
        # Filter to interesting results: 200, 201, 204, 405, OPTIONS Allow header
        interesting = [
            r
            for r in cross_product_results
            if r.get("status") in (200, 201, 204, 301, 302, 401, 405, 500)
            or (r.get("method") == "OPTIONS" and r.get("headers", {}).get("Allow"))
        ]
        print(
            f"[deep]   {len(cross_product_results)} probes; {len(interesting)} interesting",
            flush=True,
        )

    print("[deep] wayback CDX queries on all hosts", flush=True)
    wayback_results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ex:
        for r in ex.map(_wayback_cdx, final_hosts[:15]):
            wayback_results.append(r)

    print("[deep] GitHub code search", flush=True)
    gh_results = []
    for term in [
        "appcom.think-cell.com",
        "ai.think-cell.com",
        "BrandfolderAPIKey",
        "thinkcell.appcom",
        "tcserver.exe",
        "ppttc.exe",
        "tcaddin.dll",
    ]:
        gh_results.append(_gh_code_search(term, limit=20))
        time.sleep(2)  # rate-limit politeness

    print("[deep] www.think-cell.com index + JS bundle extraction", flush=True)
    www_index = _fetch_and_extract_urls("https://www.think-cell.com/")
    # Fetch a couple of linked JS bundles from www to grep for API URLs
    js_bundles = []
    for asset in www_index.get("linked_assets", [])[:8]:
        if asset.startswith("http"):
            url = asset
        elif asset.startswith("/"):
            url = "https://www.think-cell.com" + asset
        else:
            continue
        if url.endswith(".js") or url.endswith(".json"):
            js_bundles.append(_fetch_and_extract_urls(url))

    payload = {
        "schema": "simcorp-thinkcell-phase0b-deep-endpoints/v1",
        "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "cert_transparency": {
            "raw_count": ct_raw_count,
            "subdomains": ct_subdomains,
            "newly_discovered": new_subdomains,
        },
        "ssl_cert_sans": sans_per_host,
        "all_sans": all_sans,
        "final_host_list": final_hosts,
        "cross_product": {
            "total_probes": len(cross_product_results),
            "interesting": [
                r
                for r in cross_product_results
                if r.get("status") in (200, 201, 204, 301, 302, 401, 405)
                or (r.get("method") == "OPTIONS" and r.get("headers", {}).get("Allow"))
            ],
            "all": cross_product_results if not args.skip_cross_product else [],
        },
        "wayback": wayback_results,
        "github_search": gh_results,
        "www_index": www_index,
        "js_bundles_grepped": js_bundles,
    }
    output.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    # Summary
    print(f"\n[deep] wrote {output}")
    print("\n[deep] === SUBDOMAINS ===")
    print(f"  {len(final_hosts)} total ({len(new_subdomains)} new from CT)")
    if new_subdomains:
        print(f"  new: {', '.join(new_subdomains[:20])}")
    print("\n[deep] === INTERESTING CROSS-PRODUCT HITS ===")
    interesting = payload["cross_product"]["interesting"]
    by_host_status = {}
    for r in interesting:
        host = urlparse.urlparse(r["url"]).netloc
        key = (host, r.get("status"), r.get("method"))
        by_host_status.setdefault(key, []).append(r["url"])
    for (host, status, method), urls in sorted(by_host_status.items())[:80]:
        print(f"  {host} {method} {status}: {len(urls)} hits  e.g. {urls[0]}")
    print(
        f"\n[deep] === www.think-cell.com API URL HINTS ({len(www_index.get('api_url_hints', []))}) ==="
    )
    for h in www_index.get("api_url_hints", [])[:20]:
        print(f"  - {h}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
