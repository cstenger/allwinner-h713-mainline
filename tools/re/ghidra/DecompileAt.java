// Create (if missing) and decompile functions at given addresses.
// usage (headless, -process): -postScript DecompileAt.java <outfile> <addr> [addr...]
// Addresses are Ghidra addresses (image base applied). Thumb entry: pass the even address.
import ghidra.app.script.GhidraScript;
import ghidra.app.decompiler.*;
import ghidra.app.cmd.disassemble.ArmDisassembleCommand;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.*;
import java.io.*;

public class DecompileAt extends GhidraScript {
    @Override
    public void run() throws Exception {
        String[] a = getScriptArgs();
        DecompInterface d = new DecompInterface();
        DecompileOptions o = new DecompileOptions();
        o.setMaxPayloadMBytes(Integer.getInteger("decomp.payload", 50));
        d.setOptions(o);
        d.openProgram(currentProgram);
        try (PrintWriter w = new PrintWriter(new FileWriter(a[0]))) {
            for (int i = 1; i < a.length; i++) {
                Address ad = toAddr(a[i]);
                Function fn = getFunctionAt(ad);
                if (fn == null) {
                    new ArmDisassembleCommand(ad, null, true).applyTo(currentProgram, monitor);
                    fn = createFunction(ad, null);
                }
                if (fn == null) { w.println("// could not create function at " + ad); continue; }
                DecompileResults r = d.decompileFunction(fn, Integer.getInteger("decomp.timeout", 120), monitor);
                w.printf("// ==== %s @ %s%n", fn.getName(), fn.getEntryPoint());
                w.println(r.decompileCompleted() ? r.getDecompiledFunction().getC() : "// failed: " + r.getErrorMessage());
            }
        }
        d.dispose();
    }
}
