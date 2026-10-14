/* Native controls for the actual continuous-poll helper. No hardware access. */
#include <stdint.h>
#include <assert.h>
#include <errno.h>
#include <stdio.h>
typedef uint32_t u32;
typedef uint64_t u64;
typedef uint16_t u16;
#define __iomem
static u64 now, step, clear_begin, clear_end;
static unsigned reads;
static unsigned clock_reads;
static u32 mask;
static u64 ktime_get_ns(void) { clock_reads++; return now; }
static void cpu_relax(void) { }
static u32 readl(void *port)
{
 (void)port;
 now += step;
 reads++;
 return (now >= clear_begin && now < clear_end) ? 0 : mask;
}
static void writel(u32 value, void *port) { (void)value; (void)port; assert(0); }
#define readl_poll_timeout(port, value, condition, delay, timeout) ({ \
 int err = -ETIMEDOUT; \
 for (unsigned i=0; i<(timeout)/(delay); i++) { \
  (value)=readl(port); if (condition) { err=0; break; } \
 } err; })
#include "../../modules/hdmi-dsp-probe/h713-dsp-completion.h"
static void reset(u32 done, u64 cost, u64 begin, u64 end)
{
 now=reads=clock_reads=0; mask=done; step=cost; clear_begin=begin; clear_end=end;
}
int main(void)
{
 u32 status;
 /* Precomputed deadline path reads MMIO before calling the clock. */
 reset(0x20,50,0,100);
 assert(!h713_dsp_wait_clear_until(NULL,&status,mask,100000));
 assert(clock_reads == 0 && reads == 1);
 /* A 200 ns clear pulse between 1-us polling instants is observed. */
 reset(0x20,50,350,550);
 assert(!h713_dsp_wait_clear(NULL,&status,mask,100));
 assert(now == 350 && status == 0);
 /* Sticky completion must time out, never count as fresh completion. */
 reset(0x20,50,UINT64_MAX,UINT64_MAX);
 assert(h713_dsp_wait_clear(NULL,&status,mask,100) == -ETIMEDOUT);
 assert(now == 100000 && status == 0x20);
 /* Delayed clear and device1's separate done mask. */
 reset(0x100,500,250000,251000);
 assert(!h713_dsp_wait_clear(NULL,&status,mask,50000));
 assert(now == 250000);
 /* Slow MMIO is bounded by elapsed time, not number of iterations. */
 reset(0x100,30000,UINT64_MAX,UINT64_MAX);
 assert(h713_dsp_wait_clear(NULL,&status,mask,100) == -ETIMEDOUT);
 assert(now == 120000 && reads == 4);
 puts("PASS: short clear pulse, sticky timeout, delayed device1 edge, slow-MMIO elapsed bound");
}
