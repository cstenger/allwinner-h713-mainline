# Early DDC claim — experiment, not shipped

`early-ddc.patch` is the opt-in `--early-ddc` path for `h713-hdmi-session.py`
and `h713-hdmi-signal.py`, with its tests. It claims the DDC pins just before
the receiver clock stage that clocks the EDID block (stage 4), and the signal
service then adopts that hold.

Both fresh-source runs failed the no-retry check (v1 `ed-fresh-01`, v2
`v2-fresh-01`, see `../RESUME-early-ddc*-2026-11-06.json`), and the board was
rolled back to session `e8b0a1c3` / signal `2b6ac46d`. The shipped scripts in
`tools/hdmi/` are those exact files. The first-advert fault was later fixed
another way (`hpd-event-v1`, see `docs/hdmi-first-advert-root-cause-2026-11-08.md`).

The patch applies on top of the shipped files with `git apply`. The installer
it was deployed with is still `tools/hdmi/install-early-ddc.py`.
