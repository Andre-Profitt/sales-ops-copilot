# Phase 12 progressive decoding — 2026-05-02

## What's decoded vs. still gated

### ✅ Auth-token issuance flow — FULLY DECODED

Captured 2026-05-02-114234 via mitm + Frida via scheduled-task → Session 1.

```
GET https://aiauthentication.appcom.think-cell.com/
    ?build=<build>            # e.g. 1000220 (from settings.xml reqver)
    &systemid=<22-char base32> # install GUID, also from settings.xml
    &licensekey=<XXXXX-...>    # human-readable license key

Headers (3): Connection / Accept / Host. NO Authorization header. NO HMAC on the
            request itself.

Returns 200 text/plain, 121-byte URL-encoded payload:
    expires=<unix>&licensekeyid=<UUID>&userhalfmonths=N&quota=N&hash=<22-char b64url>

Client DPAPI-encrypts the response and writes to
    %APPDATA%\think-cell\aiauthentication.bin.
```

**Implementation:** `tc_toolkit.tcauth.mint_token(InstallParams)` works live from Mac.
Verified by minting a fresh 24h token without touching the install. `hash` is
server-computed; client doesn't need to compute it for issuance.

### ✅ `app.prod.ai.think-cell.com/core/` — **WSS, no Bearer (CAPTURED LIVE 2026-05-02-161513)**

**Update 2026-05-02 evening:** First successful live capture via mitm. Architecture
fully decoded. The earlier "Bearer token in HTTP header" hypothesis was wrong on two
counts: (a) the token fields are passed as **URL query params**, not in the
Authorization header, AND (b) the actual chat traffic goes over a **WebSocket** not
HTTP POST. Capture artifact: `state/thinkcell_bridge/aicore_captures/20260502-161513/`.

**Verified flow (from live capture):**

1. Token mint via `aiauthentication.appcom` (already known) → returns
   `expires=...&licensekeyid=...&userhalfmonths=...&quota=...&hash=...`
2. WebView2 navigates to:
   ```
   https://app.prod.ai.think-cell.com/?build=1000220&systemid=<sysid>&lang=en&theme=system&expires=<token.expires>&licensekeyid=<token.licensekeyid>&userhalfmonths=<token.userhalfmonths>&quota=<token.quota>&hash=<token.hash>
   ```
   ALL token fields go in the URL query string. NO Authorization header. NO Bearer.
3. Server responds 200 with React/Next.js HTML, Set-Cookie `tc_client=<uuid>.<random>`
4. WebView2 fetches `/api/config` which returns:
   ```json
   { "wsUrl": "wss://app.prod.ai.think-cell.com/core", "envName": "production" }
   ```
5. WebView2 opens **WebSocket** at `wss://app.prod.ai.think-cell.com/core` for
   the actual chat completions (NOT a HTTP POST endpoint)
6. Chat messages flow as WebSocket frames over the WSS connection
7. Generated artifacts (e.g. Excel files for inserted charts) are downloaded via
   `GET /core/file/res_<uuid>?name=<filename>` (307 redirect to a signed URL)

**Required headers** (from real WebView2 capture):

- `User-Agent`: `Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36 Edg/130.0.0.0` (or v147 — the WebView2 release on the VM)
- `Sec-CH-UA`: `"Not.A/Brand";v="8", "Microsoft Edge WebView2";v="147", "Chromium";v="147"`
- `Sec-CH-UA-Mobile`: `?0`
- `Sec-CH-UA-Platform`: `"Windows"`
- `Cookie`: `tc_client=<uuid>.<random>` (set by server on first navigation)

**The 403 we kept getting from outside** was specifically because we were missing
the token query params. Even httpx with no token passes Cloud Armor as long as the
request shape matches what the WebView2 sends — but we'd still need the right
session state for the actual app to render.

**WebSocket frame contents NOT yet captured** — initial mitm capture missed the
WSS frames because WebView2 uses HTTP/3 (QUIC) for WS by default, which bypasses
HTTP proxies. Next capture needs `WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS=--disable-quic --disable-http3`
set as user env var BEFORE PP relaunch. Script: `capture_aicore_v3_no_http3.ps1`.

**The audit reset everything we assumed.** The /core/ endpoint does NOT use HMAC signing.
Static analysis of `tcaddin.dll` via the existing Ghidra decompile (112,708 functions
at `state/thinkcell_bridge/ghidra_decompile/20260502-093500_x86_32/functions.jsonl`)
reveals the actual architecture:

**Auth scheme (verified from decompile):** Plain Bearer token, no HMAC.
Header strings present in 10+ functions:

```
Accept:application/json\r\nAuthorization:Bearer <token>
Accept:application/json\r\nContent-Type:application/json\r\nAuthorization:Bearer <token>
```

**Request flow (verified from decompile + binary string mining):**

1. PP loads `aiauthentication.bin`, decrypts via DPAPI, gets the token blob
2. PP launches a **WebView2** child process (msedgewebview2.exe) — confirmed by
   13 references to `WebView2`, 6 to `ICoreWebView2`, and the source path
   `S:\tcaddin\PpAddIn\Dialogs\PpAIDialog.cpp` (140 hits)
3. WebView2 navigates to the **PpAIURL** (NOT /core/):
   ```
   https://app.prod.ai.think-cell.com/?build=<build>&systemid=<sysid>&lang=<lang>&theme=<light|dark>
   ```
   (config keys `PpAIURL` and `PpAICoreURL` both confirmed in binary at offsets
   0x01911380 and 0x01a0c244 respectively)
4. The web app (loaded in WebView2) calls `window.chrome.webview.hostObjects.tc.getClientCredentials()`
   via the Edge JS bridge. PP responds with a JSON template found in the binary:
   ```
   { "token": "<token-payload>" }
   ```
5. The web app then sends XHR/fetch to `https://app.prod.ai.think-cell.com/core/...`
   with `Authorization: Bearer <token>` from step 4

**JS bridge methods exposed by PP to WebView2** (extracted from binary at
0x0191141c–0x01911654):

- `getClientCredentials` ← **the auth-token provider**
- `insertSummarySlide`, `setTitle`, `insertSE`, `setShapeContents`
- `getSelectedShapesContentsTextOnly`, `getSelectedShapesContents`
- `getActiveSlideContentsTextOnly`, `getActiveSlideContents`
- `getSelectedSlidesContentsTextOnly`, `getSelectedSlidesContents`
- `getSlideContentsTextOnly`, `getSlideContents`

**Why direct httpx/curl probing of /core/ from Mac returns 403 (verified
2026-05-02-13:44 across all attempts):**

Every request to `app.prod.ai.think-cell.com` (including unauthenticated
`GET /`) returns `403 Forbidden` from `nginx` with `Via: 1.1 google` —
this is **Google Cloud Armor at the edge** rejecting before any application
logic runs. Tested:

- httpx + various Bearer values (full payload / hash only / hex / b64 / etc.)
- httpx + various paths (/core/, /core/chat/completions, /core/v1/chat/completions, etc.)
- httpx + various methods (GET / POST / OPTIONS / HEAD)
- httpx + Edge UA + Origin + Referer + Sec-Fetch-\* CORS headers
- curl_cffi with `chrome131` / `chrome124` / `edge99` / `safari17_2_ios` / `firefox133` TLS impersonation
- VM (`Invoke-WebRequest` from Windows-VM) — same 403
- Other think-cell hosts: aiauthentication 400 (no GLB), freepik 404 (nginx),
  unsplash 301 (Heroku) — only `app.prod.ai`, `ai.appcom`, `schemas` are 403

**Conclusion:** Cloud Armor whitelists requests originating from a real WebView2
process (presumably checking JA3 + headers + Origin + cookie state collectively).
Replicating the exact handshake outside WebView2 has not yet succeeded.

**The only known way to capture /core/ traffic is to make a real WebView2
process navigate to the entry URL.**

## Programmatic-click investigation — failed paths

| Approach                                                      | Why it failed                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                |
| ------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `Application.CommandBars.ExecuteMso("tc:AISidePane")`         | Microsoft docs explicit: ExecuteMso supports built-in idMso only, not custom add-in controls in the `tc:` namespace. Returns "Value does not fall within expected range."                                                                                                                                                                                                                                                                                                                                    |
| UIA `ControlViewWalker` filtered for `Button`                 | Office Fluent UI ribbon items don't render as standard `Button` ControlType. Found 21 buttons, all PowerPoint chrome (title bar, view buttons), zero think-cell controls.                                                                                                                                                                                                                                                                                                                                    |
| UIA all-types enumeration with managed UIAutomationClient     | Returned 0 invokables under PowerPoint window. Office Fluent UI rendering bypasses the managed UIA tree.                                                                                                                                                                                                                                                                                                                                                                                                     |
| `Alt+Q` (Office "Tell Me" search) + "AI" + Enter via SendKeys | Keystrokes WERE delivered (verified via mitm — `substrate.office.com/search/api/v1/suggestions?query=AI` returned 200 to PowerPoint). But the dropdown didn't include `tc:AISidePane` as the selected item; Office's Tell Me index excludes custom add-in commands by default.                                                                                                                                                                                                                               |
| UIA `RawViewWalker` (depth 16, post-tab-select)               | **Stage 1 — also failed.** Probe ran 2026-05-02-163300 with think-cell tab confirmed selected. Returned 16 invokables: window controls (Min/Max/Close/File Tab), Home-tab built-ins (`SlideNewGalleryInsert`/`New Slide`), notes pane, status-bar zoom controls. **Zero think-cell ribbon controls.** Confirms tcaddin.dll renders custom ribbon items via DirectX/D2D/GDI without exposing them through UIA's even-unfiltered raw tree. UIA is fully dead for this. Probe artifact: `~\tc_invokables.json`. |

## Programmatic-click — researched strategies still to try

Web searches against current Microsoft docs + community sources confirmed four
techniques worth attempting in order of cost/probability. **Stage 1 ruled out
2026-05-02 — escalating to Stage 2 next.**

### ~~1. UIA `RawViewWalker`~~ — RULED OUT 2026-05-02

Tested. See failed-paths table above. think-cell controls are absent from
the UIA tree at every filter level (control / content / raw). Any future
strategy must bypass UIA entirely (MSAA via `WM_GETOBJECT`, QAT pinning,
or direct hook).

### 2. MSAA via `oleacc.dll` `AccessibleObjectFromWindow` (~85% prob)

Microsoft has a published code sample (`CSOfficeRibbonAccessibility` in
`microsoftarchive/msdn-code-gallery-microsoft`) that does exactly this for
Office ribbons. Pattern:

```
AccessibleObjectFromWindow(hwnd, OBJID_CLIENT, IID_IAccessible, &pAcc)
recurse via AccessibleChildren(...)
find target by accName / accRole
call IAccessible::accDoDefaultAction()
```

MSAA reaches Office controls via `WM_GETOBJECT` which Office handles natively,
unlike UIA which requires elements to be exposed in its tree explicitly.

**Stage 2 partial findings (2026-05-02-165725):** PP main-window OBJID_CLIENT
returns a thin proxy with 7 simple children (no names, no IDispatch). The rich
ribbon accessibility lives on a child HWND: `NetUIHWND` with `accName='Ribbon'`
and `accChildCount=25` (`hwnd=0xB05BA loc=350,376,509x178`). Walking from the
ribbon HWND directly is the correct entry point. Implementation gotchas
discovered:

- IAccessible must be declared as `[ComImport, InterfaceType(InterfaceIsDual)]`
  in C#, **not** `InterfaceIsIDispatch`. With IDispatch dispatch, indexed
  property getters like `accName(varChild)` fail with DISP_E_MEMBERNOTFOUND
  because Office's RCW only exposes them via PROPERTYGET, not METHOD invocation.
  `InterfaceIsDual` routes calls through the vtable in IDL order, which works.
- PowerShell loses COM type info across `out` parameters — `out IAccessible`
  becomes `System.__ComObject` and reflection-based member resolution
  returns DISP_E_MEMBERNOTFOUND. Fix: do the entire MSAA walk inside the C#
  helper and return a flat List<AccEntry> — PowerShell only consumes the
  result, never holds the IAccessible RCW.
- For full DISPATCH children (returned from `get_accChild(i)` non-null), call
  `child.accName(0)` (CHILDID_SELF) — **not** `parent.accName(i)`. Office
  returns null name from the parent for DISPATCH children.
- Discover the ribbon HWND by enumerating PP child windows, calling
  `AccessibleObjectFromWindow(child, OBJID_CLIENT)`, and matching
  `accName=='Ribbon'`. Other candidates: `NetUIHWND root='Status Bar'` (14
  children), `MsoCommandBarDock`, `MsoWorkPane`, `MDIClient root='Workspace'`.

### 3. QAT pinning via `PowerPoint.officeUI` XML (attempted 2026-05-02)

Add `tc:AISidePane` to the Quick Access Toolbar by editing
`%LocalAppData%\Microsoft\Office\PowerPoint.officeUI`. **Critical pitfall
discovered:** the `tc:` prefix MUST be bound via `xmlns:tc="thinkcell.addin"`
on the element itself or an ancestor in scope:

```xml
<mso:control xmlns:tc="thinkcell.addin" idQ="tc:AISidePane" visible="true" />
```

Without the namespace binding (which is NOT auto-applied from the
`<mso:tab xmlns:tc="thinkcell.addin">` in the same file because it's a
different scope), Office silently drops the entry. Worse: a malformed entry
can corrupt PP's startup → PP launches but never creates a window → Office
prompts "Start in Safe Mode?" on next launch → that prompt is invisible to
non-interactive Session 1, so PP zombies. Recovery requires clearing
`HKCU\Software\Microsoft\Office\16.0\PowerPoint\Resiliency\StartupItems` and
restoring `PowerPoint.officeUI` from `.bak.original` (or letting Office
regenerate defaults by deleting it).

QAT items would be stable, standard UIA buttons regardless of the underlying
custom-control type. Click via UIA InvokePattern.

Risks (per Microsoft docs + empirical):

- Editing while PowerPoint is running can corrupt the file → close PP first
- If Office detects any problem with `.officeUI`, it can revert to defaults
  and delete all customizations → back up before editing
- The `.bak.original` snapshot can itself be poisoned if pin script ran
  before backup capture; force a true clean baseline by deleting all
  `PowerPoint.officeUI*` files and letting Office regenerate

### 4. Frida custom `__handlers__` pre-placement (~95% prob, parallel improvement)

`frida-trace` regenerates handler stubs every run UNLESS a custom
`__handlers__/<dll>/<func>.js` already exists. The default stubs only log
function names; custom handlers can dump argument bytes.

Critical case sensitivity: the module name in `-i` must match the
`__handlers__` folder case exactly. `frida-trace -i bcrypt.dll!*` writes to
`__handlers__/bcrypt.dll/`; `-i BCRYPT.DLL!*` writes to `__handlers__/BCRYPT.DLL/`.

Custom handlers committed in this repo at
`scripts/frida_handlers/{BCryptCreateHash,BCryptHashData,BCryptFinishHash}.js`
dump the algorithm, HMAC key, hashed-input bytes, and hash output bytes.
Pre-place them into `<capture-dir>/__handlers__/bcrypt.dll/` before launching
frida-trace and the next capture grabs full byte content for every BCrypt call.

## Combined strategy

Run order + 2026-05-02 status:

1. ~~Stage 1: RawViewWalker (10 min).~~ **DONE — failed.** UIA tree doesn't
   surface think-cell controls at any filter level.
2. ~~Stage 2: MSAA via oleacc P/Invoke (1-2 hrs).~~ **PARTIAL — infrastructure
   complete, click never executed.** Wrote three iterations of the probe
   (PowerShell late-bind → C# [ComImport] InterfaceIsIDispatch → InterfaceIsDual
   - walk-inside-C#); located ribbon HWND `NetUIHWND accName='Ribbon'`
     `accChildCount=25`. The deep ribbon walker (`probe_thinkcell_ribbon_deep.ps1`)
     is ready to run but blocked on PP startup instability — every retry triggers
     the Safe Mode → Resiliency → zombie-PP cascade.
3. ~~Stage 3: QAT pinning.~~ **PARTIAL — pin succeeds but namespace binding
   was wrong on first attempt.** `xmlns:tc="thinkcell.addin"` must be added
   to the `<mso:control>` element itself (the binding on `<mso:tab>` does not
   propagate). Fixed in `probe_qat_pin_aisidepane.ps1`; verification blocked by
   the same PP startup instability.
4. ~~Stage 4: Frida custom handlers.~~ **DONE.** Wired into Phase 12 capture
   script (`run_phase12_with_ai_click.ps1` step `place_frida_custom_handlers`)
   so every future Phase 12 run pre-places `BCryptCreateHash.js` /
   `BCryptHashData.js` / `BCryptFinishHash.js` into
   `<capture-dir>/__handlers__/bcrypt.dll/` before launching `frida-trace`.
   Next capture will grab full HMAC key + input + output bytes.

## What the deep audit changed (2026-05-02 evening)

**Stages 1-3 (UIA / MSAA / QAT) were solving the wrong problem.** They tried
to make PowerPoint click the AI ribbon button so PowerPoint would generate
/core/ traffic. But PowerPoint **never** generates /core/ traffic — only
the WebView2 child process does. Even if we'd succeeded at clicking the
button, all PowerPoint would have done is launch WebView2 with a URL.

The real problem isn't "trigger the click" — it's **"make a real WebView2
instance navigate to the entry URL"**. That can be done multiple ways without
any PowerPoint UI involvement.

## Workarounds in priority order (2026-05-02 audit)

### #1 — Playwright with WebView2 JS-bridge polyfill (~75% prob, all-Mac, no VM)

The cleanest path. Run a Playwright Chromium instance on Mac, navigate to:

```
https://app.prod.ai.think-cell.com/?build=1000217&systemid=<sysid>&lang=en-US&theme=light
```

Inject a JS shim before page load that polyfills `window.chrome.webview.hostObjects.tc`:

```javascript
window.chrome = window.chrome || {};
window.chrome.webview = {
  hostObjects: {
    tc: {
      getClientCredentials: async () =>
        JSON.stringify({ token: "<URL-encoded-payload-from-mint_token>" }),
      getActiveSlideContents: async () => "stub",
      getSelectedSlidesContents: async () => "stub",
      // ... rest of the 13 bridge methods
    },
  },
};
```

Use Playwright's `page.route()` to capture every /core/ request. The web app
loads, calls the bridge, makes /core/ requests with our token. We see the
exact wire format end-to-end.

**Risk:** Cloud Armor's edge-403 may still block Playwright if its check is
based on something other than TLS/UA (e.g. specific cookie state from a Microsoft
EdgeHTML embed flag). If so, fall back to #2.

### #2 — Frida injection of `CPpAIDialog::CPpAIDialog` constructor (~70%, requires healthy PP)

Skip the UI entirely. Attach Frida to a running POWERPNT.EXE, find the
constructor at `tcaddin.dll + 0x431050` (`FUN_2c431050`), call it directly
with a synthetic `CPpDocumentWindow*` argument. The dialog opens, WebView2
launches, /core/ traffic flows through mitm.

```javascript
const baseAddr = Module.findBaseAddress('tcaddin.dll');
const ctorAddr = baseAddr.add(0x431050);
const ctor = new NativeFunction(ctorAddr, 'pointer',
    ['pointer','pointer','pointer'], 'thiscall');
// CPpDocumentWindow* must be obtained — either:
//   (a) hook CPpDocumentWindow::CPpDocumentWindow constructor, capture this-ptr
//   (b) walk known global vtable pointers in tcaddin.dll's data segment
const docWnd = ...;
const dialogStorage = Memory.alloc(0x800); // sizeof CPpAIDialog (estimate)
ctor(dialogStorage, docWnd, NULL);
```

**Blocker:** PP zombies within 30-60s of launch (MsoCrashMainThread per the
log audit). Need to either (a) extend the healthy window or (b) attach Frida
_before_ the zombie cascade hits.

### #3 — Stand up a local WebView2 + JS bridge in C# / Edge (~60%, on VM)

Write a small WebView2 host application in C# that:

1. Initializes ICoreWebView2 with `AddHostObjectToScript("tc", new TcBridge())`
2. Exposes `getClientCredentials()` returning the minted token JSON
3. Navigates to the entry URL

Run on the VM where think-cell is registered. WebView2 from a Microsoft
Edge installation has the same TLS profile as the legitimate think-cell
embed, so Cloud Armor accepts it.

**Why this beats #1 if Cloud Armor TLS-fingerprints:** uses real WebView2
runtime (msedgewebview2.exe), not Playwright Chromium. Identical TLS to
the legitimate path.

### #4 — Static-analysis-only path via Ghidra (~40%, no traffic capture needed)

Decompile `FUN_2c431050` (CPpAIDialog ctor, 1462 bytes) and the chain
of WebView2 setup functions (`FUN_2d0d7f40` 2897 bytes, `FUN_2d0d7180`
884 bytes, `FUN_2c002247` 443 bytes). Read the source-of-truth:

- The exact entry URL template (already extracted: `app.prod.ai/?build=&systemid=&lang=&theme=`)
- The exact Bearer header format (already extracted: `Authorization:Bearer <token>`)
- The web app's response payload schema (only readable from a captured
  /core/ response — BLOCKED at static analysis since responses aren't
  hardcoded)

**Limit:** static analysis tells us the request format but not the response
schema or the chat-completions wire format. Need at least one captured
response to know how to consume /core/ output.

## Recommended next step

**Do #1 first.** All-Mac, no VM, no PP, no Frida. If Cloud Armor passes
Playwright Chromium, we're done in 30 minutes. If it 403s, pivot to #3
(real WebView2 on VM) which has the strongest TLS-equivalence guarantee.

## Sources (verified 2026-05-02)

- TreeWalker.RawViewWalker: https://learn.microsoft.com/en-us/dotnet/api/system.windows.automation.treewalker.rawviewwalker
- UI Automation Tree Overview: https://learn.microsoft.com/en-us/windows/win32/winauto/uiauto-treeoverview
- AccessibleObjectFromWindow: https://learn.microsoft.com/en-us/windows/win32/api/oleacc/nf-oleacc-accessibleobjectfromwindow
- Microsoft sample CSOfficeRibbonAccessibility: https://github.com/microsoftarchive/msdn-code-gallery-microsoft/blob/master/OneCodeTeam/Automate%20Office%20Ribbon%20through%20MSAA%20%28CSOfficeRibbon%E2%80%8BAccessibility%29
- pinvoke.net IAccessible (oleacc): https://www.pinvoke.net/default.aspx/oleacc/IAccessible.html
- MS-CUSTOMUI QAT schema: https://learn.microsoft.com/en-us/openspecs/office_standards/ms-customui/93e2f741-a06c-4096-8dbf-5a97fefca545
- frida-trace docs: https://frida.re/docs/frida-trace/
- SensePost frida-trace deep dive: https://sensepost.com/blog/2025/using-improving-frida-trace/

## Capture artifacts

- 20260502-114234: first successful capture (auth flow decoded)
- 20260502-121229: PSTools.zip capture (false positive, no think-cell traffic)
- 20260502-121540: COM connect failed (PP zombie state)
- 20260502-121751: Tell-Me Alt+Q capture (auth re-fired, no `/core/`)
- 20260502-163300: RawViewWalker probe (`tc_invokables.json` — 16 invokables, all PowerPoint chrome, zero think-cell controls; rules out UIA at every filter level)
- 20260502-165725: HWND-MSAA probe (`tc_hwnds.json` — 21 child windows; located ribbon at `NetUIHWND hwnd=0xB05BA accName='Ribbon' accChildCount=25 loc=350,376,509x178`; established correct MSAA entry point)
- 20260502-170321: QAT pin (`tc_qat_pin.json` — `tc:AISidePane` injected into PowerPoint.officeUI; XML round-trips, success=true, pre_size=7168 → post_size=8477; namespace binding missing → Office silently dropped entry; fixed in script)
- 20260502-171138: Office crash recovery succeeded (`tc_recover.log` — cleared `HKCU\...\PowerPoint\Resiliency\{StartupItems,DisabledItems,DocumentRecovery}`, restored officeUI from .bak.original, PP launched cold pid=10584)
- 20260502-171608: clean-baseline reset (`tc_clean.log` — deleted ALL `PowerPoint.officeUI*` files including poisoned .bak.original; Office regenerated default 7162-byte officeUI; PP up at 'Presentation1 - PowerPoint')
- 20260502-172823: Stage 2c deep ribbon MSAA walk WITH think-cell tab selected (`tc_ribbon_deep.json` — `ribbon_hwnd=0x9F044A`, `accessible_count=1` (just the root, role=38 Indicator), `candidate_count=0`, `errors=0`). **Hypothesis:** when the think-cell tab is active, tcaddin.dll's custom rendering replaces the standard MSAA ribbon tree, leaving only the root container accessible. The prior HwndProbe (171608) saw 25 children precisely because no think-cell tab was selected. Probe extended with `-SkipTabSelect` flag to test the hypothesis next session.
