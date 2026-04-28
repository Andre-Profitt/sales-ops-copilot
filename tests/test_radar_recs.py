"""radar_recs — pull_actionable_recs reads radar's sqlite DB.

Tests cover the two regimes that matter for the daily brief:
  1. radar.db missing → return [] (radar is optional infrastructure)
  2. radar.db present → must_try + should_try with status=proposed bubble up,
     ordered by severity then confidence, with citations counted.
"""

from __future__ import annotations

import json
import pathlib
import sqlite3


def _build_fixture_db(path: pathlib.Path) -> None:
    """Create a minimal radar-shaped sqlite DB with 4 recs across all severities."""
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE entities (
            id TEXT PRIMARY KEY,
            type TEXT NOT NULL,
            canonical_name TEXT NOT NULL
        );
        CREATE TABLE recommendations (
            id TEXT PRIMARY KEY,
            entity_id TEXT NOT NULL REFERENCES entities(id),
            recommendation_type TEXT NOT NULL,
            summary TEXT NOT NULL,
            confidence REAL NOT NULL,
            evidence_strength TEXT,
            blast_radius TEXT,
            expected_benefit TEXT,
            do_nothing_cost TEXT,
            citations_json TEXT NOT NULL DEFAULT '[]',
            severity TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'proposed',
            created_at TEXT NOT NULL
        );
        """
    )
    rows_entities = [
        ("ent:a", "software_artifact", "Alpha"),
        ("ent:b", "software_artifact", "Beta"),
        ("ent:c", "software_artifact", "Gamma"),
        ("ent:d", "software_artifact", "Delta"),
    ]
    conn.executemany("INSERT INTO entities VALUES (?, ?, ?)", rows_entities)
    rows_recs = [
        # Two must_try — second has higher confidence so should sort first within bucket
        (
            "rec:1",
            "ent:a",
            "version_upgrade",
            "Alpha upgrade",
            0.7,
            "moderate",
            "local",
            None,
            None,
            json.dumps([{"claim_id": "c1"}, {"claim_id": "c2"}]),
            "must_try",
            "proposed",
            "2026-04-28T00:00:00",
        ),
        (
            "rec:2",
            "ent:b",
            "deprecation_response",
            "Beta deprecation",
            0.95,
            "strong",
            "system",
            None,
            None,
            json.dumps([{"claim_id": "c3"}]),
            "must_try",
            "proposed",
            "2026-04-28T00:00:00",
        ),
        # should_try at 0.8 — should appear after both must_try
        (
            "rec:3",
            "ent:c",
            "version_upgrade",
            "Gamma upgrade",
            0.8,
            "strong",
            "local",
            None,
            None,
            "[]",
            "should_try",
            "proposed",
            "2026-04-28T00:00:00",
        ),
        # nice_to_know — must be filtered out
        (
            "rec:4",
            "ent:d",
            "version_upgrade",
            "Delta nice",
            0.9,
            "weak",
            "local",
            None,
            None,
            "[]",
            "nice_to_know",
            "proposed",
            "2026-04-28T00:00:00",
        ),
        # accepted (already decided) — must be filtered out
        (
            "rec:5",
            "ent:a",
            "version_upgrade",
            "Alpha already accepted",
            0.99,
            "strong",
            "local",
            None,
            None,
            "[]",
            "must_try",
            "accepted",
            "2026-04-28T00:00:00",
        ),
    ]
    conn.executemany(
        "INSERT INTO recommendations VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        rows_recs,
    )
    conn.commit()
    conn.close()


def test_returns_empty_when_db_missing(tmp_path: pathlib.Path) -> None:
    from scripts.radar_recs import pull_actionable_recs

    missing = tmp_path / "no_such.db"
    assert pull_actionable_recs(db_path=missing) == []


def test_returns_actionable_only_ordered(tmp_path: pathlib.Path) -> None:
    from scripts.radar_recs import pull_actionable_recs

    db = tmp_path / "radar.db"
    _build_fixture_db(db)

    recs = pull_actionable_recs(db_path=db)

    # nice_to_know and accepted are filtered out — only 3 remain
    assert len(recs) == 3
    rec_ids = [r["rec_id"] for r in recs]
    assert "rec:4" not in rec_ids  # nice_to_know dropped
    assert "rec:5" not in rec_ids  # accepted dropped

    # Ordering: both must_try first (higher confidence first within bucket),
    # then should_try
    assert [r["rec_id"] for r in recs] == ["rec:2", "rec:1", "rec:3"]
    assert recs[0]["severity"] == "must_try"
    assert recs[1]["severity"] == "must_try"
    assert recs[2]["severity"] == "should_try"

    # Entity name from the join populated
    assert recs[0]["entity"] == "Beta"
    assert recs[1]["entity"] == "Alpha"

    # Citation counts derived from citations_json
    assert recs[0]["citation_count"] == 1
    assert recs[1]["citation_count"] == 2
    assert recs[2]["citation_count"] == 0


def test_limit_caps_results(tmp_path: pathlib.Path) -> None:
    from scripts.radar_recs import pull_actionable_recs

    db = tmp_path / "radar.db"
    _build_fixture_db(db)

    recs = pull_actionable_recs(db_path=db, limit=1)
    assert len(recs) == 1
    # The cap takes the top of the ordered list — must_try with highest confidence
    assert recs[0]["rec_id"] == "rec:2"
