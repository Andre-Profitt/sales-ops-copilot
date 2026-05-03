"""Custom exception types for tc_com_driver.

All errors derive from `ThinkCellError` so callers can catch the whole family.
Errors are raised with actionable messages — never silently swallow.
"""

from __future__ import annotations


class ThinkCellError(Exception):
    """Base class for every tc_com_driver-specific error."""


class WrongPlatformError(ThinkCellError):
    """Raised when `ThinkCellClient.connect()` is invoked on a non-Windows OS.

    `pywin32` and the underlying COM dispatch are Windows-only. This driver
    has no useful Mac/Linux behavior beyond surfacing this error and letting
    callers route around it.
    """


class PowerPointNotRunningError(ThinkCellError):
    """Raised when no PowerPoint instance is available and one cannot be launched.

    Distinct from `ThinkCellNotFoundError`: PowerPoint itself is missing or
    we lack permission to start it. think-cell may still be installed.
    """


class ThinkCellNotFoundError(ThinkCellError):
    """Raised when no think-cell add-in is registered on the running PowerPoint.

    The add-in's `ProgID` / `Description` did not match any of the
    case-insensitive variants we look for under `Application.COMAddIns`.
    """


class ThinkCellNotActiveError(ThinkCellError):
    """Raised when think-cell is registered but `Connect == False`.

    The add-in is installed but disabled in PowerPoint's COM-Add-Ins UI.
    Callers can either ask the user to enable it, or call
    `PpAddIn.activate_add_in(True)` if they hold the IPpMacroInterface
    handle through another path.
    """
