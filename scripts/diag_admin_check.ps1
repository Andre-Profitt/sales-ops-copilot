$ErrorActionPreference = "Continue"
Write-Output "Current user: $env:USERNAME"
$prin = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
Write-Output "IsAdmin: $($prin.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator))"
Write-Output ""
Write-Output "=== whoami /groups (admin-related) ==="
& whoami /groups 2>&1 | Select-String "Admin|S-1-5-32-544|UAC|Mandatory"
Write-Output ""
Write-Output "=== local admins group members ==="
Get-LocalGroupMember -Group "Administrators" -ErrorAction SilentlyContinue | Format-Table Name, ObjectClass, PrincipalSource -AutoSize
