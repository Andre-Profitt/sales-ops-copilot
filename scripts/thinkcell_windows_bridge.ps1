# Runs think-cell JSON automation on Windows.
#
# This is intentionally Windows-side PowerShell because ppttc.exe is Windows-only
# and think-cell's Office API is COM-based. The script keeps the .ppttc JSON raw:
# PowerShell ConvertFrom-Json/ConvertTo-Json can change empty arrays and nulls in
# ways ppttc.exe rejects.
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string] $PpttcPath,

    [Parameter(Mandatory = $true)]
    [string] $TemplatePath,

    [Parameter(Mandatory = $true)]
    [string] $OutputPptx,

    [string] $PpttcExe,

    [string[]] $ExpectText = @()
)

$ErrorActionPreference = "Stop"

function Resolve-ExistingPath {
    param(
        [Parameter(Mandatory = $true)]
        [string] $Path,
        [Parameter(Mandatory = $true)]
        [string] $Label
    )

    $item = Get-Item -LiteralPath $Path -ErrorAction SilentlyContinue
    if (-not $item) {
        throw "$Label not found: $Path"
    }
    return $item.FullName
}

function Find-PpttcExe {
    param([string] $ExplicitPath)

    if ($ExplicitPath) {
        return Resolve-ExistingPath $ExplicitPath "ppttc.exe"
    }

    $candidates = @(
        "C:\Program Files\think-cell\ppttc.exe",
        "C:\Program Files (x86)\think-cell\ppttc.exe",
        "$env:LOCALAPPDATA\think-cell\ppttc.exe"
    )
    foreach ($candidate in $candidates) {
        if (Test-Path -LiteralPath $candidate) {
            return (Get-Item -LiteralPath $candidate).FullName
        }
    }

    throw "ppttc.exe not found in standard think-cell install locations."
}

function Rewrite-PpttcTemplate {
    param(
        [Parameter(Mandatory = $true)]
        [string] $InputPpttc,
        [Parameter(Mandatory = $true)]
        [string] $WindowsTemplatePath
    )

    $raw = Get-Content -LiteralPath $InputPpttc -Raw
    $match = [regex]::Match($raw, '"template"\s*:\s*"([^"]+)"')
    if (-not $match.Success) {
        throw "Could not locate a top-level template field in $InputPpttc"
    }

    $templateJson = $WindowsTemplatePath | ConvertTo-Json -Compress
    $rewrittenRaw = [regex]::Replace(
        $raw,
        '"template"\s*:\s*"[^"]+"',
        ('"template": ' + $templateJson),
        1
    )

    $inputItem = Get-Item -LiteralPath $InputPpttc
    $rewrittenPath = Join-Path $inputItem.DirectoryName ($inputItem.BaseName + ".windows.ppttc")
    $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($rewrittenPath, $rewrittenRaw, $utf8NoBom)
    return $rewrittenPath
}

function Assert-PptxContainsText {
    param(
        [Parameter(Mandatory = $true)]
        [string] $PptxPath,
        [Parameter(Mandatory = $true)]
        [string[]] $Needles
    )

    if ($Needles.Count -eq 0) {
        return
    }

    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $found = @{}
    foreach ($needle in $Needles) {
        $found[$needle] = $false
    }

    $zip = [System.IO.Compression.ZipFile]::OpenRead($PptxPath)
    try {
        foreach ($entry in $zip.Entries) {
            if (-not ($entry.FullName.StartsWith("ppt/") -and $entry.FullName.EndsWith(".xml"))) {
                continue
            }
            $stream = $entry.Open()
            try {
                $reader = New-Object System.IO.StreamReader($stream)
                $text = $reader.ReadToEnd()
            }
            finally {
                if ($reader) { $reader.Dispose() }
                $stream.Dispose()
            }

            foreach ($needle in $Needles) {
                if (-not $found[$needle] -and $text.Contains($needle)) {
                    $found[$needle] = $true
                }
            }
        }
    }
    finally {
        $zip.Dispose()
    }

    $missing = @($Needles | Where-Object { -not $found[$_] })
    if ($missing.Count -gt 0) {
        throw "Output PPTX missing expected text: $($missing -join ', ')"
    }
}

$ppttcResolved = Resolve-ExistingPath $PpttcPath ".ppttc input"
$templateResolved = Resolve-ExistingPath $TemplatePath "PowerPoint template"
$ppttcExeResolved = Find-PpttcExe $PpttcExe
$outputDir = Split-Path -Parent $OutputPptx
if ($outputDir) {
    New-Item -ItemType Directory -Path $outputDir -Force | Out-Null
}

$rewrittenPpttc = Rewrite-PpttcTemplate $ppttcResolved $templateResolved
if (Test-Path -LiteralPath $OutputPptx) {
    Remove-Item -LiteralPath $OutputPptx -Force
}

Write-Host "think-cell bridge"
Write-Host "  ppttc.exe: $ppttcExeResolved"
Write-Host "  input:     $ppttcResolved"
Write-Host "  rewritten: $rewrittenPpttc"
Write-Host "  template:  $templateResolved"
Write-Host "  output:    $OutputPptx"

& $ppttcExeResolved $rewrittenPpttc -o $OutputPptx 2>&1
$exitCode = $LASTEXITCODE
if ($exitCode -ne 0) {
    throw "ppttc.exe exited $exitCode"
}
if (-not (Test-Path -LiteralPath $OutputPptx)) {
    throw "ppttc.exe exited 0 but did not create output: $OutputPptx"
}

$outputItem = Get-Item -LiteralPath $OutputPptx
if ($outputItem.Length -le 0) {
    throw "ppttc.exe created an empty output file: $OutputPptx"
}

if ($ExpectText.Count -gt 0) {
    Assert-PptxContainsText $outputItem.FullName $ExpectText
}

Write-Host "  size:      $($outputItem.Length) bytes"
Write-Host "  status:    ok"
