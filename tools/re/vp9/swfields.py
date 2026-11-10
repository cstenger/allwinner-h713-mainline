# Software probability context (ctx+0x3cb8) layout, from the emulated Vp9ResetProbs.
# (name, offset, dims, row_pad): row_pad = stored row width when rows are padded.
import itertools
SW = [('kf_y_mode', 0x000, (10, 10, 9), None), ('seg_tree', 0x387, (7,), None), ('seg_pred', 0x38e, (3,), None),
      ('kf_uv_mode', 0x397, (10, 9), None), ('inter_mode', 0x3fb, (7, 3), 4), ('is_inter', 0x417, (4,), None),
      ('tx8', 0x41b, (2, 1), None), ('tx16', 0x41d, (2, 2), None), ('tx32', 0x421, (2, 3), None),
      ('static14', 0x427, (14,), None), ('y_mode', 0x435, (4, 9), None), ('uv_mode', 0x459, (10, 9), None),
      ('kf_partition', 0x4b3, (16, 3), 4), ('partition', 0x4f3, (16, 3), 4), ('interp_filter', 0x533, (4, 2), None),
      ('comp_mode', 0x53b, (5,), None), ('skip', 0x540, (3,), None),
      ('mv.joint', 0x543, (3,), None), ('mv.sign', 0x546, (2,), None), ('mv.class0_bit', 0x548, (2,), None),
      ('mv.fr', 0x54a, (2, 3), None), ('mv.class0_hp', 0x550, (2,), None), ('mv.hp', 0x552, (2,), None),
      ('mv.classes', 0x554, (2, 10), None), ('mv.class0_fr', 0x568, (2, 2, 3), None), ('mv.bits', 0x574, (2, 10), None),
      ('single_ref', 0x588, (5, 2), None), ('comp_ref', 0x592, (5,), None), ('coef', 0x597, (4, 2, 2, 6, 6, 3), None)]

def name_of(off):
    for n, base, dims, pad in SW:
        rows = dims[:-1]; w = pad or dims[-1]
        size = w
        for d in rows: size *= d
        if base <= off < base + size:
            r, c = divmod(off - base, w)
            if c >= dims[-1]: return f'{n}[pad]'
            idx = []
            for d in reversed(rows): idx.append(r % d); r //= d
            return n + ''.join(f'[{i}]' for i in reversed(idx)) + f'[{c}]'
    return f'?{off:#x}'
