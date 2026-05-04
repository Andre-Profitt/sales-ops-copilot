<#
Fire the full click sequence to make PowerPoint trigger the AI Side Pane.
Designed to run during a capture window — proxy + mitm + frida already set up
by capture_aicore_oneshot.ps1.

Sequence:
  1. Launch PowerPoint visibly (Session 1)
  2. Wait for MainWindowTitle
  3. SetForegroundWindow on PP
  4. UIA-select think-cell tab
  5. Compute AI button pixel position from tab bounds + known ribbon layout
  6. Win32 SendInput mouse-click at computed position
  7. Wait briefly, then send "hello\n" via SendKeys
#>
$ErrorActionPreference = "Continue"
Start-Transcript -Path "$env:USERPROFILE\tc_click_now.log" -Force | Out-Null
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName System.Windows.Forms

Add-Type @"
using System;
using System.Runtime.InteropServices;
public class Win32Mouse {
    [DllImport("user32.dll")] public static extern void mouse_event(uint f, uint dx, uint dy, uint dw, UIntPtr ex);
    [DllImport("user32.dll")] public static extern bool SetCursorPos(int X, int Y);
    [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
    [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr h, int n);
    public const uint LDOWN = 0x0002;
    public const uint LUP   = 0x0004;
    public const int SW_RESTORE = 9;
    public const int SW_SHOWNORMAL = 1;
    public const int SW_MAXIMIZE = 3;
}
"@

Write-Host "[1] Launching PowerPoint..."
$exe = "$env:ProgramFiles\Microsoft Office\root\Office16\POWERPNT.EXE"
Start-Process -FilePath $exe -ArgumentList "/N"

# Wait up to 30s for PP MainWindowTitle
$deadline = (Get-Date).AddSeconds(30)
$pp = $null
while ((Get-Date) -lt $deadline) {
    $pp = Get-Process POWERPNT -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowTitle } | Select-Object -First 1
    if ($pp) { break }
    Start-Sleep -Milliseconds 500
}
if (-not $pp) {
    Write-Host "ERROR: PP never came up"
    Stop-Transcript | Out-Null
    exit 1
}
Write-Host "[2] PP up: pid=$($pp.Id) hwnd=$($pp.MainWindowHandle) title='$($pp.MainWindowTitle)'"

# Wait a few seconds for ribbon to fully render
Start-Sleep -Seconds 4

# Bring to foreground + maximize
[void] [Win32Mouse]::ShowWindow($pp.MainWindowHandle, [Win32Mouse]::SW_MAXIMIZE)
Start-Sleep -Milliseconds 200
[void] [Win32Mouse]::SetForegroundWindow($pp.MainWindowHandle)
Start-Sleep -Milliseconds 500

# Verify still healthy after maximize
$ppNow = Get-Process -Id $pp.Id -ErrorAction SilentlyContinue
if (-not $ppNow -or $ppNow.MainWindowHandle -eq 0) {
    Write-Host "ERROR: PP zombied after maximize"
    Stop-Transcript | Out-Null
    exit 2
}

# Find + select think-cell tab via UIA
Write-Host "[3] Locating think-cell tab..."
$rootUIA = [System.Windows.Automation.AutomationElement]::RootElement
$cond = New-Object System.Windows.Automation.PropertyCondition(
    [System.Windows.Automation.AutomationElement]::ProcessIdProperty, $pp.Id
)
$ppWindows = $rootUIA.FindAll([System.Windows.Automation.TreeScope]::Children, $cond)

$tcCond = New-Object System.Windows.Automation.PropertyCondition(
    [System.Windows.Automation.AutomationElement]::NameProperty, "think-cell"
)
$tab = $null
foreach ($w in $ppWindows) {
    $found = $w.FindFirst([System.Windows.Automation.TreeScope]::Descendants, $tcCond)
    if ($found -and $found.Current.ControlType.LocalizedControlType -eq "tab item") {
        $tab = $found
        break
    }
}
if (-not $tab) {
    Write-Host "ERROR: no think-cell tab found via UIA"
    Stop-Transcript | Out-Null
    exit 3
}
$tabBounds = $tab.Current.BoundingRectangle
Write-Host "  think-cell tab bounds: x=$($tabBounds.X) y=$($tabBounds.Y) w=$($tabBounds.Width) h=$($tabBounds.Height)"

# Select the tab via UIA SelectionItem pattern
try {
    $sel = $tab.GetCurrentPattern([System.Windows.Automation.SelectionItemPattern]::Pattern)
    $sel.Select()
    Write-Host "  tab selected via UIA"
} catch {
    Write-Host "  UIA select failed, falling back to mouse click on tab"
    $tabCenterX = [int]($tabBounds.X + $tabBounds.Width / 2)
    $tabCenterY = [int]($tabBounds.Y + $tabBounds.Height / 2)
    [void] [Win32Mouse]::SetCursorPos($tabCenterX, $tabCenterY)
    Start-Sleep -Milliseconds 200
    [Win32Mouse]::mouse_event([Win32Mouse]::LDOWN, 0, 0, 0, [UIntPtr]::Zero)
    Start-Sleep -Milliseconds 80
    [Win32Mouse]::mouse_event([Win32Mouse]::LUP, 0, 0, 0, [UIntPtr]::Zero)
}
Start-Sleep -Seconds 2

# Compute AI button position from tab bounds + known ribbon layout
# think-cell tab structure (per officeUI XML earlier):
#   Group "Structure": ActivateThinkCell + box{NewSlide,Paste,FormatPainter} + AgendaMenu
#   Group "Elements":  LibraryDialog + ChartsGallery + AISidePane + box{TextBox,Pentagon,etc}
#   ... more groups
#
# The ribbon area starts ~at tab.Y + tab.Height (just below the tab strip).
# Each group is ~200px wide. AI button is in the 2nd group.
#
# Better approach: try a SPRAY of clicks in plausible AI button locations,
# since we know it's a "large" button in the Elements group.
# The Elements group should be roughly 200-400px right of the tab's left edge,
# and the ribbon row is roughly tab.Height below the tab strip.

$ribbonRowY = [int]($tabBounds.Y + $tabBounds.Height + 50)  # ~middle of ribbon row

# Spray candidate X positions across the Elements group region.
# think-cell tab is wide; spray every ~25px from x=350 to x=900 of the ribbon area.
# A "large" button is ~80px wide so collision likely if we hit somewhere in range.

$sprayPositions = @()
$ribbonStartX = [int]$tabBounds.X
# AI button is in Elements group. Structure group starts at tab.X.
# Empirically: Structure ~150-300px wide, Elements next group, AI ~3rd item.
# Spray around 200-700px right of ribbon start.
for ($dx = 250; $dx -le 800; $dx += 60) {
    $sprayPositions += [int]($ribbonStartX + $dx)
}

Write-Host "[4] Spraying clicks at ribbon row y=$ribbonRowY across $($sprayPositions.Count) X positions..."
Write-Host "    NOTE: a successful click on the AI button will open the side pane."
Write-Host "    The click sequence will then send 'hello' + Enter to whatever has focus."

# We do ONE click at a time, then check if the AI side pane opened by looking
# for a panel with 'AI' / 'thinkcell' / 'side pane' in its name.
# To save time within the capture window, just spray and then send the prompt.

# Bring PP to foreground again before clicking
[void] [Win32Mouse]::SetForegroundWindow($pp.MainWindowHandle)
Start-Sleep -Milliseconds 300

foreach ($cx in $sprayPositions) {
    [void] [Win32Mouse]::SetCursorPos($cx, $ribbonRowY)
    Start-Sleep -Milliseconds 80
    [Win32Mouse]::mouse_event([Win32Mouse]::LDOWN, 0, 0, 0, [UIntPtr]::Zero)
    Start-Sleep -Milliseconds 60
    [Win32Mouse]::mouse_event([Win32Mouse]::LUP, 0, 0, 0, [UIntPtr]::Zero)
    Start-Sleep -Milliseconds 250
    Write-Host "  clicked ($cx, $ribbonRowY)"
}

# Check if any new window appeared (the AI side pane is a docked panel)
Start-Sleep -Seconds 2
$ppAfter = Get-Process -Id $pp.Id -ErrorAction SilentlyContinue
if ($ppAfter -and $ppAfter.MainWindowHandle -ne 0) {
    Write-Host "[5] PP still healthy. Sending 'hello' + Enter via SendKeys..."
    [void] [Win32Mouse]::SetForegroundWindow($ppAfter.MainWindowHandle)
    Start-Sleep -Milliseconds 500
    [System.Windows.Forms.SendKeys]::SendWait("hello")
    Start-Sleep -Milliseconds 500
    [System.Windows.Forms.SendKeys]::SendWait("{ENTER}")
    Start-Sleep -Seconds 8  # let response come back
    Write-Host "[6] Done. /core/ should have fired if any click landed on AI button."
} else {
    Write-Host "[5] PP zombied - click landed somewhere bad."
}

Stop-Transcript | Out-Null
