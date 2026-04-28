#!/usr/bin/env python3
"""Pull actionable radar recommendations for the daily brief.

Read-only access to `~/code/apps/radar/state/radar.db` (override via `RADAR_DB`).
Returns must_try + should_try recs in `status='proposed'`, ordered by severity
then confidence. Returns an empty list if the DB is missing or unreadable —
radar is optional infrastructure and the brief must still render.

This module is the first half of closing the radar outcome loop: surface →
decide → verify → feedback. It only reads; the decision-write half lives in a
follow-up `/radar-triage` command (TODO).
"""

from __future__ import annotations

import json
import os
import pathlib
import sqlite3
from typing import Any

DEFAULT_RADAR_DB = pathlib.Path(
    os.environ.get(
        "RADAR_DB",
        str(pathlib.Path.home() / "code" / "apps" / "radar" / "state" / "radar.db"),
    )
)

# must_try and should_try recs in proposed status are the actionable surface.
# nice_to_know is filtered out because it's clamped (verification gate) — those
# only become actionable after lab recipes verify the underlying claims.
_QUERY = """
SELECT
    r.id,
    r.severity,
    r.recommendation_type,
    r.summary,
    r.confidence,
    r.evidence_strength,
    r.blast_radius,
    r.expected_benefit,
    r.do_nothing_cost,
    r.citations_json,
    e.canonical_name AS entity_name,
    r.entity_id
FROM recommendations r
LEFT JOIN entities e ON r.entity_id = e.id
WHERE r.severity IN ('must_try', 'should_try')
  AND r.status = 'proposed'
ORDER BY
    CASE r.severity
        WHEN 'must_try' THEN 1
        WHEN 'should_try' THEN 2
        ELSE 3
    END,
    r.confidence DESC,
    r.created_at DESC
"""


def pull_actionable_recs(
    db_path: pathlib.Path | str | None = None,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    """Return actionable radar recs as plain dicts.

    Args:
        db_path: override `~/code/apps/radar/state/radar.db`. Tests pass a fixture.
        limit: cap result length (default: no cap).

    Returns:
        List of {rec_id, severity, type, entity, summary, confidence,
        evidence_strength, blast_radius, expected_benefit, do_nothing_cost,
        citation_count} dicts. Empty list if DB missing/unreadable.
    """
    db = pathlib.Path(db_path) if db_path else DEFAULT_RADAR_DB
    if not db.exists():
        return []

    try:
        # Open read-only via URI mode so a concurrent write from the radar
        # daemon can't be blocked or corrupted by us.
        uri = f"file:{db}?mode=ro"
        with sqlite3.connect(uri, uri=True) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(_QUERY).fetchall()
    except sqlite3.Error:
        return []

    out: list[dict[str, Any]] = []
    for row in rows:
        try:
            citations = json.loads(row["citations_json"] or "[]")
        except (json.JSONDecodeError, TypeError):
            citations = []
        out.append(
            {
                "rec_id": row["id"],
                "severity": row["severity"],
                "type": row["recommendation_type"],
                "entity": row["entity_name"] or row["entity_id"],
                "summary": row["summary"],
                "confidence": row["confidence"] or 0.0,
                "evidence_strength": row["evidence_strength"] or "—",
                "blast_radius": row["blast_radius"] or "—",
                "expected_benefit": row["expected_benefit"],
                "do_nothing_cost": row["do_nothing_cost"],
                "citation_count": len(citations) if isinstance(citations, list) else 0,
            }
        )

    if limit is not None:
        out = out[:limit]
    return out


if __name__ == "__main__":
    recs = pull_actionable_recs()
    print(f"{len(recs)} actionable radar recs")
    for r in recs:
        print(f"  [{r['severity']:10s}] {r['type']:22s} | {r['entity']:30s} | {r['summary'][:60]}")
