#!/usr/bin/env python3
"""Run the repeatable SimCorp think-cell programmatic automation lab.

The lab separates what can be automated safely from what must stay manual or
donor-based:

- macOS builds/verifies strict `.ppttc` payloads and OpenXML donor contracts.
- the Parallels Windows VM runs real PowerPoint/Excel/think-cell probes.
- `ppttc.exe` updates already-named native think-cell chart/text elements.
- Excel COM `AddRangeImage` remains the production lane for table images.
"""

from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import re
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from itertools import chain
from pathlib import Path
from typing import Any
from zipfile import ZipFile

from _directors import canonical_directors
from build_table_image_donors import TABLE_IMAGE_TARGETS as TABLE_IMAGE_DONOR_NAMES
from build_thinkcell_seed_template import (
    CHART_DONORS,
    TABLE_STUB_NAMES_BY_SLIDE,
    TEXT_FIELD_NAMES_BY_SLIDE,
)
from ppttc_template import template_named_elements


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PERIOD = "2026-Q2"
DEFAULT_HOST = "Windows-VM"
DEFAULT_DIRECTOR_SLUG = "Jesper-Tyrer"
SEED_TEMPLATE = ROOT / "assets" / "LAND_thinkcell_seed.pptx"
PROBE_PS1 = ROOT / "scripts" / "thinkcell_programmatic_probe.ps1"

OFFICIAL_API_CONTRACT: dict[str, Any] = {
    "schema": "thinkcell-official-api-contract/v1",
    "manual_urls": {
        "api": "https://www.think-cell.com/en/resources/manual/api",
        "excel_data_automation": "https://www.think-cell.com/en/resources/manual/exceldataautomation",
        "json_data_automation": "https://www.think-cell.com/en/resources/manual/jsondataautomation",
    },
    "platform": [
        "Windows-only; the API is exposed through Office COM add-ins.",
        "Calls are late-bound; no think-cell type library is registered.",
        "Office Web Add-ins cannot use this API because they cannot interact with Office COM add-ins.",
    ],
    "entry_points": {
        "powerpoint": 'Application.COMAddIns("thinkcell.addin").Object  # tcPpAddIn',
        "excel": 'Application.COMAddIns("thinkcell.addin").Object  # tcXlAddIn',
    },
    "excel_data_automation": {
        "tcXlAddIn": [
            {
                "name": "PresentationFromTemplate",
                "purpose": "Open a presentation from a think-cell template; not yet exercised by the SimCorp pipeline.",
            },
            {
                "name": "UpdateChart",
                "purpose": "Deprecated single-chart update; do not invoke. Use UpdateBatch instead.",
                "deprecated": True,
            },
            {
                "name": "CreateUpdate",
                "purpose": "Returns a tcUpdate object that batches AddRangeData and AddRangeImage calls.",
            },
        ],
        "tcUpdate": [
            {
                "name": "AddRangeData(Target, Name, Range, Transposed)",
                "purpose": "Bind an Excel range as datasheet content for a named chart/table element.",
            },
            {
                "name": "AddRangeImage(Target, Name, Range)",
                "purpose": "Bind an Excel range as an image into a named element. Only available through UpdateBatch.",
            },
            {
                "name": "Send()",
                "purpose": "Commits the queued AddRangeData/AddRangeImage updates to PowerPoint.",
            },
        ],
        "target_enum": [
            "Presentation",
            "SlideRange",
            "Slide",
            "Master",
            "CustomLayout",
        ],
        "name_resolution": [
            "Name must already exist in the PowerPoint template as an AddRangeData or AddRangeImage name.",
            "Names are case-insensitive.",
            "If the same name appears multiple times, all matching elements receive the same data.",
        ],
        "transposed_semantics": [
            "Standard charts: swaps series and categories.",
            "Tables: swaps row and column layout.",
            "Gantt/timeline: swaps activities and anchor points.",
            "Scatter/bubble: swaps data points and dimensions.",
        ],
    },
    "powerpoint_api": [
        "Style files: LoadStyle, LoadStyleForRegion, GetStyleName, RemoveStyles.",
        "Mekko Graphics: ImportMekkoGraphicsCharts, GetMekkoGraphicsXML.",
        "Update lane: PresentationFromTemplateStep3, UpdateChartStep3, UpdateBatchStep3 (used internally; ppttc.exe is the preferred wrapper).",
        "UI-only: ShowChartGallery, StartTableInsertion (not headless creation methods).",
    ],
    "json_data_automation": {
        "ppttc_shape": "Array of template objects; each has 'template' (path or URL) and 'data' (array of {name, table}).",
        "table_rules": [
            "First row is categories with a leading null cell (the corner).",
            "Subsequent rows carry series labels in the first column then values.",
            "Empty row [] suppresses a series and shifts colors.",
        ],
        "cell_types": [
            "string",
            "number",
            "date (YYYY-MM-DD)",
            "percentage (numeric, no % sign)",
            "fill (hex/RGB; pair with value cell, never replace)",
            "null",
        ],
    },
}

CAPABILITY_VERDICT_ORDER = [
    "ppttc_exe_template_update",
    "excel_create_update",
    "excel_addrangedata",
    "excel_addrangeimage",
    "excel_send",
    "excel_presentation_from_template",
    "excel_update_chart_deprecated",
    "powerpoint_update_batch_step3",
    "powerpoint_update_chart_step3",
    "powerpoint_presentation_from_template_step3",
    "powerpoint_load_style",
    "powerpoint_load_style_for_region",
    "powerpoint_get_style_name",
    "powerpoint_remove_styles",
    "powerpoint_import_mekko_graphics",
    "powerpoint_get_mekko_graphics_xml",
    "powerpoint_show_chart_gallery",
    "powerpoint_start_table_insertion",
    "programmatic_chart_creation",
    "native_editable_thinkcell_tables",
    "web_addin_path",
    "tcserver_http_service",
]

SOURCE_MAP_DOC = "docs/thinkcell-corpus/automation-api-source-map.md"

OBSERVED_NOT_PRODUCTION_STOP_CONDITION = (
    "Observed-uninvoked methods are not production support: do not adopt them in a "
    "factory build until a proof lane (donor template + named element + bound output + "
    "rendered assertion) exists for that specific method."
)


@dataclass
class LabCheck:
    name: str
    status: str
    details: dict[str, Any] = field(default_factory=dict)


def _python() -> str:
    venv = ROOT / ".venv" / "bin" / "python"
    return str(venv) if venv.exists() else sys.executable


def _slug(value: str) -> str:
    return value.replace(" ", "-")


def _director_by_slug(slug: str) -> dict[str, Any]:
    for director in canonical_directors():
        if _slug(str(director["name"])) == slug:
            return director
    raise SystemExit(f"unknown director slug: {slug}")


def _selected_directors(args: argparse.Namespace) -> list[dict[str, Any]]:
    if args.all_directors:
        return canonical_directors()
    return [_director_by_slug(args.director_slug)]


def _to_unc(path: Path) -> str:
    resolved = path.expanduser().resolve()
    home = Path.home().resolve()
    rel = resolved.relative_to(home)
    return r"\\Mac\Home" + "\\" + "\\".join(rel.parts)


def _run(
    command: list[str],
    *,
    check: bool = False,
    timeout: int | None = None,
) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        command,
        cwd=ROOT,
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
    )
    if check and completed.returncode != 0:
        sys.stderr.write(completed.stdout)
        sys.stderr.write(completed.stderr)
        raise SystemExit(completed.returncode)
    return completed


def _vm_status() -> dict[str, Any]:
    result = _run(["prlctl", "list", "--all"], timeout=20)
    if result.returncode != 0:
        return {"status": "unknown", "stdout": result.stdout, "stderr": result.stderr}
    rows = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    running = any("Windows 11" in row and "running" in row for row in rows)
    return {
        "status": "running" if running else "not_running",
        "stdout": result.stdout,
    }


def _vm_status_check() -> LabCheck:
    status = _vm_status()
    return LabCheck(
        "parallels_vm_status",
        "pass" if status.get("status") == "running" else "fail",
        status,
    )


def _run_windows_probe(host: str) -> tuple[dict[str, Any] | None, LabCheck]:
    command = [
        "ssh",
        "-o",
        "BatchMode=yes",
        "-o",
        "ConnectTimeout=8",
        host,
        f'powershell -NoProfile -ExecutionPolicy Bypass -File "{_to_unc(PROBE_PS1)}"',
    ]
    result = _run(command, timeout=120)
    details = {
        "returncode": result.returncode,
        "stdout_tail": result.stdout[-4000:],
        "stderr_tail": result.stderr[-4000:],
    }
    if result.returncode != 0:
        return None, LabCheck("windows_com_probe", "fail", details)

    json_lines = [
        line.strip() for line in result.stdout.splitlines() if line.strip().startswith("{")
    ]
    if not json_lines:
        return None, LabCheck(
            "windows_com_probe", "fail", details | {"error": "no JSON object in probe output"}
        )

    try:
        probe = json.loads(json_lines[-1])
    except json.JSONDecodeError as exc:
        return None, LabCheck("windows_com_probe", "fail", details | {"error": str(exc)})

    caps = probe.get("capabilities", {})
    expected_caps = {
        "ppttc_template_update": True,
        "powerpoint_update_batch_step3": True,
        "excel_add_range_image": True,
        "programmatic_create_chart": False,
    }
    mismatches = {
        key: {"expected": expected, "actual": caps.get(key)}
        for key, expected in expected_caps.items()
        if caps.get(key) != expected
    }
    status = "pass" if not mismatches else "warn"
    return probe, LabCheck(
        "windows_com_probe",
        status,
        {
            "machine": probe.get("machine", {}),
            "thinkcell": probe.get("thinkcell", {}),
            "capability_mismatches": mismatches,
            "capabilities": caps,
            "errors": probe.get("errors", []),
        },
    )


def _expected_seed_names() -> set[str]:
    names = {spec.name for spec in CHART_DONORS}
    names.update(chain.from_iterable(TEXT_FIELD_NAMES_BY_SLIDE.values()))
    names.update(chain.from_iterable(TABLE_STUB_NAMES_BY_SLIDE.values()))
    return names


def _validate_seed_template() -> LabCheck:
    expected = _expected_seed_names()
    if not SEED_TEMPLATE.exists():
        return LabCheck("seed_template_contract", "fail", {"missing_template": str(SEED_TEMPLATE)})
    names = set(template_named_elements(SEED_TEMPLATE))
    missing = sorted(expected - names)
    extra = sorted(names - expected)
    return LabCheck(
        "seed_template_contract",
        "pass" if not missing else "fail",
        {
            "template": str(SEED_TEMPLATE),
            "expected_names": len(expected),
            "actual_names": len(names),
            "missing": missing,
            "extra": extra,
            "chart_names": len(CHART_DONORS),
            "text_names": sum(len(items) for items in TEXT_FIELD_NAMES_BY_SLIDE.values()),
            "table_stub_names": sum(len(items) for items in TABLE_STUB_NAMES_BY_SLIDE.values()),
        },
    )


def _validate_table_image_donors() -> LabCheck:
    donor_dir = ROOT / "state" / "thinkcell_bridge" / "table_image_donors"
    missing: list[str] = []
    bad: dict[str, list[str]] = {}
    good = 0
    for name in TABLE_IMAGE_DONOR_NAMES:
        path = donor_dir / f"{name}.pptx"
        if not path.exists():
            missing.append(name)
            continue
        names = sorted(template_named_elements(path))
        if name not in names:
            bad[name] = names
            continue
        good += 1
    status = "pass" if not missing and not bad else "fail"
    return LabCheck(
        "table_image_donor_contract",
        status,
        {
            "donor_dir": str(donor_dir),
            "expected_donors": len(TABLE_IMAGE_DONOR_NAMES),
            "valid_donors": good,
            "missing": missing,
            "bad": bad,
        },
    )


def _load_optional_json(path: Path) -> Any | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _salesforce_intel_context(
    *,
    period: str,
    directors: list[dict[str, Any]],
) -> tuple[dict[str, Any], LabCheck]:
    slugs = {_slug(str(director["name"])) for director in directors}
    director_names = {str(director["name"]) for director in directors}
    regional_dir = ROOT / "state" / period / "__regional__"
    fit_path = regional_dir / "thinkcell_sf_fit" / "thinkcell_quarter_salesforce_fit.json"
    smoke_path = regional_dir / "meeting_spine" / "meeting_spine_smoke_report.json"
    goal_path = regional_dir / "goal_audit" / "regional_deck_goal_audit.json"

    fit = _load_optional_json(fit_path)
    smoke = _load_optional_json(smoke_path)
    goal = _load_optional_json(goal_path)

    fit_directors: list[dict[str, Any]] = []
    if fit:
        for row in fit.get("directors", []):
            if row.get("director") not in director_names:
                continue
            visual_fit = row.get("visual_fit", {})
            fit_directors.append(
                {
                    "director": row.get("director"),
                    "territory": row.get("territory"),
                    "q2_open_arr_count": row.get("q2_open_arr_count"),
                    "q2_open_arr_eur": row.get("q2_open_arr_eur"),
                    "q2_open_renewal_count": row.get("q2_open_renewal_count"),
                    "q2_open_renewal_acv_eur": row.get("q2_open_renewal_acv_eur"),
                    "fy26_open_renewal_count": row.get("fy26_open_renewal_count"),
                    "fy26_open_renewal_acv_eur": row.get("fy26_open_renewal_acv_eur"),
                    "internal_rows_removed": row.get("internal_rows_removed"),
                    "chart_gates": {
                        "bar_column": _eligible_value(visual_fit.get("bar_column")),
                        "scatter_bubble": _eligible_value(visual_fit.get("scatter_bubble")),
                        "timeline_gantt_q2_renewals": (
                            visual_fit.get("timeline_gantt", {}).get("eligible_for_q2_renewals")
                            if isinstance(visual_fit.get("timeline_gantt"), dict)
                            else None
                        ),
                        "timeline_gantt_fy26_renewals": (
                            visual_fit.get("timeline_gantt", {}).get("eligible_for_fy26_renewals")
                            if isinstance(visual_fit.get("timeline_gantt"), dict)
                            else None
                        ),
                        "mekko": _eligible_value(visual_fit.get("mekko")),
                        "gantt_from_actions": (
                            visual_fit.get("action_register", {}).get(
                                "gantt_eligible_from_salesforce"
                            )
                            if isinstance(visual_fit.get("action_register"), dict)
                            else None
                        ),
                    },
                }
            )

    specs: list[dict[str, Any]] = []
    for director in directors:
        slug = _slug(str(director["name"]))
        path = ROOT / "state" / period / slug / "factory" / "regional_intelligence_spec.json"
        spec = _load_optional_json(path)
        if spec is None:
            specs.append({"slug": slug, "path": str(path), "status": "missing"})
            continue
        actions = spec.get("first_two_week_actions", [])
        specs.append(
            {
                "slug": slug,
                "path": str(path),
                "status": spec.get("status"),
                "source_gaps": spec.get("source_gaps", []),
                "metric_contract": spec.get("metric_contract", {}),
                "current_may_orientation": spec.get("current_may_orientation", {}),
                "first_two_week_actions": actions[:4] if isinstance(actions, list) else [],
                "deck_injection_target_count": len(spec.get("deck_injection_targets", []))
                if isinstance(spec.get("deck_injection_targets"), list)
                else None,
            }
        )

    smoke_rows = []
    if smoke:
        for row in smoke.get("results", []):
            if row.get("slug") in slugs:
                smoke_rows.append(row)

    goal_rows = []
    if isinstance(goal, list):
        for row in goal:
            if row.get("slug") in slugs:
                goal_rows.append(
                    {
                        "director": row.get("director"),
                        "slug": row.get("slug"),
                        "status": row.get("status"),
                        "residual_risks": row.get("residual_risks", []),
                        "artifacts": row.get("artifacts", {}),
                    }
                )

    context = {
        "fit_path": str(fit_path),
        "fit_totals": (fit or {}).get("totals", {}),
        "family_eligibility_counts": (fit or {}).get("family_eligibility_counts", {}),
        "fit_directors": fit_directors,
        "regional_intelligence_specs": specs,
        "meeting_spine_smoke_path": str(smoke_path),
        "meeting_spine_smoke_status": (smoke or {}).get("status"),
        "meeting_spine_smoke_rows": smoke_rows,
        "goal_audit_path": str(goal_path),
        "goal_audit_rows": goal_rows,
    }
    problems = []
    if not fit:
        problems.append("missing Salesforce think-cell fit JSON")
    if len(fit_directors) != len(directors):
        problems.append("missing selected director rows in Salesforce fit JSON")
    if any(row.get("status") != "pass" for row in specs):
        problems.append("one or more regional intelligence specs are missing or not pass")
    if smoke and any(row.get("status") != "pass" for row in smoke_rows):
        problems.append("one or more meeting spine smoke rows are not pass")
    if isinstance(goal, list) and any(row.get("status") != "pass" for row in goal_rows):
        problems.append("one or more regional goal audit rows are not pass")

    return context, LabCheck(
        "salesforce_intel_context",
        "pass" if not problems else "fail",
        {
            "problems": problems,
            "q2_rows": context["fit_totals"].get("q2_publishable_rows"),
            "removed_internal_rows": context["fit_totals"].get("q2_internal_rows_removed"),
            "family_eligibility_counts": context["family_eligibility_counts"],
            "spec_statuses": {row["slug"]: row.get("status") for row in specs},
            "meeting_smoke": {row.get("slug"): row.get("status") for row in smoke_rows},
            "goal_audit": {row.get("slug"): row.get("status") for row in goal_rows},
        },
    )


def _eligible_value(value: Any) -> Any:
    if isinstance(value, dict):
        return value.get("eligible")
    return value


def _ppttc_path(period: str, director_slug: str) -> Path:
    return ROOT / "state" / period / director_slug / f"{director_slug}-LAND-{period}.ppttc"


def _build_ppttc(period: str, directors: list[dict[str, Any]]) -> LabCheck:
    if len(directors) == len(canonical_directors()):
        command = [
            _python(),
            "scripts/build_ppttc.py",
            "--all-directors",
            "--period",
            period,
            "--template",
            str(SEED_TEMPLATE),
            "--strict-template",
        ]
    else:
        command = [
            _python(),
            "scripts/build_ppttc.py",
            "--director",
            str(directors[0]["name"]),
            "--period",
            period,
            "--template",
            str(SEED_TEMPLATE),
            "--strict-template",
        ]
    result = _run(command, timeout=300)
    details: dict[str, Any] = {
        "command": command,
        "returncode": result.returncode,
        "stdout_tail": result.stdout[-4000:],
        "stderr_tail": result.stderr[-4000:],
    }
    if result.returncode != 0:
        return LabCheck("ppttc_strict_build", "fail", details)

    expected = _expected_seed_names()
    per_director = []
    for director in directors:
        slug = _slug(str(director["name"]))
        path = _ppttc_path(period, slug)
        names = _ppttc_data_names(path)
        per_director.append(
            {
                "slug": slug,
                "ppttc": str(path),
                "entry_count": len(names),
                "missing_seed_names": sorted(expected - names),
                "extra_names": sorted(names - expected),
            }
        )
    failures = [row for row in per_director if row["missing_seed_names"]]
    return LabCheck(
        "ppttc_strict_build",
        "pass" if not failures else "fail",
        details | {"directors": per_director},
    )


def _ppttc_data_names(path: Path) -> set[str]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        data = payload[0].get("data", [])
    else:
        data = payload.get("data", [])
    return {str(item.get("name")) for item in data if item.get("name")}


def _ppttc_expect_texts(path: Path, *, director_name: str, period: str) -> list[str]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        data = payload[0].get("data", [])
    else:
        data = payload.get("data", [])
    expect = [director_name, period]
    for item in data:
        if item.get("name") != "S04_PipeMovement":
            continue
        for row in item.get("table", []):
            for cell in row:
                if isinstance(cell, dict) and cell.get("string"):
                    text = str(cell["string"])
                    if "Opening pipe" in text:
                        expect.append(text)
                        return expect
    return expect


def _run_ppttc_bridge(
    *,
    period: str,
    director: dict[str, Any],
    host: str,
    out_dir: Path,
) -> tuple[Path | None, LabCheck]:
    slug = _slug(str(director["name"]))
    ppttc = _ppttc_path(period, slug)
    output = out_dir / "ppttc_bridge" / f"{slug}-seed-bound.pptx"
    output.parent.mkdir(parents=True, exist_ok=True)
    expect_texts = _ppttc_expect_texts(ppttc, director_name=str(director["name"]), period=period)
    command = [
        _python(),
        "scripts/run_thinkcell_windows_bridge.py",
        "--host",
        host,
        "--ppttc",
        str(ppttc),
        "--template",
        str(SEED_TEMPLATE),
        "--output",
        str(output),
    ]
    for text in expect_texts:
        command.extend(["--expect-text", text])
    result = _run(command, timeout=240)
    details: dict[str, Any] = {
        "command": command,
        "returncode": result.returncode,
        "stdout_tail": result.stdout[-4000:],
        "stderr_tail": result.stderr[-4000:],
        "output": str(output),
        "expect_texts": expect_texts,
    }
    if result.returncode != 0 or not output.exists() or output.stat().st_size == 0:
        return None, LabCheck("windows_ppttc_bridge", "fail", details)
    proof = _pptx_package_summary(output, expect_texts=expect_texts)
    status = "pass" if not proof["missing_expected_text"] else "fail"
    return output, LabCheck("windows_ppttc_bridge", status, details | proof)


def _pptx_package_summary(path: Path, *, expect_texts: list[str]) -> dict[str, Any]:
    with ZipFile(path) as zf:
        names = zf.namelist()
        slide_parts = [
            name for name in names if name.startswith("ppt/slides/slide") and name.endswith(".xml")
        ]
        embeddings = [name for name in names if name.startswith("ppt/embeddings/")]
        text = html.unescape(
            "\n".join(zf.read(name).decode("utf-8", "ignore") for name in slide_parts)
        )
    return {
        "size_bytes": path.stat().st_size,
        "slide_count": len(slide_parts),
        "embedding_count": len(embeddings),
        "named_element_count": len(template_named_elements(path)),
        "missing_expected_text": [needle for needle in expect_texts if needle not in text],
    }


def _render_pptx(path: Path, out_dir: Path) -> LabCheck:
    soffice = shutil.which("soffice")
    if soffice is None:
        mac_soffice = Path("/Applications/LibreOffice.app/Contents/MacOS/soffice")
        soffice = str(mac_soffice) if mac_soffice.exists() else None
    pdftoppm = shutil.which("pdftoppm")
    if soffice is None or pdftoppm is None:
        return LabCheck(
            "bridge_render_smoke",
            "skip",
            {"reason": "missing soffice or pdftoppm", "soffice": soffice, "pdftoppm": pdftoppm},
        )
    render_dir = out_dir / "render"
    render_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = render_dir / f"{path.stem}.pdf"
    convert = _run(
        [
            soffice,
            "--headless",
            "--convert-to",
            "pdf",
            "--outdir",
            str(render_dir),
            str(path),
        ],
        timeout=180,
    )
    if convert.returncode != 0 or not pdf_path.exists():
        return LabCheck(
            "bridge_render_smoke",
            "fail",
            {
                "convert_returncode": convert.returncode,
                "stdout_tail": convert.stdout[-2000:],
                "stderr_tail": convert.stderr[-2000:],
                "expected_pdf": str(pdf_path),
            },
        )
    raster = _run(
        [pdftoppm, "-png", "-r", "120", str(pdf_path), str(render_dir / "slide")], timeout=180
    )
    pngs = sorted(render_dir.glob("slide-*.png"))
    return LabCheck(
        "bridge_render_smoke",
        "pass" if raster.returncode == 0 and pngs else "fail",
        {
            "pdf": str(pdf_path),
            "png_count": len(pngs),
            "first_png": str(pngs[0]) if pngs else None,
            "pdftoppm_returncode": raster.returncode,
            "stdout_tail": raster.stdout[-2000:],
            "stderr_tail": raster.stderr[-2000:],
        },
    )


def _summarize_install_inventory(probe: dict[str, Any] | None) -> dict[str, Any]:
    if not probe:
        return {}
    inv = probe.get("install_inventory") or {}
    if not inv:
        return {}
    summary: dict[str, Any] = {}
    for key in ("install_root", "ppttc", "templates", "manual", "xml_schemas"):
        folder = inv.get(key) or {}
        if not folder:
            continue
        summary[key] = {
            "path": folder.get("path"),
            "present": folder.get("present"),
            "file_count": folder.get("file_count"),
            "dir_count": folder.get("dir_count"),
            "sample_files": folder.get("sample_files", [])[:6],
            "sample_dirs": folder.get("sample_dirs", [])[:6],
        }
    for key in ("ppttc_schema_json", "sample_template_pptx", "sample_ppttc"):
        item = inv.get(key) or {}
        if item:
            summary[key] = {"path": item.get("path"), "present": item.get("present")}
    return summary


def _summarize_api_surface(probe: dict[str, Any] | None) -> dict[str, Any]:
    if not probe:
        return {}
    surface = probe.get("api_surface") or {}
    if not surface:
        return {}

    def shape(bucket: dict[str, Any] | None) -> dict[str, Any]:
        bucket = bucket or {}
        return {
            key: {
                "expected": value.get("expected", []),
                "observed": value.get("observed", []),
                "missing": value.get("missing", []),
            }
            for key, value in bucket.items()
        }

    return {
        "powerpoint": shape(surface.get("powerpoint")),
        "excel_addin": shape(surface.get("excel_addin")),
        "excel_update": shape(surface.get("excel_update")),
    }


def _ordered_capability_verdicts(probe: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not probe:
        return []
    verdicts = probe.get("capability_verdicts") or {}
    rows: list[dict[str, Any]] = []
    for key in CAPABILITY_VERDICT_ORDER:
        verdict = verdicts.get(key)
        if not verdict:
            continue
        rows.append(
            {
                "key": key,
                "status": verdict.get("status"),
                "evidence": verdict.get("evidence"),
                "manual_section": verdict.get("manual_section"),
                "deprecated": verdict.get("deprecated", False),
                "ui_only": verdict.get("ui_only", False),
            }
        )
    extras = sorted(set(verdicts.keys()) - set(CAPABILITY_VERDICT_ORDER))
    for key in extras:
        verdict = verdicts.get(key) or {}
        rows.append(
            {
                "key": key,
                "status": verdict.get("status"),
                "evidence": verdict.get("evidence"),
                "manual_section": verdict.get("manual_section"),
                "deprecated": verdict.get("deprecated", False),
                "ui_only": verdict.get("ui_only", False),
            }
        )
    return rows


def _ppttc_metadata_summary(probe: dict[str, Any] | None) -> dict[str, Any]:
    if not probe:
        return {}
    meta = probe.get("ppttc_metadata") or {}
    help_probe = probe.get("ppttc_help_probe") or {}
    return {
        "metadata": meta,
        "help_probe": help_probe,
    }


def _ppttc_samples_summary(probe: dict[str, Any] | None) -> dict[str, Any]:
    if not probe:
        return {}
    samples = probe.get("ppttc_samples") or {}
    if not samples:
        return {}
    keys = ("sample_html", "sample_ppttc", "template_pptx", "ppttc_schema_json")
    summary: dict[str, Any] = {"ppttc_dir": samples.get("ppttc_dir")}
    for key in keys:
        item = samples.get(key) or {}
        summary[key] = {
            "path": item.get("path"),
            "present": item.get("present"),
            "size_bytes": item.get("size_bytes"),
        }
    return summary


def _tcserver_summary(probe: dict[str, Any] | None) -> dict[str, Any]:
    if not probe:
        return {}
    info = probe.get("tcserver") or {}
    if not info:
        return {}
    return {
        "present": info.get("present"),
        "path": info.get("path"),
        "size_bytes": info.get("size_bytes"),
        "product_version": info.get("product_version"),
        "file_version": info.get("file_version"),
        "company_name": info.get("company_name"),
        "candidate_paths": info.get("candidate_paths", []),
        "notes": info.get("notes"),
    }


def _style_assets_summary(probe: dict[str, Any] | None) -> dict[str, Any]:
    if not probe:
        return {}
    info = probe.get("style_assets") or {}
    if not info:
        return {}
    styles_dir = info.get("styles_dir") or {}
    showcase = info.get("showcase_xml") or {}
    schemas = info.get("xml_schemas_dir") or {}
    tcstyle = info.get("tcstyle_xsd") or {}
    return {
        "styles_dir": {
            "path": styles_dir.get("path"),
            "present": styles_dir.get("present"),
            "xml_file_count": styles_dir.get("xml_file_count"),
            "first_xml": styles_dir.get("first_xml"),
            "sample_files": styles_dir.get("sample_files", [])[:6],
        },
        "showcase_xml": {
            "path": showcase.get("path"),
            "present": showcase.get("present"),
            "size_bytes": showcase.get("size_bytes"),
        },
        "xml_schemas_dir": {
            "path": schemas.get("path"),
            "present": schemas.get("present"),
            "xsd_count": schemas.get("xsd_count"),
            "sample_files": schemas.get("sample_files", [])[:8],
        },
        "tcstyle_xsd": {
            "path": tcstyle.get("path"),
            "present": tcstyle.get("present"),
            "size_bytes": tcstyle.get("size_bytes"),
        },
    }


def _style_proof_summary(probe: dict[str, Any] | None) -> dict[str, Any]:
    if not probe:
        return {}
    proof = probe.get("style_proof") or {}
    if not proof:
        return {}
    keys = (
        "get_style_name_master",
        "load_style_master",
        "get_style_name_master_after_load",
        "load_style_for_region_layout",
        "remove_styles_layout",
        "remove_styles_master_blocked",
    )
    return {
        "attempted": proof.get("attempted"),
        "skipped_reason": proof.get("skipped_reason"),
        "style_file": proof.get("style_file"),
        "steps": {key: proof.get(key, {}) for key in keys},
    }


def _mekko_samples_summary(probe: dict[str, Any] | None) -> dict[str, Any]:
    if not probe:
        return {}
    info = probe.get("mekko_samples") or {}
    if not info:
        return {}
    return {
        "samples_present": info.get("samples_present"),
        "candidate_dirs": info.get("candidate_dirs", []),
        "sample_files": info.get("sample_files", [])[:8],
        "notes": info.get("notes"),
    }


def _write_reports(
    *,
    out_dir: Path,
    period: str,
    host: str,
    directors: list[dict[str, Any]],
    checks: list[LabCheck],
    probe: dict[str, Any] | None,
    salesforce_intel: dict[str, Any],
    bridged_output: Path | None,
) -> tuple[Path, Path]:
    status = "pass" if all(check.status in {"pass", "skip"} for check in checks) else "fail"
    install_inventory_summary = _summarize_install_inventory(probe)
    api_surface_summary = _summarize_api_surface(probe)
    capability_verdicts_table = _ordered_capability_verdicts(probe)
    ppttc_summary = _ppttc_metadata_summary(probe)
    ppttc_samples_summary = _ppttc_samples_summary(probe)
    tcserver_summary = _tcserver_summary(probe)
    style_assets_summary = _style_assets_summary(probe)
    style_proof_summary = _style_proof_summary(probe)
    mekko_samples_summary = _mekko_samples_summary(probe)
    payload = {
        "schema": "simcorp-thinkcell-programmatic-lab/v3",
        "status": status,
        "created_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "period": period,
        "host": host,
        "directors": [
            {
                "name": str(director["name"]),
                "slug": _slug(str(director["name"])),
                "scope_label": str(director["scope_label"]),
            }
            for director in directors
        ],
        "seed_template": str(SEED_TEMPLATE),
        "bridged_output": str(bridged_output) if bridged_output else None,
        "source_map_doc": SOURCE_MAP_DOC,
        "probe": probe,
        "install_inventory_summary": install_inventory_summary,
        "api_surface_summary": api_surface_summary,
        "capability_verdicts_table": capability_verdicts_table,
        "ppttc_summary": ppttc_summary,
        "ppttc_samples_summary": ppttc_samples_summary,
        "tcserver_summary": tcserver_summary,
        "style_assets_summary": style_assets_summary,
        "style_proof_summary": style_proof_summary,
        "mekko_samples_summary": mekko_samples_summary,
        "official_api_contract": OFFICIAL_API_CONTRACT,
        "stop_conditions": [
            OBSERVED_NOT_PRODUCTION_STOP_CONDITION,
            "Stop if any payload blends ARR (Type IN ('Land','Expand')) with Renewal ACV (Type = 'Renewal').",
            "Stop if a JSON payload tries to invent a named element that does not exist in the donor template; .ppttc cannot create chart objects.",
            "Stop if attempting to bind native editable think-cell tables; use the table-image lane.",
            "Stop if anyone proposes registering tcserver URLs or starting tcserver as a service from automation; this is an explicit administrator step.",
        ],
        "salesforce_intel": salesforce_intel,
        "checks": [asdict(check) for check in checks],
        "operating_model": {
            "native_chart_text_lane": "Supported when elements already have AddRangeData names; run through ppttc.exe on Windows.",
            "table_lane": "Supported via Excel COM AddRangeImage table-image donors; not native editable think-cell tables.",
            "creation_lane": "Do not plan on headless chart/table creation from scratch; current COM surface exposes update methods, not a safe create method.",
            "simcorp_data_rules": "ARR and Renewal ACV stay separate; Q2 Salesforce decks must preserve explicit Type semantics.",
        },
    }
    json_path = out_dir / "thinkcell_programmatic_lab.json"
    md_path = out_dir / "thinkcell_programmatic_lab.md"
    json_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    lines = [
        "# think-cell Programmatic Lab",
        "",
        f"- Status: `{status}`",
        f"- Period: `{period}`",
        f"- Windows host: `{host}`",
        f"- Directors: {', '.join(_slug(str(director['name'])) for director in directors)}",
        f"- Seed template: `{SEED_TEMPLATE}`",
    ]
    if bridged_output:
        lines.append(f"- Bound seed output: `{bridged_output}`")
    fit_totals = salesforce_intel.get("fit_totals", {})
    if fit_totals:
        lines.append(
            f"- Salesforce rows: {fit_totals.get('q2_publishable_rows')} publishable Q2 rows "
            f"after removing {fit_totals.get('q2_internal_rows_removed')} internal/test rows"
        )
    lines.extend(
        [
            "",
            "## Checks",
            "",
            "| Check | Status | Evidence |",
            "|---|---:|---|",
        ]
    )
    for check in checks:
        evidence = _check_evidence(check)
        lines.append(f"| {check.name} | `{check.status}` | {evidence} |")

    if salesforce_intel.get("family_eligibility_counts"):
        lines.extend(
            [
                "",
                "## Salesforce Intel Applied",
                "",
                "| Family | Eligible Directors | Implication |",
                "|---|---:|---|",
            ]
        )
        implications = {
            "bar_column": "Default Q2 operating chart family.",
            "scatter_bubble": "Use for deal risk only when probability and ARR both spread.",
            "timeline_gantt_fy26_renewals": "Use for FY26 renewal milestones; avoid collapsed date sets.",
            "timeline_gantt_q2_renewals": "Rare this quarter; table fallback is usually stronger.",
            "mekko": "Candidate for dense stage x industry only.",
            "map": "Use sparingly; ranked bars are usually clearer.",
        }
        for family, count in salesforce_intel["family_eligibility_counts"].items():
            lines.append(f"| `{family}` | {count}/9 | {implications.get(family, '')} |")

        lines.extend(["", "### Selected Director Gates", ""])
        for row in salesforce_intel.get("fit_directors", []):
            gates = row.get("chart_gates", {})
            lines.append(
                "- "
                f"{row.get('director')}: "
                f"ARR rows={row.get('q2_open_arr_count')}, "
                f"Q2 renewal rows={row.get('q2_open_renewal_count')}, "
                f"scatter={gates.get('scatter_bubble')}, "
                f"FY26 renewal timeline={gates.get('timeline_gantt_fy26_renewals')}, "
                f"action Gantt={gates.get('gantt_from_actions')}"
            )

        spec_actions = []
        for spec in salesforce_intel.get("regional_intelligence_specs", []):
            for action in spec.get("first_two_week_actions", [])[:2]:
                if isinstance(action, dict):
                    spec_actions.append(
                        f"{spec.get('slug')}: {action.get('priority', '').upper()} - {action.get('claim')}"
                    )
        if spec_actions:
            lines.extend(["", "### First Two-Week Action Signals", ""])
            lines.extend(f"- {item}" for item in spec_actions[:8])

    caps = (probe or {}).get("capabilities", {})
    if caps:
        lines.extend(
            [
                "",
                "## Capability Verdict (legacy boolean snapshot)",
                "",
                f"- ppttc template update: `{caps.get('ppttc_template_update')}`",
                f"- PowerPoint batch chart update: `{caps.get('powerpoint_update_batch_step3')}`",
                f"- Excel AddRangeData: `{caps.get('excel_add_range_data')}`",
                f"- Excel AddRangeImage: `{caps.get('excel_add_range_image')}`",
                f"- Programmatic chart creation: `{caps.get('programmatic_create_chart')}`",
            ]
        )

    if capability_verdicts_table:
        lines.extend(
            [
                "",
                "## Capability Verdict Table (proven / observed / blocked / not_found)",
                "",
                "| Capability | Status | Evidence | Manual Section |",
                "|---|---|---|---|",
            ]
        )
        for row in capability_verdicts_table:
            evidence = (row.get("evidence") or "").replace("|", "\\|")
            section = (row.get("manual_section") or "").replace("|", "\\|")
            lines.append(f"| `{row['key']}` | `{row.get('status')}` | {evidence} | {section} |")

    if api_surface_summary:
        lines.extend(["", "## API Surface (categorized)", ""])
        for surface_key, label in (
            ("powerpoint", "PowerPoint add-in (tcPpAddIn)"),
            ("excel_addin", "Excel add-in (tcXlAddIn)"),
            ("excel_update", "Excel update object (tcUpdate)"),
        ):
            buckets = api_surface_summary.get(surface_key, {})
            if not buckets:
                continue
            lines.extend([f"### {label}", "", "| Group | Observed | Missing |", "|---|---|---|"])
            for group_key, group in buckets.items():
                if group_key == "other":
                    continue
                observed = ", ".join(group.get("observed", []) or []) or "_none_"
                missing = ", ".join(group.get("missing", []) or []) or "_none_"
                lines.append(f"| `{group_key}` | {observed} | {missing} |")
            other = buckets.get("other", {}).get("observed", [])
            if other:
                lines.extend(["", f"_Other observed:_ {', '.join(other)}", ""])
            lines.append("")

    if install_inventory_summary:
        lines.extend(
            [
                "",
                "## think-cell Install Inventory",
                "",
                "| Folder | Present | Files | Dirs | Sample |",
                "|---|---|---:|---:|---|",
            ]
        )
        for key in ("install_root", "ppttc", "templates", "manual", "xml_schemas"):
            folder = install_inventory_summary.get(key)
            if not folder:
                continue
            sample = ", ".join((folder.get("sample_files") or [])[:4]) or "_none_"
            lines.append(
                f"| `{key}` | `{folder.get('present')}` | "
                f"{folder.get('file_count')} | {folder.get('dir_count')} | {sample} |"
            )
        for key in ("ppttc_schema_json", "sample_template_pptx", "sample_ppttc"):
            item = install_inventory_summary.get(key)
            if not item:
                continue
            lines.append(f"| `{key}` | `{item.get('present')}` | - | - | `{item.get('path')}` |")

    ppttc_meta = (ppttc_summary or {}).get("metadata", {})
    ppttc_help = (ppttc_summary or {}).get("help_probe", {})
    if ppttc_meta or ppttc_help:
        lines.extend(["", "## ppttc.exe", ""])
        if ppttc_meta:
            lines.extend(
                [
                    f"- Path: `{ppttc_meta.get('path')}`",
                    f"- Size: `{ppttc_meta.get('size_bytes')}` bytes",
                    f"- Last write (UTC): `{ppttc_meta.get('last_write_time_utc')}`",
                    f"- Product version: `{ppttc_meta.get('product_version')}`",
                    f"- File version: `{ppttc_meta.get('file_version')}`",
                    f"- Company: `{ppttc_meta.get('company_name')}`",
                ]
            )
        if ppttc_help:
            lines.extend(
                [
                    f"- Help probe attempted: `{ppttc_help.get('attempted')}`",
                    f"- Help probe exit code: `{ppttc_help.get('exit_code')}`",
                    f"- Help probe timed out: `{ppttc_help.get('timed_out')}`",
                ]
            )
            head = ppttc_help.get("stdout_head") or ppttc_help.get("stderr_head")
            if head:
                lines.extend(["", "```", str(head).strip(), "```"])

    if ppttc_samples_summary:
        lines.extend(
            [
                "",
                "## Local think-cell Examples",
                "",
                "| Asset | Present | Path |",
                "|---|---|---|",
            ]
        )
        for key, label in (
            ("sample_html", "ppttc/sample.html"),
            ("sample_ppttc", "ppttc/sample.ppttc"),
            ("template_pptx", "ppttc/template.pptx"),
            ("ppttc_schema_json", "ppttc/ppttc-schema.json"),
        ):
            item = ppttc_samples_summary.get(key) or {}
            lines.append(f"| `{label}` | `{item.get('present')}` | `{item.get('path')}` |")

    if tcserver_summary:
        lines.extend(
            [
                "",
                "## tcserver.exe (inventory only)",
                "",
                f"- Present: `{tcserver_summary.get('present')}`",
                f"- Path: `{tcserver_summary.get('path')}`",
                f"- Size: `{tcserver_summary.get('size_bytes')}` bytes",
                f"- Product version: `{tcserver_summary.get('product_version')}`",
                f"- File version: `{tcserver_summary.get('file_version')}`",
                f"- Notes: {tcserver_summary.get('notes')}",
            ]
        )

    if style_assets_summary:
        lines.extend(
            [
                "",
                "## Style Asset Inventory",
                "",
                "| Asset | Present | Detail |",
                "|---|---|---|",
            ]
        )
        sd = style_assets_summary.get("styles_dir", {})
        lines.append(
            f"| `styles/` | `{sd.get('present')}` | xml files: `{sd.get('xml_file_count')}`; first: `{sd.get('first_xml')}` |"
        )
        sc = style_assets_summary.get("showcase_xml", {})
        lines.append(
            f"| `Customization Possibilities Showcase.xml` | `{sc.get('present')}` | size: `{sc.get('size_bytes')}` |"
        )
        xs = style_assets_summary.get("xml_schemas_dir", {})
        lines.append(f"| `xml-schemas/` | `{xs.get('present')}` | xsds: `{xs.get('xsd_count')}` |")
        ts = style_assets_summary.get("tcstyle_xsd", {})
        lines.append(
            f"| `xml-schemas/tcstyle.xsd` | `{ts.get('present')}` | size: `{ts.get('size_bytes')}` |"
        )

    if style_proof_summary:
        lines.extend(
            [
                "",
                "## Style API Proof (transient presentation)",
                "",
                f"- Attempted: `{style_proof_summary.get('attempted')}`",
                f"- Skipped reason: `{style_proof_summary.get('skipped_reason')}`",
                f"- Style file used: `{style_proof_summary.get('style_file')}`",
                "",
                "| Step | Status | Evidence |",
                "|---|---|---|",
            ]
        )
        steps = style_proof_summary.get("steps", {}) or {}
        for key in (
            "get_style_name_master",
            "load_style_master",
            "get_style_name_master_after_load",
            "load_style_for_region_layout",
            "remove_styles_layout",
            "remove_styles_master_blocked",
        ):
            step = steps.get(key, {}) or {}
            value = step.get("value")
            err = step.get("error")
            evidence = ""
            if value:
                evidence = f"value=`{value}`"
            elif err:
                evidence = f"error=`{err}`"
            lines.append(f"| `{key}` | `{step.get('status')}` | {evidence} |")

    if mekko_samples_summary:
        lines.extend(
            [
                "",
                "## Mekko Graphics Samples",
                "",
                f"- Samples present: `{mekko_samples_summary.get('samples_present')}`",
                f"- Notes: {mekko_samples_summary.get('notes')}",
            ]
        )
        if mekko_samples_summary.get("sample_files"):
            lines.append("- Sample files:")
            for sample in mekko_samples_summary["sample_files"]:
                lines.append(f"  - `{sample}`")

    lines.extend(
        [
            "",
            "## Source Map",
            "",
            f"See [`{SOURCE_MAP_DOC}`]({SOURCE_MAP_DOC.replace('docs/thinkcell-corpus/', '')}) for the structured link graph from each official manual page to its factory implication and probe coverage.",
        ]
    )

    lines.extend(
        [
            "",
            "## Official API Contract Summary",
            "",
            "Source: think-cell user manual.",
            "",
            f"- API: <{OFFICIAL_API_CONTRACT['manual_urls']['api']}>",
            f"- Excel data automation: <{OFFICIAL_API_CONTRACT['manual_urls']['excel_data_automation']}>",
            f"- JSON data automation: <{OFFICIAL_API_CONTRACT['manual_urls']['json_data_automation']}>",
            "",
            "Platform:",
            "",
        ]
    )
    for item in OFFICIAL_API_CONTRACT["platform"]:
        lines.append(f"- {item}")
    lines.extend(
        [
            "",
            f"- PowerPoint entry point: `{OFFICIAL_API_CONTRACT['entry_points']['powerpoint']}`",
            f"- Excel entry point: `{OFFICIAL_API_CONTRACT['entry_points']['excel']}`",
            "",
            "### Excel Data Automation (tcXlAddIn / tcUpdate)",
            "",
            "tcXlAddIn methods:",
            "",
        ]
    )
    for entry in OFFICIAL_API_CONTRACT["excel_data_automation"]["tcXlAddIn"]:
        suffix = " _(deprecated)_" if entry.get("deprecated") else ""
        lines.append(f"- `{entry['name']}`{suffix} — {entry['purpose']}")
    lines.extend(["", "tcUpdate methods:", ""])
    for entry in OFFICIAL_API_CONTRACT["excel_data_automation"]["tcUpdate"]:
        lines.append(f"- `{entry['name']}` — {entry['purpose']}")
    lines.extend(
        [
            "",
            "Target enum: "
            + ", ".join(
                f"`{t}`" for t in OFFICIAL_API_CONTRACT["excel_data_automation"]["target_enum"]
            )
            + ".",
            "",
            "Name resolution:",
            "",
        ]
    )
    for item in OFFICIAL_API_CONTRACT["excel_data_automation"]["name_resolution"]:
        lines.append(f"- {item}")
    lines.extend(["", "Transposed semantics:", ""])
    for item in OFFICIAL_API_CONTRACT["excel_data_automation"]["transposed_semantics"]:
        lines.append(f"- {item}")
    lines.extend(["", "### PowerPoint API (tcPpAddIn)", ""])
    for item in OFFICIAL_API_CONTRACT["powerpoint_api"]:
        lines.append(f"- {item}")
    lines.extend(
        [
            "",
            "### JSON Data Automation",
            "",
            f"- Shape: {OFFICIAL_API_CONTRACT['json_data_automation']['ppttc_shape']}",
            "",
            "Table rules:",
            "",
        ]
    )
    for item in OFFICIAL_API_CONTRACT["json_data_automation"]["table_rules"]:
        lines.append(f"- {item}")
    lines.extend(["", "Cell types:", ""])
    for item in OFFICIAL_API_CONTRACT["json_data_automation"]["cell_types"]:
        lines.append(f"- `{item}`")

    lines.extend(
        [
            "",
            "## Stop Conditions",
            "",
            f"- {OBSERVED_NOT_PRODUCTION_STOP_CONDITION}",
            "- Stop if any payload blends ARR (Type IN ('Land','Expand')) with Renewal ACV (Type = 'Renewal').",
            "- Stop if a JSON payload tries to invent a named element that does not exist in the donor template; `.ppttc` cannot create chart objects.",
            "- Stop if attempting to bind native editable think-cell tables; use the table-image lane.",
        ]
    )

    lines.extend(
        [
            "",
            "## Build Direction",
            "",
            "1. Keep treating stock `.potx` as design/donor references, not drop-in automation templates.",
            "2. Build named seed banks per use case: LAND, renewal risk, QBR/quarter deck, and forecast movement.",
            "3. Use the Windows VM as the authoritative runtime for ppttc and Excel COM table-image refresh.",
            "4. Keep native think-cell tables blocked until a real named, data-backed donor is captured.",
        ]
    )
    md_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return json_path, md_path


def _check_evidence(check: LabCheck) -> str:
    details = check.details
    if "capabilities" in details:
        caps = details["capabilities"]
        return (
            f"ppttc={caps.get('ppttc_template_update')}, "
            f"batch={caps.get('powerpoint_update_batch_step3')}, "
            f"image={caps.get('excel_add_range_image')}, "
            f"create={caps.get('programmatic_create_chart')}"
        )
    if "expected_names" in details:
        return f"{details.get('actual_names')}/{details.get('expected_names')} names"
    if "valid_donors" in details:
        return f"{details.get('valid_donors')}/{details.get('expected_donors')} donors"
    if "q2_rows" in details:
        return (
            f"q2_rows={details.get('q2_rows')}, "
            f"removed={details.get('removed_internal_rows')}, "
            f"families={details.get('family_eligibility_counts')}"
        )
    if "directors" in details:
        return ", ".join(f"{row['slug']}:{row['entry_count']}" for row in details["directors"])
    if "embedding_count" in details:
        return (
            f"slides={details.get('slide_count')}, "
            f"embeddings={details.get('embedding_count')}, "
            f"missing={len(details.get('missing_expected_text', []))}"
        )
    if "png_count" in details:
        return f"pngs={details.get('png_count')}"
    if "status" in details:
        return str(details["status"])
    return re.sub(r"\s+", " ", json.dumps(details, sort_keys=True))[:180]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--period", default=DEFAULT_PERIOD)
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--director-slug", default=DEFAULT_DIRECTOR_SLUG)
    parser.add_argument("--all-directors", action="store_true")
    parser.add_argument("--skip-vm-probe", action="store_true")
    parser.add_argument("--skip-bridge", action="store_true")
    parser.add_argument(
        "--render", action="store_true", help="Render the bridged seed output to PNGs."
    )
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()

    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    out_dir = args.output_dir or ROOT / "state" / "thinkcell_bridge" / "programmatic_lab" / stamp
    out_dir.mkdir(parents=True, exist_ok=True)

    directors = _selected_directors(args)
    checks: list[LabCheck] = []
    checks.append(_vm_status_check())
    checks.append(_validate_seed_template())
    checks.append(_validate_table_image_donors())
    salesforce_intel, salesforce_check = _salesforce_intel_context(
        period=args.period, directors=directors
    )
    checks.append(salesforce_check)

    probe: dict[str, Any] | None = None
    if args.skip_vm_probe:
        checks.append(LabCheck("windows_com_probe", "skip", {"reason": "--skip-vm-probe"}))
    else:
        probe, probe_check = _run_windows_probe(args.host)
        checks.append(probe_check)

    checks.append(_build_ppttc(args.period, directors))

    bridged_output: Path | None = None
    if args.skip_bridge:
        checks.append(LabCheck("windows_ppttc_bridge", "skip", {"reason": "--skip-bridge"}))
    else:
        bridged_output, bridge_check = _run_ppttc_bridge(
            period=args.period,
            director=directors[0],
            host=args.host,
            out_dir=out_dir,
        )
        checks.append(bridge_check)
        if args.render and bridged_output:
            checks.append(_render_pptx(bridged_output, out_dir))

    json_path, md_path = _write_reports(
        out_dir=out_dir,
        period=args.period,
        host=args.host,
        directors=directors,
        checks=checks,
        probe=probe,
        salesforce_intel=salesforce_intel,
        bridged_output=bridged_output,
    )
    print(f"json={json_path}")
    print(f"markdown={md_path}")
    for check in checks:
        print(f"{check.status.upper():>7} {check.name}")
    return 0 if all(check.status in {"pass", "skip", "running"} for check in checks) else 2


if __name__ == "__main__":
    raise SystemExit(main())
