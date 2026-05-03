"""Validate the LAND think-cell chart injection contract.

The production chart path has three places that must stay aligned:
1. `.ppttc` data entries emitted by `build_ppttc.py`.
2. named donor charts in `build_thinkcell_seed_template.py`.
3. chart slides copied by `_windows_test/merge_charts_into_layout.ps1`.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from build_thinkcell_seed_template import CHART_DONORS  # noqa: E402
from ppttc_template import CHART_INJECTIONS, template_named_elements  # noqa: E402


def _ppttc_chart_names() -> set[str]:
    text = (ROOT / "scripts" / "build_ppttc.py").read_text()
    return set(re.findall(r'_chart_entry\(\s*"([^"]+)"', text))


def _merge_chart_slides() -> list[int]:
    text = (ROOT / "_windows_test" / "merge_charts_into_layout.ps1").read_text()
    match = re.search(r"\$chartSlides\s*=\s*@\((.*?)\)", text, re.S)
    if not match:
        raise SystemExit("merge_charts_into_layout.ps1 does not define $chartSlides")
    return [int(value) for value in re.findall(r"\d+", match.group(1))]


def _assert_equal(label: str, left: set[str | int], right: set[str | int]) -> None:
    if left == right:
        return
    missing = sorted(right - left)
    extra = sorted(left - right)
    raise SystemExit(f"{label} mismatch: missing={missing} extra={extra}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--seed",
        type=Path,
        default=ROOT / "assets" / "LAND_thinkcell_seed.pptx",
        help="Seed template to check for named chart elements.",
    )
    args = parser.parse_args()

    ppttc_names = _ppttc_chart_names()
    donor_names = {donor.name for donor in CHART_DONORS}
    injection_names = {injection.chart_name for injection in CHART_INJECTIONS}

    donor_slides = {donor.target_slide for donor in CHART_DONORS}
    injection_slides = {injection.slide_number for injection in CHART_INJECTIONS}
    merge_slides = set(_merge_chart_slides())

    expected_count = 12
    if len(ppttc_names) != expected_count:
        raise SystemExit(f"build_ppttc.py emits {len(ppttc_names)} chart names, expected {expected_count}")
    if len(CHART_INJECTIONS) != expected_count:
        raise SystemExit(f"CHART_INJECTIONS has {len(CHART_INJECTIONS)} entries, expected {expected_count}")
    if len(_merge_chart_slides()) != expected_count:
        raise SystemExit(f"$chartSlides has {len(_merge_chart_slides())} entries, expected {expected_count}")

    _assert_equal("ppttc vs seed donor chart names", ppttc_names, donor_names)
    _assert_equal("ppttc vs injection chart names", ppttc_names, injection_names)
    _assert_equal("seed donor vs injection slides", donor_slides, injection_slides)
    _assert_equal("injection vs merge slides", injection_slides, merge_slides)

    if args.seed.exists():
        seed_names = template_named_elements(args.seed)
        missing_seed_names = sorted(injection_names - seed_names)
        if missing_seed_names:
            raise SystemExit(f"{args.seed} is missing chart names: {missing_seed_names}")

    print(
        "ok chart injection contract "
        f"charts={len(injection_names)} slides={','.join(str(s) for s in sorted(injection_slides))}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
