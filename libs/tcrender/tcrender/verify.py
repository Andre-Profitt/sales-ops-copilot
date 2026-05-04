"""Post-render verification: confirm that bindings actually landed in a .pptx.

ppttc.exe returns exit-code 0 even when most bindings fail to resolve; the
rendered .pptx silently lacks director-specific content. This module scans
the rendered .pptx and asserts that a caller-provided list of expected
strings actually appears somewhere in the slide XML.

Public API
~~~~~~~~~~

* :class:`VerifyResult` -- frozen result of :func:`verify_render`.
* :func:`verify_render` -- scan a rendered .pptx for a list of expected
  strings and report which ones landed.
* :func:`binding_evidence_strings` -- walk a .ppttc and return concrete
  strings the rendered .pptx should contain (director name, period, scope
  label, top account names, formatted ARR values, etc.).

Pure stdlib + lxml. ASCII-only.
"""

from __future__ import annotations

import json
import re
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from lxml import etree

# Strings shorter than this are treated as too-generic to count as evidence
# of a real render. ``"no"`` or ``"7"`` could appear anywhere in a deck for
# unrelated reasons; ``"Jesper Tyrer"`` cannot.
_MIN_EVIDENCE_LEN = 4

# Strings that match this regex are too generic / too likely to appear in
# template boilerplate (stage labels, headers, legend titles). They are NOT
# strong evidence of a successful render and are filtered out by
# ``binding_evidence_strings``.
_BORING_PATTERNS: tuple[re.Pattern[str], ...] = (
    # "1 - Prospecting", "2 - Discovery": digit, REQUIRED space, hyphen,
    # REQUIRED space, then a letter. The required spaces stop us flagging
    # "2026-Q2" (which has neither space).
    re.compile(r"^\s*\d+ - [A-Za-z]"),
    re.compile(r"^\s*[A-Z]{1,3}\s*$"),  # "ARR", "EUR" by itself
    re.compile(r"^(yes|no|true|false|n/?a|none|null|tbd)$", re.IGNORECASE),
)

# Slide XML parts. Verification only scans slide bodies; layouts/masters are
# template scaffolding and don't contain the substituted values.
_NS = {"a": "http://schemas.openxmlformats.org/drawingml/2006/main"}


@dataclass(frozen=True)
class VerifyResult:
    """Outcome of :func:`verify_render`.

    Attributes:
        found: Expected strings that DID appear in the rendered .pptx slide
            XML, in the order they were checked.
        missing: Expected strings that did NOT appear, in the order they
            were checked.
        match_ratio: ``len(found) / len(expected_strings)``; ``1.0`` when no
            strings were expected.
        passed: ``match_ratio >= min_match_ratio``.
        scanned_xml_parts: Number of slide-XML parts inspected (for
            diagnostics).
    """

    found: tuple[str, ...]
    missing: tuple[str, ...]
    match_ratio: float
    passed: bool
    scanned_xml_parts: int


def verify_render(
    output_pptx_path: Path,
    expected_strings: list[str] | tuple[str, ...],
    min_match_ratio: float = 0.5,
) -> VerifyResult:
    """Scan a rendered .pptx for ``expected_strings`` and report match ratio.

    Concatenates all <a:t> text-run content from every
    ``ppt/slides/slide*.xml`` part. For each entry in ``expected_strings``,
    checks whether the entry appears (substring match, case-sensitive) in
    the concatenated text.

    Args:
        output_pptx_path: Path to the rendered .pptx.
        expected_strings: Strings the caller expects to appear in the
            rendered slides. Empty iterable -> ``passed=True`` with
            ``match_ratio=1.0`` (vacuous pass).
        min_match_ratio: Minimum fraction of ``expected_strings`` that must
            be found for ``passed=True``. Default ``0.5``.

    Returns:
        :class:`VerifyResult`.

    Raises:
        FileNotFoundError: if ``output_pptx_path`` does not exist.
        zipfile.BadZipFile: if ``output_pptx_path`` is not a valid .pptx.
        ValueError: if ``min_match_ratio`` is outside ``[0.0, 1.0]``.
    """
    output_pptx_path = output_pptx_path.expanduser().resolve()
    if not output_pptx_path.exists():
        raise FileNotFoundError(f"output not found: {output_pptx_path}")
    if not (0.0 <= min_match_ratio <= 1.0):
        raise ValueError(f"min_match_ratio must be in [0,1]; got {min_match_ratio}")

    expected = tuple(expected_strings)

    haystack, scanned = _slides_text_blob(output_pptx_path)

    found_list: list[str] = []
    missing_list: list[str] = []
    for s in expected:
        if not isinstance(s, str):
            raise TypeError(f"expected_strings must contain str; got {type(s).__name__}")
        if s and s in haystack:
            found_list.append(s)
        else:
            missing_list.append(s)

    if not expected:
        ratio = 1.0
    else:
        ratio = len(found_list) / len(expected)
    passed = ratio >= min_match_ratio

    return VerifyResult(
        found=tuple(found_list),
        missing=tuple(missing_list),
        match_ratio=round(ratio, 4),
        passed=passed,
        scanned_xml_parts=scanned,
    )


def binding_evidence_strings(ppttc_path: Path) -> list[str]:
    """Walk a .ppttc and return concrete strings the rendered .pptx should contain.

    Heuristics (all conservative -- err on the side of NOT flagging a string
    as evidence rather than flagging boilerplate):

    1. Scalar string bindings (``[[{string: <val>}]]``): emit the value as
       evidence iff it is at least :data:`_MIN_EVIDENCE_LEN` characters and
       does not match a "boring" pattern (stage labels, single-word "yes"
       / "no", currency tickers, etc.).
    2. Multi-row tabular bindings: extract every cell with
       ``{string: <val>}`` shape and apply the same boring-string filter.
       Numeric cells (``{number: <n>}``) are NOT emitted because formatting
       depends on think-cell number-format rules and we don't want false
       failures.

    Strings are returned in the order they appear in the .ppttc, deduplicated
    while preserving first-seen order.

    Args:
        ppttc_path: Path to the .ppttc JSON file.

    Returns:
        Ordered list of unique evidence strings.

    Raises:
        FileNotFoundError: if ``ppttc_path`` does not exist.
        ValueError: if the .ppttc top-level shape is wrong.
    """
    ppttc_path = ppttc_path.expanduser().resolve()
    text = ppttc_path.read_text(encoding="utf-8")
    parsed = json.loads(text)
    if not isinstance(parsed, list) or not parsed:
        raise ValueError(f".ppttc must be a non-empty JSON array: {ppttc_path}")

    seen: set[str] = set()
    out: list[str] = []
    for entry in parsed:
        if not isinstance(entry, dict):
            continue
        data = entry.get("data")
        if not isinstance(data, list):
            continue
        for binding in data:
            if not isinstance(binding, dict):
                continue
            table = binding.get("table")
            if not isinstance(table, list):
                continue
            for row in table:
                if not isinstance(row, list):
                    continue
                for cell in row:
                    if not isinstance(cell, dict):
                        continue
                    val = cell.get("string")
                    if not isinstance(val, str):
                        continue
                    if not _is_evidence_string(val):
                        continue
                    if val in seen:
                        continue
                    seen.add(val)
                    out.append(val)
    return out


# -- internals -------------------------------------------------------------


def _slides_text_blob(pptx_path: Path) -> tuple[str, int]:
    """Return concatenated <a:t> text from all slide-XML parts.

    Returns ``(blob, scanned_count)``. The blob preserves text order within
    each slide and concatenates slide bodies with single newlines so
    multi-line expected strings (e.g. exec-summary bullets that span <a:t>
    runs) still match where appropriate -- but cross-slide false matches
    don't bleed into one another via a single space.
    """
    parts: list[str] = []
    scanned = 0
    with zipfile.ZipFile(pptx_path, "r") as zf:
        for name in zf.namelist():
            if not _is_slide_xml(name):
                continue
            scanned += 1
            try:
                root = etree.fromstring(zf.read(name))
            except etree.XMLSyntaxError:
                continue
            slide_chunks: list[str] = []
            for t in root.iter(f"{{{_NS['a']}}}t"):
                if t.text:
                    slide_chunks.append(t.text)
            parts.append("".join(slide_chunks))
    return ("\n".join(parts), scanned)


def _is_slide_xml(name: str) -> bool:
    if not name.startswith("ppt/slides/"):
        return False
    tail = name[len("ppt/slides/") :]
    if not tail.startswith("slide") or not tail.endswith(".xml"):
        return False
    middle = tail[len("slide") : -len(".xml")]
    return middle.isdigit()


def _is_evidence_string(value: str) -> bool:
    """Decide whether ``value`` is unique enough to count as evidence."""
    s = value.strip()
    if len(s) < _MIN_EVIDENCE_LEN:
        return False
    for pat in _BORING_PATTERNS:
        if pat.match(s):
            return False
    return True


def _truthy_for_test(_x: Any) -> bool:
    """Internal -- placeholder for future heuristics; never raise."""
    return True


__all__ = [
    "VerifyResult",
    "binding_evidence_strings",
    "verify_render",
]
