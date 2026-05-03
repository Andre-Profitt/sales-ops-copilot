"""Build LAND presentation-ready decks.

Pipeline per director:
1. Build strict `.ppttc` against the 42-name seed template.
2. Build the branded LAND layout deck.
3. If chart injections are enabled, bind and merge native think-cell charts on
   the Windows VM.
4. Otherwise publish the native layout directly.
5. Validate the final PPTX package and donor-boilerplate sentinels.
"""

from __future__ import annotations

import argparse
import html
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from zipfile import ZipFile

from _directors import canonical_directors
from build_ppttc import (
    LiteralWorkbook,
    ModelWorkbook,
    _build_for_director,
    _director_artifacts,
    _load_json,
    _parse_markdown_sections,
    _resolve_director,
)
from ppttc_template import CHART_INJECTIONS, build_director_template


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PERIOD = "2026-Q2"
DEFAULT_HOST = "Windows-VM"
SEED_TEMPLATE = ROOT / "assets" / "LAND_thinkcell_seed.pptx"
BASE_TEMPLATE = ROOT / "assets" / "LAND_template.pptx"
MERGE_SCRIPT = ROOT / "_windows_test" / "merge_charts_into_layout.ps1"
RUN_INTERACTIVE = ROOT / "_windows_test" / "run_interactive_task.ps1"
STATE_DIR = ROOT / "state" / "thinkcell_bridge"
EXPECTED_SLIDES = 28
MIN_NATIVE_TABLES = 12
FORBIDDEN_TEXT = (
    "Keywords:",
    "This slide contains",
    "Insert your desired text",
    "Insert chart title here",
    "[think-cell",
    "Pipe-movement bridge",
    "Stage × Industry",
    "Sales velocity",
    "Pipeline creation velocity",
    "GRR proxy",
    "old APAC",
    "Rebekka",
    "current deck had",
    "ready for rehearsal",
    "publish blockers",
    "Original Apr 20 pack",
    "CreatedDate velocity proxy",
    "sales-velocity proxy",
    "unwtd",
    "ARR unwtd",
    "ARR (unwtd)",
)


def _safe_name(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value)


def _to_unc(path: Path) -> str:
    resolved = path.expanduser().resolve()
    home = Path.home().resolve()
    rel = resolved.relative_to(home)
    return r"\\Mac\Home" + "\\" + "\\".join(rel.parts)


def _run(command: list[str], *, capture: bool = False) -> subprocess.CompletedProcess[str]:
    print("+ " + " ".join(command), flush=True)
    return subprocess.run(
        command,
        cwd=ROOT,
        check=True,
        text=True,
        capture_output=capture,
    )


def _build_layout_deck(director: dict[str, object], period: str) -> Path:
    artifacts = _director_artifacts(period, director)
    trends = _load_json(artifacts.trends_path)
    brief = _parse_markdown_sections(artifacts.brief_path.read_text())
    model = ModelWorkbook(artifacts.model_path)
    legacy = LiteralWorkbook(artifacts.legacy_path)
    generated = build_director_template(
        artifacts=artifacts,
        base_template_path=BASE_TEMPLATE,
        trends=trends,
        brief_sections=brief,
        model=model,
        legacy=legacy,
        inject_charts=False,
    )
    layout = artifacts.director_dir / f"{artifacts.slug}-LAND-{artifacts.period}-layout.pptx"
    if generated != layout:
        if layout.exists():
            layout.unlink()
        generated.replace(layout)
    return layout


def _run_thinkcell_bridge(artifacts, host: str) -> Path:
    charts = artifacts.director_dir / f"{artifacts.slug}-LAND-{artifacts.period}-charts.pptx"
    command = [
        sys.executable,
        "scripts/run_thinkcell_windows_bridge.py",
        "--host",
        host,
        "--ppttc",
        str(artifacts.director_dir / f"{artifacts.slug}-LAND-{artifacts.period}.ppttc"),
        "--template",
        str(SEED_TEMPLATE),
        "--output",
        str(charts),
        "--expect-text",
        artifacts.name,
        "--expect-text",
        artifacts.period,
    ]
    _run(command)
    return charts


def _prepare_windows_merge(host: str) -> None:
    _run(["scp", str(MERGE_SCRIPT), str(RUN_INTERACTIVE), f"{host}:C:/tcw/"])


def _write_merge_wrapper(artifacts, layout: Path, charts: Path, output: Path) -> Path:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    run_id = f"{_safe_name(artifacts.slug)}_{_safe_name(artifacts.period)}_{int(time.time())}"
    wrapper = STATE_DIR / f"merge_{run_id}.ps1"
    wrapper.write_text(
        "\n".join(
            [
                '$ErrorActionPreference = "Stop"',
                '$merge = "C:\\tcw\\merge_charts_into_layout.ps1"',
                f'$layout = "{_to_unc(layout)}"',
                f'$charts = "{_to_unc(charts)}"',
                f'$output = "{_to_unc(output)}"',
                f'$runId = "{run_id}"',
                '$localLayout = "C:\\tcw\\$runId-layout.pptx"',
                '$localCharts = "C:\\tcw\\$runId-charts.pptx"',
                '$localOutput = "C:\\tcw\\$runId-merged.pptx"',
                "Remove-Item -LiteralPath @($localLayout, $localCharts, $localOutput) -Force -ErrorAction SilentlyContinue",
                "Copy-Item -LiteralPath $layout -Destination $localLayout -Force",
                "Copy-Item -LiteralPath $charts -Destination $localCharts -Force",
                "& $merge -LayoutPath $localLayout -ChartsPath $localCharts -OutputPath $localOutput",
                "Copy-Item -LiteralPath $localOutput -Destination $output -Force",
                "",
            ]
        )
    )
    return wrapper


def _run_merge(artifacts, layout: Path, charts: Path, host: str) -> Path:
    output = artifacts.director_dir / f"{artifacts.slug}-LAND-{artifacts.period}.pptx"
    wrapper = _write_merge_wrapper(artifacts, layout, charts, output)
    remote_wrapper = f"C:/tcw/{wrapper.name}"
    _run(["scp", str(wrapper), f"{host}:{remote_wrapper}"])
    task_name = f"CodexLandMerge_{_safe_name(artifacts.slug)}_{int(time.time())}"
    _run(
        [
            "ssh",
            host,
            (
                "powershell -NoProfile -ExecutionPolicy Bypass "
                f"-File C:\\tcw\\run_interactive_task.ps1 "
                f"-ScriptPath C:\\tcw\\{wrapper.name} "
                f"-TaskName {task_name}"
            ),
        ]
    )
    _wait_for_task(host, task_name)
    log_path = STATE_DIR / f"merge_{artifacts.slug}.log"
    log_text = ""
    for _ in range(12):
        _run(["scp", f"{host}:C:/tcw/merge-charts-into-layout.log", str(log_path)])
        log_text = log_path.read_text(errors="ignore")
        if "END ok" in log_text:
            return output
        if "ERROR " in log_text:
            break
        time.sleep(5)
    if "END ok" not in log_text:
        raise SystemExit(f"PowerPoint merge did not report END ok: {log_path}")
    return output


def _publish_layout_directly(artifacts, layout: Path) -> Path:
    output = artifacts.director_dir / f"{artifacts.slug}-LAND-{artifacts.period}.pptx"
    shutil.copy2(layout, output)
    return output


def _wait_for_task(host: str, task_name: str, *, timeout_seconds: int = 240) -> None:
    deadline = time.time() + timeout_seconds
    quoted_task = "'" + task_name.replace("'", "''") + "'"
    while time.time() < deadline:
        result = _run(
            [
                "ssh",
                host,
                (
                    "powershell -NoProfile -Command "
                    f'"[string](Get-ScheduledTask -TaskName {quoted_task}).State"'
                ),
            ],
            capture=True,
        )
        if result.stdout.strip() == "Ready":
            return
        time.sleep(5)
    raise SystemExit(f"Timed out waiting for scheduled task: {task_name}")


def _validate_final_deck(path: Path, *, director_name: str, period: str) -> None:
    if not path.exists() or path.stat().st_size == 0:
        raise SystemExit(f"Final deck missing or empty: {path}")
    with ZipFile(path) as zf:
        names = zf.namelist()
        slides = [name for name in names if name.startswith("ppt/slides/slide") and name.endswith(".xml")]
        embeddings = [name for name in names if name.startswith("ppt/embeddings/")]
        text = html.unescape("\n".join(zf.read(name).decode("utf-8", "ignore") for name in slides))
    if len(slides) != EXPECTED_SLIDES:
        raise SystemExit(f"{path} has {len(slides)} slides, expected {EXPECTED_SLIDES}")
    if CHART_INJECTIONS:
        if len(embeddings) < len(CHART_INJECTIONS):
            raise SystemExit(
                f"{path} contains {len(embeddings)} native chart OLE parts, "
                f"expected at least {len(CHART_INJECTIONS)} think-cell chart objects"
            )
    elif embeddings:
        raise SystemExit(
            f"{path} contains {len(embeddings)} native chart OLE parts; "
            "publishable deck currently requires native table/bar replacements for weak donor charts"
        )
    native_tables = text.count("<a:tbl")
    if native_tables < MIN_NATIVE_TABLES:
        raise SystemExit(f"{path} has {native_tables} native tables, expected at least {MIN_NATIVE_TABLES}")
    missing = [needle for needle in (director_name, period) if needle not in text]
    if missing:
        raise SystemExit(f"{path} is missing expected text: {missing}")
    if director_name == "Jesper Tyrer":
        missing_original_targets = [
            needle
            for needle in (
                "Q1 opened",
                "May 2026",
                "Friday, May 1, 2026",
                "EUR 17.1M",
                "Q1 slips",
                "EUR 9.4M",
                "FY26 renewals",
                "EUR 33.5M",
                "Current state workbook",
                "reconcile",
                "Q1 Land losses",
                "Q2-Q3 risk triage",
                "EUR 4.9M",
                "overdue-close",
                "EUR 10.7M",
                "EUR 5.6M",
                "Commit = EUR 2.7M",
                "zero recent activity",
                "top 7 open deals",
                "top 5 = 89%",
                "Amova Asset Management",
                "3 owners carry 50 pushes",
                "EUR 22.0M",
                "11 open deals pushed",
                "Edwina Chow owns 5",
                "Approved 2026",
                "Coolabah",
                "EUR 3.8M",
                "6 -> 12",
                "EUR 4.6M",
                "1W / 16L",
                "EUR 8.6M lost",
                "unweighted",
                "weighted ARR",
                "unweighted ARR",
            )
            if needle not in text
        ]
        if missing_original_targets:
            raise SystemExit(
                f"{path} is missing original APAC target coverage: {missing_original_targets}"
            )
    leaked = [needle for needle in FORBIDDEN_TEXT if needle in text]
    if leaked:
        raise SystemExit(f"{path} still contains donor boilerplate: {leaked}")


def _director_selection(args: argparse.Namespace) -> list[dict[str, object]]:
    if args.director:
        return [_resolve_director(args.director)]
    return canonical_directors()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--period", default=DEFAULT_PERIOD)
    parser.add_argument("--director", help="Build one director by display name or slug.")
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--skip-seed", action="store_true", help="Reuse the existing seed template.")
    args = parser.parse_args()

    if not args.skip_seed:
        _run([sys.executable, "scripts/build_thinkcell_seed_template.py", "--output", str(SEED_TEMPLATE)])
    if CHART_INJECTIONS:
        _prepare_windows_merge(args.host)

    outputs: list[Path] = []
    for director in _director_selection(args):
        artifacts = _director_artifacts(args.period, director)
        print(f"\n=== {artifacts.name} ===", flush=True)
        _build_for_director(
            director,
            period=args.period,
            template_path=SEED_TEMPLATE.resolve(),
            strict_template_contract=True,
        )
        layout = _build_layout_deck(director, args.period)
        if CHART_INJECTIONS:
            charts = _run_thinkcell_bridge(artifacts, args.host)
            final = _run_merge(artifacts, layout, charts, args.host)
        else:
            final = _publish_layout_directly(artifacts, layout)
        _validate_final_deck(final, director_name=artifacts.name, period=artifacts.period)
        outputs.append(final)
        print(f"ok {final}", flush=True)

    print("\nbuilt presentation decks:")
    for output in outputs:
        print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
