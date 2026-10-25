# Route B check on the production kernel (2026-10-24)

Module `h713-hdmi-v4l2.ko` sha `0a63ac9e`, `completion=pair source_cached=1`,
NV12 1280x720, via `tools/hdmi/route-b-bench.sh check`.

1. First build (copy slot = pair index): 4968 completions, 4968 unstable.
2. `ring-timeline.py` (board.log): the pair advances +1 every 16.75 ms and
   names the slot being captured; slot pair-1 never changes during a period.
3. Copy slot (idx+2)%3: hashes pass, but full verify re-reads the uncached
   vb2 buffer, 19 ms/frame > one period -> all rejected.
4. Guard = pair unchanged after the copy, full verify off in pair mode
   (verify_full=-1 auto): 300/300 delivered, 0 rejected, 59.7 fps,
   3.0 ms per copy+convert. frame0.png = the decoded first frame.
