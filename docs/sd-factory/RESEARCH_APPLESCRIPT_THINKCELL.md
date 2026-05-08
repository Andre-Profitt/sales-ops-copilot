# Research — AppleScript / Apple Events as a path to driving think-cell on macOS

**Date:** 2026-04-29
**Host:** macOS 15 (Darwin 25.1.0), PowerPoint 16.108.2, think-cell 15.0.1000217 (`/Library/Application Support/Microsoft/think-cell/tcaddin.plugin`).
**Question:** can AppleScript drive PowerPoint + think-cell _without_ the System Settings → Privacy & Security → Accessibility / Screen Recording grants — i.e. using only the Apple-Events "Automation" permission model?
**Verdict (TL;DR):** **Not viable.** Apple Events reach PowerPoint without prompts, but the surface they expose cannot create charts, cannot invoke think-cell, and cannot reach ribbon items. Every think-cell entry point either requires Accessibility (System Events GUI scripting) or is Windows-only (`run VB macro`, `CommandBars.ExecuteMso`, COM API). The supported macOS automation path remains the `.ppttc` JSON file already wired in `scripts/build_ppttc.py`.

---

## 1. PowerPoint AppleScript dictionary findings

Source: `/Applications/Microsoft PowerPoint.app/Contents/Resources/PowerPoint.sdef` (287 KB).

What **is** scriptable via Apple Events with no prompts:

- `application`, `presentation`, `slide`, `shape`, `text range` — the standard surface.
- `add in` class with `name`, `loaded`, `registered`, `path` — read-only metadata only. Live probe returned `name=think-cell, loaded=true, registered=true, path=/Library/Application Support/Microsoft/think-cell/tcaddin.plugin/Contents/Resources`.
- `command bar` / `command bar control` / `execute` command from the shared MSO suite.
- `run VB macro` command (defined in the dictionary, fails at runtime — see below).

What **is not** in the dictionary at all:

- `chart`, `chart series`, `chart datasheet`, `OLEObject`, `OLEFormat`, `Embeddings`, `Excel.Range` — no class for embedded Office charts. (`grep` for `chart` returned only autoshape flowchart enums and slide-show options, never a chart object.)
- No `paste special`, `paste link`, `Excel.Workbook`, `Workbooks.Open`. There is no Apple-Events surface for the Excel-→-PowerPoint paste-link workflow that think-cell's datalink relies on.
- No add-in callback / invoke / `CallByName` style mechanism — the `add in` class has no method element, only properties.

Permission state confirmed live: `osascript -e 'tell application "Microsoft PowerPoint" to get version'` returned `16.108.2` immediately on first call, no prompts. PowerPoint is auto-authorized for Apple Events under the standard `com.microsoft.powerpoint` allow-list; nothing to grant.

## 2. think-cell ribbon scripting feasibility

Three candidate routes were probed live; all failed:

**Path A — `run VB macro`.** The dictionary advertises a `run VB macro` command (`code="sPPTrVbM"`). At runtime PowerPoint rejects it with AppleScript error `-1708` "doesn't understand the 'run VB macro' message". This matches the [Microsoft Q&A canonical answer](https://learn.microsoft.com/en-us/answers/questions/4886584/application-commandbars-executemso-equivalent-on-a): _"In Excel/PowerPoint 2016 for the Mac it is not possible to modify command bars or call command bar commands."_ `Application.CommandBars.ExecuteMso` and the wider VBA ribbon-invocation surface are Windows-only on Office 2016+ even where the AppleScript dictionary still references them. Net: there is no way to call `tcAddIn.InsertChartBarBar` (or any think-cell macro) from outside PowerPoint on macOS.

**Path B — command bar control invocation.** Live enumeration of `command bar "Ribbon"` returned exactly **1 control**, with no child enumeration possible — attempting to read its `name`/`control type` raised `Access not allowed (-10003)`. macOS Office does not expose the modern Fluent Ribbon as `command bar control` children, so `idMso` ids and `execute` cannot reach Insert > think-cell entries.

**Path C — `System Events` GUI scripting into the PowerPoint process.** This is the conventional "fake clicks via accessibility tree" route. Live probe `tell application "System Events" to tell process "Microsoft PowerPoint" to get name of menu bar 1` returned `missing value`, which is the documented signal that the **Accessibility** entitlement is _not_ granted to the controlling process (System Events silently no-ops instead of erroring). This is exactly the wall the original question is trying to bypass.

So Path A is dead-on-Mac, Path B has no controls to drive, and Path C is the perm wall the brief is trying to skip. The Apple-Events "Automation" permission model is _granted_ for PowerPoint already and could not buy us a think-cell command surface even with full cooperation.

## 3. Prior-art findings

- [think-cell official manual — JSON automation (`.ppttc`)](https://www.think-cell.com/en/resources/manual/jsondataautomation): `.ppttc` opens cross-platform on macOS via Finder double-click or `open file.ppttc`. Slash-separated paths on macOS, backslash-escaped on Windows. **The `ppttc.exe` and `tcserver.exe` headless command-line wrappers are explicitly Windows-only.** First-time server registration also requires a UAC prompt (Windows). On macOS, you launch a `.ppttc` and PowerPoint does the rest.
- [think-cell official manual — API](https://www.think-cell.com/en/resources/manual/api): the API is COM-based, accessed via `Application.COMAddIns` from VBA/C#. _No AppleScript surface; not exposed on macOS at all._
- [Microsoft Q&A — `CommandBars.ExecuteMso` on Mac](https://learn.microsoft.com/en-us/answers/questions/4886584/application-commandbars-executemso-equivalent-on-a): canonical "no" — direct VBA object-model calls only on Mac; ribbon invocation requires Windows.
- [Microsoft Office VBA — `CommandBars.ExecuteMso` reference](https://learn.microsoft.com/en-us/office/vba/api/office.commandbars.executemso): documents the call shape but does not flag the macOS gap.
- StackOverflow / Mr.Excel / Experts-Exchange threads for `ExecuteMso` Mac: confirm that even widely-used calls (`PrintPreviewAndPrint`, `WindowsArrangeAll`) raise runtime error 5 on Mac. No working think-cell + AppleScript example surfaces in the public corpus.
- GitHub: no `applescript` + `think-cell` repo or gist surfaced. Apple's [Mac Automation Scripting Guide](https://developer.apple.com/library/archive/documentation/LanguagesUtilities/Conceptual/MacAutomationScriptingGuide/HowMacScriptingWorks.html) confirms Apple Events do not expose Office add-in command surfaces.

## 4. Verdict — **NOT viable**

AppleScript over pure Apple Events cannot create think-cell charts, link to Excel ranges, or invoke ribbon commands on macOS. The Apple-Events permission model is already pre-granted for PowerPoint, but the surface it exposes is too narrow to matter. Bypassing the Accessibility / Screen Recording wall via this route is impossible because the destination simply isn't there.

What does work on macOS, in priority order:

1. **`.ppttc` JSON automation** — already wired in `scripts/build_ppttc.py` and `scripts/ppttc_template.py`. Cross-platform, no perm prompts, opens via `open foo.ppttc` (a plain Apple-Events `open` call). The current blocker is the _donor-chart template_ on the PowerPoint side, not the automation transport (per `docs/HANDOFF_THINKCELL_PPTTC_2026-04-30.md`). Fix the template and the headless macOS path closes itself; AppleScript adds nothing.
2. **`python-pptx` direct authoring** — bypasses think-cell entirely; current `vanilla` render path in brand-deck-agent.
3. Last-resort GUI automation — needs Accessibility + Screen Recording, defeats the purpose.

## 5. Prototype

`/Users/test/code/apps/sales-ops-copilot/scripts/wire_one_chart.applescript` — research-only AppleScript that probes Path A / Path B / Path C and logs each failure mode with its exact error code. Run with:

```bash
osascript /Users/test/code/apps/sales-ops-copilot/scripts/wire_one_chart.applescript
```

Captured run on 2026-04-29:

```
PowerPoint reachable via Apple Events, version=16.108.2
Path A FAILED as expected: -1708 — "run VB macro" not understood
Path B: ribbon controls visible = 1 (no child enumeration on macOS)
Path C FAILED — Accessibility not granted (System Events returned missing value)
Production think-cell path on macOS = .ppttc JSON automation (scripts/build_ppttc.py).
```

The prototype does not touch `state/2026-Q2/Jesper-Tyrer/land.model.xlsx` or `assets/LAND_template.pptx` — it is a documented null result, kept in-tree as evidence so a future agent doesn't relitigate this.
