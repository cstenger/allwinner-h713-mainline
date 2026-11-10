# H713 build artifact location — the single source of truth.
#
# Artifacts go to build/ in the repo. That directory is git-ignored and holds
# nothing but generated output; the scripts that produce it live in
# tools/build/.
#
# Set H713_BUILD_DIR to build somewhere else (another disk, a tmpfs, a second
# checkout's artifacts). It must be an absolute path.
#
# KEEP IT PRUNED. Kernel trees are content-addressed — build/linux-<version>-<digest>
# — so a tree whose digest no longer matches the current series is never reused,
# only re-created. They accumulate silently at ~2 GiB each. Left alone from
# 2026-08-17 to 09-11 they reached 101 trees, 208 GB and ~620k directories, which
# took `git status` to 21 s and put git's fsmonitor daemon over
# fs.inotify.max_user_watches so it could not start at all. Pruning to the trees
# actually in use took the worktree back to 31k directories and status to 0.5 s.
# See "Build cache cleanup" in docs/build.md.
#
# Sourced by tools/build/build.sh and every script that reads its output.

if [ -n "${H713_BUILD_DIR:-}" ]; then
  case "$H713_BUILD_DIR" in
    /*) ;;
    *) echo "error: H713_BUILD_DIR must be an absolute path, got '$H713_BUILD_DIR'" >&2; return 1 2>/dev/null || exit 1 ;;
  esac
else
  # Default: build/ beside this file's repo root. Callers set ROOT or
  # PROJECT_ROOT before sourcing; fall back to this file's own location.
  H713_BUILD_DIR=${ROOT:-${PROJECT_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}}/build
fi
