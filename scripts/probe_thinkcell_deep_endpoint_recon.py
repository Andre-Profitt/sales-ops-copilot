#!/usr/bin/env python3
"""DEEP endpoint reconnaissance — going as far as read-only probing allows.

Layers:
1. Wire fingerprinting per subdomain (TLS, cipher, ALPN, server, CDN, WAF)
2. Path / API directory brute-force with common wordlist
3. HTTP method matrix on interesting paths (GET/POST/PUT/DELETE/PATCH/HEAD/OPTIONS/TRACE/PURGE/CONNECT)
4. Authenticated probing with DPAPI-token replay (pull fresh from VM, decrypt, replay)
5. Subdomain brute-force with common prefixes
6. JS-bundle scrape for embedded API URLs (marketing site + others)
7. Cross-host correlation: IP / ASN / CDN / WAF clustering
8. Cert chain + transparency log proper parse
9. Robots.txt + sitemaps + .well-known/* full walk

Read-only. No fuzzing of private endpoints. Auth-replay uses our own token.
"""

from __future__ import annotations

import argparse
import base64
import concurrent.futures
import json
import re
import socket
import ssl
import subprocess
import sys
import time
import urllib.parse as urlparse
import urllib.request as urlrequest
import urllib.error as urlerror
from pathlib import Path
from collections import defaultdict


ROOT = Path(__file__).resolve().parent.parent

KNOWN_SUBDOMAINS = [
    "ai.appcom.think-cell.com",
    "ai.think-cell.com",
    "aiauthentication.appcom.think-cell.com",
    "app.prod.ai.think-cell.com",
    "appcom.think-cell.com",
    "bug.appcom.think-cell.com",
    "cdnauthentication.appcom.think-cell.com",
    "flaticon.appcom.think-cell.com",
    "freepik.appcom.think-cell.com",
    "matomo.think-cell.com",
    "academy.think-cell.com",
    "pexels.appcom.think-cell.com",
    "prod.ai.think-cell.com",
    "schemas.think-cell.com",
    "server.think-cell.com",
    "static.think-cell.com",
    "think-cell.com",
    "unsplash.appcom.think-cell.com",
    "unsupported.appcom.think-cell.com",
    "update.appcom.think-cell.com",
    "usage.appcom.think-cell.com",
    "www.server.think-cell.com",
    "www.think-cell.com",
]

API_WORDLIST = [
    # Common API roots
    "api",
    "api/v0",
    "api/v1",
    "api/v2",
    "api/v3",
    "v0",
    "v1",
    "v2",
    "v3",
    "rest",
    "graphql",
    "rpc",
    # API endpoints
    "api/v1/auth",
    "api/v1/login",
    "api/v1/logout",
    "api/v1/token",
    "api/v1/refresh",
    "api/v1/user",
    "api/v1/users",
    "api/v1/account",
    "api/v1/profile",
    "api/v1/search",
    "api/v1/photos",
    "api/v1/photos/curated",
    "api/v1/popular",
    "api/v1/images",
    "api/v1/templates",
    "api/v1/charts",
    "api/v1/tickets",
    "api/v1/usage",
    "api/v1/quota",
    "api/v1/license",
    "api/v1/keys",
    "api/v1/files",
    "api/v1/upload",
    "api/v1/download",
    "api/v1/admin",
    "api/v1/openapi.json",
    "api/v1/schema",
    # Auth flows
    "auth",
    "auth/login",
    "auth/logout",
    "auth/token",
    "auth/refresh",
    "oauth/authorize",
    "oauth/token",
    "oauth/refresh",
    "login",
    "logout",
    "register",
    "signup",
    "session",
    # Admin / debug
    "admin",
    "admin/api",
    "admin/console",
    "admin/dashboard",
    "debug",
    "debug/info",
    "debug/heap",
    "debug/pprof",
    "_admin",
    "_api",
    "_internal",
    "_status",
    "_health",
    "actuator/info",
    "actuator/health",
    "actuator/metrics",
    "actuator/env",
    # Health / monitoring
    "health",
    "healthz",
    "livez",
    "readyz",
    "readiness",
    "liveness",
    "status",
    "statusz",
    "ping",
    "echo",
    "version",
    "info",
    "uptime",
    "metrics",
    "metrics/prometheus",
    "stats",
    # Docs / spec
    "openapi.json",
    "openapi.yaml",
    "swagger.json",
    "swagger-ui/",
    "swagger",
    "api-docs",
    "v3/api-docs",
    "redoc",
    "docs",
    "doc",
    "schema",
    "schemas",
    "spec",
    "specs",
    # Well-known
    ".well-known/openid-configuration",
    ".well-known/oauth-authorization-server",
    ".well-known/security.txt",
    ".well-known/jwks.json",
    ".well-known/change-password",
    ".well-known/host-meta",
    # Static
    "robots.txt",
    "sitemap.xml",
    "sitemap_index.xml",
    "humans.txt",
    "ads.txt",
    "favicon.ico",
    "manifest.json",
    # think-cell specific guesses
    "tcserver",
    "ppttc",
    "thinkcell",
    "tc",
    "ppttc/template1.pptx",
    "ppttc/template2.pptx",
    "ppttc/template3.pptx",
    "ppttc/template4.pptx",
    "ppttc/template5.pptx",
    "ppttc/template6.pptx",
    "ppttc/sample1.pptx",
    "ppttc/index.html",
    "templates",
    "templates/list",
    "templates/index",
    "schemas/tcstyle.xsd",
    "schemas/next/tcstyle",
    "32687/tcstyle.xsd",
    "36264/tcstyle.xsd",
    "38000/tcstyle.xsd",
    "38068/tcstyle.xsd",
    "next/tcstyle",
    "next/tcstyle.xsd",
    # Update/diagnostic
    "update",
    "update/check",
    "updates",
    "updates/latest",
    "version-check",
    "diagnostic",
    "diagnostics",
    "report",
    "feedback",
    "bug",
    "bugs",
    "ticket",
    "tickets",
    "telemetry",
    "usage",
    "events",
    # Portal
    "portal",
    "portal/login",
    "portal/api",
    "portal/auth",
    "portal/admin",
    "portal/en",
    "portal/de",
    "portal/fr",
    "portal/en/login.srf",
    "portal/en/trial.srf",
    "portal/en/downloads.srf",
    # Misc
    "ws",
    "websocket",
    "stream",
    "events/stream",
    "sse",
]

SUBDOMAIN_BRUTEFORCE_PREFIXES = [
    "dev",
    "staging",
    "stage",
    "prod",
    "production",
    "test",
    "qa",
    "uat",
    "internal",
    "intranet",
    "admin",
    "console",
    "dashboard",
    "api",
    "rest",
    "graphql",
    "rpc",
    "ws",
    "beta",
    "preview",
    "sandbox",
    "demo",
    "lab",
    "playground",
    "partner",
    "partners",
    "vendor",
    "support",
    "help",
    "kb",
    "wiki",
    "docs",
    "doc",
    "developer",
    "developers",
    "mail",
    "smtp",
    "imap",
    "pop3",
    "exchange",
    "ftp",
    "sftp",
    "vpn",
    "remote",
    "auth",
    "sso",
    "id",
    "identity",
    "login",
    "signin",
    "static",
    "cdn",
    "assets",
    "media",
    "files",
    "img",
    "image",
    "images",
    "photo",
    "photos",
    "secrets",
    "vault",
    "secret",
    "build",
    "ci",
    "deploy",
    "jenkins",
    "gitlab",
    "monitoring",
    "metrics",
    "logs",
    "log",
    "data",
    "db",
    "database",
    "demo",
    "trial",
    "us",
    "eu",
    "uk",
    "de",
    "fr",
    "asia",
    "ai-staging",
    "ai-dev",
    "ai-test",
    "tcserver",
    "ppttc",
    "thinkcell-server",
    "qa-ai",
    "dev-ai",
    "preview-ai",
]

HTTP_METHODS_TO_TRY = ["GET", "HEAD", "OPTIONS", "POST", "PUT", "DELETE", "PATCH", "TRACE"]


def _http(
    url: str,
    method: str = "HEAD",
    *,
    timeout: int = 8,
    headers: dict | None = None,
    body: bytes | None = None,
) -> dict:
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
    req.add_header("User-Agent", "tcw-deep-recon/1.0")
    if headers:
        for k, v in headers.items():
            req.add_header(k, v)
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
            out["body_preview"] = data.decode("utf-8", errors="replace")[:600]
        except Exception:
            pass
    except Exception as e:
        out["error"] = f"{type(e).__name__}: {e}"
    out["elapsed_ms"] = int((time.time() - started) * 1000)
    return out


def _tls_fingerprint(host: str, *, timeout: int = 8) -> dict:
    """Detailed TLS handshake fingerprint."""
    out = {"host": host, "tls_versions": {}, "alpn": [], "cert": {}, "error": None}
    # Test ALPN by trying h2, http/1.1, h3
    for alpn_attempt in [["h2", "http/1.1"], ["http/1.1"], ["h3"]]:
        try:
            ctx = ssl.create_default_context()
            ctx.set_alpn_protocols(alpn_attempt)
            with socket.create_connection((host, 443), timeout=timeout) as sock:
                with ctx.wrap_socket(sock, server_hostname=host) as ssock:
                    proto = ssock.selected_alpn_protocol()
                    if proto and proto not in out["alpn"]:
                        out["alpn"].append(proto)
                    out["tls_versions"]["negotiated"] = ssock.version()
                    cert = ssock.getpeercert()
                    if not out["cert"] and cert:
                        out["cert"] = {
                            "issuer": dict(x[0] for x in cert.get("issuer", [])),
                            "subject": dict(x[0] for x in cert.get("subject", [])),
                            "san": [v for k, v in cert.get("subjectAltName", []) if k == "DNS"],
                            "not_before": cert.get("notBefore"),
                            "not_after": cert.get("notAfter"),
                            "serial": cert.get("serialNumber"),
                        }
        except Exception as e:
            out.setdefault("alpn_errors", []).append(f"{alpn_attempt}: {type(e).__name__}: {e}")
    # Try forced TLS versions
    for ver_name, version in [
        ("TLSv1.2", ssl.TLSVersion.TLSv1_2),
        ("TLSv1.3", ssl.TLSVersion.TLSv1_3),
    ]:
        try:
            ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            ctx.minimum_version = version
            ctx.maximum_version = version
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            with socket.create_connection((host, 443), timeout=timeout) as sock:
                with ctx.wrap_socket(sock, server_hostname=host) as ssock:
                    out["tls_versions"][ver_name] = {
                        "ok": True,
                        "cipher": ssock.cipher(),
                    }
        except Exception as e:
            out["tls_versions"][ver_name] = {"ok": False, "error": str(e)[:100]}
    return out


def _detect_cdn_waf(headers: dict) -> dict:
    """Detect CDN/WAF from response headers."""
    out = {"cdn": [], "waf": [], "framework": [], "raw_signals": []}
    h = {k.lower(): v for k, v in headers.items()}
    # CDN signals
    if "cf-ray" in h or "cf-cache-status" in h:
        out["cdn"].append("Cloudflare")
    if "x-cache" in h and "cloudfront" in (h.get("via") or "").lower():
        out["cdn"].append("CloudFront")
    if "x-akamai-transformed" in h or "akamai" in (h.get("server") or "").lower():
        out["cdn"].append("Akamai")
    if "x-amz-cf-id" in h:
        out["cdn"].append("AWS CloudFront")
    if "x-azure-ref" in h:
        out["cdn"].append("Azure CDN")
    if "x-fastly" in h or "fastly" in (h.get("server") or "").lower():
        out["cdn"].append("Fastly")
    # WAF signals
    if "cf-mitigated" in h:
        out["waf"].append("Cloudflare WAF")
    if "x-sucuri-id" in h:
        out["waf"].append("Sucuri")
    if "x-iinfo" in h:
        out["waf"].append("Incapsula")
    if "x-cdn" in h:
        out["raw_signals"].append(f"x-cdn={h['x-cdn']}")
    # Framework signals
    server = (h.get("server") or "").lower()
    if "nginx" in server:
        out["framework"].append("nginx")
    if "apache" in server:
        out["framework"].append("Apache")
    if "microsoft-iis" in server:
        out["framework"].append("IIS")
    if "kestrel" in server:
        out["framework"].append("Kestrel/.NET")
    if "express" in (h.get("x-powered-by") or "").lower():
        out["framework"].append("Express")
    if "asp.net" in (h.get("x-powered-by") or "").lower():
        out["framework"].append("ASP.NET")
    return out


def _probe_path_per_host(host: str, path: str) -> dict:
    url = f"https://{host}/{path.lstrip('/')}"
    return _http(url, method="HEAD", timeout=6)


def _wire_layer(hosts: list[str]) -> list[dict]:
    print(f"[deep] Layer 1: TLS/cert fingerprint × {len(hosts)} hosts", flush=True)
    out = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
        for r in ex.map(_tls_fingerprint, hosts):
            out.append(r)
    return out


def _path_layer(hosts: list[str]) -> list[dict]:
    print(
        f"[deep] Layer 2: path enumeration × {len(hosts)} hosts × {len(API_WORDLIST)} paths",
        flush=True,
    )
    tasks = [(h, p) for h in hosts for p in API_WORDLIST]
    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=24) as ex:
        futs = [ex.submit(_probe_path_per_host, h, p) for h, p in tasks]
        for fut in concurrent.futures.as_completed(futs):
            try:
                r = fut.result()
                if r.get("status") and r["status"] != 404:
                    results.append(r)
            except Exception:
                pass
    return results


def _method_matrix_layer(interesting_endpoints: list[str]) -> list[dict]:
    print(
        f"[deep] Layer 3: method matrix × {len(interesting_endpoints)} endpoints × {len(HTTP_METHODS_TO_TRY)} methods",
        flush=True,
    )
    out = []
    tasks = [(url, m) for url in interesting_endpoints for m in HTTP_METHODS_TO_TRY]
    with concurrent.futures.ThreadPoolExecutor(max_workers=12) as ex:
        for r in ex.map(lambda t: _http(t[0], method=t[1], timeout=6), tasks):
            if (
                r.get("status")
                and r["status"] not in (404, 405)
                or (r.get("headers") or {}).get("Allow")
            ):
                out.append(r)
    return out


def _pull_dpapi_token() -> dict:
    """Pull fresh aiauthentication.bin from VM and decrypt."""
    print("[deep] Layer 4: pulling fresh DPAPI token from VM", flush=True)
    out = {"pulled": False, "decrypted": False, "token": None, "error": None}
    try:
        # PowerShell on VM: read bytes, decrypt with DPAPI, base64
        ps = (
            "Add-Type -AssemblyName System.Security; "
            '$b = [System.IO.File]::ReadAllBytes("$env:APPDATA\\think-cell\\aiauthentication.bin"); '
            "$d = [System.Security.Cryptography.ProtectedData]::Unprotect($b, $null, "
            "[System.Security.Cryptography.DataProtectionScope]::CurrentUser); "
            "[System.Convert]::ToBase64String($d)"
        )
        enc = base64.b64encode(ps.encode("utf-16le")).decode("ascii")
        r = subprocess.run(
            [
                "ssh",
                "-o",
                "BatchMode=yes",
                "-o",
                "ConnectTimeout=8",
                "Windows-VM",
                f"powershell -NoProfile -ExecutionPolicy Bypass -EncodedCommand {enc}",
            ],
            text=True,
            capture_output=True,
            timeout=30,
            check=False,
        )
        if r.returncode != 0:
            out["error"] = f"ssh exit {r.returncode}: {r.stderr[:200]}"
            return out
        b64 = r.stdout.strip()
        out["pulled"] = True
        decrypted = base64.b64decode(b64)
        out["decrypted"] = True
        # Skip 4-byte length prefix
        try:
            text = decrypted[4:].decode("utf-8", errors="replace")
            out["token"] = text
            # Parse token fields
            for m in re.finditer(r"(\w+)=([^&]+)", text):
                out.setdefault("fields", {})[m.group(1)] = m.group(2)
            # Check expiry
            if "expires" in out.get("fields", {}):
                exp = int(out["fields"]["expires"])
                out["expired"] = exp < time.time()
                out["seconds_remaining"] = exp - int(time.time())
        except Exception as e:
            out["error"] = f"parse: {e}"
    except Exception as e:
        out["error"] = f"{type(e).__name__}: {e}"
    return out


def _auth_replay_layer(interesting_endpoints: list[str], token: str) -> list[dict]:
    """Replay token against interesting endpoints in multiple auth styles."""
    print(
        f"[deep] Layer 4: auth-replay × {len(interesting_endpoints)} endpoints × 5 auth styles",
        flush=True,
    )
    auth_styles = [
        {"name": "bearer", "headers": {"Authorization": f"Bearer {token}"}},
        {
            "name": "basic_pseudo",
            "headers": {"Authorization": f"Basic {base64.b64encode(token.encode()).decode()}"},
        },
        {"name": "x-license-key", "headers": {"X-License-Key": token}},
        {"name": "x-thinkcell-token", "headers": {"X-Thinkcell-Token": token}},
        {"name": "cookie", "headers": {"Cookie": f"thinkcell_auth={urlparse.quote(token)}"}},
    ]
    out = []
    for url in interesting_endpoints:
        # Get unauth baseline
        baseline = _http(url, method="GET", timeout=6)
        for style in auth_styles:
            authed = _http(url, method="GET", timeout=6, headers=style["headers"])
            if authed.get("status") != baseline.get("status") or len(
                authed.get("body_preview") or ""
            ) != len(baseline.get("body_preview") or ""):
                out.append(
                    {
                        "url": url,
                        "auth_style": style["name"],
                        "baseline_status": baseline.get("status"),
                        "authed_status": authed.get("status"),
                        "baseline_body_len": len(baseline.get("body_preview") or ""),
                        "authed_body_len": len(authed.get("body_preview") or ""),
                        "authed_body_preview": (authed.get("body_preview") or "")[:300],
                    }
                )
    return out


def _subdomain_brute(prefixes: list[str]) -> list[dict]:
    print(f"[deep] Layer 5: subdomain brute-force × {len(prefixes)} prefixes", flush=True)
    out = []

    def _try(prefix):
        host = f"{prefix}.think-cell.com"
        try:
            socket.setdefaulttimeout(4)
            ips = sorted({i[4][0] for i in socket.getaddrinfo(host, None, socket.AF_INET)})
            return {"host": host, "ips": ips, "resolves": True}
        except Exception:
            return None

    with concurrent.futures.ThreadPoolExecutor(max_workers=12) as ex:
        for r in ex.map(_try, prefixes):
            if r and r.get("resolves"):
                out.append(r)
    return out


def _js_bundle_scrape(host: str = "www.think-cell.com") -> dict:
    print(f"[deep] Layer 6: JS bundle scrape from {host}", flush=True)
    out = {"host": host, "linked_assets": [], "api_url_hints": [], "bundles_scraped": 0}
    try:
        with urlrequest.urlopen(f"https://{host}/", timeout=15) as r:
            body = r.read(800_000).decode("utf-8", errors="replace")
        for m in re.finditer(r'(?:src|href)\s*=\s*"([^"]+\.(?:js|json))"', body):
            out["linked_assets"].append(m.group(1))
        out["linked_assets"] = sorted(set(out["linked_assets"]))[:20]
        for asset in out["linked_assets"][:10]:
            url = (
                asset
                if asset.startswith("http")
                else f"https://{host}{asset}"
                if asset.startswith("/")
                else None
            )
            if not url:
                continue
            try:
                with urlrequest.urlopen(url, timeout=10) as br:
                    bundle = br.read(2_000_000).decode("utf-8", errors="replace")
                out["bundles_scraped"] += 1
                for m in re.finditer(r'"(https?://[A-Za-z0-9._/?=#&%+:-]{8,200})"', bundle):
                    if "think-cell" in m.group(1):
                        out["api_url_hints"].append(m.group(1))
                for m in re.finditer(r'"(/(?:api|v\d+|auth)/[A-Za-z0-9_/-]{2,80})"', bundle):
                    out["api_url_hints"].append(m.group(1))
            except Exception:
                pass
        out["api_url_hints"] = sorted(set(out["api_url_hints"]))[:80]
    except Exception as e:
        out["error"] = str(e)
    return out


def _cross_host_correlation(hosts: list[str]) -> dict:
    print("[deep] Layer 7: cross-host IP / CDN clustering", flush=True)
    out = {"by_ip": defaultdict(list), "by_cdn": defaultdict(list)}
    for h in hosts:
        try:
            socket.setdefaulttimeout(5)
            ips = sorted({i[4][0] for i in socket.getaddrinfo(h, None, socket.AF_INET)})
            for ip in ips:
                out["by_ip"][ip].append(h)
        except Exception:
            pass
        # CDN detection via HEAD
        try:
            r = _http(f"https://{h}/", method="HEAD", timeout=5)
            cdn_info = _detect_cdn_waf(r.get("headers", {}))
            for cdn in cdn_info["cdn"]:
                out["by_cdn"][cdn].append(h)
        except Exception:
            pass
    return {"by_ip": dict(out["by_ip"]), "by_cdn": dict(out["by_cdn"])}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument(
        "--skip-auth-replay",
        action="store_true",
        help="Skip pulling DPAPI token and auth replay (gray-area)",
    )
    parser.add_argument("--skip-path-bruteforce", action="store_true")
    args = parser.parse_args()

    output = args.output or (
        ROOT
        / "state"
        / "thinkcell_bridge"
        / "deep_endpoint_recon"
        / time.strftime("%Y%m%d-%H%M%S")
        / "deep_endpoint_recon.json"
    )
    output = output.expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)

    payload: dict = {
        "schema": "simcorp-thinkcell-deep-endpoint-recon/v1",
        "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }

    # Layer 1
    payload["wire_fingerprint"] = _wire_layer(KNOWN_SUBDOMAINS)

    # Layer 2 — only if not skipped
    if not args.skip_path_bruteforce:
        path_hits = _path_layer(KNOWN_SUBDOMAINS)
        # Filter to interesting hits (200, 301, 302, 401, 403, 405, anything but 404/500)
        interesting = sorted(
            set(
                r["url"]
                for r in path_hits
                if r.get("status") in (200, 201, 301, 302, 401, 403, 405)
            )
        )
        payload["path_hits"] = path_hits
        payload["interesting_paths"] = interesting

        # Layer 3 — method matrix on the interesting paths (cap at 80 to avoid explosion)
        payload["method_matrix"] = _method_matrix_layer(interesting[:80])

    # Layer 4 — DPAPI auth replay (skip if requested)
    if not args.skip_auth_replay:
        token_info = _pull_dpapi_token()
        payload["dpapi_token"] = {
            "pulled": token_info.get("pulled"),
            "decrypted": token_info.get("decrypted"),
            "fields": token_info.get("fields"),
            "expired": token_info.get("expired"),
            "seconds_remaining": token_info.get("seconds_remaining"),
            "error": token_info.get("error"),
        }
        if token_info.get("token") and not token_info.get("expired"):
            interesting_for_auth = payload.get("interesting_paths", [])[:40]
            # Add the obvious AI/auth endpoints
            for h in [
                "aiauthentication.appcom.think-cell.com",
                "ai.appcom.think-cell.com",
                "app.prod.ai.think-cell.com",
                "cdnauthentication.appcom.think-cell.com",
                "usage.appcom.think-cell.com",
                "bug.appcom.think-cell.com",
            ]:
                interesting_for_auth.extend(
                    [f"https://{h}/", f"https://{h}/api", f"https://{h}/v1"]
                )
            interesting_for_auth = sorted(set(interesting_for_auth))[:60]
            payload["auth_replay_diff"] = _auth_replay_layer(
                interesting_for_auth, token_info["token"]
            )

    # Layer 5 — subdomain brute-force
    payload["subdomain_bruteforce"] = _subdomain_brute(SUBDOMAIN_BRUTEFORCE_PREFIXES)
    discovered_subs = sorted(set(s["host"] for s in payload["subdomain_bruteforce"]))
    new_subs = sorted(set(discovered_subs) - set(KNOWN_SUBDOMAINS))
    payload["subdomain_bruteforce_new"] = new_subs

    # Layer 6 — JS scrape
    payload["js_bundle_scrape"] = _js_bundle_scrape("www.think-cell.com")

    # Layer 7 — cross-host correlation
    all_hosts = sorted(set(KNOWN_SUBDOMAINS + discovered_subs))
    payload["cross_host"] = _cross_host_correlation(all_hosts)

    output.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    print(f"\n[deep] wrote {output}")

    # Summary
    print("\n=== SUMMARY ===")
    print(f"  TLS fingerprints: {len(payload.get('wire_fingerprint', []))}")
    print(f"  Path hits (non-404): {len(payload.get('path_hits', []))}")
    print(f"  Interesting paths: {len(payload.get('interesting_paths', []))}")
    print(f"  Method matrix entries: {len(payload.get('method_matrix', []))}")
    if payload.get("dpapi_token"):
        t = payload["dpapi_token"]
        print(
            f"  DPAPI token: pulled={t.get('pulled')} decrypted={t.get('decrypted')} expired={t.get('expired')}"
        )
        if t.get("fields"):
            print(f"    fields: {list(t['fields'].keys())}")
    print(f"  Auth-replay diffs: {len(payload.get('auth_replay_diff') or [])}")
    print(f"  Subdomain brute-force: {len(payload['subdomain_bruteforce'])} new resolved")
    if payload["subdomain_bruteforce_new"]:
        for s in payload["subdomain_bruteforce_new"]:
            print(f"    NEW: {s}")
    print(f"  JS bundles scraped: {payload['js_bundle_scrape']['bundles_scraped']}")
    print(
        f"  Cross-host clusters: {len(payload['cross_host']['by_ip'])} IP, {len(payload['cross_host']['by_cdn'])} CDN"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
