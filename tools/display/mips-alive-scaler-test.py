#!/usr/bin/env python3
"""Is the scaler at 0x05000000 live when the display MIPS is? RUNS ON THE HOST.

WHY THIS EXISTS. tools/display/scaler-probe.sh established, with the MIPS
PARKED, that this block is fully writable from Linux (every ratio and coordinate
register takes 0xDEADBEEF verbatim and restores clean) but completely inert: no
register moves at idle, none moves across a confirmed-scanning-out 720p DECD
playback, and holding a 2:1 ratio for eight seconds changed nothing on the
panel, operator watching.

Disassembling the firmware routine that configures it (0x8b1a4810) explains why
that null is weak. The scaler's fields are not computed there -- they are copied
out of a PanelWinNode window descriptor, gated by dirty bits. The block belongs
to the MIPS's WINDOW/COMPOSITION layer. Our KMS driver injects at AFBD and takes
the output at the LVDS selector, bypassing that layer entirely, so a scaler
sitting inside it would be exactly this: present, writable, and deaf.

THE TEST. Bring the display up with the MIPS ALIVE and ask the same questions
again. `h713_disp init <id>` does precisely that -- `quiesce` is opt-in, so the
plain form leaves the core running and the logo published. Then:

  1. read-only: does anything in the block MOVE now? With the MIPS parked,
     zero of 55 registers moved. If the window layer is live and the scaler is
     in it, something should.
  2. visible: hold a 2:1 ratio and look at the logo.

WHY THIS SHAPE, AND NOT THE ONE ORIGINALLY PLANNED. The first design booted
Linux with the MIPS alive and pushed a static DECD frame. This needs neither.
The logo is already rendered THROUGH the MIPS's own display path -- that is how
it gets on the glass -- so if the scaler affects the panel at all it must affect
the logo. That removes Linux, Cedrus, the DECD submit and the kernel module from
the experiment, and with them the one documented whole-SoC hazard: live display
MIPS plus real Cedrus/DECD traffic hard-locks with no watchdog recovery. Nothing
here goes near that combination.

KNOWN LIMIT, stated so a null is not over-read: the logo is a static image on
what may be the OSD/UI window. If the scaler serves only the video window, it
could be live and still not touch the logo. A POSITIVE here is decisive; a
negative narrows the question to "not on the UI path" and the video-window
version of this test is the follow-on.

  usage: tools/display/mips-alive-scaler-test.py            # read-only
         tools/display/mips-alive-scaler-test.py --visible  # adds the ratio hold
         PORT=/dev/ttyUSB0 PROJECT=0x34 tools/display/mips-alive-scaler-test.py
"""
import os, sys, time, termios, argparse

PORT = os.environ.get("PORT", "/dev/ttyUSB0")
PROJECT = os.environ.get("PROJECT", "0x34")
SCALER = 0x05000000
MIPS_STATUS = 0x0306101C

# The registers the firmware's own configure routine touches, so a sample here
# is the same set scaler-probe.sh sampled from Linux and the two are comparable.
OFFS = [0x004, 0x010, 0x018, 0x01c, 0x030, 0x040, 0x0f0, 0x138,
        0x174, 0x178, 0x1b4, 0x1b8, 0x210, 0x224,
        0x274, 0x278, 0x2b4, 0x2b8,
        0x804, 0x808, 0x80c, 0x82c, 0x840, 0x844, 0x854, 0x858, 0x85c, 0x860]
RATIOS = [(0x274, "space B (720-tall)"), (0x174, "space A (1080-tall)")]
UNITY = "0x00400040"
TEST_RATIO = "0x00800080"


def open_port(path):
    fd = os.open(path, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
    a = termios.tcgetattr(fd)
    a[0] = 0; a[1] = 0
    a[2] = termios.CS8 | termios.CREAD | termios.CLOCAL
    a[3] = 0
    a[4] = termios.B115200; a[5] = termios.B115200
    a[6][termios.VMIN] = 0; a[6][termios.VTIME] = 0
    termios.tcsetattr(fd, termios.TCSANOW, a)
    return fd


def drain(fd):
    while True:
        try:
            if not os.read(fd, 65536):
                return
        except BlockingIOError:
            return


def write_slow(fd, data, per_char=0.002):
    for b in data:
        os.write(fd, bytes([b]))
        time.sleep(per_char)


def cmd(fd, s, settle=0.4, quiet_for=1.2, echo=False):
    """Send one U-Boot command, return everything it printed."""
    write_slow(fd, s.encode() + b"\n")
    time.sleep(settle)
    out = b""
    last = time.time()
    while time.time() - last < quiet_for:
        try:
            b = os.read(fd, 65536)
        except BlockingIOError:
            b = b""
        if b:
            out += b
            last = time.time()
            if echo:
                sys.stdout.write(b.decode("utf-8", "replace"))
                sys.stdout.flush()
        else:
            time.sleep(0.02)
    return out.decode("utf-8", "replace")


def md(fd, addr):
    """Read one 32-bit word with U-Boot's md.l, returned as 0xXXXXXXXX."""
    out = cmd(fd, "md.l 0x%08x 1" % addr, settle=0.2, quiet_for=0.5)
    for line in out.splitlines():
        parts = line.replace(":", " ").split()
        # "05000174: 00400040    @.@."  -> take the token after the address
        if len(parts) >= 2 and parts[0].lower().lstrip("0") in (
                ("%x" % addr).lstrip("0"), "%08x" % addr):
            try:
                return "0x%08X" % int(parts[1], 16)
            except ValueError:
                pass
    return "?"


def mw(fd, addr, value):
    cmd(fd, "mw.l 0x%08x %s" % (addr, value), settle=0.2, quiet_for=0.5)


def catch_uboot(fd, secs=45.0, cold=False):
    """Reboot and hold the U-Boot prompt. Types across the whole reset, because
    the autoboot delay is short and cannot be asked for after the fact.

    cold=True omits the `reboot` command and only sends interrupt keys, for when
    the operator is pulling power. THAT IS NOT A CONVENIENCE. A warm reboot out
    of a running Linux leaves the panel powered, so the bring-up's "power on"
    (PF6 high, PH16 pulsed) is a no-op, the panel never re-runs its own init,
    and the display comes up BLACK while every log line still reports success.
    U-Boot says "Power-cycle before another init" for this reason."""
    if not cold:
        write_slow(fd, b"reboot\n")
    end = time.time() + secs
    last_key = 0.0
    out = b""
    while time.time() < end:
        try:
            chunk = os.read(fd, 4096)
        except BlockingIOError:
            chunk = b""
        if chunk:
            out += chunk
            sys.stdout.write(chunk.decode("utf-8", "replace"))
            sys.stdout.flush()
        if time.time() - last_key > 0.05:
            os.write(fd, b" ")
            last_key = time.time()
        time.sleep(0.01)
    write_slow(fd, b"\x15\n")      # clear the line of spaces
    time.sleep(0.5)
    drain(fd)
    return out.decode("utf-8", "replace")


def release_mips(fd):
    """Replay h713_mips_release_reset() with mw.l. The firmware is already
    resident at 0x4b100000 with its shared memory published, so after the
    preboot has quiesced the core it can simply be released again -- no
    reflash. The original's 12 ms settling delays are satisfied for free at
    115200 baud."""
    print()
    print("=== releasing the MIPS ===")
    print("    status before: %s" % md(fd, MIPS_STATUS))
    for addr, val, what in [
            (0x02001600, "0x80000002", "clock"),
            (0x0200160c, "0x00000000", "reset asserted"),
            (0x0200160c, "0x00010000", "stage 1"),
            (0x0200160c, "0x00030000", "stage 2"),
            (0x0200160c, "0x00030001", "stage 3"),
            (0x03061030, "0x4b100000", "boot address"),
            (0x0200160c, "0x00070001", "RELEASED")]:
        mw(fd, addr, val)
        time.sleep(0.15)
    time.sleep(1.5)
    after = md(fd, MIPS_STATUS)
    print("    status after:  %s%s" % (after, "" if after == "0x00000001" else "  !! NOT ALIVE"))
    return after == "0x00000001"


def run_census(fd):
    print()
    print("=== read-only: does anything MOVE? ===")
    print("    With the MIPS parked, zero of 55 registers moved. Three samples.")
    samples = []
    for i in range(3):
        samples.append({o: md(fd, SCALER + o) for o in OFFS})
        if i < 2:
            time.sleep(1.0)
    moved = [o for o in OFFS if len({s[o] for s in samples}) > 1]
    for o in OFFS:
        vals = [s[o] for s in samples]
        print("    +0x%04x  %s  %s" % (o, " -> ".join(vals), "MOVES" if o in moved else ""))
    print()
    if moved:
        print("    => %d register(s) move: %s" %
              (len(moved), ", ".join("+0x%04x" % o for o in moved)))
        print("       The block is ACTIVE in the live window layer.")
    else:
        print("    => still nothing moves; inconclusive on its own.")
    return moved


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--visible", action="store_true",
                    help="add the ratio hold (someone must watch the panel)")
    ap.add_argument("--hold", type=float, default=8.0)
    ap.add_argument("--no-reboot", action="store_true",
                    help="assume the board is already sitting at the U-Boot prompt")
    ap.add_argument("--relight", action="store_true",
                    help="teardown, then panel-test <id> vendor-logo: puts the stock "
                         "logo on the glass AND leaves the MIPS alive. Use this for a "
                         "visible run -- plain 'init' renders nothing.")
    ap.add_argument("--no-init", action="store_true",
                    help="touch nothing; test whatever is already displayed (e.g. the "
                         "preboot's logo, which is stock's own configuration)")
    ap.add_argument("--release-mips", action="store_true",
                    help="after a normal boot (logo up, MIPS quiesced by the preboot), "
                         "replay the firmware release sequence with mw.l to un-quiesce "
                         "the core WITHOUT reflashing. This is the only way found to get "
                         "an image on the glass with the window layer live.")
    ap.add_argument("--diff-release", action="store_true",
                    help="dump every display block, release the MIPS, dump again, and "
                         "diff. Shows exactly which registers the window layer takes "
                         "over when it blanks an ARM-published image. Read-only apart "
                         "from the release itself.")
    ap.add_argument("--recommit", action="store_true",
                    help="with --diff-release: after the diff, re-assert the stock OSD "
                         "commit (control bit 0 at 0x05600140, then 1 to 0x05600144) and "
                         "see whether the logo comes back with the core still running")
    ap.add_argument("--cold", action="store_true",
                    help="operator pulls power; do not send 'reboot'. Required for a "
                         "visible run -- a warm reboot leaves the panel powered and "
                         "the bring-up's panel power-on becomes a no-op, giving a "
                         "black screen that still logs success.")
    args = ap.parse_args()

    fd = open_port(PORT)
    drain(fd)

    if not args.no_reboot:
        if args.cold:
            print("=== waiting for a COLD power cycle ===")
            print("    Pull the power now, wait ~5 s, and plug it back in.")
            print("    Listening for U-Boot and holding the prompt for 60 s.")
            catch_uboot(fd, secs=60.0, cold=True)
        else:
            print("=== rebooting to the U-Boot prompt ===")
            catch_uboot(fd)
    print()

    banner = cmd(fd, "version", quiet_for=1.0)
    if "U-Boot" not in banner:
        print("!! not at a U-Boot prompt -- got:")
        print(banner[-400:])
        print("   Re-run without --no-reboot, or interrupt autoboot manually.")
        return 1
    print("=== at the U-Boot prompt ===")

    if args.diff_release:
        # The AFBD source pointer SURVIVED the release last time -- 0x05600178
        # still held 0x6c100000, the logo's address -- and the panel went black
        # anyway. So the window layer changed something else, and a before/after
        # dump names it. `h713_disp dump` walks every display block, so diffing
        # two of them is the cheapest possible way to ask "what did the MIPS take
        # over?", and it costs nothing but a power cycle.
        print()
        print("=== dump A: ARM-published logo, MIPS parked ===")
        dump_a = cmd(fd, "h713_disp dump", settle=1.0, quiet_for=8.0)
        print("    %d lines captured" % len(dump_a.splitlines()))
        release_mips(fd)
        print()
        print("=== dump B: same display, MIPS now running ===")
        dump_b = cmd(fd, "h713_disp dump", settle=1.0, quiet_for=8.0)
        print("    %d lines captured" % len(dump_b.splitlines()))
        print()
        print("=== what the window layer took over ===")
        a = [l.rstrip() for l in dump_a.splitlines() if ":" in l and "+0x" in l]
        b = [l.rstrip() for l in dump_b.splitlines() if ":" in l and "+0x" in l]
        block_a = block_b = ""
        diffs = 0
        for la, lb in zip(a, b):
            if la != lb:
                print("    A: %s" % la.strip())
                print("    B: %s" % lb.strip())
                diffs += 1
        print()
        print("    %d differing dump line(s)" % diffs)
        if not diffs:
            print("    => the window layer changed NOTHING in the display blocks.")
            print("       Then the black is not a register takeover, and the frame")
            print("       source itself is what stopped being consumed.")
        if args.recommit:
            # tgd_put_plane_info() sets bit 0 in the AFBD channel control at
            # +0x00, then osd_ready_for_update() writes literal 1 to the channel
            # ready register at +0x04. Its lookup table is {0x05600100,
            # 0x05600140}, so 0x140 is the channel in play here.
            print()
            print("=== re-asserting the stock OSD commit with the core running ===")
            ctrl = md(fd, 0x05600140)
            print("    channel control 0x05600140 = %s" % ctrl)
            try:
                val = "0x%08X" % (int(ctrl, 16) | 1)
            except ValueError:
                val = "0x03001901"
            mw(fd, 0x05600140, val)
            time.sleep(0.2)
            mw(fd, 0x05600144, "0x00000001")
            time.sleep(1.0)
            print("    committed; source 0x05600178 = %s" % md(fd, 0x05600178))
            print()
            print("    >>> LOOK AT THE PANEL <<<")
            print("    logo back  -> the MIPS consumes ARM-programmed AFBD frames.")
            print("                  That is the feed path, and the route is open.")
            print("    still black-> the core owns the plane and ignores ours; feeding")
            print("                  it needs the window-descriptor path (tgd_put_plane_info).")
        os.close(fd)
        return 0

    if args.release_mips:
        # The whole of h713_mips_release_reset() is seven register writes, and
        # the firmware image is ALREADY at 0x4b100000 from this boot's own run,
        # with the shared memory already published. So after the preboot has put
        # the logo up and quiesced the core, the core can simply be released
        # again -- image on the glass AND window layer live, with no reflash.
        #
        # The 12 ms settling delays in the original are satisfied for free:
        # typing each command over 115200 baud takes far longer than that.
        print()
        print("=== releasing the MIPS with the logo already up ===")
        before = md(fd, MIPS_STATUS)
        print("    MIPS status before: %s (expect 0x00000000 after the preboot)" % before)
        for addr, val, what in [
                (0x02001600, "0x80000002", "clock"),
                (0x0200160c, "0x00000000", "reset asserted"),
                (0x0200160c, "0x00010000", "stage 1"),
                (0x0200160c, "0x00030000", "stage 2"),
                (0x0200160c, "0x00030001", "stage 3"),
                (0x03061030, "0x4b100000", "boot address (firmware already resident)"),
                (0x0200160c, "0x00070001", "RELEASED")]:
            print("    mw.l 0x%08x %s   %s" % (addr, val, what))
            mw(fd, addr, val)
            time.sleep(0.15)
        time.sleep(1.5)
        after = md(fd, MIPS_STATUS)
        print("    MIPS status after:  %s" % after)
        if after != "0x00000001":
            print("    !! the core did not come up. Nothing has been flashed and the")
            print("       logo path is untouched; a power cycle returns to a known state.")
            os.close(fd)
            return 1
        print("    MIPS is ALIVE, and the logo was already on the glass")
        print()
        print("    >>> IS THE LOGO STILL THERE? <<<")
        print("    If the firmware took the display back and blanked it, that is")
        print("    itself the answer: the ARM framebuffer route and the live window")
        print("    layer are mutually exclusive. Do not read a blank panel as a")
        print("    scaler result.")
        time.sleep(5)
    print()
    if args.no_init:
        print("=== using the display exactly as it is ===")
        print("    No init, no teardown. If the preboot published the boot logo and")
        print("    autoboot was interrupted, this is STOCK's own display")
        print("    configuration, untouched by our KMS driver -- a state the Linux")
        print("    probe could never test.")
    elif args.release_mips:
        pass
    elif args.relight:
        # `init` alone renders NOTHING -- it brings the display up "ready for
        # diagnostics". A black panel after it is correct behaviour, not a
        # failed panel power-on, and reading it as the latter cost a power
        # cycle. panel-test DOES render, and takes `quiesce` as an OPT-IN, so
        # its default leaves the MIPS running. teardown first, because it drops
        # the panel rail and is what makes a second bring-up behave like a
        # first -- that is the whole reason it was written.
        print("=== teardown, then relight with the MIPS ALIVE ===")
        print("    h713_disp teardown")
        cmd(fd, "h713_disp teardown", settle=1.0, quiet_for=6.0, echo=True)
        print()
        print("    h713_disp panel-test %s vendor-logo   ('quiesce' NOT passed)" % PROJECT)
        cmd(fd, "h713_disp panel-test %s vendor-logo" % PROJECT,
            settle=1.0, quiet_for=25.0, echo=True)
    else:
        print("=== bringing the display up with the MIPS ALIVE ===")
        print("    h713_disp init %s   (no 'quiesce' -- the core keeps running)" % PROJECT)
        print("    NOTE: init renders nothing. Expect a black panel; use --relight")
        print("    if you need an image on the glass for a visible test.")
        cmd(fd, "h713_disp init %s" % PROJECT, settle=1.0, quiet_for=6.0, echo=True)

    status = md(fd, MIPS_STATUS)
    print()
    print("    MIPS status 0x%08x = %s" % (MIPS_STATUS, status))
    if args.release_mips and status == "0x00000001":
        pass
    if status == "0x00000001":
        print("    MIPS is ALIVE -- the window layer should be running")
    elif args.no_init:
        print("    MIPS is parked, as expected for --no-init. This run tests STOCK's")
        print("    own display configuration, which is still new ground: every")
        print("    previous parked-MIPS reading was taken against OUR KMS driver's.")
    else:
        print("    !! expected 0x00000001 (alive). Without a live MIPS this test")
        print("       measures nothing that scaler-probe.sh has not already measured.")
        return 1

    print()
    print("    >>> IS THE LOGO ON THE PANEL? <<<")
    print("    U-Boot prints 'logo published' on a black boot too, so the message")
    print("    is not the check -- your eyes are. If the panel is black, stop:")
    print("    every reading below would be from a display that is not scanning.")
    time.sleep(4)

    if args.visible:
        # panel-test renders are TIME-LIMITED (the checker variants hold ~15s and
        # then restore every touched word). 28 registers x 3 samples is ~60s of
        # md reads, which would spend the image before the holds begin. The idle
        # census has already been taken twice, parked and alive, and did not move
        # either time -- so in a visible run, go straight to the test that matters.
        print()
        print("=== idle census skipped: the render is time-limited ===")
        print("    Taken twice already (MIPS parked and alive); nothing moved, and")
        print("    spending 60s of md reads here would outlast the image.")
    else:
        run_census(fd)

    if not args.visible:
        print()
        print("=== visible test skipped (read-only run) ===")
        print("    re-run with --visible --relight, with someone watching the panel.")
        os.close(fd)
        return 0

    _unused = """
    print()
    print("=== read-only: does anything MOVE with the MIPS alive? ===")
    print("    With the MIPS parked, zero of 55 registers moved. Three samples.")
    samples = []
    for i in range(3):
        samples.append({o: md(fd, SCALER + o) for o in OFFS})
        if i < 2:
            time.sleep(1.0)
    moved = []
    for o in OFFS:
        vals = [s[o] for s in samples]
        flag = "MOVES" if len(set(vals)) > 1 else ""
        if flag:
            moved.append(o)
        print("    +0x%04x  %s  %s" % (o, " -> ".join(vals), flag))
    print()
    if moved:
        print("    => %d register(s) move with the MIPS alive: %s" %
              (len(moved), ", ".join("+0x%04x" % o for o in moved)))
        print("       The block is ACTIVE in the live window layer. That is the")
        print("       positive scaler-probe.sh could not produce with the MIPS parked.")
    else:
        print("    => still nothing moves. The block has no observable state even")
        print("       with the window layer running, so this remains inconclusive")
        print("       on its own -- the ratio hold below is the real test.")

    """

    print()
    print("=== visible: hold a 2:1 ratio and watch the LOGO ===")
    for off, label in RATIOS:
        orig = md(fd, SCALER + off)
        print()
        print("    ---- +0x%04x, %s ----" % (off, label))
        print("    baseline %s -- look at the logo NOW" % orig)
        if orig != UNITY:
            print("    note: not at unity; restoring to this exact value afterwards")
        time.sleep(3)
        print("    >>> WRITING %s -- WATCH THE PANEL FOR %.0fs <<<" % (TEST_RATIO, args.hold))
        mw(fd, SCALER + off, TEST_RATIO)
        held = md(fd, SCALER + off)
        print("    held value reads %s" % held)
        time.sleep(args.hold)
        print("    >>> RESTORING <<<")
        mw(fd, SCALER + off, orig)
        back = md(fd, SCALER + off)
        if back != orig:
            print("    *** RESTORE FAILED: wanted %s, read %s" % (orig, back))
            print("    *** Stop here. Cold power cycle, not a reboot.")
            os.close(fd)
            return 3
        print("    restored to %s (verified)" % back)
        time.sleep(2)

    print()
    print("    WHAT DID YOU SEE?")
    print("      logo changed on either  -> the scaler IS live in the MIPS window")
    print("                                 layer. The MIPS route is real, and the")
    print("                                 parked-MIPS null is explained.")
    print("      no change on either     -> the scaler does not serve the UI window.")
    print("                                 Narrows it; the video-window test is next.")
    print()
    print("    The board is still at the U-Boot prompt with the MIPS alive.")
    print("    'boot' will continue to Linux; a cold power cycle is always safe.")
    os.close(fd)
    return 0


if __name__ == "__main__":
    sys.exit(main())
