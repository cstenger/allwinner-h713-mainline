#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0
"""Test actual private-reference witness registration, decoding and lifetime."""
import argparse,os,subprocess,tempfile
from pathlib import Path
from importlib.machinery import SourceFileLoader
h=SourceFileLoader('handoff',str(Path(__file__).with_name('test-cpu-comm-handoff.py'))).load_module()
STUBS=h.COMMON+r'''
#include <stdlib.h>
#include <stdarg.h>
#define __iomem
struct device_node {};struct kernel_param {};
struct reserved_mem { uint64_t base,size; };
#define PAGE_SIZE 4096
#define PAGE_ALIGN(n) (((n)+4095)&~4095)
#define SZ_64K 65536
#define SZ_128K 131072
#define SZ_256K 262144
#define BUILD_BUG_ON(c) _Static_assert(!(c),"BUILD_BUG_ON")
#define CC_REF_ARENA_MAX 8
#define CC_REF_LOCAL BIT(31)
#define CC_REF_ARENA_SHIFT 28
#define CC_REF_OFF_MASK ((1u<<28)-1)
#define U32_MAX UINT32_MAX
typedef uint64_t phys_addr_t;
#define WARN_ONCE(x,...) (!!(x))
#define DEFINE_MUTEX(n) static pthread_mutex_t n=PTHREAD_MUTEX_INITIALIZER
#define mutex_lock(n) pthread_mutex_lock(n)
#define mutex_unlock(n) pthread_mutex_unlock(n)
static bool cc_arena_witness;
static void *cc_witness_window;
static u32 cc_witness_mid;
static size_t cc_witness_span,cc_witness_used;
DEFINE_MUTEX(cc_arena_mutex);
static struct device_node node;
static struct reserved_mem reservation={0x4d980000,SZ_256K};
static bool node_present=true,no_map=true,lookup=true,map_fail;
static unsigned char backing[SZ_256K] __attribute__((aligned(4096)));
static int maps,unmaps;
static struct device_node *of_find_node_by_path(const char*p){return node_present?&node:0;}
static struct reserved_mem *of_reserved_mem_lookup(struct device_node*n){return lookup?&reservation:0;}
static bool of_property_read_bool(struct device_node*n,const char*p){return no_map;}
static void of_node_put(struct device_node*n){}
static void *ioremap(u32 addr,size_t size){
 assert(addr==0x4d981000 && size==SZ_256K-PAGE_SIZE);
 if(map_fail)return 0;maps++;return backing+PAGE_SIZE;
}
static void iounmap(void *p){assert(p==backing+PAGE_SIZE);unmaps++;}
#define memset_io(p,v,n) memset(p,v,n)
static bool is_vmalloc_or_module_addr(void *p){return false;}
static phys_addr_t virt_to_phys(void *p){return 0x41000000;}
static unsigned readl(void *p){return *(volatile u32 *)p;}
static void writel(u32 v,void*p){*(volatile u32 *)p=v;}
static int scnprintf(char *b,size_t size,const char *fmt,...){
 va_list a;va_start(a,fmt);int n=vsnprintf(b,size,fmt,a);va_end(a);
 return size ? (n<(int)size?n:(int)size-1):0;
}
static unsigned long ShMemAddrBase;static u32 ShMemAddr,ShMemSize;
static u32 Vir2Mid(u32 cpu,unsigned long p){return p-ShMemAddrBase+ShMemAddr;}
static unsigned long Mid2Vir(u32 cpu,u32 ref){return ref-ShMemAddr+ShMemAddrBase;}
'''
TEST=r'''
int main(void){
 u8 actual[96]={0},other[96]={0};char status[4096];
 assert(!cc_arena_prepare() && maps==0);
 assert(cc_arena_register(actual,sizeof actual)==0);
 assert(cc_ref(actual+32)==0x41000020 && cc_deref(0x41000020)==(unsigned long)(actual+32));
 cc_arena_reset();assert(!maps);
 cc_arena_witness=true;
 node_present=false;assert(cc_arena_prepare()==-ENODEV);node_present=true;
 reservation.size=PAGE_SIZE;assert(cc_arena_prepare()==-EINVAL);reservation.size=SZ_256K;
 no_map=false;assert(cc_arena_prepare()==-EINVAL);no_map=true;
 reservation.base=0x4d990000;assert(cc_arena_prepare()==-EINVAL);reservation.base=0x4d980000;
 lookup=false;assert(cc_arena_prepare()==-EINVAL);lookup=true;
 map_fail=true;assert(cc_arena_prepare()==-ENOMEM);map_fail=false;
 memset(backing,0x33,sizeof backing);
 assert(!cc_arena_prepare() && maps==1);
 assert(cc_arena_register(actual,sizeof actual)==0);
 assert(cc_arenas[0].mid==0x4d982000);
 assert(cc_ref(actual+32)==0x4d982020 && cc_deref(0x4d982020)==(unsigned long)(actual+32));
 assert(!cc_deref(0x41000020) && !cc_deref(0x4d982000+sizeof actual));
 cc_arena_witness_status(status,0);assert(strstr(status,"changed_words=0"));
 /* Simulated peer stores hit the reserved witness, not the real local arena. */
 writel(0x8baa0000,cc_arenas[0].witness+PAGE_SIZE+32);
 writel(0x8b15bd44,cc_arenas[0].witness+PAGE_SIZE+36);
 for(int i=0;i<sizeof actual;i++)assert(!actual[i]);
 for(int i=0;i<PAGE_SIZE;i++)assert(backing[i]==0x33); /* old trace untouched */
 cc_arena_witness_status(status,0);
 assert(strstr(status,"changed_words=2") && strstr(status,"first_offset=4128") && strstr(status,"8baa0000 8b15bd44"));
 assert(cc_arena_register(other,sizeof other)==1);
 assert(cc_ref(other)!=cc_ref(actual));
 cc_witness_span=cc_witness_used;
 assert(cc_arena_register(other,sizeof other)==-ENOSPC && cc_arena_count==2);
 cc_witness_span=SZ_256K-PAGE_SIZE;
 /* The driver's real arenas, in probe order, must both fit (0204 v1 refused the second). */
 cc_arena_reset();memset(backing,0x33,sizeof backing);
 u8 *sock=calloc(1,2*COMM_SOCKET_SIZE),*dev=calloc(1,CPU_COMM_DEV_SIZE);
 assert(cc_arena_register(sock,2*COMM_SOCKET_SIZE)==0);
 assert(cc_arena_register(dev,CPU_COMM_DEV_SIZE)==1);
 assert(cc_arenas[0].mid==0x4d982000);
 assert(cc_arenas[1].mid>=cc_arenas[0].mid+2*COMM_SOCKET_SIZE+PAGE_SIZE);
 assert(cc_arenas[1].mid+CPU_COMM_DEV_SIZE+PAGE_SIZE<=0x4d980000+SZ_256K);
 assert(cc_deref(cc_ref(sock+2*COMM_SOCKET_SIZE-4))==(unsigned long)(sock+2*COMM_SOCKET_SIZE-4));
 assert(cc_deref(cc_ref(dev+CPU_COMM_DEV_SIZE-4))==(unsigned long)(dev+CPU_COMM_DEV_SIZE-4));
 assert(!cc_deref(cc_arenas[1].mid+CPU_COMM_DEV_SIZE));
 cc_arena_witness_status(status,0);
 assert(strstr(status,"arenas=2") && !strstr(status,"changed_words=1") && strstr(status,"changed_words=0"));
 writel(0x8baa0018,cc_arenas[1].witness+PAGE_SIZE+CPU_COMM_DEV_SIZE-4); /* last word of dev */
 cc_arena_witness_status(status,0);assert(strstr(status,"arena=1") && strstr(status,"changed_words=1"));
 void *last=cc_arenas[1].witness+PAGE_SIZE+CPU_COMM_DEV_SIZE-4;
 for(int i=0;i<PAGE_SIZE;i++)assert(backing[i]==0x33);
 /* Only the window's remainder is left; one byte more is refused. */
 size_t left=cc_witness_span-cc_witness_used-2*PAGE_SIZE;
 assert(cc_arena_register(other,left+1)==-ENOSPC && cc_arena_count==2);
 assert(cc_arena_register(other,left)==2);
 free(sock);free(dev);
 cc_arena_reset();cc_arena_finish();
 assert(unmaps==1 && !cc_witness_window && !cc_arena_count);
 assert(readl(last)==0x8baa0018); /* never reclaim backing */
 puts("PASS real arena sizes fit, default references, reserved-window isolation, write detection, trace preservation, reservation refusal, exhaustion and teardown");
}
'''
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--kernel',type=Path,required=True);a=p.parse_args()
 d=a.kernel/'drivers/soc/sunxi/cpu_comm'
 if not d.exists():d=a.kernel
 s=(d/'cpu_comm_mem.c').read_text();x=s.index('static struct {',s.index('/* ──'))
 # Select the arena declaration, not an unrelated allocator structure.
 x=s.rfind('static struct {',0,s.index('} cc_arenas'));y=s.index('static int cc_arena_count;',x)+len('static int cc_arena_count;')
 hdr=(d/'cpu_comm.h').read_text()
 sizes=''.join(l+'\n' for l in hdr.splitlines() if l.startswith(('#define COMM_SOCKET_SIZE','#define CPU_COMM_DEV_SIZE')))
 assert sizes.count('#define')==2,'real arena sizes not found in cpu_comm.h'
 code=STUBS+sizes+s[x:y]+'\n'+'\n'.join(h.function(s,k) for k in ('int cc_arena_prepare(', 'void cc_arena_finish(', 'static int cc_arena_witness_status(', 'int cc_arena_register(', 'void cc_arena_reset(', 'u32 cc_ref(', 'unsigned long cc_deref('))+TEST
 with tempfile.TemporaryDirectory() as tmp:
  t=Path(tmp);(t/'test.c').write_text(code)
  subprocess.run(['clang','-O1','-g','-pthread','-fsanitize=address,undefined',str(t/'test.c'),'-o',str(t/'test')],check=True)
  subprocess.run([str(t/'test')],check=True,env={**os.environ,'ASAN_OPTIONS':'detect_leaks=0'},timeout=15)
if __name__=='__main__':main()
