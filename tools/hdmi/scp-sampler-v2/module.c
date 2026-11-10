// SPDX-License-Identifier: GPL-2.0-only
/* Temporary, one-shot diagnostic companion. No receiver MMIO mapping,
 * peripheral writes, reset mapping, clock operation or automatic release.
 */
#include <linux/delay.h>
#include <linux/io.h>
#include <linux/kobject.h>
#include <linux/kthread.h>
#include <linux/module.h>
#include <linux/of.h>
#include <linux/slab.h>
#include "core.h"
#include "owner.h"
#ifdef CONFIG_MODULE_FORCE_UNLOAD
#error "diagnostic retention requires forced module unload disabled"
#endif
static struct module *owner;
static void __iomem *sram;
static struct scps_receipt receipt;
static int status, reason;
static unsigned int sr, values[14];
static unsigned int bootstrap_sr,original_r13;
static unsigned int num_values=14;
static bool used, loaded, release_requested;
module_param(status,int,0444);
module_param(reason,int,0444);
module_param(sr,uint,0444);
module_param(bootstrap_sr,uint,0444);
module_param(original_r13,uint,0444);
module_param_array(values,uint,&num_values,0444);
static unsigned int io_read(void *unused,unsigned int off)
{ if(off&3 || off>=0x5000) return ~0u; return readl(sram+off); }
static int io_write(void *unused,unsigned int off,unsigned int value)
{ if(!scps_writable(off)) return -EINVAL; writel(value,sram+off); return 0; }
static void io_fence(void *unused) { wmb(); }
static void io_wait(void *unused) { usleep_range(1000,1500); }
static void io_phase(void *unused,unsigned int phase)
{ if(phase!=SCPS_CAPTURED_HELD && phase!=SCPS_REJECTED && phase!=SCPS_FROZEN) WRITE_ONCE(status,phase); }
static int capture_worker(void *unused)
{
 struct scps_io io={NULL,io_read,io_write,io_fence,io_wait,io_phase};
 int ret;
 /* Map only SRAM; the existing pinned owner reserves this exact region. */
 sram=ioremap(0x00100000,0x5000);
 if(!sram) { reason=12; status=SCPS_REJECTED; module_put_and_kthread_exit(0); }
 ret=scps_run_owned(owner,&io,&receipt);
 WRITE_ONCE(reason,receipt.reason); WRITE_ONCE(sr,receipt.sr);
 WRITE_ONCE(bootstrap_sr,receipt.bootstrap_sr);WRITE_ONCE(original_r13,receipt.original_r13);
 if(!ret) memcpy(values,receipt.values,sizeof(values));
 smp_store_release(&status,receipt.phase);
 if(ret<0) module_put_and_kthread_exit(0);
 /* Both successful capture and ambiguity retain the owner lock and our ref.
  * Our own status parameters stay readable. Owner parameter reads will block.
  * No module removal/timeout automatically unblocks a queued owner stop.
  */
 for(;;) {
  if(!ret && READ_ONCE(release_requested)) {
   if(!scps_release_guard(&io,&receipt)) break;
   ret=1; WRITE_ONCE(reason,receipt.reason);
   smp_store_release(&status,SCPS_FROZEN);
  }
  msleep(100);
 }
 kernel_param_unlock(owner);
 WRITE_ONCE(status,SCPS_RELEASED);
 module_put_and_kthread_exit(0);
}
static int capture_set(const char *value,const struct kernel_param *p)
{
 unsigned int nonce;
 struct task_struct *task;
 if(!loaded || READ_ONCE(THIS_MODULE->state)!=MODULE_STATE_LIVE) return -EAGAIN;
 if(kstrtouint(value,0,&nonce) || nonce!=SCPS_NONCE) return -EINVAL;
 if(used) return -EALREADY;
 used=true; __module_get(THIS_MODULE);
 task=kthread_run(capture_worker,NULL,"h713-scp-sample");
 if(IS_ERR(task)) { status=SCPS_REJECTED; reason=13; module_put(THIS_MODULE); return PTR_ERR(task); }
 return 0;
}
static int release_set(const char *value,const struct kernel_param *p)
{
 unsigned int nonce;
 if(kstrtouint(value,0,&nonce) || nonce!=SCPS_NONCE) return -EINVAL;
 if(READ_ONCE(status)!=SCPS_CAPTURED_HELD) return -EPERM;
 /* Explicit later permission to end state preservation is mandatory:
  * this may unblock an independently queued stop request. No automatic call.
  */
 WRITE_ONCE(release_requested,true); return 0;
}
static const struct kernel_param_ops capture_ops={.set=capture_set};
static const struct kernel_param_ops release_ops={.set=release_set};
static int result_get(char *buffer,const struct kernel_param *p)
{
 int state=smp_load_acquire(&status),len,i;
 if(state!=SCPS_CAPTURED_HELD && state!=SCPS_RELEASED) return -EAGAIN;
 len=scnprintf(buffer,PAGE_SIZE,"%u %d %u %u",SCPS_NONCE,state,reason,sr);
 for(i=0;i<14;i++) len+=scnprintf(buffer+len,PAGE_SIZE-len," %u",values[i]);
 len+=scnprintf(buffer+len,PAGE_SIZE-len,"\n");
 return len;
}
static const struct kernel_param_ops result_ops={.get=result_get};
module_param_cb(capture,&capture_ops,NULL,0200);
module_param_cb(release,&release_ops,NULL,0200);
module_param_cb(result,&result_ops,NULL,0444);
static int __init sample_init(void)
{
 BUILD_BUG_ON(sizeof(struct module)!=1152);
 if(!of_machine_is_compatible("allwinner,sun50i-h713")) return -ENODEV;
 owner=scps_get_owner(); if(!owner) return -ENODEV;
 loaded=true; /* Loading is inert: no SRAM map or write until capture setter. */
 return 0;
}
static void __exit sample_exit(void)
{
 if(sram) iounmap(sram);
 if(owner) module_put(owner);
}
module_init(sample_init);
module_exit(sample_exit);
MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("H713 one-shot resident SCP sampler; explicit capture, held owner stop path");
