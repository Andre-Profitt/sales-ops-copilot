#!/usr/bin/env bash
set -euo pipefail

VM="${RW_PBI_VM:-Windows 11}"
PBIP_MAC="${RW_PBI_PBIP_MAC:-$HOME/Downloads/rw-pbi-format-lab/rpt_vp_ops_scorecard_zebra_lab_20260509_pbip/rpt_vp_ops_scorecard_zebra_lab.pbip}"
REPORT_JSON="${RW_PBI_REPORT_JSON:-$HOME/Downloads/rw-pbi-format-lab/rpt_vp_ops_scorecard_zebra_lab_20260509_pbip/rpt_vp_ops_scorecard.Report/report.json}"
PBIP_WIN="${RW_PBI_PBIP_WIN:-C:\\Mac\\Home\\Downloads\\rw-pbi-format-lab\\rpt_vp_ops_scorecard_zebra_lab_20260509_pbip\\rpt_vp_ops_scorecard_zebra_lab.pbip}"
PBI_EXE="${RW_PBI_EXE:-C:\\Program Files\\Microsoft Power BI Desktop\\bin\\PBIDesktop.exe}"
RESET_CACHE=0

for arg in "$@"; do
  case "$arg" in
    --reset-cache) RESET_CACHE=1 ;;
    *) echo "unknown arg: $arg" >&2; exit 2 ;;
  esac
done

command -v prlctl >/dev/null
test -f "$PBIP_MAC"
test -f "$REPORT_JSON"

python3 - "$REPORT_JSON" <<'PY'
import json
import sys

path = sys.argv[1]
report = json.load(open(path))
what_changed = next(s for s in report["sections"] if s.get("displayName") == "What Changed")
encoded = "\n".join(v.get("config", "") for v in what_changed.get("visualContainers", []))
pastels = ("#ffeeee", "#fff8e6", "#eef9ee", "#FFEEEE", "#FFF8E6", "#EEF9EE")
if "Exception Movement" not in encoded:
    raise SystemExit("What Changed is missing the current Exception Movement header")
if any(color in encoded for color in pastels):
    raise SystemExit("What Changed still contains pastel status tile fills")
if any('"visualType": "card"' in v.get("config", "") for v in what_changed.get("visualContainers", [])):
    raise SystemExit("What Changed still contains card visuals")
print(f"verified report json: sections={len(report['sections'])} what_changed_visuals={len(what_changed['visualContainers'])}")
PY

echo "checking visible Windows user..."
prlctl exec "$VM" --current-user cmd /c "whoami && query user" 2>&1 | sed 's/\r$//' || true

echo "stopping Power BI Desktop session processes..."
for image in \
  PBIDesktop.exe \
  msedgewebview2.exe \
  msmdsrv.exe \
  Microsoft.Mashup.Container.exe \
  Microsoft.Mashup.Container.NetFX45.exe \
  powerbi-modeling-mcp.exe
do
  prlctl exec "$VM" --current-user taskkill /F /T /IM "$image" >/dev/null 2>&1 || true
done

if [[ "$RESET_CACHE" -eq 1 ]]; then
  echo "rotating current-user Power BI cache/recovery folders..."
  read -r -d '' RESET_PS <<'PS' || true
$base = Join-Path $env:LOCALAPPDATA 'Microsoft\Power BI Desktop'
$stamp = Get-Date -Format yyyyMMdd_HHmmss
foreach ($name in @('AutoRecovery','AnalysisServicesWorkspaces','Cache','TempSaves','WebView2')) {
  $path = Join-Path $base $name
  if (Test-Path $path) {
    Rename-Item -Path $path -NewName ($name + '_reset_' + $stamp) -ErrorAction SilentlyContinue
  }
}
foreach ($name in @('AutoRecovery','AnalysisServicesWorkspaces','Cache','TempSaves')) {
  New-Item -ItemType Directory -Force -Path (Join-Path $base $name) | Out-Null
}
Get-ChildItem -Force $base -Directory |
  Where-Object { $_.Name -match 'AutoRecovery|AnalysisServicesWorkspaces|Cache|TempSaves|WebView2' } |
  Select-Object Name,LastWriteTime |
  Format-Table -AutoSize
PS
  prlctl exec "$VM" --current-user powershell -NoProfile -ExecutionPolicy Bypass -Command "$RESET_PS" | sed 's/\r$//'
fi

echo "launching Power BI Desktop in the visible user session..."
LAUNCH_PS="Start-Process -FilePath '$PBI_EXE' -ArgumentList @('$PBIP_WIN')"
prlctl exec "$VM" --current-user powershell -NoProfile -ExecutionPolicy Bypass -Command "$LAUNCH_PS" >/dev/null

echo "waiting for PBIP window..."
for _ in {1..45}; do
  title="$(
    prlctl exec "$VM" --current-user powershell -NoProfile -Command "(Get-Process PBIDesktop -ErrorAction SilentlyContinue | Select-Object -First 1).MainWindowTitle" 2>/dev/null |
      tr -d '\r'
  )"
  if [[ "$title" == *"rpt_vp_ops_scorecard_zebra_lab"* ]]; then
    echo "opened: $title"
    exit 0
  fi
  sleep 2
done

echo "Power BI Desktop did not reach the expected PBIP window title." >&2
prlctl exec "$VM" --current-user powershell -NoProfile -Command "Get-Process PBIDesktop -ErrorAction SilentlyContinue | Select-Object ProcessName,Id,MainWindowTitle | Format-Table -AutoSize" | sed 's/\r$//' >&2
exit 1
