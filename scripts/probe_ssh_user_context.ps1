Write-Host "WhoAmI: $(whoami)"
Write-Host "Session ID: $((Get-Process -PID $PID).SessionId)"
Write-Host "Interactive sessions (qwinsta):"
qwinsta 2>&1 | ForEach-Object { Write-Host "  $_" }
Write-Host ""
Write-Host "Is admin: $(([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator))"
Write-Host "Token elevation: $((whoami /priv | Select-String 'SeTakeOwnershipPrivilege' | Out-String).Trim())"
