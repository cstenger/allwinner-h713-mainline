-- H713 keystone for mpv: pre-warps the picture so a tilted projector shows a
-- rectangle (docs/keystone-plan.md, phase 3). RUNS IN mpv ON THE TARGET.
--
--   mpv --script=/usr/local/share/h713/keystone.lua ...   (h713-play does this)
--
-- Every half second it reads /run/h713-keystone/state (h713-keystone's
-- daemon) and the lens geometry in /etc/h713-keystone.conf (`h713-keystone
-- lens`). While |keystone_deg| >= min_deg it sets keepaspect=no, loads
-- keystone.glsl and gives it the matrix below; otherwise it removes both, so
-- a level projector costs nothing. Without a measured lens it does nothing.
-- keystone.glsl is a template: each new matrix is written into a copy under
-- /tmp and swapped in, because vo=gpu has no //!PARAM.
--
-- The model. The projector is a pinhole: frame position u (0..1, left to
-- right) and v (0..1, top to bottom) leave the lens along tangents
-- x = s(2u - 1) across and t = tt - (tt - tb) v up. Pitching the projector by
-- phi toward a vertical surface at unit distance puts that ray at the
-- homogeneous wall point R(phi) (x, t, 1) -- the rotation matrix itself is
-- the homography. The frame lands as a trapezoid, wide at the far edge; the
-- picture goes in the largest rectangle with the panel's aspect that fits,
-- standing on the near (narrow) edge, letterboxed inside by the video's own
-- aspect. The shader inverts nothing: it maps each frame position straight
-- to the picture position the wall needs there.
--
-- Mirror: under a top/bottom flip (h713-mirror rear-ceiling, ceiling) the
-- frame's top is the panel's bottom, so the lens tangents and the pitch
-- change sign. Left/right mirrors change nothing: the model is symmetric.
--
-- selftest=yes prints the matrix for a few angles and quits (headless check:
-- tools/video/keystone-check.py).

local mp = require 'mp'
local msg = require 'mp.msg'

local opts = {
	state = "/run/h713-keystone/state",
	conf = "/etc/h713-keystone.conf",
	shader = "/usr/local/share/h713/keystone.glsl",
	min_deg = 0.5,		-- below this the warp is off (sensor noise ~0.1 deg)
	max_deg = 40,		-- h713-keystone never asks for more than 45
	selftest = "",
}
require('mp.options').read_options(opts, "keystone")

local function mul(a, b)
	local r = {}
	for i = 1, 3 do
		r[i] = {}
		for j = 1, 3 do
			r[i][j] = a[i][1] * b[1][j] + a[i][2] * b[2][j] + a[i][3] * b[3][j]
		end
	end
	return r
end

-- Frame position -> stretched-picture position, homogeneous, for pitch phi
-- (radians), lens tangents s (half width), tb, tt (bottom, top edge), and
-- video aspect va (width / height).
local function warp(phi, s, tb, tt, va)
	local c, n = math.cos(phi), math.sin(phi)
	local A = {{2 * s, 0, -s}, {0, -(tt - tb), tt}, {0, 0, 1}}
	local R = {{1, 0, 0}, {0, c, n}, {0, -n, c}}
	-- The frame's bottom and top edges on the wall: height and half width.
	local zb, zt = c - tb * n, c - tt * n
	local yb, yt = (tb * c + n) / zb, (tt * c + n) / zt
	local hb, ht = s / zb, s / zt
	local ar = (tt - tb) / (2 * s)		-- panel height / width, unpitched
	local hw = math.min(hb, ht)
	local hr = 2 * hw * ar
	if hr > yt - yb then hr = yt - yb; hw = hr / (2 * ar) end
	local ytop = (hb <= ht) and (yb + hr) or yt
	-- Wall -> the corrected rectangle, 0..1 from its top-left corner.
	local B = {{1 / (2 * hw), 0, 0.5}, {0, -1 / hr, ytop / hr}, {0, 0, 1}}
	-- The rectangle -> mpv's picture, stretched to the frame by keepaspect=no.
	local pa = 1 / ar
	local cx, cy, cw, ch = 0, 0, 1, 1
	if va > pa then ch = pa / va; cy = (1 - ch) / 2 else cw = va / pa; cx = (1 - cw) / 2 end
	local C = {{1 / cw, 0, -cx / cw}, {0, 1 / ch, -cy / ch}, {0, 0, 1}}
	return mul(C, mul(B, mul(R, A)))
end

local function read_kv(path)
	local f = io.open(path, "r")
	if not f then return nil end
	local t = {}
	for line in f:lines() do
		local k, v = line:match("^([%w_]+)=(.*)$")
		if k then t[k] = v end
	end
	f:close()
	return t
end

local mirror_path
do
	local p = io.popen("ls /sys/bus/platform/drivers/sun50i-h713-afbd/*/mirror_mode 2>/dev/null")
	if p then mirror_path = p:read("*l"); p:close() end
end

local function mirror_mode()
	if not mirror_path then return 0 end
	local f = io.open(mirror_path, "r")
	if not f then return 0 end
	local m = tonumber(f:read("*l")) or 0
	f:close()
	return m
end

local function video_aspect()
	local vp = mp.get_property_native("video-out-params")
	if not vp or not vp.dw or not vp.dh or vp.dh <= 0 then return 16 / 9 end
	local a = vp.dw / vp.dh
	if vp.rotate and vp.rotate % 180 == 90 then a = 1 / a end
	return a
end

-- GLSL builds a mat3 column by column.
local function matrix_glsl(M)
	local c = {}
	for j = 1, 3 do
		for i = 1, 3 do c[#c + 1] = string.format("%.9g", M[i][j]) end
	end
	return "mat3(" .. table.concat(c, ", ") .. ")"
end

local template
local function shader_text(M)
	if not template then
		local f = io.open(opts.shader, "r")
		if not f then return nil end
		template = f:read("*a")
		f:close()
	end
	local text, n = template:gsub("KEYSTONE_MATRIX", matrix_glsl(M))
	return n == 1 and text or nil
end

local function matrix_opts(M)
	local o = {}
	for i = 1, 3 do
		for j = 1, 3 do
			o[#o + 1] = string.format("k%d%d=%.7g", i - 1, j - 1, M[i][j])
		end
	end
	return table.concat(o, ",")
end

local active, last = nil, nil	-- active: the generated shader in use
local serial = 0

local function apply()
	local st = read_kv(opts.state) or {}
	local cf = read_kv(opts.conf) or {}
	local k = tonumber(st.keystone_deg) or 0
	local s, tb, tt = tonumber(cf.lens_s), tonumber(cf.lens_tb), tonumber(cf.lens_tt)
	local mode = mirror_mode()
	local va = video_aspect()
	local key = string.format("%s %s %s %s %d %.4f", k, s, tb, tt, mode, va)
	if key == last then return end
	last = key

	if not (s and tb and tt) or math.abs(k) < opts.min_deg then
		if active then
			mp.commandv("change-list", "glsl-shaders", "remove", active)
			mp.set_property("keepaspect", "yes")
			os.remove(active)
			active = nil
			msg.info(s and "keystone off" or "keystone off: no lens geometry (h713-keystone lens)")
		end
		return
	end

	local deg = math.max(-opts.max_deg, math.min(opts.max_deg, k))
	local phi = math.rad(deg)
	if math.floor(mode / 2) % 2 == 1 then
		tb, tt, phi = -tt, -tb, -phi
	end
	local text = shader_text(warp(phi, s, tb, tt, va))
	if not text then
		msg.error("cannot use " .. opts.shader .. " (missing, or no KEYSTONE_MATRIX)")
		return
	end
	serial = serial + 1
	local path = string.format("/tmp/h713-keystone-%s-%d.glsl", mp.get_property("pid"), serial)
	local f = io.open(path, "w")
	if not f then msg.error("cannot write " .. path); return end
	f:write(text)
	f:close()
	mp.set_property("keepaspect", "no")
	mp.commandv("change-list", "glsl-shaders", "append", path)
	if active then
		mp.commandv("change-list", "glsl-shaders", "remove", active)
		os.remove(active)
	end
	active = path
	msg.info(string.format("keystone %.1f deg (mirror %d, video aspect %.3f)", deg, mode, va))
end

if opts.selftest ~= "" then
	-- Lens of a typical short-throw: tangents chosen to be checked, not real.
	local s, tb = 0.38, 0.02
	local tt = tb + 2 * s * 720 / 1280
	for _, d in ipairs({0, 10, 20, 30, -15}) do
		for _, va in ipairs({16 / 9, 2.39, 4 / 3}) do
			local M = warp(math.rad(d), s, tb, tt, va)
			print(string.format("selftest %g %g %g %g %.6f %s", d, s, tb, tt, va, matrix_opts(M)))
		end
	end
	mp.commandv("quit")
else
	mp.add_periodic_timer(0.5, apply)
	mp.register_event("shutdown", function() if active then os.remove(active) end end)
	mp.observe_property("video-out-params", "native", function() last = nil; apply() end)
end
