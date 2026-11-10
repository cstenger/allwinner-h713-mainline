/* SPDX-License-Identifier: GPL-2.0-only */
/* Isolated owner build only; no independent DSP client and no teardown. */
#include <linux/mutex.h>
unsigned h713_owner_arm;
module_param_named(owner_arm, h713_owner_arm, uint, 0400);
static DEFINE_MUTEX(owner_mutex);
static unsigned owner_step, owner_attempted;
static bool owner_failed, owner_timeout, owner_claimed, owner_terminal;
static u32 owner_ctl, owner_cfg;
static u32 owner_raw[4][2] = {{~0U,~0U},{~0U,~0U},{~0U,~0U},{~0U,~0U}};
static u32 owner_phase[4][2], owner_sent[4][2], owner_status[4][2];
static u32 owner_outcome[4][2];
int h713_owner_health(u32 *ctl, u32 *cfg);
int h713_owner_audiotop(unsigned operation);

static bool owner_patched(unsigned pair)
{
 return owner_outcome[pair][0] == 1 && owner_outcome[pair][1] == 1 &&
  (owner_raw[pair][0] & 0xffff) == 1 && (owner_raw[pair][1] & 0xffff) == 1;
}
static int owner_version(unsigned pair, unsigned dev)
{
 u32 status, response;
 int ret;
 if (!owner_claimed) return -EPERM;
 if (owner_timeout) {
  owner_phase[pair][dev] = 6; owner_outcome[pair][dev] = 3;
  pr_notice("H713 OWNER pair=%u dev=%u SKIPPED sent=0\n", pair, dev);
  return 0;
 }
 owner_phase[pair][dev] = 1;
 pr_notice("H713 OWNER pair=%u dev=%u BUSY_WAIT sent=0\n", pair, dev);
 ret = readl_poll_timeout(port, status, !(status & BIT(dev ? 7 : 4)), 10, 50000);
 if (ret) goto timeout;
 owner_phase[pair][dev] = 2;
 pr_notice("H713 OWNER pair=%u dev=%u COMMAND_WRITE_BEGIN status=%08x\n",pair,dev,status);
 writel(0x80ff0000, port + (dev ? 0x18 : 0x10));
 owner_sent[pair][dev] = 1; owner_phase[pair][dev] = 4;
 pr_notice("H713 OWNER pair=%u dev=%u COMMAND_SENT sent=1\n",pair,dev);
 pr_notice("H713 OWNER pair=%u dev=%u DONE_WAIT sent=1\n",pair,dev);
 ret = readl_poll_timeout(port, status, status & BIT(dev ? 8 : 5), 10, 50000);
 if (ret) goto timeout;
 response = readl(port + (dev ? 0x18 : 0x10));
 owner_raw[pair][dev] = response; owner_status[pair][dev] = status;
 owner_phase[pair][dev] = 5; owner_outcome[pair][dev] = 1;
 pr_notice("H713 OWNER pair=%u dev=%u COMPLETE status=%08x response=%08x\n",pair,dev,status,response);
 return 0;
timeout:
 owner_status[pair][dev] = status; owner_outcome[pair][dev] = 2; owner_timeout = true;
 pr_notice("H713 OWNER pair=%u dev=%u %s_TIMEOUT status=%08x sent=%u\n",pair,dev,
  owner_sent[pair][dev] ? "DONE" : "BUSY",status,owner_sent[pair][dev]);
 return 0;
}
static int owner_checkpoint(unsigned pair)
{
 if (owner_claimed || readl(dsp_lock.own) != 0xaa) return -EIO;
 if (owner_timeout || !owner_patched(pair)) owner_terminal = true;
 if (pair == 3) owner_terminal = true;
 return 0;
}
/* The exact existing 22-word normal teardown, retaining maps/clocks and
 * the lifetime pin. No patch operation, new address or rollback is added. */
static int owner_restore_graph(void)
{
 int ret,release;
 if (!graph_active || graph_written != ARRAY_SIZE(graph_settings)) return -EPERM;
 ret = h713_dsp_claim(&dsp_lock);
 if (ret) return ret;
 owner_claimed = true;
 while (graph_written) {
  unsigned index = graph_written - 1;
  ret = write_verified(graph_settings[index].address,graph_saved[index]);
  if (ret) break;
  pr_notice("H713 OWNER graph-restore address=%04x value=%04x verified\n",graph_settings[index].address,graph_saved[index]);
  graph_written--;
 }
 release = h713_dsp_release(&dsp_lock);
 if (!release) owner_claimed = false;
 return ret ? ret : release;
}
static int owner_operation(unsigned n)
{
 unsigned pair;
 int ret;
 switch (n) {
 case 1:
  return owner_ctl == 0x700 && owner_cfg == 0x011a5e00 ? 0 : -EPERM;
 case 2: case 8: case 14: case 21:
  ret = h713_dsp_claim(&dsp_lock);
  if (!ret) owner_claimed = true;
  return ret;
 case 3: case 4: return owner_version(0, n - 3);
 case 9: case 10: return owner_version(1, n - 9);
 case 15: case 16: return owner_version(2, n - 15);
 case 22: case 23: return owner_version(3, n - 22);
 case 5: case 11: case 17: case 24:
  if (!owner_claimed) return -EPERM;
  ret = h713_dsp_release(&dsp_lock);
  if (!ret) owner_claimed = false;
  return ret;
 case 6: case 12: case 18: case 25:
  pair = n == 6 ? 0 : n == 12 ? 1 : n == 18 ? 2 : 3;
  return owner_checkpoint(pair);
 case 7: case 13: case 19: case 20:
  pair = n == 7 ? 0 : n == 13 ? 1 : 2;
  if (owner_timeout || owner_claimed || !owner_patched(pair)) return -EPERM;
  if (h713_owner_arm == 2) {
   ret = n == 7 ? owner_restore_graph() : h713_owner_audiotop(n == 13 ? 1 : n == 19 ? 2 : 3);
   if (ret) return ret;
  }
  /* Both arms share settling waits, including no-write shams. */
  usleep_range(n == 7 ? 100000 : 10000,n == 7 ? 101000 : 15000);
  return 0;
 }
 return -EINVAL;
}
static int owner_expected(unsigned step)
{
 u32 cfg = h713_owner_arm == 2 && step >= 13 ? 0 : 0x011a5e00;
 u32 ctl = h713_owner_arm == 2 && step == 19 ? 0 : 0x700;
 return owner_ctl == ctl && owner_cfg == cfg ? 0 : -EIO;
}
static int owner_step_set(const char *value, const struct kernel_param *kp)
{
 unsigned n;
 int ret;
 if (kstrtouint(value,10,&n)) return -EINVAL;
 mutex_lock(&owner_mutex);
 if (h713_owner_arm < 1 || h713_owner_arm > 2 || owner_failed || owner_terminal ||
     n != owner_step + 1 || n > 25 || h713_dsp_failed || !graph_active) {
  ret = -EPERM; goto out;
 }
 ret = h713_owner_health(&owner_ctl,&owner_cfg);
 if (!ret) ret = owner_expected(owner_step);
 if (ret) { owner_failed = true; goto out; }
 owner_attempted = n;
 pr_notice("H713 OWNER step=%u BEGIN arm=%u ctl=%08x cfg=%08x\n",n,h713_owner_arm,owner_ctl,owner_cfg);
 ret = owner_operation(n);
 if (!ret) ret = h713_owner_health(&owner_ctl,&owner_cfg);
 if (!ret) ret = owner_expected(n);
 if (ret) {
  owner_failed = true;
  pr_err("H713 OWNER step=%u FAILED ret=%d; physical cold cycle required\n",n,ret);
 } else {
  owner_step = n;
  pr_notice("H713 OWNER step=%u DONE terminal=%u ctl=%08x cfg=%08x graph_remaining=%u\n",n,owner_terminal,owner_ctl,owner_cfg,graph_written);
 }
out:
 mutex_unlock(&owner_mutex);
 return ret;
}
static int owner_state_get(char *buf,const struct kernel_param *kp)
{
 unsigned i;
 int n;
 mutex_lock(&owner_mutex);
 n = scnprintf(buf,PAGE_SIZE,"{\"schema\":\"h713-owner-boundary-v1\",\"arm\":%u,\"step\":%u,\"attempted\":%u,\"failed\":%u,\"timeout\":%u,\"claimed\":%u,\"terminal\":%u,\"ctl\":%u,\"cfg\":%u,\"graph_remaining\":%u,\"pairs\":[",
  h713_owner_arm,owner_step,owner_attempted,owner_failed,owner_timeout,owner_claimed,owner_terminal,owner_ctl,owner_cfg,graph_written);
 for(i=0;i<4;i++)
  n += scnprintf(buf+n,PAGE_SIZE-n,"%s{\"raw\":[%u,%u],\"outcome\":[%u,%u],\"phase\":[%u,%u],\"sent\":[%u,%u],\"status\":[%u,%u]}",i ? "," : "",owner_raw[i][0],owner_raw[i][1],owner_outcome[i][0],owner_outcome[i][1],owner_phase[i][0],owner_phase[i][1],owner_sent[i][0],owner_sent[i][1],owner_status[i][0],owner_status[i][1]);
 n += scnprintf(buf+n,PAGE_SIZE-n,"],\"graph_saved\":[");
 for(i=0;i<ARRAY_SIZE(graph_saved);i++)
  n += scnprintf(buf+n,PAGE_SIZE-n,"%s%u",i ? "," : "",graph_saved[i]);
 n += scnprintf(buf+n,PAGE_SIZE-n,"]}\n");
 mutex_unlock(&owner_mutex);
 return n;
}
static const struct kernel_param_ops owner_step_ops = {.set=owner_step_set};
static const struct kernel_param_ops owner_state_ops = {.get=owner_state_get};
module_param_cb(owner_step,&owner_step_ops,NULL,0200);
module_param_cb(owner_state,&owner_state_ops,NULL,0400);
