#!/usr/bin/env python3
"""Mac→VM→Mac canary — runs gates 1+2+3 of the deck-factory harness.

Gate 1 (Mac):  scripts/validate_xlsx_strict.py            — strict OOXML linter
Gate 2 (VM):   scripts/vm/roundtrip_excel.ps1             — Excel COM repair-pass canary
Gate 3 (Mac):  scripts/diff_oxml.py                       — structural diff input vs roundtrip

This is the loop we'll run when re-attempting the SNN_ named-range migration:
write → gate-1 → ferry → gate-2 → ferry-back → gate-3 → patch the writer.

Usage:
    python3 scripts/run_xlsx_canary.py state/2026-Q2/Jesper-Tyrer/land.model.xlsx
    python3 scripts/run_xlsx_canary.py --skip-vm  state/.../land.model.xlsx   # gate-1 only
    python3 scripts/run_xlsx_canary.py --host Windows-VM state/.../land.model.xlsx
    python3 scripts/run_xlsx_canary.py --report state/canary/jesper.md  state/.../land.model.xlsx

Exit codes:
    0   all gates clean
    1   gate-1 fail (strict validation)
    2   gate-2 fail (Excel triggered repair pass — root cause identified)
    3   infra failure (ssh/scp/ps invocation broken)
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = REPO_ROOT / "scripts"
VALIDATOR = SCRIPTS / "validate_xlsx_strict.py"
DIFF = SCRIPTS / "diff_oxml.py"
VM_PS1 = SCRIPTS / "vm" / "roundtrip_excel.ps1"

DEFAULT_HOST = "Windows-VM"
VM_REMOTE_DIR = r"C:\share\xlsx_canary"


@dataclass
class GateResult:
    name: str
    ok: bool
    summary: str = ""
    payload: dict | list | str | None = None
    duration_s: float = 0.0
    fatal: bool = False  # if true, abort the pipeline

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "ok": self.ok,
            "summary": self.summary,
            "payload": self.payload,
            "duration_s": round(self.duration_s, 3),
            "fatal": self.fatal,
        }


@dataclass
class CanaryReport:
    input_path: str
    host: str | None
    gate_results: list[GateResult] = field(default_factory=list)

    @property
    def all_ok(self) -> bool:
        return all(g.ok for g in self.gate_results)

    def to_dict(self) -> dict:
        return {
            "input_path": self.input_path,
            "host": self.host,
            "all_ok": self.all_ok,
            "gates": [g.to_dict() for g in self.gate_results],
        }


def _time(fn, *args, **kwargs):
    t0 = time.monotonic()
    out = fn(*args, **kwargs)
    return out, time.monotonic() - t0


def gate1_strict(input_path: Path) -> GateResult:
    """Run the Mac-side strict OOXML linter."""
    cmd = [sys.executable, str(VALIDATOR), str(input_path), "--json"]
    proc, dur = _time(subprocess.run, cmd, capture_output=True, text=True, check=False)
    if proc.returncode == 3:
        return GateResult(
            "gate1.strict",
            ok=False,
            fatal=True,
            summary="validator could not open file",
            duration_s=dur,
            payload={"stderr": proc.stderr},
        )
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return GateResult(
            "gate1.strict",
            ok=False,
            fatal=True,
            summary="validator returned non-JSON output",
            duration_s=dur,
            payload={"stdout": proc.stdout[-500:]},
        )
    rep = payload["reports"][0]
    fail_count = rep.get("fail_count", 0)
    warn_count = rep.get("warn_count", 0)
    ok = fail_count == 0
    summary = (
        f"fail={fail_count} warn={warn_count} defined_names={rep.get('defined_names_count', 0)}"
    )
    return GateResult("gate1.strict", ok=ok, summary=summary, payload=rep, duration_s=dur)


def _ssh(host: str, *args: str, capture: bool = True) -> subprocess.CompletedProcess:
    cmd = ["ssh", host, *args]
    return subprocess.run(cmd, capture_output=capture, text=True, check=False)


def _scp(src: str, dst: str) -> subprocess.CompletedProcess:
    return subprocess.run(["scp", "-q", src, dst], capture_output=True, text=True, check=False)


def gate2_roundtrip(
    host: str, input_path: Path, vm_remote_dir: str
) -> tuple[GateResult, Path | None]:
    """Ferry input to VM, run the PowerShell canary, ferry back roundtrip + JSON.

    Returns (GateResult, local_path_to_roundtrip_xlsx_or_None).
    """
    t0 = time.monotonic()

    # Ensure VM dir exists
    mkdir_cmd = (
        f'powershell -NoProfile -Command "New-Item -ItemType Directory -Path '
        f"'{vm_remote_dir}' -Force | Out-Null"
        f'"'
    )
    r = _ssh(host, mkdir_cmd)
    if r.returncode != 0:
        return GateResult(
            "gate2.roundtrip",
            ok=False,
            fatal=True,
            summary=f"ssh mkdir failed: {r.stderr.strip()[:200]}",
            duration_s=time.monotonic() - t0,
        ), None

    remote_xlsx = f"{vm_remote_dir}\\{input_path.name}"
    remote_ps1 = f"{vm_remote_dir}\\roundtrip_excel.ps1"
    remote_json = f"{vm_remote_dir}\\{input_path.stem}.canary.json"

    # Ferry inputs
    r = _scp(str(input_path), f"{host}:{remote_xlsx}")
    if r.returncode != 0:
        return GateResult(
            "gate2.roundtrip",
            ok=False,
            fatal=True,
            summary=f"scp xlsx → VM failed: {r.stderr.strip()[:200]}",
            duration_s=time.monotonic() - t0,
        ), None
    r = _scp(str(VM_PS1), f"{host}:{remote_ps1}")
    if r.returncode != 0:
        return GateResult(
            "gate2.roundtrip",
            ok=False,
            fatal=True,
            summary=f"scp ps1 → VM failed: {r.stderr.strip()[:200]}",
            duration_s=time.monotonic() - t0,
        ), None

    # Run the canary
    run_cmd = (
        f"powershell -NoProfile -ExecutionPolicy Bypass "
        f'-File "{remote_ps1}" '
        f'-Path "{remote_xlsx}" '
        f'-OutputJson "{remote_json}"'
    )
    r = _ssh(host, run_cmd)

    # Ferry JSON back
    json_local = Path(tempfile.gettempdir()) / f"{input_path.stem}.canary.json"
    r2 = _scp(f"{host}:{remote_json}", str(json_local))
    if r2.returncode != 0 or not json_local.exists():
        return GateResult(
            "gate2.roundtrip",
            ok=False,
            fatal=True,
            summary=f"scp canary json ← VM failed: {r2.stderr.strip()[:200]}",
            duration_s=time.monotonic() - t0,
            payload={"ps_stdout": r.stdout[-500:], "ps_stderr": r.stderr[-500:]},
        ), None

    try:
        canary = json.loads(json_local.read_text())
    except json.JSONDecodeError as e:
        return GateResult(
            "gate2.roundtrip",
            ok=False,
            fatal=True,
            summary=f"canary json unparseable: {e}",
            duration_s=time.monotonic() - t0,
            payload={"raw": json_local.read_text()[:500]},
        ), None

    # Ferry roundtrip xlsx back if it exists
    roundtrip_local: Path | None = None
    if canary.get("ok") and canary.get("output_path"):
        # output_path is a Windows path; just use the basename next to the input
        rt_basename = Path(canary["output_path"].replace("\\", "/")).name
        rt_remote = f"{vm_remote_dir}\\{rt_basename}"
        rt_local = input_path.with_name(rt_basename)
        r3 = _scp(f"{host}:{rt_remote}", str(rt_local))
        if r3.returncode == 0 and rt_local.exists():
            roundtrip_local = rt_local

    cl = canary.get("corrupt_load")
    cl_name = canary.get("corrupt_load_name")
    repair_log = canary.get("repair_log")
    ok = bool(canary.get("ok")) and cl == 0
    summary_bits = [f"corrupt_load={cl}({cl_name})"]
    if repair_log:
        summary_bits.append("repair_log_present")
    if canary.get("error"):
        summary_bits.append(f"error={canary['error'][:80]}")
    summary = " ".join(summary_bits)

    return GateResult(
        "gate2.roundtrip",
        ok=ok,
        summary=summary,
        payload=canary,
        duration_s=time.monotonic() - t0,
    ), roundtrip_local


def gate3_diff(input_path: Path, roundtrip_path: Path) -> GateResult:
    cmd = [sys.executable, str(DIFF), str(input_path), str(roundtrip_path), "--json"]
    proc, dur = _time(subprocess.run, cmd, capture_output=True, text=True, check=False)
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return GateResult(
            "gate3.diff",
            ok=False,
            fatal=True,
            summary="diff returned non-JSON",
            duration_s=dur,
            payload={"stdout": proc.stdout[-500:]},
        )

    parts_diff = len(payload.get("part_diffs") or [])
    bin_changed = len(payload.get("binary_changed") or [])
    parts_added = len(payload.get("parts_added") or [])
    parts_removed = len(payload.get("parts_removed") or [])

    # Excel rewriting style is not necessarily a "fail" — what matters is
    # whether the roundtrip introduced semantic changes. For now we report
    # ok=True regardless (informational); the caller can interpret.
    summary = (
        f"parts_added={parts_added} parts_removed={parts_removed} "
        f"binary_changed={bin_changed} xml_parts_diffed={parts_diff}"
    )
    return GateResult("gate3.diff", ok=True, summary=summary, payload=payload, duration_s=dur)


def render_markdown(report: CanaryReport) -> str:
    lines = ["# xlsx canary report", "", f"- input: `{report.input_path}`"]
    if report.host:
        lines.append(f"- host:  `{report.host}`")
    lines.append(f"- result: **{'CLEAN' if report.all_ok else 'PROBLEMS'}**")
    lines.append("")
    for g in report.gate_results:
        flag = "✓" if g.ok else "✗"
        lines.append(f"## {flag} {g.name}  ({g.duration_s:.2f}s)")
        lines.append(f"- {g.summary}")
        if g.name == "gate1.strict" and isinstance(g.payload, dict):
            findings = g.payload.get("findings", [])
            fails = [f for f in findings if f["level"] == "fail"]
            warns = [f for f in findings if f["level"] == "warn"]
            for f in fails[:20]:
                lines.append(f"  - **FAIL** `{f['rule']}` — {f['message']}")
            for f in warns[:10]:
                lines.append(f"  - warn `{f['rule']}` — {f['message']}")
        elif g.name == "gate2.roundtrip" and isinstance(g.payload, dict):
            for k in (
                "corrupt_load",
                "corrupt_load_name",
                "bytes_in",
                "bytes_out",
                "open_seconds",
                "save_seconds",
                "error",
            ):
                v = g.payload.get(k)
                if v is not None:
                    lines.append(f"  - {k}: `{v}`")
            rl = g.payload.get("repair_log")
            if rl:
                lines.append("  - repair_log:")
                lines.append("    ```")
                for ln in str(rl).splitlines()[:30]:
                    lines.append(f"    {ln}")
                lines.append("    ```")
        elif g.name == "gate3.diff" and isinstance(g.payload, dict):
            for pd in (g.payload.get("part_diffs") or [])[:5]:
                lines.append(f"  - part `{pd['part']}`")
                for path in (pd.get("added_elements") or [])[:5]:
                    lines.append(f"    - `+ element {path}`")
                for path in (pd.get("removed_elements") or [])[:5]:
                    lines.append(f"    - `- element {path}`")
                for entry in (pd.get("attr_added") or [])[:5]:
                    lines.append(f"    - `+ attr {entry[1]}={entry[2]!r} on {entry[0]}`")
                for entry in (pd.get("attr_modified") or [])[:5]:
                    lines.append(
                        f"    - `~ attr {entry[1]} on {entry[0]}: {entry[2]!r} → {entry[3]!r}`"
                    )
        lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    p.add_argument("input", type=Path, help="xlsx to canary")
    p.add_argument("--host", default=DEFAULT_HOST, help=f"VM SSH alias (default: {DEFAULT_HOST})")
    p.add_argument(
        "--remote-dir", default=VM_REMOTE_DIR, help=f"VM working dir (default: {VM_REMOTE_DIR})"
    )
    p.add_argument(
        "--skip-vm", action="store_true", help="run only gate-1 (Mac-only, no VM round-trip)"
    )
    p.add_argument("--report", type=Path, default=None, help="write a markdown report to this path")
    p.add_argument("--json", action="store_true", help="emit JSON instead of text")
    args = p.parse_args(argv)

    if not args.input.exists():
        sys.stderr.write(f"input not found: {args.input}\n")
        return 3

    report = CanaryReport(input_path=str(args.input), host=None if args.skip_vm else args.host)

    # Gate 1
    g1 = gate1_strict(args.input)
    report.gate_results.append(g1)
    if g1.fatal:
        return 3
    if not g1.ok:
        # A gate-1 fail is ship-blocking but not infra-fatal — we can still
        # ferry to gate-2 to learn whether Excel agrees with our linter.
        # However per Andre's policy we DO NOT proceed to migration on a
        # gate-1 fail; we just collect data.
        pass

    if args.skip_vm:
        md = render_markdown(report)
        if args.report:
            args.report.parent.mkdir(parents=True, exist_ok=True)
            args.report.write_text(md, encoding="utf-8")
        if args.json:
            print(json.dumps(report.to_dict(), indent=2))
        else:
            print(md)
        return 0 if report.all_ok else 1

    # Gate 2 + 3
    g2, roundtrip_path = gate2_roundtrip(args.host, args.input, args.remote_dir)
    report.gate_results.append(g2)
    if g2.fatal:
        if not args.json:
            print(render_markdown(report))
        return 3

    if roundtrip_path is not None and roundtrip_path.exists():
        g3 = gate3_diff(args.input, roundtrip_path)
        report.gate_results.append(g3)

    md = render_markdown(report)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(md, encoding="utf-8")
    if args.json:
        print(json.dumps(report.to_dict(), indent=2))
    else:
        print(md)

    if not g1.ok:
        return 1
    if g2.ok is False and isinstance(g2.payload, dict) and g2.payload.get("corrupt_load") in (1, 2):
        return 2
    return 0 if report.all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
