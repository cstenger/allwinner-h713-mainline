/* Bench instrumentation, enabled only by h713_tvfe_trace=1. */
static bool h713_tvfe_trace_enabled;
static void __iomem *h713_tvfe_trace_r_ccu;
static void __iomem *h713_tvfe_trace_ppu;

static int __init h713_tvfe_trace_setup(char *value)
{
	if (!value || strcmp(value, "1"))
		return -EINVAL;
	h713_tvfe_trace_enabled = true;
	return 0;
}
early_param("h713_tvfe_trace", h713_tvfe_trace_setup);

static void h713_tvfe_boot_trace(const char *stage)
{
	u32 gate, tvfe, tvcap;

	if (!h713_tvfe_trace_enabled || !h713_tvfe_trace_r_ccu ||
	    !h713_tvfe_trace_ppu)
		return;
	gate = readl(h713_tvfe_trace_r_ccu + 0x1ac);
	pr_info("H713 TVFE v1 stage=%s gate=%08x state=begin\n", stage, gate);
	if ((gate & (BIT(0) | BIT(16))) != (BIT(0) | BIT(16))) {
		pr_info("H713 TVFE v1 stage=%s gate=%08x state=skipped\n", stage, gate);
		return;
	}
	tvfe = readl(h713_tvfe_trace_ppu + 0xa4);
	tvcap = readl(h713_tvfe_trace_ppu + 0x124);
	pr_info("H713 TVFE v1 stage=%s gate=%08x state=sample tvfe=%08x tvcap=%08x\n",
		stage, gate, tvfe, tvcap);
}

static int __init h713_tvfe_trace_early(void)
{
	if (!h713_tvfe_trace_enabled)
		return 0;
	if (!of_machine_is_compatible("allwinner,sun50i-h713")) {
		pr_err("H713 TVFE trace: wrong machine; disabled\n");
		h713_tvfe_trace_enabled = false;
		return 0;
	}
	h713_tvfe_trace_r_ccu = ioremap(0x07010000, 0x1000);
	h713_tvfe_trace_ppu = ioremap(0x07001000, 0x400);
	if (!h713_tvfe_trace_r_ccu || !h713_tvfe_trace_ppu) {
		pr_err("H713 TVFE trace: map failed; disabled\n");
		iounmap(h713_tvfe_trace_r_ccu);
		iounmap(h713_tvfe_trace_ppu);
		h713_tvfe_trace_enabled = false;
		return 0;
	}
	/* Retain these read-only diagnostic mappings for later callbacks. */
	h713_tvfe_boot_trace("linux_early_initcall");
	return 0;
}
early_initcall(h713_tvfe_trace_early);
