#!/usr/bin/env python3
"""Apply safe text-only polish to linked regional decks.

This is a post-build cleanup for the May 2026 batch. It does not touch
relationships, chart data, OLE objects, table-image links, or shape geometry.
It only rewrites visible text runs that are known donor/generic leftovers.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from _directors import canonical_directors
from ppttc_template import A_NS, P_NS, R_NS


ROOT = Path(__file__).resolve().parent.parent
MC_NS = "http://schemas.openxmlformats.org/markup-compatibility/2006"
VML_NS = "urn:schemas-microsoft-com:vml"
P14_NS = "http://schemas.microsoft.com/office/powerpoint/2010/main"
A14_NS = "http://schemas.microsoft.com/office/drawing/2010/main"
A16_NS = "http://schemas.microsoft.com/office/drawing/2014/main"

ET.register_namespace("", P_NS)
ET.register_namespace("a", A_NS)
ET.register_namespace("r", R_NS)
ET.register_namespace("mc", MC_NS)
ET.register_namespace("p14", P14_NS)
ET.register_namespace("a14", A14_NS)
ET.register_namespace("a16", A16_NS)

TEXT_REPLACEMENTS = {
    "Exec summary": "May operating summary",
    "By owner": "May pipeline by owner",
    "May pipeline by owner": "Owner pipeline coverage",
    "May Land+Expand unweighted ARR by owner, filtered to nonzero value for readability.": "Owner-level Land+Expand unweighted ARR, filtered to nonzero value for readability.",
    "Current Q2 readiness by owner, using workbook-supported rows only.": "Current Q2 readiness grouped by account owner, using workbook-supported rows only.",
    "Per-territory pipeline mix": "Territory pipeline mix",
    "2026-Q2 closeable Land+Expand ARR": "2026-Q2 closeable Land+Expand unweighted ARR",
    "Open Land+Expand beyond 2026-Q2": "Open Land+Expand unweighted ARR beyond 2026-Q2",
    "Open Land+Expand ARR by rep within director scope": "Open Land+Expand unweighted ARR by rep within director scope",
    "Open ARR by Account.BillingCountry within director scope": "Open Land+Expand unweighted ARR by country within director scope",
    "What moved this quarter — opening + new − won − lost = closing": "Land+Expand unweighted ARR movement; Renewal ACV excluded",
    "What moved this quarter - opening + new - won - lost = closing": "Land+Expand unweighted ARR movement; Renewal ACV excluded",
    "ARR (EUR)": "ARR (mEUR)",
    "Open ARR (EUR)": "Open ARR (mEUR)",
}
TITLE_MAP_PATH = ROOT / "config" / "director_facing_title_map.may_2026.json"


def _configured_replacements() -> dict[str, str]:
    replacements = dict(TEXT_REPLACEMENTS)
    if TITLE_MAP_PATH.exists():
        config = json.loads(TITLE_MAP_PATH.read_text(encoding="utf-8"))
        replacements.update({str(old): str(new) for old, new in (config.get("replacements") or {}).items()})
    return replacements


def slugify(value: str) -> str:
    return value.replace(" ", "-")


def _to_float(value: object) -> float:
    try:
        number = float(value or 0)
    except (TypeError, ValueError):
        return 0.0
    return number if math.isfinite(number) else 0.0


def _fmt_meur(value: object) -> str:
    return f"EUR {_to_float(value) / 1_000_000:.1f}M"


def _fmt_count(value: object) -> str:
    return str(int(round(_to_float(value))))


def _regional_intel(path: Path) -> dict[str, object]:
    try:
        slug = path.parent.name
        period = path.parent.parent.name
    except IndexError:
        return {}
    spec = ROOT / "state" / period / slug / "factory" / "regional_intelligence_spec.json"
    if not spec.exists():
        return {}
    return json.loads(spec.read_text(encoding="utf-8"))


def _regional_replacements(path: Path) -> dict[int, dict[str, str]]:
    """Return slide-specific replacements backed by regional_intelligence_spec.

    Key 0 means deck-wide. Slide keys are 1-indexed PowerPoint slide numbers.
    """

    spec = _regional_intel(path)
    if not spec:
        return {}
    if spec.get("territory") == "APAC":
        return {
            0: {
                "Refresh next-step evidence for Danantara, Krungthai, Temasek, and HKMA; LTH's next step points beyond the Q2 close date.": (
                    "Refresh next-step evidence for Danantara, Krungthai, Temasek, and HKMA; flag overdue-close exposure and August timing risk where next steps miss Q2."
                ),
                "Preserve the Q1 accountability spine while using the current workbook for live Q2 values.": (
                    "Preserve the Q1 accountability spine: Q1 opened EUR 17.1M, Q1 lost EUR 5.5M, Q1 slips EUR 9.4M."
                ),
                "Original APAC approval context: Coolabah and Danantara were approved in 2026; Amova remained pending/candidate.": (
                    "Original APAC Approved 2026 context: Coolabah and Danantara / EUR 3.8M; all-open approval scope was 7 gaps / EUR 10.7M; Amova remained pending/candidate."
                ),
                "Keep Q1 loss accountability and Q2 QTD losses as separate horizons.": (
                    "Original Q1 Land losses: 14 / EUR 5.5M; Missing reason code and Stage-at-loss mix need hygiene review; forecast accuracy was 1W / 16L, EUR 8.6M lost, 6% win rate."
                ),
                "Current all-open exposure plus original APAC concentration spine: top 7 open deals, top 5 = 89%.": (
                    "Current all-open exposure plus original APAC concentration spine: top 7 open deals / EUR 9.6M, top 5 = 89%, Amova Asset Management."
                ),
            },
            4: {
                "May review question: which named Q2 deals have customer proof, approval status, and dated next steps for the commit call?": (
                    "Original Q2 activity baseline: 6 deals / EUR 5.0M and zero recent activity. May review question: which named Q2 deals have customer proof, approval status, and dated next steps for the commit call?"
                ),
            },
        }

    original = spec.get("original_intelligence", {})
    gold = spec.get("gold_context", {})
    if not isinstance(original, dict):
        original = {}
    if not isinstance(gold, dict):
        gold = {}

    open_land = f"{_fmt_count(original.get('open_land_deals'))} deals / {_fmt_meur(original.get('open_land_arr_eur'))}"
    q1_losses = (
        f"{_fmt_count(original.get('q1_land_losses'))} losses / "
        f"{_fmt_meur(original.get('q1_land_lost_arr_eur'))}"
    )
    renewal_acv = _to_float(original.get("q2_q3_renewal_acv_eur"))
    renewal_label = _fmt_meur(renewal_acv) if renewal_acv > 0 else "No prior ACV"
    top5 = gold.get("top_5_share_pct")
    concentration_label = f"Top 5 = {float(top5):.0f}%" if isinstance(top5, (int, float)) else "Source attached"
    largest = ""
    largest_deals = gold.get("largest_deals")
    if isinstance(largest_deals, list) and largest_deals:
        first = largest_deals[0] if isinstance(largest_deals[0], dict) else {}
        account = str(first.get("account") or first.get("opportunity") or "largest deal")
        arr = _fmt_meur(first.get("arr_unweighted"))
        largest = f"Compare current exposure to original/gold concentration: {account[:42]} / {arr}."
    else:
        largest = "Compare current largest-deal exposure to the director's original/gold source pack."

    return {
        0: {
            "Use current workbook values; no director-specific prior-review target pack is attached.": (
                "Use the Apr 20 original ETL sidecar as the prior baseline and the Apr 30 workbook for May values."
            ),
            "No prior territory pack is applied for this director; keep the page limited to current workbook-supported facts.": (
                f"Original ETL baseline is attached: open Land {open_land}; Q1 Land losses {q1_losses}; live May actions use current workbook rows."
            ),
            "Do not infer prior approved deals from another territory pack.": (
                "Prior approval context must come from this director's ETL sidecar; current gaps remain workbook-supported."
            ),
            "Use workbook rows until a prior source pack is attached.": (
                "Original renewal ACV basis is source-labeled; validate against refreshed workbook before quoting."
            ),
            "Do not apply another territory's Q2 baseline to this director.": (
                "Use this director's original ETL sidecar for prior context; do not borrow another territory baseline."
            ),
            "Current all-open exposure; prior territory concentration spine is not applied.": (
                "Current all-open exposure plus this director's original ETL/gold concentration spine."
            ),
            "Current workbook risk triage; prior territory risk spine is not applied.": (
                "Current workbook risk triage plus this director's original territory risk spine."
            ),
            "Out-of-quarter context needs a director-specific source pack before it is added to this page.": (
                "Out-of-quarter context can use the director ETL/gold pack; May actions still tie to workbook rows."
            ),
        },
        4: {
            "Prior-review targets vs current state": "Original ETL targets vs current May state",
            "Prior-review targets": "Original ETL baseline",
            "Not attached": open_land,
            "Do not infer director-specific prior targets from another territory pack.": (
                f"Prior open Land {open_land}; Q1 Land losses {q1_losses}."
            ),
        },
        11: {
            "Prior baseline": "Original ETL baseline",
            "Not attached": renewal_label,
        },
        12: {
            "Prior FY26 baseline": "Original FY26 baseline",
            "Prior Q2 subset": "Original Q2 subset",
            "Not attached": renewal_label,
            "Use this director's source pack only.": "Source-label the ETL baseline and current workbook separately.",
            "No prior subset applied.": "Source-labeled where present.",
        },
        21: {
            "Prior baseline": "Original ETL baseline",
            "Prior concentration pack": "Original concentration pack",
            "Not attached": concentration_label,
            "Use current concentration metrics only for this director.": largest,
        },
    }


def _slide_xml(root: ET.Element) -> bytes:
    text = ET.tostring(root, encoding="unicode", xml_declaration=True)
    if 'Requires="v"' in text and "xmlns:v=" not in text:
        text = text.replace("<sld ", f'<sld xmlns:v="{VML_NS}" ', 1)
        text = text.replace("<p:sld ", f'<p:sld xmlns:v="{VML_NS}" ', 1)
    return text.encode("utf-8")


def _clean_donor_waterfall_label(text_nodes: list[ET.Element]) -> int:
    changes = 0
    values = [node.text or "" for node in text_nodes]
    for idx in range(0, max(0, len(values) - 4)):
        if values[idx : idx + 5] == ["Revenues, costs, ", "t", "otals [USD ", "m", "]"]:
            text_nodes[idx].text = "ARR (mEUR)"
            for node in text_nodes[idx + 1 : idx + 5]:
                node.text = ""
            changes += 1
    return changes


def _fix_slide(data: bytes, replacements: dict[str, str]) -> tuple[bytes, int]:
    root = ET.fromstring(data)
    text_nodes = list(root.iter(f"{{{A_NS}}}t"))
    changes = _clean_donor_waterfall_label(text_nodes)
    for node in text_nodes:
        original = node.text
        if not original:
            continue
        updated = original
        for old, new in replacements.items():
            updated = updated.replace(old, new)
        if updated != original:
            node.text = updated
            changes += 1
    if not changes:
        return data, 0
    return _slide_xml(root), changes


def polish_deck(path: Path) -> int:
    replacements = _configured_replacements()
    dynamic = _regional_replacements(path)
    with ZipFile(path) as zin:
        entries = {item.filename: zin.read(item.filename) for item in zin.infolist()}

    total = 0
    for name, data in list(entries.items()):
        if not (name.startswith("ppt/slides/slide") and name.endswith(".xml")):
            continue
        slide_replacements = dict(replacements)
        match = re.search(r"slide(\d+)\.xml$", name)
        slide_no = int(match.group(1)) if match else 0
        slide_replacements.update(dynamic.get(0, {}))
        slide_replacements.update(dynamic.get(slide_no, {}))
        fixed, changes = _fix_slide(data, slide_replacements)
        if changes:
            entries[name] = fixed
            total += changes

    if not total:
        return 0
    tmp_path = path.with_suffix(".tmp.pptx")
    with ZipFile(tmp_path, "w", ZIP_DEFLATED) as zout:
        for name, data in entries.items():
            zout.writestr(name, data)
    tmp_path.replace(path)
    return total


def target_decks(period: str, director_slug: str | None) -> list[Path]:
    if director_slug:
        return [ROOT / "state" / period / director_slug / f"{director_slug}-LAND-{period}-table-image-linked.pptx"]
    decks: list[Path] = []
    for director in canonical_directors():
        slug = slugify(str(director["name"]))
        decks.append(ROOT / "state" / period / slug / f"{slug}-LAND-{period}-table-image-linked.pptx")
    return decks


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--period", default="2026-Q2")
    parser.add_argument("--director-slug")
    args = parser.parse_args()

    for deck in target_decks(args.period, args.director_slug):
        if not deck.exists():
            raise SystemExit(f"missing deck: {deck}")
        changes = polish_deck(deck)
        print(f"{deck}: text_changes={changes}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
