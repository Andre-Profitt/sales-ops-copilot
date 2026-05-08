# Phase 1 Runbook — Frida + mitmproxy + Procmon live capture

Captures the complete picture of one think-cell workflow:

- **Frida**: in-proc COM/HTTP/IPC syscalls inside POWERPNT.EXE
- **mitmproxy**: every HTTPS body to/from think-cell.com cloud
- **Procmon**: file/registry/process events (especially tcasr.exe spawn)

Run on the Windows VM **interactive desktop session** (not via SSH non-interactive).

## One-time setup

```powershell
# As admin in interactive PowerShell on VM
powershell -ExecutionPolicy Bypass -File \\Mac\Home\code\apps\sales-ops-copilot\scripts\setup_phase1_capture_env.ps1
```

Verify:

```powershell
python -c "import frida; print(frida.__version__)"
python -m mitmproxy.tools.dump --version
```

Procmon: download from sysinternals if not already at `C:\tcw\procmon\Procmon64a.exe`.

## Configure POWERPNT.EXE proxy (one-time per Office install)

Set system proxy to mitmproxy's port:

```powershell
# Set system proxy (admin)
netsh winhttp set proxy 127.0.0.1:8888
# Or per-app via WinINET
$reg = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Internet Settings"
Set-ItemProperty -Path $reg -Name "ProxyEnable" -Value 1
Set-ItemProperty -Path $reg -Name "ProxyServer" -Value "127.0.0.1:8888"
```

## Capture session

### Terminal 1 — mitmproxy

```powershell
mitmdump -p 8888 --set confdir=$env:USERPROFILE\.mitmproxy --set hardump=$env:USERPROFILE\tc_capture\mitm.har -w $env:USERPROFILE\tc_capture\mitm.flow --set anticache=true --set tls_version_client_min=TLS1
```

Filter to think-cell only:

```
~h .*\.think-cell\.com
```

### Terminal 2 — Procmon

```powershell
& "C:\tcw\procmon\Procmon64a.exe" /accepteula /nofilter /backingfile $env:USERPROFILE\tc_capture\procmon.pml /quiet /minimized
```

Then File > Capture (or Ctrl+E to start). Filter (Ctrl+L) to:

- Process Name is POWERPNT.EXE
- Process Name is EXCEL.EXE
- Process Name is tcaddin (image)
- Process Name is tcasr.exe
- Process Name is tcserver.exe
- Process Name is ppttc.exe

### Terminal 3 — Frida

Open PowerPoint first (without the chart — empty deck). Then:

```powershell
$pid = (Get-Process POWERPNT).Id
$traceFile = "$env:USERPROFILE\tc_capture\frida.log"
frida-trace -p $pid `
  -i "tcaddin.dll!*" `
  -i "ole32.dll!IDispatch*" `
  -i "WinHttp*!WinHttp*" `
  -i "kernelbase.dll!Create*Mutex*" `
  -i "kernelbase.dll!Create*FileMapping*" `
  -i "kernelbase.dll!OpenProcess" `
  -i "user32.dll!SendMessageW" `
  -i "user32.dll!PostMessageW" `
  -o $traceFile
```

Frida loads handlers under `$cwd\__handlers__\` — leave them or customize for richer logging.

### Workflow (manual, ~10 min)

While all three are running:

1. **Open a fresh deck**: File > New > Blank
2. **Insert a think-cell chart**: think-cell ribbon > Charts > Bar
   - Capture: ribbon callback → tcaddin internal → tcasr spawn → cloud calls
3. **Use AI feature** (if available): think-cell > AI > Generate
   - Capture: AI auth flow, app.prod.ai.think-cell.com calls, aiauthentication.bin reads
4. **Insert stock image**: think-cell > Insert > Image > Search
   - Capture: pexels/unsplash/freepik proxy calls, /api/v1/search request
5. **Save deck**: File > Save As (transient location)
   - Capture: customXml part write, telemetry post
6. **Close PowerPoint**

Wait 10 sec for telemetry flushes. Then:

- Ctrl+E in Procmon (stop capture)
- Ctrl+C in mitmproxy
- Ctrl+C in frida-trace

### Capture artifacts to ferry

```
$env:USERPROFILE\tc_capture\
├── mitm.flow         (mitmproxy binary log)
├── mitm.har          (HTTP archive — easier to read)
├── procmon.pml       (Procmon binary log)
├── frida.log         (frida-trace text log)
└── __handlers__/     (frida handler scripts)
```

Convert procmon.pml to CSV for easier analysis:

```powershell
& "C:\tcw\procmon\Procmon64a.exe" /OpenLog $env:USERPROFILE\tc_capture\procmon.pml /SaveAs $env:USERPROFILE\tc_capture\procmon.csv /AcceptEula
```

Copy artifacts to Mac:

```powershell
$dest = "\\Mac\Home\code\apps\sales-ops-copilot\state\thinkcell_bridge\phase1_capture\$(Get-Date -Format yyyyMMdd-HHmmss)"
New-Item -ItemType Directory -Path $dest -Force
Copy-Item -Recurse $env:USERPROFILE\tc_capture\* $dest
```

## After capture

Run the analyzer on Mac:

```bash
.venv/bin/python scripts/analyze_phase1_capture.py --capture state/thinkcell_bridge/phase1_capture/<latest>
```

Outputs unified call/HTTP timeline.

## Stop rules

- **Cert trust**: only install mitmproxy CA in personal Windows VM root store, NEVER on a SimCorp-issued machine
- **Capture period**: keep capture sessions short (~10 min). Long captures bloat to GBs and miss the signal
- **Reset proxy after**: `netsh winhttp reset proxy` to remove system proxy when done
- **Don't capture authenticated SimCorp traffic**: this VM is personal think-cell only. Do not log into SimCorp accounts during capture
- **EULA caveat**: this is for interoperability research on a personal license; do not republish or share captures

## Expected yield

- Complete COM call sequence during a chart insertion
- Wire format for: AI auth, telemetry POST, /api/v1/search, stock-image proxies
- tcasr.exe IPC contract (mutex names, shared memory section names, Win32 messages)
- The exact aiauthentication.bin generation flow
- Internal think-cell C++ class methods invoked (via `tcaddin.dll!*` Frida hooks)
