/* SPDX-License-Identifier: GPL-2.0-only */
/* Public kobject/module APIs only. No private addresses or kallsyms lookup.
 * kset_find_obj pins the embedded module kobject. mod_sysfs_teardown waits
 * for those references before freeing struct module. try_module_get is
 * therefore safe even while a concurrent unload attempts teardown.
 */
#ifndef SCPS_OWNER_H
#define SCPS_OWNER_H
static struct module *scps_get_owner(void)
{
 struct kobject *object;
 struct module *owner;
 object=kset_find_obj(THIS_MODULE->mkobj.kobj.kset,"h713_hdmi_signal");
 if(!object) return NULL;
 owner=container_of(object,struct module_kobject,kobj)->mod;
 if(!owner || READ_ONCE(owner->state)!=MODULE_STATE_LIVE || !try_module_get(owner)) owner=NULL;
 kobject_put(object);
 return owner;
}
static int scps_owner_bool(struct module *owner,const char *name,int wanted)
{
 unsigned int i;
 char value[8];
 for(i=0;i<owner->num_kp;i++) {
  const struct kernel_param *p=&owner->kp[i];
  if(!strcmp(p->name,name)) {
   if(p->ops!=&param_ops_bool || !p->ops->get || p->ops->get(value,p)<1) return 0;
   return value[0]==(wanted?'Y':'N');
  }
 }
 return 0;
}
/* The caller stays the owner of this mutex until an explicit later release.
 * Holding it on success preserves the bad state even if a stop is queued.
 * On ambiguous failure it is never automatically released.
 */
static int scps_run_owned(struct module *owner,struct scps_io *io,struct scps_receipt *r)
{
 int ret;
 kernel_param_lock(owner);
 if(!scps_owner_bool(owner,"ready",1) || !scps_owner_bool(owner,"failed",0) ||
    !scps_owner_bool(owner,"restored",0)) {
  r->reason=11; r->phase=SCPS_REJECTED; r->touched=0;
  kernel_param_unlock(owner); return -1;
 }
 ret=scps_capture(io,r);
 if(ret<0) kernel_param_unlock(owner);
 return ret;
}
#endif
