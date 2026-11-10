0x8b13c350  8fbf006c  lw       $ra, 0x6c($sp)
0x8b13c354  03e00008  jr       $ra
0x8b13c358  27bd0070  addiu    $sp, $sp, 0x70
0x8b13c35c  27bdffd8  addiu    $sp, $sp, -0x28
0x8b13c360  afb00010  sw       $s0, 0x10($sp)
0x8b13c364  00808025  move     $s0, $a0
0x8b13c368  24840007  addiu    $a0, $a0, 7
0x8b13c36c  afbf0024  sw       $ra, 0x24($sp)
0x8b13c370  afb10014  sw       $s1, 0x14($sp)
0x8b13c374  afb20018  sw       $s2, 0x18($sp)
0x8b13c378  afb3001c  sw       $s3, 0x1c($sp)
0x8b13c37c  0ec600d0  jal      0x8b180340
0x8b13c380  afb40020  sw       $s4, 0x20($sp)
0x8b13c384  26040006  addiu    $a0, $s0, 6
0x8b13c388  0ec600d0  jal      0x8b180340
0x8b13c38c  00408825  move     $s1, $v0
0x8b13c390  26040005  addiu    $a0, $s0, 5
0x8b13c394  26130004  addiu    $s3, $s0, 4
0x8b13c398  0ec600d0  jal      0x8b180340
0x8b13c39c  00409025  move     $s2, $v0
0x8b13c3a0  00021200  sll      $v0, $v0, 8
0x8b13c3a4  02602025  move     $a0, $s3
0x8b13c3a8  00118e00  sll      $s1, $s1, 0x18
0x8b13c3ac  0ec600d0  jal      0x8b180340
0x8b13c3b0  02228825  or       $s1, $s1, $v0
0x8b13c3b4  00518825  or       $s1, $v0, $s1
0x8b13c3b8  00122c00  sll      $a1, $s2, 0x10
0x8b13c3bc  02252825  or       $a1, $s1, $a1
0x8b13c3c0  02609025  move     $s2, $s3
0x8b13c3c4  34b10003  ori      $s1, $a1, 3
0x8b13c3c8  7c120804  ins      $s2, $zero, 0, 2
0x8b13c3cc  36640003  ori      $a0, $s3, 3
0x8b13c3d0  0ec600e5  jal      0x8b180394
0x8b13c3d4  00052e02  srl      $a1, $a1, 0x18
0x8b13c3d8  7e253c00  ext      $a1, $s1, 0x10, 8
0x8b13c3dc  0ec600e5  jal      0x8b180394
0x8b13c3e0  26440002  addiu    $a0, $s2, 2
0x8b13c3e4  7e253a00  ext      $a1, $s1, 8, 8
0x8b13c3e8  0ec600e5  jal      0x8b180394
0x8b13c3ec  26440001  addiu    $a0, $s2, 1
0x8b13c3f0  322500ff  andi     $a1, $s1, 0xff
0x8b13c3f4  0ec600e5  jal      0x8b180394
0x8b13c3f8  02402025  move     $a0, $s2
0x8b13c3fc  0ec600d0  jal      0x8b180340
0x8b13c400  2604000f  addiu    $a0, $s0, 0xf
0x8b13c404  2604000e  addiu    $a0, $s0, 0xe
0x8b13c408  0ec600d0  jal      0x8b180340
0x8b13c40c  00408825  move     $s1, $v0
0x8b13c410  2604000d  addiu    $a0, $s0, 0xd
0x8b13c414  2614000c  addiu    $s4, $s0, 0xc
0x8b13c418  0ec600d0  jal      0x8b180340
0x8b13c41c  00409825  move     $s3, $v0
0x8b13c420  00021200  sll      $v0, $v0, 8
0x8b13c424  02802025  move     $a0, $s4
0x8b13c428  00118e00  sll      $s1, $s1, 0x18
0x8b13c42c  0ec600d0  jal      0x8b180340
0x8b13c430  02228825  or       $s1, $s1, $v0
0x8b13c434  00518825  or       $s1, $v0, $s1
0x8b13c438  00139c00  sll      $s3, $s3, 0x10
0x8b13c43c  3c028000  lui      $v0, 0x8000
0x8b13c440  02338825  or       $s1, $s1, $s3
0x8b13c444  02228825  or       $s1, $s1, $v0
0x8b13c448  02809025  move     $s2, $s4
0x8b13c44c  7c120804  ins      $s2, $zero, 0, 2
0x8b13c450  00112e02  srl      $a1, $s1, 0x18
0x8b13c454  0ec600e5  jal      0x8b180394
0x8b13c458  36840003  ori      $a0, $s4, 3
0x8b13c45c  7e253c00  ext      $a1, $s1, 0x10, 8
0x8b13c460  0ec600e5  jal      0x8b180394
0x8b13c464  26440002  addiu    $a0, $s2, 2
0x8b13c468  7e253a00  ext      $a1, $s1, 8, 8
0x8b13c46c  0ec600e5  jal      0x8b180394
0x8b13c470  26440001  addiu    $a0, $s2, 1
0x8b13c474  322500ff  andi     $a1, $s1, 0xff
0x8b13c478  0ec600e5  jal      0x8b180394
0x8b13c47c  02402025  move     $a0, $s2
0x8b13c480  0ec600d0  jal      0x8b180340
0x8b13c484  2604001b  addiu    $a0, $s0, 0x1b
0x8b13c488  2604001a  addiu    $a0, $s0, 0x1a
0x8b13c48c  26120018  addiu    $s2, $s0, 0x18
0x8b13c490  0ec600d0  jal      0x8b180340
0x8b13c494  00029e00  sll      $s3, $v0, 0x18
0x8b13c498  26040019  addiu    $a0, $s0, 0x19
0x8b13c49c  0ec600d0  jal      0x8b180340
0x8b13c4a0  00028c00  sll      $s1, $v0, 0x10
0x8b13c4a4  02402025  move     $a0, $s2
0x8b13c4a8  02338825  or       $s1, $s1, $s3
0x8b13c4ac  0ec600d0  jal      0x8b180340
0x8b13c4b0  00408025  move     $s0, $v0
0x8b13c4b4  00511025  or       $v0, $v0, $s1
0x8b13c4b8  00102a00  sll      $a1, $s0, 8
0x8b13c4bc  00a22825  or       $a1, $a1, $v0
0x8b13c4c0  00a08825  move     $s1, $a1
0x8b13c4c4  02408025  move     $s0, $s2
0x8b13c4c8  7c1118c4  ins      $s1, $zero, 3, 1
0x8b13c4cc  7c100804  ins      $s0, $zero, 0, 2
0x8b13c4d0  36440003  ori      $a0, $s2, 3
0x8b13c4d4  0ec600e5  jal      0x8b180394
0x8b13c4d8  00052e02  srl      $a1, $a1, 0x18
0x8b13c4dc  7e253c00  ext      $a1, $s1, 0x10, 8
0x8b13c4e0  0ec600e5  jal      0x8b180394
0x8b13c4e4  26040002  addiu    $a0, $s0, 2
0x8b13c4e8  7e253a00  ext      $a1, $s1, 8, 8
0x8b13c4ec  0ec600e5  jal      0x8b180394
0x8b13c4f0  26040001  addiu    $a0, $s0, 1
0x8b13c4f4  322500f7  andi     $a1, $s1, 0xf7
0x8b13c4f8  0ec600e5  jal      0x8b180394
0x8b13c4fc  02002025  move     $a0, $s0
0x8b13c500  8fb00010  lw       $s0, 0x10($sp)
0x8b13c504  8fb10014  lw       $s1, 0x14($sp)
0x8b13c508  8fb20018  lw       $s2, 0x18($sp)
0x8b13c50c  8fb3001c  lw       $s3, 0x1c($sp)
0x8b13c510  8fb40020  lw       $s4, 0x20($sp)
0x8b13c514  8fbf0024  lw       $ra, 0x24($sp)
0x8b13c518  24020001  addiu    $v0, $zero, 1
0x8b13c51c  03e00008  jr       $ra
0x8b13c520  27bd0028  addiu    $sp, $sp, 0x28
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
0x8b13c72c  03e00008  jr       $ra
0x8b13c730  27bd0018  addiu    $sp, $sp, 0x18
0x8b13c734  24020020  addiu    $v0, $zero, 0x20
