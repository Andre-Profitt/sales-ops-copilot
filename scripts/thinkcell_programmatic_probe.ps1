<#
Returns a machine-readable capability probe for the Windows think-cell runtime.

This script intentionally probes update surfaces only. think-cell chart/table
creation is ribbon/UI-led in this install; the production automation contract is
to update already-named elements through ppttc.exe, PowerPoint COM, or Excel COM.

The probe captures, in order, the machine surface, the think-cell install
inventory, ppttc.exe metadata, the PowerPoint and Excel add-in COM surfaces
including all foreign add-ins, and a categorized capability verdict using
proven / observed_uninvoked / blocked / not_found statuses.
#>
[CmdletBinding()]
param(
    [switch] $NoPpttcHelpProbe,
    [switch] $NoStyleProofProbe
)

$ErrorActionPreference = "Continue"

# Methods our SimCorp pipeline actually invokes today. Anything else is
# "observed_uninvoked": present on the COM surface but not in the proven path.
$Script:PipelineExercisedExcelUpdate  = @("AddRangeData", "AddRangeImage", "Send")
$Script:PipelineExercisedExcelAddin   = @("CreateUpdate")
$Script:PipelineExercisedPpt          = @()  # ppttc.exe is the proven lane; PPT COM methods are not directly invoked yet.

# Categorized API surface buckets keyed by method name. Drives the categorized
# probe section so future agents see template/style/UI separately.
$Script:PptMethodGroups = [ordered]@{
    template_update = @(
        "PresentationFromTemplateStep3",
        "UpdateChartStep3",
        "UpdateBatchStep3"
    )
    style = @(
        "LoadStyle", "LoadStyleStep2",
        "LoadStyleForRegion", "LoadStyleForRegionStep2",
        "GetStyleName", "GetStyleNameStep2",
        "RemoveStyles", "RemoveStylesStep2"
    )
    mekko = @(
        "ImportMekkoGraphicsCharts",
        "GetMekkoGraphicsXML"
    )
    ui_only = @(
        "ShowChartGallery",
        "StartTableInsertion"
    )
    addin_lifecycle = @(
        "ActivateAddIn",
        "IsAddInActive"
    )
    bain_toolbox = @(
        "BainToolboxApplyShift",
        "BainToolboxRectangles"
    )
}

$Script:ExcelAddinGroups = [ordered]@{
    update_entry = @("CreateUpdate")
    presentation_template = @("PresentationFromTemplate")
    deprecated = @("UpdateChart")
}

$Script:ExcelUpdateGroups = [ordered]@{
    data = @("AddRangeData")
    image = @("AddRangeImage")
    commit = @("Send")
}

function New-ProbeResult {
    [ordered]@{
        timestamp_utc = [DateTime]::UtcNow.ToString("o")
        schema = "simcorp-thinkcell-probe/v3"
        machine = [ordered]@{}
        thinkcell = [ordered]@{}
        install_inventory = [ordered]@{}
        ppttc_metadata = [ordered]@{}
        ppttc_help_probe = [ordered]@{}
        ppttc_samples = [ordered]@{}
        tcserver = [ordered]@{}
        style_assets = [ordered]@{}
        mekko_samples = [ordered]@{}
        powerpoint = [ordered]@{}
        excel = [ordered]@{}
        api_surface = [ordered]@{}
        style_proof = [ordered]@{}
        capabilities = [ordered]@{}
        capability_verdicts = [ordered]@{}
        errors = @()
    }
}

function Add-ProbeError {
    param(
        [Parameter(Mandatory = $true)]
        [object] $Result,
        [Parameter(Mandatory = $true)]
        [string] $Where,
        [Parameter(Mandatory = $true)]
        [object] $ErrorRecord
    )

    $message = if ($ErrorRecord.Exception) {
        $ErrorRecord.Exception.Message
    } else {
        [string] $ErrorRecord
    }
    $Result.errors += [ordered]@{
        where = $Where
        message = $message
    }
}

function Find-PpttcExe {
    $candidates = @(
        "C:\Program Files\think-cell\ppttc.exe",
        "C:\Program Files (x86)\think-cell\ppttc.exe",
        "$env:LOCALAPPDATA\think-cell\ppttc.exe"
    )
    foreach ($candidate in $candidates) {
        if (Test-Path -LiteralPath $candidate) {
            return (Get-Item -LiteralPath $candidate)
        }
    }
    return $null
}

function Get-MemberSurface {
    param([object] $Object)

    if ($null -eq $Object) {
        return @()
    }
    try {
        return @(
            $Object |
                Get-Member |
                Where-Object { $_.MemberType -in @("Method", "Property") } |
                Sort-Object Name |
                ForEach-Object {
                    [ordered]@{
                        name = $_.Name
                        member_type = [string] $_.MemberType
                        definition = [string] $_.Definition
                    }
                }
        )
    } catch {
        return @()
    }
}

function Get-MemberNames {
    param([object[]] $Members)

    return @($Members | ForEach-Object { $_.name })
}

function Get-ComAddinInventory {
    param([object] $App)

    $list = @()
    if ($null -eq $App) { return $list }
    try {
        foreach ($candidate in $App.COMAddIns) {
            $row = [ordered]@{
                prog_id = [string] $candidate.ProgID
                description = $null
                connect = $null
                guid = $null
            }
            try { $row.description = [string] $candidate.Description } catch {}
            try { $row.connect = [bool] $candidate.Connect } catch {}
            try { $row.guid = [string] $candidate.Guid } catch {}
            $list += $row
        }
    } catch {}
    return $list
}

function Get-FolderInventory {
    param(
        [string] $Path,
        [int] $SampleSize = 8
    )

    $info = [ordered]@{
        path = $Path
        present = $false
        file_count = 0
        dir_count = 0
        sample_files = @()
        sample_dirs = @()
    }
    if (-not $Path) { return $info }
    if (-not (Test-Path -LiteralPath $Path)) { return $info }
    $info.present = $true
    try {
        $children = Get-ChildItem -LiteralPath $Path -Force -ErrorAction Stop
        $files = @($children | Where-Object { -not $_.PSIsContainer })
        $dirs = @($children | Where-Object { $_.PSIsContainer })
        $info.file_count = $files.Count
        $info.dir_count = $dirs.Count
        $info.sample_files = @($files | Sort-Object Name | Select-Object -First $SampleSize | ForEach-Object { $_.Name })
        $info.sample_dirs = @($dirs | Sort-Object Name | Select-Object -First $SampleSize | ForEach-Object { $_.Name })
    } catch {}
    return $info
}

function Get-PpttcMetadata {
    param([object] $PpttcItem)

    $info = [ordered]@{
        path = $null
        size_bytes = $null
        last_write_time_utc = $null
        product_version = $null
        file_version = $null
        company_name = $null
        product_name = $null
        original_filename = $null
    }
    if ($null -eq $PpttcItem) { return $info }
    $info.path = $PpttcItem.FullName
    $info.size_bytes = $PpttcItem.Length
    try {
        $info.last_write_time_utc = $PpttcItem.LastWriteTimeUtc.ToString("o")
    } catch {}
    try {
        $vi = [System.Diagnostics.FileVersionInfo]::GetVersionInfo($PpttcItem.FullName)
        $info.product_version = [string] $vi.ProductVersion
        $info.file_version = [string] $vi.FileVersion
        $info.company_name = [string] $vi.CompanyName
        $info.product_name = [string] $vi.ProductName
        $info.original_filename = [string] $vi.OriginalFilename
    } catch {}
    return $info
}

function Invoke-PpttcHelpProbe {
    param(
        [string] $Path,
        [int] $TimeoutMs = 4000
    )

    $info = [ordered]@{
        attempted = $false
        skipped_reason = $null
        exit_code = $null
        timed_out = $false
        stdout_head = $null
        stderr_head = $null
        error = $null
    }
    if (-not $Path -or -not (Test-Path -LiteralPath $Path)) {
        $info.skipped_reason = "ppttc.exe not found"
        return $info
    }
    $info.attempted = $true
    try {
        $psi = New-Object System.Diagnostics.ProcessStartInfo
        $psi.FileName = $Path
        # Pass --help; ppttc.exe with no args likely opens a modal dialog. The
        # think-cell CLI accepts --help in current builds; if it does not, the
        # process should exit quickly with a non-zero code. We protect against
        # any blocking dialog with a hard timeout and forced kill.
        $psi.Arguments = "--help"
        $psi.UseShellExecute = $false
        $psi.RedirectStandardOutput = $true
        $psi.RedirectStandardError = $true
        $psi.CreateNoWindow = $true
        $proc = [System.Diagnostics.Process]::Start($psi)
        if (-not $proc.WaitForExit($TimeoutMs)) {
            try { $proc.Kill() } catch {}
            $info.timed_out = $true
        }
        $stdout = $proc.StandardOutput.ReadToEnd()
        $stderr = $proc.StandardError.ReadToEnd()
        try { $info.exit_code = $proc.ExitCode } catch {}
        $info.stdout_head = (($stdout -split "`r?`n") | Select-Object -First 8) -join "`n"
        $info.stderr_head = (($stderr -split "`r?`n") | Select-Object -First 8) -join "`n"
    } catch {
        $info.error = $_.Exception.Message
    }
    return $info
}

function Group-MethodsByBucket {
    param(
        [string[]] $DiscoveredNames,
        [object] $GroupSpec
    )

    $names = @($DiscoveredNames | Where-Object { $_ } | Select-Object -Unique)
    $result = [ordered]@{}
    $accountedFor = New-Object System.Collections.Generic.HashSet[string]
    foreach ($key in $GroupSpec.Keys) {
        $expected = $GroupSpec[$key]
        $observed = @($expected | Where-Object { $names -contains $_ })
        $missing = @($expected | Where-Object { $names -notcontains $_ })
        foreach ($name in $observed) { [void] $accountedFor.Add($name) }
        $result[$key] = [ordered]@{
            expected = $expected
            observed = $observed
            missing = $missing
        }
    }
    $result["other"] = [ordered]@{
        observed = @($names | Where-Object { -not $accountedFor.Contains($_) })
    }
    return $result
}

function Resolve-MethodVerdict {
    param(
        [string] $Name,
        [string[]] $DiscoveredNames,
        [string[]] $PipelineNames
    )

    $present = $DiscoveredNames -contains $Name
    if (-not $present) { return "not_found" }
    if ($PipelineNames -contains $Name) { return "proven" }
    return "observed_uninvoked"
}

function Get-FileSummary {
    param([string] $Path)

    $info = [ordered]@{
        path = $Path
        present = $false
        size_bytes = $null
        last_write_time_utc = $null
    }
    if (-not $Path -or -not (Test-Path -LiteralPath $Path)) { return $info }
    try {
        $item = Get-Item -LiteralPath $Path -ErrorAction Stop
        $info.present = $true
        $info.size_bytes = $item.Length
        $info.last_write_time_utc = $item.LastWriteTimeUtc.ToString("o")
    } catch {}
    return $info
}

function Get-PpttcSampleInventory {
    param([string] $InstallRoot)

    $info = [ordered]@{
        ppttc_dir = $null
        sample_html = [ordered]@{ present = $false }
        sample_ppttc = [ordered]@{ present = $false }
        template_pptx = [ordered]@{ present = $false }
        ppttc_schema_json = [ordered]@{ present = $false }
    }
    if (-not $InstallRoot) { return $info }
    $dir = Join-Path $InstallRoot "ppttc"
    $info.ppttc_dir = $dir
    if (-not (Test-Path -LiteralPath $dir)) { return $info }
    $info.sample_html = Get-FileSummary (Join-Path $dir "sample.html")
    $info.sample_ppttc = Get-FileSummary (Join-Path $dir "sample.ppttc")
    $info.template_pptx = Get-FileSummary (Join-Path $dir "template.pptx")
    $info.ppttc_schema_json = Get-FileSummary (Join-Path $dir "ppttc-schema.json")
    return $info
}

function Get-TcServerInventory {
    param([string] $InstallRoot)

    $info = [ordered]@{
        candidate_paths = @()
        present = $false
        path = $null
        size_bytes = $null
        last_write_time_utc = $null
        product_version = $null
        file_version = $null
        company_name = $null
        product_name = $null
        notes = "Inventory only. No URL registration. No service start."
    }
    $candidates = @()
    if ($InstallRoot) {
        $candidates += (Join-Path $InstallRoot "tcserver.exe")
        $candidates += (Join-Path $InstallRoot "ppttc\tcserver.exe")
    }
    $candidates += "C:\Program Files\think-cell\tcserver.exe"
    $candidates += "C:\Program Files (x86)\think-cell\tcserver.exe"
    $info.candidate_paths = $candidates
    foreach ($candidate in $candidates) {
        if ($candidate -and (Test-Path -LiteralPath $candidate)) {
            try {
                $item = Get-Item -LiteralPath $candidate -ErrorAction Stop
                $info.present = $true
                $info.path = $item.FullName
                $info.size_bytes = $item.Length
                $info.last_write_time_utc = $item.LastWriteTimeUtc.ToString("o")
                try {
                    $vi = [System.Diagnostics.FileVersionInfo]::GetVersionInfo($item.FullName)
                    $info.product_version = [string] $vi.ProductVersion
                    $info.file_version = [string] $vi.FileVersion
                    $info.company_name = [string] $vi.CompanyName
                    $info.product_name = [string] $vi.ProductName
                } catch {}
                break
            } catch {}
        }
    }
    return $info
}

function Get-StyleAssetInventory {
    param([string] $InstallRoot)

    $info = [ordered]@{
        styles_dir = [ordered]@{ path = $null; present = $false; xml_file_count = 0; sample_files = @(); first_xml = $null }
        showcase_xml = [ordered]@{ present = $false }
        xml_schemas_dir = [ordered]@{ path = $null; present = $false; xsd_count = 0; sample_files = @() }
        tcstyle_xsd = [ordered]@{ present = $false }
    }
    if (-not $InstallRoot) { return $info }
    $stylesDir = Join-Path $InstallRoot "styles"
    $info.styles_dir.path = $stylesDir
    if (Test-Path -LiteralPath $stylesDir) {
        $info.styles_dir.present = $true
        try {
            $xmlFiles = @(Get-ChildItem -LiteralPath $stylesDir -Recurse -Filter "*.xml" -File -ErrorAction Stop)
            $info.styles_dir.xml_file_count = $xmlFiles.Count
            $info.styles_dir.sample_files = @($xmlFiles | Select-Object -First 6 | ForEach-Object { $_.FullName.Substring($stylesDir.Length).TrimStart('\','/') })
            if ($xmlFiles.Count -gt 0) {
                $info.styles_dir.first_xml = $xmlFiles[0].FullName
            }
        } catch {}
        $showcase = Join-Path $stylesDir "Customization Possibilities Showcase\Customization Possibilities Showcase.xml"
        $info.showcase_xml = Get-FileSummary $showcase
    }
    $xsdDir = Join-Path $InstallRoot "xml-schemas"
    $info.xml_schemas_dir.path = $xsdDir
    if (Test-Path -LiteralPath $xsdDir) {
        $info.xml_schemas_dir.present = $true
        try {
            $xsds = @(Get-ChildItem -LiteralPath $xsdDir -Filter "*.xsd" -File -ErrorAction Stop)
            $info.xml_schemas_dir.xsd_count = $xsds.Count
            $info.xml_schemas_dir.sample_files = @($xsds | Select-Object -First 12 | ForEach-Object { $_.Name })
        } catch {}
        $info.tcstyle_xsd = Get-FileSummary (Join-Path $xsdDir "tcstyle.xsd")
    }
    return $info
}

function Get-MekkoSampleInventory {
    $info = [ordered]@{
        candidate_dirs = @(
            "$env:USERPROFILE\Documents\SimCorp\mekko_samples",
            "C:\SimCorp\mekko_samples"
        )
        samples_present = $false
        sample_files = @()
        notes = "Mekko Graphics import requires a real Mekko Graphics chart in PowerPoint. think-cell ships no sample. Inventory only."
    }
    foreach ($dir in $info.candidate_dirs) {
        if ($dir -and (Test-Path -LiteralPath $dir)) {
            try {
                $files = @(Get-ChildItem -LiteralPath $dir -File -ErrorAction Stop)
                if ($files.Count -gt 0) {
                    $info.samples_present = $true
                    $info.sample_files = @($files | Select-Object -First 8 | ForEach-Object { $_.FullName })
                    break
                }
            } catch {}
        }
    }
    return $info
}

function Invoke-StyleProofProbe {
    <#
    Safe Style API proof probe. Reuses the supplied live PowerPoint.Application
    and runs every step on a transient, never-saved presentation. Each step
    records pass/fail/error/skip; no source asset is modified.
    #>
    param(
        [object] $App,
        [object] $Addin,
        [string] $StyleFile
    )

    $report = [ordered]@{
        attempted = $false
        skipped_reason = $null
        style_file = $StyleFile
        get_style_name_master = [ordered]@{ status = "skip"; value = $null; error = $null }
        load_style_master = [ordered]@{ status = "skip"; error = $null }
        get_style_name_master_after_load = [ordered]@{ status = "skip"; value = $null; error = $null }
        load_style_for_region_layout = [ordered]@{ status = "skip"; error = $null }
        remove_styles_layout = [ordered]@{ status = "skip"; error = $null }
        remove_styles_master_blocked = [ordered]@{ status = "skip"; error = $null; expected = "manual states masters must always retain a style" }
    }
    if ($null -eq $Addin -or $null -eq $App) {
        $report.skipped_reason = "no PowerPoint application or think-cell add-in object"
        return $report
    }
    if (-not $StyleFile -or -not (Test-Path -LiteralPath $StyleFile)) {
        $report.skipped_reason = "no installed style file available"
        return $report
    }
    $report.attempted = $true

    $pres = $null
    try {
        # Untitled msoTrue=-1 — create a transient presentation in the live app.
        $pres = $App.Presentations.Add(-1)
        $master = $pres.Designs(1).SlideMaster
        $layouts = $master.CustomLayouts
        $layout = if ($layouts.Count -ge 2) { $layouts.Item(2) } else { $layouts.Item(1) }

        # 1. GetStyleName before any LoadStyle — should return the active default.
        try {
            $name = $Addin.GetStyleName($master)
            $report.get_style_name_master.status = if ($name) { "pass" } else { "fail" }
            $report.get_style_name_master.value = [string] $name
        } catch {
            $report.get_style_name_master.status = "fail"
            $report.get_style_name_master.error = $_.Exception.Message
        }

        # 2. LoadStyle on the temp master.
        try {
            $Addin.LoadStyle($master, $StyleFile)
            $report.load_style_master.status = "pass"
        } catch {
            $report.load_style_master.status = "fail"
            $report.load_style_master.error = $_.Exception.Message
        }

        # 3. GetStyleName again — value should reflect the loaded style or stay a non-empty string.
        try {
            $name2 = $Addin.GetStyleName($master)
            $report.get_style_name_master_after_load.status = if ($name2) { "pass" } else { "fail" }
            $report.get_style_name_master_after_load.value = [string] $name2
        } catch {
            $report.get_style_name_master_after_load.status = "fail"
            $report.get_style_name_master_after_load.error = $_.Exception.Message
        }

        # 4. LoadStyleForRegion on the temp layout (left half).
        try {
            $w = [single] $layout.Width
            $h = [single] $layout.Height
            $Addin.LoadStyleForRegion($layout, $StyleFile, [single] 0, [single] 0, [single] ($w / 2), $h)
            $report.load_style_for_region_layout.status = "pass"
        } catch {
            $report.load_style_for_region_layout.status = "fail"
            $report.load_style_for_region_layout.error = $_.Exception.Message
        }

        # 5. RemoveStyles on the temp layout — allowed.
        try {
            $Addin.RemoveStyles($layout)
            $report.remove_styles_layout.status = "pass"
        } catch {
            $report.remove_styles_layout.status = "fail"
            $report.remove_styles_layout.error = $_.Exception.Message
        }

        # 6. RemoveStyles on the master must fail (manual: masters must always have a style).
        try {
            $Addin.RemoveStyles($master)
            # If this succeeds, the manual contract has changed; surface as 'unexpected_pass'.
            $report.remove_styles_master_blocked.status = "unexpected_pass"
        } catch {
            $report.remove_styles_master_blocked.status = "pass"
            $report.remove_styles_master_blocked.error = $_.Exception.Message
        }
    } catch {
        $report.skipped_reason = "style proof probe top-level error: $($_.Exception.Message)"
    } finally {
        if ($null -ne $pres) {
            try { $pres.Saved = -1 } catch {}
            try { $pres.Close() | Out-Null } catch {}
        }
    }
    return $report
}

$result = New-ProbeResult

try {
    $os = Get-CimInstance Win32_OperatingSystem
    $cpu = Get-CimInstance Win32_Processor | Select-Object -First 1
    $result.machine = [ordered]@{
        computer_name = $env:COMPUTERNAME
        user = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
        os_caption = $os.Caption
        os_version = $os.Version
        architecture = $env:PROCESSOR_ARCHITECTURE
        cpu = $cpu.Name
        powershell = $PSVersionTable.PSVersion.ToString()
    }
} catch {
    Add-ProbeError $result "machine" $_
}

$installRoot = $null
$ppttcItem = $null
try {
    $ppttcItem = Find-PpttcExe
    $installRoot = if ($ppttcItem) { Split-Path -Parent $ppttcItem.FullName } else { $null }
    $result.thinkcell = [ordered]@{
        ppttc_found = $null -ne $ppttcItem
        ppttc_path = if ($ppttcItem) { $ppttcItem.FullName } else { $null }
        ppttc_size_bytes = if ($ppttcItem) { $ppttcItem.Length } else { $null }
        install_root = $installRoot
        ppttc_samples_present = if ($installRoot) { Test-Path -LiteralPath (Join-Path $installRoot "ppttc") } else { $false }
        templates_present = if ($installRoot) { Test-Path -LiteralPath (Join-Path $installRoot "templates") } else { $false }
        xml_schemas_present = if ($installRoot) { Test-Path -LiteralPath (Join-Path $installRoot "xml-schemas") } else { $false }
    }
} catch {
    Add-ProbeError $result "thinkcell" $_
}

try {
    $rootInventory = Get-FolderInventory $installRoot
    $ppttcFolder = if ($installRoot) { Join-Path $installRoot "ppttc" } else { $null }
    $templatesFolder = if ($installRoot) { Join-Path $installRoot "templates" } else { $null }
    $manualFolder = if ($installRoot) { Join-Path $installRoot "manual" } else { $null }
    $xmlSchemasFolder = if ($installRoot) { Join-Path $installRoot "xml-schemas" } else { $null }

    $ppttcInv = Get-FolderInventory $ppttcFolder 12
    $templatesInv = Get-FolderInventory $templatesFolder 12
    $manualInv = Get-FolderInventory $manualFolder 12
    $xmlSchemasInv = Get-FolderInventory $xmlSchemasFolder 12

    $schemaPath = if ($ppttcFolder) { Join-Path $ppttcFolder "ppttc-schema.json" } else { $null }
    $sampleTemplatePath = if ($ppttcFolder) { Join-Path $ppttcFolder "template.pptx" } else { $null }
    $samplePpttcPath = if ($ppttcFolder) { Join-Path $ppttcFolder "sample.ppttc" } else { $null }

    $result.install_inventory = [ordered]@{
        install_root = $rootInventory
        ppttc = $ppttcInv
        templates = $templatesInv
        manual = $manualInv
        xml_schemas = $xmlSchemasInv
        ppttc_schema_json = [ordered]@{
            path = $schemaPath
            present = if ($schemaPath) { Test-Path -LiteralPath $schemaPath } else { $false }
        }
        sample_template_pptx = [ordered]@{
            path = $sampleTemplatePath
            present = if ($sampleTemplatePath) { Test-Path -LiteralPath $sampleTemplatePath } else { $false }
        }
        sample_ppttc = [ordered]@{
            path = $samplePpttcPath
            present = if ($samplePpttcPath) { Test-Path -LiteralPath $samplePpttcPath } else { $false }
        }
    }
} catch {
    Add-ProbeError $result "install_inventory" $_
}

try {
    $result.ppttc_metadata = Get-PpttcMetadata $ppttcItem
} catch {
    $result.ppttc_metadata = [ordered]@{ path = $null }
    Add-ProbeError $result "ppttc_metadata" $_
}

try {
    if ($NoPpttcHelpProbe.IsPresent) {
        $result.ppttc_help_probe = [ordered]@{
            attempted = $false
            skipped_reason = "NoPpttcHelpProbe switch set"
        }
    } elseif ($ppttcItem) {
        $result.ppttc_help_probe = Invoke-PpttcHelpProbe $ppttcItem.FullName 4000
    } else {
        $result.ppttc_help_probe = [ordered]@{
            attempted = $false
            skipped_reason = "ppttc.exe not found"
        }
    }
} catch {
    $result.ppttc_help_probe = [ordered]@{ attempted = $false; error = $_.Exception.Message }
    Add-ProbeError $result "ppttc_help_probe" $_
}

try { $result.ppttc_samples = Get-PpttcSampleInventory $installRoot } catch { Add-ProbeError $result "ppttc_samples" $_ }
try { $result.tcserver = Get-TcServerInventory $installRoot } catch { Add-ProbeError $result "tcserver" $_ }
try { $result.style_assets = Get-StyleAssetInventory $installRoot } catch { Add-ProbeError $result "style_assets" $_ }
try { $result.mekko_samples = Get-MekkoSampleInventory } catch { Add-ProbeError $result "mekko_samples" $_ }

try {
    $ppt = New-Object -ComObject PowerPoint.Application
    $allAddins = Get-ComAddinInventory $ppt
    $addin = $null
    foreach ($candidate in $ppt.COMAddIns) {
        if ($candidate.ProgID -eq "thinkcell.addin") {
            $addin = $candidate
            break
        }
    }

    $members = @()
    if ($null -ne $addin) {
        if (-not $addin.Connect) {
            $addin.Connect = $true
        }
        $members = Get-MemberSurface $addin.Object
    }

    $result.powerpoint = [ordered]@{
        available = $true
        version = $ppt.Version
        build = $ppt.Build
        com_addin_count = $allAddins.Count
        com_addins = $allAddins
        thinkcell_addin_found = $null -ne $addin
        thinkcell_addin_connect = if ($addin) { [bool] $addin.Connect } else { $false }
        thinkcell_addin_description = if ($addin) { [string] $addin.Description } else { $null }
        thinkcell_addin_guid = if ($addin) { try { [string] $addin.Guid } catch { $null } } else { $null }
        object_type = if ($addin -and $addin.Object) { $addin.Object.GetType().FullName } else { $null }
        members = $members
    }

    if ($NoStyleProofProbe.IsPresent) {
        $result.style_proof = [ordered]@{
            attempted = $false
            skipped_reason = "NoStyleProofProbe switch set"
        }
    } elseif ($null -ne $addin) {
        $styleFile = $null
        try {
            if ($result.style_assets.showcase_xml.present) {
                $styleFile = $result.style_assets.showcase_xml.path
            } elseif ($result.style_assets.styles_dir.first_xml) {
                $styleFile = $result.style_assets.styles_dir.first_xml
            }
        } catch {}
        try {
            $result.style_proof = Invoke-StyleProofProbe -App $ppt -Addin $addin.Object -StyleFile $styleFile
        } catch {
            $result.style_proof = [ordered]@{ attempted = $false; error = $_.Exception.Message }
            Add-ProbeError $result "style_proof" $_
        }
    } else {
        $result.style_proof = [ordered]@{
            attempted = $false
            skipped_reason = "no think-cell add-in on PowerPoint"
        }
    }

    try {
        $ppt.Quit() | Out-Null
    } catch {}
} catch {
    $result.powerpoint = [ordered]@{ available = $false; com_addins = @(); members = @() }
    Add-ProbeError $result "powerpoint" $_
}

try {
    $xl = New-Object -ComObject Excel.Application
    $xl.Visible = $false
    $xl.DisplayAlerts = $false

    $allAddins = Get-ComAddinInventory $xl
    $addin = $null
    foreach ($candidate in $xl.COMAddIns) {
        if ($candidate.ProgID -eq "thinkcell.addin") {
            $addin = $candidate
            break
        }
    }

    $addinMembers = @()
    $updateMembers = @()
    if ($null -ne $addin) {
        if (-not $addin.Connect) {
            $addin.Connect = $true
        }
        $addinMembers = Get-MemberSurface $addin.Object
        try {
            $update = $addin.Object.CreateUpdate()
            $updateMembers = Get-MemberSurface $update
        } catch {
            Add-ProbeError $result "excel.CreateUpdate" $_
        }
    }

    $result.excel = [ordered]@{
        available = $true
        version = $xl.Version
        build = $xl.Build
        com_addin_count = $allAddins.Count
        com_addins = $allAddins
        thinkcell_addin_found = $null -ne $addin
        thinkcell_addin_connect = if ($addin) { [bool] $addin.Connect } else { $false }
        thinkcell_addin_description = if ($addin) { [string] $addin.Description } else { $null }
        thinkcell_addin_guid = if ($addin) { try { [string] $addin.Guid } catch { $null } } else { $null }
        object_type = if ($addin -and $addin.Object) { $addin.Object.GetType().FullName } else { $null }
        addin_members = $addinMembers
        update_members = $updateMembers
    }
    try {
        $xl.Quit() | Out-Null
    } catch {}
} catch {
    $result.excel = [ordered]@{ available = $false; com_addins = @(); addin_members = @(); update_members = @() }
    Add-ProbeError $result "excel" $_
}

$pptNames = Get-MemberNames $result.powerpoint.members
$excelAddinNames = Get-MemberNames $result.excel.addin_members
$excelUpdateNames = Get-MemberNames $result.excel.update_members
$allNames = @($pptNames + $excelAddinNames + $excelUpdateNames)

$result.api_surface = [ordered]@{
    powerpoint = Group-MethodsByBucket -DiscoveredNames $pptNames -GroupSpec $Script:PptMethodGroups
    excel_addin = Group-MethodsByBucket -DiscoveredNames $excelAddinNames -GroupSpec $Script:ExcelAddinGroups
    excel_update = Group-MethodsByBucket -DiscoveredNames $excelUpdateNames -GroupSpec $Script:ExcelUpdateGroups
}

# Backwards compatible boolean capabilities — lab.py mismatch check depends on
# these exact keys; do not rename.
$result.capabilities = [ordered]@{
    ppttc_template_update = [bool] $result.thinkcell.ppttc_found
    powerpoint_update_chart_step3 = $pptNames -contains "UpdateChartStep3"
    powerpoint_update_batch_step3 = $pptNames -contains "UpdateBatchStep3"
    powerpoint_presentation_from_template_step3 = $pptNames -contains "PresentationFromTemplateStep3"
    excel_create_update = $excelAddinNames -contains "CreateUpdate"
    excel_add_range_data = $excelUpdateNames -contains "AddRangeData"
    excel_add_range_image = $excelUpdateNames -contains "AddRangeImage"
    excel_send_update = $excelUpdateNames -contains "Send"
    programmatic_create_chart = (@($allNames | Where-Object { $_ -match "Create.*Chart|Insert.*Chart" }).Count -gt 0)
    ui_chart_gallery_only = $pptNames -contains "ShowChartGallery"
}

$ppttcVerdict = if ($result.thinkcell.ppttc_found) { "proven" } else { "not_found" }

$verdicts = [ordered]@{
    ppttc_exe_template_update = [ordered]@{
        status = $ppttcVerdict
        evidence = "ppttc.exe path: $($result.thinkcell.ppttc_path)"
        manual_section = "JSON Data Automation"
    }
    excel_addrangedata = [ordered]@{
        status = (Resolve-MethodVerdict "AddRangeData" $excelUpdateNames $Script:PipelineExercisedExcelUpdate)
        evidence = "Excel UpdateBatch: tcUpdate.AddRangeData(Target, Name, Range, Transposed)"
        manual_section = "Excel Data Automation > UpdateBatch"
    }
    excel_addrangeimage = [ordered]@{
        status = (Resolve-MethodVerdict "AddRangeImage" $excelUpdateNames $Script:PipelineExercisedExcelUpdate)
        evidence = "Excel UpdateBatch: tcUpdate.AddRangeImage(Target, Name, Range); only available via UpdateBatch"
        manual_section = "Excel Data Automation > UpdateBatch"
    }
    excel_send = [ordered]@{
        status = (Resolve-MethodVerdict "Send" $excelUpdateNames $Script:PipelineExercisedExcelUpdate)
        evidence = "Excel UpdateBatch: tcUpdate.Send() commits queued range/image updates"
        manual_section = "Excel Data Automation > UpdateBatch"
    }
    excel_create_update = [ordered]@{
        status = (Resolve-MethodVerdict "CreateUpdate" $excelAddinNames $Script:PipelineExercisedExcelAddin)
        evidence = "Excel tcXlAddIn.CreateUpdate() entry point for batch updates"
        manual_section = "Excel Data Automation > UpdateBatch"
    }
    excel_presentation_from_template = [ordered]@{
        status = (Resolve-MethodVerdict "PresentationFromTemplate" $excelAddinNames $Script:PipelineExercisedExcelAddin)
        evidence = "Excel tcXlAddIn.PresentationFromTemplate creates presentation from a template; not yet exercised by SimCorp pipeline"
        manual_section = "Excel Data Automation"
    }
    excel_update_chart_deprecated = [ordered]@{
        status = (Resolve-MethodVerdict "UpdateChart" $excelAddinNames $Script:PipelineExercisedExcelAddin)
        evidence = "Excel tcXlAddIn.UpdateChart is deprecated in favor of UpdateBatch; do not invoke"
        manual_section = "Excel Data Automation"
        deprecated = $true
    }
    powerpoint_update_batch_step3 = [ordered]@{
        status = (Resolve-MethodVerdict "UpdateBatchStep3" $pptNames $Script:PipelineExercisedPpt)
        evidence = "PowerPoint tcPpAddIn.UpdateBatchStep3 (late-bound IDispatch); SimCorp lane uses ppttc.exe wrapper instead"
        manual_section = "API > PowerPoint"
    }
    powerpoint_update_chart_step3 = [ordered]@{
        status = (Resolve-MethodVerdict "UpdateChartStep3" $pptNames $Script:PipelineExercisedPpt)
        evidence = "PowerPoint tcPpAddIn.UpdateChartStep3 (late-bound IDispatch); not exercised"
        manual_section = "API > PowerPoint"
    }
    powerpoint_presentation_from_template_step3 = [ordered]@{
        status = (Resolve-MethodVerdict "PresentationFromTemplateStep3" $pptNames $Script:PipelineExercisedPpt)
        evidence = "PowerPoint tcPpAddIn.PresentationFromTemplateStep3; not exercised; ppttc.exe is preferred wrapper"
        manual_section = "API > PowerPoint"
    }
    powerpoint_load_style = [ordered]@{
        status = if ($result.style_proof.load_style_master.status -eq "pass") {
            "proven"
        } else {
            (Resolve-MethodVerdict "LoadStyle" $pptNames $Script:PipelineExercisedPpt)
        }
        evidence = "Style file load on a transient master; status from style_proof.load_style_master"
        manual_section = "API > Style files"
        proof = $result.style_proof.load_style_master.status
    }
    powerpoint_get_style_name = [ordered]@{
        status = if ($result.style_proof.get_style_name_master.status -eq "pass") {
            "proven"
        } else {
            (Resolve-MethodVerdict "GetStyleName" $pptNames $Script:PipelineExercisedPpt)
        }
        evidence = "GetStyleName on a transient master; status from style_proof.get_style_name_master"
        manual_section = "API > Style files"
        proof = $result.style_proof.get_style_name_master.status
        sample_value = $result.style_proof.get_style_name_master.value
    }
    powerpoint_load_style_for_region = [ordered]@{
        status = if ($result.style_proof.load_style_for_region_layout.status -eq "pass") {
            "proven"
        } else {
            (Resolve-MethodVerdict "LoadStyleForRegion" $pptNames $Script:PipelineExercisedPpt)
        }
        evidence = "LoadStyleForRegion on a transient layout (left half); status from style_proof.load_style_for_region_layout"
        manual_section = "API > Style files"
        proof = $result.style_proof.load_style_for_region_layout.status
    }
    powerpoint_remove_styles = [ordered]@{
        status = if ($result.style_proof.remove_styles_layout.status -eq "pass") {
            "proven"
        } else {
            (Resolve-MethodVerdict "RemoveStyles" $pptNames $Script:PipelineExercisedPpt)
        }
        evidence = "RemoveStyles on a transient layout; status from style_proof.remove_styles_layout. Manual: master cannot have styles removed."
        manual_section = "API > Style files"
        proof = $result.style_proof.remove_styles_layout.status
        master_block_proof = $result.style_proof.remove_styles_master_blocked.status
    }
    powerpoint_import_mekko_graphics = [ordered]@{
        status = if ($result.mekko_samples.samples_present) {
            (Resolve-MethodVerdict "ImportMekkoGraphicsCharts" $pptNames $Script:PipelineExercisedPpt)
        } else {
            "blocked"
        }
        evidence = "Imports Mekko Graphics charts as native think-cell charts; blocker = no Mekko Graphics donor sample on disk"
        manual_section = "API > Mekko Graphics import"
        blocker = if ($result.mekko_samples.samples_present) { $null } else { "no Mekko Graphics donor PPTX present on the runtime" }
    }
    powerpoint_get_mekko_graphics_xml = [ordered]@{
        status = if ($result.mekko_samples.samples_present) {
            (Resolve-MethodVerdict "GetMekkoGraphicsXML" $pptNames $Script:PipelineExercisedPpt)
        } else {
            "blocked"
        }
        evidence = "Returns Mekko Graphics XML for a chart; blocker = no Mekko Graphics donor sample on disk; manual specifies E_INVALIDARG (0x80070057) on a non-Mekko shape"
        manual_section = "API > Mekko Graphics import"
        blocker = if ($result.mekko_samples.samples_present) { $null } else { "no Mekko Graphics donor PPTX present on the runtime" }
    }
    powerpoint_show_chart_gallery = [ordered]@{
        status = (Resolve-MethodVerdict "ShowChartGallery" $pptNames $Script:PipelineExercisedPpt)
        evidence = "UI-only: opens think-cell chart gallery; not a headless creation method"
        manual_section = "API > UI"
        ui_only = $true
    }
    powerpoint_start_table_insertion = [ordered]@{
        status = (Resolve-MethodVerdict "StartTableInsertion" $pptNames $Script:PipelineExercisedPpt)
        evidence = "UI-only: starts interactive table insertion; not a headless creation method"
        manual_section = "API > UI"
        ui_only = $true
    }
    programmatic_chart_creation = [ordered]@{
        status = if ($result.capabilities.programmatic_create_chart) { "observed_uninvoked" } else { "not_found" }
        evidence = "No COM method matching Create*Chart / Insert*Chart was found on the COM surface; chart creation remains UI/donor driven"
        manual_section = "(none)"
    }
    native_editable_thinkcell_tables = [ordered]@{
        status = "blocked"
        evidence = "Domain-blocked: native editable think-cell tables fail to bind cleanly without PowerPoint repair prompts; use the Excel COM AddRangeImage table-image lane instead"
        manual_section = "API > UI"
    }
    web_addin_path = [ordered]@{
        status = "blocked"
        evidence = "Office Web Add-ins cannot reach Office COM add-ins; the think-cell COM API is Windows-desktop-only"
        manual_section = "API > Limitations"
    }
    tcserver_http_service = [ordered]@{
        status = if ($result.tcserver.present) { "observed_uninvoked" } else { "not_found" }
        evidence = "tcserver.exe inventory only (path/version/size). No URL registration, no service start. POST mime application/vnd.think-cell.ppttc+json"
        manual_section = "JSON Data Automation > think-cell server"
        path = $result.tcserver.path
        product_version = $result.tcserver.product_version
    }
}

$result.capability_verdicts = $verdicts

$result | ConvertTo-Json -Depth 10 -Compress
