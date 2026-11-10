#!/usr/bin/env python3
"""Build the optional fixed stock DSP patch probe in an isolated directory."""
import argparse
import hashlib
import json
import shutil
import struct
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PATCH_SHA = '8e31db199e0078d142f622436ff0b7249b333dbb6df8ec3fbabc0d8fea6ea0c5'

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--kernel-build', required=True, type=Path)
    ap.add_argument('--patch', required=True, type=Path)
    ap.add_argument('--output', required=True, type=Path)
    args = ap.parse_args()
    data = args.patch.read_bytes()
    if len(data) != 2896 or hashlib.sha256(data).hexdigest() != PATCH_SHA:
        raise SystemExit('Refusing unknown stock patch identity or length')
    kernel = args.kernel_build.resolve()
    if not (kernel/'Module.symvers').is_file():
        raise SystemExit('Exact complete kernel build required')
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    shutil.copy2(ROOT/'modules/hdmi-dsp-probe/h713-hdmi-dsp-probe.c', output)
    shutil.copy2(ROOT/'modules/hdmi-dsp-probe/h713-dsp-lock.h', output)
    shutil.copy2(ROOT/'modules/hdmi-dsp-probe/h713-dsp-completion.h', output)
    (output/'Makefile').write_text('obj-m += h713-hdmi-dsp-probe.o\nccflags-y += -DH713_STOCK_DSP_PATCH\n')
    pairs = [struct.unpack_from('>HH', data, n) for n in range(0, len(data), 4)]
    (output/'stock-dsp-patch.h').write_text(
        '/* Fixed stock patch SHA256: '+PATCH_SHA+' */\n'
        'static const struct dsp_pair stock_dsp_patch[] = {\n'+
        ''.join(f'\t{{ 0x{a:04x}, 0x{v:04x} }},\n' for a,v in pairs)+
        '};\nstatic_assert(ARRAY_SIZE(stock_dsp_patch) == 724);\n')
    subprocess.run(['make','-s','-C',str(kernel),f'M={output}','ARCH=arm64','LLVM=1','modules'],check=True)
    module=output/'h713-hdmi-dsp-probe.ko'
    print(json.dumps(dict(module=str(module),kernel_build=str(kernel),
                         patch_sha256=PATCH_SHA,pairs=len(pairs),
                         module_sha256=hashlib.sha256(module.read_bytes()).hexdigest())))

if __name__ == '__main__':
    main()
