-- H713 keystone for mpv: pre-warps the picture so a tilted projector shows a
-- level rectangle (docs/keystone-plan.md). RUNS IN mpv ON THE TARGET.
--
--   mpv --script=/usr/local/share/h713/keystone.lua ...   (h713-play does this)
--
-- Every half second it reads /run/h713-keystone/state (h713-keystone's
-- daemon) and the lens geometry in /etc/h713-keystone.conf (`h713-keystone
-- lens`). While the pitch (keystone_deg) or the roll (level_deg) to correct
-- is at least min_deg, it sets keepaspect=no and blend-subtitles=video, and
-- loads keystone.glsl with the matrix below; otherwise it removes all three,
-- so a level projector costs nothing. Without a measured lens it does nothing.
-- keystone.glsl is a template: each new matrix is written into a copy under
-- /tmp and swapped in, because vo=gpu has no //!PARAM.
--
-- The model. The projector is a pinhole: panel position u (0..1, left to
-- right) and v (0..1, top to bottom) leaves the lens along the ray
-- (x, t, 1) = (s(2u - 1), tt - (tt - tb) v, 1) -- right, up, forward. The
-- projector's attitude is rebuilt from gravity: the published pitch, roll and
-- upside-down state give the up vector u in those coordinates, and the lens
-- is taken to face the wall square (its horizontal direction is the wall's
-- normal f); r = u x f. The rotation with rows r, u, f takes a ray to the
-- wall, homogeneously: (X, Y, Z) -> (X/Z, Y/Z) on a wall at unit distance.
-- The panel lands as a quadrilateral; the picture goes in the largest level
-- rectangle with the panel's aspect that fits inside it, letterboxed by the
-- video's own aspect. The shader inverts nothing: it maps each frame
-- position straight to the picture position the wall needs there.
--
-- Mirror: the display mirrors the frame (h713-mirror) after the GPU, so a
-- frame position reaches the lens as D (x, t, 1), D = diag(+-1, +-1, 1). The
-- frame's rotation is then R D -- no longer a pure rotation for the rear
-- modes, which is the point. The picture keeps whatever orientation the
-- mirror gives it uncorrected: its top goes where the frame's top points on
-- the wall, its left where the frame's left points.
--
-- Roll is levelled only in auto on a wall (the daemon's level_deg); on a
-- ceiling the picture's rotation is the projector's yaw, which gravity cannot
-- see. The OSD is drawn after every shader hook in vo=gpu and stays unwarped;
-- subtitles are blended into the video first and warp with it.
--
-- Trims (h713-keystone trim) add to what the daemon publishes: pitch, roll,
-- and yaw -- the projector turned left or right, which gravity cannot see,
-- applied as a turn of the wall about the vertical. Not under `off`. While
-- playing: Alt+Up/Down pitch, Alt+Left/Right yaw, Alt+[ / Alt+] roll, 0.5 deg
-- a press, Alt+0 resets; each is saved through h713-keystone trim --persist
-- (script-message keystone-trim AXIS +D|-D|=D|reset does the same, for a
-- remote or a test).
--
-- selftest=yes prints matrices for a grid of poses and quits (headless check:
-- tools/video/keystone-check.py).

local mp = require 'mp'
local msg = require 'mp.msg'

local opts = {
	state = "/run/h713-keystone/state",
	conf = "/etc/h713-keystone.conf",
	runconf = "/run/h713-keystone/conf",	-- non-persisted settings, if any
	tool = "h713-keystone",
	step = 0.5,
	shader = "/usr/local/share/h713/keystone.glsl",
	min_deg = 0.5,		-- below this the warp is off (sensor noise ~0.1 deg)
	max_deg = 40,		-- pitch; h713-keystone never asks for more than 45
	max_roll = 30,
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

local function cross(a, b)
	return {a[2] * b[3] - a[3] * b[2], a[3] * b[1] - a[1] * b[3], a[1] * b[2] - a[2] * b[1]}
end

local function unit(a)
	local l = math.sqrt(a[1] ^ 2 + a[2] ^ 2 + a[3] ^ 2)
	return {a[1] / l, a[2] / l, a[3] / l}
end

-- Keep the part of convex polygon poly where nx x + ny y <= d.
local function clip(poly, nx, ny, d)
	local out = {}
	for i = 1, #poly do
		local p, q = poly[i], poly[i % #poly + 1]
		local fp, fq = nx * p[1] + ny * p[2] - d, nx * q[1] + ny * q[2] - d
		if fp <= 0 then out[#out + 1] = p end
		if (fp < 0 and fq > 0) or (fp > 0 and fq < 0) then
			local t = fp / (fp - fq)
			out[#out + 1] = {p[1] + t * (q[1] - p[1]), p[2] + t * (q[2] - p[2])}
		end
	end
	return out
end

-- The largest level rectangle of height/width ar inside the convex
-- quadrilateral q: its centre, width and height. For a width w, the centres
-- that fit are q's edges each moved inward by the rectangle's half extent
-- along the edge normal; bisect for the largest w that leaves any.
local function fit(q, ar)
	local area = 0
	local x0, x1, y0, y1 = math.huge, -math.huge, math.huge, -math.huge
	for i = 1, 4 do
		local p, r = q[i], q[i % 4 + 1]
		area = area + p[1] * r[2] - r[1] * p[2]
		x0, x1 = math.min(x0, p[1]), math.max(x1, p[1])
		y0, y1 = math.min(y0, p[2]), math.max(y1, p[2])
	end
	local o = area > 0 and 1 or -1		-- inside is left of each edge when CCW
	local hp = {}
	for i = 1, 4 do
		local p, r = q[i], q[i % 4 + 1]
		local nx, ny = o * (r[2] - p[2]), -o * (r[1] - p[1])
		hp[i] = {nx, ny, nx * p[1] + ny * p[2]}
	end
	local function centres(w)
		local h = w * ar
		local poly = {{x0, y0}, {x1, y0}, {x1, y1}, {x0, y1}}
		for i = 1, 4 do
			local n = hp[i]
			poly = clip(poly, n[1], n[2], n[3] - math.abs(n[1]) * w / 2 - math.abs(n[2]) * h / 2)
			if #poly == 0 then return nil end
		end
		return poly
	end
	local lo, hi = 0, x1 - x0
	for _ = 1, 60 do
		local mid = (lo + hi) / 2
		if centres(mid) then lo = mid else hi = mid end
	end
	local poly = centres(lo)
	local cx, cy = 0, 0
	for _, p in ipairs(poly) do cx, cy = cx + p[1], cy + p[2] end
	return cx / #poly, cy / #poly, lo, lo * ar
end

-- Frame position -> stretched-picture position, homogeneous. pitch: lens tilt
-- toward the projector's own top, roll: its right side above the horizon
-- (degrees, as h713-keystone publishes them), yaw: the projector turned to
-- its right of square (degrees, a trim); inv: upside down; mode:
-- h713-mirror's number; s, tb, tt: the lens tangents (half width, bottom and
-- top edge); va: the video's aspect (width / height).
local function warp(pitch, roll, yaw, inv, mode, s, tb, tt, va)
	local p, r, y = math.rad(pitch), math.rad(roll), math.rad(yaw)
	local si = inv and -1 or 1
	-- Up, in the projector's (right, up, forward) coordinates.
	local up = {math.sin(r), si * math.cos(r) * math.cos(p), si * math.cos(r) * math.sin(p)}
	local fw = unit({-up[3] * up[1], -up[3] * up[2], 1 - up[3] * up[3]})
	local rt = cross(up, fw)
	-- Turned right by yaw: the wall's normal sits that much to its left.
	local cy, sy_ = math.cos(y), math.sin(y)
	rt, fw = {cy * rt[1] + sy_ * fw[1], cy * rt[2] + sy_ * fw[2], cy * rt[3] + sy_ * fw[3]},
		{cy * fw[1] - sy_ * rt[1], cy * fw[2] - sy_ * rt[2], cy * fw[3] - sy_ * rt[3]}
	-- The frame reaches the lens mirrored by the display: D (x, t, 1).
	local hx = mode % 2 == 1 and -1 or 1
	local vy = math.floor(mode / 2) % 2 == 1 and -1 or 1
	local R = {{rt[1] * hx, rt[2] * vy, rt[3]}, {up[1] * hx, up[2] * vy, up[3]}, {fw[1] * hx, fw[2] * vy, fw[3]}}
	-- In frame coordinates the lens tangents are mirrored too.
	local ftb, ftt = tb, tt
	if vy < 0 then ftb, ftt = -tt, -tb end
	local A = {{2 * s, 0, -s}, {0, -(ftt - ftb), ftt}, {0, 0, 1}}
	local RA = mul(R, A)
	-- The frame on the wall.
	local q = {}
	for i, c in ipairs({{0, 0}, {1, 0}, {1, 1}, {0, 1}}) do
		local X = RA[1][1] * c[1] + RA[1][2] * c[2] + RA[1][3]
		local Y = RA[2][1] * c[1] + RA[2][2] * c[2] + RA[2][3]
		local Z = RA[3][1] * c[1] + RA[3][2] * c[2] + RA[3][3]
		if Z <= 0 then return nil end
		q[i] = {X / Z, Y / Z}
	end
	local ar = (tt - tb) / (2 * s)		-- panel height / width
	local cx, cy, w, h = fit(q, ar)
	-- Wall -> the rectangle, 0..1 from the picture's top-left corner, which
	-- is wherever the frame's top-left points (sx, sy).
	local sx = (rt[1] * hx >= 0) and 1 or -1
	local sy = (up[2] * vy >= 0) and 1 or -1
	local B = {
		sx > 0 and {1 / w, 0, -(cx - w / 2) / w} or {-1 / w, 0, (cx + w / 2) / w},
		sy > 0 and {0, -1 / h, (cy + h / 2) / h} or {0, 1 / h, -(cy - h / 2) / h},
		{0, 0, 1},
	}
	-- The rectangle -> mpv's picture, stretched to the frame by keepaspect=no.
	local pa = 1 / ar
	local lx, ly, lw, lh = 0, 0, 1, 1
	if va > pa then lh = pa / va; ly = (1 - lh) / 2 else lw = va / pa; lx = (1 - lw) / 2 end
	local C = {{1 / lw, 0, -lx / lw}, {0, 1 / lh, -ly / lh}, {0, 0, 1}}
	return mul(C, mul(B, RA))
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
			o[#o + 1] = string.format("k%d%d=%.9g", i - 1, j - 1, M[i][j])
		end
	end
	return table.concat(o, ",")
end

local active, last = nil, nil	-- active: the generated shader in use
local serial = 0
local saved_blend

local function off(why)
	if not active then return end
	mp.commandv("change-list", "glsl-shaders", "remove", active)
	mp.set_property("keepaspect", "yes")
	if saved_blend then mp.set_property("blend-subtitles", saved_blend) end
	os.remove(active)
	active = nil
	msg.info(why)
end

-- The settings in force: the runtime file while a non-persisted change made
-- one (it then holds everything), else /etc.
local function settings()
	return read_kv(opts.runconf) or read_kv(opts.conf) or {}
end

local function apply()
	local st = read_kv(opts.state) or {}
	local cf = settings()
	local k = tonumber(st.keystone_deg) or 0
	local l = tonumber(st.level_deg) or 0
	local y = 0
	if (st.keystone or cf.keystone or "auto") ~= "off" then
		k = k + (tonumber(cf.trim_pitch) or 0)
		l = l + (tonumber(cf.trim_roll) or 0)
		y = tonumber(cf.trim_yaw) or 0
	end
	-- Facing a ceiling or floor the daemon gives the tilt from its normal
	-- toward the projector's own top: an upright pose by construction.
	local inv = st.inverted == "1" and (st.surface or "wall") == "wall"
	local s, tb, tt = tonumber(cf.lens_s), tonumber(cf.lens_tb), tonumber(cf.lens_tt)
	local mode = mirror_mode()
	local va = video_aspect()
	local key = string.format("%s %s %s %s %s %s %s %d %.4f", k, l, y, inv, s, tb, tt, mode, va)
	if key == last then return end
	last = key

	if not (s and tb and tt) then
		off("keystone off: no lens geometry (h713-keystone lens)")
		return
	end
	if math.abs(k) < opts.min_deg and math.abs(l) < opts.min_deg and math.abs(y) < opts.min_deg then
		off("keystone off")
		return
	end

	k = math.max(-opts.max_deg, math.min(opts.max_deg, k))
	l = math.max(-opts.max_roll, math.min(opts.max_roll, l))
	y = math.max(-opts.max_roll, math.min(opts.max_roll, y))
	local M = warp(k, l, y, inv, mode, s, tb, tt, va)
	local text = M and shader_text(M)
	if not text then
		msg.error(M and ("cannot use " .. opts.shader .. " (missing, or no KEYSTONE_MATRIX)")
			or "the frame does not reach the wall at this pose")
		return
	end
	serial = serial + 1
	local path = string.format("/tmp/h713-keystone-%s-%d.glsl", mp.get_property("pid"), serial)
	local f = io.open(path, "w")
	if not f then msg.error("cannot write " .. path); return end
	f:write(text)
	f:close()
	if not active then
		saved_blend = mp.get_property("blend-subtitles")
		mp.set_property("keepaspect", "no")
		mp.set_property("blend-subtitles", "video")
	end
	mp.commandv("change-list", "glsl-shaders", "append", path)
	if active then
		mp.commandv("change-list", "glsl-shaders", "remove", active)
		os.remove(active)
	end
	active = path
	msg.verbose("matrix " .. matrix_opts(M))
	msg.info(string.format("keystone %.1f deg, level %.1f deg, yaw %.1f deg (%s, mirror %d, video aspect %.3f)",
		k, l, y, inv and "upside down" or "upright", mode, va))
end

-- Manual adjustment: one trim through h713-keystone (so the CLI, the remote
-- and these keys share one setting), then redraw at once.
local function trim(axis, arg)
	local args = {opts.tool, "trim", axis}
	if arg then args[#args + 1] = arg end
	args[#args + 1] = "--persist"
	local r = mp.command_native({name = "subprocess", args = args, playback_only = false,
		capture_stdout = true, capture_stderr = true})
	if not r or r.status ~= 0 then
		mp.osd_message("keystone trim failed: " .. ((r and r.stderr) or "?"), 3)
		return
	end
	last = nil
	apply()
	local cf = settings()
	mp.osd_message(string.format("keystone trim  pitch %s  yaw %s  roll %s",
		cf.trim_pitch or "0", cf.trim_yaw or "0", cf.trim_roll or "0"), 2)
end

local function bind(key, name, axis, sign)
	mp.add_key_binding(key, name, function()
		trim(axis, (sign > 0 and "+" or "-") .. opts.step)
	end, {repeatable = true})
end

if opts.selftest ~= "" then
	-- Two lenses: this unit's (axis through the picture's centre) and one
	-- with an offset, so neither symmetry hides a sign.
	local lenses = {{0.50149, -0.28092, 0.28325}, {0.38, 0.02, 0.02 + 0.76 * 720 / 1280}}
	-- Physically sensible pairings of attitude and mirror: upright front and
	-- rear, upside-down ceiling and rear-ceiling.
	local poses = {{false, 0}, {false, 1}, {true, 3}, {true, 2}}
	for _, ln in ipairs(lenses) do
		for _, ps in ipairs(poses) do
			for _, p in ipairs({0, 10, 20, 30, -15}) do
				for _, r in ipairs({0, 5, -8}) do
					for _, y in ipairs({0, 6, -10}) do
						for _, va in ipairs({16 / 9, 2.39, 4 / 3}) do
							local M = warp(p, r, y, ps[1], ps[2], ln[1], ln[2], ln[3], va)
							print(string.format("selftest %g %g %g %d %d %.5f %.5f %.5f %.6f %s",
								p, r, y, ps[1] and 1 or 0, ps[2], ln[1], ln[2], ln[3], va, matrix_opts(M)))
						end
					end
				end
			end
		end
	end
	mp.commandv("quit")
else
	bind("Alt+UP", "keystone-pitch-up", "pitch", 1)
	bind("Alt+DOWN", "keystone-pitch-down", "pitch", -1)
	bind("Alt+RIGHT", "keystone-yaw-right", "yaw", 1)
	bind("Alt+LEFT", "keystone-yaw-left", "yaw", -1)
	bind("Alt+]", "keystone-roll-right", "roll", 1)
	bind("Alt+[", "keystone-roll-left", "roll", -1)
	mp.add_key_binding("Alt+0", "keystone-trim-reset", function() trim("reset") end)
	mp.register_script_message("keystone-trim", function(axis, arg) trim(axis, arg) end)
	mp.add_periodic_timer(0.5, apply)
	mp.register_event("shutdown", function() if active then os.remove(active) end end)
	mp.observe_property("video-out-params", "native", function() last = nil; apply() end)
end
