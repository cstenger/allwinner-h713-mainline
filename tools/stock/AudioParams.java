/** Stock HAL routing query and bounded diagnostic sink selection. */
public class AudioParams {
    public static void main(String[] args) {
        try {
            Class<?> system=Class.forName("android.media.AudioSystem");
            String key="audio_devices_out_active";
            if(args.length==0)System.out.println(system.getMethod("getParameters",String.class).invoke(null,key));
            else {
                if(args.length!=1 || !(args[0].equals("AUDIO_A2DP") || args[0].equals("AUDIO_SPEAKER")))throw new IllegalArgumentException("unsupported diagnostic sink");
                Object rc=system.getMethod("setParameters",String.class).invoke(null,key+"="+args[0]);
                System.out.println("setParameters rc="+rc);
                if(!rc.equals(0))throw new IllegalStateException("HAL rejected route");
                System.out.println(system.getMethod("getParameters",String.class).invoke(null,key));
            }
            System.exit(0);
        }catch(Throwable t){t.printStackTrace();System.exit(1);}
    }
}
