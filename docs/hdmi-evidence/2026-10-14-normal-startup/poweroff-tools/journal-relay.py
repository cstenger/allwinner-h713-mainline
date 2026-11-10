"""Relay selected journal units over UART; reopen after console hangup."""
import errno,os,signal,subprocess,sys,time

class UartWriter:
 def __init__(self,path='/dev/ttyS0',opener=os.open,writer=os.write,closer=os.close,clock=time.monotonic,sleep=time.sleep):
  self.path=path;self.open=opener;self.write=writer;self.close=closer;self.clock=clock;self.sleep=sleep;self.fd=None
 def emit(self,line):
  deadline=self.clock()+5;offset=0
  while offset<len(line):
   try:
    if self.fd is None:self.fd=self.open(self.path,os.O_WRONLY|os.O_NOCTTY|os.O_NONBLOCK)
    count=self.write(self.fd,line[offset:])
    if count<=0:raise OSError(errno.EIO,'UART write made no progress')
    offset+=count
   except OSError as error:
    if error.errno not in (errno.EIO,errno.ENXIO,errno.EAGAIN) or self.clock()>=deadline:raise
    if error.errno!=errno.EAGAIN:
     self.finish();offset=0
    self.sleep(.05)
 def finish(self):
  if self.fd is not None:self.close(self.fd);self.fd=None

def main():
 signal.signal(signal.SIGHUP,signal.SIG_IGN)
 writer=UartWriter()
 command=['journalctl','--follow','--no-pager','--all','--full','-o','short-monotonic']
 for unit in ('h713-hdmi-capture.service','h713-hdmi-poweroff-recorder.service','h713-hdmi-signal.service'):command+=['-u',unit]
 process=subprocess.Popen(command,stdout=subprocess.PIPE,env={**os.environ,'SYSTEMD_COLORS':'0','SYSTEMD_URLIFY':'0'})
 try:
  for line in process.stdout:writer.emit(line)
  raise SystemExit(process.wait())
 finally:
  writer.finish()
  if process.poll() is None:process.terminate();process.wait(timeout=3)

if __name__=='__main__':main()
