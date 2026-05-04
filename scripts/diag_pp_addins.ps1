<# Inventory all PP COM add-ins + recent crash events. #>
$ErrorActionPreference = "Continue"

Write-Output "=== HKCU PowerPoint Add-ins ==="
$kcu = "HKCU:\Software\Microsoft\Office\16.0\PowerPoint\Addins"
if (Test-Path $kcu) {
    Get-ChildItem $kcu | ForEach-Object {
        $p = Get-ItemProperty $_.PSPath -ErrorAction SilentlyContinue
        Write-Output "  $($_.PSChildName) | LoadBehavior=$($p.LoadBehavior) | FriendlyName=$($p.FriendlyName)"
    }
}

Write-Output ""
Write-Output "=== HKLM PowerPoint Add-ins ==="
$klm = "HKLM:\SOFTWARE\Microsoft\Office\16.0\PowerPoint\Addins"
if (Test-Path $klm) {
    Get-ChildItem $klm | ForEach-Object {
        $p = Get-ItemProperty $_.PSPath -ErrorAction SilentlyContinue
        Write-Output "  $($_.PSChildName) | LoadBehavior=$($p.LoadBehavior) | FriendlyName=$($p.FriendlyName)"
    }
}
$klm32 = "HKLM:\SOFTWARE\Wow6432Node\Microsoft\Office\16.0\PowerPoint\Addins"
if (Test-Path $klm32) {
    Write-Output "  --- Wow6432Node ---"
    Get-ChildItem $klm32 | ForEach-Object {
        $p = Get-ItemProperty $_.PSPath -ErrorAction SilentlyContinue
        Write-Output "  $($_.PSChildName) | LoadBehavior=$($p.LoadBehavior) | FriendlyName=$($p.FriendlyName)"
    }
}

Write-Output ""
Write-Output "=== Last 5 Office crash events ==="
Get-EventLog -LogName Application -Newest 50 -EntryType Error -ErrorAction SilentlyContinue |
    Where-Object { $_.Source -in @('Application Error', 'Microsoft Office 16') -and $_.Message -match 'POWERPNT|tcaddin|aitrx' } |
    Select-Object -First 5 |
    ForEach-Object {
        $msg = $_.Message
        if ($msg.Length -gt 600) { $msg = $msg.Substring(0, 600) }
        Write-Output "[$($_.TimeGenerated)] $($_.Source) #$($_.EventID)"
        Write-Output $msg
        Write-Output ""
    }

Write-Output ""
Write-Output "=== aitrx.dll references ==="
Get-ChildItem "C:\Program Files\Common Files\Microsoft Shared\Office16\AI" -ErrorAction SilentlyContinue | Format-Table Name, Length -AutoSize

Write-Output ""
Write-Output "=== Resiliency state ==="
$res = "HKCU:\Software\Microsoft\Office\16.0\PowerPoint\Resiliency"
foreach ($sub in @("StartupItems","DisabledItems","DocumentRecovery","CrashingAddinList")) {
    $k = "$res\$sub"
    if (Test-Path $k) {
        $vals = Get-ItemProperty $k -ErrorAction SilentlyContinue
        $count = ($vals.PSObject.Properties | Where-Object { $_.Name -notmatch '^PS' }).Count
        Write-Output "  $sub : $count entries"
    }
}
