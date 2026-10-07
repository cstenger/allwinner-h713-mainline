// H713: keystone pre-warp of mpv's whole output (docs/keystone-plan.md).
//
// keystone.lua loads this only while a correction is due, sets keepaspect=no
// so OUTPUT is the whole 1280x720 frame (mpv's own letterbox bars would
// clip a picture the warp moves), and swaps in a copy whose matrix (the one
// placeholder below) maps a frame position (0..1, top-left origin) to a
// homogeneous position in mpv's stretched picture. A copy per matrix, not a
// parameter: vo=gpu, the renderer h713-play uses, has no shader parameters
// (only gpu-next does). The matrix carries the projection (pitch about the
// lens), the corrected rectangle and the letterbox, so the shader only
// divides and samples. Black outside.
//
// Not by hand: the matrix is meaningless without keystone.lua.

//!HOOK OUTPUT
//!BIND HOOKED
//!DESC H713 keystone
vec4 hook() {
	mat3 m = KEYSTONE_MATRIX;
	vec3 p = m * vec3(HOOKED_pos, 1.0);
	if (p.z <= 0.0)
		return vec4(0.0, 0.0, 0.0, 1.0);
	vec2 s = p.xy / p.z;
	if (any(lessThan(s, vec2(0.0))) || any(greaterThan(s, vec2(1.0))))
		return vec4(0.0, 0.0, 0.0, 1.0);
	return HOOKED_tex(s);
}
