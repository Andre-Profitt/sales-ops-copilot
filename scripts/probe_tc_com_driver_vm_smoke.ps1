#requires -Version 5.1
<#
VM-side smoke for libs/tc_com_driver against a running PowerPoint+think-cell.

Pre-conditions (all on Andre's interactive desktop session BEFORE running):
- PowerPoint open on the VM
- think-cell ribbon visible (add-in active)
- An empty .pptx is fine; no specific deck content needed

What this does:
1. Locate the x64 Python (`Python313-amd64`)
2. Ensure pywin32 + pytest are installed under --user
3. Install libs/tc_com_driver in editable mode from the UNC path
4. Run pytest against tests/test_smoke_vm.py
5. Emit JSON result to -OutputPath

Emits structured verdict:
- python_ok / python_error
- pywin32_ok / pywin32_error
- tc_com_driver_install_ok / install_error
- pytest_ran / pytest_passed / pytest_failed
- powerpoint_pid (or null)
- thinkcell_addin_found / addin_progid
#>

param(
    [Parameter(Mandatory=$true)]
    [string]$OutputPath
)

$ErrorActionPreference = "Continue"
$ProgressPreference = "SilentlyContinue"

function Log($m, $c="Cyan") { Write-Host "[tc-com-smoke] $m" -ForegroundColor $c }

$state = [ordered]@{
    timestamp_utc = (Get-Date).ToUniversalTime().ToString("o")
    host          = $env:COMPUTERNAME
    python_exe    = $null
    python_ok     = $false
    pywin32_ok    = $false
    pywin32_version = $null
    tc_com_driver_install_ok = $false
    powerpoint_pid = $null
    powerpoint_running = $false
    thinkcell_addin_found = $false
    thinkcell_addin_progid = $null
    thinkcell_addin_description = $null
    pytest_ran = $false
    pytest_passed = $null
    pytest_failed = $null
    pytest_stdout_tail = $null
    pytest_stderr_tail = $null
    overall_verdict = "unknown"
}

# 1. Locate x64 Python
$pyExe = "$env:LOCALAPPDATA\Programs\Python\Python313-amd64\python.exe"
if (-not (Test-Path -LiteralPath $pyExe)) {
    Log "x64 Python missing at $pyExe" Red
    $state.overall_verdict = "python_missing"
    $state | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $OutputPath -Encoding UTF8
    exit 2
}
$state.python_exe = $pyExe
$state.python_ok = $true
Log "Python: $((& $pyExe --version 2>&1).ToString().Trim())"

# 2. Install pywin32 + pytest if needed
Log "Ensuring pywin32 + pytest are installed (--user)"
$pipOut = & $pyExe -m pip install --user --upgrade --no-warn-script-location pywin32 pytest 2>&1 | Out-String
$pipExit = $LASTEXITCODE
if ($pipExit -ne 0) {
    Log "pip install failed (exit=$pipExit)" Red
    $state.pytest_stdout_tail = ($pipOut -split "`n" | Select-Object -Last 8) -join "`n"
    $state.overall_verdict = "pywin32_install_failed"
    $state | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $OutputPath -Encoding UTF8
    exit 3
}
$pywin32Ver = (& $pyExe -c "import win32com; print(win32com.__file__)" 2>&1 | Out-String).Trim()
if ($LASTEXITCODE -eq 0) {
    $state.pywin32_ok = $true
    $state.pywin32_version = $pywin32Ver
    Log "pywin32 ok: $pywin32Ver" Green
} else {
    Log "pywin32 import failed: $pywin32Ver" Red
    $state.overall_verdict = "pywin32_import_failed"
    $state | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $OutputPath -Encoding UTF8
    exit 4
}

# 3. Install tc_com_driver editable from UNC path
$libRoot = "\\Mac\Home\code\apps\sales-ops-copilot\libs\tc_com_driver"
if (-not (Test-Path -LiteralPath $libRoot)) {
    Log "tc_com_driver not found at $libRoot" Red
    $state.overall_verdict = "lib_path_missing"
    $state | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $OutputPath -Encoding UTF8
    exit 5
}
Log "Installing tc_com_driver editable from $libRoot"
$installOut = & $pyExe -m pip install --user --no-warn-script-location -e $libRoot 2>&1 | Out-String
if ($LASTEXITCODE -ne 0) {
    Log "tc_com_driver install failed" Red
    $state.pytest_stderr_tail = ($installOut -split "`n" | Select-Object -Last 10) -join "`n"
    $state.overall_verdict = "lib_install_failed"
    $state | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $OutputPath -Encoding UTF8
    exit 6
}
$state.tc_com_driver_install_ok = $true
Log "tc_com_driver installed" Green

# 4. Detect POWERPNT + think-cell add-in (best-effort, won't block)
$pp = Get-Process POWERPNT -ErrorAction SilentlyContinue | Select-Object -First 1
if ($pp) {
    $state.powerpoint_pid = $pp.Id
    $state.powerpoint_running = $true
    Log "POWERPNT pid: $($pp.Id)"

    # Try to enumerate COMAddIns to confirm think-cell is loaded (read-only)
    $detectScript = @"
import sys
try:
    import win32com.client as wc
    app = wc.GetActiveObject("PowerPoint.Application")
    addins = app.COMAddIns
    for i in range(addins.Count):
        a = addins.Item(i+1)
        desc = (a.Description or "").lower()
        progid = (a.ProgId or "").lower()
        if "think-cell" in desc or "think-cell" in progid or "thinkcell" in progid:
            print(f"FOUND|{a.ProgId}|{a.Description}|{a.Connect}")
            sys.exit(0)
    print("NOT_FOUND")
except Exception as e:
    print(f"ERROR|{type(e).__name__}|{e}")
"@
    $detectFile = "$env:TEMP\tc_detect_$([guid]::NewGuid().ToString('N')).py"
    Set-Content -LiteralPath $detectFile -Value $detectScript -Encoding UTF8
    $detectOut = (& $pyExe $detectFile 2>&1 | Out-String).Trim()
    Remove-Item -LiteralPath $detectFile -Force -ErrorAction SilentlyContinue
    Log "addin detect: $detectOut"
    if ($detectOut -match "^FOUND\|([^|]+)\|([^|]*)\|") {
        $state.thinkcell_addin_found = $true
        $state.thinkcell_addin_progid = $matches[1]
        $state.thinkcell_addin_description = $matches[2]
    }
} else {
    Log "POWERPNT not running - VM smoke will skip with that marker" Yellow
}

# 5. Run pytest
$testFile = "$libRoot\tests\test_smoke_vm.py"
if (-not (Test-Path -LiteralPath $testFile)) {
    Log "test_smoke_vm.py not found at $testFile" Red
    $state.overall_verdict = "test_file_missing"
    $state | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $OutputPath -Encoding UTF8
    exit 7
}

Log "Running pytest"
$pytestOut = & $pyExe -m pytest $testFile -v --tb=short 2>&1 | Out-String
$pytestExit = $LASTEXITCODE
$state.pytest_ran = $true
$state.pytest_stdout_tail = ($pytestOut -split "`n" | Select-Object -Last 30) -join "`n"

# Parse pass/fail counts from output
if ($pytestOut -match "(\d+)\s+passed") { $state.pytest_passed = [int]$matches[1] }
if ($pytestOut -match "(\d+)\s+failed") { $state.pytest_failed = [int]$matches[1] }

if ($pytestExit -eq 0) {
    $state.overall_verdict = "smoke_passed"
    Log "smoke passed" Green
} elseif ($pytestExit -eq 5) {
    # pytest exit 5 = no tests collected (all skipped)
    $state.overall_verdict = "all_skipped"
    Log "all tests skipped (pytest exit 5)" Yellow
} else {
    $state.overall_verdict = "smoke_failed"
    Log "smoke failed (pytest exit=$pytestExit)" Red
}

$state | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $OutputPath -Encoding UTF8
Log "wrote $OutputPath"
