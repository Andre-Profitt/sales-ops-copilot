from __future__ import annotations

import json
from pathlib import Path

from scripts.sd_factory.design_gate import (
    compare_contact_sheets,
    discover_director_contact_sheets,
    load_acknowledgements,
    write_acknowledgement,
)


def _make_contact_sheet(directory: Path, *, pattern: str) -> Path:
    """Create a tiny grayscale contact_sheet.jpg with a chosen pattern.

    The average-hash diff requires non-uniform images to discriminate, since
    a fully uniform image hashes to all-1 bits regardless of brightness.
    """

    from PIL import Image, ImageDraw

    directory.mkdir(parents=True, exist_ok=True)
    size = 16
    img = Image.new("L", (size, size), color=128)
    draw = ImageDraw.Draw(img)
    if pattern == "left_dark":
        draw.rectangle([0, 0, size // 2, size], fill=20)
        draw.rectangle([size // 2, 0, size, size], fill=235)
    elif pattern == "right_dark":
        draw.rectangle([0, 0, size // 2, size], fill=235)
        draw.rectangle([size // 2, 0, size, size], fill=20)
    elif pattern == "stripes":
        for y in range(0, size, 2):
            draw.rectangle([0, y, size, y + 1], fill=20)
    else:
        raise ValueError(f"unknown pattern {pattern!r}")
    sheet = directory / "contact_sheet.jpg"
    img.save(sheet, format="JPEG", quality=95)
    return sheet


def _make_period(root: Path, period: str, directors: dict[str, str]) -> None:
    base = root / "state" / period / "__regional__" / "visual_gate" / "review_package"
    for slug, pattern in directors.items():
        director_dir = base / f"{slug}-LAND-{period}-meeting-spine"
        _make_contact_sheet(director_dir, pattern=pattern)


def test_discover_returns_director_slugs_and_paths(tmp_path: Path) -> None:
    _make_period(tmp_path, "2026-Q2", {"Jesper-Tyrer": "left_dark", "Adam-Steinhouse": "stripes"})

    found = discover_director_contact_sheets("2026-Q2", root=tmp_path)
    slugs = sorted(slug for slug, _ in found)
    assert slugs == ["Adam-Steinhouse", "Jesper-Tyrer"]
    for _, path in found:
        assert path.name == "contact_sheet.jpg"


def test_compare_with_no_prior_period_returns_baseline(tmp_path: Path) -> None:
    _make_period(tmp_path, "2026-Q2", {"Jesper-Tyrer": "left_dark"})

    report = compare_contact_sheets("2026-Q2", prior_period=None, root=tmp_path)
    assert report.status == "baseline"
    assert report.directors[0]["verdict"] == "baseline"
    assert report.directors_requiring_ack == []


def test_compare_identical_sheets_pass(tmp_path: Path) -> None:
    _make_period(tmp_path, "2026-Q2", {"Jesper-Tyrer": "left_dark"})
    _make_period(tmp_path, "2026-Q1", {"Jesper-Tyrer": "left_dark"})

    report = compare_contact_sheets("2026-Q2", prior_period="2026-Q1", root=tmp_path)
    assert report.status == "pass"
    director = report.directors[0]
    assert director["verdict"] == "pass"
    assert director["diff_score"] == 0.0


def test_compare_diverging_sheets_requires_ack(tmp_path: Path) -> None:
    _make_period(tmp_path, "2026-Q2", {"Jesper-Tyrer": "left_dark"})
    _make_period(tmp_path, "2026-Q1", {"Jesper-Tyrer": "right_dark"})

    report = compare_contact_sheets(
        "2026-Q2",
        prior_period="2026-Q1",
        root=tmp_path,
        drift_threshold=0.05,
    )
    director = report.directors[0]
    assert director["verdict"] == "drift"
    assert director["requires_acknowledgement"] is True
    assert report.status == "needs_ack"
    assert "Jesper-Tyrer" in report.directors_requiring_ack


def test_acknowledgement_clears_drift_status(tmp_path: Path) -> None:
    _make_period(tmp_path, "2026-Q2", {"Jesper-Tyrer": "left_dark"})
    _make_period(tmp_path, "2026-Q1", {"Jesper-Tyrer": "right_dark"})

    write_acknowledgement(
        "2026-Q2",
        "Jesper-Tyrer",
        root=tmp_path,
        actor="Andre",
        reason="Approved layout change for May",
    )
    report = compare_contact_sheets(
        "2026-Q2",
        prior_period="2026-Q1",
        root=tmp_path,
        drift_threshold=0.05,
    )
    director = report.directors[0]
    assert director["verdict"] == "acknowledged"
    assert director["requires_acknowledgement"] is False
    assert report.status != "needs_ack"


def test_load_acknowledgements_round_trip(tmp_path: Path) -> None:
    write_acknowledgement(
        "2026-Q2",
        "Jesper-Tyrer",
        root=tmp_path,
        actor="Andre",
        reason="r1",
    )
    write_acknowledgement(
        "2026-Q2",
        "Adam-Steinhouse",
        root=tmp_path,
        actor="Andre",
        reason="r2",
    )
    acks = load_acknowledgements("2026-Q2", root=tmp_path)
    assert set(acks.keys()) == {"Jesper-Tyrer", "Adam-Steinhouse"}
    raw = json.loads(
        (
            tmp_path
            / "state"
            / "2026-Q2"
            / "__regional__"
            / "factory_plan"
            / "mom_contact_sheet_gate.ack.json"
        ).read_text()
    )
    assert raw["schema"] == "sd-mom-contact-sheet-ack/v1"


def test_compare_with_missing_current_directory_returns_warn(tmp_path: Path) -> None:
    report = compare_contact_sheets("2026-Q2", prior_period="2026-Q1", root=tmp_path)
    assert report.status == "warn"
    assert any("no current contact sheets" in note for note in report.notes)
