# Phase 1 sub-runbook — AI auth-flow capture (single feature use)

**Goal:** capture exactly one think-cell AI feature invocation and reveal how the desktop app authenticates to `app.prod.ai.think-cell.com/core/`.

**Scope (hard):** AI feature only. No chart insertion, no stock-image search, no telemetry — those are separate runbooks.

## Verified intel feeding this runbook

All bullets below were confirmed by static analysis of `tcaddin.dll` and Phase 11 endpoint recon. They are observations to ground the capture, not assumptions to extend.

- AI endpoint: `https://app.prod.ai.think-cell.com/core/` (UTF-16LE in `tcaddin.dll`, C++ constant `PpAICoreURL`)
- AI body uses Chat Completions JSON keys: `messages`, `content`, `role`
- HMAC-SHA256 via Windows BCrypt-CNG: `BCryptCreateHash`, `BCryptHashData`, `BCRYPT_ALG_HANDLE_HMAC_FLAG` all present as ASCII strings
- JWT is **definitively not used** (all 7 markers absent: `"alg":`, `"typ":"JWT"`, `"kid":`, `eyJ`, `RS256`, `HS256`, `ES256`)
- AWS Signature V4 is **not used** (all AWS markers absent)
- No `X-TC-*`, `X-License-Key`, or `X-Build` literals in the binary
- DPAPI token format on disk: `expires=<unix>&licensekeyid=<guid>&userhalfmonths=N&quota=N&hash=<HMAC>` — decryptable via `[ProtectedData]::Unprotect()`
- Local cache file: `%APPDATA%\think-cell\aiauthentication.bin`
- Server-side auth endpoint: `https://aiauthentication.appcom.think-cell.com/`
- POWERPNT.EXE makes the outbound HTTPS calls during AI feature use; `tcasr.exe` is a sidecar

## What we expect to learn

The capture is successful when these four observable markers are present in the artifacts:

1. The exact `Authorization` header value (or whichever header carries the credential) on the request to `app.prod.ai.think-cell.com/core/`
2. The auth-exchange shape — whether the DPAPI token is sent directly, or first traded at `aiauthentication.appcom` for something else (cookie, opaque bearer, derived HMAC signature)
3. The full request body schema for the AI feature: top-level keys around `messages` / `content` / `role`, plus any envelope fields (model name, request id, context)
4. The token-refresh request to `aiauthentication.appcom`: HTTP method, path, body, response shape

## Pre-conditions

- Personal Windows VM (interactive desktop, not SSH non-interactive)
- Python + Frida + mitmproxy installed (per `setup_phase1_capture_env.ps1`)
- mitmproxy CA installed in Windows root store
- think-cell ribbon enabled, valid personal license
- PowerPoint not currently running
- An empty `.pptx` ready in a known path for AI-feature trigger

## Step 1 — Force token refresh

Trigger a fresh auth flow on demand. Back up first so the box is restorable.

```powershell
$tc = "$env:APPDATA\think-cell"
Copy-Item "$tc\aiauthentication.bin" "$tc\aiauthentication.bin.bak" -Force
Remove-Item "$tc\aiauthentication.bin" -Force
```

Restore at end of session (see Stop rules).

## Step 2 — mitmproxy (Terminal 1)

Filter to auth + AI subdomains only. No usage, no stock images, no update.

```powershell
$cap = "$env:USERPROFILE\tc_auth"
New-Item -ItemType Directory -Path $cap -Force | Out-Null

mitmdump -p 8888 `
  --set confdir=$env:USERPROFILE\.mitmproxy `
  --set hardump=$cap\mitm.har `
  -w $cap\mitm.flow `
  --set anticache=true `
  --view-filter "~h (aiauthentication|cdnauthentication|ai\.appcom|app\.prod\.ai|prod\.ai)\.think-cell\.com"
```

The filter is intentionally tight. If something interesting shows up outside it, broaden in a follow-up run.

## Step 3 — Frida hooks (Terminal 2)

Launch PowerPoint first (empty deck, no AI feature yet), then attach.

```powershell
$pid = (Get-Process POWERPNT).Id
$cap = "$env:USERPROFILE\tc_auth"

frida-trace -p $pid `
  -i "winhttp.dll!WinHttpSendRequest" `
  -i "winhttp.dll!WinHttpWriteData" `
  -i "winhttp.dll!WinHttpReceiveResponse" `
  -i "winhttp.dll!WinHttpReadData" `
  -i "winhttp.dll!WinHttpQueryHeaders" `
  -i "winhttp.dll!WinHttpAddRequestHeaders" `
  -i "bcrypt.dll!BCryptCreateHash" `
  -i "bcrypt.dll!BCryptHashData" `
  -i "bcrypt.dll!BCryptFinishHash" `
  -i "kernelbase.dll!CryptUnprotectData" `
  -i "tcaddin.dll!*Auth*" `
  -i "tcaddin.dll!*Token*" `
  -i "tcaddin.dll!*Sign*" `
  -i "tcaddin.dll!*Hmac*" `
  -o $cap\frida.log
```

Why these targets:

- `WinHttpSendRequest` / `WinHttpAddRequestHeaders` / `WinHttpWriteData` capture the wire format including final header set and body bytes after any in-app TLS-pinning bypass would need to release them.
- `BCryptCreateHash` / `BCryptHashData` / `BCryptFinishHash` are the HMAC-SHA256 computation moments. Inspecting the key/data passed to these reveals what the `hash=` field on the DPAPI token signs over and what the request signature signs over (if any).
- `CryptUnprotectData` is the DPAPI unwrap of `aiauthentication.bin`.
- `tcaddin.dll!*Auth* / *Token* / *Sign* / *Hmac*` are the in-process methods orchestrating the above.

## Step 4 — Set system proxy

```powershell
netsh winhttp set proxy 127.0.0.1:8888
$reg = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Internet Settings"
Set-ItemProperty -Path $reg -Name "ProxyEnable" -Value 1
Set-ItemProperty -Path $reg -Name "ProxyServer" -Value "127.0.0.1:8888"
```

## Step 5 — Trigger exactly one AI feature use

Total session ≈ 10 minutes. Keep the workflow minimal so the artifact only contains AI-related traffic.

1. PowerPoint already open (from Step 3).
2. Open the prepared empty `.pptx`.
3. think-cell ribbon → invoke one AI feature (the first available AI action — text/chart-suggestion/etc., whichever the personal license exposes).
4. Wait for the response to render in the UI.
5. Do not interact with anything else. Do not save. Do not insert charts. Do not search images.
6. Close PowerPoint.

The capture should contain at minimum:

- One token-refresh exchange with `aiauthentication.appcom.think-cell.com` (because Step 1 deleted the cached token)
- One AI request to `app.prod.ai.think-cell.com/core/`
- Their corresponding HMAC computations and DPAPI unwrap in the Frida log

## Step 6 — Stop captures

```powershell
# Ctrl+C in both terminals
netsh winhttp reset proxy
$reg = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Internet Settings"
Set-ItemProperty -Path $reg -Name "ProxyEnable" -Value 0
```

Confirm artifacts:

```powershell
Get-ChildItem $env:USERPROFILE\tc_auth
# Expected: mitm.har, mitm.flow, frida.log, __handlers__\
```

## Step 7 — Ferry to Mac

```powershell
$ts = Get-Date -Format yyyyMMdd-HHmmss
$dest = "\\Mac\Home\code\apps\sales-ops-copilot\state\thinkcell_bridge\phase1_auth_capture\$ts"
New-Item -ItemType Directory -Path $dest -Force | Out-Null
Copy-Item -Recurse $env:USERPROFILE\tc_auth\* $dest
```

## Analysis (Mac side)

```bash
cd ~/code/apps/sales-ops-copilot
.venv/bin/python scripts/analyze_phase1_capture.py \
    --capture state/thinkcell_bridge/phase1_auth_capture/<latest>
```

Targeted queries to run against the artifacts. Each maps to one of the four expected outputs.

**1. Authorization header on `app.prod.ai/core/`:**

```bash
jq '.log.entries[] | select(.request.url | test("app\\.prod\\.ai.*/core/"))
  | {url: .request.url, headers: .request.headers}' \
  state/thinkcell_bridge/phase1_auth_capture/<latest>/mitm.har
```

**2. Auth-exchange flow — request/response shape at `aiauthentication.appcom`:**

```bash
jq '.log.entries[] | select(.request.url | test("aiauthentication\\.appcom"))
  | {method: .request.method, url: .request.url,
     reqBody: .request.postData.text, respBody: .response.content.text}' \
  state/thinkcell_bridge/phase1_auth_capture/<latest>/mitm.har
```

**3. AI request body schema:**

```bash
jq '.log.entries[] | select(.request.url | test("app\\.prod\\.ai.*/core/"))
  | .request.postData.text' \
  state/thinkcell_bridge/phase1_auth_capture/<latest>/mitm.har | jq '.'
```

**4. HMAC computation moments (Frida):**

```bash
grep -E "BCryptCreateHash|BCryptHashData|BCryptFinishHash|CryptUnprotectData" \
  state/thinkcell_bridge/phase1_auth_capture/<latest>/frida.log
```

Cross-reference timestamps: each `WinHttpSendRequest` to `app.prod.ai/core/` should be preceded by a `BCryptHashData` window whose input bytes are the canonical-request material the HMAC signs.

## Stop rules

- **Restore the token backup** at end of session: `Move-Item "$env:APPDATA\think-cell\aiauthentication.bin.bak" "$env:APPDATA\think-cell\aiauthentication.bin" -Force`
- **Reset Windows proxy** (`netsh winhttp reset proxy` and `ProxyEnable = 0`) before resuming normal use of the VM
- **Never share captures publicly** — they contain a personal license credential. Local Mac path only, never push to git, never paste into chat.
- **mitmproxy CA stays only on this personal VM** — never on a SimCorp-issued machine
- **Don't replay captured tokens** against any infrastructure beyond this VM
- **Don't loop the capture** — single-shot per session. Repeated forced refresh could trigger anti-abuse on the auth endpoint.

## What this unlocks

Once the four observable markers above are extracted and documented in `state/thinkcell_bridge/phase1_auth_capture/<latest>/findings.md`, the auth wall is characterized and Phase 12 (interoperability harness) can proceed against a known-shape protocol.
