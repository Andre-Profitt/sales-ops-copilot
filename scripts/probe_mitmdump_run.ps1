$ProgressPreference = "SilentlyContinue"
$pyExe = "$env:LOCALAPPDATA\Programs\Python\Python313-amd64\python.exe"

# Try CA gen via -m and see what mitmdump actually says
Write-Host "=== invoking mitmdump in foreground for 8 seconds ==="
$psi = New-Object System.Diagnostics.ProcessStartInfo
$psi.FileName = $pyExe
$psi.Arguments = "-m mitmproxy.tools.dump -p 18891 --listen-host 127.0.0.1"
$psi.UseShellExecute = $false
$psi.RedirectStandardOutput = $true
$psi.RedirectStandardError = $true
$psi.CreateNoWindow = $true

$proc = [System.Diagnostics.Process]::Start($psi)
$stdoutTask = $proc.StandardOutput.ReadToEndAsync()
$stderrTask = $proc.StandardError.ReadToEndAsync()

Start-Sleep -Seconds 8
if (-not $proc.HasExited) {
    $proc.Kill()
    Write-Host "(was still running, killed)"
} else {
    Write-Host "(exited on its own with code $($proc.ExitCode))"
}
$stdout = $stdoutTask.Result
$stderr = $stderrTask.Result

Write-Host "--- STDOUT (first 60 lines) ---"
($stdout -split "`n" | Select-Object -First 60) | ForEach-Object { Write-Host $_ }
Write-Host "--- STDERR (first 60 lines) ---"
($stderr -split "`n" | Select-Object -First 60) | ForEach-Object { Write-Host $_ }

Write-Host "--- post-run: does ~/.mitmproxy exist? ---"
$caDir = "$env:USERPROFILE\.mitmproxy"
if (Test-Path -LiteralPath $caDir) {
    Get-ChildItem -LiteralPath $caDir -Force | Format-Table Name,Length -AutoSize | Out-String | Write-Host
} else {
    Write-Host "  $caDir does not exist"
}
