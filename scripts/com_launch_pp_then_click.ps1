<#
Launch PowerPoint via COM activation (instead of POWERPNT.EXE), which bypasses
the mso20win32client.dll account-auth path that's been crashing. Then run
the same click sequence.
#>
$ErrorActionPreference = "Continue"
Start-Transcript -Path "$env:USERPROFILE\tc_com_launch.log" -Force | Out-Null
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName System.Windows.Forms

Add-Type @"
using System;
using System.Runtime.InteropServices;
public class W32 {
    [DllImport("user32.dll")] public static extern void mouse_event(uint f, uint dx, uint dy, uint dw, UIntPtr ex);
    [DllImport("user32.dll")] public static extern bool SetCursorPos(int X, int Y);
    [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
    [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr h, int n);
    public const uint LDOWN = 0x0002;
    public const uint LUP   = 0x0004;
    public const int SW_MAXIMIZE = 3;
    public const int SW_SHOWNORMAL = 1;
}
"@

# Kill any stragglers
Get-Process POWERPNT -ErrorAction SilentlyContinue | Stop-Process -Force
Start-Sleep -Seconds 3

# Clear Resiliency
$res = "HKCU:\Software\Microsoft\Office\16.0\PowerPoint\Resiliency"
foreach ($sub in @("StartupItems","DisabledItems","DocumentRecovery","CrashingAddinList")) {
    $k = "$res\$sub"
    if (Test-Path $k) {
        Get-ItemProperty $k -ErrorAction SilentlyContinue | ForEach-Object {
            $_.PSObject.Properties | Where-Object { $_.Name -notmatch "^PS" } | ForEach-Object {
                Remove-ItemProperty $k -Name $_.Name -Force -ErrorAction SilentlyContinue
            }
        }
    }
}

Write-Host "[1] Activating PowerPoint.Application via COM..."
try {
    $ppt = New-Object -ComObject PowerPoint.Application
    # Visible requires MsoTriState (msoTrue=-1, msoFalse=0, msoCTrue=1, msoTriStateMixed=-2)
    $ppt.Visible = -1
} catch {
    Write-Host "  COM activation failed: $($_.Exception.Message)"
    Stop-Transcript | Out-Null
    exit 1
}
Write-Host "  COM ppt activated. Adding presentation..."
try {
    $pres = $ppt.Presentations.Add(1)  # 1 = msoTrue (with window)
} catch {
    Write-Host "  Presentations.Add failed: $($_.Exception.Message)"
    Stop-Transcript | Out-Null
    exit 2
}
Start-Sleep -Seconds 6

# Get HWND directly from COM Application object (more reliable than Get-Process)
$hwnd = [IntPtr]::Zero
try {
    $hwnd = [IntPtr]$ppt.HWND
    Write-Host "[2a] $ppt.HWND: $hwnd"
} catch {
    Write-Host "[2a] $ppt.HWND failed: $($_.Exception.Message)"
}

# Also locate the process so we have pid
$ppPid = $null
$attempts = 0
while ($attempts -lt 15 -and -not $ppPid) {
    $procs = Get-Process POWERPNT -ErrorAction SilentlyContinue
    if ($procs) { $ppPid = $procs[0].Id; break }
    Start-Sleep -Milliseconds 500
    $attempts++
}
Write-Host "[2b] PP pid=$ppPid attempts=$attempts hwnd_from_com=$hwnd"

if ($hwnd -eq [IntPtr]::Zero) {
    Write-Host "[!] No HWND from COM. Aborting."
    Stop-Transcript | Out-Null
    exit 3
}

# Synthesize a $pp object with the fields we need
$pp = [PSCustomObject]@{
    Id = $ppPid
    MainWindowHandle = $hwnd
    MainWindowTitle = "(via COM)"
}
Write-Host "[2] PP up: pid=$($pp.Id) hwnd=$($pp.MainWindowHandle)"

# Maximize + foreground
[void] [W32]::ShowWindow($pp.MainWindowHandle, [W32]::SW_MAXIMIZE)
Start-Sleep -Milliseconds 500
[void] [W32]::SetForegroundWindow($pp.MainWindowHandle)
Start-Sleep -Seconds 2

# Verify still healthy
$ppNow = Get-Process -Id $pp.Id -ErrorAction SilentlyContinue
if (-not $ppNow -or $ppNow.MainWindowHandle -eq 0) {
    Write-Host "[!] PP zombied after maximize"
    Stop-Transcript | Out-Null
    exit 4
}

# Get window dimensions for proper click coordinates
Add-Type @"
using System;
using System.Runtime.InteropServices;
public class WinRect {
    [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT rc);
    [StructLayout(LayoutKind.Sequential)] public struct RECT { public int L, T, R, B; }
}
"@
$r = New-Object WinRect+RECT
[void] [WinRect]::GetWindowRect($pp.MainWindowHandle, [ref]$r)
Write-Host "  PP window bounds: L=$($r.L) T=$($r.T) R=$($r.R) B=$($r.B) (w=$($r.R - $r.L) h=$($r.B - $r.T))"

# Find think-cell tab via UIA
Write-Host "[3] Locating think-cell tab via UIA..."
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
    Write-Host "[!] think-cell tab not found in UIA tree (think-cell may not be loaded)"
    Stop-Transcript | Out-Null
    exit 5
}
$tabBounds = $tab.Current.BoundingRectangle
Write-Host "  think-cell tab: x=$($tabBounds.X) y=$($tabBounds.Y) w=$($tabBounds.Width) h=$($tabBounds.Height)"

# Select the tab (click on it)
$tabCenterX = [int]($tabBounds.X + $tabBounds.Width / 2)
$tabCenterY = [int]($tabBounds.Y + $tabBounds.Height / 2)
[void] [W32]::SetForegroundWindow($pp.MainWindowHandle)
Start-Sleep -Milliseconds 200
[void] [W32]::SetCursorPos($tabCenterX, $tabCenterY)
Start-Sleep -Milliseconds 200
[W32]::mouse_event([W32]::LDOWN, 0, 0, 0, [UIntPtr]::Zero)
Start-Sleep -Milliseconds 80
[W32]::mouse_event([W32]::LUP, 0, 0, 0, [UIntPtr]::Zero)
Start-Sleep -Seconds 2
Write-Host "[4] Clicked tab at ($tabCenterX, $tabCenterY)"

# Spray clicks at ribbon row below tab strip
$ribbonY = [int]($tabBounds.Y + $tabBounds.Height + 50)
Write-Host "[5] Spraying ribbon at y=$ribbonY..."

# AI button is in Elements group, ~3rd item. Spray X positions.
# Be smarter: first compute likely positions based on ribbon width.
$ribbonStartX = [int]$tabBounds.X
$xPositions = @()
for ($dx = 200; $dx -le 900; $dx += 50) {
    $xPositions += [int]($ribbonStartX + $dx)
}

foreach ($cx in $xPositions) {
    [void] [W32]::SetCursorPos($cx, $ribbonY)
    Start-Sleep -Milliseconds 60
    [W32]::mouse_event([W32]::LDOWN, 0, 0, 0, [UIntPtr]::Zero)
    Start-Sleep -Milliseconds 50
    [W32]::mouse_event([W32]::LUP, 0, 0, 0, [UIntPtr]::Zero)
    Start-Sleep -Milliseconds 200
}
Write-Host "  sprayed $($xPositions.Count) clicks across ribbon"

# Whatever clicked. If AI side pane opened, send "hello"
Start-Sleep -Seconds 2
[void] [W32]::SetForegroundWindow($pp.MainWindowHandle)
Start-Sleep -Milliseconds 500
[System.Windows.Forms.SendKeys]::SendWait("hello")
Start-Sleep -Milliseconds 400
[System.Windows.Forms.SendKeys]::SendWait("{ENTER}")
Write-Host "[6] Sent 'hello' + Enter"

Start-Sleep -Seconds 10
Write-Host "[7] Done -/core/ should have fired if a click landed correctly."
Stop-Transcript | Out-Null
