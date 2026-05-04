$ErrorActionPreference = "Continue"
Get-Process POWERPNT -ErrorAction SilentlyContinue | Select-Object Id, MainWindowHandle, MainWindowTitle, StartTime, Responding | Format-Table -AutoSize
Write-Output ""
Write-Output "=== think-cell add-in load state ==="
$kcu = "HKCU:\Software\Microsoft\Office\PowerPoint\Addins\thinkcell.addin"
$klm = "HKLM:\SOFTWARE\Microsoft\Office\PowerPoint\Addins\thinkcell.addin"
foreach ($k in @($kcu, $klm)) {
    if (Test-Path $k) {
        $p = Get-ItemProperty $k -ErrorAction SilentlyContinue
        Write-Output "  $k LoadBehavior=$($p.LoadBehavior)"
    }
}
Write-Output ""
Write-Output "=== Identity registered? ==="
$id = "HKCU:\Software\Microsoft\Office\16.0\Common\Identity\Identities"
if (Test-Path $id) {
    Get-ChildItem $id | Select-Object PSChildName | Format-Table -AutoSize
}
