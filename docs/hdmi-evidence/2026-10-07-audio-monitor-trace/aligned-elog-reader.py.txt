import ctypes,mmap,os,struct,sys
f=os.open('/dev/mem',os.O_RDWR|os.O_SYNC)
m=mmap.mmap(f,0x200000,mmap.MAP_SHARED,mmap.PROT_READ|mmap.PROT_WRITE,offset=0x4b270000)
w=(ctypes.c_uint32*(0x200000//4)).from_buffer(m)
sys.stdout.buffer.write(b''.join(struct.pack('<I',x) for x in w))
del w
m.close();os.close(f)
