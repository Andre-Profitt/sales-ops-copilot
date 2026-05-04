<#
ShowChartGallery HWND parameter probe.

Now-known signature: ShowChartGallery(Left, Top, Width, Height, HWND).
The HWND parameter means the gallery can be parented to an arbitrary
window. Question: can the gallery be rendered headlessly (or to a hidden
parent) so it can be enumerated programmatically?

Three test cases:
1. Pass HWND = 0 (NULL parent)
2. Pass a desktop HWND
3. Create a hidden System.Windows.Forms.Form and pass its handle

Each test wraps in try/catch with a short timeout. The existing
hidden-surface probe found ShowChartGallery returns 0x800706BA (RPC server
unavailable) under non-interactive SSH; this probe captures the same
behavior across HWND variants for documentation.
#>
[CmdletBinding()]
param(
    [string] $OutputPath
)

$ErrorActionPreference = "Continue"
$ProgressPreference = "SilentlyContinue"

function New-Result {
    [ordered]@{
        schema = "simcorp-thinkcell-gallery-hwnd-probe/v1"
        timestamp_utc = [DateTime]::UtcNow.ToString("o")
        machine = [ordered]@{}
        session = [ordered]@{}
        attempts = @()
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
$result.session.user_interactive = [Environment]::UserInteractive
$result.session.session_name = $env:SESSIONNAME

Add-Type -AssemblyName System.Windows.Forms -ErrorAction SilentlyContinue
$cs = @"
using System;
using System.Runtime.InteropServices;
namespace TcWin {
    public static class W {
        [DllImport("user32.dll")] public static extern IntPtr GetDesktopWindow();
    }
}
"@
try { Add-Type -TypeDefinition $cs -Language CSharp -ErrorAction Stop } catch {}

$ppt = $null
$tcPp = $null
$hiddenForm = $null
try {
    $ppt = New-Object -ComObject PowerPoint.Application
    $a = $ppt.COMAddIns | Where-Object { $_.ProgId -like "thinkcell*" } | Select-Object -First 1
    if (-not $a) { Add-ErrorRow -Result $result -Where "addin" -Err "thinkcell.addin missing"; throw "no addin" }
    $tcPp = $a.Object
    # Need a presentation/active-window for the gallery to have a context
    $pres = $ppt.Presentations.Add($false)
    $slide = $pres.Slides.Add(1, 1)

    $hiddenForm = New-Object System.Windows.Forms.Form
    $hiddenForm.WindowState = [System.Windows.Forms.FormWindowState]::Minimized
    $hiddenForm.ShowInTaskbar = $false
    $hiddenForm.Opacity = 0
    $hiddenForm.Show()
    $hiddenHandle = $hiddenForm.Handle
    $desktopHandle = [TcWin.W]::GetDesktopWindow()

    $cases = @(
        @{ tag = "hwnd_zero"; hwnd = [IntPtr]::Zero },
        @{ tag = "hwnd_desktop"; hwnd = $desktopHandle },
        @{ tag = "hwnd_hidden_form"; hwnd = $hiddenHandle }
    )
    foreach ($c in $cases) {
        $rec = [ordered]@{
            tag = $c.tag
            hwnd = $c.hwnd.ToInt64()
            success = $false
            error = $null
            hresult = $null
            duration_ms = 0
        }
        $sw = [System.Diagnostics.Stopwatch]::StartNew()
        try {
            $tcPp.ShowChartGallery(100, 100, 400, 300, $c.hwnd)
            $rec.success = $true
        } catch [System.Runtime.InteropServices.COMException] {
            $rec.hresult = "0x" + $_.Exception.HResult.ToString("X8")
            $rec.error = $_.Exception.Message
        } catch [System.Reflection.TargetInvocationException] {
            $rec.hresult = if ($_.Exception.InnerException) { "0x" + $_.Exception.InnerException.HResult.ToString("X8") } else { $null }
            $rec.error = if ($_.Exception.InnerException) { $_.Exception.InnerException.Message } else { $_.Exception.Message }
        } catch {
            $rec.error = $_.Exception.GetType().Name + ": " + $_.Exception.Message
        }
        $sw.Stop()
        $rec.duration_ms = [int]$sw.ElapsedMilliseconds
        $result.attempts += $rec
        Start-Sleep -Milliseconds 200
    }
    try { $pres.Close() } catch {}
} catch {
    Add-ErrorRow -Result $result -Where "main" -Err $_
} finally {
    if ($hiddenForm) { try { $hiddenForm.Close(); $hiddenForm.Dispose() } catch {} }
    if ($tcPp) { try { [System.Runtime.InteropServices.Marshal]::ReleaseComObject($tcPp) | Out-Null } catch {} }
    if ($ppt) { try { $ppt.Quit() } catch {}; try { [System.Runtime.InteropServices.Marshal]::ReleaseComObject($ppt) | Out-Null } catch {} }
}

$result.verdict.attempt_count = $result.attempts.Count
$result.verdict.successes = ($result.attempts | Where-Object { $_.success }).Count
$result.verdict.rpc_unavailable_count = ($result.attempts | Where-Object { $_.hresult -eq "0x800706BA" }).Count
$result.verdict.distinct_hresults = @($result.attempts | ForEach-Object { $_.hresult } | Where-Object { $_ } | Sort-Object -Unique)

if ($OutputPath) {
    $dir = Split-Path -Parent $OutputPath
    if ($dir -and -not (Test-Path -LiteralPath $dir)) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }
    $result | ConvertTo-Json -Depth 100 | Set-Content -LiteralPath $OutputPath -Encoding UTF8
}
$result | ConvertTo-Json -Depth 100 -Compress
