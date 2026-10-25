# Test 3 follow-up: the same NV12 stills on the production kernel (10-24)

* **Boot:** normal production cold boot `bb62864c…` (kernel clang 23.1.1,
  `#1 SMP Fri Oct 16 15:44:49`). No failed units, HDMI handoff present.
* **Run:** `ARMED=yes kms-yuv-still 15 band.nv12 chart.nv12`, the same
  binary and still files as Test 3. The plane correctly reports no NV16.
  Both stills committed with AFBD `0x10 = 03000013` (format 0) and
  `0x4c = 01680500` (360 chroma rows): **the same register values as on
  the test kernel**. No faults; console restored. Log: `kms-yuv-still.log`.
* **Video:** `local/lcd-photos/test_108/IMG_1070.mov`. Operator: "Production
  looked correct."

`compare-chart-test-vs-production.png` shows the same chart still, top on
the Test 3 kernel and bottom on production:

* **Production:** each hue square carries its own colour (red, orange,
  yellow, chartreuse, green, spring, cyan, azure, blue, violet, magenta, …)
  and the gradient bars are dark at the left. **Correct.**
* **Test 3 kernel:** chroma about 100 px to the right, wrapped (§10.25.2).

## Result

* **The production KMS NV12 plane presents chroma correctly.** Route B's
  output path has no defect.
* **The horizontal shift is specific to the Test 3 kernel.** It's either
  patch `0189` or the full rebuild with clang 23.1.3 (production: 23.1.1).
  The patch doesn't change the NV12 path's addresses, strides or chroma
  rows, which points at the rebuild, but this is unproven. A control kernel
  (same tree and compiler, no patch) would separate the two.
* **The NV16 verdict is unaffected:** format 2's scrambled-tiles picture
  also appeared in Test 2, on the T4 FIT, which carries the production
  kernel Image.
