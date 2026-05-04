<# Show actual rollback progress: download size, install state, what files have landed. #>
$ErrorActionPreference = "Continue"

Write-Output "=== ClickToRun process state ==="
Get-Process OfficeClickToRun -ErrorAction SilentlyContinue | ForEach-Object {
    $cpu = "?"
    try { $cpu = "{0:N1}" -f $_.CPU } catch {}
    Write-Output "  pid=$($_.Id) CPU=${cpu}s mem=$([int]($_.WorkingSet64/1MB))MB started=$($_.StartTime)"
}

Write-Output ""
Write-Output "=== Current vs target version ==="
$reg = Get-ItemProperty "HKLM:\SOFTWARE\Microsoft\Office\ClickToRun\Configuration" -ErrorAction SilentlyContinue
Write-Output "  current: $($reg.VersionToReport)"
Write-Output "  target:  16.0.19822.20182"

Write-Output ""
Write-Output "=== Updates staging folder ==="
$updates = "C:\Program Files\Common Files\Microsoft Shared\ClickToRun\Updates"
if (Test-Path $updates) {
    Get-ChildItem $updates -Directory -ErrorAction SilentlyContinue | ForEach-Object {
        $size = "{0:N1}" -f ((Get-ChildItem $_.FullName -Recurse -ErrorAction SilentlyContinue | Measure-Object Length -Sum).Sum / 1MB)
        Write-Output "  $($_.Name) - ${size} MB - last modified $($_.LastWriteTime)"
    }
}

Write-Output ""
Write-Output "=== Recent C2R log activity ==="
$logDir = "C:\Program Files\Common Files\Microsoft Shared\ClickToRun\Logs"
if (Test-Path $logDir) {
    $latestLog = Get-ChildItem $logDir -Filter "*.log" | Sort-Object LastWriteTime -Desc | Select-Object -First 1
    if ($latestLog) {
        Write-Output "  latest log: $($latestLog.Name) ($([int]($latestLog.Length/1KB))KB, modified $($latestLog.LastWriteTime))"
        Write-Output "  --- last 15 lines ---"
        Get-Content $latestLog.FullName -Tail 15 -ErrorAction SilentlyContinue | ForEach-Object {
            Write-Output "    $_"
        }
    }
}

Write-Output ""
Write-Output "=== Network bytes for OfficeClickToRun (this minute) ==="
$counter = "\Process(OfficeClickToRun)\IO Read Bytes/sec"
try {
    $sample = Get-Counter $counter -SampleInterval 2 -MaxSamples 3 -ErrorAction Stop
    $rates = $sample.CounterSamples | ForEach-Object { "{0:N0}" -f $_.CookedValue }
    Write-Output "  IO Read bytes/sec (3 samples 2s apart): $($rates -join ' | ')"
} catch {
    Write-Output "  perfcounter unavailable"
}
