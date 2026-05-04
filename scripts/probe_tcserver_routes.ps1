<#
Phase 4 probe — start tcserver.exe locally on the VM and characterize its 5 routes.

Routes enumerated from binary string mining (verified):
  /api
  /api/v1/search
  /auth
  /schemas
  /v0

Read-only behavior probe. Starts tcserver in a background process, waits for
its listen port to come up, then sends a battery of unauthenticated GET +
OPTIONS to characterize what each route returns. Stops the process before exiting.

Pre-conditions:
  - tcserver.exe present at C:\Program Files (x86)\think-cell\tcserver.exe (verified)
  - No PowerPoint or other think-cell tool actively using the binary
  - Free outbound localhost networking

Output goes to $OutputDir as tcserver_probe.json.

Usage:
  .\probe_tcserver_routes.ps1 -OutputDir "C:\tcserver-probe\<TS>"
                              -PortHint 8080
                              -DurationSeconds 60
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string] $OutputDir,

    [int] $PortHint = 8080,

    [int] $DurationSeconds = 60,

    [switch] $SkipStart  # if tcserver is already running
)

$ErrorActionPreference = "Continue"
$ProgressPreference = "SilentlyContinue"

if (-not (Test-Path -LiteralPath $OutputDir)) {
    New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null
}

function Log { param($m) Write-Host "[tcserver-probe] $m" }

$tcserverPath = "C:\Program Files (x86)\think-cell\tcserver.exe"
if (-not (Test-Path -LiteralPath $tcserverPath)) {
    throw "tcserver.exe not found at $tcserverPath"
}

$result = [ordered]@{
    schema           = "tc-tcserver-routes-probe/v1"
    started_utc      = [DateTime]::UtcNow.ToString("o")
    tcserver_path    = $tcserverPath
    tcserver_version = $null
    duration_seconds = $DurationSeconds
    port_attempted   = $PortHint
    listen_port      = $null
    spawn_pid        = $null
    spawn_args       = @()
    routes           = @()
    listening_ports  = @()
    errors           = @()
}

try {
    $vi = [System.Diagnostics.FileVersionInfo]::GetVersionInfo($tcserverPath)
    $result.tcserver_version = $vi.ProductVersion
} catch {
    $result.errors += [ordered]@{ where = "version"; message = $_.Exception.Message }
}

# ---------- 1. Start tcserver.exe ----------
$proc = $null
if (-not $SkipStart) {
    Log "Starting tcserver.exe (port hint $PortHint)"
    try {
        # tcserver.exe likely takes --port or similar. Try a few common patterns.
        # If it fails, capture stdout/stderr for diagnostics.
        $argLists = @(
            @("--port", "$PortHint"),
            @("-p", "$PortHint"),
            @("/port:$PortHint"),
            @()  # default args, let it pick its own port
        )
        foreach ($args in $argLists) {
            $stdoutLog = Join-Path $OutputDir "tcserver_stdout_$($args.Count).log"
            $stderrLog = Join-Path $OutputDir "tcserver_stderr_$($args.Count).log"
            try {
                $p = Start-Process -FilePath $tcserverPath -ArgumentList $args `
                    -RedirectStandardOutput $stdoutLog -RedirectStandardError $stderrLog `
                    -PassThru -NoNewWindow -ErrorAction Stop
                Start-Sleep -Seconds 3
                if (-not $p.HasExited) {
                    $proc = $p
                    $result.spawn_args = $args
                    $result.spawn_pid = $p.Id
                    Log "Started PID $($p.Id) with args: $($args -join ' ')"
                    break
                } else {
                    Log "Quick exit (code $($p.ExitCode)) with args: $($args -join ' ')"
                }
            } catch {
                Log "Spawn failed with args $($args -join ' '): $($_.Exception.Message)"
            }
        }
    } catch {
        $result.errors += [ordered]@{ where = "start"; message = $_.Exception.Message }
    }
}

# ---------- 2. Find which port it's actually listening on ----------
if ($proc -and -not $proc.HasExited) {
    $deadline = (Get-Date).AddSeconds(15)
    while ((Get-Date) -lt $deadline) {
        try {
            $tcp = Get-NetTCPConnection -OwningProcess $proc.Id -State Listen -ErrorAction SilentlyContinue
            if ($tcp) {
                foreach ($conn in $tcp) {
                    $result.listening_ports += $conn.LocalPort
                }
                $result.listen_port = $tcp[0].LocalPort
                Log "tcserver listening on port(s): $($result.listening_ports -join ', ')"
                break
            }
        } catch {}
        Start-Sleep -Milliseconds 500
    }
}

if (-not $result.listen_port) {
    $result.listen_port = $PortHint  # try the hint anyway
    Log "Could not detect listen port via TCP enumeration; defaulting to $PortHint"
}

# ---------- 3. Probe the 5 documented routes + a few siblings ----------
$base = "http://127.0.0.1:$($result.listen_port)"
$routeProbes = @(
    @{ method = "GET";     path = "/" },
    @{ method = "OPTIONS"; path = "/" },
    @{ method = "GET";     path = "/api" },
    @{ method = "OPTIONS"; path = "/api" },
    @{ method = "POST";    path = "/api"; body = "" },
    @{ method = "GET";     path = "/api/v1" },
    @{ method = "GET";     path = "/api/v1/search" },
    @{ method = "POST";    path = "/api/v1/search"; body = '{"query":""}'; ct = "application/json" },
    @{ method = "GET";     path = "/auth" },
    @{ method = "POST";    path = "/auth"; body = "" },
    @{ method = "GET";     path = "/schemas" },
    @{ method = "GET";     path = "/v0" },
    @{ method = "GET";     path = "/v0/health" },
    # ppttc submission endpoint — known mime
    @{ method = "POST";    path = "/"; body = '{"slides":[]}'; ct = "application/vnd.think-cell.ppttc+json" },
    # standard health/discovery
    @{ method = "GET";     path = "/health" },
    @{ method = "GET";     path = "/healthz" },
    @{ method = "GET";     path = "/version" }
)

Log "Probing $($routeProbes.Count) routes against $base"
foreach ($probe in $routeProbes) {
    $url = $base + $probe.path
    $row = [ordered]@{
        method = $probe.method
        url    = $url
        ct_sent = $probe.ct
        body_size_sent = if ($probe.body) { ($probe.body).Length } else { 0 }
    }
    try {
        $headers = @{}
        if ($probe.ct) { $headers["Content-Type"] = $probe.ct }
        $resp = if ($probe.method -in @("POST", "PUT")) {
            Invoke-WebRequest -Method $probe.method -Uri $url -Headers $headers `
                -Body ($probe.body) -TimeoutSec 8 -SkipHttpErrorCheck -UseBasicParsing
        } else {
            Invoke-WebRequest -Method $probe.method -Uri $url -Headers $headers `
                -TimeoutSec 8 -SkipHttpErrorCheck -UseBasicParsing
        }
        $row.status = [int] $resp.StatusCode
        $row.headers = @{}
        foreach ($k in $resp.Headers.Keys) { $row.headers[$k] = $resp.Headers[$k] }
        $row.body_size = $resp.Content.Length
        if ($resp.Content) {
            $headBytes = if ($resp.Content -is [byte[]]) { $resp.Content[0..([Math]::Min(599, $resp.Content.Length - 1))] } else { ([Text.Encoding]::UTF8.GetBytes($resp.Content)) }
            $row.body_head = [Text.Encoding]::UTF8.GetString($headBytes[0..([Math]::Min(599, $headBytes.Length - 1))])
        } else {
            $row.body_head = ""
        }
    } catch {
        $row.error = $_.Exception.Message
    }
    $result.routes += $row
    Log "  $($probe.method) $($probe.path): status=$($row.status) size=$($row.body_size)B"
}

# ---------- 4. Stop tcserver if we started it ----------
if ($proc -and -not $proc.HasExited) {
    Log "Stopping tcserver PID $($proc.Id)"
    try { Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue } catch {}
}

$result.ended_utc = [DateTime]::UtcNow.ToString("o")
$out = Join-Path $OutputDir "tcserver_probe.json"
$result | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath $out -Encoding UTF8
Log "Wrote $out"

# Echo brief summary
Log ""
Log "=== Summary ==="
Log "tcserver_version: $($result.tcserver_version)"
Log "spawn_pid: $($result.spawn_pid)  args: $($result.spawn_args -join ' ')"
Log "listen_port: $($result.listen_port)  all_ports: $($result.listening_ports -join ', ')"
Log "routes probed: $($result.routes.Count)"
foreach ($r in $result.routes) {
    Log "  $($r.method) $($r.url): $(if ($r.error) { 'ERR ' + $r.error.Substring(0, [Math]::Min(60, $r.error.Length)) } else { "$($r.status)  $($r.body_size)B" })"
}
