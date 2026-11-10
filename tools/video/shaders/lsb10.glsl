// H713: put the AV1 core's LSB-aligned 10-bit samples where P010 expects them.
//
// The AV1 core writes P010 with each sample in bits 9:0, not 15:6. With
// V4L2_REQUEST_LSB10_LINEAR=1 the VA driver exports that as plain linear
// P010 so GL can import it at all, and the samples are then read 64 times
// too small (an almost black picture). Multiplying by 64 is exact: a 10-bit
// sample v reads as v/65535 and belongs at v*64/65535. Use only together
// with that variable, and only for 10-bit AV1 (tools/video/h713-play does
// both); on anything else it washes the picture out.
//
//   mpv --glsl-shaders=/usr/local/share/h713/lsb10.glsl ...

//!HOOK LUMA
//!BIND HOOKED
//!DESC H713 LSB10 luma x64
vec4 hook() { return HOOKED_tex(HOOKED_pos) * 64.0; }

//!HOOK CHROMA
//!BIND HOOKED
//!DESC H713 LSB10 chroma x64
vec4 hook() { return HOOKED_tex(HOOKED_pos) * 64.0; }
