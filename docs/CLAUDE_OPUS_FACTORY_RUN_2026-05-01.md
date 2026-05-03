# Claude Opus factory run — 2026-05-01

Run owner: Claude Opus, executing `docs/CLAUDE_OPUS_FACTORY_DRIVER_2026-05-01.md`.
No git operations. Hardening tranche only.

## Tranche shipped

Reusable, standalone `.ppttc` validation/lint gate. Pure Python — no
Office, VM bridge, or think-cell dependency. Designed to be called by a
factory runner _before_ the slow VM round-trip.

### Files added

- `scripts/validate_ppttc.py` — module + CLI. Structural rules
  (array/template/data/name/table, cell `null` or `{string|number|date}`,
  no duplicate `name` per template) plus optional manifest-drift checks
  against an expected-name list (warning by default, error in
  `--strict`). Exit codes: 0 ok, 2 errors, 3 warnings-as-errors.
- `tests/test_validate_ppttc.py` — 35 tests covering top-level shape,
  entry shape, cell tags, duplicate-name detection, manifest drift,
  manifest loading variants (JSON array / object / categorized lists /
  newline-delimited), and CLI exit codes / JSON mode.
- `docs/thinkcell-corpus/ppttc-validator.md` — corpus doc covering why
  the gate exists, what it checks, CLI usage, manifest formats, and the
  intentional non-integration into `build_ppttc.py` (calling it from a
  runner keeps the gate reusable and avoids changing emitter behavior
  under the experimental template flag).

### Files modified

- `docs/thinkcell-corpus/manifest.json` — added `ppttc-validator.md` to
  `tracked_docs`, added `ppttc_validator` block, bumped KG counts
  (752→753 nodes, 4097→4099 edges, 597→598 docs).
- `scripts/build_thinkcell_knowledge_graph.py` — registered the new
  corpus doc so Graph-RAG queries surface it.

## Verification run

- `python3 -m py_compile scripts/validate_ppttc.py
scripts/build_thinkcell_knowledge_graph.py` → OK
- `python3 -m json.tool docs/thinkcell-corpus/manifest.json` → OK
- `python3 -m pytest tests/test_validate_ppttc.py
tests/test_thinkcell_insertion_pilot.py -q` → 98 passed
  (35 new + 63 adjacent), 0 failed
- `python3 scripts/build_thinkcell_knowledge_graph.py` →
  `nodes=753 edges=4099 docs=598`
- `python3 scripts/query_thinkcell_knowledge_graph.py
"ppttc validator lint gate"` → new doc returned at top with score
  97.4
- Smoke run against a real `.ppttc` already in `state/`
  (`QTR05_FY26RenewalTimeline_Gantt-stock-donor-2026-Q2.ppttc`) →
  `templates=1 names=1 errors=0 warnings=0 ok=yes`

## Wiring decision (intentional)

Did _not_ auto-call the validator from `scripts/build_ppttc.py`. That
emitter still has the experimental auto-generated-template path gated
behind `--experimental-generated-template`, and a lint-on-emit hook
would silently change behavior under that flag. Recommended pattern is:
factory runner calls `python3 scripts/validate_ppttc.py <ppttc>
--expected-names <wired-template-manifest>` after each emit and fails
the step on non-zero exit. This is documented in
`docs/thinkcell-corpus/ppttc-validator.md`.

## Blockers

None for this tranche. The headless programmatic chart-creation API is
still not callable; that remains the upstream platform block recorded
in `docs/thinkcell-corpus/automation-api-surface.md` and is not in
scope for this run.

## Next best work

1. Author per-template expected-name manifests (one per wired
   template) and check them into `assets/`. Today the validator can
   only run drift checks when the caller supplies a list; baking the
   manifests in turns the existing `template_named_elements()` reader
   into the source of truth for what a wired template promises.
2. Add a thin runner step (e.g. in
   `scripts/run_thinkcell_insertion_pilot.py` plan-only mode, or a
   small `scripts/run_factory_validation.py`) that walks today's
   per-director `.ppttc` outputs, loads the matching template manifest,
   and reports pass/fail per director — gives codex/codex review a
   one-shot answer to "is the monthly factory ready to ship?"
3. Consider extending the validator to also assert the referenced
   `template` path exists on disk and is a readable zip; currently it
   only validates the JSON contract. (Skipped here to keep this tranche
   small and to avoid coupling the gate to filesystem state.)
