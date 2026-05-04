"""Verify a tcseed PPTX against the binding registry.

Checks:
  - every required element name from the registry exists as a shape name
  - no forbidden text (dev instructions, donor placeholders, lorem ipsum)
  - no PowerPoint repair-prompt-prone constructs (off-canvas; future)

Forbidden text patterns are loaded from state/atlas/graph.json's
debris_signature nodes when available (single source of truth via the
atlas), falling back to a hard-coded list otherwise.

Outputs a JSON report and returns:
  0 — pass
  1 — fail (details in report)
  2 — usage error
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import yaml
from pptx import Presentation

REPO = Path(__file__).resolve().parent.parent
ATLAS_GRAPH = REPO / "state" / "atlas" / "graph.json"

FALLBACK_PATTERNS = [
    r"\[think-cell\b.*?\]",
    r"paste from\b.*",
    r"no think-cell binding here",
    r"lorem ipsum",
    r"click to add",
    r"\bUser count \[K\]\b",
    r"\[USD m\]",
    r"\bProduct A\b",
    r"\bBU1\b|\bBU2\b",
]


def _load_forbidden_patterns() -> list[re.Pattern[str]]:
    """Prefer atlas graph (debris_signature nodes); fallback to hard-coded list."""
    if ATLAS_GRAPH.exists():
        try:
            graph = json.loads(ATLAS_GRAPH.read_text())
            patterns = [
                n["key"]
                for n in graph.get("nodes", {}).values()
                if isinstance(n, dict) and n.get("kind") == "debris_signature"
            ]
            if patterns:
                return [re.compile(p, re.IGNORECASE) for p in patterns]
        except (json.JSONDecodeError, KeyError):
            pass
    return [re.compile(p, re.IGNORECASE) for p in FALLBACK_PATTERNS]


def _required_names_from_registry(registry: dict) -> set[str]:
    names: set[str] = set()
    for slide in registry["slides"]:
        for el in slide.get("elements", []):
            if el.get("required"):
                names.add(el["name"])
    return names


def _shape_names_from_pptx(template: Path) -> set[str]:
    prs = Presentation(str(template))
    names: set[str] = set()
    for slide in prs.slides:
        for shape in slide.shapes:
            if getattr(shape, "name", None):
                names.add(shape.name)
    return names


def _all_text_runs(template: Path) -> list[str]:
    prs = Presentation(str(template))
    out: list[str] = []
    for slide in prs.slides:
        for shape in slide.shapes:
            if shape.has_text_frame:
                for para in shape.text_frame.paragraphs:  # type: ignore[attr-defined]
                    for run in para.runs:
                        if run.text:
                            out.append(run.text)
    return out


def _scan_forbidden(texts: list[str], patterns: list[re.Pattern[str]]) -> list[dict]:
    findings: list[dict] = []
    for t in texts:
        for pat in patterns:
            if pat.search(t):
                findings.append({"pattern": pat.pattern, "text": t[:200]})
    return findings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--template", required=True, type=Path)
    parser.add_argument("--registry", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args(argv)

    if not args.template.exists():
        sys.stderr.write(f"template not found: {args.template}\n")
        return 2
    if not args.registry.exists():
        sys.stderr.write(f"registry not found: {args.registry}\n")
        return 2

    registry = yaml.safe_load(args.registry.read_text())
    required = _required_names_from_registry(registry)
    present = _shape_names_from_pptx(args.template)
    missing = sorted(required - present)

    patterns = _load_forbidden_patterns()
    forbidden = _scan_forbidden(_all_text_runs(args.template), patterns)
    pattern_source = "atlas" if ATLAS_GRAPH.exists() else "fallback"

    status = "pass" if not missing and not forbidden else "fail"
    report = {
        "status": status,
        "template": str(args.template),
        "registry": str(args.registry),
        "pattern_source": pattern_source,
        "required_elements_total": len(required),
        "required_elements_present": len(required & present),
        "required_elements_missing": missing,
        "forbidden_text": forbidden,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2))

    if status == "pass":
        print(
            f"OK: {len(required & present)}/{len(required)} required shapes present, no forbidden text (patterns: {pattern_source})"
        )
        return 0

    sys.stderr.write(json.dumps(report, indent=2) + "\n")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
