<# Grep think-cell logs for AI-related references. #>
$ErrorActionPreference = "Continue"
$root = "$env:LocalAppData\think-cell_3000"

foreach ($log in @("POWERPNT_log.log", "tcupdate_log.log", "tcperf_log.log", "EXCEL_log.log")) {
    $f = Join-Path $root $log
    if (-not (Test-Path -LiteralPath $f)) { continue }
    Write-Output "=== $log ==="
    $matches = Select-String -LiteralPath $f -Pattern "AI|/core|app\.prod|Bearer|Authorization|completions|aiauth|webview2|sidepane|openai|anthropic|claude|gpt-" -SimpleMatch:$false -CaseSensitive:$false |
        Select-Object -First 30
    $matches | ForEach-Object {
        $line = $_.Line
        if ($line.Length -gt 250) { $line = $line.Substring(0, 250) }
        Write-Output "  L$($_.LineNumber): $line"
    }
    Write-Output ""
}
