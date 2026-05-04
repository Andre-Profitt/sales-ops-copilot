"""High-level `TcRenderClient`: validate + render via a `Transport`.

Validation walks the documented ppttc-schema.json shape (an array of
{template: str, data: [{name: str, table: list[list]}]}). The check is
intentionally structural: full type validation per cell is deferred to
ppttc.exe itself which already implements the canonical schema.
"""

from __future__ import annotations

import dataclasses
import json
import time
from pathlib import Path
from typing import Any

from .archive import archive_render
from .models import RenderError, RenderResult, ValidationResult
from .quality import GateResult, QualityGateError, gate_render
from .template_prep import (
    extract_scalar_string_bindings,
    substitute_placeholders,
)
from .transport import (
    DEFAULT_TIMEOUT_SECONDS,
    SSHTransport,
    Transport,
)
from .verify import binding_evidence_strings, verify_render

# Optional schema lookup: the official ppttc-schema.json may be cached locally
# under state/thinkcell_bridge/official_docs_corpus/<ts>/ppttc-schema.json.
# When present, we use it for one extra cross-check (top-level type=array).
# Absent file is non-fatal -- we still run the structural check.
_SCHEMA_FILE_NAME = "ppttc-schema.json"


class TcRenderClient:
    """Public client. Validate .ppttc shapes; render .ppttc -> .pptx."""

    def __init__(
        self,
        transport: Transport | None = None,
        schema_path: Path | None = None,
    ) -> None:
        self.transport: Transport = transport or SSHTransport()
        self.schema_path = schema_path

    # -- validation --------------------------------------------------------

    def validate_ppttc(self, ppttc_path: Path) -> ValidationResult:
        """Validate a .ppttc file structurally against the documented schema.

        Returns a `ValidationResult`. The check is intentionally structural --
        ppttc.exe is the authoritative type-checker for cell payloads. We
        verify:
            - top-level is a non-empty JSON array
            - each entry is an object with required keys `template`, `data`
            - `template` is a non-empty string (path or http/https URL)
            - `data` is a list of {name: str, table: list[list]} objects

        Args:
            ppttc_path: path to the .ppttc file.

        Returns:
            ValidationResult.binding_count is the total count of {name, table}
            entries across all top-level objects (counted regardless of
            whether the file ultimately validates).
        """
        ppttc_path = ppttc_path.expanduser().resolve()
        errors: list[str] = []
        binding_count = 0
        try:
            text = ppttc_path.read_text(encoding="utf-8")
        except FileNotFoundError as exc:
            return ValidationResult(valid=False, errors=(str(exc),), binding_count=0)
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError as exc:
            return ValidationResult(valid=False, errors=(f"invalid JSON: {exc}",), binding_count=0)

        if not isinstance(parsed, list):
            errors.append(f"top-level must be JSON array, got {type(parsed).__name__}")
            return ValidationResult(valid=False, errors=tuple(errors), binding_count=0)
        if not parsed:
            errors.append("top-level array is empty")
            return ValidationResult(valid=False, errors=tuple(errors), binding_count=0)

        for i, entry in enumerate(parsed):
            if not isinstance(entry, dict):
                errors.append(f"[{i}] not an object")
                continue
            tpl = entry.get("template")
            data = entry.get("data")
            if not isinstance(tpl, str) or not tpl:
                errors.append(f"[{i}].template missing or not a non-empty string")
            if not isinstance(data, list):
                errors.append(f"[{i}].data missing or not a list")
                continue
            for j, b in enumerate(data):
                binding_count += 1
                if not isinstance(b, dict):
                    errors.append(f"[{i}].data[{j}] not an object")
                    continue
                if "name" not in b or not isinstance(b["name"], str) or not b["name"]:
                    errors.append(f"[{i}].data[{j}].name missing or not a non-empty string")
                if "table" not in b or not isinstance(b["table"], list):
                    errors.append(f"[{i}].data[{j}].table missing or not a list")
                    continue
                for k, row in enumerate(b["table"]):
                    if not isinstance(row, list):
                        errors.append(f"[{i}].data[{j}].table[{k}] is not a list (row)")

        # Optional cross-check against shipped schema -- top-level type only.
        # Full JSON-Schema validation would pull in jsonschema; we keep
        # tcrender stdlib-only and let ppttc.exe do the canonical validation.
        if self.schema_path and self.schema_path.exists():
            try:
                schema = json.loads(self.schema_path.read_text(encoding="utf-8"))
                if schema.get("type") != "array":
                    errors.append("schema top-level type is not 'array' -- check schema_path")
            except (json.JSONDecodeError, OSError) as exc:
                errors.append(f"schema cross-check failed: {exc}")

        return ValidationResult(valid=not errors, errors=tuple(errors), binding_count=binding_count)

    # -- render ------------------------------------------------------------

    def render(
        self,
        ppttc_path: Path,
        output_path: Path,
        template_override: Path | None = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        keep_stage_files: bool = False,
        prep_jinja: bool = True,
        verify: bool = True,
        verify_min_match_ratio: float = 0.5,
        extra_evidence_strings: list[str] | None = None,
        quality_gate: bool = False,
        quality_gate_min_match_ratio: float = 0.6,
        quality_gate_brand_check: bool = False,
        quality_gate_strict: bool = False,
        archive_to: Path | None = None,
        archive_director: str | None = None,
        archive_period: str | None = None,
        archive_audit: dict[str, Any] | None = None,
    ) -> RenderResult:
        """Render a .ppttc to a .pptx via ppttc.exe over the transport.

        Args:
            ppttc_path: Mac-side .ppttc input.
            output_path: Mac-side .pptx destination (overwritten if present).
            template_override: optional Mac-side donor .pptx; rewrites all
                entries[].template to the staged path before invocation.
            timeout: hard wall-clock cap for ppttc.exe in seconds.
            keep_stage_files: if True, do not delete the VM-local stage dir.
            prep_jinja: if True (default), pre-substitute Jinja-style
                ``{key}`` placeholders in the donor template before invoking
                ppttc.exe. Bindings are auto-extracted from the .ppttc by
                :func:`tcrender.template_prep.extract_scalar_string_bindings`.
                When ``template_override`` is None, prep_jinja is a no-op
                (we don't have a donor file to substitute).
            verify: if True (default), after the render, scan the rendered
                .pptx for evidence strings derived from the .ppttc bindings
                via :func:`tcrender.verify.binding_evidence_strings`. Raise
                :class:`RenderError` if fewer than ``verify_min_match_ratio``
                of those strings appear in the output.
            verify_min_match_ratio: minimum fraction of evidence strings
                that must appear in the rendered .pptx for verification to
                pass. Default 0.5.
            extra_evidence_strings: optional caller-provided strings to add
                to the auto-derived evidence list (e.g. formatted ARR
                values, custom labels not present in scalar bindings).
            quality_gate: if True, run the production quality gate
                (verify-match-ratio + jinja-leak + completeness) after the
                render. The gate result is logged into the audit sidecar
                when ``archive_to`` is set; ``quality_gate_strict=True``
                turns gate failures into ``QualityGateError``.
            quality_gate_min_match_ratio: floor passed to ``gate_render``.
                Default 0.6 (tighter than verify-only default).
            quality_gate_brand_check: forwarded to ``gate_render``.
            quality_gate_strict: if True, raise ``QualityGateError`` when
                the gate reports any failure.
            archive_to: if set, archive the rendered .pptx into
                ``<archive_to>/<archive_period>/<archive_director>/decks/<ts>/``
                with an ``audit.json`` sidecar. ``archive_director`` and
                ``archive_period`` are required when this is set.
            archive_director: director slug used for archival.
            archive_period: period label used for archival.
            archive_audit: optional pre-built audit payload merged into
                ``audit.json`` (e.g. fix-id flags from the emitting
                ``build_ppttc.py``).

        Returns:
            RenderResult with size, exit code, elapsed time, and stdout/stderr
            tails. When ``archive_to`` is set, ``RenderResult.output_path``
            points at the archived location.

        Raises:
            FileNotFoundError if ppttc_path or template_override does not exist.
            ValueError if the .ppttc fails the structural validator.
            RenderError on ppttc.exe non-zero exit, transport failure, timeout,
            missing/empty ferried output, or (when ``verify=True``) missing
            director-specific content in the rendered .pptx.
            QualityGateError if ``quality_gate=True`` and
            ``quality_gate_strict=True`` and the gate fails.
        """
        ppttc_path = ppttc_path.expanduser().resolve()
        output_path = output_path.expanduser().resolve()

        v = self.validate_ppttc(ppttc_path)
        if not v.valid:
            raise ValueError(f".ppttc failed structural validation: {'; '.join(v.errors[:5])}")

        # Optionally pre-substitute Jinja-style placeholders in the donor
        # template before ppttc.exe touches it. We only do this when the
        # caller supplied a template_override -- we will not silently rewrite
        # the embedded `template` path of the .ppttc.
        effective_template = template_override
        if prep_jinja and template_override is not None:
            bindings = extract_scalar_string_bindings(ppttc_path)
            if bindings:
                effective_template = substitute_placeholders(
                    template_path=template_override,
                    bindings=bindings,
                    output_path=None,
                )

        t0 = time.monotonic()
        run = self.transport.run_render(
            ppttc_path=ppttc_path,
            output_path=output_path,
            template_override=effective_template,
            timeout=timeout,
            keep_stage_files=keep_stage_files,
        )
        # Wall-clock of the whole call (stage + ppttc + ferry). The transport
        # tracks ppttc.exe alone in its `elapsed_seconds`; we report the full
        # round-trip here for consistency with the public API contract.
        elapsed = round(time.monotonic() - t0, 3)
        if run.output_size_bytes <= 0:
            raise RenderError(f"ferried output is zero-bytes: {output_path}")

        # Optionally verify the rendered output contains expected
        # director-specific strings. Empty evidence list -> verification
        # is a no-op (vacuous pass).
        if verify:
            evidence = binding_evidence_strings(ppttc_path)
            if extra_evidence_strings:
                evidence.extend(s for s in evidence if s)
                evidence.extend(s for s in extra_evidence_strings if s and s not in evidence)
            if evidence:
                vr = verify_render(
                    output_pptx_path=output_path,
                    expected_strings=evidence,
                    min_match_ratio=verify_min_match_ratio,
                )
                if not vr.passed:
                    pct_missing = round((1.0 - vr.match_ratio) * 100.0, 1)
                    sample_missing = ", ".join(repr(s) for s in vr.missing[:5])
                    raise RenderError(
                        f"rendered output is missing {pct_missing}% of expected "
                        f"director-specific content "
                        f"(found {len(vr.found)}/{len(evidence)}, "
                        f"min_ratio={verify_min_match_ratio}); "
                        f"missing sample: [{sample_missing}]"
                    )

        result = RenderResult(
            input_ppttc=ppttc_path,
            output_path=output_path,
            output_size_bytes=run.output_size_bytes,
            exit_code=run.exit_code,
            elapsed_seconds=elapsed,
            ssh_stdout_tail=run.stdout,
            ssh_stderr_tail=run.stderr,
        )

        # Quality gate (off by default). The gate runs against the
        # rendered file BEFORE archival so failures are reported on the
        # path the caller asked for. When archival is also enabled, the
        # gate result rides in the audit sidecar regardless of strictness.
        gate_result: GateResult | None = None
        if quality_gate:
            gate_result = gate_render(
                result=result,
                ppttc_path=ppttc_path,
                min_match_ratio=quality_gate_min_match_ratio,
                require_no_jinja_leak=True,
                brand_check=quality_gate_brand_check,
                extra_evidence_strings=extra_evidence_strings,
            )
            if quality_gate_strict and not gate_result.passed:
                reasons = "; ".join(f.reason for f in gate_result.failures)
                raise QualityGateError(f"quality gate failed: {reasons}")

        # Archival: move rendered .pptx to the per-director tree and emit
        # audit.json. Returns the archived path; we mint a new RenderResult
        # so callers see the on-disk truth.
        if archive_to is not None:
            if not archive_director or not archive_period:
                raise ValueError("archive_to requires archive_director and archive_period")
            extra_audit: dict[str, Any] = {}
            if gate_result is not None:
                extra_audit["quality_gate"] = _gate_result_to_dict(gate_result)
            archived_path = archive_render(
                result=result,
                director=archive_director,
                period=archive_period,
                audit=archive_audit or {},
                archive_root=archive_to,
                template_path=template_override,
                ppttc_path=ppttc_path,
                extra_audit=extra_audit,
            )
            result = dataclasses.replace(result, output_path=archived_path)

        return result


def _gate_result_to_dict(gate: GateResult) -> dict[str, Any]:
    """Serialize a GateResult for audit.json (JSON-stable)."""
    return {
        "passed": gate.passed,
        "binding_count": gate.binding_count,
        "bindings_with_evidence": gate.bindings_with_evidence,
        "jinja_leaks": list(gate.jinja_leaks),
        "verify_match_ratio": gate.verify.match_ratio if gate.verify else None,
        "failures": [
            {"check": f.check, "reason": f.reason, "details": dict(f.details)}
            for f in gate.failures
        ],
    }


# Re-export for convenience
__all__ = ["TcRenderClient"]


def _public_models() -> tuple[type, ...]:
    """Tiny helper to keep mypy/static checkers happy with re-exports."""
    return (RenderResult, ValidationResult)


_ = _public_models  # silence unused-import lints in narrow checkers
_ANY: Any = None  # type: ignore[assignment]
