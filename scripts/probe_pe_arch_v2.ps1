$ErrorActionPreference = "Stop"
$paths = @(
    "C:\Program Files (x86)\think-cell\tcaddin.dll",
    "C:\Program Files (x86)\think-cell\arm64\tcaddin.dll"
)
foreach ($p in $paths) {
    if (-not (Test-Path -LiteralPath $p)) { Write-Host "MISSING: $p"; continue }
    $bytes = [System.IO.File]::ReadAllBytes($p)
    $eLfanew = [BitConverter]::ToInt32($bytes, 0x3c)
    Write-Host "FILE: $p"
    Write-Host "  size: $($bytes.Length)"
    Write-Host "  e_lfanew: 0x$('{0:X4}' -f $eLfanew)"
    # PE signature should be at e_lfanew (4 bytes 'P','E',0,0)
    $sig = $bytes[$eLfanew..($eLfanew+3)]
    Write-Host "  PE sig (4 bytes): $('{0:X2}{1:X2}{2:X2}{3:X2}' -f $sig[0], $sig[1], $sig[2], $sig[3])"
    # Machine type at e_lfanew + 4 (2 bytes LE)
    $machine = [BitConverter]::ToUInt16($bytes, $eLfanew + 4)
    $arch = switch ($machine) {
        0x8664 { "x86_64 (AMD64)" }
        0xAA64 { "ARM64" }
        0x14c  { "x86_32 (i386)" }
        default { "0x{0:X4} unknown" -f $machine }
    }
    Write-Host "  machine: 0x$('{0:X4}' -f $machine) -> $arch"
    Write-Host ""
}
