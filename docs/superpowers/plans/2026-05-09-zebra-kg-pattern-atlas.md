# Zebra KG Pattern Atlas (PR4) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the KG **active** instead of inert. Mine the 439 Zebra DAX expressions and 130 relationships for canonical patterns, surface them as queryable atlases, and provide an authoring assistant that suggests Zebra DAX candidates for new RW measure authoring (so PR2's 5 measures and every future authoring task adapt patterns instead of inventing from scratch).

**Architecture:** Two pure analyzers (DAX, topology) emit static JSON atlases. Query CLI extension reads atlases for ad-hoc lookup. Authoring assistant takes an intent string + scores patterns for fit. The atlases are derived artifacts (gitignored); the summary doc is tracked.

**Tech Stack:** Python 3.13 stdlib only (`re`, `json`, `csv`, `collections`, `dataclasses`). pytest. No new third-party deps.

**Spec rationale:** Captured in conversation 2026-05-09 turn after PR3 push. Andre flagged that we built KG storage but never analyzed it; "best probe/rebuild action layer" needed.

**Branch:** `feat/track-rw-tooling`. Local commits only; Codex pushes/PRs.

**Predecessor work:**

- KG core (`bbcff37`) — `data/zebra_kg/measure_catalog.csv` (439 measures × 7 cols incl. full DAX + scenario), `nodes_datamodel.jsonl` (1572 nodes), `edges_datamodel.jsonl` (1099 edges)
- Recipe pipeline (`8a396bf..fe615d7`) — visual-side consumer; PR4 is the data-model-side consumer

**Sequencing:** PR4 lands before PR2. Once the atlases exist, PR2's 5 measures get authored _from_ canonical patterns (cite source template + DAX shape in TMDL comments).

---

## File structure

```
scripts/sales/
  rw_zebra_kg_dax_atlas.py        NEW — DAX feature extraction + clustering
  rw_zebra_kg_topology_atlas.py   NEW — Relationship topology analysis
  rw_zebra_kg_query.py            MOD — add --dax-pattern + --topology flags
  rw_zebra_kg_suggest_dax.py      NEW — intent → pattern → DAX candidates

tests/sales/
  test_rw_zebra_kg_dax_atlas.py        NEW
  test_rw_zebra_kg_topology_atlas.py   NEW
  test_rw_zebra_kg_suggest_dax.py      NEW
  (test_rw_zebra_kg_query.py extended for new flags)

data/zebra_kg/
  dax_patterns.json               NEW (gitignored — derived)
  topology_patterns.json          NEW (gitignored — derived)

docs/sales/
  RW_ZEBRA_KG_PATTERNS.md         NEW — tracked summary doc
```

---

## Task 1: DAX feature extractor + atlas

**Files:**

- Create: `scripts/sales/rw_zebra_kg_dax_atlas.py`
- Create: `tests/sales/test_rw_zebra_kg_dax_atlas.py`

### Goal

Read `data/zebra_kg/measure_catalog.csv` (439 rows). For each measure, extract a feature vector (which DAX functions used, in what role). Cluster by feature signature. Emit `data/zebra_kg/dax_patterns.json` keyed by pattern name with: signature, match count, templates, canonical example, sample list.

### Feature signature design

Each measure produces a frozenset of feature tags from regex matches over its DAX expression:

| Tag                                                                               | Regex                             | Meaning                    |
| --------------------------------------------------------------------------------- | --------------------------------- | -------------------------- |
| `time:dates_in_period`                                                            | `\bDATESINPERIOD\b`               | rolling N-day/month window |
| `time:date_add`                                                                   | `\bDATEADD\b`                     | shift by N units           |
| `time:sameperiodlastyear`                                                         | `\bSAMEPERIODLASTYEAR\b`          | classic YoY                |
| `time:datesytd`                                                                   | `\bDATESYTD\b`                    | YTD aggregation            |
| `time:datesbetween`                                                               | `\bDATESBETWEEN\b`                | explicit start/end         |
| `time:today_arithmetic`                                                           | `\bTODAY\s*\(\s*\)\s*[-+]`        | `TODAY() - N` style        |
| `agg:sum`                                                                         | `\bSUM\s*\(`                      | direct SUM                 |
| `agg:countrows`                                                                   | `\bCOUNTROWS\s*\(`                | row count                  |
| `agg:divide`                                                                      | `\bDIVIDE\s*\(`                   | safe ratio                 |
| `agg:sumx` / `agg:countx` / `agg:averagex`                                        | `\b(SUMX\|COUNTX\|AVERAGEX)\s*\(` | iterators                  |
| `filter:calculate`                                                                | `\bCALCULATE\s*\(`                | filter context modifier    |
| `filter:filter`                                                                   | `\bFILTER\s*\(`                   | row-level predicate        |
| `filter:keepfilters` / `filter:all` / `filter:allexcept` / `filter:removefilters` | resp.                             | scope modifiers            |
| `cond:if` / `cond:switch`                                                         | resp.                             | conditional logic          |
| `var`                                                                             | `\bVAR\b` (with `RETURN`)         | variable usage             |
| `lookup:related`                                                                  | `\bRELATED\s*\(`                  | dim-side fetch             |
| `lookup:lookupvalue`                                                              | `\bLOOKUPVALUE\s*\(`              | explicit lookup            |

Pattern naming: cluster measures by tag-set. Each unique tag-set gets a deterministic pattern name from sorted tags joined with `+`. Rare clusters (≤2 measures) collapse into `pattern_misc`. Top patterns get pretty names via a small dictionary (e.g. `time:dates_in_period+agg:sum+filter:calculate` → `time_window_calculate_sum`).

### Implementation

Steps that the implementer follows:

- [ ] **Step 1: Test file** — write `tests/sales/test_rw_zebra_kg_dax_atlas.py` with 5 unit tests:
  - `test_extract_feature_tags_recognises_time_window` — `CALCULATE(SUM(Sales[Amount]), DATESINPERIOD(Calendar[Date], TODAY(), -7, DAY))` → tags include `time:dates_in_period`, `time:today_arithmetic`, `agg:sum`, `filter:calculate`
  - `test_extract_feature_tags_handles_yoy` — `CALCULATE([Sales], SAMEPERIODLASTYEAR(Calendar[Date]))` → `time:sameperiodlastyear`, `filter:calculate`
  - `test_extract_feature_tags_handles_variance` — `[Sales] - [Sales PY]` → no time/agg/filter tags (just measure refs); should not crash
  - `test_pattern_name_for_signature_deterministic` — same tag set → same name across calls
  - `test_build_atlas_clusters_real_corpus` — load real `measure_catalog.csv`, build atlas, assert: ≥10 distinct patterns, ≥1 pattern named with `time:` prefix, total measures across patterns equals input count (no drops). `skipif` if catalog file missing.

- [ ] **Step 2: Implementation** — `scripts/sales/rw_zebra_kg_dax_atlas.py`:

```python
"""Mine the Zebra DAX corpus for canonical patterns. Reads
data/zebra_kg/measure_catalog.csv (produced by rw_zebra_kg_datamodel),
extracts a feature signature per measure via regex, clusters by signature,
and emits data/zebra_kg/dax_patterns.json with per-pattern: signature,
match_count, templates, canonical example, sample measure list.

Usage:
    python3 -m scripts.sales.rw_zebra_kg_dax_atlas \\
      --catalog data/zebra_kg/measure_catalog.csv \\
      --out data/zebra_kg/dax_patterns.json
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CATALOG = REPO_ROOT / "data/zebra_kg/measure_catalog.csv"
DEFAULT_OUT = REPO_ROOT / "data/zebra_kg/dax_patterns.json"


# Feature tag definitions. Order matters: more specific tags first so e.g.
# DATESINPERIOD is tagged time:dates_in_period not just time:any.
_FEATURE_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("time:dates_in_period",     re.compile(r"\bDATESINPERIOD\b", re.IGNORECASE)),
    ("time:date_add",            re.compile(r"\bDATEADD\b", re.IGNORECASE)),
    ("time:sameperiodlastyear",  re.compile(r"\bSAMEPERIODLASTYEAR\b", re.IGNORECASE)),
    ("time:datesytd",            re.compile(r"\bDATESYTD\b", re.IGNORECASE)),
    ("time:datesbetween",        re.compile(r"\bDATESBETWEEN\b", re.IGNORECASE)),
    ("time:today_arithmetic",    re.compile(r"\bTODAY\s*\(\s*\)\s*[-+]")),
    ("agg:sum",                  re.compile(r"\bSUM\s*\(", re.IGNORECASE)),
    ("agg:countrows",            re.compile(r"\bCOUNTROWS\s*\(", re.IGNORECASE)),
    ("agg:divide",               re.compile(r"\bDIVIDE\s*\(", re.IGNORECASE)),
    ("agg:sumx",                 re.compile(r"\bSUMX\s*\(", re.IGNORECASE)),
    ("agg:countx",               re.compile(r"\bCOUNTX\s*\(", re.IGNORECASE)),
    ("agg:averagex",             re.compile(r"\bAVERAGEX\s*\(", re.IGNORECASE)),
    ("filter:calculate",         re.compile(r"\bCALCULATE\s*\(", re.IGNORECASE)),
    ("filter:filter",            re.compile(r"\bFILTER\s*\(", re.IGNORECASE)),
    ("filter:keepfilters",       re.compile(r"\bKEEPFILTERS\s*\(", re.IGNORECASE)),
    ("filter:all",               re.compile(r"\bALL\s*\(", re.IGNORECASE)),
    ("filter:allexcept",         re.compile(r"\bALLEXCEPT\s*\(", re.IGNORECASE)),
    ("filter:removefilters",     re.compile(r"\bREMOVEFILTERS\s*\(", re.IGNORECASE)),
    ("cond:if",                  re.compile(r"\bIF\s*\(", re.IGNORECASE)),
    ("cond:switch",              re.compile(r"\bSWITCH\s*\(", re.IGNORECASE)),
    ("var",                      re.compile(r"\bVAR\b", re.IGNORECASE)),
    ("lookup:related",           re.compile(r"\bRELATED\s*\(", re.IGNORECASE)),
    ("lookup:lookupvalue",       re.compile(r"\bLOOKUPVALUE\s*\(", re.IGNORECASE)),
]

# Pretty names for high-frequency clusters; falls through to deterministic
# tag-joined name otherwise.
_PRETTY_NAMES = {
    frozenset({"time:dates_in_period", "agg:sum", "filter:calculate"}):
        "time_window_calculate_sum",
    frozenset({"time:sameperiodlastyear", "filter:calculate"}):
        "yoy_via_sameperiodlastyear",
    frozenset({"time:datesytd", "filter:calculate"}):
        "ytd_via_datesytd",
    frozenset({"agg:divide"}):
        "safe_ratio",
    frozenset({"filter:calculate", "filter:filter"}):
        "filter_calculate_predicate",
    frozenset({"cond:if", "filter:calculate"}):
        "conditional_aggregate",
    frozenset({"agg:countrows", "filter:calculate"}):
        "filtered_row_count",
}


def extract_feature_tags(dax: str) -> frozenset[str]:
    """Return the set of feature tags for a DAX expression."""
    if not isinstance(dax, str) or not dax.strip():
        return frozenset()
    tags: set[str] = set()
    for tag, pat in _FEATURE_PATTERNS:
        if pat.search(dax):
            tags.add(tag)
    return frozenset(tags)


def pattern_name_for_signature(sig: frozenset[str]) -> str:
    """Deterministic pattern name from a tag set."""
    if not sig:
        return "pattern_no_features"
    if sig in _PRETTY_NAMES:
        return _PRETTY_NAMES[sig]
    return "+".join(sorted(sig))


@dataclass
class Pattern:
    name: str
    signature: list = field(default_factory=list)
    match_count: int = 0
    templates: list = field(default_factory=list)
    canonical_example: dict = field(default_factory=dict)
    samples: list = field(default_factory=list)


def build_atlas(rows: Iterable[dict]) -> dict:
    """Cluster measures by feature signature → atlas dict."""
    by_sig: dict[frozenset, list[dict]] = defaultdict(list)
    for row in rows:
        dax = row.get("expression", "")
        sig = extract_feature_tags(dax)
        by_sig[sig].append(row)

    patterns: dict[str, dict] = {}
    misc: list[dict] = []
    for sig, measures in by_sig.items():
        if len(measures) <= 2:
            misc.extend(measures)
            continue
        name = pattern_name_for_signature(sig)
        templates = sorted({m["template_slug"] for m in measures})
        canonical = max(measures, key=lambda m: len(m.get("expression", "")))
        patterns[name] = {
            "signature": sorted(sig),
            "match_count": len(measures),
            "templates": templates,
            "canonical_example": {
                "name": canonical["name"],
                "table": canonical.get("table", ""),
                "template": canonical["template_slug"],
                "expression": canonical.get("expression", ""),
                "format_string": canonical.get("format_string", ""),
            },
            "samples": [
                {"name": m["name"], "template": m["template_slug"]}
                for m in measures[:8]
            ],
        }
    if misc:
        patterns["pattern_misc"] = {
            "signature": [],
            "match_count": len(misc),
            "templates": sorted({m["template_slug"] for m in misc}),
            "canonical_example": {},
            "samples": [
                {"name": m["name"], "template": m["template_slug"]}
                for m in misc[:8]
            ],
        }
    return {
        "total_measures": sum(p["match_count"] for p in patterns.values()),
        "pattern_count": len(patterns),
        "patterns": patterns,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[0])
    parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()

    catalog = args.catalog.expanduser()
    rows = list(csv.DictReader(catalog.open()))
    atlas = build_atlas(rows)

    out = args.out.expanduser()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(atlas, indent=2, ensure_ascii=False) + "\n")

    print(f"measures: {atlas['total_measures']}")
    print(f"patterns: {atlas['pattern_count']}")
    print(f"top 8 by match_count:")
    for name, p in sorted(
        atlas["patterns"].items(), key=lambda kv: -kv[1]["match_count"]
    )[:8]:
        print(f"  {name:48} {p['match_count']:4}  templates={len(p['templates'])}")
    print(f"out: {out}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Run tests** — `4 unit + 1 corpus = 5 passed`
- [ ] **Step 4: End-to-end** — `python3 -m scripts.sales.rw_zebra_kg_dax_atlas` → prints pattern counts, writes JSON
- [ ] **Step 5: Inspect findings** — paste the top 8 patterns from stdout into the report; this is the "what did we learn" outcome
- [ ] **Step 6: Commit** — `feat(track:rw): zebra_kg DAX pattern atlas — 439 measures clustered`

---

## Task 2: Topology atlas

**Files:**

- Create: `scripts/sales/rw_zebra_kg_topology_atlas.py`
- Create: `tests/sales/test_rw_zebra_kg_topology_atlas.py`

### Goal

Read `data/zebra_kg/nodes_datamodel.jsonl` + `edges_datamodel.jsonl`. For each template, classify the relationship topology and emit `data/zebra_kg/topology_patterns.json`.

### Topology features per template

- `fact_tables`: tables that appear on the `from_table` side of M:1 relationships (heuristic: count of incoming M:1 edges)
- `dim_tables`: the `to_table` side of M:1 (heuristic: count of outgoing M:1 edges)
- `bidirectional_count`: relationships with `cross_filter == "both"`
- `inactive_count`: relationships with `active == False`
- `calendar_pattern`: does the template have a dedicated date dim? (table name regex `^d_?(calendar|date|time)`)
- `scenario_pattern`: dedicated scenario dim? (table containing measures with scenarios AC/PY/PL/FC pointing to a `Scenario`/`Version` table — or flat measure-per-scenario, no dim)
- `role_playing_dims`: same dim joined twice via different FK columns

### Steps

- [ ] **Step 1: Tests** — 4 unit (synthetic) + 1 corpus integration
- [ ] **Step 2: Implementation** — module with `classify_template_topology(template_slug, nodes, edges) -> dict` + `build_topology_atlas(nodes, edges) -> dict`
- [ ] **Step 3: Run tests + end-to-end + inspect findings**
- [ ] **Step 4: Commit** — `feat(track:rw): zebra_kg topology atlas — relationship patterns`

(Implementation detail deferred to the implementer — pattern matches Task 1's structure but operates on relationships not DAX. The plan would balloon if I expand it inline; the implementer is given Task 1 as the reference.)

---

## Task 3: Query CLI extension

**Files:**

- Modify: `scripts/sales/rw_zebra_kg_query.py`

### Goal

Add two new flags to the existing query CLI:

- `--dax-pattern <name>` — print the canonical example + samples for a named pattern from `dax_patterns.json`
- `--list-dax-patterns` — print all pattern names + match counts (sorted desc)
- `--topology <template_slug>` — print the topology classification for that template

### Steps

- [ ] **Step 1: Update tests** — extend `tests/sales/test_rw_zebra_kg_query.py` with 3 new tests covering the new flags using the fixtures from PR1's KG query test
- [ ] **Step 2: Implementation** — extend `main()` argparse + dispatch logic
- [ ] **Step 3: Smoke** — run all 3 new flags against real atlases, paste output
- [ ] **Step 4: Commit** — `feat(track:rw): query CLI — --dax-pattern + --topology + --list-dax-patterns`

---

## Task 4: Authoring assistant

**Files:**

- Create: `scripts/sales/rw_zebra_kg_suggest_dax.py`
- Create: `tests/sales/test_rw_zebra_kg_suggest_dax.py`

### Goal

Given an intent string (e.g., `"7-day window of Closed Won ARR"`), score patterns from the atlas by fit and return ranked candidates with adaptation suggestions.

### Scoring

Tokenize intent. For each pattern, compute fit score:

- +5 per intent token that matches a feature tag (e.g., "7-day" → `time:dates_in_period` or `time:today_arithmetic`)
- +3 per intent token that appears in the canonical example's name (e.g., "Closed Won" → matches measure named "Closed Won AC")
- +2 per intent token in the canonical DAX expression
- −1 per pattern feature tag not in the intent (penalize over-complex patterns)

Return top 3 by score with: pattern name, canonical DAX, suggested adaptation (replace template-specific table names with RW table names from a small dictionary `{"Sales": "f_opportunity", "Calendar": "d_calendar", "BusinessUnits": "d_region", "KPIs": "d_kpi"}`).

### Steps

- [ ] **Step 1: Tests** — 4 unit tests covering: intent tokenization, scoring against synthetic atlas, adaptation rename (Sales→f_opportunity), zero-match graceful fallback
- [ ] **Step 2: Implementation**
- [ ] **Step 3: Smoke** — run against the real atlas with 3 PR2-relevant intents:
  - `"7-day window of Closed Won ARR"`
  - `"Variance vs PY for Pipeline ARR"`
  - `"Stage 3+ deals without Commercial Approval"`
    Paste top-1 candidate per intent.
- [ ] **Step 4: Commit** — `feat(track:rw): zebra_kg DAX suggester — intent → ranked candidates`

---

## Task 5: Findings doc

**Files:**

- Create: `docs/sales/RW_ZEBRA_KG_PATTERNS.md`

### Goal

Tracked summary doc of what we learned. Auto-generates from the atlases — but the doc itself is hand-written, with embedded counts/excerpts.

### Sections

- **Methodology** — feature extraction, clustering, topology classification (1 paragraph)
- **Top 10 DAX patterns** — name, count, canonical example, list of using-templates
- **Topology findings** — calendar-table convention, scenario-dim usage rate, bidirectional cross-filter usage, fact/dim ratio per template
- **Adaptation guide for RW** — how to lift Zebra patterns into RW (table renames, motion_type filter add, ARR vs ACV split)
- **Implications for PR2** — for each of the 5 PR2 measures, cite the canonical Zebra pattern that informs the authoring

### Steps

- [ ] **Step 1: Generate sections programmatically** — small script (run inline, not committed) that reads the atlases and emits the markdown skeleton
- [ ] **Step 2: Hand-write the methodology + adaptation-guide sections**
- [ ] **Step 3: Commit** — `docs(track:rw): RW_ZEBRA_KG_PATTERNS — what 439 measures + 130 rels taught us`

---

## Task 6: Final pass + push

- [ ] **Step 1: Full pytest** — all sales tests pass
- [ ] **Step 2: Secret scan** — clean
- [ ] **Step 3: Update gitignore** — `data/zebra_kg/dax_patterns.json` and `topology_patterns.json` ignored
- [ ] **Step 4: Push branch** — Codex reviews

---

## Self-review

1. **Spec coverage:** every layer from the conversation maps to a task. DAX atlas (1), topology atlas (2), probe CLI (3), authoring assistant (4), findings doc (5).
2. **Scope discipline:** PR4 lands the ANALYSIS. PR2 lands the AUTHORING (uses PR4's outputs). Two clean PRs.
3. **Type consistency:** `Pattern`, `extract_feature_tags`, `pattern_name_for_signature` defined in Task 1, used identically in Tasks 3 + 4.
4. **Open follow-ups (deferred):**
   - Per-measure fitness signal (e.g., "this Zebra DAX uses VAR; RW model has no VAR equivalent yet — score-down")
   - Cross-template idiom detection (e.g., is the same DAX pattern used identically across 3+ templates? That's stronger evidence than a single example)
   - Suggester learning loop — once we author a measure, capture which Zebra pattern won and feed it back as a labeled example
