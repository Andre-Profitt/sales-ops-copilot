$screenshot = (Get-ChildItem $env:TEMP -Directory -Filter "edge_test_*" -ErrorAction SilentlyContinue | Sort-Object LastWriteTime -Desc | Select-Object -First 1).FullName + "\screenshot.png"
Write-Output "screenshot path: $screenshot"
if (Test-Path -LiteralPath $screenshot) {
    Copy-Item -LiteralPath $screenshot -Destination "\\Mac\Home\code\apps\sales-ops-copilot\state\thinkcell_bridge\edge_screenshot.png" -Force
    Write-Output "COPIED"
} else {
    Write-Output "NOT_FOUND"
}
