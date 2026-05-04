<# Inspect the think-cell_3000 folder — likely WebView2 user-data for AI feature. #>
$ErrorActionPreference = "Continue"
$root = "$env:LocalAppData\think-cell_3000"
if (-not (Test-Path -LiteralPath $root)) {
    Write-Output "$root not found"
    exit
}

Write-Output "=== top-level contents of $root ==="
Get-ChildItem -LiteralPath $root -Force | Format-Table Mode, LastWriteTime, Length, Name -AutoSize

Write-Output ""
Write-Output "=== full recursive tree (first 60) ==="
Get-ChildItem -LiteralPath $root -Recurse -File -Force -ErrorAction SilentlyContinue |
    Select-Object -First 60 |
    Format-Table @{n='size';e={$_.Length}}, @{n='mt';e={$_.LastWriteTime.ToString('yyyy-MM-dd HH:mm')}}, FullName -AutoSize

Write-Output ""
Write-Output "=== files containing 'Bearer' / 'Authorization' / 'app.prod.ai' / '/core/' ==="
$hits = 0
Get-ChildItem -LiteralPath $root -Recurse -File -Force -ErrorAction SilentlyContinue |
    Where-Object { $_.Length -lt 10485760 } |
    ForEach-Object {
        try {
            $bytes = [System.IO.File]::ReadAllBytes($_.FullName)
            $text = [System.Text.Encoding]::ASCII.GetString($bytes)
            if ($text -match "Bearer |Authorization|/core/|app\.prod\.ai|completions") {
                $script:hits++
                Write-Output "  HIT: $($_.FullName) ($($_.Length) bytes)"
                # Show context
                foreach ($pat in @("Bearer ", "Authorization", "/core/", "app.prod.ai", "completions")) {
                    $idx = $text.IndexOf($pat)
                    if ($idx -ge 0) {
                        $ctx = $text.Substring([Math]::Max(0, $idx-40), [Math]::Min(200, $text.Length - [Math]::Max(0, $idx-40)))
                        $ctx = $ctx -replace "[^ -~]", "."
                        Write-Output "     [$pat] ...$ctx..."
                    }
                }
            }
        } catch {}
    }
Write-Output ""
Write-Output "Total hits: $hits"
