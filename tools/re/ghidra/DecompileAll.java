// Decompile every function in the current program to <outdir>/<program>.c
// usage (headless): -postScript DecompileAll.java <outdir>
import ghidra.app.script.GhidraScript;
import ghidra.app.decompiler.*;
import ghidra.program.model.listing.*;
import java.io.*;

public class DecompileAll extends GhidraScript {
    @Override
    public void run() throws Exception {
        String outdir = getScriptArgs().length > 0 ? getScriptArgs()[0] : ".";
        DecompInterface d = new DecompInterface();
        DecompileOptions o = new DecompileOptions();
        d.setOptions(o);
        d.openProgram(currentProgram);
        File f = new File(outdir, currentProgram.getName() + ".c");
        try (PrintWriter w = new PrintWriter(new FileWriter(f))) {
            int n = 0, bad = 0;
            for (Function fn : currentProgram.getFunctionManager().getFunctions(true)) {
                if (fn.isExternal() || fn.isThunk()) continue;
                DecompileResults r = d.decompileFunction(fn, 120, monitor);
                w.printf("// ==== %s @ %s%n", fn.getName(), fn.getEntryPoint());
                if (r != null && r.decompileCompleted()) {
                    w.println(r.getDecompiledFunction().getC()); n++;
                } else {
                    w.println("// decompile failed: " + (r == null ? "null" : r.getErrorMessage())); bad++;
                }
            }
            println("DecompileAll: " + n + " functions, " + bad + " failed -> " + f);
        }
        d.dispose();
    }
}
