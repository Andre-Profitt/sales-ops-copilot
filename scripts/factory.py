#!/usr/bin/env python3
"""LAND deck factory CLI -- run all 9 director renders end-to-end.

Pipeline per director (production default):
    build_ppttc.py --director <Name> --period <P>      (build .ppttc)
    -> tcrender.TcRenderClient.render(...)              (render via SSH)
    -> archive into state/<P>/<dir>/decks/<ts>/         (move .pptx + audit.json)
    -> tcrender.native_fallback.enhance_deck(...)       (chart data on chart slides; ON by default)
    -> optional quality gate                            (verify + jinja-leak + completeness)

Streams progress in a `[i/N] <Director>: ppttc built (<n> bindings) ->
render <s>s -> archived -> gate PASSED|FAILED` form so a launchd run is
greppable. Final summary table prints pass/fail per director and an
exit code reflecting overall success in strict mode.

Polish-pass + master-transplant lineage are NOT in the production flow.
They produced visible quality bugs (black-fill ``PolishPassNakedTitle/
Subtitle`` text boxes, oversized ``PolishPassCoverNavyStripe``,
``Rechteck 137`` Lorem-ipsum donor leftover transplanted into Sarah's
master). The polish pass is now strictly opt-in behind
``--experimental-polish-pass`` (default off). The master-transplant
flow was never invoked from this script and stays out. Native-fallback
is the production-default enhancer (use ``--no-native-fallback`` to
disable in tests).

Hard constraints:
    * Stdlib + lxml only (already deps via tcrender + openpyxl).
    * ASCII-only.
    * NEVER auto-runs at pytest collection -- all logic lives behind
      ``main()`` and ``__name__ == '__main__'`` only invokes it.
    * Default template is ``assets/LAND_thinkcell_seed.pptx`` (the
      pre-polish, pre-transplant, pre-Lorem-ipsum donor); override with
      ``--template``.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# Repo layout: scripts/factory.py -> repo root is parents[1]. We have to add
# scripts/ to sys.path so we can import _directors and reuse the canonical
# director list. Done lazily inside _resolve_directors() to keep import-time
# side effects out of the module (so pytest can import this file freely).
REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = REPO_ROOT / "scripts"
DEFAULT_TEMPLATE = REPO_ROOT / "assets" / "LAND_thinkcell_seed.pptx"
DEFAULT_PERIOD = "2026-Q2"

# Variants that are NOT the canonical programmatic seed. The bare
# `LAND_thinkcell_seed.pptx` IS the working seed used by
# scripts/thinkcell_programmatic_lab.py — do NOT mark it legacy.
LEGACY_SEED_MARKERS = (
    "LAND_thinkcell_seed_polished",
    "LAND_thinkcell_seed_charts",
    "/legacy/",
    "Patrick-Gaughan-LAND",
    "pre-stripdev",
    "pre-jinja-cleanup",
)


def _is_legacy_template(template_path: Path) -> bool:
    s = str(template_path)
    return any(marker in s for marker in LEGACY_SEED_MARKERS)


@dataclass(frozen=True)
class FactoryDirectorResult:
    """One director's outcome from a factory run."""

    director: str
    slug: str
    ppttc_path: Path | None
    archived_pptx: Path | None
    elapsed_seconds: float
    binding_count: int
    gate_passed: bool | None  # None when gate was disabled
    error: str | None
    rendered: bool

    @property
    def ok(self) -> bool:
        if self.error is not None:
            return False
        if self.gate_passed is False:
            return False
        return self.rendered


@dataclass
class FactorySummary:
    """Aggregate result for a factory run."""

    period: str
    template: Path
    results: list[FactoryDirectorResult] = field(default_factory=list)

    @property
    def all_ok(self) -> bool:
        return all(r.ok for r in self.results)

    @property
    def passed_count(self) -> int:
        return sum(1 for r in self.results if r.ok)


# -- director resolution ---------------------------------------------------


def _resolve_directors(arg: str) -> list[dict[str, Any]]:
    """Resolve ``--directors`` arg to canonical director dicts.

    Args:
        arg: ``"all"`` (default in CLI) or comma-separated slugs/names.

    Returns:
        Ordered list of director dicts with at least ``name`` + ``scope_label``.
    """
    if str(SCRIPTS_DIR) not in sys.path:
        sys.path.insert(0, str(SCRIPTS_DIR))
    from _directors import canonical_directors  # type: ignore[import-not-found]

    canonical = canonical_directors()
    if arg.strip().lower() in {"all", "", "*"}:
        return canonical

    requested = [s.strip() for s in arg.split(",") if s.strip()]
    by_key = {d["name"].casefold(): d for d in canonical}
    by_key.update({_slug(d["name"]).casefold(): d for d in canonical})

    selected: list[dict[str, Any]] = []
    missing: list[str] = []
    for r in requested:
        d = by_key.get(r.casefold())
        if d is None:
            missing.append(r)
            continue
        if d not in selected:
            selected.append(d)
    if missing:
        raise SystemExit(
            f"Unknown director(s): {', '.join(missing)}. "
            f"Known: {', '.join(d['name'] for d in canonical)}"
        )
    return selected


def _slug(name: str) -> str:
    return name.replace(" ", "-")


# -- ppttc build (subprocess to keep this script lightweight) --------------


def _build_ppttc(director_name: str, period: str, template: Path) -> Path:
    """Invoke ``scripts/build_ppttc.py`` for a single director.

    Returns the .ppttc path printed by the builder.
    """
    cmd = [
        sys.executable,
        str(SCRIPTS_DIR / "build_ppttc.py"),
        "--director",
        director_name,
        "--period",
        period,
        "--template",
        str(template),
    ]
    cp = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        check=False,
    )
    if cp.returncode != 0:
        raise RuntimeError(
            f"build_ppttc.py exited rc={cp.returncode}\n"
            f"stdout={cp.stdout.strip()}\nstderr={cp.stderr.strip()}"
        )
    # build_ppttc.py prints one .ppttc path per director plus a count line.
    paths = [line.strip() for line in cp.stdout.splitlines() if line.strip().endswith(".ppttc")]
    if not paths:
        raise RuntimeError(f"build_ppttc.py produced no .ppttc path on stdout:\n{cp.stdout}")
    out = Path(paths[-1])
    if not out.exists():
        raise FileNotFoundError(f"build_ppttc.py reported missing path: {out}")
    return out


def _ppttc_binding_count(ppttc_path: Path) -> int:
    try:
        parsed = json.loads(ppttc_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return 0
    if not isinstance(parsed, list):
        return 0
    return sum(
        len(entry.get("data", []))
        for entry in parsed
        if isinstance(entry, dict) and isinstance(entry.get("data"), list)
    )


# -- one-director render ---------------------------------------------------


def render_one_director(
    director: dict[str, Any],
    *,
    period: str,
    template: Path,
    archive: bool,
    quality_gate: bool,
    quality_gate_strict: bool,
    archive_root: Path | None,
    ssh_host: str,
    timeout: float,
    skip_ppttc_build: bool = False,
    pre_built_ppttc: Path | None = None,
    native_fallback: bool = False,
    polish_pass_enabled: bool = False,
    image_charts: bool = True,
) -> FactoryDirectorResult:
    """Build .ppttc and render one director's deck.

    The function imports tcrender lazily so the factory module is import
    time-cheap (pytest collection-safe).
    """
    name = director["name"]
    slug = _slug(name)
    t_total = time.monotonic()

    if skip_ppttc_build and pre_built_ppttc is not None:
        ppttc = pre_built_ppttc
    else:
        try:
            ppttc = _build_ppttc(name, period, template)
        except (RuntimeError, FileNotFoundError) as exc:
            return FactoryDirectorResult(
                director=name,
                slug=slug,
                ppttc_path=None,
                archived_pptx=None,
                elapsed_seconds=round(time.monotonic() - t_total, 3),
                binding_count=0,
                gate_passed=None,
                error=f"build_ppttc failed: {exc}",
                rendered=False,
            )

    bindings = _ppttc_binding_count(ppttc)

    # Lazy import: keeps this script import-cheap.
    from tcrender import (  # noqa: PLC0415 - intentional lazy import
        QualityGateError,
        SSHTransport,
        TcRenderClient,
    )
    from tcrender.models import RenderError as _RenderError  # noqa: PLC0415

    client = TcRenderClient(transport=SSHTransport(host=ssh_host))
    state_dir = REPO_ROOT / "state" / period / slug
    output_pptx = state_dir / f"{slug}-LAND-{period}.pptx"
    output_pptx.parent.mkdir(parents=True, exist_ok=True)

    archive_kwargs: dict[str, Any] = {}
    if archive:
        archive_kwargs.update(
            {
                "archive_to": archive_root or (REPO_ROOT / "state"),
                "archive_director": slug,
                "archive_period": period,
                "archive_audit": {
                    "fix_F_01": "fixed-2026-05-03",
                    "fix_F_02": "fixed-2026-05-03",
                    "factory_version": 1,
                },
            }
        )

    try:
        result = client.render(
            ppttc_path=ppttc,
            output_path=output_pptx,
            template_override=template,
            timeout=timeout,
            quality_gate=quality_gate,
            quality_gate_strict=quality_gate_strict,
            **archive_kwargs,
        )
    except QualityGateError as exc:
        return FactoryDirectorResult(
            director=name,
            slug=slug,
            ppttc_path=ppttc,
            archived_pptx=None,
            elapsed_seconds=round(time.monotonic() - t_total, 3),
            binding_count=bindings,
            gate_passed=False,
            error=str(exc),
            rendered=False,
        )
    except _RenderError as exc:
        return FactoryDirectorResult(
            director=name,
            slug=slug,
            ppttc_path=ppttc,
            archived_pptx=None,
            elapsed_seconds=round(time.monotonic() - t_total, 3),
            binding_count=bindings,
            gate_passed=None,
            error=f"render failed: {exc}",
            rendered=False,
        )

    archived = result.output_path if archive else None

    # Native-PPT fallback enhancement (optional). Runs against the archived
    # .pptx and produces a sibling enhanced.pptx in the same decks/<ts>/ dir.
    # The audit sidecar gains `enhanced_with_native_fallback: true` + the
    # list of bindings inserted.
    if native_fallback and archived is not None:
        try:
            from tcrender.native_fallback import (  # noqa: PLC0415
                enhance_deck,
            )

            enhanced_out = archived.parent / f"{archived.stem}-enhanced.pptx"
            enh_result = enhance_deck(
                deck_path=archived,
                ppttc_path=ppttc,
                output_path=enhanced_out,
            )
            # Update audit.json with enhancement metadata.
            audit_path = archived.parent / "audit.json"
            if audit_path.exists():
                try:
                    audit_payload = json.loads(audit_path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    audit_payload = {}
                audit_payload["enhanced_with_native_fallback"] = True
                audit_payload["enhanced_path"] = str(enh_result.enhanced_path)
                audit_payload["enhanced_bindings_inserted"] = list(enh_result.bindings_inserted)
                audit_payload["enhanced_skipped"] = [
                    {"binding": n, "reason": r} for n, r in enh_result.skipped
                ]
                audit_path.write_text(
                    json.dumps(audit_payload, indent=2, sort_keys=True, ensure_ascii=True),
                    encoding="utf-8",
                )
        except Exception as exc:  # noqa: BLE001 - enhancement is best-effort
            print(
                f"[factory] native-fallback enhancement failed for {name}: {exc}",
                file=sys.stderr,
            )

    # Image-charts pass (default ON for production). Runs against the most
    # recent deck on disk for this director (enhanced > archived) and writes
    # ``<archived stem>-image-charts.pptx``. Replaces native chart shapes
    # from native_fallback with PNG-rendered consulting-grade matplotlib
    # charts (SimCorp brand palette, no chart-junk, EUR M labels). Native
    # tables produced by native_fallback (S07/S08/S09/S11/S22/S24/S26)
    # remain untouched. Audit sidecar gains ``image_charts_applied: true``
    # + the list of bindings rendered as images.
    if image_charts and archived is not None:
        try:
            from tcrender.image_charts import (  # noqa: PLC0415
                enhance_deck_with_images,
            )

            audit_path = archived.parent / "audit.json"
            ic_input: Path = archived
            if audit_path.exists():
                try:
                    audit_payload = json.loads(audit_path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    audit_payload = {}
                ep = audit_payload.get("enhanced_path")
                if isinstance(ep, str) and Path(ep).exists():
                    ic_input = Path(ep)
            ic_out = archived.parent / f"{archived.stem}-image-charts.pptx"
            ic_result = enhance_deck_with_images(
                deck_path=ic_input,
                ppttc_path=ppttc,
                output_path=ic_out,
            )
            if audit_path.exists():
                try:
                    audit_payload = json.loads(audit_path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    audit_payload = {}
                audit_payload["image_charts_applied"] = True
                audit_payload["image_charts_output_path"] = str(ic_result.enhanced_path)
                audit_payload["image_charts_bindings_rendered"] = list(ic_result.bindings_rendered)
                audit_payload["image_charts_skipped"] = [
                    {"binding": n, "reason": r} for n, r in ic_result.skipped
                ]
                audit_path.write_text(
                    json.dumps(audit_payload, indent=2, sort_keys=True, ensure_ascii=True),
                    encoding="utf-8",
                )
        except Exception as exc:  # noqa: BLE001 - image-charts is best-effort
            print(
                f"[factory] image-charts enhancement failed for {name}: {exc}",
                file=sys.stderr,
            )

    # Polish-pass (optional). Runs against the enhanced .pptx if present,
    # falling back to the archived raw .pptx otherwise. Output: sibling
    # ``<archived stem>-final.pptx``. Audit sidecar gains
    # ``polish_pass_applied: true`` + the list of fixes applied.
    if polish_pass_enabled and archived is not None:
        try:
            from tcrender.polish_pass import polish_pass  # noqa: PLC0415

            audit_path = archived.parent / "audit.json"
            enhanced_path: Path | None = None
            if audit_path.exists():
                try:
                    audit_payload = json.loads(audit_path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    audit_payload = {}
                ep = audit_payload.get("enhanced_path")
                if isinstance(ep, str) and Path(ep).exists():
                    enhanced_path = Path(ep)
            polish_input = enhanced_path if enhanced_path is not None else archived
            polish_out = archived.parent / f"{archived.stem}-final.pptx"
            scope_label = director.get("scope_label") or ""
            pp_result = polish_pass(
                deck_path=polish_input,
                output_path=polish_out,
                director_name=name,
                period=period,
                scope_label=scope_label,
            )
            if audit_path.exists():
                try:
                    audit_payload = json.loads(audit_path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    audit_payload = {}
                audit_payload["polish_pass_applied"] = True
                audit_payload["polish_pass_output_path"] = str(pp_result.output_path)
                audit_payload["polish_pass_fixes_applied"] = list(pp_result.fixes_applied)
                audit_payload["polish_pass_skipped"] = [
                    {"name": n, "reason": r} for n, r in pp_result.skipped
                ]
                audit_payload["polish_pass_slide_count_before"] = pp_result.original_slide_count
                audit_payload["polish_pass_slide_count_after"] = pp_result.polished_slide_count
                audit_path.write_text(
                    json.dumps(audit_payload, indent=2, sort_keys=True, ensure_ascii=True),
                    encoding="utf-8",
                )
        except Exception as exc:  # noqa: BLE001 - polish is best-effort
            print(
                f"[factory] polish-pass failed for {name}: {exc}",
                file=sys.stderr,
            )

    elapsed = round(time.monotonic() - t_total, 3)
    return FactoryDirectorResult(
        director=name,
        slug=slug,
        ppttc_path=ppttc,
        archived_pptx=archived,
        elapsed_seconds=elapsed,
        binding_count=bindings,
        gate_passed=True if quality_gate else None,
        error=None,
        rendered=True,
    )


# -- top-level factory loop -----------------------------------------------


def run_factory(
    *,
    period: str,
    directors: list[dict[str, Any]],
    template: Path,
    archive: bool,
    quality_gate: bool,
    strict_gate: bool,
    archive_root: Path | None,
    ssh_host: str,
    timeout: float,
    progress: bool = True,
    native_fallback: bool = False,
    polish_pass_enabled: bool = False,
    image_charts: bool = True,
) -> FactorySummary:
    """Run the full factory loop over a list of directors."""
    summary = FactorySummary(period=period, template=template)
    n = len(directors)
    for i, director in enumerate(directors, start=1):
        prefix = f"[{i}/{n}] {director['name']}"
        if progress:
            print(f"{prefix}: building...", flush=True)
        r = render_one_director(
            director,
            period=period,
            template=template,
            archive=archive,
            quality_gate=quality_gate,
            quality_gate_strict=strict_gate,
            archive_root=archive_root,
            ssh_host=ssh_host,
            timeout=timeout,
            native_fallback=native_fallback,
            polish_pass_enabled=polish_pass_enabled,
            image_charts=image_charts,
        )
        summary.results.append(r)
        if progress:
            print(_format_progress_line(prefix, r), flush=True)
    return summary


def _format_progress_line(prefix: str, r: FactoryDirectorResult) -> str:
    if r.error:
        return f"{prefix}: ERROR ({r.elapsed_seconds}s) -- {r.error[:160]}"
    bits = [f"ppttc built ({r.binding_count} bindings)"]
    if r.rendered:
        bits.append(f"render {r.elapsed_seconds}s")
        if r.archived_pptx:
            bits.append("archived")
    if r.gate_passed is True:
        bits.append("gate PASSED")
    elif r.gate_passed is False:
        bits.append("gate FAILED")
    return f"{prefix}: " + " -> ".join(bits)


# -- CLI -------------------------------------------------------------------


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="factory",
        description=("LAND deck factory: build .ppttc + render + archive for 1..9 directors."),
    )
    p.add_argument("--period", default=DEFAULT_PERIOD, help="Quarter label, e.g. 2026-Q2.")
    p.add_argument(
        "--directors",
        default="all",
        help=(
            "'all' (default) or comma-separated director names/slugs "
            "(e.g. 'Jesper-Tyrer,Sarah-Pittroff')."
        ),
    )
    p.add_argument(
        "--template",
        type=Path,
        default=DEFAULT_TEMPLATE,
        help=f"Donor .pptx template (default: {DEFAULT_TEMPLATE.relative_to(REPO_ROOT)}).",
    )
    p.add_argument(
        "--archive-root",
        type=Path,
        default=None,
        help="Override archive root (default: <repo>/state).",
    )
    p.add_argument("--no-archive", action="store_true", help="Skip archival step.")
    p.add_argument(
        "--quality-gate",
        action="store_true",
        help="Run the quality gate (verify + jinja-leak + completeness).",
    )
    p.add_argument(
        "--strict-gate",
        action="store_true",
        help="Raise QualityGateError on gate failure (implies --quality-gate).",
    )
    p.add_argument("--ssh-host", default="Windows-VM", help="SSH config alias for ppttc.exe host.")
    p.add_argument("--timeout", type=float, default=240.0, help="Per-render wall-clock cap (s).")
    nf = p.add_mutually_exclusive_group()
    nf.add_argument(
        "--native-fallback",
        dest="native_fallback",
        action="store_true",
        default=True,
        help=(
            "After archival, run the native-PPT fallback enhancer "
            "(tcrender.native_fallback.enhance_deck) and write a sibling "
            "<archived>-enhanced.pptx with native chart/table shapes "
            "populated from the .ppttc bindings. ON by default; "
            "the only thing rendering chart data on chart slides."
        ),
    )
    nf.add_argument(
        "--no-native-fallback",
        dest="native_fallback",
        action="store_false",
        help="Disable native-fallback enhancement (default ON).",
    )
    p.add_argument(
        "--experimental-polish-pass",
        dest="polish_pass",
        action="store_true",
        help=(
            "EXPERIMENTAL / OPT-IN. After native-fallback, run the "
            "polish-pass (tcrender.polish_pass.polish_pass) and write a "
            "sibling <archived>-final.pptx. Currently produces visible "
            "quality bugs (black-fill PolishPassNakedTitle/Subtitle "
            "boxes, oversized PolishPassCoverNavyStripe, Sarah-master "
            "Lorem ipsum leftover). DO NOT enable for SHIP outputs."
        ),
    )
    ic = p.add_mutually_exclusive_group()
    ic.add_argument(
        "--image-charts",
        dest="image_charts",
        action="store_true",
        default=True,
        help=(
            "After native-fallback, run the consulting-grade image-chart "
            "renderer (tcrender.image_charts.enhance_deck_with_images) "
            "and write a sibling <archived>-image-charts.pptx. Replaces "
            "Office-default native python-pptx charts with matplotlib "
            "PNGs in the SimCorp brand palette (matches Andre's prior "
            "shipped LAND deck pattern: 0 native charts, 17 embedded "
            "images per director). ON by default for production."
        ),
    )
    ic.add_argument(
        "--no-image-charts",
        dest="image_charts",
        action="store_false",
        help="Disable image-charts pass (default ON).",
    )
    p.add_argument(
        "--print-default-template",
        action="store_true",
        help="Print the canonical default template path and exit.",
    )
    p.add_argument(
        "--allow-legacy-seed",
        action="store_true",
        help=(
            "Allow legacy debris seed paths. Required if --template points at "
            "assets/LAND_thinkcell_seed*, assets/legacy/, or any quarantined "
            "asset. Use only for forensic comparison."
        ),
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help=(
            "Resolve directors + template path and print the plan without "
            "building any .ppttc or rendering. Does not require the template "
            "file to exist."
        ),
    )
    return p.parse_args(argv)


def _print_summary_table(summary: FactorySummary) -> None:
    print()
    print("=" * 78)
    print(f"Factory summary -- period={summary.period} template={summary.template.name}")
    print("=" * 78)
    print(
        f"{'#':>2} {'Director':<22} {'Bindings':>8} {'Elapsed':>8} "
        f"{'Gate':<8} {'Status':<6} {'Output'}"
    )
    print("-" * 78)
    for i, r in enumerate(summary.results, start=1):
        gate = (
            "PASSED" if r.gate_passed is True else "FAILED" if r.gate_passed is False else "(off)"
        )
        status = "OK" if r.ok else "FAIL"
        out = (
            str(r.archived_pptx.relative_to(REPO_ROOT))
            if r.archived_pptx and r.archived_pptx.is_relative_to(REPO_ROOT)
            else (str(r.archived_pptx) if r.archived_pptx else "-")
        )
        print(
            f"{i:>2} {r.director:<22} {r.binding_count:>8} "
            f"{r.elapsed_seconds:>8.2f} {gate:<8} {status:<6} {out}"
        )
        if r.error:
            print(f"   ! {r.error[:200]}")
    print("-" * 78)
    print(f"Passed: {summary.passed_count}/{len(summary.results)} | All OK: {summary.all_ok}")


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)

    if args.print_default_template:
        print(DEFAULT_TEMPLATE)
        return 0

    template = args.template.expanduser().resolve()

    if _is_legacy_template(template) and not args.allow_legacy_seed:
        sys.stderr.write(
            f"refusing to use quarantined/legacy template: {template}\n"
            "pass --allow-legacy-seed for forensic-only override.\n"
        )
        return 2

    if not args.dry_run and not template.exists():
        print(f"[factory] template not found: {template}", file=sys.stderr)
        return 2

    quality_gate = args.quality_gate or args.strict_gate
    archive = not args.no_archive

    try:
        directors = _resolve_directors(args.directors)
    except SystemExit as exc:
        print(f"[factory] {exc}", file=sys.stderr)
        return 2

    if args.dry_run:
        print(f"[factory] dry-run period={args.period} template={template}")
        print(f"[factory] directors ({len(directors)}):")
        for d in directors:
            print(f"  - {d['name']}")
        return 0

    summary = run_factory(
        period=args.period,
        directors=directors,
        template=template,
        archive=archive,
        quality_gate=quality_gate,
        strict_gate=args.strict_gate,
        archive_root=args.archive_root,
        ssh_host=args.ssh_host,
        timeout=args.timeout,
        progress=True,
        native_fallback=args.native_fallback,
        polish_pass_enabled=args.polish_pass,
        image_charts=args.image_charts,
    )

    _print_summary_table(summary)

    if args.strict_gate and not summary.all_ok:
        return 1
    if not summary.all_ok and not args.strict_gate:
        # Soft mode: surface a non-zero exit but distinguish strict vs soft.
        return 0 if summary.passed_count > 0 else 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
