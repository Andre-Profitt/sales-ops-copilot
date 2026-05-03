#!/usr/bin/env python3
"""Phase 1 analyzer — ingests Frida + mitmproxy + Procmon captures, produces a
unified call/HTTP/IPC timeline.

Inputs (pulled from VM via the runbook to a single capture dir):
  capture/
    mitm.har        — HTTP archive (mitmproxy --hardump output)
    mitm.flow       — mitmproxy binary log (optional)
    frida.log       — frida-trace text log
    procmon.csv     — Procmon CSV export

Output: <capture>/unified_timeline.json + summary.md
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


def _parse_frida(path: Path) -> list[dict]:
    """frida-trace text log lines look like:
       /* TID 0x1234 */
       hh:mm:ss.fff <module>!<func>(args)
    Return list of {ts, tid, module, func, raw}.
    """
    if not path.exists():
        return []
    rows = []
    cur_tid = None
    line_re = re.compile(r"^\s*(\d{1,2}:\d{2}:\d{2}\.\d{1,6})\s+(\S+!\S+)(.*)$")
    tid_re = re.compile(r"TID\s+(0x[0-9a-fA-F]+)")
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        m_tid = tid_re.search(line)
        if m_tid:
            cur_tid = m_tid.group(1)
            continue
        m = line_re.match(line)
        if m:
            ts, fn, rest = m.groups()
            module, func = fn.split("!", 1)
            rows.append(
                {
                    "source": "frida",
                    "ts_local": ts,
                    "tid": cur_tid,
                    "module": module,
                    "func": func,
                    "tail": rest.strip(),
                }
            )
    return rows


def _parse_har(path: Path) -> list[dict]:
    if not path.exists():
        return []
    try:
        h = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except json.JSONDecodeError:
        return []
    rows = []
    for entry in h.get("log", {}).get("entries", []):
        req = entry.get("request", {})
        res = entry.get("response", {})
        rows.append(
            {
                "source": "mitm",
                "ts_iso": entry.get("startedDateTime"),
                "method": req.get("method"),
                "url": req.get("url"),
                "status": res.get("status"),
                "request_size": req.get("bodySize"),
                "response_size": res.get("bodySize"),
                "request_content_type": _header(req, "Content-Type"),
                "response_content_type": _header(res, "Content-Type"),
                "duration_ms": entry.get("time"),
                "request_body_preview": (req.get("postData", {}).get("text") or "")[:500],
                "response_body_preview": (res.get("content", {}).get("text") or "")[:500],
            }
        )
    return rows


def _header(obj: dict, name: str) -> str | None:
    for h in obj.get("headers", []):
        if h.get("name", "").lower() == name.lower():
            return h.get("value")
    return None


def _parse_procmon(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows = []
    with path.open(encoding="utf-8", errors="replace") as f:
        try:
            reader = csv.DictReader(f)
            for r in reader:
                op = r.get("Operation", "")
                proc = r.get("Process Name", "")
                # filter to interesting ops only — keep everything that's think-cell-named
                if any(
                    k in proc.lower()
                    for k in ("powerpnt", "tcaddin", "tcasr", "tcserver", "ppttc", "excel")
                ):
                    rows.append(
                        {
                            "source": "procmon",
                            "ts_local": r.get("Time of Day"),
                            "process": proc,
                            "pid": r.get("PID"),
                            "operation": op,
                            "path": r.get("Path"),
                            "result": r.get("Result"),
                            "detail": (r.get("Detail") or "")[:400],
                        }
                    )
        except Exception as e:
            return [{"source": "procmon", "error": str(e)}]
    return rows


def _summarize(events: list[dict]) -> dict:
    by_source = Counter(e.get("source") for e in events)
    out = {
        "total_events": len(events),
        "by_source": dict(by_source),
    }
    # Frida
    frida = [e for e in events if e.get("source") == "frida"]
    if frida:
        out["frida"] = {
            "total": len(frida),
            "top_modules": Counter(e.get("module") for e in frida).most_common(15),
            "top_funcs": Counter(e.get("func") for e in frida).most_common(30),
            "tids_seen": sorted({e.get("tid") for e in frida if e.get("tid")}),
        }
    # mitm
    mitm = [e for e in events if e.get("source") == "mitm"]
    if mitm:
        host_re = re.compile(r"https?://([^/]+)")
        hosts = []
        for e in mitm:
            m = host_re.search(e.get("url") or "")
            if m:
                hosts.append(m.group(1))
        out["mitm"] = {
            "total": len(mitm),
            "by_method": Counter(e.get("method") for e in mitm),
            "by_status": Counter(e.get("status") for e in mitm),
            "top_hosts": Counter(hosts).most_common(20),
            "thinkcell_calls": [e for e in mitm if "think-cell.com" in (e.get("url") or "")],
        }
    # procmon
    procmon = [e for e in events if e.get("source") == "procmon"]
    if procmon:
        out["procmon"] = {
            "total": len(procmon),
            "by_process": Counter(e.get("process") for e in procmon),
            "by_operation": Counter(e.get("operation") for e in procmon).most_common(20),
            "tcasr_events": [e for e in procmon if "tcasr" in (e.get("process") or "").lower()][
                :50
            ],
        }
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--capture",
        type=Path,
        required=True,
        help="Directory containing mitm.har, frida.log, procmon.csv",
    )
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()

    cap = args.capture.expanduser().resolve()
    if not cap.is_dir():
        raise SystemExit(f"capture dir not found: {cap}")

    output_dir = args.output or cap
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"[phase1] reading captures from {cap}", flush=True)
    frida_events = _parse_frida(cap / "frida.log")
    mitm_events = _parse_har(cap / "mitm.har")
    procmon_events = _parse_procmon(cap / "procmon.csv")

    all_events = frida_events + mitm_events + procmon_events
    summary = _summarize(all_events)

    timeline = output_dir / "unified_timeline.json"
    timeline.write_text(
        json.dumps(
            {
                "schema": "simcorp-thinkcell-phase1-timeline/v1",
                "capture_dir": str(cap),
                "summary": summary,
                "events": all_events,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"[phase1] wrote {timeline}", flush=True)

    md = output_dir / "summary.md"
    lines = [
        "# Phase 1 Capture Summary",
        f"Capture dir: `{cap}`",
        f"- Total events: **{summary['total_events']}**",
        f"- By source: {summary['by_source']}",
        "",
    ]
    if "frida" in summary:
        lines += [
            "## Frida",
            f"- {summary['frida']['total']} events across {len(summary['frida']['tids_seen'])} threads",
            "- Top funcs called:",
        ]
        for fn, c in summary["frida"]["top_funcs"][:20]:
            lines.append(f"  - `{fn}` — {c}")
        lines.append("")
    if "mitm" in summary:
        lines += [
            "## HTTP (mitmproxy)",
            f"- {summary['mitm']['total']} requests",
            f"- Methods: {dict(summary['mitm']['by_method'])}",
            f"- Statuses: {dict(summary['mitm']['by_status'])}",
            "- Top hosts:",
        ]
        for h, c in summary["mitm"]["top_hosts"]:
            lines.append(f"  - {h} ({c})")
        lines += ["", "### think-cell.com calls"]
        for e in summary["mitm"]["thinkcell_calls"][:30]:
            lines.append(
                f"- `{e.get('method')} {e.get('url')}` → {e.get('status')} ({e.get('response_size')} bytes)"
            )
        lines.append("")
    if "procmon" in summary:
        lines += [
            "## Procmon",
            f"- {summary['procmon']['total']} relevant events",
            f"- Per-process: {dict(summary['procmon']['by_process'])}",
            "- Top operations:",
        ]
        for op, c in summary["procmon"]["by_operation"]:
            lines.append(f"  - {op}: {c}")
        if summary["procmon"]["tcasr_events"]:
            lines += ["", "### tcasr.exe events (first 20)"]
            for e in summary["procmon"]["tcasr_events"][:20]:
                lines.append(
                    f"- {e.get('ts_local')} {e.get('operation')} {e.get('path')} → {e.get('result')}"
                )
    md.write_text("\n".join(lines), encoding="utf-8")
    print(f"[phase1] wrote {md}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
