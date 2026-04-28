#!/usr/bin/env python3
"""Verify every credential the brief needs. Run before brief.py."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys


def run(cmd: list[str], merge_stderr: bool = False) -> tuple[int, str]:
    p = subprocess.run(cmd, capture_output=True, text=True)
    out = (p.stdout + p.stderr) if merge_stderr else p.stdout
    return p.returncode, out.strip()


def check(label: str, ok: bool, detail: str = "") -> bool:
    mark = "✓" if ok else "✗"
    print(f"  {mark} {label}{(' — ' + detail) if detail else ''}")
    return ok


def main() -> int:
    print("Preflight check\n")
    failures = 0

    # az
    if not shutil.which("az"):
        check("az CLI installed", False, "install with: brew install azure-cli")
        failures += 1
    else:
        rc, out = run(["az", "account", "show", "--query", "user.name", "-o", "tsv"])
        if rc == 0 and "@simcorp.com" in out:
            check("az authenticated as SimCorp user", True, out)
        else:
            check("az authenticated as SimCorp user", False, "run: az login")
            failures += 1

    # sf CLI
    if not shutil.which("sf"):
        check("sf CLI installed", False, "install with: npm install -g @salesforce/cli")
        failures += 1
    else:
        rc, out = run(["sf", "org", "list", "--json"])
        if rc == 0 and out:
            try:
                result = json.loads(out).get("result", {})
                # Connected orgs can show up under nonScratchOrgs, other, sandboxes, devHubs
                pools = ("nonScratchOrgs", "other", "sandboxes", "devHubs")
                all_orgs = [o for k in pools for o in result.get(k, [])]
                connected = [o for o in all_orgs if o.get("connectedStatus") == "Connected"]
                if connected:
                    user = connected[0].get("username", "?")
                    check("sf CLI org connected", True, user)
                else:
                    check("sf CLI org connected", False, "run: sf org login web")
                    failures += 1
            except json.JSONDecodeError:
                check("sf CLI org connected", False, "could not parse org list")
                failures += 1
        else:
            check("sf CLI org connected", False, f"sf returned rc={rc}")
            failures += 1

    # Power BI / Fabric API
    rc, out = run(
        [
            "az",
            "rest",
            "--method",
            "get",
            "--resource",
            "https://analysis.windows.net/powerbi/api",
            "--uri",
            "https://api.powerbi.com/v1.0/myorg/groups?$top=1",
            "--query",
            "value[0].name",
            "-o",
            "tsv",
        ]
    )
    if rc == 0 and out:
        check("Power BI / Fabric API reachable", True, f"sample workspace: {out}")
    else:
        check("Power BI / Fabric API reachable", False, out[:120])
        failures += 1

    # apro-openai endpoint reachable (no key required - we use AAD)
    rc, out = run(
        [
            "az",
            "cognitiveservices",
            "account",
            "show",
            "--name",
            "apro-openai",
            "--resource-group",
            "rg-claude-code",
            "--query",
            "properties.endpoint",
            "-o",
            "tsv",
        ]
    )
    if rc == 0 and out:
        check("apro-openai endpoint resolved", True, out)
    else:
        check("apro-openai endpoint resolved", False, out[:120])
        failures += 1

    # apro-openai deployments
    rc, out = run(
        [
            "az",
            "cognitiveservices",
            "account",
            "deployment",
            "list",
            "--name",
            "apro-openai",
            "--resource-group",
            "rg-claude-code",
            "--query",
            "[].name",
            "-o",
            "tsv",
        ]
    )
    if rc == 0 and out:
        deployments = out.split()
        check("apro-openai deployments", True, ", ".join(deployments))
    else:
        check("apro-openai deployments", False, "no deployments returned")
        failures += 1

    # _filters.py drift check vs sibling repo (account-drilldown)
    rc, _ = run([sys.executable, "scripts/check_filters_sync.py"])
    if rc == 0:
        check("_filters.py in sync with account-drilldown", True)
    else:
        check(
            "_filters.py in sync with account-drilldown",
            False,
            "run: python3 scripts/check_filters_sync.py",
        )
        failures += 1

    print()
    if failures == 0:
        print("All checks passed. You're ready to run brief.py.")
        return 0
    print(f"{failures} check(s) failed. Fix above before running brief.py.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
