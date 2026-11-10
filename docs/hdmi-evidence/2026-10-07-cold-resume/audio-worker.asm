0x8b13a270  afbf0014  sw       $ra, 0x14($sp)
0x8b13a274  0ec6f4ad  jal      0x8b1bd2b4
0x8b13a278  00808025  move     $s0, $a0
0x8b13a27c  2604001c  addiu    $a0, $s0, 0x1c
0x8b13a280  24060014  addiu    $a2, $zero, 0x14
0x8b13a284  0ec6f4ad  jal      0x8b1bd2b4
0x8b13a288  00002825  move     $a1, $zero
0x8b13a28c  8fbf0014  lw       $ra, 0x14($sp)
0x8b13a290  ae000030  sw       $zero, 0x30($s0)
0x8b13a294  ae000034  sw       $zero, 0x34($s0)
0x8b13a298  ae00003c  sw       $zero, 0x3c($s0)
0x8b13a29c  8fb00010  lw       $s0, 0x10($sp)
0x8b13a2a0  03e00008  jr       $ra
0x8b13a2a4  27bd0018  addiu    $sp, $sp, 0x18
0x8b13a2a8  27bdffb8  addiu    $sp, $sp, -0x48
0x8b13a2ac  afb50040  sw       $s5, 0x40($sp)
0x8b13a2b0  3c158b23  lui      $s5, 0x8b23
0x8b13a2b4  afb30038  sw       $s3, 0x38($sp)
0x8b13a2b8  26b5f0bc  addiu    $s5, $s5, -0xf44        # -> 0x8b22f0bc
0x8b13a2bc  8cb30518  lw       $s3, 0x518($a1)
0x8b13a2c0  8ea20004  lw       $v0, 4($s5)        # -> 0x8b22f0c0
0x8b13a2c4  afb0002c  sw       $s0, 0x2c($sp)
0x8b13a2c8  afb10030  sw       $s1, 0x30($sp)
0x8b13a2cc  afb20034  sw       $s2, 0x34($sp)
0x8b13a2d0  afb4003c  sw       $s4, 0x3c($sp)
0x8b13a2d4  00808825  move     $s1, $a0
0x8b13a2d8  afbf0044  sw       $ra, 0x44($sp)
0x8b13a2dc  02602025  move     $a0, $s3
0x8b13a2e0  8cb400b0  lw       $s4, 0xb0($a1)
0x8b13a2e4  00a08025  move     $s0, $a1
0x8b13a2e8  0040f809  jalr     $v0
0x8b13a2ec  00c09025  move     $s2, $a2
0x8b13a2f0  92230010  lbu      $v1, 0x10($s1)
0x8b13a2f4  10620009  beq      $v1, $v0, 0x8b13a31c
0x8b13a2f8  26050078  addiu    $a1, $s0, 0x78
0x8b13a2fc  8ea30008  lw       $v1, 8($s5)        # -> 0x8b22f0c4
0x8b13a300  02802025  move     $a0, $s4
0x8b13a304  a2220010  sb       $v0, 0x10($s1)
0x8b13a308  0060f809  jalr     $v1
0x8b13a30c  afa50020  sw       $a1, 0x20($sp)
0x8b13a310  82220010  lb       $v0, 0x10($s1)
0x8b13a314  04400036  bltz     $v0, 0x8b13a3f0
0x8b13a318  8fa50020  lw       $a1, 0x20($sp)
0x8b13a31c  8ea20018  lw       $v0, 0x18($s5)        # -> 0x8b22f0d4
0x8b13a320  0040f809  jalr     $v0
0x8b13a324  02602025  move     $a0, $s3
0x8b13a328  92220010  lbu      $v0, 0x10($s1)
0x8b13a32c  304200f0  andi     $v0, $v0, 0xf0
0x8b13a330  50400026  beql     $v0, $zero, 0x8b13a3cc
0x8b13a334  8fb0002c  lw       $s0, 0x2c($sp)
0x8b13a338  8e22000c  lw       $v0, 0xc($s1)
0x8b13a33c  54400023  bnel     $v0, $zero, 0x8b13a3cc
0x8b13a340  8fb0002c  lw       $s0, 0x2c($sp)
0x8b13a344  8e22003c  lw       $v0, 0x3c($s1)
0x8b13a348  24420001  addiu    $v0, $v0, 1
0x8b13a34c  2c430065  sltiu    $v1, $v0, 0x65
0x8b13a350  5460002c  bnel     $v1, $zero, 0x8b13a404
0x8b13a354  ae22003c  sw       $v0, 0x3c($s1)
0x8b13a358  8e260000  lw       $a2, ($s1)
0x8b13a35c  8e230004  lw       $v1, 4($s1)
0x8b13a360  00c31025  or       $v0, $a2, $v1
0x8b13a364  10400018  beqz     $v0, 0x8b13a3c8
0x8b13a368  ae20003c  sw       $zero, 0x3c($s1)
0x8b13a36c  0246001b  divu     $zero, $s2, $a2
0x8b13a370  00c001f4  teq      $a2, $zero, 7
0x8b13a374  3c028b1f  lui      $v0, 0x8b1f
0x8b13a378  24426dcc  addiu    $v0, $v0, 0x6dcc        # -> 0x8b1f6dcc
0x8b13a37c  afa20014  sw       $v0, 0x14($sp)
0x8b13a380  3c058b1f  lui      $a1, 0x8b1f
0x8b13a384  240201ce  addiu    $v0, $zero, 0x1ce
0x8b13a388  3c078b1f  lui      $a3, 0x8b1f
0x8b13a38c  3c068b1f  lui      $a2, 0x8b1f
0x8b13a390  24a55104  addiu    $a1, $a1, 0x5104        # -> 0x8b1f5104
0x8b13a394  24040004  addiu    $a0, $zero, 4
0x8b13a398  afa20010  sw       $v0, 0x10($sp)
0x8b13a39c  24e76dbc  addiu    $a3, $a3, 0x6dbc        # -> 0x8b1f6dbc
0x8b13a3a0  24c669c8  addiu    $a2, $a2, 0x69c8        # -> 0x8b1f69c8
0x8b13a3a4  00009012  mflo     $s2
0x8b13a3a8  72439002  mul      $s2, $s2, $v1
0x8b13a3ac  001291c2  srl      $s2, $s2, 7
0x8b13a3b0  0ec54252  jal      0x8b150948
0x8b13a3b4  afb20018  sw       $s2, 0x18($sp)
0x8b13a3b8  8ea2000c  lw       $v0, 0xc($s5)        # -> 0x8b22f0c8
0x8b13a3bc  02402825  move     $a1, $s2
0x8b13a3c0  0040f809  jalr     $v0
0x8b13a3c4  02602025  move     $a0, $s3
0x8b13a3c8  8fb0002c  lw       $s0, 0x2c($sp)
0x8b13a3cc  8fb10030  lw       $s1, 0x30($sp)
0x8b13a3d0  8fb20034  lw       $s2, 0x34($sp)
0x8b13a3d4  8fb30038  lw       $s3, 0x38($sp)
0x8b13a3d8  8fb4003c  lw       $s4, 0x3c($sp)
0x8b13a3dc  8fb50040  lw       $s5, 0x40($sp)
0x8b13a3e0  8fbf0044  lw       $ra, 0x44($sp)
0x8b13a3e4  24020001  addiu    $v0, $zero, 1
0x8b13a3e8  03e00008  jr       $ra
0x8b13a3ec  27bd0048  addiu    $sp, $sp, 0x48
0x8b13a3f0  8ea20010  lw       $v0, 0x10($s5)
0x8b13a3f4  0040f809  jalr     $v0
0x8b13a3f8  02602025  move     $a0, $s3
0x8b13a3fc  1000ffc7  b        0x8b13a31c
0x8b13a400  8fa50020  lw       $a1, 0x20($sp)
0x8b13a404  8fb0002c  lw       $s0, 0x2c($sp)
0x8b13a408  8fb10030  lw       $s1, 0x30($sp)
0x8b13a40c  8fb20034  lw       $s2, 0x34($sp)
0x8b13a410  8fb30038  lw       $s3, 0x38($sp)
0x8b13a414  8fb4003c  lw       $s4, 0x3c($sp)
0x8b13a418  8fb50040  lw       $s5, 0x40($sp)
0x8b13a41c  8fbf0044  lw       $ra, 0x44($sp)
0x8b13a420  24020001  addiu    $v0, $zero, 1
0x8b13a424  03e00008  jr       $ra
0x8b13a428  27bd0048  addiu    $sp, $sp, 0x48
0x8b13a42c  27bdffd8  addiu    $sp, $sp, -0x28
0x8b13a430  afb0001c  sw       $s0, 0x1c($sp)
0x8b13a434  3c108b23  lui      $s0, 0x8b23
0x8b13a438  afb10020  sw       $s1, 0x20($sp)
0x8b13a43c  8e02f118  lw       $v0, -0xee8($s0)        # -> 0x8b22f118
0x8b13a440  00808825  move     $s1, $a0
0x8b13a444  8ca40520  lw       $a0, 0x520($a1)
0x8b13a448  afbf0024  sw       $ra, 0x24($sp)
0x8b13a44c  0040f809  jalr     $v0
0x8b13a450  ae250000  sw       $a1, ($s1)
0x8b13a454  10400009  beqz     $v0, 0x8b13a47c
0x8b13a458  8fbf0024  lw       $ra, 0x24($sp)
0x8b13a45c  8e220000  lw       $v0, ($s1)
0x8b13a460  2610f118  addiu    $s0, $s0, -0xee8        # -> 0x8b22f118
0x8b13a464  8e190004  lw       $t9, 4($s0)        # -> 0x8b22f11c
0x8b13a468  8fb10020  lw       $s1, 0x20($sp)
0x8b13a46c  8fb0001c  lw       $s0, 0x1c($sp)
0x8b13a470  8c440520  lw       $a0, 0x520($v0)
0x8b13a474  03200008  jr       $t9
