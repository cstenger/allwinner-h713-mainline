import hashlib,os
from pathlib import Path
original='c882461d5ee69128c79d99b784fde668ee4d57ab09ae308738e3f9ea91fd1ce7'
candidate='ea5828f159fc6be1f40473804dea8f37430810d0629eb21b54ebea3bbb00f9cb'
spl='cb9da87448a57aa1cafbc7ebf66200b5183304cef1eafe23d0818b99696a49ec'
size=1798*512;off=4828160*512
sha=lambda d:hashlib.sha256(d).hexdigest()
new=Path('/tmp/h713-dispatch-uboot-original.bin').read_bytes()
assert len(new)==size and sha(new)==original
with open('/dev/mmcblk0','r+b',buffering=0) as f:
 f.seek(16*512);before_spl=f.read(64*512);assert sha(before_spl)==spl
 f.seek(off);before=f.read(size);assert sha(before)==candidate
 f.seek(off);assert f.write(new)==size;os.fsync(f.fileno())
 f.seek(off);assert sha(f.read(size))==original
 f.seek(16*512);assert f.read(64*512)==before_spl
print('RESTORED-VERIFIED',original,'SPL-UNCHANGED',spl,flush=True)
