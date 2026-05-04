<# Show think-cell folder + aiauthentication.bin state. #>
$ErrorActionPreference = "Continue"
$tc = "$env:APPDATA\think-cell"
Write-Output "think-cell folder: $tc"
Write-Output "exists: $(Test-Path -LiteralPath $tc)"
if (Test-Path -LiteralPath $tc) {
    Get-ChildItem -LiteralPath $tc | Format-Table Name, Length, LastWriteTime -AutoSize
}
Write-Output ""
Write-Output "POWERPNT processes:"
Get-Process POWERPNT -ErrorAction SilentlyContinue | Format-Table Id, MainWindowTitle, MainWindowHandle, StartTime -AutoSize
