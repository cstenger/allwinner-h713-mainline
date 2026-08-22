#!/usr/bin/env python3
"""Dump HEVC SPS / PPS / slice-header fields and diff two streams.

Written to answer one question that kept being assumed instead of checked:
when two streams are generated from the same source with one encoder setting
changed, is that setting really the ONLY difference in the bitstream?

    hevc-bitstream-dump.py a.h265 b.h265

Parses enough of the syntax to reach the fields that matter for a stateless
decoder's control filling. It deliberately stops before VUI and the extension
flags -- everything past sps_temporal_mvp/strong_intra_smoothing is not worth
the parsing risk for this purpose, and a wrong parse there would produce
confident nonsense.

st_ref_pic_set() is implemented properly (including the inter-RPS prediction
form) because it cannot be skipped: it sits between the SPS fields we want and
the ones after it, and mis-skipping it silently corrupts every later field.
"""
import sys


def nal_units(data):
    out, i = [], 0
    while True:
        j = data.find(b"\x00\x00\x01", i)
        if j < 0:
            break
        k = data.find(b"\x00\x00\x01", j + 3)
        end = len(data) if k < 0 else (k - 1 if data[k - 1] == 0 else k)
        payload = data[j + 3:end]
        if payload:
            out.append(((payload[0] >> 1) & 0x3F, payload))
        i = j + 3
    return out


def unescape(b):
    out, i = bytearray(), 0
    while i < len(b):
        if i + 2 < len(b) and b[i] == 0 and b[i + 1] == 0 and b[i + 2] == 3:
            out += b[i:i + 2]
            i += 3
        else:
            out.append(b[i])
            i += 1
    return bytes(out)


class BR:
    def __init__(self, b):
        self.b, self.p = b, 0

    def u(self, n):
        v = 0
        for _ in range(n):
            v = (v << 1) | ((self.b[self.p >> 3] >> (7 - (self.p & 7))) & 1)
            self.p += 1
        return v

    def ue(self):
        z = 0
        while self.u(1) == 0:
            z += 1
            if z > 32:
                raise ValueError("bad ue")
        return (1 << z) - 1 + (self.u(z) if z else 0)

    def se(self):
        k = self.ue()
        return (k + 1) // 2 if k % 2 else -(k // 2)


def profile_tier_level(r, max_sub_layers_minus1):
    r.u(2); r.u(1); r.u(5)
    r.u(32)
    r.u(48)
    r.u(8)
    if max_sub_layers_minus1:
        sub_p, sub_l = [], []
        for _ in range(max_sub_layers_minus1):
            sub_p.append(r.u(1)); sub_l.append(r.u(1))
        for _ in range(max_sub_layers_minus1, 8):
            r.u(2)
        for i in range(max_sub_layers_minus1):
            if sub_p[i]:
                r.u(2); r.u(1); r.u(5); r.u(32); r.u(48)
            if sub_l[i]:
                r.u(8)


def st_ref_pic_set(r, idx, num_sets, num_delta_pocs):
    """Returns NumDeltaPocs for this set; appends to num_delta_pocs."""
    inter = r.u(1) if idx != 0 else 0
    if inter:
        if idx == num_sets:
            r.ue()                      # delta_idx_minus1
        r.u(1)                          # delta_rps_sign
        r.ue()                          # abs_delta_rps_minus1
        ref = num_delta_pocs[idx - 1]
        n = 0
        for _ in range(ref + 1):
            used = r.u(1)
            if not used:
                if r.u(1):              # use_delta_flag
                    n += 1
            else:
                n += 1
        return n
    neg, pos = r.ue(), r.ue()
    for _ in range(neg):
        r.ue(); r.u(1)
    for _ in range(pos):
        r.ue(); r.u(1)
    return neg + pos


def parse_sps(payload):
    r = BR(unescape(payload[2:]))
    f = {}
    f["sps_video_parameter_set_id"] = r.u(4)
    msl = r.u(3)
    f["sps_max_sub_layers_minus1"] = msl
    f["sps_temporal_id_nesting"] = r.u(1)
    profile_tier_level(r, msl)
    f["sps_id"] = r.ue()
    f["chroma_format_idc"] = r.ue()
    if f["chroma_format_idc"] == 3:
        f["separate_colour_plane"] = r.u(1)
    f["pic_width_in_luma_samples"] = r.ue()
    f["pic_height_in_luma_samples"] = r.ue()
    if r.u(1):                          # conformance_window_flag
        f["conf_win"] = [r.ue(), r.ue(), r.ue(), r.ue()]
    f["bit_depth_luma_minus8"] = r.ue()
    f["bit_depth_chroma_minus8"] = r.ue()
    f["log2_max_poc_lsb_minus4"] = r.ue()
    sub_info = r.u(1)
    for _ in range(msl + 1 if sub_info else 1):
        f.setdefault("max_dec_pic_buffering_minus1", r.ue())
        f.setdefault("max_num_reorder_pics", r.ue())
        f.setdefault("max_latency_increase_plus1", r.ue())
    f["log2_min_luma_cb_size_minus3"] = r.ue()
    f["log2_diff_max_min_luma_cb_size"] = r.ue()
    f["log2_min_luma_tb_size_minus2"] = r.ue()
    f["log2_diff_max_min_luma_tb_size"] = r.ue()
    f["max_transform_hierarchy_depth_inter"] = r.ue()
    f["max_transform_hierarchy_depth_intra"] = r.ue()
    f["scaling_list_enabled"] = r.u(1)
    if f["scaling_list_enabled"]:
        f["sps_scaling_list_data_present"] = r.u(1)
        if f["sps_scaling_list_data_present"]:
            f["_scaling_list_data"] = "present (not parsed)"
            return f                    # stop rather than mis-skip
    f["amp_enabled"] = r.u(1)
    f["sample_adaptive_offset_enabled"] = r.u(1)
    f["pcm_enabled"] = r.u(1)
    if f["pcm_enabled"]:
        r.u(4); r.u(4); r.ue(); r.ue()
        f["pcm_loop_filter_disabled"] = r.u(1)
    n = r.ue()
    f["num_short_term_ref_pic_sets"] = n
    ndp = []
    for i in range(n):
        ndp.append(st_ref_pic_set(r, i, n, ndp))
    f["NumDeltaPocs"] = ndp
    f["long_term_ref_pics_present"] = r.u(1)
    if f["long_term_ref_pics_present"]:
        m = r.ue()
        f["num_long_term_ref_pics_sps"] = m
        for _ in range(m):
            r.u(f["log2_max_poc_lsb_minus4"] + 4); r.u(1)
    f["SPS_TEMPORAL_MVP_ENABLED"] = r.u(1)
    f["strong_intra_smoothing_enabled"] = r.u(1)
    return f


def parse_slice(payload, sps, pps):
    """Early slice-segment-header fields, up to slice_type."""
    r = BR(unescape(payload[2:]))
    f = {}
    nal_type = (payload[0] >> 1) & 0x3F
    f["first_slice_segment_in_pic"] = r.u(1)
    if 16 <= nal_type <= 23:
        f["no_output_of_prior_pics"] = r.u(1)
    f["slice_pic_parameter_set_id"] = r.ue()
    if not f["first_slice_segment_in_pic"]:
        f["_not_first_slice"] = True
        return f
    for _ in range(pps.get("num_extra_slice_header_bits", 0)):
        r.u(1)
    f["slice_type"] = {0: "B", 1: "P", 2: "I"}.get(r.ue(), "?")
    if pps.get("output_flag_present"):
        f["pic_output_flag"] = r.u(1)
    return f


def collect(path):
    data = open(path, "rb").read()
    sps = pps = None
    slices = []
    for t, payload in nal_units(data):
        try:
            if t == 33 and sps is None:
                sps = parse_sps(payload)
            elif t == 34 and pps is None:
                from importlib import util
                pps = {}
                # reuse the PPS dumper's parse by inlining the few fields we need
                rr = BR(unescape(payload[2:]))
                rr.ue(); rr.ue()
                pps["dependent_slice_segments_enabled"] = rr.u(1)
                pps["output_flag_present"] = rr.u(1)
                pps["num_extra_slice_header_bits"] = rr.u(3)
            elif t <= 21 and sps and pps and len(slices) < 6:
                slices.append(parse_slice(payload, sps, pps))
        except Exception as e:
            print("  parse error in NAL type %d: %s" % (t, e))
    return sps or {}, slices


def diff(name_a, a, name_b, b, title):
    keys = sorted(set(a) | set(b))
    if not keys:
        return
    w = max(len(k) for k in keys)
    print("\n=== %s ===" % title)
    print("%-*s  %-24s %-24s" % (w, "field", name_a, name_b))
    ndiff = 0
    for k in keys:
        va, vb = a.get(k, "-"), b.get(k, "-")
        d = str(va) != str(vb)
        ndiff += d
        print("%-*s  %-24s %-24s%s" % (w, k, va, vb, "   <<< DIFFERS" if d else ""))
    print("-> %d field(s) differ" % ndiff)


pa, pb = sys.argv[1], sys.argv[2]
sa, sla = collect(pa)
sb, slb = collect(pb)
na, nb = pa.split("/")[-1], pb.split("/")[-1]
diff(na, sa, nb, sb, "SPS")
for i in range(min(len(sla), len(slb))):
    diff(na, sla[i], nb, slb[i], "slice header #%d" % i)
