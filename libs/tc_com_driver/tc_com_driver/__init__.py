"""tc_com_driver — pywin32 wrapper around think-cell's documented COM surface.

Public API:
    - `ThinkCellClient` — context-managed entry point. Finds PowerPoint,
      locates the think-cell add-in, exposes `pp` / `xl` wrappers.
    - `PpAddIn`     — wraps `IPpMacroInterface` (19 user-visible methods).
    - `XlAddIn`     — wraps `IXlMacroInterface` (3 user-visible methods).
    - `UpdateBatch` — wraps `IUpdateBatch`      (3 user-visible methods).
    - Exception classes derived from `ThinkCellError`.

See `CLAUDE.md` for usage and platform requirements. Windows-only at runtime;
on non-Windows hosts `ThinkCellClient.connect()` raises `WrongPlatformError`
(imports themselves succeed so callers can introspect the API everywhere).
"""

from __future__ import annotations

from tc_com_driver.client import ThinkCellClient
from tc_com_driver.errors import (
    PowerPointNotRunningError,
    ThinkCellError,
    ThinkCellNotActiveError,
    ThinkCellNotFoundError,
    WrongPlatformError,
)
from tc_com_driver.pp_addin import PP_MACRO_IID, PpAddIn
from tc_com_driver.update_batch import UPDATE_BATCH_IID, UpdateBatch
from tc_com_driver.xl_addin import XL_MACRO_IID, XlAddIn

__all__ = [
    "PP_MACRO_IID",
    "PowerPointNotRunningError",
    "PpAddIn",
    "ThinkCellClient",
    "ThinkCellError",
    "ThinkCellNotActiveError",
    "ThinkCellNotFoundError",
    "UPDATE_BATCH_IID",
    "UpdateBatch",
    "WrongPlatformError",
    "XL_MACRO_IID",
    "XlAddIn",
]

__version__ = "0.1.0"
