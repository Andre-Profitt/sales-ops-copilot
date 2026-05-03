# think-cell Windows Bridge

Purpose: run the supported think-cell `.ppttc` automation path on Windows while keeping the macOS repo as the source of truth.

## Contract

- The `.ppttc` file comes from `scripts/build_ppttc.py`.
- The template must already contain real think-cell elements with AddRangeData names.
  For LAND, use `assets/LAND_thinkcell_seed.pptx`.
- The bridge rewrites only the first JSON `"template"` value, without reparsing the JSON.
- `ppttc.exe` runs on Windows and the generated `.pptx` is copied back to macOS.

This does not create missing think-cell names. Office Web Add-ins / Office.js are not a viable path for think-cell because think-cell exposes its API through Office COM add-ins.

## Local Windows VM

The wrapper assumes the Parallels VM can SSH as `Windows-VM` and can read the Mac home share at `\\Mac\Home`.

```bash
python3 scripts/run_thinkcell_windows_bridge.py \
  --ppttc state/2026-Q2/Jesper-Tyrer/Jesper-Tyrer-LAND-2026-Q2.ppttc \
  --template assets/LAND_thinkcell_seed.pptx \
  --output state/2026-Q2/Jesper-Tyrer/Jesper-Tyrer-LAND-2026-Q2-charts.pptx
```

Add `--expect-text "known value"` for a binding smoke test when the output should contain a deterministic string.

## Windows-Side Script

If working inside VS Code Remote / PowerShell on the VM, call the bridge directly:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\thinkcell_windows_bridge.ps1 `
  -PpttcPath C:\tcw\input.ppttc `
  -TemplatePath C:\tcw\wired-template.pptx `
  -OutputPptx C:\tcw\output.pptx `
  -ExpectText "Competition: Germany"
```

## Proven Probe

On April 30, 2026, the bridge was tested by inserting think-cell's official named sample slide into `LAND_template.pptx`, running `ppttc.exe`, and verifying:

- `Competition: Germany` appears once in the generated PPTX.
- `Competition: Canada` appears once in the generated PPTX.
- The copied template placeholder `<SlideTitle>` is gone from the output.

This proves native think-cell objects copied through PowerPoint COM remain bindable inside the LAND deck.

## Production LAND Builder

Use the wrapper for full deck generation:

```bash
.venv/bin/python scripts/build_land_presentation_decks.py --period 2026-Q2 --skip-seed
```

It builds strict `.ppttc` files, binds `assets/LAND_thinkcell_seed.pptx` on
Windows, merges chart shapes into the branded LAND layout deck via PowerPoint
COM, and validates the final deck package.
