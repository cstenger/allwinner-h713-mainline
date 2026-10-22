/* SPDX-License-Identifier: GPL-2.0-only */
/* Pure predicate: retaining an existing ON domain never powers it on. */
static bool h713_retention_eligible(bool requested, bool trace, u32 gate,
				    u32 gp6, u32 mips, u32 scp,
				    u32 tvfe, u32 tvcap)
{
	return requested && trace && (gate & 0x10001) == 0x10001 &&
		gp6 == 0x48444d49 && mips == 0 && !(scp & 1) &&
		(tvfe & 0x30008) == 0x10000 &&
		(tvcap & 0x30008) == 0x10000;
}
