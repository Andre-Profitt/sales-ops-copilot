<#
Coordinate-based visual probe for the think-cell ribbon/gallery path.

This avoids expensive UIAutomation tree walks. It opens a disposable PowerPoint,
expands the ribbon, selects the think-cell tab, captures screenshots, then tries
one conservative click in the ribbon area. The output is used to decide whether
robotic chart insertion is viable.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string] $OutputDir,
    [switch] $TryClickElements
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

function Add-User32Mouse {
    $code = @"
using System;
using System.Runtime.InteropServices;
public static class SimCorpMouse2 {
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
    Add-User32Mouse
    [SimCorpMouse2]::SetCursorPos($X, $Y) | Out-Null
    Start-Sleep -Milliseconds 100
    [SimCorpMouse2]::mouse_event(0x0002, 0, 0, 0, [UIntPtr]::Zero)
    Start-Sleep -Milliseconds 80
    [SimCorpMouse2]::mouse_event(0x0004, 0, 0, 0, [UIntPtr]::Zero)
    Start-Sleep -Milliseconds $DelayMs
    return [ordered]@{ x = $X; y = $Y }
}

function Send-Keys {
    param([string] $Keys, [int] $DelayMs = 500)
    try {
        $ws = New-Object -ComObject WScript.Shell
        $ws.SendKeys($Keys)
        Start-Sleep -Milliseconds $DelayMs
    } catch {}
}

New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null
$result = [ordered]@{
    schema = "simcorp-thinkcell-mouse-gallery-path/v1"
    timestamp_utc = [DateTime]::UtcNow.ToString("o")
    output_dir = $OutputDir
    try_click_elements = [bool] $TryClickElements
    actions = @()
    screenshots = @()
    shape_count = $null
    errors = @()
}

$ppt = $null
$pres = $null
try {
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
    try {
        $isMinimized = $ppt.CommandBars.GetPressedMso("MinimizeRibbon")
        if ($isMinimized) {
            $ppt.CommandBars.ExecuteMso("MinimizeRibbon")
            Start-Sleep -Milliseconds 900
        }
    } catch {
        try {
            if ($ppt.CommandBars.Item("Ribbon").Height -lt 120) {
                $ppt.CommandBars.ExecuteMso("MinimizeRibbon")
                Start-Sleep -Milliseconds 900
            }
        } catch {}
    }
    $result.screenshots += Save-ScreenShot (Join-Path $OutputDir "01_ready.png")

    if ($TryClickElements) {
        $result.actions += [ordered]@{ action = "click_skip_tips"; click = (Click-Screen 832 626 700) }
        $result.screenshots += Save-ScreenShot (Join-Path $OutputDir "02_after_skip_tips.png")
        $result.actions += [ordered]@{ action = "click_insert_tab_elements_candidate"; click = (Click-Screen 1547 350 1400) }
        $result.screenshots += Save-ScreenShot (Join-Path $OutputDir "03_after_insert_tab_elements_candidate.png")
        $result.actions += [ordered]@{ action = "click_slide_candidate"; click = (Click-Screen 1280 620 1200) }
        $result.screenshots += Save-ScreenShot (Join-Path $OutputDir "04_after_slide_candidate.png")
    } else {
        Send-Keys "^{F1}" 700
        $result.actions += [ordered]@{ action = "send_ctrl_f1" }
        $result.screenshots += Save-ScreenShot (Join-Path $OutputDir "02_after_ctrl_f1.png")

        $result.actions += [ordered]@{ action = "click_thinkcell_tab"; click = (Click-Screen 184 190 1000) }
        $result.screenshots += Save-ScreenShot (Join-Path $OutputDir "03_after_thinkcell_tab_click.png")
    }

    $result.shape_count = $slide.Shapes.Count
    try { $pres.SaveCopyAs((Join-Path $OutputDir "mouse-gallery-probe.pptx")) } catch {}
} catch {
    $result.errors += [ordered]@{ where = "top_level"; message = $_.Exception.Message }
} finally {
    if ($pres) {
        try { $pres.Saved = -1 } catch {}
        try { $pres.Close() | Out-Null } catch {}
    }
    if ($ppt) {
        try { $ppt.Quit() | Out-Null } catch {}
    }
}

Write-JsonNoBom (Join-Path $OutputDir "thinkcell_mouse_gallery_path.json") $result 10
