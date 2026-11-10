package com.h713.hdmicapture;

import android.app.*;
import android.content.*;
import android.media.*;
import android.os.*;
import android.util.Log;
import java.io.*;

/** Temporary HDMI-only capture through the unmodified stock AudioRecord HAL. */
public class CaptureService extends Service {
    public IBinder onBind(Intent intent) { return null; }
    public int onStartCommand(Intent intent, int flags, int id) {
        NotificationManager manager=getSystemService(NotificationManager.class);
        manager.createNotificationChannel(new NotificationChannel("capture","HDMI capture diagnostic",NotificationManager.IMPORTANCE_LOW));
        startForeground(1,new Notification.Builder(this,"capture").setContentTitle("HDMI capture diagnostic").setSmallIcon(android.R.drawable.ic_media_play).build());
        final int seconds=intent.getIntExtra("seconds",15);
        final String name=intent.getStringExtra("name");
        final boolean a2dp=intent.getBooleanExtra("a2dp",false);
        new Thread(() -> capture(seconds,name,a2dp)).start();
        return START_NOT_STICKY;
    }
    void capture(int seconds,String name,boolean a2dp) {
        boolean restoreSink=false;
        AudioRecord record=null;
        try(PrintWriter status=new PrintWriter(new File(getFilesDir(),"status.txt"))) {
            if(seconds<1 || seconds>30 || name==null || !name.matches("[a-zA-Z0-9_-]+"))throw new IllegalArgumentException("invalid trial parameters");
            if(a2dp) {
                String before=(String)Class.forName("android.media.AudioSystem").getMethod("getParameters",String.class).invoke(null,"audio_devices_out_active");
                if(!"AUDIO_SPEAKER=".equals(before))throw new IllegalStateException("unexpected initial sink "+before);
                restoreSink=true;
                Object rc=Class.forName("android.media.AudioSystem").getMethod("setParameters",String.class).invoke(null,"audio_devices_out_active=AUDIO_A2DP");
                String after=(String)Class.forName("android.media.AudioSystem").getMethod("getParameters",String.class).invoke(null,"audio_devices_out_active");
                status.println("A2DP rc="+rc+" mode="+after);status.flush();
                if(!"AUDIO_A2DP=".equals(after))throw new IllegalStateException("A2DP sink did not activate");
            }
            AudioDeviceInfo hdmi=null;
            for(AudioDeviceInfo d:getSystemService(AudioManager.class).getDevices(AudioManager.GET_DEVICES_INPUTS)) {
                status.println("INPUT id="+d.getId()+" type="+d.getType()+" name="+d.getProductName());
                if(d.getType()==AudioDeviceInfo.TYPE_HDMI) {
                    if(hdmi!=null)throw new IllegalStateException("multiple HDMI inputs");
                    hdmi=d;
                }
            }
            if(hdmi==null)throw new IllegalStateException("no HDMI input");
            int size=AudioRecord.getMinBufferSize(48000,AudioFormat.CHANNEL_IN_STEREO,AudioFormat.ENCODING_PCM_16BIT);
            if(size<0)throw new IllegalStateException("unsupported stereo S16 48kHz");
            record=new AudioRecord(MediaRecorder.AudioSource.MIC,48000,AudioFormat.CHANNEL_IN_STEREO,AudioFormat.ENCODING_PCM_16BIT,Math.max(size,16384));
            if(record.getState()!=AudioRecord.STATE_INITIALIZED)throw new IllegalStateException("record not initialized");
            if(!record.setPreferredDevice(hdmi))throw new IllegalStateException("HDMI preference rejected");
            record.startRecording();
            if(record.getRecordingState()!=AudioRecord.RECORDSTATE_RECORDING)throw new IllegalStateException("recording not started");
            AudioDeviceInfo routed=null;
            for(int i=0;i<50;i++){routed=record.getRoutedDevice();if(routed!=null)break;Thread.sleep(10);}
            if(routed==null || routed.getId()!=hdmi.getId())throw new IllegalStateException("not routed to HDMI; no samples read");
            status.println("ROUTED HDMI id="+routed.getId());status.flush();
            long end=System.nanoTime()+seconds*1000000000L,total=0;
            byte[] buffer=new byte[4096];
            try(FileOutputStream out=new FileOutputStream(new File(getFilesDir(),name+".pcm"))) {
                while(System.nanoTime()<end) {
                    routed=record.getRoutedDevice();
                    if(routed==null || routed.getId()!=hdmi.getId())throw new IllegalStateException("HDMI route lost");
                    int n=record.read(buffer,0,buffer.length,AudioRecord.READ_NON_BLOCKING);
                    if(n<0)throw new IllegalStateException("read failed "+n);
                    if(n==0)Thread.sleep(10);else {out.write(buffer,0,n);total+=n;}
                }
            }
            status.println("CAPTURE bytes="+total+" frames="+(total/4)+" rate=48000 stereo S16LE");
        } catch(Exception e) {
            Log.e("HdmiCapture","Capture failed",e);
            try(PrintWriter status=new PrintWriter(new FileOutputStream(new File(getFilesDir(),"status.txt"),true))) {e.printStackTrace(status);}catch(Exception ignored){}
        } finally {
            if(record!=null){try {record.stop();}catch(Exception ignored){}record.release();}
            if(restoreSink) {
                try(PrintWriter status=new PrintWriter(new FileOutputStream(new File(getFilesDir(),"status.txt"),true))) {
                    Object rc=Class.forName("android.media.AudioSystem").getMethod("setParameters",String.class).invoke(null,"audio_devices_out_active=AUDIO_SPEAKER");
                    String after=(String)Class.forName("android.media.AudioSystem").getMethod("getParameters",String.class).invoke(null,"audio_devices_out_active");
                    status.println("RESTORE rc="+rc+" mode="+after);
                    if(!"AUDIO_SPEAKER=".equals(after))throw new IllegalStateException("speaker restore not confirmed");
                }catch(Exception e){Log.e("HdmiCapture","SPEAKER RESTORE FAILED",e);}
            }
            stopForeground(true);stopSelf();
        }
    }
}
