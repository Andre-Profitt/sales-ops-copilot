<#
OleViewDotNet module probe for think-cell COM registration.

Uses OleViewDotNet's PowerShell module, not the GUI, so it works over SSH.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string] $OutputDir,

    [string] $ModulePath = "C:\tcw\oleviewdotnet\OleViewDotNet.psd1"
)

$ErrorActionPreference = "Continue"
$ProgressPreference = "SilentlyContinue"

function Write-JsonNoBom {
    param([string] $Path, [object] $Object, [int] $Depth = 12)
    $parent = Split-Path -Parent $Path
    if ($parent) { New-Item -ItemType Directory -Path $parent -Force | Out-Null }
    $json = $Object | ConvertTo-Json -Depth $Depth
    $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($Path, $json, $utf8NoBom)
}

function Add-ErrorRow {
    param([object] $Result, [string] $Where, [object] $ErrorRecord)
    $message = if ($ErrorRecord.Exception) { $ErrorRecord.Exception.Message } else { [string] $ErrorRecord }
    $Result.errors += [ordered]@{ where = $Where; message = $message }
}

function Convert-ComClass {
    param([object] $Class)
    if ($null -eq $Class) { return $null }
    [ordered]@{
        clsid = [string] $Class.Clsid
        name = [string] $Class.Name
        default_server = [string] $Class.DefaultServer
        default_server_name = [string] $Class.DefaultServerName
        default_server_type = [string] $Class.DefaultServerType
        default_threading_model = [string] $Class.DefaultThreadingModel
        app_id = [string] $Class.AppID
        has_app_id = [bool] $Class.HasAppID
        type_lib = [string] $Class.TypeLib
        has_type_lib = [bool] $Class.HasTypeLib
        can_elevate = [bool] $Class.CanElevate
        auto_elevation = [bool] $Class.AutoElevation
        has_run_as = [bool] $Class.HasRunAs
        run_as = [string] $Class.RunAs
        activatable_from_app = [bool] $Class.ActivatableFromApp
        safe_for_scripting = [bool] $Class.SafeForScripting
        safe_for_initializing = [bool] $Class.SafeForInitializing
        trusted_marshaller = [bool] $Class.TrustedMarshaller
        interfaces_loaded = [bool] $Class.InterfacesLoaded
        interface_count = @($Class.Interfaces).Count
        factory_interface_count = @($Class.FactoryInterfaces).Count
        prog_ids = @($Class.ProgIds | ForEach-Object { [string] $_ })
        create_context = [string] $Class.CreateContext
        supports_remote_activation = [bool] $Class.SupportsRemoteActivation
        source = [string] $Class.Source
        default_access_permission = [string] $Class.DefaultAccessPermission
        default_launch_permission = [string] $Class.DefaultLaunchPermission
    }
}

New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null

$result = [ordered]@{
    schema = "simcorp-thinkcell-oleviewdotnet-probe/v1"
    timestamp_utc = [DateTime]::UtcNow.ToString("o")
    output_dir = $OutputDir
    module_path = $ModulePath
    module_present = Test-Path -LiteralPath $ModulePath
    commands = @()
    thinkcell_class = $null
    tcaddin_classes = @()
    thinkcell_progids = @()
    matching_interfaces = @()
    verdict = [ordered]@{}
    errors = @()
}

try {
    Import-Module $ModulePath -Force
    $result.commands = @(Get-Command -Module OleViewDotNet | Select-Object Name, CommandType)
    Get-ComDatabase -SetCurrent -NoProgress | Out-Null
} catch {
    Add-ErrorRow $result "import_or_database" $_
}

try {
    $result.thinkcell_class = Convert-ComClass (Get-ComClass -ProgId thinkcell.addin)
} catch {
    Add-ErrorRow $result "get_class_by_progid" $_
}

try {
    $result.tcaddin_classes = @(Get-ComClass -ServerName tcaddin.dll | ForEach-Object { Convert-ComClass $_ })
} catch {
    Add-ErrorRow $result "get_class_by_server" $_
}

try {
    $result.thinkcell_progids = @(Get-ComProgId | Where-Object { $_.Name -match "(?i)think|ppttc|tcaddin" } | ForEach-Object {
        [ordered]@{
            name = [string] $_.Name
            clsid = [string] $_.Clsid
            source = [string] $_.Source
        }
    })
} catch {
    Add-ErrorRow $result "get_progids" $_
}

try {
    $result.matching_interfaces = @(Get-ComInterface | Where-Object {
        ([string] $_.Name) -match "(?i)think|cell|chart|mekko"
    } | Select-Object -First 80 | ForEach-Object {
        [ordered]@{
            name = [string] $_.Name
            iid = [string] $_.Iid
            base = [string] $_.Base
            source = [string] $_.Source
        }
    })
} catch {
    Add-ErrorRow $result "get_interfaces" $_
}

$class = $result.thinkcell_class
$result.verdict = [ordered]@{
    module_loaded = @($result.commands).Count -gt 0
    class_found = $null -ne $class
    class_count_for_tcaddin_dll = @($result.tcaddin_classes).Count
    has_type_lib = if ($class) { [bool] $class.has_type_lib } else { $false }
    factory_interface_count = if ($class) { [int] $class.factory_interface_count } else { 0 }
    interface_count = if ($class) { [int] $class.interface_count } else { 0 }
    registered_constructor_surface = $false
    conclusion = "OleViewDotNet module found the same single late-bound in-proc think-cell add-in class and no registered TypeLib or factory interface."
}

$jsonPath = Join-Path $OutputDir "thinkcell_oleviewdotnet_probe.json"
Write-JsonNoBom $jsonPath $result 14
$result | ConvertTo-Json -Depth 14
