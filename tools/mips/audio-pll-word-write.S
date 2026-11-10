/* Cold-installed shim for stock byte writes to PLL scalar config only.
 * Both helpers' displaced first epilogue LW runs in the hook delay slot.
 * t0/a1/a2/a3/v1 are caller-saved; v0, ra and callee-saved regs preserved.
 */
.set noreorder
.set noat
.text
.globl _start
_start:
 lui $t0,0x8b18
 ori $t0,$t0,0x03cc
 b shared
 nop
masked_entry:
 lui $t0,0x8b18
 ori $t0,$t0,0x0434
shared:
 lui $a1,0xbb88
 xor $a1,$a0,$a1
 sltiu $a2,$a1,0x14
 beq $a2,$zero,original_byte
 addiu $a3,$a1,-8
 sltiu $a3,$a3,4
 bne $a3,$zero,original_byte
 andi $a2,$a0,3
 sll $a2,$a2,3
 addiu $a3,$zero,-4
 and $a3,$a0,$a3
 lw $v1,0($a3)
 addiu $a1,$zero,255
 sllv $a1,$a1,$a2
 nor $a1,$zero,$a1
 and $v1,$v1,$a1
 andi $a1,$s1,255
 sllv $a1,$a1,$a2
 or $v1,$v1,$a1
 sw $v1,0($a3)
 jr $t0
 nop
original_byte:
 sb $s1,0($a0)
 jr $t0
 nop
