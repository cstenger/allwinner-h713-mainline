import hashlib,os
from pathlib import Path
original='c882461d5ee69128c79d99b784fde668ee4d57ab09ae308738e3f9ea91fd1ce7'
candidate='3c2dd5d5208a23f1c4511c37b704a3d17e8a9bce29f16293dc8e768a7582660a'
spl='cb9da87448a57aa1cafbc7ebf66200b5183304cef1eafe23d0818b99696a49ec'
size=1798*512;off=4828160*512
sha=lambda d:hashlib.sha256(d).hexdigest()
new=Path('/tmp/h713-pll-init-uboot.bin').read_bytes()
assert len(new)==size and sha(new)==candidate
with open('/dev/mmcblk0','r+b',buffering=0) as f:
 f.seek(16*512);before_spl=f.read(64*512);assert sha(before_spl)==spl
 f.seek(off);before=f.read(size);assert sha(before)==original
 Path('/root/h713-pll-init-uboot-rollback.bin').write_bytes(before)
 assert sha(Path('/root/h713-pll-init-uboot-rollback.bin').read_bytes())==original
 f.seek(off);assert f.write(new)==size;os.fsync(f.fileno())
 f.seek(off);assert sha(f.read(size))==candidate
 f.seek(16*512);assert f.read(64*512)==before_spl
print('INSTALLED-VERIFIED',candidate,'SPL-UNCHANGED',spl,flush=True)
