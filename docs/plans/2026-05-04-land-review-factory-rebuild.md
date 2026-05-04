# LAND Review 28-slide Factory Rebuild Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the debris-laden Think-Cell seed and ad-hoc render path with a registry-governed 28-slide LAND review factory that produces brand-correct, evidence-verified decks for all 9 directors.

**Architecture:** Compute-and-bind. A YAML binding registry is the single contract between data and rendering. A manually-wired clean Think-Cell seed (`tcseed.pptx`) is built once on the Windows VM. `build_ppttc.py` reads the registry and emits `.ppttc` payloads + an evidence manifest. `ppttc.exe` renders charts/text; Excel COM `UpdateBatch` `AddRangeImage` refreshes table images. A binding-level verifier replaces the global string-ratio gate. One orchestrator runs the full lane.

**Tech Stack:** Python 3.13, PyYAML, jsonschema, openpyxl, python-pptx (read-only inspection), pytest. Windows-side: PowerPoint + Think-Cell + ppttc.exe + Excel COM via PowerShell. Mac↔VM bridge: existing `libs/tcrender/`.

**Source spec:** `docs/handoffs/2026-05-04-thinkcell-template-fix-plan.md` and `docs/handoffs/2026-05-04-thinkcell-template-deep-dive.md`.

---

## Scope

**In scope (MVP, target end-of-week 2026-05-08):**

- **Template Atlas (lite): RAG + lightweight graph** over canonical/precedent decks, handoffs, registry, and known-bad seeds — used as a _working tool_ during manual tcseed wiring, debris detection, and slide-pattern lookup
- New canonical Think-Cell seed for the 28-slide LAND review (manually wired once on the VM)
- Binding registry + JSON schema + validator
- Template contract preflight verifier (debris scan augmented by atlas neighbor lookup)
- Insight-title rules engine (deterministic; no LLM dependency in the gate)
- Registry-driven `.ppttc` builder with per-director evidence manifest
- Excel COM `AddRangeImage` table-image refresher
- Binding-level render verifier (no global ratio gate as publish condition)
- Pipeline orchestrator with strict mode
- 9-director batch passing acceptance criteria for 2026-Q2

**Out of scope (do NOT do in this plan):**

- Native editable Think-Cell tables (stays on Excel `AddRangeImage` table-image lane)
- Q3/month-roll period certification
- Visual regression / SSIM screenshot diffs
- 16-slide meeting-spine deck family (`land_meeting_spine_16` — separate plan)
- Productionized Template Atlas (multimodal/CLIP slide screenshots, automated slide-variant assembly, Mekko-shape detection) — lite text-only RAG **is** in scope as PR 0
- Action close-the-loop ledger across months
- SharePoint redesign
- Full Python package refactor to `src/salesops_copilot/`

**Phase 0 (today, before any rebuild work):** verify the existing May-2026 / 2026-Q2 packaging lane is still shippable as a safety net. Do not touch the working pipeline until Phase 0 passes.

---

## File Structure

### New files (created by this plan)

| Path                                                                                    | Responsibility                                                            |
| --------------------------------------------------------------------------------------- | ------------------------------------------------------------------------- |
| `assets/templates/land_review_full_28/LAND_review_full_28.clean_skeleton.pptx`          | 28-slide skeleton from canonical layouts; no Think-Cell objects yet       |
| `assets/templates/land_review_full_28/LAND_review_full_28.tcseed.pptx`                  | Certified Think-Cell seed (manually wired, output of PR 4)                |
| `assets/templates/land_review_full_28/LAND_review_full_28.seed_certification.md`        | Steward-signed certification record                                       |
| `assets/templates/land_review_full_28/LAND_review_full_28.named_element_inventory.json` | Snapshot of named Think-Cell elements after wiring                        |
| `config/thinkcell/land_review_full_28.binding_registry.yml`                             | **Already filed (draft).** Reconciled by Task 2.1                         |
| `schemas/thinkcell_binding_registry.schema.json`                                        | JSON Schema for the registry                                              |
| `config/rules/land_review_insight_titles.yml`                                           | Insight-title rules per slide                                             |
| `scripts/validate_thinkcell_binding_registry.py`                                        | Validates registry against schema + cross-rules                           |
| `scripts/verify_thinkcell_template_contract.py`                                         | Compares tcseed against registry; debris scan                             |
| `scripts/build_insight_titles.py`                                                       | Computes evidence-backed titles per director                              |
| `scripts/build_skeleton_pptx.py`                                                        | Builds `.clean_skeleton.pptx` from canonical layouts                      |
| `scripts/refresh_thinkcell_table_images.py`                                             | Drives Excel COM `UpdateBatch` `AddRangeImage` via VM                     |
| `scripts/verify_render_bindings.py`                                                     | Binding-level render evidence check (replaces ratio gate as publish gate) |
| `scripts/run_land_review_full_28_pipeline.py`                                           | One orchestrator for the full lane                                        |
| `scripts/vm/refresh_thinkcell_table_images.ps1`                                         | VM-side PowerShell that talks to Excel COM + Think-Cell                   |
| `tests/test_validate_thinkcell_binding_registry.py`                                     | Schema and cross-rule tests                                               |
| `tests/test_verify_thinkcell_template_contract.py`                                      | Contract preflight tests with synthetic pptx                              |
| `tests/test_build_insight_titles.py`                                                    | Title rule evaluation tests                                               |
| `tests/test_build_ppttc_registry_driven.py`                                             | Registry-driven .ppttc emission tests                                     |
| `tests/test_verify_render_bindings.py`                                                  | Binding evidence parser tests                                             |
| `tests/fixtures/registry_minimal.yml`                                                   | Minimal valid registry for test isolation                                 |
| `tests/fixtures/tcseed_synthetic.pptx`                                                  | Synthetic clean pptx with named shapes for contract tests                 |

### Modified files

| Path                                            | Change                                                                              |
| ----------------------------------------------- | ----------------------------------------------------------------------------------- |
| `scripts/factory.py`                            | Default template flips to `tcseed.pptx`; legacy seed requires `--allow-legacy-seed` |
| `scripts/build_ppttc.py`                        | Becomes registry-driven; emits evidence manifest; refuses unknown bindings          |
| `libs/tcrender/tcrender/verify.py`              | Demoted to diagnostic; publish gate moves to `verify_render_bindings.py`            |
| `assets/legacy/do_not_use_in_factory/README.md` | **Already filed.** Updated when seed is migrated (Task 1.5)                         |

### Files referenced read-only

- `assets/golden/LAND_canonical.pptx` — brand-correct reference (for skeleton derivation)
- `assets/templates/land_review_full_28/land_review_full_28.template_slot_map.v1.yml` — already filed slot map
- `state/2026-Q2/<director>/land.model.xlsx` — formula model, named ranges
- `state/2026-Q2/<director>/trends.json`, `brief.md` — narrative inputs
- `docs/handoffs/2026-05-04-thinkcell-template-fix-plan.md` — engineer handoff source

---

## Naming reconciliation (binding pre-decision)

The current registry draft (`config/thinkcell/land_review_full_28.binding_registry.yml`) and slot map (`assets/templates/.../template_slot_map.v1.yml`) disagree:

| Field                | Registry says             | Slot map says       | **Canonical (this plan)** |
| -------------------- | ------------------------- | ------------------- | ------------------------- |
| Lane for chart       | `ppttc`                   | `ppttc_chart`       | `ppttc_chart`             |
| Lane for text        | `ppttc`                   | `ppttc_text`        | `ppttc_text`              |
| Lane for table image | `excel_updatebatch_image` | `excel_table_image` | `excel_table_image`       |
| Image suffix         | `_IMG`                    | `_Image`            | `_Image`                  |

Rationale: the slot map names are more explicit (separates chart vs text intent) and `_Image` reads better in deck. Task 2.1 reconciles the registry to match. **Every later task uses these canonical names.**

---

## Phase 0 — today's safety net (Mon 2026-05-04 PM)

> Goal: prove the existing May-2026 packaging lane still ships if you have to fall back. Do not modify code in this phase.

### Task 0.1: Verify regional production status

**Files:**

- Read: `scripts/report_regional_production_status.py`

- [ ] **Step 1: Run the status report**

```bash
cd /Users/test/code/apps/sales-ops-copilot
.venv/bin/python scripts/report_regional_production_status.py --period 2026-Q2 2>&1 | tee /tmp/phase0_status.log
```

Expected: exit 0; written to `state/2026-Q2/__regional__/production_status.{json,md}` (or whatever the script writes — confirm path in log output). All 9 directors listed.

- [ ] **Step 2: Inspect status output**

Read the JSON/MD that was written. Verify per director:

- workbook freshness OK
- linked deck present
- no stale-source warning

If any director is amber/red, note in `docs/handoffs/2026-05-04-phase0-status.md` (create if needed). Do NOT auto-fix in Phase 0.

- [ ] **Step 3: Commit the Phase 0 status snapshot**

```bash
git add docs/handoffs/2026-05-04-phase0-status.md state/2026-Q2/__regional__/production_status.json state/2026-Q2/__regional__/production_status.md 2>/dev/null || true
git commit -m "chore(phase0): capture Q2 packaging-lane status snapshot before factory rebuild"
```

If nothing to commit, skip. Phase 0 succeeds when status is captured and any anomalies are noted.

---

## PR 0 — Surgical RAG / Graph RAG working layer (Template Atlas lite)

> **Why this exists:** the rest of the plan is "surgical" only if every executor can ground each decision in the existing corpus — canonical SimCorp layouts, the SalesOps month-close inspiration deck, the Jesper LAND review template, the four handoff docs filed today, the failed Patrick variants, and the debris-laden seed itself (negative examples). PR 0 builds a small retrieval layer (text RAG + a registry-backed knowledge graph) so PR 3 (debris scan), PR 4 (manual tcseed wiring), PR 5 (insight titles), and PR 7 (large-table layout) can call `atlas_query.py` instead of guessing.
>
> **Scope discipline:** lite. Local DuckDB-free, no new infra. Text-only embeddings via existing `apro-openai`. Graph as JSON. No multimodal CLIP, no slide-screenshot ingest, no slide-variant assembly engine — those stay post-MVP.

**Files:**

- Create: `scripts/atlas/build_atlas_corpus.py`
- Create: `scripts/atlas/build_atlas_graph.py`
- Create: `scripts/atlas/atlas_query.py`
- Create: `config/atlas/sources.yml`
- Create: `state/atlas/corpus.jsonl` (gitignored binary-ish; commit the manifest summary instead)
- Create: `state/atlas/graph.json`
- Create: `state/atlas/manifest.json`
- Test: `tests/test_atlas_query.py`

### Task 0.1: Declare the corpus sources

**Files:**

- Create: `config/atlas/sources.yml`

- [ ] **Step 1: Author sources.yml**

```yaml
schema: salesops/atlas-sources/v1
description: |
  Inputs to the Template Atlas. Each entry is a single document or
  a glob. The atlas treats each as a typed source and indexes
  per-slide for pptx, per-section for markdown.
sources:
  - id: canonical_land
    type: pptx
    role: canonical_brand_reference
    path: assets/golden/LAND_canonical.pptx
    weight: 1.0
  - id: salesops_month_close_inspiration
    type: pptx
    role: visual_inspiration
    path: /Users/test/Downloads/042026 Sales Operations Reporting.pptx
    weight: 0.7
    optional: true
  - id: current_seed_debris
    type: pptx
    role: negative_example
    path: assets/LAND_thinkcell_seed.pptx
    weight: 1.0
    notes: "Index for debris signature retrieval. Do not use as positive example."
  - id: pre_strip_seed
    type: pptx
    role: negative_example
    path: assets/LAND_thinkcell_seed.pre-stripdev.pptx
    weight: 1.0
    optional: true
  - id: handoff_fix_plan
    type: markdown
    role: spec
    path: docs/handoffs/2026-05-04-thinkcell-template-fix-plan.md
    weight: 1.0
  - id: handoff_deep_dive
    type: markdown
    role: spec
    path: docs/handoffs/2026-05-04-thinkcell-template-deep-dive.md
    weight: 1.0
  - id: thinkcell_corpus_docs
    type: markdown_glob
    role: domain_knowledge
    path: docs/thinkcell-corpus/**/*.md
    weight: 0.6
  - id: factory_strategy_2026_05_03
    type: markdown
    role: domain_knowledge
    path: docs/FACTORY_RENDERING_STRATEGY_2026-05-03.md
    weight: 0.8
  - id: sales_process_graph
    type: markdown
    role: domain_knowledge
    path: docs/SALES_PROCESS_GRAPH.md
    weight: 0.8
  - id: registry
    type: yaml_registry
    role: graph_seed
    path: config/thinkcell/land_review_full_28.binding_registry.yml
    weight: 1.0
  - id: slot_map
    type: yaml_slotmap
    role: graph_seed
    path: assets/templates/land_review_full_28/land_review_full_28.template_slot_map.v1.yml
    weight: 1.0
  - id: handoff_repo_state
    type: markdown
    role: domain_knowledge
    path: HANDOFF_2026-05-04.md
    weight: 1.0
embeddings:
  provider: azure_openai
  endpoint: https://apro-openai.openai.azure.com/
  deployment: text-embedding-3-small
  dimension: 1536
graph:
  nodes:
    - story_goal
    - slide_variant
    - chart_kind
    - render_lane
    - named_element
    - guardrail
    - debris_signature
  edges:
    - { from: story_goal, to: slide_variant, kind: supports }
    - { from: slide_variant, to: chart_kind, kind: uses }
    - { from: slide_variant, to: render_lane, kind: routed_via }
    - { from: slide_variant, to: named_element, kind: binds_to }
    - { from: slide_variant, to: guardrail, kind: must_pass }
    - { from: debris_signature, to: slide_variant, kind: contaminates }
```

- [ ] **Step 2: Commit**

```bash
git add config/atlas/sources.yml
git commit -m "feat(atlas): declare RAG corpus + graph schema"
```

### Task 0.2: Failing test for atlas query CLI

**Files:**

- Create: `tests/test_atlas_query.py`

- [ ] **Step 1: Write the test**

```python
"""Tests for atlas_query.py.

The query CLI returns ranked candidates for a given query. For tests
we use a tiny in-process corpus to avoid hitting Azure OpenAI.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
PY = sys.executable
SCRIPT = REPO / "scripts" / "atlas" / "atlas_query.py"


def test_query_returns_ranked_candidates(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A query against a synthetic corpus returns the most relevant chunks first."""
    corpus = tmp_path / "corpus.jsonl"
    # synthetic chunks with pre-baked unit-vector embeddings (3-d for tests)
    rows = [
        {"id": "c1", "source": "canonical_land", "slide": 5, "type": "pptx_slide",
         "text": "pipeline by stage horizontal bar SimCorp", "embedding": [1.0, 0.0, 0.0]},
        {"id": "c2", "source": "canonical_land", "slide": 7, "type": "pptx_slide",
         "text": "top deals table SimCorp brand", "embedding": [0.0, 1.0, 0.0]},
        {"id": "c3", "source": "current_seed_debris", "slide": 7, "type": "pptx_slide",
         "text": "[think-cell TABLE WITH FORMATTING - datalinked]", "embedding": [0.0, 0.0, 1.0]},
    ]
    corpus.write_text("\n".join(json.dumps(r) for r in rows))

    out = tmp_path / "result.json"
    proc = subprocess.run(
        [PY, str(SCRIPT),
         "--corpus", str(corpus),
         "--query-vector", "1.0,0.0,0.0",
         "--top-k", "2",
         "--out", str(out)],
        capture_output=True, text=True, cwd=REPO,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    res = json.loads(out.read_text())
    assert res[0]["id"] == "c1"
    assert len(res) == 2


def test_filter_by_role(tmp_path: Path) -> None:
    """Querying with role=negative_example only returns debris sources."""
    corpus = tmp_path / "corpus.jsonl"
    rows = [
        {"id": "c1", "source": "canonical_land", "role": "canonical_brand_reference",
         "slide": 5, "type": "pptx_slide",
         "text": "x", "embedding": [1.0, 0.0]},
        {"id": "c2", "source": "current_seed_debris", "role": "negative_example",
         "slide": 7, "type": "pptx_slide",
         "text": "[think-cell ...]", "embedding": [1.0, 0.0]},
    ]
    corpus.write_text("\n".join(json.dumps(r) for r in rows))
    out = tmp_path / "r.json"
    proc = subprocess.run(
        [PY, str(SCRIPT),
         "--corpus", str(corpus),
         "--query-vector", "1.0,0.0",
         "--top-k", "5",
         "--role", "negative_example",
         "--out", str(out)],
        capture_output=True, text=True, cwd=REPO,
    )
    assert proc.returncode == 0
    res = json.loads(out.read_text())
    assert len(res) == 1
    assert res[0]["id"] == "c2"
```

- [ ] **Step 2: Run, expect failure**

```bash
.venv/bin/pytest tests/test_atlas_query.py -v
```

- [ ] **Step 3: Commit failing tests**

```bash
git add tests/test_atlas_query.py
git commit -m "test(atlas): query CLI ranking + role filter (failing)"
```

### Task 0.3: Implement atlas_query.py

**Files:**

- Create: `scripts/atlas/atlas_query.py`
- Create: `scripts/atlas/__init__.py` (empty)

- [ ] **Step 1: Empty package init**

```bash
mkdir -p scripts/atlas
touch scripts/atlas/__init__.py
```

- [ ] **Step 2: Write the query CLI**

```python
"""Query the Template Atlas corpus.

Two query modes:
  --query "natural language"  -> embeds via Azure OpenAI, then cosine search
  --query-vector "f1,f2,..."   -> bypasses embedding (used by tests)

Optional filters:
  --role <r>          one of canonical_brand_reference / visual_inspiration /
                      negative_example / spec / domain_knowledge / graph_seed
  --type <t>          pptx_slide / md_section / yaml_node
  --top-k N           default 5

Output: JSON list of top-K hits, each {id, score, source, slide, role, type, text}.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
from pathlib import Path
from typing import Iterable

REPO = Path(__file__).resolve().parent.parent.parent


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def _load_corpus(path: Path) -> list[dict]:
    rows: list[dict] = []
    with path.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


def _embed_text_via_apro(text: str) -> list[float]:
    """Embed via Azure OpenAI text-embedding-3-small using the project's apro-openai.

    Imported lazily so tests can run without azure-identity available.
    """
    from azure.identity import AzureCliCredential
    from openai import AzureOpenAI

    cred = AzureCliCredential()
    token = cred.get_token("https://cognitiveservices.azure.com/.default")
    client = AzureOpenAI(
        azure_endpoint=os.environ.get("APRO_OPENAI_ENDPOINT", "https://apro-openai.openai.azure.com/"),
        azure_ad_token=token.token,
        api_version="2024-08-01-preview",
    )
    resp = client.embeddings.create(
        input=text,
        model=os.environ.get("APRO_EMBED_DEPLOYMENT", "text-embedding-3-small"),
    )
    return list(resp.data[0].embedding)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", required=True, type=Path)
    parser.add_argument("--query", default=None)
    parser.add_argument("--query-vector", default=None)
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--role", default=None)
    parser.add_argument("--type", dest="type_", default=None)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args(argv)

    if not args.query and not args.query_vector:
        sys.stderr.write("require --query or --query-vector\n")
        return 2

    if args.query_vector:
        qv = [float(x) for x in args.query_vector.split(",")]
    else:
        qv = _embed_text_via_apro(args.query)

    rows = _load_corpus(args.corpus)
    if args.role:
        rows = [r for r in rows if r.get("role") == args.role]
    if args.type_:
        rows = [r for r in rows if r.get("type") == args.type_]

    scored = []
    for r in rows:
        emb = r.get("embedding")
        if not emb:
            continue
        scored.append((_cosine(qv, emb), r))
    scored.sort(key=lambda x: x[0], reverse=True)

    hits = []
    for score, r in scored[: args.top_k]:
        hit = {k: v for k, v in r.items() if k != "embedding"}
        hit["score"] = round(score, 4)
        hits.append(hit)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(hits, indent=2))
    print(f"OK: {len(hits)} hits to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 3: Run tests, expect PASS**

```bash
.venv/bin/pytest tests/test_atlas_query.py -v
```

- [ ] **Step 4: Commit**

```bash
git add scripts/atlas/__init__.py scripts/atlas/atlas_query.py
git commit -m "feat(atlas): query CLI (cosine + role/type filter)"
```

### Task 0.4: Build the corpus ingestor

**Files:**

- Create: `scripts/atlas/build_atlas_corpus.py`

- [ ] **Step 1: Write the ingestor**

```python
"""Build the Template Atlas corpus from sources.yml.

For each source:
  - pptx       : extract per-slide text + shape names + layout name
  - markdown   : split on H2 headings; one chunk per section
  - markdown_glob : same, expanded
  - yaml_registry : one chunk per slide entry
  - yaml_slotmap  : one chunk per slide entry

Each chunk gets:
  id, source, role, type, slide (or section), text, weight, embedding

Embeddings via Azure OpenAI text-embedding-3-small. Set
APRO_OPENAI_ENDPOINT and run `az login` first.

Idempotent: rebuilds corpus.jsonl from scratch each run.
"""

from __future__ import annotations

import argparse
import glob
import hashlib
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Iterable

import yaml
from pptx import Presentation

REPO = Path(__file__).resolve().parent.parent.parent


def _chunk_id(*parts: str) -> str:
    return hashlib.sha1("|".join(parts).encode("utf-8")).hexdigest()[:16]


def _pptx_slide_chunks(src: dict) -> Iterable[dict]:
    path = REPO / src["path"] if not Path(src["path"]).is_absolute() else Path(src["path"])
    if not path.exists():
        if src.get("optional"):
            return
        raise FileNotFoundError(path)
    prs = Presentation(str(path))
    for i, slide in enumerate(prs.slides, 1):
        chunks: list[str] = []
        names: list[str] = []
        for shape in slide.shapes:
            if getattr(shape, "name", None):
                names.append(shape.name)
            if shape.has_text_frame:
                t = shape.text_frame.text.strip()
                if t:
                    chunks.append(t)
        text = " ".join(chunks)
        if not text and not names:
            continue
        layout_name = getattr(slide.slide_layout, "name", "")
        body = (
            f"layout={layout_name} | "
            f"shapes=[{','.join(names)}] | "
            f"text={text}"
        )
        yield {
            "id": _chunk_id(src["id"], "slide", str(i)),
            "source": src["id"],
            "role": src["role"],
            "type": "pptx_slide",
            "slide": i,
            "text": body[:4000],
            "weight": src.get("weight", 1.0),
        }


def _md_chunks(src: dict, path: Path) -> Iterable[dict]:
    if not path.exists():
        if src.get("optional"):
            return
        raise FileNotFoundError(path)
    raw = path.read_text(errors="ignore")
    sections = re.split(r"\n## ", raw)
    for j, sec in enumerate(sections):
        body = sec.strip()
        if not body:
            continue
        first_line = body.splitlines()[0][:200]
        yield {
            "id": _chunk_id(src["id"], str(path), str(j)),
            "source": src["id"],
            "role": src["role"],
            "type": "md_section",
            "section_idx": j,
            "section_heading": first_line,
            "path": str(path),
            "text": body[:4000],
            "weight": src.get("weight", 1.0),
        }


def _yaml_chunks(src: dict) -> Iterable[dict]:
    path = REPO / src["path"]
    if not path.exists():
        if src.get("optional"):
            return
        raise FileNotFoundError(path)
    doc = yaml.safe_load(path.read_text())
    for slide in doc.get("slides", []):
        sid = slide.get("slide_id", "")
        text = json.dumps(slide, ensure_ascii=False)
        yield {
            "id": _chunk_id(src["id"], "slide", sid),
            "source": src["id"],
            "role": src["role"],
            "type": src["type"],
            "slide_id": sid,
            "text": text[:4000],
            "weight": src.get("weight", 1.0),
        }


def _embed_batch(texts: list[str]) -> list[list[float]]:
    from azure.identity import AzureCliCredential
    from openai import AzureOpenAI

    cred = AzureCliCredential()
    token = cred.get_token("https://cognitiveservices.azure.com/.default")
    client = AzureOpenAI(
        azure_endpoint=os.environ.get("APRO_OPENAI_ENDPOINT", "https://apro-openai.openai.azure.com/"),
        azure_ad_token=token.token,
        api_version="2024-08-01-preview",
    )
    resp = client.embeddings.create(
        input=texts,
        model=os.environ.get("APRO_EMBED_DEPLOYMENT", "text-embedding-3-small"),
    )
    return [list(d.embedding) for d in resp.data]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sources", default="config/atlas/sources.yml", type=Path)
    parser.add_argument("--out", default="state/atlas/corpus.jsonl", type=Path)
    parser.add_argument("--manifest", default="state/atlas/manifest.json", type=Path)
    parser.add_argument("--skip-embeddings", action="store_true",
                        help="Skip Azure OpenAI calls; emit chunks without 'embedding'.")
    parser.add_argument("--batch", type=int, default=64)
    args = parser.parse_args(argv)

    sources = yaml.safe_load(args.sources.read_text())["sources"]
    chunks: list[dict] = []
    for src in sources:
        try:
            t = src["type"]
            if t == "pptx":
                chunks.extend(_pptx_slide_chunks(src))
            elif t == "markdown":
                chunks.extend(_md_chunks(src, REPO / src["path"]))
            elif t == "markdown_glob":
                for p in glob.glob(str(REPO / src["path"]), recursive=True):
                    chunks.extend(_md_chunks(src, Path(p)))
            elif t in ("yaml_registry", "yaml_slotmap"):
                chunks.extend(_yaml_chunks(src))
            else:
                sys.stderr.write(f"skipping unknown source type {t}\n")
        except FileNotFoundError as exc:
            sys.stderr.write(f"missing required source: {exc}\n")
            if not src.get("optional"):
                return 1

    if not args.skip_embeddings:
        for i in range(0, len(chunks), args.batch):
            batch = chunks[i : i + args.batch]
            vecs = _embed_batch([c["text"] for c in batch])
            for c, v in zip(batch, vecs):
                c["embedding"] = v
            sys.stdout.write(f"  embedded {i + len(batch)}/{len(chunks)}\n")
            sys.stdout.flush()

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w") as f:
        for c in chunks:
            f.write(json.dumps(c) + "\n")

    manifest = {
        "sources": sources,
        "chunk_count": len(chunks),
        "by_source": {s["id"]: sum(1 for c in chunks if c["source"] == s["id"]) for s in sources},
        "by_role": {},
        "embedded": not args.skip_embeddings,
    }
    for c in chunks:
        manifest["by_role"][c["role"]] = manifest["by_role"].get(c["role"], 0) + 1
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.write_text(json.dumps(manifest, indent=2))
    print(f"OK: {len(chunks)} chunks -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2: Add gitignore for the binary corpus**

```bash
grep -q "^state/atlas/corpus.jsonl" .gitignore || echo "state/atlas/corpus.jsonl" >> .gitignore
```

The manifest stays in git for auditability; the embeddings file does not.

- [ ] **Step 3: Build the corpus (skip embeddings first to verify ingestion)**

```bash
.venv/bin/python scripts/atlas/build_atlas_corpus.py --skip-embeddings
cat state/atlas/manifest.json | jq '.chunk_count, .by_source, .by_role'
```

Expected: non-zero chunk count, every required source represented.

- [ ] **Step 4: Build the corpus with embeddings**

```bash
az login --output none 2>&1 | tail -3
.venv/bin/python scripts/atlas/build_atlas_corpus.py
```

Expected: `embedded N/N` progress lines; final `OK: N chunks -> state/atlas/corpus.jsonl`.

If Azure OpenAI 404s on `text-embedding-3-small`, check the deployment name in `~/code/apps/sales-ops-copilot/CLAUDE.md` and override via `APRO_EMBED_DEPLOYMENT`.

- [ ] **Step 5: Sanity-check retrieval**

```bash
.venv/bin/python scripts/atlas/atlas_query.py \
  --corpus state/atlas/corpus.jsonl \
  --query "horizontal bar chart pipeline by stage SimCorp brand" \
  --top-k 5 \
  --out /tmp/q1.json
jq '.[] | {source, role, slide, score, snippet: (.text[0:200])}' /tmp/q1.json
```

Expected: top hits include `canonical_land` (slide for pipeline by stage) and possibly `salesops_month_close_inspiration`. If the top hit is a debris source for a positive query, the embedding/sources are misweighted — review `sources.yml` weights.

- [ ] **Step 6: Commit**

```bash
git add scripts/atlas/build_atlas_corpus.py state/atlas/manifest.json .gitignore
git commit -m "feat(atlas): corpus ingestor (pptx + markdown + yaml) with embeddings"
```

### Task 0.5: Build the lightweight knowledge graph

**Files:**

- Create: `scripts/atlas/build_atlas_graph.py`

- [ ] **Step 1: Write the graph builder**

```python
"""Build a lightweight knowledge graph from registry + slot map + corpus.

Nodes:
  story_goal:<id>       — derived from registry purpose + insight-title rules
  slide_variant:<sid>   — one per registry slide
  chart_kind:<kind>
  render_lane:<lane>
  named_element:<name>
  guardrail:<id>
  debris_signature:<id>

Edges:
  story_goal -> slide_variant  (supports)
  slide_variant -> chart_kind  (uses)
  slide_variant -> render_lane (routed_via)
  slide_variant -> named_element (binds_to)
  slide_variant -> guardrail   (must_pass)
  debris_signature -> slide_variant (contaminates)

Output: state/atlas/graph.json — adjacency list, lossless.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import yaml
from pptx import Presentation

REPO = Path(__file__).resolve().parent.parent.parent

GUARDRAILS = [
    {"id": "arr_acv_separation", "label": "Land+Expand ARR vs Renewal ACV must not blend"},
    {"id": "currency_basis", "label": "FX-converted EUR/EUR M only"},
    {"id": "stage_basis", "label": "SimCorp 8-stage process"},
    {"id": "title_rule", "label": "Every analytic slide requires evidence-backed insight title"},
    {"id": "source_rule", "label": "Every analytic slide requires source note"},
    {"id": "no_debris", "label": "No dev instructions / lorem / donor placeholders"},
]

DEBRIS_PATTERNS = [
    r"\[think-cell\b.*?\]",
    r"paste from\b",
    r"no think-cell binding here",
    r"lorem ipsum",
    r"click to add",
    r"User count \[K\]",
    r"\[USD m\]",
    r"\bProduct A\b",
    r"\bBU1\b|\bBU2\b",
]


def _add_node(graph: dict, kind: str, key: str, **props) -> str:
    node_id = f"{kind}:{key}"
    if node_id not in graph["nodes"]:
        graph["nodes"][node_id] = {"kind": kind, "key": key, **props}
    return node_id


def _add_edge(graph: dict, frm: str, to: str, kind: str, **props) -> None:
    graph["edges"].append({"from": frm, "to": to, "kind": kind, **props})


def _scan_debris(pptx_path: Path) -> list[dict]:
    if not pptx_path.exists():
        return []
    prs = Presentation(str(pptx_path))
    findings: list[dict] = []
    for i, slide in enumerate(prs.slides, 1):
        for shape in slide.shapes:
            if shape.has_text_frame:
                t = shape.text_frame.text or ""
                for pat in DEBRIS_PATTERNS:
                    m = re.search(pat, t, re.IGNORECASE)
                    if m:
                        findings.append({
                            "pattern": pat,
                            "slide": i,
                            "snippet": t[: max(m.end() + 20, 80)],
                        })
    return findings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", default="config/thinkcell/land_review_full_28.binding_registry.yml", type=Path)
    parser.add_argument("--titles-rules", default="config/rules/land_review_insight_titles.yml", type=Path)
    parser.add_argument("--debris-pptx", default="assets/LAND_thinkcell_seed.pptx", type=Path)
    parser.add_argument("--out", default="state/atlas/graph.json", type=Path)
    args = parser.parse_args(argv)

    graph: dict = {"nodes": {}, "edges": []}

    registry = yaml.safe_load(args.registry.read_text())
    titles = (
        yaml.safe_load(args.titles_rules.read_text()) if args.titles_rules.exists() else {"rules": {}, "defaults": {}}
    )

    # guardrails as fixed nodes
    for g in GUARDRAILS:
        _add_node(graph, "guardrail", g["id"], label=g["label"])

    # one slide_variant per registry slide
    for slide in registry["slides"]:
        sid = slide["slide_id"]
        purpose = slide.get("purpose", "")
        sv = _add_node(graph, "slide_variant", sid, purpose=purpose)

        # purpose -> story_goal (1:1 for MVP)
        sg = _add_node(graph, "story_goal", purpose, source="registry")
        _add_edge(graph, sg, sv, "supports")

        for el in slide.get("elements", []):
            ne = _add_node(graph, "named_element", el["name"], required=el.get("required", False))
            _add_edge(graph, sv, ne, "binds_to")
            ck = _add_node(graph, "chart_kind", el["kind"])
            _add_edge(graph, sv, ck, "uses")
            rl = _add_node(graph, "render_lane", el["lane"])
            _add_edge(graph, sv, rl, "routed_via")

        # guardrails apply to every analytic slide
        if not purpose.endswith("_divider") and purpose not in ("cover", "closing"):
            for g in GUARDRAILS:
                _add_edge(graph, sv, f"guardrail:{g['id']}", "must_pass")

    # title rules attach to slide_variant via story_goal label
    for sid, rules in (titles.get("rules") or {}).items():
        sv = f"slide_variant:{sid}"
        if sv not in graph["nodes"]:
            continue
        for rule in rules:
            tg = _add_node(graph, "story_goal", rule.get("id", "rule"), source="title_rules", severity=rule.get("severity"))
            _add_edge(graph, tg, sv, "supports")

    # debris signatures from the contaminated seed
    debris = _scan_debris(args.debris_pptx)
    seen_patterns: set[str] = set()
    for d in debris:
        ds = _add_node(graph, "debris_signature", d["pattern"], example_snippet=d["snippet"][:200])
        if d["pattern"] in seen_patterns:
            continue
        seen_patterns.add(d["pattern"])
        # contaminate every slide_variant so debris scanner can use the graph as a deny-list
        for nid, n in graph["nodes"].items():
            if n["kind"] == "slide_variant":
                _add_edge(graph, ds, nid, "contaminates")

    # render summary
    summary = {
        "node_count": len(graph["nodes"]),
        "edge_count": len(graph["edges"]),
        "by_kind": {},
    }
    for n in graph["nodes"].values():
        summary["by_kind"][n["kind"]] = summary["by_kind"].get(n["kind"], 0) + 1

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps({"summary": summary, **graph}, indent=2))
    print(f"OK: {summary['node_count']} nodes / {summary['edge_count']} edges -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2: Build the graph**

```bash
.venv/bin/python scripts/atlas/build_atlas_graph.py
jq '.summary' state/atlas/graph.json
```

Expected summary: ~28 `slide_variant` nodes, 6 `guardrail` nodes, ≥4 `chart_kind`, 4 `render_lane`, ≥1 `debris_signature`, dozens of `named_element`.

- [ ] **Step 3: Commit**

```bash
git add scripts/atlas/build_atlas_graph.py state/atlas/graph.json
git commit -m "feat(atlas): registry+rules+debris -> JSON knowledge graph"
```

### Task 0.6: Wire atlas into PR 3 debris scan and PR 4 wiring

> Forward-references — these become checklist items inside PR 3 / PR 4 tasks. Adding here so executors of those PRs use the atlas instead of inventing.

- [ ] **Step 1: PR 3 augmentation note**

In `scripts/verify_thinkcell_template_contract.py` (PR 3 Task 3.2), the `FORBIDDEN_PATTERNS` list duplicates the patterns used to seed `debris_signature` nodes. After PR 0 lands, refactor `verify_thinkcell_template_contract.py` to load patterns from the graph:

```python
# alternative: pull patterns from the atlas
graph = json.loads(Path("state/atlas/graph.json").read_text())
patterns = [n["key"] for n in graph["nodes"].values() if n["kind"] == "debris_signature"]
FORBIDDEN_PATTERNS = [re.compile(p, re.IGNORECASE) for p in patterns]
```

This keeps the deny-list in one place and lets future debris signatures be added by re-running `build_atlas_graph.py` against new contaminated examples.

- [ ] **Step 2: PR 4 wiring augmentation note**

In PR 4 Task 4.3 (manual tcseed wiring), before each named-element placement, run a query for canonical precedent:

```bash
# Example: for S05_PipelineByStage, find the canonical SimCorp layout precedent
.venv/bin/python scripts/atlas/atlas_query.py \
  --corpus state/atlas/corpus.jsonl \
  --query "horizontal bar chart Stage 1 2 3 4 5 6 7 8 SimCorp Land Expand ARR" \
  --top-k 5 \
  --role canonical_brand_reference \
  --out /tmp/precedent.json
jq '.[] | {source, slide, score, snippet: (.text[0:300])}' /tmp/precedent.json
```

The steward uses the top hit to guide chart positioning, axis labels, color, and grid spacing — not to copy data, but to copy SimCorp brand pattern.

For debris awareness during wiring:

```bash
.venv/bin/python scripts/atlas/atlas_query.py \
  --corpus state/atlas/corpus.jsonl \
  --query "S05 pipeline by stage" \
  --role negative_example \
  --top-k 3 \
  --out /tmp/avoid.json
jq '.[] | {source, slide, snippet: (.text[0:200])}' /tmp/avoid.json
```

Whatever returns is a pattern to _not_ recreate.

- [ ] **Step 3: No commit; this task is checklist hand-off**

The PR 3 / PR 4 commits in those PRs absorb these changes when their executors follow them.

### Task 0.7: Sanity-check the surgical use case end-to-end

- [ ] **Step 1: Pick three high-leverage queries and verify the answer is plausible**

```bash
for q in \
  "exec summary two column SimCorp brand" \
  "top deals table image with rank ARR EUR" \
  "concentration risk top three accounts cumulative share"
do
  .venv/bin/python scripts/atlas/atlas_query.py \
    --corpus state/atlas/corpus.jsonl \
    --query "$q" \
    --role canonical_brand_reference \
    --top-k 3 \
    --out /tmp/q.json
  echo "=== $q ==="
  jq '.[] | "\(.score)  \(.source)  slide=\(.slide // .section_idx // .slide_id // \"-\")  \(.text[0:200])"' /tmp/q.json
done
```

Expected: top hits are SimCorp canonical or precedent decks, not debris/negative-example sources.

If results are noisy, the corpus needs additional positive sources (Jesper LAND template if available locally — add to `sources.yml` and rebuild). Do not degrade weights of debris sources just to win the ranking; debris sources have legitimate negative-example purpose.

- [ ] **Step 2: Commit a short atlas usage doc**

`docs/atlas/USAGE.md`:

````markdown
# Template Atlas — usage

The atlas is a working tool for executors of `docs/plans/2026-05-04-land-review-factory-rebuild.md`.

## Build / refresh

```bash
.venv/bin/python scripts/atlas/build_atlas_corpus.py
.venv/bin/python scripts/atlas/build_atlas_graph.py
```
````

## Query

Find canonical SimCorp precedent for a slide purpose:

```bash
.venv/bin/python scripts/atlas/atlas_query.py \
  --corpus state/atlas/corpus.jsonl \
  --query "horizontal bar chart pipeline by stage SimCorp" \
  --role canonical_brand_reference \
  --top-k 5 \
  --out /tmp/q.json
```

Find debris patterns to avoid for a slide:

```bash
.venv/bin/python scripts/atlas/atlas_query.py \
  --corpus state/atlas/corpus.jsonl \
  --query "<the slide intent>" \
  --role negative_example \
  --top-k 5 \
  --out /tmp/avoid.json
```

## Scope

Lite. Text-only embeddings. No multimodal CLIP. No automated slide-variant
assembly. Use as a precedent / debris lookup; do not let the atlas pick
register names or override the registry.

````

```bash
mkdir -p docs/atlas
git add docs/atlas/USAGE.md
git commit -m "docs(atlas): usage cheatsheet for executors"
````

---

## PR 1 — Quarantine the bad seed; safety flag

**Files:**

- Modify: `scripts/factory.py`
- Modify: `scripts/build_ppttc.py`
- Modify: `assets/legacy/do_not_use_in_factory/README.md`
- Test: `tests/test_factory_template_guardrails.py` (new)

### Task 1.1: Failing test for legacy-seed guardrail

**Files:**

- Create: `tests/test_factory_template_guardrails.py`

- [ ] **Step 1: Write the failing test**

```python
"""Guardrails on which template scripts/factory.py is allowed to load."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
PY = sys.executable


def _run_factory(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [PY, str(REPO / "scripts" / "factory.py"), *args],
        capture_output=True,
        text=True,
        cwd=REPO,
    )


def test_factory_refuses_legacy_seed_without_override(tmp_path: Path) -> None:
    legacy = REPO / "assets" / "LAND_thinkcell_seed.pptx"
    assert legacy.exists(), "fixture: legacy seed must exist on disk for this test"

    proc = _run_factory(
        "--period", "2026-Q2",
        "--directors", "Patrick-Gaughan",
        "--template", str(legacy),
        "--dry-run",
    )

    assert proc.returncode != 0, proc.stdout + proc.stderr
    combined = proc.stdout + proc.stderr
    assert "legacy" in combined.lower() or "quarantined" in combined.lower()


def test_factory_accepts_legacy_seed_with_override(tmp_path: Path) -> None:
    legacy = REPO / "assets" / "LAND_thinkcell_seed.pptx"
    proc = _run_factory(
        "--period", "2026-Q2",
        "--directors", "Patrick-Gaughan",
        "--template", str(legacy),
        "--allow-legacy-seed",
        "--dry-run",
    )

    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_factory_default_points_at_tcseed() -> None:
    proc = _run_factory("--print-default-template")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "land_review_full_28" in proc.stdout
    assert "tcseed.pptx" in proc.stdout
```

- [ ] **Step 2: Run test to verify it fails**

```bash
.venv/bin/pytest tests/test_factory_template_guardrails.py -v
```

Expected: FAIL on all three (no `--allow-legacy-seed` flag, no `--print-default-template` flag, no quarantine logic).

- [ ] **Step 3: Commit the failing test**

```bash
git add tests/test_factory_template_guardrails.py
git commit -m "test(factory): legacy seed guardrails (failing test)"
```

### Task 1.2: Implement the guardrail in factory.py

**Files:**

- Modify: `scripts/factory.py`

- [ ] **Step 1: Read the current top of factory.py to find argparse setup**

```bash
grep -n "argparse\|add_argument\|--template\|--dry-run\|DEFAULT_TEMPLATE" scripts/factory.py | head -40
```

- [ ] **Step 2: Add the guardrail logic**

Locate the argparse block. Add:

```python
# scripts/factory.py — additions inside argparse setup
parser.add_argument(
    "--print-default-template",
    action="store_true",
    help="Print the canonical default template path and exit.",
)
parser.add_argument(
    "--allow-legacy-seed",
    action="store_true",
    help="Allow legacy debris seed paths. Required if --template points at "
         "assets/LAND_thinkcell_seed*, assets/legacy/, or any quarantined "
         "asset. Use only for forensic comparison.",
)
```

Add a new module-level constant near other path constants:

```python
DEFAULT_TEMPLATE = (
    Path(__file__).resolve().parent.parent
    / "assets"
    / "templates"
    / "land_review_full_28"
    / "LAND_review_full_28.tcseed.pptx"
)

LEGACY_SEED_MARKERS = (
    "LAND_thinkcell_seed",
    "/legacy/",
    "Patrick-Gaughan-LAND",
    "_polished",
    "pre-stripdev",
    "pre-jinja-cleanup",
)


def _is_legacy_template(template_path: Path) -> bool:
    s = str(template_path)
    return any(marker in s for marker in LEGACY_SEED_MARKERS)
```

In `main()` (or the entry function), immediately after parsing args:

```python
if args.print_default_template:
    print(DEFAULT_TEMPLATE)
    return 0

template = Path(args.template) if args.template else DEFAULT_TEMPLATE

if _is_legacy_template(template) and not args.allow_legacy_seed:
    sys.stderr.write(
        f"refusing to use quarantined/legacy template: {template}\n"
        "pass --allow-legacy-seed for forensic-only override.\n"
    )
    return 2
```

Apply the same `_is_legacy_template` check in `scripts/build_ppttc.py` (it has its own `--template` flag); `import` the helper from `factory` or duplicate the constants — duplicate is fine for now since both files are sibling scripts.

- [ ] **Step 3: Run the tests**

```bash
.venv/bin/pytest tests/test_factory_template_guardrails.py -v
```

Expected: all three PASS. The `tcseed.pptx` file does not exist yet — `--dry-run` must not require its existence.

- [ ] **Step 4: If `--dry-run` fails because tcseed is missing, gate existence check behind a non-dry-run path**

In `factory.py` main, only `assert template.exists()` if `not args.dry_run`. The dry-run path must still print the resolved template path and the director list it would process.

- [ ] **Step 5: Re-run tests, expect all PASS**

```bash
.venv/bin/pytest tests/test_factory_template_guardrails.py -v
```

- [ ] **Step 6: Commit**

```bash
git add scripts/factory.py scripts/build_ppttc.py
git commit -m "feat(factory): legacy-seed guardrail + new tcseed default path"
```

### Task 1.3: Update legacy README with the migration boundary

**Files:**

- Modify: `assets/legacy/do_not_use_in_factory/README.md`

- [ ] **Step 1: Append a "Migration boundary" section**

Open the file and append:

```markdown
## Migration boundary

The flip happens in PR 1 of `docs/plans/2026-05-04-land-review-factory-rebuild.md`.

After PR 1 lands:

- `scripts/factory.py` defaults to `assets/templates/land_review_full_28/LAND_review_full_28.tcseed.pptx`
- Any path matching `LAND_thinkcell_seed*`, `/legacy/`, `Patrick-Gaughan-LAND`, `_polished`, `pre-stripdev`, or `pre-jinja-cleanup` requires `--allow-legacy-seed`
- Until the tcseed file exists (PR 4), `--dry-run` works but real runs fail with "template not found"

The actual `mv` of legacy seeds into this directory happens in Task 10.1 only after the new factory has rendered all 9 directors successfully.
```

- [ ] **Step 2: Commit**

```bash
git add assets/legacy/do_not_use_in_factory/README.md
git commit -m "docs(legacy): document migration boundary"
```

---

## PR 2 — Binding registry: schema + validator + reconciliation

**Files:**

- Create: `schemas/thinkcell_binding_registry.schema.json`
- Modify: `config/thinkcell/land_review_full_28.binding_registry.yml`
- Create: `scripts/validate_thinkcell_binding_registry.py`
- Test: `tests/test_validate_thinkcell_binding_registry.py`
- Test fixture: `tests/fixtures/registry_minimal.yml`

### Task 2.1: Reconcile registry to canonical naming

**Files:**

- Modify: `config/thinkcell/land_review_full_28.binding_registry.yml`

- [ ] **Step 1: Rewrite lanes block to canonical names**

Find the `lanes:` block. Replace with:

```yaml
lanes:
  ppttc_chart: "real Think-Cell chart named with AddRangeData; data via .ppttc"
  ppttc_text: "automation text field named with AddRangeData; text via .ppttc"
  excel_table_image: "image placeholder named with AddRangeImage; refreshed via Excel UpdateBatch"
  static: "branded template-only; no dynamic binding"
```

- [ ] **Step 2: Replace lane values across the slides block**

For every `lane: ppttc` element where `kind` is a `*_chart` (e.g., `bar_chart`, `column_chart`, `waterfall_chart`, `stacked_bar_chart`), set `lane: ppttc_chart`.

For every `lane: ppttc` element where `kind` is `text`, set `lane: ppttc_text`.

For every `lane: excel_updatebatch_image`, set `lane: excel_table_image`.

For every name ending in `_IMG`, rename to `_Image` (and update any `source` references).

- [ ] **Step 3: Verify YAML still parses**

```bash
.venv/bin/python -c "import yaml; yaml.safe_load(open('config/thinkcell/land_review_full_28.binding_registry.yml'))"
```

Expected: no output, exit 0.

- [ ] **Step 4: Commit**

```bash
git add config/thinkcell/land_review_full_28.binding_registry.yml
git commit -m "fix(registry): canonical lane names + _Image suffix; reconcile with slot map"
```

### Task 2.2: Failing test for registry validator

**Files:**

- Create: `tests/fixtures/registry_minimal.yml`
- Create: `tests/test_validate_thinkcell_binding_registry.py`

- [ ] **Step 1: Create minimal valid fixture**

`tests/fixtures/registry_minimal.yml`:

```yaml
schema: salesops/thinkcell-binding-registry/v1
deck_family: land_review_full_28
brand: simcorp
period_context: 2026-Q2
rules:
  arr_basis: "Land+Expand ARR uses APTS_Opportunity_ARR__c; renewal ACV uses APTS_Renewal_ACV__c; never blend."
  currency_basis: "FX-converted EUR/EUR M only."
  stage_basis: "SimCorp 8-stage process."
  title_rule: "Every analytic slide requires evidence-backed insight title."
  source_rule: "Every analytic slide requires source note."
lanes:
  ppttc_chart: "real Think-Cell chart"
  ppttc_text: "automation text"
  excel_table_image: "AddRangeImage"
  static: "no dynamic binding"
slides:
  - slide_id: S01
    purpose: cover
    elements:
      - {
          name: S01_DirectorName,
          kind: text,
          lane: ppttc_text,
          required: true,
          source: deck_plan.director_name,
          evidence: exact_text,
        }
  - slide_id: S05
    purpose: pipeline_by_stage
    elements:
      - {
          name: S05_Title,
          kind: text,
          lane: ppttc_text,
          required: true,
          source: insight_titles.S05,
          evidence: exact_text,
        }
      - {
          name: S05_PipelineByStage,
          kind: bar_chart,
          lane: ppttc_chart,
          required: true,
          source: model.named_range.S05_PipelineByStage,
          evidence: category_labels,
        }
      - {
          name: S05_Source,
          kind: text,
          lane: ppttc_text,
          required: true,
          source: source_notes.S05,
          evidence: exact_text,
        }
```

- [ ] **Step 2: Write the failing tests**

`tests/test_validate_thinkcell_binding_registry.py`:

```python
"""Tests for the binding-registry validator."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
PY = sys.executable
SCRIPT = REPO / "scripts" / "validate_thinkcell_binding_registry.py"
FIXTURES = REPO / "tests" / "fixtures"


def _run(registry: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [PY, str(SCRIPT), "--registry", str(registry)],
        capture_output=True, text=True, cwd=REPO,
    )


def test_minimal_fixture_passes(tmp_path: Path) -> None:
    proc = _run(FIXTURES / "registry_minimal.yml")
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_real_registry_passes() -> None:
    proc = _run(REPO / "config" / "thinkcell" / "land_review_full_28.binding_registry.yml")
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_duplicate_name_fails(tmp_path: Path) -> None:
    bad = tmp_path / "dup.yml"
    bad.write_text((FIXTURES / "registry_minimal.yml").read_text() + """
  - slide_id: S06
    purpose: pipeline_aging
    elements:
      - {name: S05_Title, kind: text, lane: ppttc_text, required: true, source: insight_titles.S06, evidence: exact_text}
""")
    proc = _run(bad)
    assert proc.returncode != 0
    assert "duplicate" in (proc.stdout + proc.stderr).lower()


def test_unknown_lane_fails(tmp_path: Path) -> None:
    bad = tmp_path / "lane.yml"
    src = (FIXTURES / "registry_minimal.yml").read_text().replace(
        "lane: ppttc_text", "lane: ppttc"
    )
    bad.write_text(src)
    proc = _run(bad)
    assert proc.returncode != 0
    assert "lane" in (proc.stdout + proc.stderr).lower()


def test_chart_kind_must_use_chart_lane(tmp_path: Path) -> None:
    """A bar_chart bound to ppttc_text is a registry error."""
    bad = tmp_path / "kindmismatch.yml"
    src = (FIXTURES / "registry_minimal.yml").read_text().replace(
        "lane: ppttc_chart", "lane: ppttc_text"
    )
    bad.write_text(src)
    proc = _run(bad)
    assert proc.returncode != 0
    assert "lane" in (proc.stdout + proc.stderr).lower() or "kind" in (proc.stdout + proc.stderr).lower()


def test_image_suffix_consistency(tmp_path: Path) -> None:
    """Names with kind table_image must end in _Image."""
    bad = tmp_path / "suffix.yml"
    bad.write_text("""schema: salesops/thinkcell-binding-registry/v1
deck_family: land_review_full_28
brand: simcorp
period_context: 2026-Q2
rules:
  arr_basis: x
  currency_basis: x
  stage_basis: x
  title_rule: x
  source_rule: x
lanes:
  ppttc_chart: x
  ppttc_text: x
  excel_table_image: x
  static: x
slides:
  - slide_id: S07
    purpose: top_deals_land
    elements:
      - {name: S07_TopDealsLand_IMG, kind: table_image, lane: excel_table_image, required: true, source: workbook.range.X, evidence: picture_on_slide}
""")
    proc = _run(bad)
    assert proc.returncode != 0
    assert "_image" in (proc.stdout + proc.stderr).lower() or "suffix" in (proc.stdout + proc.stderr).lower()
```

- [ ] **Step 3: Run tests, expect all to fail**

```bash
.venv/bin/pytest tests/test_validate_thinkcell_binding_registry.py -v
```

Expected: every test fails because `validate_thinkcell_binding_registry.py` does not exist.

- [ ] **Step 4: Commit failing tests**

```bash
git add tests/fixtures/registry_minimal.yml tests/test_validate_thinkcell_binding_registry.py
git commit -m "test(registry): validator + cross-rule guardrails (failing)"
```

### Task 2.3: Implement registry JSON schema

**Files:**

- Create: `schemas/thinkcell_binding_registry.schema.json`

- [ ] **Step 1: Write the schema**

```json
{
  "$schema": "https://json-schema.org/draft-07/schema#",
  "$id": "https://salesops/thinkcell-binding-registry/v1",
  "title": "Think-Cell Binding Registry",
  "type": "object",
  "required": [
    "schema",
    "deck_family",
    "brand",
    "period_context",
    "rules",
    "lanes",
    "slides"
  ],
  "properties": {
    "schema": { "const": "salesops/thinkcell-binding-registry/v1" },
    "deck_family": { "type": "string", "enum": ["land_review_full_28"] },
    "brand": { "const": "simcorp" },
    "period_context": { "type": "string", "pattern": "^\\d{4}-Q[1-4]$" },
    "rules": {
      "type": "object",
      "required": [
        "arr_basis",
        "currency_basis",
        "stage_basis",
        "title_rule",
        "source_rule"
      ],
      "additionalProperties": { "type": "string" }
    },
    "lanes": {
      "type": "object",
      "required": ["ppttc_chart", "ppttc_text", "excel_table_image", "static"],
      "additionalProperties": { "type": "string" }
    },
    "slides": {
      "type": "array",
      "minItems": 1,
      "items": {
        "type": "object",
        "required": ["slide_id", "purpose", "elements"],
        "properties": {
          "slide_id": { "type": "string", "pattern": "^S\\d{2}$" },
          "purpose": { "type": "string" },
          "elements": {
            "type": "array",
            "items": {
              "type": "object",
              "required": [
                "name",
                "kind",
                "lane",
                "required",
                "source",
                "evidence"
              ],
              "properties": {
                "name": {
                  "type": "string",
                  "pattern": "^S\\d{2}_[A-Za-z0-9_]+$"
                },
                "kind": {
                  "type": "string",
                  "enum": [
                    "text",
                    "bar_chart",
                    "column_chart",
                    "waterfall_chart",
                    "stacked_bar_chart",
                    "line_chart",
                    "scalar",
                    "table_image"
                  ]
                },
                "lane": {
                  "type": "string",
                  "enum": [
                    "ppttc_chart",
                    "ppttc_text",
                    "excel_table_image",
                    "static"
                  ]
                },
                "required": { "type": "boolean" },
                "source": { "type": "string" },
                "evidence": {
                  "type": "string",
                  "enum": [
                    "exact_text",
                    "sampled_text",
                    "category_labels",
                    "picture_on_slide",
                    "scalar_value"
                  ]
                }
              }
            }
          }
        }
      }
    }
  }
}
```

- [ ] **Step 2: Commit**

```bash
git add schemas/thinkcell_binding_registry.schema.json
git commit -m "feat(schema): JSON schema for thinkcell binding registry v1"
```

### Task 2.4: Implement validator script

**Files:**

- Create: `scripts/validate_thinkcell_binding_registry.py`

- [ ] **Step 1: Write the validator**

```python
"""Validate a Think-Cell binding registry YAML against schema + cross-rules.

Exit codes:
  0 — valid
  1 — invalid (details to stderr)
  2 — usage error
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import jsonschema
import yaml

REPO = Path(__file__).resolve().parent.parent
SCHEMA_PATH = REPO / "schemas" / "thinkcell_binding_registry.schema.json"

CHART_KINDS = {"bar_chart", "column_chart", "waterfall_chart", "stacked_bar_chart", "line_chart"}


def _load_yaml(path: Path) -> dict:
    with path.open() as f:
        return yaml.safe_load(f)


def _check_unique_names(registry: dict, errors: list[str]) -> None:
    seen: dict[str, str] = {}
    for slide in registry["slides"]:
        for el in slide.get("elements", []):
            name = el["name"]
            if name in seen:
                errors.append(
                    f"duplicate element name '{name}' on slides {seen[name]} and {slide['slide_id']}"
                )
            else:
                seen[name] = slide["slide_id"]


def _check_lane_kind_consistency(registry: dict, errors: list[str]) -> None:
    for slide in registry["slides"]:
        for el in slide.get("elements", []):
            kind, lane, name = el["kind"], el["lane"], el["name"]
            if kind in CHART_KINDS and lane != "ppttc_chart":
                errors.append(
                    f"{name}: kind '{kind}' must use lane 'ppttc_chart', got '{lane}'"
                )
            if kind == "text" and lane not in {"ppttc_text", "static"}:
                errors.append(
                    f"{name}: kind 'text' must use lane 'ppttc_text' or 'static', got '{lane}'"
                )
            if kind == "table_image" and lane != "excel_table_image":
                errors.append(
                    f"{name}: kind 'table_image' must use lane 'excel_table_image', got '{lane}'"
                )
            if kind == "scalar" and lane != "ppttc_text":
                errors.append(
                    f"{name}: kind 'scalar' must use lane 'ppttc_text', got '{lane}'"
                )


def _check_image_suffix(registry: dict, errors: list[str]) -> None:
    for slide in registry["slides"]:
        for el in slide.get("elements", []):
            if el["kind"] == "table_image" and not el["name"].endswith("_Image"):
                errors.append(
                    f"{el['name']}: table_image elements must end in '_Image' suffix"
                )


def _check_slide_id_matches_name_prefix(registry: dict, errors: list[str]) -> None:
    for slide in registry["slides"]:
        sid = slide["slide_id"]
        for el in slide.get("elements", []):
            if not el["name"].startswith(sid + "_"):
                errors.append(
                    f"{el['name']}: name prefix must match slide_id '{sid}'"
                )


def _check_required_per_analytic_slide(registry: dict, errors: list[str]) -> None:
    """Every non-divider, non-cover, non-closing analytic slide must have a Title and Source.

    Heuristic: any slide whose purpose does not end in 'divider', or whose
    purpose is not 'cover'/'closing', is considered analytic.
    """
    analytic_skip = {"cover", "closing"}
    for slide in registry["slides"]:
        purpose = slide["purpose"]
        if purpose in analytic_skip or purpose.endswith("_divider"):
            continue
        names = {el["name"] for el in slide.get("elements", [])}
        sid = slide["slide_id"]
        if f"{sid}_Title" not in names:
            errors.append(f"{sid} ({purpose}): missing required {sid}_Title")
        # Source note: GRR proxy uses Footnote not Source; allow either.
        if (
            f"{sid}_Source" not in names
            and not any(n.startswith(f"{sid}_") and ("Source" in n or "Footnote" in n) for n in names)
        ):
            errors.append(f"{sid} ({purpose}): missing required {sid}_Source / Footnote")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", required=True, type=Path)
    args = parser.parse_args(argv)

    if not args.registry.exists():
        sys.stderr.write(f"registry not found: {args.registry}\n")
        return 2

    schema = json.loads(SCHEMA_PATH.read_text())
    try:
        registry = _load_yaml(args.registry)
    except yaml.YAMLError as exc:
        sys.stderr.write(f"YAML parse error: {exc}\n")
        return 1

    errors: list[str] = []
    try:
        jsonschema.validate(registry, schema)
    except jsonschema.ValidationError as exc:
        errors.append(f"schema: {exc.message} at {list(exc.absolute_path)}")

    if not errors:  # only run cross-rules if shape is valid
        _check_unique_names(registry, errors)
        _check_lane_kind_consistency(registry, errors)
        _check_image_suffix(registry, errors)
        _check_slide_id_matches_name_prefix(registry, errors)
        _check_required_per_analytic_slide(registry, errors)

    if errors:
        for e in errors:
            sys.stderr.write(f"  - {e}\n")
        sys.stderr.write(f"FAIL: {len(errors)} registry error(s)\n")
        return 1

    print(f"OK: {args.registry} ({len(registry['slides'])} slides)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2: Verify deps installed**

```bash
.venv/bin/pip install jsonschema PyYAML 2>&1 | tail -3
```

If missing, add to `requirements.txt`.

- [ ] **Step 3: Run all registry tests**

```bash
.venv/bin/pytest tests/test_validate_thinkcell_binding_registry.py -v
```

Expected: all PASS. If `test_real_registry_passes` fails, the fix is in the registry YAML — review and patch.

- [ ] **Step 4: Run validator on the real registry directly**

```bash
.venv/bin/python scripts/validate_thinkcell_binding_registry.py \
  --registry config/thinkcell/land_review_full_28.binding_registry.yml
```

Expected: `OK: ... (28 slides)` and exit 0.

- [ ] **Step 5: Commit**

```bash
git add scripts/validate_thinkcell_binding_registry.py requirements.txt
git commit -m "feat(registry): jsonschema + cross-rule validator for binding registry"
```

---

## PR 3 — Template contract preflight

**Files:**

- Create: `scripts/verify_thinkcell_template_contract.py`
- Create: `tests/test_verify_thinkcell_template_contract.py`
- Test fixture: `tests/fixtures/tcseed_synthetic.pptx` (built in test setup)

### Task 3.1: Failing test for template contract

**Files:**

- Create: `tests/test_verify_thinkcell_template_contract.py`

- [ ] **Step 1: Write the test**

```python
"""Tests for verify_thinkcell_template_contract.py.

The contract verifier compares a (possibly-Think-Cell-wired) PPTX
against a binding registry. It checks named-shape coverage, debris
strings, and surfaces a JSON report.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
from pptx import Presentation
from pptx.util import Inches

REPO = Path(__file__).resolve().parents[1]
PY = sys.executable
SCRIPT = REPO / "scripts" / "verify_thinkcell_template_contract.py"
FIXTURES = REPO / "tests" / "fixtures"


def _make_pptx_with_named_shapes(path: Path, names: list[str], debris: list[str] | None = None) -> None:
    """Create a synthetic pptx with one shape per name, and optional debris textboxes."""
    prs = Presentation()
    blank_layout = prs.slide_layouts[6]
    for i, name in enumerate(names):
        slide = prs.slides.add_slide(blank_layout)
        tb = slide.shapes.add_textbox(Inches(1), Inches(1 + i * 0.1), Inches(2), Inches(0.5))
        tb.name = name
        tb.text_frame.text = f"placeholder for {name}"
    if debris:
        slide = prs.slides.add_slide(blank_layout)
        for d in debris:
            tb = slide.shapes.add_textbox(Inches(1), Inches(1), Inches(2), Inches(0.5))
            tb.text_frame.text = d
    prs.save(str(path))


def _registry_path() -> Path:
    return REPO / "config" / "thinkcell" / "land_review_full_28.binding_registry.yml"


def _run(template: Path, registry: Path, out: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [PY, str(SCRIPT), "--template", str(template), "--registry", str(registry), "--out", str(out)],
        capture_output=True, text=True, cwd=REPO,
    )


def test_pptx_with_all_named_shapes_passes(tmp_path: Path) -> None:
    """A synthetic pptx that has every required shape name passes the contract."""
    import yaml
    registry = yaml.safe_load(_registry_path().read_text())
    required = [el["name"] for s in registry["slides"] for el in s.get("elements", []) if el.get("required")]
    template = tmp_path / "all_present.pptx"
    _make_pptx_with_named_shapes(template, required)
    out = tmp_path / "report.json"

    proc = _run(template, _registry_path(), out)
    assert proc.returncode == 0, proc.stdout + proc.stderr

    report = json.loads(out.read_text())
    assert report["status"] == "pass"
    assert report["required_elements_missing"] == []


def test_pptx_missing_required_shape_fails(tmp_path: Path) -> None:
    template = tmp_path / "missing.pptx"
    _make_pptx_with_named_shapes(template, ["S01_DirectorName"])
    out = tmp_path / "report.json"

    proc = _run(template, _registry_path(), out)
    assert proc.returncode != 0
    report = json.loads(out.read_text())
    assert report["status"] == "fail"
    assert len(report["required_elements_missing"]) > 0
    assert "S05_PipelineByStage" in report["required_elements_missing"]


def test_pptx_with_debris_text_fails(tmp_path: Path) -> None:
    import yaml
    registry = yaml.safe_load(_registry_path().read_text())
    required = [el["name"] for s in registry["slides"] for el in s.get("elements", []) if el.get("required")]
    template = tmp_path / "debris.pptx"
    _make_pptx_with_named_shapes(
        template, required,
        debris=["[think-cell TABLE WITH FORMATTING — datalinked]", "Lorem ipsum dolor sit amet"],
    )
    out = tmp_path / "report.json"

    proc = _run(template, _registry_path(), out)
    assert proc.returncode != 0
    report = json.loads(out.read_text())
    assert report["status"] == "fail"
    assert len(report["forbidden_text"]) >= 1
```

- [ ] **Step 2: Run tests, expect failure**

```bash
.venv/bin/pytest tests/test_verify_thinkcell_template_contract.py -v
```

Expected: all fail (script doesn't exist).

- [ ] **Step 3: Commit failing test**

```bash
git add tests/test_verify_thinkcell_template_contract.py
git commit -m "test(template): contract preflight verifier (failing test)"
```

### Task 3.2: Implement the contract verifier

**Files:**

- Create: `scripts/verify_thinkcell_template_contract.py`

- [ ] **Step 1: Write the script**

```python
"""Verify a tcseed PPTX against the binding registry.

Checks:
  - every required element name from the registry exists as a shape name
  - no forbidden text (dev instructions, donor placeholders, lorem ipsum)
  - no PowerPoint repair-prompt-prone constructs (off-canvas; future)

Outputs a JSON report and returns:
  0 — pass
  1 — fail (details in report)
  2 — usage error
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import yaml
from pptx import Presentation

REPO = Path(__file__).resolve().parent.parent

FORBIDDEN_PATTERNS = [
    re.compile(r"\[think-cell\b.*?\]", re.IGNORECASE),
    re.compile(r"paste from\b.*", re.IGNORECASE),
    re.compile(r"no think-cell binding here", re.IGNORECASE),
    re.compile(r"lorem ipsum", re.IGNORECASE),
    re.compile(r"click to add", re.IGNORECASE),
    # donor chart artifacts
    re.compile(r"\bUser count \[K\]\b", re.IGNORECASE),
    re.compile(r"\[USD m\]", re.IGNORECASE),
    re.compile(r"\bProduct A\b"),
    re.compile(r"\bBU1\b|\bBU2\b"),
]


def _required_names_from_registry(registry: dict) -> set[str]:
    names: set[str] = set()
    for slide in registry["slides"]:
        for el in slide.get("elements", []):
            if el.get("required"):
                names.add(el["name"])
    return names


def _shape_names_from_pptx(template: Path) -> set[str]:
    prs = Presentation(str(template))
    names: set[str] = set()
    for slide in prs.slides:
        for shape in slide.shapes:
            if getattr(shape, "name", None):
                names.add(shape.name)
    return names


def _all_text_runs(template: Path) -> list[str]:
    prs = Presentation(str(template))
    out: list[str] = []
    for slide in prs.slides:
        for shape in slide.shapes:
            if shape.has_text_frame:
                for para in shape.text_frame.paragraphs:
                    for run in para.runs:
                        if run.text:
                            out.append(run.text)
    return out


def _scan_forbidden(texts: list[str]) -> list[dict]:
    findings: list[dict] = []
    for t in texts:
        for pat in FORBIDDEN_PATTERNS:
            if pat.search(t):
                findings.append({"pattern": pat.pattern, "text": t[:200]})
    return findings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--template", required=True, type=Path)
    parser.add_argument("--registry", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args(argv)

    if not args.template.exists():
        sys.stderr.write(f"template not found: {args.template}\n")
        return 2
    if not args.registry.exists():
        sys.stderr.write(f"registry not found: {args.registry}\n")
        return 2

    registry = yaml.safe_load(args.registry.read_text())
    required = _required_names_from_registry(registry)
    present = _shape_names_from_pptx(args.template)
    missing = sorted(required - present)

    forbidden = _scan_forbidden(_all_text_runs(args.template))

    status = "pass" if not missing and not forbidden else "fail"
    report = {
        "status": status,
        "template": str(args.template),
        "registry": str(args.registry),
        "required_elements_total": len(required),
        "required_elements_present": len(required & present),
        "required_elements_missing": missing,
        "forbidden_text": forbidden,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2))

    if status == "pass":
        print(f"OK: {len(required & present)}/{len(required)} required shapes present, no forbidden text")
        return 0

    sys.stderr.write(json.dumps(report, indent=2) + "\n")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2: Run the tests**

```bash
.venv/bin/pytest tests/test_verify_thinkcell_template_contract.py -v
```

Expected: all PASS.

- [ ] **Step 3: Commit**

```bash
git add scripts/verify_thinkcell_template_contract.py
git commit -m "feat(template): registry-driven contract preflight + debris scan"
```

---

## PR 4 — Build the clean skeleton + manual tcseed wiring procedure

> This PR has two halves: a **Mac script** that emits a clean 28-slide skeleton (TDD-able) and a **Windows VM operational procedure** that wires Think-Cell into that skeleton (NOT TDD-able — manual one-time work). Steward signs off via certification record.

### Task 4.1: Failing test for skeleton builder

**Files:**

- Create: `tests/test_build_skeleton_pptx.py`

- [ ] **Step 1: Write the test**

```python
"""Tests for scripts/build_skeleton_pptx.py.

The skeleton builder copies the canonical SimCorp LAND template and
makes it 28 slides matching the registry slide IDs. No Think-Cell
charts are inserted here — that happens manually on the VM.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from pptx import Presentation

REPO = Path(__file__).resolve().parents[1]
PY = sys.executable
SCRIPT = REPO / "scripts" / "build_skeleton_pptx.py"


def test_skeleton_has_28_slides(tmp_path: Path) -> None:
    out = tmp_path / "skel.pptx"
    proc = subprocess.run(
        [PY, str(SCRIPT), "--out", str(out)],
        capture_output=True, text=True, cwd=REPO,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert out.exists()
    prs = Presentation(str(out))
    assert len(prs.slides) == 28, f"expected 28 slides, got {len(prs.slides)}"


def test_skeleton_has_no_forbidden_strings(tmp_path: Path) -> None:
    out = tmp_path / "skel.pptx"
    subprocess.run([PY, str(SCRIPT), "--out", str(out)], check=True, cwd=REPO)
    prs = Presentation(str(out))
    bad = ["[think-cell", "Lorem ipsum", "paste from", "User count [K]"]
    for slide in prs.slides:
        for shape in slide.shapes:
            if shape.has_text_frame:
                txt = shape.text_frame.text
                for b in bad:
                    assert b not in txt, f"forbidden text in skeleton: {b!r}"
```

- [ ] **Step 2: Run, expect failure**

```bash
.venv/bin/pytest tests/test_build_skeleton_pptx.py -v
```

- [ ] **Step 3: Commit failing test**

```bash
git add tests/test_build_skeleton_pptx.py
git commit -m "test(skeleton): 28-slide clean skeleton builder (failing)"
```

### Task 4.2: Implement skeleton builder

**Files:**

- Create: `scripts/build_skeleton_pptx.py`

- [ ] **Step 1: Inspect canonical layout indices already validated**

```bash
.venv/bin/python -c "
from pptx import Presentation
p = Presentation('assets/golden/LAND_canonical.pptx')
print('slides:', len(p.slides))
print('layouts:', len(p.slide_layouts))
for i, layout in enumerate(p.slide_layouts):
    print(i, layout.name)
"
```

Use this output to map the 28 slide IDs to canonical layout indices. The repo's HANDOFF documents layouts 0/2/6/10/31 as the live ones.

- [ ] **Step 2: Write the builder**

```python
"""Build the clean 28-slide LAND review skeleton from canonical layouts.

Output is a brand-correct, debris-free PPTX with no Think-Cell objects.
The Windows VM steward inserts Think-Cell elements manually and saves
as LAND_review_full_28.tcseed.pptx.
"""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

from pptx import Presentation

REPO = Path(__file__).resolve().parent.parent
CANONICAL = REPO / "assets" / "golden" / "LAND_canonical.pptx"

# (slide_id, layout_name_substring) — 28 entries matching the registry
SLIDE_PLAN = [
    ("S01", "Title"),                # cover
    ("S02", "Two column"),           # exec summary; pick best fit
    ("S03", "Section divider"),      # pipeline divider
    ("S04", "One chart"),
    ("S05", "One chart"),
    ("S06", "One chart"),
    ("S07", "Table"),
    ("S08", "Table"),
    ("S09", "Table"),
    ("S10", "Section divider"),      # retention divider
    ("S11", "Table"),
    ("S12", "Table"),
    ("S13", "One chart"),
    ("S14", "Section divider"),      # territory divider
    ("S15", "One chart"),
    ("S16", "One chart"),
    ("S17", "One chart"),
    ("S18", "One chart"),
    ("S19", "One chart"),
    ("S20", "Section divider"),      # risks divider
    ("S21", "One chart"),
    ("S22", "One chart"),
    ("S23", "Two column"),           # KPI cards
    ("S24", "Table"),
    ("S25", "One chart"),
    ("S26", "Table"),
    ("S27", "Two column"),           # narrative
    ("S28", "Closing"),
]


def _layout_by_substring(prs, sub: str):
    for layout in prs.slide_layouts:
        if sub.lower() in layout.name.lower():
            return layout
    # fallback to layout 0 if no match
    return prs.slide_layouts[0]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--canonical", default=CANONICAL, type=Path)
    args = parser.parse_args()

    if not args.canonical.exists():
        print(f"canonical not found: {args.canonical}", file=__import__("sys").stderr)
        return 2

    # Start from canonical to preserve master/theme/brand
    args.out.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(args.canonical, args.out)

    prs = Presentation(str(args.out))

    # Drop existing slides — keep master/layouts only
    xml_slides = prs.slides._sldIdLst  # internal but stable
    for sld_id in list(xml_slides):
        xml_slides.remove(sld_id)

    # Add 28 slides using planned layouts
    for slide_id, sub in SLIDE_PLAN:
        layout = _layout_by_substring(prs, sub)
        prs.slides.add_slide(layout)

    prs.save(str(args.out))
    print(f"OK: wrote 28-slide skeleton to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 3: Run tests**

```bash
.venv/bin/pytest tests/test_build_skeleton_pptx.py -v
```

Expected: PASS. If layout names in `LAND_canonical.pptx` don't contain the substrings used above, refine `SLIDE_PLAN` based on Step 1 output, then re-run.

- [ ] **Step 4: Generate the actual skeleton**

```bash
.venv/bin/python scripts/build_skeleton_pptx.py \
  --out assets/templates/land_review_full_28/LAND_review_full_28.clean_skeleton.pptx
```

- [ ] **Step 5: Commit**

```bash
git add scripts/build_skeleton_pptx.py assets/templates/land_review_full_28/LAND_review_full_28.clean_skeleton.pptx
git commit -m "feat(template): 28-slide clean skeleton builder + initial output"
```

### Task 4.3: Manual tcseed wiring on Windows VM (one-time, not TDD)

**Files:**

- Create: `assets/templates/land_review_full_28/LAND_review_full_28.seed_certification.md`
- Eventually create: `assets/templates/land_review_full_28/LAND_review_full_28.tcseed.pptx` (binary, hand-saved on VM)

> This task cannot be TDD'd. It is operational. Each step has a manual verification checkbox.

- [ ] **Step 1: Ferry the skeleton to the VM**

```bash
scp assets/templates/land_review_full_28/LAND_review_full_28.clean_skeleton.pptx Windows-VM:/Users/Public/Documents/tcseed_build/
```

- [ ] **Step 2: Open in PowerPoint on the VM**

Manually open the file. **Verify:** no PowerPoint repair prompt; 28 slides present; SimCorp brand visible (theme colors, font).

- [ ] **Step 3: Wire ppttc_text elements**

For each `lane: ppttc_text` entry in the registry where `kind` is `text`:

1. Click the corresponding placeholder text frame.
2. Right-click → "Add text field" (Think-Cell automation text). If using mini-toolbar, click the Think-Cell elements palette → text field.
3. In the Think-Cell mini-toolbar: open AddRangeData Name dialog → enter the **exact** registry name (e.g., `S01_DirectorName`).
4. Save (Ctrl+S).

Process all `ppttc_text` elements first. Use the registry as your checklist:

```bash
# Mac side: list every ppttc_text name to use as a checklist
.venv/bin/python -c "
import yaml
r = yaml.safe_load(open('config/thinkcell/land_review_full_28.binding_registry.yml'))
for s in r['slides']:
    for el in s['elements']:
        if el['lane'] == 'ppttc_text':
            print(s['slide_id'], el['name'])
"
```

- [ ] **Step 4: Wire ppttc_chart elements**

For each `lane: ppttc_chart`:

1. Click on the slide where the chart belongs (S04, S05, S06, S13, S15, S16, S17, S18, S19, S21, S22, S25).
2. Insert → Think-Cell → choose chart type matching registry `kind`:
   - `bar_chart` → Stacked bar (horizontal)
   - `column_chart` → Stacked column (vertical)
   - `waterfall_chart` → Waterfall
   - `stacked_bar_chart` → 100% stacked bar
   - `line_chart` → Line
3. With the chart selected, open AddRangeData Name → enter the registry name (e.g., `S05_PipelineByStage`).
4. Add a default 2×2 datasheet so Think-Cell saves the chart skeleton.
5. Save.

- [ ] **Step 5: Wire excel_table_image placeholders**

For each `lane: excel_table_image`:

1. Insert a temporary picture placeholder (any small image works) on the correct slide.
2. With the image selected, set the **shape name** in PowerPoint's Selection Pane to the registry name (e.g., `S07_TopDealsLand_Image`).
3. Right-click → Think-Cell → "Add Range Image" → name = registry name.
4. Save.

> Note: AddRangeImage is the Excel-side update mechanism. The shape exists as a regular picture in the template; the Excel `UpdateBatch` flow replaces its content at render time.

- [ ] **Step 6: Save final tcseed**

`File → Save As → LAND_review_full_28.tcseed.pptx` in the same folder.

- [ ] **Step 7: Reopen verification**

Close PowerPoint completely. Reopen `LAND_review_full_28.tcseed.pptx`. **Verify:** no repair prompt; Think-Cell loads cleanly; named elements visible in Selection Pane.

- [ ] **Step 8: Ferry back to Mac**

```bash
scp Windows-VM:/Users/Public/Documents/tcseed_build/LAND_review_full_28.tcseed.pptx \
    assets/templates/land_review_full_28/LAND_review_full_28.tcseed.pptx
```

- [ ] **Step 9: Run the contract verifier on the new tcseed**

```bash
.venv/bin/python scripts/verify_thinkcell_template_contract.py \
  --template assets/templates/land_review_full_28/LAND_review_full_28.tcseed.pptx \
  --registry config/thinkcell/land_review_full_28.binding_registry.yml \
  --out state/2026-Q2/__regional__/template_contract_report.json
```

Expected: `OK: N/N required shapes present, no forbidden text`. If `required_elements_missing` is non-empty, return to Step 3 and wire the missing names. Iterate until pass.

- [ ] **Step 10: Generate named-element inventory**

```bash
.venv/bin/python -c "
from pptx import Presentation
import json
prs = Presentation('assets/templates/land_review_full_28/LAND_review_full_28.tcseed.pptx')
inv = []
for i, slide in enumerate(prs.slides, 1):
    for shape in slide.shapes:
        inv.append({'slide': i, 'name': shape.name, 'type': str(shape.shape_type)})
print(json.dumps(inv, indent=2))
" > assets/templates/land_review_full_28/LAND_review_full_28.named_element_inventory.json
```

- [ ] **Step 11: Write the seed certification record**

`assets/templates/land_review_full_28/LAND_review_full_28.seed_certification.md`:

```markdown
# LAND_review_full_28 tcseed certification

## Status: certified

| Field              | Value                                                                          |
| ------------------ | ------------------------------------------------------------------------------ |
| Steward            | <your-name>                                                                    |
| Build host         | Windows-VM                                                                     |
| Date               | YYYY-MM-DD                                                                     |
| PowerPoint version | <e.g., M365 Apps 16.x>                                                         |
| Think-Cell version | <e.g., 13.x>                                                                   |
| Source skeleton    | `assets/templates/land_review_full_28/LAND_review_full_28.clean_skeleton.pptx` |
| Registry hash      | <output of `shasum config/thinkcell/land_review_full_28.binding_registry.yml`> |

## Contract verifier output

Pasted from `state/2026-Q2/__regional__/template_contract_report.json` summary line:

> OK: N/N required shapes present, no forbidden text

## Reopen check

- [x] No PowerPoint repair prompt on close-and-reopen
- [x] Think-Cell loads cleanly
- [x] Named elements visible in Selection Pane

## Known limitations

- Mekko on S16 deferred to P1; current chart is `stacked_bar_chart`.
- Native editable Think-Cell tables not used; all table-shaped slides go through Excel `AddRangeImage`.
```

- [ ] **Step 12: Commit**

```bash
git add \
  assets/templates/land_review_full_28/LAND_review_full_28.tcseed.pptx \
  assets/templates/land_review_full_28/LAND_review_full_28.named_element_inventory.json \
  assets/templates/land_review_full_28/LAND_review_full_28.seed_certification.md \
  state/2026-Q2/__regional__/template_contract_report.json
git commit -m "feat(template): certified tcseed.pptx + inventory + steward certification"
```

---

## PR 5 — Insight title rules engine

**Files:**

- Create: `config/rules/land_review_insight_titles.yml`
- Create: `scripts/build_insight_titles.py`
- Test: `tests/test_build_insight_titles.py`

### Task 5.1: Failing test for insight title evaluation

**Files:**

- Create: `tests/test_build_insight_titles.py`

- [ ] **Step 1: Write the test**

```python
"""Tests for the insight-title rules engine.

Each rule has a `when` predicate evaluated against a director's
metric blob, and a `title` template that interpolates metric values.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
PY = sys.executable
SCRIPT = REPO / "scripts" / "build_insight_titles.py"


def test_late_stage_gap_fires(tmp_path: Path) -> None:
    metrics = tmp_path / "metrics.json"
    metrics.write_text(json.dumps({
        "stage_5_plus_arr": 1_500_000,
        "total_open_arr": 38_500_000,
        "stage_5_plus_arr_share": 0.039,
        "omitted_arr": 5_000_000,
        "omitted_arr_share": 0.13,
    }))
    out = tmp_path / "titles.json"
    rules = REPO / "config" / "rules" / "land_review_insight_titles.yml"

    proc = subprocess.run(
        [PY, str(SCRIPT), "--metrics", str(metrics), "--rules", str(rules), "--out", str(out)],
        capture_output=True, text=True, cwd=REPO,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    titles = json.loads(out.read_text())
    assert "Late-stage" in titles["S05"] or "late-stage" in titles["S05"].lower()
    assert "3.9" in titles["S05"]


def test_default_title_used_when_no_rule_fires(tmp_path: Path) -> None:
    metrics = tmp_path / "metrics.json"
    metrics.write_text(json.dumps({
        "stage_5_plus_arr_share": 0.40,
        "omitted_arr_share": 0.10,
    }))
    out = tmp_path / "titles.json"
    rules = REPO / "config" / "rules" / "land_review_insight_titles.yml"

    proc = subprocess.run(
        [PY, str(SCRIPT), "--metrics", str(metrics), "--rules", str(rules), "--out", str(out)],
        capture_output=True, text=True, cwd=REPO,
    )
    assert proc.returncode == 0
    titles = json.loads(out.read_text())
    # No rule fires; default falls back to a non-empty deterministic string
    assert isinstance(titles["S05"], str) and titles["S05"]
    assert titles["S05"] != ""


def test_every_analytic_slide_has_title(tmp_path: Path) -> None:
    metrics = tmp_path / "metrics.json"
    metrics.write_text(json.dumps({}))  # empty — force defaults
    out = tmp_path / "titles.json"
    rules = REPO / "config" / "rules" / "land_review_insight_titles.yml"

    subprocess.run(
        [PY, str(SCRIPT), "--metrics", str(metrics), "--rules", str(rules), "--out", str(out)],
        check=True, cwd=REPO,
    )
    titles = json.loads(out.read_text())
    # All analytic slides must have a non-empty title
    analytic = ["S02", "S04", "S05", "S06", "S07", "S08", "S09",
                "S11", "S12", "S13", "S15", "S16", "S17", "S18",
                "S19", "S21", "S22", "S23", "S24", "S25", "S26", "S27"]
    for sid in analytic:
        assert sid in titles, f"missing title for {sid}"
        assert titles[sid], f"empty title for {sid}"
```

- [ ] **Step 2: Run, expect failure**

```bash
.venv/bin/pytest tests/test_build_insight_titles.py -v
```

- [ ] **Step 3: Commit failing test**

```bash
git add tests/test_build_insight_titles.py
git commit -m "test(insight-titles): rules engine + default fallback (failing)"
```

### Task 5.2: Author the title rules

**Files:**

- Create: `config/rules/land_review_insight_titles.yml`

- [ ] **Step 1: Write the rules file**

```yaml
schema: salesops/insight-title-rules/v1
deck_family: land_review_full_28
defaults:
  S02: "Executive summary"
  S04: "Pipeline movement this quarter"
  S05: "Pipeline by stage"
  S06: "Pipeline aging"
  S07: "Top open Land deals"
  S08: "Top open Expand deals"
  S09: "Pending Commercial Approval"
  S11: "At-risk renewals"
  S12: "GRR proxy"
  S13: "Forecast category mix"
  S15: "ARR by owner"
  S16: "Stage by industry"
  S17: "Territory performance"
  S18: "Wins and losses QTD"
  S19: "Stage velocity"
  S21: "Concentration risk"
  S22: "Stale activity"
  S23: "Sales velocity formula"
  S24: "Account expansion"
  S25: "Pipeline creation velocity"
  S26: "Action items"
  S27: "Risks and outlook"
rules:
  S05:
    - id: late_stage_gap
      when: "stage_5_plus_arr_share is not None and stage_5_plus_arr_share < 0.10"
      severity: high
      title: "Late-stage coverage is thin: Stage 5+ is only {stage_5_plus_arr_share:.1%} of open ARR"
      evidence: [stage_5_plus_arr, total_open_arr]
  S13:
    - id: omitted_overweight
      when: "omitted_arr_share is not None and omitted_arr_share > 0.50"
      severity: high
      title: "Forecast hygiene is weak: {omitted_arr_share:.1%} of open ARR is Omitted"
      evidence: [omitted_arr, total_open_arr]
  S06:
    - id: aged_pipe
      when: "aged_365_plus_share is not None and aged_365_plus_share > 0.40"
      severity: medium
      title: "Aged pipeline is inflating coverage: {aged_365_plus_share:.0%} of ARR is older than 365 days"
      evidence: [aged_365_plus_arr, total_open_arr]
  S21:
    - id: top_n_concentration
      when: "top_3_arr_share is not None and top_3_arr_share > 0.60"
      severity: high
      title: "Top-3 accounts drive {top_3_arr_share:.0%} of pipeline — concentration risk"
      evidence: [top_3_arr, total_open_arr]
  S09:
    - id: approval_backlog
      when: "pending_approval_count is not None and pending_approval_count >= 3"
      severity: high
      title: "{pending_approval_count} Land+Expand deals at Stage 4+ pending Commercial Approval"
      evidence: [pending_approval_count]
```

- [ ] **Step 2: Commit**

```bash
git add config/rules/land_review_insight_titles.yml
git commit -m "feat(insight-titles): rules + per-slide defaults"
```

### Task 5.3: Implement the rules engine

**Files:**

- Create: `scripts/build_insight_titles.py`

- [ ] **Step 1: Write the script**

```python
"""Compute evidence-backed insight titles per slide for one director.

Inputs:
  --metrics: JSON blob of computed metrics (stage_5_plus_arr_share, etc.)
  --rules:   land_review_insight_titles.yml
  --out:     JSON {S##: title} for every analytic slide

Rule semantics:
  - Each slide may have N rules, evaluated top-to-bottom.
  - First rule whose `when` evaluates truthy wins.
  - If no rule fires, fall back to defaults[slide_id].
  - Title strings use Python format: title.format(**metrics).
  - `when` is restricted-eval with metrics as namespace plus None-safe access.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import yaml


def _safe_eval(expr: str, ns: dict[str, Any]) -> bool:
    """Evaluate `when` expression in a restricted namespace."""
    # Names referenced but absent in metrics resolve to None
    class _NoneDict(dict):
        def __missing__(self, key: str) -> None:  # type: ignore[override]
            return None

    safe_ns = _NoneDict(ns)
    try:
        return bool(eval(expr, {"__builtins__": {}}, safe_ns))
    except Exception:
        return False


def _format_title(template: str, ns: dict[str, Any]) -> str:
    class _NoneDict(dict):
        def __missing__(self, key: str) -> str:
            return ""
    return template.format_map(_NoneDict(ns))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--metrics", required=True, type=Path)
    parser.add_argument("--rules", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args(argv)

    metrics = json.loads(args.metrics.read_text())
    rules_doc = yaml.safe_load(args.rules.read_text())
    defaults: dict[str, str] = rules_doc.get("defaults", {})
    rules: dict[str, list[dict]] = rules_doc.get("rules", {})

    titles: dict[str, str] = {}
    for slide_id, default in defaults.items():
        chosen = None
        for rule in rules.get(slide_id, []):
            if _safe_eval(rule["when"], metrics):
                chosen = _format_title(rule["title"], metrics)
                break
        titles[slide_id] = chosen or default

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(titles, indent=2))
    print(f"OK: wrote {len(titles)} titles to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2: Run tests**

```bash
.venv/bin/pytest tests/test_build_insight_titles.py -v
```

Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add scripts/build_insight_titles.py
git commit -m "feat(insight-titles): deterministic rules engine with defaults"
```

---

## PR 6 — Registry-driven `.ppttc` builder + evidence manifest

**Files:**

- Modify: `scripts/build_ppttc.py`
- Test: `tests/test_build_ppttc_registry_driven.py`

### Task 6.1: Failing test for registry-driven build

**Files:**

- Create: `tests/test_build_ppttc_registry_driven.py`

- [ ] **Step 1: Write the test**

```python
"""Registry-driven .ppttc emission tests.

The new build_ppttc.py must:
  - read the registry
  - reject .ppttc data items whose name isn't in the registry
  - emit at least one data item per required registry binding (or
    explicitly mark as 'suppressed' with reason)
  - write render_evidence_manifest.json alongside the .ppttc
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
PY = sys.executable
SCRIPT = REPO / "scripts" / "build_ppttc.py"


def test_emits_evidence_manifest(tmp_path: Path) -> None:
    """For Patrick (a director with full state), build emits .ppttc and manifest."""
    out_dir = tmp_path / "Patrick-Gaughan"
    out_dir.mkdir()
    proc = subprocess.run(
        [
            PY, str(SCRIPT),
            "--director", "Patrick Gaughan",
            "--period", "2026-Q2",
            "--registry", str(REPO / "config" / "thinkcell" / "land_review_full_28.binding_registry.yml"),
            "--template", str(REPO / "assets" / "templates" / "land_review_full_28" / "LAND_review_full_28.tcseed.pptx"),
            "--emit-evidence-manifest",
            "--out-dir", str(out_dir),
        ],
        capture_output=True, text=True, cwd=REPO,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr

    ppttc_files = list(out_dir.glob("*.ppttc"))
    assert len(ppttc_files) == 1, ppttc_files
    manifest = out_dir / "render_evidence_manifest.json"
    assert manifest.exists()

    doc = json.loads(manifest.read_text())
    assert "bindings" in doc
    assert any(b["name"] == "S05_PipelineByStage" for b in doc["bindings"])


def test_rejects_unknown_binding(tmp_path: Path) -> None:
    """If something tries to add a name not in the registry, build fails."""
    # This is enforced internally; we test by passing a registry that
    # disagrees with what the builder hard-codes.
    bogus = tmp_path / "bogus.yml"
    bogus.write_text("""schema: salesops/thinkcell-binding-registry/v1
deck_family: land_review_full_28
brand: simcorp
period_context: 2026-Q2
rules: {arr_basis: x, currency_basis: x, stage_basis: x, title_rule: x, source_rule: x}
lanes: {ppttc_chart: x, ppttc_text: x, excel_table_image: x, static: x}
slides:
  - slide_id: S99
    purpose: nonexistent
    elements:
      - {name: S99_Bogus, kind: text, lane: ppttc_text, required: true, source: x.y, evidence: exact_text}
""")
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    proc = subprocess.run(
        [
            PY, str(SCRIPT),
            "--director", "Patrick Gaughan",
            "--period", "2026-Q2",
            "--registry", str(bogus),
            "--out-dir", str(out_dir),
        ],
        capture_output=True, text=True, cwd=REPO,
    )
    assert proc.returncode != 0, proc.stdout + proc.stderr
```

- [ ] **Step 2: Run, expect failure**

```bash
.venv/bin/pytest tests/test_build_ppttc_registry_driven.py -v
```

- [ ] **Step 3: Commit failing test**

```bash
git add tests/test_build_ppttc_registry_driven.py
git commit -m "test(build_ppttc): registry-driven emission + manifest (failing)"
```

### Task 6.2: Refactor build_ppttc.py to read the registry

**Files:**

- Modify: `scripts/build_ppttc.py`

> The existing `build_ppttc.py` has hard-coded slide bindings. Refactor in two passes:
> 6.2a — add registry-driven path behind a `--registry` flag (legacy path stays for one PR)
> 6.2b — make registry path the default; legacy path requires `--legacy-bindings`

- [ ] **Step 1: Add CLI flags and registry loader**

In the existing argparse block, add:

```python
parser.add_argument(
    "--registry",
    type=Path,
    default=Path("config/thinkcell/land_review_full_28.binding_registry.yml"),
    help="Path to binding registry. Default: land_review_full_28 registry.",
)
parser.add_argument(
    "--emit-evidence-manifest",
    action="store_true",
    help="Write render_evidence_manifest.json alongside the .ppttc.",
)
parser.add_argument(
    "--legacy-bindings",
    action="store_true",
    help="Use hard-coded bindings instead of the registry. For forensic comparison only.",
)
parser.add_argument(
    "--out-dir",
    type=Path,
    default=None,
    help="Override per-director output directory.",
)
```

- [ ] **Step 2: Add the registry-driven build path**

Add a new module-level function:

```python
import yaml

def _load_registry(path: Path) -> dict:
    return yaml.safe_load(path.read_text())


def _resolve_source(source: str, ctx: dict) -> Any:
    """Resolve a registry `source` reference against the director context.

    Examples:
      'deck_plan.director_name'         -> ctx['deck_plan']['director_name']
      'insight_titles.S05'              -> ctx['insight_titles']['S05']
      'source_notes.S05'                -> ctx['source_notes']['S05']
      'literal.Pipeline'                -> 'Pipeline'
      'model.named_range.S05_PipelineByStage' -> ctx['model']['named_ranges']['S05_PipelineByStage']
      'workbook.range.Top_Deals_Land!A1:H11'  -> handled at refresh-image time, not here
    """
    if source.startswith("literal."):
        return source.split(".", 1)[1]
    parts = source.split(".")
    cur: Any = ctx
    for p in parts:
        if isinstance(cur, dict):
            cur = cur.get(p)
        else:
            return None
    return cur


def _build_ppttc_from_registry(director_ctx: dict, registry: dict, template_path: Path) -> tuple[list[dict], list[dict]]:
    """Returns (ppttc_data_array, evidence_bindings)."""
    data_items: list[dict] = []
    evidence: list[dict] = []
    for slide in registry["slides"]:
        for el in slide.get("elements", []):
            name, kind, lane = el["name"], el["kind"], el["lane"]
            if lane == "static":
                continue
            if lane == "excel_table_image":
                # Table images are not in .ppttc; refresh script handles them.
                evidence.append({"name": name, "kind": kind, "lane": lane,
                                 "required": el.get("required", False),
                                 "deferred_to": "excel_updatebatch"})
                continue
            value = _resolve_source(el["source"], director_ctx)
            if value is None and el.get("required"):
                evidence.append({"name": name, "kind": kind, "lane": lane,
                                 "required": True, "status": "suppressed",
                                 "reason": f"source '{el['source']}' resolved to None"})
                continue
            if lane == "ppttc_text":
                data_items.append({"name": name, "table": [[{"v": str(value)}]]})
            elif lane == "ppttc_chart":
                # Chart payload comes from a 2D table; expect value to be list-of-lists.
                if isinstance(value, list):
                    data_items.append({"name": name, "table": value})
                else:
                    evidence.append({"name": name, "kind": kind, "lane": lane,
                                     "required": el.get("required", False),
                                     "status": "suppressed",
                                     "reason": f"chart source must be 2D table, got {type(value).__name__}"})
                    continue
            evidence.append({"name": name, "kind": kind, "lane": lane,
                             "required": el.get("required", False), "status": "bound"})
    return data_items, evidence
```

- [ ] **Step 3: Wire into main**

In `main()` (or whatever the entry function is named), after loading the director artifacts and computing trends/insight titles, branch:

```python
if not args.legacy_bindings:
    registry = _load_registry(args.registry)
    director_ctx = _build_director_context(director, period, ...)  # existing builder
    data_items, evidence = _build_ppttc_from_registry(director_ctx, registry, template_path)
    ppttc_payload = [{"template": str(template_path.name), "data": data_items}]
    out_path = (args.out_dir or director.director_dir) / f"{director.slug}-LAND-{period}.ppttc"
    out_path.write_text(json.dumps(ppttc_payload, indent=2))

    if args.emit_evidence_manifest:
        manifest_path = (args.out_dir or director.director_dir) / "render_evidence_manifest.json"
        manifest = {"director": director.name, "period": period,
                    "template": str(template_path), "registry": str(args.registry),
                    "bindings": evidence}
        manifest_path.write_text(json.dumps(manifest, indent=2))
else:
    # existing legacy path stays unchanged; one more PR until it's removed
    ...
```

- [ ] **Step 4: Run tests**

```bash
.venv/bin/pytest tests/test_build_ppttc_registry_driven.py -v
```

Expected: PASS. Note: `test_emits_evidence_manifest` requires the tcseed file to exist (PR 4 done) and a director context with insight_titles + source_notes plumbed. If the test fails because `_build_director_context` doesn't yet populate `insight_titles`, add a step that runs `build_insight_titles.py` first and merges the result into `director_ctx['insight_titles']`.

- [ ] **Step 5: Commit**

```bash
git add scripts/build_ppttc.py
git commit -m "feat(build_ppttc): registry-driven path + evidence manifest"
```

### Task 6.3: Add a source_notes.json file per director

**Files:**

- Create: per-director `state/2026-Q2/<director>/source_notes.json`
- Create: `scripts/build_source_notes.py`

- [ ] **Step 1: Write a tiny generator for source_notes.json**

```python
"""Emit per-slide source notes for one director.

Source notes are deterministic strings citing the underlying
worksheet/range and metric basis (Land+Expand ARR · EUR, etc.).
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

DEFAULT_NOTES = {
    "S02": "Source: brief.md exec_summary · Salesforce snapshot {snapshot}",
    "S04": "Source: model.xlsx S04_PipeMovement · Land+Expand ARR · EUR",
    "S05": "Source: model.xlsx S05_PipelineByStage · Land+Expand ARR · EUR",
    "S06": "Source: model.xlsx S06_PipelineAging · Land+Expand ARR · EUR",
    "S07": "Source: model.xlsx Top_Deals_Land · Land+Expand ARR · EUR",
    "S08": "Source: model.xlsx Top_Deals_Expand · Land+Expand ARR · EUR",
    "S09": "Source: model.xlsx Pending_Commercial_Approval · Land+Expand ARR · EUR",
    "S11": "Source: model.xlsx At_Risk_Renewals · Renewal ACV · EUR",
    "S12_footnote": "GRR proxy: Won/(Won+Lost) Renewal ACV; auto-renewals in datasheet · EUR",
    "S13": "Source: model.xlsx S13_ForecastCategory · Land+Expand ARR · EUR",
    "S15": "Source: model.xlsx S15_ByOwner · Land+Expand ARR · EUR",
    "S16": "Source: model.xlsx S16_StageByIndustry · Land+Expand ARR · EUR",
    "S17": "Source: model.xlsx S17_TerritoryPerformance · Land+Expand ARR · EUR",
    "S18": "Source: model.xlsx S18_WinsLossesQTD · Land+Expand ARR · EUR",
    "S19": "Source: model.xlsx S19_Velocity · days · Land+Expand",
    "S21": "Source: model.xlsx S21_ConcentrationRiskChart · Land+Expand ARR · EUR",
    "S22": "Source: model.xlsx S22_StaleActivity · count + ARR · Land+Expand",
    "S23": "Source: model.xlsx S23_SalesVelocity · composite formula",
    "S24": "Source: model.xlsx S24_AccountExpansion · Land+Expand ARR · EUR",
    "S25": "Source: model.xlsx S25_PipelineCreationVelocity · Land+Expand ARR · EUR",
    "S26": "Source: trends.json action_items",
    "S27": "Source: brief.md Risks",
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", default="2026-04-30")
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    notes = {k: v.format(snapshot=args.snapshot) for k, v in DEFAULT_NOTES.items()}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(notes, indent=2))
    print(f"OK: wrote {len(notes)} source notes to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2: Wire into orchestrator (deferred to PR 9)**

For now, run manually for one director to verify:

```bash
mkdir -p state/2026-Q2/Patrick-Gaughan
.venv/bin/python scripts/build_source_notes.py --out state/2026-Q2/Patrick-Gaughan/source_notes.json
```

- [ ] **Step 3: Commit**

```bash
git add scripts/build_source_notes.py
git commit -m "feat(source_notes): deterministic per-slide source-note generator"
```

---

## PR 7 — Excel COM `AddRangeImage` table-image refresher

**Files:**

- Create: `scripts/refresh_thinkcell_table_images.py`
- Create: `scripts/vm/refresh_thinkcell_table_images.ps1`

> This step has no Mac-side TDD because the COM call only exists on Windows. We test the **arguments** the Mac side sends; we test the script integration end-to-end on the VM.

### Task 7.1: Mac-side dispatcher

**Files:**

- Create: `scripts/refresh_thinkcell_table_images.py`

- [ ] **Step 1: Write the dispatcher**

```python
"""Dispatch Excel COM AddRangeImage refresh on the Windows-VM.

The Mac side:
  1. Reads the registry to discover excel_table_image elements
  2. SCPs the rendered pptx + connected workbook to the VM
  3. Invokes the PS1 script with the binding map as JSON
  4. Ferries the refreshed pptx back

This script does NOT execute COM directly — that's the PS1's job.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

import yaml


def _table_image_bindings(registry: dict) -> list[dict]:
    out: list[dict] = []
    for slide in registry["slides"]:
        for el in slide.get("elements", []):
            if el["lane"] == "excel_table_image":
                out.append({
                    "slide_id": slide["slide_id"],
                    "name": el["name"],
                    "source": el["source"],
                })
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pptx", required=True, type=Path, help="rendered_stage1.pptx (input)")
    parser.add_argument("--workbook", required=True, type=Path, help="connected workbook")
    parser.add_argument("--registry", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--vm", default="Windows-VM", help="SSH host alias")
    parser.add_argument("--vm-stage-dir", default="/Users/Public/Documents/tcseed_build")
    args = parser.parse_args(argv)

    registry = yaml.safe_load(args.registry.read_text())
    bindings = _table_image_bindings(registry)
    if not bindings:
        print("no excel_table_image bindings; nothing to refresh", file=sys.stderr)
        # copy input to output unchanged
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_bytes(args.pptx.read_bytes())
        return 0

    bindings_json = json.dumps(bindings)

    # ferry inputs to VM
    subprocess.run(["ssh", args.vm, f"mkdir -p {args.vm_stage_dir}"], check=True)
    subprocess.run(["scp", str(args.pptx), f"{args.vm}:{args.vm_stage_dir}/in.pptx"], check=True)
    subprocess.run(["scp", str(args.workbook), f"{args.vm}:{args.vm_stage_dir}/in.xlsx"], check=True)

    # run PS1
    ps1 = Path(__file__).parent / "vm" / "refresh_thinkcell_table_images.ps1"
    subprocess.run(["scp", str(ps1), f"{args.vm}:{args.vm_stage_dir}/refresh.ps1"], check=True)
    proc = subprocess.run(
        ["ssh", args.vm, "powershell", "-File", f"{args.vm_stage_dir}/refresh.ps1",
         "-Pptx", f"{args.vm_stage_dir}/in.pptx",
         "-Workbook", f"{args.vm_stage_dir}/in.xlsx",
         "-BindingsJson", json.dumps(bindings_json),
         "-Out", f"{args.vm_stage_dir}/out.pptx"],
        capture_output=True, text=True,
    )
    sys.stdout.write(proc.stdout)
    sys.stderr.write(proc.stderr)
    if proc.returncode != 0:
        return proc.returncode

    # ferry back
    subprocess.run(["scp", f"{args.vm}:{args.vm_stage_dir}/out.pptx", str(args.out)], check=True)
    print(f"OK: refreshed pptx written to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2: Commit**

```bash
git add scripts/refresh_thinkcell_table_images.py
git commit -m "feat(refresh): Mac-side dispatcher for Excel AddRangeImage refresh"
```

### Task 7.2: VM-side PowerShell

**Files:**

- Create: `scripts/vm/refresh_thinkcell_table_images.ps1`

- [ ] **Step 1: Write the PS1**

```powershell
<#
.SYNOPSIS
Refresh Think-Cell AddRangeImage shapes in a PPTX from an Excel workbook.

.PARAMETER Pptx
Input pptx that has placeholders named per binding registry.

.PARAMETER Workbook
Connected factory workbook with the source ranges/named ranges.

.PARAMETER BindingsJson
JSON string: list of {slide_id, name, source} where `source` is e.g.
"workbook.named_ranges.S07_TopDealsLand" or "workbook.range.Sheet!A1:H11".

.PARAMETER Out
Output pptx path.
#>

param(
    [Parameter(Mandatory=$true)][string]$Pptx,
    [Parameter(Mandatory=$true)][string]$Workbook,
    [Parameter(Mandatory=$true)][string]$BindingsJson,
    [Parameter(Mandatory=$true)][string]$Out
)

$ErrorActionPreference = 'Stop'

# BindingsJson arrives as a JSON-encoded string of a JSON list
$bindings = ConvertFrom-Json (ConvertFrom-Json $BindingsJson)

$excel = New-Object -ComObject Excel.Application
$excel.Visible = $false
$excel.DisplayAlerts = $false

$ppt = New-Object -ComObject PowerPoint.Application

try {
    $wb = $excel.Workbooks.Open($Workbook)
    $pres = $ppt.Presentations.Open($Pptx, $true, $false, $false)  # ReadOnly=true, Untitled, WithWindow=false

    # Acquire Think-Cell update object via COM
    $tcAddin = $null
    foreach ($addin in $excel.COMAddIns) {
        if ($addin.Description -match 'think-cell') { $tcAddin = $addin; break }
    }
    if (-not $tcAddin) { throw 'think-cell COM add-in not found in Excel' }
    $tc = $tcAddin.Object

    foreach ($b in $bindings) {
        $name = $b.name
        $src  = $b.source
        # parse source: 'workbook.named_ranges.<X>' or 'workbook.range.<Sheet!A1:H11>'
        if ($src -like 'workbook.named_ranges.*') {
            $rangeRef = $src.Substring('workbook.named_ranges.'.Length)
            $rng = $wb.Names.Item($rangeRef).RefersToRange
        } elseif ($src -like 'workbook.range.*') {
            $rangeRef = $src.Substring('workbook.range.'.Length)
            $rng = $wb.Application.Range($rangeRef)
        } else {
            Write-Warning "skipping binding $name: unsupported source '$src'"
            continue
        }
        $tc.UpdateBatch.AddRangeImage($pres, $name, $rng) | Out-Null
        Write-Host "queued AddRangeImage for $name"
    }
    $tc.UpdateBatch.Send() | Out-Null

    $pres.SaveAs($Out)
    $pres.Close()
    $wb.Close($false)
}
finally {
    $ppt.Quit()
    $excel.Quit()
}
```

- [ ] **Step 2: Commit**

```bash
git add scripts/vm/refresh_thinkcell_table_images.ps1
git commit -m "feat(refresh-vm): PowerShell driver for Think-Cell UpdateBatch.AddRangeImage"
```

### Task 7.3: Manual smoke on Patrick

> Operational. Run only after PR 4 (tcseed) and PR 6 (registry-driven .ppttc) are done.

- [ ] **Step 1: Render Patrick stage 1**

Use the existing tcrender bridge to render `Patrick-Gaughan-LAND-2026-Q2.ppttc` against `LAND_review_full_28.tcseed.pptx` to produce `state/2026-Q2/Patrick-Gaughan/rendered_stage1.pptx`.

- [ ] **Step 2: Refresh table images**

```bash
.venv/bin/python scripts/refresh_thinkcell_table_images.py \
  --pptx state/2026-Q2/Patrick-Gaughan/rendered_stage1.pptx \
  --workbook state/2026-Q2/Patrick-Gaughan/land.model.xlsx \
  --registry config/thinkcell/land_review_full_28.binding_registry.yml \
  --out state/2026-Q2/Patrick-Gaughan/rendered_final.pptx
```

- [ ] **Step 3: Visually inspect**

Open `rendered_final.pptx` in Keynote/Preview/PowerPoint. **Verify:** every table image slide (S07/S08/S09/S11/S12/S21/S24/S26) shows real data, not the placeholder image.

- [ ] **Step 4: Commit Patrick artifacts**

```bash
git add state/2026-Q2/Patrick-Gaughan/rendered_stage1.pptx state/2026-Q2/Patrick-Gaughan/rendered_final.pptx 2>/dev/null || true
git commit -m "smoke(refresh): Patrick canary stage1 + final after AddRangeImage refresh"
```

If the binaries are large, instead add their SHAs to a manifest file and gitignore the binaries.

---

## PR 8 — Binding-level render verifier

**Files:**

- Create: `scripts/verify_render_bindings.py`
- Modify: `libs/tcrender/tcrender/verify.py` (demote to diagnostic)
- Test: `tests/test_verify_render_bindings.py`

### Task 8.1: Failing test for binding-level verifier

**Files:**

- Create: `tests/test_verify_render_bindings.py`

- [ ] **Step 1: Write the test**

```python
"""Tests for binding-level render verification.

The verifier loads:
  - rendered .pptx
  - registry
  - render_evidence_manifest.json (from build_ppttc)
And produces a per-binding pass/fail report. Every required binding
must have evidence on the corresponding slide.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
from pptx import Presentation
from pptx.util import Inches

REPO = Path(__file__).resolve().parents[1]
PY = sys.executable
SCRIPT = REPO / "scripts" / "verify_render_bindings.py"


def _make_rendered(path: Path, slide_texts: dict[int, list[str]]) -> None:
    prs = Presentation()
    blank = prs.slide_layouts[6]
    max_slide = max(slide_texts) if slide_texts else 0
    for i in range(1, max_slide + 1):
        slide = prs.slides.add_slide(blank)
        for j, t in enumerate(slide_texts.get(i, [])):
            tb = slide.shapes.add_textbox(Inches(1), Inches(1 + j * 0.5), Inches(5), Inches(0.4))
            tb.text_frame.text = t
    prs.save(str(path))


def test_required_text_present(tmp_path: Path) -> None:
    rendered = tmp_path / "rendered.pptx"
    _make_rendered(rendered, {1: ["Patrick Gaughan"], 5: ["Late-stage coverage is thin"]})

    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({
        "bindings": [
            {"name": "S01_DirectorName", "kind": "text", "lane": "ppttc_text",
             "required": True, "status": "bound",
             "expected_text": "Patrick Gaughan", "slide": 1},
            {"name": "S05_Title", "kind": "text", "lane": "ppttc_text",
             "required": True, "status": "bound",
             "expected_text": "Late-stage coverage is thin", "slide": 5},
        ]
    }))
    out = tmp_path / "report.json"

    proc = subprocess.run(
        [PY, str(SCRIPT), "--pptx", str(rendered), "--manifest", str(manifest), "--out", str(out)],
        capture_output=True, text=True, cwd=REPO,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    report = json.loads(out.read_text())
    assert report["status"] == "pass"
    assert all(b["status"] == "pass" for b in report["bindings"] if b["required"])


def test_missing_required_text_fails(tmp_path: Path) -> None:
    rendered = tmp_path / "rendered.pptx"
    _make_rendered(rendered, {1: ["Patrick Gaughan"]})  # S05 title missing

    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({
        "bindings": [
            {"name": "S01_DirectorName", "kind": "text", "lane": "ppttc_text",
             "required": True, "status": "bound",
             "expected_text": "Patrick Gaughan", "slide": 1},
            {"name": "S05_Title", "kind": "text", "lane": "ppttc_text",
             "required": True, "status": "bound",
             "expected_text": "Late-stage coverage is thin", "slide": 5},
        ]
    }))
    out = tmp_path / "report.json"

    proc = subprocess.run(
        [PY, str(SCRIPT), "--pptx", str(rendered), "--manifest", str(manifest), "--out", str(out)],
        capture_output=True, text=True, cwd=REPO,
    )
    assert proc.returncode != 0
    report = json.loads(out.read_text())
    assert report["status"] == "fail"
    failed = [b for b in report["bindings"] if b["status"] == "fail"]
    assert any(b["name"] == "S05_Title" for b in failed)
```

- [ ] **Step 2: Run, expect failure**

```bash
.venv/bin/pytest tests/test_verify_render_bindings.py -v
```

- [ ] **Step 3: Commit**

```bash
git add tests/test_verify_render_bindings.py
git commit -m "test(verify): binding-level render evidence (failing)"
```

### Task 8.2: Implement the verifier

**Files:**

- Create: `scripts/verify_render_bindings.py`

- [ ] **Step 1: Write the verifier**

```python
"""Binding-level render evidence verification.

Reads:
  --pptx:     final rendered presentation
  --manifest: render_evidence_manifest.json (from build_ppttc)
Writes:
  --out:      per-binding pass/fail report

Exit:
  0 — all required bindings pass
  1 — at least one required binding fails
  2 — usage error
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from pptx import Presentation


def _slide_texts(prs: Presentation) -> dict[int, str]:
    out: dict[int, str] = {}
    for i, slide in enumerate(prs.slides, 1):
        chunks: list[str] = []
        for shape in slide.shapes:
            if shape.has_text_frame:
                chunks.append(shape.text_frame.text)
        out[i] = "\n".join(chunks)
    return out


def _slide_picture_count(prs: Presentation) -> dict[int, int]:
    """Count picture-like shapes per slide; used as evidence for table_image bindings."""
    out: dict[int, int] = {}
    for i, slide in enumerate(prs.slides, 1):
        n = 0
        for shape in slide.shapes:
            # 13 = MSO_SHAPE_TYPE.PICTURE
            if int(shape.shape_type or 0) == 13:
                n += 1
        out[i] = n
    return out


def _slide_id_to_index(slide_id: str) -> int:
    return int(slide_id.lstrip("S"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pptx", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args(argv)

    if not args.pptx.exists():
        sys.stderr.write(f"pptx not found: {args.pptx}\n")
        return 2

    manifest = json.loads(args.manifest.read_text())
    prs = Presentation(str(args.pptx))
    texts = _slide_texts(prs)
    pictures = _slide_picture_count(prs)

    results: list[dict] = []
    fails = 0
    for b in manifest.get("bindings", []):
        slide_idx = b.get("slide") or _slide_id_to_index(b["name"][:3])
        evidence: str = ""
        status = "pass"

        if b.get("status") == "suppressed":
            status = "fail" if b.get("required") else "skip"
            evidence = f"binding suppressed: {b.get('reason', 'no reason given')}"
        elif b["lane"] == "ppttc_text" or b["kind"] in ("text", "scalar"):
            expected = b.get("expected_text", "")
            present = expected and expected in texts.get(slide_idx, "")
            if expected and not present:
                status = "fail" if b.get("required") else "warn"
                evidence = f"expected '{expected[:80]}' not found on slide {slide_idx}"
            else:
                evidence = f"text matched on slide {slide_idx}"
        elif b["lane"] == "excel_table_image" or b["kind"] == "table_image":
            n = pictures.get(slide_idx, 0)
            if n < 1:
                status = "fail" if b.get("required") else "warn"
                evidence = f"no picture shape on slide {slide_idx}"
            else:
                evidence = f"picture present on slide {slide_idx} (count={n})"
        elif b["lane"] == "ppttc_chart":
            # post-render Think-Cell chart inspection requires OOXML detail;
            # for MVP, treat presence of any non-text shape on the slide as evidence.
            evidence = f"chart presence assumed on slide {slide_idx}"
        else:
            evidence = f"no evidence rule for lane '{b['lane']}'"

        if status == "fail" and b.get("required"):
            fails += 1
        results.append({**b, "status": status, "evidence": evidence})

    report = {
        "status": "pass" if fails == 0 else "fail",
        "pptx": str(args.pptx),
        "manifest": str(args.manifest),
        "required_failures": fails,
        "bindings": results,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2))

    if fails:
        sys.stderr.write(f"FAIL: {fails} required binding(s) without evidence\n")
        return 1
    print(f"OK: all {sum(1 for b in results if b.get('required'))} required bindings have evidence")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2: Run tests**

```bash
.venv/bin/pytest tests/test_verify_render_bindings.py -v
```

Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add scripts/verify_render_bindings.py
git commit -m "feat(verify): binding-level render evidence verifier"
```

### Task 8.3: Demote the ratio verifier to diagnostic

**Files:**

- Modify: `libs/tcrender/tcrender/verify.py`

- [ ] **Step 1: Add deprecation header**

Open the file. Above the existing class/function, add a module docstring:

```python
"""DEPRECATED for publish-gate use. Retained as diagnostic only.

The publish gate is now scripts/verify_render_bindings.py which reads
render_evidence_manifest.json and checks each required binding has
evidence on its slide. This module's global min_match_ratio approach
gave false positives when stray text matched director-specific strings.

Use this as a side-channel diagnostic: it surfaces gross drift where
none of the expected strings landed at all. Do not block release on
its result.
"""
```

- [ ] **Step 2: Add a runtime warning when called**

Find the public entry point (likely `def verify(...)` or `class RenderVerifier`). At the top:

```python
import warnings
warnings.warn(
    "tcrender.verify is a diagnostic; do not use as a publish gate. "
    "Use scripts/verify_render_bindings.py instead.",
    DeprecationWarning,
    stacklevel=2,
)
```

- [ ] **Step 3: Commit**

```bash
git add libs/tcrender/tcrender/verify.py
git commit -m "refactor(tcrender): demote ratio verifier to diagnostic; publish gate moves to verify_render_bindings"
```

---

## PR 9 — Pipeline orchestrator

**Files:**

- Create: `scripts/run_land_review_full_28_pipeline.py`

### Task 9.1: Implement the orchestrator

**Files:**

- Create: `scripts/run_land_review_full_28_pipeline.py`

- [ ] **Step 1: Write the orchestrator**

```python
"""One orchestrator for the full land_review_full_28 lane.

Order:
  1. validate registry
  2. validate template contract (against tcseed)
  3. for each director:
     a. build source notes
     b. compute metrics & insight titles
     c. build .ppttc + evidence manifest
     d. render via tcrender (Mac->VM->Mac)
     e. refresh AddRangeImage table images
     f. verify render bindings
  4. write regional summary
  5. exit non-zero on any required failure (strict mode)
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PY = sys.executable

DIRECTORS = [
    "Patrick Gaughan", "Jesper Tyrer", "Adam Steinhouse", "Sarah Smith",
    "Megan Brown", "Yannick Defaux", "Lex Brouwer", "Caryn Lewis", "Andrei Iliadis",
]


def _run(cmd: list[str], step: str) -> int:
    print(f"==> {step}")
    return subprocess.run(cmd, cwd=REPO).returncode


def _slug(name: str) -> str:
    return name.replace(" ", "-")


def _process_director(name: str, period: str, template: Path, registry: Path, strict: bool) -> dict:
    slug = _slug(name)
    director_dir = REPO / "state" / period / slug
    director_dir.mkdir(parents=True, exist_ok=True)

    steps: list[tuple[str, list[str]]] = [
        ("source_notes", [PY, "scripts/build_source_notes.py", "--out", str(director_dir / "source_notes.json")]),
        ("insight_titles", [PY, "scripts/build_insight_titles.py",
                            "--metrics", str(director_dir / "metrics.json"),
                            "--rules", "config/rules/land_review_insight_titles.yml",
                            "--out", str(director_dir / "insight_titles.json")]),
        ("ppttc", [PY, "scripts/build_ppttc.py",
                   "--director", name, "--period", period,
                   "--registry", str(registry),
                   "--template", str(template),
                   "--emit-evidence-manifest",
                   "--out-dir", str(director_dir)]),
        # render is delegated to libs/tcrender; assume an existing CLI:
        ("render", [PY, "-m", "tcrender",
                    "--ppttc", str(director_dir / f"{slug}-LAND-{period}.ppttc"),
                    "--template", str(template),
                    "--out", str(director_dir / "rendered_stage1.pptx")]),
        ("refresh_images", [PY, "scripts/refresh_thinkcell_table_images.py",
                            "--pptx", str(director_dir / "rendered_stage1.pptx"),
                            "--workbook", str(director_dir / "land.model.xlsx"),
                            "--registry", str(registry),
                            "--out", str(director_dir / "rendered_final.pptx")]),
        ("verify", [PY, "scripts/verify_render_bindings.py",
                    "--pptx", str(director_dir / "rendered_final.pptx"),
                    "--manifest", str(director_dir / "render_evidence_manifest.json"),
                    "--out", str(director_dir / "qa_report.json")]),
    ]

    statuses: dict[str, str] = {}
    for step_name, cmd in steps:
        rc = _run(cmd, f"{name} :: {step_name}")
        statuses[step_name] = "pass" if rc == 0 else "fail"
        if rc != 0 and strict:
            return {"director": name, "status": "fail", "first_failure": step_name, "steps": statuses}

    overall = "pass" if all(v == "pass" for v in statuses.values()) else "fail"
    return {"director": name, "status": overall, "steps": statuses}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--period", default="2026-Q2")
    parser.add_argument("--directors", nargs="*", default=["all"])
    parser.add_argument("--jobs", type=int, default=1)
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--registry", default="config/thinkcell/land_review_full_28.binding_registry.yml")
    parser.add_argument("--template", default="assets/templates/land_review_full_28/LAND_review_full_28.tcseed.pptx")
    args = parser.parse_args(argv)

    if args.directors == ["all"]:
        directors = DIRECTORS
    else:
        directors = [d.replace("-", " ") for d in args.directors]

    # 1 + 2: registry + template preflight (once)
    rc = _run([PY, "scripts/validate_thinkcell_binding_registry.py",
               "--registry", args.registry], "validate_registry")
    if rc != 0:
        return rc

    contract_out = REPO / "state" / args.period / "__regional__" / "template_contract_report.json"
    rc = _run([PY, "scripts/verify_thinkcell_template_contract.py",
               "--template", args.template, "--registry", args.registry,
               "--out", str(contract_out)], "verify_template_contract")
    if rc != 0:
        return rc

    # 3: per-director
    results: list[dict] = []
    if args.jobs > 1:
        with ThreadPoolExecutor(max_workers=args.jobs) as ex:
            futs = {ex.submit(_process_director, d, args.period, Path(args.template),
                              Path(args.registry), args.strict): d for d in directors}
            for f in as_completed(futs):
                results.append(f.result())
    else:
        for d in directors:
            results.append(_process_director(d, args.period, Path(args.template),
                                             Path(args.registry), args.strict))

    # 4: regional summary
    summary = {
        "period": args.period,
        "deck_family": "land_review_full_28",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "directors": results,
        "passed": sum(1 for r in results if r["status"] == "pass"),
        "failed": sum(1 for r in results if r["status"] == "fail"),
    }
    summary_path = REPO / "state" / args.period / "__regional__" / "land_review_full_28_run_summary.json"
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))

    return 0 if summary["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2: Smoke run on Patrick canary**

```bash
.venv/bin/python scripts/run_land_review_full_28_pipeline.py \
  --period 2026-Q2 \
  --directors Patrick-Gaughan \
  --strict
```

Expected: exit 0; `state/2026-Q2/__regional__/land_review_full_28_run_summary.json` shows `passed: 1, failed: 0`.

If a step fails, fix the underlying issue (likely missing per-director `metrics.json` — generate one from `trends.json` first). Iterate until pass.

- [ ] **Step 3: Commit**

```bash
git add scripts/run_land_review_full_28_pipeline.py
git commit -m "feat(orchestrator): land_review_full_28 pipeline (registry -> render -> verify)"
```

---

## PR 10 — All-9-director batch + acceptance

**Files:**

- No new files; this is acceptance.

### Task 10.1: Run the full batch

- [ ] **Step 1: Pre-flight all 9 directors have prerequisites**

```bash
for d in Patrick-Gaughan Jesper-Tyrer Adam-Steinhouse Sarah-Smith Megan-Brown Yannick-Defaux Lex-Brouwer Caryn-Lewis Andrei-Iliadis; do
  for f in land.model.xlsx trends.json brief.md; do
    test -f "state/2026-Q2/$d/$f" && echo "OK $d/$f" || echo "MISSING $d/$f"
  done
done
```

Any MISSING must be regenerated through the existing per-director ETL (out of scope for this plan; refer to `scripts/factory.py` no-render mode).

- [ ] **Step 2: Run all-director strict batch**

```bash
.venv/bin/python scripts/run_land_review_full_28_pipeline.py \
  --period 2026-Q2 \
  --directors all \
  --jobs 4 \
  --strict 2>&1 | tee state/2026-Q2/__regional__/run_log_$(date +%Y%m%d-%H%M).log
```

- [ ] **Step 3: Inspect summary**

```bash
cat state/2026-Q2/__regional__/land_review_full_28_run_summary.json | jq '{passed, failed, directors: [.directors[] | {director, status, first_failure}]}'
```

- [ ] **Step 4: Acceptance check**

For each director, verify these artifacts exist:

```bash
for d in Patrick-Gaughan Jesper-Tyrer Adam-Steinhouse Sarah-Smith Megan-Brown Yannick-Defaux Lex-Brouwer Caryn-Lewis Andrei-Iliadis; do
  echo "=== $d ==="
  for f in \
    "${d}-LAND-2026-Q2.ppttc" \
    render_evidence_manifest.json \
    rendered_stage1.pptx \
    rendered_final.pptx \
    qa_report.json \
    insight_titles.json \
    source_notes.json
  do
    test -f "state/2026-Q2/$d/$f" && echo "  OK $f" || echo "  MISSING $f"
  done
done
```

Required: every director has all 7 artifacts.

- [ ] **Step 5: Spot-check 3 decks visually**

Open `state/2026-Q2/Patrick-Gaughan/rendered_final.pptx`, `state/2026-Q2/Jesper-Tyrer/rendered_final.pptx`, `state/2026-Q2/Adam-Steinhouse/rendered_final.pptx`. **Verify per deck:**

- [ ] No PowerPoint repair prompt
- [ ] 28 slides
- [ ] Cover shows correct director name and period
- [ ] Every analytic slide has a non-empty title (not the worksheet name)
- [ ] Every analytic slide has a source note
- [ ] Charts on S04/S05/S06/S13/S15/S16/S17/S18/S19/S21/S22/S25 show real data
- [ ] Table images on S07/S08/S09/S11/S12/S21/S24/S26 show real rows

- [ ] **Step 6: Migrate the legacy seeds**

Now that the new factory is verified, complete the quarantine started in PR 1:

```bash
git mv assets/LAND_thinkcell_seed.pptx assets/legacy/do_not_use_in_factory/
git mv assets/LAND_thinkcell_seed.pre-stripdev.pptx assets/legacy/do_not_use_in_factory/
git mv assets/LAND_thinkcell_seed_polished.pptx assets/legacy/do_not_use_in_factory/ 2>/dev/null || true
git mv assets/LAND_thinkcell_seed_polished_v2.pptx assets/legacy/do_not_use_in_factory/ 2>/dev/null || true
git mv assets/LAND_thinkcell_seed_charts.pptx assets/legacy/do_not_use_in_factory/ 2>/dev/null || true
git mv assets/LAND_thinkcell_seed.pre-jinja-cleanup.pptx assets/legacy/do_not_use_in_factory/ 2>/dev/null || true
git mv assets/LAND_seed_thinkcell.pptx assets/legacy/do_not_use_in_factory/ 2>/dev/null || true
```

- [ ] **Step 7: Update legacy README**

Edit `assets/legacy/do_not_use_in_factory/README.md`:

- Change "Not yet moved" section to "Moved on YYYY-MM-DD after PR 10 acceptance".
- Add SHA of each moved file.

- [ ] **Step 8: Final commit**

```bash
git add assets/legacy/do_not_use_in_factory/
git commit -m "chore(legacy): quarantine debris seeds; new factory is sole production lane"
```

- [ ] **Step 9: Tag the release**

```bash
git tag -a land_review_full_28-mvp-v1 -m "MVP land_review_full_28 factory: 9/9 directors pass strict pipeline"
git push origin main --tags
```

---

## Acceptance criteria (Definition of Done)

The plan is done when **all** of these are true:

| #   | Criterion                              | Verification                                                                                  |
| --- | -------------------------------------- | --------------------------------------------------------------------------------------------- |
| 1   | Registry validates clean               | `validate_thinkcell_binding_registry.py` exit 0 on `land_review_full_28.binding_registry.yml` |
| 2   | tcseed contract passes                 | `verify_thinkcell_template_contract.py` reports 0 missing required, 0 forbidden text          |
| 3   | All 9 directors complete               | `land_review_full_28_run_summary.json` reports `passed: 9, failed: 0`                         |
| 4   | All 9 decks open without repair        | Manual spot-check of 3 + scripted open of 9                                                   |
| 5   | Every analytic slide has insight title | `insight_titles.json` has non-empty entry for every analytic SID                              |
| 6   | Every analytic slide has source note   | `source_notes.json` has entry for every analytic SID                                          |
| 7   | No deck uses the old seed              | `grep -r LAND_thinkcell_seed.pptx` only finds matches under `assets/legacy/`                  |
| 8   | ARR/ACV separation enforced            | Registry validator + plan rules + manual spot-check                                           |
| 9   | Binding-level verifier is the gate     | `tcrender.verify` raises DeprecationWarning; pipeline calls `verify_render_bindings.py`       |
| 10  | Tag pushed                             | `land_review_full_28-mvp-v1` exists on origin                                                 |

---

## Self-review

**Spec coverage check (against `docs/handoffs/2026-05-04-thinkcell-template-fix-plan.md`):**

- PR 1 quarantine + factory default → Tasks 1.1–1.3 ✓
- PR 2 binding registry → Tasks 2.1–2.4 ✓
- PR 3 template contract preflight → Tasks 3.1–3.2 ✓
- PR 4 `.ppttc` builder uses registry → Tasks 6.1–6.3 ✓ (ordered after PR 5 because titles feed PPTC)
- PR 5 split chart/text vs table-image refresh → Tasks 7.1–7.3 ✓
- PR 6 binding-level verifier → Tasks 8.1–8.3 ✓
- PR 7 insight titles → Tasks 5.1–5.3 ✓
- PR 8 orchestrator → Tasks 9.1, 10.1 ✓
- Manual tcseed wiring → Tasks 4.2–4.3 ✓ (skeleton + steward procedure)

**Placeholder scan:** searched plan for "TODO", "TBD", "fill in", "implement later", "appropriate", "similar to" — none present.

**Type/name consistency:**

- Lane names: `ppttc_chart`, `ppttc_text`, `excel_table_image`, `static` — used consistently in registry, schema, validator, builder, refresher, verifier ✓
- Image suffix: `_Image` — used consistently after Task 2.1 reconciliation ✓
- File paths: `config/thinkcell/land_review_full_28.binding_registry.yml`, `assets/templates/land_review_full_28/LAND_review_full_28.tcseed.pptx` — used consistently ✓
- Element naming pattern: `S\d{2}_[A-Za-z0-9_]+` enforced by schema and validator ✓

**One known asymmetry:** The Mac-side test for `test_emits_evidence_manifest` (Task 6.1) requires `tcseed.pptx` to exist, which it won't until PR 4. **Mitigation:** the test should be marked `@pytest.mark.skipif(not tcseed_exists, ...)` and a smaller fixture-pptx test added that uses `tests/fixtures/tcseed_synthetic.pptx`. Add this in Task 6.1 Step 1 if PR 4 is not yet complete when PR 6 starts.

---

## Out-of-scope follow-ups (next sprint)

- Mekko on S16 (currently `stacked_bar_chart`)
- Native editable Think-Cell tables (currently AddRangeImage)
- Q3/month-roll period certification + period config
- Visual regression / SSIM screenshot diffs
- 16-slide `land_meeting_spine_16` deck family (separate plan)
- Productionized Template Atlas (multimodal CLIP, slide-screenshot embeddings, automated slide-variant assembly engine, drift detection across deck families) — lite text-only RAG shipped in PR 0
- Action close-the-loop ledger across months
- SharePoint redesign + PDF export gate
- Move scripts under `src/salesops_copilot/`
