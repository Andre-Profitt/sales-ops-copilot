<#
ODT rollback v2 -- use winget (Windows Package Manager) to install ODT.
Then run elevated setup.exe /configure with version pin.
#>
$ErrorActionPreference = "Continue"
Start-Transcript -Path "$env:USERPROFILE\odt_rollback.log" -Force | Out-Null

$workDir = "$env:USERPROFILE\odt_work"
New-Item -ItemType Directory -Path $workDir -Force | Out-Null

# 1. Try several download paths for ODT setup.exe
Write-Host "[1] Acquiring Office Deployment Tool setup.exe..."
$setupExe = $null

# Try winget first
try {
    Write-Host "  trying: winget"
    $wgOut = & winget install --id Microsoft.OfficeDeploymentTool --accept-source-agreements --accept-package-agreements 2>&1
    Write-Host ($wgOut | Out-String)
    # Find the installed setup.exe
    $candidates = @(
        "C:\Program Files\Common Files\microsoft shared\OFFICE16\Office Setup Controller\Setup.exe",
        "$env:ProgramFiles\OfficeDeploymentTool\setup.exe",
        "$env:ProgramFiles(x86)\OfficeDeploymentTool\setup.exe"
    )
    foreach ($c in $candidates) {
        if (Test-Path $c) { $setupExe = $c; Write-Host "  found via winget: $c"; break }
    }
} catch {
    Write-Host "  winget failed: $($_.Exception.Message)"
}

# Fallback: direct download with Edge / IE BITS
if (-not $setupExe) {
    Write-Host "  trying direct download (current ODT URL)..."
    # As of 2026-04 the ODT installer is at:
    $directUrls = @(
        "https://download.microsoft.com/download/8/A/3/8A357CC1-BE92-4F95-9D5D-D44C12B4F77E/officedeploymenttool_19127-20158.exe",
        "https://download.microsoft.com/download/2/7/A/27AF1BE6-DD20-4CB4-B154-EBAB8A7D4A7E/officedeploymenttool_18526-20144.exe",
        "https://download.microsoft.com/download/officedeploymenttool/officedeploymenttool_19029-20136.exe"
    )
    $installerPath = "$workDir\OfficeDeploymentTool.exe"
    foreach ($u in $directUrls) {
        try {
            Write-Host "  trying: $u"
            Invoke-WebRequest -Uri $u -OutFile $installerPath -UseBasicParsing -TimeoutSec 60 -ErrorAction Stop
            $sz = (Get-Item $installerPath).Length
            Write-Host "  downloaded $sz bytes"
            if ($sz -lt 1000000) {
                Write-Host "  TOO SMALL -- probably HTML redirect, skipping"
                Remove-Item $installerPath -Force -ErrorAction SilentlyContinue
                continue
            }
            # Self-extract
            $extractDir = "$workDir\extracted"
            Remove-Item $extractDir -Recurse -Force -ErrorAction SilentlyContinue
            New-Item -ItemType Directory -Path $extractDir -Force | Out-Null
            & $installerPath /quiet /extract:$extractDir
            Start-Sleep -Seconds 5
            if (Test-Path "$extractDir\setup.exe") {
                $setupExe = "$extractDir\setup.exe"
                Write-Host "  extracted setup.exe at: $setupExe"
                break
            }
        } catch {
            Write-Host "  failed: $($_.Exception.Message)"
        }
    }
}

# Last resort: use the existing ClickToRun setup binaries
if (-not $setupExe) {
    Write-Host "  fallback: looking for any existing setup.exe in ClickToRun install..."
    $candidates = Get-ChildItem "C:\Program Files\Common Files" -Recurse -Filter "setup.exe" -ErrorAction SilentlyContinue | Select-Object -First 5
    foreach ($c in $candidates) {
        Write-Host "  candidate: $($c.FullName)"
    }
}

if (-not $setupExe) {
    Write-Host "[!] Could not acquire setup.exe via any method"
    Stop-Transcript | Out-Null
    exit 1
}

# 2. Generate Configuration.xml
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
  <RemoveMSI />
</Configuration>
"@
$configPath = "$workDir\Configuration.xml"
Set-Content -LiteralPath $configPath -Value $configXml -Force
Write-Host "[2] Wrote config: $configPath"

# 3. Stop Office apps
Write-Host "[3] Stopping Office apps..."
Get-Process POWERPNT, EXCEL, WINWORD, OUTLOOK, ONENOTE -ErrorAction SilentlyContinue | Stop-Process -Force
Start-Sleep -Seconds 3

# 4. Run setup.exe /configure ELEVATED
Write-Host "[4] Launching setup.exe /configure (UAC prompt will appear on your desktop)..."
Write-Host "    setup.exe: $setupExe"
Write-Host "    config:    $configPath"
try {
    $proc = Start-Process -FilePath $setupExe `
        -ArgumentList "/configure", "`"$configPath`"" `
        -Verb RunAs `
        -Wait `
        -PassThru `
        -ErrorAction Stop
    Write-Host "[5] setup.exe exited with code: $($proc.ExitCode)"
} catch {
    Write-Host "[!] setup.exe launch failed: $($_.Exception.Message)" -ForegroundColor Red
    Stop-Transcript | Out-Null
    exit 3
}

# 5. Verify
$reg = Get-ItemProperty "HKLM:\SOFTWARE\Microsoft\Office\ClickToRun\Configuration" -ErrorAction SilentlyContinue
$final = $reg.VersionToReport
$ppExe = "C:\Program Files\Microsoft Office\root\Office16\POWERPNT.EXE"
$ppVer = if (Test-Path $ppExe) { (Get-Item $ppExe).VersionInfo.FileVersion } else { "(missing)" }
Write-Host ""
Write-Host "  registry VersionToReport: $final"
Write-Host "  POWERPNT.EXE FileVersion: $ppVer"
if ($final -eq "16.0.19822.20182") {
    Write-Host "  STATUS: SUCCESS"
} else {
    Write-Host "  STATUS: did not flip"
}
Stop-Transcript | Out-Null
