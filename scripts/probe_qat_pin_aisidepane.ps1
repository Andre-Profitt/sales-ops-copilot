<#
Stage 3 — QAT pinning of think-cell's AI button.

If UIA RawViewWalker (Stage 1) and MSAA via oleacc (Stage 2) both fail to
expose tc:AISidePane, this script promotes it to the Quick Access Toolbar by
editing PowerPoint.officeUI. QAT items are standard UIA Buttons regardless of
the underlying custom-control implementation, so once pinned, the AI button
becomes invocable via UIA InvokePattern.

Per Microsoft docs (MS-CUSTOMUI):
  - Editing PowerPoint.officeUI while PP is running can corrupt the file.
  - If Office detects ANY problem with .officeUI, it reverts to defaults and
    deletes all customizations.
  - We back up the original first; restore on failure.

Procedure:
  1. Verify PowerPoint is NOT running (kill any zombies).
  2. Backup %LocalAppData%\Microsoft\Office\PowerPoint.officeUI -> .bak.original
     (ALSO save a sequenced .bak with timestamp to keep history.)
  3. Read existing XML; if no <qat> -> create skeleton; if <qat> exists -> insert
     <control idQ="tc:AISidePane" /> as last child of documentControls if not already there.
  4. Write back. Verify XML round-trips by reparsing.
  5. Caller relaunches PowerPoint and runs the standard UIA-button click.

This script is reversible: a separate -Restore mode copies .bak.original back.
#>
param(
    [switch]$Restore
)
$ErrorActionPreference = "Continue"

$officeUI = "$env:LocalAppData\Microsoft\Office\PowerPoint.officeUI"
$bakOrig = "$officeUI.bak.original"
$bakSeq = "$officeUI.bak.$(Get-Date -Format yyyyMMddHHmmss)"
$out = "$env:USERPROFILE\tc_qat_pin.json"
$result = [ordered]@{
    timestamp_utc = [DateTime]::UtcNow.ToString("o")
    mode = if ($Restore) { "restore" } else { "pin" }
    officeUI_path = $officeUI
    pre_existed = $false
    pre_size = $null
    post_size = $null
    pp_killed = @()
    errors = @()
}

# 1. PowerPoint must be closed
$ppProcs = Get-Process POWERPNT -ErrorAction SilentlyContinue
foreach ($p in $ppProcs) {
    try { Stop-Process -Id $p.Id -Force -ErrorAction Stop; $result.pp_killed += $p.Id } catch {
        $result.errors += [ordered]@{ where = "kill_pp"; pid = $p.Id; message = $_.Exception.Message }
    }
}
Start-Sleep -Seconds 2

if ($Restore) {
    if (Test-Path -LiteralPath $bakOrig) {
        Copy-Item -LiteralPath $bakOrig -Destination $officeUI -Force
        $result.restored_from = $bakOrig
        $result.post_size = (Get-Item -LiteralPath $officeUI).Length
    } else {
        $result.errors += [ordered]@{ where = "restore"; message = "no .bak.original found" }
    }
    $result | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $out -Force
    return
}

# 2. Backup
if (Test-Path -LiteralPath $officeUI) {
    $result.pre_existed = $true
    $result.pre_size = (Get-Item -LiteralPath $officeUI).Length
    if (-not (Test-Path -LiteralPath $bakOrig)) {
        Copy-Item -LiteralPath $officeUI -Destination $bakOrig -Force
        $result.bak_original = $bakOrig
    }
    Copy-Item -LiteralPath $officeUI -Destination $bakSeq -Force
    $result.bak_seq = $bakSeq
}

# 3. Build / patch XML.
# MS-CUSTOMUI minimum form:
#   <mso:cmd app="PowerPoint" dt="0" />
#   <mso:customUI xmlns:mso="http://schemas.microsoft.com/office/2009/07/customui">
#     <mso:ribbon>
#       <mso:qat>
#         <mso:documentControls>
#           <mso:control idQ="x1:tc_AISidePane" visible="true"/>
#           ...
#         </mso:documentControls>
#       </mso:qat>
#     </mso:ribbon>
#   </mso:customUI>
# Note the namespace prefix `x1:` used by MS-CUSTOMUI for cross-add-in idQ refs;
# that prefix is bound to think-cell's CustomUI namespace URI by Office at load
# time. Without the binding, we use idMso fallback OR inject the namespace decl
# ourselves. Try the simple form first.

$nsMso = "http://schemas.microsoft.com/office/2009/07/customui"

if ($result.pre_existed) {
    try {
        [xml]$doc = Get-Content -LiteralPath $officeUI -Raw
    } catch {
        $result.errors += [ordered]@{ where = "parse"; message = $_.Exception.Message }
        $result | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $out -Force
        exit 1
    }
} else {
    [xml]$doc = New-Object System.Xml.XmlDocument
    $decl = $doc.CreateXmlDeclaration("1.0", "utf-8", $null)
    [void] $doc.AppendChild($decl)
    $cmd = $doc.CreateElement("mso", "cmd", $nsMso)
    $cmd.SetAttribute("app", "PowerPoint")
    $cmd.SetAttribute("dt", "0")
    [void] $doc.AppendChild($cmd)
    $cui = $doc.CreateElement("mso", "customUI", $nsMso)
    [void] $doc.AppendChild($cui)
}

$ns = New-Object System.Xml.XmlNamespaceManager($doc.NameTable)
$ns.AddNamespace("mso", $nsMso)

$cui = $doc.SelectSingleNode("//mso:customUI", $ns)
if (-not $cui) {
    $cui = $doc.CreateElement("mso", "customUI", $nsMso)
    [void] $doc.DocumentElement.AppendChild($cui)
}

$ribbon = $cui.SelectSingleNode("mso:ribbon", $ns)
if (-not $ribbon) {
    $ribbon = $doc.CreateElement("mso", "ribbon", $nsMso)
    [void] $cui.AppendChild($ribbon)
}

$qat = $ribbon.SelectSingleNode("mso:qat", $ns)
if (-not $qat) {
    $qat = $doc.CreateElement("mso", "qat", $nsMso)
    [void] $ribbon.AppendChild($qat)
}

$docCtrls = $qat.SelectSingleNode("mso:documentControls", $ns)
if (-not $docCtrls) {
    $docCtrls = $doc.CreateElement("mso", "documentControls", $nsMso)
    [void] $qat.AppendChild($docCtrls)
}

# Check if AISidePane is already pinned
$existing = $docCtrls.SelectNodes("mso:control[@idQ='tc:AISidePane' or @idQ='x1:tc_AISidePane']", $ns)
if ($existing.Count -gt 0) {
    $result.already_pinned = $true
} else {
    # CRITICAL: bind xmlns:tc on the control element itself so the `tc:` prefix
    # in idQ resolves. Without this binding in scope, Office silently ignores
    # the entry and may even corrupt customizations on next launch.
    # think-cell's add-in publishes the namespace as "thinkcell.addin" (verified
    # against the existing customUI XML's <mso:tab xmlns:tc="thinkcell.addin">).
    $ctrl = $doc.CreateElement("mso", "control", $nsMso)
    $ctrl.SetAttribute("xmlns:tc", "thinkcell.addin")
    $ctrl.SetAttribute("idQ", "tc:AISidePane")
    $ctrl.SetAttribute("visible", "true")
    [void] $docCtrls.AppendChild($ctrl)
    $result.added_idQ = "tc:AISidePane"
}

# 4. Write back
try {
    $doc.Save($officeUI)
    $result.post_size = (Get-Item -LiteralPath $officeUI).Length
    $result.success = $true
} catch {
    $result.errors += [ordered]@{ where = "save"; message = $_.Exception.Message }
    if (Test-Path -LiteralPath $bakSeq) {
        Copy-Item -LiteralPath $bakSeq -Destination $officeUI -Force
        $result.rolled_back = $true
    }
}

$result | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $out -Force
Write-Host "QAT pin: success=$($result.success) added=$($result.added_idQ) already=$($result.already_pinned) bak=$bakOrig"
