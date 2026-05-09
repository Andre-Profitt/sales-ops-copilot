"""Build the local Power BI Desktop formatting lab for RW VP Ops.

This is Path A support tooling: use Fabric REST on the Mac to export the live
report definition into the Parallels shared folder, then open that PBIP wrapper
from Windows Power BI Desktop for renderer-validated formatting/capture work.

Usage:
    python3 -m scripts.sales.rw_pbi_desktop_lab
    python3 -m scripts.sales.rw_pbi_desktop_lab --launch
"""

from __future__ import annotations

import argparse
import base64
import csv
import json
import subprocess
import time
from pathlib import Path

import requests
from azure.identity import AzureCliCredential

WORKSPACE_ID = "b66233d5-9d4a-44ba-89a8-b70206d98ae7"
REPORT_ID = "d7362a11-f3dd-4bd1-a69a-68c941c2598b"
REPORT_NAME = "rpt_vp_ops_scorecard"

FABRIC = "https://api.fabric.microsoft.com"
FABRIC_RES = "https://api.fabric.microsoft.com/.default"

DEFAULT_LAB_DIR = Path.home() / "Downloads" / "rw-pbi-format-lab"
DEFAULT_VM = "Windows 11"
DEFAULT_WINDOWS_USER = "TESTB04E\\test"
POWERBI_EXE = r"C:\Program Files\Microsoft Power BI Desktop\bin\PBIDesktop.exe"


LAB_ROWS = [
    [
        "Status",
        "Metric",
        "Count",
        "ARR",
        "Secondary",
        "Definition",
        "ForwardPct",
        "DaysStalled",
        "Coverage",
    ],
    [
        "At Risk",
        "Low forward rate",
        "14",
        "12500000",
        "Below target",
        "Forward rate < 70%",
        "0.42",
        "31",
        "1.8",
    ],
    [
        "Watch",
        "Stalled late stage",
        "9",
        "7200000",
        "Needs inspection",
        "Stage age above threshold",
        "0.61",
        "18",
        "2.4",
    ],
    [
        "Healthy",
        "On plan",
        "38",
        "23100000",
        "No immediate action",
        "Stage motion and coverage green",
        "0.78",
        "7",
        "3.6",
    ],
    [
        "Stage Moves",
        "Moved stage in 7d",
        "21",
        "16400000",
        "Comprehensive movement",
        "Forward/backward movement window",
        "0.74",
        "5",
        "3.1",
    ],
    [
        "Slips",
        "Close date slipped",
        "7",
        "5100000",
        "Needs OFH ETL",
        "Deferred until close-date history lands",
        "0.55",
        "22",
        "2.0",
    ],
    [
        "New Opps",
        "Created in 7d",
        "12",
        "8300000",
        "ARR only",
        "Land + Expand only",
        "0.71",
        "3",
        "2.9",
    ],
    [
        "Closed",
        "Won in 7d",
        "5",
        "3900000",
        "ARR only",
        "Land + Expand only",
        "0.82",
        "0",
        "3.4",
    ],
]


def _token() -> str:
    return AzureCliCredential().get_token(FABRIC_RES).token


def _wait_lro(resp: requests.Response, token: str) -> dict:
    if resp.status_code in (200, 201):
        return resp.json() if resp.text else {}
    if resp.status_code != 202:
        resp.raise_for_status()

    location = resp.headers.get("Location") or (
        f"{FABRIC}/v1/operations/{resp.headers['x-ms-operation-id']}"
    )
    while True:
        time.sleep(int(resp.headers.get("Retry-After", 3)))
        status = requests.get(location, headers={"Authorization": f"Bearer {token}"})
        status.raise_for_status()
        body = status.json()
        if body.get("status") == "Succeeded":
            result = requests.get(
                f"{location}/result",
                headers={"Authorization": f"Bearer {token}"},
            )
            result.raise_for_status()
            return result.json() if result.text else {}
        if body.get("status") == "Failed":
            raise RuntimeError(f"Fabric operation failed: {body}")


def fetch_live_definition() -> list[dict]:
    """Return decoded Fabric report definition parts for rpt_vp_ops_scorecard."""
    token = _token()
    resp = requests.post(
        f"{FABRIC}/v1/workspaces/{WORKSPACE_ID}/reports/{REPORT_ID}/getDefinition",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
    data = _wait_lro(resp, token)
    parts = data["definition"]["parts"]
    required = {"definition.pbir", "report.json"}
    present = {part["path"] for part in parts}
    missing = required - present
    if missing:
        raise RuntimeError(f"Fabric definition is missing required part(s): {sorted(missing)}")
    return parts


def write_pbip(parts: list[dict], lab_dir: Path) -> Path:
    """Write a local PBIP wrapper that points at the decoded live report definition."""
    root = lab_dir / f"{REPORT_NAME}_live_pbip"
    report_dir = root / f"{REPORT_NAME}.Report"
    report_dir.mkdir(parents=True, exist_ok=True)

    for part in parts:
        path = report_dir / part["path"]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(base64.b64decode(part["payload"]))

    pbip_path = root / f"{REPORT_NAME}.pbip"
    pbip = {
        "version": "1.0",
        "artifacts": [{"report": {"path": f"{REPORT_NAME}.Report"}}],
        "settings": {"enableAutoRecovery": True},
    }
    pbip_path.write_text(json.dumps(pbip, indent=2) + "\n", encoding="utf-8")
    (root / ".gitignore").write_text(
        "**/.pbi/localSettings.json\n**/.pbi/cache.abf\n",
        encoding="utf-8",
    )
    return pbip_path


def write_dummy_data(lab_dir: Path) -> Path:
    """Write a tiny CSV for manual card/table formatting experiments."""
    lab_dir.mkdir(parents=True, exist_ok=True)
    path = lab_dir / "rw_format_lab_data.csv"
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerows(LAB_ROWS)
    return path


def write_readme(lab_dir: Path, pbip_path: Path, csv_path: Path) -> Path:
    readme = lab_dir / "rw_format_lab_readme.md"
    readme.write_text(
        f"""# RW Power BI Desktop formatting lab

Generated by `python3 -m scripts.sales.rw_pbi_desktop_lab`.

Mac folder:

`{lab_dir}`

Windows folder:

`{windows_path(lab_dir)}`

Open this PBIP in Windows Power BI Desktop:

`{windows_path(pbip_path)}`

Use this CSV only for isolated formatting experiments when the live report will
not open or sign-in is blocked:

`{windows_path(csv_path)}`

Capture renderer-validated visuals after save:

`python3 -m scripts.sales.rw_capture_visual --list --page "What Changed"`
`python3 -m scripts.sales.rw_capture_visual --extract <visual-name> --raw`

Business guardrail: ARR is Land + Expand only. ACV is Renewal only. Do not blend
them except for the explicitly labeled `Total Open Pipeline Value` measure.
""",
        encoding="utf-8",
    )
    return readme


def windows_path(path: Path) -> str:
    """Map a Mac home path to the default Parallels shared-folder path."""
    resolved = path.expanduser().resolve()
    home = Path.home().resolve()
    try:
        rel = resolved.relative_to(home)
    except ValueError:
        raise ValueError(f"{resolved} is outside {home}; cannot map to C:\\Mac\\Home") from None
    return r"C:\Mac\Home" + "\\" + "\\".join(rel.parts)


def launch_powerbi(pbip_path: Path, vm: str, windows_user: str) -> None:
    """Launch Power BI Desktop in the interactive Windows session via Task Scheduler."""
    win_pbip = windows_path(pbip_path)
    task_run = f'\\"{POWERBI_EXE}\\" \\"{win_pbip}\\"'
    create_and_run = (
        "schtasks /Create /TN RWOpenPBIP /SC ONCE /ST 23:59 "
        f'/TR "{task_run}" /RU {windows_user} /IT /F '
        "&& schtasks /Run /TN RWOpenPBIP"
    )
    delete_task = "schtasks /Delete /TN RWOpenPBIP /F"
    try:
        subprocess.run(["prlctl", "exec", vm, "cmd", "/c", create_and_run], check=True)
    finally:
        subprocess.run(["prlctl", "exec", vm, "cmd", "/c", delete_task], check=False)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[0])
    parser.add_argument("--lab-dir", type=Path, default=DEFAULT_LAB_DIR)
    parser.add_argument("--skip-live", action="store_true", help="Only write CSV/readme scaffolding")
    parser.add_argument("--launch", action="store_true", help="Launch the generated PBIP in Parallels")
    parser.add_argument("--vm", default=DEFAULT_VM)
    parser.add_argument("--windows-user", default=DEFAULT_WINDOWS_USER)
    args = parser.parse_args()

    args.lab_dir.mkdir(parents=True, exist_ok=True)
    csv_path = write_dummy_data(args.lab_dir)

    if args.skip_live:
        pbip_path = args.lab_dir / f"{REPORT_NAME}_live_pbip" / f"{REPORT_NAME}.pbip"
    else:
        print("fetching live Fabric report definition...")
        pbip_path = write_pbip(fetch_live_definition(), args.lab_dir)

    readme_path = write_readme(args.lab_dir, pbip_path, csv_path)
    print(f"lab: {args.lab_dir}")
    print(f"pbip: {pbip_path}")
    print(f"csv: {csv_path}")
    print(f"readme: {readme_path}")
    print(f"windows pbip: {windows_path(pbip_path)}")

    if args.launch:
        launch_powerbi(pbip_path, args.vm, args.windows_user)


if __name__ == "__main__":
    main()
