"""
Analyze a Phase 12 /core/ capture produced by capture_aicore_oneshot.ps1.

Reads mitm.flow + frida.log, extracts every app.prod.ai request, decodes
auth headers + body schemas, and writes a markdown report.

Usage (from Mac):
  python3 analyze_aicore_capture.py <capture-dir>
  python3 analyze_aicore_capture.py /Volumes/Mac/Users/test/tc_aicore_captures/20260502-180000

If running on Mac with the VM's UNC path, you can also pass the SMB path:
  python3 analyze_aicore_capture.py //Mac/Home/.../tc_aicore_captures/20260502-180000

Output: <capture-dir>/report.md
"""

from __future__ import annotations
import json
import sys
import re
from pathlib import Path

try:
    from mitmproxy import io
except ImportError:
    print("ERROR: mitmproxy not installed. Install with: pip install --user mitmproxy")
    sys.exit(1)


def main():
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(1)
    cap_dir = Path(sys.argv[1])
    if not cap_dir.exists():
        print(f"ERROR: capture dir not found: {cap_dir}")
        sys.exit(1)

    flow_path = cap_dir / "mitm.flow"
    frida_path = cap_dir / "frida.log"
    report_path = cap_dir / "report.md"

    out = []
    out.append(f"# /core/ capture analysis — {cap_dir.name}\n")

    # ---------- mitm.flow ----------
    if flow_path.exists():
        out.append(f"## mitm.flow ({flow_path.stat().st_size} bytes)\n")
        thinkcell_flows = []
        all_hosts = set()
        with open(flow_path, "rb") as f:
            try:
                reader = io.FlowReader(f)
                for flow in reader.stream():
                    if not hasattr(flow, "request"):
                        continue
                    host = flow.request.pretty_host or flow.request.host
                    all_hosts.add(host)
                    if "think-cell" in host.lower() or "thinkcell" in host.lower():
                        thinkcell_flows.append(flow)
            except Exception as e:
                out.append(f"\n_warning: flow read error: {e}_\n")

        out.append(f"- Distinct hosts: {len(all_hosts)}")
        out.append(f"- think-cell flows: {len(thinkcell_flows)}")
        out.append("- Top hosts: " + ", ".join(sorted(all_hosts)[:15]))
        out.append("")

        for i, flow in enumerate(thinkcell_flows):
            req = flow.request
            resp = flow.response
            host = req.pretty_host or req.host
            out.append(f"### Flow {i + 1}: {req.method} https://{host}{req.path}\n")
            out.append("**Request headers:**")
            for k, v in req.headers.items():
                # Mask the token if it's >40 chars (it's the secret)
                v_safe = v if len(v) < 80 else f"{v[:60]}...({len(v)} chars)"
                out.append(f"- `{k}`: `{v_safe}`")
            out.append("")
            if req.content:
                body_str = req.content.decode("utf-8", errors="replace")
                out.append("**Request body:**")
                out.append("```")
                out.append(body_str[:4000])
                if len(body_str) > 4000:
                    out.append(f"...({len(body_str)} chars total)")
                out.append("```")
                out.append("")
                # Try to parse as JSON
                try:
                    parsed = json.loads(body_str)
                    out.append(
                        "**Parsed JSON keys:** "
                        + ", ".join(
                            f"`{k}`" for k in (parsed.keys() if isinstance(parsed, dict) else [])
                        )
                    )
                    out.append("")
                except Exception:
                    pass
            if resp:
                out.append(f"**Response: {resp.status_code} {resp.reason}**")
                ct = resp.headers.get("content-type", "?")
                out.append(f"- content-type: `{ct}`")
                if resp.content:
                    body_str = resp.content.decode("utf-8", errors="replace")
                    out.append("```")
                    out.append(body_str[:4000])
                    if len(body_str) > 4000:
                        out.append(f"...({len(body_str)} chars total)")
                    out.append("```")
                out.append("")
    else:
        out.append("## mitm.flow — NOT FOUND\n")

    # ---------- frida.log ----------
    if frida_path.exists():
        out.append(f"## frida.log ({frida_path.stat().st_size} bytes)\n")
        text = frida_path.read_text(errors="replace")

        # WinHttpSendRequest captures (custom handler)
        wsr_matches = re.findall(
            r"WinHttpSendRequest headers=(\".*?\") body_len=(\d+) body_hex=([0-9a-f]*)", text
        )
        out.append(f"- WinHttpSendRequest calls captured: {len(wsr_matches)}")
        # Filter: only show ones that look like /core/ or app.prod.ai
        relevant = []
        for headers_str, body_len, body_hex in wsr_matches:
            try:
                headers = json.loads(headers_str)
            except Exception:
                headers = headers_str
            # The headers field contains "Authorization: Bearer ..." etc.
            relevant.append((headers, int(body_len), body_hex))
        # Show ones that mention /core or app.prod or Authorization
        interesting = [
            r
            for r in relevant
            if any(k in str(r[0]) for k in ["app.prod.ai", "/core/", "Authorization"])
        ]
        out.append(f"- Relevant (has Authorization or /core/): {len(interesting)}")
        out.append("")
        for headers, blen, bhex in interesting[:10]:
            out.append("```")
            out.append(f"headers: {headers}")
            out.append(f"body_len: {blen}")
            if bhex:
                # Try to decode body as utf-8
                try:
                    body_bytes = bytes.fromhex(bhex)
                    body_str = body_bytes.decode("utf-8", errors="replace")
                    out.append(f"body (utf-8): {body_str[:600]!r}")
                except Exception:
                    out.append(f"body (hex): {bhex[:200]}")
            out.append("```")
            out.append("")

        # BCrypt custom handler captures
        bcs = re.findall(
            r"BCryptCreateHash hAlg=(\w+) flags=(\w+) isHmac=(\w+) cbSecret=(\d+) secret_hex=([\w<>:.\- ]*)",
            text,
        )
        out.append(f"\n- BCryptCreateHash calls: {len(bcs)}")
        hmac_calls = [b for b in bcs if b[2] == "True"]
        out.append(f"- HMAC mode calls: {len(hmac_calls)}")
        for hAlg, flags, isHmac, cbSecret, secret_hex in hmac_calls[:5]:
            out.append(f"  - hAlg={hAlg} cbSecret={cbSecret} secret_hex={secret_hex[:60]}")

        bhd = re.findall(r"BCryptHashData hHash=(\w+) cbInput=(\d+) input_hex=([0-9a-f]*)", text)
        out.append(f"- BCryptHashData calls: {len(bhd)}")
        for hHash, cbInput, input_hex in bhd[:3]:
            out.append(f"  - hHash={hHash} cbInput={cbInput} input_preview={input_hex[:120]}")

        bfh = re.findall(
            r"BCryptFinishHash hHash=(\w+) cbOutput=(\d+) \((\S+)\) output_hex=([0-9a-f]*)", text
        )
        out.append(f"- BCryptFinishHash calls: {len(bfh)}")
        for hHash, cbOutput, alg, output_hex in bfh[:3]:
            out.append(
                f"  - hHash={hHash} cbOutput={cbOutput} alg={alg} output_hex={output_hex[:60]}"
            )
    else:
        out.append("## frida.log — NOT FOUND\n")

    # ---------- Synthesis ----------
    out.append("\n## Synthesis\n")
    if flow_path.exists():
        with open(flow_path, "rb") as f:
            text = f.read().decode("latin-1")
        if "app.prod.ai" in text:
            out.append(
                "- ✅ /core/ traffic was captured. See request/response above for the wire format."
            )
        else:
            out.append("- ❌ No app.prod.ai traffic captured. Possible reasons:")
            out.append("  - The AI button was not clicked during the capture window")
            out.append(
                "  - WebView2 bypassed the system proxy (try the registry override or `netsh winhttp set proxy` already done)"
            )
            out.append("  - PowerPoint zombied before the click landed")
    else:
        out.append("- mitm.flow missing — capture script may have failed before mitm started")

    report = "\n".join(out)
    report_path.write_text(report)
    print(f"Report written: {report_path}")
    print()
    print(report[:4000])
    if len(report) > 4000:
        print("...(truncated; see file for full)")


if __name__ == "__main__":
    main()
