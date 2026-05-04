$ErrorActionPreference = "Stop"
$paths = @(
    "C:\Program Files (x86)\think-cell",
    "C:\Program Files\think-cell"
)
Write-Host "=== think-cell install dirs ==="
foreach ($p in $paths) {
    if (Test-Path -LiteralPath $p) {
        Write-Host "FOUND: $p"
        Get-ChildItem -LiteralPath $p -Recurse -Filter "tcaddin.dll" | ForEach-Object {
            $stream = [System.IO.File]::OpenRead($_.FullName)
            $buf = New-Object byte[] 1024
            [void]$stream.Read($buf, 0, 1024)
            $stream.Close()
            $eLfanew = [BitConverter]::ToInt32($buf, 0x3c)
            $machine = [BitConverter]::ToUInt16($buf, $eLfanew + 4)
            $arch = switch ($machine) {
                0x8664 { "x86_64" }
                0xAA64 { "ARM64"  }
                0x14c  { "x86_32" }
                default { "0x{0:X4}" -f $machine }
            }
            Write-Host ("  {0}  arch={1}  size={2}" -f $_.FullName, $arch, $_.Length)
        }
    } else {
        Write-Host "MISSING: $p"
    }
}

Write-Host ""
Write-Host "=== Office bitness ==="
$reg32 = "HKLM:\SOFTWARE\WOW6432Node\Microsoft\Office\ClickToRun\Configuration"
$reg64 = "HKLM:\SOFTWARE\Microsoft\Office\ClickToRun\Configuration"
foreach ($r in @($reg32, $reg64)) {
    if (Test-Path $r) {
        $p = Get-ItemProperty $r
        Write-Host ("  {0}  Platform={1}  ProductReleaseIds={2}" -f $r, $p.Platform, $p.ProductReleaseIds)
    }
}
