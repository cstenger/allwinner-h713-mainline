/* Host rig: just enough of hantro.h for rockchip_av1_entropymode.c. */
#include "sunxi_h713_av1_compat.h"
#include "rockchip_av1_entropymode.h"
struct hantro_av1_dec_hw_ctx {
	struct av1cdfs *cdfs;
	struct mvcdfs *cdfs_ndvc;
	struct av1cdfs cdfs_last[NUM_REF_FRAMES];
	struct mvcdfs cdfs_last_ndvc[NUM_REF_FRAMES];
};
struct hantro_ctx { struct hantro_av1_dec_hw_ctx av1_dec; };
