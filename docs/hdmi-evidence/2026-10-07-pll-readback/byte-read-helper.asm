0x8b180340  27bdffe8  addiu    $sp, $sp, -0x18
0x8b180344  afb00010  sw       $s0, 0x10($sp)
0x8b180348  afbf0014  sw       $ra, 0x14($sp)
0x8b18034c  0ec60073  jal      0x8b1801cc
0x8b180350  00808025  move     $s0, $a0
0x8b180354  1440000a  bnez     $v0, 0x8b180380
0x8b180358  3c04b500  lui      $a0, 0xb500
0x8b18035c  02042021  addu     $a0, $s0, $a0
0x8b180360  3c102000  lui      $s0, 0x2000
0x8b180364  00902025  or       $a0, $a0, $s0
0x8b180368  90820000  lbu      $v0, ($a0)
0x8b18036c  8fb00010  lw       $s0, 0x10($sp)
0x8b180370  8fbf0014  lw       $ra, 0x14($sp)
0x8b180374  304200ff  andi     $v0, $v0, 0xff
0x8b180378  03e00008  jr       $ra
0x8b18037c  27bd0018  addiu    $sp, $sp, 0x18
0x8b180380  8fb00010  lw       $s0, 0x10($sp)
0x8b180384  8fbf0014  lw       $ra, 0x14($sp)
0x8b180388  00001025  move     $v0, $zero
0x8b18038c  03e00008  jr       $ra
