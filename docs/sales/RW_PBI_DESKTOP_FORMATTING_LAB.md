# RW Power BI Desktop Formatting Lab

Status as of 2026-05-09: Path A is now partially unblocked. Power BI Desktop is
installed in the Parallels Windows 11 VM, and the Mac can regenerate a
Desktop-oriented lab folder from the live Fabric report definition.

This does not make the Mac a full Power BI Desktop host. Power BI Desktop still
runs only in Windows, and the VM must be signed in before interactive UI work is
usable.

## Installed Surface

- VM: `Windows 11`
- Power BI Desktop: `C:\Program Files\Microsoft Power BI Desktop\bin\PBIDesktop.exe`
- Mac shared folder: `/Users/test/Downloads/rw-pbi-format-lab`
- Windows shared folder: `C:\Mac\Home\Downloads\rw-pbi-format-lab`
- Installer retained in the lab folder: `PBIDesktopSetup_x64.exe`
- Installer SHA-256:
  `1cb55a20a16d8a9f83702938ca816a16c402a845eca700ef64134eb8009935dd`

## Regenerate The Lab

Run from repo root:

```bash
python3 -m scripts.sales.rw_pbi_desktop_lab
```

This writes:

- `/Users/test/Downloads/rw-pbi-format-lab/rpt_vp_ops_scorecard_live_pbip/`
- `/Users/test/Downloads/rw-pbi-format-lab/rpt_vp_ops_scorecard_live_pbip/rpt_vp_ops_scorecard.pbip`
- `/Users/test/Downloads/rw-pbi-format-lab/rw_format_lab_data.csv`
- `/Users/test/Downloads/rw-pbi-format-lab/rw_format_lab_readme.md`

The PBIP wrapper is built from Fabric `getDefinition`. The live report currently
returns only `definition.pbir`, `report.json`, and `.platform`. That is enough to
archive and attempt Desktop opening of the report definition; it is not a PBIX
export and does not contain an imported local semantic model.

Launch Desktop against the PBIP:

```bash
python3 -m scripts.sales.rw_pbi_desktop_lab --launch
```

Equivalent manual Windows path:

```text
C:\Mac\Home\Downloads\rw-pbi-format-lab\rpt_vp_ops_scorecard_live_pbip\rpt_vp_ops_scorecard.pbip
```

## What Was Verified

- Parallels VM is running and accepts `prlctl exec`.
- Power BI Desktop installed silently from the official Microsoft installer.
- `PBIDesktop.exe` exists at the expected Windows path.
- A scheduled interactive task can launch `PBIDesktop.exe`.
- Fabric report metadata is readable from the Mac.
- Fabric `getDefinition` succeeds for `rpt_vp_ops_scorecard`.
- Power BI REST PBIX export is blocked with HTTP 403 for this report/tenant.

The 403 export probe used Power BI REST `Export` for report
`d7362a11-f3dd-4bd1-a69a-68c941c2598b`; the last request id captured was
`7cd9881f-5899-435b-817a-700de204804d`.

## Current Blockers

- The Windows VM was at the lock screen during the PBIP launch test. Desktop can
  be launched into the interactive session, but formatting work needs a signed-in
  Windows desktop.
- Power BI Desktop UI automation through Parallels is unreliable. The app wrapper
  often does not expose clickable windows to macOS accessibility, and Windows
  HTML controls did not respond consistently to synthetic clicks.
- The Desktop path should be treated as a manual formatting/capture lane, not a
  dependable end-to-end automation lane.

## Formatting Target

Use the brainstorm HTML mockups as the visual target:

- `.superpowers/brainstorm/95130-1778258028/content/03-what-changed-combined.html`
- `.superpowers/brainstorm/95130-1778258028/content/04-forecast-tab.html`
- `.superpowers/brainstorm/95130-1778258028/content/05-stage-hygiene-tab.html`

Capture these shapes first:

- RAG card with tint, accent border, title typography, primary number, and
  secondary line.
- Combined count plus ARR card, if Desktop can represent it cleanly as one visual.
- Table conditional formatting for threshold-crossable cells.

RAG tokens from `docs/sales/RW_VISUAL_DESIGN_SPEC.md`:

- At Risk: tint `#fee`, accent `#c33`
- Watch: tint `#fff8e6`, accent `#d80`
- Healthy: tint `#eef9ee`, accent `#393`

## Capture Loop

1. Sign into Windows and open the PBIP in Power BI Desktop.
2. Format one representative visual against the mockup.
3. Save the report or publish the edited report back to Fabric.
4. Pull the renderer-validated visual shape:

```bash
python3 -m scripts.sales.rw_capture_visual --list --page "What Changed"
python3 -m scripts.sales.rw_capture_visual --extract <visual-name> --raw
```

5. Move the captured `singleVisual.objects` shape into
   `scripts/sales/_pbir_shapes.py`.
6. Generalize it in `scripts/sales/_pbir_helpers.py`.
7. Recompose the page and validate before pushing:

```bash
python3 -m scripts.sales.rw_compose_what_changed
python3 -m scripts.sales.rw_compose_forecast
python3 -m scripts.sales.rw_validate --live
```

## Business Guardrail

ARR and ACV never blend. ARR is Land + Expand only. ACV is Renewal only. The one
cross-motion measure is `Total Open Pipeline Value`, and it must stay explicitly
labeled as cross-motion.
