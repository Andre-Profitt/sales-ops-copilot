#!/usr/bin/env python3
"""Stage a think-cell bundle onto a private Azure VM and optionally run it.

This wrapper solves the practical Azure gap for the LAND monthly deck flow:

1. Zip a local Windows test/deploy bundle.
2. Upload it to a private Azure Storage container.
3. Generate a short-lived SAS URL for the uploaded bundle.
4. Use `az vm run-command invoke` to download and expand the bundle on the VM.
5. Optionally install think-cell from a local installer or direct installer URL.
6. Optionally run the existing `_windows_test/run_test.ps1` smoke path.

The script intentionally uses the Azure CLI as the auth/control plane so it
fits the rest of this repo's existing auth model (`az login`).
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from typing import Any
from zipfile import ZIP_DEFLATED, ZipFile


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_BUNDLE_DIR = ROOT / "_windows_test"
DEFAULT_CONTAINER = "soc-thinkcell"
DEFAULT_REMOTE_ROOT = r"C:\soc-thinkcell"


def _run(
    args: list[str],
    *,
    capture_output: bool = True,
    check: bool = True,
    text: bool = True,
) -> subprocess.CompletedProcess[str]:
    proc = subprocess.run(args, capture_output=capture_output, text=text, check=False)
    if check and proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip()
        cmd = " ".join(args)
        raise RuntimeError(f"command failed ({proc.returncode}): {cmd}\n{detail}")
    return proc


def _az_json(args: list[str]) -> Any:
    proc = _run(["az", *args, "-o", "json"])
    payload = proc.stdout.strip()
    if not payload:
        return None
    return json.loads(payload)


def _ps_quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _utc_expiry(hours: int) -> str:
    return (dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=hours)).strftime("%Y-%m-%dT%H:%MZ")


def _utc_stamp() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _discover_storage_account(subscription: str, resource_group: str) -> str:
    query = (
        "Resources "
        "| where type =~ 'microsoft.storage/storageaccounts' "
        f"| where subscriptionId =~ '{subscription}' and resourceGroup =~ '{resource_group}' "
        "| project name, kind, location "
        "| order by iif(kind =~ 'StorageV2', 0, 1) asc, name asc"
    )
    data = _az_json(["graph", "query", "-q", query, "--first", "20"])
    rows = data.get("data", []) if isinstance(data, dict) else []
    if not rows:
        raise RuntimeError(
            f"no storage accounts found in subscription={subscription} resource_group={resource_group}"
        )
    return rows[0]["name"]


def _storage_key(subscription: str, resource_group: str, account_name: str) -> str:
    keys = _az_json(
        [
            "storage",
            "account",
            "keys",
            "list",
            "--subscription",
            subscription,
            "-g",
            resource_group,
            "-n",
            account_name,
        ]
    )
    if not keys:
        raise RuntimeError(f"no storage keys returned for {account_name}")
    return keys[0]["value"]


def _ensure_container(account_name: str, account_key: str, container: str) -> None:
    _run(
        [
            "az",
            "storage",
            "container",
            "create",
            "--account-name",
            account_name,
            "--account-key",
            account_key,
            "--name",
            container,
            "-o",
            "none",
        ]
    )


def _zip_bundle(bundle_dir: Path, stamp: str) -> Path:
    if not bundle_dir.exists():
        raise RuntimeError(f"bundle directory not found: {bundle_dir}")
    if not bundle_dir.is_dir():
        raise RuntimeError(f"bundle path is not a directory: {bundle_dir}")

    tmp_dir = Path(tempfile.mkdtemp(prefix="thinkcell-azure-"))
    zip_path = tmp_dir / f"{bundle_dir.name}-{stamp}.zip"
    with ZipFile(zip_path, "w", compression=ZIP_DEFLATED) as zf:
        for path in sorted(bundle_dir.rglob("*")):
            if path.is_dir():
                continue
            if path.name == ".DS_Store":
                continue
            zf.write(path, arcname=path.relative_to(bundle_dir))
    return zip_path


def _upload_blob(
    *,
    account_name: str,
    account_key: str,
    container: str,
    blob_name: str,
    file_path: Path,
) -> None:
    _run(
        [
            "az",
            "storage",
            "blob",
            "upload",
            "--account-name",
            account_name,
            "--account-key",
            account_key,
            "--container-name",
            container,
            "--name",
            blob_name,
            "--file",
            str(file_path),
            "--overwrite",
            "true",
            "-o",
            "none",
        ]
    )


def _blob_url(account_name: str, container: str, blob_name: str, sas_token: str) -> str:
    return f"https://{account_name}.blob.core.windows.net/{container}/{blob_name}?{sas_token}"


def _blob_sas(
    *,
    account_name: str,
    account_key: str,
    container: str,
    blob_name: str,
    expiry: str,
) -> str:
    proc = _run(
        [
            "az",
            "storage",
            "blob",
            "generate-sas",
            "--account-name",
            account_name,
            "--account-key",
            account_key,
            "--container-name",
            container,
            "--name",
            blob_name,
            "--permissions",
            "r",
            "--expiry",
            expiry,
            "-o",
            "tsv",
        ]
    )
    token = proc.stdout.strip()
    if not token:
        raise RuntimeError(f"failed to generate SAS for {blob_name}")
    return token


def _delete_blob(account_name: str, account_key: str, container: str, blob_name: str) -> None:
    _run(
        [
            "az",
            "storage",
            "blob",
            "delete",
            "--account-name",
            account_name,
            "--account-key",
            account_key,
            "--container-name",
            container,
            "--name",
            blob_name,
            "-o",
            "none",
        ]
    )


def _build_remote_script(
    *,
    session_dir_name: str,
    remote_root: str,
    bundle_url: str,
    installer_url: str | None,
    run_smoke: bool,
    setup_ssh: bool,
    license_key: str | None,
) -> str:
    ppt_candidates = [
        r"C:\Program Files\Microsoft Office\root\Office16\POWERPNT.EXE",
        r"C:\Program Files (x86)\Microsoft Office\root\Office16\POWERPNT.EXE",
        r"C:\Program Files\Microsoft Office\Office16\POWERPNT.EXE",
        r"C:\Program Files (x86)\Microsoft Office\Office16\POWERPNT.EXE",
    ]
    tc_candidates = [
        r"C:\Program Files\think-cell\think-cell.exe",
        r"C:\Program Files (x86)\think-cell\think-cell.exe",
        r"C:\Users\*\AppData\Local\Programs\think-cell\think-cell.exe",
    ]
    ppttc_candidates = [
        r"C:\Program Files\think-cell\ppttc.exe",
        r"C:\Program Files (x86)\think-cell\ppttc.exe",
        r"%LOCALAPPDATA%\think-cell\ppttc.exe",
    ]

    installer_block = "$null" if installer_url is None else _ps_quote(installer_url)
    license_block = "$null" if license_key is None else _ps_quote(license_key)
    run_smoke_literal = "$true" if run_smoke else "$false"
    setup_ssh_literal = "$true" if setup_ssh else "$false"

    return f"""
$ErrorActionPreference = 'Stop'

function Find-FirstExisting([string[]]$paths) {{
  foreach ($candidate in $paths) {{
    $expanded = [Environment]::ExpandEnvironmentVariables($candidate)
    if ($expanded.Contains('*')) {{
      $matches = Get-ChildItem -Path $expanded -ErrorAction SilentlyContinue | Select-Object -ExpandProperty FullName
      foreach ($match in $matches) {{
        if (Test-Path $match) {{ return $match }}
      }}
    }} elseif (Test-Path $expanded) {{
      return $expanded
    }}
  }}
  return $null
}}

$result = [ordered]@{{
  status = 'ok'
  startUtc = [DateTime]::UtcNow.ToString('yyyy-MM-ddTHH:mm:ssZ')
  computerName = $env:COMPUTERNAME
}}

try {{
  $remoteRoot = {_ps_quote(remote_root)}
  $sessionDir = Join-Path $remoteRoot {_ps_quote(session_dir_name)}
  $bundleDir = Join-Path $sessionDir 'bundle'
  $bundleZip = Join-Path $sessionDir 'bundle.zip'
  $installerUrl = {installer_block}
  $licenseKey = {license_block}
  $runSmoke = {run_smoke_literal}
  $setupSsh = {setup_ssh_literal}

  New-Item -ItemType Directory -Force -Path $bundleDir | Out-Null
  Invoke-WebRequest -UseBasicParsing -Uri {_ps_quote(bundle_url)} -OutFile $bundleZip
  Expand-Archive -LiteralPath $bundleZip -DestinationPath $bundleDir -Force

  $result.sessionDir = $sessionDir
  $result.bundleDir = $bundleDir
  $result.bundleFiles = @(Get-ChildItem -LiteralPath $bundleDir -Force | Select-Object -ExpandProperty Name)

  $pptCandidates = @({", ".join(_ps_quote(p) for p in ppt_candidates)})
  $tcCandidates = @({", ".join(_ps_quote(p) for p in tc_candidates)})
  $ppttcCandidates = @({", ".join(_ps_quote(p) for p in ppttc_candidates)})

  $result.powerPointPath = Find-FirstExisting $pptCandidates
  try {{
    $pp = New-Object -ComObject PowerPoint.Application
    $result.powerPointCom = 'ok'
    try {{ $pp.Quit() }} catch {{}}
  }} catch {{
    $result.powerPointCom = 'fail'
    $result.powerPointComError = $_.Exception.Message
  }}

  if ($installerUrl) {{
    $installerPath = Join-Path $sessionDir 'think-cell-setup.exe'
    Invoke-WebRequest -UseBasicParsing -Uri $installerUrl -OutFile $installerPath
    $stylePath = Join-Path $bundleDir 'SimCorp-thinkcell-style.xml'
    $installerArgs = @('/qb', 'ALLUSERS=1', 'NOFIRSTSTART=1')
    if (Test-Path $stylePath) {{
      $installerArgs += ('DEFAULTSTYLE=' + $stylePath)
    }}
    if ($licenseKey) {{
      $installerArgs += ('LICENSEKEY=' + $licenseKey)
    }}
    $proc = Start-Process -FilePath $installerPath -ArgumentList $installerArgs -PassThru -Wait
    $result.installerExitCode = $proc.ExitCode
    $result.installerPath = $installerPath
  }}

  $result.thinkCellExe = Find-FirstExisting $tcCandidates
  $result.ppttcPath = Find-FirstExisting $ppttcCandidates

  if ($setupSsh) {{
    $setupScript = Join-Path $bundleDir 'setup_ssh.ps1'
    if (Test-Path $setupScript) {{
      $sshLines = & powershell -ExecutionPolicy Bypass -File $setupScript 2>&1
      $result.setupSshExitCode = $LASTEXITCODE
      $result.setupSshOutput = [string]::Join("`n", ($sshLines | ForEach-Object {{ "$_" }}))
    }} else {{
      $result.setupSshExitCode = 1
      $result.setupSshOutput = 'setup_ssh.ps1 not found in bundle'
    }}
  }}

  if ($runSmoke) {{
    $runScript = Join-Path $bundleDir 'run_test.ps1'
    if (-not (Test-Path $runScript)) {{
      throw 'run_test.ps1 not found in bundle'
    }}
    $smokeLines = & powershell -ExecutionPolicy Bypass -File $runScript 2>&1
    $result.smokeExitCode = $LASTEXITCODE
    $result.smokeOutput = [string]::Join("`n", ($smokeLines | ForEach-Object {{ "$_" }}))
    $logPath = Join-Path $bundleDir 'ppttc-stdout.log'
    if (Test-Path $logPath) {{
      $result.smokeLogPath = $logPath
    }}
  }}
}} catch {{
  $result.status = 'error'
  $result.error = $_.Exception.Message
  $result.errorType = $_.Exception.GetType().FullName
}}

$result.endUtc = [DateTime]::UtcNow.ToString('yyyy-MM-ddTHH:mm:ssZ')
$result | ConvertTo-Json -Depth 8 -Compress

if ($result.status -ne 'ok') {{
  exit 1
}}
if ($result.Contains('installerExitCode') -and $result.installerExitCode -ne 0) {{
  exit $result.installerExitCode
}}
if ($result.Contains('smokeExitCode') -and $result.smokeExitCode -ne 0) {{
  exit $result.smokeExitCode
}}
"""


def _invoke_remote(
    *,
    subscription: str,
    resource_group: str,
    vm_name: str,
    script: str,
) -> tuple[int, dict[str, Any] | None, str, str]:
    proc = _run(
        [
            "az",
            "vm",
            "run-command",
            "invoke",
            "--subscription",
            subscription,
            "-g",
            resource_group,
            "-n",
            vm_name,
            "--command-id",
            "RunPowerShellScript",
            "--scripts",
            script,
            "-o",
            "json",
        ],
        check=False,
    )
    stdout_json: dict[str, Any] | None = None
    raw_stdout = ""
    raw_stderr = ""

    if proc.stdout.strip():
        payload = json.loads(proc.stdout)
        components = payload.get("value", [])
        stdout_parts: list[str] = []
        stderr_parts: list[str] = []
        for item in components:
            message = item.get("message", "")
            code = item.get("code", "")
            if "StdOut" in code:
                stdout_parts.append(message)
            elif "StdErr" in code:
                stderr_parts.append(message)
        raw_stdout = "\n".join(p.strip() for p in stdout_parts if p.strip())
        raw_stderr = "\n".join(p.strip() for p in stderr_parts if p.strip())
        if raw_stdout:
            lines = [line for line in raw_stdout.splitlines() if line.strip()]
            candidate = lines[-1]
            try:
                stdout_json = json.loads(candidate)
            except json.JSONDecodeError:
                stdout_json = None
    return proc.returncode, stdout_json, raw_stdout, raw_stderr


def _summarize(result: dict[str, Any] | None, raw_stdout: str, raw_stderr: str) -> int:
    if result is None:
        print("remote result: could not parse JSON payload", file=sys.stderr)
        if raw_stdout:
            print(raw_stdout, file=sys.stderr)
        if raw_stderr:
            print(raw_stderr, file=sys.stderr)
        return 2

    print(json.dumps(result, indent=2))
    if raw_stderr:
        print("\nremote stderr:")
        print(raw_stderr)

    if result.get("status") != "ok":
        return 2
    if result.get("installerExitCode") not in (None, 0):
        return int(result["installerExitCode"])
    if result.get("smokeExitCode") not in (None, 0):
        return int(result["smokeExitCode"])
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Deploy a think-cell Windows bundle to a private Azure VM via Storage + RunCommand."
    )
    ap.add_argument("--vm-subscription", required=True, help="Azure subscription id containing the target VM.")
    ap.add_argument("--vm-resource-group", required=True, help="Resource group containing the target VM.")
    ap.add_argument("--vm-name", required=True, help="Target Windows VM name.")
    ap.add_argument(
        "--storage-subscription",
        help="Azure subscription id containing the storage account. Defaults to --vm-subscription.",
    )
    ap.add_argument(
        "--storage-resource-group",
        help="Storage account resource group. Defaults to the VM resource group.",
    )
    ap.add_argument(
        "--storage-account",
        help="Storage account used as the handoff hop. If omitted, auto-discovers the first StorageV2 account in the storage resource group.",
    )
    ap.add_argument(
        "--container",
        default=DEFAULT_CONTAINER,
        help=f"Blob container used for staging (default: {DEFAULT_CONTAINER}).",
    )
    ap.add_argument(
        "--bundle-dir",
        type=Path,
        default=DEFAULT_BUNDLE_DIR,
        help=f"Local bundle directory to zip and deploy (default: {DEFAULT_BUNDLE_DIR}).",
    )
    ap.add_argument(
        "--installer-path",
        type=Path,
        help="Local think-cell setup executable (.exe) to upload and install on the VM.",
    )
    ap.add_argument(
        "--installer-url",
        help="Direct think-cell setup executable (.exe) URL the VM can download.",
    )
    ap.add_argument(
        "--license-key-env",
        help="Optional environment variable name containing a think-cell license key.",
    )
    ap.add_argument(
        "--blob-expiry-hours",
        type=int,
        default=6,
        help="Lifetime of generated SAS URLs in hours (default: 6).",
    )
    ap.add_argument(
        "--remote-root",
        default=DEFAULT_REMOTE_ROOT,
        help=f"Remote root directory on the VM (default: {DEFAULT_REMOTE_ROOT}).",
    )
    ap.add_argument(
        "--run-smoke",
        action="store_true",
        help="Run run_test.ps1 from the deployed bundle after staging/install.",
    )
    ap.add_argument(
        "--setup-ssh",
        action="store_true",
        help="Run setup_ssh.ps1 from the deployed bundle after staging/install.",
    )
    ap.add_argument(
        "--cleanup-blobs",
        action="store_true",
        help="Delete uploaded blobs after the remote step finishes.",
    )
    args = ap.parse_args()

    if args.installer_path and args.installer_url:
        raise SystemExit("Pass only one of --installer-path or --installer-url.")

    vm_subscription = args.vm_subscription
    storage_subscription = args.storage_subscription or vm_subscription
    storage_rg = args.storage_resource_group or args.vm_resource_group

    bundle_zip: Path | None = None
    try:
        storage_account = args.storage_account or _discover_storage_account(storage_subscription, storage_rg)
        license_key = None
        if args.license_key_env:
            license_key = os.environ.get(args.license_key_env)
            if not license_key:
                raise RuntimeError(f"environment variable not set or empty: {args.license_key_env}")

        bundle_dir = args.bundle_dir.expanduser().resolve()
        if args.installer_path:
            installer_path = args.installer_path.expanduser().resolve()
            if not installer_path.exists():
                raise RuntimeError(f"installer not found: {installer_path}")
        else:
            installer_path = None

        stamp = _utc_stamp()
        session_dir_name = f"run-{stamp}"
        expiry = _utc_expiry(args.blob_expiry_hours)

        bundle_zip = _zip_bundle(bundle_dir, stamp)
        storage_key = _storage_key(storage_subscription, storage_rg, storage_account)
        _ensure_container(storage_account, storage_key, args.container)

        bundle_blob = f"{session_dir_name}/{bundle_zip.name}"
        _upload_blob(
            account_name=storage_account,
            account_key=storage_key,
            container=args.container,
            blob_name=bundle_blob,
            file_path=bundle_zip,
        )
        bundle_sas = _blob_sas(
            account_name=storage_account,
            account_key=storage_key,
            container=args.container,
            blob_name=bundle_blob,
            expiry=expiry,
        )
        bundle_url = _blob_url(storage_account, args.container, bundle_blob, bundle_sas)

        installer_url = args.installer_url
        installer_blob = None
        if installer_path is not None:
            installer_blob = f"{session_dir_name}/{installer_path.name}"
            _upload_blob(
                account_name=storage_account,
                account_key=storage_key,
                container=args.container,
                blob_name=installer_blob,
                file_path=installer_path,
            )
            installer_sas = _blob_sas(
                account_name=storage_account,
                account_key=storage_key,
                container=args.container,
                blob_name=installer_blob,
                expiry=expiry,
            )
            installer_url = _blob_url(storage_account, args.container, installer_blob, installer_sas)

        script = _build_remote_script(
            session_dir_name=session_dir_name,
            remote_root=args.remote_root,
            bundle_url=bundle_url,
            installer_url=installer_url,
            run_smoke=args.run_smoke,
            setup_ssh=args.setup_ssh,
            license_key=license_key,
        )
        rc, result, raw_stdout, raw_stderr = _invoke_remote(
            subscription=vm_subscription,
            resource_group=args.vm_resource_group,
            vm_name=args.vm_name,
            script=script,
        )

        if args.cleanup_blobs:
            try:
                if installer_blob is not None:
                    _delete_blob(storage_account, storage_key, args.container, installer_blob)
                _delete_blob(storage_account, storage_key, args.container, bundle_blob)
            except Exception as exc:  # pragma: no cover - best effort cleanup
                print(f"warning: blob cleanup failed: {exc}", file=sys.stderr)

        summary_rc = _summarize(result, raw_stdout, raw_stderr)
        if summary_rc != 0:
            return summary_rc
        if rc != 0:
            return rc
        return 0
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    finally:
        if bundle_zip is not None:
            shutil.rmtree(bundle_zip.parent, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
