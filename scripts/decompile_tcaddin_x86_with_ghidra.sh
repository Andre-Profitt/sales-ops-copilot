#!/usr/bin/env bash
# Phase 2 (x86_32 variant) — Ghidra-headless decompile of x86_32 tcaddin.dll
# Sibling to decompile_tcaddin_with_ghidra.sh which targets the ARM64 build.
# x86_32 SLEIGH is mature; this run produces real decompile (not just DelayLoad stubs).
#
# Run: ./decompile_tcaddin_x86_with_ghidra.sh

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
GHIDRA_DIR="${ROOT}/state/thinkcell_bridge/ghidra"
DLL_LOCAL="${ROOT}/state/thinkcell_bridge/tcaddin_dll_x64/tcaddin.dll"
PROJECT_DIR="${GHIDRA_DIR}/project"
PROJECT_NAME="tcaddin_x86"
TS="$(date +%Y%m%d-%H%M%S)_x86"
OUTPUT_JSONL="${ROOT}/state/thinkcell_bridge/ghidra_decompile/${TS}/functions.jsonl"

GHIDRA_HOME=$(find "${GHIDRA_DIR}" -maxdepth 2 -type d -name "ghidra_*_PUBLIC" | head -1)
if [ -z "${GHIDRA_HOME}" ] || [ ! -d "${GHIDRA_HOME}" ]; then
  echo "ERROR: Ghidra not installed at ${GHIDRA_DIR}"
  exit 1
fi
if [ ! -f "${DLL_LOCAL}" ]; then
  echo "ERROR: ${DLL_LOCAL} missing."
  exit 1
fi

echo "[ghidra-x86] DLL: ${DLL_LOCAL}"
echo "[ghidra-x86] file: $(file "${DLL_LOCAL}")"
echo "[ghidra-x86] size: $(stat -f%z "${DLL_LOCAL}") bytes"
echo "[ghidra-x86] project: ${PROJECT_NAME}"
echo "[ghidra-x86] output: ${OUTPUT_JSONL}"

mkdir -p "${PROJECT_DIR}" "$(dirname "${OUTPUT_JSONL}")"
SCRIPT_DIR="${ROOT}/scripts/ghidra_scripts"
mkdir -p "${SCRIPT_DIR}"
POSTSCRIPT="${SCRIPT_DIR}/ExportFunctionsToJsonl.java"
# Reuse the existing post-script if present, write fresh otherwise (identical body).
if [ ! -f "${POSTSCRIPT}" ]; then
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
fi

export TCADDIN_OUTPUT_JSONL="${OUTPUT_JSONL}"

# PHASE 1: import + auto-analyze (explicit x86:LE:32:default to avoid SLEIGH ambiguity).
if [ ! -f "${PROJECT_DIR}/${PROJECT_NAME}.gpr" ]; then
  echo "[ghidra-x86] PHASE 1: import + auto-analyze (x86:LE:32:default)"
  "${GHIDRA_HOME}/support/analyzeHeadless" \
    "${PROJECT_DIR}" "${PROJECT_NAME}" \
    -import "${DLL_LOCAL}" \
    -processor x86:LE:32:default \
    -overwrite \
    -log "${GHIDRA_DIR}/analyze_x86.log" \
    2>&1 | tail -20
  echo "[ghidra-x86] PHASE 1 complete"
else
  echo "[ghidra-x86] PHASE 1 already done (${PROJECT_DIR}/${PROJECT_NAME}.gpr exists)"
fi

# PHASE 2: open analyzed project, run export script.
echo "[ghidra-x86] PHASE 2: running export on analyzed project"
"${GHIDRA_HOME}/support/analyzeHeadless" \
  "${PROJECT_DIR}" "${PROJECT_NAME}" \
  -process tcaddin.dll \
  -noanalysis \
  -postScript ExportFunctionsToJsonl \
  -scriptPath "${SCRIPT_DIR}" \
  -log "${GHIDRA_DIR}/export_x86.log" \
  2>&1 | tail -20

echo "[ghidra-x86] decompile complete"
echo "[ghidra-x86] output: ${OUTPUT_JSONL}"
if [ -f "${OUTPUT_JSONL}" ]; then
  echo "[ghidra-x86] $(wc -l < "${OUTPUT_JSONL}") functions decompiled"
fi
