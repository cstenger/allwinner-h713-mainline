/* FAILED EXPERIMENT -- DO NOT RUN.
 * Hardware faulted inside dcache_disable before the copy loop, then reset.
 * Kept solely to reproduce/analyze the failed installation method.
 * One-boot helper for verified U-Boot relocation 0x7ff13000 only.
 * Source 0x50000000 -> trace table 0x7ffa4880, exactly 6256 bytes.
 * U-Boot's own dcache_disable/enable routines, verified CRC 1625241d.
 * No persistent storage writes. Retains x18 (U-Boot global data pointer).
 */
.text
.global _start
_start:
 stp x29,x30,[sp,#-16]!
 stp x19,x20,[sp,#-16]!
 stp x21,x22,[sp,#-16]!
 ldr x19,source
 ldr x20,destination
 mov x21,#6256
 ldr x22,disable
 blr x22
1:
 ldr x9,[x19],#8
 str x9,[x20],#8
 subs x21,x21,#8
 b.ne 1b
 dsb sy
 ldr x22,enable
 blr x22
 ldp x21,x22,[sp],#16
 ldp x19,x20,[sp],#16
 ldp x29,x30,[sp],#16
 mov x0,#0
 ret
.balign 8
source: .quad 0x50000000
destination: .quad 0x7ffa4880
disable: .quad 0x7ff157e8
enable: .quad 0x7ff15724
