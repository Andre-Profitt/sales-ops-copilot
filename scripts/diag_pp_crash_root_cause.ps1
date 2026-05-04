<#
Determine whether the POWERPNT crash is:
  (A) Microsoft Office 19929 regression --bug exists independent of our actions
  (B) Damage we caused via Phase 12 invasive ops (file deletes, registry edits)
  (C) Both --regression + we made it worse

Diagnostics:
  1. Office update timeline: when did 19929 land on this VM
  2. Crash event timeline: when was the FIRST POWERPNT crash
  3. Read full WER Report.wer files (have stack frames + parameters)
  4. Check for actual .dmp files (Windows Error Reporting LocalDumps)
  5. Check if TCDiag.exe is installed (think-cell's own isolation tool)
  6. Look for evidence of healthy PP usage between 19929 install and crashes
#>
$ErrorActionPreference = "Continue"

Write-Output "===================================================================="
Write-Output " POWERPNT crash root-cause diagnostic"
Write-Output "===================================================================="
Write-Output ""

# ============================================================
# 1. Office build install timeline
# ============================================================
Write-Output "=== 1. Office update / install timeline ==="
$updateLog = "$env:LocalAppData\..\..\..\Program Files\Common Files\Microsoft Shared\ClickToRun\Updates\detect.log"
$detectLog = "C:\Program Files\Common Files\microsoft shared\ClickToRun\Logs"
if (Test-Path $detectLog) {
    Get-ChildItem $detectLog -ErrorAction SilentlyContinue | Sort-Object LastWriteTime -Desc | Select-Object -First 5 | ForEach-Object {
        Write-Output "  $($_.Name) ($($_.Length) bytes, last $($_.LastWriteTime))"
    }
}

# Check current installed version
$reg = "HKLM:\SOFTWARE\Microsoft\Office\ClickToRun\Configuration"
if (Test-Path $reg) {
    $cfg = Get-ItemProperty $reg -ErrorAction SilentlyContinue
    Write-Output "  ClickToRun ProductReleaseIds: $($cfg.ProductReleaseIds)"
    Write-Output "  VersionToReport: $($cfg.VersionToReport)"
    Write-Output "  PreviousVersionToReport: $($cfg.PreviousVersionToReport)"
    Write-Output "  CDNBaseUrl: $($cfg.CDNBaseUrl)"
    Write-Output "  ServicingBranch: $($cfg.UpdateChannel)"
    Write-Output "  CurrentBranch: $($cfg.CurrentBranch)"
}

# Check setup.exe / Office binary modification times (a proxy for install date)
$ppExe = "C:\Program Files\Microsoft Office\root\Office16\POWERPNT.EXE"
$msoDll = "C:\Program Files\Common Files\Microsoft Shared\Office16\mso20win32client.dll"
foreach ($p in @($ppExe, $msoDll)) {
    if (Test-Path $p) {
        $f = Get-Item $p
        Write-Output "  $($f.Name): version=$($f.VersionInfo.FileVersion) modified=$($f.LastWriteTime) created=$($f.CreationTime)"
    }
}

Write-Output ""
# ============================================================
# 2. Crash event timeline (full history)
# ============================================================
Write-Output "=== 2. POWERPNT crash event timeline ==="
$crashes = Get-EventLog -LogName Application -After (Get-Date).AddDays(-30) -EntryType Error -ErrorAction SilentlyContinue |
    Where-Object { $_.Message -match "POWERPNT|powerp" -and $_.Source -in @("Application Error", "Microsoft Office 16", ".NET Runtime", "Windows Error Reporting") }

Write-Output "  Total crashes in last 30 days: $($crashes.Count)"
if ($crashes.Count -gt 0) {
    $first = $crashes | Sort-Object TimeGenerated | Select-Object -First 1
    $last  = $crashes | Sort-Object TimeGenerated -Desc | Select-Object -First 1
    Write-Output "  FIRST crash: $($first.TimeGenerated) [$($first.Source) #$($first.EventID)]"
    Write-Output "  LAST  crash: $($last.TimeGenerated) [$($last.Source) #$($last.EventID)]"
    Write-Output ""
    Write-Output "  All crash timestamps:"
    $crashes | Sort-Object TimeGenerated | ForEach-Object {
        Write-Output "    $($_.TimeGenerated) | $($_.Source) #$($_.EventID)"
    }
}

Write-Output ""
# ============================================================
# 3. WER Report.wer files (have rich crash data + stack)
# ============================================================
Write-Output "=== 3. WER Report.wer files ==="
$werRoot = "$env:LocalAppData\Microsoft\Windows\WER"
if (Test-Path $werRoot) {
    $reports = Get-ChildItem -LiteralPath $werRoot -Recurse -Filter "Report.wer" -ErrorAction SilentlyContinue |
        Where-Object {
            $content = Get-Content $_.FullName -ErrorAction SilentlyContinue -Raw
            $content -match "POWERPNT" -or $content -match "powerp"
        } |
        Sort-Object LastWriteTime -Desc | Select-Object -First 5

    Write-Output "  Found $($reports.Count) POWERPNT WER reports"
    foreach ($r in $reports) {
        Write-Output ""
        Write-Output "  --- $($r.FullName) ---"
        $content = Get-Content $r.FullName -ErrorAction SilentlyContinue
        # Show key fields: AppName, AppVersion, ModName, ModVersion, Exception, FaultModuleOffset
        $content | Where-Object { $_ -match "^(AppName|AppVersion|ModName|ModVersion|Exception|FaultMod|EventTime|Sig\[|DynamicSig\[|Param)" } | ForEach-Object {
            Write-Output "    $_"
        }
    }
}

Write-Output ""
# ============================================================
# 4. .dmp files (full crash dumps if LocalDumps enabled)
# ============================================================
Write-Output "=== 4. .dmp files ==="
$dumpRoots = @(
    "$env:LocalAppData\CrashDumps",
    "C:\ProgramData\Microsoft\Windows\WER\ReportArchive",
    "C:\ProgramData\Microsoft\Windows\WER\ReportQueue"
)
foreach ($dr in $dumpRoots) {
    if (Test-Path $dr) {
        $dmps = Get-ChildItem -LiteralPath $dr -Recurse -Filter "*.dmp" -ErrorAction SilentlyContinue |
            Where-Object { $_.Name -match "POWERPNT|powerp" }
        Write-Output "  $dr : $($dmps.Count) POWERPNT dumps"
        $dmps | Select-Object -First 3 | ForEach-Object {
            Write-Output "    $($_.FullName) ($($_.Length) bytes, $($_.LastWriteTime))"
        }
    }
}

Write-Output ""
# ============================================================
# 5. TCDiag.exe (think-cell isolation tool)
# ============================================================
Write-Output "=== 5. think-cell TCDiag.exe ==="
$tcDiag = @(
    "C:\Program Files (x86)\think-cell\TCDiag.exe",
    "C:\Program Files\think-cell\TCDiag.exe",
    "C:\Program Files (x86)\think-cell\tcdiag.exe"
) | Where-Object { Test-Path $_ } | Select-Object -First 1

if ($tcDiag) {
    Write-Output "  FOUND: $tcDiag"
    Write-Output "  (Run interactively with PowerPoint open to binary-search add-in conflicts)"
} else {
    Write-Output "  NOT FOUND in standard paths"
    # Search more broadly
    Get-ChildItem "C:\Program Files (x86)\think-cell" -Filter "*.exe" -ErrorAction SilentlyContinue | ForEach-Object {
        Write-Output "    available: $($_.FullName)"
    }
}

Write-Output ""
# ============================================================
# 6. Was PP healthy between 19929 install and crashes?
# ============================================================
Write-Output "=== 6. PP usage between 19929 install and first crash ==="
# Look for evidence of PP usage: recent files registry, taskbar usage, logs
$mru = "HKCU:\Software\Microsoft\Office\16.0\PowerPoint\User MRU"
if (Test-Path $mru) {
    Get-ChildItem $mru -ErrorAction SilentlyContinue | ForEach-Object {
        $kid = $_.Name -replace ".*\\", ""
        Write-Output "  Identity: $kid"
        $items = Get-ChildItem "$($_.PSPath)\File MRU" -ErrorAction SilentlyContinue
        Write-Output "    File MRU items: $($items.Count)"
    }
}

# PP startup events from Office 16 source
$startups = Get-EventLog -LogName Application -After (Get-Date).AddDays(-30) -ErrorAction SilentlyContinue |
    Where-Object { $_.Message -match "POWERPNT|powerp" -and $_.Source -eq "Microsoft Office 16" -and $_.EntryType -ne "Error" } |
    Select-Object -First 10
Write-Output "  Non-error PP-related events (recent): $($startups.Count)"

Write-Output ""
Write-Output "===================================================================="
Write-Output " ROOT CAUSE ASSESSMENT (read above + decide)"
Write-Output "===================================================================="
