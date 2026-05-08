# `.ppttc` validator / lint gate

Reusable structural + manifest-drift gate for the `.ppttc` JSON files the
monthly LAND deck factory emits before they are handed to the Windows VM
bridge. Pure Python, no Office / VM / think-cell dependency.

## Why this exists

think-cell's `ppttc.exe` runtime is permissive by design:

- It loads the template, applies bindings whose `name` matches a named
  element in the deck, **and silently ignores everything else**.
- Duplicate `name` entries inside a single template are not flagged —
  later entries overwrite earlier ones with no diagnostic.
- Malformed JSON only surfaces once the operator clicks through the
  Windows VM bridge ("The template failed to load").

Every one of these has bitten the factory in the last quarter. The
validator catches them before the file leaves the Mac.

## Tool

- Module + CLI: `scripts/validate_ppttc.py`
- Tests: `tests/test_validate_ppttc.py` (35 tests, no Office / VM / think-cell)

## What it checks

Structural (errors):

- top level is a non-empty JSON array of template objects
- each template has a non-empty string `template` and an array `data`
- each data entry has a non-empty string `name` and an array `table`
- each row is an array; each cell is `null` or `{string|number|date: …}`
- a cell carrying multiple known tags or zero known tags is rejected
- duplicate `name` within a single template is rejected (per-template,
  not cross-template — separate templates may share a name)

Manifest drift (warning by default, error in `--strict`):

- emitted names that are not in the supplied expected-name manifest
- expected names that are not emitted by the file

Unknown cell tags (warning, never error) — surfaces forwards-compat
breakage in our own emitter without rejecting otherwise-valid files.

## CLI contract

```bash
python3 scripts/validate_ppttc.py path/to/file.ppttc
python3 scripts/validate_ppttc.py path/to/file.ppttc \
    --expected-names assets/LAND_thinkcell_seed_names.json
python3 scripts/validate_ppttc.py path/to/file.ppttc \
    --expected-names manifest.json --strict
python3 scripts/validate_ppttc.py path/to/file.ppttc --json
```

Exit codes (factory-runner friendly):

| code | meaning                                    |
| ---: | ------------------------------------------ |
|    0 | no errors (warnings may be present)        |
|    2 | structural or strict-mode errors           |
|    3 | warnings only, with `--warnings-as-errors` |

Stdout is always a one-line summary (`ppttc=X templates=N names=M
errors=E warnings=W ok=yes|no`). Per-finding text goes to stderr in
text mode; full JSON goes to stdout in `--json` mode.

## Manifest formats accepted

```json
["S01_DirectorName", "S04_PipeMovement"]
```

```json
{ "expected_names": ["S01_DirectorName"] }
```

```json
{
  "chart_names": ["S04_PipeMovement"],
  "text_names": ["S01_DirectorName"],
  "table_names": ["S07_TopDealsLand"]
}
```

Or a newline-delimited file (`#` comments allowed).

## How the factory should use it

The validator is a standalone gate; integration into older build paths
is opt-in. The recommended pattern is:

1. After `scripts/build_ppttc.py` writes a `.ppttc` for a director,
   call `scripts/validate_ppttc.py <ppttc>` with `--expected-names`
   pointing at the wired template's name manifest.
2. On non-zero exit, fail the factory step before invoking the VM
   bridge — the bridge is slow and a structurally broken file wastes
   that round-trip.
3. In CI / test environments where the wired-template manifest is not
   available, run without `--expected-names`. Structural errors still
   gate the build.

This is intentionally not auto-wired into `build_ppttc.py` itself: that
script is in active use against multiple template paths (the
experimental auto-generated path included), and a lint gate wired into
the emitter would change behavior under the experimental flag. Calling
the validator from a runner / CI step keeps the gate reusable without
touching the emitter contract.

## Programmatic use

```python
from validate_ppttc import validate_ppttc, load_payload, load_expected_names

result = validate_ppttc(
    load_payload(Path("…ppttc")),
    expected_names=load_expected_names(Path("…manifest.json")),
    strict=True,
)
if not result.ok:
    raise SystemExit(2)
```
