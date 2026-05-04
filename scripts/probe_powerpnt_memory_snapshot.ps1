<#
SENSITIVE: Memory dumps may contain decrypted credentials, license tokens, AI request bodies.
           Local Mac path only. Never push to git. Never paste content.

POWERPNT.exe userland minidump probe.

Use case: while PowerPoint is loaded with think-cell and the user inserts a
chart, take a MiniDumpWithFullMemory dump of POWERPNT.exe. The dump captures
heap state, stack frames, and live string/buffer contents -- useful for
finding decrypted credential material, pre-HMAC-input buffers, and AI
request bodies in flight.

Behaviour:
  1. Find POWERPNT.exe by name; bail with clear error if not running.
  2. Pre-flight working-set size check; require -AllowLargeDump if >1 GB.
  3. P/Invoke dbghelp.dll!MiniDumpWriteDump with MiniDumpWithFullMemory.
  4. Write the .dmp to $env:USERPROFILE\tc_memdump\<ts>\powerpnt.dmp.
  5. Emit a state JSON sidecar: dump path, dump size, pid, working set,
     module table filtered to tcaddin|tcasr|bcrypt|winhttp + their bases.

Switches:
  -OutputPath          path to write the JSON sidecar (Mac UNC ok).
  -DumpDir             override the default $env:USERPROFILE\tc_memdump\<ts>.
  -AllowLargeDump      proceed even if estimated dump size exceeds 1 GB.
  -DryRun              do not call MiniDumpWriteDump; just emit metadata.
                       (Used by parse-test and Andre to verify the bail paths.)
#>
[CmdletBinding()]
param(
    [string] $OutputPath,
    [string] $DumpDir,
    [switch] $AllowLargeDump,
    [switch] $DryRun
)

$ErrorActionPreference = "Continue"
$ProgressPreference = "SilentlyContinue"

function New-Result {
    [ordered]@{
        schema = "simcorp-powerpnt-memory-snapshot-probe/v1"
        timestamp_utc = [DateTime]::UtcNow.ToString("o")
        machine = [ordered]@{}
        powerpnt = [ordered]@{}
        dump = [ordered]@{}
        modules_of_interest = @()
        thinkcell_modules = @()
        verdict = [ordered]@{}
        errors = @()
    }
}
function Add-ErrorRow {
    param([object] $Result, [string] $Where, [object] $Err)
    $msg = if ($Err.Exception) { $Err.Exception.Message } else { [string] $Err }
    $Result.errors += [ordered]@{ where = $Where; message = $msg }
}

function Write-Result {
    param([object] $Result, [string] $Path)
    if (-not $Path) {
        $Result | ConvertTo-Json -Depth 100 -Compress
        return
    }
    $dir = Split-Path -Parent $Path
    if ($dir -and -not (Test-Path -LiteralPath $dir)) {
        New-Item -ItemType Directory -Path $dir -Force | Out-Null
    }
    $Result | ConvertTo-Json -Depth 100 | Set-Content -LiteralPath $Path -Encoding UTF8
    $Result | ConvertTo-Json -Depth 100 -Compress
}

$result = New-Result
$result.machine.os = (Get-CimInstance Win32_OperatingSystem).Caption
$result.machine.host = $env:COMPUTERNAME
$result.machine.user = $env:USERNAME
$result.machine.dry_run = [bool] $DryRun
$result.machine.allow_large_dump = [bool] $AllowLargeDump

# Step 1 -- find POWERPNT.exe
$pptProc = $null
try {
    $pptProc = Get-Process -Name POWERPNT -ErrorAction SilentlyContinue | Select-Object -First 1
} catch { Add-ErrorRow -Result $result -Where "find_powerpnt" -Err $_ }

if (-not $pptProc) {
    $result.verdict.status = "powerpnt_not_running"
    $result.verdict.message = "POWERPNT.exe is not running. Open PowerPoint with think-cell loaded, then re-run."
    Write-Result -Result $result -Path $OutputPath
    exit 0
}

$result.powerpnt.pid = $pptProc.Id
$result.powerpnt.process_name = $pptProc.ProcessName
$result.powerpnt.working_set_bytes = [int64] $pptProc.WorkingSet64
$result.powerpnt.private_bytes = [int64] $pptProc.PrivateMemorySize64
$result.powerpnt.virtual_bytes = [int64] $pptProc.VirtualMemorySize64
$result.powerpnt.module_count = $pptProc.Modules.Count
try { $result.powerpnt.start_time = $pptProc.StartTime.ToString("o") } catch {}
try { $result.powerpnt.main_window_title = [string] $pptProc.MainWindowTitle } catch {}

# Step 2 -- module enumeration filtered to tcaddin|tcasr|bcrypt|winhttp and any think-cell-named module
try {
    $modOfInterestRegex = "(?i)tcaddin|tcasr|bcrypt|winhttp"
    $tcModuleRegex = "(?i)tc|think"
    foreach ($m in $pptProc.Modules) {
        $entry = [ordered]@{
            name = $m.ModuleName
            file = $m.FileName
            base_address = "0x" + $m.BaseAddress.ToInt64().ToString("X16")
            module_size = $m.ModuleMemorySize
        }
        try { $entry.file_version = (Get-Item -LiteralPath $m.FileName -ErrorAction SilentlyContinue).VersionInfo.FileVersion } catch {}
        if ($m.ModuleName -match $modOfInterestRegex -or $m.FileName -match $modOfInterestRegex) {
            $result.modules_of_interest += $entry
        }
        if ($m.ModuleName -match $tcModuleRegex -or $m.FileName -match "(?i)think.cell") {
            $result.thinkcell_modules += $entry
        }
    }
} catch { Add-ErrorRow -Result $result -Where "module_enum" -Err $_ }

# Step 3 -- size cap
$estimatedBytes = [int64] $pptProc.WorkingSet64
$oneGb = [int64] 1073741824
$result.dump.estimated_bytes = $estimatedBytes
$result.dump.estimated_mb = [math]::Round($estimatedBytes / 1MB, 1)
$result.dump.size_cap_bytes = $oneGb
if ($estimatedBytes -gt $oneGb -and -not $AllowLargeDump) {
    $result.verdict.status = "size_cap_exceeded"
    $result.verdict.message = "POWERPNT working set is $([math]::Round($estimatedBytes / 1MB, 1)) MB which exceeds the 1024 MB cap. Re-run with -AllowLargeDump to proceed."
    Write-Result -Result $result -Path $OutputPath
    exit 0
}

# Step 4 -- resolve dump dir + path
if (-not $DumpDir) {
    $ts = (Get-Date).ToString("yyyyMMdd-HHmmss")
    $DumpDir = Join-Path $env:USERPROFILE "tc_memdump\$ts"
}
if (-not (Test-Path -LiteralPath $DumpDir)) {
    New-Item -ItemType Directory -Path $DumpDir -Force | Out-Null
}
$dumpPath = Join-Path $DumpDir "powerpnt.dmp"
$result.dump.dir = $DumpDir
$result.dump.path = $dumpPath

if ($DryRun) {
    $result.verdict.status = "dry_run_ok"
    $result.verdict.message = "Dry run requested -- skipped MiniDumpWriteDump. Pre-flight checks passed."
    Write-Result -Result $result -Path $OutputPath
    exit 0
}

# Step 5 -- P/Invoke dbghelp!MiniDumpWriteDump
$dumpOk = $false
try {
    if (-not ("Tc.MiniDump" -as [type])) {
        $sig = @"
using System;
using System.IO;
using System.Runtime.InteropServices;
using Microsoft.Win32.SafeHandles;

namespace Tc {
    public static class MiniDump {
        [Flags]
        public enum Type : uint {
            MiniDumpNormal = 0x00000000,
            MiniDumpWithDataSegs = 0x00000001,
            MiniDumpWithFullMemory = 0x00000002,
            MiniDumpWithHandleData = 0x00000004,
            MiniDumpWithThreadInfo = 0x00001000,
            MiniDumpWithUnloadedModules = 0x00000020,
            MiniDumpWithFullMemoryInfo = 0x00000800,
            MiniDumpWithProcessThreadData = 0x00000100
        }

        [DllImport("dbghelp.dll", EntryPoint = "MiniDumpWriteDump", CallingConvention = CallingConvention.StdCall, CharSet = CharSet.Unicode, ExactSpelling = true, SetLastError = true)]
        private static extern bool MiniDumpWriteDump(
            IntPtr hProcess,
            uint processId,
            SafeHandle hFile,
            Type dumpType,
            IntPtr exceptionParam,
            IntPtr userStreamParam,
            IntPtr callbackParam);

        public static void Write(int pid, string path, Type type) {
            using (var p = System.Diagnostics.Process.GetProcessById(pid)) {
                using (var fs = new FileStream(path, FileMode.Create, FileAccess.Write)) {
                    bool ok = MiniDumpWriteDump(
                        p.Handle,
                        (uint)pid,
                        fs.SafeFileHandle,
                        type,
                        IntPtr.Zero,
                        IntPtr.Zero,
                        IntPtr.Zero);
                    if (!ok) {
                        int err = Marshal.GetLastWin32Error();
                        throw new System.ComponentModel.Win32Exception(err, "MiniDumpWriteDump failed (Win32=" + err + ")");
                    }
                }
            }
        }
    }
}
"@
        Add-Type -TypeDefinition $sig -Language CSharp -ErrorAction Stop | Out-Null
    }

    $combined = (
        [Tc.MiniDump+Type]::MiniDumpWithFullMemory -bor
        [Tc.MiniDump+Type]::MiniDumpWithHandleData -bor
        [Tc.MiniDump+Type]::MiniDumpWithThreadInfo -bor
        [Tc.MiniDump+Type]::MiniDumpWithUnloadedModules -bor
        [Tc.MiniDump+Type]::MiniDumpWithFullMemoryInfo -bor
        [Tc.MiniDump+Type]::MiniDumpWithProcessThreadData
    )
    $result.dump.flags = "MiniDumpWithFullMemory|HandleData|ThreadInfo|UnloadedModules|FullMemoryInfo|ProcessThreadData"
    $result.dump.flags_value = [uint32] $combined

    [Tc.MiniDump]::Write($pptProc.Id, $dumpPath, $combined)
    $dumpOk = $true
} catch {
    Add-ErrorRow -Result $result -Where "minidump_write" -Err $_
    $result.verdict.status = "minidump_failed"
    $result.verdict.message = "MiniDumpWriteDump raised an exception. See errors[]."
    Write-Result -Result $result -Path $OutputPath
    exit 1
}

# Step 6 -- verify dump exists
try {
    if (Test-Path -LiteralPath $dumpPath) {
        $info = Get-Item -LiteralPath $dumpPath
        $result.dump.actual_bytes = [int64] $info.Length
        $result.dump.actual_mb = [math]::Round($info.Length / 1MB, 1)
        $result.dump.created_utc = $info.CreationTimeUtc.ToString("o")
    }
} catch { Add-ErrorRow -Result $result -Where "verify_dump" -Err $_ }

if ($dumpOk -and $result.dump.actual_bytes -gt 0) {
    $result.verdict.status = "ok"
    $result.verdict.message = "Dump written to $dumpPath ($($result.dump.actual_mb) MB). Modules of interest: $($result.modules_of_interest.Count). Think-cell modules: $($result.thinkcell_modules.Count)."
} else {
    $result.verdict.status = "dump_missing_or_empty"
    $result.verdict.message = "MiniDumpWriteDump returned ok but dump file is missing or zero bytes."
}

Write-Result -Result $result -Path $OutputPath
exit 0
