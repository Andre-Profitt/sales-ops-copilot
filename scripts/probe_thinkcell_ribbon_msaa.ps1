<#
Stage 2 — MSAA / oleacc walk of the PowerPoint ribbon, take 3.

Prior attempts: PowerShell late-binding to System.__ComObject IAccessible failed
silently (accChildCount returned 0). [ComImport] typed wrapper still came back
as System.__ComObject across the `out` boundary. Fix: do the entire walk in C#,
return a flat .NET object[] to PowerShell. C# sees a real typed IAccessible
the whole way, no PowerShell interop in the hot path.

Approach (per Microsoft sample CSOfficeRibbonAccessibility):
  1. UIA select think-cell tab (the tab itself IS UIA-visible; only its
     contents are not).
  2. AccessibleObjectFromWindow(hwndPP, OBJID_CLIENT) -> IAccessible root.
  3. Recurse via accChildCount + get_accChild.
  4. Dump every accessible with a Name into a flat array.
  5. Write JSON; flag AI candidates.
#>
$ErrorActionPreference = "Continue"
Add-Type -AssemblyName UIAutomationClient

# Whole walk in C#. PowerShell just consumes a list of plain objects.
Add-Type -TypeDefinition @"
using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;

// IAccessible is a Dual interface — Office's RCW responds to dispid=ACC_CHILDCOUNT
// with PROPERTYGET but rejects dispid=ACC_NAME with DISP_E_MEMBERNOTFOUND when
// invoked as DISPATCH_METHOD. Use InterfaceIsDual to dispatch through the vtable
// (in IDL order) which is the canonical access path Office expects.
[ComImport, Guid("618736E0-3C3D-11CF-810C-00AA00389B71"),
 InterfaceType(ComInterfaceType.InterfaceIsDual)]
public interface IAccessible {
    [DispId(-5000)]  object accParent { get; }
    [DispId(-5001)]  int    accChildCount { get; }
    [DispId(-5002)]  object get_accChild([In, MarshalAs(UnmanagedType.Struct)] object varChild);
    [DispId(-5003)]  string get_accName([In, Optional, MarshalAs(UnmanagedType.Struct)] object varChild);
    [DispId(-5004)]  string get_accValue([In, Optional, MarshalAs(UnmanagedType.Struct)] object varChild);
    [DispId(-5005)]  string get_accDescription([In, Optional, MarshalAs(UnmanagedType.Struct)] object varChild);
    [DispId(-5006)]  object get_accRole([In, Optional, MarshalAs(UnmanagedType.Struct)] object varChild);
    [DispId(-5007)]  object get_accState([In, Optional, MarshalAs(UnmanagedType.Struct)] object varChild);
    [DispId(-5013)]  string get_accDefaultAction([In, Optional, MarshalAs(UnmanagedType.Struct)] object varChild);
    [DispId(-5015)]  void   accLocation(out int pxLeft, out int pyTop, out int pcxWidth, out int pcyHeight, [In, Optional, MarshalAs(UnmanagedType.Struct)] object varChild);
    [DispId(-5018)]  void   accDoDefaultAction([In, Optional, MarshalAs(UnmanagedType.Struct)] object varChild);
}

public class AccEntry {
    public int    Depth;
    public string Breadcrumb;
    public int    Idx;
    public string Name;
    public int    RoleInt;
    public string DefAction;
    public int    X, Y, W, H;
    public bool   IsFullChild;
}

public static class MsaaWalker {
    [DllImport("oleacc.dll")]
    static extern int AccessibleObjectFromWindow(
        IntPtr hwnd, uint id, ref Guid iid,
        [MarshalAs(UnmanagedType.Interface)] out IAccessible ppvObject);
    static readonly uint OBJID_CLIENT = 0xFFFFFFFC;
    static Guid IID_IAccessible = new Guid("618736E0-3C3D-11CF-810C-00AA00389B71");

    public static int RootChildCount;
    public static string RootName;
    public static List<string> Errors = new List<string>();

    public static List<AccEntry> Walk(IntPtr hwnd, int maxDepth) {
        Errors.Clear();
        var list = new List<AccEntry>();
        IAccessible root;
        int hr = AccessibleObjectFromWindow(hwnd, OBJID_CLIENT, ref IID_IAccessible, out root);
        if (hr != 0 || root == null) {
            Errors.Add("AccessibleObjectFromWindow hr=0x" + hr.ToString("X"));
            return list;
        }
        try { RootChildCount = root.accChildCount; } catch (Exception e) { Errors.Add("rootChildCount: " + e.Message); }
        try { RootName = root.get_accName(0); } catch (Exception e) { Errors.Add("rootName: " + e.Message); }

        list.Add(new AccEntry {
            Depth = 0, Breadcrumb = "<root>", Idx = 0,
            Name = RootName, RoleInt = SafeRole(root, 0),
            IsFullChild = true
        });

        WalkInto(root, 1, maxDepth, "<root>", list);
        return list;
    }

    static int SafeRole(IAccessible acc, object child) {
        try {
            object r = acc.get_accRole(child);
            if (r is int) return (int)r;
            if (r != null && r.GetType().IsValueType) return Convert.ToInt32(r);
        } catch {}
        return -1;
    }

    static void WalkInto(IAccessible acc, int depth, int maxDepth, string crumb, List<AccEntry> list) {
        if (depth > maxDepth) return;
        int count = 0;
        try { count = acc.accChildCount; } catch (Exception e) { Errors.Add("accChildCount@" + depth + ": " + e.Message); return; }
        if (count <= 0) return;
        for (int i = 1; i <= count; i++) {
            object childObj = null;
            try { childObj = acc.get_accChild(i); } catch {}

            string name = null;
            string defAction = null;
            int x=0, y=0, w=0, h=0;
            try { name = acc.get_accName(i); } catch {}
            try { defAction = acc.get_accDefaultAction(i); } catch {}
            try { acc.accLocation(out x, out y, out w, out h, i); } catch {}

            IAccessible childAcc = childObj as IAccessible;
            bool isFull = childAcc != null;

            if (!string.IsNullOrEmpty(name) || !string.IsNullOrEmpty(defAction)) {
                list.Add(new AccEntry {
                    Depth = depth, Breadcrumb = crumb, Idx = i,
                    Name = name, RoleInt = SafeRole(acc, i), DefAction = defAction,
                    X = x, Y = y, W = w, H = h, IsFullChild = isFull
                });
            }

            if (isFull) {
                string newCrumb = name != null ? crumb + " / " + name : crumb + " / [" + i + "]";
                WalkInto(childAcc, depth + 1, maxDepth, newCrumb, list);
            }
        }
    }
}

public static class W32 {
    [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
}
"@

$out = "$env:USERPROFILE\tc_msaa.json"
$result = [ordered]@{
    timestamp_utc = [DateTime]::UtcNow.ToString("o")
    pp_pid = $null
    pp_title = $null
    tab_selected = $false
    accessibles = @()
    candidates = @()
    errors = @()
}

$pp = Get-Process POWERPNT -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowTitle } | Select-Object -First 1
if (-not $pp) {
    $result.errors += "no PP with MainWindowTitle"
    $result | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $out -Force
    exit 1
}
$result.pp_pid = $pp.Id
$result.pp_title = $pp.MainWindowTitle
[void] [W32]::SetForegroundWindow($pp.MainWindowHandle)
Start-Sleep -Milliseconds 500

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

# Walk in C#
$entries = [MsaaWalker]::Walk($pp.MainWindowHandle, 14)
$result.root_child_count = [MsaaWalker]::RootChildCount
$result.root_name = [MsaaWalker]::RootName
foreach ($err in [MsaaWalker]::Errors) { $result.errors += $err }

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
Write-Host "MSAA walk done: $($result.accessible_count) accessibles, $($result.candidate_count) AI candidates -> $out"
