# tcrender

Mac-side Python wrapper around think-cell's documented headless render path:
`ppttc.exe <input.ppttc> -o <output.pptx>`.

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
)
print(r.output_size_bytes, r.elapsed_seconds, r.exit_code)
```

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
- Live render is gated behind `TCRENDER_LIVE=1`; verifies the round-trip end
  to end against the same fixture.

## See also

- `libs/tc_com_driver/` — IDispatch-based wrapper for COM-only flows
  (UpdateBatch, PresentationFromTemplate). Distinct from this lib.
- `state/thinkcell_bridge/official_docs_corpus/` — canonical doc extraction.
