# Brief: bring the remaining docs onto the current paradigm

Task specification for an agent doing the documentation cleanup. Written
2026-09-23 by the session that established the paradigm and did the first three
files, so the pattern to copy is already in the tree.

Read this whole brief before editing anything. §2 is the part that will cost you
if skipped.

---

## 1. What the paradigm is

The problem is **not** that these docs are too long. It was measured: 115 files,
~50,000 lines, and roughly 45% is dated material superseded by something later.
That 45% is mostly **falsified hypotheses with their disconfirming evidence
attached**, and it is the most valuable content in the repo — it is what stops
dead ends being re-run. Two of them have been re-proposed *after* being closed.

The problem is that the corpus was **unindexed and unsignposted**. A reader
could not tell a current authority from a dated snapshot, or find a fact without
grepping.

So the paradigm is four things:

1. **[`README.md`](README.md)** — the index. Organised by "is this still true?",
   not by directory. Its §3 ("closed — do not reopen") is the highest-value
   section in the docs tree.
2. **Orientation banners** on long files: what this is, whether it is current,
   which direction it runs, where the current answer lives. See
   [`mips-display-recovery.md`](mips-display-recovery.md) and
   [`video-decode.md`](video-decode.md) for the two worked examples — copy their
   shape.
3. **Facts as data, narrative as prose.** Register facts live once in
   [`re/registers.yaml`](re/registers.yaml);
   [`register-index.md`](register-index.md) is GENERATED from it.
4. **Gates**, so none of the above silently rots: `tools/check-repo.sh`.

---

## 2. Hard constraints — violating these does real damage

**DO NOT DELETE OR MERGE DOCUMENTS.** Not superseded ones, not "redundant" ones,
not the dead ends. Condensing here means *adding signposts*, not removing text.
If you believe a file is genuinely worthless, say so in your report and leave it
alone. The repo keeps wrong answers on purpose.

**DO NOT TOUCH THESE FILES.** They have uncommitted work from a concurrent
session:

```
docs/status.md
docs/roadmap.md
docs/handoff-2026-09-17-scaled-playback.md
docs/handoff-2026-09-23-retire-display-scaling.md
patches/kernel/          (all)
tools/display/kms-nv12-plane-test.c
```

If `git status` shows a file as modified and you did not modify it, it belongs
to someone else. Leave it and note it.

**DO NOT HAND-EDIT `register-index.md`.** It is generated. Edit
`re/registers.yaml` and run `tools/docs/gen-register-index.py`.

**VERIFY BEFORE YOU ASSERT.** Every claim you add to a banner must be checked
against the file you are bannering. See §5 — this has already gone wrong.

**RUN THE GATE BEFORE EVERY COMMIT:**

```
tools/check-repo.sh
```

Exit 0 or the commit is not ready.

---

## 3. The work, in priority order

### 3.1 Orientation banners for long documents (highest value)

12 files ≥400 lines have no banner. In descending size:

| file | lines |
| --- | --- |
| `wifi-failure-2026-08-17.md` | 2259 |
| `ge2d-plane-open-re.md` | 1497 |
| `handoff-2026-09-01-decd-kms-shape.md` | 955 |
| `flash.md` | 812 |
| `handoff-wifi-sdio-2026-08-17.md` | 687 |
| `hdmi-in.md` | 526 |
| `audio.md` | 484 |
| `handoff-2026-08-30.md` | 482 |
| `decode-production-readiness.md` | 479 |
| `handoff-2026-08-29.md` | 451 |
| `handoff-2026-08-24-display.md` | 450 |
| `backlight-investigation.md` | 400 |

(`status.md` and `roadmap.md` also qualify but are excluded by §2.)

**A banner must answer, in this order:**

1. What is this file? (reference / journal / dated snapshot / closed
   investigation)
2. Is it current? If dormant, give the date of the last entry.
3. What order does it run in? Several here are newest-first and say nothing.
4. Where is the current answer instead? Link it.
5. Anything that would mislead a skimmer — a bold "DONE" that was scoped to one
   day, a heading that misdescribes the section under it.

**Not every file needs one.** `flash.md` and `audio.md` may well be ordinary
current reference docs; if so, a banner adds noise. Read first, then decide, and
say in your report which you skipped and why.

### 3.2 Supersede pointers on handoffs

15 handoffs have no pointer in their first 12 lines. Add a one-line banner naming
what replaced them. Use [`README.md`](README.md) §5 for the per-area ordering.

**Exclusions:** the newest handoff in each area correctly has no pointer —
`2026-09-23-retire-display-scaling` (also §2-excluded), `2026-09-17-*` (both
§2-excluded or newest), and `handoff-wifi-sdio-2026-08-17.md` is the only WiFi
handoff. Do not invent a successor that does not exist.

13 of the 28 handoffs already self-mark correctly. Copy their wording; do not
introduce a second style.

### 3.3 Register backlog (open-ended — do as much as is defensible)

`register-index.md` ends with **86 addresses mentioned in 3+ documents that
nothing defines**. 23 are catalogued so far.

For each you take on: find where it is actually explained, add an entry to
`re/registers.yaml`, regenerate, and confirm the count drops.

**Only add an entry you can point at evidence for.** The schema requires a
`source:` that exists and a `confidence:` of `confirmed-on-hardware` /
`static-analysis` / `inferred`. The generator rejects duplicates, unknown
confidence values, missing sources, and hazards that do not state a consequence
— all four rejections are tested, so it will catch you.

An unsourced entry here is **worse** than leaving the address undefined, because
this file looks authoritative. If the docs disagree about an address, mark it
`inferred`, say so in the notes, and flag it in your report rather than picking
a winner.

---

## 4. How to verify

```
tools/check-repo.sh                         # both gates
tools/docs/gen-register-index.py            # regenerate after YAML edits
tools/docs/gen-register-index.py --check    # drift only
tools/docs/check-links.py                   # links only
```

Every link you add must resolve — the gate enforces it. Anchors are not
verified, so `file.md#section` passes on the file existing alone; check the
heading yourself.

Commits: one logical change each, present-tense subject under ~72 chars, body
explaining *why*. Match the surrounding `git log`. Do not amend or force-push;
the branch is shared.

---

## 5. Failure modes that have already happened here

These are not hypothetical. Each cost time in the session that wrote this brief.

**Bannering a file based on its name.** `ge2d-plane-open-re.md` sounds like it
is about GE2D being a dead end. It is not — it is 1,497 lines of *plane-open*
static analysis, and GE2D's death is recorded elsewhere. A banner was one step
from being added that described the wrong subject. **Read the file.**

**`grep "^# "` does not know about code fences.** It reported a stray top-level
heading in `video-decode.md`, `# 12 non-zero rows of 512`. That is a comment
*inside a hexdump*. "Fixing" it would have corrupted the dump. The link checker
skips fenced and indented blocks for the same reason: disassembly here contains
`handler[+0x14](word)`, a perfect impostor for link syntax.

**Generated files that scan their own directory.** The register index lives in
`docs/` and is full of addresses, so counting it made every run change the next
run's output. If you add generation, exclude the output.

**A gate that fails on arrival gets disabled.** Links were measured *before* the
checker was wired in — 525 links, one apparent failure, and that one a false
positive. If your change makes `check-repo.sh` fail, fix the change, do not
loosen the gate.

**Assuming a passing check means coverage.** The recurring failure in this
project is a suite that passes because it silently skipped the test. If you add
a check, prove it can fail by breaking something on purpose.

---

## 6. What to report back

- Which files you bannered, and which you deliberately skipped, with reasons.
- Any file whose content contradicts what `README.md` says about it — the index
  was written from verified conclusions, but it was written fast.
- Any address where the docs disagree, left `inferred` rather than resolved.
- Anything you believe should be deleted, **not deleted** — with the argument.
