0x8b135d58  ae0000a8  sw       $zero, 0xa8($s0)
0x8b135d5c  1000ffa4  b        0x8b135bf0
0x8b135d60  ae0000ac  sw       $zero, 0xac($s0)
0x8b135d64  5043ffa3  beql     $v0, $v1, 0x8b135bf4
0x8b135d68  8fb00038  lw       $s0, 0x38($sp)
0x8b135d6c  8ca30090  lw       $v1, 0x90($a1)
0x8b135d70  24630001  addiu    $v1, $v1, 1
0x8b135d74  2c64000b  sltiu    $a0, $v1, 0xb
0x8b135d78  1480ff9d  bnez     $a0, 0x8b135bf0
0x8b135d7c  aca30090  sw       $v1, 0x90($a1)
0x8b135d80  afa20018  sw       $v0, 0x18($sp)
0x8b135d84  3c028b1f  lui      $v0, 0x8b1f
0x8b135d88  24425d18  addiu    $v0, $v0, 0x5d18        # -> 0x8b1f5d18
0x8b135d8c  afa20014  sw       $v0, 0x14($sp)
0x8b135d90  3c078b1f  lui      $a3, 0x8b1f
0x8b135d94  24020189  addiu    $v0, $zero, 0x189
0x8b135d98  3c068b1f  lui      $a2, 0x8b1f
0x8b135d9c  3c058b1f  lui      $a1, 0x8b1f
0x8b135da0  24e75cc4  addiu    $a3, $a3, 0x5cc4        # -> 0x8b1f5cc4
0x8b135da4  24c65b38  addiu    $a2, $a2, 0x5b38        # -> 0x8b1f5b38
0x8b135da8  24a55104  addiu    $a1, $a1, 0x5104        # -> 0x8b1f5104
0x8b135dac  afa20010  sw       $v0, 0x10($sp)
0x8b135db0  0ec54252  jal      0x8b150948
0x8b135db4  24040003  addiu    $a0, $zero, 3
0x8b135db8  0ec4e898  jal      0x8b13a260
0x8b135dbc  26040078  addiu    $a0, $s0, 0x78
0x8b135dc0  3c028b23  lui      $v0, 0x8b23
0x8b135dc4  8c42f0f4  lw       $v0, -0xf0c($v0)        # -> 0x8b22f0f4
0x8b135dc8  0040f809  jalr     $v0
0x8b135dcc  8e040518  lw       $a0, 0x518($s0)
0x8b135dd0  0ec4f4c9  jal      0x8b13d324
0x8b135dd4  24040004  addiu    $a0, $zero, 4
0x8b135dd8  1000ff85  b        0x8b135bf0
0x8b135ddc  ae000090  sw       $zero, 0x90($s0)
0x8b135de0  24a600c0  addiu    $a2, $a1, 0xc0
0x8b135de4  8ca50518  lw       $a1, 0x518($a1)
0x8b135de8  0ec4da1c  jal      0x8b136870
0x8b135dec  00c02025  move     $a0, $a2
0x8b135df0  5040ff80  beql     $v0, $zero, 0x8b135bf4
0x8b135df4  8fb00038  lw       $s0, 0x38($sp)
0x8b135df8  92020529  lbu      $v0, 0x529($s0)
0x8b135dfc  5040ff7d  beql     $v0, $zero, 0x8b135bf4
0x8b135e00  8fb00038  lw       $s0, 0x38($sp)
0x8b135e04  3c028b23  lui      $v0, 0x8b23
0x8b135e08  8c59f078  lw       $t9, -0xf88($v0)        # -> 0x8b22f078
0x8b135e0c  1320ff78  beqz     $t9, 0x8b135bf0
0x8b135e10  26040272  addiu    $a0, $s0, 0x272
0x8b135e14  1000000b  b        0x8b135e44
0x8b135e18  8fb00038  lw       $s0, 0x38($sp)
0x8b135e1c  3c028b23  lui      $v0, 0x8b23
0x8b135e20  8c42f104  lw       $v0, -0xefc($v0)        # -> 0x8b22f104
0x8b135e24  8e040518  lw       $a0, 0x518($s0)
