$ErrorActionPreference = "Stop"
$src  = "C:\Program Files (x86)\think-cell\tcaddin.dll"
$dest = "\\Mac\Home\code\apps\sales-ops-copilot\state\thinkcell_bridge\tcaddin_dll_x64"
New-Item -ItemType Directory -Path $dest -Force | Out-Null
Copy-Item -LiteralPath $src -Destination "$dest\tcaddin.dll" -Force
$f = Get-Item -LiteralPath "$dest\tcaddin.dll"
Write-Host "copied: $($f.FullName) size=$($f.Length)"
