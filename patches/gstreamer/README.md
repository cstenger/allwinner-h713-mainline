> **RETIRED 2026-10-02 with the direct path (WP2 decision,
> [gpu-fallback-plan.md](../../docs/gpu-fallback-plan.md)).**
> These served `v4l2codecs -> kmssink` scanout on the video plane. The board
> installs them only as an opt-in plugin path (`/opt/gst-h713`, used via
> `GST_PLUGIN_PATH`), and stock GStreamer is already the default. The stock
> GPU path (`v4l2sl*dec`/`va*dec ! glimagesink`) is zero-copy and needs none
> of them.

# GStreamer patches
