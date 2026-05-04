$ErrorActionPreference = "Continue"

Write-Output "=== Office version (post-rollback verification) ==="
$reg = Get-ItemProperty "HKLM:\SOFTWARE\Microsoft\Office\ClickToRun\Configuration" -ErrorAction SilentlyContinue
Write-Output "  ClickToRun VersionToReport: $($reg.VersionToReport)"
$ppExe = "C:\Program Files\Microsoft Office\root\Office16\POWERPNT.EXE"
Write-Output "  POWERPNT.EXE: $((Get-Item $ppExe).VersionInfo.FileVersion) modified $((Get-Item $ppExe).LastWriteTime)"
$mso = "C:\Program Files\Common Files\Microsoft Shared\Office16\mso20win32client.dll"
Write-Output "  mso20win32client.dll: $((Get-Item $mso).VersionInfo.FileVersion) modified $((Get-Item $mso).LastWriteTime)"

Write-Output ""
Write-Output "=== Latest PP crash (last 5 min) ==="
Get-EventLog -LogName Application -After (Get-Date).AddMinutes(-5) -EntryType Error -ErrorAction SilentlyContinue |
    Where-Object { $_.Message -match "POWERPNT" } |
    Select-Object -First 2 |
    ForEach-Object {
        $msg = if ($_.Message.Length -gt 600) { $_.Message.Substring(0, 600) } else { $_.Message }
        Write-Output "[$($_.TimeGenerated) $($_.Source) #$($_.EventID)]"
        Write-Output $msg
        Write-Output ""
    }

Write-Output ""
Write-Output "=== think-cell add-in state ==="
$kcu = "HKCU:\Software\Microsoft\Office\PowerPoint\Addins\thinkcell.addin"
if (Test-Path $kcu) {
    Get-ItemProperty $kcu | Format-List FriendlyName, LoadBehavior, Description
} else {
    Write-Output "  HKCU\...\thinkcell.addin: NOT REGISTERED"
}
$klm = "HKLM:\SOFTWARE\Microsoft\Office\PowerPoint\Addins\thinkcell.addin"
if (Test-Path $klm) {
    Get-ItemProperty $klm | Format-List FriendlyName, LoadBehavior, Description
} else {
    Write-Output "  HKLM\...\thinkcell.addin: NOT REGISTERED"
}

Write-Output ""
Write-Output "=== Resiliency state (anything in DisabledItems?) ==="
$di = "HKCU:\Software\Microsoft\Office\16.0\PowerPoint\Resiliency\DisabledItems"
if (Test-Path $di) {
    Get-ItemProperty $di -ErrorAction SilentlyContinue | ForEach-Object {
        $_.PSObject.Properties | Where-Object { $_.Name -notmatch "^PS" } | ForEach-Object {
            Write-Output "  DisabledItem: $($_.Name) = $($_.Value -join ',')"
        }
    }
}
$si = "HKCU:\Software\Microsoft\Office\16.0\PowerPoint\Resiliency\StartupItems"
if (Test-Path $si) {
    Get-ItemProperty $si -ErrorAction SilentlyContinue | ForEach-Object {
        $_.PSObject.Properties | Where-Object { $_.Name -notmatch "^PS" } | ForEach-Object {
            Write-Output "  StartupItem: $($_.Name) = $($_.Value -join ',')"
        }
    }
}

Write-Output ""
Write-Output "=== aitrx.dll (Microsoft Local AI conflict?) ==="
$ait = "C:\Program Files\Common Files\Microsoft Shared\Office16\AI\aitrx.dll"
if (Test-Path $ait) {
    Write-Output "  aitrx.dll: $((Get-Item $ait).VersionInfo.FileVersion) modified $((Get-Item $ait).LastWriteTime)"
}
