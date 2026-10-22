/* Native fake-MMIO execution of the actual built-in observer. */
#include <assert.h>
#include <errno.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdarg.h>
#include <sys/types.h>
typedef uint32_t u32;
typedef uint16_t u16;
typedef uint64_t u64;
#define __iomem
#define __init __attribute__((unused))
#define BIT(n) (1U << (n))
#define ARRAY_SIZE(a) (sizeof(a) / sizeof((a)[0]))
#define DEFINE_MUTEX(n) int n
#define mutex_lock(p) ((void)(p))
#define mutex_unlock(p) ((void)(p))
#define late_initcall(f)
#define IS_ERR(p) ((uintptr_t)(p) > (uintptr_t)-4096)
#define PTR_ERR(p) ((int)(intptr_t)(p))
#define __ATTR_WO(n) { .attr = {0} }
#define __ATTR_RO(n) { .attr = {0} }
struct kobject {int dummy;};
struct attribute {int dummy;};
struct kobj_attribute {struct attribute attr;};
struct attribute_group {struct attribute **attrs;};
struct device_node {int dummy;};
struct of_phandle_args {struct device_node *np; int args_count; unsigned int args[1];};
struct clk {int enabled;};
struct reset_control {int dummy;};
enum {CLK_PLL_VIDEO0,CLK_PLL_ADC,CLK_BUS_TVCAP,CLK_BUS_CAP_300M,
 CLK_VINCAP_DMA,CLK_TVFE_1296M,CLK_BUS_HDMI_AUDIO,CLK_HDMI_AUDIO,
 CLK_AUDIO_CPU,CLK_AUDIO_UMAC,CLK_AUDIO_IHB,CLK_PLL_VIDEO2,
 CLK_DEINT,CLK_PANEL,CLK_SVP_DTL,CLK_AFBD,CLK_BUS_DISP};
static struct clk fake_clocks[17];
static struct reset_control fake_reset;
static struct device_node fake_node;
static struct kobject fake_obj, *kernel_kobj = &fake_obj;
static char logbuf[4096];
static bool h713_tvfe_retain_applied = true, h713_tvfe_retain_violated;
static void *h713_tvfe_trace_r_ccu = (void *)0x07010000;
static void *h713_tvfe_trace_ppu = (void *)0x07001000;
static u32 gate=0x10001, tvfe=0x10000, tvcap=0x10000;
static u32 ccu[0xcc/4], at[4], own, peer, response[2], status;
static int writes, requests, deasserts, resource_denied, ignore_lock, no_done, busy;
static u32 wanted0=1, wanted1=1;

#define pr_notice(...) snprintf(logbuf, sizeof(logbuf), __VA_ARGS__)
#define pr_err(...) snprintf(logbuf, sizeof(logbuf), __VA_ARGS__)
static void *request_mem_region(uintptr_t p, unsigned size, const char *s)
{return resource_denied ? NULL : &fake_obj;}
static void *ioremap(uintptr_t p, unsigned size) {return (void *)p;}
static struct device_node *of_find_compatible_node(void *a, void *b, const char *s) {return &fake_node;}
static struct device_node *of_find_node_by_path(const char *s) {return &fake_node;}
static void *of_find_property(struct device_node *n,const char *s,void *len) {return NULL;}
static void of_node_put(struct device_node *n) {}
static struct clk *of_clk_get_from_provider(struct of_phandle_args *s) {assert(s->args[0]<17);return &fake_clocks[s->args[0]];}
static int clk_prepare_enable(struct clk *c) {c->enabled=1;return 0;}
static int __clk_is_enabled(struct clk *c) {return c->enabled;}
static void usleep_range(unsigned a,unsigned b) {assert(a<=b);}
static struct reset_control *of_reset_control_get_exclusive(struct device_node *n,const char *s) {return &fake_reset;}
static int reset_control_status(struct reset_control *r) {return !(ccu[0x54/4] & BIT(16));}
static int reset_control_deassert(struct reset_control *r) {deasserts++;ccu[0x54/4]|=BIT(16);return 0;}
static int kstrtouint(const char *s,unsigned base,unsigned *n) {*n=strtoul(s,NULL,base);return 0;}
static int sysfs_emit_at(char *buf,int off,const char *fmt,...) {
 va_list a;va_start(a,fmt);int n=vsnprintf(buf+off,4096-off,fmt,a);va_end(a);return n;
}
#define sysfs_emit(b,...) sysfs_emit_at(b,0,__VA_ARGS__)
static struct kobject *kobject_create_and_add(const char *s,struct kobject *p) {return &fake_obj;}
static int sysfs_create_group(struct kobject *p,const struct attribute_group *g) {return 0;}
static void kobject_put(struct kobject *p) {}

static u32 readl(const void *p) {
 uintptr_t a=(uintptr_t)p;
 if(a==0x070101ac) return gate;
 if(a==0x070010a4 || a==0x07001124) {
  assert((gate & 0x10001)==0x10001);return a==0x070010a4 ? tvfe : tvcap;
 }
 if(a==0x0306101c || a==0x07000400) return 0;
 if(a>=0x02001d10 && a<0x02001ddc) return ccu[(a-0x02001d10)/4];
 if(a==0x05700040) return 0x00011111;
 if(a==0x05700044 || a==0x05700088) return 0x11111111;
 if(a==0x05700080) return 0x00001111;
 if(a==0x05700000) return 0xfff11111;
 if(a==0x05700004) return 1;
 if(a==0x05700084) return 0xfff000ef;
 assert((tvfe & 0x30008)==0x10000 && (tvcap & 0x30008)==0x10000);
 assert((ccu[0x54/4] & 0x10001)==0x10001 && (ccu[0x78/4] & 0x10001)==0x10001);
 if(a>=0x0614a000 && a<=0x0614a00c) return at[(a-0x0614a000)/4];
 if(a==0x05001530) return peer;
 if(a==0x05001534) return own;
 if(a==0x06144000) return busy ? BIT(4)|BIT(7) : status;
 if(a==0x06144010) return response[0];
 if(a==0x06144018) return response[1];
 assert(!"unexpected MMIO read");return 0;
}
static void writel(u32 v,void *p) {
 uintptr_t a=(uintptr_t)p;writes++;
 /* Neither PPU/RTC/GP6 nor lock-peer writes are allowed. */
 assert(a!=0x05001530 && !(a>=0x07000000 && a<0x08000000));
 if(a>=0x02001d10 && a<0x02001ddc) {ccu[(a-0x02001d10)/4]=v;return;}
 if(a==0x0614a000 || a==0x0614a00c) {at[(a-0x0614a000)/4]=v;return;}
 if(a==0x05001534) {assert(v==0x55 || v==0xaa);if(!ignore_lock)own=v;return;}
 if(a==0x06144010 || a==0x06144018) {
  assert(v==0x80ff0000 && own==0x55);requests++;
  unsigned dev=a==0x06144018;response[dev]=0x80ff0000|(dev ? wanted1:wanted0);
  if(!no_done) status|=BIT(dev ? 8:5);
  return;
 }
 assert(!"unexpected MMIO write");
}
#define readl_poll_timeout(p,v,condition,delay,timeout) ({ \
 int _ret=-ETIMEDOUT;assert((delay)==10);assert((timeout)==10000 || (timeout)==50000); \
 for(int _i=0;_i<4;_i++){(v)=readl(p);if(condition){_ret=0;break;}}_ret;})
/* Only the stock-response helper is used by this bench. */
#define ktime_get_ns() 0ULL
#define cpu_relax() ((void)0)

#include "observer.inc"

static int step(unsigned n) {
 char b[20];snprintf(b,sizeof(b),"%u",n);return step_store(NULL,NULL,b,strlen(b));
}
int main(int argc,char **argv) {
 const char *mode=argc>1 ? argv[1] : "normal";
 ccu[0x78/4]=0x10001;
 if(!strcmp(mode,"inherited")) {at[0]=0x700;at[3]=0x011a5e00;}
 if(!strcmp(mode,"zero")) wanted0=wanted1=0;
 if(!strcmp(mode,"done-timeout")) no_done=1;
 if(!strcmp(mode,"lock-mismatch")) ignore_lock=1;
 if(!strcmp(mode,"resource-denied")) resource_denied=1;
 assert(step(2)<0 && requests==0 && writes==0); /* no skipped steps */
 if(!strcmp(mode,"closed-gate")) {
  gate=0;assert(step(1)<0 && requests==0);assert(step(1)<0);return 0;
 }
 if(!strcmp(mode,"violated")) {
  h713_tvfe_retain_violated=true;assert(step(1)<0 && writes==0);return 0;
 }
 for(unsigned n=1;n<=46;n++) {
  if(!strcmp(mode,"busy-timeout") && n==43) busy=1;
  if(!strcmp(mode,"power-loss") && n==43) tvfe=0x20000;
  int before=requests,ret=step(n);
  if(ret<0) {
   assert(retention_failed);assert(step(n)<0 && requests==before);
   assert(!strcmp(mode,"lock-mismatch") || !strcmp(mode,"resource-denied") || !strcmp(mode,"power-loss"));
   assert(requests==0);return 0;
  }
 }
 assert(retention_step==46 && !retention_failed && !retention_claimed && own==0xaa);
 assert(deasserts==1);
 if(no_done || busy) {
  assert(retention_timeout && retention_outcome[0]==2 && retention_outcome[1]==3);
  assert(retention_raw[0]==~0U && retention_raw[1]==~0U);
  assert(requests==(busy?0:1));
 } else {
  assert(requests==2 && retention_outcome[0]==1 && retention_outcome[1]==1);
  assert((retention_raw[0]&0xffff)==wanted0 && (retention_raw[1]&0xffff)==wanted1);
 }
 if(!strcmp(mode,"inherited")) assert(retention_inherited);
 char json[4096];state_show(NULL,NULL,json);assert(strstr(json,"\"step\":46"));
 assert(step(47)<0 && step(43)<0);return 0;
}
