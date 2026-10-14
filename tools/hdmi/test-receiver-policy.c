/* Native test of the actual parked/client release policy; no hardware access. */
#include <stdbool.h>
#include <assert.h>
#include <stdio.h>
#include "../../modules/hdmi-receiver/h713-receiver-policy.h"
int main(void)
{
 for (unsigned status=0; status<4; status++)
  for (unsigned clients=0; clients<3; clients++)
   assert(h713_receiver_release_allowed(status,clients) == (status==0 && clients==0));
 assert(!h713_receiver_release_allowed(~0U,0));
 assert(!h713_receiver_release_allowed(0,1000));
 for (unsigned current=0;current<6;current++)
  for (unsigned next=0;next<6;next++)
   assert(h713_receiver_clock_step_allowed(current,next) ==
          (current<=4 && next<=4 && (next==current || next==current+1)));
 for (unsigned status=0;status<4;status++)
  for (unsigned clients=0;clients<3;clients++)
   for (unsigned ready=0;ready<2;ready++)
    for (unsigned accepting=0;accepting<2;accepting++)
     for (int error=-1;error<=1;error++)
      assert(h713_receiver_park_allowed(status,clients,ready,accepting,error)==
             (status==1 && clients==0 && ready && accepting && !error));
 assert(!h713_receiver_park_allowed(~0U,0,true,true,0));
 puts("PASS: firmware-active, unknown status and active-client release blocked; only parked/no-client release allowed");
}
