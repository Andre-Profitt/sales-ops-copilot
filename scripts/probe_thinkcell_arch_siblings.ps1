<#
Architecture-sibling enumeration for tcaddin.dll.

Current install path is C:\Program Files (x86)\think-cell\arm64\tcaddin.dll.
The (x86) parent + arm64 child layout is unusual; this probe checks for
sibling architecture folders (arm, x86, x64, amd64) and compares the DLLs
across them. Different builds occasionally expose different exported surface.

Read-only. No COM activation. No method invocation.
#>
[CmdletBinding()]
param(
    [string] $OutputPath
)

$ErrorActionPreference = "Continue"
$ProgressPreference = "SilentlyContinue"

function New-Result {
    [ordered]@{
        schema = "simcorp-thinkcell-arch-siblings-probe/v1"
        timestamp_utc = [DateTime]::UtcNow.ToString("o")
        machine = [ordered]@{}
        thinkcell_root_candidates = @()
        sibling_dirs = @()
        dlls = @()
        verdict = [ordered]@{}
        errors = @()
    }
}

function Add-ErrorRow {
    param([object] $Result, [string] $Where, [object] $Err)
    $msg = if ($Err.Exception) { $Err.Exception.Message } else { [string] $Err }
    $Result.errors += [ordered]@{ where = $Where; message = $msg }
}

$result = New-Result
try {
    $result.machine.os = (Get-CimInstance Win32_OperatingSystem -ErrorAction Stop).Caption
} catch {
    Add-ErrorRow -Result $result -Where "machine:os" -Err $_
}
$result.machine.arch = $env:PROCESSOR_ARCHITECTURE
$result.machine.host = $env:COMPUTERNAME

$rootCandidates = @(
    "C:\Program Files\think-cell",
    "C:\Program Files (x86)\think-cell",
    "$env:LOCALAPPDATA\think-cell"
)
foreach ($root in $rootCandidates) {
    $entry = [ordered]@{ path = $root; exists = (Test-Path -LiteralPath $root) }
    if ($entry.exists) {
        try {
            $entry.subdirs = @(Get-ChildItem -LiteralPath $root -Directory -ErrorAction Stop | ForEach-Object { $_.Name })
        } catch {
            Add-ErrorRow -Result $result -Where "subdirs:$root" -Err $_
            $entry.subdirs = @()
        }
    }
    $result.thinkcell_root_candidates += $entry
}

$archDirs = @()
foreach ($entry in $result.thinkcell_root_candidates | Where-Object { $_.exists -and $_.subdirs }) {
    foreach ($s in $entry.subdirs) {
        if ($s -match '^(arm64|arm|x86|x64|amd64|win32)$') {
            $archDirs += (Join-Path $entry.path $s)
        }
    }
}
$result.sibling_dirs = $archDirs

foreach ($d in $archDirs) {
    try {
        $dlls = Get-ChildItem -LiteralPath $d -File -Filter "*.dll" -ErrorAction Stop
        foreach ($dll in $dlls) {
            $vi = (Get-Item -LiteralPath $dll.FullName).VersionInfo
            $info = [ordered]@{
                path = $dll.FullName
                arch_dir = Split-Path -Leaf $d
                size = $dll.Length
                file_version = $vi.FileVersion
                product_version = $vi.ProductVersion
                hash_sha256 = (Get-FileHash -LiteralPath $dll.FullName -Algorithm SHA256).Hash
                last_write_utc = $dll.LastWriteTimeUtc.ToString("o")
            }
            try {
                $bytes = [System.IO.File]::ReadAllBytes($dll.FullName)
                $text = [System.Text.Encoding]::ASCII.GetString($bytes)
                $info.marker_counts = [ordered]@{
                    tc_methods = ([regex]::Matches($text, "(?<![A-Za-z])tc[A-Z][a-zA-Z]{3,}")).Count
                    cxl_classes = ([regex]::Matches($text, "CXl[A-Z][a-zA-Z]+::[a-zA-Z]+")).Count
                    start_table = ([regex]::Matches($text, "StartTableInsertion")).Count
                    charts_gallery = ([regex]::Matches($text, "ChartsGallery")).Count
                    bain_toolbox = ([regex]::Matches($text, "BainToolbox")).Count
                    step_methods = ([regex]::Matches($text, "Step[1-9]\b")).Count
                }
            } catch {
                Add-ErrorRow -Result $result -Where "string_scan:$($dll.FullName)" -Err $_
            }
            $result.dlls += $info
        }
    } catch {
        Add-ErrorRow -Result $result -Where "enum:$d" -Err $_
    }
}

$uniqueVersions = @($result.dlls | ForEach-Object { $_.file_version } | Where-Object { $_ } | Sort-Object -Unique)
$uniqueHashes = @($result.dlls | ForEach-Object { $_.hash_sha256 } | Sort-Object -Unique)
$tcaddinDlls = @($result.dlls | Where-Object { (Split-Path -Leaf $_.path) -eq "tcaddin.dll" })
$result.verdict.dll_count = $result.dlls.Count
$result.verdict.tcaddin_dll_count = $tcaddinDlls.Count
$result.verdict.distinct_versions = $uniqueVersions
$result.verdict.distinct_hashes = $uniqueHashes
$result.verdict.architecture_variants_present = ($tcaddinDlls.Count -gt 1)
$result.verdict.cross_arch_marker_diff = ($tcaddinDlls | ForEach-Object { $_.marker_counts } | Sort-Object -Unique).Count -gt 1

if ($OutputPath) {
    $dir = Split-Path -Parent $OutputPath
    if ($dir -and -not (Test-Path -LiteralPath $dir)) {
        New-Item -ItemType Directory -Path $dir -Force | Out-Null
    }
    $result | ConvertTo-Json -Depth 100 | Set-Content -LiteralPath $OutputPath -Encoding UTF8
}
$result | ConvertTo-Json -Depth 100 -Compress
