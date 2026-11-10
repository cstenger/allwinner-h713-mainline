0x8b1800d8  24020002  addiu    $v0, $zero, 2
0x8b1800dc  10820003  beq      $a0, $v0, 0x8b1800ec
0x8b1800e0  3c048b20  lui      $a0, 0x8b20
0x8b1800e4  0ac56cc1  j        0x8b15b304
0x8b1800e8  24841808  addiu    $a0, $a0, 0x1808        # -> 0x8b201808
0x8b1800ec  27bdffe0  addiu    $sp, $sp, -0x20
0x8b1800f0  8ca50004  lw       $a1, 4($a1)
0x8b1800f4  afbf001c  sw       $ra, 0x1c($sp)
0x8b1800f8  00a02025  move     $a0, $a1
0x8b1800fc  0ec56813  jal      0x8b15a04c
0x8b180100  afa50010  sw       $a1, 0x10($sp)
0x8b180104  3c03b500  lui      $v1, 0xb500
0x8b180108  00431021  addu     $v0, $v0, $v1
0x8b18010c  3c032000  lui      $v1, 0x2000
0x8b180110  00431025  or       $v0, $v0, $v1
0x8b180114  8c460000  lw       $a2, ($v0)
0x8b180118  8fa50010  lw       $a1, 0x10($sp)
0x8b18011c  8fbf001c  lw       $ra, 0x1c($sp)
0x8b180120  3c048b20  lui      $a0, 0x8b20
0x8b180124  24841820  addiu    $a0, $a0, 0x1820        # -> 0x8b201820
0x8b180128  0ac56cc1  j        0x8b15b304
0x8b18012c  27bd0020  addiu    $sp, $sp, 0x20
