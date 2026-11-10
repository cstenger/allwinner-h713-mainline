#!/usr/bin/env python3
"""Run the vendor's AV1 decoder (libawav1.so) end to end in the emulator and
capture, for every frame, the register image it would start the hardware with
and the DMA buffers those registers point at.

The hardware never runs: VP9DecEControl::Start -- where the vendor hands its
register sets to a thread that flushes them to MMIO -- is intercepted, the
sets are saved, and the call returns as if the thread had been started. The
Android services the library expects (CedarC memory adapter, VE ops, frame
buffer manager, stream buffer) are faked in Python with identity "physical"
addresses, so every address in a captured register is an emulator address
whose contents can be dumped.

    vendor-decode.py stream.ivf OUTDIR [max_frames]

Writes OUTDIR/frameNNN.setK.regs (the 1168-byte image; the vendor's packed
struct is its first 0x488 bytes) and OUTDIR/frameNNN.<buffer>.bin for each non-zero *_base.
"""
import os, struct, sys
here = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(here, '..'))
from awemu import Lib
from unicorn.arm_const import UC_ARM_REG_PC, UC_ARM_REG_LR

LIB = os.environ.get('AV1_LIB', os.path.join(here, '../../../local/h713-lab/ve-extract/libs/libawav1.so'))
VERBOSE = int(os.environ.get('VERBOSE', '1'))
CORE_ID = 0x0003b16d
CFG_WORD = 0x22                       # decoder_cfg | av1_baseline_cfg

FIELDS = {}
for l in open(os.path.join(here, 'swregisters-bits.txt')):
    f = l.split()
    if f[3] != 'NONE':
        FIELDS[f[0]] = (int(f[3]), int(f[1]))


def ivf_frames(path):
    d = open(path, 'rb').read()
    assert d[:4] == b'DKIF', 'not an IVF file'
    o = struct.unpack_from('<H', d, 6)[0]
    w, h = struct.unpack_from('<HH', d, 12)
    frames = []
    while o + 12 <= len(d):
        n = struct.unpack_from('<I', d, o)[0]
        frames.append(d[o + 12:o + 12 + n]); o += 12 + n
    return w, h, frames


class Harness:
    def __init__(self, stream, outdir, max_frames):
        self.w, self.h, self.frames = ivf_frames(stream)
        self.frames = self.frames[:max_frames]
        self.outdir = outdir
        os.makedirs(outdir, exist_ok=True)
        self.L = L = Lib(LIB, log=self.log, heap=0x2f000000)
        self.sizes = {}
        self.captured = 0
        self.unknown = set()
        self._stubs()
        self.mmio = L.add_mmio('av1', 0x1000)
        L.wr(self.mmio, CORE_ID); L.wr(self.mmio + 4, CFG_WORD)
        self._tables()
        self._sbm()
        L.intercept('_ZNK14VP9DecEControl5StartEPvPKN6taffel6ctypes11SwRegistersEiPS0_', self.start)

    def log(self, *a):
        if VERBOSE > 1 or (VERBOSE and a and a[0] == 'LOG'):
            print(*a)

    # ---- memory -------------------------------------------------------
    def alloc(self, n):
        a = self.L.alloc(max(n, 1), 64)
        self.sizes[a] = n
        return a

    # ---- printf-style formatting for the library's own logs ----------
    def fmt(self, fmt, args):
        out, i, ai = [], 0, 0
        while i < len(fmt):
            c = fmt[i]
            if c != '%':
                out.append(c); i += 1; continue
            j = i + 1
            while j < len(fmt) and fmt[j] in '0123456789.-+ #lhzjt':
                j += 1
            conv = fmt[j] if j < len(fmt) else ''
            spec = fmt[i:j + 1]
            if conv == '%':
                out.append('%')
            elif conv == 's':
                out.append(self.L.cstr(args(ai)) if args(ai) else '(null)'); ai += 1
            elif conv in 'duixXpc':
                v = args(ai); ai += 1
                if 'll' in spec:
                    ai += ai & 1 == 0 and 0  # 64-bit args are pair-aligned; approximate
                    v |= args(ai) << 32; ai += 1
                if conv in 'di' and v & 0x80000000 and 'll' not in spec:
                    v -= 1 << 32
                out.append({'x': f'{v:x}', 'X': f'{v:X}', 'p': f'{v:#x}', 'c': chr(v & 0xff)}.get(conv, str(v)))
            elif conv in 'fg':
                out.append('<f>'); ai += 2
            else:
                out.append(spec)
            i = j + 1
        return ''.join(out)

    def varargs(self, regs, first):
        L = self.L
        def get(i):
            k = first + i
            return regs[k] if k < 4 else L.stack_arg(k - 4)
        return get

    def _stubs(self):
        L, E = self.L, self.L.extern
        mem = lambda lib, r: None
        def new(lib, r): return self.alloc(r[0])
        def calloc(lib, r): return self.alloc(r[0] * r[1])
        def realloc(lib, r):
            a = self.alloc(r[1])
            if r[0]:
                n = min(self.sizes.get(r[0], r[1]), r[1])
                lib.uc.mem_write(a, bytes(lib.uc.mem_read(r[0], n)))
            return a
        def memmove(lib, r):
            lib.uc.mem_write(r[0], bytes(lib.uc.mem_read(r[1], r[2]))); return r[0]
        def memset_chk(lib, r):
            lib.uc.mem_write(r[0], bytes([r[1] & 0xff]) * r[2]); return r[0]
        def memcmp(lib, r):
            a, b = bytes(lib.uc.mem_read(r[0], r[2])), bytes(lib.uc.mem_read(r[1], r[2]))
            return 0 if a == b else (1 if a > b else -1)
        def strlen(lib, r): return len(lib.cstr(r[0]))
        def strcmp(lib, r):
            a, b = lib.cstr(r[0]), lib.cstr(r[1]); return 0 if a == b else (1 if a > b else -1)
        def alog(lib, r):
            self.log('LOG', self.fmt(lib.cstr(r[2]), self.varargs(r, 3)).rstrip())
        def printf(lib, r):
            if VERBOSE: print('printf', self.fmt(lib.cstr(r[0]), self.varargs(r, 1)).rstrip())
        def puts(lib, r):
            if VERBOSE: print('puts', lib.cstr(r[0]))
        def guard_acq(lib, r): return 1 if lib.rd(r[0], 1) == 0 else 0
        def guard_rel(lib, r): lib.wr(r[0], 1, 1)
        def boom(lib, r): raise RuntimeError('library aborted / threw')
        keys = {}
        def key_create(lib, r):
            k = len(keys) + 1; keys[k] = 0; lib.wr(r[0], k); return 0
        def getspec(lib, r): return keys.get(r[0], 0)
        def setspec(lib, r): keys[r[0]] = r[1]; return 0
        def this(lib, r): return r[0]
        for n in ('_Znwj', '_Znaj', 'cdc_malloc'): E[n] = new
        for n in ('cdc_calloc', 'calloc'): E[n] = calloc
        E['realloc'] = realloc
        for n in ('memmove',): E[n] = memmove
        E['__memset_chk'] = memset_chk
        E['memcmp'] = memcmp
        for n in ('strlen', '__strlen_chk'): E[n] = strlen
        E['strcmp'] = strcmp
        E['__android_log_print'] = alog
        for n in ('printf', 'fprintf'): E[n] = printf if n == 'printf' else (lambda lib, r: None)
        E['puts'] = puts
        E['__cxa_guard_acquire'] = guard_acq
        E['__cxa_guard_release'] = guard_rel
        for n in ('__cxa_throw', '_ZSt9terminatev', 'abort', 'exit', '__cxa_allocate_exception'):
            E[n] = boom
        E['pthread_key_create'] = key_create
        E['pthread_getspecific'] = getspec
        E['pthread_setspecific'] = setspec
        for n in ('_ZdlPv', '_ZdaPv', 'cdc_free'):
            E[n] = mem
        for n in ('pthread_mutex_init', 'pthread_mutex_lock', 'pthread_mutex_unlock',
                  'pthread_mutex_destroy', 'pthread_cond_init', 'pthread_cond_signal',
                  'pthread_cond_destroy', 'VDecoderRegister', 'srand', 'rand', 'sched_yield'):
            E[n] = lambda lib, r: 0
        E['access'] = E['open'] = lambda lib, r: 0xffffffff
        E['fopen'] = lambda lib, r: 0
        # C++ runtime pieces whose effect we do not need: return `this`
        for y in L.stubs.values():
            if y.startswith('_ZNSt3__1') or y.startswith('_ZThn') or y.startswith('_ZTv'):
                E.setdefault(y, this)
        E['GetVeOpsS'] = lambda lib, r: self.veops
        E['MemAdapterGetOpsS'] = lambda lib, r: self.memops
        E['FbmCreate'] = self.fbm_create
        E['FbmRequestBuffer'] = self.fbm_request
        E['FbmReturnBuffer'] = self.fbm_return
        E['FbmDestroy'] = lambda lib, r: 0

    # ---- CedarC service tables ---------------------------------------
    def table(self, name, impls, n=40):
        t = self.L.alloc(4 * n)
        for i in range(n):
            f = impls.get(i)
            if f is None:
                f = (lambda k: lambda lib, r: self.unk(f'{name}[{k:#x}]', r))(4 * i)
            self.L.wr(t + 4 * i, self.L.add_stub(f'{name}{i}', f))
        return t

    def unk(self, what, r):
        if what not in self.unknown:
            self.unknown.add(what)
            print('  (unhandled call', what, [hex(x) for x in r], ')')
        return 0

    def _tables(self):
        ident = lambda lib, r: r[0]
        def palloc(lib, r): return self.alloc(r[0])
        def memset_(lib, r): lib.uc.mem_write(r[0], bytes([r[1] & 0xff]) * r[2]); return 0
        def memcpy_(lib, r): lib.uc.mem_write(r[0], bytes(lib.uc.mem_read(r[1], r[2]))); return 0
        self.memops = self.table('memops', {
            0: lambda lib, r: 0, 1: lambda lib, r: 0, 2: lambda lib, r: 0x10000000,
            4: palloc, 5: palloc, 6: lambda lib, r: 0, 7: lambda lib, r: 0,
            8: ident, 9: ident, 10: ident, 11: ident,
            12: memset_, 13: memcpy_, 14: memcpy_, 15: memcpy_})
        self.veself = self.L.alloc(0x100)
        def regbase(lib, r):
            print(f'  veops getRegBase(group={r[1]}) -> AV1 window')
            return self.mmio
        self.veops = self.table('veops', {
            0: lambda lib, r: self.veself, 1: lambda lib, r: 0,
            2: lambda lib, r: 0, 3: lambda lib, r: 0, 4: lambda lib, r: 0,
            5: lambda lib, r: 0, 8: regbase})

    # ---- frame buffer manager ---------------------------------------
    def fbm_create(self, lib, r):
        self.fbm_pics = []
        self.fbm_out = []
        return self.alloc(0x100)

    def fbm_request(self, lib, r):
        L = self.L
        w, h = (self.w + 63) & ~63, (self.h + 63) & ~63
        pic = self.alloc(0x200)
        y = self.alloc(w * h * 3 // 2 + 0x10000)
        L.wr(pic + 0x0c, self.w); L.wr(pic + 0x10, self.h); L.wr(pic + 0x14, w)
        L.wr(pic + 0x50, y); L.wr(pic + 0x54, y + w * h)
        L.wr(pic + 0x74, y); L.wr(pic + 0x78, y + w * h)
        L.wr(pic + 0x70, len(self.fbm_pics))
        self.fbm_pics.append(pic)
        return pic

    def fbm_return(self, lib, r):
        self.fbm_out.append((r[1], r[2]))
        return 0

    # ---- stream buffer ----------------------------------------------
    def _sbm(self):
        L = self.L
        self.ring_sz = 8 << 20
        self.ring = self.alloc(self.ring_sz)
        self.next_frame = 0
        self.sbm = L.alloc(0x100)
        self.info = L.alloc(0x40)
        pos = [0]
        def request(lib, r):
            if self.next_frame >= len(self.frames):
                return 0
            data = self.frames[self.next_frame]
            if pos[0] + len(data) > self.ring_sz:
                pos[0] = 0
            a = self.ring + pos[0]
            L.uc.mem_write(a, data)
            pos[0] += (len(data) + 0x3ff) & ~0x3ff
            L.uc.mem_write(self.info, b'\0' * 0x40)
            L.wr(self.info, a); L.wr(self.info + 4, len(data))
            L.wr(self.info + 8, self.next_frame * 33333)
            self.next_frame += 1
            return self.info
        entries = {0xc: lambda lib, r: self.ring, 0x10: lambda lib, r: self.ring_sz,
                   0x24: request, 0x28: lambda lib, r: 0, 0x2c: lambda lib, r: 0}
        for off in range(0, 0x60, 4):
            f = entries.get(off, (lambda k: lambda lib, r: self.unk(f'sbm[{k:#x}]', r))(off))
            L.wr(self.sbm + off, L.add_stub(f'sbm{off:x}', f))

    # ---- the capture ------------------------------------------------
    def start(self, lib, r):
        """VP9DecEControl::Start(this, cwl, const SwRegisters *regs, int n, void **handle)"""
        L = self.L
        regs, n, handle = r[2], r[3], L.stack_arg(0)
        blk = self.alloc(0x4948)
        L.wr(blk + 0x44, n)
        fr = self.captured
        for i in range(n):
            body = bytes(L.uc.mem_read(regs + i * 0x488, 0x488))
            L.uc.mem_write(blk + 0x48 + i * 0x490, body)
            # the packed struct is image[0:0x488]; the last two words are not in it
            img = body + b'\0' * 8
            open(os.path.join(self.outdir, f'frame{fr:03d}.set{i}.regs'), 'wb').write(img)
            if i == 0:
                self.dump_buffers(fr, img)
        L.wr(handle, blk)
        self.captured += 1
        print(f'captured frame {fr}: {n} register set(s)')
        return 0

    def field(self, img, name):
        lo, w = FIELDS[name]
        return (int.from_bytes(img, 'little') >> lo) & ((1 << w) - 1)

    def dump_buffers(self, fr, img):
        """Write a replay package: every allocation a *_base field points into
        (whole, once), and for each field the allocation and offset, so the
        image can be relocated to real IOVAs. frameNNN.json + frameNNN.allocK.bin"""
        import json
        L = self.L
        allocs, relocs = [], []
        index = {}
        for name in FIELDS:
            if not name.endswith('_base'):
                continue
            a = self.field(img, name)
            if not a:
                continue
            base = max((b for b in self.sizes if b <= a), default=None)
            if base is None or a >= base + self.sizes[base]:
                print(f'  {name} = {a:#x} is not inside any allocation')
                continue
            if base not in index:
                index[base] = len(allocs)
                size = self.sizes[base]
                fn = f'frame{fr:03d}.alloc{len(allocs)}.bin'
                open(os.path.join(self.outdir, fn), 'wb').write(bytes(L.uc.mem_read(base, size)))
                allocs.append({'file': fn, 'size': size, 'emu_base': base})
            lo, w = FIELDS[name]
            relocs.append({'field': name, 'lo': lo, 'width': w,
                           'alloc': index[base], 'offset': a - base})
        json.dump({'frame': fr, 'regs': f'frame{fr:03d}.set0.regs',
                   'allocs': allocs, 'relocs': relocs},
                  open(os.path.join(self.outdir, f'frame{fr:03d}.json'), 'w'), indent=1)

    # ---- drive the plugin -------------------------------------------
    def run(self):
        L = self.L
        L.wr(L.data_imports.get('GLOBAL_CDC_LOG_LEVEL', L.alloc(4)), 2 if VERBOSE > 1 else 5)
        ve = L.alloc(0x200)
        dec = L.call('_Z16CreateAv1DecoderP11VIDEOENGINE', ve)
        vt = [L.rd(dec + 4 * i) for i in range(7)]
        print('decoder', hex(dec), 'vtable', [hex(x) for x in vt])
        cfg = L.alloc(0xb4)
        L.wr(cfg + 0x70, self.memops); L.wr(cfg + 0x7c, self.veops); L.wr(cfg + 0x80, self.veself)
        info = L.alloc(0x100)
        L.wr(info + 4, self.w); L.wr(info + 8, self.h)
        rc = L.call(vt[0], dec, cfg, info, L.alloc(0x100))
        print('init ->', rc)
        rc = L.call(vt[2], dec, self.sbm, 0)
        print('setSbm ->', rc)
        for step in range(len(self.frames) * 8 + 16):
            rc = L.call(vt[5], dec, 0, max_insns=200_000_000)
            if VERBOSE > 1:
                print('decode ->', rc)
            if self.next_frame >= len(self.frames) and rc in (5, 0xffffffff):
                break
        print(f'done: {self.captured} frame(s) captured, {len(self.fbm_out)} returned to FBM')


if __name__ == '__main__':
    Harness(sys.argv[1], sys.argv[2], int(sys.argv[3]) if len(sys.argv) > 3 else 5).run()
