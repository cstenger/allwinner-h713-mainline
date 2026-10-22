/* SPDX-License-Identifier: GPL-2.0-only */
/* Phase A teardown bench, PCM translation unit. Restores only values this
 * sole owner saved during normal setup, in normal release_resources()
 * order. No route restore, W1C clear, flush pulse, IRQ free or DMA free.
 * Both arms perform identical reads; only arm 2 writes. */
extern unsigned h713_owner_arm;
int h713_owner_health(u32 *ctl,u32 *cfg);
int h713_owner_census(void);
int h713_owner_spdi(void);
int h713_owner_bridge(void);
int h713_owner_audiotop(unsigned operation);
int h713_owner_context(char *buf,int size);
static void __iomem *owner_rccu,*owner_ppu,*owner_mips;
/* Census (step 1) and post-operation readbacks of the 12 teardown words:
 * SPDI1 CTL0, CTL1, AudIf mask, bridge mask, global enable, stream
 * START/END/BLOCK/CONFIG/FLUSH, STREAM_SYNC, address-high. */
#define OWNER_WORDS 12
static u32 owner_census[OWNER_WORDS],owner_after_spdi[OWNER_WORDS],owner_after_bridge[OWNER_WORDS];
static bool owner_census_done,owner_spdi_seen,owner_bridge_seen;
static bool owner_spdi_applied,owner_bridge_applied;
static unsigned owner_spdi_writes,owner_bridge_writes,owner_at_writes;
static unsigned owner_census_stage,owner_census_flags;

static int h713_owner_init_check(void)
{
 struct device_node *chosen = of_find_node_by_path("/chosen");
 u32 marker = 0;
 int ret;
 if (!chosen) return -EPERM;
 ret = of_property_read_u32(chosen,"h713,dsp-teardown-a-v1",&marker);
 of_node_put(chosen);
 return ret || marker != 0x54445241 || h713_owner_arm < 1 || h713_owner_arm > 2 ? -EPERM : 0;
}
int h713_owner_health(u32 *ctl,u32 *cfg)
{
 if (!audio_top_initialized || !graph_ready || period_active || capture_card ||
     !owner_rccu || !owner_ppu || !owner_mips)
  return -EPERM;
 if ((readl(owner_rccu) & 0x10001) != 0x10001) return -EIO;
 if ((readl(owner_ppu) & 0x30008) != 0x10000 ||
     (readl(owner_ppu + 0x80) & 0x30008) != 0x10000 || readl(owner_mips) != 1)
  return -EIO;
 *ctl = readl(audio_top); *cfg = readl(audio_top + 0xc);
 return 0;
}
/* AudIf/bridge reads only while AudioTop control is on. */
static int owner_read_words(u32 *w)
{
 u32 ctl,cfg;
 int ret = h713_owner_health(&ctl,&cfg);
 if (ret) return ret;
 if (ctl != 0x700) return -EPERM;
 w[0] = readl(audif + AUDIF_SPDI1_CTL0);
 w[1] = readl(audif + AUDIF_SPDI1_CTL1);
 w[2] = readl(audif + AUDIF_IRQ_MASK);
 w[3] = readl(audbrg + AUDBRG_IRQ_MASK);
 w[4] = readl(audbrg + AUDBRG_GLOBAL_IRQ_EN);
 w[5] = readl(audbrg + AUDBRG_OSTREAM0 + AUDBRG_STREAM_START);
 w[6] = readl(audbrg + AUDBRG_OSTREAM0 + AUDBRG_STREAM_END);
 w[7] = readl(audbrg + AUDBRG_OSTREAM0 + AUDBRG_STREAM_BLOCK);
 w[8] = readl(audbrg + AUDBRG_OSTREAM0 + AUDBRG_STREAM_CONFIG);
 w[9] = readl(audbrg + AUDBRG_OSTREAM0 + AUDBRG_STREAM_FLUSH);
 w[10] = readl(audbrg + AUDBRG_STREAM_SYNC);
 w[11] = readl(audbrg_addr_hi);
 return 0;
}
/* Normal setup leaves stage 3: SPDI1 open with input disabled, bridge
 * stream inert, period IRQ masked, global enable set, no PCM. */
static int owner_census_valid(const u32 *w)
{
 u32 dma = (u32)audbrg_dma_addr;
 if (!spdi1_opened || !spdi1_activated || !audif_irq_requested ||
     !audbrg_configured || audbrg_stage_applied != 3 || !audbrg_irq_requested ||
     pcm_running || period_active || capture_card || !audbrg_dma_area ||
     upper_32_bits(audbrg_dma_addr) || (dma & 0xf))
  return -EPERM;
 if (audio_top_saved_ctl || audio_top_saved_cfg) return -EPERM;
 if (w[0] != 0 || w[1] != 0x00003000 || w[2] != (audif_saved_mask | AUDIF_SPDI1_W1C))
  return -EIO;
 if (w[3] != audbrg_saved_irq_mask ||
     w[4] != (audbrg_saved_global_irq_en | AUDBRG_GLOBAL_IRQ_BIT) ||
     w[5] != ((dma >> 4) & 0x00ffffff) ||
     w[6] != (((dma + AUDBRG_DMA_SIZE - 1) >> 4) & 0x00ffffff) ||
     w[7] != (AUDBRG_DMA_BLOCK >> 4) || w[8] != AUDBRG_OSTREAM0_CONFIG ||
     w[9] != audbrg_saved_stream[4] || w[10] != 0 ||
     (w[11] & AUDBRG_ADDR_HI_MASK) != ((dma >> 28) << 4))
  return -EIO;
 return 0;
}
static int owner_same(const u32 *a,const u32 *b,unsigned first,unsigned count)
{
 unsigned i;
 for (i = first; i < first + count; i++) if (a[i] != b[i]) return -EIO;
 return 0;
}
int h713_owner_census(void)
{
 int ret;
 if (owner_census_done) return -EPERM;
 ret = owner_read_words(owner_census);
 if (ret) return ret;
 owner_census_stage = audbrg_stage_applied;
 owner_census_flags = spdi1_opened | spdi1_activated << 1 | audif_irq_requested << 2 |
  audbrg_configured << 3 | audbrg_irq_requested << 4;
 ret = owner_census_valid(owner_census);
 if (ret) return ret;
 owner_census_done = true;
 return 0;
}
/* Exact normal order: CTL0, CTL1, posting read, mask, posting read. */
int h713_owner_spdi(void)
{
 u32 now[OWNER_WORDS];
 int ret;
 if (!owner_census_done || owner_spdi_seen || owner_bridge_seen) return -EPERM;
 ret = owner_read_words(now);
 if (ret) return ret;
 if (owner_same(now,owner_census,0,OWNER_WORDS)) return -EIO;
 owner_spdi_seen = true;
 if (h713_owner_arm == 2) {
  if (!spdi1_activated || !spdi1_opened) return -EPERM;
  writel(spdi1_saved_ctl0,audif + AUDIF_SPDI1_CTL0); owner_spdi_writes++;
  writel(spdi1_saved_ctl1,audif + AUDIF_SPDI1_CTL1); owner_spdi_writes++;
  readl(audif + AUDIF_SPDI1_CTL1);
  writel(audif_saved_mask,audif + AUDIF_IRQ_MASK); owner_spdi_writes++;
  readl(audif + AUDIF_IRQ_MASK);
  owner_spdi_applied = true;
  pr_notice("H713 TEARDOWN spdi-restore ctl0=%08x ctl1=%08x mask=%08x written\n",
   spdi1_saved_ctl0,spdi1_saved_ctl1,audif_saved_mask);
 }
 ret = owner_read_words(owner_after_spdi);
 if (ret) return ret;
 if (h713_owner_arm == 2) {
  if (owner_after_spdi[0] != spdi1_saved_ctl0 || owner_after_spdi[1] != spdi1_saved_ctl1 ||
      owner_after_spdi[2] != audif_saved_mask || owner_same(owner_after_spdi,owner_census,3,9))
   return -EIO;
 } else if (owner_same(owner_after_spdi,owner_census,0,OWNER_WORDS)) return -EIO;
 return 0;
}
/* Exact normal order: mask, global enable, posting read, then stream
 * START/END/BLOCK/CONFIG/FLUSH, STREAM_SYNC, address-high, posting read.
 * Stage 3 only: the stage-4 flush pulse is never added. */
int h713_owner_bridge(void)
{
 u32 now[OWNER_WORDS];
 int ret;
 if (!owner_spdi_seen || owner_bridge_seen) return -EPERM;
 ret = owner_read_words(now);
 if (ret) return ret;
 if (owner_same(now,owner_after_spdi,0,OWNER_WORDS)) return -EIO;
 owner_bridge_seen = true;
 if (h713_owner_arm == 2) {
  if (!owner_spdi_applied || !audbrg_configured || audbrg_stage_applied != 3) return -EPERM;
  writel(audbrg_saved_irq_mask,audbrg + AUDBRG_IRQ_MASK); owner_bridge_writes++;
  writel(audbrg_saved_global_irq_en,audbrg + AUDBRG_GLOBAL_IRQ_EN); owner_bridge_writes++;
  readl(audbrg + AUDBRG_GLOBAL_IRQ_EN);
  writel(audbrg_saved_stream[0],audbrg + AUDBRG_OSTREAM0 + AUDBRG_STREAM_START); owner_bridge_writes++;
  writel(audbrg_saved_stream[1],audbrg + AUDBRG_OSTREAM0 + AUDBRG_STREAM_END); owner_bridge_writes++;
  writel(audbrg_saved_stream[2],audbrg + AUDBRG_OSTREAM0 + AUDBRG_STREAM_BLOCK); owner_bridge_writes++;
  writel(audbrg_saved_stream[3],audbrg + AUDBRG_OSTREAM0 + AUDBRG_STREAM_CONFIG); owner_bridge_writes++;
  writel(audbrg_saved_stream[4],audbrg + AUDBRG_OSTREAM0 + AUDBRG_STREAM_FLUSH); owner_bridge_writes++;
  writel(audbrg_saved_stream_sync,audbrg + AUDBRG_STREAM_SYNC); owner_bridge_writes++;
  writel(audbrg_saved_addr_hi,audbrg_addr_hi); owner_bridge_writes++;
  readl(audbrg_addr_hi);
  owner_bridge_applied = true;
  pr_notice("H713 TEARDOWN bridge-restore mask=%08x global=%08x stream=%08x/%08x/%08x/%08x/%08x sync=%08x addr_hi=%08x written\n",
   audbrg_saved_irq_mask,audbrg_saved_global_irq_en,audbrg_saved_stream[0],audbrg_saved_stream[1],
   audbrg_saved_stream[2],audbrg_saved_stream[3],audbrg_saved_stream[4],audbrg_saved_stream_sync,audbrg_saved_addr_hi);
 }
 ret = owner_read_words(owner_after_bridge);
 if (ret) return ret;
 if (h713_owner_arm == 2) {
  if (owner_same(owner_after_bridge,owner_after_spdi,0,3) ||
      owner_after_bridge[3] != audbrg_saved_irq_mask || owner_after_bridge[4] != audbrg_saved_global_irq_en ||
      owner_after_bridge[5] != audbrg_saved_stream[0] || owner_after_bridge[6] != audbrg_saved_stream[1] ||
      owner_after_bridge[7] != audbrg_saved_stream[2] || owner_after_bridge[8] != audbrg_saved_stream[3] ||
      owner_after_bridge[9] != audbrg_saved_stream[4] || owner_after_bridge[10] != audbrg_saved_stream_sync ||
      owner_after_bridge[11] != audbrg_saved_addr_hi)
   return -EIO;
 } else if (owner_same(owner_after_bridge,owner_after_spdi,0,OWNER_WORDS)) return -EIO;
 return 0;
}
/* Normal AudioTop restore writes saved config then saved control (both
 * zero by init check); control 700 then restores access. Arm 2 only. */
int h713_owner_audiotop(unsigned operation)
{
 u32 ctl,cfg;
 int ret = h713_owner_health(&ctl,&cfg);
 if (ret) return ret;
 if (!owner_bridge_seen || (h713_owner_arm == 2 && !owner_bridge_applied)) return -EPERM;
 if (operation == 1) {
  if (ctl != 0x700 || cfg != 0x011a5e00) return -EPERM;
  writel(audio_top_saved_cfg,audio_top + 0xc); owner_at_writes++;
  return readl(audio_top + 0xc) == audio_top_saved_cfg ? 0 : -EIO;
 }
 if (cfg != audio_top_saved_cfg) return -EPERM;
 if (operation == 2) {
  if (ctl != 0x700) return -EPERM;
  writel(audio_top_saved_ctl,audio_top); owner_at_writes++;
  return readl(audio_top) == audio_top_saved_ctl ? 0 : -EIO;
 }
 if (operation == 3) {
  if (ctl != audio_top_saved_ctl) return -EPERM;
  writel(0x700,audio_top); owner_at_writes++;
  return readl(audio_top) == 0x700 ? 0 : -EIO;
 }
 return -EINVAL;
}
static int owner_words_json(char *buf,int size,const char *name,const u32 *w,bool seen)
{
 unsigned i;
 int n = scnprintf(buf,size,",\"%s\":",name);
 if (!seen) return n + scnprintf(buf+n,size-n,"null");
 for (i = 0; i < OWNER_WORDS; i++)
  n += scnprintf(buf+n,size-n,"%s%u",i ? "," : "[",w[i]);
 return n + scnprintf(buf+n,size-n,"]");
}
/* Cached values only: never touches MMIO, safe while control is off. */
int h713_owner_context(char *buf,int size)
{
 int n = scnprintf(buf,size,",\"ctx\":{\"saved\":[%u,%u,%u,%u,%u,%u,%u,%u,%u,%u,%u,%u],\"saved_route\":%u,\"at_saved\":[%u,%u],\"dma\":%u,\"census_stage\":%u,\"census_flags\":%u,\"spdi_applied\":%u,\"bridge_applied\":%u,\"spdi_writes\":%u,\"bridge_writes\":%u,\"at_writes\":%u",
  spdi1_saved_ctl0,spdi1_saved_ctl1,audif_saved_mask,audbrg_saved_irq_mask,audbrg_saved_global_irq_en,
  audbrg_saved_stream[0],audbrg_saved_stream[1],audbrg_saved_stream[2],audbrg_saved_stream[3],audbrg_saved_stream[4],
  audbrg_saved_stream_sync,audbrg_saved_addr_hi,audif_saved_route,audio_top_saved_ctl,audio_top_saved_cfg,
  (u32)audbrg_dma_addr,owner_census_stage,owner_census_flags,owner_spdi_applied,owner_bridge_applied,
  owner_spdi_writes,owner_bridge_writes,owner_at_writes);
 n += owner_words_json(buf+n,size-n,"census",owner_census,owner_census_done);
 n += owner_words_json(buf+n,size-n,"after_spdi",owner_after_spdi,owner_spdi_seen);
 n += owner_words_json(buf+n,size-n,"after_bridge",owner_after_bridge,owner_bridge_seen);
 return n + scnprintf(buf+n,size-n,"}");
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
  * experimental write; IRQ objects, mappings and DMA stay allocated. */
 disable_irq(audif_irq);
 disable_irq(audbrg_irq);
 __module_get(THIS_MODULE);
 return 0;
}
