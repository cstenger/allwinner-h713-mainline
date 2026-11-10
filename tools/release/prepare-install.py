#!/usr/bin/env python3
"""Prepare/verify a private DDR3 install/rollback packet. Never flashes a device.

The optional readback command opens a separately protected USB disk O_RDONLY.
Live UART/fastboot execution is deliberately absent; commands are review data.
"""
import argparse
import fcntl
import hashlib
import json
import mmap
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
import tarfile
import uuid
import zlib

SECTOR = 512
CHUNK = 16 * 1024 * 1024
DISK_BYTES = 7818182656
MODEL = 'HY200 QZ713DF_A1 (Allwinner H713)'
RESCUE_SPL_SHA = 'dab3b1585a8d05d30d87a57795fa505409304ce7287cfa58d5c8deed1bcf75f0'
READ_RAM = 0x50000000
ORDER = ('root', 'fat', 'proper', 'spl')


def need(ok, message):
    if not ok:
        raise ValueError(message)


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for data in iter(lambda: f.read(CHUNK), b''):
            h.update(data)
    return h.hexdigest()


def safe(root, name):
    p = Path(name)
    need(not p.is_absolute() and '..' not in p.parts and p.parts, 'unsafe packet path')
    result = root / p
    need(not any(x.is_symlink() for x in (result, *result.parents)), 'symlink input/output forbidden')
    return result


def ledger(root, name):
    result = {}
    for line in (root / name).read_text().splitlines():
        digest, relative = line.split('  ', 1)
        need(re.fullmatch('[0-9a-f]{64}', digest) and relative not in result, 'bad/duplicate ledger entry')
        path = safe(root, relative)
        need(path.is_file() and sha(path) == digest, 'checksum mismatch: ' + relative)
        result[relative] = digest
    return result


def seal(root):
    files = [p for p in sorted(root.rglob('*')) if p.is_file() and p.name != 'SHA256SUMS']
    (root / 'SHA256SUMS').write_text(''.join(sha(p) + '  ' + str(p.relative_to(root)) + '\n' for p in files))


def copy(source, target):
    """CoW copy when possible; never use mutation-sharing hard links."""
    target.parent.mkdir(parents=True, exist_ok=True)
    with source.open('rb') as src, target.open('xb') as dst:
        try:
            fcntl.ioctl(dst.fileno(), 0x40049409, src.fileno())  # Linux FICLONE
        except OSError:
            shutil.copyfileobj(src, dst, CHUNK)
    target.chmod(0o600)


def read_at(f, offset, size):
    f.seek(offset)
    data = f.read(size)
    need(len(data) == size, 'short image read')
    return data


def gpt(image):
    need(image.stat().st_size == DISK_BYTES, 'wrong baseline disk size')
    with image.open('rb') as f:
        header = read_at(f, 512, 512)
        def valid(h):
            need(h[:8] == b'EFI PART', 'missing GPT')
            size = struct.unpack_from('<I', h, 12)[0]
            need(92 <= size <= 512, 'invalid GPT header size')
            check = bytearray(h[:size]); expected = struct.unpack_from('<I', check, 16)[0]
            struct.pack_into('<I', check, 16, 0)
            need(zlib.crc32(check) & 0xffffffff == expected, 'GPT header CRC mismatch')
        valid(header)
        array_lba, count, entry_size, crc = struct.unpack_from('<QIII', header, 72)
        need(count == 28 and entry_size == 128 and array_lba == 2, 'GPT array would overlap SPL or differs from layout')
        data = read_at(f, array_lba * 512, count * entry_size)
        need(zlib.crc32(data) & 0xffffffff == crc, 'GPT array CRC mismatch')
        backup_lba = struct.unpack_from('<Q', header, 32)[0]
        need(backup_lba == DISK_BYTES // 512 - 1, 'wrong backup GPT location')
        other = read_at(f, backup_lba * 512, 512); valid(other)
        b_lba, b_count, b_size, b_crc = struct.unpack_from('<QIII', other, 72)
        need((b_count, b_size, b_crc) == (count, entry_size, crc), 'GPT arrays metadata differ')
        need(read_at(f, b_lba * 512, len(data)) == data, 'GPT arrays differ')
        need(other[56:72] == header[56:72], 'GPT disk GUIDs differ')
    parts = []
    for i in range(count):
        e = data[i * entry_size:(i + 1) * entry_size]
        if e[:16] == bytes(16):
            continue
        start, end = struct.unpack_from('<QQ', e, 32)
        first, last = struct.unpack_from('<QQ', header, 40)
        need(first <= start <= end <= last, 'partition outside usable GPT range')
        parts.append(dict(number=i + 1, label=e[56:128].decode('utf-16-le').rstrip('\0'),
                          start_lba=start, sectors=end - start + 1, guid=str(uuid.UUID(bytes_le=e[16:32]))))
    need([p['number'] for p in parts] == list(range(1,28)), 'expected exact partition numbers 1..27')
    ordered = sorted(parts,key=lambda p:p['start_lba'])
    need(all(a['start_lba']+a['sectors'] <= b['start_lba'] for a,b in zip(ordered,ordered[1:])), 'overlapping GPT partitions')
    expected = {2: ('bootloader_b', 0x22000, 0x10000), 9: ('super', 0x92400, 0x400000),
                18: ('empty', 0x49ac00, 0x7800), 26: ('linux', 5555200, 5767168),
                27: ('UDISK', 11322368, 2021113344 // 512)}
    for number, pin in expected.items():
        part = next(p for p in parts if p['number'] == number)
        need((part['label'], part['start_lba'], part['sectors']) == pin, 'partition identity mismatch: '+str(number))
    return dict(entry_slots=count, disk_guid=str(uuid.UUID(bytes_le=header[56:72])), partitions=parts)


def environment(data):
    need(len(data) == 65536 and zlib.crc32(data[4:]) & 0xffffffff == int.from_bytes(data[:4], 'little'),
         'environment CRC/size mismatch')
    result = {}
    for item in data[4:].split(b'\0\0', 1)[0].split(b'\0'):
        key, value = item.decode('ascii').split('=', 1)
        need(key not in result, 'duplicate environment key')
        result[key] = value
    return result


def check_spl(data):
    need(len(data) == 32768 and data[4:12] == b'eGON.BT0', 'invalid SPL region')
    expected, size = struct.unpack_from('<II', data, 12)
    need(32 <= size <= len(data) and size % 4 == 0, 'invalid eGON length')
    check = bytearray(data[:size]); struct.pack_into('<I', check, 12, 0x5f0a6c39)
    need(sum(struct.unpack('<' + 'I' * (size // 4), check)) & 0xffffffff == expected, 'SPL eGON checksum mismatch')


def all_raw_sparse(source, target):
    """Every logical block is RAW, including zeros. Host may resparse to 16 MiB."""
    size = source.stat().st_size
    need(size and size % 4096 == 0 and size + 12 < 2**32, 'all-RAW sparse size invalid')
    with source.open('rb') as src, target.open('xb') as dst:
        dst.write(struct.pack('<I4H4I', 0xed26ff3a, 1, 0, 28, 12, 4096, size // 4096, 1, 0))
        dst.write(struct.pack('<2H2I', 0xcac1, 0, size // 4096, size + 12))
        shutil.copyfileobj(src, dst, CHUNK)
    return check_all_raw(target, sha(source), size)


def check_all_raw(path, expected_sha, expected_bytes):
    with path.open('rb') as f:
        header = f.read(28)
        need(len(header) == 28, 'short sparse header')
        need(struct.unpack('<I4H4I', header) == (0xed26ff3a, 1, 0, 28, 12, 4096, expected_bytes // 4096, 1, 0),
             'sparse header mismatch')
        need(struct.unpack('<2H2I', f.read(12)) == (0xcac1, 0, expected_bytes // 4096, expected_bytes + 12),
             'sparse must contain one RAW chunk; skips/fill forbidden')
        h = hashlib.sha256(); size = 0
        for data in iter(lambda: f.read(CHUNK), b''):
            h.update(data); size += len(data)
        need(size == expected_bytes and h.hexdigest() == expected_sha, 'sparse payload mismatch')
    return dict(type='Android sparse v1; one RAW chunk; no skips/fill', logical_bytes=expected_bytes,
                raw_sha256=expected_sha, sparse_sha256=sha(path))


def target_bounds(role, size, layout):
    parts = {p['number']: p for p in layout['partitions']}
    if role == 'root':
        need(size in (2147483648, 2952790016), 'unexpected root image size')
        start, limit = parts[26]['start_lba'], parts[26]['sectors']
    elif role == 'fat':
        need(size == 33554432, 'boot FAT must be exactly 32 MiB')
        start, limit = parts[2]['start_lba'], parts[2]['sectors']
    elif role == 'proper':
        need(size == 955904, 'proper extent must remain exactly 1867 sectors')
        start, limit = 0x49ac00, 1867
    elif role == 'spl':
        need(size == 32768, 'SPL must be exactly 64 sectors')
        start, limit = 0x10, 64
    else:
        raise ValueError('unexpected write role')
    need(size % 512 == 0 and size // 512 <= limit, 'write exceeds target bounds')
    return start, size // 512


def chunk_pins(path, start_lba=0):
    result = []
    with path.open('rb') as f:
        offset = 0
        for data in iter(lambda: f.read(CHUNK), b''):
            need(len(data) % 512 == 0, 'unaligned extent')
            result.append(dict(offset=offset, bytes=len(data), lba=start_lba + offset // 512,
                               sha256=hashlib.sha256(data).hexdigest(), crc32=f'{zlib.crc32(data) & 0xffffffff:08x}'))
            offset += len(data)
    return result


def disk_pins(image, overlays):
    """SHA-256/CRC32 for the exact baseline or hypothetical post-write disk."""
    opened = [(start, size, path.open('rb')) for start, size, path in overlays]
    result = []; whole = hashlib.sha256()
    try:
        with image.open('rb') as f:
            for offset in range(0, DISK_BYTES, CHUNK):
                data = bytearray(f.read(min(CHUNK, DISK_BYTES - offset)))
                need(len(data) == min(CHUNK, DISK_BYTES - offset), 'short baseline image')
                for start, size, src in opened:
                    lo, hi = max(start, offset), min(start + size, offset + len(data))
                    if lo < hi:
                        src.seek(lo - start); piece = src.read(hi - lo)
                        need(len(piece) == hi - lo, 'short overlay payload')
                        data[lo-offset:hi-offset] = piece
                whole.update(data)
                result.append(dict(offset=offset, bytes=len(data), sha256=hashlib.sha256(data).hexdigest(),
                                   crc32=f'{zlib.crc32(data) & 0xffffffff:08x}'))
    finally:
        for _, _, src in opened: src.close()
    return dict(bytes=DISK_BYTES, sha256=whole.hexdigest(), chunks=result)


def crc_commands(chunks):
    result = []
    for p in chunks:
        lba = p.get('lba', p['offset'] // 512)
        result.append(dict(uart=[f'mmc read 0x{READ_RAM:x} 0x{lba:x} 0x{p["bytes"]//512:x}',
                                 f'crc32 0x{READ_RAM:x} 0x{p["bytes"]:x}'],
                           expected_read_sectors=p['bytes']//512, expected_crc32=p['crc32'],
                           note='Stop unless MMC read reports exactly this count and OK, then CRC matches.'))
    return result


def phase(mode, role, root, layout, serial):
    raw = root / 'payloads' / mode / (role + '.bin')
    size = raw.stat().st_size; start, sectors = target_bounds(role, size, layout)
    alias = 'h713pkt_' + role
    labels = {p['label'] for p in layout['partitions']}
    need(alias not in labels and alias + '_a' not in labels, 'raw alias collides with GPT partition')
    payload = raw.with_suffix('.simg') if role in ('root', 'fat') else raw
    argv = ['fastboot', '-s', serial, '-S', '16M', 'flash', alias, str(payload.relative_to(root))]
    return dict(role=role, alias=alias, payload=str(payload.relative_to(root)), raw=str(raw.relative_to(root)),
                offset=start*512, bytes=size, start_lba=start, sectors=sectors, sha256=sha(raw),
                uart_setup=['mmc dev 1 0', f'setenv fastboot_partition_alias_{alias}',
                            f'setenv fastboot_raw_partition_{alias} 0x{start:x} 0x{sectors:x} mmcpart 0',
                            f'printenv fastboot_raw_partition_{alias}', 'run fastboot_mode'],
                host_gates=[dict(argv=['fastboot','-s',serial,'getvar','serialno'], value=serial),
                            dict(argv=['fastboot','-s',serial,'getvar','is-userspace'], value='no'),
                            dict(argv=['fastboot','-s',serial,'getvar','max-download-size'], value='0x02000000'),
                            dict(argv=['fastboot','-s',serial,'getvar','has-slot:'+alias], value='no'),
                            dict(argv=['fastboot','-s',serial,'getvar','partition-size:'+alias], value=f'0x{size:016x}')],
                host_flash=argv, host_return=['fastboot','-s',serial,'continue'],
                uart_checkpoint=crc_commands(chunk_pins(raw,start)))


def prepare(candidate, backup, identity_evidence, rescue_spl, fel_tool, output):
    candidate, backup, output = candidate.resolve(), backup.resolve(), output.resolve()
    need(not output.exists(), 'output must be new; never overwrite/resume a packet')
    candidate_pins = ledger(candidate, 'PACKAGE-SHA256SUMS')
    backup_pins = ledger(backup, 'SHA256SUMS')
    release = json.loads((candidate/'release.json').read_text())
    need(release['qualification'].startswith('UNQUALIFIED'), 'unexpected candidate qualification')
    check = json.loads((backup/'full-backup-result.json').read_text())
    host_check = json.loads((backup/'host-copy-verification.json').read_text())
    image = safe(backup, 'emmc-user-area.img')
    need(check['status'].startswith('PASS') and check['host_nodes_readonly'] == 28 and check['unmounted'], 'backup did not pass protected two-read comparison')
    need(check['sha256'] == backup_pins['emmc-user-area.img'] == host_check['user_area_sha256'], 'backup evidence/image disagree')
    need(host_check['filesystem_checks']['rootfs']['returncode'] == 0, 'backup rootfs is not clean')
    layout = gpt(image)
    env_data = (backup/'rollback-extents/environment-64KiB.bin').read_bytes()
    env = environment(env_data)
    with image.open('rb') as f:
        need(read_at(f,0x49ec00*512,65536)==env_data,'saved environment differs from baseline disk')
    expected_env = json.loads((candidate/'boot-environment.json').read_text())
    need(all(env.get(k) == expected_env[k] for k in ('bootcmd','preboot')), 'candidate boot environment differs; no automatic save permitted')
    serial = env['serial#']; need(re.fullmatch('[0-9a-f]{16}', serial), 'invalid board USB serial')
    evidence = identity_evidence.read_text().splitlines()
    need(len(evidence) >= 2 and re.fullmatch('[0-9a-f]{32}', evidence[0]) and int(evidence[1])*512 == DISK_BYTES, 'CID/capacity evidence malformed')
    need(sha(rescue_spl) == RESCUE_SPL_SHA, 'rehearsed FEL rescue SPL pin mismatch')
    check_spl(rescue_spl.read_bytes())
    config = (candidate/'provenance/uboot.config').read_text()
    for line in ('CONFIG_FASTBOOT_FLASH_MMC_DEV=1', 'CONFIG_FASTBOOT_BUF_ADDR=0x42000000',
                 'CONFIG_FASTBOOT_BUF_SIZE=0x2000000', '# CONFIG_CMD_HASH is not set'):
        need(line in config.splitlines(), 'unexpected U-Boot configuration: '+line)
    # Private images/configuration must never become a public source artifact.
    output.mkdir(parents=True,mode=0o700)
    metadata = output/'metadata';metadata.mkdir()
    for name in ('release.json','source-lock.json','boot-environment.json'):
        copy(candidate/name,metadata/name)
    copy(identity_evidence,metadata/'identity-evidence.txt')
    copy(image,output/'baseline/emmc-user-area.img')
    copy(backup/'pre-shutdown-immutable-regions.tar',output/'baseline/immutable-regions.tar')
    copy(rescue_spl,output/'rescue/rehearsed-spl.bin')
    need(fel_tool.is_file() and not fel_tool.is_symlink(),'explicit host FEL executable required')
    copy(fel_tool,output/'tools/sunxi-fel');(output/'tools/sunxi-fel').chmod(0o500)
    serial_sources=Path(__file__).resolve().parents[1]/'serial'
    for name in ('ymodem_send.py','h713_tty.py'):
        copy(serial_sources/name,output/'tools/serial'/name)
    with tarfile.open(backup/'pre-shutdown-immutable-regions.tar') as tar:
        for name in ('rescue-full-region.bin','emmc-boot0.bin','emmc-boot1.bin'):
            info=tar.getmember(name);need(info.isfile() and info.size <= 4194304, 'unexpected immutable capture')
            path=output/'rescue'/name;path.write_bytes(tar.extractfile(info).read());path.chmod(0o600)
    with image.open('rb') as f:
        need(read_at(f,0x4a0c00*512,2097152)==(output/'rescue/rescue-full-region.bin').read_bytes(),'rescue proper differs from baseline disk')
    sources = {'install': {'root':candidate/'rootfs/rootfs.ext4','fat':candidate/'boot.img',
                           'proper':candidate/'firmware/u-boot-proper.itb','spl':candidate/'firmware/spl-region.bin'},
               'rollback':{'root':backup/'rollback-extents/linux-p26.ext4','fat':backup/'rollback-extents/bootloader-b-fat.img',
                           'proper':backup/'rollback-extents/u-boot-proper-1867-sectors.bin','spl':backup/'rollback-extents/spl-region.bin'}}
    manifests = {}
    for mode in ('install','rollback'):
        directory=output/'payloads'/mode;directory.mkdir(parents=True)
        for role,source in sources[mode].items():
            target=directory/(role+'.bin')
            if role=='proper' and mode=='install':
                proper=source.read_bytes()
                need(len(proper)>=8 and struct.unpack('>II',proper[:8])==(0xd00dfeed,len(proper)), 'proper FIT total length mismatch')
                target.write_bytes(proper+bytes((-len(proper))%512));target.chmod(0o600)
            else:copy(source,target)
            if role=='spl':check_spl(target.read_bytes())
            target_bounds(role,target.stat().st_size,layout)
            if role in ('root','fat'):all_raw_sparse(target,target.with_suffix('.simg'))
        manifests[mode]=[phase(mode,role,output,layout,serial) for role in ORDER]
    # Derive actual expected whole-disk bytes, including unchanged GPT/Android,
    # the root partition tail, environment, rescue, stash and vendor regions.
    baseline=disk_pins(image,[])
    need(baseline['sha256']==check['sha256'],'baseline changed during preparation')
    post=disk_pins(image,[(p['offset'],p['bytes'],output/p['raw']) for p in manifests['install']])
    rollback=disk_pins(image,[(p['offset'],p['bytes'],output/p['raw']) for p in manifests['rollback']])
    need(rollback==baseline,'rollback does not reconstruct exact baseline user area')
    readbacks=output/'readback';readbacks.mkdir()
    for name,value in [('baseline',baseline),('install',post),('rollback',rollback)]:
        (readbacks/(name+'.json')).write_text(json.dumps(value,indent=2)+'\n')
    rule=('ACTION=="add", SUBSYSTEM=="block", ATTRS{idVendor}=="1f3a", ATTRS{idProduct}=="1010", '
          'ATTRS{serial}=="'+serial+'", ENV{UDISKS_IGNORE}="1", OWNER="chris", MODE="0400", '
          'RUN{program}+="/usr/bin/blockdev --setro $devnode"\n')
    (output/'99-h713-packet-readonly.rules').write_text(rule)
    packet=dict(schema='h713-install-packet-v1', preparation_only=True, hardware_executed=False,
                model=MODEL, emmc_cid=evidence[0], usb_serial=serial, disk_bytes=DISK_BYTES, layout=layout,
                baseline_sha256=baseline['sha256'], expected_install_sha256=post['sha256'],
                candidate_release_sha256=candidate_pins['release.json'],
                input_ledgers={'candidate_package':sha(candidate/'PACKAGE-SHA256SUMS'),'backup':sha(backup/'SHA256SUMS')},
                buffer=dict(fastboot_address=0x42000000,fastboot_bytes=0x2000000,readback_address=READ_RAM,readback_bytes=CHUNK),
                boot_environment=dict(sha256=hashlib.sha256(env_data).hexdigest(),bootcmd=env['bootcmd'],preboot=env['preboot'],save_permitted=False),
                phases=manifests, boot_fat_baseline_findings=host_check['filesystem_checks']['boot-fat'],
                protected_policy='Every byte outside the four selected extents must match baseline. No GPT/environment/Android/rescue/stash writes.',
                final_readback_required=True, tested_fastboot_version='fastboot version 37.0.0p1-android-tools',
                rescue=dict(spl_sha256=RESCUE_SPL_SHA,proper_lba=0x4a0c00,
                            proper_region_sha256=sha(output/'rescue/rescue-full-region.bin'),
                            host_fel_sha256=sha(output/'tools/sunxi-fel'),
                            host_fel_argv=['tools/sunxi-fel','-p','spl','rescue/rehearsed-spl.bin'],
                            note='Physical FEL recovery loads the already rehearsed on-board rescue proper. Revalidate rescue prompt/device; then use rollback phases. Never save its RAM environment.'))
    (output/'packet.json').write_text(json.dumps(packet,indent=2)+'\n')
    fastboot=shutil.which('fastboot')
    need(fastboot is not None,'host fastboot is missing')
    version=subprocess.check_output([fastboot,'--version'],text=True).splitlines()[0]
    need(version==packet['tested_fastboot_version'],'host fastboot version differs from validated version')
    (output/'HOST-TOOLS.json').write_text(json.dumps({'fastboot':{'path':fastboot,'version':version,'sha256':sha(Path(fastboot))}},indent=2)+'\n')
    write_plan(output,packet,baseline)
    copy(Path(__file__).resolve(),output/'packet-tool.py')
    seal(output)
    return packet


def validate_structure(packet, root):
    need(packet['schema']=='h713-install-packet-v1' and packet['preparation_only'] and not packet['hardware_executed'], 'packet state/schema invalid')
    need(packet['disk_bytes']==DISK_BYTES and packet['final_readback_required'] and not packet['boot_environment']['save_permitted'], 'unsafe policy')
    serial=packet['usb_serial'];need(re.fullmatch('[0-9a-f]{16}',serial),'bad USB serial')
    for mode in ('install','rollback'):
        need([p['role'] for p in packet['phases'][mode]]==list(ORDER),'SPL must be last; roles/order changed')
        for p in packet['phases'][mode]:
            role=p['role'];raw_name='payloads/'+mode+'/'+role+'.bin'
            need(p['raw']==raw_name,'raw source path changed')
            raw=safe(root,raw_name);start,sectors=target_bounds(role,raw.stat().st_size,packet['layout'])
            need((p['start_lba'],p['sectors'],p['offset'],p['bytes'])==(start,sectors,start*512,raw.stat().st_size),'write address/count changed')
            alias='h713pkt_'+role;need(p['alias']==alias,'unsafe target alias')
            source='payloads/'+mode+'/'+role+('.simg' if role in ('root','fat') else '.bin')
            need(p['payload']==source and p['host_flash']==['fastboot','-s',serial,'-S','16M','flash',alias,source],'flash target/arguments changed')
            need(p['host_return']==['fastboot','-s',serial,'continue'],'unexpected reset/return command')
            expected=['mmc dev 1 0',f'setenv fastboot_partition_alias_{alias}',
                      f'setenv fastboot_raw_partition_{alias} 0x{start:x} 0x{sectors:x} mmcpart 0',
                      f'printenv fastboot_raw_partition_{alias}','run fastboot_mode']
            need(p['uart_setup']==expected,'RAM alias/hardware partition commands changed')


def validate_phases(packet, root):
    validate_structure(packet,root)
    need(packet['schema']=='h713-install-packet-v1' and packet['preparation_only'] and not packet['hardware_executed'], 'packet state/schema invalid')
    need(packet['disk_bytes']==DISK_BYTES and packet['final_readback_required'] and not packet['boot_environment']['save_permitted'], 'unsafe policy')
    layout=packet['layout']
    need(layout==gpt(root/'baseline/emmc-user-area.img'),'layout no longer matches baseline')
    for mode in ('install','rollback'):
        need([p['role'] for p in packet['phases'][mode]]==list(ORDER),'SPL must be last; roles/order changed')
        ranges=[]
        for p in packet['phases'][mode]:
            raw=safe(root,p['raw']);size=raw.stat().st_size
            need(size==p['bytes'] and sha(raw)==p['sha256'],'raw payload changed')
            start,sectors=target_bounds(p['role'],size,layout)
            need((p['start_lba'],p['sectors'],p['offset'])==(start,sectors,start*512),'write address/count changed')
            need(p==phase(mode,p['role'],root,layout,packet['usb_serial']),'phase commands/gates/pins changed')
            if p['role'] in ('root','fat'):check_all_raw(safe(root,p['payload']),p['sha256'],size)
            if p['role']=='spl':check_spl(raw.read_bytes())
            ranges.append((p['offset'],p['offset']+size))
        ranges.sort();need(all(a[1]<=b[0] for a,b in zip(ranges,ranges[1:])),'write ranges overlap')


def verify(root):
    root=root.resolve();pins=ledger(root,'SHA256SUMS')
    actual={str(p.relative_to(root)) for p in root.rglob('*') if p.is_file() and p.name!='SHA256SUMS'}
    need(actual==set(pins),'unsealed/missing packet file')
    packet=json.loads((root/'packet.json').read_text());validate_phases(packet,root)
    need(sha(root/'tools/sunxi-fel')==packet['rescue']['host_fel_sha256'],'host FEL executable changed')
    need(sha(root/'rescue/rehearsed-spl.bin')==RESCUE_SPL_SHA,'rescue SPL changed')
    check_spl((root/'rescue/rehearsed-spl.bin').read_bytes())
    with (root/'baseline/emmc-user-area.img').open('rb') as f:
        need(read_at(f,0x4a0c00*512,2097152)==(root/'rescue/rescue-full-region.bin').read_bytes(),'rescue proper changed')
        need(hashlib.sha256(read_at(f,0x49ec00*512,65536)).hexdigest()==packet['boot_environment']['sha256'],'environment identity changed')
    image=root/'baseline/emmc-user-area.img'
    baseline=disk_pins(image,[])
    need(baseline==json.loads((root/'readback/baseline.json').read_text()),'baseline pins changed')
    need(baseline['sha256']==packet['baseline_sha256'],'baseline identity changed')
    for mode in ('install','rollback'):
        expected=disk_pins(image,[(p['offset'],p['bytes'],root/p['raw']) for p in packet['phases'][mode]])
        need(expected==json.loads((root/'readback'/(mode+'.json')).read_text()),'expected readback changed: '+mode)
        need(expected['sha256']==(packet['expected_install_sha256'] if mode=='install' else packet['baseline_sha256']),'whole image identity changed')
    write_plan(root,packet,baseline,check=True)
    return dict(status='PASS packet checksums, layout, bounded phases, all-RAW payloads and complete disk overlays',
                preparation_only=True,hardware_executed=False,files=len(pins))


def write_plan(root, packet, baseline, check=False):
    def emit(name,text):
        if check:need((root/name).read_text()==text,'review transcript changed: '+name)
        else:(root/name).write_text(text)
    serial=packet['usb_serial']
    for mode in ('install','rollback'):
        lines=['# '+mode.title()+' command transcript — review and gate each step', '',
               'This is review data, not a batch installer. No command in this file has been executed.',
               'Before live execution, require `fastboot --version` and executable SHA-256 to match HOST-TOOLS.json.',
               'Run host commands from the packet directory. Record each reply outside the sealed packet.',
               'Stop on any unexpected output, timeout, USB disconnect or failed hash; never auto-retry a write.', '',
               '## Entry and identity', '',
               'Reuse a verified cold-held prompt if still valid; otherwise take a fresh physical cold boot and catch the ordinary countdown. Enable/read back PB5; Linux must not have run since cold power-on.',
               'Confirm model, MMC user area (device 1, hardware partition 0), exact GPT and USB serial.',
               'Check `printenv bootcmd preboot serial#`; saved bootcmd/preboot must match packet.json.',
               'Never run saveenv/env save, erase, flashall, update, GPT commands or a reboot from fastboot.', '',
               'Install the packet read-only udev rule and temporarily disable desktop automount before UMS.',
               'It gives only chris read access on this exact board serial and sets disk/partitions read-only.',
               'Verify all 28 nodes are RO and unmounted; readback tool repeats those gates.', '',
               'Host setup requiring operator sudo:', '```sh',
               'sudo install -Dm644 99-h713-packet-readonly.rules /run/udev/rules.d/99-h713-packet-readonly.rules',
               'sudo udevadm control --reload-rules', '```', '',
               'At held UART prompt: `run serial_mode; ums 0 mmc 1`.',
               'Identify the newly enumerated disk by USB serial/capacity/GPT, never an assumed /dev/sdX.',
               'Run the appropriate preflight, supplying that observed --device and a new external --receipt:',
               '```sh',
               'python3 packet-tool.py readback --packet . --mode '+('baseline' if mode=='install' else 'recovery')+
               ' --device /dev/disk/by-id/usb-Linux_UMS_disk_0_'+serial+'-0:0 --receipt ../'+mode+'-preflight.json',
               '```',
               'Installation preflight requires an exact baseline disk. If Linux ran since backup, obtain a fresh verified backup.',
               'Recovery preflight permits differences only inside the four rollback extents; all other bytes must match baseline.',
               'Close the descriptor, exit UMS with one UART Ctrl-C and verify prompt/fan. No reset.', '']
        for i,p in enumerate(packet['phases'][mode],1):
            lines += [f'## Phase {i}: {p["role"]}', '',
                      f'Exact write: LBA 0x{p["start_lba"]:x}, sectors 0x{p["sectors"]:x}, bytes {p["bytes"]}.',
                      f'Raw SHA-256: `{p["sha256"]}`.', '', 'UART, one command/reply at a time:', '```text',
                      *p['uart_setup'], '```', '',
                      'Host getvar gates (stop unless every value agrees; numeric hex may be formatted differently):', '```sh']
            for gate in p['host_gates']:lines.append(' '.join(gate['argv'])+'  # expected '+gate['value'])
            lines += ['```', '', 'Only after those replies pass:', '```sh', ' '.join(p['host_flash']),
                      ' '.join(p['host_return']), '```', '',
                      'Continue returns to the same RAM-resident U-Boot without rebooting. Validate every MMC read/CRC32 pair below.',
                      'CRC32 is an immediate transfer checkpoint; final whole-device SHA-256 readback is mandatory.', '```text']
            for step in p['uart_checkpoint']:
                lines += [step['uart'][0]+f'  # expect {step["expected_read_sectors"]} blocks read: OK',
                          step['uart'][1]+'  # expect '+step['expected_crc32']]
            lines += ['```', '']
        lines += ['## Final readback before any boot', '',
                  'Start protected UMS again from this held prompt; reverify RO/unmounted nodes.', '```sh',
                  'python3 packet-tool.py readback --packet . --mode '+mode+
                  ' --device /dev/disk/by-id/usb-Linux_UMS_disk_0_'+serial+'-0:0 --receipt ../'+mode+'-final.json',
                  '```', 'The tool compares every disk chunk, including every byte outside the four writes.',
                  'Only after PASS, exit UMS, verify PB5 high, and remove RAM-only aliases:', '```text']
        for role in ORDER:
            lines += ['setenv fastboot_raw_partition_h713pkt_'+role, 'setenv fastboot_partition_alias_h713pkt_'+role]
        lines += ['```', 'Do not save the environment. Confirm persistent environment CRC/hash still matches the packet.', '',
                  '## First boot and acceptance', '',
                  'Only after reviewed live execution and final PASS, `run bootcmd` uses the existing guarded startup.',
                  'Capture UART build/handoff and the new boot ID; verify 4 CPUs, kernel config, module identity and bundle manifests.',
                  'For the candidate, read the new SSH host public key/fingerprint over UART and pin it in a separate host known_hosts file.',
                  'Never auto-accept a changed SSH key. Host keys are generated on first boot, not copied from rollback.',
                  'Verify calibration, HDMI desktop/audio/startup, file playback/decoder, networking, keys, standby, shutdown and recovery.',
                  'Rootfs growth/first-boot logs change disk hashes; whole-device expected hashes apply before boot.',
                  'The baseline boot FAT inconsistencies are preserved by rollback, not repaired.', '',
                  'After gadget disconnect, restore original desktop settings and remove the temporary root-owned rule.', '']
        emit(mode.upper()+'.md','\n'.join(lines))
    emit('PREFLIGHT-UART.json',json.dumps(dict(
        identity_uart=['version','gpio set PB5','gpio status PB5','mmc dev 1 0','mmc info','part list mmc 1','printenv bootcmd preboot serial#'],
        expectations=dict(model=MODEL,cid=packet['emmc_cid'],usb_serial=serial,layout=packet['layout'],
                          mmc_name='8GTF4R',manufacturer='15',pb5='output: 1'),
        note='CID is recorded from Linux evidence; this U-Boot lacks mmc-reg support. Bind live identity with exact GPT and whole-disk baseline readback plus SoC USB serial.',
        full_baseline_uart_crc_alternative=crc_commands(baseline['chunks']),
        note_crc='CRC alternative assists diagnosis; it does not replace the mandatory host SHA-256 gate.'),indent=2)+'\n')
    emit('RECOVERY.md','''# Recovery and exact rollback

The baseline complete user-area image and separate eMMC boot0/boot1 captures
are private recovery artifacts. They are not whole-disk flash instructions.
The rollback transcript writes only the original Linux p26, boot FAT, proper
and SPL extents; it reconstructs the exact baseline user-area hash before boot.
No environment/GPT/Android/rescue/stash writes are permitted. Rootfs rollback
restores the full 2.75 GiB partition, including any space grown by the candidate.

If a write/check fails while this U-Boot is alive, stop at the prompt, retain
fan PB5 high and transcripts, and enter the rollback preflight. Do not reset a
partially installed system. If USB is unstable, do not retry writes blindly.

If SPL/proper cannot reach a prompt, physically power off, connect UART/OTG,
hold FEL at power-on, release, and confirm the Allwinner FEL device. Arm a
fresh SPL/autoboot UART catcher before running the pinned RAM loader once:

    timeout --signal=TERM --kill-after=5s 30s tools/sunxi-fel -p spl rescue/rehearsed-spl.bin

The host tool and rescue SPL SHA-256 pins are in packet.json. Verify this Linux
x86-64 host tool's dynamic libraries before the live window. This previously
rehearsed RAM SPL loads
the preserved older rescue proper at LBA 0x4a0c00; it writes no storage.
This SPL hands off to rescue U-Boot instead of returning to ROM. The FEL host
tool can therefore remain waiting for its post-SPL ROM signature read after
successful rescue entry. A timeout/terminated host wait is not, by itself,
success or proof of a failed RAM boot. Require the fresh SPL banner, the exact
rescue proper banner from the pinned region, and a caught U-Boot prompt on
UART. Only after that receipt may the remaining host wait be terminated; do
not reset or repeat the load. If the UART receipt is missing at the deadline,
stop and preserve evidence. Never accept a host exit status alone as this gate.

Validate the rescue prompt, MMC identity, GPT and fan, then establish the four RAM raw
aliases from ROLLBACK.md. Old rescue defaults/aliases are not authoritative.
Never save the rescue environment. Reconfirm fastboot device 1/user area and
all getvar/alias gates on the rescue build before writing anything.

If USB recovery is unavailable, load exact small boot rollback extents via
UART YMODEM at 0x42000000, verify transferred size and CRC32, then use explicitly
bounded MMC writes to the proper slot and SPL (SPL last). Exact commands and
pins are in FEL-UART-BOOT-ROLLBACK.json. After readback, this restores access to
the accepted bootloader; the Linux rootfs/boot FAT still require their complete
rollback phases before boot. This is a fallback, not a bulk UART rootfs method.

Rehearsal of the complete new recovery packet is still pending. No live
installation, rollback or rescue test was performed during packet preparation.
''')
    stages=[]
    for role in ('proper','spl'):
        p=next(p for p in packet['phases']['rollback'] if p['role']==role)
        raw=root/p['raw'];crc=f'{zlib.crc32(raw.read_bytes()) & 0xffffffff:08x}'
        stages.append(dict(role=role,host_argv=['python3','-B','tools/serial/ymodem_send.py',p['raw'],'--port','<verified UART>'],
                           uart_load='loady 0x42000000',expected_filesize=f'{p["bytes"]:x}',
                           uart_ram_crc=f'crc32 0x42000000 0x{p["bytes"]:x}',expected_crc32=crc,
                           uart_write=f'mmc write 0x42000000 0x{p["start_lba"]:x} 0x{p["sectors"]:x}',
                           uart_readback=[f'mmc read 0x50000000 0x{p["start_lba"]:x} 0x{p["sectors"]:x}',f'crc32 0x50000000 0x{p["bytes"]:x}'],
                           gate='Close passive UART readers during YMODEM; validate each echo/status/size/CRC; stop on mismatch. No reset until all required filesystem rollback completes.'))
    emit('FEL-UART-BOOT-ROLLBACK.json',json.dumps(stages,indent=2)+'\n')


def mask_recovery(data,offset,ranges,baseline):
    result=bytearray(data)
    for extent in ranges:
        lo=max(offset,extent['offset']);hi=min(offset+len(result),extent['offset']+extent['bytes'])
        if lo<hi:result[lo-offset:hi-offset]=read_at(baseline,lo,hi-lo)
    return result


def readback(root, device, mode, receipt):
    """Read-only USB verification; no USB export, mode switch or disk write."""
    import stat
    from datetime import datetime, timezone
    root=root.resolve();receipt=receipt.resolve()
    need(root not in receipt.parents and not receipt.exists(),'receipt must be a new file outside sealed packet')
    verify(root)
    packet=json.loads((root/'packet.json').read_text())
    path=device.resolve();name=path.name
    need(path.parent==Path('/dev') and re.fullmatch('sd[a-z]+',name) and stat.S_ISBLK(path.stat().st_mode),'whole USB block device required')
    sys=Path('/sys/class/block')/name
    need(int((sys/'size').read_text())*512==DISK_BYTES,'device capacity mismatch')
    ancestry=(sys/'device').resolve();found=False
    for parent in (ancestry,*ancestry.parents):
        try:
            if ((parent/'idVendor').read_text().strip(),(parent/'idProduct').read_text().strip(),(parent/'serial').read_text().strip())==('1f3a','1010',packet['usb_serial']):found=True
        except OSError:pass
    need(found,'board USB identity mismatch')
    nodes=[p for p in Path('/sys/class/block').iterdir() if p.name==name or re.fullmatch(re.escape(name)+'[0-9]+',p.name)]
    need(len(nodes)==28 and all((p/'ro').read_text().strip()=='1' for p in nodes),'disk/partitions must all be enforced read-only')
    nums={(p/'dev').read_text().strip() for p in nodes}
    need(not any(line.split()[2] in nums for line in Path('/proc/self/mountinfo').read_text().splitlines()),'board partition is mounted')
    expected=json.loads((root/'readback'/('baseline.json' if mode=='recovery' else mode+'.json')).read_text())
    fd=os.open(path,os.O_RDONLY|os.O_CLOEXEC|os.O_DIRECT);memory=mmap.mmap(-1,CHUNK);view=memoryview(memory)
    whole=hashlib.sha256();checked=hashlib.sha256();ranges=packet['phases']['rollback'] if mode=='recovery' else []
    try:
        with (root/'baseline/emmc-user-area.img').open('rb') as baseline:
            for i,p in enumerate(expected['chunks']):
                n=p['bytes'];need(os.preadv(fd,[view[:n]],p['offset'])==n,'short direct device read')
                data=bytearray(view[:n]);whole.update(data)
                if ranges:data=mask_recovery(data,p['offset'],ranges,baseline)
                need(hashlib.sha256(data).hexdigest()==p['sha256'],'device mismatch at byte '+str(p['offset']))
                checked.update(data)
                if (i+1)%16==0 or i+1==len(expected['chunks']):print(json.dumps(dict(mode=mode,bytes=p['offset']+n,total=DISK_BYTES)),flush=True)
        need(checked.hexdigest()==expected['sha256'],'whole readback mismatch')
        result=dict(status='PASS read-only device verification',mode=mode,packet_sha256=sha(root/'packet.json'),
                    utc=datetime.now(timezone.utc).isoformat(),host_boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
                    actual_device_sha256=whole.hexdigest(),compared_sha256=checked.hexdigest(),bytes=DISK_BYTES,
                    protected_only=(mode=='recovery'),device_storage_writes=False)
        with receipt.open('x') as f:json.dump(result,f,indent=2);f.write('\n')
        return result
    finally:view.release();memory.close();os.close(fd)


def main():
    parser=argparse.ArgumentParser(description=__doc__);sub=parser.add_subparsers(dest='command',required=True)
    p=sub.add_parser('prepare')
    for name in ('candidate','backup','identity-evidence','rescue-spl','fel-tool','output'):p.add_argument('--'+name,required=True,type=Path)
    p=sub.add_parser('verify');p.add_argument('--packet',required=True,type=Path)
    p=sub.add_parser('readback');p.add_argument('--packet',required=True,type=Path);p.add_argument('--device',required=True,type=Path)
    p.add_argument('--mode',required=True,choices=('baseline','install','rollback','recovery'));p.add_argument('--receipt',required=True,type=Path)
    a=parser.parse_args()
    if a.command=='prepare':
        result=prepare(a.candidate,a.backup,a.identity_evidence,a.rescue_spl,a.fel_tool,a.output)
        print(json.dumps(dict(status='PREPARED ONLY; no live hardware actions',output=str(a.output.resolve()),baseline_sha256=result['baseline_sha256']),indent=2))
    elif a.command=='verify':print(json.dumps(verify(a.packet),indent=2))
    else:print(json.dumps(readback(a.packet,a.device,a.mode,a.receipt),indent=2))

if __name__=='__main__':main()
