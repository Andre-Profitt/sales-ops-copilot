#requires -Version 5.1
<#
Phase 12 capture - STOP.
Reset proxy, kill mitmdump + frida-trace, restore aiauthentication.bin.
#>

$ProgressPreference = "SilentlyContinue"
function Log($m, $c="Cyan") { Write-Host "[stop] $m" -ForegroundColor $c }

$state = "$env:USERPROFILE\tc_auth\.current_session"
if (-not (Test-Path -LiteralPath $state)) {
    Log "No active capture session marker at $state" Red
    exit 1
}
$sess = Get-Content -LiteralPath $state | ConvertFrom-Json
$cap = $sess.capture_dir
Log "Capture dir: $cap"

# 1. Reset system proxy
& netsh winhttp reset proxy | Out-Null
$reg = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Internet Settings"
Set-ItemProperty -Path $reg -Name "ProxyEnable" -Value 0
Log "Proxy reset" Green

# 2. Stop mitmdump
$mitmPidFile = "$cap\mitm.pid"
if (Test-Path -LiteralPath $mitmPidFile) {
    $mitmPid = [int](Get-Content -LiteralPath $mitmPidFile)
    try {
        Stop-Process -Id $mitmPid -Force -ErrorAction Stop
        Log "Stopped mitmdump pid=$mitmPid" Green
    } catch {
        Log "mitmdump pid=$mitmPid already gone or failed: $($_.Exception.Message)" Yellow
    }
}

# 3. Stop frida-trace
$fridaPidFile = "$cap\frida.pid"
if (Test-Path -LiteralPath $fridaPidFile) {
    $fridaPid = [int](Get-Content -LiteralPath $fridaPidFile)
    try {
        Stop-Process -Id $fridaPid -Force -ErrorAction Stop
        Log "Stopped frida-trace pid=$fridaPid" Green
    } catch {
        Log "frida-trace pid=$fridaPid already gone or failed: $($_.Exception.Message)" Yellow
    }
}
Start-Sleep -Seconds 2

# 4. Restore aiauthentication.bin if backup exists - prefer the freshly captured one if both exist
$tc = "$env:APPDATA\think-cell"
$aiauth = "$tc\aiauthentication.bin"
$bak = "$tc\aiauthentication.bin.bak"
if (Test-Path -LiteralPath $aiauth) {
    Log "aiauth exists post-capture (size $((Get-Item $aiauth).Length))" Green
    # Save a copy into the capture dir
    Copy-Item -LiteralPath $aiauth -Destination "$cap\aiauthentication.bin.captured" -Force
    Log "Saved post-capture token snapshot to $cap\aiauthentication.bin.captured" Green
} elseif (Test-Path -LiteralPath $bak) {
    Move-Item -LiteralPath $bak -Destination $aiauth -Force
    Log "Restored aiauthentication.bin from backup" Green
} else {
    Log "No aiauth and no backup - VM will need fresh license auth on next think-cell launch" Yellow
}

# 5. Confirm artifacts
Log "" Cyan
Log "Capture artifacts in $cap" Cyan
Get-ChildItem -LiteralPath $cap -Force | Select-Object Name, Length | Format-Table -AutoSize | Out-String | Write-Host

# 6. Suggest ferry to Mac
Log "" Cyan
Log "To ferry to Mac, in this PowerShell:" Yellow
Log "  `$dest = '\\Mac\Home\code\apps\sales-ops-copilot\state\thinkcell_bridge\phase12_auth_capture\$($sess.ts)'" Yellow
Log "  New-Item -ItemType Directory -Path `$dest -Force | Out-Null" Yellow
Log "  Copy-Item -LiteralPath '$cap\*' `$dest -Recurse -Force" Yellow

# 7. Clear session marker
Remove-Item -LiteralPath $state -Force -ErrorAction SilentlyContinue
