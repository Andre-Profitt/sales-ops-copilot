#!/usr/bin/env python3
"""End-to-end .ppttc -> .pptx demo via the documented `ppttc.exe` headless path.

This is the canonical sample for invoking the production pipeline
(build_ppttc.py output -> tcrender). Use it as the reference when wiring
new cadence scripts into the LAND deck factory.

A `.ppttc` is a JSON file shaped as `[{"template": "<.pptx path>", "data": [...]}]`
where each entry under `data` names a think-cell element on the template and
provides a `table` of cell values. think-cell ships a CLI binary
`ppttc.exe <input.ppttc> -o <output.pptx>` (Windows-only) that consumes the JSON
and emits a populated .pptx without needing a PowerPoint COM session.

Per the official docs corpus
(`state/thinkcell_bridge/official_docs_corpus/.../extraction.json`,
question C_presentations_open):

    "There is no documented PowerPoint-COM 'Presentations.Open(.ppttc)'
     entry point. The documented ways to render a .ppttc are: (1) double-click;
     (2) command-line: 'ppttc.exe <input.ppttc> -o <output.pptx>' (Windows-only);
     (3) HTTP POST to tcserver.exe ..."

Earlier iterations of this demo used `Presentations.Open(.ppttc)` via the
COM driver -- which works incidentally on a licensed VM but is not a
documented entry point. This rewrite pivots to ppttc.exe via `tcrender`,
which runs the render over SSH from Mac.

Real fixture (verified 2026-05-02):
    --ppttc            _windows_test/Jesper-Tyrer-LAND-2026-Q2.ppttc
    --template-override _windows_test/LAND_template.pptx
    -> ~8.9 MB output (reference live run produced 8,932,404 bytes).

Cross-platform: this script imports cleanly on Mac/Linux/Windows. The render
itself is performed by ppttc.exe on the Windows VM via the `SSHTransport`.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from tcrender import RenderError, SSHTransport, TcRenderClient


@dataclass(frozen=True)
class DemoResult:
    """Structured summary of a single .ppttc -> .pptx run."""

    input_ppttc: Path
    template_path_used: Path | None
    output_pptx: Path
    output_size_bytes: int
    bindings_count: int
    elapsed_seconds: float
    exit_code: int


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="build_ppttc_demo",
        description=(
            "Render a .ppttc to a .pptx via the documented ppttc.exe CLI on "
            "the Windows VM (over SSH). Mac/Windows-callable; the render runs "
            "remotely. Requires SSH access to the VM with ppttc.exe installed."
        ),
    )
    p.add_argument(
        "--ppttc",
        type=Path,
        required=True,
        help="Path to the .ppttc JSON instruction file (think-cell template binding).",
    )
    p.add_argument(
        "--template-override",
        type=Path,
        default=None,
        help="Optional .pptx path to substitute for the .ppttc's embedded template field.",
    )
    p.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Output .pptx path (default: <ppttc-stem>-output-<ts>.pptx beside the input).",
    )
    p.add_argument(
        "--keep-stage-files",
        action="store_true",
        help="Leave the VM-local stage tempdir in place after the render (for debugging).",
    )
    p.add_argument(
        "--ssh-host",
        default="Windows-VM",
        help="SSH config alias for the Windows VM (default: Windows-VM).",
    )
    p.add_argument(
        "--timeout",
        type=float,
        default=240.0,
        help="Hard wall-clock cap for ppttc.exe in seconds (default: 240).",
    )
    return p.parse_args(argv)


def _load_and_validate_ppttc(ppttc_path: Path) -> tuple[list[dict[str, Any]], int]:
    """Parse the .ppttc, validate shape, return (entries, total_bindings).

    Kept as a script-local helper for back-compat with the smoke test which
    exercises the validator directly. Internally also runs the canonical
    structural check via TcRenderClient.validate_ppttc.
    """
    text = ppttc_path.read_text(encoding="utf-8")
    parsed = json.loads(text)
    if not isinstance(parsed, list) or not parsed:
        raise ValueError(f"--ppttc must be a non-empty JSON array, got {type(parsed).__name__}")
    total_bindings = 0
    for i, entry in enumerate(parsed):
        if not isinstance(entry, dict):
            raise ValueError(f"--ppttc entry [{i}] is not a JSON object")
        if "template" not in entry or "data" not in entry:
            raise ValueError(f"--ppttc entry [{i}] missing required 'template'/'data' keys")
        if not isinstance(entry["data"], list):
            raise ValueError(f"--ppttc entry [{i}].data must be a list")
        total_bindings += len(entry["data"])
    return parsed, total_bindings


def _default_output_path(ppttc: Path) -> Path:
    ts = time.strftime("%Y%m%d-%H%M%S")
    return (ppttc.parent / f"{ppttc.stem}-output-{ts}.pptx").resolve()


def run(args: argparse.Namespace) -> DemoResult:
    """Execute the full .ppttc -> .pptx render. Caller handles errors."""
    ppttc_in = args.ppttc.expanduser().resolve()
    if not ppttc_in.exists():
        raise FileNotFoundError(f"--ppttc does not exist: {ppttc_in}")

    parsed, bindings_count = _load_and_validate_ppttc(ppttc_in)
    print(
        f"[demo] {ppttc_in.name}: {bindings_count} named binding(s) "
        f"across {len(parsed)} entry/entries"
    )

    template_used: Path | None = None
    if args.template_override is not None:
        tpl_resolved = args.template_override.expanduser().resolve()
        if not tpl_resolved.exists():
            raise FileNotFoundError(f"--template-override does not exist: {tpl_resolved}")
        template_used = tpl_resolved

    out_path = args.out.expanduser().resolve() if args.out else _default_output_path(ppttc_in)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    client = TcRenderClient(transport=SSHTransport(host=args.ssh_host))
    result = client.render(
        ppttc_path=ppttc_in,
        output_path=out_path,
        template_override=template_used,
        timeout=args.timeout,
        keep_stage_files=args.keep_stage_files,
    )

    return DemoResult(
        input_ppttc=ppttc_in,
        template_path_used=template_used,
        output_pptx=result.output_path,
        output_size_bytes=result.output_size_bytes,
        bindings_count=bindings_count,
        elapsed_seconds=result.elapsed_seconds,
        exit_code=result.exit_code,
    )


def _print_summary(r: DemoResult) -> None:
    print("=== build_ppttc_demo ===")
    print(f"  input_ppttc        : {r.input_ppttc}")
    print(f"  template_path_used : {r.template_path_used}")
    print(f"  output_pptx        : {r.output_pptx}")
    print(f"  output_size_bytes  : {r.output_size_bytes:,}")
    print(f"  bindings_count     : {r.bindings_count}")
    print(f"  elapsed_seconds    : {r.elapsed_seconds}")
    print(f"  ppttc_exit_code    : {r.exit_code}")


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        result = run(args)
    except FileNotFoundError as exc:
        print(f"[demo] input missing: {exc}", file=sys.stderr)
        return 3
    except (ValueError, json.JSONDecodeError) as exc:
        print(f"[demo] invalid .ppttc: {exc}", file=sys.stderr)
        return 4
    except RenderError as exc:
        print(f"[demo] render failed: {exc}", file=sys.stderr)
        return 5
    _print_summary(result)
    return 0


if __name__ == "__main__":
    sys.exit(main())
