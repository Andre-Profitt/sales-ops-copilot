<#
Combined endpoints + environment probe.

Lanes:
- A. tcserver.exe / tcaddin.dll / ppttc.exe / tcasr.exe binary string scan
     for URL patterns, HTTP route patterns, think-cell.com subdomains,
     /api/ /v[0-9]/ /admin/* style paths.
- D. Registry + env-var + filesystem enumeration.
- E. Network endpoint extraction (URLs, hostnames).

Read-only. Static binary analysis + registry/filesystem reads only.
#>
[CmdletBinding()]
param(
    [string] $OutputPath,
    [int] $MaxStringHits = 800
)

$ErrorActionPreference = "Continue"
$ProgressPreference = "SilentlyContinue"

function New-Result {
    [ordered]@{
        schema = "simcorp-thinkcell-endpoints-environment-probe/v1"
        timestamp_utc = [DateTime]::UtcNow.ToString("o")
        machine = [ordered]@{}
        binaries = @()
        registry = @()
        env_vars = @()
        filesystem = @()
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
$result.machine.os = (Get-CimInstance Win32_OperatingSystem).Caption
$result.machine.host = $env:COMPUTERNAME
$result.machine.arch = $env:PROCESSOR_ARCHITECTURE

# A + E: Binary string scan
$binaryPaths = @(
    "C:\Program Files (x86)\think-cell\arm64\tcaddin.dll",
    "C:\Program Files (x86)\think-cell\ppttc.exe",
    "C:\Program Files (x86)\think-cell\tcserver.exe",
    "C:\Program Files (x86)\think-cell\tcasr.exe"
) | Where-Object { Test-Path -LiteralPath $_ }

foreach ($p in $binaryPaths) {
    try {
        $bytes = [System.IO.File]::ReadAllBytes($p)
        $ascii = [System.Text.Encoding]::ASCII.GetString($bytes)
        $utf16 = [System.Text.Encoding]::Unicode.GetString($bytes)
        $combined = $ascii + "`n" + $utf16

        $entry = [ordered]@{
            path = $p
            size = $bytes.Length
            file_version = (Get-Item -LiteralPath $p).VersionInfo.FileVersion
        }

        # URLs
        $urlRe = [regex]::new('(?i)https?://[A-Za-z0-9._/~?=#&%+:-]{4,200}')
        $urls = @($urlRe.Matches($combined) | ForEach-Object { $_.Value } | Sort-Object -Unique | Select-Object -First $MaxStringHits)
        $entry.urls = $urls
        $entry.url_count = $urls.Count

        # think-cell-specific subdomains
        $tcHostRe = [regex]::new('(?i)([a-z0-9-]+\.think-cell\.com)')
        $tcHosts = @($tcHostRe.Matches($combined) | ForEach-Object { $_.Groups[1].Value } | Sort-Object -Unique)
        $entry.thinkcell_hosts = $tcHosts

        # HTTP route patterns: token starting with / followed by lowercase
        $routeRe = [regex]::new('(?<![A-Za-z0-9_])(/(?:api|v\d+|admin|debug|metrics|health|version|status|render|update|export|files?|jobs?|render|generate|portal|auth|login|logout|user|tenant|partner|license|tcserver|ppttc|schema|spec|openapi|swagger|graphql)[a-zA-Z0-9_/-]{0,80})')
        $routes = @($routeRe.Matches($combined) | ForEach-Object { $_.Value } | Sort-Object -Unique | Select-Object -First $MaxStringHits)
        $entry.http_routes = $routes

        # Endpoint-style hint strings
        $hintRe = [regex]::new('(?i)\b(GET|POST|PUT|DELETE|PATCH|OPTIONS|HEAD)\s+/[A-Za-z0-9_/-]{1,80}')
        $hints = @($hintRe.Matches($combined) | ForEach-Object { $_.Value } | Sort-Object -Unique | Select-Object -First 60)
        $entry.method_route_hints = $hints

        # Diagnostic / log keywords
        $diagRe = [regex]::new('(?i)\b(TC_[A-Z][A-Z0-9_]+|THINKCELL_[A-Z][A-Z0-9_]+|tc(verbose|debug|trace|log|diagnostic)[A-Za-z]*)\b')
        $diags = @($diagRe.Matches($combined) | ForEach-Object { $_.Value } | Sort-Object -Unique | Select-Object -First 60)
        $entry.diagnostic_keywords = $diags

        $result.binaries += $entry
    } catch {
        Add-ErrorRow -Result $result -Where "binary_scan:$p" -Err $_
    }
}

# D: Registry walk
$regRoots = @(
    "HKCU:\Software\think-cell",
    "HKLM:\Software\think-cell",
    "HKLM:\Software\Wow6432Node\think-cell",
    "HKCU:\Software\Microsoft\Office\PowerPoint\Addins\thinkcell.addin",
    "HKCU:\Software\Microsoft\Office\Excel\Addins\thinkcell.addin",
    "HKLM:\Software\Microsoft\Office\PowerPoint\Addins\thinkcell.addin",
    "HKLM:\Software\Microsoft\Office\Excel\Addins\thinkcell.addin",
    "HKLM:\Software\Wow6432Node\Microsoft\Office\PowerPoint\Addins\thinkcell.addin",
    "HKLM:\Software\Wow6432Node\Microsoft\Office\Excel\Addins\thinkcell.addin"
)
foreach ($root in $regRoots) {
    if (-not (Test-Path -LiteralPath $root)) { continue }
    try {
        $tree = @()
        $stack = New-Object System.Collections.Generic.Queue[string]
        $stack.Enqueue($root)
        $depth = 0
        while ($stack.Count -gt 0 -and $depth -lt 1000) {
            $depth++
            $cur = $stack.Dequeue()
            try {
                $key = Get-Item -LiteralPath $cur -ErrorAction Stop
                $valueDict = [ordered]@{}
                foreach ($vname in $key.GetValueNames()) {
                    try {
                        $vraw = $key.GetValue($vname)
                        $vstr = if ($null -eq $vraw) { $null } else { [string]$vraw }
                        $valueDict[$vname] = if ($vstr -and $vstr.Length -gt 400) { $vstr.Substring(0, 400) + "..." } else { $vstr }
                    } catch { $valueDict[$vname] = "READ_ERROR" }
                }
                $tree += [ordered]@{
                    path = $cur
                    sub_keys = @($key.GetSubKeyNames())
                    values = $valueDict
                }
                foreach ($sn in $key.GetSubKeyNames()) {
                    $stack.Enqueue("$cur\$sn")
                }
            } catch { Add-ErrorRow -Result $result -Where "reg_read:$cur" -Err $_ }
        }
        $result.registry += [ordered]@{ root = $root; nodes = $tree }
    } catch { Add-ErrorRow -Result $result -Where "reg_walk:$root" -Err $_ }
}

# Env vars: TC_*, THINKCELL_*, TCADDIN_*, TCASR_*
foreach ($v in [Environment]::GetEnvironmentVariables().GetEnumerator()) {
    if ($v.Key -match '^(TC_|THINKCELL_|TCADDIN_|TCASR_|TCSERVER_)') {
        $result.env_vars += [ordered]@{
            scope = "process"
            name = $v.Key
            value = [string]$v.Value
        }
    }
}
foreach ($scope in @("User", "Machine")) {
    try {
        $vars = [Environment]::GetEnvironmentVariables([System.EnvironmentVariableTarget]::$scope)
        foreach ($v in $vars.GetEnumerator()) {
            if ($v.Key -match '^(TC_|THINKCELL_|TCADDIN_|TCASR_|TCSERVER_)') {
                $result.env_vars += [ordered]@{
                    scope = $scope.ToLower()
                    name = $v.Key
                    value = [string]$v.Value
                }
            }
        }
    } catch { Add-ErrorRow -Result $result -Where "env:$scope" -Err $_ }
}

# Filesystem: think-cell directories outside the install root
$fsRoots = @(
    "$env:LOCALAPPDATA\think-cell",
    "$env:APPDATA\think-cell",
    "$env:ProgramData\think-cell",
    "$env:TEMP\think-cell",
    "$env:LOCALAPPDATA\Temp\think-cell"
)
foreach ($r in $fsRoots) {
    if (-not (Test-Path -LiteralPath $r)) {
        $result.filesystem += [ordered]@{ path = $r; exists = $false }
        continue
    }
    try {
        $items = Get-ChildItem -LiteralPath $r -Recurse -File -Depth 5 -ErrorAction SilentlyContinue | Select-Object -First 200
        $entry = [ordered]@{
            path = $r
            exists = $true
            file_count = $items.Count
            files = @($items | ForEach-Object {
                [ordered]@{
                    rel = $_.FullName.Substring($r.Length).TrimStart('\')
                    size = $_.Length
                    last_write_utc = $_.LastWriteTimeUtc.ToString("o")
                    extension = $_.Extension
                }
            })
        }
        $result.filesystem += $entry
    } catch { Add-ErrorRow -Result $result -Where "fs:$r" -Err $_ }
}

# Verdicts
$allUrls = @($result.binaries | ForEach-Object { $_.urls } | Where-Object { $_ } | Sort-Object -Unique)
$allHosts = @($result.binaries | ForEach-Object { $_.thinkcell_hosts } | Where-Object { $_ } | Sort-Object -Unique)
$allRoutes = @($result.binaries | ForEach-Object { $_.http_routes } | Where-Object { $_ } | Sort-Object -Unique)
$result.verdict.binary_count = $result.binaries.Count
$result.verdict.distinct_url_count = $allUrls.Count
$result.verdict.distinct_thinkcell_hosts = $allHosts
$result.verdict.distinct_route_count = $allRoutes.Count
$result.verdict.distinct_routes = $allRoutes
$result.verdict.urls_sample = ($allUrls | Select-Object -First 60)
$result.verdict.registry_node_count = ($result.registry | ForEach-Object { $_.nodes.Count } | Measure-Object -Sum).Sum
$result.verdict.env_var_count = $result.env_vars.Count
$result.verdict.filesystem_path_count = ($result.filesystem | Where-Object { $_.exists }).Count

if ($OutputPath) {
    $dir = Split-Path -Parent $OutputPath
    if ($dir -and -not (Test-Path -LiteralPath $dir)) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }
    $result | ConvertTo-Json -Depth 100 | Set-Content -LiteralPath $OutputPath -Encoding UTF8
}
$result | ConvertTo-Json -Depth 100 -Compress
