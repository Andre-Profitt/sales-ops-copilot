# Research Swarm Synthesis — 2026-05-01

Eight independent research agents dispatched in parallel to find think-cell
automation surface beyond the public docs and the user's existing 22-document
corpus. Below is the consolidated synthesis.

## Agent Status

| #   | Agent                           | Status   | Output                              |
| --- | ------------------------------- | -------- | ----------------------------------- |
| 1   | Patent miner                    | complete | `agent-1-patents.md`                |
| 2   | Wayback + community recon       | running  | (pending)                           |
| 3   | Talks + LinkedIn intel          | complete | `agent-3-talks-linkedin.md`         |
| 4   | Adjacent product API survey     | complete | `agent-4-adjacent-products.md`      |
| 5   | think-cell Cloud probe          | complete | `agent-5-cloud-probe.md`            |
| 6   | LLM-decompilation pipeline spec | complete | `agent-6-llm-decompile-pipeline.md` |
| 7   | Differential build analysis     | complete | `agent-7-version-evolution.md`      |
| 8   | Academic RE literature          | complete | `agent-8-academic-literature.md`    |

## Headline Findings (Cross-Cutting)

### 1. The public surface is genuinely small — even smaller than we documented

The actual count of documented COM methods is **~9** on the public API page,
not the ~25 estimate. (Agent 4.) tcXlAddIn exposes `CreateUpdate`,
`PresentationFromTemplate`, `UpdateChart`; `tcUpdate` exposes `AddRangeData`,
`AddRangeImage`, `Send`; tcPpAddIn exposes `LoadStyle`, `LoadStyleForRegion`,
`GetStyleName`, `RemoveStyles`, `ImportMekkoGraphicsCharts`,
`GetMekkoGraphicsXML`, plus `PresentationFromTemplate` / `UpdateBatch`. The
existing hidden-surface probe found 19 PowerPoint-side resolvable names
including step-numbered variants (`PresentationFromTemplateStep3`,
`UpdateBatchStep3`, `GetStyleNameStep2`, etc.); that's the **empirical**
surface, larger than the documented surface.

### 2. think-cell's "minimal API" is category-standard, not exceptional

Of 10 surveyed competitors (Mekko Graphics, Empower, Power-user, EOS,
Aploris, Datylon, Vivid Charts, Slidewise/Bright Slide, Macabacus, etc.), 7
publish **zero** developer API. Only Datylon (REST-based, fundamentally
different product) exposes meaningfully more. Mekko Graphics has comparable
size with **more read-side methods** (`GetChartData`, `IsMekkoChart`,
`GetChartType`) — these are what think-cell _could plausibly_ add but hasn't.
(Agent 4.)

### 3. NEW SURFACE: `tcasr.exe` sidecar process — not in our existing corpus

think-cell's own dev blog post "By Default Different" discloses that
`tcaddin.dll` communicates with a separate sidecar process `tcasr.exe` via
**named mutexes**, **Win32 user messages**, and **shared-memory file
backing**. (Agent 3.) Our existing COM registry probe and Procmon trace did
not call out this process. **This is a new probe target**: enumerate
processes named `tcasr*`, capture the shared-memory contract, observe the
Win32 message protocol. The sidecar may host functionality the in-proc
COM dispatch interface deliberately does not expose.

### 4. Step\* method hypothesis confirmed as COM interface evolution

`*Step1` / `*Step2` / `*Step3` is the textbook COM interface-evolution
pattern parallel to Microsoft's `IFoo`/`IFoo2`/`IFoo3` — each Step is a
non-backward-compatible revision kept callable via separate vtable slots.
(Agent 7.) The existing probe resolved `*Step3` only because that's what
the higher-version installer ships. **`Step1` and `Step2` predecessors
likely still exist as callable methods** with earlier-shape parameter
signatures — `IDispatch::GetTypeInfo` enumeration would reveal them.

### 5. `GetStyleName` was officially "new" in tc14 (Nov 2025) but

`GetStyleNameStep2` was already resolvable. This proves that **method
resolution lags documentation**: methods exist callable years before they're
publicly documented. (Agent 7.) The user's installed 15.0.100.220 is a
**pre-GA pilot of tc15**, so it likely contains tc15-only methods not yet
documented anywhere.

### 6. `.ppttc` and tcserver.exe are dated to specific releases

- `.ppttc` JSON: introduced **tc9 / April 2018**, IANA registration
  `application/vnd.think-cell.ppttc+json` dated 2018-04-16 by
  Arno Schoedl.
- `tcserver.exe`: introduced **tc10 / 2019** alongside macOS support.
- The single endpoint is `POST <bind-url>/` with body
  `application/vnd.think-cell.ppttc+json`, response `.pptx` binary.
- **No built-in auth** — operator deploys behind reverse proxy / mTLS /
  network ACL.
  (Agents 5 + 7.)

### 7. NEW SURFACE: server.think-cell.com (213.61.194.234)

Resolves; `/portal/` returns HTTP 200 with empty body, SSO-gated. This is
think-cell's internal license/admin portal, **not** a SaaS product. May
expose admin endpoints worth a separate probe pass, but requires
authentication. (Agent 5.) `static.think-cell.com` is their CDN.

### 8. NEW SURFACE: browser extension uses native messaging to local add-in

think-cell ships a Chrome/Edge/Firefox extension that scrapes Tableau views
and web images, then communicates with the local desktop add-in via
**native messaging**. (Agent 5.) The native-messaging protocol is
local-only but **undocumented** — reverse-engineering this protocol could
reveal additional commands the desktop add-in accepts that the COM
dispatch interface does not advertise.

### 9. "Send With Gmail.Mailto" mystery solved

It's a Windows MAILTO protocol handler under
`HKLM\SOFTWARE\Clients\Mail\` — **not** an Outlook add-in or cloud
service. Opens Gmail compose in the default browser via OAuth2. **Not an
API**; just implements the Windows MAILTO contract. (Agent 5.) Close out
the open question from `com-registry-probe.md`.

### 10. think-cell's hooking engine is on Apple Silicon Office

Sebastian Theophil's 2024 ARM talk subtitle "(and Hacking)" connects to
the same engineering lineage as Simon McPartlin's 2014 Meeting C++ talk
"Industrial Strength Software Hacking" — which is the public reference
description of how `tcaddin.dll` modifies Office processes. The 2024 talk
ports this to AArch64. (Agent 3.) **This means tcaddin.dll is doing
in-memory function detouring on Office on Apple Silicon and Windows-on-ARM
the user's VM is running the ARM64 build.** The hidden-surface probe's
3,200-name scan found `CFindCodePattern` — that's the pattern-matching
infrastructure for the hook engine.

### 11. Patents are algorithmic, not architectural

~10 US patents/applications, all assigned to Think-Cell Software GmbH.
Cluster into: layout constraint solving, chart label placement,
image-based chart-data extraction, document-structure synchronization.
**No coverage of OOXML custom XML parts, COM dispatch tables, ribbon
callbacks, the JSON automation protocol, or any wire format.** Patents
do not reveal API surface. The closest hint is **US 10,789,414**
(pattern-based canvas filling) which formalizes an Excel→PowerPoint
pattern model — possibly the conceptual ancestor of `.ppttc`. **US
10,776,448** (cell-based reactive computing) is the only sole-Schödl
filing and sketches a reactive-cell-with-external-triggers abstraction
that may be the conceptual ancestor of the JSON Data Automation server.
(Agent 1.)

### 12. Public engineer disclosures: stack signals

- Boost.Spirit (parsing — likely used in the `.ppttc` parser)
- COIN-OR CLP solver (linear programming for layout)
- OpenCV + Leptonica (chart recognition from images — backs the
  image-extraction patents)
- Proprietary persistence library for "whole object trees" (this is
  the `think-cellXML` custom XML part serializer)
- Windows hook engine via assembly-pattern signature scanning
  (Agent 3.)

### 13. Correction: Matthias Hofmann is NOT a think-cell engineer

Earlier corpus content speculated this. Justia hits for that name are
unrelated (mechanical engineering / a patent attorney at Boehmert &
Boehmert). (Agent 1.) Confirmed think-cell engineers: Schödl (CTO),
Hannebauer (CEO), Theophil, Schöch, Ziegler, Lahmann, Nordhus,
Ringenberg, McPartlin, Müller, Fracassi.

## Convergent Recommendations (across multiple agents)

The following techniques received **multi-agent endorsement** as highest-yield:

### Convergent #1 — `IDispatch::GetTypeInfo()` enumeration

- Agent 7 names it as the **"cheapest probe"** for the Step\* hypothesis
- Agent 8's #1 academic-lit-derived recommendation (OOAnalyzer + Ghidra
  RTTI is its #1, but TypeInfo dump is in agent 8's eight concrete probe
  sketches as `IDispatchEx::GetNextDispID`)
- The user-facing tier-1 probe set already includes this as Probe 1
- **Action: run probe 1 first.**

### Convergent #2 — RTTI / vtable harvest from tcaddin.dll

- Agent 8 ranks this as the **highest yield-per-hour technique** the user
  has not tried (OOAnalyzer + Ghidra)
- Agent 6 specs the concrete pipeline: Ghidra 11.x headless +
  `RecoverClassesFromRTTIScript` + astrelsky's
  `Ghidra-Cpp-Class-Analyzer` → `ghidrecomp` → SQLite + sqlite-vec
- $35-60/run on Anthropic Batch API; OSS-only path; 4-8h wall-clock
- **Action: run after tier-1 probes if those don't crack open.**

### Convergent #3 — Frida-Gum DBI hook on `IDispatch::Invoke`

- Agent 8 ranks this #2: proven technique on MSGraph (Check Point
  case study); surfaces DISPIDs that fire under UI actions but never
  appear in `GetIDsOfNames` enumeration
- Different code path from static probing — observes runtime behavior
- **Action: medium-priority follow-up.**

### Convergent #4 — BinDiff / ghidriff between two tcaddin.dll versions

- Agent 8 ranks this #3 — cheapest path to enumerate internal-only API
  additions invisible to string scans
- Agent 7 mentions ManageEngine MSI patches for tc12/tc13 as a way to
  get historical builds
- **Action: medium-priority.**

### Convergent #5 — Probe `tcasr.exe` sidecar

- New finding from Agent 3 — process not in the existing corpus
- Communicates with `tcaddin.dll` via named mutexes, Win32 messages,
  shared-memory file
- **Action: new probe needed (not in tier-1 set yet).**

### Convergent #6 — Reverse the browser-extension native-messaging protocol

- New finding from Agent 5 — Chrome/Edge/Firefox extension talks to
  local desktop add-in
- Native messaging is JSON-over-stdin/stdout; manifest names the
  reachable extension and command set
- **Action: new probe needed (not in tier-1 set yet).**

## Definitively Closed Questions

- **No cloud / SaaS think-cell product exists.** No `app.`/`cloud.`/
  `online.`/`api.`/`web.`/`portal.` subdomain resolves. The desktop
  COM remains the superset surface. (Agent 5.)
- **No mobile product.** No iOS, no Android. (Agent 5.)
- **No Office Web Add-in path.** Hard-blocked by Microsoft's add-in
  model. (Agent 5, confirms existing unblock matrix.)
- **No Word / OneNote / Visio integration.** Only PowerPoint and Excel
  desktop. (Agent 5.)
- **Patents do not reveal API.** ~10 patents, all algorithmic. (Agent 1.)
- **think-cell does not publish a TLB.** Late-bound IDispatch only.
  (Agents 1, 6, 7 confirm existing corpus finding.)

## Open Threads After This Swarm

- **Agent 2 (wayback + community recon) still running.** Will check for
  documented-then-removed methods across 2014–2026 snapshots and
  community-discovered tricks.
- **The Step\* family** has not been enumerated. Probe 1 (typeinfo) is
  the path.
- **`tcasr.exe` sidecar** has not been characterized.
- **Browser-extension native-messaging protocol** has not been
  characterized.
- **server.think-cell.com/portal/** is SSO-gated; out of scope without
  credentials.

## Recommended Next Action

Per the corpus's existing operating discipline (state, then probe, then
update unblock matrix):

1. Run **Probe 1 (typeinfo)** now — multi-agent convergent recommendation,
   lowest effort.
2. If probe 1 surfaces the Step\* family, document each new method and
   gate via separate proof-writes before invoking.
3. Run **Probe 2 (pe_resources)** for the customUI ribbon XML.
4. Decide on **Frida DBI** vs. **OOAnalyzer RTTI harvest** for the
   medium-effort lane based on probe 1+2 outcome.
5. Add `tcasr.exe sidecar probe` and `browser-extension native-messaging
probe` as new tier-2 entries in the workplan.

## Citations

Per-agent reports in this directory:

- [agent-1-patents.md](agent-1-patents.md)
- [agent-3-talks-linkedin.md](agent-3-talks-linkedin.md)
- [agent-4-adjacent-products.md](agent-4-adjacent-products.md)
- [agent-5-cloud-probe.md](agent-5-cloud-probe.md)
- [agent-6-llm-decompile-pipeline.md](agent-6-llm-decompile-pipeline.md)
- [agent-7-version-evolution.md](agent-7-version-evolution.md)
- [agent-8-academic-literature.md](agent-8-academic-literature.md)
- agent-2-wayback-community.md (pending)
