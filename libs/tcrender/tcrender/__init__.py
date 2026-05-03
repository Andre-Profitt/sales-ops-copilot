"""tcrender: Mac-side wrapper around think-cell ppttc.exe headless render.

Public API:
    TcRenderClient   -- high-level client; .render() and .validate_ppttc()
    Transport        -- abstract transport interface
    SSHTransport     -- concrete SSH-based transport (default host: Windows-VM)
    RenderResult     -- frozen dataclass returned by .render()
    ValidationResult -- frozen dataclass returned by .validate_ppttc()
    RenderError      -- raised when ppttc.exe exits non-zero or transport fails
"""

from __future__ import annotations

from .models import RenderError, RenderResult, ValidationResult
from .render import TcRenderClient
from .transport import SSHTransport, Transport

__all__ = [
    "RenderError",
    "RenderResult",
    "SSHTransport",
    "TcRenderClient",
    "Transport",
    "ValidationResult",
]
__version__ = "0.1.0"
