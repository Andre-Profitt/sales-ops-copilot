$path = "\\Mac\Home\code\apps\sales-ops-copilot\scripts\run_in_session1.ps1"
$tokens = $null
$errors = $null
[System.Management.Automation.Language.Parser]::ParseFile($path, [ref]$tokens, [ref]$errors) | Out-Null
if ($errors -and $errors.Count -gt 0) {
    Write-Host "PARSE_FAIL" -ForegroundColor Red
    foreach ($e in $errors) {
        Write-Host "  Line $($e.Extent.StartLineNumber): $($e.Message)"
    }
    exit 1
} else {
    Write-Host "PARSE_OK"
    exit 0
}
