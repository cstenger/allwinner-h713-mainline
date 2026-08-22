"""Minimal HEVC PPS/SPS field dumper -- enough to diff two streams' coding tools."""
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
    """Strip emulation prevention bytes (00 00 03 -> 00 00)."""
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


def parse_pps(payload):
    r = BR(unescape(payload[2:]))          # skip the 2-byte NAL header
    f = {}
    f["pps_id"] = r.ue()
    f["sps_id"] = r.ue()
    f["dependent_slice_segments_enabled"] = r.u(1)
    f["output_flag_present"] = r.u(1)
    f["num_extra_slice_header_bits"] = r.u(3)
    f["sign_data_hiding_enabled"] = r.u(1)
    f["cabac_init_present"] = r.u(1)
    f["num_ref_idx_l0_default_active_minus1"] = r.ue()
    f["num_ref_idx_l1_default_active_minus1"] = r.ue()
    f["init_qp_minus26"] = r.se()
    f["constrained_intra_pred"] = r.u(1)
    f["transform_skip_enabled"] = r.u(1)
    f["cu_qp_delta_enabled"] = r.u(1)
    if f["cu_qp_delta_enabled"]:
        f["diff_cu_qp_delta_depth"] = r.ue()
    f["pps_cb_qp_offset"] = r.se()
    f["pps_cr_qp_offset"] = r.se()
    f["pps_slice_chroma_qp_offsets_present"] = r.u(1)
    f["weighted_pred"] = r.u(1)
    f["weighted_bipred"] = r.u(1)
    f["transquant_bypass_enabled"] = r.u(1)
    f["TILES_ENABLED"] = r.u(1)
    f["ENTROPY_CODING_SYNC_ENABLED"] = r.u(1)
    if f["TILES_ENABLED"]:
        f["num_tile_columns_minus1"] = r.ue()
        f["num_tile_rows_minus1"] = r.ue()
        f["uniform_spacing"] = r.u(1)
    f["pps_loop_filter_across_slices_enabled"] = r.u(1)
    f["deblocking_filter_control_present"] = r.u(1)
    if f["deblocking_filter_control_present"]:
        f["deblocking_filter_override_enabled"] = r.u(1)
        f["pps_deblocking_filter_disabled"] = r.u(1)
        if not f["pps_deblocking_filter_disabled"]:
            f["beta_offset_div2"] = r.se()
            f["tc_offset_div2"] = r.se()
    f["pps_scaling_list_data_present"] = r.u(1)
    f["lists_modification_present"] = r.u(1)
    f["log2_parallel_merge_level_minus2"] = r.ue()
    f["slice_segment_header_extension_present"] = r.u(1)
    return f


results = {}
for path in sys.argv[1:]:
    data = open(path, "rb").read()
    for t, payload in nal_units(data):
        if t == 34:                        # PPS_NUT
            results[path] = parse_pps(payload)
            break

keys = sorted({k for v in results.values() for k in v})
names = list(results)
w = max(len(k) for k in keys)
print("%-*s  %s" % (w, "PPS field", "  ".join("%-22s" % n.split("/")[-1] for n in names)))
for k in keys:
    vals = [results[n].get(k, "-") for n in names]
    flag = "   <<< DIFFERS" if len(set(map(str, vals))) > 1 else ""
    print("%-*s  %s%s" % (w, k, "  ".join("%-22s" % v for v in vals), flag))
