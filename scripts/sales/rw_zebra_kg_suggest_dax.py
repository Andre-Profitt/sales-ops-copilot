"""Authoring assistant — given an intent string, score patterns from
data/zebra_kg/dax_patterns.json by fit and return top N candidates with
RW-adapted DAX suggestions.

Usage:
    python3 -m scripts.sales.rw_zebra_kg_suggest_dax \\
      --intent "7-day window of Closed Won ARR" --top 3
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ATLAS = REPO_ROOT / "data/zebra_kg/dax_patterns.json"

_STOPWORDS = frozenset(
    {
        "of",
        "the",
        "a",
        "an",
        "with",
        "for",
        "in",
        "on",
        "by",
        "to",
        "from",
        "and",
        "or",
    }
)

_INTENT_TAG_MAP = {
    # Time tokens
    "7-day": ["time:dates_in_period", "time:date_add", "time:today_arithmetic"],
    "7d": ["time:dates_in_period", "time:date_add", "time:today_arithmetic"],
    "last": ["time:dates_in_period", "time:date_add", "time:sameperiodlastyear"],
    "rolling": ["time:dates_in_period", "time:date_add"],
    "yoy": ["time:sameperiodlastyear", "time:date_add"],
    "ytd": ["time:datesytd"],
    "py": ["time:sameperiodlastyear"],
    "previous": ["time:sameperiodlastyear", "time:date_add"],
    "year-over-year": ["time:sameperiodlastyear"],
    "window": ["time:dates_in_period", "time:datesbetween"],
    # Aggregation tokens
    "sum": ["agg:sum"],
    "count": ["agg:countrows", "agg:countx"],
    "ratio": ["agg:divide"],
    "rate": ["agg:divide"],
    "pct": ["agg:divide"],
    "percentage": ["agg:divide"],
    "average": ["agg:averagex"],
    # Filter / conditional tokens
    "filtered": ["filter:filter", "filter:calculate"],
    "where": ["filter:filter", "filter:calculate"],
    "without": ["filter:filter", "filter:calculate", "cond:if"],
    "conditional": ["cond:if", "cond:switch"],
    "exception": ["cond:if", "filter:filter"],
    "approval": ["cond:if", "filter:filter"],
    "gate": ["cond:if", "filter:filter"],
    "variance": ["agg:divide"],
    "vs": ["time:sameperiodlastyear", "agg:divide"],
}

_RW_RENAME_MAP = {
    "Sales Table": "f_opportunity",
    "Sales": "f_opportunity",
    "Calendar": "d_calendar",
    "BusinessUnits": "d_region",
    "KPIs": "d_kpi",
    "Products": "d_product",
    "Comments": "d_comment",
    "Inventory": "f_opportunity",
    "Cost": "f_opportunity",
    "Revenue": "f_opportunity",
}


def tokenize_intent(intent: str) -> list[str]:
    """Lowercase, split on whitespace, drop stopwords."""
    return [t for t in re.split(r"\s+", intent.lower().strip()) if t and t not in _STOPWORDS]


def score_pattern(name: str, pattern: dict, intent_tokens: list[str]) -> int:
    """Compute fit score for a pattern given intent tokens."""
    sig = set(pattern.get("signature", []))
    canonical = pattern.get("canonical_example", {}) or {}
    canonical_name = (canonical.get("name", "") or "").lower()
    canonical_dax = (canonical.get("expression", "") or "").lower()

    score = 0
    matched_tags: set[str] = set()

    for token in intent_tokens:
        # +5 for tag matches via the keyword map
        for tag in _INTENT_TAG_MAP.get(token, []):
            if tag in sig:
                score += 5
                matched_tags.add(tag)
        # +3 if token in canonical name
        if token in canonical_name:
            score += 3
        # +2 if token in canonical DAX
        if token in canonical_dax:
            score += 2

    # −1 per pattern feature tag NOT semantically in intent
    unmatched = sig - matched_tags
    score -= len(unmatched)

    return score


def adapt_dax(dax: str, rename_map: dict[str, str] = _RW_RENAME_MAP) -> str:
    """Rewrite Zebra-template table names to RW equivalents via word-boundary
    regex. Cosmetic — the result is for review, not auto-deploy."""
    out = dax
    # Sort by descending length so multi-word renames (e.g. "Sales Table")
    # resolve before bare "Sales".
    for src, dst in sorted(rename_map.items(), key=lambda kv: -len(kv[0])):
        # Match the source name as a token boundary (preceded/followed by
        # non-identifier chars). DAX table refs look like `Sales[Field]`
        # or `'Sales Table'[Field]`. Be conservative: replace whole-word.
        pattern = re.compile(rf"\b{re.escape(src)}\b")
        out = pattern.sub(dst, out)
    return out


def suggest(intent: str, atlas: dict, top_n: int = 3) -> list[dict]:
    """Return top-N pattern candidates with adaptation suggestions."""
    patterns = atlas.get("patterns", {})
    if not patterns:
        return []
    intent_tokens = tokenize_intent(intent)

    scored = [(name, score_pattern(name, p, intent_tokens), p) for name, p in patterns.items()]
    scored.sort(key=lambda x: -x[1])

    out: list[dict] = []
    for name, score, p in scored[:top_n]:
        canonical = p.get("canonical_example", {}) or {}
        canonical_dax = canonical.get("expression", "") or ""
        out.append(
            {
                "pattern": name,
                "score": score,
                "match_count": p.get("match_count", 0),
                "templates": p.get("templates", [])[:3],
                "canonical_name": canonical.get("name", ""),
                "canonical_template": canonical.get("template", ""),
                "canonical_dax": canonical_dax,
                "adapted_dax": adapt_dax(canonical_dax),
            }
        )
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[0])
    parser.add_argument("--intent", type=str, required=True)
    parser.add_argument("--atlas", type=Path, default=DEFAULT_ATLAS)
    parser.add_argument("--top", type=int, default=3)
    args = parser.parse_args()

    atlas = json.loads(args.atlas.expanduser().read_text())
    suggestions = suggest(args.intent, atlas, top_n=args.top)

    print(f"# intent: {args.intent!r}")
    print(f"# top {len(suggestions)} candidates:\n")
    for i, s in enumerate(suggestions, 1):
        print(f"{i}. {s['pattern']}  (score={s['score']}, match_count={s['match_count']})")
        print(f"   from: {s['canonical_template']}  measure: {s['canonical_name']!r}")
        print(f"   canonical: {s['canonical_dax']}")
        print(f"   adapted:   {s['adapted_dax']}")
        print()


if __name__ == "__main__":
    main()
