"""High-level `TcRenderClient`: validate + render via a `Transport`.

Validation walks the documented ppttc-schema.json shape (an array of
{template: str, data: [{name: str, table: list[list]}]}). The check is
intentionally structural: full type validation per cell is deferred to
ppttc.exe itself which already implements the canonical schema.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from .models import RenderError, RenderResult, ValidationResult
from .transport import (
    DEFAULT_TIMEOUT_SECONDS,
    SSHTransport,
    Transport,
)

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
    ) -> RenderResult:
        """Render a .ppttc to a .pptx via ppttc.exe over the transport.

        Args:
            ppttc_path: Mac-side .ppttc input.
            output_path: Mac-side .pptx destination (overwritten if present).
            template_override: optional Mac-side donor .pptx; rewrites all
                entries[].template to the staged path before invocation.
            timeout: hard wall-clock cap for ppttc.exe in seconds.
            keep_stage_files: if True, do not delete the VM-local stage dir.

        Returns:
            RenderResult with size, exit code, elapsed time, and stdout/stderr
            tails.

        Raises:
            FileNotFoundError if ppttc_path or template_override does not exist.
            ValueError if the .ppttc fails the structural validator.
            RenderError on ppttc.exe non-zero exit, transport failure, timeout,
            or missing/empty ferried output.
        """
        ppttc_path = ppttc_path.expanduser().resolve()
        output_path = output_path.expanduser().resolve()

        v = self.validate_ppttc(ppttc_path)
        if not v.valid:
            raise ValueError(f".ppttc failed structural validation: {'; '.join(v.errors[:5])}")

        t0 = time.monotonic()
        run = self.transport.run_render(
            ppttc_path=ppttc_path,
            output_path=output_path,
            template_override=template_override,
            timeout=timeout,
            keep_stage_files=keep_stage_files,
        )
        # Wall-clock of the whole call (stage + ppttc + ferry). The transport
        # tracks ppttc.exe alone in its `elapsed_seconds`; we report the full
        # round-trip here for consistency with the public API contract.
        elapsed = round(time.monotonic() - t0, 3)
        if run.output_size_bytes <= 0:
            raise RenderError(f"ferried output is zero-bytes: {output_path}")

        return RenderResult(
            input_ppttc=ppttc_path,
            output_path=output_path,
            output_size_bytes=run.output_size_bytes,
            exit_code=run.exit_code,
            elapsed_seconds=elapsed,
            ssh_stdout_tail=run.stdout,
            ssh_stderr_tail=run.stderr,
        )


# Re-export for convenience
__all__ = ["TcRenderClient"]


def _public_models() -> tuple[type, ...]:
    """Tiny helper to keep mypy/static checkers happy with re-exports."""
    return (RenderResult, ValidationResult)


_ = _public_models  # silence unused-import lints in narrow checkers
_ANY: Any = None  # type: ignore[assignment]
