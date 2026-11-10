#!/usr/bin/env python3
"""Compile the actual TVFE component against fake MMIO/clock/reset providers."""
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
source = r'''
#include <stdint.h>
#include <stdbool.h>
#include <stdio.h>
#include <string.h>
#include <errno.h>
#include <assert.h>
typedef uint16_t u16;
typedef uint32_t u32;
#define __iomem
#define BIT(n) (1U<<(n))
#define ARRAY_SIZE(a) (sizeof(a)/sizeof((a)[0]))
#define IS_ERR(p) ((uintptr_t)(p) > (uintptr_t)-4096)
#define IS_ERR_OR_NULL(p) (!(p) || IS_ERR(p))
#define PTR_ERR(p) ((int)(intptr_t)(p))
#define pr_info(...) ((void)0)
#define pr_err(...) ((void)0)
#define CLK_PLL_VIDEO0 0
#define CLK_PLL_ADC 1
struct device_node { int dummy; };
struct clk { int dummy; };
struct reset_control { int dummy; };
struct of_phandle_args { int args_count; struct device_node *np; unsigned int args[1]; };
static struct device_node node;
static struct clk clock;
static struct reset_control reset;
static u32 ccu_words[22], baseline[22], tvfe_word;
static int maps, fail_map, bus_writes, assertions, deassertions, reset_asserted;
static int clock_gets, clock_puts, reset_puts;
static void *ioremap(unsigned address, unsigned size) {
 (void)size;
 if (++maps == fail_map) return NULL;
 return address == 0x02001d10 ? (void *)ccu_words : (void *)&tvfe_word;
}
static void iounmap(void *p) { (void)p; }
static u32 readl(void *p) { return *(u32 *)p; }
static void writel(u32 value, void *p) {
 if (p == &ccu_words[0x54/4]) bus_writes++;
 *(u32 *)p=value;
}
static void usleep_range(unsigned min, unsigned max) { (void)min; (void)max; }
static struct device_node *of_find_compatible_node(void *a, void *b, const char *c) {
 (void)a; (void)b; (void)c; return &node;
}
static bool of_device_is_available(struct device_node *p) { (void)p; return true; }
static void of_node_put(struct device_node *p) { (void)p; }
static struct clk *of_clk_get_from_provider(struct of_phandle_args *p) {
 (void)p; clock_gets++; return &clock;
}
static bool __clk_is_enabled(struct clk *p) { (void)p; return true; }
static int clk_prepare_enable(struct clk *p) { (void)p; return 0; }
static void clk_disable_unprepare(struct clk *p) { (void)p; }
static void clk_put(struct clk *p) { (void)p; clock_puts++; }
static unsigned long clk_get_rate(struct clk *p) __attribute__((unused));
static unsigned long clk_get_rate(struct clk *p) { (void)p; return 1; }
static struct reset_control *of_reset_control_get_shared(struct device_node *p, const char *name) {
 (void)p; (void)name; return &reset;
}
static int reset_control_status(struct reset_control *p) { (void)p; return reset_asserted; }
static int reset_control_deassert(struct reset_control *p) {
 (void)p; deassertions++; reset_asserted=0; ccu_words[0x54/4] |= BIT(16); return 0;
}
static int reset_control_assert(struct reset_control *p) {
 (void)p; assertions++; reset_asserted=1; ccu_words[0x54/4] &= ~BIT(16); return 0;
}
static void reset_control_put(struct reset_control *p) { (void)p; reset_puts++; }
#include "h713-hdmi-tvfe.c"
static void fresh(void) {
 for (unsigned i=0; i<ARRAY_SIZE(ccu_words); i++) ccu_words[i]=0x100+i;
 ccu_words[0x54/4]=0;
 memcpy(baseline,ccu_words,sizeof(baseline));
 maps=fail_map=bus_writes=assertions=deassertions=0;
 clock_gets=clock_puts=reset_puts=0;
 reset_asserted=1; tvfe_word=0x00111111;
}
int main(void) {
 fresh();
 assert(!h713_hdmi_tvfe_prepare());
 assert(tvfe_word==0x00111111 && deassertions==1 && clock_gets==2);
 h713_hdmi_tvfe_release();
 assert(!memcmp(ccu_words,baseline,sizeof(baseline)));
 assert(assertions==1 && reset_puts==1 && clock_puts==clock_gets && reset_asserted==1);
 /* Mapping failure must not write an unsaved bus value. */
 fresh(); fail_map=2;
 assert(h713_hdmi_tvfe_prepare()==-ENOMEM);
 assert(bus_writes==0 && !memcmp(ccu_words,baseline,sizeof(baseline)));
 /* Reject inherited demod ownership without changing it or reset refs. */
 fresh(); ccu_words[0x54/4]=BIT(16)|BIT(0);
 assert(h713_hdmi_tvfe_prepare()==-EBUSY);
 assert(ccu_words[0x54/4]==(BIT(16)|BIT(0)) && deassertions==0);
 /* Uninitialized source3 TVFE control fails and fully rolls clocks back. */
 fresh(); tvfe_word=0;
 assert(h713_hdmi_tvfe_prepare()==-EBUSY);
 assert(!memcmp(ccu_words,baseline,sizeof(baseline)) && reset_asserted==1);
 assert(assertions==1 && clock_gets==clock_puts);
 puts("PASS: actual TVFE setup/restore, second-map failure without unsaved writes, inherited-owner rejection, uninitialized-source rollback");
}
'''
with tempfile.TemporaryDirectory(prefix='h713-tvfe-test-') as directory:
    directory = Path(directory)
    for header in ('linux/clk.h','linux/clk-provider.h','linux/delay.h','linux/io.h',
                   'linux/module.h','linux/of.h','linux/of_clk.h','linux/reset.h',
                   'dt-bindings/clock/sun50i-h713-ccu.h'):
        path=directory/header
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('/* Fake provider declarations come from the test harness. */\n')
    (directory/'test.c').write_text(source)
    subprocess.run(['cc','-Wall','-Wextra','-Werror','-Wno-sign-compare','-Wno-missing-field-initializers',
                    '-I',str(directory),'-I',str(ROOT/'modules/hdmi-audio'),
                    str(directory/'test.c'),'-o',str(directory/'test')],check=True)
    subprocess.run([str(directory/'test')],check=True)
