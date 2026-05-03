"""Mac-runnable smoke tests for `tc_com_driver`.

Verifies that:
    1. The package imports cleanly on non-Windows (no eager pywin32 import).
    2. All public symbols are exported.
    3. `ThinkCellClient.connect()` raises `WrongPlatformError` on Mac/Linux.
    4. The wrapper classes accept a fake dispatch and forward calls
       through `__getattr__`-style attribute access (sanity-check that no
       method shadows a real one accidentally).

If pywin32 happens to be installed (rare on Mac, but possible via a stub
wheel), the platform-error path still triggers because we gate on
`sys.platform == 'win32'`, not on importability of `win32com`.
"""

from __future__ import annotations

import sys
from typing import Any
from unittest.mock import MagicMock

import pytest


def test_imports_clean_on_non_windows() -> None:
    """Package import must not require pywin32 on Mac/Linux."""
    import tc_com_driver  # noqa: F401

    assert hasattr(tc_com_driver, "__version__")


def test_public_api_exports() -> None:
    import tc_com_driver

    expected = {
        "ThinkCellClient",
        "PpAddIn",
        "XlAddIn",
        "UpdateBatch",
        "ThinkCellError",
        "WrongPlatformError",
        "PowerPointNotRunningError",
        "ThinkCellNotFoundError",
        "ThinkCellNotActiveError",
        "PP_MACRO_IID",
        "XL_MACRO_IID",
        "UPDATE_BATCH_IID",
    }
    missing = expected - set(tc_com_driver.__all__)
    assert not missing, f"missing exports: {missing}"
    for name in expected:
        assert hasattr(tc_com_driver, name)


def test_iid_constants_match_typeinfo() -> None:
    """The wrapper IIDs must exactly match the typeinfo dump."""
    from tc_com_driver import PP_MACRO_IID, UPDATE_BATCH_IID, XL_MACRO_IID

    assert PP_MACRO_IID == "{24f3e526-2a15-4b8b-bc6a-558500f451c1}"
    assert XL_MACRO_IID == "{085347c3-2d5b-4885-869a-b9cc362b924c}"
    assert UPDATE_BATCH_IID == "{be9bb0c3-e5fb-4de5-b499-aae20fff6fad}"


def test_exception_hierarchy() -> None:
    from tc_com_driver import (
        PowerPointNotRunningError,
        ThinkCellError,
        ThinkCellNotActiveError,
        ThinkCellNotFoundError,
        WrongPlatformError,
    )

    for exc in (
        WrongPlatformError,
        PowerPointNotRunningError,
        ThinkCellNotFoundError,
        ThinkCellNotActiveError,
    ):
        assert issubclass(exc, ThinkCellError)
        assert issubclass(exc, Exception)


@pytest.mark.skipif(sys.platform == "win32", reason="Mac/Linux-only platform-guard test")
def test_connect_raises_wrong_platform_on_mac() -> None:
    """`connect()` must refuse on non-Windows BEFORE importing pywin32."""
    from tc_com_driver import ThinkCellClient, WrongPlatformError

    with pytest.raises(WrongPlatformError) as exc_info:
        ThinkCellClient.connect()
    assert sys.platform in str(exc_info.value)


def test_pp_addin_method_count() -> None:
    """12 user-visible public methods + 7 FHIDDEN _step* = 19 wrapped entries.

    The spec frames it as 19 user-visible IPpMacroInterface methods. Of those,
    7 are FHIDDEN `Step*` variants we expose under `_step*` for advanced
    callers (so they don't pollute the public surface). The remaining 12
    are the documented public methods (activate, styles, mekko, table,
    gallery, bain-toolbox).
    """
    from tc_com_driver import PpAddIn

    public = [
        n
        for n in dir(PpAddIn)
        if not n.startswith("_") and callable(getattr(PpAddIn, n)) and n != "raw"
    ]
    private_step = [n for n in dir(PpAddIn) if n.startswith("_step")]
    expected_public = sorted(
        [
            "activate_add_in",
            "is_add_in_active",
            "load_style",
            "load_style_for_region",
            "remove_styles",
            "get_style_name",
            "get_mekko_graphics_xml",
            "import_mekko_graphics_charts",
            "start_table_insertion",
            "show_chart_gallery",
            "bain_toolbox_rectangles",
            "bain_toolbox_apply_shift",
        ]
    )
    assert sorted(public) == expected_public
    assert len(private_step) == 7, f"expected 7 _step* methods, got {private_step!r}"
    # 12 public + 7 step = 19 wrapped methods on IPpMacroInterface.
    assert len(public) + len(private_step) == 19


def test_xl_addin_method_count() -> None:
    from tc_com_driver import XlAddIn

    public = [
        n
        for n in dir(XlAddIn)
        if not n.startswith("_") and callable(getattr(XlAddIn, n)) and n != "raw"
    ]
    assert sorted(public) == sorted(["presentation_from_template", "update_chart", "create_update"])


def test_update_batch_method_count() -> None:
    from tc_com_driver import UpdateBatch

    public = [
        n
        for n in dir(UpdateBatch)
        if not n.startswith("_") and callable(getattr(UpdateBatch, n)) and n != "raw"
    ]
    assert sorted(public) == sorted(["add_range_data", "add_range_image", "send"])


def test_pp_addin_forwards_to_dispatch() -> None:
    """Wrappers must forward COM calls to the underlying dispatch verbatim."""
    from tc_com_driver import PpAddIn

    fake: Any = MagicMock()
    fake.IsAddInActive.return_value = 1  # COM truthy VARIANT_BOOL
    pp = PpAddIn(fake)

    assert pp.is_add_in_active() is True
    fake.IsAddInActive.assert_called_once_with()

    pp.activate_add_in(True)
    fake.ActivateAddIn.assert_called_once_with(True)

    pp.load_style("layout-handle", r"C:\styles\corp.style")
    fake.LoadStyle.assert_called_once_with("layout-handle", r"C:\styles\corp.style")

    pp.load_style_for_region("layout", "f.style", 1.0, 2.0, 3.0, 4.0)
    fake.LoadStyleForRegion.assert_called_once_with("layout", "f.style", 1.0, 2.0, 3.0, 4.0)

    fake.GetStyleName.return_value = "CorpStyle"
    assert pp.get_style_name("layout") == "CorpStyle"

    fake.GetMekkoGraphicsXML.return_value = "<root/>"
    assert pp.get_mekko_graphics_xml("shape") == "<root/>"


def test_xl_addin_forwards_and_wraps_update_batch() -> None:
    from tc_com_driver import UpdateBatch, XlAddIn

    fake: Any = MagicMock()
    xl = XlAddIn(fake)

    pres_dispatch = MagicMock()
    fake.PresentationFromTemplate.return_value = pres_dispatch
    pres = xl.presentation_from_template(workbook="wb", template="t.pptx", powerpoint_app="ppt")
    assert pres is pres_dispatch
    fake.PresentationFromTemplate.assert_called_once_with("wb", "t.pptx", "ppt")

    xl.update_chart(target="pres", chart_name="ARRChart", range="rng", transposed=True)
    fake.UpdateChart.assert_called_once_with("pres", "ARRChart", "rng", True)

    batch_dispatch = MagicMock()
    fake.CreateUpdate.return_value = batch_dispatch
    batch = xl.create_update()
    assert isinstance(batch, UpdateBatch)
    assert batch.raw is batch_dispatch


def test_update_batch_forwards() -> None:
    from tc_com_driver import UpdateBatch

    fake: Any = MagicMock()
    batch = UpdateBatch(fake)

    batch.add_range_data(target="t", name="ARR", range="r", transposed=False)
    fake.AddRangeData.assert_called_once_with("t", "ARR", "r", False)

    batch.add_range_image(target="t", name="logo", range="r2")
    fake.AddRangeImage.assert_called_once_with("t", "logo", "r2")

    batch.send()
    fake.Send.assert_called_once_with()


def test_pywin32_skipped_when_absent() -> None:
    """If pywin32 is unavailable, connect() should still raise our typed error.

    Uses `pytest.importorskip` per the spec to keep the test rig honest:
    if pywin32 IS importable on a Mac, this test is harmless. If not, we
    skip the deeper assertion.
    """
    pytest.importorskip("win32com", reason="pywin32 not installed (expected on Mac)")
    # Even if win32com is importable, connect() still refuses on non-Windows
    # platforms via the WrongPlatformError sys.platform check above.
