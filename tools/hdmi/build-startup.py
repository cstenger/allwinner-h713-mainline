#!/usr/bin/env python3
"""Build an opt-in startup bundle for the validated 6.18.38 bench image.

RTC GP6 is a crash-loop guard, acknowledged by Linux after healthy startup. GP7 remains the
reboot-mode word. No bootloader binary or kernel image is changed.
"""
import argparse
import hashlib
import json
import shutil
import struct
import zlib
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
LATCH=0x07090118
MAGIC=0x48444d49
HEALTHY=0x48444f4b  # HDOK; only the health-ack unit writes this value
# Validated Oct 16 FIT and board FDT: playback-gated PA (0181) plus
# panel/shared-DT prerequisites (0182-0187).
# U-Boot refuses any other image before it launches anything; build() checks
# these against build/out so a kernel swap cannot silently outdate them.
FIT_SIZE=7795668
FDT_SIZE=34666
FIT=ROOT/'build/out/h713-kernel.fit'
DTB=ROOT/'build/out/sun50i-h713-hy200-qz713df-a1.dtb'
PREBOOT='if itest.l *0x0709011c == 0xfa57b007; then mw.l 0x0709011c 0; run fastboot_mode; elif itest.l *0x0709011c == 0xb007c0de; then mw.l 0x0709011c 0; setenv bootdelay -1; fi; usb start'
BOOTCMD='if fatload mmc 1:2 0x52000000 h713-hdmi.scr; then source 0x52000000; else echo HDMI startup script missing - use h713_hdmi_previous_bootcmd for recovery; fi'


def script():
    # Commands in each stage are chained: no partial stage can authorize Linux.
    stages={
      'image':[
        'fatload mmc 1:2 0x50000000 h713-kernel.fit',
        f'itest ${{filesize}} == {FIT_SIZE:x}', # exact proven FIT size, hex
        'fdt addr 0x50000000',
        'fdt get size hdmi_fdt_size /images/fdt-1 data',
        f'itest ${{hdmi_fdt_size}} == {FDT_SIZE:x}',
        'fdt get addr hdmi_fdt /images/fdt-1 data',
        'itest ${hdmi_fdt} -ge 50000000',
        'setexpr hdmi_fdt_end ${hdmi_fdt} + ${hdmi_fdt_size}',
        f'itest ${{hdmi_fdt_end}} -le {0x50000000+FIT_SIZE:x}',
        'cp.b ${hdmi_fdt} 0x4f000000 ${hdmi_fdt_size}',
        'fdt addr 0x4f000000', 'fdt resize 0x1000',
        'fdt set /soc/audio-bridge@203042c interrupts <0 115 4 0 113 4>',
        'fdt get value hdmi_ccu /soc/clock-controller@2001000 phandle',
        'itest ${hdmi_ccu} -gt 0', 'itest ${hdmi_ccu} -lt ffffffff',
        'fdt mknode /soc hdmi-mips-shutdown',
        'fdt set /soc/hdmi-mips-shutdown compatible h713,hdmi-mips-shutdown-bench',
        'fdt set /soc/hdmi-mips-shutdown resets <${hdmi_ccu} 1 ${hdmi_ccu} 2 ${hdmi_ccu} 3>',
        'fdt set /soc/hdmi-mips-shutdown clocks <${hdmi_ccu} 19 ${hdmi_ccu} 20>'],
      'launch':[
        'itest.l *0x0306101c == 0',
        'itest.l *0x02001600 == 0',
        'itest.l *0x0200160c == 0',
        'itest.l *0x0709011c == 0',
        'itest.l *0x070101ac == 0',
        # Lamp (PB5, shared with the fan) off while the panel is powered
        # without drive (white field) and while the relaunch drops the 720p
        # timing; hdmi_source turns it back on once the final frame is latched.
        'mw.l 0x07090118 0x48444d49',
        'itest.l *0x07090118 == 48444d49',
        'gpio clear PB5',
        'h713_disp auto 0x34 logo',
        'h713_disp mips-comm-trace 0x34',
        'itest.l *0x0306101c == 1',
        # commdev refreshes the ARM cache for the pointer and all 16 records.
        'h713_disp commdev',
        'itest.l *0x4b1227b4 == 03e00008',
        'itest.l *0x4b1227b8 == 24020001',
        'setexpr.l hdmi_dev *0x4b22efe4',
        'itest ${hdmi_dev} -ge 8b100000',
        'itest ${hdmi_dev} -lt 8bffff00',
        'setexpr hdmi_rec ${hdmi_dev} - 40000000',
        'setexpr hdmi_rec ${hdmi_rec} + a8',
        'setenv hdmi_count 0', 'setenv hdmi_bad 0', 'setenv hdmi_pid 0'],
      'source':[
        'itest ${hdmi_count} == 1', 'itest ${hdmi_bad} == 0',
        'itest ${hdmi_pid} -gt 0',
        'h713_disp commcall eaf13de5 chan=0 pid=${hdmi_pid} 3',
        'h713_disp commtrace',
        'itest.l *0x4d980004 == 434f4d4d',
        'itest.l *0x4d980080 == 43414e31',
        'itest.l *0x4d980ffc == 43414e31',
        'itest.l *0x4d980078 == 3', 'itest.l *0x4d98007c == 1',
        # The live firmware reprograms the panel TCON to 1080p (2200x1125);
        # the 720p panel cannot lock and stays black. Replay U-Boot's
        # h713_disp_latch_panel_timing(): mode[2:0]=4, 720p timing, then
        # pulse +0x0c bit 0. Arithmetic only, no bare & in hush.
        'setexpr.l hdmi_tm *0x0588001c',
        'setexpr hdmi_tr ${hdmi_tm} % 8',
        'setexpr hdmi_tm ${hdmi_tm} - ${hdmi_tr}',
        'setexpr hdmi_tm ${hdmi_tm} + 4',
        'mw.l 0x0588001c ${hdmi_tm}',
        'mw.l 0x05880020 02f80550', 'mw.l 0x05880024 02d00500',
        'mw.l 0x05880028 00140028', 'mw.l 0x0588002c 80000014',
        'mw.l 0x05880030 80010003',
        'setexpr.l hdmi_tc *0x0588000c',
        'setexpr hdmi_tr ${hdmi_tc} % 2',
        'setexpr hdmi_tc ${hdmi_tc} - ${hdmi_tr}',
        'setexpr hdmi_tr ${hdmi_tc} + 1',
        'mw.l 0x0588000c ${hdmi_tr}', 'mw.l 0x0588000c ${hdmi_tc}',
        'itest.l *0x05880020 == 02f80550', 'itest.l *0x05880024 == 02d00500',
        'itest.l *0x05880030 == 80010003',
        'echo H713 panel 720p timing re-latched after source 3',
        'gpio set PB5',
        'fdt addr 0x4f000000',
        # setexpr stores bare %lx; fdt cells parse base 0, so prefix 0x.
        # hdmi_ccu needs none: fdt get value already stores 0x%08X.
        'fdt set /chosen h713,hdmi-boot-v1 <0x48444d49 0 0x${hdmi_pid}>',
        'echo H713 HDMI shared startup handoff verified',
        'bootm 0x50000000 - 0x4f000000'],
      'record':[
        'setexpr.l hdmi_w0 *${hdmi_rec}',
        'setexpr hdmi_ptr ${hdmi_rec} + 8',
        'setexpr.l hdmi_slot_pid *${hdmi_ptr}',
        'setexpr hdmi_ptr ${hdmi_rec} + c',
        'setexpr.l hdmi_key *${hdmi_ptr}'],
    }
    lines=['# Generated by tools/hdmi/build-startup.py. GP6: 0/HDOK -> HDMI -> Linux health ack; other states fallback.']
    for name,commands in stages.items():
        lines.append("setenv hdmi_"+name+" '"+' && '.join(commands)+"'")
    lines += [
      'if itest.l *0x07090118 != 0 && itest.l *0x07090118 != 48444f4b; then',
      '  echo H713 HDMI unacknowledged or unknown GP6 - logo-only fallback',
      # Warm boots still need the panel: Linux only adopts what U-Boot drew.
      '  if itest.l *0x0306101c == 0; then',
      '    gpio clear PB5',
      '    if h713_disp auto 0x34 logo; then true; else echo H713 warm logo bring-up failed; fi',
      '    gpio set PB5',
      '  fi',
      '  if fatload mmc 1:2 0x50000000 h713-kernel.fit; then bootm 0x50000000; fi',
      'else',
      '  if run hdmi_image && run hdmi_launch; then',
      '    for hdmi_i in 0 1 2 3 4 5 6 7 8 9 a b c d e f; do',
      '      if run hdmi_record; then',
      '        if itest ${hdmi_key} != ffffffff; then',
      '          if itest ${hdmi_key} != 0 || itest ${hdmi_slot_pid} != 0 || itest ${hdmi_w0} != 0; then',
      '            setexpr hdmi_count ${hdmi_count} + 1',
      '            setexpr hdmi_chan ${hdmi_w0} / 10000',
      '            if itest ${hdmi_chan} != 0 || itest ${hdmi_slot_pid} == 0; then setenv hdmi_bad 1; fi',
      '            setenv hdmi_pid ${hdmi_slot_pid}',
      '          fi',
      '        fi',
      '      else setenv hdmi_bad 1; fi',
      '      setexpr hdmi_rec ${hdmi_rec} + 30',
      '    done',
      '    if run hdmi_source; then true; else gpio set PB5; echo H713 HDMI source/boot failed - cold cycle required; false; fi',
      '  else gpio set PB5; echo H713 HDMI preparation/launch failed - inspect state before retry; false; fi',
      'fi', '']
    return '\n'.join(lines)


def legacy_image(data):
    # U-Boot legacy IH_TYPE_SCRIPT: one big-endian length and zero terminator.
    payload=struct.pack('>II',len(data),0)+data
    header=struct.pack('>7I4B32s',0x27051956,0,0,len(payload),0,0,zlib.crc32(payload),5,22,6,0,b'H713 guarded HDMI startup')
    crc=zlib.crc32(header)
    return header[:4]+struct.pack('>I',crc)+header[8:]+payload


def check_kernel(fit=FIT,dtb=DTB):
    for path,size in ((fit,FIT_SIZE),(dtb,FDT_SIZE)):
        if path.exists() and path.stat().st_size!=size:
            raise SystemExit(f'{path} is {path.stat().st_size} bytes, startup script pins {size}; update FIT_SIZE/FDT_SIZE only for a validated kernel')

def build(output):
    # Both entry points must package the health unit with the shared script.
    # The old full installer cannot safely update the installed production stack.
    import importlib.util
    spec=importlib.util.spec_from_file_location('shared_package',ROOT/'tools/hdmi/build-shared-startup.py')
    package=importlib.util.module_from_spec(spec);spec.loader.exec_module(package)
    return package.build(output)

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('output',type=Path)
    build(parser.parse_args().output)
