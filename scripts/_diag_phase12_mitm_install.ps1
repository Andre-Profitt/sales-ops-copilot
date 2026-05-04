<#
Diagnostic — what state is mitmproxy install in on the VM?
Uses single-quoted strings to dodge PowerShell parser quirks with parens.
#>
$ErrorActionPreference = "Continue"

Write-Host '=== which python + pip ==='
Write-Host "python: $((Get-Command python -ErrorAction SilentlyContinue).Source)"
Write-Host "pip:    $((Get-Command pip -ErrorAction SilentlyContinue).Source)"

Write-Host ''
Write-Host '=== pip show mitmproxy ==='
pip show mitmproxy 2>&1 | Select-String -Pattern '^Name|^Version|^Location'

Write-Host ''
Write-Host '=== try direct import ==='
$pyImportTest = 'import mitmproxy; print("OK", mitmproxy.__file__)'
& python -c $pyImportTest 2>&1 | Select-Object -First 5

Write-Host ''
Write-Host '=== check site-packages for mitmproxy directory ==='
$sitepkgs = & python -c 'import sysconfig; print(sysconfig.get_paths()["purelib"])'
Write-Host "site-packages: $sitepkgs"
$mitmDir = Join-Path $sitepkgs 'mitmproxy'
if (Test-Path $mitmDir) {
    Write-Host 'mitmproxy/ DIR EXISTS'
    Get-ChildItem $mitmDir -Directory | Select-Object -First 5 -ExpandProperty Name | ForEach-Object { Write-Host "  $_" }
} else {
    Write-Host 'mitmproxy/ DIR MISSING'
}

Write-Host ''
Write-Host '=== reinstall mitmproxy fresh ==='
& python -m pip install --upgrade --force-reinstall mitmproxy 2>&1 | Select-Object -Last 5

Write-Host ''
Write-Host '=== verify after reinstall ==='
$pyVerify = 'import mitmproxy.version; print("VERSION", mitmproxy.version.VERSION)'
& python -c $pyVerify 2>&1
