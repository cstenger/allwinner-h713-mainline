#include <stdbool.h>
#include <assert.h>
#include <stdio.h>
#include "../../modules/scp-probe/h713-scp-hold.h"

int main(void)
{
	assert(!h713_scp_hold_valid(0, false));
	assert(!h713_scp_hold_valid(999, true));
	assert(h713_scp_hold_valid(1000, false));
	assert(h713_scp_hold_valid(150000, false));
	assert(!h713_scp_hold_valid(150001, false));
	assert(h713_scp_hold_valid(150001, true));
	assert(h713_scp_hold_valid(3660000, true));
	assert(!h713_scp_hold_valid(3660000, false));
	assert(!h713_scp_hold_valid(3660001, true));
	assert(!h713_scp_hold_valid(~0U, true));
	puts("PASS: ordinary150-second limit preserved; explicit endurance opt-in bounded to3660 seconds");
	return 0;
}
