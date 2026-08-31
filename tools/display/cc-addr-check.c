// SPDX-License-Identifier: GPL-2.0
/*
 * Bench check for the cc_ref() physical-reference conversion.
 *
 * cpu_comm registers two driver-private arenas and publishes
 * virt_to_phys(base) as the MIPS-visible address:
 *
 *   arena 0 = s_CommSockt    — a module-global array (module .bss)
 *   arena 1 = pcpu_comm_dev  — kzalloc(119648)
 *
 * On arm64 a module lives in the vmalloc region, not the linear map, so
 * virt_to_phys() takes its __kimg_to_phys() branch and returns an
 * arithmetic result that is not the address of that data. This module
 * reproduces both allocations and prints virt_to_phys() beside the true
 * physical address from a page-table walk, plus the physical addresses
 * of successive pages so contiguity can be seen rather than assumed.
 */

#include <linux/init.h>
#include <linux/kernel.h>
#include <linux/mm.h>
#include <linux/module.h>
#include <linux/slab.h>
#include <linux/vmalloc.h>

/* Same size and storage class as cpu_comm's s_CommSockt (2 * 4992). */
static u32 bss_like_s_commsockt[2 * (4992 / 4)];

static phys_addr_t true_phys(const void *p)
{
	unsigned long v = (unsigned long)p;

	if (is_vmalloc_or_module_addr(p)) {
		struct page *pg = vmalloc_to_page(p);

		if (!pg)
			return 0;
		return page_to_phys(pg) + offset_in_page(v);
	}
	return virt_to_phys(p);
}

static void report(const char *name, const void *base, size_t size)
{
	phys_addr_t claimed = virt_to_phys(base);
	phys_addr_t actual = true_phys(base);
	unsigned int i;

	pr_info("cc-addr-check: %s\n", name);
	pr_info("cc-addr-check:   va               = 0x%lx\n",
		(unsigned long)base);
	pr_info("cc-addr-check:   vmalloc/module   = %s\n",
		is_vmalloc_or_module_addr(base) ? "yes" : "no");
	pr_info("cc-addr-check:   virt_to_phys()   = 0x%llx  <- what cc_ref publishes\n",
		(unsigned long long)claimed);
	pr_info("cc-addr-check:   page-walk phys   = 0x%llx  <- where the data really is\n",
		(unsigned long long)actual);
	pr_info("cc-addr-check:   VERDICT          = %s\n",
		claimed == actual ? "MATCH" : "*** MISMATCH ***");

	/* base + offset arithmetic is only valid if the pages are contiguous */
	for (i = 0; i < size / PAGE_SIZE && i < 4; i++) {
		const void *p = (const u8 *)base + (size_t)i * PAGE_SIZE;

		pr_info("cc-addr-check:   page %u: va+0x%lx -> phys 0x%llx\n",
			i, (unsigned long)i * PAGE_SIZE,
			(unsigned long long)true_phys(p));
	}
}

static int __init cc_addr_check_init(void)
{
	void *kz;

	pr_info("cc-addr-check: PAGE_OFFSET=0x%lx  module_va=0x%lx\n",
		(unsigned long)PAGE_OFFSET,
		(unsigned long)bss_like_s_commsockt);

	report("arena 0 shape: module-global array (as s_CommSockt)",
	       bss_like_s_commsockt, sizeof(bss_like_s_commsockt));

	kz = kzalloc(2 * 4992, GFP_KERNEL);
	if (kz) {
		report("arena 0 FIXED: kzalloc(9984) (as s_CommSockt now)",
		       kz, 2 * 4992);
		kfree(kz);
	}

	kz = kzalloc(119648, GFP_KERNEL);
	if (kz) {
		report("arena 1 shape: kzalloc(119648) (as pcpu_comm_dev)",
		       kz, 119648);
		kfree(kz);
	}

	return -EAGAIN; /* report and unload; nothing to leave behind */
}

module_init(cc_addr_check_init);

MODULE_DESCRIPTION("Bench check for cpu_comm cc_ref physical translation");
MODULE_LICENSE("GPL");
