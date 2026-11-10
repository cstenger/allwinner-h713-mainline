#!/usr/bin/env python3
"""Build a private, boot-bound SCP sampler package offline. Never contact hardware."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import secrets
import shutil
import struct

ROOT = Path(__file__).resolve().parents[3]
ENTRY, GUARD = 0x4404, 0x4414
A, A_END, B, B_END = 0x4ac0, 0x4c00, 0x4da0, 0x4f00
OUT, SAVED = 0x4f80, 0x4fd8
REGS = [0x07091014, 0x07091b00, 0x07091b04, 0x07091b08,
        0x07091020, 0x07091030, 0x07091034, 0x07091038,
        0x07091c00, 0x07091c04, 0x07091d00, 0x07091d04,
        0x07091e00, 0x07091e04]
ORIGINAL, NOP, MARKER = 0x84830010, 0x15000000, 0x48444d49
SR_UNSAFE = 0x17e  # cache, MMU, interrupt and shadow-context enables


def sha(data):
    return hashlib.sha256(data).hexdigest()


def require(ok,message):
    if not ok:raise ValueError(message)


def original_invariants(words):
    """R0 is software zero and R13 is unused in ALL original paths."""
    used=set();writes_zero=[]
    for index,insn in enumerate(words):
        op=insn>>26;d=(insn>>21)&31;a=(insn>>16)&31;b=(insn>>11)&31
        if insn==NOP or op in [0,3,4]:continue
        if op==6:
            used.add(d)
            if d==0:writes_zero.append((index,insn))
        elif op in [0x2a,0x27,0x21]:
            used.update([d,a])
            if d==0:writes_zero.append((index,insn))
        elif op==0x35:used.update([a,b])
        elif op==0x2f:used.add(a)
        elif op==0x39:used.update([a,b])
        elif op==0x38:
            used.update([d,a,b])
            if d==0:writes_zero.append((index,insn))
        else:raise ValueError('unreviewed original opcode: '+hex(insn))
    require(13 not in used,'bootstrap spare register is used by original firmware')
    require(writes_zero==[(0,0x18000000)],'original R0 invariant changed')
    return dict(r0_initialized_to_zero_and_never_rewritten=True,r13_unused_in_all_original_paths=True)


def elf_section(data,name):
    require(data[:6]==b'\x7fELF\x02\x01','expected ELF64 little-endian image')
    offset=struct.unpack_from('<Q',data,40)[0]
    size,count,strings=struct.unpack_from('<HHH',data,58)
    require(size==64,'unexpected ELF section header')
    headers=[struct.unpack_from('<IIQQQQIIQQ',data,offset+i*size) for i in range(count)]
    table=headers[strings];names=data[table[4]:table[4]+table[5]]
    for h in headers:
        if names[h[0]:].split(b'\0',1)[0].decode()==name:return data[h[4]:h[4]+h[5]]
    raise ValueError('missing ELF section '+name)


def sw(base, reg, offset):
    return 0xd4000000 | ((offset >> 11) << 21) | (base << 16) | (reg << 11) | (offset & 2047)


def payload(nonce):
    words, listing, labels, fixups = [], [], {}, []
    def emit(word, description):
        words.append(word); listing.append(description)
    def label(name): labels[name] = len(words)
    def ori(d, a, n): emit(0xa8000000 | d << 21 | a << 16 | n, f'l.ori r{d},r{a},0x{n:x}')
    def constant(d, n):
        emit(0x18000000 | d << 21 | n >> 16, f'l.movhi r{d},0x{n>>16:x}')
        ori(d, d, n & 65535)
    def load(d, a, n): emit(0x84000000 | d << 21 | a << 16 | n, f'l.lwz r{d},0x{n:x}(r{a})')
    def store(a, r, n): emit(sw(a, r, n), f'l.sw 0x{n:x}(r{a}),r{r}')
    def ne(a, b): emit(0xe4200000 | a << 16 | b << 11, f'l.sfne r{a},r{b}')
    def nei(a, n): emit(0xbc200000 | a << 16 | n, f'l.sfnei r{a},{n}')
    def branch(op, target):
        fixups.append((len(words), op, target)); emit(0, f'branch{op} {target}'); emit(NOP, 'l.nop (delay)')
    def sync(): emit(0x22000000, 'l.msync')
    nei(0, 0); branch(4, 'bad_zero')
    emit(0x22800000, 'l.psync (discard bootstrap prefetch)')
    load(13, 0, OUT+116)  # restore the spare register used by the bootstrap
    for i, reg in enumerate([3, 4, 5, 10, 11]): store(0, reg, SAVED+4*i)
    ori(3, 0, OUT)
    emit(0xb4800011, 'l.mfspr r4,r0,SPR_SR')
    store(3, 4, 8)
    emit(0xa4a40000 | SR_UNSAFE, f'l.andi r5,r4,0x{SR_UNSAFE:x}')
    nei(5, 0); branch(4, 'error')
    emit(0xa4a40001, 'l.andi r5,r4,1')
    nei(5, 1); branch(4, 'error')
    load(4, 0, SAVED); nei(4, 0x4f00); branch(4, 'error')
    constant(4, MARKER); ne(10, 4); branch(4, 'error')
    constant(5, 0x07090000); ne(11, 5); branch(4, 'error')
    constant(10, nonce)
    # Echo BEFORE entry publication. A challenge issued after entry/done
    # can only be echoed by a later original-loop re-entry with valid context.
    load(4, 3, 16); sync(); store(3, 4, 112)
    sync(); store(3, 10, 4)
    load(4, 3, 0); nei(4, 0); branch(3, 'return')
    nei(4, 1); branch(4, 'error')
    store(3, 0, 0); sync()  # consume request before any peripheral load
    load(4, 3, 28); nei(4, 0); branch(4, 'error')
    store(3, 10, 28); sync()  # one-shot latch, also retained on a stalled load
    for i, address in enumerate(REGS):
        ori(4, 0, i+1); store(3, 4, 24)
        ori(5, 11, address & 65535); load(4, 5, 0); store(3, 4, 32+4*i)
    # Completion is DATA completion only. Host changes its challenge after
    # seeing done; the echo handler is reached again only after original-loop
    # return, context restore, and re-entry validation.
    sync(); store(3, 10, 12); branch(0, 'return')
    label('error'); ori(4, 0, 1); store(3, 4, 20)
    label('return')
    for i, reg in enumerate([3, 4, 5, 10, 11]): load(reg, 0, SAVED+4*i)
    load(4, 3, 16)  # execute the displaced original load before its sfnei
    branch(0, ENTRY+4)
    label('bad_zero'); branch(0, 'bad_zero')
    cut = 78
    if any(site == cut-1 for site, _, _ in fixups): cut -= 1
    def address(index): return A+4*index if index < cut else B+4*(index-cut)
    for index, op, target in fixups:
        dest = address(labels[target]) if isinstance(target, str) else target
        words[index] = op << 26 | (((dest-address(index))//4) & 0x3ffffff)
    bridge_pc = A+4*cut
    first = words[:cut]+[((B-bridge_pc)//4) & 0x3ffffff, NOP]
    first += [NOP]*(80-len(first))
    second = words[cut:]
    assert len(second)*4 <= B_END-B, f'monitor too large: {len(words)} instructions'
    listing_text = '\n'.join(f'{address(i):04x} {word:08x} {listing[i]}' for i, word in enumerate(words))+'\n'
    listing_text += f'{bridge_pc:04x} {first[cut]:08x} l.j 0x{B:x} (fragment bridge)\n'
    return first, second, ((A-ENTRY)//4) & 0x3ffffff, listing_text


def build(snapshot, identity, output):
    if output.exists(): raise ValueError('output already exists')
    x = json.loads(snapshot.read_text()); sram = bytes.fromhex(x['sram_hex'])
    ident = json.loads(identity.read_text())
    require(ident['boot_id'] == '2d8c3970-4164-4a38-8e86-375bb440c971','wrong boot')
    require(ident['kernel_build_ids'] == ['66f8c0b7121b03985b8cc8aa2f03da135fbdca2b'],'wrong kernel build')
    require(ident['owner_sha256'] == '0a6987ced911cc12f2a36ff2a9550e397c1c0f5889f4b65e8453b298cefe4497','wrong owner')
    owner_bytes=(ROOT/'build/hdmi-startup-signal-owner/h713-hdmi-signal.ko').read_bytes()
    require(sha(owner_bytes)==ident['owner_sha256'],'local owner differs')
    require(sha(elf_section(owner_bytes,'.note.gnu.build-id'))==ident['owner_note_sha256'],'loaded owner build ID differs from file')
    require(len(sram) == 0x5000,'wrong SRAM size')
    require(struct.unpack_from('<4I', sram, ENTRY) == (ORIGINAL, 0xbc240000, 0x0ffffffe, NOP),'wrong wait loop')
    header = (ROOT/'modules/hdmi-signal/edid-trial-code.h').read_text().split('static const u32 edid_trial_code[] = {', 1)[1].split('};', 1)[0]
    original_code = [int(v, 16) for v in re.findall(r'^\s*0x([0-9a-f]{8}),', header, re.M)]
    require(sram[0x4000:0x4000+4*len(original_code)] == struct.pack('<'+'I'*len(original_code), *original_code),'original code mismatch')
    invariants=original_invariants(original_code)
    require(x['scp_marker']['stop_request'] == x['scp_marker']['exception'] == x['scp_marker']['error'] == x['scp_marker']['done'] == '0x0','owner not in safe wait state')
    nonce = 0x5a000000 | secrets.randbits(24)
    first, second, hook, listing = payload(nonce)
    output.mkdir(mode=0o700, parents=True)
    def save(name, data): (output/name).write_bytes(data)
    save('baseline-sram.bin', sram)
    save('fragment-a.bin', struct.pack('<'+'I'*len(first), *first))
    save('fragment-b.bin', struct.pack('<'+'I'*len(second), *second))
    save('listing.txt', listing.encode())
    manifest = dict(schema='h713-scp-sampler-v2', prepared_only=True, hardware_execution_authorized=False,
                    nonce=nonce, identity=ident, baseline_sram_sha256=sha(sram), entry=ENTRY, guard=GUARD,
                    hook=hook, original_instruction=ORIGINAL,
                    initial_challenge=nonce^0x13579bdf,post_challenge=nonce^0x2468ace0,
                    fragments=[dict(offset=A, file='fragment-a.bin', bytes=4*len(first)), dict(offset=B, file='fragment-b.bin', bytes=4*len(second))],
                    output=OUT, saved=SAVED, read_registers=REGS, sr_unsafe_mask=SR_UNSAFE,
                    resident_scratch=True, automatic_release=False, resets=False, peripheral_writes=False,
                    runtime_entry_and_return_handshakes_required=True)
    manifest['bootstrap']=dict(**invariants,cache_state_observed_before_scratch_branch=True,
                              spare_register=13,spare_register_restored=True,peripheral_accesses=0)
    (output/'manifest.json').write_text(json.dumps(manifest, indent=2)+'\n')
    def array(name, values):
        return 'static const unsigned int '+name+'[] = {\n'+''.join('  '+','.join(f'0x{v:08x}u' for v in values[i:i+8])+',\n' for i in range(0, len(values), 8))+'};\n'
    generated = f'#define SCPS_NONCE 0x{nonce:08x}u\n#define SCPS_HOOK 0x{hook:08x}u\n'
    generated += f'#define SCPS_GUARD_RELEASE 0x{((A-GUARD)//4)&0x3ffffff:08x}u\n'
    generated += f'#define SCPS_INITIAL_CHALLENGE 0x{nonce^0x13579bdf:08x}u\n#define SCPS_POST_CHALLENGE 0x{nonce^0x2468ace0:08x}u\n'
    generated += array('scps_baseline', list(struct.unpack('<5120I', sram)))
    generated += array('scps_fragment_a', first)+array('scps_fragment_b', second)
    save('generated.h', generated.encode())
    for name in ['core.h', 'owner.h', 'module.c', 'Makefile', 'model.py', 'test.py', 'capture.py','remote_test.py','README.md']:
        source = Path(__file__).with_name(name)
        if source.exists(): shutil.copyfile(source, output/name)
    shutil.copyfile(__file__, output/'build.py')
    print(json.dumps(dict(status='resident monitor generated offline',nonce=nonce,instructions=len(first)+len(second),hardware_write=False),indent=2))


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--snapshot', required=True, type=Path); p.add_argument('--identity', required=True, type=Path)
    p.add_argument('--output', required=True, type=Path)
    a = p.parse_args(); build(a.snapshot, a.identity, a.output)
