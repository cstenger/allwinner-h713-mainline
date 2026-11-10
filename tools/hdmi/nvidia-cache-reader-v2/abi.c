/* SPDX-License-Identifier: MIT
 * Offline ABI recorder: compile with NVIDIA's exact published headers.
 * No device, library initialization, ioctl or driver API is called.
 */
#include <stddef.h>
#include <stdio.h>
#include <sys/ioctl.h>
#include "nv_escape.h"
#include "nv-ioctl-numbers.h"
#include "ctrl/ctrl0000/ctrl0000gpu.h"
#include "ctrl/ctrl0073/ctrl0073specific.h"
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
 SIZE(NV0000_CTRL_GPU_GET_ATTACHED_IDS_PARAMS);
 SIZE(NV0000_CTRL_GPU_GET_ID_INFO_V2_PARAMS); SIZE(NV0000_CTRL_GPU_GET_PCI_INFO_PARAMS);
 OFF(NV0000_CTRL_GPU_GET_PCI_INFO_PARAMS,bus); OFF(NV0000_CTRL_GPU_GET_PCI_INFO_PARAMS,slot);
 SIZE(NV0073_CTRL_SPECIFIC_GET_CONNECTOR_DATA_PARAMS);
 printf("\"attached_ids_command\":%u,\"gpu_info_command\":%u,\"pci_command\":%u,\"connector_command\":%u,",
 NV0000_CTRL_CMD_GPU_GET_ATTACHED_IDS,NV0000_CTRL_CMD_GPU_GET_ID_INFO_V2,
 NV0000_CTRL_CMD_GPU_GET_PCI_INFO,NV0073_CTRL_CMD_SPECIFIC_GET_CONNECTOR_DATA);
 printf("\"ioctl_alloc\":%lu,\"ioctl_control\":%lu,\"ioctl_free\":%lu,",
 (unsigned long)_IOWR(NV_IOCTL_MAGIC,NV_ESC_RM_ALLOC,NVOS21_PARAMETERS),
 (unsigned long)_IOWR(NV_IOCTL_MAGIC,NV_ESC_RM_CONTROL,NVOS54_PARAMETERS),
 (unsigned long)_IOWR(NV_IOCTL_MAGIC,NV_ESC_RM_FREE,NVOS00_PARAMETERS));
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
