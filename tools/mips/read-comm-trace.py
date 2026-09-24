#!/usr/bin/env python3
"""Read the flashed U-Boot mips-comm-trace mailbox on the H713 board.

Install the trace only with ``h713_disp mips-comm-trace 0x34`` at U-Boot.
This program verifies the source-path trampolines and trace magic before it
interprets the fixed uncached mailbox. It never writes device memory.
"""
import argparse
import importlib.util
import json
from pathlib import Path
import time


PATCHED_WORDS = (
    (0x4b1008e0, 0x3c18ad98),
    (0x4b1008e8, 0xaf190020),
    (0x4b1008f4, 0x8cb90004),
    (0x4b1008fc, 0x0ac57118),
    (0x4b107580, 0x0ec40238),
    (0x4b100920, 0x3c18ad98),
    (0x4b10092c, 0xaf190020),
    (0x4b107588, 0x0ac40248),
    (0x4b10758c, 0x00000000),
    (0x4b100960, 0x3c18ad98),
    (0x4b100968, 0xaf190034),
    (0x4b10097c, 0x0ac42557),
    (0x4b10098c, 0x0ac424e8),
    (0x4b109554, 0x0ac40258),
    (0x4b109558, 0x8fbe00d0),
    (0x4b1009a0, 0x3c18ad98),
    (0x4b1009a8, 0xaf190034),
    (0x4b1095a0, 0x0ac40268),
    (0x4b123f4c, 0x0ec40128),
    (0x4b123f54, 0x0ac400b1),
    (0x4b1204b4, 0x0ec400f0),
    (0x4b12052c, 0x0ec40190),
)

ADAPTER_PATCHED_WORDS = (
    (0x4b10a228, 0x0ec40400),
    (0x4b101000, 0x3c18ad98),
    (0x4b101008, 0xaf190058),
    (0x4b10100c, 0xaf04005c),
    (0x4b101010, 0x3c198b25),
    (0x4b101014, 0x8f393578),
    (0x4b101018, 0xaf190060),
    (0x4b10101c, 0x0ac52d12),
    (0x4b10a230, 0x0ac40410),
    (0x4b101040, 0x3c1aad98),
    (0x4b101048, 0xaf5b0058),
)

MAILBOX = 0x4d980000
MAGIC = 0x434f4d4d
CANARY = 0x43414e31

COMM_STAGES = {
    0: "none", 0xb004: "handler-enter", 0xc001: "handler-return",
    0xc002: "return-send-enter", 0xc009: "return-ack-wait",
    0xc010: "return-ack-woke", 0xc013: "return-send-done",
}
CALL_STAGES = {
    0: "none", 0xe001: "call-irq", 0xe006: "call-action",
    0xe007: "call-worker-enqueue", 0xe008: "call-ack-send",
    0xe009: "call-ack-done", 0xe011: "call-dispatch-done",
}
ACK_STAGES = {
    0: "none", 0xd001: "return-ack-irq", 0xd002: "sender-wakeup",
    0xd004: "sender-wakeup-done", 0xf003: "return-ack-done",
}
SOURCE_STAGES = {
    0: "none", 0x5101: "callback-event", 0x5102: "callback-queued",
    0x5201: "worker-dequeued", 0x5202: "source-unchanged",
    0x5203: "transition-complete",
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--watch", type=float, default=0,
                        help="bounded watch duration in seconds (maximum 60)")
    parser.add_argument("--interval", type=float, default=0.01,
                        help="poll interval in seconds (0.002..1; default 0.01)")
    parser.add_argument("--kmsg", action="store_true",
                        help="also publish changes to the kernel log/serial console")
    parser.add_argument("--source-only", action="store_true",
                        help="sample only source markers and page guards to reduce poll overhead")
    args = parser.parse_args()
    if not 0 <= args.watch <= 60:
        parser.error("--watch must be between 0 and 60 seconds")
    if not 0.002 <= args.interval <= 1:
        parser.error("--interval must be between 0.002 and 1 second")

    spec = importlib.util.spec_from_file_location(
        "mips_shell", Path(__file__).with_name("mips-shell.py"))
    shell = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(shell)
    mem = shell.Mem()

    for address, expected in PATCHED_WORDS:
        actual = mem.u32(address)
        if actual != expected:
            raise SystemExit(f"comm-trace patch mismatch at {address:#x}: "
                             f"{actual:#010x} != {expected:#010x}")
    adapter_site = mem.u32(0x4b10a228)
    adapter_enabled = adapter_site == ADAPTER_PATCHED_WORDS[0][1]
    if adapter_enabled:
        for address, expected in ADAPTER_PATCHED_WORDS:
            actual = mem.u32(address)
            if actual != expected:
                raise SystemExit(f"adapter patch mismatch at {address:#x}: "
                                 f"{actual:#010x} != {expected:#010x}")
    elif adapter_site != 0x0ec52d12:
        raise SystemExit(f"unrecognized adapter call patch {adapter_site:#010x}")
    if mem.u32(MAILBOX + 4) != MAGIC:
        raise SystemExit("comm-trace magic absent; refusing to interpret mailbox")
    if (mem.u32(MAILBOX + 0x80) != CANARY or
            mem.u32(MAILBOX + 0xffc) != CANARY):
        raise SystemExit("comm-trace page guard absent; refusing to interpret mailbox")

    kmsg = open("/dev/kmsg", "w", buffering=1) if args.kmsg else None

    def sample():
        guards = (mem.u32(MAILBOX + 0x80), mem.u32(MAILBOX + 0xffc))
        adapter = ({
            "adapter": f"{mem.u32(MAILBOX + 0x58):04x}",
            "requested": mem.u32(MAILBOX + 0x5c),
            "callback_object": f"{mem.u32(MAILBOX + 0x60):08x}",
        } if adapter_enabled else {})
        if args.source_only:
            callback, event, new, old, source_queue, worker, vp_init = (
                mem.u32(MAILBOX + off) for off in
                (0x20, 0x24, 0x28, 0x2c, 0x30, 0x34, 0x38))
            return {
                "guards": f"{guards[0]:08x}/{guards[1]:08x}",
                **adapter,
                "callback": f"{callback:04x}:{SOURCE_STAGES.get(callback, 'other')}",
                "worker": f"{worker:04x}:{SOURCE_STAGES.get(worker, 'other')}",
                "event": event, "new": new, "old": old,
                "source_queue": f"{source_queue:08x}",
                "vp_init": f"{vp_init:04x}",
            }
        values = [mem.u32(MAILBOX + off) for off in
                  (0x00, 0x08, 0x0c, 0x10, 0x20, 0x24, 0x28, 0x2c,
                   0x30, 0x34, 0x38, 0x40, 0x44, 0x48, 0x4c, 0x50, 0x54)]
        (comm, queue, call, ack, callback, event, new, old, source_queue,
         worker, vp_init, frame, dirty, mode, control, commit, dirty_latch) = values
        return {
            "guards": f"{guards[0]:08x}/{guards[1]:08x}",
            **adapter,
            "comm": f"{comm:04x}:{COMM_STAGES.get(comm, 'other')}",
            "call": f"{call:04x}:{CALL_STAGES.get(call, 'other')}",
            "ack": f"{ack:04x}:{ACK_STAGES.get(ack, 'other')}",
            "queue": f"{queue:08x}",
            "callback": f"{callback:04x}:{SOURCE_STAGES.get(callback, 'other')}",
            "worker": f"{worker:04x}:{SOURCE_STAGES.get(worker, 'other')}",
            "event": event, "new": new, "old": old,
            "source_queue": f"{source_queue:08x}",
            "vp_init": f"{vp_init:04x}", "frame": f"{frame:04x}",
            "dirty": f"{dirty:08x}", "mode": f"{mode:08x}",
            "control": f"{control:08x}", "commit": f"{commit:08x}",
            "dirty_latch": f"{dirty_latch:08x}",
        }

    started = time.monotonic()
    previous = None
    while True:
        now = time.monotonic()
        state = sample()
        state["seconds"] = round(now - started, 3)
        comparable = tuple((key, value) for key, value in state.items()
                           if key != "seconds")
        if comparable != previous or now - started >= args.watch:
            line = json.dumps(state, separators=(",", ":"))
            print(line, flush=True)
            if kmsg:
                kmsg.write("<6>h713-mips-trace: " + line + "\n")
            previous = comparable
        if now - started >= args.watch:
            break
        time.sleep(min(args.interval, args.watch - (now - started)))


if __name__ == "__main__":
    main()
