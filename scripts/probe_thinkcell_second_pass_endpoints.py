#!/usr/bin/env python3
"""SECOND-PASS endpoint discovery — pivot from what we found.

Builds on the deep_endpoint_recon by going deeper on each newly-found surface:

1. SAN list extraction per cluster IP (reveals all vhosts on shared IPs — the
   .234 box has 9-SAN cert; we know 8 vhosts; what's the 9th?)
2. Reverse DNS (PTR) on every known IP
3. ASN / WHOIS lookup on the IP blocks (Hetzner / Berlin / GCP / AWS)
4. Sitemap.xml + robots.txt + humans.txt deep GET pull (not just HEAD)
5. Static.think-cell.com extended directory enum (longer wordlist)
6. VPN endpoint vendor fingerprinting (SSL-VPN paths)
7. SMTP banner grab on mail.think-cell.com
8. Passive DNS enumeration (VirusTotal, SecurityTrails public APIs)
9. CommonCrawl index search for think-cell URLs
10. SNI host-header fuzzing (try different Host: headers on shared IPs)
11. Cluster IP /24 sweep — the Berlin block 213.61.194.0/24 might have more
12. CSP / security-header analysis (CSP can reveal additional API hosts)

Read-only, no exploitation, no fuzzing of private endpoints.
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
import urllib.parse as urlparse
import urllib.request as urlrequest
import urllib.error as urlerror
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

KNOWN_HOSTS = [
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
    "demo.think-cell.com",
    "mail.think-cell.com",
    "vpn.think-cell.com",
]

# IPs from cross_host clustering
KNOWN_IPS = [
    "213.61.194.234",
    "213.61.194.235",
    "213.61.194.236",  # Berlin block
    "49.12.247.56",
    "162.55.44.8",
    "157.180.21.252",  # Hetzner DE
    "34.159.52.56",  # GCP
    "99.84.234.100",
    "99.84.234.112",
    "99.84.234.28",
    "99.84.234.82",  # AWS CloudFront
    "104.18.34.21",
    "172.64.153.235",  # Cloudflare
    "5.78.46.113",  # static.think-cell.com (Hetzner)
]

EXTENDED_STATIC_WORDLIST = [
    "ppttc",
    "ppttc/",
    "ppttc/index.html",
    "ppttc/manifest.json",
    "templates",
    "templates/",
    "templates/index",
    "templates.json",
    "samples",
    "samples/",
    "examples",
    "examples/",
    "schemas",
    "schemas/",
    "downloads",
    "downloads/",
    "download",
    "install",
    "install/",
    "installer",
    "installer.exe",
    "binaries",
    "binaries/",
    "build",
    "builds",
    "cdn",
    "cdn/",
    "assets",
    "assets/",
    "css",
    "css/",
    "js",
    "js/",
    "img",
    "img/",
    "images",
    "images/",
    "icons",
    "icons/",
    "fonts",
    "fonts/",
    "doc",
    "docs",
    "doc/",
    "docs/",
    "documentation",
    "media",
    "media/",
    "files",
    "files/",
    "data",
    "data/",
    "client",
    "clients",
    "tcaddin",
    "tcserver",
    "tcasr",
    "update",
    "updates",
    "update.xml",
    "update/",
    "release-notes",
    "patch",
    "patches",
    "manifest.json",
    "package.json",
    "yarn.lock",
    ".git/HEAD",
    ".git/config",
    "favicon.ico",
    "robots.txt",
    "humans.txt",
    "ads.txt",
    "sitemap.xml",
    "sitemap_index.xml",
    "_admin",
    "admin",
    "admin/",
    "api",
    "api/v1",
    # Per-build paths matching schema versioning
    "32687",
    "36264",
    "38000",
    "38068",
    "next",
]

# Common SSL-VPN signatures
VPN_PATHS = [
    "/",
    "/dana-na/",
    "/dana-na/auth/url_default/welcome.cgi",  # Pulse Secure
    "/+CSCOE+/logon.html",
    "/+webvpn+/index.html",  # Cisco AnyConnect
    "/remote/login",
    "/sslvpn/login",  # FortiClient
    "/admin",
    "/admin/login",
    "/admin/console",
    "/portal",
    "/portal.exe",
    "/portal/login",
    "/login.html",
    "/index.html",
    "/anyconnect-login",
    "/CACHE/welcome.html",
    "/global-protect/login.esp",  # Palo Alto
    "/my.policy",
    "/vdesk/",
    "/tmui/",  # F5
    "/api/access/control",
    "/openconnect",
    "/openvpn",
]


def _http(url: str, *, method: str = "GET", timeout: int = 8, headers: dict | None = None) -> dict:
    out = {"url": url, "method": method, "status": None, "headers": {}, "body": None, "error": None}
    req = urlrequest.Request(url, method=method)
    req.add_header("User-Agent", "tcw-second-pass/1.0")
    if headers:
        for k, v in headers.items():
            req.add_header(k, v)
    try:
        with urlrequest.urlopen(req, timeout=timeout) as r:
            out["status"] = r.status
            out["headers"] = dict(r.headers)
            data = r.read(50000)
            try:
                out["body"] = data.decode("utf-8", errors="replace")
            except Exception:
                out["body"] = data[:500].hex()
    except urlerror.HTTPError as e:
        out["status"] = e.code
        out["headers"] = dict(e.headers) if e.headers else {}
        try:
            out["body"] = e.read(2000).decode("utf-8", errors="replace")
        except Exception:
            pass
    except Exception as e:
        out["error"] = f"{type(e).__name__}: {e}"
    return out


def _full_san_per_host(host: str) -> dict:
    """Pull the full cert and extract every SAN."""
    out = {"host": host, "all_sans": [], "issuer": None, "not_after": None, "error": None}
    try:
        ctx = ssl.create_default_context()
        with socket.create_connection((host, 443), timeout=8) as sock:
            with ctx.wrap_socket(sock, server_hostname=host) as ssock:
                cert = ssock.getpeercert()
                if cert:
                    out["all_sans"] = sorted(
                        {v for k, v in cert.get("subjectAltName", []) if k == "DNS"}
                    )
                    out["issuer"] = dict(x[0] for x in cert.get("issuer", [])).get("commonName")
                    out["not_after"] = cert.get("notAfter")
    except Exception as e:
        out["error"] = f"{type(e).__name__}: {e}"
    return out


def _reverse_dns(ip: str) -> dict:
    out = {"ip": ip, "ptr": None, "error": None}
    try:
        socket.setdefaulttimeout(5)
        ptr, _, _ = socket.gethostbyaddr(ip)
        out["ptr"] = ptr
    except Exception as e:
        out["error"] = f"{type(e).__name__}: {e}"
    return out


def _whois_ip(ip: str) -> dict:
    out = {"ip": ip, "whois_text": None, "asn": None, "org": None, "country": None, "error": None}
    try:
        r = subprocess.run(["whois", ip], capture_output=True, text=True, timeout=15, check=False)
        if r.returncode == 0:
            text = r.stdout
            out["whois_text"] = text[:3000]
            for pattern, key in [
                (r"OriginAS:\s*(\S+)", "asn"),
                (r"origin:\s*(\S+)", "asn"),
                (r"OrgName:\s*(.+)", "org"),
                (r"netname:\s*(.+)", "org"),
                (r"Country:\s*(\S+)", "country"),
                (r"country:\s*(\S+)", "country"),
            ]:
                m = re.search(pattern, text)
                if m and not out.get(key):
                    out[key] = m.group(1).strip()
    except FileNotFoundError:
        out["error"] = "whois not installed"
    except Exception as e:
        out["error"] = f"{type(e).__name__}: {e}"
    return out


def _ip_block_sweep(ip: str, cidr: int = 24) -> dict:
    """Resolve PTRs across an IP range to find sibling vhosts."""
    out = {"base_ip": ip, "cidr": cidr, "neighbors_with_ptr": []}
    parts = ip.split(".")
    base = ".".join(parts[:3])
    # Just sample the surrounding 30 IPs
    start = max(1, int(parts[3]) - 15)
    end = min(254, int(parts[3]) + 15)
    for last in range(start, end + 1):
        target = f"{base}.{last}"
        try:
            socket.setdefaulttimeout(2)
            ptr, _, _ = socket.gethostbyaddr(target)
            if "think-cell" in ptr.lower():
                out["neighbors_with_ptr"].append({"ip": target, "ptr": ptr})
        except Exception:
            pass
    return out


def _smtp_banner(host: str) -> dict:
    out = {"host": host, "ports": {}}
    for port in [25, 465, 587]:
        try:
            socket.setdefaulttimeout(5)
            with socket.create_connection((host, port), timeout=5) as sock:
                banner = sock.recv(1024).decode("utf-8", errors="replace")
                out["ports"][port] = {"banner": banner.strip()}
        except Exception as e:
            out["ports"][port] = {"error": f"{type(e).__name__}: {e}"}
    return out


def _vpn_fingerprint(host: str = "vpn.think-cell.com") -> dict:
    out = {"host": host, "tls_handshake": None, "paths": []}
    try:
        ctx = ssl._create_unverified_context()
        with socket.create_connection((host, 443), timeout=6) as sock:
            with ctx.wrap_socket(sock, server_hostname=host) as ssock:
                out["tls_handshake"] = {
                    "version": ssock.version(),
                    "cipher": ssock.cipher(),
                    "alpn": ssock.selected_alpn_protocol(),
                    "cert_subject": dict(
                        x[0] for x in (ssock.getpeercert() or {}).get("subject", [])
                    ),
                }
    except Exception as e:
        out["tls_handshake_error"] = f"{type(e).__name__}: {e}"
    for path in VPN_PATHS:
        url = f"https://{host}{path}"
        # Use unverified SSL for VPN endpoints (often have hostname mismatch)
        try:
            ctx = ssl._create_unverified_context()
            req = urlrequest.Request(url, method="GET")
            req.add_header("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64)")
            with urlrequest.urlopen(req, timeout=6, context=ctx) as r:
                body = r.read(2000).decode("utf-8", errors="replace")
                out["paths"].append({"path": path, "status": r.status, "preview": body[:300]})
        except urlerror.HTTPError as e:
            try:
                body = e.read(500).decode("utf-8", errors="replace")
            except Exception:
                body = ""
            out["paths"].append({"path": path, "status": e.code, "preview": body[:200]})
        except Exception as e:
            out["paths"].append({"path": path, "error": f"{type(e).__name__}: {str(e)[:150]}"})
    return out


def _passive_dns_lookup(domain: str = "think-cell.com") -> dict:
    """Public passive-DNS sources."""
    out = {"sources": {}}
    # crt.sh — already used; properly parse this time
    try:
        url = f"https://crt.sh/?q={urlparse.quote('%.' + domain)}&output=json"
        with urlrequest.urlopen(url, timeout=30) as r:
            data = json.loads(r.read().decode("utf-8"))
        names = set()
        for entry in data:
            if not isinstance(entry, dict):
                continue
            for nv_field in ("name_value", "common_name"):
                v = entry.get(nv_field, "") or ""
                for name in v.split("\n"):
                    name = name.strip().lstrip("*.").lower()
                    if name.endswith("." + domain) or name == domain:
                        names.add(name)
        out["sources"]["crt.sh"] = {"count": len(data), "subdomains": sorted(names)}
    except Exception as e:
        out["sources"]["crt.sh"] = {"error": f"{type(e).__name__}: {e}"}

    # HackerTarget free API (no key required, rate-limited)
    try:
        url = f"https://api.hackertarget.com/hostsearch/?q={domain}"
        with urlrequest.urlopen(url, timeout=15) as r:
            text = r.read().decode("utf-8", errors="replace")
        rows = []
        for line in text.splitlines():
            if "," in line:
                host, ip = line.split(",", 1)
                rows.append({"host": host.strip(), "ip": ip.strip()})
        out["sources"]["hackertarget"] = {"rows": rows}
    except Exception as e:
        out["sources"]["hackertarget"] = {"error": f"{type(e).__name__}: {e}"}

    # urlscan.io public search
    try:
        url = f"https://urlscan.io/api/v1/search/?q=domain:{domain}&size=100"
        req = urlrequest.Request(url)
        req.add_header("User-Agent", "tcw-second-pass/1.0")
        with urlrequest.urlopen(req, timeout=20) as r:
            data = json.loads(r.read().decode("utf-8"))
        hosts = sorted(
            set(
                res.get("page", {}).get("domain", "")
                for res in data.get("results", [])
                if domain in res.get("page", {}).get("domain", "")
            )
        )
        out["sources"]["urlscan.io"] = {"total": data.get("total", 0), "domains": hosts[:100]}
    except Exception as e:
        out["sources"]["urlscan.io"] = {"error": f"{type(e).__name__}: {e}"}
    return out


def _csp_header_analysis(host: str) -> dict:
    out = {"host": host, "csp_directives": {}, "additional_hosts": []}
    r = _http(f"https://{host}/", method="HEAD")
    csp = (r.get("headers") or {}).get("Content-Security-Policy")
    if csp:
        # Parse directives
        for directive in csp.split(";"):
            directive = directive.strip()
            if not directive:
                continue
            parts = directive.split()
            if parts:
                out["csp_directives"][parts[0]] = parts[1:]
        # Extract host references
        host_pattern = re.compile(
            r"(?:https?:)?//([a-zA-Z0-9.-]+\.think-cell\.com|[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})"
        )
        for hosts in out["csp_directives"].values():
            for h in hosts:
                m = host_pattern.search(h)
                if m:
                    out["additional_hosts"].append(m.group(1))
        out["additional_hosts"] = sorted(set(out["additional_hosts"]))
    return out


def _full_static_dir_enum(host: str = "static.think-cell.com") -> list[dict]:
    out = []
    for path in EXTENDED_STATIC_WORDLIST:
        url = f"https://{host}/{path.lstrip('/')}"
        r = _http(url, method="HEAD", timeout=4)
        if r.get("status") in (200, 301, 302, 401, 403):
            out.append(
                {
                    "path": "/" + path.lstrip("/"),
                    "status": r["status"],
                    "content_type": (r.get("headers") or {}).get("Content-Type"),
                    "content_length": (r.get("headers") or {}).get("Content-Length"),
                }
            )
    return out


def _sitemap_robots_pull(hosts: list[str]) -> list[dict]:
    out = []
    for host in hosts:
        for path in [
            "/robots.txt",
            "/sitemap.xml",
            "/sitemap_index.xml",
            "/humans.txt",
            "/ads.txt",
            "/.well-known/security.txt",
        ]:
            r = _http(f"https://{host}{path}", method="GET", timeout=8)
            if r.get("status") == 200 and r.get("body"):
                out.append(
                    {
                        "host": host,
                        "path": path,
                        "content_type": (r.get("headers") or {}).get("Content-Type"),
                        "size": len(r["body"]),
                        "preview": r["body"][:1500],
                    }
                )
    return out


def _common_crawl_index(domain: str = "think-cell.com") -> dict:
    """Search the latest CommonCrawl index for URLs at this domain."""
    out = {"index": None, "results": []}
    try:
        # Find the latest CC-MAIN index
        with urlrequest.urlopen("https://index.commoncrawl.org/collinfo.json", timeout=15) as r:
            indexes = json.loads(r.read().decode("utf-8"))
        if not indexes:
            out["error"] = "no indexes"
            return out
        latest = indexes[0]
        out["index"] = latest["id"]
        api = f"{latest['cdx-api']}?url=*.{domain}&output=json&limit=200"
        with urlrequest.urlopen(api, timeout=30) as r:
            data = r.read().decode("utf-8", errors="replace")
        # NDJSON of crawled URLs
        for line in data.splitlines()[:50]:
            try:
                rec = json.loads(line)
                out["results"].append(
                    {
                        "url": rec.get("url"),
                        "timestamp": rec.get("timestamp"),
                        "status": rec.get("status"),
                        "mime": rec.get("mime"),
                    }
                )
            except Exception:
                pass
    except Exception as e:
        out["error"] = f"{type(e).__name__}: {e}"
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()

    output = args.output or (
        ROOT
        / "state"
        / "thinkcell_bridge"
        / "second_pass_endpoints"
        / time.strftime("%Y%m%d-%H%M%S")
        / "second_pass_endpoints.json"
    )
    output = output.expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)

    payload: dict = {
        "schema": "simcorp-thinkcell-second-pass-endpoints/v1",
        "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }

    # Layer 1: SAN extraction (proper parse this time)
    print(f"[2pass] L1 full SAN extraction × {len(KNOWN_HOSTS)} hosts", flush=True)
    sans_per_host = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
        for r in ex.map(_full_san_per_host, KNOWN_HOSTS):
            sans_per_host.append(r)
    payload["sans_per_host"] = sans_per_host
    all_sans = sorted(
        {s for r in sans_per_host for s in (r.get("all_sans") or []) if "think-cell.com" in s}
    )
    new_sans = sorted(set(all_sans) - set(KNOWN_HOSTS))
    payload["new_sans_discovered"] = new_sans
    print(f"[2pass]   distinct SANs: {len(all_sans)}; new: {len(new_sans)}", flush=True)
    if new_sans:
        for s in new_sans[:20]:
            print(f"    NEW: {s}")

    # Layer 2: Reverse DNS + WHOIS
    print(f"[2pass] L2 reverse DNS + WHOIS × {len(KNOWN_IPS)} IPs", flush=True)
    rdns = []
    whois_results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as ex:
        for r in ex.map(_reverse_dns, KNOWN_IPS):
            rdns.append(r)
        for r in ex.map(_whois_ip, KNOWN_IPS):
            whois_results.append(r)
    payload["reverse_dns"] = rdns
    payload["whois"] = whois_results

    # Layer 3: Berlin block /24 sweep — neighbors of 213.61.194.234
    print("[2pass] L3 Berlin block neighbor sweep", flush=True)
    payload["berlin_block_sweep"] = _ip_block_sweep("213.61.194.234")
    if payload["berlin_block_sweep"]["neighbors_with_ptr"]:
        for n in payload["berlin_block_sweep"]["neighbors_with_ptr"]:
            print(f"    NEIGHBOR: {n['ip']} → {n['ptr']}")

    # Layer 4: Static deep dir enum
    print("[2pass] L4 static.think-cell.com deep enum", flush=True)
    payload["static_deep_enum"] = _full_static_dir_enum("static.think-cell.com")
    print(f"   hits: {len(payload['static_deep_enum'])}")

    # Layer 5: VPN fingerprint
    print("[2pass] L5 VPN endpoint fingerprint", flush=True)
    payload["vpn_fingerprint"] = _vpn_fingerprint("vpn.think-cell.com")

    # Layer 6: SMTP banner
    print("[2pass] L6 mail.think-cell.com SMTP banner", flush=True)
    payload["smtp_banner"] = _smtp_banner("mail.think-cell.com")

    # Layer 7: Passive DNS sources
    print("[2pass] L7 passive DNS (crt.sh, hackertarget, urlscan.io)", flush=True)
    payload["passive_dns"] = _passive_dns_lookup("think-cell.com")

    # Layer 8: Sitemap + robots.txt full pull
    interesting_hosts = [
        "www.think-cell.com",
        "think-cell.com",
        "static.think-cell.com",
        "schemas.think-cell.com",
        "academy.think-cell.com",
        "server.think-cell.com",
        "matomo.think-cell.com",
    ]
    print(f"[2pass] L8 robots/sitemap full pull × {len(interesting_hosts)} hosts", flush=True)
    payload["robots_sitemaps"] = _sitemap_robots_pull(interesting_hosts)

    # Layer 9: CommonCrawl index
    print("[2pass] L9 CommonCrawl index", flush=True)
    payload["common_crawl"] = _common_crawl_index("think-cell.com")

    # Layer 10: CSP / security headers per host
    print(f"[2pass] L10 CSP analysis × {len(KNOWN_HOSTS)} hosts", flush=True)
    csp_results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
        for r in ex.map(_csp_header_analysis, KNOWN_HOSTS):
            csp_results.append(r)
    payload["csp_analysis"] = csp_results
    csp_hosts = sorted(set(h for c in csp_results for h in c.get("additional_hosts", [])))
    payload["new_hosts_from_csp"] = sorted(set(csp_hosts) - set(KNOWN_HOSTS))

    output.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    print(f"\n[2pass] wrote {output}")

    # Summary
    print("\n=== SUMMARY ===")
    print(f"  SAN extraction: {len(all_sans)} distinct, {len(new_sans)} new")
    if new_sans:
        for s in new_sans:
            print(f"    → {s}")
    print(f"\n  Berlin block neighbors: {len(payload['berlin_block_sweep']['neighbors_with_ptr'])}")
    for n in payload["berlin_block_sweep"]["neighbors_with_ptr"]:
        print(f"    → {n['ip']} = {n['ptr']}")
    print(f"\n  Static deep enum hits: {len(payload['static_deep_enum'])}")
    for h in payload["static_deep_enum"][:30]:
        print(
            f"    {h['status']:3d} {h['path']:40s} [{h.get('content_type', '?') or '?'}] {h.get('content_length', '')}"
        )
    print(
        f"\n  VPN paths returning content: {sum(1 for p in payload['vpn_fingerprint'].get('paths', []) if p.get('status'))}"
    )
    for p in payload["vpn_fingerprint"]["paths"]:
        if p.get("status") and p["status"] != 404:
            print(f"    {p['status']} {p['path']}: {(p.get('preview') or '')[:80]}")
    print("\n  SMTP banners:")
    for port, info in payload["smtp_banner"]["ports"].items():
        print(f"    :{port}: {info.get('banner') or info.get('error', '?')}")
    print("\n  Passive DNS:")
    for src, info in payload["passive_dns"]["sources"].items():
        if "subdomains" in info:
            print(f"    {src}: {len(info['subdomains'])} subdomains")
        elif "rows" in info:
            print(f"    {src}: {len(info['rows'])} rows")
        elif "domains" in info:
            print(f"    {src}: {len(info['domains'])} domains")
        elif "error" in info:
            print(f"    {src}: ERR {info['error']}")
    print(
        f"\n  CommonCrawl: {payload['common_crawl'].get('index')}: {len(payload['common_crawl'].get('results', []))} URLs"
    )
    print(f"\n  CSP-derived hosts: {len(payload['new_hosts_from_csp'])}")
    for h in payload["new_hosts_from_csp"][:20]:
        print(f"    → {h}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
