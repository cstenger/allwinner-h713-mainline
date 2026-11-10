0x8b13bcb8  27bdff98  addiu    $sp, $sp, -0x68
0x8b13bcbc  00a01025  move     $v0, $a1
0x8b13bcc0  afb00040  sw       $s0, 0x40($sp)
0x8b13bcc4  27a50010  addiu    $a1, $sp, 0x10
0x8b13bcc8  00808025  move     $s0, $a0
0x8b13bccc  afb10044  sw       $s1, 0x44($sp)
0x8b13bcd0  afa00010  sw       $zero, 0x10($sp)
0x8b13bcd4  afa00014  sw       $zero, 0x14($sp)
0x8b13bcd8  afa00018  sw       $zero, 0x18($sp)
0x8b13bcdc  afa0001c  sw       $zero, 0x1c($sp)
0x8b13bce0  afa00020  sw       $zero, 0x20($sp)
0x8b13bce4  afb20048  sw       $s2, 0x48($sp)
0x8b13bce8  afb3004c  sw       $s3, 0x4c($sp)
0x8b13bcec  afb40050  sw       $s4, 0x50($sp)
0x8b13bcf0  afb50054  sw       $s5, 0x54($sp)
0x8b13bcf4  afb60058  sw       $s6, 0x58($sp)
0x8b13bcf8  afb7005c  sw       $s7, 0x5c($sp)
0x8b13bcfc  afbe0060  sw       $fp, 0x60($sp)
0x8b13bd00  afbf0064  sw       $ra, 0x64($sp)
0x8b13bd04  0ec4edb9  jal      0x8b13b6e4
0x8b13bd08  00402025  move     $a0, $v0
0x8b13bd0c  1440000e  bnez     $v0, 0x8b13bd48
0x8b13bd10  00408825  move     $s1, $v0
0x8b13bd14  02201025  move     $v0, $s1
0x8b13bd18  8fb00040  lw       $s0, 0x40($sp)
0x8b13bd1c  8fb10044  lw       $s1, 0x44($sp)
0x8b13bd20  8fb20048  lw       $s2, 0x48($sp)
0x8b13bd24  8fb3004c  lw       $s3, 0x4c($sp)
0x8b13bd28  8fb40050  lw       $s4, 0x50($sp)
0x8b13bd2c  8fb50054  lw       $s5, 0x54($sp)
0x8b13bd30  8fb60058  lw       $s6, 0x58($sp)
0x8b13bd34  8fb7005c  lw       $s7, 0x5c($sp)
0x8b13bd38  8fbe0060  lw       $fp, 0x60($sp)
0x8b13bd3c  8fbf0064  lw       $ra, 0x64($sp)
0x8b13bd40  03e00008  jr       $ra
0x8b13bd44  27bd0068  addiu    $sp, $sp, 0x68
0x8b13bd48  02002025  move     $a0, $s0
0x8b13bd4c  0ec4ed79  jal      0x8b13b5e4
0x8b13bd50  02009025  move     $s2, $s0
0x8b13bd54  7c120804  ins      $s2, $zero, 0, 2
0x8b13bd58  2405000d  addiu    $a1, $zero, 0xd
0x8b13bd5c  0ec600e5  jal      0x8b180394
0x8b13bd60  36040003  ori      $a0, $s0, 3
0x8b13bd64  26440002  addiu    $a0, $s2, 2
0x8b13bd68  0ec600e5  jal      0x8b180394
0x8b13bd6c  24050032  addiu    $a1, $zero, 0x32
0x8b13bd70  26440001  addiu    $a0, $s2, 1
0x8b13bd74  0ec600e5  jal      0x8b180394
0x8b13bd78  24050066  addiu    $a1, $zero, 0x66
0x8b13bd7c  261e0007  addiu    $fp, $s0, 7
0x8b13bd80  24050067  addiu    $a1, $zero, 0x67
0x8b13bd84  0ec600e5  jal      0x8b180394
0x8b13bd88  02402025  move     $a0, $s2
0x8b13bd8c  26020006  addiu    $v0, $s0, 6
0x8b13bd90  03c02025  move     $a0, $fp
0x8b13bd94  00409025  move     $s2, $v0
0x8b13bd98  0ec600d0  jal      0x8b180340
0x8b13bd9c  afa20034  sw       $v0, 0x34($sp)
0x8b13bda0  02402025  move     $a0, $s2
0x8b13bda4  00029600  sll      $s2, $v0, 0x18
0x8b13bda8  26020005  addiu    $v0, $s0, 5
0x8b13bdac  00409825  move     $s3, $v0
0x8b13bdb0  26170004  addiu    $s7, $s0, 4
0x8b13bdb4  0ec600d0  jal      0x8b180340
0x8b13bdb8  afa20038  sw       $v0, 0x38($sp)
0x8b13bdbc  02602025  move     $a0, $s3
0x8b13bdc0  0ec600d0  jal      0x8b180340
0x8b13bdc4  00029c00  sll      $s3, $v0, 0x10
0x8b13bdc8  02e02025  move     $a0, $s7
0x8b13bdcc  02729825  or       $s3, $s3, $s2
0x8b13bdd0  0ec600d0  jal      0x8b180340
0x8b13bdd4  00409025  move     $s2, $v0
0x8b13bdd8  00531025  or       $v0, $v0, $s3
0x8b13bddc  00122a00  sll      $a1, $s2, 8
0x8b13bde0  00a22825  or       $a1, $a1, $v0
0x8b13bde4  8fa20014  lw       $v0, 0x14($sp)
0x8b13bde8  02e0b025  move     $s6, $s7
0x8b13bdec  7c057a44  ins      $a1, $zero, 9, 7
0x8b13bdf0  00021240  sll      $v0, $v0, 9
0x8b13bdf4  7c160804  ins      $s6, $zero, 0, 2
0x8b13bdf8  00a22825  or       $a1, $a1, $v0
0x8b13bdfc  36e20003  ori      $v0, $s7, 3
0x8b13be00  34b20010  ori      $s2, $a1, 0x10
0x8b13be04  26d30002  addiu    $s3, $s6, 2
0x8b13be08  00402025  move     $a0, $v0
0x8b13be0c  00052e02  srl      $a1, $a1, 0x18
0x8b13be10  afa20028  sw       $v0, 0x28($sp)
0x8b13be14  0ec600e5  jal      0x8b180394
0x8b13be18  afb3002c  sw       $s3, 0x2c($sp)
0x8b13be1c  26c20001  addiu    $v0, $s6, 1
0x8b13be20  0040a025  move     $s4, $v0
0x8b13be24  02602025  move     $a0, $s3
0x8b13be28  7e453c00  ext      $a1, $s2, 0x10, 8
0x8b13be2c  0ec600e5  jal      0x8b180394
0x8b13be30  afa20030  sw       $v0, 0x30($sp)
0x8b13be34  02802025  move     $a0, $s4
0x8b13be38  0ec600e5  jal      0x8b180394
0x8b13be3c  7e453a00  ext      $a1, $s2, 8, 8
0x8b13be40  324500ff  andi     $a1, $s2, 0xff
0x8b13be44  0ec600e5  jal      0x8b180394
0x8b13be48  02c02025  move     $a0, $s6
0x8b13be4c  02002025  move     $a0, $s0
0x8b13be50  26150008  addiu    $s5, $s0, 8
0x8b13be54  0ec4ed9c  jal      0x8b13b670
0x8b13be58  2613000a  addiu    $s3, $s0, 0xa
0x8b13be5c  2614000b  addiu    $s4, $s0, 0xb
0x8b13be60  26120009  addiu    $s2, $s0, 9
0x8b13be64  0ec600d0  jal      0x8b180340
0x8b13be68  02802025  move     $a0, $s4
0x8b13be6c  0ec600d0  jal      0x8b180340
0x8b13be70  02602025  move     $a0, $s3
0x8b13be74  0ec600d0  jal      0x8b180340
0x8b13be78  02402025  move     $a0, $s2
0x8b13be7c  0ec600d0  jal      0x8b180340
0x8b13be80  02a02025  move     $a0, $s5
0x8b13be84  30420002  andi     $v0, $v0, 2
0x8b13be88  1440fff6  bnez     $v0, 0x8b13be64
0x8b13be8c  00000000  nop      
0x8b13be90  0ec600d0  jal      0x8b180340
0x8b13be94  03c02025  move     $a0, $fp
0x8b13be98  8fa40034  lw       $a0, 0x34($sp)
0x8b13be9c  00029600  sll      $s2, $v0, 0x18
0x8b13bea0  0ec600d0  jal      0x8b180340
0x8b13bea4  3c144000  lui      $s4, 0x4000
0x8b13bea8  8fa40038  lw       $a0, 0x38($sp)
0x8b13beac  00029c00  sll      $s3, $v0, 0x10
0x8b13beb0  0ec600d0  jal      0x8b180340
0x8b13beb4  02729825  or       $s3, $s3, $s2
0x8b13beb8  02e02025  move     $a0, $s7
0x8b13bebc  0ec600d0  jal      0x8b180340
0x8b13bec0  00409025  move     $s2, $v0
0x8b13bec4  00531025  or       $v0, $v0, $s3
0x8b13bec8  8fa40028  lw       $a0, 0x28($sp)
0x8b13becc  00122a00  sll      $a1, $s2, 8
0x8b13bed0  00a22825  or       $a1, $a1, $v0
0x8b13bed4  00a09025  move     $s2, $a1
0x8b13bed8  0ec600e5  jal      0x8b180394
0x8b13bedc  00052e02  srl      $a1, $a1, 0x18
0x8b13bee0  8fa4002c  lw       $a0, 0x2c($sp)
0x8b13bee4  7c120844  ins      $s2, $zero, 1, 1
0x8b13bee8  0ec600e5  jal      0x8b180394
0x8b13beec  7e453c00  ext      $a1, $s2, 0x10, 8
0x8b13bef0  8fa40030  lw       $a0, 0x30($sp)
0x8b13bef4  7e453a00  ext      $a1, $s2, 8, 8
0x8b13bef8  0ec600e5  jal      0x8b180394
0x8b13befc  2613000c  addiu    $s3, $s0, 0xc
0x8b13bf00  02c02025  move     $a0, $s6
0x8b13bf04  0ec600e5  jal      0x8b180394
0x8b13bf08  324500fd  andi     $a1, $s2, 0xfd
0x8b13bf0c  8fb2001c  lw       $s2, 0x1c($sp)
0x8b13bf10  3c0200ff  lui      $v0, 0xff
0x8b13bf14  34428000  ori      $v0, $v0, 0x8000
0x8b13bf18  001293c0  sll      $s2, $s2, 0xf
0x8b13bf1c  02429024  and      $s2, $s2, $v0
0x8b13bf20  8fa20020  lw       $v0, 0x20($sp)
0x8b13bf24  0260a825  move     $s5, $s3
0x8b13bf28  7c150804  ins      $s5, $zero, 0, 2
0x8b13bf2c  30427fff  andi     $v0, $v0, 0x7fff
0x8b13bf30  02429025  or       $s2, $s2, $v0
0x8b13bf34  36730003  ori      $s3, $s3, 3
0x8b13bf38  0254a025  or       $s4, $s2, $s4
0x8b13bf3c  26b70002  addiu    $s7, $s5, 2
0x8b13bf40  02602025  move     $a0, $s3
0x8b13bf44  0ec600e5  jal      0x8b180394
0x8b13bf48  24050040  addiu    $a1, $zero, 0x40
0x8b13bf4c  26b60001  addiu    $s6, $s5, 1
0x8b13bf50  02e02025  move     $a0, $s7
0x8b13bf54  0ec600e5  jal      0x8b180394
0x8b13bf58  7e853c00  ext      $a1, $s4, 0x10, 8
0x8b13bf5c  02c02025  move     $a0, $s6
0x8b13bf60  0ec600e5  jal      0x8b180394
0x8b13bf64  7e853a00  ext      $a1, $s4, 8, 8
0x8b13bf68  02a02025  move     $a0, $s5
0x8b13bf6c  0ec600e5  jal      0x8b180394
0x8b13bf70  328500ff  andi     $a1, $s4, 0xff
0x8b13bf74  3c026000  lui      $v0, 0x6000
0x8b13bf78  02429025  or       $s2, $s2, $v0
0x8b13bf7c  02602025  move     $a0, $s3
0x8b13bf80  0ec600e5  jal      0x8b180394
0x8b13bf84  24050060  addiu    $a1, $zero, 0x60
0x8b13bf88  02e02025  move     $a0, $s7
0x8b13bf8c  0ec600e5  jal      0x8b180394
0x8b13bf90  7e453c00  ext      $a1, $s2, 0x10, 8
0x8b13bf94  02c02025  move     $a0, $s6
0x8b13bf98  0ec600e5  jal      0x8b180394
0x8b13bf9c  7e453a00  ext      $a1, $s2, 8, 8
0x8b13bfa0  324500ff  andi     $a1, $s2, 0xff
0x8b13bfa4  0ec600e5  jal      0x8b180394
0x8b13bfa8  02a02025  move     $a0, $s5
0x8b13bfac  0ec600d0  jal      0x8b180340
0x8b13bfb0  2604001b  addiu    $a0, $s0, 0x1b
0x8b13bfb4  0ec600d0  jal      0x8b180340
0x8b13bfb8  2604001a  addiu    $a0, $s0, 0x1a
0x8b13bfbc  0ec600d0  jal      0x8b180340
0x8b13bfc0  26040019  addiu    $a0, $s0, 0x19
0x8b13bfc4  0ec600d0  jal      0x8b180340
0x8b13bfc8  26040018  addiu    $a0, $s0, 0x18
0x8b13bfcc  02201025  move     $v0, $s1
0x8b13bfd0  8fb00040  lw       $s0, 0x40($sp)
0x8b13bfd4  8fb10044  lw       $s1, 0x44($sp)
0x8b13bfd8  8fb20048  lw       $s2, 0x48($sp)
0x8b13bfdc  8fb3004c  lw       $s3, 0x4c($sp)
0x8b13bfe0  8fb40050  lw       $s4, 0x50($sp)
0x8b13bfe4  8fb50054  lw       $s5, 0x54($sp)
0x8b13bfe8  8fb60058  lw       $s6, 0x58($sp)
0x8b13bfec  8fb7005c  lw       $s7, 0x5c($sp)
0x8b13bff0  8fbe0060  lw       $fp, 0x60($sp)
0x8b13bff4  8fbf0064  lw       $ra, 0x64($sp)
0x8b13bff8  03e00008  jr       $ra
0x8b13bffc  27bd0068  addiu    $sp, $sp, 0x68
0x8b13c000  27bdff90  addiu    $sp, $sp, -0x70
0x8b13c004  afa00020  sw       $zero, 0x20($sp)
0x8b13c008  afa00024  sw       $zero, 0x24($sp)
0x8b13c00c  afa00028  sw       $zero, 0x28($sp)
0x8b13c010  afa0002c  sw       $zero, 0x2c($sp)
0x8b13c014  afa00030  sw       $zero, 0x30($sp)
0x8b13c018  afb00048  sw       $s0, 0x48($sp)
0x8b13c01c  afb1004c  sw       $s1, 0x4c($sp)
0x8b13c020  afb20050  sw       $s2, 0x50($sp)
0x8b13c024  afb30054  sw       $s3, 0x54($sp)
0x8b13c028  afb40058  sw       $s4, 0x58($sp)
0x8b13c02c  afb5005c  sw       $s5, 0x5c($sp)
0x8b13c030  afb60060  sw       $s6, 0x60($sp)
0x8b13c034  afb70064  sw       $s7, 0x64($sp)
0x8b13c038  afbe0068  sw       $fp, 0x68($sp)
0x8b13c03c  10a000b9  beqz     $a1, 0x8b13c324
0x8b13c040  afbf006c  sw       $ra, 0x6c($sp)
0x8b13c044  0080a025  move     $s4, $a0
0x8b13c048  249e001b  addiu    $fp, $a0, 0x1b
0x8b13c04c  03c02025  move     $a0, $fp
0x8b13c050  2697001a  addiu    $s7, $s4, 0x1a
0x8b13c054  afa50074  sw       $a1, 0x74($sp)
0x8b13c058  0ec600d0  jal      0x8b180340
0x8b13c05c  26960019  addiu    $s6, $s4, 0x19
0x8b13c060  0ec600d0  jal      0x8b180340
0x8b13c064  02e02025  move     $a0, $s7
0x8b13c068  26950018  addiu    $s5, $s4, 0x18
0x8b13c06c  0ec600d0  jal      0x8b180340
0x8b13c070  02c02025  move     $a0, $s6
0x8b13c074  26930007  addiu    $s3, $s4, 7
0x8b13c078  0ec600d0  jal      0x8b180340
0x8b13c07c  02a02025  move     $a0, $s5
0x8b13c080  26920006  addiu    $s2, $s4, 6
0x8b13c084  02602025  move     $a0, $s3
0x8b13c088  26910005  addiu    $s1, $s4, 5
0x8b13c08c  0ec600d0  jal      0x8b180340
0x8b13c090  afa20038  sw       $v0, 0x38($sp)
0x8b13c094  0ec600d0  jal      0x8b180340
0x8b13c098  02402025  move     $a0, $s2
0x8b13c09c  26900004  addiu    $s0, $s4, 4
0x8b13c0a0  0ec600d0  jal      0x8b180340
0x8b13c0a4  02202025  move     $a0, $s1
0x8b13c0a8  02002025  move     $a0, $s0
0x8b13c0ac  0ec600d0  jal      0x8b180340
0x8b13c0b0  afa2003c  sw       $v0, 0x3c($sp)
0x8b13c0b4  2684000f  addiu    $a0, $s4, 0xf
0x8b13c0b8  0ec600d0  jal      0x8b180340
0x8b13c0bc  afa20040  sw       $v0, 0x40($sp)
0x8b13c0c0  0ec600d0  jal      0x8b180340
0x8b13c0c4  2684000e  addiu    $a0, $s4, 0xe
0x8b13c0c8  0ec600d0  jal      0x8b180340
0x8b13c0cc  2684000d  addiu    $a0, $s4, 0xd
0x8b13c0d0  0ec600d0  jal      0x8b180340
0x8b13c0d4  2684000c  addiu    $a0, $s4, 0xc
0x8b13c0d8  8fa30074  lw       $v1, 0x74($sp)
0x8b13c0dc  27a50020  addiu    $a1, $sp, 0x20
0x8b13c0e0  0ec4edb9  jal      0x8b13b6e4
0x8b13c0e4  00602025  move     $a0, $v1
0x8b13c0e8  1040008e  beqz     $v0, 0x8b13c324
0x8b13c0ec  0040a025  move     $s4, $v0
0x8b13c0f0  8fa40038  lw       $a0, 0x38($sp)
0x8b13c0f4  8fa30020  lw       $v1, 0x20($sp)
0x8b13c0f8  7c820840  ext      $v0, $a0, 1, 2
0x8b13c0fc  14620008  bne      $v1, $v0, 0x8b13c120
0x8b13c100  8fa3003c  lw       $v1, 0x3c($sp)
0x8b13c104  8fa40040  lw       $a0, 0x40($sp)
0x8b13c108  00031200  sll      $v0, $v1, 8
0x8b13c10c  8fa30024  lw       $v1, 0x24($sp)
0x8b13c110  00821025  or       $v0, $a0, $v0
0x8b13c114  7c423240  ext      $v0, $v0, 9, 7
0x8b13c118  10620084  beq      $v1, $v0, 0x8b13c32c
0x8b13c11c  02801025  move     $v0, $s4
0x8b13c120  0ec600d0  jal      0x8b180340
0x8b13c124  02602025  move     $a0, $s3
0x8b13c128  00022e00  sll      $a1, $v0, 0x18
0x8b13c12c  02402025  move     $a0, $s2
0x8b13c130  0ec600d0  jal      0x8b180340
0x8b13c134  afa50038  sw       $a1, 0x38($sp)
0x8b13c138  8fa50038  lw       $a1, 0x38($sp)
0x8b13c13c  00023400  sll      $a2, $v0, 0x10
0x8b13c140  02202025  move     $a0, $s1
0x8b13c144  00c53025  or       $a2, $a2, $a1
0x8b13c148  0ec600d0  jal      0x8b180340
0x8b13c14c  afa6003c  sw       $a2, 0x3c($sp)
0x8b13c150  02002025  move     $a0, $s0
0x8b13c154  0ec600d0  jal      0x8b180340
0x8b13c158  afa20038  sw       $v0, 0x38($sp)
0x8b13c15c  8fa6003c  lw       $a2, 0x3c($sp)
0x8b13c160  8fa50038  lw       $a1, 0x38($sp)
0x8b13c164  36040003  ori      $a0, $s0, 3
0x8b13c168  00461025  or       $v0, $v0, $a2
0x8b13c16c  00052a00  sll      $a1, $a1, 8
0x8b13c170  00a22825  or       $a1, $a1, $v0
0x8b13c174  8fa20024  lw       $v0, 0x24($sp)
0x8b13c178  7c057a44  ins      $a1, $zero, 9, 7
0x8b13c17c  00021240  sll      $v0, $v0, 9
0x8b13c180  00a22825  or       $a1, $a1, $v0
0x8b13c184  34a20080  ori      $v0, $a1, 0x80
0x8b13c188  00052e02  srl      $a1, $a1, 0x18
0x8b13c18c  0ec600e5  jal      0x8b180394
