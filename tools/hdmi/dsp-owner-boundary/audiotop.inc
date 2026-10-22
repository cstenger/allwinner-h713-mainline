/* SPDX-License-Identifier: GPL-2.0-only */
extern unsigned h713_owner_arm;
static void __iomem *owner_rccu,*owner_ppu,*owner_mips;
static int h713_owner_init_check(void)
{
 struct device_node *chosen = of_find_node_by_path("/chosen");
 u32 marker = 0;
 int ret;
 if (!chosen) return -EPERM;
 ret = of_property_read_u32(chosen,"h713,dsp-owner-boundary-v1",&marker);
 of_node_put(chosen);
 return ret || marker != 0x4f574e31 || h713_owner_arm < 1 || h713_owner_arm > 2 ? -EPERM : 0;
}
int h713_owner_health(u32 *ctl,u32 *cfg)
{
 if (!audio_top_initialized || !graph_ready || period_active || !owner_rccu || !owner_ppu || !owner_mips)
  return -EPERM;
 if ((readl(owner_rccu) & 0x10001) != 0x10001) return -EIO;
 if ((readl(owner_ppu) & 0x30008) != 0x10000 ||
     (readl(owner_ppu + 0x80) & 0x30008) != 0x10000 || readl(owner_mips) != 1)
  return -EIO;
 *ctl = readl(audio_top); *cfg = readl(audio_top + 0xc);
 return 0;
}
int h713_owner_audiotop(unsigned operation)
{
 u32 ctl,cfg;
 int ret = h713_owner_health(&ctl,&cfg);
 if (ret) return ret;
 if (operation == 1) {
  if (ctl != 0x700 || cfg != 0x011a5e00) return -EPERM;
  writel(0,audio_top + 0xc);
  return readl(audio_top + 0xc) == 0 ? 0 : -EIO;
 }
 if (cfg != 0) return -EPERM;
 if (operation == 2) {
  if (ctl != 0x700) return -EPERM;
  writel(0,audio_top);
  return readl(audio_top) == 0 ? 0 : -EIO;
 }
 if (operation == 3) {
  if (ctl != 0) return -EPERM;
  writel(0x700,audio_top);
  return readl(audio_top) == 0x700 ? 0 : -EIO;
 }
 return -EINVAL;
}
static int h713_owner_pin(void)
{
 owner_rccu = ioremap(0x070101ac,4);
 owner_ppu = ioremap(0x070010a4,0x84);
 owner_mips = ioremap(0x0306101c,4);
 if (!owner_rccu || !owner_ppu || !owner_mips) {
  iounmap(owner_rccu); iounmap(owner_ppu); iounmap(owner_mips);
  owner_rccu = owner_ppu = owner_mips = NULL;
  return -ENOMEM;
 }
 /* No userspace PCM exists in this build. Stop IRQ handlers before any
  * experimental AudioTop gate change; both arms share this intervention. */
 disable_irq(audif_irq);
 disable_irq(audbrg_irq);
 __module_get(THIS_MODULE);
 return 0;
}
