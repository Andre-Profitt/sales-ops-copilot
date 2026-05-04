$ErrorActionPreference = "Continue"

# Survey PowerPoint state
Write-Host "=== POWERPNT processes ==="
Get-Process POWERPNT -ErrorAction SilentlyContinue | Select-Object Id, SessionId, MainWindowTitle, ProcessName | Format-Table -AutoSize | Out-String | Write-Host

$pyExe = "$env:LOCALAPPDATA\Programs\Python\Python313-amd64\python.exe"

# Try Dispatch (creates new instance) instead of GetActiveObject (looks up ROT)
$probe = @"
import win32com.client as wc
import pythoncom

# Method 1: Dispatch — auto-creates if needed
try:
    app = wc.Dispatch("PowerPoint.Application")
    print(f"DISPATCH_OK Name={app.Name!r} Version={app.Version!r} Visible={app.Visible}")
    print(f"COMAddIns count: {app.COMAddIns.Count}")
    for i in range(app.COMAddIns.Count):
        a = app.COMAddIns.Item(i+1)
        d = (a.Description or "")
        p = (a.ProgId or "")
        c = a.Connect
        marker = "TC" if "think-cell" in d.lower() or "thinkcell" in p.lower() else "  "
        print(f"  [{marker}] {a.ProgId!r}  {a.Description!r}  Connect={c}")
except Exception as e:
    print(f"DISPATCH_ERR {type(e).__name__}: {e}")
"@
$tmp = "$env:TEMP\tc_probe_$([guid]::NewGuid().ToString('N')).py"
Set-Content -LiteralPath $tmp -Value $probe -Encoding UTF8
Write-Host "=== Trying Dispatch ==="
& $pyExe $tmp 2>&1
Remove-Item -LiteralPath $tmp -Force -ErrorAction SilentlyContinue

Write-Host ""
Write-Host "=== POWERPNT after probe ==="
Get-Process POWERPNT -ErrorAction SilentlyContinue | Select-Object Id, SessionId | Format-Table -AutoSize | Out-String | Write-Host
