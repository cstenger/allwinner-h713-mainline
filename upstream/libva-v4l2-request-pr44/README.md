# Upstream contribution for bootlin/libva-v4l2-request PR #44 — prepared, not sent

Everything needed to publish this is here and **nothing has been published**.
No fork exists, no branch has been pushed, no comment has been posted. Sending
it is a decision, not a follow-up step.

Prepared 2026-08-22 against PR #44 head **`c488d8df`** ("Added HEVC").

## What is here

| file | what it is |
| --- | --- |
| `PR-COMMENT.md` | the comment to post on the PR thread, ready to paste verbatim (everything below its `---`) |
| `PR-DESCRIPTION.md` | title and body if you open a pull request instead of, or as well as, commenting |
| `0001-h265-pass-the-scaling-matrix.patch` | the code change, **hardware-validated**, against `c488d8df` |
| `hevc-scaling-matrix.bundle` | the same commit as a complete, self-contained git bundle (377 KB, full history — it does not need GitHub to be reachable) |
| `SUGGESTION-deblocking-flag.patch` | the `DEBLOCKING_FILTER_CONTROL_PRESENT` one-liner, **compiled but never validated** — see below |

The working clone this came from is at `local/upstream/libva-v4l2-request`
(untracked, as `local/` always is), on branch `h713/hevc-scaling-matrix`.

## Why the code and the suggestion are kept apart

`0001` is the scaling-matrix fix. It is validated the way everything in this
project is meant to be: two new vectors that fail without it and are bit-exact
with it, on hardware, with GStreamer as an independent oracle. It also builds
clean on `c488d8df` — checked on the board, `19/19` targets, no warnings from
the added code.

`SUGGESTION-deblocking-flag.patch` is deliberately **not** on the branch. The
current derivation is wrong by the spec, but cedrus references neither that flag
nor `UNIFORM_SPACING`, so this project's gate cannot score the change either
way. Shipping unvalidated code upstream and shipping an unvalidated OPP are the
same mistake, so it goes as an argument in prose (`PR-COMMENT.md` §3) with the
patch attached for whoever can test it. Do not fold it into the PR without a
decoder that reads the flag.

## To publish later

Comment only — no git needed. Open the PR, paste everything below the `---` in
`PR-COMMENT.md`.

To open a pull request as well, from a fresh clone:

```bash
git clone https://github.com/bootlin/libva-v4l2-request && cd libva-v4l2-request
git fetch origin refs/pull/44/head:pr44
git bundle unbundle /path/to/hevc-scaling-matrix.bundle
git checkout -b h713/hevc-scaling-matrix 1943715211d4b66b1733ea52fd56651123fe9b4b
```

or, equivalently, without the bundle:

```bash
git checkout -b h713/hevc-scaling-matrix pr44
git am /path/to/0001-h265-pass-the-scaling-matrix.patch
```

then fork on GitHub, `git remote add fork git@github.com:<you>/libva-v4l2-request.git`,
`git push fork h713/hevc-scaling-matrix`, and open the PR **against the PR #44
branch, not master** — the change assumes #44's HEVC port is present.

## To rebuild the evidence

The claims in `PR-COMMENT.md` are reproducible from this repo:
`tools/video/make-test-streams.sh` generates the vectors (`h04`/`h05` are the
scaling-list ones, `h05` from `tools/video/scaling-list-custom.txt`) and
`tools/video/hevc-decode-test.sh` scores them on the board — software control
first, then GStreamer as oracle, then the shim. Full write-up with the claims
that did **not** survive checking:
[`docs/reference/bootlin-pr44-report.md`](../../docs/reference/bootlin-pr44-report.md).
