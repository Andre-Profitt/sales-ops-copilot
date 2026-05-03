"""Wrapper around think-cell's `IPpMacroInterface` dispatch interface.

IID: `{24f3e526-2a15-4b8b-bc6a-558500f451c1}`
Source typeinfo: `state/thinkcell_bridge/typeinfo/20260501-215903/thinkcell_typeinfo_probe.json`
Cross-check: `state/thinkcell_bridge/csharp_interop/20260501-215903/Thinkcell.Interop.cs`

19 user-visible methods + 7 FHIDDEN `Step*` variants exposed as `_step*` for
advanced callers. The Step methods are documented but hidden in the typelib;
do not invoke them in production without an empirical write-test that
defines expected behavior.
"""

from __future__ import annotations

from typing import Any

PP_MACRO_IID = "{24f3e526-2a15-4b8b-bc6a-558500f451c1}"


class PpAddIn:
    """PowerPoint-side think-cell add-in. Wraps `IPpMacroInterface`."""

    __slots__ = ("_dispatch",)

    def __init__(self, dispatch: Any) -> None:
        """Wrap a live `IPpMacroInterface` dispatch handle.

        Args:
            dispatch: `win32com.client.CDispatch` for the PowerPoint
                add-in's think-cell `IPpMacroInterface` (typically
                obtained from `Application.COMAddIns(progid).Object`).
        """
        self._dispatch = dispatch

    @property
    def raw(self) -> Any:
        """The underlying `win32com.client.CDispatch` handle (escape hatch)."""
        return self._dispatch

    # -- activation ----------------------------------------------------------

    def activate_add_in(self, active: bool) -> None:
        """Enable or disable the add-in within the current PowerPoint session.

        COM dispid: ``1018``.
        Param names from typeinfo: ``Active``.
        """
        self._dispatch.ActivateAddIn(bool(active))

    def is_add_in_active(self) -> bool:
        """Return True when the add-in is currently enabled.

        COM dispid: ``1019``. No params.
        """
        return bool(self._dispatch.IsAddInActive())

    # -- styles --------------------------------------------------------------

    def load_style(self, custom_layout_or_master: Any, file_name: str) -> None:
        """Apply a think-cell style file to a layout or master slide.

        COM dispid: ``1020``.
        Param names from typeinfo: ``CustomLayoutOrMaster``, ``FileName``.

        Args:
            custom_layout_or_master: `CustomLayout` or `Master` dispatch.
            file_name: Path to a `.style` (or equivalent) think-cell style file.
        """
        self._dispatch.LoadStyle(custom_layout_or_master, file_name)

    def load_style_for_region(
        self,
        custom_layout: Any,
        file_name: str,
        left: float,
        top: float,
        width: float,
        height: float,
    ) -> None:
        """Apply a style file scoped to a rectangular region of a layout.

        COM dispid: ``1021``.
        Param names from typeinfo: ``CustomLayout``, ``FileName``, ``Left``,
        ``Top``, ``Width``, ``Height``.

        Args:
            custom_layout: `CustomLayout` dispatch.
            file_name: Path to the think-cell style file.
            left: Left edge of the region (PowerPoint points).
            top: Top edge of the region (PowerPoint points).
            width: Width of the region (PowerPoint points).
            height: Height of the region (PowerPoint points).
        """
        self._dispatch.LoadStyleForRegion(
            custom_layout, file_name, float(left), float(top), float(width), float(height)
        )

    def remove_styles(self, custom_layout: Any) -> None:
        """Remove all think-cell styles from a layout.

        COM dispid: ``1022``.
        Param names from typeinfo: ``CustomLayout``.
        """
        self._dispatch.RemoveStyles(custom_layout)

    def get_style_name(self, custom_layout_or_master: Any) -> str:
        """Return the active think-cell style name on the given layout/master.

        COM dispid: ``1029``.
        Param names from typeinfo: ``CustomLayoutOrMaster``.

        Returns:
            Style name as a string. Empty string when no style is bound.
        """
        return str(self._dispatch.GetStyleName(custom_layout_or_master))

    # -- mekko-graphics ------------------------------------------------------

    def get_mekko_graphics_xml(self, shape: Any) -> str:
        """Serialize the Mekko Graphics chart bound to `shape` to XML.

        COM dispid: ``1026``.
        Param names from typeinfo: ``Shape``.

        Args:
            shape: PowerPoint `Shape` hosting a Mekko Graphics chart.

        Returns:
            The chart's XML payload as a string.
        """
        return str(self._dispatch.GetMekkoGraphicsXML(shape))

    def import_mekko_graphics_charts(self, shapes: Any) -> None:
        """Import Mekko Graphics charts from a SAFEARRAY of `Shape` references.

        COM dispid: ``1027``.
        Param names from typeinfo: ``safeArrayOfShapes``.

        Args:
            shapes: SAFEARRAY (typically a Python tuple/list that pywin32
                marshals as VARIANT-of-array) of `Shape` dispatches.
        """
        self._dispatch.ImportMekkoGraphicsCharts(shapes)

    # -- table / gallery -----------------------------------------------------

    def start_table_insertion(self) -> None:
        """Start interactive table insertion (UI-driven).

        COM dispid: ``1028``. No params.
        """
        self._dispatch.StartTableInsertion()

    def show_chart_gallery(
        self, left: float, top: float, width: float, height: float, hwnd: int
    ) -> None:
        """Show the think-cell chart-gallery picker anchored to a region.

        COM dispid: ``1030``.
        Param names from typeinfo: ``Left``, ``Top``, ``Width``, ``Height``, ``HWND``.

        Args:
            left: Anchor left (PowerPoint points).
            top: Anchor top (PowerPoint points).
            width: Anchor width (PowerPoint points).
            height: Anchor height (PowerPoint points).
            hwnd: Win32 window handle to parent the gallery to.
        """
        self._dispatch.ShowChartGallery(
            float(left), float(top), float(width), float(height), int(hwnd)
        )

    # -- bain toolbox --------------------------------------------------------

    def bain_toolbox_rectangles(
        self,
        slide: Any,
        movable: Any,
        fixed: Any,
    ) -> None:
        """Bain Toolbox: register movable + fixed rectangles on a slide.

        COM dispid: ``1031``.
        Param names from typeinfo: ``Slide``,
        ``safeArrayOfLeftTopWidthHeightMovable``,
        ``safeArrayOfLeftTopWidthHeightFixed``.

        Args:
            slide: PowerPoint `Slide` dispatch.
            movable: SAFEARRAY of (left, top, width, height) tuples for
                movable rectangles.
            fixed: SAFEARRAY of (left, top, width, height) tuples for
                fixed-position rectangles.
        """
        self._dispatch.BainToolboxRectangles(slide, movable, fixed)

    def bain_toolbox_apply_shift(self, slide: Any, offsets: Any) -> None:
        """Bain Toolbox: apply per-rectangle (dx, dy) offsets on a slide.

        COM dispid: ``1032``.
        Param names from typeinfo: ``Slide``, ``safeArrayOfOffsets``.

        Args:
            slide: PowerPoint `Slide` dispatch.
            offsets: SAFEARRAY of (dx, dy) offsets, parallel to the
                rectangles previously registered.
        """
        self._dispatch.BainToolboxApplyShift(slide, offsets)

    # -- FHIDDEN Step methods ------------------------------------------------
    # advanced; see typeinfo for callers
    # FHIDDEN means "deliberately hidden in typelib"; these are valid dispids
    # but parameter types are encoded as VARIANT/IUnknown SAFEARRAYs and the
    # contracts are not publicly documented. Exposed under `_step*` so they
    # remain reachable for empirical work without polluting the public API.

    def _step3_presentation_from_template(
        self, bstr_template: str, lnkid: Any, iunk_storage: Any
    ) -> Any:
        """advanced; see typeinfo for callers.

        COM dispid: ``266056320``.
        Param names from typeinfo: ``bstrTemplate``, ``psalnkid``, ``psaiunkStorage``.
        """
        return self._dispatch.PresentationFromTemplateStep3(bstr_template, lnkid, iunk_storage)

    def _step3_update_chart(self, idisp: Any, bstr_chart_name: str, iunk_storage: Any) -> Any:
        """advanced; see typeinfo for callers.

        COM dispid: ``266056321``.
        Param names from typeinfo: ``idisp``, ``bstrChartName``, ``iunkStorage``.
        """
        return self._dispatch.UpdateChartStep3(idisp, bstr_chart_name, iunk_storage)

    def _step3_update_batch(self, names: Any, targets: Any, storages: Any, n_charts: int) -> Any:
        """advanced; see typeinfo for callers.

        COM dispid: ``266056322``.
        Param names from typeinfo: ``psaName``, ``psaidispTarget``,
        ``psaiunkStorage``, ``nCharts``.
        """
        return self._dispatch.UpdateBatchStep3(names, targets, storages, int(n_charts))

    def _step2_load_style(self, idisp_layout_or_master: Any, bstr_file_name: str) -> Any:
        """advanced; see typeinfo for callers.

        COM dispid: ``266056323``.
        Param names from typeinfo: ``idispCustomLayoutOrMaster``, ``bstrFileName``.
        """
        return self._dispatch.LoadStyleStep2(idisp_layout_or_master, bstr_file_name)

    def _step2_load_style_for_region(
        self,
        idisp_custom_layout: Any,
        bstr_file_name: str,
        f_left: float,
        f_top: float,
        f_width: float,
        f_height: float,
    ) -> Any:
        """advanced; see typeinfo for callers.

        COM dispid: ``266056324``.
        Param names from typeinfo: ``idispCustomLayout``, ``bstrFileName``,
        ``fLeft``, ``fTop``, ``fWidth``, ``fHeight``.
        """
        return self._dispatch.LoadStyleForRegionStep2(
            idisp_custom_layout, bstr_file_name, f_left, f_top, f_width, f_height
        )

    def _step2_remove_styles(self, idisp_custom_layout: Any) -> Any:
        """advanced; see typeinfo for callers.

        COM dispid: ``266056325``.
        Param names from typeinfo: ``idispCustomLayout``.
        """
        return self._dispatch.RemoveStylesStep2(idisp_custom_layout)

    def _step2_get_style_name(self, idisp_layout_or_master: Any) -> Any:
        """advanced; see typeinfo for callers.

        COM dispid: ``266056326``.
        Param names from typeinfo: ``idispCustomLayoutOrMaster``.
        """
        return self._dispatch.GetStyleNameStep2(idisp_layout_or_master)
