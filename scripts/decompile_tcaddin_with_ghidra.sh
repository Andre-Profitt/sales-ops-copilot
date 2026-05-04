#!/usr/bin/env bash
# Phase 2 — Ghidra-headless decompile of tcaddin.dll
# Produces JSONL function database for downstream LLM labeling.
#
# Setup: ./decompile_tcaddin_with_ghidra.sh --setup
# Run:   ./decompile_tcaddin_with_ghidra.sh --decompile

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
GHIDRA_DIR="${ROOT}/state/thinkcell_bridge/ghidra"
# Resolve latest Ghidra release dynamically from GitHub API
GHIDRA_HOME=""  # will be set after extraction

DLL_REMOTE='C:\\Program Files (x86)\\think-cell\\arm64\\tcaddin.dll'
DLL_LOCAL="${ROOT}/state/thinkcell_bridge/tcaddin_dll/tcaddin.dll"
PROJECT_DIR="${GHIDRA_DIR}/project"
PROJECT_NAME="tcaddin"
OUTPUT_JSONL="${ROOT}/state/thinkcell_bridge/ghidra_decompile/$(date +%Y%m%d-%H%M%S)/functions.jsonl"

cmd="${1:-}"

case "$cmd" in
  --setup)
    echo "[ghidra] setting up at ${GHIDRA_DIR}"
    mkdir -p "${GHIDRA_DIR}"
    # Skip download if already extracted
    EXISTING=$(find "${GHIDRA_DIR}" -maxdepth 2 -type d -name "ghidra_*_PUBLIC" | head -1)
    if [ -n "${EXISTING}" ]; then
      echo "[ghidra] already extracted: ${EXISTING}"
    else
      # Resolve latest release from GitHub API
      echo "[ghidra] resolving latest release URL via GitHub API"
      RELEASE_JSON=$(curl -sL https://api.github.com/repos/NationalSecurityAgency/ghidra/releases/latest)
      DOWNLOAD_URL=$(echo "${RELEASE_JSON}" | grep -oE '"browser_download_url":\s*"[^"]+\.zip"' | head -1 | sed 's/.*"\([^"]*\)"$/\1/')
      if [ -z "${DOWNLOAD_URL}" ]; then
        echo "ERROR: failed to resolve Ghidra download URL from GitHub API"
        echo "Response was:"
        echo "${RELEASE_JSON}" | head -20
        exit 1
      fi
      echo "[ghidra] downloading: ${DOWNLOAD_URL}"
      rm -f "${GHIDRA_DIR}/ghidra.zip"
      curl -L --fail -o "${GHIDRA_DIR}/ghidra.zip" "${DOWNLOAD_URL}"
      ZIP_SIZE=$(stat -f%z "${GHIDRA_DIR}/ghidra.zip" 2>/dev/null || stat -c%s "${GHIDRA_DIR}/ghidra.zip")
      echo "[ghidra] downloaded ${ZIP_SIZE} bytes"
      if [ "${ZIP_SIZE}" -lt 100000000 ]; then
        echo "ERROR: ghidra.zip suspiciously small (${ZIP_SIZE} bytes); expected >100MB"
        head -c 500 "${GHIDRA_DIR}/ghidra.zip"
        exit 1
      fi
      (cd "${GHIDRA_DIR}" && unzip -q ghidra.zip)
      rm "${GHIDRA_DIR}/ghidra.zip"
    fi
    GHIDRA_HOME=$(find "${GHIDRA_DIR}" -maxdepth 2 -type d -name "ghidra_*_PUBLIC" | head -1)
    if ! command -v java >/dev/null 2>&1; then
      echo "[ghidra] WARN: Java JDK 21+ required. Install via 'brew install --cask temurin'"
    else
      echo "[ghidra] java: $(java --version | head -1)"
    fi
    echo "[ghidra] ready: ${GHIDRA_HOME}"
    ;;

  --pull-dll)
    echo "[ghidra] pulling tcaddin.dll from VM"
    mkdir -p "$(dirname "${DLL_LOCAL}")"
    scp Windows-VM:"${DLL_REMOTE}" "${DLL_LOCAL}"
    echo "[ghidra] tcaddin.dll: $(stat -f%z "${DLL_LOCAL}") bytes, sha256=$(shasum -a 256 "${DLL_LOCAL}" | awk '{print $1}')"
    ;;

  --decompile)
    GHIDRA_HOME=$(find "${GHIDRA_DIR}" -maxdepth 2 -type d -name "ghidra_*_PUBLIC" | head -1)
    if [ -z "${GHIDRA_HOME}" ] || [ ! -d "${GHIDRA_HOME}" ]; then
      echo "ERROR: Ghidra not installed. Run --setup first."
      exit 1
    fi
    if [ ! -f "${DLL_LOCAL}" ]; then
      echo "ERROR: ${DLL_LOCAL} missing. Run --pull-dll first."
      exit 1
    fi
    mkdir -p "${PROJECT_DIR}" "$(dirname "${OUTPUT_JSONL}")"
    SCRIPT_DIR="${ROOT}/scripts/ghidra_scripts"
    mkdir -p "${SCRIPT_DIR}"
    POSTSCRIPT="${SCRIPT_DIR}/ExportFunctionsToJsonl.java"
    cat > "${POSTSCRIPT}" <<'JAVA'
//@category Analysis
import ghidra.app.script.GhidraScript;
import ghidra.app.decompiler.*;
import ghidra.program.model.listing.*;
import ghidra.program.model.symbol.*;
import com.google.gson.*;
import java.io.*;
import java.util.*;

public class ExportFunctionsToJsonl extends GhidraScript {
    @Override
    public void run() throws Exception {
        String outPath = System.getenv("TCADDIN_OUTPUT_JSONL");
        if (outPath == null) outPath = "/tmp/tcaddin_functions.jsonl";
        DecompInterface decompiler = new DecompInterface();
        decompiler.openProgram(currentProgram);
        try (PrintWriter w = new PrintWriter(new FileWriter(outPath))) {
            FunctionIterator it = currentProgram.getFunctionManager().getFunctions(true);
            int count = 0;
            while (it.hasNext() && !monitor.isCancelled()) {
                Function f = it.next();
                JsonObject o = new JsonObject();
                o.addProperty("address", f.getEntryPoint().toString());
                o.addProperty("name", f.getName());
                o.addProperty("signature", f.getSignature().toString());
                o.addProperty("body_size", f.getBody().getNumAddresses());
                o.addProperty("calling_convention", f.getCallingConventionName());
                Symbol[] syms = currentProgram.getSymbolTable().getSymbols(f.getEntryPoint());
                JsonArray symbols = new JsonArray();
                for (Symbol s : syms) symbols.add(s.getName());
                o.add("symbols", symbols);
                try {
                    DecompileResults res = decompiler.decompileFunction(f, 60, monitor);
                    if (res != null && res.getDecompiledFunction() != null) {
                        o.addProperty("decompiled_c", res.getDecompiledFunction().getC());
                    }
                } catch (Exception e) {
                    o.addProperty("decompile_error", e.getMessage());
                }
                w.println(o.toString());
                count++;
                if (count % 500 == 0) println("decompiled " + count + " functions");
            }
            println("done: " + count + " functions");
        }
    }
}
JAVA
    export TCADDIN_OUTPUT_JSONL="${OUTPUT_JSONL}"
    # PHASE 1: import + auto-analyze (no post-script). Long step.
    if [ ! -f "${PROJECT_DIR}/${PROJECT_NAME}.gpr" ]; then
      echo "[ghidra] PHASE 1: import + auto-analyze (1-2 hours)"
      "${GHIDRA_HOME}/support/analyzeHeadless" \
        "${PROJECT_DIR}" "${PROJECT_NAME}" \
        -import "${DLL_LOCAL}" \
        -overwrite \
        -log "${GHIDRA_DIR}/analyze.log" \
        2>&1 | tail -10
      echo "[ghidra] PHASE 1 complete"
    else
      echo "[ghidra] PHASE 1 already done (${PROJECT_DIR}/${PROJECT_NAME}.gpr exists)"
    fi
    # PHASE 2: open analyzed project, run export script. Fast.
    echo "[ghidra] PHASE 2: running export on analyzed project"
    "${GHIDRA_HOME}/support/analyzeHeadless" \
      "${PROJECT_DIR}" "${PROJECT_NAME}" \
      -process tcaddin.dll \
      -noanalysis \
      -postScript ExportFunctionsToJsonl \
      -scriptPath "${SCRIPT_DIR}" \
      -log "${GHIDRA_DIR}/export.log" \
      2>&1 | tail -10
    echo "[ghidra] decompile complete"
    echo "[ghidra] output: ${OUTPUT_JSONL}"
    if [ -f "${OUTPUT_JSONL}" ]; then
      echo "[ghidra] $(wc -l < "${OUTPUT_JSONL}") functions decompiled"
    fi
    ;;

  *)
    cat <<EOF
Usage: $0 [--setup | --pull-dll | --decompile]

Steps:
  1. $0 --setup       Download Ghidra 11.4 to state/thinkcell_bridge/ghidra/
  2. $0 --pull-dll    Pull tcaddin.dll from Windows-VM via scp
  3. $0 --decompile   Run headless decompile, output JSONL to
                      state/thinkcell_bridge/ghidra_decompile/<ts>/functions.jsonl

After --decompile, run:
  .venv/bin/python scripts/label_thinkcell_functions_with_claude.py \\
    --jsonl state/thinkcell_bridge/ghidra_decompile/<latest>/functions.jsonl

Then query:
  .venv/bin/python scripts/query_thinkcell_function_db.py "chart constructor"
EOF
    ;;
esac
