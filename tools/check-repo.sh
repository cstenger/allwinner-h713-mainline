#!/usr/bin/env bash
# Repo self-consistency gate. RUNS ON THE HOST. No board, no network.
#
# This is the HOST-side counterpart to tools/video/check-video-stack.sh, and the
# split is deliberate: that script answers "is the board running what this repo
# says it should", needs BOARD and ssh, and cannot run at all when the bench is
# powered down. The checks here need nothing but the working tree, so they can
# gate a commit.
#
# What it enforces, and why each earns its place:
#
#   register index drift
#     docs/register-index.md is GENERATED from docs/re/registers.yaml. A
#     generated file with no drift gate is the "index nobody updates" failure
#     with extra steps -- it keeps looking authoritative while saying something
#     the source no longer says. This also validates the YAML itself: duplicate
#     addresses, unknown confidence values, sources naming files that do not
#     exist, and hazard entries that do not state a consequence.
#
#   documentation links
#     525-odd relative links across 115 files. A dead link in an index is worse
#     than a missing entry, because it asserts that something exists.
#
# Exit status is 0 only when everything passes, so it can gate a commit hook or
# CI. Install it as a pre-commit hook with:
#
#     ln -s ../../tools/check-repo.sh .git/hooks/pre-commit
#
# It is NOT installed automatically. Hooks are local state, and silently adding
# one to somebody's clone is the kind of surprise that gets hooks disabled.
#
#   usage: tools/check-repo.sh
set -uo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$ROOT" || exit 2

fail=0
run() {
	local label=$1; shift
	printf '== %s\n' "$label"
	if "$@"; then
		return 0
	fi
	printf '   FAILED: %s\n' "$label"
	fail=1
}

run "register index vs docs/re/registers.yaml" \
	python3 tools/docs/gen-register-index.py --check
echo
run "documentation links resolve" \
	python3 tools/docs/check-links.py

echo
if [ "$fail" -eq 0 ]; then
	echo "REPO: consistent"
else
	echo "REPO: INCONSISTENT — see above"
	echo
	echo "  If the register index is stale, regenerate it rather than editing"
	echo "  the markdown by hand:  tools/docs/gen-register-index.py"
fi
exit "$fail"
