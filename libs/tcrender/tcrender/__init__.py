"""tcrender: Mac-side wrapper around think-cell ppttc.exe headless render.

Production deck-render path for the LAND factory. Pairs with
scripts/build_ppttc.py (emits the .ppttc input). Sibling lib
libs/tc_com_driver covers COM-dispatch utility flows (UpdateBatch,
PresentationFromTemplate) and is not the production bulk-render path.

Public API:
    TcRenderClient   -- high-level client; .render() and .validate_ppttc()
    Transport        -- abstract transport interface
    SSHTransport     -- concrete SSH-based transport (default host: Windows-VM)
    RenderResult     -- frozen dataclass returned by .render()
    ValidationResult -- frozen dataclass returned by .validate_ppttc()
    RenderError      -- raised when ppttc.exe exits non-zero or transport fails
    QualityGateError -- subclass raised when ``quality_gate=True`` and gate fails

    template_prep -- substitute Jinja-style ``{key}`` placeholders in donor
        .pptx templates before ppttc.exe touches them.
        scan_placeholders, substitute_placeholders, binding_name_to_placeholder,
        extract_scalar_string_bindings.
    verify -- post-render evidence check that bindings actually landed.
        VerifyResult, verify_render, binding_evidence_strings.
    quality -- production quality gate (verify + jinja-leak + completeness +
        optional brand check). GateFailure, GateResult, gate_render.
    archive -- per-director archival tree + audit.json sidecar.
        archive_render, ARCHIVE_AUDIT_FILENAME.
"""

from __future__ import annotations

from . import (
    archive,
    master_transplant,
    narrative,
    narrative_templates,
    native_fallback,
    polish_pass as polish_pass_module,
    quality,
    template_polish,
    template_prep,
    verify,
)
from .archive import ARCHIVE_AUDIT_FILENAME, archive_render
from .master_transplant import (
    MASTER_PARTS_PREFIXES,
    TransplantResult,
    extract_wired_tcfield_bindings,
    transplant_visual_identity,
)
from .models import RenderError, RenderResult, ValidationResult
from .narrative import (
    DirectorContext,
    NarrativeError,
    generate_chart_insight,
    generate_exec_summary,
    generate_risks_outlook,
)
from .narrative_templates import (
    NARRATIVE_TEMPLATES,
    extract_templates_from_deck,
    populate_narrative,
    render_style_guide,
)
from .native_fallback import BRAND_PALETTE, EnhanceResult, enhance_deck
from .polish_pass import (
    POLISH_PASS_AUDIT_KEY,
    PolishPassResult,
    polish_pass,
)
from .quality import GateFailure, GateResult, QualityGateError, gate_render
from .render import TcRenderClient
from .template_polish import (
    PolishResult,
    SectionDivider,
    add_footer_to_master,
    add_section_dividers,
    embed_thinkcell_style,
    polish_template,
)
from .template_prep import (
    binding_name_to_placeholder,
    extract_scalar_string_bindings,
    scan_placeholders,
    substitute_placeholders,
)
from .transport import SSHTransport, Transport
from .verify import VerifyResult, binding_evidence_strings, verify_render

__all__ = [
    "ARCHIVE_AUDIT_FILENAME",
    "BRAND_PALETTE",
    "DirectorContext",
    "EnhanceResult",
    "GateFailure",
    "GateResult",
    "MASTER_PARTS_PREFIXES",
    "NARRATIVE_TEMPLATES",
    "NarrativeError",
    "POLISH_PASS_AUDIT_KEY",
    "PolishPassResult",
    "PolishResult",
    "QualityGateError",
    "RenderError",
    "RenderResult",
    "SSHTransport",
    "SectionDivider",
    "TcRenderClient",
    "Transport",
    "TransplantResult",
    "ValidationResult",
    "VerifyResult",
    "add_footer_to_master",
    "add_section_dividers",
    "archive",
    "archive_render",
    "binding_evidence_strings",
    "binding_name_to_placeholder",
    "embed_thinkcell_style",
    "enhance_deck",
    "extract_scalar_string_bindings",
    "extract_templates_from_deck",
    "extract_wired_tcfield_bindings",
    "gate_render",
    "generate_chart_insight",
    "generate_exec_summary",
    "generate_risks_outlook",
    "master_transplant",
    "narrative",
    "narrative_templates",
    "native_fallback",
    "polish_pass",
    "polish_template",
    "populate_narrative",
    "quality",
    "render_style_guide",
    "scan_placeholders",
    "substitute_placeholders",
    "template_polish",
    "template_prep",
    "transplant_visual_identity",
    "verify",
    "verify_render",
]
__version__ = "0.3.0"
