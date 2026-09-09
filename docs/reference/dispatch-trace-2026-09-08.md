# RPC and detector dispatch trace, 2026-09-08

Read-only board investigation plus static disassembly. No new RPCs, frame
submissions, ring writes, or firmware patches were performed.

## The detector has a registered caller

The earlier search concentrated on primary-vtable slot +0x40 and missed the
secondary-base callback thunk:

```
Enable VideoDecoder, 0x8b146e34
  -> message-manager getter 0x8b15817c
  -> manager vtable +0x0c: register(event=8, callback=self+0xbc, arg=0)

message manager DoMessage, 0x8b156bf8
  -> list indexed by message ID
  -> callback vtable +0x0c, dispatch at 0x8b156d28
  -> 0x8b147678: j 0x8b147390; addiu a0,a0,-0xbc [delay slot]
  -> THidTVPro state machine
  -> detector CheckSignal -> GetFrameInfo
```

The constructor writes secondary vptr `0x8b1f8c28` at self+0xbc; that
vtable's +0x0c entry is `0x8b147678`. This is why searching only for loads
from primary-vtable +0x40 was insufficient.

Live ARM reads confirm the registration structure on this boot:

- Manager singleton global `0x4b499dbc` points to MIPS `0x8b7e81c0`.
- Manager vptr is `0x8b1fbfac`; registration method is `0x8b1575d8`.
- Event-8 head is manager+0x1c+8*4; count is manager+0x130c+8*4.
- Count is 6. The sixth node (`0x8b7e8844`) contains callback `0x8b830908`,
  which equals THidTVPro `0x8b83084c` +0xbc.
- Callback magic is `0xa5a5a5a5`, vptr `0x8b1f8c28`, dispatch `0x8b147678`.
- The dispatcher checks this magic before invoking the callback.

These observations establish a registered dispatch path. They do not establish
how often event 8 is produced, whether dispatch is reaching the sixth callback,
or whether a preceding callback blocks. The event producer remains unresolved.
The table at `0x8b22f234` groups IDs `(8,108,208,8)`; do not yet label event 8
as vsync or a timer without tracing the producer.

## GetFrameInfo correction

At `0x8b147834`, GetFrameInfo copies 144 bytes from the selected AFBD descriptor
address into **a1**, its caller-supplied destination. It does not unconditionally
write detector+self+0xb0. CheckSignal (`0x8b147dd0`) explicitly passes self+0xb0;
the `dtv get_fb` path passes a stack buffer.

Thus successful debug parsing with zero persistent detector headers is
consistent. The older statement that those zeros prove GetFrameInfo never
executed is false. They are evidence about the persistent polling path only,
subject also to the cache-visibility limitation below.

## RPC path and what its result proves

The registered SetSource adapter at `0x8b10a218` reads the argument from a0+4,
calls `0x8b14b448`, then writes return-count zero. The HAL routine logs entry,
converts the source via `0x8b12bbf0`, calls `0x8b109174`, and stores its input
source to MIPS global `0x8b2729ac` at instruction `0x8b14b508`.

ARM read `0x4b2729ac` returned zero. This is a useful future witness, but not
proof that the handler did not run: the firmware uses cached KSEG0 data and
ARM /dev/mem does not establish coherence with the MIPS cache. The same caution
applies to ARM observations of detector state and log records. Entry instructions
read from live code matched the source image at both adapter and HAL addresses.

The repository CPU_COMM implementation waits for a RETURN, looks it up by
session, and copies its result. Therefore its successful ioctl is stronger
than a transport ACK. Zero returned values are exactly what the SetSource
adapter writes; they are not themselves an error or proof of a no-op.
The loaded module's entire binary was not matched to this source in this pass.
There is still no independent handler-execution trace for the latest call.

## Next discriminating experiment

Prepare bounded firmware-side witnesses for event-8 dispatch, entry into its
sixth callback, and CheckSignal return. Place witnesses in an established
uncached trace area and preserve original instructions. Inspect the event
producer and previous callbacks before choosing a trigger. A trace should
separate: no event, an earlier blocked callback, state-machine entry with a
failed read, and a successful poll that fails later.

This is a proposed instrumentation experiment, not an executed patch. Do not
increase the ring budget or toggle the source again merely to obtain the same
ambiguous observation. A direct arbitrary function call is not yet justified
without checking thread, locking, and cache requirements.

Firmware SHA-256: `4380f1b3ed7b62aa50582e7cb16a87bdface1b4300578fe3631a416354da30ce`.
Evidence: [disassembly and live callback walk](dispatch-trace-2026-09-08/).
Board remained alive with ring writes exhausted at 1/1.
