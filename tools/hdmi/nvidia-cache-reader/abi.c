/* SPDX-License-Identifier: MIT
 * Offline ABI recorder: compile with NVIDIA's exact published headers.
 * No device, library initialization, ioctl or driver API is called.
 */
#include <stddef.h>
#include <stdio.h>
#include "nvos.h"
#include "class/cl0080.h"
#include "ctrl/ctrl0073/ctrl0073system.h"
#define SIZE(t) printf("\"" #t "\":%zu,",sizeof(t))
#define OFF(t,f) printf("\"" #t "." #f "\":%zu,",offsetof(t,f))
int main(void)
{
 printf("{");
 SIZE(NVOS21_PARAMETERS); OFF(NVOS21_PARAMETERS,pAllocParms); OFF(NVOS21_PARAMETERS,status);
 SIZE(NVOS54_PARAMETERS); OFF(NVOS54_PARAMETERS,params); OFF(NVOS54_PARAMETERS,status);
 SIZE(NVOS00_PARAMETERS); SIZE(NV0080_ALLOC_PARAMETERS);
 SIZE(NV0073_CTRL_SYSTEM_GET_SUPPORTED_PARAMS);
 SIZE(NV0073_CTRL_SYSTEM_GET_CONNECT_STATE_PARAMS);
 SIZE(NV0073_CTRL_SYSTEM_GET_SET_HOTPLUG_CONFIG_PARAMS);
 SIZE(NV0073_CTRL_SYSTEM_GET_HOTPLUG_STATE_PARAMS);
 printf("\"cached_flags\":%u,",NV0073_CTRL_SYSTEM_GET_CONNECT_STATE_FLAGS_METHOD_CACHED |
    (NV0073_CTRL_SYSTEM_GET_CONNECT_STATE_FLAGS_DDC_DISABLE<<4) |
    (NV0073_CTRL_SYSTEM_GET_CONNECT_STATE_FLAGS_LOAD_DISABLE<<5));
 printf("\"root_class\":%u,\"device_class\":%u,",NV01_ROOT_CLIENT,NV01_DEVICE_0);
 printf("\"supported\":%u,\"connect\":%u,\"config\":%u,\"state\":%u}\n",
  NV0073_CTRL_CMD_SYSTEM_GET_SUPPORTED,NV0073_CTRL_CMD_SYSTEM_GET_CONNECT_STATE,
  NV0073_CTRL_CMD_SYSTEM_GET_HOTPLUG_CONFIG,NV0073_CTRL_CMD_SYSTEM_GET_HOTPLUG_STATE);
 return 0;
}
