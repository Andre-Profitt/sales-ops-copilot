"""Path helpers for the Sales Director factory scaffold.

The helpers are deliberately conservative: they calculate paths only and never
create, move, or delete files.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


def repo_root() -> Path:
    """Return the repository root from this package location."""

    return Path(__file__).resolve().parents[2]


def state_period_root(period: str, *, root: Path | None = None) -> Path:
    """Return ``state/<period>``."""

    return (root or repo_root()) / "state" / period


def regional_root(period: str, *, root: Path | None = None) -> Path:
    """Return ``state/<period>/__regional__``."""

    return state_period_root(period, root=root) / "__regional__"


def director_root(period: str, director_slug: str, *, root: Path | None = None) -> Path:
    """Return ``state/<period>/<director_slug>``."""

    return state_period_root(period, root=root) / director_slug


def production_runs_root(period: str, *, root: Path | None = None) -> Path:
    """Return the regional production-runs directory for a period."""

    return regional_root(period, root=root) / "production_runs"


def thinkcell_scaffold_root(period: str | None = None, *, root: Path | None = None) -> Path:
    """Return the think-cell build-scaffold root, optionally scoped to a period."""

    base = (root or repo_root()) / "state" / "thinkcell_bridge" / "build_scaffold"
    return base / period if period else base


@dataclass(frozen=True)
class ArtifactPaths:
    """Collected artifact roots for a period and optional director slug."""

    period: str
    root: Path = repo_root()
    director_slug: str | None = None

    @property
    def state_period(self) -> Path:
        return state_period_root(self.period, root=self.root)

    @property
    def regional(self) -> Path:
        return regional_root(self.period, root=self.root)

    @property
    def director(self) -> Path | None:
        if self.director_slug is None:
            return None
        return director_root(self.period, self.director_slug, root=self.root)

    @property
    def production_runs(self) -> Path:
        return production_runs_root(self.period, root=self.root)

    @property
    def thinkcell_scaffold(self) -> Path:
        return thinkcell_scaffold_root(self.period, root=self.root)


__all__ = [
    "ArtifactPaths",
    "director_root",
    "production_runs_root",
    "regional_root",
    "repo_root",
    "state_period_root",
    "thinkcell_scaffold_root",
]

