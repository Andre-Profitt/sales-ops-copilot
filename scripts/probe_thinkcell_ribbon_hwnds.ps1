<#
Stage 2b — enumerate PowerPoint's child HWNDs and probe each via MSAA.

Top-level POWERPNT.EXE main-window IAccessible (OBJID_CLIENT) returns only a
thin shell with 7 simple children, no names. The rich ribbon accessibility
tree lives on child windows of class NetUIHWND / RibbonContainer / etc.

This probe enumerates all child HWNDs of the PP main window, calls
AccessibleObjectFromWindow(child, OBJID_CLIENT) on each, and reports the
class name + accName + accChildCount for the first level. The ribbon child
should be obvious: it'll have hundreds of children including the AI button.
#>
$ErrorActionPreference = "Continue"

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

public class HwndInfo {
    public IntPtr Hwnd;
    public string ClassName;
    public string WindowText;
    public int X, Y, W, H;
    public bool Visible;
    public string AccRootName;
    public int AccChildCount;
    public string AccError;
    public List<string> AccFirstChildNames = new List<string>();
}

public static class HwndProbe {
    [DllImport("user32.dll")] static extern bool EnumChildWindows(IntPtr hwnd, EnumChildProc cb, IntPtr lParam);
    [DllImport("user32.dll", CharSet = CharSet.Unicode)] static extern int GetClassName(IntPtr hwnd, StringBuilder lp, int max);
    [DllImport("user32.dll", CharSet = CharSet.Unicode)] static extern int GetWindowText(IntPtr hwnd, StringBuilder lp, int max);
    [DllImport("user32.dll")] static extern bool IsWindowVisible(IntPtr hwnd);
    [DllImport("user32.dll")] static extern bool GetWindowRect(IntPtr hwnd, out RECT rc);
    [DllImport("oleacc.dll")] static extern int AccessibleObjectFromWindow(IntPtr hwnd, uint id, ref Guid iid,
        [MarshalAs(UnmanagedType.Interface)] out IAccessible ppvObject);
    delegate bool EnumChildProc(IntPtr hwnd, IntPtr lParam);

    static readonly uint OBJID_CLIENT = 0xFFFFFFFC;
    static Guid IID_IAccessible = new Guid("618736E0-3C3D-11CF-810C-00AA00389B71");

    [StructLayout(LayoutKind.Sequential)] public struct RECT { public int L, T, R, B; }

    public static List<HwndInfo> Probe(IntPtr top) {
        var list = new List<HwndInfo>();
        EnumChildWindows(top, (h, lp) => {
            var sb = new StringBuilder(256);
            GetClassName(h, sb, 256);
            string cls = sb.ToString();
            sb.Clear();
            GetWindowText(h, sb, 1024);
            string txt = sb.ToString();
            RECT r;
            GetWindowRect(h, out r);

            var info = new HwndInfo {
                Hwnd = h,
                ClassName = cls,
                WindowText = txt,
                X = r.L, Y = r.T, W = r.R - r.L, H = r.B - r.T,
                Visible = IsWindowVisible(h)
            };

            // Skip invisible/zero-size windows to keep noise down — they
            // never hold the visible AI ribbon button.
            if (!info.Visible || info.W <= 1 || info.H <= 1) {
                list.Add(info);
                return true;
            }

            IAccessible acc;
            int hr = AccessibleObjectFromWindow(h, OBJID_CLIENT, ref IID_IAccessible, out acc);
            if (hr != 0 || acc == null) {
                info.AccError = "AccessibleObjectFromWindow hr=0x" + hr.ToString("X");
                list.Add(info);
                return true;
            }
            try { info.AccRootName = acc.get_accName(0); } catch (Exception e) { info.AccError = "rootName: " + e.Message; }
            try { info.AccChildCount = acc.accChildCount; } catch (Exception e) {
                if (info.AccError != null) info.AccError += "; ";
                info.AccError = (info.AccError ?? "") + "childCount: " + e.Message;
            }
            // Sample first 8 child names so we can recognize the ribbon
            for (int i = 1; i <= Math.Min(8, info.AccChildCount); i++) {
                try {
                    string n = acc.get_accName(i);
                    if (!string.IsNullOrEmpty(n)) info.AccFirstChildNames.Add(n);
                } catch {}
            }

            list.Add(info);
            return true;
        }, IntPtr.Zero);
        return list;
    }
}
"@

$out = "$env:USERPROFILE\tc_hwnds.json"
$result = [ordered]@{
    timestamp_utc = [DateTime]::UtcNow.ToString("o")
    pp_pid = $null
    hwnds = @()
    candidates = @()
}

$pp = Get-Process POWERPNT -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowTitle } | Select-Object -First 1
if (-not $pp) {
    $result.error = "no PP"
    $result | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $out -Force
    exit 1
}
$result.pp_pid = $pp.Id
$result.pp_title = $pp.MainWindowTitle
$result.pp_main_hwnd = "0x$('{0:X}' -f $pp.MainWindowHandle.ToInt64())"

$infos = [HwndProbe]::Probe($pp.MainWindowHandle)
foreach ($i in $infos) {
    $entry = [ordered]@{
        hwnd = "0x$('{0:X}' -f $i.Hwnd.ToInt64())"
        cls = $i.ClassName
        text = $i.WindowText
        loc = "$($i.X),$($i.Y),$($i.W)x$($i.H)"
        visible = $i.Visible
        accRootName = $i.AccRootName
        accChildCount = $i.AccChildCount
        accError = $i.AccError
        accFirstChildNames = $i.AccFirstChildNames
    }
    $result.hwnds += $entry
    # candidates: visible windows with rich accessibility (>10 children) OR
    # any with "AI" / ribbon-like names in the first-children sample
    if ($i.Visible -and (
        $i.AccChildCount -gt 10 -or
        ($i.AccFirstChildNames -join " " -match "(?i)\bAI\b|copilot|ribbon|tab"))) {
        $result.candidates += $entry
    }
}

$result | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath $out -Force
Write-Host "Hwnd probe done: $($result.hwnds.Count) windows, $($result.candidates.Count) ribbon candidates -> $out"
