import os,pathlib,select,sys,time
sys.path.insert(0,str(pathlib.Path('tools/serial').resolve()))
from console import open_port
p=pathlib.Path(__file__).resolve().parent
fd=open_port('/dev/ttyUSB0')
try:
    with (p/'steps-uart.log').open('xb',buffering=0) as raw, (p/'steps-uart-events.log').open('x',buffering=1) as events:
        events.write('OPEN /dev/ttyUSB0 monotonic='+str(time.monotonic())+'\n')
        end=time.monotonic()+2400
        while time.monotonic()<end and not (p/'stop-steps-uart').exists():
            if select.select([fd],[],[],1)[0]:
                b=os.read(fd,65536)
                if not b:raise RuntimeError('UART lost; no reconnect')
                raw.write(b)
        events.write('CLOSE monotonic='+str(time.monotonic())+'\n')
finally:os.close(fd)
