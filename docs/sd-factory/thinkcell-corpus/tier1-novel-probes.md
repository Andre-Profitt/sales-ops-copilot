# Tier 1 Novel Probes

Date: 2026-05-01

This file documents five new probes that explore code paths the existing
hidden-surface, COM-registry, OleViewDotNet, Procmon/ETW, and ribbon-UIA
probes did not cover. Each probe tests an _orthogonal_ question — not a
re-run of `IDispatch::GetIDsOfNames` against new candidate strings.

The five probes were prioritized after the 2026-05-01 research swarm
(see `research-swarm-2026-05-01/SYNTHESIS.md`), where multiple
independent agents corroborated `IDispatch::GetTypeInfo` as the single
highest-yield untried path against tcaddin.dll.

## Probe Index

| #   | Probe            | Question it answers                                                                                                                                   | Yield expectation                                      |
| --- | ---------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------ |
| 1   | `typeinfo`       | Does IDispatch expose ITypeInfo, exposing the _complete_ method/property table including hidden DISPIDs?                                              | High — orthogonal to all prior name-resolution work    |
| 2   | `pe_resources`   | Does tcaddin.dll embed PE resources (customUI ribbon XML, dialog templates, RT_RCDATA blobs) that map onAction callbacks to underlying methods?       | High — string scan does not reach resource sections    |
| 3   | `clipboard`      | When a think-cell chart is on the clipboard, what private formats are present and can their bytes be dumped to derive the chart serialization schema? | High — closest path to canonical chart-spec format     |
| 4   | `xladdin_hidden` | Are there novel methods/properties on tcXlAddIn or tcUpdate beyond the documented `CreateUpdate`/`AddRangeData`/`AddRangeImage`/`Send`?               | Medium — Excel surface was less probed than PowerPoint |
| 5   | `arch_siblings`  | Do x86 / x64 / arm64 sibling DLLs of tcaddin.dll exist with different exported surface?                                                               | Low-Medium — current install path is `arm64`-suffixed  |

## Why These Beat "More Candidate Names"

Every prior hidden-surface pass relied on `IDispatch::GetIDsOfNames(name) ?
DISPID : DISP_E_UNKNOWNNAME`. This treats discovery as guess-and-check
against the public name table. The probes below use different code paths:

- **Probe 1** uses `IDispatch::GetTypeInfo(0)`. If the implementer chose
  to expose ITypeInfo, this enumerates the entire dispatch table —
  including DISPIDs that no candidate name list would have reached.
  The 2026-05-01 swarm's differential-builds agent flagged this as the
  single cheapest path to enumerate the hypothesized
  `*Step1` / `*Step2` / `BainToolbox*` undocumented siblings.

- **Probe 2** parses PE resource sections, which the binary string scan
  did not. Office add-ins almost universally embed `customUI.xml` here;
  reading it gives a direct map from every ribbon button onAction
  callback (e.g., `tglbtnWaterfall_onAction`) to the C++ method invoked.

- **Probe 3** dumps the clipboard contents during interactive copy of a
  think-cell chart. Private clipboard formats registered by tcaddin.dll
  are the on-the-wire serialization of the chart object — the closest
  reachable equivalent to "the format think-cell uses internally" and
  qualitatively different from probing IDispatch.

- **Probe 4** mirrors the existing PowerPoint hidden-surface harness
  against the Excel side of the add-in. The PowerPoint side resolved
  19 callable names from 3,200 candidates; the Excel side has only had
  a small documented-method check. Re-running 3,200 candidates against
  `tcXlAddIn` and the `tcUpdate` builder may surface a hidden range
  binder (e.g., `AddRangeChart`, `AddNamedRange`) that the docs do not
  list.

- **Probe 5** is a quick file-system enumeration — the install path
  `Program Files (x86)\think-cell\arm64\` is unusual and worth checking
  for sibling-architecture builds with different surface.

## Probe Files

| Probe          | PowerShell harness                           | Python runner                                   |
| -------------- | -------------------------------------------- | ----------------------------------------------- |
| typeinfo       | `scripts/probe_thinkcell_typeinfo.ps1`       | `scripts/run_thinkcell_typeinfo_probe.py`       |
| pe_resources   | `scripts/probe_thinkcell_pe_resources.ps1`   | `scripts/run_thinkcell_pe_resources_probe.py`   |
| clipboard      | `scripts/probe_thinkcell_clipboard.ps1`      | `scripts/run_thinkcell_clipboard_probe.py`      |
| xladdin_hidden | `scripts/probe_thinkcell_xladdin_hidden.ps1` | `scripts/run_thinkcell_xladdin_hidden_probe.py` |
| arch_siblings  | `scripts/probe_thinkcell_arch_siblings.ps1`  | `scripts/run_thinkcell_arch_siblings_probe.py`  |

Output paths follow the established convention:

```
state/thinkcell_bridge/<probe>/<YYYYMMDD-HHMMSS>/thinkcell_<probe>_probe.json
```

Plus, where applicable, a `dumps/` subdirectory of extracted artifacts
(PE resources for probe 2; raw clipboard format bytes for probe 3).

## Run Order (recommended)

```bash
# All run from the repo root with the existing SSH bridge to Windows-VM.

# 1. Cheap and orthogonal — start here.
.venv/bin/python scripts/run_thinkcell_arch_siblings_probe.py
.venv/bin/python scripts/run_thinkcell_typeinfo_probe.py

# 2. Larger, but reveals dump artifacts.
.venv/bin/python scripts/run_thinkcell_pe_resources_probe.py

# 3. Excel-side scan; same model as the existing PP probe.
.venv/bin/python scripts/run_thinkcell_xladdin_hidden_probe.py

# 4. Interactive — print the runbook and follow it on the VM console.
.venv/bin/python scripts/run_thinkcell_clipboard_probe.py --print-runbook
# Then human-step on the VM:
#   - Copy a think-cell chart in PowerPoint
#   - Run the printed PowerShell command on the VM console
```

## Stop Rules

These probes are read-only by design:

- **typeinfo**: enumerates ITypeInfo via `GetTypeAttr`/`GetFuncDesc`/`GetVarDesc`/`GetNames`.
  Never calls `Invoke`; never mutates state.
- **pe_resources**: opens DLLs with `LOAD_LIBRARY_AS_DATAFILE`, not for
  execution.
- **clipboard**: only reads with `OpenClipboard`/`GetClipboardData`. Does
  not write to the clipboard. Does not mutate any deck.
- **xladdin_hidden**: the `Test-DispatchName` helper resolves names via
  late-bound member access; for unknown names the runtime returns
  `DISP_E_UNKNOWNNAME` and the helper records that as unresolved.
  When a name _does_ resolve, the helper deliberately does not call any
  parameter-bearing method.
- **arch_siblings**: file-system + version-info enumeration only.

If any probe accidentally creates a UI dialog, the harness should be
killed and the failure logged. Production runs of the existing harness
have observed `0x800706BA` (RPC server unavailable) when UI methods
were forced on a non-interactive SSH session — that's the existing
fail-safe; the new probes inherit it.

## Update the Unblock Matrix

After running each probe:

1. If the probe surfaces _new_ callable methods (probes 1, 4):
   - Add them to a "Probed Surface Update" section in `unblock-matrix.md`
   - Re-classify each per the "Direct API status / Factory status / Hard
     blocked" three-axis model
   - Do NOT invoke any newly-found method blindly — gate via a separate
     proof-write that asserts behavior on a transient deck.

2. If the probe surfaces new artifact types (probes 2, 3):
   - Persist the dumps to `state/thinkcell_bridge/<probe>/<timestamp>/dumps/`
     (already gitignored)
   - Index notable artifacts (e.g., the customUI XML) into the knowledge
     graph as `BinaryArtifact` nodes
   - Update `automation-api-surface.md` with citations to the dumps

3. If the probe finds _no_ new surface (probe 5 expected; probes 1-4
   possible):
   - Log the negative result in the Tier 1 verdict table below
   - Strengthens the existing "no hidden API" verdict from a single
     methodology to N orthogonal methodologies

## Tier 1 Verdict Table (initially empty)

| Probe          | Status  | New surface? | Run timestamp | Output JSON |
| -------------- | ------- | ------------ | ------------- | ----------- |
| typeinfo       | not_run | —            | —             | —           |
| pe_resources   | not_run | —            | —             | —           |
| clipboard      | not_run | —            | —             | —           |
| xladdin_hidden | not_run | —            | —             | —           |
| arch_siblings  | not_run | —            | —             | —           |

## Anti-Goals

- Do not run these probes against a production SimCorp deck or workbook.
  The probes acquire fresh `Excel.Application` and `PowerPoint.Application`
  instances and dispose them at the end.
- Do not call any newly-resolved method without a separate proof-write
  that defines expected behavior. A resolved DISPID is _not_ a production
  contract.
- Do not start `tcserver.exe` from these probes. The existing unblock
  matrix gates that decision separately.
- Do not over-index on the public manual: the tcaddin.dll surface is
  measured empirically here, not from documentation.

## See Also

- `research-swarm-2026-05-01/SYNTHESIS.md` — the 8-agent research swarm
  output that prioritized these probes.
- `hidden-surface-probe.md` — prior PowerPoint-side static probe.
- `com-registry-probe.md` — registry / OleView / Procmon evidence.
- `interactive-ui-path-probe.md` — the existing UI-path proof for
  `StartTableInsertion` + canvas click.
- `automation-api-surface.md` — current readable hub for the documented
  automation surface.
- `unblock-matrix.md` — three-axis verdict per lane.
