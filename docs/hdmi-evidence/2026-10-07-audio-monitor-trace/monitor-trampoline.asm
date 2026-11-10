8b1004c0: addiu $sp, $sp, -8
8b1004c4: sw $t8, ($sp)
8b1004c8: sw $t9, 4($sp)
8b1004cc: lui $t8, 0xad98
8b1004d0: lw $t9, 0x100($t8)
8b1004d4: addiu $t9, $t9, 1
8b1004d8: sw $t9, 0x100($t8)
8b1004dc: sw $v0, 0x108($t8)
8b1004e0: sw $v1, 0x10c($t8)
8b1004e4: lw $t9, 4($s1)
8b1004e8: sw $t9, 0x110($t8)
8b1004ec: lw $t9, 8($s1)
8b1004f0: sw $t9, 0x114($t8)
8b1004f4: sw $s1, 0x118($t8)
8b1004f8: beq $v1, $v0, 0x8b100508
8b1004fc: lw $t9, 0x104($t8)
8b100500: addiu $t9, $t9, 1
8b100504: sw $t9, 0x104($t8)
8b100508: lw $t8, ($sp)
8b10050c: lw $t9, 4($sp)
8b100510: addiu $sp, $sp, 8
8b100514: beq $v1, $v0, 0x8b100524
8b100518: nop 
8b10051c: j 0x8b13a2fc
8b100520: nop 
8b100524: j 0x8b13a31c
8b100528: nop 
