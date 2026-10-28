# Runtime reconnection status

Operator confirmed console visible and HDMI connected at projector, USB still
out. Same boot cf6a1d00-38b9-43a2-a720-f4f270499327 remains healthy; signal none,
video inactive, PipeWire loopback verified, five backend/speaker/health units
NRestarts=0. Host DRM card1-HDMI-A-1 disconnected/disabled, EDID length 0;
NVIDIA audio port 2 not available, no projector sink. Signal-owner journal
says EDID/HPD ready; module ready=Y failed=N. This does not prove electrical
HPD at the host. Automatic first reconnection has not passed.

Inspected DRM connector detect interface in local primary kernel source. Host
status is root-owned and noninteractive sudo is unavailable, so no connector
write/reprobe was attempted. No board changes, service restarts or reset.
Next is one explicit cable reseat at the PC, preserving this same board boot.

PC-end reseat restored host connector connected and projector sink. Same board boot now locked 1280x720, video/speaker active/success/NRestarts=0, no service reset. Host fixture launched explicitly. Capture/codec-monitor tone gates PASS on both channels (~0.20467 RMS, 440-Hz ratio ~1), operator confirms moving picture/colour/clean continuous tone. Functional runtime reconnection PASS with this source-side reseat caveat; first projector-end reconnect alone was not an automatic PASS.
