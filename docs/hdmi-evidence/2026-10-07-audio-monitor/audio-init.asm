0x8b139e60  250669c8  addiu    $a2, $t0, 0x69c8
0x8b139e64  27c55104  addiu    $a1, $fp, 0x5104
0x8b139e68  afa4001c  sw       $a0, 0x1c($sp)
0x8b139e6c  afa20010  sw       $v0, 0x10($sp)
0x8b139e70  0ec54252  jal      0x8b150948
0x8b139e74  24040003  addiu    $a0, $zero, 3
0x8b139e78  92020021  lbu      $v0, 0x21($s0)
0x8b139e7c  02a02025  move     $a0, $s5
0x8b139e80  02802825  move     $a1, $s4
0x8b139e84  0ec4d9e0  jal      0x8b136780
0x8b139e88  a2020020  sb       $v0, 0x20($s0)
0x8b139e8c  8e040014  lw       $a0, 0x14($s0)
0x8b139e90  36310008  ori      $s1, $s1, 8
0x8b139e94  1082ff51  beq      $a0, $v0, 0x8b139bdc
0x8b139e98  00409025  move     $s2, $v0
0x8b139e9c  1000ffae  b        0x8b139d58
0x8b139ea0  3c028b1f  lui      $v0, 0x8b1f
0x8b139ea4  3c028b1f  lui      $v0, 0x8b1f
0x8b139ea8  24426ce8  addiu    $v0, $v0, 0x6ce8        # -> 0x8b1f6ce8
0x8b139eac  3c098b1f  lui      $t1, 0x8b1f
0x8b139eb0  3c088b1f  lui      $t0, 0x8b1f
0x8b139eb4  afa20014  sw       $v0, 0x14($sp)
0x8b139eb8  3c1e8b1f  lui      $fp, 0x8b1f
0x8b139ebc  2402012e  addiu    $v0, $zero, 0x12e
0x8b139ec0  24040003  addiu    $a0, $zero, 3
0x8b139ec4  afa20010  sw       $v0, 0x10($sp)
0x8b139ec8  25276c18  addiu    $a3, $t1, 0x6c18        # -> 0x8b1f6c18
0x8b139ecc  250669c8  addiu    $a2, $t0, 0x69c8        # -> 0x8b1f69c8
0x8b139ed0  27c55104  addiu    $a1, $fp, 0x5104        # -> 0x8b1f5104
0x8b139ed4  0ec54252  jal      0x8b150948
0x8b139ed8  afb6001c  sw       $s6, 0x1c($sp)
0x8b139edc  92020020  lbu      $v0, 0x20($s0)
0x8b139ee0  92040021  lbu      $a0, 0x21($s0)
0x8b139ee4  36310002  ori      $s1, $s1, 2
0x8b139ee8  1044ff36  beq      $v0, $a0, 0x8b139bc4
0x8b139eec  ae16000c  sw       $s6, 0xc($s0)
0x8b139ef0  1000ffd3  b        0x8b139e40
0x8b139ef4  afa20018  sw       $v0, 0x18($sp)
0x8b139ef8  3c028b1f  lui      $v0, 0x8b1f
0x8b139efc  24426cc4  addiu    $v0, $v0, 0x6cc4        # -> 0x8b1f6cc4
0x8b139f00  3c098b1f  lui      $t1, 0x8b1f
0x8b139f04  3c088b1f  lui      $t0, 0x8b1f
0x8b139f08  afa20014  sw       $v0, 0x14($sp)
0x8b139f0c  3c1e8b1f  lui      $fp, 0x8b1f
0x8b139f10  24020127  addiu    $v0, $zero, 0x127
0x8b139f14  afa20010  sw       $v0, 0x10($sp)
0x8b139f18  25276c18  addiu    $a3, $t1, 0x6c18        # -> 0x8b1f6c18
0x8b139f1c  250669c8  addiu    $a2, $t0, 0x69c8        # -> 0x8b1f69c8
0x8b139f20  27c55104  addiu    $a1, $fp, 0x5104        # -> 0x8b1f5104
0x8b139f24  24040003  addiu    $a0, $zero, 3
0x8b139f28  0ec54252  jal      0x8b150948
0x8b139f2c  afb3001c  sw       $s3, 0x1c($sp)
0x8b139f30  8e02000c  lw       $v0, 0xc($s0)
0x8b139f34  36310001  ori      $s1, $s1, 1
0x8b139f38  1056ff1e  beq      $v0, $s6, 0x8b139bb4
0x8b139f3c  ae130008  sw       $s3, 8($s0)
0x8b139f40  1000ffd8  b        0x8b139ea4
0x8b139f44  afa20018  sw       $v0, 0x18($sp)
0x8b139f48  3c028b1f  lui      $v0, 0x8b1f
0x8b139f4c  24426c9c  addiu    $v0, $v0, 0x6c9c        # -> 0x8b1f6c9c
0x8b139f50  3c098b1f  lui      $t1, 0x8b1f
0x8b139f54  3c088b1f  lui      $t0, 0x8b1f
0x8b139f58  afa20014  sw       $v0, 0x14($sp)
0x8b139f5c  3c1e8b1f  lui      $fp, 0x8b1f
0x8b139f60  2402010f  addiu    $v0, $zero, 0x10f
0x8b139f64  afa40018  sw       $a0, 0x18($sp)
0x8b139f68  afa20010  sw       $v0, 0x10($sp)
0x8b139f6c  25276c18  addiu    $a3, $t1, 0x6c18        # -> 0x8b1f6c18
0x8b139f70  250669c8  addiu    $a2, $t0, 0x69c8        # -> 0x8b1f69c8
0x8b139f74  27c55104  addiu    $a1, $fp, 0x5104        # -> 0x8b1f5104
0x8b139f78  afb2001c  sw       $s2, 0x1c($sp)
0x8b139f7c  0ec54252  jal      0x8b150948
0x8b139f80  24040003  addiu    $a0, $zero, 3
0x8b139f84  8e020008  lw       $v0, 8($s0)
0x8b139f88  36310200  ori      $s1, $s1, 0x200
0x8b139f8c  1053ff06  beq      $v0, $s3, 0x8b139ba8
0x8b139f90  a2120025  sb       $s2, 0x25($s0)
0x8b139f94  1000ffd8  b        0x8b139ef8
0x8b139f98  afa20018  sw       $v0, 0x18($sp)
0x8b139f9c  3c028b1f  lui      $v0, 0x8b1f
0x8b139fa0  24426c78  addiu    $v0, $v0, 0x6c78        # -> 0x8b1f6c78
0x8b139fa4  3c098b1f  lui      $t1, 0x8b1f
0x8b139fa8  3c088b1f  lui      $t0, 0x8b1f
0x8b139fac  afa20014  sw       $v0, 0x14($sp)
0x8b139fb0  3c1e8b1f  lui      $fp, 0x8b1f
0x8b139fb4  24020107  addiu    $v0, $zero, 0x107
0x8b139fb8  25276c18  addiu    $a3, $t1, 0x6c18        # -> 0x8b1f6c18
0x8b139fbc  250669c8  addiu    $a2, $t0, 0x69c8        # -> 0x8b1f69c8
0x8b139fc0  27c55104  addiu    $a1, $fp, 0x5104        # -> 0x8b1f5104
0x8b139fc4  afa40018  sw       $a0, 0x18($sp)
0x8b139fc8  afb2001c  sw       $s2, 0x1c($sp)
0x8b139fcc  24040003  addiu    $a0, $zero, 3
0x8b139fd0  0ec54252  jal      0x8b150948
0x8b139fd4  afa20010  sw       $v0, 0x10($sp)
0x8b139fd8  a2120024  sb       $s2, 0x24($s0)
0x8b139fdc  0ec4d9bb  jal      0x8b1366ec
0x8b139fe0  02a02025  move     $a0, $s5
0x8b139fe4  92040025  lbu      $a0, 0x25($s0)
0x8b139fe8  36310100  ori      $s1, $s1, 0x100
0x8b139fec  1082feeb  beq      $a0, $v0, 0x8b139b9c
0x8b139ff0  00409025  move     $s2, $v0
0x8b139ff4  1000ffd5  b        0x8b139f4c
0x8b139ff8  3c028b1f  lui      $v0, 0x8b1f
0x8b139ffc  afa20018  sw       $v0, 0x18($sp)
0x8b13a000  3c028b1f  lui      $v0, 0x8b1f
0x8b13a004  24426c54  addiu    $v0, $v0, 0x6c54        # -> 0x8b1f6c54
0x8b13a008  3c098b1f  lui      $t1, 0x8b1f
0x8b13a00c  3c088b1f  lui      $t0, 0x8b1f
0x8b13a010  afa20014  sw       $v0, 0x14($sp)
0x8b13a014  3c1e8b1f  lui      $fp, 0x8b1f
0x8b13a018  240200f7  addiu    $v0, $zero, 0xf7
0x8b13a01c  afa20010  sw       $v0, 0x10($sp)
0x8b13a020  25276c18  addiu    $a3, $t1, 0x6c18        # -> 0x8b1f6c18
0x8b13a024  250669c8  addiu    $a2, $t0, 0x69c8        # -> 0x8b1f69c8
0x8b13a028  27c55104  addiu    $a1, $fp, 0x5104        # -> 0x8b1f5104
0x8b13a02c  24040003  addiu    $a0, $zero, 3
0x8b13a030  0ec54252  jal      0x8b150948
0x8b13a034  afb2001c  sw       $s2, 0x1c($sp)
0x8b13a038  24020002  addiu    $v0, $zero, 2
0x8b13a03c  24110004  addiu    $s1, $zero, 4
0x8b13a040  1642feca  bne      $s2, $v0, 0x8b139b6c
0x8b13a044  a6120010  sh       $s2, 0x10($s0)
0x8b13a048  8fa2006c  lw       $v0, 0x6c($sp)
0x8b13a04c  90420538  lbu      $v0, 0x538($v0)
0x8b13a050  5440fec7  bnel     $v0, $zero, 0x8b139b70
0x8b13a054  3c028b23  lui      $v0, 0x8b23
0x8b13a058  8fa3006c  lw       $v1, 0x6c($sp)
0x8b13a05c  24020001  addiu    $v0, $zero, 1
0x8b13a060  02802025  move     $a0, $s4
0x8b13a064  0ec502aa  jal      0x8b140aa8
0x8b13a068  a0620538  sb       $v0, 0x538($v1)
0x8b13a06c  1000fec0  b        0x8b139b70
0x8b13a070  3c028b23  lui      $v0, 0x8b23
0x8b13a074  3c028b1f  lui      $v0, 0x8b1f
0x8b13a078  24426c28  addiu    $v0, $v0, 0x6c28        # -> 0x8b1f6c28
0x8b13a07c  a2000020  sb       $zero, 0x20($s0)
0x8b13a080  a6000024  sh       $zero, 0x24($s0)
0x8b13a084  3c098b1f  lui      $t1, 0x8b1f
0x8b13a088  3c088b1f  lui      $t0, 0x8b1f
0x8b13a08c  afa20014  sw       $v0, 0x14($sp)
0x8b13a090  3c1e8b1f  lui      $fp, 0x8b1f
0x8b13a094  240200e6  addiu    $v0, $zero, 0xe6
0x8b13a098  afa20010  sw       $v0, 0x10($sp)
0x8b13a09c  25276c18  addiu    $a3, $t1, 0x6c18        # -> 0x8b1f6c18
0x8b13a0a0  250669c8  addiu    $a2, $t0, 0x69c8        # -> 0x8b1f69c8
0x8b13a0a4  27c55104  addiu    $a1, $fp, 0x5104        # -> 0x8b1f5104
0x8b13a0a8  0ec54252  jal      0x8b150948
0x8b13a0ac  24040001  addiu    $a0, $zero, 1
0x8b13a0b0  8e020008  lw       $v0, 8($s0)
0x8b13a0b4  00531023  subu     $v0, $v0, $s3
0x8b13a0b8  2c420002  sltiu    $v0, $v0, 2
0x8b13a0bc  1440fea1  bnez     $v0, 0x8b139b44
0x8b13a0c0  3c160003  lui      $s6, 3
0x8b13a0c4  8fa6006c  lw       $a2, 0x6c($sp)
0x8b13a0c8  8fa40070  lw       $a0, 0x70($sp)
0x8b13a0cc  02602825  move     $a1, $s3
0x8b13a0d0  0ec4d2f1  jal      0x8b134bc4
0x8b13a0d4  ae130008  sw       $s3, 8($s0)
0x8b13a0d8  1000ff4d  b        0x8b139e10
0x8b13a0dc  8fb00030  lw       $s0, 0x30($sp)
0x8b13a0e0  8fa40070  lw       $a0, 0x70($sp)
0x8b13a0e4  02603825  move     $a3, $s3
0x8b13a0e8  36268007  ori      $a2, $s1, 0x8007
0x8b13a0ec  0ec4ccae  jal      0x8b1332b8
0x8b13a0f0  24050002  addiu    $a1, $zero, 2
0x8b13a0f4  1040000f  beqz     $v0, 0x8b13a134
0x8b13a0f8  8fa40070  lw       $a0, 0x70($sp)
0x8b13a0fc  3c020002  lui      $v0, 2
0x8b13a100  24430015  addiu    $v1, $v0, 0x15        # -> 0x00020015
0x8b13a104  5263fe8f  beql     $s3, $v1, 0x8b139b44
0x8b13a108  24530050  addiu    $s3, $v0, 0x50        # -> 0x00020050
0x8b13a10c  12620007  beq      $s3, $v0, 0x8b13a12c
0x8b13a110  2443008f  addiu    $v1, $v0, 0x8f        # -> 0x0002008f
0x8b13a114  1263000f  beq      $s3, $v1, 0x8b13a154
0x8b13a118  24430093  addiu    $v1, $v0, 0x93        # -> 0x00020093
0x8b13a11c  02631826  xor      $v1, $s3, $v1
0x8b13a120  24420092  addiu    $v0, $v0, 0x92        # -> 0x00020092
0x8b13a124  1000fe87  b        0x8b139b44
0x8b13a128  0043980a  movz     $s3, $v0, $v1
0x8b13a12c  1000fe85  b        0x8b139b44
0x8b13a130  26730057  addiu    $s3, $s3, 0x57
0x8b13a134  02603825  move     $a3, $s3
0x8b13a138  36268026  ori      $a2, $s1, 0x8026
0x8b13a13c  0ec4ccae  jal      0x8b1332b8
0x8b13a140  24050002  addiu    $a1, $zero, 2
0x8b13a144  1440ffee  bnez     $v0, 0x8b13a100
0x8b13a148  3c020002  lui      $v0, 2
0x8b13a14c  1000fe7e  b        0x8b139b48
0x8b13a150  02003025  move     $a2, $s0
0x8b13a154  1000fe7b  b        0x8b139b44
0x8b13a158  24530091  addiu    $s3, $v0, 0x91        # -> 0x00020091
0x8b13a15c  3c088b1f  lui      $t0, 0x8b1f
0x8b13a160  1000ff14  b        0x8b139db4
0x8b13a164  3c1e8b1f  lui      $fp, 0x8b1f
0x8b13a168  27bdffe8  addiu    $sp, $sp, -0x18
0x8b13a16c  2406001c  addiu    $a2, $zero, 0x1c
0x8b13a170  afb00010  sw       $s0, 0x10($sp)
0x8b13a174  00002825  move     $a1, $zero
0x8b13a178  afbf0014  sw       $ra, 0x14($sp)
0x8b13a17c  0ec6f4ad  jal      0x8b1bd2b4
0x8b13a180  00808025  move     $s0, $a0
0x8b13a184  2604001c  addiu    $a0, $s0, 0x1c
0x8b13a188  24060014  addiu    $a2, $zero, 0x14
0x8b13a18c  0ec6f4ad  jal      0x8b1bd2b4
0x8b13a190  00002825  move     $a1, $zero
0x8b13a194  3c028b23  lui      $v0, 0x8b23
0x8b13a198  8fbf0014  lw       $ra, 0x14($sp)
0x8b13a19c  8c59f0d0  lw       $t9, -0xf30($v0)        # -> 0x8b22f0d0
0x8b13a1a0  ae000030  sw       $zero, 0x30($s0)
0x8b13a1a4  ae000034  sw       $zero, 0x34($s0)
0x8b13a1a8  ae00003c  sw       $zero, 0x3c($s0)
0x8b13a1ac  8fb00010  lw       $s0, 0x10($sp)
0x8b13a1b0  03200008  jr       $t9
0x8b13a1b4  27bd0018  addiu    $sp, $sp, 0x18
0x8b13a1b8  27bdffe8  addiu    $sp, $sp, -0x18
0x8b13a1bc  afb00010  sw       $s0, 0x10($sp)
0x8b13a1c0  00808025  move     $s0, $a0
0x8b13a1c4  afbf0014  sw       $ra, 0x14($sp)
0x8b13a1c8  0ec4e531  jal      0x8b1394c4
0x8b13a1cc  24840004  addiu    $a0, $a0, 4
0x8b13a1d0  0ec4e85a  jal      0x8b13a168
0x8b13a1d4  26040078  addiu    $a0, $s0, 0x78
0x8b13a1d8  260400c0  addiu    $a0, $s0, 0xc0
0x8b13a1dc  8fbf0014  lw       $ra, 0x14($sp)
0x8b13a1e0  8fb00010  lw       $s0, 0x10($sp)
0x8b13a1e4  0ac4d9a5  j        0x8b136694
0x8b13a1e8  27bd0018  addiu    $sp, $sp, 0x18
0x8b13a1ec  27bdffe0  addiu    $sp, $sp, -0x20
0x8b13a1f0  afb00014  sw       $s0, 0x14($sp)
0x8b13a1f4  00808025  move     $s0, $a0
0x8b13a1f8  24840004  addiu    $a0, $a0, 4
0x8b13a1fc  afbf001c  sw       $ra, 0x1c($sp)
0x8b13a200  0ec4e531  jal      0x8b1394c4
0x8b13a204  afb10018  sw       $s1, 0x18($sp)
0x8b13a208  0ec4e85a  jal      0x8b13a168
0x8b13a20c  26040078  addiu    $a0, $s0, 0x78
0x8b13a210  3c028b23  lui      $v0, 0x8b23
0x8b13a214  8c42f0bc  lw       $v0, -0xf44($v0)        # -> 0x8b22f0bc
0x8b13a218  0040f809  jalr     $v0
0x8b13a21c  261100c0  addiu    $s1, $s0, 0xc0
0x8b13a220  ae0200b0  sw       $v0, 0xb0($s0)
0x8b13a224  0ec4d9a0  jal      0x8b136680
0x8b13a228  02202025  move     $a0, $s1
0x8b13a22c  0ec4e86e  jal      0x8b13a1b8
0x8b13a230  02002025  move     $a0, $s0
0x8b13a234  8fb10018  lw       $s1, 0x18($sp)
0x8b13a238  8fbf001c  lw       $ra, 0x1c($sp)
0x8b13a23c  a2000538  sb       $zero, 0x538($s0)
0x8b13a240  8fb00014  lw       $s0, 0x14($sp)
0x8b13a244  03e00008  jr       $ra
0x8b13a248  27bd0020  addiu    $sp, $sp, 0x20
0x8b13a24c  00e08025  move     $s0, $a3
0x8b13a250  0ec4d9a3  jal      0x8b13668c
0x8b13a254  02202025  move     $a0, $s1
0x8b13a258  0ec75280  jal      0x8b1d4a00
0x8b13a25c  02002025  move     $a0, $s0
0x8b13a260  27bdffe8  addiu    $sp, $sp, -0x18
0x8b13a264  2406001c  addiu    $a2, $zero, 0x1c
0x8b13a268  afb00010  sw       $s0, 0x10($sp)
0x8b13a26c  00002825  move     $a1, $zero
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
