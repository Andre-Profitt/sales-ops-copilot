<#
ODT rollback v3 -- ODT installer pre-staged on Mac at
\\Mac\Home\code\apps\sales-ops-copilot\state\thinkcell_bridge\odt\odt_installer.exe
Copy locally, self-extract, run setup.exe /configure ELEVATED.
#>
$ErrorActionPreference = "Continue"
Start-Transcript -Path "$env:USERPROFILE\odt_rollback.log" -Force | Out-Null

$workDir = "$env:USERPROFILE\odt_work"
Remove-Item -LiteralPath "$workDir\extracted" -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Path $workDir -Force | Out-Null

# 1. Copy ODT installer from Mac SMB to local (running .exe directly from UNC may fail)
$srcInstaller = "\\Mac\Home\code\apps\sales-ops-copilot\state\thinkcell_bridge\odt\odt_installer.exe"
$installerPath = "$workDir\OfficeDeploymentTool.exe"
Copy-Item -LiteralPath $srcInstaller -Destination $installerPath -Force
$sz = (Get-Item $installerPath).Length
Write-Host "[1] ODT installer: $installerPath ($sz bytes)"

# 2. Self-extract
$extractDir = "$workDir\extracted"
New-Item -ItemType Directory -Path $extractDir -Force | Out-Null
Write-Host "[2] Self-extracting..."
& $installerPath /quiet /extract:$extractDir
Start-Sleep -Seconds 5

if (-not (Test-Path "$extractDir\setup.exe")) {
    Write-Host "[!] setup.exe not found after extract. Listing $extractDir :"
    Get-ChildItem $extractDir -ErrorAction SilentlyContinue | Format-Table Name, Length, LastWriteTime -AutoSize
    Stop-Transcript | Out-Null
    exit 2
}
$setupExe = "$extractDir\setup.exe"
Write-Host "  setup.exe at: $setupExe ($((Get-Item $setupExe).Length) bytes)"

# 3. Configuration.xml
$configXml = @"
<Configuration>
  <Updates Enabled="FALSE" />
  <Add OfficeClientEdition="64" Channel="Current" Version="16.0.19822.20182" SourcePath="">
    <Product ID="O365ProPlusRetail">
      <Language ID="en-us" />
    </Product>
  </Add>
  <Display Level="Full" AcceptEULA="TRUE" />
  <Property Name="FORCEAPPSHUTDOWN" Value="TRUE" />
  <Property Name="SharedComputerLicensing" Value="0" />
</Configuration>
"@
$configPath = "$workDir\Configuration.xml"
Set-Content -LiteralPath $configPath -Value $configXml -Force
Write-Host "[3] Wrote: $configPath"

# 4. Stop Office apps
Get-Process POWERPNT, EXCEL, WINWORD, OUTLOOK, ONENOTE -ErrorAction SilentlyContinue | Stop-Process -Force
Start-Sleep -Seconds 3

# 5. Run setup.exe /configure ELEVATED (UAC prompt on user's desktop)
Write-Host "[4] Launching elevated setup.exe /configure ..."
Write-Host "    UAC PROMPT WILL APPEAR ON YOUR DESKTOP -- click YES"
try {
    $proc = Start-Process -FilePath $setupExe `
        -ArgumentList "/configure", "`"$configPath`"" `
        -Verb RunAs `
        -Wait `
        -PassThru `
        -ErrorAction Stop
    Write-Host "[5] setup.exe exited with code: $($proc.ExitCode)"
} catch {
    Write-Host "[!] launch failed: $($_.Exception.Message)"
    Stop-Transcript | Out-Null
    exit 3
}

# 6. Verify
$reg = Get-ItemProperty "HKLM:\SOFTWARE\Microsoft\Office\ClickToRun\Configuration" -ErrorAction SilentlyContinue
$final = $reg.VersionToReport
$ppExe = "C:\Program Files\Microsoft Office\root\Office16\POWERPNT.EXE"
$ppVer = if (Test-Path $ppExe) { (Get-Item $ppExe).VersionInfo.FileVersion } else { "(missing)" }
Write-Host ""
Write-Host "=== RESULT ==="
Write-Host "  registry VersionToReport: $final"
Write-Host "  POWERPNT.EXE FileVersion: $ppVer"
Write-Host "  STATUS: $(if ($final -eq '16.0.19822.20182') { 'SUCCESS' } else { 'NOT FLIPPED' })"
Stop-Transcript | Out-Null
