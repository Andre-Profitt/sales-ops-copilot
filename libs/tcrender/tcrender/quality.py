"""Quality gate for the LAND deck factory.

Bundles the verify-render evidence check with two extra checks that are
cheap to compute and surface load-bearing problems other gates won't catch:

1. **Jinja-leak scan** -- raw ``{director_name}`` / ``{period}`` /
   ``{scope_label}`` placeholders that survived into the rendered slide
   XML. think-cell never substitutes those (they're plain text in the
   template); we substitute them via ``tcrender.template_prep`` BEFORE
   ppttc.exe runs. If a placeholder leaks past the gate, Jinja pre-pass
   silently failed.

2. **Completeness** -- count how many .ppttc bindings have evidence in
   the rendered slides. The verify match-ratio already does this with a
   single pass, but we surface it as a separate failure so callers can
   tune the floor independently of ``min_match_ratio``.

3. **Brand check** -- placeholder for future SimCorp colour / font /
   layout enforcement. Today returns ``passed=True`` with a TODO
   string; wired so the gate is callable from production code that will
   tighten over time without an API change.

Each check produces its own ``GateFailure``; callers can decide whether
to fail-stop or warn. ``QualityGateError`` is the lib-level escape hatch
for ``TcRenderClient.render(quality_gate=True)``.

Pure stdlib + lxml. ASCII-only.
"""

from __future__ import annotations

import json
import re
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

from lxml import etree

from .models import RenderError, RenderResult
from .verify import VerifyResult, binding_evidence_strings, verify_render

# Slide XML parts -- gates only inspect slide bodies, not layouts/masters.
_SLIDE_GLOB_PREFIX = "ppt/slides/slide"
_NS = {"a": "http://schemas.openxmlformats.org/drawingml/2006/main"}

# Match Jinja-style ``{key}`` literals: snake_case identifier (must start
# with a letter) wrapped in single braces. Mirrors the substitution regex
# in ``tcrender.template_prep`` so the gate flags exactly what a properly
# patched template would NOT contain.
_JINJA_LEAK_RE = re.compile(r"\{([a-z][a-z0-9_]*)\}")

# Default jinja-leak whitelist: keys legitimately allowed to survive into
# the rendered output (none today; reserved for future).
_DEFAULT_LEAK_WHITELIST: frozenset[str] = frozenset()


class QualityGateError(RenderError):
    """Raised when ``gate_render`` is called and any required check fails."""


@dataclass(frozen=True)
class GateFailure:
    """Single failed quality check.

    Attributes:
        check: short identifier (``"verify_match_ratio"``,
            ``"no_jinja_leak"``, ``"completeness"``, ``"brand_check"``).
        reason: human-readable explanation including the observed metric
            and the failing threshold.
        details: structured payload for callers that want to forward to a
            log / alert pipeline. Always JSON-serializable.
    """

    check: str
    reason: str
    details: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class GateResult:
    """Outcome of :func:`gate_render`.

    Attributes:
        passed: True iff every required check passed.
        failures: structured failures (empty when ``passed=True``).
        verify: the underlying ``VerifyResult`` if ``verify_match_ratio``
            ran; ``None`` if the .ppttc had no evidence strings (vacuous
            pass) or evidence-list construction failed.
        binding_count: total ``data[]`` bindings across the .ppttc; used
            by completeness.
        bindings_with_evidence: count of bindings whose evidence appeared
            in the rendered .pptx slide XML.
        jinja_leaks: keys (without braces) that survived into rendered
            slides; empty when no leak was detected.
    """

    passed: bool
    failures: tuple[GateFailure, ...]
    verify: VerifyResult | None
    binding_count: int
    bindings_with_evidence: int
    jinja_leaks: tuple[str, ...]


def gate_render(
    result: RenderResult,
    ppttc_path: Path,
    *,
    min_match_ratio: float = 0.6,
    require_no_jinja_leak: bool = True,
    brand_check: bool = False,
    leak_whitelist: frozenset[str] | None = None,
    extra_evidence_strings: list[str] | None = None,
) -> GateResult:
    """Apply the quality gate to a finished render.

    Args:
        result: ``RenderResult`` from :class:`tcrender.TcRenderClient`.
        ppttc_path: Path to the .ppttc that produced the render. Used to
            derive evidence strings and the binding count.
        min_match_ratio: minimum fraction of evidence strings that must
            land in the rendered .pptx to pass ``verify_match_ratio``.
            Default ``0.6`` -- tighter than the verify-only default of
            ``0.5`` because the gate runs on production output.
        require_no_jinja_leak: if True (default), the gate fails when
            any ``{key}`` placeholder survives in slide XML.
        brand_check: if True, run the brand check (today: stub returning
            pass with a TODO note in details).
        leak_whitelist: optional set of placeholder keys allowed to leak
            (e.g. literal ``{0}`` style runs). Defaults to empty.
        extra_evidence_strings: optional caller-provided strings to add
            to the auto-derived evidence list (mirrors the same kwarg
            on ``TcRenderClient.render``).

    Returns:
        :class:`GateResult` -- always returned; ``raise`` is the caller's
        decision (use ``QualityGateError`` for that).

    Raises:
        FileNotFoundError: if ``result.output_path`` or ``ppttc_path``
            does not exist.
        ValueError: if ``min_match_ratio`` is outside ``[0.0, 1.0]``.
    """
    if not (0.0 <= min_match_ratio <= 1.0):
        raise ValueError(f"min_match_ratio must be in [0,1]; got {min_match_ratio}")

    output_path = Path(result.output_path).expanduser().resolve()
    ppttc_path = Path(ppttc_path).expanduser().resolve()
    if not output_path.exists():
        raise FileNotFoundError(f"render output not found: {output_path}")
    if not ppttc_path.exists():
        raise FileNotFoundError(f".ppttc not found: {ppttc_path}")

    failures: list[GateFailure] = []
    whitelist = leak_whitelist if leak_whitelist is not None else _DEFAULT_LEAK_WHITELIST

    # 1. Evidence-based verify check.
    evidence: list[str] = binding_evidence_strings(ppttc_path)
    if extra_evidence_strings:
        evidence.extend(s for s in extra_evidence_strings if s and s not in evidence)
    verify: VerifyResult | None = None
    if evidence:
        verify = verify_render(
            output_pptx_path=output_path,
            expected_strings=evidence,
            min_match_ratio=min_match_ratio,
        )
        if not verify.passed:
            failures.append(
                GateFailure(
                    check="verify_match_ratio",
                    reason=(
                        f"verify_render match_ratio={verify.match_ratio} < floor={min_match_ratio}"
                    ),
                    details={
                        "match_ratio": verify.match_ratio,
                        "min_match_ratio": min_match_ratio,
                        "expected_count": len(evidence),
                        "found_count": len(verify.found),
                        "missing_sample": list(verify.missing[:5]),
                    },
                )
            )

    # 2. Jinja-leak scan.
    leaks = _scan_jinja_leaks(output_path, whitelist=whitelist)
    if require_no_jinja_leak and leaks:
        failures.append(
            GateFailure(
                check="no_jinja_leak",
                reason=(
                    f"{len(leaks)} jinja-style placeholder(s) survived in slide XML: "
                    + ", ".join(repr(k) for k in sorted(leaks))
                ),
                details={"leaked_keys": sorted(leaks)},
            )
        )

    # 3. Completeness -- proportion of bindings that landed.
    binding_count = _ppttc_binding_count(ppttc_path)
    bindings_with_evidence = len(verify.found) if verify is not None else binding_count
    completeness_floor = int(round(binding_count * min_match_ratio))
    if binding_count > 0 and bindings_with_evidence < completeness_floor:
        failures.append(
            GateFailure(
                check="completeness",
                reason=(
                    f"only {bindings_with_evidence}/{binding_count} bindings have "
                    f"evidence in rendered output; floor={completeness_floor} "
                    f"({int(min_match_ratio * 100)}%)"
                ),
                details={
                    "binding_count": binding_count,
                    "bindings_with_evidence": bindings_with_evidence,
                    "floor": completeness_floor,
                    "min_match_ratio": min_match_ratio,
                },
            )
        )

    # 4. Brand check -- stubbed.
    if brand_check:
        brand_failure = _brand_check_stub(output_path)
        if brand_failure is not None:
            failures.append(brand_failure)

    return GateResult(
        passed=not failures,
        failures=tuple(failures),
        verify=verify,
        binding_count=binding_count,
        bindings_with_evidence=bindings_with_evidence,
        jinja_leaks=tuple(sorted(leaks)),
    )


# -- internals -------------------------------------------------------------


def _is_slide_xml(name: str) -> bool:
    if not name.startswith(_SLIDE_GLOB_PREFIX):
        return False
    tail = name[len("ppt/slides/") :]
    if not tail.startswith("slide") or not tail.endswith(".xml"):
        return False
    middle = tail[len("slide") : -len(".xml")]
    return middle.isdigit()


def _scan_jinja_leaks(pptx_path: Path, *, whitelist: frozenset[str]) -> set[str]:
    """Return ``{key}`` placeholder names that survived in slide XML.

    Searches every <a:t> text-run; matches snake_case identifiers wrapped
    in single braces (mirrors ``template_prep._PLACEHOLDER_RE``). Keys in
    ``whitelist`` are skipped.
    """
    leaks: set[str] = set()
    with zipfile.ZipFile(pptx_path, "r") as zf:
        for name in zf.namelist():
            if not _is_slide_xml(name):
                continue
            try:
                root = etree.fromstring(zf.read(name))
            except etree.XMLSyntaxError:
                continue
            for t in root.iter(f"{{{_NS['a']}}}t"):
                text = t.text or ""
                if "{" not in text:
                    continue
                for match in _JINJA_LEAK_RE.finditer(text):
                    key = match.group(1)
                    if key not in whitelist:
                        leaks.add(key)
    return leaks


def _ppttc_binding_count(ppttc_path: Path) -> int:
    """Count ``data[]`` bindings; ``0`` on any error or wrong shape."""
    try:
        parsed = json.loads(ppttc_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return 0
    if not isinstance(parsed, list):
        return 0
    total = 0
    for entry in parsed:
        if isinstance(entry, dict) and isinstance(entry.get("data"), list):
            total += len(entry["data"])
    return total


def _brand_check_stub(_output_path: Path) -> GateFailure | None:
    """Stub for future SimCorp brand enforcement.

    Today returns ``None`` (pass) and leaves a TODO note; future
    implementations should validate the SimCorp colour palette + Open
    Sans font + slide-master geometry.
    """
    # Intentionally never fails: the contract is "callable today, real
    # later". Rev the contract by returning a GateFailure when SimCorp
    # brand metadata is wired into the verify-able output.
    return None


__all__ = [
    "GateFailure",
    "GateResult",
    "QualityGateError",
    "gate_render",
]
