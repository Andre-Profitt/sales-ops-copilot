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
