"""Wrapper around think-cell's `IUpdateBatch` dispatch interface.

IID: `{be9bb0c3-e5fb-4de5-b499-aae20fff6fad}`
Source typeinfo: `state/thinkcell_bridge/typeinfo/20260501-215903/thinkcell_typeinfo_probe.json`
Cross-check: `state/thinkcell_bridge/csharp_interop/20260501-215903/Thinkcell.Interop.cs`

Built by `XlAddIn.create_update()`; never instantiated directly.
"""

from __future__ import annotations

from typing import Any

UPDATE_BATCH_IID = "{be9bb0c3-e5fb-4de5-b499-aae20fff6fad}"


class UpdateBatch:
    """Bulk-update batch for a think-cell-instrumented presentation.

    Wraps `IUpdateBatch`. Add as many `add_range_data` / `add_range_image`
    entries as needed, then call `send()` once to apply atomically.
    """

    __slots__ = ("_dispatch",)

    def __init__(self, dispatch: Any) -> None:
        """Wrap a live `IUpdateBatch` dispatch handle.

        Args:
            dispatch: `win32com.client.CDispatch` for `IUpdateBatch`,
                obtained from `XlAddIn.create_update()`.
        """
        self._dispatch = dispatch

    @property
    def raw(self) -> Any:
        """The underlying `win32com.client.CDispatch` handle (escape hatch)."""
        return self._dispatch

    def add_range_data(
        self,
        target: Any,
        name: str,
        range: Any,  # noqa: A002 — matches COM param name `Range`
        transposed: bool = False,
    ) -> None:
        """Queue a data refresh for a named chart from an Excel `Range`.

        COM dispid: ``1``.
        Param names from typeinfo: ``Target``, ``Name``, ``Range``, ``Transposed``.

        Args:
            target: PowerPoint `Presentation`, `Slide`, or `Shape` whose
                think-cell chart named `name` should be refreshed.
            name: Chart name as defined in the think-cell template.
            range: Excel `Range` carrying the new data block.
            transposed: When True, swap rows/columns before binding.
        """
        self._dispatch.AddRangeData(target, name, range, transposed)

    def add_range_image(self, target: Any, name: str, range: Any) -> None:  # noqa: A002
        """Queue an image-from-Range refresh for a named picture placeholder.

        COM dispid: ``2``.
        Param names from typeinfo: ``Target``, ``Name``, ``Range``.

        Args:
            target: Container (`Presentation` / `Slide` / `Shape`).
            name: Image placeholder name in the template.
            range: Excel `Range` to capture as a picture.
        """
        self._dispatch.AddRangeImage(target, name, range)

    def send(self) -> None:
        """Apply every queued update atomically. No return value.

        COM dispid: ``3``. No params.
        """
        self._dispatch.Send()
