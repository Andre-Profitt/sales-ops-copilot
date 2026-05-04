# Template Atlas — usage

The atlas is a working tool for executors of `docs/plans/2026-05-04-land-review-factory-rebuild.md`. Lite text-only RAG plus a lightweight knowledge graph over canonical SimCorp decks, handoffs, the registry, the slot map, and known-bad seeds.

## Build / refresh

```bash
# corpus (skip live embeddings if you don't have az login)
.venv/bin/python scripts/atlas/build_atlas_corpus.py --skip-embeddings

# corpus with live embeddings (requires az login + apro-openai access)
az login
.venv/bin/python scripts/atlas/build_atlas_corpus.py

# graph
.venv/bin/python scripts/atlas/build_atlas_graph.py
```

Outputs:

- `state/atlas/corpus.jsonl` — gitignored, regenerated on every run
- `state/atlas/manifest.json` — committed, summarizes corpus shape per source/role
- `state/atlas/graph.json` — committed, lossless adjacency list

## Query (precedent retrieval)

Find canonical SimCorp precedent for a slide purpose:

```bash
.venv/bin/python scripts/atlas/atlas_query.py \
  --corpus state/atlas/corpus.jsonl \
  --query "horizontal bar chart pipeline by stage SimCorp" \
  --role canonical_brand_reference \
  --top-k 5 \
  --out /tmp/q.json
jq '.[] | {source, slide, score, snippet: (.text[0:200])}' /tmp/q.json
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

Skip embeddings (vector mode for tests):

```bash
.venv/bin/python scripts/atlas/atlas_query.py \
  --corpus state/atlas/corpus.jsonl \
  --query-vector "1.0,0.0,0.0" \
  --top-k 5 \
  --out /tmp/q.json
```

## Roles

`role` filters narrow retrieval to a corpus slice:

- `canonical_brand_reference` — the SimCorp LAND template (positive example)
- `visual_inspiration` — the SalesOps month-close deck (style benchmark)
- `negative_example` — debris-laden seed and pre-strip backup (do **not** copy)
- `spec` — the two 2026-05-04 handoff plans
- `domain_knowledge` — repo handoffs, factory strategy, sales-process graph
- `graph_seed` — registry + slot map (graph nodes, not retrieval targets)

## Where the atlas plugs into the rebuild plan

- **PR 3 Task 3.2 (template contract verifier):** loads debris patterns from `state/atlas/graph.json` (single source of truth) instead of duplicating regex literals.
- **PR 4 Task 4.3 (manual tcseed wiring on Windows VM):** before placing each named element, the steward queries the atlas with the slide intent + role filter to ground positioning/colors in canonical precedent, then re-queries with `role=negative_example` to avoid known debris signatures for that slide.

## Scope (intentional)

Lite. Text-only embeddings. No multimodal CLIP. No automated slide-variant assembly engine. No drift detection across deck families.

Use as a precedent / debris lookup; do **not** let the atlas pick registry names or override the registry. The registry remains the single source of truth for binding names; the atlas is a working tool that informs human and subagent decisions during execution of the rebuild plan.

The fully productionized version (multimodal CLIP, screenshot embeddings, slide-variant assembly engine) is out of scope for the MVP; it lives in the next-sprint backlog.

## Refreshing after registry / rules changes

When the registry, slot map, insight-title rules, or sources.yml change, rebuild both:

```bash
.venv/bin/python scripts/atlas/build_atlas_corpus.py --skip-embeddings  # or live
.venv/bin/python scripts/atlas/build_atlas_graph.py
```

The graph builder is fast (<5s) and pure-deterministic. Rebuild every time PR 2 Task 2.1 (registry reconciliation) or PR 5 Task 5.2 (insight-title rules) lands.
