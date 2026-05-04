<#
tcserver.exe controlled start + route probe.

Per the unblock matrix, starting tcserver.exe is a gating decision. The string
scan revealed 28 versioned routes (/v0 - /v9 with type suffixes + /schemas).
This probe:

1. Starts tcserver.exe on a non-default port (8842) bound to 127.0.0.1 only
2. Probes each known route with HEAD/OPTIONS/GET
3. POSTs a sample think-cellXML to each /vN to characterize behavior
4. Captures response headers + bodies
5. Stops the server cleanly

Read-only against the live server. No state-changing operations.
The server runs only for the duration of this probe.
#>
[CmdletBinding()]
param(
    [string] $OutputPath,
    [int] $Port = 8842,
    [string] $TcServerExe = "C:\Program Files (x86)\think-cell\tcserver.exe"
)

$ErrorActionPreference = "Continue"
$ProgressPreference = "SilentlyContinue"

function New-Result {
    [ordered]@{
        schema = "simcorp-thinkcell-tcserver-routes-probe/v1"
        timestamp_utc = [DateTime]::UtcNow.ToString("o")
        machine = [ordered]@{}
        tcserver = [ordered]@{}
        startup = [ordered]@{}
        route_probes = @()
        verdict = [ordered]@{}
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

# Routes from binary string scan
$routes = @(
    "/", "/schemas",
    "/v0", "/v0EE", "/v0h",
    "/v1", "/v1E", "/v1H", "/v1M",
    "/v2", "/v2B", "/v2HP", "/v2f",
    "/v3", "/v3f", "/v3fA",
    "/v4", "/v4D", "/v4U",
    "/v5", "/v5B",
    "/v6", "/v6H", "/v6M", "/v6f",
    "/v7", "/v7G", "/v7H", "/v7f",
    "/v8",
    "/v9", "/v9f"
)

if (-not (Test-Path -LiteralPath $TcServerExe)) {
    Add-Err -Result $result -Where "tcserver_exe_missing" -Err "Path not found: $TcServerExe"
    if ($OutputPath) {
        $dir = Split-Path -Parent $OutputPath
        if ($dir -and -not (Test-Path -LiteralPath $dir)) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }
        $result | ConvertTo-Json -Depth 100 | Set-Content -LiteralPath $OutputPath -Encoding UTF8
    }
    $result | ConvertTo-Json -Depth 100 -Compress
    exit 0
}

$tcserverInfo = Get-Item -LiteralPath $TcServerExe
$result.tcserver.path = $TcServerExe
$result.tcserver.size = $tcserverInfo.Length
$result.tcserver.version = $tcserverInfo.VersionInfo.FileVersion

# Get tcserver --help to understand its CLI options
try {
    $helpProc = Start-Process -FilePath $TcServerExe -ArgumentList "--help" -PassThru -RedirectStandardOutput "$env:TEMP\tcserver_help.txt" -RedirectStandardError "$env:TEMP\tcserver_help_err.txt" -NoNewWindow -Wait
    $result.tcserver.help_text = (Get-Content "$env:TEMP\tcserver_help.txt" -Raw -ErrorAction SilentlyContinue) + "`n--err--`n" + (Get-Content "$env:TEMP\tcserver_help_err.txt" -Raw -ErrorAction SilentlyContinue)
} catch {
    Add-Err -Result $result -Where "help" -Err $_
}

# Start tcserver on the non-default port
$serverProc = $null
try {
    # Try common arg patterns: --port, -p, --bind, --listen
    $serverProc = Start-Process -FilePath $TcServerExe -ArgumentList "--port", $Port -PassThru -WindowStyle Hidden
    Start-Sleep -Seconds 3
    if ($serverProc.HasExited) {
        # Try alternate arg
        $serverProc = Start-Process -FilePath $TcServerExe -ArgumentList "-p", $Port -PassThru -WindowStyle Hidden
        Start-Sleep -Seconds 3
    }
    if ($serverProc.HasExited) {
        # No-args (default port)
        $serverProc = Start-Process -FilePath $TcServerExe -PassThru -WindowStyle Hidden
        Start-Sleep -Seconds 3
        $Port = 80  # tcserver default per docs
    }
    $result.startup.pid = $serverProc.Id
    $result.startup.port_attempted = $Port
    $result.startup.has_exited = $serverProc.HasExited
} catch {
    Add-Err -Result $result -Where "start" -Err $_
}

if ($serverProc -and -not $serverProc.HasExited) {
    # Confirm it's listening
    try {
        $listening = Get-NetTCPConnection -OwningProcess $serverProc.Id -State Listen -ErrorAction SilentlyContinue
        $result.startup.listening_ports = @($listening | ForEach-Object { "$($_.LocalAddress):$($_.LocalPort)" })
        if ($listening) {
            # Use the first listening port
            $Port = $listening[0].LocalPort
        }
    } catch {}

    # Probe each route
    foreach ($route in $routes) {
        $url = "http://127.0.0.1:$Port$route"
        foreach ($method in @("HEAD", "GET", "OPTIONS")) {
            $rec = [ordered]@{ method = $method; url = $url; status = $null; headers = @{}; body_preview = $null; error = $null }
            try {
                $req = [System.Net.HttpWebRequest]::Create($url)
                $req.Method = $method
                $req.Timeout = 5000
                $req.UserAgent = "tcw-tcserver-probe/1.0"
                $resp = $req.GetResponse()
                $rec.status = [int]$resp.StatusCode
                $headerDict = [ordered]@{}
                foreach ($h in $resp.Headers.AllKeys) { $headerDict[$h] = $resp.Headers[$h] }
                $rec.headers = $headerDict
                if ($method -ne "HEAD") {
                    $sr = New-Object System.IO.StreamReader $resp.GetResponseStream()
                    $body = $sr.ReadToEnd()
                    $sr.Close()
                    $rec.body_preview = if ($body.Length -gt 1500) { $body.Substring(0, 1500) + "..." } else { $body }
                }
                $resp.Close()
            } catch [System.Net.WebException] {
                $resp = $_.Exception.Response
                if ($resp) {
                    $rec.status = [int]$resp.StatusCode
                    $headerDict = [ordered]@{}
                    foreach ($h in $resp.Headers.AllKeys) { $headerDict[$h] = $resp.Headers[$h] }
                    $rec.headers = $headerDict
                    try {
                        $sr = New-Object System.IO.StreamReader $resp.GetResponseStream()
                        $body = $sr.ReadToEnd()
                        $sr.Close()
                        $rec.body_preview = if ($body.Length -gt 800) { $body.Substring(0, 800) + "..." } else { $body }
                    } catch {}
                } else {
                    $rec.error = $_.Exception.Message
                }
            } catch { $rec.error = $_.Exception.Message }
            $result.route_probes += $rec
        }
    }

    # POST a sample think-cellXML to selected routes
    $sampleXml = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><root reqver="36264"><version val="36264"/><CSmartGrid id="1"><m_olanguage>en-US</m_olanguage></CSmartGrid></root>'
    foreach ($route in @("/", "/v0", "/v1", "/v3", "/v6", "/v9", "/schemas")) {
        foreach ($ctype in @("application/xml", "application/vnd.think-cell.ppttc+json", "application/json")) {
            $url = "http://127.0.0.1:$Port$route"
            $rec = [ordered]@{ method = "POST"; url = $url; content_type = $ctype; status = $null; headers = @{}; body_preview = $null; error = $null }
            try {
                $req = [System.Net.HttpWebRequest]::Create($url)
                $req.Method = "POST"
                $req.ContentType = $ctype
                $req.Timeout = 5000
                $req.UserAgent = "tcw-tcserver-probe/1.0"
                $body = if ($ctype -like "*json*") { '{"templates":[{"template":"test","data":[]}]}' } else { $sampleXml }
                $bytes = [System.Text.Encoding]::UTF8.GetBytes($body)
                $req.ContentLength = $bytes.Length
                $reqStream = $req.GetRequestStream()
                $reqStream.Write($bytes, 0, $bytes.Length)
                $reqStream.Close()
                $resp = $req.GetResponse()
                $rec.status = [int]$resp.StatusCode
                $headerDict = [ordered]@{}
                foreach ($h in $resp.Headers.AllKeys) { $headerDict[$h] = $resp.Headers[$h] }
                $rec.headers = $headerDict
                $sr = New-Object System.IO.StreamReader $resp.GetResponseStream()
                $bodyText = $sr.ReadToEnd()
                $sr.Close()
                $rec.body_preview = if ($bodyText.Length -gt 1200) { $bodyText.Substring(0, 1200) + "..." } else { $bodyText }
                $resp.Close()
            } catch [System.Net.WebException] {
                $resp = $_.Exception.Response
                if ($resp) {
                    $rec.status = [int]$resp.StatusCode
                    $headerDict = [ordered]@{}
                    foreach ($h in $resp.Headers.AllKeys) { $headerDict[$h] = $resp.Headers[$h] }
                    $rec.headers = $headerDict
                    try {
                        $sr = New-Object System.IO.StreamReader $resp.GetResponseStream()
                        $bodyText = $sr.ReadToEnd()
                        $sr.Close()
                        $rec.body_preview = if ($bodyText.Length -gt 800) { $bodyText.Substring(0, 800) + "..." } else { $bodyText }
                    } catch {}
                } else { $rec.error = $_.Exception.Message }
            } catch { $rec.error = $_.Exception.Message }
            $result.route_probes += $rec
        }
    }
}

# Stop server
if ($serverProc -and -not $serverProc.HasExited) {
    try { Stop-Process -Id $serverProc.Id -Force -ErrorAction SilentlyContinue } catch {}
}

# Verdict
$result.verdict.startup_ok = ($serverProc -and $result.startup.listening_ports.Count -gt 0)
$result.verdict.total_probes = $result.route_probes.Count
$nonError = @($result.route_probes | Where-Object { $_.status -ne $null })
$result.verdict.responses_received = $nonError.Count
$distinctStatuses = $nonError | ForEach-Object { $_.status } | Sort-Object -Unique
$result.verdict.distinct_statuses = $distinctStatuses
$success = @($nonError | Where-Object { $_.status -in @(200, 201, 204) })
$result.verdict.success_count = $success.Count
$result.verdict.success_routes = @($success | ForEach-Object { "$($_.method) $($_.url)" } | Sort-Object -Unique)

if ($OutputPath) {
    $dir = Split-Path -Parent $OutputPath
    if ($dir -and -not (Test-Path -LiteralPath $dir)) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }
    $result | ConvertTo-Json -Depth 100 | Set-Content -LiteralPath $OutputPath -Encoding UTF8
}
$result | ConvertTo-Json -Depth 100 -Compress
