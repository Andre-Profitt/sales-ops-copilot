<#
OleView-lite registry probe for think-cell COM registration.

This intentionally does not install or run external tools. It reads the Windows
COM registry, Office AddIns registrations, and live COMAddIns surfaces to map
what think-cell exposes before deciding whether OleViewDotNet/Procmon are worth
bringing in.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string] $OutputDir
)

$ErrorActionPreference = "Continue"
$ProgressPreference = "SilentlyContinue"

function Write-JsonNoBom {
    param([string] $Path, [object] $Object, [int] $Depth = 12)
    $parent = Split-Path -Parent $Path
    if ($parent) { New-Item -ItemType Directory -Path $parent -Force | Out-Null }
    $json = $Object | ConvertTo-Json -Depth $Depth
    $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($Path, $json, $utf8NoBom)
}

function Get-RegValues {
    param([string] $Path)
    $values = [ordered]@{}
    try {
        if (-not (Test-Path -LiteralPath $Path)) { return $values }
        $item = Get-Item -LiteralPath $Path -ErrorAction Stop
        foreach ($name in $item.GetValueNames()) {
            $label = if ([string]::IsNullOrEmpty($name)) { "(default)" } else { $name }
            try { $values[$label] = [string] $item.GetValue($name) } catch {}
        }
    } catch {}
    return $values
}

function Get-RegDefault {
    param([string] $Path)
    try {
        if (-not (Test-Path -LiteralPath $Path)) { return $null }
        return [string] (Get-Item -LiteralPath $Path).GetValue("")
    } catch {
        return $null
    }
}

function Get-ClsidDetails {
    param([string] $Clsid)
    $base = "Registry::HKEY_CLASSES_ROOT\CLSID\$Clsid"
    $detail = [ordered]@{
        clsid = $Clsid
        present = Test-Path -LiteralPath $base
        default = $null
        values = [ordered]@{}
        inproc_server32 = [ordered]@{}
        local_server32 = [ordered]@{}
        prog_id = $null
        version_independent_prog_id = $null
        type_lib = $null
        app_id = $null
        implemented_categories = @()
    }
    if (-not $detail.present) { return $detail }
    $detail.default = Get-RegDefault $base
    $detail.values = Get-RegValues $base
    $detail.inproc_server32 = Get-RegValues "$base\InprocServer32"
    $detail.local_server32 = Get-RegValues "$base\LocalServer32"
    $detail.prog_id = Get-RegDefault "$base\ProgID"
    $detail.version_independent_prog_id = Get-RegDefault "$base\VersionIndependentProgID"
    $detail.type_lib = Get-RegDefault "$base\TypeLib"
    $detail.app_id = Get-RegDefault "$base\AppID"
    try {
        $cats = Get-ChildItem -LiteralPath "$base\Implemented Categories" -ErrorAction SilentlyContinue
        $detail.implemented_categories = @($cats | ForEach-Object { $_.PSChildName })
    } catch {}
    return $detail
}

function Get-ProgIdDetails {
    param([string] $ProgId)
    $base = "Registry::HKEY_CLASSES_ROOT\$ProgId"
    $clsid = Get-RegDefault "$base\CLSID"
    $curVer = Get-RegDefault "$base\CurVer"
    [ordered]@{
        prog_id = $ProgId
        present = Test-Path -LiteralPath $base
        default = Get-RegDefault $base
        values = Get-RegValues $base
        clsid = $clsid
        cur_ver = $curVer
        clsid_details = if ($clsid) { Get-ClsidDetails $clsid } else { $null }
        cur_ver_details = if ($curVer) { Get-ProgIdDetails $curVer } else { $null }
    }
}

function Test-ThinkCellText {
    param([object] $Value)
    if ($null -eq $Value) { return $false }
    return ([string] $Value) -match "(?i)think|tcaddin|ppttc|tcrunxl|tctabimp|tcserver|mekko|cell"
}

function Get-OfficeAddins {
    $paths = @(
        "HKCU:\Software\Microsoft\Office\PowerPoint\Addins",
        "HKLM:\Software\Microsoft\Office\PowerPoint\Addins",
        "HKLM:\Software\WOW6432Node\Microsoft\Office\PowerPoint\Addins",
        "HKCU:\Software\Microsoft\Office\Excel\Addins",
        "HKLM:\Software\Microsoft\Office\Excel\Addins",
        "HKLM:\Software\WOW6432Node\Microsoft\Office\Excel\Addins"
    )
    $rows = @()
    foreach ($path in $paths) {
        try {
            foreach ($key in Get-ChildItem -LiteralPath $path -ErrorAction SilentlyContinue) {
                $values = Get-RegValues $key.PSPath
                $haystack = [string]::Join(" ", @($key.PSChildName, $key.Name) + @($values.Values))
                if ($haystack -notmatch "(?i)think|cell|tcaddin") { continue }
                $rows += [ordered]@{
                    host_path = $path
                    name = $key.PSChildName
                    registry_path = $key.Name
                    values = $values
                }
            }
        } catch {}
    }
    return $rows
}

function Get-LiveComAddins {
    $rows = @()
    foreach ($officeHost in @("PowerPoint", "Excel")) {
        $app = $null
        try {
            $app = New-Object -ComObject "$officeHost.Application"
            if ($officeHost -eq "PowerPoint") { $app.Visible = -1 }
            $addin = $app.COMAddIns.Item("thinkcell.addin")
            $obj = $addin.Object
            $rows += [ordered]@{
                host = $officeHost
                prog_id = $addin.ProgId
                guid = $addin.Guid
                description = $addin.Description
                connect = [bool] $addin.Connect
                object_type = if ($obj) { $obj.GetType().FullName } else { $null }
            }
        } catch {
            $rows += [ordered]@{ host = $officeHost; error = $_.Exception.Message }
        } finally {
            if ($app) {
                try { $app.Quit() | Out-Null } catch {}
            }
        }
    }
    return $rows
}

New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null

$result = [ordered]@{
    schema = "simcorp-thinkcell-com-registry-probe/v1"
    timestamp_utc = [DateTime]::UtcNow.ToString("o")
    output_dir = $OutputDir
    installed_tools = @()
    office_addins_registry = @()
    progids = @()
    matching_clsids = @()
    matching_typelibs = @()
    live_com_addins = @()
    verdict = [ordered]@{}
}

try {
    $result.installed_tools = @(
        Get-Command oleview.exe, Procmon.exe, Procmon64.exe, OleViewDotNet.exe, OleViewDotNet4.exe, dotnet.exe, winget.exe -ErrorAction SilentlyContinue |
            ForEach-Object { [ordered]@{ name = $_.Name; source = $_.Source } }
    )
} catch {}

$result.office_addins_registry = @(Get-OfficeAddins)

$progIdNames = @()
try {
    $progIdNames = @(
        Get-ChildItem Registry::HKEY_CLASSES_ROOT -ErrorAction SilentlyContinue |
            Where-Object { $_.PSChildName -match "(?i)^think|^tc|think|tcaddin|ppttc|mekko" } |
            ForEach-Object { $_.PSChildName } |
            Sort-Object -Unique
    )
} catch {}
foreach ($progId in $progIdNames) {
    $result.progids += Get-ProgIdDetails $progId
}

$knownClsids = @($result.progids | ForEach-Object { $_.clsid } | Where-Object { $_ } | Sort-Object -Unique)
$matchedClsidMap = @{}
foreach ($clsid in $knownClsids) {
    $matchedClsidMap[$clsid] = Get-ClsidDetails $clsid
}
$result.matching_clsids = @($matchedClsidMap.Values | Sort-Object { $_.clsid })

try {
    $typeLibIds = @($result.matching_clsids | ForEach-Object { $_.type_lib } | Where-Object { $_ } | Sort-Object -Unique)
    foreach ($tlid in $typeLibIds) {
        $tlPath = "Registry::HKEY_CLASSES_ROOT\TypeLib\$tlid"
        if (-not (Test-Path -LiteralPath $tlPath)) { continue }
        $children = @()
        foreach ($sub in Get-ChildItem -LiteralPath $tlPath -Recurse -ErrorAction SilentlyContinue | Select-Object -First 160) {
            $children += [ordered]@{ path = $sub.Name; values = Get-RegValues $sub.PSPath }
        }
        $result.matching_typelibs += [ordered]@{ type_lib = $tlid; entries = $children }
    }
} catch {}

$result.live_com_addins = @(Get-LiveComAddins)

$constructorWords = "insert|create|add|chart|waterfall|mekko|gantt|table|element"
$exposedText = [string]::Join(" ", @($result.progids | ConvertTo-Json -Depth 8), @($result.matching_clsids | ConvertTo-Json -Depth 8))
$result.verdict = [ordered]@{
    oleview_dotnet_installed = @($result.installed_tools | Where-Object { $_.name -match "OleViewDotNet" }).Count -gt 0
    oleview_installed = @($result.installed_tools | Where-Object { $_.name -eq "oleview.exe" }).Count -gt 0
    procmon_installed = @($result.installed_tools | Where-Object { $_.name -match "Procmon" }).Count -gt 0
    matching_prog_id_count = @($result.progids).Count
    matching_clsid_count = @($result.matching_clsids).Count
    matching_typelib_count = @($result.matching_typelibs).Count
    has_constructor_like_registry_surface = $exposedText -match "(?i)$constructorWords"
    conclusion = "Registry/OleView-lite probe completed. Use this to decide whether external OleViewDotNet or Procmon adds evidence beyond COM registration."
}

$jsonPath = Join-Path $OutputDir "thinkcell_com_registry_probe.json"
Write-JsonNoBom $jsonPath $result 16
$result | ConvertTo-Json -Depth 16
