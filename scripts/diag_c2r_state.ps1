<# Find the actual ClickToRun service logs + check version availability. #>
$ErrorActionPreference = "Continue"

Write-Output "=== ClickToRun service state ==="
Get-Service -Name "ClickToRunSvc" -ErrorAction SilentlyContinue | Format-List Name, Status, StartType
Get-Service -Name "OfficeClickToRun*" -ErrorAction SilentlyContinue | Format-List Name, Status

Write-Output "=== ClickToRun log paths ==="
$paths = @(
    "C:\ProgramData\Microsoft\ClickToRun\Logs",
    "C:\ProgramData\Microsoft\OfficeSoftwareProtectionPlatform",
    "$env:LocalAppData\Microsoft\Office\16.0\Logs",
    "$env:Temp\OneDriveStandaloneSetup",
    "C:\Windows\Temp"
)
foreach ($p in $paths) {
    if (Test-Path $p) {
        $logs = Get-ChildItem $p -Filter "*.log" -ErrorAction SilentlyContinue | Sort-Object LastWriteTime -Desc | Select-Object -First 3
        if ($logs) {
            Write-Output "  $p :"
            $logs | ForEach-Object {
                Write-Output "    $($_.Name) ($([int]($_.Length/1KB))KB, $($_.LastWriteTime))"
            }
        }
    }
}

Write-Output ""
Write-Output "=== Most recent C2R*.log content ==="
$c2rLogs = @()
foreach ($p in $paths) {
    if (Test-Path $p) {
        $c2rLogs += Get-ChildItem $p -Filter "*C2R*.log" -ErrorAction SilentlyContinue
        $c2rLogs += Get-ChildItem $p -Filter "*ClickToRun*.log" -ErrorAction SilentlyContinue
        $c2rLogs += Get-ChildItem $p -Filter "*Update*.log" -ErrorAction SilentlyContinue
    }
}
$latest = $c2rLogs | Sort-Object LastWriteTime -Desc | Select-Object -First 1
if ($latest) {
    Write-Output "  $($latest.FullName) ($($latest.LastWriteTime))"
    Write-Output "  --- last 30 lines ---"
    Get-Content $latest.FullName -Tail 30 -ErrorAction SilentlyContinue | ForEach-Object { Write-Output "    $_" }
}

Write-Output ""
Write-Output "=== Test: is 19822.20182 still on the CDN? ==="
$cdnBase = "http://officecdn.microsoft.com/pr/492350f6-3a01-4f97-b9c0-c7c6ddf67d60"
$testUrl = "$cdnBase/Office/Data/16.0.19822.20182/v32.cab"
try {
    $r = Invoke-WebRequest $testUrl -Method Head -UseBasicParsing -ErrorAction Stop -TimeoutSec 10
    Write-Output "  $testUrl -> $($r.StatusCode)"
} catch {
    Write-Output "  $testUrl -> $($_.Exception.Message)"
}
$testUrl2 = "$cdnBase/Office/Data/16.0.19822.20182/i640.cab"
try {
    $r = Invoke-WebRequest $testUrl2 -Method Head -UseBasicParsing -ErrorAction Stop -TimeoutSec 10
    Write-Output "  $testUrl2 -> $($r.StatusCode)"
} catch {
    Write-Output "  $testUrl2 -> $($_.Exception.Message)"
}

Write-Output ""
Write-Output "=== ClickToRun event log ==="
Get-EventLog -LogName Application -Newest 50 -ErrorAction SilentlyContinue |
    Where-Object { $_.Source -match "Click|Office Software|Office 365|OfficeC2R|MOAC" } |
    Select-Object -First 10 TimeGenerated, Source, EventID, EntryType, Message |
    ForEach-Object {
        $msg = if ($_.Message.Length -gt 200) { $_.Message.Substring(0, 200) } else { $_.Message }
        Write-Output "  [$($_.TimeGenerated) $($_.EntryType)] $($_.Source) #$($_.EventID): $msg"
    }
