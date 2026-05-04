#!/usr/bin/env bash
# Re-decompile tcaddin.dll x86_32 build (separate Ghidra project from the x86_64 run).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
GHIDRA_HOME="${ROOT}/state/thinkcell_bridge/ghidra/ghidra_12.0.4_PUBLIC"
DLL_LOCAL="${ROOT}/state/thinkcell_bridge/tcaddin_dll_x64/tcaddin.dll"  # actually x86_32 despite dir name
PROJECT_DIR="${ROOT}/state/thinkcell_bridge/ghidra/project"
PROJECT_NAME="tcaddin_x86_32"
TS=$(date +%Y%m%d-%H%M%S)
OUTPUT_DIR="${ROOT}/state/thinkcell_bridge/ghidra_decompile/${TS}_x86_32"
OUTPUT_JSONL="${OUTPUT_DIR}/functions.jsonl"
SCRIPT_DIR="${ROOT}/scripts/ghidra_scripts"
LOG_DIR="${ROOT}/state/thinkcell_bridge/ghidra"
ANALYZE_LOG="${LOG_DIR}/analyze_x86_32.log"
EXPORT_LOG="${LOG_DIR}/export_x86_32.log"

mkdir -p "${PROJECT_DIR}" "${OUTPUT_DIR}"

if [ ! -f "${DLL_LOCAL}" ]; then
  echo "ERROR: $DLL_LOCAL missing"; exit 1
fi

if [ ! -f "${SCRIPT_DIR}/ExportFunctionsToJsonl.java" ]; then
  echo "ERROR: $SCRIPT_DIR/ExportFunctionsToJsonl.java missing"; exit 1
fi

export TCADDIN_OUTPUT_JSONL="${OUTPUT_JSONL}"

# Apple's /usr/bin/java is a stub. ALWAYS prefer brew openjdk@21 if present.
if [ -d /opt/homebrew/opt/openjdk@21/bin ]; then
  export PATH=/opt/homebrew/opt/openjdk@21/bin:$PATH
  export JAVA_HOME=/opt/homebrew/opt/openjdk@21
elif [ -d /usr/local/opt/openjdk@21/bin ]; then
  export PATH=/usr/local/opt/openjdk@21/bin:$PATH
  export JAVA_HOME=/usr/local/opt/openjdk@21
fi

if ! java -version >/dev/null 2>&1; then
  echo "ERROR: java not runnable; PATH=$PATH JAVA_HOME=$JAVA_HOME"; exit 1
fi
echo "[ghidra-x86_32] Java: $(java -version 2>&1 | head -1)"

echo "[ghidra-x86_32] PHASE 1: import + auto-analyze x86_32 build"
echo "[ghidra-x86_32] DLL: ${DLL_LOCAL}"
echo "[ghidra-x86_32] OUT: ${OUTPUT_JSONL}"
echo "[ghidra-x86_32] LOG: ${ANALYZE_LOG}"

"${GHIDRA_HOME}/support/analyzeHeadless" \
  "${PROJECT_DIR}" "${PROJECT_NAME}" \
  -import "${DLL_LOCAL}" \
  -overwrite \
  -processor "x86:LE:32:default" \
  -log "${ANALYZE_LOG}" \
  -max-cpu 8 \
  2>&1 | tail -15

echo "[ghidra-x86_32] PHASE 2: export decompiled functions"

"${GHIDRA_HOME}/support/analyzeHeadless" \
  "${PROJECT_DIR}" "${PROJECT_NAME}" \
  -process tcaddin.dll \
  -noanalysis \
  -postScript ExportFunctionsToJsonl \
  -scriptPath "${SCRIPT_DIR}" \
  -log "${EXPORT_LOG}" \
  2>&1 | tail -10

if [ -f "${OUTPUT_JSONL}" ]; then
  COUNT=$(wc -l < "${OUTPUT_JSONL}")
  echo "[ghidra-x86_32] DONE — ${COUNT} functions written to ${OUTPUT_JSONL}"
else
  echo "[ghidra-x86_32] FAILED — no output file"
  exit 1
fi
