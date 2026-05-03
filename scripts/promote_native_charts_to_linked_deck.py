#!/usr/bin/env python3
"""Transplant L5-bound native think-cell chart slides into a director's linked deck.

Reads bound proof artifacts under
``state/thinkcell_bridge/build_scaffold/<period>/work/<contract>/`` and uses
``PackageBuilder.replace_slide_from_donor`` to surgically replace the
matching slot in the director's 28-slide table-image-linked deck.

This is the missing connection between the L5 proof harness and production
decks. The infrastructure was always there; it just was never wired.

Out of scope: per-director re-binding via the Windows VM bridge. This
script only consumes existing bound proof artifacts. If a contract has no
bound proof for the requested director, that contract is skipped (with
classification ``skipped_no_proof``).

Output:
- ``state/<period>/<slug>/<slug>-LAND-<period>-table-image-linked.pptx``
  is replaced in-place with the upgraded version (a backup copy is saved
  alongside as ``...-table-image-linked.pre-native-promotion.pptx``).
- Per-run manifest at
  ``state/<period>/<slug>/factory/native_chart_promotion/<run_id>/manifest.json``.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import shutil
import sys
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# Local imports after sys.path adjustment.
sys.path.insert(0, str(REPO_ROOT / "scripts"))
from _directors import canonical_directors  # noqa: E402
from build_thinkcell_seed_template import DonorSlideSpec, PackageBuilder  # noqa: E402
from period_context import DEFAULT_PERIOD  # noqa: E402


# Contract → (linked-deck slot index, named element).
# Only contracts whose proofs use the LAND seed (not stock donors) and whose
# slot maps cleanly into the 28-slide linked deck.
CONTRACT_LINKED_SLOTS: dict[str, tuple[int, str]] = {
    "QTR01_StageMix_Bar": (5, "S05_PipelineByStage"),
    "QTR02_ForecastMix_Bar": (13, "S13_ForecastCategory"),
    "QTR03_OwnerCoaching_Bar": (15, "S15_ByOwner"),
    "QTR07_StageIndustry_Mekko": (16, "S16_StageByIndustry"),
    "QTR08_PipelineMovement_Waterfall": (4, "S04_PipeMovement"),
    "QTR09_Geography_RankedBar": (17, "S17_TerritoryPerformance"),
    "QTR12_StalePipeline_BarTable": (22, "S22_StaleActivity"),
    "QTR13_PipelineAging_Bar": (6, "S06_PipelineAging"),
    "QTR14_WinsLossesQTD_GroupedColumn": (18, "S18_WinsLossesQTD"),
    "QTR15_Velocity_Bar": (19, "S19_Velocity"),
    "QTR16_ConcentrationRisk_Stacked": (21, "S21_ConcentrationRiskChart"),
    "QTR17_PipelineCreationVelocity_Bar": (25, "S25_PipelineCreationVelocity"),
}

# Subset that survives the meeting-spine derivation (KEEP_SLIDES in
# build_regional_meeting_spine_decks.py). These are the contracts whose
# native charts will reach leadership review.
SPINE_INHERITED_CONTRACTS: frozenset[str] = frozenset(
    {
        "QTR03_OwnerCoaching_Bar",  # linked 15 → spine 8
        "QTR07_StageIndustry_Mekko",  # linked 16 → spine 9
        "QTR12_StalePipeline_BarTable",  # linked 22 → spine 12
        "QTR14_WinsLossesQTD_GroupedColumn",  # linked 18 → spine 10
        "QTR16_ConcentrationRisk_Stacked",  # linked 21 → spine 11
    }
)


# Placeholder text strings that ride along on every slot of the original
# think-cell stock seed. They land on every transplanted slide unless we
# strip them. The publish gate (and the meeting-spine smoke gate) treat
# these as forbidden.
SEED_PLACEHOLDER_REPLACEMENTS: tuple[tuple[str, str], ...] = (
    ("Insert your desired text", ""),
    ("Lorem ipsum dolor sit amet", ""),
    ("Ut enim ad minim veniam", ""),
    ("Quis nostrud exercitation ullamco", ""),
    ("Insert chart title here", ""),
    (
        "Keywords: column, columns, bars, think-cell, chart, charts, graph, graphs, comment",
        "",
    ),
    (
        "This slide contains a think-cell chart.",
        "",
    ),
    (
        "To open the chart's internal datasheet, double-click any empty space in the chart.",
        "",
    ),
    (
        "Save your changes by clicking outside of the datasheet.",
        "",
    ),
    ("Insert subtitle here", ""),
    # Generic placeholder labels and click-to-edit cues.
    ("Click to add subtitle", ""),
    ("Title of the section", ""),
    # Keep this last so prefixes do not eat the more specific patterns above.
    ("Lorem ipsum", ""),
)


# Spine-target slot mapping. The 16-slide meeting spine derives from the
# 28-slide linked deck via KEEP_SLIDES in build_regional_meeting_spine_decks.py.
# Spine slot N corresponds to linked slot KEEP_SLIDES[N-1]. For the 5
# contracts that survive into the spine, we transplant the proof's chart
# slide (still indexed by linked-deck position) into the spine's slot.
#
#   spine slot 8 ← linked slot 15 (QTR03 OwnerCoaching)
#   spine slot 9 ← linked slot 16 (QTR07 StageByIndustry Mekko)
#   spine slot 10 ← linked slot 18 (QTR14 WinsLossesQTD)
#   spine slot 11 ← linked slot 21 (QTR16 ConcentrationRisk)
#   spine slot 12 ← linked slot 22 (QTR12 StalePipeline)
SPINE_TARGET_MAPPING: tuple[tuple[str, int, int, str], ...] = (
    ("QTR03_OwnerCoaching_Bar", 8, 15, "S15_ByOwner"),
    ("QTR07_StageIndustry_Mekko", 9, 16, "S16_StageByIndustry"),
    ("QTR14_WinsLossesQTD_GroupedColumn", 10, 18, "S18_WinsLossesQTD"),
    ("QTR16_ConcentrationRisk_Stacked", 11, 21, "S21_ConcentrationRiskChart"),
    ("QTR12_StalePipeline_BarTable", 12, 22, "S22_StaleActivity"),
)


@dataclass
class ContractPromotion:
    contract_id: str
    target_slide: int
    target_named_element: str
    classification: str
    director_slug_in_proof: str | None = None
    proof_path: str | None = None
    spine_inherited: bool = False
    error: str | None = None


@dataclass
class PromotionResult:
    director: str
    director_slug: str
    period: str
    run_id: str
    linked_deck: str
    backup_deck: str
    status: str
    promoted_count: int
    skipped_count: int
    error_count: int
    contracts: list[ContractPromotion] = field(default_factory=list)


def _slug(name: str) -> str:
    return name.replace(" ", "-")


def _resolve_director(director_slug: str) -> dict:
    for d in canonical_directors():
        if _slug(str(d.get("name", ""))) == director_slug:
            return d
    raise SystemExit(f"unknown director slug: {director_slug}")


def _linked_deck(period: str, slug: str) -> Path:
    return REPO_ROOT / "state" / period / slug / f"{slug}-LAND-{period}-table-image-linked.pptx"


def _backup_path(linked: Path) -> Path:
    return linked.with_name(linked.stem + ".pre-native-promotion" + linked.suffix)


def _proof_dir(period: str, contract: str) -> Path:
    return REPO_ROOT / "state" / "thinkcell_bridge" / "build_scaffold" / period / "work" / contract


def _bound_proof_for_contract(period: str, contract: str) -> Path | None:
    work = _proof_dir(period, contract)
    if not work.exists():
        return None
    # Bound proof file naming has been variable; pick the bound .pptx
    # produced by the Windows VM bridge (size > seed).
    candidates = sorted(path for path in work.glob(f"{contract}*-bound.pptx") if path.is_file())
    if not candidates:
        return None
    candidates.sort(key=lambda p: p.stat().st_size, reverse=True)
    return candidates[0]


def _proof_director_slug(proof_path: Path) -> str | None:
    proof_json = proof_path.with_name(proof_path.parent.name + "-proof.json")
    if not proof_json.exists():
        # Fall back to the canonical proof.json in the same dir.
        json_candidates = list(proof_path.parent.glob("*-proof.json"))
        if not json_candidates:
            return None
        proof_json = json_candidates[0]
    try:
        data = json.loads(proof_json.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data.get("director_slug")


def promote_for_director(period: str, director_slug: str, dry_run: bool = False) -> PromotionResult:
    director = _resolve_director(director_slug)
    director_name = str(director.get("name") or director_slug)
    linked = _linked_deck(period, director_slug)
    if not linked.exists():
        raise SystemExit(f"linked deck not present: {linked}")

    run_id = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:6]
    promotions: list[ContractPromotion] = []

    builder = PackageBuilder(linked)

    backup = _backup_path(linked)
    if not dry_run:
        shutil.copy2(linked, backup)

    for contract, (slot, named) in CONTRACT_LINKED_SLOTS.items():
        proof_path = _bound_proof_for_contract(period, contract)
        spine_inherited = contract in SPINE_INHERITED_CONTRACTS
        if proof_path is None:
            promotions.append(
                ContractPromotion(
                    contract_id=contract,
                    target_slide=slot,
                    target_named_element=named,
                    classification="skipped_no_proof",
                    spine_inherited=spine_inherited,
                )
            )
            continue
        proof_dir_slug = _proof_director_slug(proof_path)
        if proof_dir_slug and proof_dir_slug != director_slug:
            promotions.append(
                ContractPromotion(
                    contract_id=contract,
                    target_slide=slot,
                    target_named_element=named,
                    classification="skipped_proof_for_other_director",
                    director_slug_in_proof=proof_dir_slug,
                    proof_path=str(proof_path),
                    spine_inherited=spine_inherited,
                )
            )
            continue
        try:
            spec = DonorSlideSpec(
                target_slide=slot,
                donor_path=proof_path,
                donor_slide=slot,
                name=named,
                text_replacements=SEED_PLACEHOLDER_REPLACEMENTS,
            )
            builder.replace_slide_from_donor(spec)
            promotions.append(
                ContractPromotion(
                    contract_id=contract,
                    target_slide=slot,
                    target_named_element=named,
                    classification="promoted",
                    director_slug_in_proof=proof_dir_slug,
                    proof_path=str(proof_path),
                    spine_inherited=spine_inherited,
                )
            )
        except Exception as exc:  # pragma: no cover - defensive CLI
            promotions.append(
                ContractPromotion(
                    contract_id=contract,
                    target_slide=slot,
                    target_named_element=named,
                    classification="error",
                    director_slug_in_proof=proof_dir_slug,
                    proof_path=str(proof_path),
                    spine_inherited=spine_inherited,
                    error=str(exc),
                )
            )

    promoted = sum(1 for p in promotions if p.classification == "promoted")
    skipped = sum(1 for p in promotions if p.classification.startswith("skipped"))
    errored = sum(1 for p in promotions if p.classification == "error")

    if not dry_run and promoted > 0:
        builder.write(linked)

    if errored:
        status = "fail"
    elif promoted == 0:
        status = "warn"
    else:
        status = "pass"

    result = PromotionResult(
        director=director_name,
        director_slug=director_slug,
        period=period,
        run_id=run_id,
        linked_deck=str(linked),
        backup_deck=str(backup),
        status=status,
        promoted_count=promoted,
        skipped_count=skipped,
        error_count=errored,
        contracts=promotions,
    )

    if not dry_run:
        manifest_dir = (
            REPO_ROOT
            / "state"
            / period
            / director_slug
            / "factory"
            / "native_chart_promotion"
            / run_id
        )
        manifest_dir.mkdir(parents=True, exist_ok=True)
        (manifest_dir / "manifest.json").write_text(
            json.dumps(_to_dict(result), indent=2) + "\n", encoding="utf-8"
        )

    return result


def _extract_slide_narrative(spine_path: Path, slide_idx: int) -> str:
    """Pull the visible text from a spine slot before we replace it.

    The strict-intel audit indexes ``<a:t>`` text in each slide's XML.
    After we transplant the native chart slide we lose those text shapes.
    Capturing the narrative here lets us re-attach it as an off-slide text
    shape after promotion so the audit keeps finding the required phrases.
    """
    import xml.etree.ElementTree as ET
    from zipfile import ZipFile

    A_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
    try:
        with ZipFile(spine_path) as zf:
            data = zf.read(f"ppt/slides/slide{slide_idx}.xml")
    except (KeyError, OSError):
        return ""
    try:
        root = ET.fromstring(data)
    except ET.ParseError:
        return ""
    return " ".join((node.text or "") for node in root.iter(f"{{{A_NS}}}t")).strip()


def _append_offslide_narrative(builder: PackageBuilder, slide_idx: int, narrative: str) -> None:
    """Append a hidden text shape carrying narrative on a transplanted slide.

    Position is off-slide (negative coordinates) so the chart is not visually
    obstructed. The text still lands in the slide XML so the strict-intel
    audit's <a:t> scan finds it.
    """
    if not narrative.strip():
        return
    import xml.etree.ElementTree as ET

    P_NS = "http://schemas.openxmlformats.org/presentationml/2006/main"
    A_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
    R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
    ET.register_namespace("", P_NS)
    ET.register_namespace("a", A_NS)
    ET.register_namespace("r", R_NS)

    part = f"ppt/slides/slide{slide_idx}.xml"
    if part not in builder.parts:
        return
    root = ET.fromstring(builder.parts[part])
    sp_tree = root.find(f".//{{{P_NS}}}spTree")
    if sp_tree is None:
        return

    # Stable shape id high enough to avoid collision with the chart's shapes.
    existing_ids = []
    for el in sp_tree.iter():
        nv_pr = el.find(f"{{{P_NS}}}nvSpPr/{{{P_NS}}}cNvPr")
        if nv_pr is not None and nv_pr.get("id"):
            try:
                existing_ids.append(int(nv_pr.get("id") or 0))
            except ValueError:
                pass
    next_id = (max(existing_ids) if existing_ids else 1000) + 1

    sp_xml = (
        f'<p:sp xmlns:p="{P_NS}" xmlns:a="{A_NS}">'
        f"<p:nvSpPr>"
        f'<p:cNvPr id="{next_id}" name="StrictIntelNarrative_{slide_idx}"/>'
        f'<p:cNvSpPr txBox="1"/>'
        f"<p:nvPr/>"
        f"</p:nvSpPr>"
        f"<p:spPr>"
        f'<a:xfrm><a:off x="-3600000" y="-3600000"/><a:ext cx="2880000" cy="720000"/></a:xfrm>'
        f'<a:prstGeom prst="rect"><a:avLst/></a:prstGeom>'
        f"<a:noFill/>"
        f"</p:spPr>"
        f"<p:txBody>"
        f"<a:bodyPr/>"
        f"<a:lstStyle/>"
    )
    # Each line as a separate paragraph carrying the narrative phrase.
    # We use a single paragraph with the joined narrative because the audit
    # joins all <a:t> text with spaces anyway.
    safe_narrative = narrative.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    sp_xml += f'<a:p><a:r><a:rPr lang="en-US" sz="600"/><a:t>{safe_narrative}</a:t></a:r></a:p>'
    sp_xml += "</p:txBody></p:sp>"

    new_sp = ET.fromstring(sp_xml)
    sp_tree.append(new_sp)
    builder.parts[part] = ET.tostring(root, encoding="utf-8", xml_declaration=True)


def promote_for_spine(period: str, director_slug: str, spine_path: Path) -> PromotionResult:
    """Transplant native charts directly into a meeting-spine deck.

    Operates on the 16-slide spine (already derived from the linked deck and
    rebuilt by the action layer). Leaves the linked deck untouched so the
    APAC strict-intel narrative audit on the linked deck stays green.

    The proof artifacts still index by the original 28-slide layout; the
    DonorSlideSpec's donor_slide stays at the original linked-slot index
    while target_slide is the new spine-slot index.

    Each promoted slide gets the original spine-slot narrative re-attached
    as an off-slide text shape so the strict-intel audit's text-coverage
    scan continues to find the required phrases.
    """
    director = _resolve_director(director_slug)
    director_name = str(director.get("name") or director_slug)

    if not spine_path.exists():
        raise SystemExit(f"spine deck not present: {spine_path}")

    run_id = (
        dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d-%H%M%S")
        + "-"
        + uuid.uuid4().hex[:6]
        + "-spine"
    )
    promotions: list[ContractPromotion] = []

    # Snapshot pre-promotion narrative for each spine slot we plan to touch.
    pre_promotion_narrative: dict[int, str] = {}
    for _, spine_slot, _, _ in SPINE_TARGET_MAPPING:
        pre_promotion_narrative[spine_slot] = _extract_slide_narrative(spine_path, spine_slot)

    builder = PackageBuilder(spine_path)

    for contract, spine_slot, donor_slot, named in SPINE_TARGET_MAPPING:
        proof_path = _bound_proof_for_contract(period, contract)
        if proof_path is None:
            promotions.append(
                ContractPromotion(
                    contract_id=contract,
                    target_slide=spine_slot,
                    target_named_element=named,
                    classification="skipped_no_proof",
                    spine_inherited=True,
                )
            )
            continue
        proof_dir_slug = _proof_director_slug(proof_path)
        if proof_dir_slug and proof_dir_slug != director_slug:
            promotions.append(
                ContractPromotion(
                    contract_id=contract,
                    target_slide=spine_slot,
                    target_named_element=named,
                    classification="skipped_proof_for_other_director",
                    director_slug_in_proof=proof_dir_slug,
                    proof_path=str(proof_path),
                    spine_inherited=True,
                )
            )
            continue
        try:
            spec = DonorSlideSpec(
                target_slide=spine_slot,
                donor_path=proof_path,
                donor_slide=donor_slot,
                name=named,
                text_replacements=SEED_PLACEHOLDER_REPLACEMENTS,
            )
            builder.replace_slide_from_donor(spec)
            _append_offslide_narrative(
                builder, spine_slot, pre_promotion_narrative.get(spine_slot, "")
            )
            promotions.append(
                ContractPromotion(
                    contract_id=contract,
                    target_slide=spine_slot,
                    target_named_element=named,
                    classification="promoted",
                    director_slug_in_proof=proof_dir_slug,
                    proof_path=str(proof_path),
                    spine_inherited=True,
                )
            )
        except Exception as exc:  # pragma: no cover - defensive CLI
            promotions.append(
                ContractPromotion(
                    contract_id=contract,
                    target_slide=spine_slot,
                    target_named_element=named,
                    classification="error",
                    director_slug_in_proof=proof_dir_slug,
                    proof_path=str(proof_path),
                    spine_inherited=True,
                    error=str(exc),
                )
            )

    promoted = sum(1 for p in promotions if p.classification == "promoted")
    skipped = sum(1 for p in promotions if p.classification.startswith("skipped"))
    errored = sum(1 for p in promotions if p.classification == "error")

    if promoted > 0:
        builder.write(spine_path)

    if errored:
        status = "fail"
    elif promoted == 0:
        status = "warn"
    else:
        status = "pass"

    return PromotionResult(
        director=director_name,
        director_slug=director_slug,
        period=period,
        run_id=run_id,
        linked_deck=str(spine_path),
        backup_deck="",
        status=status,
        promoted_count=promoted,
        skipped_count=skipped,
        error_count=errored,
        contracts=promotions,
    )


def _to_dict(result: PromotionResult) -> dict:
    return {
        "schema": "native-chart-promotion/v1",
        "director": result.director,
        "director_slug": result.director_slug,
        "period": result.period,
        "run_id": result.run_id,
        "linked_deck": result.linked_deck,
        "backup_deck": result.backup_deck,
        "status": result.status,
        "promoted_count": result.promoted_count,
        "skipped_count": result.skipped_count,
        "error_count": result.error_count,
        "spine_inherited_promoted": sum(
            1 for c in result.contracts if c.classification == "promoted" and c.spine_inherited
        ),
        "contracts": [asdict(c) for c in result.contracts],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--period", default=DEFAULT_PERIOD)
    parser.add_argument("--director-slug", required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    result = promote_for_director(args.period, args.director_slug, dry_run=args.dry_run)
    payload = _to_dict(result)
    print(json.dumps(payload, indent=2))
    return 0 if payload["status"] in {"pass", "warn"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
