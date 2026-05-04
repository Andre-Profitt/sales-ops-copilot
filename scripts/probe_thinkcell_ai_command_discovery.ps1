<#
Find any AI-related command in PowerPoint + think-cell ribbon that we could
.Execute() programmatically (vs. requiring a physical click).

Walks:
  - Application.CommandBars[*].Controls (all toolbars including ribbon)
  - thinkcell.addin COM members (look for AI* methods)
  - Looks for any control with "AI" / "Smart" / "Suggest" / "Generate" in
    caption / tooltip / id

Read-only enumeration. Does NOT execute anything.
#>
$ErrorActionPreference = "Continue"
$ProgressPreference = "SilentlyContinue"

function Log($m, $c="Cyan") { Write-Host "[ai-discover] $m" -ForegroundColor $c }

$result = [ordered]@{
    schema = "tc-ai-command-discovery/v1"
    timestamp_utc = [DateTime]::UtcNow.ToString("o")
    powerpoint_loaded = $false
    thinkcell_loaded = $false
    addin_methods = @()
    matching_controls = @()
    ribbon_xml = $null
    errors = @()
}

$ppt = $null
$pres = $null
try {
    Log "Launching PowerPoint COM"
    $ppt = New-Object -ComObject PowerPoint.Application
    $ppt.Visible = -1  # msoTrue
    $result.powerpoint_loaded = $true

    # Connect think-cell add-in
    $tc = $null
    try { $tc = $ppt.COMAddIns.Item("thinkcell.addin") } catch {}
    if ($tc) {
        if (-not $tc.Connect) { $tc.Connect = $true }
        $result.thinkcell_loaded = [bool] $tc.Connect
        $tcObj = $tc.Object
        Log "think-cell add-in connected"

        # Enumerate add-in methods looking for AI-related ones
        try {
            $members = $tcObj | Get-Member |
                Where-Object { $_.MemberType -in @("Method", "Property") } |
                ForEach-Object { $_.Name }
            $aiMembers = @($members | Where-Object { $_ -match "(?i)ai|smart|suggest|generate|complete|chat|prompt|llm" })
            $result.addin_methods = @($members)
            $result.ai_relevant_methods = $aiMembers
            Log "Found $($aiMembers.Count) AI-relevant addin methods: $($aiMembers -join ', ')"
        } catch {
            $result.errors += [ordered]@{ where = "addin_methods"; message = $_.Exception.Message }
        }
    } else {
        $result.errors += [ordered]@{ where = "addin"; message = "thinkcell.addin not found" }
    }

    # Open a blank presentation so the ribbon is fully populated
    $pres = $ppt.Presentations.Add(-1)
    Start-Sleep -Seconds 2  # let think-cell ribbon initialize

    # Walk CommandBars
    Log "Walking CommandBars (this is the deprecated path; ribbon controls aren't exposed here on Office 2016+)"
    try {
        $bars = $ppt.CommandBars
        $patterns = "(?i)ai|smart|suggest|generate|complete|chat|prompt|tcai"
        foreach ($bar in $bars) {
            try {
                foreach ($ctrl in $bar.Controls) {
                    $caption = ""; $tooltip = ""; $id = ""; $tag = ""
                    try { $caption = [string] $ctrl.Caption } catch {}
                    try { $tooltip = [string] $ctrl.TooltipText } catch {}
                    try { $id = [string] $ctrl.Id } catch {}
                    try { $tag = [string] $ctrl.Tag } catch {}
                    $combined = "$caption | $tooltip | $tag"
                    if ($combined -match $patterns) {
                        $result.matching_controls += [ordered]@{
                            bar_name = [string] $bar.Name
                            caption = $caption
                            tooltip = $tooltip
                            id = $id
                            tag = $tag
                            type = [string] $ctrl.Type
                            visible = $ctrl.Visible
                            enabled = $ctrl.Enabled
                        }
                    }
                }
            } catch {}
        }
        Log "Found $($result.matching_controls.Count) AI-pattern-matching CommandBar controls"
    } catch {
        $result.errors += [ordered]@{ where = "commandbars"; message = $_.Exception.Message }
    }

    # Try to grab any custom ribbon XML the addin emitted
    try {
        $idmso_candidates = @(
            "tc:AIChatPanel", "tc:AISmartGen", "tc:AICopilot",
            "tc:Copilot", "tc:CopilotPane", "tc:AIDialog",
            "tc:TextManipulation", "tc:PpAITextManipulation",
            "tc:PpAIDialog", "PpAICache"
        )
        $result.idmso_test = @()
        foreach ($id in $idmso_candidates) {
            $isVisible = $false
            try { $isVisible = $ppt.CommandBars.GetVisibleMso($id) } catch {}
            $isEnabled = $false
            try { $isEnabled = $ppt.CommandBars.GetEnabledMso($id) } catch {}
            $result.idmso_test += [ordered]@{
                idmso = $id
                visible = $isVisible
                enabled = $isEnabled
            }
        }
    } catch {
        $result.errors += [ordered]@{ where = "idmso_test"; message = $_.Exception.Message }
    }
} catch {
    $result.errors += [ordered]@{ where = "top_level"; message = $_.Exception.Message }
} finally {
    if ($pres) { try { $pres.Saved = -1; $pres.Close() } catch {} }
    if ($ppt) { try { $ppt.Quit() } catch {} }
}

# Output
$result | ConvertTo-Json -Depth 10
