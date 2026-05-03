"""Frozen dataclasses for tcrender results and the public exception type.

`RenderResult` summarizes a single ppttc.exe run end-to-end. `ValidationResult`
captures the outcome of a .ppttc shape check against the official schema.
`RenderError` is the only exception type the library raises for transport or
ppttc.exe failures (FileNotFoundError / ValueError still surface for caller
input mistakes).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


class RenderError(RuntimeError):
    """Raised when ppttc.exe returns non-zero or the transport fails."""


@dataclass(frozen=True)
class RenderResult:
    """Structured summary of one .ppttc -> .pptx render run.

    Attributes:
        input_ppttc: Mac-side path to the source .ppttc.
        output_path: Mac-side path where the rendered .pptx was ferried.
        output_size_bytes: Size of the ferried .pptx on disk.
        exit_code: ppttc.exe process exit code (0 = success).
        elapsed_seconds: Total wall-clock time including stage + ppttc + ferry.
        ssh_stdout_tail: Last ~2 KiB of ppttc.exe stdout for diagnostics.
        ssh_stderr_tail: Last ~2 KiB of ppttc.exe stderr for diagnostics.
    """

    input_ppttc: Path
    output_path: Path
    output_size_bytes: int
    exit_code: int
    elapsed_seconds: float
    ssh_stdout_tail: str
    ssh_stderr_tail: str


@dataclass(frozen=True)
class ValidationResult:
    """Outcome of a structural check against the ppttc-schema.json shape.

    Attributes:
        valid: True iff every required key is present and binding entries
            conform to {name: str, table: list[list]}.
        errors: Human-readable error strings (empty when valid).
        binding_count: Total number of {name, table} bindings across all
            top-level template-objects (counted regardless of validity).
    """

    valid: bool
    errors: tuple[str, ...]
    binding_count: int
