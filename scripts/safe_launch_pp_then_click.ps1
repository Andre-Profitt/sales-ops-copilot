<#
Launch PP in /safe mode (bypasses the mso20win32client auth crash), then
manually load the think-cell add-in via COM, then run the click sequence.

/safe disables add-ins but they can be loaded later via COMAddIns.Connect.
This is a known workaround for Office add-in development.
#>
$ErrorActionPreference = "Continue"
Start-Transcript -Path "$env:USERPROFILE\tc_safe_launch.log" -Force | Out-Null
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

# Launch PP with /safe (skip add-ins + skip most auth)
Write-Host "[1] Launching POWERPNT.EXE /safe /N..."
$exe = "$env:ProgramFiles\Microsoft Office\root\Office16\POWERPNT.EXE"
Start-Process -FilePath $exe -ArgumentList "/safe", "/N" -PassThru | Out-Null

# Wait up to 45s for MainWindowTitle (Safe mode is also slower)
$deadline = (Get-Date).AddSeconds(45)
$pp = $null
while ((Get-Date) -lt $deadline) {
    $pp = Get-Process POWERPNT -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowHandle -ne 0 } | Select-Object -First 1
    if ($pp) { break }
    Start-Sleep -Milliseconds 500
}
if (-not $pp) {
    Write-Host "[!] PP /safe didn't launch in 45s"
    Stop-Transcript | Out-Null
    exit 1
}
Write-Host "[2] PP /safe up: pid=$($pp.Id) hwnd=$($pp.MainWindowHandle) title='$($pp.MainWindowTitle)'"

# Wait for stability
Start-Sleep -Seconds 5
$ppCheck = Get-Process -Id $pp.Id -ErrorAction SilentlyContinue
if (-not $ppCheck -or $ppCheck.MainWindowHandle -eq 0) {
    Write-Host "[!] PP zombied even in /safe mode (something deeper)"
    Stop-Transcript | Out-Null
    exit 2
}
Write-Host "[3] PP /safe stable after 5s wait"

# Connect to COM + load think-cell
Write-Host "[4] Connecting via COM + loading think-cell add-in..."
try {
    $ppt = [System.Runtime.InteropServices.Marshal]::GetActiveObject("PowerPoint.Application")
} catch {
    Write-Host "  GetActiveObject failed: $($_.Exception.Message)"
    Stop-Transcript | Out-Null
    exit 3
}

# List add-ins
Write-Host "  Available COMAddIns:"
foreach ($a in $ppt.COMAddIns) {
    Write-Host "    - ProgId=$($a.ProgId) Connected=$($a.Connect) Description=$($a.Description)"
}

# Try to connect think-cell
$tcAddin = $null
try {
    $tcAddin = $ppt.COMAddIns.Item("thinkcell.addin")
} catch {
    # Try alternate ProgIDs
    foreach ($pid in @("thinkcell.addin", "TCAddIn.PowerPoint", "thinkcell")) {
        try {
            $tcAddin = $ppt.COMAddIns.Item($pid)
            Write-Host "  Found via ProgID: $pid"
            break
        } catch {}
    }
}

if (-not $tcAddin) {
    Write-Host "[!] think-cell add-in not in COMAddIns list. Listing all again:"
    foreach ($a in $ppt.COMAddIns) {
        Write-Host "    - $($a.ProgId)"
    }
    Stop-Transcript | Out-Null
    exit 4
}

Write-Host "[5] Connecting think-cell add-in (Connect = true)..."
try {
    $tcAddin.Connect = $true
    Start-Sleep -Seconds 5
    Write-Host "  Connected: $($tcAddin.Connect)"
} catch {
    Write-Host "  Connect failed: $($_.Exception.Message)"
}

# Verify PP still alive
$ppCheck = Get-Process -Id $pp.Id -ErrorAction SilentlyContinue
if (-not $ppCheck -or $ppCheck.MainWindowHandle -eq 0) {
    Write-Host "[!] PP died after add-in load"
    Stop-Transcript | Out-Null
    exit 5
}
Write-Host "[6] PP still up after think-cell load"

# Now find think-cell tab via UIA
Start-Sleep -Seconds 3
[void] [W32]::ShowWindow($pp.MainWindowHandle, [W32]::SW_MAXIMIZE)
Start-Sleep -Milliseconds 500
[void] [W32]::SetForegroundWindow($pp.MainWindowHandle)
Start-Sleep -Seconds 2

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
    Write-Host "[!] think-cell tab not found in UIA (add-in didn't register ribbon)"
    Stop-Transcript | Out-Null
    exit 6
}
$tabBounds = $tab.Current.BoundingRectangle
Write-Host "[7] think-cell tab found at x=$($tabBounds.X) y=$($tabBounds.Y) w=$($tabBounds.Width) h=$($tabBounds.Height)"

# Click tab
$tabCenterX = [int]($tabBounds.X + $tabBounds.Width / 2)
$tabCenterY = [int]($tabBounds.Y + $tabBounds.Height / 2)
[void] [W32]::SetCursorPos($tabCenterX, $tabCenterY)
Start-Sleep -Milliseconds 200
[W32]::mouse_event([W32]::LDOWN, 0, 0, 0, [UIntPtr]::Zero)
Start-Sleep -Milliseconds 80
[W32]::mouse_event([W32]::LUP, 0, 0, 0, [UIntPtr]::Zero)
Start-Sleep -Seconds 2

# Spray clicks across the ribbon row
$ribbonY = [int]($tabBounds.Y + $tabBounds.Height + 50)
$ribbonStartX = [int]$tabBounds.X
Write-Host "[8] Spraying clicks at y=$ribbonY across $ribbonStartX+200..900..."
for ($dx = 200; $dx -le 900; $dx += 50) {
    $cx = [int]($ribbonStartX + $dx)
    [void] [W32]::SetCursorPos($cx, $ribbonY)
    Start-Sleep -Milliseconds 60
    [W32]::mouse_event([W32]::LDOWN, 0, 0, 0, [UIntPtr]::Zero)
    Start-Sleep -Milliseconds 50
    [W32]::mouse_event([W32]::LUP, 0, 0, 0, [UIntPtr]::Zero)
    Start-Sleep -Milliseconds 250
}

Start-Sleep -Seconds 2
[void] [W32]::SetForegroundWindow($pp.MainWindowHandle)
[System.Windows.Forms.SendKeys]::SendWait("hello")
Start-Sleep -Milliseconds 400
[System.Windows.Forms.SendKeys]::SendWait("{ENTER}")
Write-Host "[9] Sent 'hello' + Enter, waiting 12s for response..."
Start-Sleep -Seconds 12
Write-Host "[10] DONE"
Stop-Transcript | Out-Null
