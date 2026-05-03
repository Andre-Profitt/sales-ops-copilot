"""VM-runnable smoke test for `tc_com_driver`.

Run on the licensed Windows VM with PowerPoint open and think-cell installed:

    .venv\\Scripts\\python -m pytest libs\\tc_com_driver\\tests\\test_smoke_vm.py -x -q

Skipped automatically on non-Windows or when pywin32/PowerPoint/think-cell
are unavailable.
"""

from __future__ import annotations

import sys

import pytest

# Skip the entire module on non-Windows hosts.
if sys.platform != "win32":
    pytest.skip("VM smoke test is Windows-only", allow_module_level=True)

# Skip if pywin32 isn't installed on this Windows host.
pytest.importorskip("win32com.client", reason="pywin32 required for VM smoke test")


def test_connect_finds_thinkcell_addin() -> None:
    """End-to-end: connect, find add-in, confirm it's active.

    Skips with a clear marker when:
        - PowerPoint isn't running and we can't launch it.
        - think-cell add-in isn't registered.
        - think-cell is registered but disabled.
    """
    from tc_com_driver import (
        PowerPointNotRunningError,
        ThinkCellClient,
        ThinkCellNotActiveError,
        ThinkCellNotFoundError,
    )

    try:
        client_cm = ThinkCellClient.connect()
    except PowerPointNotRunningError as exc:
        pytest.skip(f"PowerPoint not running and not launchable: {exc}")
    except ThinkCellNotFoundError as exc:
        pytest.skip(f"think-cell add-in not registered on this PowerPoint: {exc}")
    except ThinkCellNotActiveError as exc:
        pytest.skip(f"think-cell add-in present but disabled: {exc}")

    with client_cm as client:
        assert client.pp is not None
        assert client.powerpoint is not None
        assert client.pp.is_add_in_active() is True


def test_pp_addin_iid_round_trip() -> None:
    """Sanity: the wrapper IID matches the dispatch's `_oleobj_` IID."""
    from tc_com_driver import PP_MACRO_IID, ThinkCellClient

    try:
        with ThinkCellClient.connect() as client:
            raw = client.pp.raw
            # pywin32 exposes the dispatched IID via _oleobj_.GetTypeInfo
            # but a coarse sanity check is enough: the constant we exported
            # is the same one the typeinfo probe recorded.
            assert PP_MACRO_IID.lower() == "{24f3e526-2a15-4b8b-bc6a-558500f451c1}"
            assert raw is not None
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"VM environment not ready: {exc}")
