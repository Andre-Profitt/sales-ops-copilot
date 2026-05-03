#!/usr/bin/env python3
"""Finalize linked think-cell table images in PowerPoint for Mac.

Excel/think-cell `AddRangeImage` refreshes the linked table-image objects, but
PowerPoint can leave each object in a comparison/carryover state until the
user selects it and clicks Finish. This script automates that final UI step and
then applies the deck factory's exact table-image geometry.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parent.parent
CLICLICK = Path("/opt/homebrew/bin/cliclick")


@dataclass(frozen=True)
class TableImageTarget:
    name: str
    slide: int
    left: float
    top: float
    width: float
    height: float


TARGETS: tuple[TableImageTarget, ...] = (
    TableImageTarget("S04_ReviewDeltaTargets", 4, 41.00, 149.00, 877.76, 137.80),
    TableImageTarget("S05_ForecastQualityTable", 5, 41.00, 242.43, 409.45, 192.91),
    TableImageTarget("S06_HygieneSignals", 6, 41.00, 149.00, 877.76, 334.93),
    TableImageTarget("S07_TopDealsLand", 7, 41.00, 149.00, 877.76, 335.60),
    TableImageTarget("S08_TopDealsExpand", 8, 41.00, 149.00, 877.76, 335.60),
    TableImageTarget("S09_PendingCommercialApproval", 9, 41.00, 285.00, 877.76, 78.00),
    TableImageTarget("S11_RenewalPipeline", 11, 41.00, 244.79, 877.76, 236.94),
    TableImageTarget("S12_GRRProxyTable", 12, 41.00, 243.21, 877.76, 127.56),
    TableImageTarget("S13_ForecastCategoryDetail", 13, 586.41, 149.00, 301.84, 173.23),
    TableImageTarget("S16_OwnerCoaching", 16, 41.00, 232.19, 877.76, 251.90),
    TableImageTarget("S18_QTDLossSpine", 18, 471.00, 258.17, 417.25, 225.91),
    TableImageTarget("S19_DealHygieneSignals", 19, 41.00, 149.00, 877.76, 185.04),
    TableImageTarget("S21_ConcentrationTable", 21, 468.50, 161.42, 437.01, 181.10),
    TableImageTarget("S22_NamedRiskTriage", 22, 41.00, 149.00, 877.76, 185.04),
    TableImageTarget("S23_OperatingRhythm", 23, 41.00, 149.00, 877.76, 208.66),
    TableImageTarget("S24_AccountExpansion", 24, 41.00, 238.49, 877.76, 245.60),
    TableImageTarget("S25_Next14DaysCadence", 25, 41.00, 149.00, 877.76, 335.60),
    TableImageTarget("S26_ActionItems", 26, 41.00, 149.00, 877.76, 190.00),
    TableImageTarget("S27_DecisionChecklist", 27, 41.00, 149.00, 877.76, 335.60),
)


def _run(command: list[str], *, check: bool = True, input_text: str | None = None) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        command,
        text=True,
        input=input_text,
        capture_output=True,
        check=False,
    )
    if check and completed.returncode != 0:
        sys.stderr.write(completed.stdout)
        sys.stderr.write(completed.stderr)
        raise SystemExit(completed.returncode)
    return completed


def _osascript(script: str) -> str:
    return _run(["osascript"], input_text=script).stdout.strip()


def _applescript_text(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _desktop_bounds() -> tuple[int, int]:
    raw = _osascript('tell application "Finder" to get bounds of window of desktop')
    parts = [int(part.strip()) for part in raw.split(",")]
    if len(parts) != 4:
        raise SystemExit(f"unexpected desktop bounds: {raw}")
    return parts[2] - parts[0], parts[3] - parts[1]


def _screenshot(path: Path) -> None:
    _run(["screencapture", "-x", str(path)])


def _carryover_banner_visible(path: Path) -> bool:
    with Image.open(path) as image:
        rgb = image.convert("RGB")
        width, height = rgb.size
        # The carryover banner sits below the ribbon. Detect the red arrow
        # instead of relying on OCR or inaccessible Office UI controls.
        x0, x1 = int(width * 0.12), int(width * 0.42)
        y0, y1 = int(height * 0.16), int(height * 0.23)
        crop = rgb.crop((x0, y0, x1, y1))
        red_pixels = 0
        pixel_data = getattr(crop, "get_flattened_data", crop.getdata)()
        for r, g, b in pixel_data:
            if r > 150 and g < 105 and b < 120:
                red_pixels += 1
        return red_pixels > 800


def _manual_carryover_dialog_visible(path: Path) -> bool:
    with Image.open(path) as image:
        rgb = image.convert("RGB")
        width, height = rgb.size
        # The black think-cell warning dialog appears over the slide body.
        # Keep this crop away from the dark ribbon so normal Office chrome
        # does not trip the detector.
        crop = rgb.crop((int(width * 0.15), int(height * 0.21), int(width * 0.52), int(height * 0.46)))
        pixel_data = getattr(crop, "get_flattened_data", crop.getdata)()
        black_pixels = sum(1 for r, g, b in pixel_data if r < 45 and g < 45 and b < 45)
        return black_pixels > 60000


def _finish_click_position(screenshot_path: Path) -> tuple[int, int]:
    logical_width, logical_height = _desktop_bounds()
    with Image.open(screenshot_path) as image:
        physical_width, physical_height = image.size
    scale_x = physical_width / logical_width
    scale_y = physical_height / logical_height
    return round((physical_width * 0.56) / scale_x), round((physical_height * 0.193) / scale_y)


def _manual_carryover_click_position(screenshot_path: Path) -> tuple[int, int]:
    logical_width, logical_height = _desktop_bounds()
    with Image.open(screenshot_path) as image:
        physical_width, physical_height = image.size
    scale_x = physical_width / logical_width
    scale_y = physical_height / logical_height
    return round((physical_width * 0.382) / scale_x), round((physical_height * 0.468) / scale_y)


def _click_finish(screenshot_path: Path) -> None:
    if not CLICLICK.exists():
        raise SystemExit(f"missing cliclick: {CLICLICK}")
    x, y = _finish_click_position(screenshot_path)
    _run([str(CLICLICK), f"c:{x},{y}"])


def _click_manual_carryover(screenshot_path: Path) -> None:
    if not CLICLICK.exists():
        raise SystemExit(f"missing cliclick: {CLICLICK}")
    x, y = _manual_carryover_click_position(screenshot_path)
    _run([str(CLICLICK), f"c:{x},{y}"])


def _open_deck(deck: Path) -> None:
    _osascript(
        f"""
tell application "Microsoft PowerPoint"
  activate
  open POSIX file {_applescript_text(str(deck))}
  set view type of document window 1 to slide view
end tell
"""
    )


def _select_target(target: TableImageTarget) -> None:
    _osascript(
        f"""
tell application "Microsoft PowerPoint"
  activate
  set view type of document window 1 to slide view
  go to slide (view of document window 1) number {target.slide}
  set currentSlide to slide {target.slide} of active presentation
  set tableImageShape to missing value
  repeat with i from (count of shapes of currentSlide) to 1 by -1
    set candidateShape to shape i of currentSlide
    if name of candidateShape is "Pic" then
      set tableImageShape to candidateShape
      exit repeat
    end if
  end repeat
  if tableImageShape is missing value then error "missing Pic shape on slide {target.slide}"
  select tableImageShape
end tell
"""
    )


def _resize_target(target: TableImageTarget) -> None:
    _osascript(
        f"""
tell application "Microsoft PowerPoint"
  activate
  set currentSlide to slide {target.slide} of active presentation
  set tableImageShape to missing value
  repeat with i from 1 to count of shapes of currentSlide
    set candidateShape to shape i of currentSlide
    if name of candidateShape is "think-cell data - do not delete" or name of candidateShape is "Pic" then
      set lock aspect ratio of candidateShape to false
      set left position of candidateShape to {target.left}
      set top of candidateShape to {target.top}
      set width of candidateShape to {target.width}
      set height of candidateShape to {target.height}
    end if
    if name of candidateShape is "Pic" then set tableImageShape to candidateShape
  end repeat
  if tableImageShape is missing value then error "missing Pic shape on slide {target.slide}"
  set lock aspect ratio of tableImageShape to false
  set left position of tableImageShape to {target.left}
  set top of tableImageShape to {target.top}
  set width of tableImageShape to {target.width}
  set height of tableImageShape to {target.height}
end tell
"""
    )


def _save_active(close: bool) -> None:
    close_line = "close active presentation saving yes" if close else ""
    _osascript(
        f"""
tell application "Microsoft PowerPoint"
  activate
  save active presentation
  {close_line}
end tell
"""
    )


def _parse_slides(value: str | None) -> set[int] | None:
    if not value:
        return None
    return {int(part.strip()) for part in value.split(",") if part.strip()}


def finalize(deck: Path, *, slides: set[int] | None, screenshot_dir: Path, close: bool) -> None:
    deck = deck.expanduser().resolve()
    if not deck.exists():
        raise SystemExit(f"missing deck: {deck}")
    screenshot_dir.mkdir(parents=True, exist_ok=True)
    targets = [target for target in TARGETS if slides is None or target.slide in slides]
    if not targets:
        raise SystemExit("no table-image targets selected")

    _open_deck(deck)
    accepted = 0
    manual_dialogs = 0
    finalized = 0
    with tempfile.TemporaryDirectory(prefix="tc-finalize-") as tmp:
        tmp_dir = Path(tmp)
        for target in targets:
            _select_target(target)
            time.sleep(0.25)
            shot = tmp_dir / f"slide-{target.slide:02d}.png"
            _screenshot(shot)
            if _manual_carryover_dialog_visible(shot):
                _click_manual_carryover(shot)
                manual_dialogs += 1
                time.sleep(0.5)
                _screenshot(shot)
            if _carryover_banner_visible(shot):
                _click_finish(shot)
                accepted += 1
                time.sleep(0.5)
                verify_shot = tmp_dir / f"slide-{target.slide:02d}-after-finish.png"
                _screenshot(verify_shot)
                if _carryover_banner_visible(verify_shot):
                    _click_finish(verify_shot)
                    time.sleep(0.5)
                    _screenshot(verify_shot)
                if _carryover_banner_visible(verify_shot):
                    raise SystemExit(f"carryover banner still visible on slide {target.slide}")
                if screenshot_dir:
                    verify_shot.replace(screenshot_dir / verify_shot.name)
            _resize_target(target)
            time.sleep(0.1)
            finalized += 1
    _save_active(close)
    print(f"finalized={finalized} manual_dialogs={manual_dialogs} accepted_carryover={accepted} deck={deck}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("deck", type=Path)
    parser.add_argument("--slides", help="Comma-separated slide numbers. Defaults to all table-image slides.")
    parser.add_argument("--screenshot-dir", type=Path, default=ROOT / "_rendered" / "thinkcell_finalize")
    parser.add_argument("--close", action="store_true", help="Close the presentation after saving.")
    args = parser.parse_args()

    finalize(
        args.deck,
        slides=_parse_slides(args.slides),
        screenshot_dir=args.screenshot_dir,
        close=args.close,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
