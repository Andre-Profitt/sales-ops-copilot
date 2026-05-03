# think-cell Interactive UI Path Probe

Date: 2026-05-01

This is the desktop-console follow-up to the COM/OleView/Procmon scan. It
answers whether the UI-only think-cell methods can create anything when called
from the logged-in Windows session instead of the non-interactive SSH session.

## Artifacts

- Positive interactive COM UI JSON:
  `state/thinkcell_bridge/interactive_com_ui/20260501-205357/thinkcell_interactive_com_ui.json`
- Positive disposable deck:
  `state/thinkcell_bridge/interactive_com_ui/20260501-205357/interactive-com-ui-probe.pptx`
- Positive screenshot:
  `state/thinkcell_bridge/interactive_com_ui/20260501-205357/after_start_table_insertion_then_click.png`
- Interactive UI inventory JSON:
  `state/thinkcell_bridge/interactive_ui/20260501-204435/thinkcell_interactive_ui_path.json`
- Mouse/ribbon gallery probes:
  `state/thinkcell_bridge/mouse_gallery/20260501-205609/thinkcell_mouse_gallery_path.json`
  `state/thinkcell_bridge/mouse_gallery/20260501-210014/thinkcell_mouse_gallery_path.json`
- Harnesses:
  `scripts/probe_thinkcell_interactive_com_ui.ps1`
  `scripts/run_thinkcell_interactive_com_ui_probe.py`
  `scripts/probe_thinkcell_interactive_ui_path.ps1`
  `scripts/run_thinkcell_interactive_ui_path_probe.py`
  `scripts/probe_thinkcell_mouse_gallery_path.ps1`
  `scripts/run_thinkcell_mouse_gallery_path_probe.py`

## What Worked

`tcPpAddIn.StartTableInsertion()` works from the real VM console session. It
does not create a table by itself, but it puts PowerPoint into think-cell's
"click anywhere on the slide" insertion mode. A scripted mouse click on the
slide canvas then creates a real think-cell table object.

Observed proof:

- Action: `StartTableInsertion()` plus click at screen coordinate `1280,620`.
- Shape count changed from `0` to `7`.
- Saved package contains think-cell OLE parts:
  - `ppt/embeddings/oleObject1.bin`
  - `ppt/embeddings/oleObject2.bin`
- Both OLE blobs are CFB documents with readable `think-cellXML`.
- The created element includes `CSmartGrid`, `CContainerSE`, `CGridline`, and
  `CRectSE` classes.

## What Did Not Work

`tcPpAddIn.ShowChartGallery(100,100,700,500,0)` resolves through `IDispatch`,
but still failed from the interactive scheduled-task path. The error message
was blank, and no chart object was created.

The coordinate-based ribbon probe confirmed that the think-cell tab and
Insert-tab think-cell controls are visible in PowerPoint. It did not create a
chart. The first-run think-cell tutorial overlay and collapsed-ribbon state make
this path brittle; it is not a reliable unattended chart factory lane yet.

## Production Interpretation

This is a useful positive, but not a replacement for the donor/`.ppttc` chart
factory.

Use this result as:

- a possible way to create blank native think-cell table donors in a controlled
  interactive VM session,
- evidence that `StartTableInsertion` is UI-only but callable,
- a future proof target if we can programmatically name or safely patch the
  resulting `CSmartGrid`.

Do not use it yet as:

- a production `.ppttc` named table lane,
- a chart creation lane,
- a replacement for table-image donors.

The blocker is naming/binding. The created `CSmartGrid` OLE payload has no
`m_strName` value, so `.ppttc` and Excel `AddRangeData` cannot target it until
a naming path is proven. Earlier raw `m_strName` work against table-related
streams was not reliable enough to promote.

## Factory Decision

Current stance:

- Native think-cell chart factory: still donor + named element + `.ppttc`.
- Table-shaped outputs: still Excel COM `AddRangeImage` table-image lane for
  production.
- New optional research lane: interactive `StartTableInsertion` donor creation,
  followed by a strict naming/binding proof.

Minimum proof before promotion:

1. Create a blank `CSmartGrid` table by scripted UI.
2. Assign or patch a stable name.
3. Update it through `.ppttc` or Excel `AddRangeData`.
4. Save, reopen in PowerPoint, no repair prompt.
5. Render and confirm table geometry, text, and styling are intact.

## Re-run Commands

```bash
.venv/bin/python scripts/run_thinkcell_interactive_com_ui_probe.py

.venv/bin/python scripts/run_thinkcell_interactive_ui_path_probe.py

.venv/bin/python scripts/run_thinkcell_mouse_gallery_path_probe.py --try-click-elements
```
