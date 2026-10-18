from pathlib import Path
import subprocess

import argparse
parser = argparse.ArgumentParser(description='Host simulation of extracted H713 panel sequencing helpers')
parser.add_argument('source', type=Path, help='patched arch/arm/mach-sunxi/h713_mips.c')
parser.add_argument('output', type=Path, help='scratch output directory')
args = parser.parse_args()
source = args.source.read_text()
def function(name):
    start=source.index('static ',source.index(name+'(')-15)
    brace=source.index('{',start)
    depth=1;end=brace+1
    while depth:
        if source[end]=='{':depth+=1
        elif source[end]=='}':depth-=1
        end+=1
    return source[start:end]
functions='\n'.join(function(name) for name in ('h713_disp_signal_off','h713_disp_panel_initial_off','h713_disp_stock_panel_power'))
preamble=r'''
#include <assert.h>
#include <errno.h>
#include <stdint.h>
#include <stdbool.h>
#include <stdio.h>
#include <string.h>
typedef uint32_t u32;
struct udevice { int unused; };
struct gpio_desc { int unused; };
static struct udevice supply_device;
static struct gpio_desc h713_panel_reset;
static int h713_disp_configured;
#define H713_MIPS_STATUS_REG 0x0306101cUL
#define H713_DISP_AFBD_CTRL_REG 0x05600140UL
#define H713_PANEL_INITIAL_OFF_US 3000000U
#define BIT(x) (1U << (x))
#define max_t(t,a,b) ((t)(a) > (t)(b) ? (t)(a) : (t)(b))
static uint64_t now_us, off_at;
static u32 dt_off;
static int mips, ready, prepared, writes, reset, enabled, count, probed, enables;
static int fail_hold, reset_read, fail_supply, disable_error, enable_read_error, stuck_on, fail_release;
static u32 readl(uintptr_t address) { assert(address==H713_MIPS_STATUS_REG); return mips; }
static void h713_display_prepare(void) { ready=1; prepared++; }
static void clrbits_le32(void *address, u32 mask) { assert(ready); assert((uintptr_t)address==H713_DISP_AFBD_CTRL_REG && mask==1); }
static void writel(u32 value, uintptr_t address) { (void)value; assert(ready); assert(address>=0x05000000 && address<0x06000000); writes++; }
static void dmb(void) {}
static void mdelay(unsigned long value) { now_us += (uint64_t)value*1000; }
static void udelay(unsigned long value) { now_us += value; }
static int h713_panel_hold_reset(int hold) {
    assert(ready && writes>=7);
    if (hold && fail_hold) return -EPERM;
    if (!hold && fail_release) return -EIO;
    if (!hold) assert(enabled);
    reset=hold;
    return 0;
}
static int dm_gpio_get_value(struct gpio_desc *gpio) { (void)gpio; return reset_read>=0 ? reset_read : reset; }
static int h713_panel_supply(struct udevice **device) {
    assert(reset);
    if (fail_supply) return -ENODEV;
    if (!probed) { probed=1; enabled=0; off_at=now_us; }
    *device=&supply_device;
    return 0;
}
static int regulator_set_enable(struct udevice *device, int on) {
    (void)device;
    if (!on) {
        if (disable_error) return disable_error;
        if (count>1) return -EBUSY;
        if (!count) return -EALREADY;
        enabled=0;count--;off_at=now_us;
        return 0;
    }
    assert(reset);
    assert(now_us-off_at >= (dt_off>3000000U ? dt_off:3000000U));
    enabled=1;count++;enables++;
    return 0;
}
static int regulator_get_enable(struct udevice *device) { (void)device; return enable_read_error ? enable_read_error : (stuck_on ? 1:enabled); }
static u32 dev_read_u32_default(struct udevice *device, const char *key, u32 fallback) { (void)device;(void)fallback;assert(!strcmp(key,"off-on-delay-us"));return dt_off; }
static void h713_panel_print_power(const char *phase) { (void)phase; }
'''
tests=r'''
static void clean(void) {
    now_us=off_at=0;dt_off=250000;mips=0;ready=0;prepared=0;writes=0;reset=0;enabled=1;count=0;probed=0;enables=0;
    h713_disp_configured=0;fail_hold=0;reset_read=-1;fail_supply=0;disable_error=0;enable_read_error=0;stuck_on=0;fail_release=0;
}
int main(void) {
    clean();assert(h713_disp_panel_initial_off()==0);assert(prepared==1 && !enabled && reset && !enables);assert(now_us-off_at>=3000000U);assert(h713_disp_stock_panel_power()==0);assert(enabled && !reset && enables==1);
    clean();h713_disp_configured=1;ready=1;probed=1;count=1;assert(h713_disp_panel_initial_off()==0);assert(prepared==0 && count==0);assert(h713_disp_stock_panel_power()==0);
    clean();dt_off=4500123;assert(h713_disp_panel_initial_off()==0);assert(now_us-off_at>=4500123);assert(h713_disp_stock_panel_power()==0);
    clean();mips=1;assert(h713_disp_panel_initial_off()==-EBUSY);assert(!prepared && !writes && !probed && !enables);
    clean();fail_hold=1;assert(h713_disp_panel_initial_off()==-EPERM);assert(!probed && !enables);
    clean();reset_read=0;assert(h713_disp_panel_initial_off()==-EIO);assert(!probed && !enables);
    clean();fail_supply=1;assert(h713_disp_panel_initial_off()==-ENODEV);assert(reset && !enables);
    clean();probed=1;count=2;assert(h713_disp_panel_initial_off()==-EBUSY);assert(!enables);
    clean();enable_read_error=-EIO;assert(h713_disp_panel_initial_off()==-EIO);assert(!enables);
    clean();stuck_on=1;assert(h713_disp_panel_initial_off()==-EBUSY);assert(!enables);
    clean();assert(h713_disp_panel_initial_off()==0);fail_release=1;assert(h713_disp_stock_panel_power()==-EIO);assert(reset);
    puts("PASS: 11 initial-state, minimum-delay, shared-supply and failure-path cases");
    return 0;
}
'''
out = args.output.resolve()
out.mkdir(parents=True, exist_ok=True)
(out/'sequence_harness.c').write_text(preamble+'\n'+functions+'\n'+tests)
subprocess.run(['clang','-std=c11','-Wall','-Wextra','-Werror',str(out/'sequence_harness.c'),'-o',str(out/'sequence_harness')],check=True)
subprocess.run([str(out/'sequence_harness')],check=True)
