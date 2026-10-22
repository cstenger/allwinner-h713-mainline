/* Fake MMIO execution of both actual bench includes. */
#include <assert.h>
#include <errno.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdarg.h>
typedef uint32_t u32;
#define __iomem
#define ARRAY_SIZE(a) (sizeof(a)/sizeof((a)[0]))
#define BIT(n) (1U<<(n))
#define PAGE_SIZE 4096
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
static int of_property_read_u32(struct device_node*p,const char*n,u32*v){*v=0x4f574e31;return 0;}
static bool audio_top_initialized=true,graph_ready=true,period_active;
static bool graph_active=true,h713_dsp_failed;
static void *port=(void*)0x06144000,*audio_top=(void*)0x0614a000;
static u32 ctl=0x700,cfg=0x011a5e00,own=0xaa,peer,status,response[2]={1,1};
static unsigned requests,at_writes,irq_stops,pins,graph_writes;
static unsigned graph_written=22;
static struct {unsigned address;} graph_settings[22];
static unsigned short graph_saved[22];
static bool lose_graph,graph_failure;
static int write_verified(unsigned a,unsigned v){graph_writes++;if(graph_failure){h713_dsp_failed=true;return -EIO;}if(lose_graph)response[0]=response[1]=0;return 0;}
static bool lose_cfg,lose_ctl,no_done,busy,lock_bad,health_bad;
static int audif_irq=4,audbrg_irq=5;
static void* ioremap(uintptr_t p,unsigned s){return (void*)p;}
static void iounmap(void*p){}
static void disable_irq(int n){assert(n==4||n==5);irq_stops++;}
static void __module_get(void*p){pins++;}
static void usleep_range(unsigned a,unsigned b){assert(a<=b);}
static u32 readl(void*p){uintptr_t a=(uintptr_t)p;switch(a){
case 0x070101ac:return health_bad?0:0x10001;
case 0x070010a4:case 0x07001124:return 0x10000;
case 0x0306101c:return 1;
case 0x0614a000:return ctl;
case 0x0614a00c:return cfg;
case 0x05001530:return peer;
case 0x05001534:return lock_bad?0:own;
case 0x06144000:return busy?0x10:status;
case 0x06144010:return response[0];case 0x06144018:return response[1];
default:abort();}}
static void writel(u32 v,void*p){uintptr_t a=(uintptr_t)p;switch(a){
case 0x05001534:assert(v==0x55||v==0xaa);own=v;return;
case 0x06144010:case 0x06144018:assert(v==0x80ff0000);requests++;status=no_done?0:BIT(a==0x06144010?5:8);return;
case 0x0614a00c:assert(v==0);cfg=v;at_writes++;if(lose_cfg)response[0]=response[1]=0;return;
case 0x0614a000:assert(v==0||v==0x700);ctl=v;at_writes++;if(v==0&&lose_ctl)response[0]=response[1]=0;return;
default:abort();}}
#define readl_poll_timeout(addr,val,cond,delay,timeout) ({int result=-ETIMEDOUT; for(int tick=0;tick<4;tick++){val=readl(addr);if(cond){result=0;break;}}result;})
#include "h713-dsp-lock.h"
static struct h713_dsp_lock dsp_lock={(void*)0x05001530,(void*)0x05001534};
#include "audiotop.inc"
#include "observer.inc"
static void step(unsigned n){char b[16];snprintf(b,sizeof(b),"%u",n);assert(owner_step_set(b,NULL)==0);assert(owner_step==n);}
int main(int argc,char**argv){
 assert(argc==2);const char*mode=argv[1];h713_owner_arm=!strcmp(mode,"sham")?1:2;
 if(!strcmp(mode,"missing-marker")){missing_marker=true;assert(h713_owner_init_check()<0);assert(!requests);return 0;}
 assert(h713_owner_init_check()==0);assert(h713_owner_pin()==0);assert(irq_stops==2&&pins==1);
 if(!strcmp(mode,"missing-arm")){h713_owner_arm=0;assert(owner_step_set("1",NULL)==-EPERM);assert(!requests);return 0;}
 if(!strcmp(mode,"health-bad")){health_bad=true;assert(owner_step_set("1",NULL)<0);assert(owner_failed&&!requests);return 0;}
 if(!strcmp(mode,"lock-bad")){step(1);lock_bad=true;assert(owner_step_set("2",NULL)<0);assert(owner_failed&&!requests);return 0;}
 assert(owner_step_set("2",NULL)<0);assert(!requests);step(1);step(2);
 if(!strcmp(mode,"busy-timeout"))busy=true;
 if(!strcmp(mode,"done-timeout"))no_done=true;
 if(!strcmp(mode,"bad-positive"))response[0]=response[1]=0;
 step(3);step(4);step(5);step(6);
 if(owner_terminal){assert(owner_step_set("7",NULL)<0);assert(!at_writes&&!owner_claimed&&own==0xaa);assert(owner_raw[0][1]==(~0U)||!strcmp(mode,"bad-positive"));return 0;}
 lose_graph=!strcmp(mode,"lose-graph");lose_cfg=!strcmp(mode,"lose-cfg");lose_ctl=!strcmp(mode,"lose-ctl");
 if(!strcmp(mode,"context-drift")){cfg=1;assert(owner_step_set("7",NULL)<0);assert(owner_failed&&!at_writes);return 0;}
 if(!strcmp(mode,"graph-failure")){graph_failure=true;assert(owner_step_set("7",NULL)<0);assert(owner_failed&&!owner_claimed&&requests==2&&!at_writes);assert(owner_step_set("8",NULL)<0);return 0;}
 step(7);assert(graph_writes==(h713_owner_arm==1?0:22));
 step(8);if(!strcmp(mode,"late-timeout"))no_done=true;step(9);step(10);step(11);step(12);
 if(owner_terminal){assert(lose_graph||no_done);assert(owner_step_set("13",NULL)<0);assert(at_writes==0&&requests==(no_done?3:4));assert(!owner_claimed);return 0;}
 step(13);step(14);step(15);step(16);step(17);step(18);
 if(owner_terminal){assert(lose_cfg);assert(owner_step_set("19",NULL)<0);assert(at_writes==1&&requests==6);return 0;}
 step(19);assert(h713_owner_arm==1||ctl==0);step(20);step(21);step(22);step(23);step(24);step(25);
 assert(owner_terminal&&!owner_claimed&&own==0xaa&&requests==8);
 assert(at_writes==(h713_owner_arm==1?0:3));assert(owner_step_set("26",NULL)<0);
 assert((owner_raw[3][0]&0xffff)==(lose_ctl?0:1));
 char buf[4096];assert(owner_state_get(buf,NULL)<4096);assert(strstr(buf,"h713-owner-boundary-v1"));if(!strcmp(mode,"sham")||!strcmp(mode,"preserved"))puts(buf);return 0;
}
