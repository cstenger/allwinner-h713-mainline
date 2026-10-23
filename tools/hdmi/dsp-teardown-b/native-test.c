/* Fake MMIO/CCF/reset execution of all three actual Phase B bench includes. */
#include <assert.h>
#include <errno.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
typedef uint32_t u32;
typedef uint16_t u16;
typedef uint64_t dma_addr_t;
#define __iomem
#define ARRAY_SIZE(a) (sizeof(a)/sizeof((a)[0]))
#define BIT(n) (1U<<(n))
#define PAGE_SIZE 4096
#define upper_32_bits(v) ((u32)((uint64_t)(v)>>32))
#define IS_ERR_OR_NULL(p) (!(p))
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
static int of_property_read_u32(struct device_node*p,const char*n,u32*v){assert(!strcmp(n,"h713,dsp-teardown-b-v1"));*v=0x54445242;return 0;}

/* ---- fake register file ---- */
#define AUDIF_IRQ_MASK 0x04
#define AUDIF_SPDI1_CTL0 0x34
#define AUDIF_SPDI1_CTL1 0x38
#define AUDIF_SPDI1_W1C 0x00300052u
#define AUDBRG_GLOBAL_IRQ_EN 0x384
#define AUDBRG_IRQ_MASK 0x388
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
#define AUDIO_IHB_CLK_STOCK 0x81000002u
struct reg {uintptr_t a;u32 v;};
static struct reg regs[]={
 {0x06146034,0},{0x06146038,0x3000},{0x06146004,0x00300052},
 {0x06148388,0},{0x06148384,1},{0x06148100,0x006c6000},{0x06148104,0x006c6fff},
 {0x0614810c,0x40},{0x06148110,0x2207},{0x06148114,0},{0x06148390,0},{0x06142044,0x70},
};
static const u16 tv_off[15]={0x00,0x10,0x14,0x18,0x1c,0x20,0x24,0x28,0x30,0x38,0x3c,0x40,0x48,0x4c,0x50};
static const u32 tv_stock[15]={0x80000017,0x80000000,0x81000005,0x80000002,0x80000005,0x80000003,0x80000003,0x8000000b,0x80000117,0x80000002,0x80000002,0x81000002,0x80000002,0x8000020b,0x8000020b};
/* Saved = the cold U-Boot preboot words: most gates off. */
static const u32 tv_saved[15]={0x01000005,0,7,2,5,4,4,0xb,0x20a,2,2,7,2,0x20b,0x20b};
static u32 tv[15],bus=0x10001;
static u32 ctl=0x700,cfg=0x011a5e00,own=0xaa,peer,status,response[2]={1,1},tvtop=0x00011111;
static unsigned requests,graph_writes,at_writes,irq_stops,pins;
static uintptr_t tvlog[128];static u32 tvval[128];static unsigned ntv;
static bool lose_clock,lose_reset,lose_prefix,stuck_off,stuck_bus,unroute,late_timeout_p2,no_done,health_bad;
static int tv_index(uintptr_t a){for(int i=0;i<15;i++)if(a==0x02001d10u+tv_off[i])return i;return -1;}
/* Stall model: the TVFE 1296 and audio CPU/UMAC/IHB gates plus the demod bus
 * clock the audio/DSP path; other words (e.g. MPG) do not. */
static const int stall_words[]={1,9,10,11};
static bool tv_on(void){for(unsigned i=0;i<ARRAY_SIZE(stall_words);i++)if(tv[stall_words[i]]!=tv_stock[stall_words[i]])return false;return (bus&0x10001)==0x10001;}
static bool tv_all_stock(void){for(int i=0;i<15;i++)if(tv[i]!=tv_stock[i])return false;return bus==0x10001;}
static u32 *reg(uintptr_t a){for(unsigned i=0;i<ARRAY_SIZE(regs);i++)if(regs[i].a==a)return &regs[i].v;return NULL;}
/* Audio/DSP/lock windows stall unless AudioTop control is on AND clocks run. */
static void audio_access(void){assert(ctl==0x700&&tv_on());}
static u32 readl(void*p){uintptr_t a=(uintptr_t)p;u32*r=reg(a);int t=tv_index(a);
 if(r){audio_access();return *r;}
 if(t>=0)return tv[t];
 switch(a){
 case 0x02001d64:return bus;
 case 0x070101ac:return health_bad?0:0x10001;
 case 0x070010a4:case 0x07001124:return 0x10000;
 case 0x0306101c:return 1;
 case 0x05700040:return tvtop;
 case 0x0614a000:assert(tv_on());return ctl;
 case 0x0614a00c:assert(tv_on());return cfg;
 case 0x05001530:audio_access();return peer;
 case 0x05001534:audio_access();return own;
 case 0x06144000:audio_access();return status;
 case 0x06144010:audio_access();return response[0];case 0x06144018:audio_access();return response[1];
 default:fprintf(stderr,"read %lx\n",(unsigned long)a);abort();}}
static void tvlogw(uintptr_t a,u32 v){assert(ntv<128);tvlog[ntv]=a;tvval[ntv++]=v;}
static void writel(u32 v,void*p){uintptr_t a=(uintptr_t)p;u32*r=reg(a);int t=tv_index(a);
 if(r){audio_access();*r=v;return;}
 if(t>=0){tvlogw(a,v);if(!(stuck_off&&t==1&&v!=tv_stock[t]))tv[t]=v;
  if(lose_clock&&!tv_on())response[0]=response[1]=0;
  if(unroute&&!tv_on())tvtop=0;
  return;}
 switch(a){
 case 0x02001d64:tvlogw(a,v);if(!(stuck_bus&&(v&1)))bus=v;return;
 case 0x05001534:audio_access();assert(v==0x55||v==0xaa);own=v;return;
 case 0x06144010:case 0x06144018:audio_access();assert(v==0x80ff0000);requests++;status=no_done?0:BIT(a==0x06144010?5:8);return;
 case 0x0614a00c:assert(tv_on()&&v==0);cfg=v;at_writes++;if(lose_prefix)response[0]=response[1]=0;return;
 case 0x0614a000:assert(tv_on()&&(v==0||v==0x700));ctl=v;at_writes++;return;
 default:fprintf(stderr,"write %lx\n",(unsigned long)a);abort();}}
#define readl_poll_timeout(addr,val,cond,delay,timeout) ({int result=-ETIMEDOUT; for(int tick=0;tick<4;tick++){val=readl(addr);if(cond){result=0;break;}}result;})
static void usleep_range(unsigned a,unsigned b){assert(a<=b);}
static unsigned holds;static void msleep(unsigned ms){assert(ms==1000);holds++;}

/* ---- fake CCF and shared reset ---- */
struct clk{int count;bool child_hold;};
static struct clk pll_video0={1},pll_adc={1,false},aclk[5]={{1},{1},{1},{1},{1}};
static int clk_ops;
static int clk_prepare_enable(struct clk*c){c->count++;clk_ops++;return 0;}
static void clk_disable_unprepare(struct clk*c){assert(c->count>0);c->count--;clk_ops++;}
static bool __clk_is_enabled(struct clk*c){return c->count>0||c->child_hold;}
struct reset_control{int deasserted,others;};
static struct reset_control demod={1,0};
static int reset_ops;
static int reset_control_assert(struct reset_control*r){assert(r->deasserted>0);r->deasserted--;reset_ops++;if(!r->deasserted&&!r->others){bus&=~BIT(16);if(lose_reset)response[0]=response[1]=0;}return 0;}
static int reset_control_deassert(struct reset_control*r){r->deasserted++;reset_ops++;bus|=BIT(16);return 0;}
static int reset_control_status(struct reset_control*r){return !(bus&BIT(16));}

/* ---- production statics used by the includes ---- */
static char *audif=(char*)0x06146000,*audbrg=(char*)0x06148000,*audbrg_addr_hi=(char*)0x06142044;
static char *port=(char*)0x06144000,*audio_top=(char*)0x0614a000,*audio_ihb_clk_reg=(char*)0x02001d50;
static dma_addr_t audbrg_dma_addr=0x76c60000;
static void *audbrg_dma_area=(void*)1,*capture_card;
static bool audio_top_initialized=true,graph_ready=true,pcm_running,audio_ihb_retimed=true;
static unsigned period_active;
static bool spdi1_opened=true,spdi1_activated=true,audif_irq_requested=true,audbrg_configured=true,audbrg_irq_requested=true;
static unsigned audbrg_stage_applied=3;
static u32 spdi1_saved_ctl0,spdi1_saved_ctl1,audif_saved_mask,audif_saved_route;
static u32 audbrg_saved_irq_mask,audbrg_saved_global_irq_en,audbrg_saved_stream_sync,audbrg_saved_addr_hi;
static u32 audbrg_saved_stream[6];
static u32 audio_top_saved_ctl,audio_top_saved_cfg,audio_ihb_saved=AUDIO_IHB_CLK_STOCK;
struct audio_clock{const char*name;unsigned id;struct clk*clk;bool inherited_on,enabled_by_driver;};
static struct audio_clock audio_clocks[]={{"bus-hdmi-audio",0,&aclk[0],1,0},{"hdmi-audio",1,&aclk[1],1,0},{"audio-cpu",2,&aclk[2],1,0},{"audio-umac",3,&aclk[3],1,0},{"audio-ihb",4,&aclk[4],1,0}};
static bool graph_active=true,h713_dsp_failed;
static unsigned graph_written=22;
static struct {unsigned address;} graph_settings[22];
static unsigned short graph_saved[22];
static int write_verified(unsigned a,unsigned v){graph_writes++;return 0;}
static int audif_irq=4,audbrg_irq=5;
static void* ioremap(uintptr_t p,unsigned s){return (void*)p;}
static void iounmap(void*p){}
static void disable_irq(int n){irq_stops++;}
static void __module_get(void*p){pins++;}
struct tvfe_word{u16 offset;u32 stock,saved;};
static struct tvfe_word functional_words[15];
struct parent_hold{const char*name;u32 id;struct clk*clk;bool inherited_on,enabled_by_probe;};
static struct parent_hold parents[]={{"pll-video0",0,&pll_video0,1,0},{"pll-adc",1,&pll_adc,0,1}};
static char *ccu_tv=(char*)0x02001d10;
static struct reset_control *demod_reset=&demod;
static bool reset_deasserted=true,words_applied=true,bus_enabled=true,bus_saved_valid=true,tvfe_ready=true;
static u32 bus_saved;
#include "h713-dsp-lock.h"
static struct h713_dsp_lock dsp_lock={(void*)0x05001530,(void*)0x05001534};
#include "teardown.inc"
#include "tvfe.inc"
#include "observer.inc"
static int try_step(unsigned n){char b[16];snprintf(b,sizeof(b),"%u",n);return owner_step_set(b,NULL);}
static void step(unsigned n){int r=try_step(n);if(r){fprintf(stderr,"step %u ret %d\n",n,r);abort();}assert(owner_step==n);}
static void steps(unsigned a,unsigned b){for(unsigned n=a;n<=b;n++)step(n);}
static int dump(void){char buf[PAGE_SIZE];int n=owner_state_get(buf,NULL);assert(n>0&&n<PAGE_SIZE-1);assert(strstr(buf,"h713-teardown-b-v1"));fputs(buf,stdout);return 0;}
static void stopped(unsigned next,unsigned req){assert(owner_terminal&&!owner_claimed&&own==0xaa&&h713_owner_gate_is_open());assert(try_step(next)==-EPERM);assert(requests==req);}
/* Arm 2 off edge: bus gate off with reset released, then 15 words reverse. */
static void expect_off(unsigned at,u32 bus_after){
 assert(tvlog[at]==0x02001d64&&tvval[at]==0x10000);
 for(int i=0;i<15;i++)assert(tvlog[at+1+i]==0x02001d10u+tv_off[14-i]&&tvval[at+1+i]==tv_saved[14-i]);
 if(bus_after!=~0U)assert(tvlog[at+16]==0x02001d64&&tvval[at+16]==bus_after);
}
/* Reacquire: 15 stock words forward, demod bus last. */
static void expect_on(unsigned at){
 for(int i=0;i<15;i++)assert(tvlog[at+i]==0x02001d10u+tv_off[i]&&tvval[at+i]==tv_stock[i]);
 assert(tvlog[at+15]==0x02001d64&&(tvval[at+15]&0x10001)==0x10001);
}
int main(int argc,char**argv){
 assert(argc==2);const char*mode=argv[1];h713_owner_arm=!strncmp(mode,"sham",4)?1:2;
 bool driver=!strcmp(mode,"driver-clock")||!strcmp(mode,"sham-driver-clock");
 for(int i=0;i<15;i++){functional_words[i]=(struct tvfe_word){tv_off[i],tv_stock[i],tv_saved[i]};tv[i]=tv_stock[i];}
 assert(OWNER_STEPS==39);
 if(!strcmp(mode,"missing-marker")){missing_marker=true;assert(h713_owner_init_check()<0);return 0;}
 assert(h713_owner_init_check()==0&&h713_owner_pin()==0&&irq_stops==2&&pins==1);
 if(!strcmp(mode,"census-reset-flag")){reset_deasserted=false;assert(try_step(1)<0);assert(owner_failed&&!requests);return 0;}
 if(!strcmp(mode,"census-words")){tv[13]=0;assert(try_step(1)<0);assert(owner_failed&&!requests);return 0;}
 if(!strcmp(mode,"census-bus-saved")){bus_saved=1;assert(try_step(1)<0);assert(owner_failed&&!requests);return 0;}
 lose_clock=!strcmp(mode,"lose-clock");lose_reset=!strcmp(mode,"lose-reset");lose_prefix=!strcmp(mode,"lose-prefix");
 stuck_off=!strcmp(mode,"stuck-off");stuck_bus=!strcmp(mode,"stuck-bus");unroute=!strcmp(mode,"unrouted");
 if(!strcmp(mode,"shared-reset"))demod.others=1;
 if(!strcmp(mode,"child-hold"))pll_adc.child_hold=true;
 if(driver)audio_clocks[2].enabled_by_driver=true,aclk[2].count=2;
 steps(1,15);
 assert(graph_writes==22&&at_writes==1&&ntv==0);
 if(lose_prefix){stopped(16,4);return dump();}
 step(16);assert(ctl==0&&!h713_owner_gate_is_open());
 /* Closed gate: any audio/DSP/lock read would abort in readl. */
 step(17);
 if(driver)assert(aclk[2].count==(h713_owner_arm==2?1:2)&&owner_audio_dropped[2]==(h713_owner_arm==2));
 unsigned off1=ntv;assert(off1==1&&tvlog[0]==0x02001d50&&tvval[0]==AUDIO_IHB_CLK_STOCK);
 if(stuck_off){assert(try_step(18)<0);assert(owner_failed&&requests==4);return 0;}
 step(18);
 if(h713_owner_arm==2){expect_off(off1,~0U);assert(!tv_on()&&bus==0x10000&&pll_adc.count==0);assert(owner_tv_parent_after_drop[1]==(int)pll_adc.child_hold);}
 else assert(ntv==off1&&tv_on());
 step(19);assert(holds==1);
 unsigned on_at=ntv;
 if(stuck_bus){assert(try_step(20)<0);assert(owner_failed&&requests==4);return 0;}
 step(20);expect_on(on_at);assert(tv_all_stock()&&pll_adc.count==1&&reset_ops==0);
 step(21);if(driver)assert(aclk[2].count==2&&!owner_audio_dropped[2]);
 if(unroute){assert(try_step(22)<0);assert(owner_failed&&!h713_owner_gate_is_open()&&requests==4);return 0;}
 step(22);assert(ctl==0x700);
 if(!strcmp(mode,"late-timeout"))no_done=true;
 steps(23,27);
 if(owner_terminal){assert(lose_clock||no_done);stopped(28,no_done?5:6);assert(reset_ops==0);return dump();}
 step(28);step(29);
 unsigned off_at=ntv;
 if(!strcmp(mode,"shared-reset")){assert(try_step(30)<0);assert(owner_failed&&requests==6);return 0;}
 step(30);
 if(h713_owner_arm==2){expect_off(off_at,0);assert(bus==0&&reset_ops==1&&owner_tv_reset_status_after==1);}
 else assert(ntv==off_at&&reset_ops==0);
 step(31);on_at=ntv;step(32);expect_on(on_at);assert(tv_all_stock());
 assert(reset_ops==(h713_owner_arm==2?2:0)&&demod.deasserted==1);
 steps(33,39);stopped(40,8);
 assert((owner_raw[3][0]&0xffff)==(lose_reset?0:1));
 assert(pll_adc.count==1&&pll_video0.count==1);for(int i=0;i<5;i++)assert(aclk[i].count==(i==2&&driver?2:1));
 assert(clk_ops==(h713_owner_arm==2?(driver?8:4):0));
 return dump();
}
