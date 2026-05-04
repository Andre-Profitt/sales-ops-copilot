#requires -Version 5.1
<#
Run a PowerShell command in the interactive Session 1 desktop, from Session 0.

Why: Office automation that involves UI-thread code (think-cell auto-fill,
chart rendering, SaveAs) hangs forever in Session 0. The interactive desktop
is required. This script registers a one-shot scheduled task with the /IT
(interactive) flag, fires it, polls completion, captures output.

Usage from a Session 0 SSH-fired PowerShell:
    & run_in_session1.ps1 -Command "C:\path\to\some-other-script.ps1" `
        -OutputDir "\\Mac\Home\path\to\state\dir"

The task runs as the current user (whoever is logged into Session 1 - assumes
that's the same SSH user). Andre's case: testb04e\test, both Session 0 (SSH)
and Session 1 (console) are him.

Outputs:
    $OutputDir\session1_run.json - verdict
    $OutputDir\session1_run.log  - task stdout+stderr
#>

param(
    [Parameter(Mandatory=$true)]
    [string]$Command,
    [Parameter(Mandatory=$true)]
    [string]$OutputDir,
    [int]$TimeoutSeconds = 300
)

$ErrorActionPreference = "Continue"
$ProgressPreference = "SilentlyContinue"

function Log($m, $c="Cyan") { Write-Host "[s1-runner] $m" -ForegroundColor $c }

# Ensure output dir exists
New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null
$logFile = "$OutputDir\session1_run.log"
$verdictFile = "$OutputDir\session1_run.json"

# Quick session check: who's in Session 1?
$session1User = (qwinsta 2>&1 | Where-Object { $_ -match "^\s*\S+\s+(\S+)\s+1\s+Active" } | ForEach-Object { ($_ -split '\s+')[2] } | Select-Object -First 1)
# Prefer COMPUTERNAME\username on workgroup-joined boxes (USERDOMAIN=WORKGROUP is unresolvable by schtasks)
$currentUser = "$env:COMPUTERNAME\$env:USERNAME"
Log "Current user (Session 0): $currentUser  (USERDOMAIN=$env:USERDOMAIN COMPUTERNAME=$env:COMPUTERNAME)"
Log "Session 1 user: $session1User"
if (-not $session1User) {
    Log "No active Session 1 - task /IT flag will fail (needs logged-on user)" Red
    @{ verdict = "no_session1_user"; current_user = $currentUser } | ConvertTo-Json | Set-Content $verdictFile -Encoding UTF8
    exit 2
}

# Build a wrapper script that captures stdout+stderr
$wrapperPath = "$env:TEMP\s1_wrap_$([guid]::NewGuid().ToString('N')).ps1"
$wrapperTemplate = @'
$ErrorActionPreference = 'Continue'
$ProgressPreference = 'SilentlyContinue'
try {
    & __CMD__ *>&1 | Out-File -LiteralPath '__LOG__' -Encoding UTF8
    $ec = $LASTEXITCODE
} catch {
    "EXCEPTION: $($_.Exception.Message)" | Out-File -LiteralPath '__LOG__' -Encoding UTF8 -Append
    $ec = 1
}
"$ec`n" | Out-File -LiteralPath '__EXITCODE__' -Encoding ASCII
'@
$wrapperContent = $wrapperTemplate.Replace('__CMD__', $Command).Replace('__LOG__', $logFile).Replace('__EXITCODE__', "${logFile}.exitcode")
Set-Content -LiteralPath $wrapperPath -Value $wrapperContent -Encoding UTF8

# Clean up exitcode marker if leftover
Remove-Item -LiteralPath "${logFile}.exitcode" -Force -ErrorAction SilentlyContinue
"" | Out-File -LiteralPath $logFile -Encoding UTF8

$taskName = "TcDemo_S1_$([guid]::NewGuid().ToString('N').Substring(0, 8))"
Log "Task name: $taskName"

# Register the task with /IT (interactive) flag
$taskCmd = "powershell.exe"
$taskArgs = "-NoProfile -ExecutionPolicy Bypass -File `"$wrapperPath`""
$createOut = & schtasks /Create /TN $taskName /TR "$taskCmd $taskArgs" /SC ONCE /SD 01/01/2099 /ST 00:00 /RU $currentUser /RL HIGHEST /IT /F 2>&1 | Out-String
Log "schtasks /Create: $createOut"

if ($LASTEXITCODE -ne 0) {
    Log "schtasks /Create failed" Red
    @{ verdict = "task_create_failed"; output = $createOut } | ConvertTo-Json | Set-Content $verdictFile -Encoding UTF8
    Remove-Item -LiteralPath $wrapperPath -Force -ErrorAction SilentlyContinue
    exit 3
}

# Fire the task
Log "Firing task"
$runOut = & schtasks /Run /TN $taskName 2>&1 | Out-String
Log "schtasks /Run: $runOut"

# Poll for completion
$start = Get-Date
$lastStatus = ""
while ($true) {
    Start-Sleep -Seconds 3
    $elapsed = ((Get-Date) - $start).TotalSeconds
    if ($elapsed -gt $TimeoutSeconds) {
        Log "Timeout after $TimeoutSeconds s - task may still be running" Yellow
        break
    }
    $status = & schtasks /Query /TN $taskName /FO LIST 2>&1 | Where-Object { $_ -match "Status:" } | ForEach-Object { ($_ -split ":\s+", 2)[1].Trim() }
    if ($status -ne $lastStatus) {
        Log "Status: $status (elapsed ${elapsed}s)"
        $lastStatus = $status
    }
    if ($status -eq "Ready" -and (Test-Path -LiteralPath "${logFile}.exitcode")) {
        Log "Task finished" Green
        break
    }
}

# Read exit code if available
$exitCode = $null
if (Test-Path -LiteralPath "${logFile}.exitcode") {
    $exitCode = (Get-Content -LiteralPath "${logFile}.exitcode" -ErrorAction SilentlyContinue).Trim() -as [int]
}

# Cleanup task
& schtasks /Delete /TN $taskName /F 2>&1 | Out-Null
Remove-Item -LiteralPath $wrapperPath -Force -ErrorAction SilentlyContinue

# Final verdict
$logTail = if (Test-Path -LiteralPath $logFile) { (Get-Content -LiteralPath $logFile -Tail 30 -ErrorAction SilentlyContinue) -join "`n" } else { "" }
$verdict = [ordered]@{
    timestamp_utc   = (Get-Date).ToUniversalTime().ToString("o")
    task_name       = $taskName
    command         = $Command
    elapsed_seconds = ((Get-Date) - $start).TotalSeconds
    timed_out       = ($elapsed -gt $TimeoutSeconds)
    exit_code       = $exitCode
    log_file        = $logFile
    log_tail        = $logTail
    verdict         = if ($exitCode -eq 0) { "success" } elseif ($null -eq $exitCode) { "incomplete" } else { "task_failed" }
}
$verdict | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $verdictFile -Encoding UTF8
Log "Wrote $verdictFile"
Log "Verdict: $($verdict.verdict)"

if ($exitCode -ne 0) { exit $exitCode }
