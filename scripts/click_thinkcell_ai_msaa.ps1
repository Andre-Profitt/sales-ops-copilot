<#
Stage 2 — MSAA / oleacc click of think-cell's AI ribbon button.

Use after probe_thinkcell_ribbon_msaa.ps1 surfaces an AI candidate. Walks the
MSAA tree from PowerPoint main window, finds the first accessible whose accName
matches the regex provided via -NamePattern (default: AI / Copilot / SidePane),
then calls IAccessible::accDoDefaultAction on it.

Pattern is case-insensitive substring/regex against accName. If multiple match,
the first one in tree order wins; pass a tighter -NamePattern to disambiguate.

Returns JSON with what was clicked + result of the default action.
#>
param(
    [string]$NamePattern = "(?i)\bAI\b|copilot|side ?pane|chart from ai|smart"
)
$ErrorActionPreference = "Continue"
Add-Type -AssemblyName UIAutomationClient

# IAccessible via [ComImport] — see probe_thinkcell_ribbon_msaa.ps1 header.
Add-Type @"
using System;
using System.Runtime.InteropServices;

[ComImport, Guid("618736E0-3C3D-11CF-810C-00AA00389B71"),
 InterfaceType(ComInterfaceType.InterfaceIsIDispatch)]
public interface IAccessible {
    [DispId(-5000)]  object accParent { get; }
    [DispId(-5001)]  int    accChildCount { get; }
    [DispId(-5002)]  object get_accChild([In, MarshalAs(UnmanagedType.Struct)] object varChild);
    [DispId(-5003)]  string get_accName([In, Optional, MarshalAs(UnmanagedType.Struct)] object varChild);
    [DispId(-5004)]  string get_accValue([In, Optional, MarshalAs(UnmanagedType.Struct)] object varChild);
    [DispId(-5005)]  string get_accDescription([In, Optional, MarshalAs(UnmanagedType.Struct)] object varChild);
    [DispId(-5006)]  object get_accRole([In, Optional, MarshalAs(UnmanagedType.Struct)] object varChild);
    [DispId(-5007)]  object get_accState([In, Optional, MarshalAs(UnmanagedType.Struct)] object varChild);
    [DispId(-5008)]  string get_accHelp([In, Optional, MarshalAs(UnmanagedType.Struct)] object varChild);
    [DispId(-5009)]  int    get_accHelpTopic(out string pszHelpFile, [In, Optional, MarshalAs(UnmanagedType.Struct)] object varChild);
    [DispId(-5010)]  string get_accKeyboardShortcut([In, Optional, MarshalAs(UnmanagedType.Struct)] object varChild);
    [DispId(-5011)]  object accFocus { get; }
    [DispId(-5012)]  object accSelection { get; }
    [DispId(-5013)]  string get_accDefaultAction([In, Optional, MarshalAs(UnmanagedType.Struct)] object varChild);
    [DispId(-5014)]  void   accSelect(int flagsSelect, [In, Optional, MarshalAs(UnmanagedType.Struct)] object varChild);
    [DispId(-5015)]  void   accLocation(out int pxLeft, out int pyTop, out int pcxWidth, out int pcyHeight, [In, Optional, MarshalAs(UnmanagedType.Struct)] object varChild);
    [DispId(-5016)]  object accNavigate(int navDir, [In, Optional, MarshalAs(UnmanagedType.Struct)] object varStart);
    [DispId(-5017)]  object accHitTest(int xLeft, int yTop);
    [DispId(-5018)]  void   accDoDefaultAction([In, Optional, MarshalAs(UnmanagedType.Struct)] object varChild);
    [DispId(-5019)]  void   set_accName([In, Optional, MarshalAs(UnmanagedType.Struct)] object varChild, string pszName);
    [DispId(-5020)]  void   set_accValue([In, Optional, MarshalAs(UnmanagedType.Struct)] object varChild, string pszValue);
}

public static class Oleacc {
    [DllImport("oleacc.dll")]
    public static extern int AccessibleObjectFromWindow(
        IntPtr hwnd, uint id, ref Guid iid,
        [MarshalAs(UnmanagedType.Interface)] out IAccessible ppvObject);
    public const uint OBJID_CLIENT = 0xFFFFFFFC;
    public static Guid IID_IAccessible = new Guid("618736E0-3C3D-11CF-810C-00AA00389B71");
}
public static class W32 {
    [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
}
"@

$out = "$env:USERPROFILE\tc_msaa_click.json"
$result = [ordered]@{
    timestamp_utc = [DateTime]::UtcNow.ToString("o")
    name_pattern = $NamePattern
    pp_pid = $null
    matches = @()
    clicked = $false
    errors = @()
}

$pp = Get-Process POWERPNT -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowTitle } | Select-Object -First 1
if (-not $pp) {
    $result.errors += [ordered]@{ where = "find_pp"; message = "no PP" }
    $result | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $out -Force
    exit 1
}
$result.pp_pid = $pp.Id
[void] [W32]::SetForegroundWindow($pp.MainWindowHandle)
Start-Sleep -Milliseconds 500

# Select think-cell tab via UIA first
try {
    $rootUIA = [System.Windows.Automation.AutomationElement]::RootElement
    $cond = New-Object System.Windows.Automation.PropertyCondition(
        [System.Windows.Automation.AutomationElement]::ProcessIdProperty, $pp.Id
    )
    $ppWindows = $rootUIA.FindAll([System.Windows.Automation.TreeScope]::Children, $cond)
    $tcCond = New-Object System.Windows.Automation.PropertyCondition(
        [System.Windows.Automation.AutomationElement]::NameProperty, "think-cell"
    )
    foreach ($w in $ppWindows) {
        $tab = $w.FindFirst([System.Windows.Automation.TreeScope]::Descendants, $tcCond)
        if ($tab -and $tab.Current.ControlType.LocalizedControlType -eq "tab item") {
            $sel = $tab.GetCurrentPattern([System.Windows.Automation.SelectionItemPattern]::Pattern)
            $sel.Select()
            $result.tab_selected = $true
            break
        }
    }
} catch {
    $result.errors += [ordered]@{ where = "select_tab"; message = $_.Exception.Message }
}
Start-Sleep -Milliseconds 1500

# Get IAccessible for PowerPoint main window — typed via [ComImport]
$rootAcc = $null
$hr = [Oleacc]::AccessibleObjectFromWindow(
    $pp.MainWindowHandle, [Oleacc]::OBJID_CLIENT,
    [ref][Oleacc]::IID_IAccessible, [ref]$rootAcc
)
if ($hr -ne 0 -or -not $rootAcc) {
    $result.errors += [ordered]@{ where = "AccessibleObjectFromWindow"; hresult = "0x$($hr.ToString('X'))" }
    $result | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $out -Force
    exit 1
}

$found = New-Object System.Collections.Generic.List[object]

function Walk {
    param([IAccessible]$acc, [int]$depth, [int]$maxDepth, [string]$breadcrumb)
    if ($depth -gt $maxDepth -or $script:found.Count -gt 0) { return }
    $count = 0
    try { $count = $acc.accChildCount } catch { return }
    if (-not $count) { return }
    for ($i = 1; $i -le $count; $i++) {
        if ($script:found.Count -gt 0) { return }
        $childObj = $null
        try { $childObj = $acc.get_accChild($i) } catch {}
        $name = $null; $defAction = $null
        try { $name = $acc.get_accName($i) } catch {}
        try { $defAction = $acc.get_accDefaultAction($i) } catch {}

        if ($name -and $name -match $script:patternRegex) {
            $entry = [ordered]@{
                breadcrumb = "$breadcrumb / $name"
                depth = $depth
                idx = $i
                name = $name
                defAction = $defAction
                accRef = $acc
                childIdRef = $i
            }
            $script:found.Add($entry)
            return
        }

        $childAcc = $childObj -as [IAccessible]
        if ($null -ne $childAcc) {
            $newCrumb = if ($name) { "$breadcrumb / $name" } else { "$breadcrumb / [$i]" }
            Walk -acc $childAcc -depth ($depth + 1) -maxDepth $maxDepth -breadcrumb $newCrumb
        }
    }
}

$script:patternRegex = $NamePattern
Walk -acc $rootAcc -depth 1 -maxDepth 14 -breadcrumb "<root>"

if ($found.Count -eq 0) {
    $result.errors += [ordered]@{ where = "find_match"; message = "no MSAA accessible matched pattern $NamePattern" }
    $result | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $out -Force
    exit 2
}

$target = $found[0]
$result.matches += [ordered]@{
    breadcrumb = $target.breadcrumb
    name = $target.name
    defAction = $target.defAction
}

# Click via accDoDefaultAction (typed call through the [ComImport] interface)
try {
    [IAccessible]$ref = $target.accRef
    $ref.accDoDefaultAction($target.childIdRef)
    $result.clicked = $true
    $result.click_method = "IAccessible::accDoDefaultAction"
} catch {
    $result.errors += [ordered]@{ where = "accDoDefaultAction"; message = $_.Exception.Message }
}

$result | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $out -Force
Write-Host "MSAA click: matched='$($target.name)' clicked=$($result.clicked)"
