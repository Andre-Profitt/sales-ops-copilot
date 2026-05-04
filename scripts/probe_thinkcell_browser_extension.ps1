<#
Browser-extension native-messaging probe.

think-cell ships a Chrome/Edge/Firefox extension that scrapes Tableau
views and web images, then talks to the local desktop add-in via
Chromium native messaging (JSON-over-stdin/stdout, 4-byte length prefix).

The native host registration lives under:

  HKLM\SOFTWARE\Google\Chrome\NativeMessagingHosts\<name>
  HKLM\SOFTWARE\Microsoft\Edge\NativeMessagingHosts\<name>
  HKLM\SOFTWARE\Mozilla\NativeMessagingHosts\<name>
  HKLM\SOFTWARE\Wow6432Node\... (32-bit equivalents)
  HKCU\... (per-user mirrors)

Each registration's default value is the path to a manifest.json file
that names: the host binary, allowed_origins (extension IDs), description,
and the protocol type (stdio).

This probe enumerates the registered native-messaging hosts, filters for
think-cell-related, reads the manifest JSON, locates the native host
binary, and runs a static analysis (version + hash + string scan for
command names + JSON-RPC patterns).

Read-only. Does not launch the native host or write to its stdin.
#>
[CmdletBinding()]
param(
    [string] $OutputPath,
    [int] $MaxBinaryStrings = 1000
)

$ErrorActionPreference = "Continue"
$ProgressPreference = "SilentlyContinue"

function New-Result {
    [ordered]@{
        schema = "simcorp-thinkcell-browser-extension-probe/v1"
        timestamp_utc = [DateTime]::UtcNow.ToString("o")
        machine = [ordered]@{}
        registered_hosts = @()
        thinkcell_hosts = @()
        manifests = @()
        host_binaries = @()
        extension_dirs = @()
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

# 1. Enumerate native-messaging host registrations
$regBases = @(
    "HKLM:\SOFTWARE\Google\Chrome\NativeMessagingHosts",
    "HKLM:\SOFTWARE\Microsoft\Edge\NativeMessagingHosts",
    "HKLM:\SOFTWARE\Mozilla\NativeMessagingHosts",
    "HKLM:\SOFTWARE\Wow6432Node\Google\Chrome\NativeMessagingHosts",
    "HKLM:\SOFTWARE\Wow6432Node\Microsoft\Edge\NativeMessagingHosts",
    "HKLM:\SOFTWARE\Wow6432Node\Mozilla\NativeMessagingHosts",
    "HKCU:\SOFTWARE\Google\Chrome\NativeMessagingHosts",
    "HKCU:\SOFTWARE\Microsoft\Edge\NativeMessagingHosts",
    "HKCU:\SOFTWARE\Mozilla\NativeMessagingHosts"
)
foreach ($base in $regBases) {
    if (-not (Test-Path -LiteralPath $base)) { continue }
    try {
        $children = Get-ChildItem -LiteralPath $base -ErrorAction Stop
        foreach ($c in $children) {
            $manifestPath = $null
            try {
                $manifestPath = (Get-ItemProperty -LiteralPath $c.PSPath -Name "(default)" -ErrorAction Stop).'(default)'
            } catch {
                # Some keys store the manifest path as the default value of the leaf
                try { $manifestPath = (Get-ItemProperty -LiteralPath $c.PSPath).'(default)' } catch {}
            }
            $entry = [ordered]@{
                browser = if ($base -match "Chrome") { "Chrome" } elseif ($base -match "Edge") { "Edge" } elseif ($base -match "Mozilla") { "Firefox" } else { "Unknown" }
                hive = if ($base.StartsWith("HKLM")) { "HKLM" } else { "HKCU" }
                wow64 = ($base -match "Wow6432Node")
                host_name = $c.PSChildName
                registry_path = $c.PSPath
                manifest_path = $manifestPath
            }
            $result.registered_hosts += $entry
        }
    } catch {
        Add-ErrorRow -Result $result -Where "regbase:$base" -Err $_
    }
}

# 2. Filter for think-cell-related host names
$tc = @($result.registered_hosts | Where-Object { $_.host_name -match "(?i)think|thinkcell|tc[._-]" })
$result.thinkcell_hosts = $tc

# 3. Read each candidate manifest
foreach ($h in $tc) {
    if (-not $h.manifest_path) { continue }
    if (-not (Test-Path -LiteralPath $h.manifest_path)) {
        Add-ErrorRow -Result $result -Where "manifest_missing:$($h.manifest_path)" -Err "file not found"
        continue
    }
    try {
        $raw = Get-Content -LiteralPath $h.manifest_path -Raw -ErrorAction Stop
        $obj = $raw | ConvertFrom-Json -ErrorAction Stop
        $manifest = [ordered]@{
            host_name = $h.host_name
            browser = $h.browser
            manifest_path = $h.manifest_path
            name = $obj.name
            description = $obj.description
            type = $obj.type
            path = $obj.path
            allowed_origins = @($obj.allowed_origins)
            allowed_extensions = @($obj.allowed_extensions)
            raw = $raw
        }
        $result.manifests += $manifest
    } catch {
        Add-ErrorRow -Result $result -Where "manifest_parse:$($h.manifest_path)" -Err $_
    }
}

# 4. For each manifest, analyze the native host binary
foreach ($m in $result.manifests) {
    if (-not $m.path) { continue }
    if (-not (Test-Path -LiteralPath $m.path)) {
        Add-ErrorRow -Result $result -Where "host_binary_missing:$($m.path)" -Err "file not found"
        continue
    }
    try {
        $f = Get-Item -LiteralPath $m.path -ErrorAction Stop
        $vi = $f.VersionInfo
        $entry = [ordered]@{
            host_name = $m.host_name
            path = $f.FullName
            size = $f.Length
            file_version = $vi.FileVersion
            product_version = $vi.ProductVersion
            product_name = $vi.ProductName
            company = $vi.CompanyName
            hash_sha256 = (Get-FileHash -LiteralPath $f.FullName -Algorithm SHA256).Hash
            last_write_utc = $f.LastWriteTimeUtc.ToString("o")
        }
        try {
            $bytes = [System.IO.File]::ReadAllBytes($f.FullName)
            $text = [System.Text.Encoding]::UTF8.GetString($bytes)
            $entry.string_hits = [ordered]@{
                json_keywords = ([regex]::Matches($text, '"(method|action|command|cmd|type|operation|verb|op|fn|name|target|payload|args|params|result|error|id|version)"\s*:')).Count
                tc_methods = ([regex]::Matches($text, '"(tc[A-Z][a-zA-Z0-9_]{2,32}|think[A-Z][a-zA-Z]+|insert[A-Z][a-zA-Z]+|extract[A-Z][a-zA-Z]+|capture[A-Z][a-zA-Z]+|tableau[A-Z][a-zA-Z]+)"')).Count
                native_messaging = ([regex]::Matches($text, "(?i)native[_]?messaging|chrome[_]?native|stdio")).Count
                rpc = ([regex]::Matches($text, "(?i)json[_-]?rpc|methodcall|invoke")).Count
            }
            $candidates = [regex]::Matches($text, '"(?<m>(?:get|set|insert|extract|capture|update|create|render|export|import|notify|send|receive|tableau|tc|think|chart|table|image)[A-Z][a-zA-Z0-9_]{2,40})"') |
                ForEach-Object { $_.Groups["m"].Value } | Group-Object | Sort-Object Count -Descending | Select-Object -First $MaxBinaryStrings | ForEach-Object { $_.Name }
            $entry.command_candidates = @($candidates | Sort-Object -Unique)
        } catch {
            Add-ErrorRow -Result $result -Where "string_scan:$($f.FullName)" -Err $_
        }
        $result.host_binaries += $entry
    } catch {
        Add-ErrorRow -Result $result -Where "host_binary:$($m.path)" -Err $_
    }
}

# 5. Locate Chrome/Edge/Firefox extension directories that match think-cell extension IDs
# Bounded to direct-name match only (no recursion) to avoid hangs on large extension directories.
$extIds = @()
foreach ($m in $result.manifests) {
    foreach ($o in $m.allowed_origins) {
        if ($o -match "chrome-extension://([a-z]{32})/") { $extIds += $matches[1] }
    }
    foreach ($o in $m.allowed_extensions) { $extIds += $o }
}
$extIds = @($extIds | Sort-Object -Unique)
$browserExtRoots = @(
    "$env:LOCALAPPDATA\Google\Chrome\User Data\Default\Extensions",
    "$env:LOCALAPPDATA\Microsoft\Edge\User Data\Default\Extensions"
)
foreach ($id in $extIds) {
    foreach ($root in $browserExtRoots) {
        if (-not (Test-Path -LiteralPath $root)) { continue }
        $direct = Join-Path $root $id
        if (-not (Test-Path -LiteralPath $direct)) { continue }
        try {
            # Only enumerate version subdirs at depth=1, no recursion
            $versionDirs = Get-ChildItem -LiteralPath $direct -Directory -ErrorAction SilentlyContinue | Select-Object -First 5
            foreach ($vd in $versionDirs) {
                $mf = Join-Path $vd.FullName "manifest.json"
                if (-not (Test-Path -LiteralPath $mf)) { continue }
                $entry = [ordered]@{
                    extension_id = $id
                    install_path = $vd.FullName
                    manifest_json = $mf
                }
                try {
                    $mraw = Get-Content -LiteralPath $mf -Raw -ErrorAction Stop
                    $mobj = $mraw | ConvertFrom-Json -ErrorAction Stop
                    $entry.name = $mobj.name
                    $entry.version = $mobj.version
                    $entry.description = $mobj.description
                    $entry.permissions = $mobj.permissions
                    $entry.host_permissions = $mobj.host_permissions
                } catch {}
                $result.extension_dirs += $entry
            }
        } catch {
            Add-ErrorRow -Result $result -Where ("extdir:" + $root + ":" + $id) -Err $_
        }
    }
}

$result.verdict.registered_host_count = $result.registered_hosts.Count
$result.verdict.thinkcell_host_count = $result.thinkcell_hosts.Count
$result.verdict.manifests_parsed = $result.manifests.Count
$result.verdict.host_binaries_analyzed = $result.host_binaries.Count
$result.verdict.extension_dirs_found = $result.extension_dirs.Count
$result.verdict.has_thinkcell_native_messaging = ($result.thinkcell_hosts.Count -gt 0)
$result.verdict.unique_command_candidate_count = (
    @($result.host_binaries | ForEach-Object { $_.command_candidates }) |
    Where-Object { $_ } | Sort-Object -Unique
).Count

if ($OutputPath) {
    $dir = Split-Path -Parent $OutputPath
    if ($dir -and -not (Test-Path -LiteralPath $dir)) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }
    $result | ConvertTo-Json -Depth 100 | Set-Content -LiteralPath $OutputPath -Encoding UTF8
}
$result | ConvertTo-Json -Depth 100 -Compress
