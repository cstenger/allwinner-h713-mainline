/* Read scalar PLL bytes through their stock byte access width; no MMIO stores.
 * Displaced regr LW a1 runs in hook delay slot. Only exact aligned config
 * addresses are widened into four byte reads. All other reads retain LW.
 */
.set noreorder
.set noat
.text
.globl _start
_start:
 lui $t0,0xbb88
 xor $t0,$v0,$t0
 sltiu $t1,$t0,0x14
 beq $t1,$zero,original_word
 andi $t1,$t0,3
 bne $t1,$zero,original_word
 addiu $t0,$t0,-8
 sltiu $t1,$t0,4
 bne $t1,$zero,original_word
 nop
 lbu $a2,0($v0)
 lbu $t0,1($v0)
 sll $t0,$t0,8
 or $a2,$a2,$t0
 lbu $t0,2($v0)
 sll $t0,$t0,16
 or $a2,$a2,$t0
 lbu $t0,3($v0)
 sll $t0,$t0,24
 or $a2,$a2,$t0
 j 0x8b18011c
 nop
original_word:
 lw $a2,0($v0)
 j 0x8b18011c
 nop
