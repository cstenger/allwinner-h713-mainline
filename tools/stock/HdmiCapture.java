/* Temporary stock-Android AudioRecord diagnostic. No direct MMIO or ALSA.
 * Compiles against standard Java using reflection; run through app_process.
 * Refuses to read samples unless the routed input matches selected HDMI.
 */
import java.io.FileOutputStream;
import java.lang.reflect.*;

public class HdmiCapture {
    static Object invoke(Object target, String name, Class<?>[] types, Object... args) throws Exception {
        Method m = target.getClass().getMethod(name, types);
        return m.invoke(target, args);
    }
    public static void main(String[] args) {
        try { run(args); System.exit(0); }
        catch(Throwable t) { t.printStackTrace(); System.exit(1); }
    }
    static void run(String[] args) throws Exception {
        // Attribute this shell-UID process to its actual installed shell package.
        // No permission/AppOps policy changes are made.
        Class.forName("android.os.Looper").getMethod("prepareMainLooper").invoke(null);
        Class<?> threadClass = Class.forName("android.app.ActivityThread");
        Object thread = threadClass.getMethod("systemMain").invoke(null);
        Object context = threadClass.getMethod("getSystemContext").invoke(thread);
        context = invoke(context,"createPackageContext",new Class<?>[]{String.class,int.class},"com.android.shell",0);
        Field opPackage = context.getClass().getDeclaredField("mOpPackageName");
        opPackage.setAccessible(true); opPackage.set(context,"com.android.shell");
        Class<?> appClass = Class.forName("android.app.Application");
        Object app = appClass.getConstructor().newInstance();
        Method attach = appClass.getDeclaredMethod("attach",Class.forName("android.content.Context"));
        attach.setAccessible(true); attach.invoke(app,context);
        Field initial = threadClass.getDeclaredField("mInitialApplication");
        initial.setAccessible(true); initial.set(thread,app);
        String packageName=(String)threadClass.getMethod("currentOpPackageName").invoke(null);
        if(!"com.android.shell".equals(packageName))throw new IllegalStateException("invalid shell attribution "+packageName);
        System.out.println("PACKAGE " + packageName);
        Class<?> manager = Class.forName("android.media.AudioManager");
        Method devices = manager.getDeclaredMethod("getDevicesStatic", int.class);
        devices.setAccessible(true);
        Object[] inputs = (Object[]) devices.invoke(null, 1);
        Object hdmi = null;
        int wanted = -1;
        for (Object d : inputs) {
            int type = (Integer) invoke(d, "getType", new Class<?>[0]);
            int id = (Integer) invoke(d, "getId", new Class<?>[0]);
            System.out.println("INPUT id=" + id + " type=" + type + " name=" + invoke(d, "getProductName", new Class<?>[0]));
            if (type == 9) { if (hdmi != null) throw new IllegalStateException("multiple HDMI inputs"); hdmi=d; wanted=id; }
        }
        if (args.length == 0 || args[0].equals("list")) return;
        if (hdmi == null) throw new IllegalStateException("no HDMI input exposed");
        int seconds = Integer.parseInt(args[1]);
        if (seconds < 1 || seconds > 30) throw new IllegalArgumentException("seconds outside 1..30");
        Class<?> recordClass = Class.forName("android.media.AudioRecord");
        Class<?> deviceClass = Class.forName("android.media.AudioDeviceInfo");
        int minimum = (Integer) recordClass.getMethod("getMinBufferSize", int.class,int.class,int.class).invoke(null,48000,12,2);
        if (minimum < 0) throw new IllegalStateException("unsupported stereo S16 48kHz");
        Object record = recordClass.getConstructor(int.class,int.class,int.class,int.class,int.class).newInstance(1,48000,12,2,Math.max(minimum,16384));
        for(Field f:recordClass.getDeclaredFields()) {
            if(f.getName().toLowerCase().contains("pack") || f.getName().toLowerCase().contains("attrib")) {
                f.setAccessible(true);System.out.println("RECORD_FIELD "+f.getName()+"="+f.get(record));
            }
        }
        for(Method m:recordClass.getDeclaredMethods())if(m.getName().equals("native_setup"))System.out.println("SETUP "+m);
        boolean started=false;
        try {
            if ((Integer)invoke(record,"getState",new Class<?>[0]) != 1) throw new IllegalStateException("not initialized");
            if (!(Boolean)invoke(record,"setPreferredDevice",new Class<?>[]{deviceClass},hdmi)) throw new IllegalStateException("HDMI preference rejected");
            invoke(record,"startRecording",new Class<?>[0]); started=true;
            if((Integer)invoke(record,"getRecordingState",new Class<?>[0])!=3)throw new IllegalStateException("recording did not start");
            Object routed=null;
            for(int i=0;i<50;i++) { routed=invoke(record,"getRoutedDevice",new Class<?>[0]); if(routed!=null)break;Thread.sleep(10); }
            if(routed==null || (Integer)invoke(routed,"getId",new Class<?>[0])!=wanted) throw new IllegalStateException("capture did not route to HDMI; no samples read");
            System.out.println("ROUTED HDMI id="+wanted);System.out.flush();
            long end=System.nanoTime()+seconds*1000000000L;
            long total=0;
            byte[] buffer=new byte[4096];
            try(FileOutputStream out=new FileOutputStream(args[0])) {
                while(System.nanoTime()<end) {
                    routed=invoke(record,"getRoutedDevice",new Class<?>[0]);
                    if(routed==null || (Integer)invoke(routed,"getId",new Class<?>[0])!=wanted)throw new IllegalStateException("HDMI route lost");
                    int n=(Integer)invoke(record,"read",new Class<?>[]{byte[].class,int.class,int.class,int.class},buffer,0,buffer.length,1);
                    if(n<0)throw new IllegalStateException("read error "+n);
                    if(n==0)Thread.sleep(10);else {out.write(buffer,0,n);total+=n;}
                }
            }
            System.out.println("CAPTURE bytes="+total+" frames="+(total/4)+" rate=48000 stereo S16LE");
        } finally {
            try { if(started)invoke(record,"stop",new Class<?>[0]); }
            finally { invoke(record,"release",new Class<?>[0]); }
        }
    }
}
