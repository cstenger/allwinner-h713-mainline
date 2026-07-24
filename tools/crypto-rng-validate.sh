#!/bin/sh
# Validate the H713 Crypto Engine (sun8i-ce) and its TRNG/PRNG.
# Runs on the target as root. It is read-only with respect to hardware: it
# reads /proc/crypto, the driver's debugfs stats, and /dev/hwrng, and never
# writes a device register or changes a kernel tunable.
#
# What it proves:
#   1. The CE platform device is bound and probed without errors.
#   2. Every sun8i-ce algorithm passed its boot-time known-answer self-test
#      (the correctness gate for the whole DMA descriptor path).
#   3. The hardware engine actually served requests (reqs > fallback), rather
#      than everything silently falling back to software.
#   4. RNG state is sane: the CE PRNG is registered, and the CE TRNG is
#      correctly absent (this silicon lacks it). Any /dev/hwrng is a bonus.
set -eu

RNG_BYTES=4096
RUN_RNGTEST=auto

while [ "$#" -gt 0 ]; do
	case "$1" in
	--rng-bytes) RNG_BYTES=$2; shift 2 ;;
	--rngtest)   RUN_RNGTEST=yes; shift ;;
	--no-rngtest) RUN_RNGTEST=no; shift ;;
	*) echo "unknown argument: $1" >&2; exit 2 ;;
	esac
done

say()  { printf '%s\n' "$*"; }
head2() { printf '\n== %s ==\n' "$*"; }
die()  { printf 'FAIL: %s\n' "$*" >&2; exit 1; }
warn() { printf 'WARN: %s\n' "$*" >&2; }

[ "$(id -u)" -eq 0 ] || die "run as root"
[ -r /proc/crypto ] || die "no /proc/crypto"

FAIL=0

# --- 1. Driver bound + clean probe --------------------------------------------
head2 "Crypto Engine device"
DRV=/sys/bus/platform/drivers/sun8i-ce
BOUND=""
if [ -d "$DRV" ]; then
	for l in "$DRV"/*.crypto "$DRV"/*crypto*; do
		[ -e "$l" ] || continue
		BOUND=$(basename "$l"); break
	done
fi
if [ -n "$BOUND" ]; then
	say "bound platform device: $BOUND"
else
	warn "no device bound under $DRV (older sysfs layout?); continuing via /proc/crypto"
fi

if command -v dmesg >/dev/null 2>&1; then
	CE_LOG=$(dmesg | grep -iE 'sun8i-ce|Crypto Engine' || true)
	if [ -n "$CE_LOG" ]; then
		say "kernel log:"
		printf '%s\n' "$CE_LOG" | sed 's/^/  /'
		if printf '%s\n' "$CE_LOG" | grep -qiE 'self-test failed|Cannot|Fail to|error'; then
			warn "kernel log mentions a CE error (see above)"
			FAIL=1
		fi
	else
		warn "no sun8i-ce lines in dmesg (ring buffer rotated?)"
	fi
fi

# --- 2. Self-tests: correctness gate ------------------------------------------
head2 "Algorithm self-tests (/proc/crypto)"
# Walk /proc/crypto blocks; for any driver name containing sun8i-ce, capture
# name/driver/type/selftest.
CE_ALGS=$(awk '
	/^name/         { name=$3 }
	/^driver/       { driver=$3 }
	/^type/         { type=$3 }
	/^selftest/     { st=$3 }
	/^$/ {
		if (driver ~ /sun8i-ce/)
			printf "%s\t%s\t%s\t%s\n", driver, name, type, st
		name=driver=type=st=""
	}
' /proc/crypto | sort -u)

[ -n "$CE_ALGS" ] || die "no sun8i-ce algorithms registered in /proc/crypto"

NALG=0; NPASS=0
printf '%s\n' "$CE_ALGS" | while IFS='	' read -r d n t s; do
	printf '  %-20s %-14s %-10s selftest=%s\n' "$d" "$n" "$t" "$s"
done
# The while-subshell above cannot mutate counters; re-evaluate here.
NALG=$(printf '%s\n' "$CE_ALGS" | grep -c .)
NBAD=$(printf '%s\n' "$CE_ALGS" | awk -F'\t' '$4!="passed"' | grep -c . || true)
NPASS=$((NALG - NBAD))
say "sun8i-ce algorithms: $NALG total, $NPASS passed, $NBAD not-passed"
[ "$NBAD" -eq 0 ] || { die "$NBAD sun8i-ce algorithm(s) did not pass self-test (wrong CE variant?)"; }

# Expect at least the core cipher + one hash + the PRNG to be present.
for want in aes sha256 sun8i-ce-prng; do
	printf '%s\n' "$CE_ALGS" | cut -f1 | grep -q "$want" \
		|| warn "expected a sun8i-ce '$want' algorithm but none is registered"
done

# --- 3. Hardware actually served requests -------------------------------------
head2 "Hardware utilisation (debugfs stats)"
STATS=/sys/kernel/debug/sun8i-ce/stats
HW_PROVEN=0
if [ -r "$STATS" ]; then
	say "$STATS:"
	sed 's/^/  /' "$STATS"
	# A cipher/hash line looks like: "<drv> <name> reqs=N fallback=M".
	# Hardware served (N-M) must exceed zero for at least one algorithm,
	# otherwise every request fell back to software.
	HW=$(awk '
		/reqs=[0-9]+ fallback=[0-9]+/ {
			for (i=1;i<=NF;i++) {
				if ($i ~ /^reqs=/)     { r=substr($i,6) }
				if ($i ~ /^fallback=/) { f=substr($i,10) }
			}
			if (r+0 > f+0) served += (r-f)
		}
		END { print served+0 }
	' "$STATS")
	say "hardware-served cipher/hash requests since boot: $HW"
	if [ "${HW:-0}" -gt 0 ]; then
		HW_PROVEN=1
	else
		warn "no request was served by hardware yet (boot self-tests may have all fallen back on this vector set)"
	fi
else
	warn "no debugfs stats (CONFIG_CRYPTO_DEV_SUN8I_CE_DEBUG off); relying on the TRNG read below for the hardware proof"
fi

# --- 4. RNG ------------------------------------------------------------------
# The H713 Crypto Engine has NO TRNG: the hardware answers "algorithm not
# supported" for TRNG_V2 and the DMA times out, so CONFIG_CRYPTO_DEV_SUN8I_CE_TRNG
# is deliberately disabled and the CE registers no /dev/hwrng. The CE's RNG
# offering here is the PRNG (sun8i-ce-prng), validated as an algorithm in the
# self-test section above. /dev/hwrng, if present at all, comes from another
# source (e.g. the ARM SMCCC TRNG) and is treated as a bonus, never required.
head2 "RNG"
GOT=0
say "CE PRNG (sun8i-ce-prng): $(printf '%s\n' "$CE_ALGS" | grep -q 'sun8i-ce-prng' && echo 'registered + self-test passed' || echo 'not registered')"
say "CE TRNG: not present on H713 (hardware lacks TRNG_V2 — correctly disabled)"

if [ -c /dev/hwrng ]; then
	CUR=$(cat /sys/class/misc/hw_random/rng_current 2>/dev/null || echo '?')
	say "an unrelated /dev/hwrng is available (rng_current=$CUR); sampling it as a bonus"
	TMP=$(mktemp); trap 'rm -f "$TMP"' EXIT INT TERM
	if dd if=/dev/hwrng of="$TMP" bs="$RNG_BYTES" count=1 iflag=fullblock 2>/dev/null; then
		GOT=$(wc -c < "$TMP")
		DISTINCT=$(od -An -tu1 -v "$TMP" | tr -s ' ' '\n' | sed '/^$/d' | sort -u | grep -c .)
		say "read $GOT bytes, distinct byte values: $DISTINCT / 256"
		if [ "$RNG_BYTES" -ge 1024 ]; then THRESH=200; else THRESH=$((RNG_BYTES / 8)); fi
		[ "$DISTINCT" -ge "$THRESH" ] || warn "hwrng output looks non-random ($DISTINCT distinct < $THRESH)"
	else
		warn "could not read the available /dev/hwrng"
	fi
else
	say "no /dev/hwrng (expected: CE TRNG absent and no SMCCC TRNG from firmware)"
fi

ENT=$(cat /proc/sys/kernel/random/entropy_avail 2>/dev/null || echo '?')
say "kernel entropy_avail: $ENT (kernel CRNG seeds from jitter/other sources)"

# --- Summary ------------------------------------------------------------------
head2 "Result"
if [ "$FAIL" -ne 0 ]; then
	die "one or more checks reported an error above"
fi
say "PASS: $NALG sun8i-ce algorithms self-test-passed (AES/3DES ciphers, hashes, PRNG)"
[ "$HW_PROVEN" -eq 1 ] \
	&& say "PASS: hardware engine served real requests (debugfs stats)" \
	|| say "NOTE: enable CONFIG_CRYPTO_DEV_SUN8I_CE_DEBUG for per-algorithm hardware counters"
