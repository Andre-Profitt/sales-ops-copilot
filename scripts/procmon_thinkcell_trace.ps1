<#
Narrow Procmon trace for think-cell/PowerPoint COM probing.

Requires Sysinternals Process Monitor to already be extracted. The script starts
a short capture, runs a disposable PowerPoint + think-cell COM workload, stops
capture, exports CSV, and writes a filtered report.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string] $OutputDir,

    [string] $ProcmonExe = "C:\tcw\procmon\Procmon64a.exe"
)

$ErrorActionPreference = "Continue"
$ProgressPreference = "SilentlyContinue"

function Write-JsonNoBom {
    param([string] $Path, [object] $Object, [int] $Depth = 10)
    $parent = Split-Path -Parent $Path
    if ($parent) { New-Item -ItemType Directory -Path $parent -Force | Out-Null }
    $json = $Object | ConvertTo-Json -Depth $Depth
    $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($Path, $json, $utf8NoBom)
}

function Add-ErrorRow {
    param([object] $Result, [string] $Where, [object] $ErrorRecord)
    $message = if ($ErrorRecord.Exception) { $ErrorRecord.Exception.Message } else { [string] $ErrorRecord }
    $Result.errors += [ordered]@{ where = $Where; message = $message }
}

function Invoke-Procmon {
    param(
        [string[]] $Arguments,
        [int] $TimeoutSeconds = 60,
        [switch] $NoWait
    )
    function Quote-Arg {
        param([string] $Value)
        if ($Value -match '[\s"]') {
            return '"' + ($Value -replace '"', '\"') + '"'
        }
        return $Value
    }
    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = $ProcmonExe
    $psi.Arguments = [string]::Join(" ", @($Arguments | ForEach-Object { Quote-Arg $_ }))
    $psi.UseShellExecute = $false
    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError = $true
    $proc = [System.Diagnostics.Process]::Start($psi)
    if ($NoWait) {
        return [ordered]@{
            exit_code = $null
            stdout = ""
            stderr = ""
            args = $Arguments
            command_line = "$ProcmonExe $($psi.Arguments)"
            process_id = $proc.Id
            no_wait = $true
        }
    }
    $exited = $proc.WaitForExit($TimeoutSeconds * 1000)
    if (-not $exited) {
        try { $proc.Kill() } catch {}
        return [ordered]@{
            exit_code = $null
            stdout = ""
            stderr = ""
            args = $Arguments
            command_line = "$ProcmonExe $($psi.Arguments)"
            process_id = $proc.Id
            timed_out = $true
            timeout_seconds = $TimeoutSeconds
        }
    }
    [ordered]@{
        exit_code = $proc.ExitCode
        stdout = $proc.StandardOutput.ReadToEnd()
        stderr = $proc.StandardError.ReadToEnd()
        args = $Arguments
        command_line = "$ProcmonExe $($psi.Arguments)"
    }
}

function Invoke-DisposableThinkCellWorkload {
    $actions = @()
    $ppt = $null
    $pres = $null
    try {
        $ppt = New-Object -ComObject PowerPoint.Application
        $ppt.Visible = -1
        $addin = $ppt.COMAddIns.Item("thinkcell.addin")
        $tcPp = $addin.Object
        $pres = $ppt.Presentations.Add(-1)
        $slide = $pres.Slides.Add(1, 12)
        $progId = $null
        $guid = $null
        $description = $null
        try { $progId = [string] $addin.ProgId } catch {}
        try { $guid = [string] $addin.Guid } catch {}
        try { $description = [string] $addin.Description } catch {}
        $actions += [ordered]@{
            action = "load_powerpoint_thinkcell_addin"
            prog_id = $progId
            guid = $guid
            description = $description
            connect = [bool] $addin.Connect
            shapes = $slide.Shapes.Count
        }
        foreach ($method in @("StartTableInsertion", "ShowChartGallery")) {
            try {
                if ($method -eq "StartTableInsertion") {
                    $rv = $tcPp.StartTableInsertion()
                } else {
                    $rv = $tcPp.ShowChartGallery(100, 100, 700, 500, 0)
                }
                $actions += [ordered]@{ action = $method; status = "returned"; return_value = [string] $rv }
            } catch {
                $actions += [ordered]@{ action = $method; status = "error"; error = $_.Exception.Message }
            }
        }
    } catch {
        $actions += [ordered]@{ action = "workload"; status = "error"; error = $_.Exception.Message }
    } finally {
        if ($pres) {
            try { $pres.Saved = -1 } catch {}
            try { $pres.Close() | Out-Null } catch {}
        }
        if ($ppt) {
            try { $ppt.Quit() | Out-Null } catch {}
        }
    }
    return $actions
}

New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$localDir = "C:\tcw\procmon_runs\$stamp"
New-Item -ItemType Directory -Path $localDir -Force | Out-Null

$pml = Join-Path $localDir "thinkcell_procmon.pml"
$csv = Join-Path $localDir "thinkcell_procmon.csv"
$filteredCsv = Join-Path $localDir "thinkcell_procmon.filtered.csv"
$json = Join-Path $localDir "thinkcell_procmon_report.json"

$result = [ordered]@{
    schema = "simcorp-thinkcell-procmon-trace/v1"
    timestamp_utc = [DateTime]::UtcNow.ToString("o")
    procmon_exe = $ProcmonExe
    local_dir = $localDir
    output_dir = $OutputDir
    start = [ordered]@{}
    workload = @()
    stop = [ordered]@{}
    export = [ordered]@{}
    filtered = [ordered]@{}
    errors = @()
}

if (-not (Test-Path -LiteralPath $ProcmonExe)) {
    throw "Procmon executable not found: $ProcmonExe"
}

try {
    $result.start = Invoke-Procmon @("/AcceptEula", "/Quiet", "/Minimized", "/BackingFile", $pml) -NoWait
    Start-Sleep -Seconds 3
} catch {
    Add-ErrorRow $result "procmon_start" $_
}

try {
    $result.workload = @(Invoke-DisposableThinkCellWorkload)
} catch {
    Add-ErrorRow $result "workload" $_
}

Start-Sleep -Seconds 2

try {
    $result.stop = Invoke-Procmon @("/AcceptEula", "/Terminate") -TimeoutSeconds 20
    Start-Sleep -Seconds 2
} catch {
    Add-ErrorRow $result "procmon_stop" $_
}

try {
    $result.export = Invoke-Procmon @("/AcceptEula", "/Quiet", "/OpenLog", $pml, "/SaveAs", $csv) -TimeoutSeconds 35
} catch {
    Add-ErrorRow $result "procmon_export" $_
}

try {
    $rows = @()
    if (Test-Path -LiteralPath $csv) {
        $rows = @(
            Import-Csv -LiteralPath $csv |
                Where-Object {
                    $text = [string]::Join(" ", @($_."Process Name", $_.Operation, $_.Path, $_.Result, $_.Detail))
                    $text -match "(?i)POWERPNT|EXCEL|think|tcaddin|ppttc|tcrunxl|tcserver|tctabimp|D52B1FA2|Name Not Found|CLSID|COMAddIns"
                }
        )
        $rows | Export-Csv -LiteralPath $filteredCsv -NoTypeInformation -Encoding UTF8
    }
    $result.filtered = [ordered]@{
        full_csv_present = Test-Path -LiteralPath $csv
        full_csv_size_bytes = if (Test-Path -LiteralPath $csv) { (Get-Item -LiteralPath $csv).Length } else { $null }
        pml_present = Test-Path -LiteralPath $pml
        pml_size_bytes = if (Test-Path -LiteralPath $pml) { (Get-Item -LiteralPath $pml).Length } else { $null }
        filtered_csv_present = Test-Path -LiteralPath $filteredCsv
        filtered_row_count = @($rows).Count
        name_not_found_count = @($rows | Where-Object { $_.Result -eq "NAME NOT FOUND" }).Count
        first_rows = @($rows | Select-Object -First 25)
    }
} catch {
    Add-ErrorRow $result "filter" $_
}

Write-JsonNoBom $json $result 12

foreach ($path in @($pml, $csv, $filteredCsv, $json)) {
    try {
        if (Test-Path -LiteralPath $path) {
            $item = Get-Item -LiteralPath $path
            if ($item.Extension -ne ".pml" -or $item.Length -le 50000000) {
                Copy-Item -LiteralPath $path -Destination (Join-Path $OutputDir (Split-Path -Leaf $path)) -Force
            }
        }
    } catch {
        Add-ErrorRow $result "copy_$path" $_
    }
}

Write-JsonNoBom (Join-Path $OutputDir "thinkcell_procmon_report.json") $result 12
$result | ConvertTo-Json -Depth 12
