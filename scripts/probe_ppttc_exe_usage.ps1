$ErrorActionPreference = "Continue"
$ppttc = "C:\Program Files (x86)\think-cell\ppttc.exe"
$schema = "C:\Program Files (x86)\think-cell\ppttc\ppttc-schema.json"

Write-Host "=== ppttc.exe size + signature ==="
$f = Get-Item -LiteralPath $ppttc
Write-Host "  Size: $($f.Length) bytes"
$sig = Get-AuthenticodeSignature -LiteralPath $ppttc
Write-Host "  Signed by: $($sig.SignerCertificate.Subject)"

Write-Host ""
Write-Host "=== ppttc.exe --help (stderr captured) ==="
$out = & $ppttc --help 2>&1 | Out-String
Write-Host $out

Write-Host "=== ppttc.exe (no args) ==="
$out2 = & $ppttc 2>&1 | Out-String
Write-Host $out2

Write-Host "=== ppttc-schema.json contents ==="
Get-Content -LiteralPath $schema -Raw | Write-Host

Write-Host ""
Write-Host "=== strings in ppttc.exe (UTF-16 + ASCII probe for usage hints) ==="
$bytes = [System.IO.File]::ReadAllBytes($ppttc)
$ascii = [System.Text.Encoding]::ASCII.GetString($bytes)
$matches = [regex]::Matches($ascii, '[a-zA-Z0-9\-_./\\]{8,80}')
$hints = $matches | ForEach-Object { $_.Value } | Where-Object {
    $_ -match '(?i)usage|^-[a-z]|^/[a-z]|input|output|template|\.pptx|\.ppttc|tcserver|render|stdin|verbose|silent|--'
} | Select-Object -Unique | Select-Object -First 40
$hints | ForEach-Object { Write-Host "  $_" }
