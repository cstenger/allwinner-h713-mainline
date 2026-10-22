/* Fake MMIO execution of both actual Phase A bench includes. */
#include <assert.h>
#include <errno.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
typedef uint32_t u32;
typedef uint64_t dma_addr_t;
#define __iomem
#define ARRAY_SIZE(a) (sizeof(a)/sizeof((a)[0]))
#define BIT(n) (1U<<(n))
#define PAGE_SIZE 4096
#define upper_32_bits(v) ((u32)((uint64_t)(v)>>32))
#define DEFINE_MUTEX(n) int n
#define mutex_lock(p) ((void)(p))
#define mutex_unlock(p) ((void)(p))
#define module_param_named(...)
#define module_param_cb(...)
#define pr_notice(...) ((void)0)
#define pr_err(...) ((void)0)
#define scnprintf snprintf
#define THIS_MODULE NULL
struct kernel_param {int unused;};
struct kernel_param_ops {int (*set)(const char*,const struct kernel_param*);int (*get)(char*,const struct kernel_param*);};
static int kstrtouint(const char*s,int base,unsigned*n){char*end;unsigned long v=strtoul(s,&end,base);if(*end || v>0xffffffff)return -EINVAL;*n=v;return 0;}
struct device_node {int unused;};
static struct device_node node;
static bool missing_marker;
static struct device_node*of_find_node_by_path(const char*p){return missing_marker?NULL:&node;}
static void of_node_put(struct device_node*p){}
static int of_property_read_u32(struct device_node*p,const char*n,u32*v){assert(!strcmp(n,"h713,dsp-teardown-a-v1"));*v=0x54445241;return 0;}

/* Production PCM names and offsets used by teardown.inc. */
#define AUDIF_IRQ_STATUS 0x00
#define AUDIF_IRQ_MASK 0x04
#define AUDIF_EVENT_CLEAR 0x08
#define AUDIF_SPDI1_CTL0 0x34
#define AUDIF_SPDI1_CTL1 0x38
#define AUDIF_SPDI1_W1C 0x00300052u
#define AUDBRG_GLOBAL_IRQ_EN 0x384
#define AUDBRG_IRQ_MASK 0x388
#define AUDBRG_IRQ_STATUS 0x38c
#define AUDBRG_STREAM_SYNC 0x390
#define AUDBRG_OSTREAM0 0x100
#define AUDBRG_STREAM_START 0x00
#define AUDBRG_STREAM_END 0x04
#define AUDBRG_STREAM_BLOCK 0x0c
#define AUDBRG_STREAM_CONFIG 0x10
#define AUDBRG_STREAM_FLUSH 0x14
#define AUDBRG_GLOBAL_IRQ_BIT BIT(0)
#define AUDBRG_DMA_SIZE 0x10000
#define AUDBRG_DMA_BLOCK 0x400
#define AUDBRG_OSTREAM0_CONFIG 0x00002207u
#define AUDBRG_ADDR_HI_MASK 0x000000f0u
static char *audif=(char*)0x06146000,*audbrg=(char*)0x06148000,*audbrg_addr_hi=(char*)0x06142044;
static char *port=(char*)0x06144000,*audio_top=(char*)0x0614a000;
static dma_addr_t audbrg_dma_addr=0x76c60000;
static void *audbrg_dma_area=(void*)1,*capture_card;
static bool audio_top_initialized=true,graph_ready=true,pcm_running;
static unsigned period_active;
static bool spdi1_opened=true,spdi1_activated=true,audif_irq_requested=true,audbrg_configured=true,audbrg_irq_requested=true;
static unsigned audbrg_stage_applied=3;
/* Distinct nonzero saved values make order/value checks discriminating. */
static u32 spdi1_saved_ctl0=0x01,spdi1_saved_ctl1=0x11,audif_saved_mask=0x02,audif_saved_route=0x77;
static u32 audbrg_saved_irq_mask=0x2,audbrg_saved_global_irq_en=0x100,audbrg_saved_stream_sync=0x5,audbrg_saved_addr_hi=0x3;
static u32 audbrg_saved_stream[6]={0x21,0x22,0x23,0x24,0};
static u32 audio_top_saved_ctl,audio_top_saved_cfg;
static bool graph_active=true,h713_dsp_failed;

/* Fake register file. */
struct reg {uintptr_t a;u32 v;};
static struct reg regs[]={
 {0x06146034,0},{0x06146038,0x3000},{0x06146004,0x02|0x00300052},
 {0x06148388,0x2},{0x06148384,0x101},{0x06148100,0x006c6000},{0x06148104,0x006c6fff},
 {0x0614810c,0x40},{0x06148110,0x2207},{0x06148114,0},{0x06148390,0},{0x06142044,0x73},
};
static u32 *reg(uintptr_t a){for(unsigned i=0;i<ARRAY_SIZE(regs);i++)if(regs[i].a==a)return &regs[i].v;return NULL;}
static uintptr_t wlog[64];static u32 wval[64];static unsigned nw;
static u32 ctl=0x700,cfg=0x011a5e00,own=0xaa,peer,status,response[2]={1,1},echo;
static unsigned requests,at_writes,irq_stops,pins,graph_writes;
static unsigned graph_written=22;
static struct {unsigned address;} graph_settings[22];
static unsigned short graph_saved[22];
static bool lose_graph,graph_failure,lose_spdi,lose_bridge,lose_cfg,lose_ctl,stuck_spdi,stuck_bridge;
static bool no_done,busy,lock_bad,health_bad;
static int write_verified(unsigned a,unsigned v){graph_writes++;if(graph_failure){h713_dsp_failed=true;return -EIO;}if(lose_graph)response[0]=response[1]=0;return 0;}
static int audif_irq=4,audbrg_irq=5;
static void* ioremap(uintptr_t p,unsigned s){return (void*)p;}
static void iounmap(void*p){}
static void disable_irq(int n){assert(n==4||n==5);irq_stops++;}
static void __module_get(void*p){pins++;}
static void usleep_range(unsigned a,unsigned b){assert(a<=b);}
static u32 readl(void*p){uintptr_t a=(uintptr_t)p;u32*r=reg(a);
 if(r){assert(ctl==0x700);return *r;}
 switch(a){
 case 0x070101ac:return health_bad?0:0x10001;
 case 0x070010a4:case 0x07001124:return 0x10000;
 case 0x0306101c:return 1;
 case 0x0614a000:return ctl;
 case 0x0614a00c:return cfg;
 case 0x05001530:assert(ctl==0x700);return peer;
 case 0x05001534:assert(ctl==0x700);return lock_bad?0:own;
 case 0x06144000:assert(ctl==0x700);return busy?0x10:status;
 case 0x06144010:return echo?echo:response[0];case 0x06144018:return echo?echo:response[1];
 default:abort();}}
static void writel(u32 v,void*p){uintptr_t a=(uintptr_t)p;u32*r=reg(a);
 if(r){assert(ctl==0x700&&nw<64);wlog[nw]=a;wval[nw++]=v;
  if(!(stuck_spdi&&a==0x06146038)&&!(stuck_bridge&&a==0x06142044))*r=v;
  if(lose_spdi&&a==0x06146004)response[0]=response[1]=0;
  if(lose_bridge&&a==0x06142044)response[0]=response[1]=0;
  return;}
 switch(a){
 case 0x05001534:assert(v==0x55||v==0xaa);own=v;return;
 case 0x06144010:case 0x06144018:assert(v==0x80ff0000&&ctl==0x700);requests++;status=no_done?0:BIT(a==0x06144010?5:8);return;
 case 0x0614a00c:assert(v==0);cfg=v;at_writes++;if(lose_cfg)response[0]=response[1]=0;return;
 case 0x0614a000:assert(v==0||v==0x700);ctl=v;at_writes++;if(v==0&&lose_ctl)response[0]=response[1]=0;return;
 default:abort();}}
#define readl_poll_timeout(addr,val,cond,delay,timeout) ({int result=-ETIMEDOUT; for(int tick=0;tick<4;tick++){val=readl(addr);if(cond){result=0;break;}}result;})
#include "h713-dsp-lock.h"
static struct h713_dsp_lock dsp_lock={(void*)0x05001530,(void*)0x05001534};
#include "teardown.inc"
#include "observer.inc"
static void step(unsigned n){char b[16];snprintf(b,sizeof(b),"%u",n);assert(owner_step_set(b,NULL)==0);assert(owner_step==n);}
static int try_step(unsigned n){char b[16];snprintf(b,sizeof(b),"%u",n);return owner_step_set(b,NULL);}
static void pair(unsigned first){for(unsigned i=0;i<5;i++)step(first+i);}
/* Pair p occupies five steps; return the first one. */
static const unsigned pair_first[OWNER_PAIRS]={2,8,14,20,26,33};
static int dump(void){char buf[PAGE_SIZE];int n=owner_state_get(buf,NULL);assert(n>0&&n<PAGE_SIZE-1);assert(strstr(buf,"h713-teardown-a-v1"));fputs(buf,stdout);return 0;}
static void stopped(unsigned next,unsigned req){assert(owner_terminal&&!owner_claimed&&own==0xaa);assert(try_step(next)==-EPERM);assert(requests==req);}
static void no_forbidden_writes(void){
 for(unsigned i=0;i<nw;i++){assert(wlog[i]!=0x06146000&&wlog[i]!=0x06146008&&wlog[i]!=0x0614838c);
  if(wlog[i]==0x06148114)assert(wval[i]==audbrg_saved_stream[4]);}
}
static void expect_order(void){
 static const uintptr_t a[]={0x06146034,0x06146038,0x06146004,0x06148388,0x06148384,0x06148100,0x06148104,0x0614810c,0x06148110,0x06148114,0x06148390,0x06142044};
 const u32 v[]={1,0x11,2,2,0x100,0x21,0x22,0x23,0x24,0,5,3};
 assert(nw==12);for(unsigned i=0;i<12;i++)assert(wlog[i]==a[i]&&wval[i]==v[i]);
}
int main(int argc,char**argv){
 assert(argc==2);const char*mode=argv[1];h713_owner_arm=!strcmp(mode,"sham")||!strncmp(mode,"sham-",5)?1:2;
 assert(OWNER_STEPS==37);
 if(!strcmp(mode,"missing-marker")){missing_marker=true;assert(h713_owner_init_check()<0);assert(!requests);return 0;}
 assert(h713_owner_init_check()==0);assert(h713_owner_pin()==0);assert(irq_stops==2&&pins==1);
 if(!strcmp(mode,"missing-arm")){h713_owner_arm=0;assert(try_step(1)==-EPERM);assert(!requests);return 0;}
 if(!strcmp(mode,"health-bad")){health_bad=true;assert(try_step(1)<0);assert(owner_failed&&!requests);return 0;}
 if(!strcmp(mode,"census-stage4")){audbrg_stage_applied=4;assert(try_step(1)<0);assert(owner_failed&&!requests&&!nw);return 0;}
 if(!strcmp(mode,"census-pcm")){pcm_running=true;assert(try_step(1)<0);assert(owner_failed&&!requests&&!nw);return 0;}
 if(!strcmp(mode,"census-active")){*reg(0x06146034)=1;assert(try_step(1)<0);assert(owner_failed&&!requests&&!nw);return 0;}
 if(!strcmp(mode,"census-dma")){audbrg_dma_addr=0x176c60000ull;assert(try_step(1)<0);assert(owner_failed&&!requests);return 0;}
 assert(try_step(2)<0);assert(!requests);step(1);
 if(!strcmp(mode,"lock-bad")){lock_bad=true;assert(try_step(2)<0);assert(owner_failed&&!requests);return 0;}
 if(!strcmp(mode,"busy-timeout"))busy=true;
 if(!strcmp(mode,"done-timeout"))no_done=true;
 if(!strcmp(mode,"bad-positive"))response[0]=response[1]=0;
 if(!strcmp(mode,"echo"))echo=0x80ff0000;
 pair(2);
 if(owner_terminal){stopped(7,busy?0:no_done?1:2);assert(!at_writes&&!nw&&!graph_writes);
  if(echo){assert(owner_raw[0][0]==0x80ff0000);}
  if(no_done||busy){assert(owner_outcome[0][1]==3&&owner_raw[0][1]==~0U);}
  return dump();}
 lose_graph=!strcmp(mode,"lose-graph");lose_spdi=!strcmp(mode,"lose-spdi");lose_bridge=!strcmp(mode,"lose-bridge");
 lose_cfg=!strcmp(mode,"lose-cfg");lose_ctl=!strcmp(mode,"lose-ctl");
 if(!strcmp(mode,"context-drift")){cfg=1;assert(try_step(7)<0);assert(owner_failed&&!at_writes&&!graph_writes);return 0;}
 if(!strcmp(mode,"graph-failure")){graph_failure=true;assert(try_step(7)<0);assert(owner_failed&&!owner_claimed&&requests==2&&!nw);assert(try_step(8)<0);return 0;}
 step(7);assert(graph_writes==22&&graph_written==0);
 if(!strcmp(mode,"late-timeout"))no_done=true;
 pair(8);
 if(owner_terminal){stopped(13,lose_graph?4:3);assert(!nw&&!at_writes);return dump();}
 if(!strcmp(mode,"drift-before-spdi")){*reg(0x06148390)=9;assert(try_step(13)<0);assert(owner_failed&&!nw);return 0;}
 if(!strcmp(mode,"spdi-bad-readback")){stuck_spdi=true;assert(try_step(13)<0);assert(owner_failed&&nw==3&&owner_spdi_writes==3);assert(try_step(14)<0);assert(requests==4);return 0;}
 step(13);assert(nw==(h713_owner_arm==2?3:0));
 pair(14);
 if(owner_terminal){assert(lose_spdi);stopped(19,6);assert(nw==3&&!at_writes);return dump();}
 if(!strcmp(mode,"bridge-bad-readback")){stuck_bridge=true;assert(try_step(19)<0);assert(owner_failed&&nw==12);assert(try_step(20)<0);return 0;}
 step(19);
 if(h713_owner_arm==2)expect_order();else assert(!nw);
 pair(20);
 if(owner_terminal){assert(lose_bridge);stopped(25,8);assert(!at_writes);return dump();}
 step(25);assert(at_writes==(h713_owner_arm==2));
 pair(26);
 if(owner_terminal){assert(lose_cfg);stopped(31,10);assert(at_writes==1);return dump();}
 step(31);assert(h713_owner_arm==1||ctl==0);
 /* No AudIf/bridge/DSP access while control is off (readl asserts it). */
 step(32);assert(ctl==0x700);
 pair(33);
 stopped(38,12);
 assert(at_writes==(h713_owner_arm==1?0:3));
 assert((owner_raw[5][0]&0xffff)==(lose_ctl?0:1));
 no_forbidden_writes();
 return dump();
}
