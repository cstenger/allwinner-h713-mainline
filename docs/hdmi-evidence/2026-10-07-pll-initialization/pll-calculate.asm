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
0x8b13b718  afb10074  sw       $s1, 0x74($sp)
0x8b13b71c  24030004  addiu    $v1, $zero, 4
0x8b13b720  00808825  move     $s1, $a0
0x8b13b724  afa20038  sw       $v0, 0x38($sp)
0x8b13b728  02602025  move     $a0, $s3
0x8b13b72c  24020002  addiu    $v0, $zero, 2
0x8b13b730  afbf0094  sw       $ra, 0x94($sp)
0x8b13b734  afa3004c  sw       $v1, 0x4c($sp)
0x8b13b738  afa5009c  sw       $a1, 0x9c($sp)
0x8b13b73c  afb00070  sw       $s0, 0x70($sp)
0x8b13b740  afb20078  sw       $s2, 0x78($sp)
0x8b13b744  afb50084  sw       $s5, 0x84($sp)
0x8b13b748  afb60088  sw       $s6, 0x88($sp)
0x8b13b74c  afb7008c  sw       $s7, 0x8c($sp)
0x8b13b750  afbe0090  sw       $fp, 0x90($sp)
0x8b13b754  afb30060  sw       $s3, 0x60($sp)
0x8b13b758  0ec740e2  jal      0x8b1d0388
0x8b13b75c  afa2003c  sw       $v0, 0x3c($sp)
0x8b13b760  8e300000  lw       $s0, ($s1)
0x8b13b764  0040a025  move     $s4, $v0
0x8b13b768  afa20058  sw       $v0, 0x58($sp)
0x8b13b76c  0ec740e2  jal      0x8b1d0388
0x8b13b770  02002025  move     $a0, $s0
0x8b13b774  8e240004  lw       $a0, 4($s1)
0x8b13b778  00409025  move     $s2, $v0
0x8b13b77c  0ec740e2  jal      0x8b1d0388
0x8b13b780  3c158b1f  lui      $s5, 0x8b1f
0x8b13b784  00402825  move     $a1, $v0
0x8b13b788  0ec73d2a  jal      0x8b1cf4a8
0x8b13b78c  02402025  move     $a0, $s2
0x8b13b790  00402025  move     $a0, $v0
0x8b13b794  0ec73e93  jal      0x8b1cfa4c
0x8b13b798  02802825  move     $a1, $s4
0x8b13b79c  0ec74097  jal      0x8b1d025c
0x8b13b7a0  00402025  move     $a0, $v0
0x8b13b7a4  72131802  mul      $v1, $s0, $s3
0x8b13b7a8  00408025  move     $s0, $v0
0x8b13b7ac  3c028b1f  lui      $v0, 0x8b1f
0x8b13b7b0  244270f4  addiu    $v0, $v0, 0x70f4        # -> 0x8b1f70f4
0x8b13b7b4  afa20014  sw       $v0, 0x14($sp)
0x8b13b7b8  3c168b1f  lui      $s6, 0x8b1f
0x8b13b7bc  24020041  addiu    $v0, $zero, 0x41
0x8b13b7c0  3c128b1f  lui      $s2, 0x8b1f
0x8b13b7c4  26c770cc  addiu    $a3, $s6, 0x70cc        # -> 0x8b1f70cc
0x8b13b7c8  26a67034  addiu    $a2, $s5, 0x7034        # -> 0x8b1f7034
0x8b13b7cc  26457060  addiu    $a1, $s2, 0x7060        # -> 0x8b1f7060
0x8b13b7d0  24040003  addiu    $a0, $zero, 3
0x8b13b7d4  afb00018  sw       $s0, 0x18($sp)
0x8b13b7d8  afb3001c  sw       $s3, 0x1c($sp)
0x8b13b7dc  afa20010  sw       $v0, 0x10($sp)
0x8b13b7e0  00e0f025  move     $fp, $a3
0x8b13b7e4  26b77034  addiu    $s7, $s5, 0x7034        # -> 0x8b1f7034
0x8b13b7e8  0ec54252  jal      0x8b150948
0x8b13b7ec  afa30020  sw       $v1, 0x20($sp)
0x8b13b7f0  0ec740e2  jal      0x8b1d0388
0x8b13b7f4  02002025  move     $a0, $s0
0x8b13b7f8  00409825  move     $s3, $v0
0x8b13b7fc  3c02002a  lui      $v0, 0x2a
0x8b13b800  3442b981  ori      $v0, $v0, 0xb981
0x8b13b804  afa20050  sw       $v0, 0x50($sp)
0x8b13b808  3c028b1f  lui      $v0, 0x8b1f
0x8b13b80c  2442719c  addiu    $v0, $v0, 0x719c        # -> 0x8b1f719c
0x8b13b810  2410000b  addiu    $s0, $zero, 0xb
0x8b13b814  afa20054  sw       $v0, 0x54($sp)
0x8b13b818  0ec740e2  jal      0x8b1d0388
0x8b13b81c  8e240000  lw       $a0, ($s1)
0x8b13b820  00402825  move     $a1, $v0
0x8b13b824  0ec73d2a  jal      0x8b1cf4a8
0x8b13b828  02602025  move     $a0, $s3
0x8b13b82c  24040001  addiu    $a0, $zero, 1
0x8b13b830  02042004  sllv     $a0, $a0, $s0
0x8b13b834  0ec740e2  jal      0x8b1d0388
0x8b13b838  0040a025  move     $s4, $v0
0x8b13b83c  00402825  move     $a1, $v0
0x8b13b840  0ec73e93  jal      0x8b1cfa4c
0x8b13b844  02802025  move     $a0, $s4
0x8b13b848  0ec74097  jal      0x8b1d025c
0x8b13b84c  00402025  move     $a0, $v0
0x8b13b850  8fa30050  lw       $v1, 0x50($sp)
0x8b13b854  03c03825  move     $a3, $fp
0x8b13b858  02e03025  move     $a2, $s7
0x8b13b85c  0043182b  sltu     $v1, $v0, $v1
0x8b13b860  26457060  addiu    $a1, $s2, 0x7060        # -> 0x8b1f7060
0x8b13b864  10600022  beqz     $v1, 0x8b13b8f0
0x8b13b868  24040003  addiu    $a0, $zero, 3
0x8b13b86c  afa20018  sw       $v0, 0x18($sp)
0x8b13b870  8fa20054  lw       $v0, 0x54($sp)
0x8b13b874  afb0001c  sw       $s0, 0x1c($sp)
0x8b13b878  26100001  addiu    $s0, $s0, 1
0x8b13b87c  afa20014  sw       $v0, 0x14($sp)
0x8b13b880  2402005c  addiu    $v0, $zero, 0x5c
0x8b13b884  0ec54252  jal      0x8b150948
0x8b13b888  afa20010  sw       $v0, 0x10($sp)
0x8b13b88c  2402000f  addiu    $v0, $zero, 0xf
0x8b13b890  1602ffe1  bne      $s0, $v0, 0x8b13b818
0x8b13b894  3c028b1f  lui      $v0, 0x8b1f
0x8b13b898  244271d8  addiu    $v0, $v0, 0x71d8        # -> 0x8b1f71d8
0x8b13b89c  afa20014  sw       $v0, 0x14($sp)
0x8b13b8a0  24020068  addiu    $v0, $zero, 0x68
0x8b13b8a4  afa20010  sw       $v0, 0x10($sp)
0x8b13b8a8  26c770cc  addiu    $a3, $s6, 0x70cc        # -> 0x8b1f70cc
0x8b13b8ac  26a67034  addiu    $a2, $s5, 0x7034        # -> 0x8b1f7034
0x8b13b8b0  26457060  addiu    $a1, $s2, 0x7060        # -> 0x8b1f7060
0x8b13b8b4  0ec54252  jal      0x8b150948
0x8b13b8b8  24040002  addiu    $a0, $zero, 2
0x8b13b8bc  00001025  move     $v0, $zero
0x8b13b8c0  8fb00070  lw       $s0, 0x70($sp)
0x8b13b8c4  8fb10074  lw       $s1, 0x74($sp)
0x8b13b8c8  8fb20078  lw       $s2, 0x78($sp)
0x8b13b8cc  8fb3007c  lw       $s3, 0x7c($sp)
0x8b13b8d0  8fb40080  lw       $s4, 0x80($sp)
0x8b13b8d4  8fb50084  lw       $s5, 0x84($sp)
0x8b13b8d8  8fb60088  lw       $s6, 0x88($sp)
0x8b13b8dc  8fb7008c  lw       $s7, 0x8c($sp)
0x8b13b8e0  8fbe0090  lw       $fp, 0x90($sp)
0x8b13b8e4  8fbf0094  lw       $ra, 0x94($sp)
0x8b13b8e8  03e00008  jr       $ra
0x8b13b8ec  27bd0098  addiu    $sp, $sp, 0x98
0x8b13b8f0  8fa4009c  lw       $a0, 0x9c($sp)
0x8b13b8f4  2603fff5  addiu    $v1, $s0, -0xb
0x8b13b8f8  26c770cc  addiu    $a3, $s6, 0x70cc
0x8b13b8fc  ac830000  sw       $v1, ($a0)
0x8b13b900  afa30018  sw       $v1, 0x18($sp)
0x8b13b904  3c038b1f  lui      $v1, 0x8b1f
0x8b13b908  24637130  addiu    $v1, $v1, 0x7130        # -> 0x8b1f7130
0x8b13b90c  afa30014  sw       $v1, 0x14($sp)
0x8b13b910  24030057  addiu    $v1, $zero, 0x57
0x8b13b914  26a67034  addiu    $a2, $s5, 0x7034
0x8b13b918  afa2001c  sw       $v0, 0x1c($sp)
0x8b13b91c  afb00020  sw       $s0, 0x20($sp)
0x8b13b920  24040003  addiu    $a0, $zero, 3
0x8b13b924  afa30010  sw       $v1, 0x10($sp)
0x8b13b928  0ec54252  jal      0x8b150948
0x8b13b92c  afa20050  sw       $v0, 0x50($sp)
0x8b13b930  8fa20060  lw       $v0, 0x60($sp)
0x8b13b934  3c038b1f  lui      $v1, 0x8b1f
0x8b13b938  24637174  addiu    $v1, $v1, 0x7174        # -> 0x8b1f7174
0x8b13b93c  afa2001c  sw       $v0, 0x1c($sp)
0x8b13b940  8fa20050  lw       $v0, 0x50($sp)
0x8b13b944  afa30014  sw       $v1, 0x14($sp)
0x8b13b948  2403006c  addiu    $v1, $zero, 0x6c
0x8b13b94c  26c770cc  addiu    $a3, $s6, 0x70cc
0x8b13b950  26a67034  addiu    $a2, $s5, 0x7034
0x8b13b954  26457060  addiu    $a1, $s2, 0x7060
0x8b13b958  24040003  addiu    $a0, $zero, 3
0x8b13b95c  afa30010  sw       $v1, 0x10($sp)
0x8b13b960  0ec54252  jal      0x8b150948
0x8b13b964  afa20018  sw       $v0, 0x18($sp)
0x8b13b968  8fa20050  lw       $v0, 0x50($sp)
0x8b13b96c  3c1e8b1f  lui      $fp, 0x8b1f
0x8b13b970  00009825  move     $s3, $zero
0x8b13b974  0ec740e2  jal      0x8b1d0388
0x8b13b978  00402025  move     $a0, $v0
0x8b13b97c  00408825  move     $s1, $v0
0x8b13b980  27c27278  addiu    $v0, $fp, 0x7278        # -> 0x8b1f7278
0x8b13b984  afa20054  sw       $v0, 0x54($sp)
0x8b13b988  26a27034  addiu    $v0, $s5, 0x7034
0x8b13b98c  26d470cc  addiu    $s4, $s6, 0x70cc
0x8b13b990  26577060  addiu    $s7, $s2, 0x7060
0x8b13b994  27b00040  addiu    $s0, $sp, 0x40
0x8b13b998  24040020  addiu    $a0, $zero, 0x20
0x8b13b99c  afa20050  sw       $v0, 0x50($sp)
0x8b13b9a0  0ec740e2  jal      0x8b1d0388
0x8b13b9a4  00000000  nop      
0x8b13b9a8  00402025  move     $a0, $v0
0x8b13b9ac  02202825  move     $a1, $s1
0x8b13b9b0  0ec73d2a  jal      0x8b1cf4a8
0x8b13b9b4  0040f025  move     $fp, $v0
0x8b13b9b8  8fa50058  lw       $a1, 0x58($sp)
0x8b13b9bc  0ec73e93  jal      0x8b1cfa4c
0x8b13b9c0  00402025  move     $a0, $v0
0x8b13b9c4  0ec74097  jal      0x8b1d025c
0x8b13b9c8  00402025  move     $a0, $v0
0x8b13b9cc  2449ffe8  addiu    $t1, $v0, -0x18
0x8b13b9d0  2d290045  sltiu    $t1, $t1, 0x45
0x8b13b9d4  8fa60050  lw       $a2, 0x50($sp)
0x8b13b9d8  02803825  move     $a3, $s4
0x8b13b9dc  02e02825  move     $a1, $s7
0x8b13b9e0  15200013  bnez     $t1, 0x8b13ba30
0x8b13b9e4  24040003  addiu    $a0, $zero, 3
0x8b13b9e8  afa2001c  sw       $v0, 0x1c($sp)
0x8b13b9ec  8fa20054  lw       $v0, 0x54($sp)
0x8b13b9f0  afb30018  sw       $s3, 0x18($sp)
0x8b13b9f4  26730001  addiu    $s3, $s3, 1
0x8b13b9f8  afa20014  sw       $v0, 0x14($sp)
0x8b13b9fc  24020094  addiu    $v0, $zero, 0x94
0x8b13ba00  0ec54252  jal      0x8b150948
0x8b13ba04  afa20010  sw       $v0, 0x10($sp)
0x8b13ba08  24020004  addiu    $v0, $zero, 4
0x8b13ba0c  12620003  beq      $s3, $v0, 0x8b13ba1c
0x8b13ba10  26100004  addiu    $s0, $s0, 4
0x8b13ba14  1000ffe2  b        0x8b13b9a0
0x8b13ba18  8e040000  lw       $a0, ($s0)
0x8b13ba1c  3c028b1f  lui      $v0, 0x8b1f
0x8b13ba20  244272b4  addiu    $v0, $v0, 0x72b4        # -> 0x8b1f72b4
0x8b13ba24  afa20014  sw       $v0, 0x14($sp)
0x8b13ba28  1000ff9e  b        0x8b13b8a4
0x8b13ba2c  2402009a  addiu    $v0, $zero, 0x9a
0x8b13ba30  00132080  sll      $a0, $s3, 2
0x8b13ba34  03a42021  addu     $a0, $sp, $a0
0x8b13ba38  8fa3009c  lw       $v1, 0x9c($sp)
0x8b13ba3c  8c840030  lw       $a0, 0x30($a0)
0x8b13ba40  26c770cc  addiu    $a3, $s6, 0x70cc
0x8b13ba44  ac620008  sw       $v0, 8($v1)
0x8b13ba48  ac640004  sw       $a0, 4($v1)
0x8b13ba4c  afa20018  sw       $v0, 0x18($sp)
0x8b13ba50  3c028b1f  lui      $v0, 0x8b1f
0x8b13ba54  24427200  addiu    $v0, $v0, 0x7200        # -> 0x8b1f7200
0x8b13ba58  afa20014  sw       $v0, 0x14($sp)
0x8b13ba5c  2402008e  addiu    $v0, $zero, 0x8e
0x8b13ba60  26a67034  addiu    $a2, $s5, 0x7034
0x8b13ba64  26457060  addiu    $a1, $s2, 0x7060
0x8b13ba68  afa4001c  sw       $a0, 0x1c($sp)
0x8b13ba6c  afa20010  sw       $v0, 0x10($sp)
0x8b13ba70  24040003  addiu    $a0, $zero, 3
0x8b13ba74  0ec54252  jal      0x8b150948
0x8b13ba78  afb30020  sw       $s3, 0x20($sp)
0x8b13ba7c  8fa40058  lw       $a0, 0x58($sp)
0x8b13ba80  03c02825  move     $a1, $fp
0x8b13ba84  0ec73e93  jal      0x8b1cfa4c
0x8b13ba88  3c1e8b1f  lui      $fp, 0x8b1f
0x8b13ba8c  00402025  move     $a0, $v0
0x8b13ba90  0ec73d2a  jal      0x8b1cf4a8
0x8b13ba94  02202825  move     $a1, $s1
0x8b13ba98  00402025  move     $a0, $v0
0x8b13ba9c  0ec74097  jal      0x8b1d025c
0x8b13baa0  00408025  move     $s0, $v0
0x8b13baa4  00402025  move     $a0, $v0
0x8b13baa8  00408825  move     $s1, $v0
0x8b13baac  0ec740e2  jal      0x8b1d0388
0x8b13bab0  afa20068  sw       $v0, 0x68($sp)
0x8b13bab4  00402825  move     $a1, $v0
0x8b13bab8  0ec73f40  jal      0x8b1cfd00
0x8b13babc  02002025  move     $a0, $s0
0x8b13bac0  00402025  move     $a0, $v0
0x8b13bac4  0040a025  move     $s4, $v0
0x8b13bac8  0ec7499b  jal      0x8b1d266c
0x8b13bacc  afb10028  sw       $s1, 0x28($sp)
0x8b13bad0  02002025  move     $a0, $s0
0x8b13bad4  afa20020  sw       $v0, 0x20($sp)
0x8b13bad8  0ec7499b  jal      0x8b1d266c
0x8b13badc  afa30024  sw       $v1, 0x24($sp)
0x8b13bae0  afa20018  sw       $v0, 0x18($sp)
0x8b13bae4  3c028b1f  lui      $v0, 0x8b1f
0x8b13bae8  24427244  addiu    $v0, $v0, 0x7244        # -> 0x8b1f7244
0x8b13baec  afa20014  sw       $v0, 0x14($sp)
0x8b13baf0  240200a0  addiu    $v0, $zero, 0xa0
0x8b13baf4  afa3001c  sw       $v1, 0x1c($sp)
0x8b13baf8  afa20010  sw       $v0, 0x10($sp)
0x8b13bafc  26c770cc  addiu    $a3, $s6, 0x70cc
0x8b13bb00  26a67034  addiu    $a2, $s5, 0x7034
0x8b13bb04  26457060  addiu    $a1, $s2, 0x7060
0x8b13bb08  0ec54252  jal      0x8b150948
0x8b13bb0c  24040003  addiu    $a0, $zero, 3
0x8b13bb10  3c028b1f  lui      $v0, 0x8b1f
0x8b13bb14  8c435b0c  lw       $v1, 0x5b0c($v0)        # -> 0x8b1f5b0c
0x8b13bb18  8c425b08  lw       $v0, 0x5b08($v0)        # -> 0x8b1f5b08
0x8b13bb1c  24100001  addiu    $s0, $zero, 1
0x8b13bb20  afa00054  sw       $zero, 0x54($sp)
0x8b13bb24  afa20058  sw       $v0, 0x58($sp)
0x8b13bb28  27c27320  addiu    $v0, $fp, 0x7320        # -> 0x8b1f7320
0x8b13bb2c  afa20060  sw       $v0, 0x60($sp)
0x8b13bb30  3c028b1f  lui      $v0, 0x8b1f
0x8b13bb34  244272dc  addiu    $v0, $v0, 0x72dc        # -> 0x8b1f72dc
0x8b13bb38  afa3005c  sw       $v1, 0x5c($sp)
0x8b13bb3c  1000001c  b        0x8b13bbb0
0x8b13bb40  afa20064  sw       $v0, 0x64($sp)
0x8b13bb44  8fa20054  lw       $v0, 0x54($sp)
0x8b13bb48  00498825  or       $s1, $v0, $t1
0x8b13bb4c  0ec7470a  jal      0x8b1d1c28
0x8b13bb50  afb10054  sw       $s1, 0x54($sp)
0x8b13bb54  00602825  move     $a1, $v1
0x8b13bb58  0ec749ce  jal      0x8b1d2738
0x8b13bb5c  00402025  move     $a0, $v0
0x8b13bb60  00402025  move     $a0, $v0
0x8b13bb64  0040a025  move     $s4, $v0
0x8b13bb68  afb10020  sw       $s1, 0x20($sp)
0x8b13bb6c  0ec7499b  jal      0x8b1d266c
0x8b13bb70  afb00024  sw       $s0, 0x24($sp)
0x8b13bb74  afa20018  sw       $v0, 0x18($sp)
0x8b13bb78  8fa20064  lw       $v0, 0x64($sp)
0x8b13bb7c  26c770cc  addiu    $a3, $s6, 0x70cc
0x8b13bb80  26a67034  addiu    $a2, $s5, 0x7034
0x8b13bb84  afa20014  sw       $v0, 0x14($sp)
0x8b13bb88  240200a7  addiu    $v0, $zero, 0xa7
0x8b13bb8c  26457060  addiu    $a1, $s2, 0x7060
0x8b13bb90  24040003  addiu    $a0, $zero, 3
0x8b13bb94  afa3001c  sw       $v1, 0x1c($sp)
0x8b13bb98  0ec54252  jal      0x8b150948
0x8b13bb9c  afa20010  sw       $v0, 0x10($sp)
0x8b13bba0  26100001  addiu    $s0, $s0, 1
0x8b13bba4  2402000f  addiu    $v0, $zero, 0xf
0x8b13bba8  12020029  beq      $s0, $v0, 0x8b13bc50
0x8b13bbac  8fa50068  lw       $a1, 0x68($sp)
0x8b13bbb0  02802025  move     $a0, $s4
0x8b13bbb4  0ec7499b  jal      0x8b1d266c
0x8b13bbb8  241e0001  addiu    $fp, $zero, 1
0x8b13bbbc  021e2004  sllv     $a0, $fp, $s0
0x8b13bbc0  00608825  move     $s1, $v1
0x8b13bbc4  0ec74983  jal      0x8b1d260c
0x8b13bbc8  00409825  move     $s3, $v0
0x8b13bbcc  8fa40058  lw       $a0, 0x58($sp)
0x8b13bbd0  8fa5005c  lw       $a1, 0x5c($sp)
0x8b13bbd4  00403025  move     $a2, $v0
0x8b13bbd8  0ec7431e  jal      0x8b1d0c78
0x8b13bbdc  00603825  move     $a3, $v1
0x8b13bbe0  00603825  move     $a3, $v1
0x8b13bbe4  00403025  move     $a2, $v0
0x8b13bbe8  02602025  move     $a0, $s3
0x8b13bbec  02202825  move     $a1, $s1
0x8b13bbf0  0040b825  move     $s7, $v0
0x8b13bbf4  0ec744ee  jal      0x8b1d13b8
0x8b13bbf8  afa30050  sw       $v1, 0x50($sp)
0x8b13bbfc  8fa30050  lw       $v1, 0x50($sp)
0x8b13bc00  02e03025  move     $a2, $s7
0x8b13bc04  02602025  move     $a0, $s3
0x8b13bc08  00603825  move     $a3, $v1
0x8b13bc0c  2403000f  addiu    $v1, $zero, 0xf
0x8b13bc10  00701823  subu     $v1, $v1, $s0
0x8b13bc14  02202825  move     $a1, $s1
0x8b13bc18  0441ffca  bgez     $v0, 0x8b13bb44
0x8b13bc1c  007e4804  sllv     $t1, $fp, $v1
0x8b13bc20  8fa20060  lw       $v0, 0x60($sp)
0x8b13bc24  26c770cc  addiu    $a3, $s6, 0x70cc
0x8b13bc28  26a67034  addiu    $a2, $s5, 0x7034
0x8b13bc2c  afa20014  sw       $v0, 0x14($sp)
0x8b13bc30  240200a9  addiu    $v0, $zero, 0xa9
0x8b13bc34  26457060  addiu    $a1, $s2, 0x7060
0x8b13bc38  24040003  addiu    $a0, $zero, 3
0x8b13bc3c  afb00018  sw       $s0, 0x18($sp)
0x8b13bc40  0ec54252  jal      0x8b150948
0x8b13bc44  afa20010  sw       $v0, 0x10($sp)
0x8b13bc48  1000ffd6  b        0x8b13bba4
0x8b13bc4c  26100001  addiu    $s0, $s0, 1
0x8b13bc50  8fa2009c  lw       $v0, 0x9c($sp)
0x8b13bc54  8fa6009c  lw       $a2, 0x9c($sp)
0x8b13bc58  8c440008  lw       $a0, 8($v0)
0x8b13bc5c  8c430004  lw       $v1, 4($v0)
0x8b13bc60  00c03825  move     $a3, $a2
0x8b13bc64  8c420000  lw       $v0, ($v0)
0x8b13bc68  acc5000c  sw       $a1, 0xc($a2)
0x8b13bc6c  8fa60054  lw       $a2, 0x54($sp)
0x8b13bc70  ace60010  sw       $a2, 0x10($a3)
0x8b13bc74  afa20018  sw       $v0, 0x18($sp)
0x8b13bc78  3c028b1f  lui      $v0, 0x8b1f
0x8b13bc7c  24427350  addiu    $v0, $v0, 0x7350        # -> 0x8b1f7350
0x8b13bc80  afa20014  sw       $v0, 0x14($sp)
0x8b13bc84  240200c0  addiu    $v0, $zero, 0xc0
0x8b13bc88  afa40020  sw       $a0, 0x20($sp)
0x8b13bc8c  afa50024  sw       $a1, 0x24($sp)
0x8b13bc90  afa60028  sw       $a2, 0x28($sp)
0x8b13bc94  afa20010  sw       $v0, 0x10($sp)
0x8b13bc98  afa3001c  sw       $v1, 0x1c($sp)
0x8b13bc9c  26c770cc  addiu    $a3, $s6, 0x70cc
0x8b13bca0  26a67034  addiu    $a2, $s5, 0x7034
0x8b13bca4  26457060  addiu    $a1, $s2, 0x7060
0x8b13bca8  0ec54252  jal      0x8b150948
0x8b13bcac  24040003  addiu    $a0, $zero, 3
0x8b13bcb0  1000ff03  b        0x8b13b8c0
0x8b13bcb4  24020001  addiu    $v0, $zero, 1
