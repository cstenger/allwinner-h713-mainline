0x8b13b670  27bdffe0  addiu    $sp, $sp, -0x20
0x8b13b674  00003025  move     $a2, $zero
0x8b13b678  afb00018  sw       $s0, 0x18($sp)
0x8b13b67c  24050001  addiu    $a1, $zero, 1
0x8b13b680  00808025  move     $s0, $a0
0x8b13b684  afbf001c  sw       $ra, 0x1c($sp)
0x8b13b688  0ec600f7  jal      0x8b1803dc
0x8b13b68c  24840004  addiu    $a0, $a0, 4
0x8b13b690  26040010  addiu    $a0, $s0, 0x10
0x8b13b694  24060003  addiu    $a2, $zero, 3
0x8b13b698  0ec600f7  jal      0x8b1803dc
0x8b13b69c  24050007  addiu    $a1, $zero, 7
0x8b13b6a0  3c028b1f  lui      $v0, 0x8b1f
0x8b13b6a4  244270ac  addiu    $v0, $v0, 0x70ac        # -> 0x8b1f70ac
0x8b13b6a8  afa20014  sw       $v0, 0x14($sp)
0x8b13b6ac  3c078b1f  lui      $a3, 0x8b1f
0x8b13b6b0  2402001d  addiu    $v0, $zero, 0x1d
0x8b13b6b4  3c068b1f  lui      $a2, 0x8b1f
0x8b13b6b8  3c058b1f  lui      $a1, 0x8b1f
0x8b13b6bc  24e77090  addiu    $a3, $a3, 0x7090        # -> 0x8b1f7090
0x8b13b6c0  24c67034  addiu    $a2, $a2, 0x7034        # -> 0x8b1f7034
0x8b13b6c4  24a57060  addiu    $a1, $a1, 0x7060        # -> 0x8b1f7060
0x8b13b6c8  24040003  addiu    $a0, $zero, 3
0x8b13b6cc  0ec54252  jal      0x8b150948
0x8b13b6d0  afa20010  sw       $v0, 0x10($sp)
0x8b13b6d4  8fb00018  lw       $s0, 0x18($sp)
0x8b13b6d8  8fbf001c  lw       $ra, 0x1c($sp)
0x8b13b6dc  03e00008  jr       $ra
0x8b13b6e0  27bd0020  addiu    $sp, $sp, 0x20
0x8b13b6e4  27bdff68  addiu    $sp, $sp, -0x98
0x8b13b6e8  afb40080  sw       $s4, 0x80($sp)
0x8b13b6ec  8c940008  lw       $s4, 8($a0)
0x8b13b6f0  24020008  addiu    $v0, $zero, 8
0x8b13b6f4  afa20030  sw       $v0, 0x30($sp)
0x8b13b6f8  afa20048  sw       $v0, 0x48($sp)
0x8b13b6fc  24020011  addiu    $v0, $zero, 0x11
0x8b13b700  24030010  addiu    $v1, $zero, 0x10
0x8b13b704  afb3007c  sw       $s3, 0x7c($sp)
0x8b13b708  afa20034  sw       $v0, 0x34($sp)
0x8b13b70c  001499c0  sll      $s3, $s4, 7
0x8b13b710  2402000b  addiu    $v0, $zero, 0xb
0x8b13b714  afa30044  sw       $v1, 0x44($sp)
