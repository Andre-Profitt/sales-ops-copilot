$ErrorActionPreference = "Continue"
Write-Host "=== Locate ppttc.exe + tcserver.exe + ppttc-schema.json ==="
$paths = @(
    "C:\Program Files (x86)\think-cell",
    "C:\Program Files\think-cell",
    "$env:LOCALAPPDATA\think-cell",
    "$env:APPDATA\think-cell"
)
foreach ($root in $paths) {
    if (Test-Path -LiteralPath $root) {
        Write-Host ""
        Write-Host "ROOT: $root"
        Get-ChildItem -LiteralPath $root -Recurse -File -ErrorAction SilentlyContinue |
            Where-Object { $_.Name -match "(?i)^(ppttc|tcserver|tcasr|tcgmail|tcindex|tcmail|tcnatmsg|tcperf)\.exe$|ppttc-schema\.json$" } |
            Select-Object FullName, Length, LastWriteTime |
            Format-Table -AutoSize | Out-String | Write-Host
    }
}
Write-Host ""
Write-Host "=== File association for .ppttc ==="
$assoc = & cmd /c "assoc .ppttc" 2>&1 | Out-String
Write-Host $assoc
$ftype = ""
if ($assoc -match "=(.+)$") { $ftype = $matches[1].Trim() }
if ($ftype) {
    $ft = & cmd /c "ftype $ftype" 2>&1 | Out-String
    Write-Host "ftype: $ft"
}
