"""Month-over-month contact-sheet design gate (skeleton).

The visual-gate stage already renders one ``contact_sheet.jpg`` per director
into ``state/<period>/__regional__/visual_gate/review_package/<deck>/``. This
gate compares the current period's contact sheets against the prior period's
contact sheets and emits a per-director verdict. Material layout/style drift
must be acknowledged by an operator before publish.

This module is the W8 skeleton: data model, file discovery, optional
perceptual-hash diff (Pillow-based), and a documented acknowledgement
workflow. It is intentionally not yet wired into the publish gate. Codex or a
follow-up Claude run is expected to integrate it once thresholds are tuned
against a real prior month.

Acknowledgement file layout::

    state/<period>/__regional__/factory_plan/mom_contact_sheet_gate.ack.json

Schema::

    {
      "schema": "sd-mom-contact-sheet-ack/v1",
      "period": "<period>",
      "acknowledgements": [
        {"director_slug": "Jesper-Tyrer", "actor": "Andre",
         "reason": "Layout change approved", "timestamp_utc": "..."},
      ]
    }
"""

from __future__ import annotations

import datetime as dt
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

DEFAULT_DRIFT_THRESHOLD = 0.15  # 15% of average-hash bits differing => drift


@dataclass
class DirectorContactSheet:
    director_slug: str
    current_sheet: Path | None
    prior_sheet: Path | None
    diff_score: float | None
    verdict: str  # "pass" | "drift" | "baseline" | "missing_current" | "acknowledged"
    requires_acknowledgement: bool
    acknowledgement: dict | None = None
    error: str | None = None


@dataclass
class ContactSheetGateReport:
    schema: str
    period: str
    prior_period: str | None
    drift_threshold: float
    generated_at_utc: str
    status: str  # "pass" | "warn" | "fail" | "baseline" | "needs_ack"
    directors: list[dict] = field(default_factory=list)
    directors_requiring_ack: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def visual_gate_root(period: str, *, root: Path) -> Path:
    return root / "state" / period / "__regional__" / "visual_gate" / "review_package"


def gate_output_dir(period: str, *, root: Path) -> Path:
    return root / "state" / period / "__regional__" / "factory_plan"


def acknowledgement_path(period: str, *, root: Path) -> Path:
    return gate_output_dir(period, root=root) / "mom_contact_sheet_gate.ack.json"


def gate_report_path(period: str, *, root: Path) -> Path:
    return gate_output_dir(period, root=root) / "mom_contact_sheet_gate.json"


def _director_dir_to_slug(directory: Path) -> str:
    name = directory.name
    if name.endswith("-LAND-2026-Q2-meeting-spine"):
        return name[: -len("-LAND-2026-Q2-meeting-spine")]
    if "-LAND-" in name:
        return name.split("-LAND-")[0]
    return name


def discover_director_contact_sheets(period: str, *, root: Path) -> list[tuple[str, Path]]:
    base = visual_gate_root(period, root=root)
    if not base.exists():
        return []
    out: list[tuple[str, Path]] = []
    for candidate in sorted(base.iterdir()):
        if not candidate.is_dir():
            continue
        sheet = candidate / "contact_sheet.jpg"
        if sheet.exists():
            slug = _director_dir_to_slug(candidate)
            out.append((slug, sheet))
    return out


def load_acknowledgements(period: str, *, root: Path) -> dict[str, dict]:
    path = acknowledgement_path(period, root=root)
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return {ack["director_slug"]: ack for ack in payload.get("acknowledgements", [])}


def write_acknowledgement(
    period: str,
    director_slug: str,
    *,
    root: Path,
    actor: str,
    reason: str,
) -> Path:
    path = acknowledgement_path(period, root=root)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        payload = json.loads(path.read_text(encoding="utf-8"))
    else:
        payload = {
            "schema": "sd-mom-contact-sheet-ack/v1",
            "period": period,
            "acknowledgements": [],
        }
    payload.setdefault("acknowledgements", [])
    payload["acknowledgements"].append(
        {
            "director_slug": director_slug,
            "actor": actor,
            "reason": reason,
            "timestamp_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        }
    )
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


def _average_hash_bits(image_path: Path, *, size: int = 8) -> list[int] | None:
    try:
        from PIL import Image  # type: ignore[import-not-found]
    except Exception:
        return None
    try:
        with Image.open(image_path) as img:
            grey = img.convert("L").resize((size, size))
            pixels: list[int] = [int(p) for p in grey.getdata()]  # type: ignore[arg-type]
        if not pixels:
            return None
        avg = sum(pixels) / len(pixels)
        return [1 if p >= avg else 0 for p in pixels]
    except Exception:
        return None


def perceptual_diff(current: Path, prior: Path) -> float | None:
    """Return a [0, 1] Hamming-distance ratio between two images, or None on error."""

    a = _average_hash_bits(current)
    b = _average_hash_bits(prior)
    if a is None or b is None or len(a) != len(b) or not a:
        return None
    distance = sum(1 for x, y in zip(a, b) if x != y)
    return distance / len(a)


def compare_contact_sheets(
    period: str,
    *,
    prior_period: str | None,
    root: Path,
    drift_threshold: float = DEFAULT_DRIFT_THRESHOLD,
) -> ContactSheetGateReport:
    current_sheets = dict(discover_director_contact_sheets(period, root=root))
    prior_sheets: dict[str, Path] = {}
    if prior_period:
        prior_sheets = dict(discover_director_contact_sheets(prior_period, root=root))
    acks = load_acknowledgements(period, root=root)

    directors: list[DirectorContactSheet] = []
    requiring_ack: list[str] = []
    notes: list[str] = []

    if not current_sheets:
        notes.append(f"no current contact sheets found under {visual_gate_root(period, root=root)}")

    if not prior_period:
        notes.append("no prior_period supplied; treating run as baseline")

    for slug, current in sorted(current_sheets.items()):
        prior = prior_sheets.get(slug)
        ack = acks.get(slug)
        diff_score: float | None
        verdict: str
        requires_ack = False
        error: str | None = None
        if prior is None:
            verdict = "baseline" if prior_period is None else "missing_prior"
            diff_score = None
        else:
            score = perceptual_diff(current, prior)
            if score is None:
                verdict = "diff_unavailable"
                diff_score = None
                error = "PIL not available or unreadable image"
            else:
                diff_score = score
                if score > drift_threshold:
                    verdict = "drift"
                    requires_ack = True
                else:
                    verdict = "pass"
        if requires_ack and ack is not None:
            verdict = "acknowledged"
            requires_ack = False
        directors.append(
            DirectorContactSheet(
                director_slug=slug,
                current_sheet=current,
                prior_sheet=prior,
                diff_score=diff_score,
                verdict=verdict,
                requires_acknowledgement=requires_ack,
                acknowledgement=ack,
                error=error,
            )
        )
        if requires_ack:
            requiring_ack.append(slug)

    if not directors:
        status = "warn"
    elif requiring_ack:
        status = "needs_ack"
    elif all(d.verdict == "baseline" for d in directors):
        status = "baseline"
    elif any(d.verdict in {"missing_prior", "diff_unavailable"} for d in directors):
        status = "warn"
    else:
        status = "pass"

    return ContactSheetGateReport(
        schema="sales-director-mom-contact-sheet-gate/v1",
        period=period,
        prior_period=prior_period,
        drift_threshold=drift_threshold,
        generated_at_utc=dt.datetime.now(dt.timezone.utc).isoformat(),
        status=status,
        directors=[_director_to_payload(d) for d in directors],
        directors_requiring_ack=requiring_ack,
        notes=notes,
    )


def _director_to_payload(d: DirectorContactSheet) -> dict:
    payload = asdict(d)
    payload["current_sheet"] = str(d.current_sheet) if d.current_sheet else None
    payload["prior_sheet"] = str(d.prior_sheet) if d.prior_sheet else None
    return payload


def report_to_markdown(report: ContactSheetGateReport) -> str:
    lines = [
        f"# MoM Contact-Sheet Design Gate - {report.period}",
        "",
        f"- Status: `{report.status}`",
        f"- Prior period: `{report.prior_period or 'none'}`",
        f"- Drift threshold: `{report.drift_threshold}`",
        f"- Generated UTC: `{report.generated_at_utc}`",
        "",
    ]
    if report.directors_requiring_ack:
        lines.extend(["## Directors Requiring Acknowledgement", ""])
        for slug in report.directors_requiring_ack:
            lines.append(f"- {slug}")
        lines.append("")
    if report.notes:
        lines.extend(["## Notes", ""])
        for note in report.notes:
            lines.append(f"- {note}")
        lines.append("")
    lines.extend(
        [
            "## Director Verdicts",
            "",
            "| Director | Verdict | Diff score | Ack? |",
            "|---|---|---:|:---:|",
        ]
    )
    for entry in report.directors:
        lines.append(
            "| {slug} | {verdict} | {diff} | {ack} |".format(
                slug=entry["director_slug"],
                verdict=entry["verdict"],
                diff=(f"{entry['diff_score']:.3f}" if entry["diff_score"] is not None else "n/a"),
                ack=(
                    "yes"
                    if entry["acknowledgement"]
                    else ("required" if entry["requires_acknowledgement"] else "no")
                ),
            )
        )
    return "\n".join(lines).rstrip() + "\n"


__all__ = [
    "ContactSheetGateReport",
    "DEFAULT_DRIFT_THRESHOLD",
    "DirectorContactSheet",
    "acknowledgement_path",
    "compare_contact_sheets",
    "discover_director_contact_sheets",
    "gate_output_dir",
    "gate_report_path",
    "load_acknowledgements",
    "perceptual_diff",
    "report_to_markdown",
    "visual_gate_root",
    "write_acknowledgement",
]
