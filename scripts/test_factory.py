"""Tests for scripts/factory.py.

The factory CLI must:
* import without running anything (pytest collection-safe)
* expose a ``main`` callable with ``--help`` exiting 0
* resolve the canonical 9 directors from ``--directors all``
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"


@pytest.fixture(scope="module")
def factory_module():
    if str(SCRIPTS_DIR) not in sys.path:
        sys.path.insert(0, str(SCRIPTS_DIR))
    if "factory" in sys.modules:
        return importlib.reload(sys.modules["factory"])
    return importlib.import_module("factory")


def test_factory_imports_clean(factory_module) -> None:
    """Module import must not run main() or touch SF / SSH."""
    assert callable(factory_module.main)
    assert callable(factory_module.run_factory)
    assert callable(factory_module.render_one_director)
    # Constants are sane.
    assert factory_module.DEFAULT_PERIOD
    assert factory_module.DEFAULT_TEMPLATE.name.endswith(".pptx")


def test_factory_resolve_directors_all(factory_module) -> None:
    """``--directors all`` must yield the canonical 9 MD-1 directors."""
    directors = factory_module._resolve_directors("all")
    assert len(directors) == 9
    names = {d["name"] for d in directors}
    # Spot-check the Jesper / Sarah / Patrick / Megan that today's state has.
    assert {"Jesper Tyrer", "Sarah Pittroff", "Patrick Gaughan", "Megan Miceli"} <= names


def test_factory_resolve_directors_subset(factory_module) -> None:
    """Subset selection by slug or display name."""
    selected = factory_module._resolve_directors("Jesper-Tyrer,Sarah Pittroff")
    assert [d["name"] for d in selected] == ["Jesper Tyrer", "Sarah Pittroff"]


def test_factory_resolve_directors_unknown_raises(factory_module) -> None:
    with pytest.raises(SystemExit):
        factory_module._resolve_directors("Nobody-Real")


def test_factory_help_exits_zero(factory_module) -> None:
    """--help must exit 0 (sanity, also exercises the parser)."""
    with pytest.raises(SystemExit) as exc:
        factory_module.main(["--help"])
    assert exc.value.code == 0
