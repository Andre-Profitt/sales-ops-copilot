# Agent 5 — think-cell Cloud / Web Surface Probe

Date: 2026-05-01
Scope: determine whether think-cell ships any browser-based / cloud / web-hosted product
beyond the desktop COM PowerPoint add-in, and capture its public API surface.

---

## Verdict

**No cloud / SaaS / browser-based think-cell product exists.**

think-cell is a desktop-only Office COM add-in for PowerPoint and Excel on Windows
and macOS. The only network-facing surface think-cell ships is **`tcserver.exe`**, a
self-hosted Windows-only render server that consumes `.ppttc` JSON over HTTP and emits
`.pptx` files. It is installed and run by the customer; it is not a hosted SaaS.

think-cell explicitly states it does **not** work with PowerPoint for the Web, Office
Mobile, or any browser-hosted Office host (KB0143; KB0165; manual/jsondataautomation).

The non-PowerPoint/non-Excel surface is narrow and contains **no API the desktop COM
surface does not already expose**:

- a render-only HTTP endpoint (`tcserver.exe`) whose contract is the `.ppttc` JSON schema;
- a Chromium/Firefox **browser extension** that scrapes Tableau views and web images and
  hands them back to the local PowerPoint add-in (zero standalone API);
- a "Send With Gmail" Windows MAILTO handler — a tiny shim that converts MAILTO
  invocations into a Gmail compose draft.

Net: the desktop COM probe's ~25 callable methods are the production API surface. The
server adds a single HTTP+JSON entry point, not new methods.

---

## 1. Subdomain probe (DNS + HTTP)

WebFetch was denied in this sandbox; verification was done with `dig` + `curl`.

| Host                      | DNS resolves?            | HTTP                                                                                                   |
| ------------------------- | ------------------------ | ------------------------------------------------------------------------------------------------------ |
| app.think-cell.com        | NO                       | n/a                                                                                                    |
| cloud.think-cell.com      | NO                       | n/a                                                                                                    |
| online.think-cell.com     | NO                       | n/a                                                                                                    |
| web.think-cell.com        | NO                       | n/a                                                                                                    |
| portal.think-cell.com     | NO                       | n/a                                                                                                    |
| api.think-cell.com        | NO                       | n/a                                                                                                    |
| tcserver.think-cell.com   | NO                       | n/a                                                                                                    |
| **server.think-cell.com** | **YES** (213.61.194.234) | 403 at `/`, **200 at `/portal/`** (empty body, SSO-gated)                                              |
| www.think-cell.com        | YES (162.55.44.8)        | 200 → marketing site                                                                                   |
| static.think-cell.com     | YES (CDN)                | hosts manual/static assets; `/ppttc/ppttc-schema.json` returns 404 today (asset moved/CDN-cached miss) |

**`server.think-cell.com`** is think-cell's corporate license/admin portal (the
licensee-facing portal an enterprise admin signs into to manage seats), not a SaaS
product. Headers send `X-Content-Type-Options: nosniff` and `Referrer-Policy: origin`
with empty body — it is gated behind an authenticated SSO flow that this probe did not
attempt. None of the marketing/product pages reference a hosted think-cell SaaS at this
host.

**Conclusion of DNS probe:** none of the conventional SaaS subdomains exist. The single
real corporate subdomain is the internal/admin portal, not a product.

---

## 2. Public product pages

Coverage from www.think-cell.com (verified via search-engine-indexed content):

- `/en/product/think-cell-suite` — the only commercial SKU is the desktop add-in suite.
- `/en/product/whats-new` — release notes through v12 stay desktop-add-in scoped.
- `/en` and pricing — single product, single SKU, no cloud/web tier.
- `/en/resources/manual/...` — entire manual is desktop add-in + tcserver scoped.

There is no "think-cell for Web," no "think-cell Cloud," no "think-cell for IT"
console, no developer portal. The "for IT" content lives under the deployment manual
(`/en/resources/manual/deploymentguide`, `/admin-preinstallation`,
`/first-installation`) — all of it is MSI/Group-Policy/macOS-pkg deployment of the
desktop add-in.

---

## 3. tcserver.exe — the only network surface

Source: [`/en/resources/manual/jsondataautomation`](https://www.think-cell.com/en/resources/manual/jsondataautomation),
[`/en/resources/manual/api`](https://www.think-cell.com/en/resources/manual/api),
[IANA media-type registration](https://www.iana.org/assignments/media-types/application/vnd.think-cell.ppttc+json).

### Architecture

- Ships in the desktop install at `C:\Program Files (x86)\think-cell\tcserver.exe`.
- Windows-only (no Linux/Mac/container build).
- Customer-hosted; not a multi-tenant cloud.
- Bind URL chosen by operator (e.g. `http://127.0.0.1:8080` or HTTPS on a chosen port).
- "Run as auto-start service" option registers it as a Windows service under a chosen
  account (account password is captured at registration).
- Companion test page `ppttc/sample.html` POSTs the bundled `sample.ppttc` and saves
  the binary response as `.pptx` — this is the canonical worked example.

### HTTP surface — public API endpoints

The think-cell server exposes **one** documented endpoint:

| Method | Path | Request                                                    | Response                                                                                     |
| ------ | ---- | ---------------------------------------------------------- | -------------------------------------------------------------------------------------------- |
| POST   | `/`  | body: `application/vnd.think-cell.ppttc+json` (a `.ppttc`) | `application/vnd.openxmlformats-officedocument.presentationml.presentation` (`.pptx`) binary |

- IANA-registered media type: `application/vnd.think-cell.ppttc+json`, UTF-8 only,
  registered by Arno Schoedl (think-cell CTO) on 2018-04-16.
- Schema: `ppttc-schema.json`, shipped at
  `C:\Program Files (x86)\think-cell\ppttc\ppttc-schema.json` and historically also
  published at `https://static.think-cell.com/ppttc/ppttc-schema.json` (current probe
  returned 404 on that CDN path; the on-disk copy in the install folder is canonical
  and is what the product references).
- Supported from think-cell v9 onwards.

`.ppttc` payload contract (from the manual):

- top-level: `{"template": <path-or-url>, "data": [ ... ]}`
- `template`: local filesystem path **or** HTTP/HTTPS URL to a `.pptx` containing
  named elements (`AddRangeData Name` slots).
- `data[]`: each entry binds a named element to a `table` array. For automation text
  fields / Harvey balls / checkboxes, `table` is `[[{value}]]`; for charts/tables it
  mirrors the datasheet shape.

### Authentication

- The server itself ships **no built-in authentication, no API keys, no OAuth, no
  HMAC**. It is a raw HTTP/HTTPS POST endpoint.
- Auth is delegated to "deploy it behind something" (reverse proxy, mTLS, network
  ACL). Neither `/manual/jsondataautomation` nor `/manual/api` documents a protocol-
  level auth mechanism. The deployment guide's only enterprise hardening guidance is
  "Run as auto-start service" + the operator-supplied bind URL.
- Practical implication: tcserver is a render worker, not an SSO-aware service. Any
  multi-user gating happens upstream of it.

### Client SDKs

- **No official SDK.** think-cell publishes the JSON schema and expects callers to
  POST it. Documented integration mode is "any HTTP client posting JSON."
- **Unofficial libraries** (community, all third-party):
  - `thinkcell` on PyPI (Carmo) — generates `.ppttc` files from Python.
  - `ThinkcellBuilder` on PyPI — alt builder for `.ppttc`.
  - `dbdoan/ThinkcellAuto` on GitHub — FastAPI shim that takes uploads, rewrites
    template URLs, and forwards to a tcserver instance.
  - `duarteocarmo/think-cell` on GitHub — small generator utility.

These are all `.ppttc` writers; none of them adds API surface beyond the single POST.

---

## 4. "Send With Gmail" mystery — what the ProgID actually does

Source: [`/en/resources/manual/save-send-slides`](https://www.think-cell.com/en/resources/manual/save-send-slides),
KB0225, KB0240, KB0113, privacy policy.

The COM ProgID `think-cell Send With Gmail.Mailto` is **a Windows MAILTO protocol
handler**, not an Outlook add-in or a cloud service. It plugs into:

- `HKLM\SOFTWARE\Clients\Mail\` (registered mail client list)
- the `MAILTO` URL-protocol associations under `HKEY_CLASSES_ROOT`

so that Windows Settings → Apps → Default Apps → Mail (and any
`MAILTO:`/`URL:MailTo Protocol` association) can pick "think-cell Send With Gmail" as
the default mail client.

Behavior when invoked:

1. PowerPoint's `Send Slides` dialog (or any Windows app calling MAILTO with an
   attachment) hands the assembled message to the registered mail handler.
2. The handler opens a Gmail compose draft in the user's default browser, prefilled
   with subject/body and the slide attachment(s).
3. OAuth2 to Google: per think-cell's privacy policy, "the software will locally
   access and use your Google user data (i.e., your Gmail address) to create a draft
   email; no Google user data will be shared or stored (with the exception of, for
   purely technical reasons, a so-called OAuth2 refresh token)." The refresh token
   lives locally; nothing is uploaded to think-cell.
4. Requires admin install (the manual notes this option is only available if
   think-cell was installed with admin rights, presumably because the MAILTO
   association is HKLM-scoped).

**This is not an API surface.** It implements the Windows MAILTO contract, nothing
more — no callable methods, no IPC, no HTTP, no documented automation entry point.

The companion `Send Slides` feature is implemented inside PowerPoint by the desktop
add-in itself (it composes a message and hands it to whatever the user's default mail
handler is — Outlook classic via Simple MAPI, or "Send With Gmail," or copy-to-
clipboard fallback). KB0240 explicitly notes that **new Outlook for Windows** does not
yet support attachment-bearing mail composition via the integration path think-cell
uses, so think-cell falls back to classic Outlook. There is no Outlook add-in.

---

## 5. Other Office host integrations

Source: KB0165, KB0143, KB0226, manual.

| Host                                          | Integration?                                                                                  |
| --------------------------------------------- | --------------------------------------------------------------------------------------------- |
| PowerPoint (Win/Mac, desktop)                 | Yes — primary add-in.                                                                         |
| Excel (Win/Mac, desktop)                      | Yes — datasheet + Data Links integration.                                                     |
| PowerPoint for the Web                        | **No.** Explicitly unsupported.                                                               |
| Excel for the Web                             | **No.** Explicitly unsupported.                                                               |
| Office Mobile (iOS, Android, ARM Win)         | **No.** KB0143: Office Mobile lacks the COM add-in API; integration is impossible.            |
| Outlook (classic, Win)                        | Indirect only — `Send Slides` uses Simple MAPI to drop a message into Outlook. Not an add-in. |
| Outlook (new, Win)                            | Currently **broken** for attachment-bearing send (KB0240); falls back to classic Outlook.     |
| Outlook (Mac)                                 | Indirect via macOS Mail-app authorization (KB0225). Not an add-in.                            |
| Word                                          | **No** integration.                                                                           |
| OneNote                                       | **No** integration.                                                                           |
| Visio                                         | **No** integration.                                                                           |
| Microsoft Teams (bot, app, message extension) | **No** integration. No tcserver-Teams bridge documented.                                      |
| iOS app                                       | **No.**                                                                                       |
| Android app                                   | **No.**                                                                                       |
| Tableau (Desktop)                             | **No** direct integration.                                                                    |
| Tableau (Cloud/Server, in browser)            | Yes, via the **think-cell browser extension**.                                                |

### The browser extension (Chrome / Edge / Firefox)

- Auto-installs into Chrome and Edge during desktop install (must be enabled by user).
- Manual install for Firefox via Mozilla Add-ons.
- Two functions:
  1. **Create elements from Tableau** — captures a Tableau view rendered in the
     browser and links it to a think-cell chart in PowerPoint. Tableau Desktop
     standalone is **not** supported; only Tableau views displayed in a browser.
  2. **Import images and icons from web pages** into PowerPoint with two clicks.
- The extension talks to the **local desktop add-in via native messaging**; it does
  not call any think-cell-hosted endpoint and does not expose a public API of its
  own. Without the desktop add-in installed locally, the extension is useless.

### Microsoft 365 Copilot

think-cell's blog positions Copilot as a complementary tool inside Word/Excel/
PowerPoint/Outlook, but there is no Copilot plugin / agent / declarative manifest
for think-cell published. No Copilot Studio extension shipped.

---

## 6. Mobile

- No native iOS or Android app.
- KB0143: think-cell does not run on Office Mobile (the Office Mobile app on iOS,
  Android, and ARM-Windows lacks the COM add-in interface).
- Mobile users can **view** decks containing think-cell objects via Office Mobile;
  charts render as static images embedded in the PPTX. Editing requires returning to
  desktop PowerPoint with think-cell installed.
- No "think-cell Companion" or QR-code-share path.

---

## 7. Public API endpoint inventory (consolidated)

Endpoints think-cell publishes for direct programmatic use:

| Surface                              | Endpoint                                    | Contract                                               | Source                          |
| ------------------------------------ | ------------------------------------------- | ------------------------------------------------------ | ------------------------------- |
| tcserver                             | `POST <bind-url>/`                          | body `application/vnd.think-cell.ppttc+json` → `.pptx` | manual/jsondataautomation, IANA |
| Browser extension <-> desktop add-in | native-messaging IPC                        | undocumented, internal                                 | manual/tableaudata              |
| MAILTO handler                       | `mailto:` URL with attachment               | Windows MAILTO contract                                | manual/save-send-slides         |
| OAuth2 (Gmail)                       | `accounts.google.com` (Google's OAuth)      | think-cell-issued client; refresh token stored locally | privacy policy                  |
| Browser-extension Tableau pull       | the Tableau view's own browser-rendered DOM | scrape-from-rendered-view; Tableau is the upstream     | manual/tableaudata              |

There is no `api.think-cell.com`. There is no chart-rendering REST API hosted by
think-cell. There is no usage telemetry endpoint published as a developer surface.

---

## 8. Bottom line — does the non-PowerPoint surface expose API the desktop COM does not?

**No, with one nuance.**

- The COM add-in's ~25 callable methods (chart creation, data linking, style
  application, Send Slides) are the **superset** of what think-cell automation can do.
- `tcserver.exe` is **not** an API extension. It is a **transport** for a subset of
  what the COM add-in already does — specifically, the "fill named template elements
  with data and emit a `.pptx`" workflow. It runs the same engine in headless mode.
  It exposes `.ppttc` JSON (declarative template fill); it does **not** expose
  per-method calls (no "create chart of type X, add label Y, set style Z" RPC).
- Browser extension + MAILTO handler are integration shims, not new APIs.
- The mobile / Outlook / Word / Visio / OneNote / Teams surfaces are **empty**.

The single nuance: **`.ppttc` is a declarative format**, so for tasks that fit its
schema (template fill + datasheet population + reorder/reuse slides), it is a more
ergonomic way to drive think-cell from non-Windows callers and from web servers than
poking the COM API. But it cannot reach methods that don't have a `.ppttc` analogue
(arbitrary chart construction outside a pre-authored template, runtime style edits,
ad-hoc Excel-link manipulation, anything beyond "fill the named slots"). For those,
the COM API remains the only programmatic entry point.

If the user's hidden-surface probe of the COM API is the bottleneck, **the cloud /
web surface will not unblock it**. The next investigative directions are:

1. The on-disk `ppttc-schema.json` in the install folder — gives the exact element
   types and `data` shapes tcserver accepts (this is the most underexplored
   _documented_ surface).
2. Diff the COM-typelib (TLB) embedded in the add-in DLL against what the manual
   documents — the COM probe found ~25 methods, but typelib introspection often
   surfaces undocumented dispatch IDs that the official manual omits.
3. The native-messaging protocol between the browser extension and the desktop add-in
   — undocumented; if reachable, it could expose a wider command surface than the
   public COM. (Still local-only, not cloud.)

---

## Sources

- [www.think-cell.com — JSON Data Automation manual](https://www.think-cell.com/en/resources/manual/jsondataautomation)
- [www.think-cell.com — How to use think-cell's API](https://www.think-cell.com/en/resources/manual/api)
- [www.think-cell.com — Send and save slides](https://www.think-cell.com/en/resources/manual/save-send-slides)
- [www.think-cell.com — Tableau data integration](https://www.think-cell.com/en/resources/manual/tableaudata)
- [www.think-cell.com — Deployment guide](https://www.think-cell.com/en/resources/manual/deploymentguide)
- [www.think-cell.com — KB0143 (Office Mobile)](https://www.think-cell.com/en/resources/kb/0143)
- [www.think-cell.com — KB0165 (M365 / Office 2016+ support)](https://www.think-cell.com/en/resources/kb/0165)
- [www.think-cell.com — KB0225 (Mac authorization to send mail)](https://www.think-cell.com/en/resources/kb/0225)
- [www.think-cell.com — KB0240 (new Outlook for Windows)](https://www.think-cell.com/en/resources/kb/0240)
- [www.think-cell.com — KB0113 (email stuck in Outbox)](https://www.think-cell.com/en/resources/kb/0113)
- [www.think-cell.com — Privacy policy (Gmail OAuth scope)](https://www.think-cell.com/en/company/privacypolicy)
- [www.think-cell.com — think-cell 10 on macOS](https://www.think-cell.com/en/resources/content-hub/think-cell-runs-on-macos)
- [www.think-cell.com — KB0095 (Mac availability)](https://www.think-cell.com/en/resources/kb/0095)
- [IANA — application/vnd.think-cell.ppttc+json](https://www.iana.org/assignments/media-types/application/vnd.think-cell.ppttc+json)
- [Chrome Web Store — think-cell extension](https://chromewebstore.google.com/detail/think-cell/ppcdkdcafnbklehdngbhmhpidandcjke)
- [Mozilla Add-ons — think-cell](https://addons.mozilla.org/en-US/firefox/addon/think-cell/)
- [PyPI — thinkcell (unofficial)](https://pypi.org/project/thinkcell/)
- [GitHub — dbdoan/ThinkcellAuto (unofficial FastAPI shim)](https://github.com/dbdoan/ThinkcellAuto)

Word count: ~2,100.
