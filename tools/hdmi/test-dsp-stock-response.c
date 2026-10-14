/* Controls for the actual stock request/completion helper; fake MMIO only. */
#include <stdint.h>
#include <assert.h>
#include <errno.h>
#include <stdio.h>
typedef uint16_t u16;
typedef uint32_t u32;
typedef uint64_t u64;
#define __iomem
static u32 status_reg, command_reg, reply, done_mask;
static unsigned ticks, complete_at, writes, response_reads;
static u64 ktime_get_ns(void) { return (u64)ticks*10000; }
static void cpu_relax(void) { }
static void writel(u32 value, void *port)
{
 assert(port == &command_reg && value == 0x007c0000);
 command_reg=value; writes++;
 if (complete_at == 0) { command_reg=reply; status_reg=done_mask; }
 else status_reg=0;
}
static u32 readl(void *port)
{
 if (port == &status_reg) {
  ticks++;
  if (ticks >= complete_at) { command_reg=reply; status_reg=done_mask; }
 } else { assert(port == &command_reg); response_reads++; }
 return *(u32 *)port;
}
#define readl_poll_timeout(port, value, condition, delay, timeout) ({ \
 int err = -ETIMEDOUT; \
 for (unsigned i=0; i<(timeout)/(delay); i++) { \
  (value)=readl(port); if (condition) { err=0; break; } \
 } err; })
#include "../../modules/hdmi-dsp-probe/h713-dsp-completion.h"
static void reset(unsigned at, u32 mask)
{
 ticks=writes=response_reads=0; complete_at=at; done_mask=mask;
 reply=0x8081; status_reg=mask; command_reg=0;
}
int main(void)
{
 u32 status, response;
 /* New reply completes before the first status read: no clear sampled. */
 reset(0,0x20); response=0xdeadbeef;
 assert(!h713_dsp_stock_response(&status_reg,&command_reg,0x7c,done_mask,&status,&response));
 assert(response == 0x8081 && writes == 1 && response_reads == 1);
 /* Old done was set, but the command starts a slower fresh completion. */
 reset(8,0x20);
 assert(!h713_dsp_stock_response(&status_reg,&command_reg,0x7c,done_mask,&status,&response));
 assert(ticks == 8 && response == 0x8081);
 /* Independent device1 done mask. */
 reset(3,0x100);
 assert(!h713_dsp_stock_response(&status_reg,&command_reg,0x7c,done_mask,&status,&response));
 assert(ticks == 3 && response == 0x8081);
 /* No completion: bounded timeout, no consumed or accepted response. */
 reset(6000,0x20); response=0xdeadbeef;
 assert(h713_dsp_stock_response(&status_reg,&command_reg,0x7c,done_mask,&status,&response) == -ETIMEDOUT);
 assert(ticks == 5000 && response_reads == 0 && response == 0xdeadbeef && writes == 1);
 puts("PASS: immediate completed reply, delayed fresh reply, device1 mask, bounded timeout without response consumption");
}
