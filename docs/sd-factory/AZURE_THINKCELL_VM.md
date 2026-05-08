# Azure think-cell VM wrapper

Purpose: stage a Windows think-cell bundle onto a private Azure VM without RDP, using only `az`, Azure Storage, and `az vm run-command`.

This is the supported practical lane for the current LAND-monthly blocker:

1. Zip a local Windows bundle.
2. Upload it to a private blob container.
3. Generate a short-lived SAS URL.
4. Ask the VM to download and expand the bundle.
5. Optionally install think-cell.
6. Optionally run the existing Windows smoke script.

The wrapper is:

`scripts/deploy_thinkcell_azure_vm.py`

## Known Azure candidates

As of `2026-04-30`, these Windows client VMs were verified reachable with `az vm run-command` and able to instantiate `PowerPoint.Application`:

- `DK01WV2121` in subscription `7c2a340a-3a71-40b0-9dee-e48927a13d99` (`Front Office - Non VS Licensed`), resource group `rg-we-fo-om`
- `AZWEWV6021` in subscription `11e8126d-3338-4773-9910-177bde19b29a` (`Investment Book of Record`), resource group `rg-we-ibor`

At the time of that probe, PowerPoint was present on both, but `think-cell` / `ppttc.exe` was not yet installed.

## Bundle input

Default local bundle:

`_windows_test/`

That directory is expected to contain the Windows-side artifacts such as:

- `LAND_template.pptx`
- `SimCorp-thinkcell-style.xml`
- one or more `.ppttc` files
- `run_test.ps1`
- `setup_ssh.ps1`

The wrapper only requires a directory. It does not care whether the bundle is the default `_windows_test/` folder or a custom one.

## Example: stage only

This proves the Azure transport lane and returns a JSON summary from the VM:

```bash
python3 scripts/deploy_thinkcell_azure_vm.py \
  --vm-subscription 7c2a340a-3a71-40b0-9dee-e48927a13d99 \
  --vm-resource-group rg-we-fo-om \
  --vm-name DK01WV2121 \
  --storage-account sdiagrgwefoomad85f6a261f \
  --bundle-dir _windows_test
```

## Example: install think-cell from a local installer

If you have already downloaded the official Windows setup executable (`setup_*.exe`) from think-cell:

```bash
python3 scripts/deploy_thinkcell_azure_vm.py \
  --vm-subscription 7c2a340a-3a71-40b0-9dee-e48927a13d99 \
  --vm-resource-group rg-we-fo-om \
  --vm-name DK01WV2121 \
  --storage-account sdiagrgwefoomad85f6a261f \
  --bundle-dir _windows_test \
  --installer-path ~/Downloads/setup_think-cell.exe
```

The wrapper uploads the installer privately, then runs it on the VM using:

- `/qb`
- `ALLUSERS=1`
- `NOFIRSTSTART=1`
- `DEFAULTSTYLE=<bundle>\\SimCorp-thinkcell-style.xml` when the style file exists

That matches the current official think-cell deployment guidance for Windows installation parameters and default style configuration:

- https://www.think-cell.com/en/resources/manual/first-installation
- https://www.think-cell.com/en/resources/manual/deploy-default-style

## Example: full smoke

Once think-cell is installed on the VM:

```bash
python3 scripts/deploy_thinkcell_azure_vm.py \
  --vm-subscription 7c2a340a-3a71-40b0-9dee-e48927a13d99 \
  --vm-resource-group rg-we-fo-om \
  --vm-name DK01WV2121 \
  --storage-account sdiagrgwefoomad85f6a261f \
  --bundle-dir _windows_test \
  --run-smoke
```

That runs `_windows_test/run_test.ps1` remotely and returns:

- whether `ppttc.exe` exists
- whether the `.ppttc` path was rewritten
- whether a real output `.pptx` was produced
- the captured smoke output

## Optional: setup SSH

If you want the VM to expose OpenSSH Server for direct follow-up work:

```bash
python3 scripts/deploy_thinkcell_azure_vm.py \
  --vm-subscription 7c2a340a-3a71-40b0-9dee-e48927a13d99 \
  --vm-resource-group rg-we-fo-om \
  --vm-name DK01WV2121 \
  --storage-account sdiagrgwefoomad85f6a261f \
  --bundle-dir _windows_test \
  --setup-ssh
```

This just runs the existing `setup_ssh.ps1` in the bundle.

## Notes

- The wrapper uses the storage account key, not blob-RBAC, because the current SimCorp Azure login can enumerate containers and read management-plane keys but does not currently have data-plane blob upload rights with `--auth-mode login`.
- The storage handoff remains private. The VM downloads blobs through short-lived SAS URLs.
- No public IP or Bastion is required for the VM.
- This solves deployment and staging. It does not solve the separate template-authoring problem if the target `.ppttc` still points at an unwired template.
