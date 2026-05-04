$ProgressPreference = "SilentlyContinue"
$pyExe = "$env:LOCALAPPDATA\Programs\Python\Python313-amd64\python.exe"
$userBase = (& $pyExe -c "import site; print(site.USER_BASE)" 2>&1 | Out-String).Trim()

Write-Host "=== USER_BASE = $userBase ==="
$mitmdumpExe = "$userBase\Python313\Scripts\mitmdump.exe"
$mitmwebExe  = "$userBase\Python313\Scripts\mitmweb.exe"

Write-Host "=== Scripts dir contents ==="
$scriptsDir = "$userBase\Python313\Scripts"
if (Test-Path -LiteralPath $scriptsDir) {
    Get-ChildItem -LiteralPath $scriptsDir -Filter "mitm*" | Select-Object Name,Length | Format-Table -AutoSize | Out-String | Write-Host
} else {
    Write-Host "MISSING: $scriptsDir"
    # Try Roaming
    $alt = "$env:APPDATA\Python\Python313\Scripts"
    if (Test-Path -LiteralPath $alt) {
        Write-Host "FOUND ALT: $alt"
        Get-ChildItem -LiteralPath $alt -Filter "mitm*" | Select-Object Name,Length | Format-Table -AutoSize | Out-String | Write-Host
        $mitmdumpExe = "$alt\mitmdump.exe"
    }
}

Write-Host "=== mitmdump.exe --version (foreground) ==="
if (Test-Path -LiteralPath $mitmdumpExe) {
    & $mitmdumpExe --version 2>&1 | ForEach-Object { Write-Host "  $_" }
} else {
    Write-Host "  mitmdump.exe not found at $mitmdumpExe"
}

Write-Host "=== Try direct python -c invocation with import error trapping ==="
$code = @"
import sys, traceback
try:
    from mitmproxy.tools.main import mitmdump
    print("MITM_IMPORT_OK")
except Exception:
    traceback.print_exc()
    sys.exit(1)
"@
$tmpPy = "$env:TEMP\mitm_probe.py"
Set-Content -LiteralPath $tmpPy -Value $code -Encoding ASCII
& $pyExe $tmpPy 2>&1 | ForEach-Object { Write-Host "  $_" }
Remove-Item $tmpPy -Force -ErrorAction SilentlyContinue

Write-Host "=== Direct mitmdump --version via wrapper ==="
if (Test-Path -LiteralPath $mitmdumpExe) {
    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = $mitmdumpExe
    $psi.Arguments = "--version"
    $psi.UseShellExecute = $false
    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError = $true
    $proc = [System.Diagnostics.Process]::Start($psi)
    $proc.WaitForExit(15000)
    Write-Host "  exit_code: $($proc.ExitCode)"
    Write-Host "  stdout:"
    $proc.StandardOutput.ReadToEnd() -split "`n" | ForEach-Object { Write-Host "    $_" }
    Write-Host "  stderr:"
    $proc.StandardError.ReadToEnd() -split "`n" | ForEach-Object { Write-Host "    $_" }
}
