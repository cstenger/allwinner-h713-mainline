/* SPDX-License-Identifier: GPL-2.0-only */
/* Phase B teardown bench, TVFE translation unit. Splits the normal
 * h713_hdmi_tvfe_release() into a clock-off edge and the demod reset,
 * keeping mappings, clk/reset references and saved values so access can be
 * reacquired in h713_hdmi_tvfe_prepare() order without relaunching MIPS.
 * Only CCU words (0x02001d10..0x02001d67) are read here. */
extern unsigned h713_owner_arm;
#define OWNER_TV_WORDS ARRAY_SIZE(functional_words)
enum { OWNER_TVS_ON, OWNER_TVS_CLOCKS_OFF, OWNER_TVS_RESET };
int h713_owner_tvfe_census(void);
int h713_owner_tvfe_check(void);
int h713_owner_tvfe_off(bool with_reset);
int h713_owner_tvfe_on(bool reset_round);
int h713_owner_tvfe_context(char *buf,int size);
static unsigned owner_tv_state = OWNER_TVS_ON;
static bool owner_tv_census_done, owner_tv_parent_dropped[ARRAY_SIZE(parents)];
static u32 owner_tv_census[ARRAY_SIZE(functional_words) + 1];
static u32 owner_tv_off_read[2][ARRAY_SIZE(functional_words) + 1];
static unsigned owner_tv_offs, owner_tv_ons, owner_tv_resets, owner_tv_writes;
static int owner_tv_parent_after_drop[ARRAY_SIZE(parents)] = {-1,-1};
static int owner_tv_reset_status_after = -2;

static u32 owner_tv_bus_expected(void)
{
 if (owner_tv_state == OWNER_TVS_ON) return bus_saved | BIT(16) | BIT(0);
 return owner_tv_state == OWNER_TVS_CLOCKS_OFF ? bus_saved | BIT(16) : bus_saved;
}
/* Every word must match the phase this bench put it in. */
int h713_owner_tvfe_check(void)
{
 unsigned i;
 if (!owner_tv_census_done || !ccu_tv) return -EPERM;
 for (i = 0; i < OWNER_TV_WORDS; i++)
  if (readl(ccu_tv + functional_words[i].offset) !=
      (owner_tv_state == OWNER_TVS_ON ? functional_words[i].stock : functional_words[i].saved))
   return -EIO;
 return readl(ccu_tv + 0x54) == owner_tv_bus_expected() ? 0 : -EIO;
}
/* Normal prepare leaves: reset deasserted, stock words, bus gate on. */
int h713_owner_tvfe_census(void)
{
 unsigned i;
 if (owner_tv_census_done || !tvfe_ready || !words_applied || !bus_enabled ||
     !reset_deasserted || !bus_saved_valid || IS_ERR_OR_NULL(demod_reset) || !ccu_tv ||
     (bus_saved & (BIT(16) | BIT(0))))
  return -EPERM;
 for (i = 0; i < ARRAY_SIZE(parents); i++)
  if (IS_ERR_OR_NULL(parents[i].clk)) return -EPERM;
 for (i = 0; i < OWNER_TV_WORDS; i++) owner_tv_census[i] = readl(ccu_tv + functional_words[i].offset);
 owner_tv_census[OWNER_TV_WORDS] = readl(ccu_tv + 0x54);
 if (reset_control_status(demod_reset) != 0) return -EIO;
 owner_tv_census_done = true;
 return h713_owner_tvfe_check();
}
/* Arm 2: normal release order without unmapping or putting references:
 * bus gate off with reset released, words reverse, parents dropped, then
 * (reset boundary only) shared reset asserted and saved bus restored.
 * Arm 1 reads and verifies only. */
int h713_owner_tvfe_off(bool with_reset)
{
 int i, ret = h713_owner_tvfe_check();
 if (ret) return ret;
 if (owner_tv_state != OWNER_TVS_ON) return -EPERM;
 if (h713_owner_arm != 2) return 0;
 owner_tv_offs++;
 writel(bus_saved | BIT(16),ccu_tv + 0x54); owner_tv_writes++;
 readl(ccu_tv + 0x54);
 bus_enabled = false;
 for (i = OWNER_TV_WORDS - 1; i >= 0; i--) {
  writel(functional_words[i].saved,ccu_tv + functional_words[i].offset); owner_tv_writes++;
  if (readl(ccu_tv + functional_words[i].offset) != functional_words[i].saved) return -EIO;
 }
 readl(ccu_tv + functional_words[0].offset);
 words_applied = false;
 for (i = ARRAY_SIZE(parents) - 1; i >= 0; i--) {
  if (parents[i].enabled_by_probe) {
   clk_disable_unprepare(parents[i].clk);
   parents[i].enabled_by_probe = false;
   owner_tv_parent_dropped[i] = true;
  }
  /* A receiver child hold can keep the parent running: report it. */
  owner_tv_parent_after_drop[i] = __clk_is_enabled(parents[i].clk);
 }
 owner_tv_state = OWNER_TVS_CLOCKS_OFF;
 if (with_reset) {
  owner_tv_resets++;
  ret = reset_control_assert(demod_reset);
  if (ret) return ret;
  reset_deasserted = false;
  owner_tv_reset_status_after = reset_control_status(demod_reset);
  /* Shared reset: another deasserted user would leave it released. */
  if (owner_tv_reset_status_after != 1 || (readl(ccu_tv + 0x54) & BIT(16))) return -EIO;
  writel(bus_saved,ccu_tv + 0x54); owner_tv_writes++;
  if (readl(ccu_tv + 0x54) != bus_saved) return -EIO;
  owner_tv_state = OWNER_TVS_RESET;
 }
 for (i = 0; i < OWNER_TV_WORDS; i++) owner_tv_off_read[with_reset][i] = readl(ccu_tv + functional_words[i].offset);
 owner_tv_off_read[with_reset][OWNER_TV_WORDS] = readl(ccu_tv + 0x54);
 return h713_owner_tvfe_check();
}
/* h713_hdmi_tvfe_prepare() order: reset deassert and settle, parents,
 * stock words forward, demod bus last, settle. The sham performs the same
 * stock-word and bus writes (identical values) so both arms share the
 * access-restoration transactions; it has nothing to deassert or enable. */
int h713_owner_tvfe_on(bool reset_round)
{
 unsigned i;
 int ret;
 if (!owner_tv_census_done) return -EPERM;
 if (h713_owner_arm != 2 && owner_tv_state != OWNER_TVS_ON) return -EPERM;
 if (h713_owner_arm == 2 && owner_tv_state != (reset_round ? OWNER_TVS_RESET : OWNER_TVS_CLOCKS_OFF)) return -EPERM;
 if (owner_tv_state == OWNER_TVS_RESET) {
  ret = reset_control_deassert(demod_reset);
  if (ret) return ret;
  reset_deasserted = true;
  if (reset_control_status(demod_reset) != 0) return -EIO;
 }
 if (reset_round) usleep_range(10000,15000);
 for (i = 0; i < ARRAY_SIZE(parents); i++) {
  if (!owner_tv_parent_dropped[i]) continue;
  ret = clk_prepare_enable(parents[i].clk);
  if (ret) return ret;
  parents[i].enabled_by_probe = true;
  owner_tv_parent_dropped[i] = false;
 }
 for (i = 0; i < OWNER_TV_WORDS; i++) {
  writel(functional_words[i].stock,ccu_tv + functional_words[i].offset); owner_tv_writes++;
  if (readl(ccu_tv + functional_words[i].offset) != functional_words[i].stock) return -EIO;
 }
 words_applied = true;
 writel(readl(ccu_tv + 0x54) | BIT(0),ccu_tv + 0x54); owner_tv_writes++;
 if ((readl(ccu_tv + 0x54) & (BIT(16) | BIT(0))) != (BIT(16) | BIT(0))) return -EIO;
 bus_enabled = true;
 owner_tv_state = OWNER_TVS_ON;
 if (h713_owner_arm == 2) owner_tv_ons++;
 usleep_range(10000,15000);
 return h713_owner_tvfe_check();
}
static int owner_tv_words_json(char *buf,int size,const char *name,const u32 *w,bool seen)
{
 unsigned i;
 int n = scnprintf(buf,size,",\"%s\":",name);
 if (!seen) return n + scnprintf(buf+n,size-n,"null");
 for (i = 0; i <= OWNER_TV_WORDS; i++) n += scnprintf(buf+n,size-n,"%s%u",i ? "," : "[",w[i]);
 return n + scnprintf(buf+n,size-n,"]");
}
/* Cached values only; never touches MMIO. */
int h713_owner_tvfe_context(char *buf,int size)
{
 unsigned i;
 int n = scnprintf(buf,size,",\"tv\":{\"state\":%u,\"bus_saved\":%u,\"offs\":%u,\"ons\":%u,\"resets\":%u,\"writes\":%u,\"reset_status_after\":%d,\"saved\":",
  owner_tv_state,bus_saved,owner_tv_offs,owner_tv_ons,owner_tv_resets,owner_tv_writes,owner_tv_reset_status_after);
 for (i = 0; i < OWNER_TV_WORDS; i++) n += scnprintf(buf+n,size-n,"%s%u",i ? "," : "[",functional_words[i].saved);
 n += scnprintf(buf+n,size-n,"],\"parents\":[");
 for (i = 0; i < ARRAY_SIZE(parents); i++)
  n += scnprintf(buf+n,size-n,"%s[%u,%u,%u,%d]",i ? "," : "",parents[i].inherited_on,
   parents[i].enabled_by_probe,owner_tv_parent_dropped[i],owner_tv_parent_after_drop[i]);
 n += scnprintf(buf+n,size-n,"]");
 n += owner_tv_words_json(buf+n,size-n,"census",owner_tv_census,owner_tv_census_done);
 n += owner_tv_words_json(buf+n,size-n,"off_clocks",owner_tv_off_read[0],owner_tv_offs > 0 && h713_owner_arm == 2);
 n += owner_tv_words_json(buf+n,size-n,"off_reset",owner_tv_off_read[1],owner_tv_resets > 0);
 return n + scnprintf(buf+n,size-n,"}");
}
