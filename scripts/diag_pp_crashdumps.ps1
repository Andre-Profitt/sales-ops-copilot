<#
Investigate the actual PowerPoint crashes:
  - Look for crash dumps in standard locations
  - Get full event-log entries (not just truncated views)
  - Check WER (Windows Error Reporting) reports
  - Check for detailed crash signature info
#>
$ErrorActionPreference = "Continue"

Write-Output "=== POWERPNT crash dumps ==="
$dumpDirs = @(
    "$env:LocalAppData\CrashDumps",
    "$env:LocalAppData\Microsoft\Windows\WER\ReportArchive",
    "$env:LocalAppData\Microsoft\Windows\WER\ReportQueue"
)
foreach ($d in $dumpDirs) {
    if (Test-Path -LiteralPath $d) {
        Write-Output "  $d :"
        Get-ChildItem -LiteralPath $d -Recurse -ErrorAction SilentlyContinue |
            Where-Object { $_.Name -match "POWERPNT|powerp" } |
            Sort-Object LastWriteTime -Descending |
            Select-Object -First 10 |
            ForEach-Object { Write-Output "    $($_.FullName) ($($_.Length) bytes, $($_.LastWriteTime))" }
    } else {
        Write-Output "  $d : NOT EXIST"
    }
}

Write-Output ""
Write-Output "=== Latest WER report data ==="
$werDirs = Get-ChildItem -Path "$env:LocalAppData\Microsoft\Windows\WER" -Directory -ErrorAction SilentlyContinue
foreach ($wd in $werDirs) {
    Get-ChildItem -LiteralPath $wd.FullName -Directory -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -match "POWERPNT|AppCrash" -or (Get-ChildItem $_.FullName -Filter "*POWERPNT*" -ErrorAction SilentlyContinue) } |
        Sort-Object LastWriteTime -Descending |
        Select-Object -First 3 |
        ForEach-Object {
            Write-Output "  --- $($_.FullName) ---"
            Get-ChildItem -LiteralPath $_.FullName -ErrorAction SilentlyContinue | ForEach-Object {
                Write-Output "    $($_.Name) ($($_.Length) bytes)"
            }
            # Read Report.wer if exists
            $rep = Join-Path $_.FullName "Report.wer"
            if (Test-Path -LiteralPath $rep) {
                Write-Output "    --- Report.wer contents ---"
                Get-Content -LiteralPath $rep -ErrorAction SilentlyContinue | Select-Object -First 60 | ForEach-Object { Write-Output "      $_" }
            }
        }
}

Write-Output ""
Write-Output "=== Enable LocalDumps for POWERPNT (writes .dmp to LocalAppData\CrashDumps next time) ==="
$ld = "HKLM:\SOFTWARE\Microsoft\Windows\Windows Error Reporting\LocalDumps\POWERPNT.exe"
try {
    New-Item -Path $ld -Force -ErrorAction Stop | Out-Null
    New-ItemProperty -Path $ld -Name "DumpType" -Value 2 -PropertyType DWord -Force | Out-Null  # full dump
    New-ItemProperty -Path $ld -Name "DumpCount" -Value 5 -PropertyType DWord -Force | Out-Null
    New-ItemProperty -Path $ld -Name "DumpFolder" -Value "$env:LocalAppData\CrashDumps" -PropertyType ExpandString -Force | Out-Null
    Write-Output "  ENABLED (DumpType=2 full, max 5 dumps)"
} catch {
    Write-Output "  failed (need admin?): $($_.Exception.Message)"
    # Try HKCU fallback
    $ldcu = "HKCU:\SOFTWARE\Microsoft\Windows\Windows Error Reporting\LocalDumps\POWERPNT.exe"
    try {
        New-Item -Path $ldcu -Force -ErrorAction Stop | Out-Null
        New-ItemProperty -Path $ldcu -Name "DumpType" -Value 2 -PropertyType DWord -Force | Out-Null
        Write-Output "  HKCU fallback enabled"
    } catch {
        Write-Output "  HKCU also failed: $($_.Exception.Message)"
    }
}

Write-Output ""
Write-Output "=== mso20win32client.dll info ==="
$dll = "C:\Program Files\Common Files\Microsoft Shared\Office16\mso20win32client.dll"
if (Test-Path -LiteralPath $dll) {
    $f = Get-Item -LiteralPath $dll
    Write-Output "  size: $($f.Length)"
    Write-Output "  version: $((Get-Item $dll).VersionInfo.FileVersion)"
    Write-Output "  product: $((Get-Item $dll).VersionInfo.ProductName)"
    Write-Output "  description: $((Get-Item $dll).VersionInfo.FileDescription)"
    Write-Output "  company: $((Get-Item $dll).VersionInfo.CompanyName)"
}

Write-Output ""
Write-Output "=== aitrx.dll info ==="
$ait = "C:\Program Files\Common Files\Microsoft Shared\Office16\AI\aitrx.dll"
if (Test-Path -LiteralPath $ait) {
    $f = Get-Item -LiteralPath $ait
    Write-Output "  size: $($f.Length)"
    Write-Output "  version: $((Get-Item $ait).VersionInfo.FileVersion)"
    Write-Output "  product: $((Get-Item $ait).VersionInfo.ProductName)"
    Write-Output "  description: $((Get-Item $ait).VersionInfo.FileDescription)"
}

Write-Output ""
Write-Output "=== Office Connected Experience setting ==="
$cs = "HKCU:\Software\Microsoft\Office\16.0\Common\ConnectedServices"
if (Test-Path $cs) {
    Get-ItemProperty $cs | Format-List
}

Write-Output ""
Write-Output "=== Office Identity registry shape ==="
$id = "HKCU:\Software\Microsoft\Office\16.0\Common\Identity"
if (Test-Path $id) {
    Get-ChildItem $id -Recurse -ErrorAction SilentlyContinue | Select-Object -First 20 | ForEach-Object { Write-Output "  $($_.Name)" }
}
