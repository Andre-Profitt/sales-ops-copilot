<#
Find think-cell-related WebView2 user data on the VM. The AI Side Pane uses
WebView2; if it's ever been used, there will be a user-data folder with
cookies, cache, localStorage etc. that reveal the request format.
#>
$ErrorActionPreference = "Continue"
Write-Output "=== WebView2 user-data folder candidates ==="
$candidates = @(
    "$env:LocalAppData\think-cell",
    "$env:AppData\think-cell",
    "$env:LocalAppData\Microsoft\EdgeWebView\User Data",
    "$env:LocalAppData\Microsoft\EdgeWebView",
    "$env:LocalAppData\Packages",
    "$env:ProgramFiles\think-cell",
    "$env:ProgramFiles(x86)\think-cell",
    "$env:LocalAppData\Microsoft\Office\16.0\Wef"
)
foreach ($c in $candidates) {
    if (Test-Path -LiteralPath $c) {
        $sz = "?"
        try { $sz = "{0:N0}" -f (Get-ChildItem -LiteralPath $c -Recurse -ErrorAction SilentlyContinue | Measure-Object Length -Sum).Sum } catch {}
        Write-Output "  EXISTS: $c (size=$sz)"
    } else {
        Write-Output "  missing: $c"
    }
}

Write-Output ""
Write-Output "=== Search for tcaddin / think-cell WebView2 cache folders ==="
Get-ChildItem -Path $env:LocalAppData -Recurse -Directory -ErrorAction SilentlyContinue -Force |
    Where-Object { $_.Name -match "think-cell|tcaddin|tc_" -or $_.FullName -match "think-cell|tcaddin" } |
    Select-Object -First 20 FullName

Write-Output ""
Write-Output "=== Look for files that might contain /core/ URL ==="
$searchRoots = @("$env:LocalAppData\think-cell", "$env:AppData\think-cell", "$env:LocalAppData\Microsoft\EdgeWebView")
foreach ($root in $searchRoots) {
    if (-not (Test-Path -LiteralPath $root)) { continue }
    Write-Output "--- searching $root ---"
    Get-ChildItem -LiteralPath $root -Recurse -File -ErrorAction SilentlyContinue -Force |
        ForEach-Object {
            try {
                $sample = [System.IO.File]::ReadAllBytes($_.FullName) | Select-Object -First 4096
                $text = [System.Text.Encoding]::ASCII.GetString($sample)
                if ($text -match "core/|app\.prod\.ai|Bearer|Authorization") {
                    Write-Output "  HIT: $($_.FullName) ($($_.Length) bytes)"
                }
            } catch {}
        } | Select-Object -First 20
}
