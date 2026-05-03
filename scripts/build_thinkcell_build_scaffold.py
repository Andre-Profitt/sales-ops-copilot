#!/usr/bin/env python3
"""Generate build scaffolds from think-cell graph/RAG findings."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PERIOD = "2026-Q2"
DEFAULT_OUTPUT_ROOT = ROOT / "state" / "thinkcell_bridge" / "build_scaffold"
KG_DIR = ROOT / "state" / "thinkcell_bridge" / "knowledge_graph"


BUILD_LEVELS = [
    {
        "level": "L0",
        "label": "Runtime Surface",
        "node_kinds": ["Runtime", "AutomationLane"],
        "gate": "Windows VM probe reports ppttc.exe, PowerPoint addin, Excel addin, AddRangeData, AddRangeImage.",
    },
    {
        "level": "L1",
        "label": "Salesforce Fit Gate",
        "node_kinds": ["SalesforceFit", "SalesDirector", "QuarterSeedContract"],
        "gate": "Contract has eligible directors, fallback directors, and ARR/ACV guardrails.",
    },
    {
        "level": "L2",
        "label": "Template Family",
        "node_kinds": ["TemplateFamily", "Template", "QuarterSeedContract"],
        "gate": "At least one stock think-cell family maps to the SimCorp visual contract.",
    },
    {
        "level": "L3",
        "label": "Slide Donor",
        "node_kinds": ["Slide", "Signal", "ThinkCellClass", "UseClass"],
        "gate": "Candidate slide has relevant family/signals and readable think-cellXML where possible.",
    },
    {
        "level": "L4",
        "label": "Named Seed Contract",
        "node_kinds": ["QuarterSeedContract", "AutomationLane"],
        "gate": "Seed PPTX contains expected AddRangeData/AddRangeImage names before binding.",
    },
    {
        "level": "L5",
        "label": "Binding Proof",
        "node_kinds": ["Runtime", "QuarterSeedContract", "SalesforceFit"],
        "gate": "Bound output renders and contains expected values/text, not only ppttc exit code 0.",
    },
]


FAMILY_TERMS = {
    "bar_column": ["bar, column"],
    "bar_column_map_fallback": ["bar, column"],
    "bar_column_table_image": ["bar, column", "tables"],
    "scatter_bubble": ["scatter, bubble"],
    "timeline_gantt": ["timeline, gantt"],
    "mekko": ["mekko"],
    "waterfall": ["waterfall"],
    "table_image": ["tables", "useful elements/tables", "agendas, schedules, timetables"],
}


SALESFORCE_GATE_BY_FAMILY = {
    "bar_column": "bar_column",
    "bar_column_map_fallback": "bar_column",
    "bar_column_table_image": "bar_column",
    "scatter_bubble": "scatter_bubble",
    "timeline_gantt": "timeline_gantt_fy26_renewals",
    "mekko": "mekko",
    "waterfall": "bar_column",
    "table_image": "bar_column",
}


def _load_json(path: Path) -> Any:
    if not path.exists():
        raise SystemExit(f"missing input: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _latest_programmatic_lab_json() -> Path:
    root = ROOT / "state" / "thinkcell_bridge" / "programmatic_lab"
    candidates = sorted(root.glob("*/thinkcell_programmatic_lab.json"), key=lambda item: item.stat().st_mtime)
    if not candidates:
        raise SystemExit(f"no programmatic lab JSON found under {root}")
    return candidates[-1]


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


def _status(ok: bool, warn: bool = False) -> str:
    if ok and not warn:
        return "pass"
    if ok and warn:
        return "warn"
    return "pending"


def _family_terms(contract: dict[str, Any]) -> list[str]:
    family = contract["family"]
    if family in FAMILY_TERMS:
        return FAMILY_TERMS[family]
    text = f"{family} {contract.get('thinkcell_template_family', '')}".lower()
    terms: list[str] = []
    for key, values in FAMILY_TERMS.items():
        if key in text or any(value in text for value in values):
            terms.extend(values)
    return sorted(set(terms)) or [contract.get("thinkcell_template_family", family).lower()]


def _candidate_score(slide: dict[str, Any], terms: list[str], contract: dict[str, Any]) -> int:
    family_text = f"{slide['family']} {slide['template']}".lower()
    signals = set(slide.get("signals", []))
    use_class = slide.get("use_class", "")
    score = int(slide.get("donor_score") or 0)
    if any(term in family_text for term in terms):
        score += 100
    if use_class == "native_chart_donor_candidate":
        score += 40
    if "readable_thinkcellxml" in signals:
        score += 20
    if "unnamed_donor_candidate" in signals:
        score += 15
    if "chart_reference" in signals:
        score += 10
    if slide.get("simcorp_fit") == "high":
        score += 20
    if slide.get("simcorp_fit") == "medium":
        score += 10
    if contract["family"] == "table_image":
        if "table_reference" in signals:
            score += 45
        if use_class == "table_reference_or_donor_probe":
            score += 40
        if "visual_asset" in signals:
            score += 10
    if contract["family"] == "scatter_bubble" and "scatter_bubble" in signals:
        score += 35
    if contract["family"] == "timeline_gantt" and "timeline_or_gantt" in signals:
        score += 35
    if contract["family"] == "mekko" and "mekko" in signals:
        score += 35
    return score


def _select_candidate_slides(slides: list[dict[str, Any]], contract: dict[str, Any], limit: int) -> list[dict[str, Any]]:
    terms = _family_terms(contract)
    candidates = []
    for slide in slides:
        score = _candidate_score(slide, terms, contract)
        if score < 80:
            continue
        candidates.append(
            {
                "score": score,
                "template": slide["template"],
                "family": slide["family"],
                "slide_number": slide["slide_number"],
                "title": slide["title_guess"],
                "use_class": slide["use_class"],
                "donor_score": slide["donor_score"],
                "simcorp_fit": slide["simcorp_fit"],
                "signals": slide.get("signals", []),
                "chart_refs": slide.get("chart_refs", 0),
                "native_tables": slide.get("native_tables", 0),
                "readable_thinkcellxml_parts": sum(
                    1 for ole in slide.get("ole_parts", []) if ole.get("thinkcellxml_readable")
                ),
                "thinkcell_classes": sorted(
                    {
                        klass
                        for ole in slide.get("ole_parts", [])
                        for klass in ole.get("thinkcell_classes", [])
                    }
                )[:16],
            }
        )
    return sorted(candidates, key=lambda item: (-item["score"], item["template"], item["slide_number"]))[:limit]


def _template_family_matches(summaries: list[dict[str, Any]], contract: dict[str, Any]) -> list[dict[str, Any]]:
    terms = _family_terms(contract)
    matches = []
    for summary in summaries:
        haystack = f"{summary['family']} {summary['template']}".lower()
        if any(term in haystack for term in terms):
            matches.append(
                {
                    "template": summary["template"],
                    "family": summary["family"],
                    "slide_count": summary["slide_count"],
                    "chart_refs": summary["chart_refs"],
                    "readable_thinkcellxml_parts": summary["readable_thinkcellxml_parts"],
                    "use_classes": summary["use_classes"],
                    "top_slide_numbers": summary["top_slide_numbers"],
                }
            )
    return sorted(matches, key=lambda item: (item["family"], item["template"]))


def _salesforce_fit(contract: dict[str, Any], fit_rows: list[dict[str, Any]]) -> dict[str, Any]:
    gate = SALESFORCE_GATE_BY_FAMILY.get(contract["family"])
    eligible = set(contract.get("eligible_directors", []))
    fallback = set(contract.get("fallback_directors", []))
    rows = []
    for row in fit_rows:
        director = str(row["director"])
        gates = row.get("chart_gates", {})
        rows.append(
            {
                "director": director,
                "territory": row.get("territory"),
                "contract_eligible": director in eligible,
                "contract_fallback": director in fallback,
                "chart_gate": bool(gates.get(gate, True)) if gate else True,
                "q2_open_arr_count": row.get("q2_open_arr_count"),
                "q2_open_arr_eur": row.get("q2_open_arr_eur"),
                "fy26_open_renewal_count": row.get("fy26_open_renewal_count"),
                "fy26_open_renewal_acv_eur": row.get("fy26_open_renewal_acv_eur"),
            }
        )
    ready = [row["director"] for row in rows if row["contract_eligible"] and row["chart_gate"] and not row["contract_fallback"]]
    return {
        "gate": gate,
        "ready_directors": ready,
        "fallback_directors": sorted(fallback),
        "rows": rows,
    }


def _runtime_summary(programmatic_lab: dict[str, Any]) -> dict[str, Any]:
    probe = programmatic_lab.get("probe") or {}
    thinkcell = probe.get("thinkcell") or {}
    powerpoint = probe.get("powerpoint") or {}
    excel = probe.get("excel") or {}
    ppt_members = {row.get("name") for row in powerpoint.get("members", [])}
    update_members = {row.get("name") for row in excel.get("update_members", [])}
    excel_members = {row.get("name") for row in excel.get("addin_members", [])}
    return {
        "status": programmatic_lab.get("status"),
        "programmatic_lab_json": str(_latest_programmatic_lab_json().relative_to(ROOT)),
        "ppttc_found": bool(thinkcell.get("ppttc_found")),
        "ppttc_path": thinkcell.get("ppttc_path"),
        "powerpoint_addin": bool(powerpoint.get("thinkcell_addin_found")),
        "excel_addin": bool(excel.get("thinkcell_addin_found")),
        "presentation_from_template": "PresentationFromTemplateStep3" in ppt_members
        or "PresentationFromTemplate" in excel_members,
        "excel_update_batch": {"AddRangeData", "AddRangeImage", "Send"}.issubset(update_members),
        "chart_creation_api": False,
    }


def _levels_for_contract(
    contract: dict[str, Any],
    runtime: dict[str, Any],
    family_matches: list[dict[str, Any]],
    candidates: list[dict[str, Any]],
    sf_fit: dict[str, Any],
    proof: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    director_count = len(contract.get("eligible_directors", []))
    fallback_count = len(contract.get("fallback_directors", []))
    is_table_image = contract["family"] == "table_image"
    lane_text = contract["supported_lane"].lower()
    named_seed_ready = (
        "named seed" in lane_text
        or "addrangeimage" in lane_text
        or "native think-cell" in lane_text
        or "table-image donor" in lane_text
    )
    return [
        {
            **BUILD_LEVELS[0],
            "status": _status(
                runtime["status"] == "pass"
                and runtime["ppttc_found"]
                and runtime["powerpoint_addin"]
                and runtime["excel_addin"]
            ),
            "finding": "Runtime supports update automation; no general chart creation API is exposed.",
            "build_action": "Use Windows VM bridge for binding and proof; keep authoring/naming in PowerPoint with think-cell.",
        },
        {
            **BUILD_LEVELS[1],
            "status": _status(director_count > 0, fallback_count > 0),
            "finding": f"{director_count}/9 directors eligible; {fallback_count}/9 directors require fallback for this visual.",
            "build_action": "Build only eligible director variants; use the documented fallback for listed directors.",
        },
        {
            **BUILD_LEVELS[2],
            "status": _status(bool(family_matches)),
            "finding": f"{len(family_matches)} matching stock template family records found.",
            "build_action": "Start from the best matching stock family as a visual/reference donor, not as a ready-made ppttc template.",
        },
        {
            **BUILD_LEVELS[3],
            "status": _status(bool(candidates), is_table_image),
            "finding": f"{len(candidates)} candidate donor/reference slides selected.",
            "build_action": "For native charts, copy/use the donor in PowerPoint and assign contract names. For tables, keep table-image lane unless native table proof passes.",
        },
        {
            **BUILD_LEVELS[4],
            "status": _status(named_seed_ready, not is_table_image),
            "finding": contract["supported_lane"],
            "build_action": "Verify seed names before data binding. Stock POTX slides with empty names are donor references, not direct automation surfaces.",
        },
        {
            **BUILD_LEVELS[5],
            "status": "pass" if proof and proof.get("status") == "pass" else "pending",
            "finding": (
                f"Proof passed: {proof.get('contract')} for {proof.get('director_slug')}"
                if proof and proof.get("status") == "pass"
                else "Requires per-contract bound output proof."
            ),
            "build_action": (
                "Keep proof JSON attached to the scaffold and extend to additional directors/contracts."
                if proof and proof.get("status") == "pass"
                else "Run ppttc or Excel UpdateBatch, render, and assert expected contract values in the resulting package."
            ),
        },
    ]


def _load_proof(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"status": "fail", "error": f"invalid proof JSON: {path}"}


def build_scaffold(period: str, candidate_limit: int) -> dict[str, Any]:
    slide_corpus = _load_json(ROOT / "state" / "thinkcell_bridge" / "slide_corpus" / "thinkcell_slide_corpus.json")
    quarter_spec = _load_json(
        ROOT / "state" / "thinkcell_bridge" / "quarter_seed_bank" / period / "quarter_seed_bank_spec.json"
    )
    kg_manifest = _load_json(KG_DIR / "thinkcell_kg_manifest.json")
    programmatic_lab = _load_json(_latest_programmatic_lab_json())
    runtime = _runtime_summary(programmatic_lab)
    fit_rows = (programmatic_lab.get("salesforce_intel") or {}).get("fit_directors", [])

    contracts = []
    for contract in quarter_spec["contracts"]:
        family_matches = _template_family_matches(slide_corpus["summaries"], contract)
        candidates = _select_candidate_slides(slide_corpus["slides"], contract, candidate_limit)
        sf_fit = _salesforce_fit(contract, fit_rows)
        artifact_base = f"state/thinkcell_bridge/build_scaffold/{period}/work/{contract['name']}"
        proof_json = ROOT / artifact_base / f"{contract['name']}-proof.json"
        proof = _load_proof(proof_json)
        levels = _levels_for_contract(contract, runtime, family_matches, candidates, sf_fit, proof)
        contracts.append(
            {
                "name": contract["name"],
                "priority": contract["build_priority"],
                "family": contract["family"],
                "thinkcell_template_family": contract["thinkcell_template_family"],
                "supported_lane": contract["supported_lane"],
                "guardrail": contract["metric_guardrail"],
                "fallback": contract["fallback"],
                "readiness": _contract_readiness(levels),
                "proof_status": proof.get("status") if proof else "missing",
                "graph_rag_query": _graph_query(contract),
                "levels": levels,
                "family_matches": family_matches,
                "candidate_slides": candidates,
                "salesforce_fit": sf_fit,
                "artifact_scaffold": {
                    "work_dir": artifact_base,
                    "seed_pptx": f"{artifact_base}/{contract['name']}-seed.pptx",
                    "data_workbook": f"{artifact_base}/{contract['name']}-data.xlsx",
                    "ppttc": f"{artifact_base}/{contract['name']}-{period}.ppttc",
                    "bound_pptx": f"{artifact_base}/{contract['name']}-{period}-bound.pptx",
                    "render_dir": f"{artifact_base}/rendered",
                    "proof_json": f"{artifact_base}/{contract['name']}-proof.json",
                    "proof_markdown": f"{artifact_base}/{contract['name']}-proof.md",
                },
            }
        )

    return {
        "schema": "thinkcell-build-scaffold/v1",
        "created_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "period": period,
        "build_levels": BUILD_LEVELS,
        "runtime": runtime,
        "inputs": {
            "knowledge_graph_manifest": str((KG_DIR / "thinkcell_kg_manifest.json").relative_to(ROOT)),
            "knowledge_graph_schema": kg_manifest.get("schema"),
            "slide_corpus": "state/thinkcell_bridge/slide_corpus/thinkcell_slide_corpus.json",
            "quarter_seed_spec": f"state/thinkcell_bridge/quarter_seed_bank/{period}/quarter_seed_bank_spec.json",
            "programmatic_lab": runtime["programmatic_lab_json"],
        },
        "contracts": contracts,
    }


def _contract_readiness(levels: list[dict[str, Any]]) -> str:
    statuses = {level["level"]: level["status"] for level in levels}
    if statuses.get("L0") != "pass":
        return "blocked_runtime"
    if statuses.get("L2") == "pending" or statuses.get("L3") == "pending":
        return "needs_donor_research"
    if statuses.get("L5") == "pass":
        return "l5_proven"
    if statuses.get("L4") == "warn":
        return "ready_for_named_seed_authoring"
    if statuses.get("L4") == "pass":
        return "ready_for_binding_proof"
    return "needs_contract_review"


def _graph_query(contract: dict[str, Any]) -> str:
    extras = [contract["name"], contract["family"], contract["thinkcell_template_family"], contract["supported_lane"]]
    if contract.get("fallback_directors"):
        extras.append(" ".join(contract["fallback_directors"]))
    return " ".join(extras)


def write_outputs(scaffold: dict[str, Any], output_dir: Path) -> None:
    contracts_dir = output_dir / "contracts"
    contracts_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "thinkcell_build_scaffold.json"
    md_path = output_dir / "thinkcell_build_scaffold.md"
    json_path.write_text(json.dumps(scaffold, indent=2) + "\n", encoding="utf-8")
    md_path.write_text(_render_markdown(scaffold), encoding="utf-8")
    for contract in scaffold["contracts"]:
        (contracts_dir / f"{contract['name']}.md").write_text(_render_contract_markdown(scaffold, contract), encoding="utf-8")


def _render_markdown(scaffold: dict[str, Any]) -> str:
    lines = [
        "# think-cell Build Scaffold",
        "",
        f"- Period: `{scaffold['period']}`",
        f"- Created UTC: `{scaffold['created_at_utc']}`",
        f"- Runtime status: `{scaffold['runtime']['status']}`",
        f"- Contract count: `{len(scaffold['contracts'])}`",
        "",
        "## Build Levels",
        "",
        "| Level | Label | Gate |",
        "|---|---|---|",
    ]
    for level in scaffold["build_levels"]:
        lines.append(f"| `{level['level']}` | {level['label']} | {level['gate']} |")
    lines.extend(
        [
            "",
            "## Contract Scaffolds",
            "",
            "| Contract | Priority | Readiness | Proof | Lane | Candidate slides | Ready directors | Fallback directors |",
            "|---|---:|---|---|---|---:|---:|---:|",
        ]
    )
    for contract in scaffold["contracts"]:
        fit = contract["salesforce_fit"]
        lines.append(
            "| `{name}` | {priority} | `{readiness}` | `{proof}` | {lane} | {candidate_count} | {ready_count} | {fallback_count} |".format(
                name=contract["name"],
                priority=contract["priority"],
                readiness=contract["readiness"],
                proof=contract["proof_status"],
                lane=contract["supported_lane"],
                candidate_count=len(contract["candidate_slides"]),
                ready_count=len(fit["ready_directors"]),
                fallback_count=len(fit["fallback_directors"]),
            )
        )
    lines.extend(
        [
            "",
            "## Commands",
            "",
            "```bash",
            ".venv/bin/python scripts/extract_thinkcell_slide_corpus.py",
            f".venv/bin/python scripts/build_thinkcell_quarter_seed_spec.py --period {scaffold['period']}",
            f".venv/bin/python scripts/build_thinkcell_knowledge_graph.py --period {scaffold['period']}",
            f".venv/bin/python scripts/build_thinkcell_build_scaffold.py --period {scaffold['period']}",
            "```",
            "",
            "## Operating Notes",
            "",
            "- Treat stock POTX slides as donor/reference material until names are verified inside a seed PPTX.",
            "- Level L4 is the handoff from graph retrieval to actual think-cell authoring.",
            "- Level L5 is not complete until the bound deck is rendered and expected values are asserted in the output package.",
        ]
    )
    return "\n".join(lines).rstrip() + "\n"


def _render_contract_markdown(scaffold: dict[str, Any], contract: dict[str, Any]) -> str:
    lines = [
        f"# {contract['name']} Build Scaffold",
        "",
        f"- Period: `{scaffold['period']}`",
        f"- Priority: `{contract['priority']}`",
        f"- Readiness: `{contract['readiness']}`",
        f"- Proof status: `{contract['proof_status']}`",
        f"- Family: `{contract['family']}`",
        f"- think-cell family: `{contract['thinkcell_template_family']}`",
        f"- Lane: {contract['supported_lane']}",
        f"- Guardrail: {contract['guardrail']}",
        f"- Fallback: {contract['fallback']}",
        "",
        "## Level Gates",
        "",
        "| Level | Status | Finding | Build action |",
        "|---|---|---|---|",
    ]
    for level in contract["levels"]:
        lines.append(
            f"| `{level['level']}` {level['label']} | `{level['status']}` | {level['finding']} | {level['build_action']} |"
        )
    lines.extend(["", "## Candidate Slides", "", "| Rank | Score | Source | Use class | Signals |", "|---:|---:|---|---|---|"])
    for index, slide in enumerate(contract["candidate_slides"], start=1):
        source = f"{slide['template']} slide {slide['slide_number']} - {slide['title']}"
        signals = ", ".join(slide["signals"][:6])
        lines.append(f"| {index} | {slide['score']} | {source} | `{slide['use_class']}` | {signals} |")
    if not contract["candidate_slides"]:
        lines.append("| - | - | No candidate selected | - | - |")
    lines.extend(["", "## Salesforce Fit", ""])
    fit = contract["salesforce_fit"]
    lines.append(f"- Gate: `{fit['gate']}`")
    lines.append(f"- Ready directors: {', '.join(fit['ready_directors']) or 'None'}")
    lines.append(f"- Fallback directors: {', '.join(fit['fallback_directors']) or 'None'}")
    lines.extend(
        [
            "",
            "## Artifact Scaffold",
            "",
            "| Artifact | Path |",
            "|---|---|",
        ]
    )
    for key, value in contract["artifact_scaffold"].items():
        lines.append(f"| `{key}` | `{value}` |")
    lines.extend(
        [
            "",
            "## Graph Query",
            "",
            "```bash",
            f".venv/bin/python scripts/query_thinkcell_knowledge_graph.py \"{contract['graph_rag_query']}\"",
            "```",
        ]
    )
    return "\n".join(lines).rstrip() + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--period", default=DEFAULT_PERIOD)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--candidate-limit", type=int, default=5)
    args = parser.parse_args()

    output_dir = args.output_root / args.period
    scaffold = build_scaffold(args.period, args.candidate_limit)
    write_outputs(scaffold, output_dir)
    print(f"contracts={len(scaffold['contracts'])}")
    print(f"markdown={output_dir / 'thinkcell_build_scaffold.md'}")
    print(f"json={output_dir / 'thinkcell_build_scaffold.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
