<#
Phase 12 — full capture with programmatic AI button click.

Runs as scheduled task in Session 1. Three click strategies in order:
  1. UIA: walk full tree (any ControlType, depth 20) → find element with
     name/autoId matching tc:AISidePane → InvokePattern
  2. UIA fallback: LegacyIAccessiblePattern.DoDefaultAction
  3. Win32: SendInput mouse_down + mouse_up at element BoundingRectangle
     center coordinates

Then captures for 45s while the AI feature fires its /core/ request.
Stops mitm + frida-trace. Restores state. Writes completion marker.
#>
$ErrorActionPreference = "Continue"
$ProgressPreference = "SilentlyContinue"
Add-Type -AssemblyName UIAutomationClient

# Win32 SendInput / mouse_event
Add-Type @"
using System;
using System.Runtime.InteropServices;
public class Win32Mouse {
    [DllImport("user32.dll")]
    public static extern void mouse_event(uint dwFlags, uint dx, uint dy, uint dwData, UIntPtr dwExtraInfo);
    [DllImport("user32.dll")]
    public static extern bool SetCursorPos(int X, int Y);
    [DllImport("user32.dll")]
    public static extern bool SetForegroundWindow(IntPtr hWnd);
    public const uint MOUSEEVENTF_LEFTDOWN = 0x0002;
    public const uint MOUSEEVENTF_LEFTUP = 0x0004;
}
"@

$ts = Get-Date -Format "yyyyMMdd-HHmmss"
$cap = "$env:USERPROFILE\tc_auth\$ts"
New-Item -ItemType Directory -Path $cap -Force | Out-Null
$marker = "$env:USERPROFILE\tc_phase12_capture_done.json"
$startMarker = "$env:USERPROFILE\tc_phase12_capture_started.json"

$state = [ordered]@{
    schema = "tc-phase12-with-ai-click/v1"
    started_utc = [DateTime]::UtcNow.ToString("o")
    capture_dir = $cap
    session_id = (Get-Process -PID $PID).SessionId
    interactive = [System.Environment]::UserInteractive
    steps = @()
    click_attempts = @()
    errors = @()
}
$state | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath $startMarker -Force

function Step($label, $action) {
    $entry = [ordered]@{ step = $label; ok = $true; note = "" }
    try {
        $r = & $action
        if ($r) { $entry.note = ($r -join " | ").Substring(0, [Math]::Min(300, ($r -join " | ").Length)) }
    } catch {
        $entry.ok = $false
        $entry.note = $_.Exception.Message.Substring(0, [Math]::Min(300, $_.Exception.Message.Length))
        $script:state.errors += [ordered]@{ step = $label; message = $_.Exception.Message }
    }
    $script:state.steps += $entry
}

# 1. Ensure POWERPNT running with a deck and a stable main window.
Step "ensure_powerpoint_running" {
    $pp = Get-Process POWERPNT -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowTitle } | Select-Object -First 1
    if ($pp) { return "already running pid=$($pp.Id) title='$($pp.MainWindowTitle)'" }

    # Kill any zombie PP processes (stuck without a window) before launching cold
    $zombies = Get-Process POWERPNT -ErrorAction SilentlyContinue | Where-Object { -not $_.MainWindowTitle }
    foreach ($z in $zombies) {
        try { Stop-Process -Id $z.Id -Force -ErrorAction Stop } catch {}
    }
    Start-Sleep -Seconds 2

    # Launch with /N (new presentation) /S (skip startup dialogs)
    $exe = "$env:ProgramFiles\Microsoft Office\root\Office16\POWERPNT.EXE"
    Start-Process -FilePath $exe -ArgumentList "/N"

    # Poll up to 30s for MainWindowTitle to populate
    $deadline = (Get-Date).AddSeconds(30)
    $pp = $null
    while ((Get-Date) -lt $deadline) {
        $pp = Get-Process POWERPNT -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowTitle } | Select-Object -First 1
        if ($pp) { break }
        Start-Sleep -Milliseconds 500
    }
    if ($pp) {
        "launched cold; pid=$($pp.Id) title='$($pp.MainWindowTitle)' after $((30 - ($deadline - (Get-Date)).TotalSeconds))s"
    } else {
        throw "POWERPNT launched but window never appeared within 30s; killed zombies=$($zombies.Count)"
    }
}

# 2. Connect think-cell add-in via COM
Step "connect_thinkcell_addin" {
    $ppt = [System.Runtime.InteropServices.Marshal]::GetActiveObject("PowerPoint.Application")
    $tc = $ppt.COMAddIns.Item("thinkcell.addin")
    if (-not $tc.Connect) { $tc.Connect = $true }
    if ($ppt.Presentations.Count -eq 0) {
        [void] $ppt.Presentations.Add(-1)
    }
    "addin connect=$($tc.Connect), presentations=$($ppt.Presentations.Count)"
}

# 3. Backup + delete aiauthentication.bin (force re-auth at AI invocation)
$tcDir = "$env:APPDATA\think-cell"
$aiauth = "$tcDir\aiauthentication.bin"
$bak = "$tcDir\aiauthentication.bin.bak"
Step "backup_and_delete_token" {
    if (Test-Path -LiteralPath $aiauth) {
        Copy-Item -LiteralPath $aiauth -Destination $bak -Force
        Remove-Item -LiteralPath $aiauth -Force
        "backed up to $bak AND deleted (forces refresh on next think-cell network call)"
    } else {
        "no token to backup"
    }
}

# 4. Set proxy + start mitm + start frida-trace (per parallel agent's pattern)
$mitmHar = "$cap\mitm.har"
$mitmFlow = "$cap\mitm.flow"
$mitmLog = "$cap\mitm.log"
$mitmdump = "$env:APPDATA\Python\Python313\Scripts\mitmdump.exe"
$fridaTrace = "$env:APPDATA\Python\Python313\Scripts\frida-trace.exe"
$reg = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Internet Settings"

Step "set_proxy" {
    Set-ItemProperty -Path $reg -Name ProxyEnable -Value 1
    Set-ItemProperty -Path $reg -Name ProxyServer -Value "127.0.0.1:8888"
    & netsh winhttp set proxy "127.0.0.1:8888" 2>&1 | Out-Null
    "proxy on"
}

Step "start_mitmdump" {
    $args = @("-p", "8888", "--listen-host", "127.0.0.1", "--set", "hardump=$mitmHar", "-w", $mitmFlow)
    $proc = Start-Process -FilePath $mitmdump -ArgumentList $args `
        -RedirectStandardOutput $mitmLog -RedirectStandardError "$mitmLog.err" `
        -PassThru -WindowStyle Hidden
    $proc.Id | Set-Content -LiteralPath "$cap\mitm.pid" -Force
    Start-Sleep -Seconds 2
    "mitm pid=$($proc.Id)"
}

# 5. Select think-cell tab via UIA + locate AISidePane element
$root = [System.Windows.Automation.AutomationElement]::RootElement
$walker = [System.Windows.Automation.TreeWalker]::ControlViewWalker

$ppPid = (Get-Process POWERPNT -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowTitle } | Select-Object -First 1).Id
$state.powerpoint_pid = $ppPid

$ppWindows = @()
$cond = New-Object System.Windows.Automation.PropertyCondition(
    [System.Windows.Automation.AutomationElement]::ProcessIdProperty, $ppPid
)
$ppWindows = $root.FindAll([System.Windows.Automation.TreeScope]::Children, $cond)

Step "select_thinkcell_tab" {
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
    if (-not $tab) { throw "no think-cell tab" }
    $sel = $tab.GetCurrentPattern([System.Windows.Automation.SelectionItemPattern]::Pattern)
    $sel.Select()
    Start-Sleep -Milliseconds 1200
    "selected, bounds=$($tab.Current.BoundingRectangle)"
}

# 6a. Pre-place custom Frida handlers BEFORE launching frida-trace.
# frida-trace only writes default stub handlers if no file already exists at
# __handlers__/<dll>/<func>.js. Module name in the folder must match `-i` case
# exactly (bcrypt.dll lowercase to match `-i bcrypt.dll!BCrypt*`). Handlers
# dump algorithm + HMAC key bytes + hashed input bytes + output hash bytes,
# everything we need to replay/forge the /core/ HMAC.
$handlerSrc = "\\Mac\Home\code\apps\sales-ops-copilot\scripts\frida_handlers"
$handlerDst = "$cap\__handlers__\bcrypt.dll"
Step "place_frida_custom_handlers" {
    New-Item -ItemType Directory -Path $handlerDst -Force | Out-Null
    $copied = @()
    foreach ($h in @("BCryptCreateHash.js", "BCryptHashData.js", "BCryptFinishHash.js")) {
        $src = Join-Path $handlerSrc $h
        if (Test-Path -LiteralPath $src) {
            Copy-Item -LiteralPath $src -Destination (Join-Path $handlerDst $h) -Force
            $copied += $h
        }
    }
    "placed=$($copied -join ',') into $handlerDst"
}

# 6b. Attach frida-trace AFTER ribbon stabilizes but BEFORE click
Step "attach_frida" {
    $log = "$cap\frida.log"
    $args = @(
        "-p", "$ppPid",
        "-i", "winhttp.dll!WinHttp*",
        "-i", "bcrypt.dll!BCrypt*",
        "-i", "kernelbase.dll!CryptUnprotectData",
        "-o", $log
    )
    $proc = Start-Process -FilePath $fridaTrace -ArgumentList $args `
        -WorkingDirectory $cap `
        -RedirectStandardOutput "$cap\frida_stdout.log" -RedirectStandardError "$cap\frida_stderr.log" `
        -PassThru -WindowStyle Hidden
    $proc.Id | Set-Content -LiteralPath "$cap\frida.pid" -Force
    Start-Sleep -Seconds 3
    "frida pid=$($proc.Id)"
}

# 7. Find AISidePane element + click via three strategies
function Find-AIElement {
    param($root, $depth, $maxDepth, [ref]$found)
    if ($depth -gt $maxDepth -or $found.Value) { return }
    try {
        $name = $root.Current.Name
        $autoId = $root.Current.AutomationId
        # AISidePane likely has Name "AI" or contains "AI"
        # Also check AutomationId for tc:AISidePane variants
        if ($name -match "(?i)^AI$|^AI Side Pane$|sidepane|copilot" -or
            $autoId -match "AISidePane|tc:AISidePane") {
            $found.Value = $root
            return
        }
    } catch {}
    try {
        $child = $script:walker.GetFirstChild($root)
        while ($null -ne $child -and -not $found.Value) {
            Find-AIElement -root $child -depth ($depth + 1) -maxDepth $maxDepth -found $found
            $child = $script:walker.GetNextSibling($child)
        }
    } catch {}
}

$aiElement = $null
[ref]$found = [ref]$aiElement
foreach ($w in $ppWindows) {
    Find-AIElement -root $w -depth 0 -maxDepth 20 -found $found
    if ($found.Value) { $aiElement = $found.Value; break }
}

# Strategy 0 (try first): SendKeys via Office "Tell Me" search (Alt+Q).
# Works for ANY ribbon command including custom add-in ones — Office search
# resolves commands by name string, bypassing UIA entirely.
Add-Type -AssemblyName System.Windows.Forms
Step "trigger_via_tell_me_search" {
    # Bring PowerPoint to foreground
    $hwnd = (Get-Process POWERPNT | Where-Object { $_.Id -eq $ppPid }).MainWindowHandle
    [void] [Win32Mouse]::SetForegroundWindow($hwnd)
    Start-Sleep -Milliseconds 500
    # Press Alt+Q to open Tell Me / Search
    [System.Windows.Forms.SendKeys]::SendWait("%q")
    Start-Sleep -Milliseconds 700
    # Type the AI feature name. think-cell's AI is "AI Side Pane" per the
    # customUI XML; "AI" alone usually matches.
    [System.Windows.Forms.SendKeys]::SendWait("AI")
    Start-Sleep -Milliseconds 1000
    # Press Down arrow + Enter to invoke the first matching item
    [System.Windows.Forms.SendKeys]::SendWait("{DOWN}")
    Start-Sleep -Milliseconds 200
    [System.Windows.Forms.SendKeys]::SendWait("{ENTER}")
    Start-Sleep -Milliseconds 1500
    "Alt+Q -> 'AI' -> Down -> Enter sequence sent"
}
$state.click_attempts += [ordered]@{ strategy = "Tell-Me Alt+Q"; ok = $true; note = "fired via SendKeys" }

if ($aiElement) {
    $bounds = $aiElement.Current.BoundingRectangle
    $state.ai_element = [ordered]@{
        name = $aiElement.Current.Name
        autoId = $aiElement.Current.AutomationId
        controlType = $aiElement.Current.ControlType.LocalizedControlType
        bounds = "$($bounds.X),$($bounds.Y),$($bounds.Width)x$($bounds.Height)"
        isEnabled = $aiElement.Current.IsEnabled
        isOffscreen = $aiElement.Current.IsOffscreen
    }

    # Strategy 1: UIA InvokePattern
    $clicked = $false
    try {
        $invPat = $aiElement.GetCurrentPattern(
            [System.Windows.Automation.InvokePattern]::Pattern
        )
        $invPat.Invoke()
        $state.click_attempts += [ordered]@{ strategy = "UIA InvokePattern"; ok = $true }
        $clicked = $true
    } catch {
        $state.click_attempts += [ordered]@{ strategy = "UIA InvokePattern"; ok = $false; error = $_.Exception.Message }
    }

    # Strategy 2: LegacyIAccessible.DoDefaultAction
    if (-not $clicked) {
        try {
            $legPat = $aiElement.GetCurrentPattern(
                [System.Windows.Automation.LegacyIAccessiblePattern]::Pattern
            )
            $legPat.DoDefaultAction()
            $state.click_attempts += [ordered]@{ strategy = "LegacyIAccessible.DoDefaultAction"; ok = $true }
            $clicked = $true
        } catch {
            $state.click_attempts += [ordered]@{ strategy = "LegacyIAccessible.DoDefaultAction"; ok = $false; error = $_.Exception.Message }
        }
    }

    # Strategy 3: Win32 SendInput at bounding rectangle center
    if (-not $clicked -and -not $aiElement.Current.IsOffscreen) {
        try {
            $cx = [int]($bounds.X + $bounds.Width / 2)
            $cy = [int]($bounds.Y + $bounds.Height / 2)
            # Bring PowerPoint to foreground first
            $hwnd = (Get-Process POWERPNT | Where-Object { $_.Id -eq $ppPid }).MainWindowHandle
            [void] [Win32Mouse]::SetForegroundWindow($hwnd)
            Start-Sleep -Milliseconds 300
            [void] [Win32Mouse]::SetCursorPos($cx, $cy)
            Start-Sleep -Milliseconds 200
            [Win32Mouse]::mouse_event([Win32Mouse]::MOUSEEVENTF_LEFTDOWN, 0, 0, 0, [UIntPtr]::Zero)
            Start-Sleep -Milliseconds 80
            [Win32Mouse]::mouse_event([Win32Mouse]::MOUSEEVENTF_LEFTUP, 0, 0, 0, [UIntPtr]::Zero)
            $state.click_attempts += [ordered]@{ strategy = "Win32 SendInput"; ok = $true; cx = $cx; cy = $cy }
            $clicked = $true
        } catch {
            $state.click_attempts += [ordered]@{ strategy = "Win32 SendInput"; ok = $false; error = $_.Exception.Message }
        }
    }
    $state.ai_clicked = $clicked
} else {
    $state.ai_element = "NOT_FOUND"
    $state.errors += [ordered]@{ step = "find_ai_element"; message = "no UIA element matching AI pattern" }
}

# 8. Capture window — wait for AI request to fire (or just any think-cell traffic)
Start-Sleep -Seconds 45

# 9. Snapshot the new token
Step "snapshot_token" {
    if (Test-Path -LiteralPath $aiauth) {
        Copy-Item -LiteralPath $aiauth -Destination "$cap\aiauthentication.bin.captured" -Force
        $sz = (Get-Item -LiteralPath "$cap\aiauthentication.bin.captured").Length
        "captured token size=$sz"
    } else {
        "no token"
    }
}

# 10. Stop frida + mitm
Step "stop_frida" {
    $fpid = Get-Content -LiteralPath "$cap\frida.pid" -ErrorAction SilentlyContinue
    if ($fpid) { Stop-Process -Id ([int]$fpid) -Force -ErrorAction SilentlyContinue }
    Start-Sleep -Seconds 1
}
Step "stop_mitmdump" {
    $mpid = Get-Content -LiteralPath "$cap\mitm.pid" -ErrorAction SilentlyContinue
    if ($mpid) { Stop-Process -Id ([int]$mpid) -Force -ErrorAction SilentlyContinue }
    Start-Sleep -Seconds 1
}

Step "reset_proxy" {
    & netsh winhttp reset proxy 2>&1 | Out-Null
    Set-ItemProperty -Path $reg -Name ProxyEnable -Value 0
}

Step "restore_token" {
    if (Test-Path -LiteralPath $bak) {
        Copy-Item -LiteralPath $bak -Destination $aiauth -Force
    }
}

# 11. Write completion marker
$state.ended_utc = [DateTime]::UtcNow.ToString("o")
$state.harSize = if (Test-Path -LiteralPath $mitmHar) { (Get-Item -LiteralPath $mitmHar).Length } else { 0 }
$state.flowSize = if (Test-Path -LiteralPath $mitmFlow) { (Get-Item -LiteralPath $mitmFlow).Length } else { 0 }
$state.fridaSize = if (Test-Path -LiteralPath "$cap\frida.log") { (Get-Item -LiteralPath "$cap\frida.log").Length } else { 0 }
$state | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath $marker -Force
