import os,mmap,struct,json
fd=os.open('/dev/mem',os.O_RDONLY|os.O_SYNC)
def rd(a):
 with mmap.mmap(fd,4096,flags=mmap.MAP_SHARED,prot=mmap.PROT_READ,offset=a&~4095) as m:return struct.unpack_from('<I',m,a&4095)[0]
def pa(v):
 a=(v&0x1fffffff)+0x40000000
 assert 0x4b100000<=a<0x4c000000,hex(v)
 return a
obj=pa(rd(0x4b499dbc)); n=rd(obj+0x130c+8*4); node=rd(obj+0x1c+8*4)
print('event8_count',n)
for i in range(min(n+1,32)):
 if not node:break
 a=pa(node); cb=rd(a); print('node',hex(node),'callback',hex(cb),'next',hex(rd(a+4)))
 if cb:
  c=pa(cb); vt=rd(c); print('vtable',hex(vt),'magic',hex(rd(c+4)),'dispatch',hex(rd(pa(vt)+12)))
 node=rd(a+4)
print('source_result',rd(0x4b2729ac))
