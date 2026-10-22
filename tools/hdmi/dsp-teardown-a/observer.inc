/* SPDX-License-Identifier: GPL-2.0-only */
/* Phase A teardown bench, DSP translation unit. One explicit plan of
 * one-shot operations; no independent DSP client, patch or rollback. */
#include <linux/mutex.h>
unsigned h713_owner_arm;
module_param_named(owner_arm, h713_owner_arm, uint, 0400);
static DEFINE_MUTEX(owner_mutex);
enum { OWNER_CENSUS = 1, OWNER_CLAIM, OWNER_VERSION, OWNER_RELEASE, OWNER_CHECKPOINT,
 OWNER_GRAPH, OWNER_SPDI, OWNER_BRIDGE, OWNER_CFG, OWNER_CTL_OFF, OWNER_CTL_ON };
#define OWNER_PAIRS 6
static const struct { unsigned char op, arg; } owner_plan[] = {
 {OWNER_CENSUS,0},
 {OWNER_CLAIM,0},{OWNER_VERSION,0},{OWNER_VERSION,1},{OWNER_RELEASE,0},{OWNER_CHECKPOINT,0},
 {OWNER_GRAPH,0},
 {OWNER_CLAIM,1},{OWNER_VERSION,0},{OWNER_VERSION,1},{OWNER_RELEASE,1},{OWNER_CHECKPOINT,1},
 {OWNER_SPDI,1},
 {OWNER_CLAIM,2},{OWNER_VERSION,0},{OWNER_VERSION,1},{OWNER_RELEASE,2},{OWNER_CHECKPOINT,2},
 {OWNER_BRIDGE,2},
 {OWNER_CLAIM,3},{OWNER_VERSION,0},{OWNER_VERSION,1},{OWNER_RELEASE,3},{OWNER_CHECKPOINT,3},
 {OWNER_CFG,3},
 {OWNER_CLAIM,4},{OWNER_VERSION,0},{OWNER_VERSION,1},{OWNER_RELEASE,4},{OWNER_CHECKPOINT,4},
 {OWNER_CTL_OFF,4},{OWNER_CTL_ON,4},
 {OWNER_CLAIM,5},{OWNER_VERSION,0},{OWNER_VERSION,1},{OWNER_RELEASE,5},{OWNER_CHECKPOINT,5},
};
#define OWNER_STEPS ARRAY_SIZE(owner_plan)
static unsigned owner_step, owner_attempted, owner_pair, owner_requests;
static bool owner_failed, owner_timeout, owner_claimed, owner_terminal;
static u32 owner_ctl, owner_cfg, owner_want_ctl = 0x700, owner_want_cfg = 0x011a5e00;
static u32 owner_raw[OWNER_PAIRS][2] = {{~0U,~0U},{~0U,~0U},{~0U,~0U},{~0U,~0U},{~0U,~0U},{~0U,~0U}};
static u32 owner_phase[OWNER_PAIRS][2], owner_sent[OWNER_PAIRS][2], owner_status[OWNER_PAIRS][2];
static u32 owner_outcome[OWNER_PAIRS][2];
int h713_owner_health(u32 *ctl, u32 *cfg);
int h713_owner_census(void);
int h713_owner_spdi(void);
int h713_owner_bridge(void);
int h713_owner_audiotop(unsigned operation);
int h713_owner_context(char *buf, int size);

static bool owner_patched(unsigned pair)
{
 return owner_outcome[pair][0] == 1 && owner_outcome[pair][1] == 1 &&
  (owner_raw[pair][0] & 0xffff) == 1 && (owner_raw[pair][1] & 0xffff) == 1;
}
static int owner_version(unsigned pair, unsigned dev)
{
 u32 status, response;
 int ret;
 if (!owner_claimed || owner_want_ctl != 0x700) return -EPERM;
 if (owner_timeout) {
  owner_phase[pair][dev] = 6; owner_outcome[pair][dev] = 3;
  pr_notice("H713 TEARDOWN pair=%u dev=%u SKIPPED sent=0\n", pair, dev);
  return 0;
 }
 owner_phase[pair][dev] = 1;
 pr_notice("H713 TEARDOWN pair=%u dev=%u BUSY_WAIT sent=0\n", pair, dev);
 ret = readl_poll_timeout(port, status, !(status & BIT(dev ? 7 : 4)), 10, 50000);
 if (ret) goto timeout;
 owner_phase[pair][dev] = 2;
 pr_notice("H713 TEARDOWN pair=%u dev=%u COMMAND_WRITE_BEGIN status=%08x\n",pair,dev,status);
 writel(0x80ff0000, port + (dev ? 0x18 : 0x10));
 owner_requests++;
 owner_sent[pair][dev] = 1; owner_phase[pair][dev] = 4;
 pr_notice("H713 TEARDOWN pair=%u dev=%u COMMAND_SENT sent=1\n",pair,dev);
 pr_notice("H713 TEARDOWN pair=%u dev=%u DONE_WAIT sent=1\n",pair,dev);
 ret = readl_poll_timeout(port, status, status & BIT(dev ? 8 : 5), 10, 50000);
 if (ret) goto timeout;
 response = readl(port + (dev ? 0x18 : 0x10));
 owner_raw[pair][dev] = response; owner_status[pair][dev] = status;
 owner_phase[pair][dev] = 5; owner_outcome[pair][dev] = 1;
 pr_notice("H713 TEARDOWN pair=%u dev=%u COMPLETE status=%08x response=%08x\n",pair,dev,status,response);
 return 0;
timeout:
 owner_status[pair][dev] = status; owner_outcome[pair][dev] = 2; owner_timeout = true;
 pr_notice("H713 TEARDOWN pair=%u dev=%u %s_TIMEOUT status=%08x sent=%u\n",pair,dev,
  owner_sent[pair][dev] ? "DONE" : "BUSY",status,owner_sent[pair][dev]);
 return 0;
}
/* The changed or timed-out pair ends the plan; no later operation runs. */
static int owner_checkpoint(unsigned pair)
{
 if (owner_claimed || readl(dsp_lock.own) != 0xaa) return -EIO;
 if (owner_timeout || !owner_patched(pair) || pair == OWNER_PAIRS - 1) owner_terminal = true;
 return 0;
}
/* The exact existing 22-word normal teardown, in both arms. */
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
  pr_notice("H713 TEARDOWN graph-restore address=%04x value=%04x verified\n",graph_settings[index].address,graph_saved[index]);
  graph_written--;
 }
 release = h713_dsp_release(&dsp_lock);
 if (!release) owner_claimed = false;
 return ret ? ret : release;
}
static int owner_intervene(unsigned op, unsigned after)
{
 int ret = 0;
 if (owner_timeout || owner_claimed || !owner_patched(after)) return -EPERM;
 switch (op) {
 case OWNER_GRAPH: ret = owner_restore_graph(); break;
 case OWNER_SPDI: ret = h713_owner_spdi(); break;
 case OWNER_BRIDGE: ret = h713_owner_bridge(); break;
 case OWNER_CFG: case OWNER_CTL_OFF: case OWNER_CTL_ON:
  if (h713_owner_arm != 2) break;
  ret = h713_owner_audiotop(op - OWNER_CFG + 1);
  if (ret) return ret;
  if (op == OWNER_CFG) owner_want_cfg = 0;
  owner_want_ctl = op == OWNER_CTL_OFF ? 0 : 0x700;
  break;
 }
 if (ret) return ret;
 /* Both arms share settling waits, including no-write shams. */
 usleep_range(op == OWNER_GRAPH ? 100000 : 10000,op == OWNER_GRAPH ? 101000 : 15000);
 return 0;
}
static int owner_operation(unsigned n)
{
 unsigned op = owner_plan[n - 1].op, arg = owner_plan[n - 1].arg;
 int ret;
 switch (op) {
 case OWNER_CENSUS:
  if (owner_ctl != 0x700 || owner_cfg != 0x011a5e00) return -EPERM;
  return h713_owner_census();
 case OWNER_CLAIM:
  if (owner_claimed || owner_want_ctl != 0x700) return -EPERM;
  owner_pair = arg;
  ret = h713_dsp_claim(&dsp_lock);
  if (!ret) owner_claimed = true;
  return ret;
 case OWNER_VERSION: return owner_version(owner_pair, arg);
 case OWNER_RELEASE:
  if (!owner_claimed || owner_pair != arg) return -EPERM;
  ret = h713_dsp_release(&dsp_lock);
  if (!ret) owner_claimed = false;
  return ret;
 case OWNER_CHECKPOINT:
  if (owner_pair != arg) return -EPERM;
  return owner_checkpoint(arg);
 }
 return owner_intervene(op, arg);
}
static int owner_step_set(const char *value, const struct kernel_param *kp)
{
 unsigned n;
 int ret;
 if (kstrtouint(value,10,&n)) return -EINVAL;
 mutex_lock(&owner_mutex);
 if (h713_owner_arm < 1 || h713_owner_arm > 2 || owner_failed || owner_terminal ||
     n != owner_step + 1 || n > OWNER_STEPS || h713_dsp_failed || !graph_active) {
  ret = -EPERM; goto out;
 }
 ret = h713_owner_health(&owner_ctl,&owner_cfg);
 if (!ret && (owner_ctl != owner_want_ctl || owner_cfg != owner_want_cfg)) ret = -EIO;
 if (ret) { owner_failed = true; goto out; }
 owner_attempted = n;
 pr_notice("H713 TEARDOWN step=%u BEGIN arm=%u op=%u ctl=%08x cfg=%08x\n",n,h713_owner_arm,owner_plan[n-1].op,owner_ctl,owner_cfg);
 ret = owner_operation(n);
 if (!ret) ret = h713_owner_health(&owner_ctl,&owner_cfg);
 if (!ret && (owner_ctl != owner_want_ctl || owner_cfg != owner_want_cfg)) ret = -EIO;
 if (ret) {
  owner_failed = true;
  pr_err("H713 TEARDOWN step=%u FAILED ret=%d; physical cold cycle required\n",n,ret);
 } else {
  owner_step = n;
  pr_notice("H713 TEARDOWN step=%u DONE terminal=%u ctl=%08x cfg=%08x graph_remaining=%u\n",n,owner_terminal,owner_ctl,owner_cfg,graph_written);
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
 n = scnprintf(buf,PAGE_SIZE,"{\"schema\":\"h713-teardown-a-v1\",\"arm\":%u,\"step\":%u,\"steps\":%u,\"attempted\":%u,\"failed\":%u,\"timeout\":%u,\"claimed\":%u,\"terminal\":%u,\"requests\":%u,\"ctl\":%u,\"cfg\":%u,\"graph_remaining\":%u,\"plan\":[",
  h713_owner_arm,owner_step,(unsigned)OWNER_STEPS,owner_attempted,owner_failed,owner_timeout,owner_claimed,owner_terminal,owner_requests,owner_ctl,owner_cfg,graph_written);
 for (i = 0; i < OWNER_STEPS; i++)
  n += scnprintf(buf+n,PAGE_SIZE-n,"%s%u",i ? "," : "",owner_plan[i].op * 16 + owner_plan[i].arg);
 n += scnprintf(buf+n,PAGE_SIZE-n,"],\"pairs\":[");
 for (i = 0; i < OWNER_PAIRS; i++)
  n += scnprintf(buf+n,PAGE_SIZE-n,"%s{\"raw\":[%u,%u],\"outcome\":[%u,%u],\"phase\":[%u,%u],\"sent\":[%u,%u],\"status\":[%u,%u]}",i ? "," : "",owner_raw[i][0],owner_raw[i][1],owner_outcome[i][0],owner_outcome[i][1],owner_phase[i][0],owner_phase[i][1],owner_sent[i][0],owner_sent[i][1],owner_status[i][0],owner_status[i][1]);
 n += scnprintf(buf+n,PAGE_SIZE-n,"],\"graph_saved\":[");
 for (i = 0; i < ARRAY_SIZE(graph_saved); i++)
  n += scnprintf(buf+n,PAGE_SIZE-n,"%s%u",i ? "," : "",graph_saved[i]);
 n += scnprintf(buf+n,PAGE_SIZE-n,"]");
 n += h713_owner_context(buf+n,PAGE_SIZE-n);
 n += scnprintf(buf+n,PAGE_SIZE-n,"}\n");
 mutex_unlock(&owner_mutex);
 return n;
}
static const struct kernel_param_ops owner_step_ops = {.set=owner_step_set};
static const struct kernel_param_ops owner_state_ops = {.get=owner_state_get};
module_param_cb(owner_step,&owner_step_ops,NULL,0200);
module_param_cb(owner_state,&owner_state_ops,NULL,0400);
