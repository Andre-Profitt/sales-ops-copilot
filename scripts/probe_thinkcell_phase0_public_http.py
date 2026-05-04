#!/usr/bin/env python3
"""Phase 0 — public HTTP / Cert Transparency / Wayback discovery on think-cell.com.

Mac-side, no VM required. All probes are read-only against public surfaces.

Probes:
- Cert Transparency (crt.sh) for all subdomains
- HEAD + OPTIONS against each known subdomain
- Common well-known paths (/.well-known/*, /openapi.*, /robots.txt, /health, /version)
- Wayback CDX API for historical snapshots of new subdomains
- DNS lookups (CNAME, A, TXT, NS) for each host

Output: state/thinkcell_bridge/phase0_public_http/<ts>/phase0_public_http.json
"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import socket
import subprocess
import sys
import time
from pathlib import Path
from urllib import error as urlerror
from urllib import parse as urlparse
from urllib import request as urlrequest


ROOT = Path(__file__).resolve().parent.parent

# Known + newly-discovered subdomains
KNOWN_SUBDOMAINS = [
    "www.think-cell.com",
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

WELL_KNOWN_PATHS = [
    "/",
    "/robots.txt",
    "/sitemap.xml",
    "/.well-known/security.txt",
    "/.well-known/openid-configuration",
    "/.well-known/oauth-authorization-server",
    "/openapi.json",
    "/openapi.yaml",
    "/swagger.json",
    "/api/schema",
    "/api/openapi.json",
    "/api/v1/openapi.json",
    "/v0/openapi.json",
    "/health",
    "/healthz",
    "/status",
    "/version",
    "/info",
    "/metrics",
    "/graphql",
    "/admin",
    "/portal",
]


def _http_request(url: str, method: str = "HEAD", timeout: int = 10) -> dict:
    req = urlrequest.Request(url, method=method)
    req.add_header("User-Agent", "tcw-phase0-probe/1.0 (research; local lab)")
    out = {
        "url": url,
        "method": method,
        "status": None,
        "headers": {},
        "body_preview": None,
        "error": None,
    }
    try:
        with urlrequest.urlopen(req, timeout=timeout) as r:
            out["status"] = r.status
            out["headers"] = dict(r.headers)
            if method == "GET":
                body = r.read(2000)
                try:
                    out["body_preview"] = body.decode("utf-8", errors="replace")
                except Exception:
                    out["body_preview"] = body[:500].hex()
    except urlerror.HTTPError as e:
        out["status"] = e.code
        out["headers"] = dict(e.headers) if e.headers else {}
        out["error"] = f"HTTP {e.code} {e.reason}"
        try:
            body = e.read(2000)
            out["body_preview"] = body.decode("utf-8", errors="replace")
        except Exception:
            pass
    except urlerror.URLError as e:
        out["error"] = f"URL error: {e.reason}"
    except socket.timeout:
        out["error"] = "timeout"
    except Exception as e:
        out["error"] = f"{type(e).__name__}: {e}"
    return out


def _ct_log_lookup(query: str = "%.think-cell.com") -> list[dict]:
    """Cert Transparency lookup via crt.sh."""
    url = f"https://crt.sh/?q={urlparse.quote(query)}&output=json"
    try:
        with urlrequest.urlopen(url, timeout=30) as r:
            data = json.loads(r.read().decode("utf-8"))
            return data
    except Exception as e:
        return [{"error": f"{type(e).__name__}: {e}"}]


def _wayback_lookup(host: str) -> dict:
    """Wayback Machine CDX API - find historical snapshots."""
    url = f"https://web.archive.org/cdx/search/cdx?url={host}/*&output=json&limit=200&from=20100101"
    try:
        with urlrequest.urlopen(url, timeout=20) as r:
            data = json.loads(r.read().decode("utf-8"))
            return {"host": host, "rows": data}
    except Exception as e:
        return {"host": host, "error": f"{type(e).__name__}: {e}"}


def _dns_lookup(host: str) -> dict:
    """DNS lookup via system resolver. Returns A, CNAME, NS, TXT where available."""
    out = {"host": host, "a": [], "cname": None, "ns": [], "txt": [], "errors": []}
    try:
        infos = socket.getaddrinfo(host, None, socket.AF_INET)
        out["a"] = sorted({i[4][0] for i in infos})
    except Exception as e:
        out["errors"].append(f"A: {e}")
    for rec_type in ("CNAME", "TXT", "NS"):
        try:
            r = subprocess.run(
                ["dig", "+short", host, rec_type],
                text=True,
                capture_output=True,
                timeout=8,
                check=False,
            )
            lines = [l.strip() for l in r.stdout.strip().splitlines() if l.strip()]
            if rec_type == "CNAME" and lines:
                out["cname"] = lines[0]
            elif rec_type == "TXT":
                out["txt"] = lines
            elif rec_type == "NS":
                out["ns"] = lines
        except FileNotFoundError:
            out["errors"].append(f"{rec_type}: dig not installed")
            break
        except Exception as e:
            out["errors"].append(f"{rec_type}: {e}")
    return out


def _per_host_probes(host: str) -> dict:
    return {
        "host": host,
        "dns": _dns_lookup(host),
        "head_root": _http_request(f"https://{host}/", method="HEAD"),
        "options_root": _http_request(f"https://{host}/", method="OPTIONS"),
        "well_known": [
            _http_request(f"https://{host}{path}", method="GET") for path in WELL_KNOWN_PATHS
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--max-hosts", type=int, default=40)
    args = parser.parse_args()

    output = args.output
    if output is None:
        stamp = time.strftime("%Y%m%d-%H%M%S")
        output = (
            ROOT
            / "state"
            / "thinkcell_bridge"
            / "phase0_public_http"
            / stamp
            / "phase0_public_http.json"
        )
    output = output.expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)

    print("[phase0] cert transparency lookup", flush=True)
    ct = _ct_log_lookup()
    ct_subdomains = sorted(
        {
            e.get("name_value", "").lower().lstrip("*.")
            for e in ct
            if isinstance(e, dict) and "name_value" in e
        }
    )
    flat = []
    for s in ct_subdomains:
        for line in s.split("\n"):
            line = line.strip().lstrip("*.")
            if line.endswith(".think-cell.com") or line == "think-cell.com":
                flat.append(line)
    flat = sorted(set(flat))[: args.max_hosts]
    print(
        f"[phase0] cert transparency: {len(ct)} entries, {len(flat)} unique hostnames", flush=True
    )

    all_hosts = sorted(set(KNOWN_SUBDOMAINS + flat))[: args.max_hosts]
    print(f"[phase0] probing {len(all_hosts)} hosts in parallel", flush=True)

    per_host = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
        futures = {ex.submit(_per_host_probes, h): h for h in all_hosts}
        for fut in concurrent.futures.as_completed(futures):
            try:
                per_host.append(fut.result())
            except Exception as e:
                per_host.append({"host": futures[fut], "error": f"{type(e).__name__}: {e}"})

    print("[phase0] wayback CDX for new subdomains", flush=True)
    new_subdomains = sorted(set(flat) - set(KNOWN_SUBDOMAINS))
    wayback = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ex:
        for s in new_subdomains[:20]:
            wayback.append(ex.submit(_wayback_lookup, s))
        wayback = [f.result() for f in wayback]

    payload = {
        "schema": "simcorp-thinkcell-phase0-public-http/v1",
        "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "cert_transparency": {
            "raw_count": len(ct),
            "unique_hostnames": flat,
            "newly_discovered": new_subdomains,
        },
        "per_host": per_host,
        "wayback": wayback,
    }
    output.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    # Brief summary
    print(f"\n[phase0] wrote {output}", flush=True)
    print(f"[phase0] {len(flat)} subdomains via CT, {len(new_subdomains)} new", flush=True)
    print("\n[phase0] new subdomains discovered:", flush=True)
    for s in new_subdomains:
        print(f"  - {s}", flush=True)
    print("\n[phase0] hosts with live HEAD response:", flush=True)
    for h in per_host:
        head = h.get("head_root", {})
        if head.get("status"):
            print(
                f"  {h['host']}: HEAD {head['status']} (server={head.get('headers', {}).get('Server', '?')})"
            )
    return 0


if __name__ == "__main__":
    sys.exit(main())
