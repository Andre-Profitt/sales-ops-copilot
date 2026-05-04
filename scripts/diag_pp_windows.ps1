<#
List EVERY HWND owned by POWERPNT (or all PP processes), regardless of
whether it's the MainWindowHandle. Helps diagnose zombie PP state where
MainWindowHandle is 0 but the process still has windows.
#>
$ErrorActionPreference = "Continue"

Add-Type -TypeDefinition @"
using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;
using System.Text;
public static class WE {
    [DllImport("user32.dll")] static extern bool EnumWindows(EnumWindowsProc cb, IntPtr lParam);
    [DllImport("user32.dll")] static extern int GetWindowThreadProcessId(IntPtr h, out int pid);
    [DllImport("user32.dll", CharSet=CharSet.Unicode)] static extern int GetClassName(IntPtr h, StringBuilder s, int n);
    [DllImport("user32.dll", CharSet=CharSet.Unicode)] static extern int GetWindowText(IntPtr h, StringBuilder s, int n);
    [DllImport("user32.dll")] static extern bool IsWindowVisible(IntPtr h);
    delegate bool EnumWindowsProc(IntPtr h, IntPtr lp);
    public static List<string> All(int targetPid) {
        var r = new List<string>();
        EnumWindows((h, lp) => {
            int p; GetWindowThreadProcessId(h, out p);
            if (p != targetPid) return true;
            var cls = new StringBuilder(64); GetClassName(h, cls, 64);
            var txt = new StringBuilder(512); GetWindowText(h, txt, 512);
            r.Add("hwnd=0x" + h.ToInt64().ToString("X") + " cls=" + cls + " vis=" + IsWindowVisible(h) + " text='" + txt + "'");
            return true;
        }, IntPtr.Zero);
        return r;
    }
}
"@

Get-Process POWERPNT -ErrorAction SilentlyContinue | ForEach-Object {
    Write-Output "=== pid=$($_.Id) ==="
    $hwnds = [WE]::All($_.Id)
    Write-Output "  hwnd_count=$($hwnds.Count)"
    foreach ($h in $hwnds) { Write-Output "  $h" }
}
