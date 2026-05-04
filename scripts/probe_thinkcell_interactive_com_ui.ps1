<#
Run think-cell UI-only COM methods from the logged-in console session.

The prior SSH-only run got RPC unavailable for StartTableInsertion and
ShowChartGallery. This probe runs the same calls from an interactive scheduled
task, captures screenshots, and records whether a chart/table object is added.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string] $OutputDir
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

function Save-ScreenShot {
    param([string] $Path)
    try {
        Add-Type -AssemblyName System.Drawing -ErrorAction Stop | Out-Null
        Add-Type -AssemblyName System.Windows.Forms -ErrorAction Stop | Out-Null
        $bounds = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds
        $bitmap = New-Object System.Drawing.Bitmap $bounds.Width, $bounds.Height
        $graphics = [System.Drawing.Graphics]::FromImage($bitmap)
        try {
            $graphics.CopyFromScreen($bounds.Location, [System.Drawing.Point]::Empty, $bounds.Size)
            $parent = Split-Path -Parent $Path
            if ($parent) { New-Item -ItemType Directory -Path $parent -Force | Out-Null }
            $bitmap.Save($Path, [System.Drawing.Imaging.ImageFormat]::Png)
            return [ordered]@{ path = $Path; ok = $true; width = $bounds.Width; height = $bounds.Height }
        } finally {
            $graphics.Dispose()
            $bitmap.Dispose()
        }
    } catch {
        return [ordered]@{ path = $Path; ok = $false; error = $_.Exception.Message }
    }
}

function Send-Keys {
    param([string] $Keys, [int] $DelayMs = 400)
    try {
        $ws = New-Object -ComObject WScript.Shell
        $ws.SendKeys($Keys)
        Start-Sleep -Milliseconds $DelayMs
    } catch {}
}

function Add-User32Mouse {
    $code = @"
using System;
using System.Runtime.InteropServices;
public static class SimCorpMouse {
  [DllImport("user32.dll")] public static extern bool SetCursorPos(int X, int Y);
  [DllImport("user32.dll")] public static extern void mouse_event(uint dwFlags, uint dx, uint dy, uint dwData, UIntPtr dwExtraInfo);
}
"@
    try {
        Add-Type -TypeDefinition $code -Language CSharp -ErrorAction Stop | Out-Null
    } catch {
        if ($_.Exception.Message -notmatch "already exists") { throw }
    }
}

function Click-Screen {
    param([int] $X, [int] $Y, [int] $DelayMs = 700)
    try {
        Add-User32Mouse
        [SimCorpMouse]::SetCursorPos($X, $Y) | Out-Null
        Start-Sleep -Milliseconds 120
        [SimCorpMouse]::mouse_event(0x0002, 0, 0, 0, [UIntPtr]::Zero)
        Start-Sleep -Milliseconds 80
        [SimCorpMouse]::mouse_event(0x0004, 0, 0, 0, [UIntPtr]::Zero)
        Start-Sleep -Milliseconds $DelayMs
        return [ordered]@{ x = $X; y = $Y; ok = $true }
    } catch {
        return [ordered]@{ x = $X; y = $Y; ok = $false; error = $_.Exception.Message }
    }
}

function Invoke-UiComAction {
    param(
        [string] $Name,
        [scriptblock] $Action,
        [object] $Slide,
        [object] $Result
    )
    $row = [ordered]@{
        name = $Name
        status = "not_run"
        shapes_before = $null
        shapes_after = $null
        elapsed_ms = $null
        return_value = $null
        error = $null
        screenshots = @()
    }
    try {
        $row.shapes_before = $Slide.Shapes.Count
        $row.screenshots += Save-ScreenShot (Join-Path $OutputDir ("before_" + $Name + ".png"))
        $sw = [System.Diagnostics.Stopwatch]::StartNew()
        $rv = & $Action
        $sw.Stop()
        Start-Sleep -Milliseconds 1200
        $row.status = "returned"
        $row.elapsed_ms = [int] $sw.ElapsedMilliseconds
        $row.return_value = if ($null -eq $rv) { $null } else { [string] $rv }
        $row.shapes_after = $Slide.Shapes.Count
        $row.screenshots += Save-ScreenShot (Join-Path $OutputDir ("after_" + $Name + ".png"))
        Send-Keys "{ESC}" 300
    } catch {
        $row.status = "error"
        $row.error = $_.Exception.Message
        try { $row.shapes_after = $Slide.Shapes.Count } catch {}
        $row.screenshots += Save-ScreenShot (Join-Path $OutputDir ("error_" + $Name + ".png"))
        Send-Keys "{ESC}" 300
    }
    $Result.actions += $row
}

New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null

$result = [ordered]@{
    schema = "simcorp-thinkcell-interactive-com-ui/v1"
    timestamp_utc = [DateTime]::UtcNow.ToString("o")
    output_dir = $OutputDir
    session = [ordered]@{}
    screenshots = @()
    actions = @()
    package_summary = [ordered]@{}
    verdict = [ordered]@{}
    errors = @()
}

$ppt = $null
$pres = $null
try {
    try {
        $result.session.user = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
        $result.session.session_id = (Get-Process -Id $PID).SessionId
        $result.session.interactive = [Environment]::UserInteractive
    } catch {}

    $ppt = New-Object -ComObject PowerPoint.Application
    $ppt.Visible = -1
    try { $ppt.WindowState = 3 } catch {}
    $pres = $ppt.Presentations.Add(-1)
    $slide = $pres.Slides.Add(1, 12)
    try { $ppt.ActiveWindow.View.GotoSlide(1) | Out-Null } catch {}
    try {
        Add-Type -AssemblyName Microsoft.VisualBasic -ErrorAction SilentlyContinue | Out-Null
        [Microsoft.VisualBasic.Interaction]::AppActivate($ppt.Caption) | Out-Null
    } catch {}
    Start-Sleep -Milliseconds 1600
    Send-Keys "{ESC}" 300
    $result.screenshots += Save-ScreenShot (Join-Path $OutputDir "01_ready.png")

    $tcPp = $ppt.COMAddIns.Item("thinkcell.addin").Object

    Invoke-UiComAction "start_table_insertion" {
        $tcPp.StartTableInsertion()
    } $slide $result

    Invoke-UiComAction "start_table_insertion_then_click" {
        $tcPp.StartTableInsertion()
        Start-Sleep -Milliseconds 900
        Click-Screen 1280 620 1800 | ConvertTo-Json -Compress
    } $slide $result

    Invoke-UiComAction "show_chart_gallery" {
        $tcPp.ShowChartGallery(100, 100, 700, 500, 0)
    } $slide $result

    $deck = Join-Path $OutputDir "interactive-com-ui-probe.pptx"
    try {
        $pres.SaveCopyAs($deck)
        $result.package_summary = [ordered]@{
            path = $deck
            size_bytes = (Get-Item -LiteralPath $deck).Length
            shape_count = $slide.Shapes.Count
        }
    } catch { Add-ErrorRow $result "save_package" $_ }

    $created = @($result.actions | Where-Object { $_.shapes_after -gt $_.shapes_before })
    $errors = @($result.actions | Where-Object { $_.status -eq "error" })
    $result.verdict = [ordered]@{
        any_action_returned = @($result.actions | Where-Object { $_.status -eq "returned" }).Count -gt 0
        any_action_created_shape = @($created).Count -gt 0
        created_shape_actions = @($created | ForEach-Object { $_.name })
        error_actions = @($errors | ForEach-Object { [ordered]@{ name = $_.name; error = $_.error } })
        shape_count = $slide.Shapes.Count
        conclusion = if (@($created).Count -gt 0) {
            "Interactive COM UI method created a shape. Inspect deck before any production use."
        } elseif (@($errors).Count -lt @($result.actions).Count) {
            "At least one interactive COM UI method returned, but none created a chart/table without further mouse placement."
        } else {
            "Interactive COM UI methods failed from the scheduled console path."
        }
    }
} catch {
    Add-ErrorRow $result "top_level" $_
} finally {
    if ($pres) {
        try { $pres.Saved = -1 } catch {}
        try { $pres.Close() | Out-Null } catch {}
    }
    if ($ppt) {
        try { $ppt.Quit() | Out-Null } catch {}
    }
}

Write-JsonNoBom (Join-Path $OutputDir "thinkcell_interactive_com_ui.json") $result 12
