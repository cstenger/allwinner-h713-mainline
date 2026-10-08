#!/usr/bin/env python3
"""Aligned reads of four stock-identified words; no MMIO writes or page copies.

Only after stock physical mapping and display/audio clock state are checked.
05001530/34: snd_alsa_trid REG_Init maps exactly these eight bytes.
02001d48/4c: stock CPU/UMAC clock configuration, no hardware clock retiming.
"""
import ctypes,json,mmap,os
addresses=(0x05001530,0x05001534,0x02001d48,0x02001d4c)
fd=os.open('/dev/mem',os.O_RDWR|os.O_SYNC)
pages={}
result={}
for address in addresses:
 page=address&~4095
 if page not in pages:
  mapping=mmap.mmap(fd,4096,mmap.MAP_SHARED,mmap.PROT_READ|mmap.PROT_WRITE,offset=page)
  pages[page]=(mapping,(ctypes.c_uint32*1024).from_buffer(mapping))
 result[f'{address:08x}']=f'{pages[page][1][(address-page)//4]:08x}'
print(json.dumps(result,sort_keys=True))
