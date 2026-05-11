"""Apply a custom Power BI theme JSON to rpt_vp_ops_scorecard.

Patches `report.json.config.themeCollection.customTheme` with the contents
of a local theme JSON, then pushes via Fabric REST updateDefinition. Idempotent
— re-running with a modified theme overwrites the previous one.

The PBI `config` field is itself a JSON-encoded string (not a nested dict),
so we parse it, patch `themeCollection`, re-stringify, and put it back.

Usage:
    # Default: apply themes/rw_simcorp_consulting.json
    python3 -m scripts.sales.rw_apply_theme

    # Custom path
    python3 -m scripts.sales.rw_apply_theme --theme path/to/theme.json

    # Dry-run: show diff without pushing
    python3 -m scripts.sales.rw_apply_theme --dry-run

    # Strip any custom theme; revert to base CY24SU10
    python3 -m scripts.sales.rw_apply_theme --reset
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from scripts.sales.rw_add_visual import (
    REPORT_ID,
    WORKSPACE_ID,
    _token,
    get_current_report_json,
    push_report,
)

DEFAULT_THEME = (
    Path(__file__).resolve().parent.parent.parent / "themes" / "rw_simcorp_consulting.json"
)


def _load_theme(path: Path) -> dict:
    if not path.exists():
        raise SystemExit(f"  theme file not found: {path}")
    return json.loads(path.read_text())


def _patch_config(rj: dict, theme: dict | None) -> tuple[dict, dict]:
    """Patch `config` (JSON-string) to set or clear themeCollection.customTheme.

    Returns (before_themeCollection, after_themeCollection) for diff display.
    """
    cfg_str = rj.get("config", "{}")
    cfg = json.loads(cfg_str) if isinstance(cfg_str, str) else cfg_str

    before = json.loads(json.dumps(cfg.get("themeCollection", {})))  # deep copy

    cfg.setdefault("themeCollection", {})
    if theme is None:
        cfg["themeCollection"].pop("customTheme", None)
    else:
        # Strip our metadata keys before injection — PBI's validator may reject
        # unknown root-level keys.
        clean = {k: v for k, v in theme.items() if not k.startswith("_") and k != "$schema"}
        cfg["themeCollection"]["customTheme"] = {"name": clean.get("name", "Custom"), **clean}

    after = json.loads(json.dumps(cfg.get("themeCollection", {})))
    rj["config"] = json.dumps(cfg)
    return before, after


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[0])
    ap.add_argument(
        "--theme",
        default=str(DEFAULT_THEME),
        help=f"Path to theme JSON (default: {DEFAULT_THEME})",
    )
    ap.add_argument("--dry-run", action="store_true", help="Show planned change; don't push")
    ap.add_argument("--reset", action="store_true", help="Strip customTheme; revert to base")
    args = ap.parse_args()

    token = _token()
    print("fetching report.json...")
    rj = get_current_report_json(token)

    if args.reset:
        before, after = _patch_config(rj, None)
        print(f"  before: {json.dumps(before, indent=2)[:200]}")
        print(f"  after:  {json.dumps(after, indent=2)[:200]}")
    else:
        theme = _load_theme(Path(args.theme))
        print(
            f"  theme: {theme.get('name', '<unnamed>')} from {args.theme}"
            f" ({len(theme.get('visualStyles', {}))} visualType styles)"
        )
        before, after = _patch_config(rj, theme)
        print("\nbefore.themeCollection:")
        print(json.dumps(before, indent=2))
        print("\nafter.themeCollection (truncated):")
        # Don't dump the full theme; just show the keys
        if "customTheme" in after:
            ct = after["customTheme"]
            print(
                json.dumps(
                    {
                        "baseTheme": after.get("baseTheme"),
                        "customTheme": {
                            "name": ct.get("name"),
                            "_top_level_keys": sorted(ct.keys()),
                            "_visualStyles_count": len(ct.get("visualStyles", {})),
                        },
                    },
                    indent=2,
                )
            )

    if args.dry_run:
        print("\n--dry-run: not pushing")
        return

    print("\npushing...")
    push_report(token, rj)
    print(
        f"\ndone. open: https://app.fabric.microsoft.com/groups/{WORKSPACE_ID}/reports/{REPORT_ID}"
    )


if __name__ == "__main__":
    main()
