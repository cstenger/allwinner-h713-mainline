0x8b13c524  27bdff90  addiu    $sp, $sp, -0x70
0x8b13c528  2406001c  addiu    $a2, $zero, 0x1c
0x8b13c52c  afb00054  sw       $s0, 0x54($sp)
0x8b13c530  afb10058  sw       $s1, 0x58($sp)
0x8b13c534  00a08025  move     $s0, $a1
0x8b13c538  00808825  move     $s1, $a0
0x8b13c53c  00002825  move     $a1, $zero
0x8b13c540  afb2005c  sw       $s2, 0x5c($sp)
0x8b13c544  afb30060  sw       $s3, 0x60($sp)
0x8b13c548  afb40064  sw       $s4, 0x64($sp)
0x8b13c54c  afb50068  sw       $s5, 0x68($sp)
0x8b13c550  afbf006c  sw       $ra, 0x6c($sp)
0x8b13c554  0ec6f4ad  jal      0x8b1bd2b4
0x8b13c558  27a40030  addiu    $a0, $sp, 0x30
0x8b13c55c  8e050000  lw       $a1, ($s0)
0x8b13c560  8e020004  lw       $v0, 4($s0)
0x8b13c564  8e030008  lw       $v1, 8($s0)
0x8b13c568  8e040030  lw       $a0, 0x30($s0)
0x8b13c56c  8e060034  lw       $a2, 0x34($s0)
0x8b13c570  afa50030  sw       $a1, 0x30($sp)
0x8b13c574  afa20034  sw       $v0, 0x34($sp)
0x8b13c578  14440003  bne      $v0, $a0, 0x8b13c588
0x8b13c57c  afa30038  sw       $v1, 0x38($sp)
0x8b13c580  50660038  beql     $v1, $a2, 0x8b13c664
0x8b13c584  8fb00054  lw       $s0, 0x54($sp)
0x8b13c588  afa2001c  sw       $v0, 0x1c($sp)
0x8b13c58c  3c028b1f  lui      $v0, 0x8b1f
0x8b13c590  2442740c  addiu    $v0, $v0, 0x740c        # -> 0x8b1f740c
0x8b13c594  3c138b1f  lui      $s3, 0x8b1f
0x8b13c598  afa20014  sw       $v0, 0x14($sp)
0x8b13c59c  3c158b1f  lui      $s5, 0x8b1f
0x8b13c5a0  24020152  addiu    $v0, $zero, 0x152
0x8b13c5a4  3c148b1f  lui      $s4, 0x8b1f
0x8b13c5a8  266773f4  addiu    $a3, $s3, 0x73f4        # -> 0x8b1f73f4
0x8b13c5ac  afa30024  sw       $v1, 0x24($sp)
0x8b13c5b0  afa40018  sw       $a0, 0x18($sp)
0x8b13c5b4  afa60020  sw       $a2, 0x20($sp)
0x8b13c5b8  afa50028  sw       $a1, 0x28($sp)
0x8b13c5bc  26a67034  addiu    $a2, $s5, 0x7034        # -> 0x8b1f7034
0x8b13c5c0  26857060  addiu    $a1, $s4, 0x7060        # -> 0x8b1f7060
0x8b13c5c4  24040003  addiu    $a0, $zero, 3
0x8b13c5c8  0ec54252  jal      0x8b150948
0x8b13c5cc  afa20010  sw       $v0, 0x10($sp)
0x8b13c5d0  0ec4f0d7  jal      0x8b13c35c
0x8b13c5d4  02202025  move     $a0, $s1
0x8b13c5d8  8e030004  lw       $v1, 4($s0)
0x8b13c5dc  8e020008  lw       $v0, 8($s0)
0x8b13c5e0  2624000f  addiu    $a0, $s1, 0xf
0x8b13c5e4  ae030030  sw       $v1, 0x30($s0)
0x8b13c5e8  0ec600d0  jal      0x8b180340
0x8b13c5ec  ae020034  sw       $v0, 0x34($s0)
0x8b13c5f0  2624000e  addiu    $a0, $s1, 0xe
0x8b13c5f4  0ec600d0  jal      0x8b180340
0x8b13c5f8  00028600  sll      $s0, $v0, 0x18
0x8b13c5fc  2624000d  addiu    $a0, $s1, 0xd
0x8b13c600  0ec600d0  jal      0x8b180340
0x8b13c604  00029400  sll      $s2, $v0, 0x10
0x8b13c608  2624000c  addiu    $a0, $s1, 0xc
0x8b13c60c  02509025  or       $s2, $s2, $s0
0x8b13c610  0ec600d0  jal      0x8b180340
0x8b13c614  00408025  move     $s0, $v0
0x8b13c618  00521025  or       $v0, $v0, $s2
0x8b13c61c  00108200  sll      $s0, $s0, 8
0x8b13c620  266773f4  addiu    $a3, $s3, 0x73f4        # -> 0x8b1f73f4
0x8b13c624  02028025  or       $s0, $s0, $v0
0x8b13c628  06000017  bltz     $s0, 0x8b13c688
0x8b13c62c  afa70018  sw       $a3, 0x18($sp)
0x8b13c630  3c028b1f  lui      $v0, 0x8b1f
0x8b13c634  2442746c  addiu    $v0, $v0, 0x746c        # -> 0x8b1f746c
0x8b13c638  afa20014  sw       $v0, 0x14($sp)
0x8b13c63c  2402015e  addiu    $v0, $zero, 0x15e
0x8b13c640  26857060  addiu    $a1, $s4, 0x7060        # -> 0x8b1f7060
0x8b13c644  24040003  addiu    $a0, $zero, 3
0x8b13c648  26a67034  addiu    $a2, $s5, 0x7034        # -> 0x8b1f7034
0x8b13c64c  0ec54252  jal      0x8b150948
0x8b13c650  afa20010  sw       $v0, 0x10($sp)
0x8b13c654  27a50030  addiu    $a1, $sp, 0x30
0x8b13c658  0ec4f000  jal      0x8b13c000
0x8b13c65c  02202025  move     $a0, $s1
0x8b13c660  8fb00054  lw       $s0, 0x54($sp)
0x8b13c664  8fb10058  lw       $s1, 0x58($sp)
0x8b13c668  8fb2005c  lw       $s2, 0x5c($sp)
0x8b13c66c  8fb30060  lw       $s3, 0x60($sp)
0x8b13c670  8fb40064  lw       $s4, 0x64($sp)
0x8b13c674  8fb50068  lw       $s5, 0x68($sp)
0x8b13c678  8fbf006c  lw       $ra, 0x6c($sp)
0x8b13c67c  24020001  addiu    $v0, $zero, 1
0x8b13c680  03e00008  jr       $ra
0x8b13c684  27bd0070  addiu    $sp, $sp, 0x70
0x8b13c688  3c028b1f  lui      $v0, 0x8b1f
0x8b13c68c  24427458  addiu    $v0, $v0, 0x7458        # -> 0x8b1f7458
0x8b13c690  afa20014  sw       $v0, 0x14($sp)
0x8b13c694  2402015b  addiu    $v0, $zero, 0x15b
0x8b13c698  26a67034  addiu    $a2, $s5, 0x7034
0x8b13c69c  26857060  addiu    $a1, $s4, 0x7060
0x8b13c6a0  afa20010  sw       $v0, 0x10($sp)
0x8b13c6a4  0ec54252  jal      0x8b150948
0x8b13c6a8  24040003  addiu    $a0, $zero, 3
0x8b13c6ac  02202025  move     $a0, $s1
0x8b13c6b0  0ec4ef2e  jal      0x8b13bcb8
0x8b13c6b4  27a50030  addiu    $a1, $sp, 0x30
0x8b13c6b8  8fb00054  lw       $s0, 0x54($sp)
0x8b13c6bc  8fb10058  lw       $s1, 0x58($sp)
0x8b13c6c0  8fb2005c  lw       $s2, 0x5c($sp)
0x8b13c6c4  8fb30060  lw       $s3, 0x60($sp)
0x8b13c6c8  8fb40064  lw       $s4, 0x64($sp)
0x8b13c6cc  8fb50068  lw       $s5, 0x68($sp)
0x8b13c6d0  8fbf006c  lw       $ra, 0x6c($sp)
0x8b13c6d4  24020001  addiu    $v0, $zero, 1
0x8b13c6d8  03e00008  jr       $ra
0x8b13c6dc  27bd0070  addiu    $sp, $sp, 0x70
0x8b13c6e0  27bdffe8  addiu    $sp, $sp, -0x18
0x8b13c6e4  2484015f  addiu    $a0, $a0, 0x15f
0x8b13c6e8  afb00010  sw       $s0, 0x10($sp)
0x8b13c6ec  afbf0014  sw       $ra, 0x14($sp)
0x8b13c6f0  0ec600d0  jal      0x8b180340
0x8b13c6f4  00a08025  move     $s0, $a1
0x8b13c6f8  7c421100  ext      $v0, $v0, 4, 3
0x8b13c6fc  00021880  sll      $v1, $v0, 2
0x8b13c700  3c028b1f  lui      $v0, 0x8b1f
0x8b13c704  24427480  addiu    $v0, $v0, 0x7480        # -> 0x8b1f7480
0x8b13c708  00431021  addu     $v0, $v0, $v1
0x8b13c70c  8c420000  lw       $v0, ($v0)
0x8b13c710  00400008  jr       $v0
0x8b13c714  00000000  nop      
0x8b13c718  240200c0  addiu    $v0, $zero, 0xc0
0x8b13c71c  ae02000c  sw       $v0, 0xc($s0)
0x8b13c720  8fbf0014  lw       $ra, 0x14($sp)
0x8b13c724  8fb00010  lw       $s0, 0x10($sp)
0x8b13c728  24020001  addiu    $v0, $zero, 1
