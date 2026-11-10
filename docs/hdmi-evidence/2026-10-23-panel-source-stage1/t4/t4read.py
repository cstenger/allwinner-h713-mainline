import mmap,os,json,subprocess,sys
fd=os.open('/dev/mem',os.O_RDONLY|os.O_SYNC)
def w(pa):
    b=pa&~0xfff;m=mmap.mmap(fd,4096,mmap.MAP_SHARED,mmap.PROT_READ,offset=b);v=memoryview(m).cast('I');x=v[(pa-b)//4];v.release();m.close();return x
P=lambda va: va-0x80000000+0x40000000
r={'label':sys.argv[1],'uptime':open('/proc/uptime').read().split()[0]}
obj=w(P(0x8b499b14)); r['memagent']={'vptr':'%08x'%w(P(obj)),'c':'%08x'%w(P(obj)+0xc),'b4':'%08x'%w(P(obj)+0xb4)}
r['bypass']='%08x'%w(0x02010030); r['sel']='%08x'%w(0x051c006c)
r['tcon']='%08x %08x %08x'%(w(0x0588001c),w(0x05880020),w(0x05880024))
r['afbd']={'%03x'%o:'%08x'%w(0x05600000+o) for o in range(0,0xa0,4)}
r['afbd_pair']='%08x %08x'%(w(0x05600320),w(0x05600324))
r['comp']={'%03x'%o:'%08x'%w(0x05000000+o) for o in (0x030,0x178,0x1b8,0x278,0x2b8)}
r['fp_trace']=' '.join('%08x'%w(0x4d980000+o) for o in range(0x40,0x58,4))
node='/proc/device-tree/reserved-memory/framebuf@4bf41000'
r['pool']=[open(node+'/reg','rb').read().hex(), os.path.exists(node+'/no-map')]
r['faults']=subprocess.run("dmesg | grep -i -E 'iommu.*(fault|error)|page fault|unhandled' | grep -v 'Default domain' | wc -l",shell=True,capture_output=True,text=True).stdout.strip()
r['cedrus']=subprocess.run('fuser /dev/video0 2>/dev/null',shell=True,capture_output=True,text=True).stdout.strip()
import time
r['iommu']={'%03x'%o:'%08x'%w(0x02010000+o) for o in list(range(0x100,0x140,4))+[0x30]}
s=[]
for i in range(6):
    s.append('%08x %08x'%(w(0x05600320),w(0x05600324))); time.sleep(0.1)
r['pair_samples']=s
r['afbd_en']='%08x'%w(0x05600010)
print(json.dumps(r))
