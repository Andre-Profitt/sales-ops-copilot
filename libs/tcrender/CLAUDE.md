# tcrender

Mac-side Python wrapper around think-cell's documented headless render path:
`ppttc.exe <input.ppttc> -o <output.pptx>`.

## Production status

Production route for the LAND deck factory. The 9-director SD-monthly cadence
runs through this lib end-to-end at ~3 seconds per deck (Mac -> SSH -> VM
`ppttc.exe` -> ferry-back). Pairs with `scripts/build_ppttc.py` (emits the
`.ppttc` input) and `scripts/build_ppttc_demo.py` (canonical sample invocation).

Sibling lib `libs/tc_com_driver` is the COM-dispatch utility surface — use
that one for bespoke `UpdateBatch` / `PresentationFromTemplate` flows and
interactive PowerPoint sessions, not for the bulk-render factory path.

## What this is

A stdlib-only client that drives the documented `ppttc.exe` CLI on a Windows VM
over SSH from a Mac developer host. The .ppttc and its donor .pptx template are
staged to a VM-local tempdir, ppttc.exe runs, and the rendered .pptx is ferried
back to a Mac path. No COM, no PowerPoint UI dependency.

Documented entry point per think-cell's official corpus
(`state/thinkcell_bridge/official_docs_corpus/.../extraction.json`,
question C_presentations_open):

> "command-line: 'ppttc.exe <input.ppttc> -o <output.pptx>' (Windows-only;
> ppttc.exe lives in the 'ppttc' subfolder of the install)."

## Public API

```python
from tcrender import TcRenderClient, SSHTransport

client = TcRenderClient(transport=SSHTransport(host="Windows-VM"))

# Validate the .ppttc shape against the official schema
v = client.validate_ppttc(Path("deck.ppttc"))
assert v.valid, v.errors
print(v.binding_count)  # total {name, table} bindings across all entries

# Render: stage -> ppttc.exe -> ferry-back
r = client.render(
    ppttc_path=Path("deck.ppttc"),
    output_path=Path("rendered.pptx"),
    template_override=Path("template.pptx"),  # optional; rewrites entries[].template
    timeout=240.0,
    prep_jinja=True,    # default; pre-substitute {key} placeholders in donor template
    verify=True,        # default; raise RenderError if rendered output lacks director-specific content
)
print(r.output_size_bytes, r.elapsed_seconds, r.exit_code)
```

## template_prep -- Jinja-style pre-substitution (added 0.2.0)

LAND_template.pptx (and similar director-deck templates) ship with
Jinja-style placeholders like `{director_name}`, `{period}`, `{scope_label}`
baked into slide XML as plain text. ppttc.exe doesn't substitute those (it
only fills think-cell named bindings), so the rendered .pptx still shows
literal `{director_name}` instead of e.g. `Jesper Tyrer`. This module walks
the donor .pptx and rewrites slide XML before ppttc.exe touches the
template.

```python
from tcrender.template_prep import (
    binding_name_to_placeholder,
    extract_scalar_string_bindings,
    scan_placeholders,
    substitute_placeholders,
)

# 1. Discover what placeholders the template contains.
found: dict[str, list[Path]] = scan_placeholders(Path("LAND_template.pptx"))
# -> {"director_name": [PosixPath("ppt/slides/slide1.xml")],
#     "period": [slide1.xml, slide2.xml, slide5.xml, ...],
#     "scope_label": [slide1.xml]}

# 2. Substitute (input file is NEVER mutated; output goes to tempdir if None).
patched = substitute_placeholders(
    Path("LAND_template.pptx"),
    bindings={"director_name": "Jesper Tyrer", "period": "2026-Q2", "scope_label": "APAC"},
    output_path=None,
)

# 3. Helper: project a think-cell binding name onto the placeholder key.
binding_name_to_placeholder("S01_DirectorName")  # -> "director_name"

# 4. Helper: pull all scalar-string bindings from a .ppttc keyed by
#    placeholder name -- this is what TcRenderClient.render(prep_jinja=True)
#    feeds into substitute_placeholders.
extract_scalar_string_bindings(Path("Jesper.ppttc"))
# -> {"director_name": "Jesper Tyrer", "period": "2026-Q2", "scope_label": "APAC", ...}
```

`TcRenderClient.render(prep_jinja=True)` (default) auto-runs steps 4 + 2
when `template_override` is supplied; nothing extra is required at the
caller site.

## verify -- post-render evidence checks (added 0.2.0)

ppttc.exe returns exit-code 0 even when most bindings fail to land. Without
this module the LAND factory silently produces empty decks (verified live
2026-05-02 -- 4 SHIP outputs all `exit 0`, 0 mentions of director name).

```python
from tcrender.verify import VerifyResult, binding_evidence_strings, verify_render

# 1. Pull evidence strings from a .ppttc -- director name, period, scope,
#    top account names, etc. Boring strings ("1 - Prospecting", short
#    tokens, single-word "no") are filtered out so the evidence list
#    actually proves the deck is the right one.
evidence: list[str] = binding_evidence_strings(Path("Jesper.ppttc"))

# 2. Scan the rendered .pptx for those strings.
result: VerifyResult = verify_render(
    output_pptx_path=Path("rendered.pptx"),
    expected_strings=evidence,
    min_match_ratio=0.5,
)
result.passed       # bool
result.found        # tuple[str, ...] -- expected strings that landed
result.missing      # tuple[str, ...] -- expected strings that didn't
result.match_ratio  # float in [0, 1]
```

`TcRenderClient.render(verify=True)` (default) auto-runs both steps and
raises `RenderError` if the rendered .pptx is missing more than
`1 - verify_min_match_ratio` of the auto-derived evidence strings.

## Transport

`Transport` is an abstract interface; the only concrete is `SSHTransport`
(host string, default `"Windows-VM"`). `ppttc.exe` reads paths embedded in the
.ppttc verbatim; UNC paths from the SSH session reliably fail with access
errors, so the transport always stages locally to the VM's `%TEMP%` and
rewrites `template` entries to the staged Windows path before invoking
ppttc.exe.

## Tests

- `tests/test_smoke.py` — Mac-runnable: imports clean, validates the
  Jesper-Tyrer fixture (binding_count = 42).
- `tests/test_template_prep.py` — Mac-runnable: binding-name -> placeholder
  transform; scan + substitute on the LAND template; non-mutation of input;
  scalar extraction off the Jesper .ppttc.
- `tests/test_verify.py` — Mac-runnable: VerifyResult immutability; full /
  partial / zero match ratios on synthetic .pptx; evidence-string filtering
  off the Jesper .ppttc (must include `Jesper Tyrer`/`2026-Q2`/`APAC`,
  exclude stage labels).
- Live render is gated behind `TCRENDER_LIVE=1`; verifies the round-trip end
  to end against the same fixture, and (since 0.2.0) asserts the rendered
  .pptx contains "Jesper Tyrer", "2026-Q2", "APAC" so the prep-jinja path
  is exercised end-to-end.

## See also

- `libs/tc_com_driver/` — IDispatch-based wrapper for COM-only flows
  (UpdateBatch, PresentationFromTemplate). Distinct from this lib.
- `state/thinkcell_bridge/official_docs_corpus/` — canonical doc extraction.
