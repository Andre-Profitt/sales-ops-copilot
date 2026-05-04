$ErrorActionPreference = "Continue"
$ProgressPreference = "SilentlyContinue"

# Locate POWERPNT.exe (Office 365 default install)
$candidates = @(
    "C:\Program Files\Microsoft Office\root\Office16\POWERPNT.EXE",
    "C:\Program Files (x86)\Microsoft Office\root\Office16\POWERPNT.EXE",
    "C:\Program Files\Microsoft Office\Office16\POWERPNT.EXE"
)
$pp = $candidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
if (-not $pp) {
    Write-Host "POWERPNT.EXE not found in standard paths" -ForegroundColor Red
    exit 1
}
Write-Host "Launching: $pp"

# Already running? skip
$existing = Get-Process POWERPNT -ErrorAction SilentlyContinue | Select-Object -First 1
if ($existing) {
    Write-Host "Already running (pid=$($existing.Id))"
    exit 0
}

# Launch headless-ish (no specific deck; default empty deck)
$proc = Start-Process -FilePath $pp -PassThru
Write-Host "Launched POWERPNT pid=$($proc.Id)"

# Wait for COM ROT registration
Start-Sleep -Seconds 8

# Verify COM-accessible from same session
$pyExe = "$env:LOCALAPPDATA\Programs\Python\Python313-amd64\python.exe"
$probe = @"
try:
    import win32com.client as wc
    app = wc.GetActiveObject("PowerPoint.Application")
    print("COM_OK", app.Name, app.Version)
    # Walk add-ins
    for i in range(app.COMAddIns.Count):
        a = app.COMAddIns.Item(i+1)
        d = (a.Description or "")
        p = (a.ProgId or "")
        c = a.Connect
        marker = "TC" if "think-cell" in d.lower() or "thinkcell" in p.lower() else "  "
        print(f"  [{marker}] {a.ProgId!r}  {a.Description!r}  Connect={c}")
except Exception as e:
    print(f"COM_ERR {type(e).__name__}: {e}")
"@
$tmp = "$env:TEMP\tc_probe_$([guid]::NewGuid().ToString('N')).py"
Set-Content -LiteralPath $tmp -Value $probe -Encoding UTF8
& $pyExe $tmp 2>&1
Remove-Item -LiteralPath $tmp -Force -ErrorAction SilentlyContinue
