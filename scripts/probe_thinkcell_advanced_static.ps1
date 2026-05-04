<#
Advanced static PowerShell probe — no Office runtime required.

Lanes:
- DPAPI decrypt of aiauthentication.bin
- Filesystem deep walk of think-cell install (every file: hash, version, sig)
- Authenticode signing cert extraction + chain
- WMI / Service / Scheduled Task / Driver enumeration for tc* names
- Office add-in registry full walk (all add-ins, not just think-cell)
- Related CLSID enumeration (sequential to think-cell's CLSID)
- Loopback TCP/UDP listeners snapshot
- Memory-mapped section names enumeration via NtQuerySystemInformation (\BaseNamedObjects requires Sysinternals winobj or PoC)
#>
[CmdletBinding()]
param(
    [string] $OutputPath
)

$ErrorActionPreference = "Continue"
$ProgressPreference = "SilentlyContinue"
Add-Type -AssemblyName System.Security -ErrorAction SilentlyContinue

function New-Result {
    [ordered]@{
        schema = "simcorp-thinkcell-advanced-static-probe/v1"
        timestamp_utc = [DateTime]::UtcNow.ToString("o")
        machine = [ordered]@{}
        dpapi_decrypt = [ordered]@{}
        filesystem = @()
        signing_certs = @()
        services = @()
        scheduled_tasks = @()
        drivers = @()
        office_addins = @()
        related_clsids = @()
        loopback_listeners = @()
        environment_vars_tc = @()
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
$result.machine.user = $env:USERNAME

# 1. DPAPI decrypt aiauthentication.bin
$aiAuthPath = "$env:APPDATA\think-cell\aiauthentication.bin"
if (Test-Path -LiteralPath $aiAuthPath) {
    try {
        $encBytes = [System.IO.File]::ReadAllBytes($aiAuthPath)
        $result.dpapi_decrypt.encrypted_size = $encBytes.Length
        $result.dpapi_decrypt.encrypted_sha256 = [System.BitConverter]::ToString(
            (New-Object System.Security.Cryptography.SHA256Managed).ComputeHash($encBytes)
        ).Replace("-", "").ToLowerInvariant()
        try {
            $decrypted = [System.Security.Cryptography.ProtectedData]::Unprotect(
                $encBytes, $null,
                [System.Security.Cryptography.DataProtectionScope]::CurrentUser
            )
            $result.dpapi_decrypt.decrypted = $true
            $result.dpapi_decrypt.decrypted_size = $decrypted.Length
            $text = [System.Text.Encoding]::UTF8.GetString($decrypted)
            $printable = ($text.ToCharArray() | Where-Object { [char]::IsControl($_) -eq $false -or $_ -in @("`n", "`r", "`t") }).Count
            if ($text.Length -gt 0 -and ($printable / $text.Length) -gt 0.85) {
                $result.dpapi_decrypt.is_text = $true
                $result.dpapi_decrypt.preview = if ($text.Length -gt 1500) { $text.Substring(0, 1500) + "..." } else { $text }
                # JWT detection: three base64 segments separated by .
                if ($text -match '^([A-Za-z0-9_-]+)\.([A-Za-z0-9_-]+)\.([A-Za-z0-9_-]+)$') {
                    $result.dpapi_decrypt.format_hint = "JWT"
                    $header_b64 = $matches[1]
                    $payload_b64 = $matches[2]
                    $b64pad = { param($s) $s + ("=" * ((4 - $s.Length % 4) % 4)) }
                    try {
                        $hdr_bytes = [System.Convert]::FromBase64String((& $b64pad $header_b64.Replace("-","+").Replace("_","/")))
                        $pay_bytes = [System.Convert]::FromBase64String((& $b64pad $payload_b64.Replace("-","+").Replace("_","/")))
                        $result.dpapi_decrypt.jwt_header = [System.Text.Encoding]::UTF8.GetString($hdr_bytes)
                        $result.dpapi_decrypt.jwt_payload = [System.Text.Encoding]::UTF8.GetString($pay_bytes)
                    } catch {
                        Add-ErrorRow -Result $result -Where "jwt_decode" -Err $_
                    }
                } elseif ($text -match '^\{') {
                    $result.dpapi_decrypt.format_hint = "JSON"
                    try {
                        $obj = $text | ConvertFrom-Json
                        $result.dpapi_decrypt.json_keys = @($obj.PSObject.Properties.Name)
                    } catch {}
                }
            } else {
                $result.dpapi_decrypt.is_text = $false
                $result.dpapi_decrypt.head_hex = (($decrypted[0..[Math]::Min(63, $decrypted.Length-1)] | ForEach-Object { $_.ToString("X2") }) -join "")
            }
        } catch {
            $result.dpapi_decrypt.decrypted = $false
            Add-ErrorRow -Result $result -Where "dpapi_unprotect" -Err $_
        }
    } catch {
        Add-ErrorRow -Result $result -Where "dpapi_read" -Err $_
    }
}

# 2. Filesystem deep walk of install
$installRoot = "C:\Program Files (x86)\think-cell"
if (Test-Path -LiteralPath $installRoot) {
    try {
        $files = Get-ChildItem -LiteralPath $installRoot -Recurse -File -ErrorAction SilentlyContinue
        foreach ($f in $files) {
            $entry = [ordered]@{
                rel = $f.FullName.Substring($installRoot.Length).TrimStart('\')
                size = $f.Length
                last_write_utc = $f.LastWriteTimeUtc.ToString("o")
                extension = $f.Extension
            }
            try { $vi = $f.VersionInfo; $entry.file_version = $vi.FileVersion; $entry.product_version = $vi.ProductVersion } catch {}
            if ($f.Extension -in @(".dll", ".exe", ".sys", ".ocx")) {
                try {
                    $entry.sha256 = (Get-FileHash -LiteralPath $f.FullName -Algorithm SHA256).Hash
                } catch {}
                try {
                    $sig = Get-AuthenticodeSignature -LiteralPath $f.FullName
                    if ($sig.Status -eq "Valid") {
                        $entry.signing_status = $sig.Status.ToString()
                        $entry.signer_subject = $sig.SignerCertificate.Subject
                        $entry.signer_thumbprint = $sig.SignerCertificate.Thumbprint
                        $entry.signing_time = $sig.SignerCertificate.NotBefore.ToString("o")
                    } else {
                        $entry.signing_status = $sig.Status.ToString()
                    }
                } catch {}
            }
            $result.filesystem += $entry
        }
    } catch { Add-ErrorRow -Result $result -Where "fs_walk" -Err $_ }
}

# 3. Unique signing certs
$result.signing_certs = @($result.filesystem |
    Where-Object { $_.signer_thumbprint } |
    Group-Object -Property signer_thumbprint |
    ForEach-Object {
        [ordered]@{
            thumbprint = $_.Name
            subject = $_.Group[0].signer_subject
            file_count = $_.Count
            sample_files = @($_.Group | Select-Object -First 3 -ExpandProperty rel)
        }
    })

# 4. Services
try {
    $result.services = @(Get-Service | Where-Object {
        $_.Name -match "(?i)tc|think" -or $_.DisplayName -match "(?i)think.cell"
    } | ForEach-Object {
        [ordered]@{
            name = $_.Name; display_name = $_.DisplayName; status = [string]$_.Status
            start_type = [string]$_.StartType
        }
    })
} catch { Add-ErrorRow -Result $result -Where "services" -Err $_ }

# 5. Scheduled Tasks
try {
    $result.scheduled_tasks = @(Get-ScheduledTask | Where-Object {
        $_.TaskName -match "(?i)tc|think" -or $_.Description -match "(?i)think.cell"
    } | ForEach-Object {
        [ordered]@{
            name = $_.TaskName; path = $_.TaskPath; state = [string]$_.State
            description = $_.Description
            actions = @($_.Actions | ForEach-Object { $_.Execute + " " + $_.Arguments })
        }
    })
} catch { Add-ErrorRow -Result $result -Where "tasks" -Err $_ }

# 6. Drivers
try {
    $result.drivers = @(Get-CimInstance Win32_SystemDriver | Where-Object {
        $_.Name -match "(?i)tc|think" -or $_.PathName -match "(?i)think.cell"
    } | ForEach-Object {
        [ordered]@{ name = $_.Name; state = $_.State; path = $_.PathName }
    })
} catch { Add-ErrorRow -Result $result -Where "drivers" -Err $_ }

# 7. Office add-ins (all of them)
$addinRoots = @(
    "HKCU:\Software\Microsoft\Office\PowerPoint\Addins",
    "HKCU:\Software\Microsoft\Office\Excel\Addins",
    "HKCU:\Software\Microsoft\Office\Word\Addins",
    "HKLM:\Software\Microsoft\Office\PowerPoint\Addins",
    "HKLM:\Software\Microsoft\Office\Excel\Addins",
    "HKLM:\Software\Microsoft\Office\Word\Addins",
    "HKLM:\Software\Wow6432Node\Microsoft\Office\PowerPoint\Addins",
    "HKLM:\Software\Wow6432Node\Microsoft\Office\Excel\Addins",
    "HKLM:\Software\Wow6432Node\Microsoft\Office\Word\Addins"
)
foreach ($r in $addinRoots) {
    if (-not (Test-Path -LiteralPath $r)) { continue }
    try {
        Get-ChildItem -LiteralPath $r -ErrorAction SilentlyContinue | ForEach-Object {
            $vals = @{}
            try { $vals = (Get-ItemProperty -LiteralPath $_.PSPath) } catch {}
            $result.office_addins += [ordered]@{
                root = $r; addin = $_.PSChildName
                friendly_name = $vals.FriendlyName; description = $vals.Description
                load_behavior = $vals.LoadBehavior; command_line_safe = $vals.CommandLineSafe
            }
        }
    } catch { Add-ErrorRow -Result $result -Where "addin:$r" -Err $_ }
}

# 8. Related CLSIDs (sequential nearby think-cell's {D52B1FA2-...})
# Walk a sample of CLSID prefixes that match think-cell-ish patterns
try {
    $hkcrCLSID = "Registry::HKEY_CLASSES_ROOT\CLSID"
    $tcRelated = @()
    foreach ($prefix in @("{D52B1FA2-", "{D52B1FA3-", "{D52B1FA1-")) {
        Get-ChildItem -Path $hkcrCLSID -ErrorAction SilentlyContinue |
            Where-Object { $_.PSChildName -like "$prefix*" } |
            Select-Object -First 50 |
            ForEach-Object {
                $iSrv = Join-Path $_.PSPath "InprocServer32"
                $progId = Join-Path $_.PSPath "ProgID"
                $entry = [ordered]@{ clsid = $_.PSChildName }
                try { $entry.default = (Get-ItemProperty -LiteralPath $_.PSPath -Name "(default)").'(default)' } catch {}
                try { $entry.inproc_server = (Get-ItemProperty -LiteralPath $iSrv -Name "(default)").'(default)' } catch {}
                try { $entry.progid = (Get-ItemProperty -LiteralPath $progId -Name "(default)").'(default)' } catch {}
                if ($entry.inproc_server -match "think.cell" -or $entry.progid -match "thinkcell" -or $entry.default -match "think.cell") {
                    $tcRelated += $entry
                }
            }
    }
    $result.related_clsids = @($tcRelated)
} catch { Add-ErrorRow -Result $result -Where "clsid_walk" -Err $_ }

# 9. Loopback TCP listeners (snapshot)
try {
    $result.loopback_listeners = @(Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue |
        Where-Object { $_.LocalAddress -in @("127.0.0.1", "::1", "0.0.0.0", "::") } |
        ForEach-Object {
            $proc = $null
            try { $proc = (Get-Process -Id $_.OwningProcess -ErrorAction SilentlyContinue).ProcessName } catch {}
            [ordered]@{
                local = "$($_.LocalAddress):$($_.LocalPort)"
                pid = $_.OwningProcess
                process = $proc
            }
        } |
        Where-Object { $_.process -match "(?i)tc|think|powerpnt|excel|ppttc|tcasr|tcserver" -or $true })  # keep all for context
} catch { Add-ErrorRow -Result $result -Where "loopback" -Err $_ }

# 10. TC environment variables (process / user / machine)
foreach ($scope in @("Process", "User", "Machine")) {
    try {
        $vars = [Environment]::GetEnvironmentVariables([System.EnvironmentVariableTarget]::$scope)
        foreach ($v in $vars.GetEnumerator()) {
            if ($v.Key -match '^(TC_|THINKCELL_|TCADDIN_|TCASR_|TCSERVER_|PPTTC_)') {
                $result.environment_vars_tc += [ordered]@{
                    scope = $scope.ToLower(); name = $v.Key; value = [string]$v.Value
                }
            }
        }
    } catch {}
}

# Verdict
$result.verdict.dpapi_token_decrypted = $result.dpapi_decrypt.decrypted -eq $true
$result.verdict.dpapi_format = $result.dpapi_decrypt.format_hint
$result.verdict.fs_file_count = $result.filesystem.Count
$result.verdict.signed_binary_count = ($result.filesystem | Where-Object { $_.signer_thumbprint }).Count
$result.verdict.distinct_signers = $result.signing_certs.Count
$result.verdict.tc_services = $result.services.Count
$result.verdict.tc_tasks = $result.scheduled_tasks.Count
$result.verdict.tc_drivers = $result.drivers.Count
$result.verdict.office_addin_count = $result.office_addins.Count
$result.verdict.related_clsid_count = $result.related_clsids.Count
$result.verdict.loopback_listener_count = $result.loopback_listeners.Count

if ($OutputPath) {
    $dir = Split-Path -Parent $OutputPath
    if ($dir -and -not (Test-Path -LiteralPath $dir)) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }
    $result | ConvertTo-Json -Depth 100 | Set-Content -LiteralPath $OutputPath -Encoding UTF8
}
$result | ConvertTo-Json -Depth 100 -Compress
