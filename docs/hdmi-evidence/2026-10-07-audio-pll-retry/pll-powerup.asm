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
