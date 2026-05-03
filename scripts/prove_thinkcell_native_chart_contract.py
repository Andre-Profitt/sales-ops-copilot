#!/usr/bin/env python3
"""Build and prove a native think-cell chart scaffold contract."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any
from zipfile import ZIP_DEFLATED, ZipFile

from PIL import Image, ImageStat

from ppttc_template import template_named_elements
from thinkcell_cfb import CfbStreamEdit, replace_cfb_stream_data


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PERIOD = "2026-Q2"
DEFAULT_DIRECTOR_SLUG = "Jesper-Tyrer"
DEFAULT_CONTRACT = "QTR01_StageMix_Bar"
DEFAULT_SEED_SOURCE = ROOT / "assets" / "LAND_thinkcell_seed.pptx"
EMU_PER_INCH = 914400


@dataclass(frozen=True)
class NativeChartContract:
    contract: str
    source_name: str
    target_name: str
    slide: int
    required_terms: tuple[str, ...]
    source_seed: Path = DEFAULT_SEED_SOURCE


@dataclass
class Check:
    name: str
    status: str
    details: dict[str, Any] = field(default_factory=dict)


CONTRACTS: dict[str, NativeChartContract] = {
    DEFAULT_CONTRACT: NativeChartContract(
        contract=DEFAULT_CONTRACT,
        source_name="S05_PipelineByStage",
        target_name="QTR01_StageMix_Bar",
        slide=5,
        required_terms=("3 - Engagement", "6 - Contracting", "Open ARR (mEUR)"),
    ),
    "QTR02_ForecastMix_Bar": NativeChartContract(
        contract="QTR02_ForecastMix_Bar",
        source_name="S13_ForecastCategory",
        target_name="QTR02_ForecastMix_Bar",
        slide=13,
        required_terms=("Pipeline", "Commit", "ARR (mEUR)"),
    ),
    "QTR03_OwnerCoaching_Bar": NativeChartContract(
        contract="QTR03_OwnerCoaching_Bar",
        source_name="S15_ByOwner",
        target_name="QTR03_OwnerCoaching_Bar",
        slide=15,
        required_terms=("Enzo Cotroneo", "Jesper Tyrer", "Open ARR (mEUR)"),
    ),
    "QTR07_StageIndustry_Mekko": NativeChartContract(
        contract="QTR07_StageIndustry_Mekko",
        source_name="S16_StageByIndustry",
        target_name="QTR07_StageIndustry_Mekko",
        slide=16,
        required_terms=("Prospecting", "Asset Management", "Central Bank"),
    ),
    "QTR08_PipelineMovement_Waterfall": NativeChartContract(
        contract="QTR08_PipelineMovement_Waterfall",
        source_name="S04_PipeMovement",
        target_name="QTR08_PipelineMovement_Waterfall",
        slide=4,
        required_terms=(
            "Opening pipe (start of 2026-Q2)",
            "Closing pipe (2026-Q2 CFQ)",
            "ARR (mEUR)",
        ),
    ),
    "QTR09_Geography_RankedBar": NativeChartContract(
        contract="QTR09_Geography_RankedBar",
        source_name="S17_TerritoryPerformance",
        target_name="QTR09_Geography_RankedBar",
        slide=17,
        required_terms=("Australia", "Malaysia", "Open ARR (mEUR)"),
    ),
    "QTR13_PipelineAging_Bar": NativeChartContract(
        contract="QTR13_PipelineAging_Bar",
        source_name="S06_PipelineAging",
        target_name="QTR13_PipelineAging_Bar",
        slide=6,
        required_terms=("0-30 days", "730 days", "zombie", "Open ARR (mEUR)"),
    ),
    "QTR14_WinsLossesQTD_GroupedColumn": NativeChartContract(
        contract="QTR14_WinsLossesQTD_GroupedColumn",
        source_name="S18_WinsLossesQTD",
        target_name="QTR14_WinsLossesQTD_GroupedColumn",
        slide=18,
        required_terms=("Won", "Lost", "ARR (Land+Expand, mEUR)", "ACV (Renewal, mEUR)"),
    ),
    "QTR15_Velocity_Bar": NativeChartContract(
        contract="QTR15_Velocity_Bar",
        source_name="S19_Velocity",
        target_name="QTR15_Velocity_Bar",
        slide=19,
        required_terms=("Median age (days)", "Prospect.", "Contract"),
    ),
    "QTR16_ConcentrationRisk_Stacked": NativeChartContract(
        contract="QTR16_ConcentrationRisk_Stacked",
        source_name="S21_ConcentrationRiskChart",
        target_name="QTR16_ConcentrationRisk_Stacked",
        slide=21,
        required_terms=("Top 1 account", "Top 5 accounts", "Share (%)"),
    ),
    "QTR17_PipelineCreationVelocity_Bar": NativeChartContract(
        contract="QTR17_PipelineCreationVelocity_Bar",
        source_name="S25_PipelineCreationVelocity",
        target_name="QTR17_PipelineCreationVelocity_Bar",
        slide=25,
        required_terms=("Feb 16", "Apr 27", "New ARR (mEUR)"),
    ),
}


def _director_dir(period: str, director_slug: str) -> Path:
    return ROOT / "state" / period / director_slug


def _work_dir(period: str, contract: str) -> Path:
    return ROOT / "state" / "thinkcell_bridge" / "build_scaffold" / period / "work" / contract


def _source_ppttc(period: str, director_slug: str) -> Path:
    return _director_dir(period, director_slug) / f"{director_slug}-LAND-{period}.ppttc"


def _run(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=ROOT, text=True, capture_output=True, check=False)


def _replace_named_element(source: Path, output: Path, old_name: str, new_name: str) -> Check:
    old = f"<m_strName>{old_name}</m_strName>".encode("utf-8")
    new = f"<m_strName>{new_name}</m_strName>".encode("utf-8")
    touched = 0
    replacements = 0
    output.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(source) as zin, ZipFile(output, "w", ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            data = zin.read(item.filename)
            if item.filename.startswith("ppt/embeddings/") and item.filename.endswith(".bin"):
                result = replace_cfb_stream_data(
                    data,
                    (CfbStreamEdit(name="think-cellXML", replacements=((old, new),)),),
                )
                data = result.data
                touched += result.streams_touched
                replacements += result.replacements_made
            zout.writestr(item, data)
    names = set(template_named_elements(output))
    ok = new_name in names and old_name not in names and touched == 1 and replacements == 1
    return Check(
        "named_seed_contract",
        "pass" if ok else "fail",
        {
            "source_seed": str(source),
            "seed_pptx": str(output),
            "old_name": old_name,
            "new_name": new_name,
            "streams_touched": touched,
            "replacements": replacements,
            "name_present": new_name in names,
            "old_name_present": old_name in names,
            "name_count": len(names),
        },
    )


def _load_source_entry(path: Path, source_name: str) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    for item in payload:
        for entry in item.get("data", []):
            if entry.get("name") == source_name:
                return entry
    raise KeyError(f"{source_name} not found in {path}")


def _write_contract_ppttc(source_ppttc: Path, output: Path, seed: Path, contract: NativeChartContract) -> Check:
    try:
        entry = _load_source_entry(source_ppttc, contract.source_name)
    except Exception as exc:  # noqa: BLE001 - proof artifact should preserve exact failure.
        return Check("ppttc_contract_payload", "fail", {"source_ppttc": str(source_ppttc), "error": str(exc)})
    qtr_entry = json.loads(json.dumps(entry))
    qtr_entry["name"] = contract.target_name
    payload = [{"template": str(seed.resolve()), "data": [qtr_entry]}]
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    terms_present = []
    text = output.read_text(encoding="utf-8")
    for term in contract.required_terms:
        terms_present.append({"term": term, "present": term in text})
    ok = all(item["present"] for item in terms_present)
    return Check(
        "ppttc_contract_payload",
        "pass" if ok else "fail",
        {
            "source_ppttc": str(source_ppttc),
            "contract_ppttc": str(output),
            "template": str(seed),
            "source_name": contract.source_name,
            "target_name": contract.target_name,
            "required_terms": terms_present,
        },
    )


def _bridge_ppttc(ppttc: Path, seed: Path, output: Path) -> Check:
    command = [
        sys.executable,
        "scripts/run_thinkcell_windows_bridge.py",
        "--ppttc",
        str(ppttc),
        "--template",
        str(seed),
        "--output",
        str(output),
    ]
    result = _run(command)
    ok = result.returncode == 0 and output.exists() and output.stat().st_size > 0
    return Check(
        "windows_ppttc_binding",
        "pass" if ok else "fail",
        {
            "command": command,
            "returncode": result.returncode,
            "stdout_tail": result.stdout[-4000:],
            "stderr_tail": result.stderr[-4000:],
            "bound_pptx": str(output),
            "bound_pptx_bytes": output.stat().st_size if output.exists() else 0,
        },
    )


def _iter_ppt_xml_text(path: Path) -> str:
    chunks: list[str] = []
    with ZipFile(path) as zf:
        for name in zf.namelist():
            if name.startswith("ppt/") and name.endswith(".xml"):
                chunks.append(zf.read(name).decode("utf-8", "ignore"))
    return "\n".join(chunks)


def _check_bound_package(path: Path, contract: NativeChartContract) -> Check:
    names = set(template_named_elements(path)) if path.exists() else set()
    text = _iter_ppt_xml_text(path) if path.exists() else ""
    term_checks = [{"term": term, "present": term in text} for term in contract.required_terms]
    ok = path.exists() and contract.target_name in names and all(item["present"] for item in term_checks)
    return Check(
        "bound_package_assertions",
        "pass" if ok else "fail",
        {
            "bound_pptx": str(path),
            "target_name": contract.target_name,
            "target_name_present": contract.target_name in names,
            "required_terms": term_checks,
        },
    )


def _render_deck(deck: Path, render_dir: Path) -> Check:
    if render_dir.exists():
        shutil.rmtree(render_dir)
    command = [
        sys.executable,
        "scripts/render_deck_for_review.py",
        str(deck),
        "--output-dir",
        str(render_dir),
    ]
    result = _run(command)
    return Check(
        "render_deck",
        "pass" if result.returncode == 0 else "fail",
        {
            "command": command,
            "returncode": result.returncode,
            "stdout_tail": result.stdout[-4000:],
            "stderr_tail": result.stderr[-4000:],
            "png_dir": str(render_dir / "png"),
            "pdf_dir": str(render_dir / "pdf"),
        },
    )


def _proof_render(render_dir: Path, contract: NativeChartContract) -> Check:
    path = render_dir / "png" / f"slide-{contract.slide:02d}.png"
    if not path.exists():
        short_path = render_dir / "png" / f"slide-{contract.slide}.png"
        if short_path.exists():
            path = short_path
    details: dict[str, Any] = {"slide": contract.slide, "png": str(path)}
    if not path.exists():
        return Check("rendered_chart_visibility", "fail", details | {"error": "missing render"})
    with Image.open(path) as image:
        rgb = image.convert("RGB")
        width, height = rgb.size
        crop = rgb.crop((int(width * 0.04), int(height * 0.18), int(width * 0.96), int(height * 0.88)))
        gray = crop.convert("L")
        stat = ImageStat.Stat(gray)
        pixel_data = getattr(gray, "get_flattened_data", gray.getdata)()
        dark_pixels = sum(1 for pixel in pixel_data if pixel < 190)
    ok = stat.stddev[0] >= 8.0 and dark_pixels >= 5000
    details.update(
        {
            "image_size": [width, height],
            "content_crop_stddev": round(stat.stddev[0], 3),
            "content_crop_dark_pixels": dark_pixels,
            "min_stddev": 8.0,
            "min_dark_pixels": 5000,
        }
    )
    return Check("rendered_chart_visibility", "pass" if ok else "fail", details)


def _write_markdown(path: Path, payload: dict[str, Any]) -> None:
    lines = [
        f"# {payload['contract']} Native Chart Proof",
        "",
        f"- Status: `{payload['status']}`",
        f"- Period: `{payload['period']}`",
        f"- Director: `{payload['director_slug']}`",
        f"- Seed: `{payload['seed_pptx']}`",
        f"- PPTTC: `{payload['ppttc']}`",
        f"- Bound deck: `{payload['deck']}`",
        f"- Render dir: `{payload['render_dir']}`",
        "",
        "## Checks",
        "",
        "| Check | Status |",
        "|---|---|",
    ]
    for check in payload["checks"]:
        lines.append(f"| `{check['name']}` | `{check['status']}` |")
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--period", default=DEFAULT_PERIOD)
    parser.add_argument("--director-slug", default=DEFAULT_DIRECTOR_SLUG)
    parser.add_argument("--contract", default=DEFAULT_CONTRACT)
    args = parser.parse_args()

    contract = CONTRACTS.get(args.contract)
    if not contract:
        raise SystemExit(f"unsupported contract: {args.contract}")

    work_dir = _work_dir(args.period, contract.contract)
    seed = work_dir / f"{contract.contract}-seed.pptx"
    ppttc = work_dir / f"{contract.contract}-{args.period}.ppttc"
    bound = work_dir / f"{contract.contract}-{args.period}-bound.pptx"
    render_dir = work_dir / "rendered"
    source_ppttc = _source_ppttc(args.period, args.director_slug)
    work_dir.mkdir(parents=True, exist_ok=True)

    checks = [
        _replace_named_element(contract.source_seed, seed, contract.source_name, contract.target_name),
        _write_contract_ppttc(source_ppttc, ppttc, seed, contract),
    ]
    if all(check.status == "pass" for check in checks):
        checks.append(_bridge_ppttc(ppttc, seed, bound))
    if all(check.status == "pass" for check in checks):
        checks.append(_check_bound_package(bound, contract))
    if all(check.status == "pass" for check in checks):
        checks.append(_render_deck(bound, render_dir))
    if all(check.status == "pass" for check in checks):
        checks.append(_proof_render(render_dir, contract))

    status = "pass" if all(check.status == "pass" for check in checks) else "fail"
    payload = {
        "schema": "thinkcell-native-chart-proof/v1",
        "created_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "status": status,
        "contract": contract.contract,
        "period": args.period,
        "director_slug": args.director_slug,
        "deck": str(bound),
        "workbook": "",
        "source_ppttc": str(source_ppttc),
        "seed_pptx": str(seed),
        "ppttc": str(ppttc),
        "render_dir": str(render_dir),
        "targets": [
            {
                "name": contract.target_name,
                "source_name": contract.source_name,
                "slide": contract.slide,
                "required_terms": list(contract.required_terms),
            }
        ],
        "checks": [asdict(check) for check in checks],
    }
    proof_json = work_dir / f"{contract.contract}-proof.json"
    proof_md = work_dir / f"{contract.contract}-proof.md"
    proof_json.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    _write_markdown(proof_md, payload)
    print(f"status={status}")
    print(f"proof_json={proof_json}")
    print(f"proof_md={proof_md}")
    return 0 if status == "pass" else 2


if __name__ == "__main__":
    raise SystemExit(main())
