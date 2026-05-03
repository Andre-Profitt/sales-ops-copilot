"""Wrapper around think-cell's `IXlMacroInterface` dispatch interface.

IID: `{085347c3-2d5b-4885-869a-b9cc362b924c}`
Source typeinfo: `state/thinkcell_bridge/typeinfo/20260501-215903/thinkcell_typeinfo_probe.json`
Cross-check: `state/thinkcell_bridge/csharp_interop/20260501-215903/Thinkcell.Interop.cs`

Three user-visible methods. Drives Excel-to-PowerPoint deck generation and
chart updates from an Excel-side handle on the think-cell add-in.
"""

from __future__ import annotations

from typing import Any

from tc_com_driver.update_batch import UpdateBatch

XL_MACRO_IID = "{085347c3-2d5b-4885-869a-b9cc362b924c}"


class XlAddIn:
    """Excel-side think-cell add-in. Wraps `IXlMacroInterface`."""

    __slots__ = ("_dispatch",)

    def __init__(self, dispatch: Any) -> None:
        """Wrap a live `IXlMacroInterface` dispatch handle.

        Args:
            dispatch: `win32com.client.CDispatch` for the Excel add-in's
                think-cell `IXlMacroInterface` (typically obtained from
                `Application.COMAddIns(progid).Object` on Excel).
        """
        self._dispatch = dispatch

    @property
    def raw(self) -> Any:
        """The underlying `win32com.client.CDispatch` handle (escape hatch)."""
        return self._dispatch

    def presentation_from_template(
        self,
        workbook: Any,
        template: Any,
        powerpoint_app: Any,
    ) -> Any:
        """Generate a new PowerPoint deck from an Excel workbook + template.

        Primary deck-generation entry point. think-cell ingests `workbook`
        through `template`, drives `powerpoint_app` to materialize a fresh
        `Presentation`, and returns the resulting `Presentation` dispatch.

        COM dispid: ``1``.
        Param names from typeinfo: ``Workbook``, ``Template``, ``PpApplication``.

        Args:
            workbook: Excel `Workbook` with named ranges that match
                placeholders in `template`.
            template: Path (str) or `Presentation` of the think-cell
                template to expand.
            powerpoint_app: PowerPoint `Application` instance that will
                host the generated deck.

        Returns:
            The generated `Presentation` dispatch handle.
        """
        return self._dispatch.PresentationFromTemplate(workbook, template, powerpoint_app)

    def update_chart(
        self,
        target: Any,
        chart_name: str,
        range: Any,  # noqa: A002 — matches COM param name `Range`
        transposed: bool = False,
    ) -> None:
        """Refresh a single named chart from an Excel `Range`.

        For multi-chart updates prefer `create_update()` for atomicity.

        COM dispid: ``2``.
        Param names from typeinfo: ``Target``, ``ChartName``, ``Range``, ``Transposed``.

        Args:
            target: PowerPoint container (`Presentation` / `Slide` / `Shape`).
            chart_name: Chart name as defined in the template.
            range: Excel `Range` carrying the new data.
            transposed: When True, swap rows/columns before binding.
        """
        self._dispatch.UpdateChart(target, chart_name, range, transposed)

    def create_update(self) -> UpdateBatch:
        """Open a bulk update batch.

        Multiple `add_range_data` / `add_range_image` calls + a single
        `send()` is significantly faster — and atomic — compared to
        repeated `update_chart` calls.

        COM dispid: ``4``. No params.

        Returns:
            An `UpdateBatch` wrapping the returned `IUpdateBatch` dispatch.
        """
        batch_dispatch = self._dispatch.CreateUpdate()
        return UpdateBatch(batch_dispatch)
