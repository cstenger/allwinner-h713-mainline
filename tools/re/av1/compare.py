#!/usr/bin/env python3
"""Compare the H713 AV1 register generator (host rig output) with the vendor
library (vendor-decode.py output), frame by frame.

    compare.py VENDOR_DIR RIG_DIR [frames] [--all]

Registers: every named field except addresses (*_base, *_msb) and the ones a
real run fills in afterwards (hardware statistics). Buffers: the CPU-written
ones, byte for byte -- probabilities, global model, tile info, film grain.
pdec_config: every non-address field; addresses structurally (plane 0 is the
reference's rec/header base from the main image, planes 1/2 at the same
offsets as the vendor's). The vendor's plane 1/2 header bases lag a frame
(it fills them before plane 0), so those are not compared.
"""
import json, os, sys

here = os.path.dirname(os.path.abspath(__file__))
F = {}
for l in open(os.path.join(here, 'swregisters-bits.txt')):
    f = l.split()
    if f[3] != 'NONE':
        F[f[0][3:]] = (int(f[3]), int(f[1]))

SKIP_SUFFIX = ('_base', '_msb')
HW_OUTPUT = ('count', 'hw_cycles', '_bw', 'irq', 'used_hw')
# Fields the vendor leaves stale from an earlier frame while the frame header
# switches their feature off: compared only when the (vendor's) switch is on.
DONT_CARE = {
    'base_lf_level_2': ('filtering_dis', 0), 'base_lf_level_3': ('filtering_dis', 0),
    'skip_ref0': ('skip_mode_flag', 1), 'skip_ref1': ('skip_mode_flag', 1),
    'delta_q_res_log': ('delta_q_present', 1),
}
DONT_CARE.update({k: ('apply_grain', 1) for k in (
    'cb_luma_mult', 'cb_mult', 'cb_offset', 'chroma_scaling_from_luma',
    'clip_to_restricted_range', 'cr_luma_mult', 'cr_mult', 'cr_offset',
    'num_cb_points_b', 'num_cr_points_b', 'num_y_points_b', 'overlap_flag',
    'random_seed', 'scaling_shift')})


def cares(k, v):
    return k not in DONT_CARE or v[DONT_CARE[k][0]] == DONT_CARE[k][1]


P = {}
for l in open(os.path.join(here, 'pdecswregs-bits.txt')):
    f = l.split()
    if f[3] != 'NONE':
        P[f[0][3:]] = (int(f[3]), int(f[1]))


def fields(path, table=F, data=None):
    v = int.from_bytes(data if data is not None else open(path, 'rb').read(), 'little')
    return {n: (v >> lo) & ((1 << w) - 1) for n, (lo, w) in table.items()}


def pdec_diffs(vregs, rregs, vb, rb):
    """Differences between two pdec configs; [] if equal."""
    v, r = fields(None, P, vb[:496]), fields(None, P, rb[:496])
    out = [(k, v[k], r[k]) for k in P if not k.endswith(SKIP_SUFFIX) and v[k] != r[k]]
    allbits = sum(((1 << w) - 1) << lo for lo, w in P.values())
    cv = int.from_bytes(vb[:496], 'little') & ~allbits
    cr = int.from_bytes(rb[:496], 'little') & ~allbits
    if cv != cr:
        out.append(('(constant bits)', cv, cr))
    for i in range(7):
        for regs, pd, who in ((vregs, v, 'vendor'), (rregs, r, 'rig')):
            if pd[f'in{i}_plane0_strm_base'] != regs[f'ref{i}_lum_base']:
                out.append((f'in{i}_plane0_strm_base != ref{i}_lum_base ({who})',
                            pd[f'in{i}_plane0_strm_base'], regs[f'ref{i}_lum_base']))
            if pd[f'in{i}_plane0_hdr_base'] != regs[f'ref{i}_cb_base']:
                out.append((f'in{i}_plane0_hdr_base != ref{i}_cb_base ({who})',
                            pd[f'in{i}_plane0_hdr_base'], regs[f'ref{i}_cb_base']))
        for pl in (1, 2):
            dv = v[f'in{i}_plane{pl}_strm_base'] - v[f'in{i}_plane0_strm_base']
            dr = r[f'in{i}_plane{pl}_strm_base'] - r[f'in{i}_plane0_strm_base']
            if dv != dr:
                out.append((f'in{i}_plane{pl}_strm offset', dv, dr))
    return out


def vendor_buffer(vdir, fr, field):
    m = json.load(open(os.path.join(vdir, f'frame{fr:03d}.json')))
    for r in m['relocs']:
        if r['field'] == 'sw_' + field:
            a = m['allocs'][r['alloc']]
            d = open(os.path.join(vdir, a['file']), 'rb').read()
            return d[r['offset']:]
    return None


def main():
    vdir, rdir = sys.argv[1], sys.argv[2]
    n = int(sys.argv[3]) if len(sys.argv) > 3 and sys.argv[3].isdigit() else 10
    show_all = '--all' in sys.argv
    total = compared = 0
    for fr in range(n):
        vp = os.path.join(vdir, f'frame{fr:03d}.set0.regs')
        rp = os.path.join(rdir, f'frame{fr:03d}.regs')
        if not (os.path.exists(vp) and os.path.exists(rp)):
            break
        compared += 1
        v, r = fields(vp), fields(rp)
        # strm_start_pos is the tile data's offset in a 32-byte aligned
        # buffer, so it follows placement; what the hardware reads does not
        diffs = [(k, v[k], r[k]) for k in F
                 if not k.endswith(SKIP_SUFFIX) and not any(h in k for h in HW_OUTPUT)
                 and k not in ('strm_start_pos', 'stream_len')
                 and cares(k, v) and v[k] != r[k]]
        dv = v['stream_len'] - v['strm_start_pos']
        dr = r['stream_len'] - r['strm_start_pos']
        if dv != dr:
            diffs.append(('stream_len - strm_start_pos', dv, dr))
        bufs = []
        for field, name, size in (('prob_tab_base', 'prob.bin', 0x2fe0),
                                  ('global_model_base', 'gm.bin', 0xe0),
                                  ('tile_base', 'tile.bin', 0x500),
                                  ('film_grain_base', 'fg.bin', 0x3300)):
            vb = vendor_buffer(vdir, fr, field)
            rb = open(os.path.join(rdir, f'frame{fr:03d}.{name}'), 'rb').read()
            if vb is None:
                continue
            vb, rb = vb[:size], rb[:size]
            nd = sum(1 for a, b in zip(vb, rb) if a != b)
            first = next((i for i, (a, b) in enumerate(zip(vb, rb)) if a != b), None)
            bufs.append(f'{name}:{"OK" if not nd else f"{nd} B differ (first @{first:#x})"}')
            total += bool(nd)
        vp_ = vendor_buffer(vdir, fr, 'pdec_config_base')
        rp_ = os.path.join(rdir, f'frame{fr:03d}.pdec.bin')
        vregs, rregs = fields(vp), fields(rp)
        if vp_ is None and not rregs['pdec_config_base']:
            bufs.append('pdec:none')
        elif vp_ is None or not rregs['pdec_config_base']:
            bufs.append(f'pdec:vendor={"yes" if vp_ else "no"} rig={"yes" if rregs["pdec_config_base"] else "no"}')
            total += 1
        else:
            pd = pdec_diffs(vregs, rregs, vp_, open(rp_, 'rb').read())
            bufs.append('pdec:OK' if not pd else f'pdec:{len(pd)} differ')
            diffs += [('pdec.' + k, a, b) for k, a, b in pd]
        total += len(diffs)
        print(f'frame {fr}: {len(diffs)} field(s) differ; ' + '  '.join(bufs))
        for k, a, b in (diffs if show_all else diffs[:25]):
            print(f'    {k:40s} vendor={a:#x} rig={b:#x}')
        if not show_all and len(diffs) > 25:
            print(f'    ... {len(diffs) - 25} more')
    print(f'total differing fields: {total} over {compared} frame(s)')
    if compared != n:
        sys.exit(f'error: compared {compared} of {n} frame(s) -- missing captures or rig output')
    sys.exit(1 if total else 0)


if __name__ == '__main__':
    main()
