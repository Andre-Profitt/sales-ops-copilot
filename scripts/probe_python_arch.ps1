$ErrorActionPreference = "Stop"
$paths = @(
    "$env:LOCALAPPDATA\Programs\Python\Python313-amd64\python.exe",
    "$env:LOCALAPPDATA\Programs\Python\Python313-arm64\python.exe"
)
foreach ($p in $paths) {
    if (Test-Path -LiteralPath $p) {
        $bytes = [System.IO.File]::ReadAllBytes($p)
        $eLfanew = [BitConverter]::ToInt32($bytes, 0x3c)
        $machine = [BitConverter]::ToUInt16($bytes, $eLfanew + 4)
        $arch = switch ($machine) {
            0x8664 { "x86_64 (AMD64)" }
            0xAA64 { "ARM64" }
            0x14c  { "x86_32" }
            default { "unknown 0x{0:X4}" -f $machine }
        }
        Write-Host "$p -> PE machine: $arch (size=$($bytes.Length))"
    } else {
        Write-Host "missing: $p"
    }
}
