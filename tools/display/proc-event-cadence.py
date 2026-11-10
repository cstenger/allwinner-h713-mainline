import os,mmap,struct,time,json
fd=os.open('/dev/mem',os.O_RDWR|os.O_SYNC)
m=mmap.mmap(fd,4096,flags=mmap.MAP_SHARED,prot=mmap.PROT_READ|mmap.PROT_WRITE,offset=0x05140000)
def rd(o):return struct.unpack_from('<I',m,o)[0]
def wr(o,v):
 struct.pack_into('<I',m,o,v)
 if rd(o)!=v:raise RuntimeError('control readback mismatch')
saved=rd(0x34);mask=0x3b
if saved & mask or saved & (mask<<16):raise RuntimeError('Target events not masked or acknowledgement already asserted')
counts={str(i):0 for i in (0,1,3,4,5)}
first={};last={};intervals={k:[] for k in counts}
def ack(bits):
 base= saved & ~(mask<<16)
 wr(0x34,base);wr(0x34,base|(bits<<16));wr(0x34,base)
try:
 initial=rd(0xe00);ack(mask);after=rd(0xe00)
 start=time.monotonic();end=start+2
 while time.monotonic()<end:
  bits=rd(0xe00)&mask
  if bits:
   now=time.monotonic()-start
   for k in counts:
    if bits&(1<<int(k)):
     counts[k]+=1
     if k in last:intervals[k].append(now-last[k])
     first.setdefault(k,now);last[k]=now
   ack(bits)
  time.sleep(.0005)
 print(json.dumps(dict(control=hex(saved),initial=hex(initial),after_ack=hex(after),counts=counts,first=first,interval_ranges={k:([min(v),max(v)] if v else []) for k,v in intervals.items()})))
finally:
 wr(0x34,saved)
 print('Exact control restored:',hex(rd(0x34)))
 m.close();os.close(fd)
