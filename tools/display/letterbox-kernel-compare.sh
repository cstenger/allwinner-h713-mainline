#!/usr/bin/env bash
# Does the kernel's letterbox table say what letterbox-recipe.py says?
# RUNS ON THE HOST. Compiles the driver's own h713_lb_fields[], field
# functions and h713_lb_words() -- extracted verbatim from the driver source,
# not retyped -- against a stub of the kernel API, seeds the snapshot from a
# letterbox-baseline.py dump exactly as h713_lb_snapshot() does at probe, and
# diffs every register word against the recipe for a set of geometries.
#
#   letterbox-kernel-compare.sh DRIVER.c [BASELINE.txt]
#
# Exit 0 only if every word of every geometry matches and the native
# geometry reproduces the snapshot (the probe-time self-check).
set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
REPO=$(cd "$HERE/../.." && pwd)
DRV=${1:?driver source}
BASE=${2:-$REPO/docs/reference/letterbox-baseline-2026-10-04/native-720p.txt}
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT

# Verbatim: from the block enum to the NR bracket defines, and the two helpers.
awk '/^enum \{ LB_COMP/{p=1} /^\/\* The NR hold\/release bracket/{p=0} p' "$DRV" > "$T/table.inc"
awk '/^static int h713_lb_reg_index/{p=1} p{print} p&&/^}/{p=0}' "$DRV" > "$T/fn.inc"
awk '/^static int h713_lb_words/{p=1} p{print} p&&/^}/{p=0}' "$DRV" >> "$T/fn.inc"
grep -q h713_lb_fields "$T/table.inc" && grep -q h713_lb_words "$T/fn.inc" ||
	{ echo "could not extract the table from $DRV"; exit 1; }
max=$(sed -n 's/^#define H713_LB_MAX_REGS[[:space:]]*\([0-9]*\).*/\1/p' "$DRV")
geom=$(awk '/^struct h713_geom \{/{p=1} p{print} p&&/^\};/{p=0}' "$DRV")

cat > "$T/h.c" <<C
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <errno.h>
#include <stdbool.h>
typedef uint8_t u8; typedef uint16_t u16; typedef uint32_t u32; typedef int64_t s64;
#define GENMASK(h, l) (((~0u) >> (31 - (h))) & ~((1u << (l)) - 1))
#define ALIGN(x, a) (((x) + (a) - 1) / (a) * (a))
#define DIV_ROUND_UP(n, d) (((n) + (d) - 1) / (d))
#define max(a, b) ((a) > (b) ? (a) : (b))
#define ARRAY_SIZE(a) (sizeof(a) / sizeof((a)[0]))
#define H713_LB_MAX_REGS $max
$geom
struct h713_afbd { struct h713_geom native; unsigned int lb_nregs;
	u8 lb_blk[H713_LB_MAX_REGS]; u16 lb_off[H713_LB_MAX_REGS]; u32 lb_snap[H713_LB_MAX_REGS]; };
#include "table.inc"
#include "fn.inc"
static const char *bn[] = { "comp", "route", "proc", "lvds", "vblend" };
int main(int argc, char **argv)
{
	static struct h713_afbd hh, *h = &hh;
	char name[32], blk[16]; unsigned off, val, addr; u32 words[H713_LB_MAX_REGS];
	FILE *f = fopen(argv[1], "r"); unsigned i;
	h->native = (struct h713_geom){ 1280, 720, 0, 0, 1280, 720 };
	/* h713_lb_snapshot(), with the dump standing in for readl() */
	for (i = 0; i < ARRAY_SIZE(h713_lb_fields); i++) {
		const struct h713_lb_field *fl = &h713_lb_fields[i];
		int found = 0;
		if (h713_lb_reg_index(h, fl->blk, fl->off) >= 0) continue;
		rewind(f);
		while (fscanf(f, "%31s %x %x", name, &addr, &val) == 3) {
			if (sscanf(name, "%15[^+]+%x", blk, &off) != 2) continue;
			if (!strcmp(blk, bn[fl->blk]) && off == fl->off) { found = 1; break; }
		}
		if (!found) { fprintf(stderr, "MISSING %s+%03x in the dump\n", bn[fl->blk], fl->off); return 2; }
		h->lb_blk[h->lb_nregs] = fl->blk; h->lb_off[h->lb_nregs] = fl->off;
		h->lb_snap[h->lb_nregs++] = val;
	}
	if (h713_lb_words(h, &h->native, words)) { fprintf(stderr, "native not expressible\n"); return 2; }
	for (i = 0; i < h->lb_nregs; i++)
		if (words[i] != h->lb_snap[i]) { fprintf(stderr, "PROBE-CHECK FAIL (the driver would turn letterbox off at boot): %s+%03x\n", bn[h->lb_blk[i]], h->lb_off[i]); return 2; }
	/* geometries from stdin: w h dx dy ow oh */
	struct h713_geom g;
	while (scanf("%u %u %u %u %u %u", &g.w, &g.h, &g.dx, &g.dy, &g.ow, &g.oh) == 6) {
		int r = h713_lb_words(h, &g, words);
		printf("geom %u %u %u %u %u %u %d\n", g.w, g.h, g.dx, g.dy, g.ow, g.oh, r);
		for (i = 0; !r && i < h->lb_nregs; i++)
			printf("%s %03x %08X\n", bn[h->lb_blk[i]], h->lb_off[i], words[i]);
	}
	printf("nregs %u\n", h->lb_nregs);
	return 0;
}
C
cc -O1 -Wall -Wno-unused-function -I"$T" -o "$T/h" "$T/h.c"

GEOMS="1280 720 0 0 1280 720
1280 536 0 0 1280 536
1280 536 0 92 1280 536
852 480 214 120 852 480
640 360 0 0 1280 720
852 480 0 0 1278 720
720 576 160 0 960 720
352 288 200 0 880 720
640 360 160 90 960 540
720 480 0 0 1280 720
720 576 160 0 960 720
1280 534 0 93 1280 534"
echo "$GEOMS" | "$T/h" "$BASE" > "$T/kernel.txt"
python3 - "$T/kernel.txt" "$BASE" "$HERE/letterbox-recipe.py" <<'P'
import json, subprocess, sys, tempfile, os
kern, base, recipe = sys.argv[1:]
cur, geoms = None, {}
for line in open(kern):
    f = line.split()
    if f[0] == "geom":
        cur = tuple(map(int, f[1:7])); geoms[cur] = ({} if f[7] == "0" else None)
    elif f[0] in ("comp", "route", "proc", "lvds", "vblend"):
        geoms[cur][(f[0], int(f[1], 16))] = int(f[2], 16)
    elif f[0] == "nregs":
        nregs = int(f[1])
bad = words = 0
for (w, h, dx, dy, ow, oh), kw in geoms.items():
    j = tempfile.mktemp(suffix=".json")
    r = subprocess.run([sys.executable, recipe, "--live", base, f"{w}x{h}", f"{dx},{dy}",
                        "--out", f"{ow}x{oh}", "--pitch", str((w + 15) // 16 * 16), "--json", j],
                       capture_output=True, text=True)
    if r.returncode or kw is None:
        if (r.returncode != 0) != (kw is None):
            bad += 1; print(f"MISMATCH {w}x{h}->{ow}x{oh}@{dx},{dy}: recipe rc {r.returncode}, kernel {'refused' if kw is None else 'ok'}")
        continue
    regs = {(x["block"], x["off"]): x["new"] for x in json.load(open(j))["regs"] if x["block"] != "afbd"}
    os.unlink(j)
    if set(regs) != set(kw):
        bad += 1; print(f"REGISTER SET DIFFERS {w}x{h}->{ow}x{oh}: only recipe {sorted(set(regs)-set(kw))} only kernel {sorted(set(kw)-set(regs))}")
    for k in sorted(set(regs) & set(kw)):
        words += 1
        if regs[k] != kw[k]:
            bad += 1; print(f"DIFF {w}x{h}->{ow}x{oh}@{dx},{dy} {k[0]}+{k[1]:03x}: kernel {kw[k]:08X} recipe {regs[k]:08X}")
print(f"{len(geoms)} geometries, {words} words, {nregs} registers per geometry: "
      + ("ALL MATCH" if not bad else f"{bad} DIFFERENCES"))
sys.exit(1 if bad else 0)
P
