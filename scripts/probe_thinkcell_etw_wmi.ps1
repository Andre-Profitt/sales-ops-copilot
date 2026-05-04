<#
ETW provider / WMI namespace / perfcounter enumeration probe.

Static enumeration prep for Phase 12 (live ETW + mitm + Frida capture).
This probe ENUMERATES ONLY. It does NOT enable any trace, does NOT
start logman -ets, does NOT install any tools.

Targets:
  1. logman query providers  -> all registered ETW providers (manifest + classic)
     Filter for: think-cell, tc, Office, PowerPoint, BCrypt, Crypt32,
     WinHttp, Schannel.
     For each: GUID, name, source DLL, log type, message file.
  2. WMI: top-level root namespaces, then any class whose name matches
     thinkcell|office|powerpoint.
  3. Performance counter sets matching office|powerpoint|think|tc.
  4. Process snapshot for POWERPNT.EXE / tcaddin.dll / tcasr.exe.

ASCII-only (PS5.1 compatible). No em-dashes. No smart quotes.
#>
[CmdletBinding()]
param(
    [string] $OutputPath
)

$ErrorActionPreference = "Continue"
$ProgressPreference = "SilentlyContinue"

function New-Result {
    [ordered]@{
        schema = "simcorp-thinkcell-etw-wmi-inventory/v1"
        timestamp_utc = [DateTime]::UtcNow.ToString("o")
        machine = [ordered]@{}
        etw_providers = [ordered]@{
            total_registered = 0
            auth_relevant = @()
            office_powerpoint = @()
            think_cell = @()
            raw_sample_count = 0
        }
        etw_provider_details = [ordered]@{}
        wmi_namespaces = [ordered]@{
            root_top_level = @()
            namespace_class_hits = @()
        }
        perf_counters = [ordered]@{
            matching_sets = @()
        }
        processes = [ordered]@{
            powerpnt_running = $false
            tcasr_running = $false
            powerpnt_modules_thinkcell = @()
        }
        recommended_phase12_guids = @()
        errors = @()
    }
}

function Add-Err {
    param([object] $Result, [string] $Where, [object] $Err)
    $msg = if ($Err.Exception) { $Err.Exception.Message } else { [string] $Err }
    $Result.errors += [ordered]@{ where = $Where; message = $msg }
}

$result = New-Result
$result.machine.os = (Get-CimInstance Win32_OperatingSystem).Caption
$result.machine.host = $env:COMPUTERNAME
$result.machine.arch = $env:PROCESSOR_ARCHITECTURE

# ---------------------------------------------------------------------------
# 1. ETW providers via logman query providers
# ---------------------------------------------------------------------------
$rawProviders = $null
try {
    $rawProviders = & logman query providers 2>&1
} catch { Add-Err -Result $result -Where "logman_providers" -Err $_ }

# Parse: rows look like
#   "Provider Name                            {GUID}"
$providerRows = @()
if ($rawProviders) {
    foreach ($line in $rawProviders) {
        $s = [string]$line
        if ($s -match '^\s*(.+?)\s+\{([0-9A-Fa-f-]{36})\}\s*$') {
            $providerRows += [ordered]@{
                name = $matches[1].Trim()
                guid = "{" + $matches[2].ToUpper() + "}"
            }
        }
    }
}
$result.etw_providers.total_registered = $providerRows.Count
$result.etw_providers.raw_sample_count = if ($rawProviders) { $rawProviders.Count } else { 0 }

# Auth-relevant filter list (case-insensitive)
$authPatterns = @(
    'BCrypt', 'Crypt32', 'WinHttp', 'Schannel', 'NCrypt', 'LSA',
    'SSL', 'TLS', 'HTTP'
)
$officePatterns = @('Office', 'PowerPoint', 'PPT')
$tcPatterns = @('think-cell', 'thinkcell', 'tcaddin', 'tcasr')

function Match-Any {
    param([string] $text, [string[]] $patterns)
    foreach ($p in $patterns) {
        if ($text -match [regex]::Escape($p)) { return $true }
    }
    return $false
}

$authMatched = @()
$officeMatched = @()
$tcMatched = @()

foreach ($row in $providerRows) {
    $n = [string]$row.name
    if (Match-Any $n $authPatterns) { $authMatched += $row }
    if (Match-Any $n $officePatterns) { $officeMatched += $row }
    if (Match-Any $n $tcPatterns) { $tcMatched += $row }
}

$result.etw_providers.auth_relevant = @($authMatched)
$result.etw_providers.office_powerpoint = @($officeMatched)
$result.etw_providers.think_cell = @($tcMatched)

# Deep detail for matched providers via "logman query providers <GUID>"
$detailTargets = @()
$detailTargets += $authMatched
$detailTargets += $officeMatched
$detailTargets += $tcMatched

# Dedup by GUID
$seen = @{}
$detailTargets = @($detailTargets | Where-Object {
    if ($seen.ContainsKey($_.guid)) { return $false } else { $seen[$_.guid] = $true; return $true }
})

foreach ($prov in $detailTargets) {
    try {
        $detail = & logman query providers $prov.guid 2>&1 | Out-String
        # Parse: typical block contains lines like "Source File: <path>"
        $sourceFile = $null
        $messageFile = $null
        $resourceFile = $null
        $value = $null
        $logType = $null
        if ($detail -match '(?im)^\s*Source\s*File:\s*(.+)$') { $sourceFile = $matches[1].Trim() }
        if ($detail -match '(?im)^\s*Message\s*File:\s*(.+)$') { $messageFile = $matches[1].Trim() }
        if ($detail -match '(?im)^\s*Resource\s*File:\s*(.+)$') { $resourceFile = $matches[1].Trim() }
        if ($detail -match '(?im)^\s*Value\s*:\s*(.+)$') { $value = $matches[1].Trim() }
        if ($detail -match '(?im)^\s*Log\s*Type:\s*(.+)$') { $logType = $matches[1].Trim() }

        $result.etw_provider_details[$prov.guid] = [ordered]@{
            name = $prov.name
            guid = $prov.guid
            source_file = $sourceFile
            message_file = $messageFile
            resource_file = $resourceFile
            value = $value
            log_type = $logType
            raw_excerpt = ($detail.Substring(0, [Math]::Min(2400, $detail.Length)))
        }
    } catch {
        Add-Err -Result $result -Where ("provider_detail:" + $prov.guid) -Err $_
    }
}

# ---------------------------------------------------------------------------
# 2. WMI namespaces under root + class match for thinkcell/office/powerpoint
# ---------------------------------------------------------------------------
$rootNamespaces = @()
try {
    $ns = Get-CimInstance -Namespace root -ClassName __Namespace -ErrorAction Stop |
          Select-Object -ExpandProperty Name
    $rootNamespaces = @($ns)
    $result.wmi_namespaces.root_top_level = @($ns)
} catch { Add-Err -Result $result -Where "wmi_root_namespace" -Err $_ }

# Search class names per namespace. To keep this bounded, we search root and
# the obvious application namespaces that exist (cimv2, default, Microsoft, etc.)
$tcClassRegex = '(?i)thinkcell|think_cell|powerpoint|office'
$nsToScan = @('root') + (@($rootNamespaces | ForEach-Object { "root\" + $_ }))

# WMI is slow per-namespace; cap depth to top level only for this static probe
foreach ($scanNs in $nsToScan) {
    try {
        $classes = Get-CimClass -Namespace $scanNs -ErrorAction SilentlyContinue |
                   Where-Object { $_.CimClassName -match $tcClassRegex }
        foreach ($c in $classes) {
            $result.wmi_namespaces.namespace_class_hits += [ordered]@{
                namespace = $scanNs
                class_name = $c.CimClassName
            }
        }
    } catch {
        Add-Err -Result $result -Where ("wmi_scan:" + $scanNs) -Err $_
    }
}

# ---------------------------------------------------------------------------
# 3. Performance counters
# ---------------------------------------------------------------------------
try {
    $sets = Get-Counter -ListSet * -ErrorAction SilentlyContinue
    $matched = @($sets | Where-Object { $_.CounterSetName -match '(?i)office|powerpoint|think|tc' })
    foreach ($m in $matched) {
        $result.perf_counters.matching_sets += [ordered]@{
            name = $m.CounterSetName
            description = $m.Description
            counter_count = ($m.Counter | Measure-Object).Count
            counters = @($m.Counter)
        }
    }
} catch { Add-Err -Result $result -Where "perf_counters" -Err $_ }

# ---------------------------------------------------------------------------
# 4. Process snapshot
# ---------------------------------------------------------------------------
try {
    $pp = Get-Process POWERPNT -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($pp) {
        $result.processes.powerpnt_running = $true
        $result.processes.powerpnt_pid = $pp.Id
        $tcMods = @($pp.Modules | Where-Object { $_.ModuleName -match '(?i)tc|think' })
        $result.processes.powerpnt_modules_thinkcell = @($tcMods | ForEach-Object {
            [ordered]@{ name = $_.ModuleName; file = $_.FileName }
        })
    }
} catch { Add-Err -Result $result -Where "process_powerpnt" -Err $_ }

try {
    $tcasr = Get-Process tcasr -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($tcasr) {
        $result.processes.tcasr_running = $true
        $result.processes.tcasr_pid = $tcasr.Id
        $result.processes.tcasr_path = $tcasr.Path
    }
} catch { Add-Err -Result $result -Where "process_tcasr" -Err $_ }

# ---------------------------------------------------------------------------
# Recommendations: which GUIDs are worth enabling for Phase 12
# ---------------------------------------------------------------------------
# Hard-coded canonical Phase-12 candidates (we will check if each is registered)
$candidates = @(
    @{ name = "Microsoft-Windows-WinHttp"; guid = "{7D44233D-3055-4B9C-BA64-0D47CA40A232}"; reason = "HTTPS request URIs / status / headers without mitm" },
    @{ name = "Microsoft-Windows-WinINet"; guid = "{43D1A55C-76D6-4F7E-995C-64C711E5CAFE}"; reason = "WinINet HTTP for Office add-ins" },
    @{ name = "Microsoft-Windows-Schannel-Events"; guid = "{91CC1150-71AA-47E2-AE18-C96E61736B6F}"; reason = "TLS handshake details, cipher suite" },
    @{ name = "Microsoft-Windows-Crypto-BCrypt"; guid = "{C7E089AC-BA2A-11E0-9AF7-68384824019B}"; reason = "BCrypt API calls (HMAC, hashes) -> definitive auth scheme proof" },
    @{ name = "Microsoft-Windows-Crypto-NCrypt"; guid = "{E8ED09DC-100C-45E2-9FC8-B53399EC1F70}"; reason = "NCrypt key operations" },
    @{ name = "Microsoft-Windows-Crypto-CNG"; guid = "{E3E0E2D0-C9C7-4F3E-9C5E-39C0EE2D1E8E}"; reason = "CNG higher-level crypto operations" },
    @{ name = "Microsoft-Windows-LSA"; guid = "{CC85922F-DB41-11D2-9244-006008269001}"; reason = "Auth package interactions" },
    @{ name = "Microsoft-Windows-WebIO"; guid = "{50B3E73C-9370-461D-BB9F-26F32D68887D}"; reason = "WinHTTP+WinINet shared web I/O layer" },
    @{ name = "Microsoft-Windows-DNS-Client"; guid = "{1C95126E-7EEA-49A9-A3FE-A378B03DDB4D}"; reason = "Hostname resolution timing" }
)

$registeredGuids = @{}
foreach ($row in $providerRows) { $registeredGuids[$row.guid.ToUpper()] = $row.name }

foreach ($cand in $candidates) {
    $g = $cand.guid.ToUpper()
    $registered = $registeredGuids.ContainsKey($g)
    $resolvedName = if ($registered) { $registeredGuids[$g] } else { $null }
    $result.recommended_phase12_guids += [ordered]@{
        candidate_name = $cand.name
        guid = $cand.guid
        reason = $cand.reason
        registered_on_vm = $registered
        registered_name = $resolvedName
    }
}

# ---------------------------------------------------------------------------
# Emit
# ---------------------------------------------------------------------------
if ($OutputPath) {
    $dir = Split-Path -Parent $OutputPath
    if ($dir -and -not (Test-Path -LiteralPath $dir)) {
        New-Item -ItemType Directory -Path $dir -Force | Out-Null
    }
    $result | ConvertTo-Json -Depth 100 | Set-Content -LiteralPath $OutputPath -Encoding UTF8
}
$result | ConvertTo-Json -Depth 100 -Compress
