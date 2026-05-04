"""Output archival + audit log for the LAND deck factory.

Once a render finishes (and any quality gate passes), we want to move the
.pptx into a per-director archival tree alongside an immutable audit JSON
sidecar. The audit captures hashes of every input + the rendered output, the
.ppttc binding count, the verify outcome, and which numeric-fix flags the
emitting build_ppttc.py supported -- so we can answer "which directors got
the F-01/F-02 fixes after 2026-05-03?" months later without spelunking
through the deck XML.

Archival layout::

    state/<period>/<director>/decks/<ts>/
        <Director>-LAND-<period>-<ts>.pptx
        audit.json

The original .ppttc + template paths are referenced (with sha256 + size) but
NOT copied -- they are large, deterministic, and live next to the rest of the
director state.

Pure stdlib + lxml. ASCII-only.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import shutil
import time
from pathlib import Path
from typing import Any

from .models import RenderResult

ARCHIVE_AUDIT_FILENAME = "audit.json"


def archive_render(
    result: RenderResult,
    director: str,
    period: str,
    audit: dict[str, Any] | None = None,
    *,
    archive_root: Path | None = None,
    timestamp: str | None = None,
    template_path: Path | None = None,
    ppttc_path: Path | None = None,
    extra_audit: dict[str, Any] | None = None,
) -> Path:
    """Move ``result.output_path`` into the director archive tree, write audit.

    Args:
        result: RenderResult returned by ``TcRenderClient.render``.
        director: director slug (e.g. ``"Jesper-Tyrer"``). Used as the
            second directory level under ``archive_root``. Spaces are
            replaced with hyphens but no other normalization is done; the
            caller should pass the canonical slug.
        period: period label (e.g. ``"2026-Q2"``). Used as the first
            directory level under ``archive_root``.
        audit: caller-supplied payload merged into ``audit.json``. May
            include fix-id flags such as ``{"fix_F_01": "fixed-2026-05-03",
            "fix_F_02": "fixed-2026-05-03"}``.
        archive_root: where to anchor ``<period>/<director>/decks/<ts>/``.
            Defaults to ``state/`` next to ``result.output_path``'s repo
            root, computed by walking up from the .pptx until a ``state/``
            sibling is found, falling back to ``result.output_path.parent /
            "state"``.
        timestamp: directory timestamp; default ``time.strftime
            ('%Y%m%d-%H%M%S')``.
        template_path: optional Mac-side donor .pptx that produced the
            render. Logged with sha256 + size in the audit.
        ppttc_path: optional explicit .ppttc path. Defaults to
            ``result.input_ppttc``.
        extra_audit: optional extra payload merged AFTER ``audit`` (so
            extra_audit wins on key collision). Use this from
            :func:`tcrender.render.TcRenderClient.render` to inject the
            verify result + any fix flags consistently.

    Returns:
        Absolute path to the archived .pptx.

    Raises:
        FileNotFoundError: if ``result.output_path`` no longer exists.
        OSError: on filesystem failure during archival.
    """
    src = Path(result.output_path).expanduser().resolve()
    if not src.exists():
        raise FileNotFoundError(f"render output not found: {src}")

    ts = timestamp or time.strftime("%Y%m%d-%H%M%S")
    director_slug = director.replace(" ", "-")

    root = (archive_root or _default_archive_root(src)).expanduser().resolve()
    deck_dir = root / period / director_slug / "decks" / ts
    deck_dir.mkdir(parents=True, exist_ok=True)

    archived = deck_dir / src.name
    # Use replace so cross-device archives still work (move semantics with
    # atomicity on the same filesystem).
    shutil.move(str(src), str(archived))

    audit_payload = _build_audit_payload(
        result=result,
        director=director_slug,
        period=period,
        timestamp=ts,
        archived_path=archived,
        template_path=template_path,
        ppttc_path=ppttc_path or Path(result.input_ppttc),
        caller_audit=audit or {},
        extra_audit=extra_audit or {},
    )
    audit_file = deck_dir / ARCHIVE_AUDIT_FILENAME
    audit_file.write_text(
        json.dumps(audit_payload, indent=2, sort_keys=True, ensure_ascii=True),
        encoding="utf-8",
    )

    return archived


# -- internals -------------------------------------------------------------


def _default_archive_root(output_path: Path) -> Path:
    """Walk up from ``output_path`` to find a sibling ``state/`` directory.

    Falls back to ``<output_path.parent>/state`` if no ancestor has one.
    """
    here = output_path.parent
    for parent in [here, *here.parents]:
        candidate = parent / "state"
        if candidate.is_dir():
            return candidate
    return here / "state"


def _sha256_of(path: Path) -> str:
    """Stream-hash ``path`` and return the hex digest. Empty/missing -> ``""``."""
    if not path.exists() or not path.is_file():
        return ""
    h = hashlib.sha256()
    with path.open("rb") as fp:
        for chunk in iter(lambda: fp.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def _file_meta(path: Path | None) -> dict[str, Any]:
    """Return a ``{path, sha256, size_bytes, exists}`` dict for ``path``."""
    if path is None:
        return {"path": None, "sha256": "", "size_bytes": 0, "exists": False}
    p = Path(path).expanduser()
    exists = p.exists() and p.is_file()
    return {
        "path": str(p),
        "sha256": _sha256_of(p) if exists else "",
        "size_bytes": p.stat().st_size if exists else 0,
        "exists": exists,
    }


def _ppttc_binding_count(ppttc_path: Path | None) -> int:
    """Count ``data[]`` bindings in a .ppttc; ``0`` on any error."""
    if ppttc_path is None:
        return 0
    p = Path(ppttc_path).expanduser()
    if not p.exists() or not p.is_file():
        return 0
    try:
        parsed = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return 0
    if not isinstance(parsed, list):
        return 0
    total = 0
    for entry in parsed:
        if isinstance(entry, dict) and isinstance(entry.get("data"), list):
            total += len(entry["data"])
    return total


def _build_audit_payload(
    *,
    result: RenderResult,
    director: str,
    period: str,
    timestamp: str,
    archived_path: Path,
    template_path: Path | None,
    ppttc_path: Path | None,
    caller_audit: dict[str, Any],
    extra_audit: dict[str, Any],
) -> dict[str, Any]:
    """Assemble the audit.json content."""
    payload: dict[str, Any] = {
        "schema_version": 1,
        "director": director,
        "period": period,
        "timestamp": timestamp,
        "render": {
            "elapsed_seconds": result.elapsed_seconds,
            "exit_code": result.exit_code,
            "stdout_tail": result.ssh_stdout_tail,
            "stderr_tail": result.ssh_stderr_tail,
        },
        "ppttc": {
            **_file_meta(ppttc_path),
            "binding_count": _ppttc_binding_count(ppttc_path),
        },
        "template": _file_meta(template_path),
        "output": {
            **_file_meta(archived_path),
            # Cross-check vs the value the transport observed pre-archive
            # (post-archive size should be identical -- shutil.move on the
            # same filesystem doesn't rewrite content).
            "size_bytes_at_render": result.output_size_bytes,
        },
    }
    # Merge caller_audit first, then extra_audit, so the latter wins.
    for k, v in caller_audit.items():
        payload[k] = _normalize(v)
    for k, v in extra_audit.items():
        payload[k] = _normalize(v)
    return payload


def _normalize(value: Any) -> Any:
    """Make ``value`` JSON-serializable with stable types."""
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return _normalize(dataclasses.asdict(value))
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, (list, tuple)):
        return [_normalize(v) for v in value]
    if isinstance(value, dict):
        return {str(k): _normalize(v) for k, v in value.items()}
    return value


__all__ = [
    "ARCHIVE_AUDIT_FILENAME",
    "archive_render",
]
