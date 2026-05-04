<#
Stage 2c — deep MSAA walk of the PowerPoint Ribbon HWND.

Stage 2b found the ribbon's accessible at NetUIHWND root='Ribbon' children=25.
Stage 2 was walking the wrong HWND (main PP window, only 7 simple children).
This probe finds the Ribbon HWND by class+name then walks its IAccessible tree
to depth N, dumping every named element with its breadcrumb so we can identify
the AI button.

Critical change vs. Stage 2: when a child IAccessible (VT_DISPATCH) exists,
walk it via `get_accChild(i)` then call accName(0)/accDefaultAction(0)/accRole(0)
on the CHILD itself — NOT parent.accName(i). Office's ribbon exposes child
items as full DISPATCH children, not simple children, and parent.accName(i)
returns null for those.
#>
$ErrorActionPreference = "Continue"
Add-Type -AssemblyName UIAutomationClient

Add-Type -TypeDefinition @"
using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;
using System.Text;

[ComImport, Guid("618736E0-3C3D-11CF-810C-00AA00389B71"),
 InterfaceType(ComInterfaceType.InterfaceIsDual)]
public interface IAccessible {
    [DispId(-5000)] object accParent { get; }
    [DispId(-5001)] int    accChildCount { get; }
    [DispId(-5002)] object get_accChild([In, MarshalAs(UnmanagedType.Struct)] object varChild);
    [DispId(-5003)] string get_accName([In, Optional, MarshalAs(UnmanagedType.Struct)] object varChild);
    [DispId(-5004)] string get_accValue([In, Optional, MarshalAs(UnmanagedType.Struct)] object varChild);
    [DispId(-5005)] string get_accDescription([In, Optional, MarshalAs(UnmanagedType.Struct)] object varChild);
    [DispId(-5006)] object get_accRole([In, Optional, MarshalAs(UnmanagedType.Struct)] object varChild);
    [DispId(-5007)] object get_accState([In, Optional, MarshalAs(UnmanagedType.Struct)] object varChild);
    [DispId(-5008)] string get_accHelp([In, Optional, MarshalAs(UnmanagedType.Struct)] object varChild);
    [DispId(-5009)] int    get_accHelpTopic(out string pszHelpFile, [In, Optional, MarshalAs(UnmanagedType.Struct)] object varChild);
    [DispId(-5010)] string get_accKeyboardShortcut([In, Optional, MarshalAs(UnmanagedType.Struct)] object varChild);
    [DispId(-5011)] object accFocus { get; }
    [DispId(-5012)] object accSelection { get; }
    [DispId(-5013)] string get_accDefaultAction([In, Optional, MarshalAs(UnmanagedType.Struct)] object varChild);
    [DispId(-5014)] void   accSelect(int flagsSelect, [In, Optional, MarshalAs(UnmanagedType.Struct)] object varChild);
    [DispId(-5015)] void   accLocation(out int pxLeft, out int pyTop, out int pcxWidth, out int pcyHeight, [In, Optional, MarshalAs(UnmanagedType.Struct)] object varChild);
    [DispId(-5016)] object accNavigate(int navDir, [In, Optional, MarshalAs(UnmanagedType.Struct)] object varStart);
    [DispId(-5017)] object accHitTest(int xLeft, int yTop);
    [DispId(-5018)] void   accDoDefaultAction([In, Optional, MarshalAs(UnmanagedType.Struct)] object varChild);
    [DispId(-5019)] void   set_accName([In, Optional, MarshalAs(UnmanagedType.Struct)] object varChild, string pszName);
    [DispId(-5020)] void   set_accValue([In, Optional, MarshalAs(UnmanagedType.Struct)] object varChild, string pszValue);
}

public class AccEntry {
    public int Depth;
    public string Breadcrumb;
    public int Idx;
    public string Name;
    public int RoleInt;
    public string DefAction;
    public int X, Y, W, H;
    public bool IsFullChild;
}

public static class RibbonWalker {
    [DllImport("user32.dll")] static extern bool EnumChildWindows(IntPtr hwnd, EnumChildProc cb, IntPtr lParam);
    [DllImport("user32.dll", CharSet = CharSet.Unicode)] static extern int GetClassName(IntPtr hwnd, StringBuilder lp, int max);
    [DllImport("oleacc.dll")] static extern int AccessibleObjectFromWindow(IntPtr hwnd, uint id, ref Guid iid,
        [MarshalAs(UnmanagedType.Interface)] out IAccessible ppvObject);
    delegate bool EnumChildProc(IntPtr hwnd, IntPtr lParam);

    static readonly uint OBJID_CLIENT = 0xFFFFFFFC;
    static Guid IID_IAccessible = new Guid("618736E0-3C3D-11CF-810C-00AA00389B71");

    public static List<string> Errors = new List<string>();
    public static IntPtr RibbonHwnd;

    // Find the Ribbon NetUIHWND by walking children, opening each, and checking accName=='Ribbon'.
    public static IntPtr FindRibbonHwnd(IntPtr top) {
        IntPtr found = IntPtr.Zero;
        EnumChildWindows(top, (h, lp) => {
            var sb = new StringBuilder(64);
            GetClassName(h, sb, 64);
            if (sb.ToString() != "NetUIHWND") return true;
            IAccessible acc;
            int hr = AccessibleObjectFromWindow(h, OBJID_CLIENT, ref IID_IAccessible, out acc);
            if (hr != 0 || acc == null) return true;
            try {
                string n = acc.get_accName(0);
                if (n == "Ribbon") { found = h; return false; }
            } catch {}
            return true;
        }, IntPtr.Zero);
        return found;
    }

    public static List<AccEntry> Walk(IntPtr ribbonHwnd, int maxDepth) {
        Errors.Clear();
        var list = new List<AccEntry>();
        IAccessible root;
        int hr = AccessibleObjectFromWindow(ribbonHwnd, OBJID_CLIENT, ref IID_IAccessible, out root);
        if (hr != 0 || root == null) {
            Errors.Add("ribbon AOFW hr=0x" + hr.ToString("X"));
            return list;
        }
        list.Add(MakeEntry(root, 0, "<ribbon>", 0));
        WalkInto(root, 1, maxDepth, "<ribbon>", list);
        return list;
    }

    static AccEntry MakeEntry(IAccessible acc, int depth, string crumb, int idx) {
        var e = new AccEntry { Depth = depth, Breadcrumb = crumb, Idx = idx, IsFullChild = true };
        try { e.Name = acc.get_accName(0); } catch {}
        try { e.DefAction = acc.get_accDefaultAction(0); } catch {}
        try {
            object r = acc.get_accRole(0);
            if (r is int) e.RoleInt = (int)r;
            else if (r != null && r.GetType().IsValueType) e.RoleInt = Convert.ToInt32(r);
            else e.RoleInt = -1;
        } catch { e.RoleInt = -1; }
        try { acc.accLocation(out e.X, out e.Y, out e.W, out e.H, 0); } catch {}
        return e;
    }

    static void WalkInto(IAccessible acc, int depth, int maxDepth, string crumb, List<AccEntry> list) {
        if (depth > maxDepth) return;
        int count = 0;
        try { count = acc.accChildCount; } catch (Exception ex) { Errors.Add("childCount@" + depth + ": " + ex.Message); return; }
        if (count <= 0) return;
        for (int i = 1; i <= count; i++) {
            object childObj = null;
            try { childObj = acc.get_accChild(i); } catch {}
            IAccessible childAcc = childObj as IAccessible;

            if (childAcc != null) {
                // Full child — query the CHILD with CHILDID_SELF=0
                var e = MakeEntry(childAcc, depth, crumb, i);
                list.Add(e);
                if (!string.IsNullOrEmpty(e.Name)) {
                    string nc = crumb + " / " + e.Name;
                    WalkInto(childAcc, depth + 1, maxDepth, nc, list);
                } else {
                    string nc = crumb + " / [#" + i + "]";
                    WalkInto(childAcc, depth + 1, maxDepth, nc, list);
                }
            } else {
                // Simple child — query the PARENT with the child's index
                var e = new AccEntry { Depth = depth, Breadcrumb = crumb, Idx = i, IsFullChild = false };
                try { e.Name = acc.get_accName(i); } catch {}
                try { e.DefAction = acc.get_accDefaultAction(i); } catch {}
                try {
                    object r = acc.get_accRole(i);
                    if (r is int) e.RoleInt = (int)r;
                    else if (r != null && r.GetType().IsValueType) e.RoleInt = Convert.ToInt32(r);
                    else e.RoleInt = -1;
                } catch { e.RoleInt = -1; }
                try { acc.accLocation(out e.X, out e.Y, out e.W, out e.H, i); } catch {}
                if (!string.IsNullOrEmpty(e.Name) || !string.IsNullOrEmpty(e.DefAction)) list.Add(e);
            }
        }
    }
}

public static class W32 {
    [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
}
"@

param(
    [switch]$SkipTabSelect
)
$out = "$env:USERPROFILE\tc_ribbon_deep.json"
$result = [ordered]@{
    timestamp_utc = [DateTime]::UtcNow.ToString("o")
    pp_pid = $null
    ribbon_hwnd = $null
    skip_tab_select = $SkipTabSelect.IsPresent
    accessibles = @()
    candidates = @()
    errors = @()
}

$pp = Get-Process POWERPNT -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowTitle } | Select-Object -First 1
if (-not $pp) {
    $result.errors += "no PP"
    $result | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $out -Force
    exit 1
}
$result.pp_pid = $pp.Id
$result.pp_title = $pp.MainWindowTitle
[void] [W32]::SetForegroundWindow($pp.MainWindowHandle)
Start-Sleep -Milliseconds 500

if (-not $SkipTabSelect) {
    # Select think-cell tab via UIA
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
        $result.errors += "select_tab: " + $_.Exception.Message
    }
    Start-Sleep -Milliseconds 1500
}

$ribbonHwnd = [RibbonWalker]::FindRibbonHwnd($pp.MainWindowHandle)
if ($ribbonHwnd -eq [IntPtr]::Zero) {
    $result.errors += "no Ribbon NetUIHWND under PP main"
    $result | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $out -Force
    exit 1
}
$result.ribbon_hwnd = "0x$('{0:X}' -f $ribbonHwnd.ToInt64())"

$entries = [RibbonWalker]::Walk($ribbonHwnd, 14)
foreach ($err in [RibbonWalker]::Errors) { $result.errors += $err }

$roleNames = @{
    -1=$null; 0="TitleBar"; 1="MenuBar"; 2="ScrollBar"; 8="Window"; 9="Client";
    10="MenuPopup"; 11="MenuItem"; 13="Application"; 14="Document"; 15="Pane";
    18="Border"; 19="Grouping"; 20="Separator"; 21="ToolBar"; 22="StatusBar";
    32="List"; 33="ListItem"; 36="PageTab"; 39="Graphic"; 40="StaticText";
    41="Text"; 42="PushButton"; 43="CheckButton"; 44="RadioButton"; 45="ComboBox";
    47="ProgressBar"; 50="Slider"; 55="ButtonDropdown"; 56="ButtonMenu";
    57="ButtonDropdownGrid"; 59="PageTabList"; 60="Clock"; 61="SplitButton"
}

foreach ($e in $entries) {
    $entry = [ordered]@{
        depth = $e.Depth
        breadcrumb = $e.Breadcrumb
        idx = $e.Idx
        name = $e.Name
        role = $(if ($roleNames.ContainsKey($e.RoleInt)) { $roleNames[$e.RoleInt] } else { "Role($($e.RoleInt))" })
        defAction = $e.DefAction
        loc = "$($e.X),$($e.Y),$($e.W)x$($e.H)"
        isFullChild = $e.IsFullChild
    }
    $result.accessibles += $entry
    if ($e.Name -match "(?i)\bAI\b|copilot|side ?pane|chart from ai|smart") {
        $result.candidates += $entry
    }
}

$result.accessible_count = $result.accessibles.Count
$result.candidate_count = $result.candidates.Count
$result | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath $out -Force
Write-Host "Ribbon deep walk: $($result.accessible_count) accessibles, $($result.candidate_count) AI candidates -> $out"
