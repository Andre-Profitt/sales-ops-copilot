(*
  wire_one_chart.applescript — DOCUMENTED ATTEMPT (NOT PRODUCTION).

  Purpose
    Demonstrate every AppleScript path that *might* drive a think-cell
    bar-chart insert on macOS without the System Settings → Privacy &
    Security → Accessibility / Screen Recording grants.

  Outcome (verified 2026-04-29 against PowerPoint 16.108.2 + think-cell
  15.0.1000217 on macOS 15)
    Path A (run VB macro, AppleEvents only)         : -1708 not understood
    Path B (CommandBar control invocation)          : ribbon exposes 1
                                                      opaque control; no
                                                      child enumeration,
                                                      no idMso surface
    Path C (System Events GUI scripting)            : returns `missing
                                                      value` until Acces-
                                                      sibility is granted

  Conclusion
    The pure-AppleEvents surface cannot reach the think-cell ribbon. The
    only Apple-Events path that reaches the deck at all is
      a) plain shape/slide manipulation in PowerPoint's native dictionary
         (no chart class, no datasheet class, no add-in invocation), and
      b) launching a `.ppttc` file via `open` (the supported think-cell
         JSON-automation entry point — handled by `scripts/build_ppttc.py`,
         not by AppleScript).

  See docs/RESEARCH_APPLESCRIPT_THINKCELL.md for the full writeup.
*)

on run
    set xlsx to "/Users/test/code/apps/sales-ops-copilot/state/2026-Q2/Jesper-Tyrer/land.model.xlsx"
    set pptx to "/Users/test/code/apps/sales-ops-copilot/assets/LAND_template.pptx"

    -- Step 1: confirm Apple Events reach PowerPoint without prompts.
    tell application "Microsoft PowerPoint"
        activate
        set v to version
    end tell
    log "PowerPoint reachable via Apple Events, version=" & v

    -- Step 2 (Path A): run VB macro. Documented as broken on Mac since
    -- Office 2016. Captured for evidence.
    try
        tell application "Microsoft PowerPoint"
            run VB macro "tcAddIn.InsertChartBarBar"
        end tell
        log "Path A SUCCESS (unexpected — recheck environment)"
    on error errMsg number errNum
        log "Path A FAILED as expected: " & errNum & " — " & errMsg
    end try

    -- Step 3 (Path B): inspect ribbon command bar. Returns one opaque
    -- control with no child enumeration; idMso ribbon ids are not
    -- exposed on macOS Office.
    tell application "Microsoft PowerPoint"
        set ribbonControlCount to count of command bar controls of command bar "Ribbon"
    end tell
    log "Path B: ribbon controls visible = " & ribbonControlCount & " (no child enumeration on macOS)"

    -- Step 4 (Path C): System Events GUI scripting — needs Accessibility.
    -- macOS System Events silently returns `missing value` when Accessibility
    -- is not granted, instead of raising an error. Treat that as failure.
    try
        tell application "System Events"
            tell process "Microsoft PowerPoint"
                set menuName to name of menu bar 1
            end tell
        end tell
        if menuName is missing value then
            log "Path C FAILED — Accessibility not granted (System Events returned missing value)."
        else
            log "Path C SUCCESS — Accessibility granted, menu bar name=" & menuName
        end if
    on error errMsg number errNum
        log "Path C ERROR: " & errNum & " — " & errMsg
    end try

    -- Step 5: the only viable headless think-cell path on macOS is the
    -- .ppttc JSON automation, which is launched as a document open. We
    -- DO NOT actually run it from this script — that pipeline lives in
    -- scripts/build_ppttc.py and is the production path.
    log "Production think-cell path on macOS = .ppttc JSON automation (scripts/build_ppttc.py)."
    log "This file is research-only; no chart was wired."

    return "see Console / log for path-by-path results"
end run
