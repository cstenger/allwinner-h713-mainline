/* Bench-only: observe an already-ON warm domain, never command it ON. */
#include "h713-retention-policy.h"
static bool h713_tvfe_retain_requested;
static bool h713_tvfe_retain_eligible;
static bool h713_tvfe_retain_applied;
static bool h713_tvfe_retain_violated;

static int __init h713_tvfe_retain_setup(char *value)
{
	if (!value || strcmp(value, "1"))
		return -EINVAL;
	h713_tvfe_retain_requested = true;
	return 0;
}
early_param("h713_tvfe_retain", h713_tvfe_retain_setup);

static void __init h713_tvfe_retain_check(void)
{
	void __iomem *gp6, *mips, *scp;
	u32 gate;

	if (!h713_tvfe_retain_requested)
		return;
	if (!h713_tvfe_trace_enabled || !h713_tvfe_trace_r_ccu ||
	    !h713_tvfe_trace_ppu)
		goto refused;
	gate = readl(h713_tvfe_trace_r_ccu + 0x1ac);
	if ((gate & 0x10001) != 0x10001)
		goto refused;
	gp6 = ioremap(0x07090118, 4);
	mips = ioremap(0x0306101c, 4);
	scp = ioremap(0x07000400, 4);
	if (gp6 && mips && scp)
		h713_tvfe_retain_eligible = h713_retention_eligible(true, true, gate,
			readl(gp6), readl(mips), readl(scp),
			readl(h713_tvfe_trace_ppu + 0xa4),
			readl(h713_tvfe_trace_ppu + 0x124));
	iounmap(gp6);
	iounmap(mips);
	iounmap(scp);
	if (h713_tvfe_retain_eligible) {
		pr_notice("H713 RETENTION eligible=1; warm domains initially ON; no power command\n");
		return;
	}
refused:
	pr_err("H713 RETENTION eligible=0; observation refused; no power command\n");
}
