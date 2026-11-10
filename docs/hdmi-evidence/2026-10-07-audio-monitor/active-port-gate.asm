0x8b139348  0ec4e3e1  jal      0x8b138f84
0x8b13934c  02002025  move     $a0, $s0
0x8b139350  92020531  lbu      $v0, 0x531($s0)
0x8b139354  5040ffe3  beql     $v0, $zero, 0x8b1392e4
0x8b139358  8fb00020  lw       $s0, 0x20($sp)
0x8b13935c  8e06054c  lw       $a2, 0x54c($s0)
0x8b139360  02202825  move     $a1, $s1
0x8b139364  26040080  addiu    $a0, $s0, 0x80
0x8b139368  8fb10024  lw       $s1, 0x24($sp)
0x8b13936c  8fb00020  lw       $s0, 0x20($sp)
0x8b139370  8fb20028  lw       $s2, 0x28($sp)
0x8b139374  8fbf002c  lw       $ra, 0x2c($sp)
0x8b139378  0ac4e8aa  j        0x8b13a2a8
0x8b13937c  27bd0030  addiu    $sp, $sp, 0x30
