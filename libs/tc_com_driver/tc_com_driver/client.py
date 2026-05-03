"""`ThinkCellClient` — context manager that finds and connects the add-in.

The connect path:

1. Refuse on non-Windows (`WrongPlatformError`).
2. Find a running PowerPoint via `win32com.client.GetActiveObject`, or
   launch one via `Dispatch("PowerPoint.Application")`.
3. Walk `Application.COMAddIns` for a registered think-cell add-in
   (matching `ProgID` or `Description` substring, case-insensitive).
4. If found but `Connect == False`, raise `ThinkCellNotActiveError`.
5. Wrap the `.Object` dispatch in `PpAddIn`. Excel-side `XlAddIn` is
   resolved on demand via `client.xl` (think-cell launches Excel itself
   when needed; we only attach if the user provides an Excel app).
"""

from __future__ import annotations

import sys
from types import TracebackType
from typing import Any

from tc_com_driver.errors import (
    PowerPointNotRunningError,
    ThinkCellNotActiveError,
    ThinkCellNotFoundError,
    WrongPlatformError,
)
from tc_com_driver.pp_addin import PpAddIn
from tc_com_driver.xl_addin import XlAddIn

# ProgID / description tokens we accept as "this is think-cell". Matched
# case-insensitively against `COMAddIn.ProgID` and `COMAddIn.Description`.
_THINKCELL_TOKENS: tuple[str, ...] = ("think-cell", "thinkcell")


def _is_windows() -> bool:
    return sys.platform == "win32"


def _matches_thinkcell(addin: Any) -> bool:
    """Return True when `addin` is a registered think-cell add-in."""
    for attr in ("ProgID", "Description"):
        try:
            value = getattr(addin, attr, None)
        except Exception:  # noqa: BLE001 — pywin32 surfaces COMError as anything
            value = None
        if not value:
            continue
        text = str(value).lower()
        if any(tok in text for tok in _THINKCELL_TOKENS):
            return True
    return False


def _find_addin(host_app: Any) -> Any:
    """Locate the think-cell COMAddIn on a host (PowerPoint or Excel) app.

    Returns:
        The matching COMAddIn dispatch.

    Raises:
        ThinkCellNotFoundError: no add-in matched.
        ThinkCellNotActiveError: matched but `Connect == False`.
    """
    addins = host_app.COMAddIns
    count = int(getattr(addins, "Count", 0))
    matched: Any = None
    for i in range(1, count + 1):  # COM collections are 1-indexed
        addin = addins.Item(i)
        if _matches_thinkcell(addin):
            matched = addin
            break
    if matched is None:
        raise ThinkCellNotFoundError(
            "No think-cell COM add-in registered on the host application. "
            "Verify install via PowerPoint > Options > Add-Ins > COM Add-Ins."
        )
    if not bool(getattr(matched, "Connect", False)):
        raise ThinkCellNotActiveError(
            "think-cell add-in is registered but disabled (Connect=False). "
            "Enable it in COM Add-Ins, or call PpAddIn.activate_add_in(True) "
            "if you already hold an IPpMacroInterface handle."
        )
    return matched


class ThinkCellClient:
    """Context-managed think-cell client.

    Use as `with ThinkCellClient.connect() as client: ...`. Holds a
    PowerPoint `Application` reference and a `PpAddIn` wrapper. The
    `XlAddIn` wrapper is built lazily via `attach_excel(excel_app)`.
    """

    __slots__ = (
        "_powerpoint",
        "_pp_addin",
        "_xl_addin",
        "_owns_powerpoint",
    )

    def __init__(
        self,
        powerpoint: Any,
        pp_addin: PpAddIn,
        owns_powerpoint: bool = False,
    ) -> None:
        self._powerpoint = powerpoint
        self._pp_addin = pp_addin
        self._xl_addin: XlAddIn | None = None
        self._owns_powerpoint = owns_powerpoint

    # -- factories -----------------------------------------------------------

    @classmethod
    def connect(cls, launch_if_missing: bool = True) -> "ThinkCellClient":
        """Connect to a running PowerPoint and locate the think-cell add-in.

        Args:
            launch_if_missing: If True (default), spawn a new PowerPoint
                instance when none is running. If False, raise
                `PowerPointNotRunningError` instead.

        Raises:
            WrongPlatformError: when running on a non-Windows OS.
            PowerPointNotRunningError: PowerPoint is not running and we
                were told (or unable) to launch it.
            ThinkCellNotFoundError: PowerPoint is up but think-cell is
                not registered.
            ThinkCellNotActiveError: think-cell is registered but disabled.
        """
        if not _is_windows():
            raise WrongPlatformError(
                f"tc_com_driver requires Windows; current platform={sys.platform!r}. "
                "pywin32 + COM dispatch are Windows-only."
            )

        # Lazy-import: pywin32 is only available on Windows. The smoke-on-Mac
        # path raises `WrongPlatformError` before we get here, so this import
        # is safe by construction. Wrap in a try to give a clear error if
        # pywin32 is missing on a Windows host.
        try:
            import pythoncom  # noqa: F401  (initializes COM apartment)
            import win32com.client as win32com_client
        except ImportError as exc:  # pragma: no cover — Windows-host-only branch
            raise WrongPlatformError(
                "pywin32 is not installed on this Windows host; run `pip install pywin32>=308`."
            ) from exc

        powerpoint, owns = cls._acquire_powerpoint(win32com_client, launch_if_missing)
        addin = _find_addin(powerpoint)
        pp_dispatch = addin.Object  # IPpMacroInterface dispatch
        return cls(
            powerpoint=powerpoint,
            pp_addin=PpAddIn(pp_dispatch),
            owns_powerpoint=owns,
        )

    @staticmethod
    def _acquire_powerpoint(win32com_client: Any, launch_if_missing: bool) -> tuple[Any, bool]:
        """Return `(powerpoint_app, owns_it)` or raise."""
        try:
            return win32com_client.GetActiveObject("PowerPoint.Application"), False
        except Exception:  # noqa: BLE001 — COMError when no instance
            if not launch_if_missing:
                raise PowerPointNotRunningError(
                    "No running PowerPoint instance and launch_if_missing=False."
                ) from None
        try:
            app = win32com_client.Dispatch("PowerPoint.Application")
        except Exception as exc:  # noqa: BLE001
            raise PowerPointNotRunningError(
                "Failed to launch PowerPoint via Dispatch('PowerPoint.Application')."
            ) from exc
        return app, True

    # -- attach -------------------------------------------------------------

    def attach_excel(self, excel_app: Any) -> XlAddIn:
        """Attach an Excel `Application` and resolve its think-cell add-in.

        think-cell registers a separate COM add-in on Excel exposing
        `IXlMacroInterface`. Pass an Excel app obtained by the caller
        (e.g. `win32com.client.Dispatch("Excel.Application")` or a
        `Workbook.Application` reference) and this resolves it once and
        caches the wrapper.

        Args:
            excel_app: Excel `Application` dispatch.

        Returns:
            An `XlAddIn` wrapping the resolved `IXlMacroInterface`.
        """
        if self._xl_addin is None:
            xl_dispatch = _find_addin(excel_app).Object
            self._xl_addin = XlAddIn(xl_dispatch)
        return self._xl_addin

    # -- accessors ----------------------------------------------------------

    @property
    def powerpoint(self) -> Any:
        """The PowerPoint `Application` dispatch."""
        return self._powerpoint

    @property
    def pp(self) -> PpAddIn:
        """The PowerPoint-side think-cell add-in wrapper."""
        return self._pp_addin

    @property
    def xl(self) -> XlAddIn:
        """The Excel-side add-in wrapper.

        Raises:
            RuntimeError: if `attach_excel(excel_app)` has not been called.
        """
        if self._xl_addin is None:
            raise RuntimeError(
                "Excel add-in not attached; call ThinkCellClient.attach_excel(excel_app) "
                "with an Excel Application dispatch first."
            )
        return self._xl_addin

    # -- context manager ----------------------------------------------------

    def __enter__(self) -> "ThinkCellClient":
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        # We deliberately do NOT close PowerPoint even when we launched it;
        # quitting an Application that may host the user's other decks would
        # be hostile. Drop our references and let pywin32 GC the dispatch.
        self._xl_addin = None
        # Keep _pp_addin and _powerpoint for read; just let them fall out of
        # scope when the `with` exits.
