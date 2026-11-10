0x8b13c7d0  24020001  addiu    $v0, $zero, 1
0x8b13c7d4  03e00008  jr       $ra
0x8b13c7d8  27bd0018  addiu    $sp, $sp, 0x18
0x8b13c7dc  ae00000c  sw       $zero, 0xc($s0)
0x8b13c7e0  8fbf0014  lw       $ra, 0x14($sp)
0x8b13c7e4  8fb00010  lw       $s0, 0x10($sp)
0x8b13c7e8  24020001  addiu    $v0, $zero, 1
0x8b13c7ec  03e00008  jr       $ra
0x8b13c7f0  27bd0018  addiu    $sp, $sp, 0x18
0x8b13c7f4  27bdffc0  addiu    $sp, $sp, -0x40
0x8b13c7f8  afb00024  sw       $s0, 0x24($sp)
0x8b13c7fc  00808025  move     $s0, $a0
0x8b13c800  24840045  addiu    $a0, $a0, 0x45
0x8b13c804  afbf003c  sw       $ra, 0x3c($sp)
0x8b13c808  afb10028  sw       $s1, 0x28($sp)
0x8b13c80c  afb2002c  sw       $s2, 0x2c($sp)
0x8b13c810  afb30030  sw       $s3, 0x30($sp)
0x8b13c814  afb40034  sw       $s4, 0x34($sp)
0x8b13c818  afb50038  sw       $s5, 0x38($sp)
0x8b13c81c  0ec600d0  jal      0x8b180340
0x8b13c820  00a09825  move     $s3, $a1
0x8b13c824  26040046  addiu    $a0, $s0, 0x46
0x8b13c828  0ec600d0  jal      0x8b180340
0x8b13c82c  0040a025  move     $s4, $v0
0x8b13c830  26040047  addiu    $a0, $s0, 0x47
0x8b13c834  0ec600d0  jal      0x8b180340
0x8b13c838  00029200  sll      $s2, $v0, 8
0x8b13c83c  26040048  addiu    $a0, $s0, 0x48
0x8b13c840  0254a025  or       $s4, $s2, $s4
0x8b13c844  3c15000f  lui      $s5, 0xf
0x8b13c848  0ec600d0  jal      0x8b180340
0x8b13c84c  00029400  sll      $s2, $v0, 0x10
0x8b13c850  26040049  addiu    $a0, $s0, 0x49
0x8b13c854  00408825  move     $s1, $v0
0x8b13c858  0ec600d0  jal      0x8b180340
0x8b13c85c  02559024  and      $s2, $s2, $s5
0x8b13c860  2604004a  addiu    $a0, $s0, 0x4a
0x8b13c864  02549025  or       $s2, $s2, $s4
0x8b13c868  0ec600d0  jal      0x8b180340
0x8b13c86c  0002a200  sll      $s4, $v0, 8
0x8b13c870  0291a025  or       $s4, $s4, $s1
0x8b13c874  00028c00  sll      $s1, $v0, 0x10
0x8b13c878  3c028b1f  lui      $v0, 0x8b1f
0x8b13c87c  02358824  and      $s1, $s1, $s5
0x8b13c880  244274b8  addiu    $v0, $v0, 0x74b8        # -> 0x8b1f74b8
0x8b13c884  02348825  or       $s1, $s1, $s4
0x8b13c888  afa20014  sw       $v0, 0x14($sp)
0x8b13c88c  3c078b1f  lui      $a3, 0x8b1f
0x8b13c890  24020195  addiu    $v0, $zero, 0x195
0x8b13c894  3c068b1f  lui      $a2, 0x8b1f
0x8b13c898  3c058b1f  lui      $a1, 0x8b1f
0x8b13c89c  24e774a0  addiu    $a3, $a3, 0x74a0        # -> 0x8b1f74a0
0x8b13c8a0  24c67034  addiu    $a2, $a2, 0x7034        # -> 0x8b1f7034
0x8b13c8a4  afb20018  sw       $s2, 0x18($sp)
0x8b13c8a8  afb1001c  sw       $s1, 0x1c($sp)
0x8b13c8ac  afa20010  sw       $v0, 0x10($sp)
0x8b13c8b0  24a57060  addiu    $a1, $a1, 0x7060        # -> 0x8b1f7060
0x8b13c8b4  0ec54252  jal      0x8b150948
0x8b13c8b8  24040003  addiu    $a0, $zero, 3
0x8b13c8bc  02602825  move     $a1, $s3
0x8b13c8c0  02002025  move     $a0, $s0
0x8b13c8c4  ae710000  sw       $s1, ($s3)
0x8b13c8c8  0ec4f1b8  jal      0x8b13c6e0
0x8b13c8cc  ae720004  sw       $s2, 4($s3)
0x8b13c8d0  8fb00024  lw       $s0, 0x24($sp)
0x8b13c8d4  8fb10028  lw       $s1, 0x28($sp)
0x8b13c8d8  8fb2002c  lw       $s2, 0x2c($sp)
0x8b13c8dc  8fb30030  lw       $s3, 0x30($sp)
0x8b13c8e0  8fb40034  lw       $s4, 0x34($sp)
0x8b13c8e4  8fb50038  lw       $s5, 0x38($sp)
0x8b13c8e8  8fbf003c  lw       $ra, 0x3c($sp)
0x8b13c8ec  24020001  addiu    $v0, $zero, 1
0x8b13c8f0  03e00008  jr       $ra
0x8b13c8f4  27bd0040  addiu    $sp, $sp, 0x40
0x8b13c8f8  27bdffe8  addiu    $sp, $sp, -0x18
0x8b13c8fc  24840056  addiu    $a0, $a0, 0x56
0x8b13c900  afb00010  sw       $s0, 0x10($sp)
0x8b13c904  afbf0014  sw       $ra, 0x14($sp)
0x8b13c908  0ec600d0  jal      0x8b180340
0x8b13c90c  00a08025  move     $s0, $a1
0x8b13c910  3042000f  andi     $v0, $v0, 0xf
0x8b13c914  2c43000f  sltiu    $v1, $v0, 0xf
0x8b13c918  1060000f  beqz     $v1, 0x8b13c958
0x8b13c91c  3c038b1f  lui      $v1, 0x8b1f
0x8b13c920  00021080  sll      $v0, $v0, 2
0x8b13c924  246374d0  addiu    $v1, $v1, 0x74d0        # -> 0x8b1f74d0
0x8b13c928  00621021  addu     $v0, $v1, $v0
0x8b13c92c  8c420000  lw       $v0, ($v0)
0x8b13c930  00400008  jr       $v0
0x8b13c934  00000000  nop      
0x8b13c938  3c020002  lui      $v0, 2
0x8b13c93c  3442ee00  ori      $v0, $v0, 0xee00
0x8b13c940  ae020008  sw       $v0, 8($s0)
0x8b13c944  8fbf0014  lw       $ra, 0x14($sp)
0x8b13c948  8fb00010  lw       $s0, 0x10($sp)
0x8b13c94c  24020001  addiu    $v0, $zero, 1
0x8b13c950  03e00008  jr       $ra
0x8b13c954  27bd0018  addiu    $sp, $sp, 0x18
0x8b13c958  3402ac44  ori      $v0, $zero, 0xac44
0x8b13c95c  ae020008  sw       $v0, 8($s0)
0x8b13c960  8fbf0014  lw       $ra, 0x14($sp)
0x8b13c964  8fb00010  lw       $s0, 0x10($sp)
0x8b13c968  24020001  addiu    $v0, $zero, 1
0x8b13c96c  03e00008  jr       $ra
0x8b13c970  27bd0018  addiu    $sp, $sp, 0x18
0x8b13c974  3402bb80  ori      $v0, $zero, 0xbb80
0x8b13c978  ae020008  sw       $v0, 8($s0)
0x8b13c97c  8fbf0014  lw       $ra, 0x14($sp)
0x8b13c980  8fb00010  lw       $s0, 0x10($sp)
0x8b13c984  24020001  addiu    $v0, $zero, 1
0x8b13c988  03e00008  jr       $ra
0x8b13c98c  27bd0018  addiu    $sp, $sp, 0x18
0x8b13c990  24027d00  addiu    $v0, $zero, 0x7d00
0x8b13c994  ae020008  sw       $v0, 8($s0)
0x8b13c998  8fbf0014  lw       $ra, 0x14($sp)
0x8b13c99c  8fb00010  lw       $s0, 0x10($sp)
0x8b13c9a0  24020001  addiu    $v0, $zero, 1
0x8b13c9a4  03e00008  jr       $ra
0x8b13c9a8  27bd0018  addiu    $sp, $sp, 0x18
0x8b13c9ac  3c020001  lui      $v0, 1
0x8b13c9b0  24425888  addiu    $v0, $v0, 0x5888        # -> 0x00015888
0x8b13c9b4  ae020008  sw       $v0, 8($s0)
0x8b13c9b8  8fbf0014  lw       $ra, 0x14($sp)
0x8b13c9bc  8fb00010  lw       $s0, 0x10($sp)
0x8b13c9c0  24020001  addiu    $v0, $zero, 1
0x8b13c9c4  03e00008  jr       $ra
0x8b13c9c8  27bd0018  addiu    $sp, $sp, 0x18
0x8b13c9cc  3c020002  lui      $v0, 2
0x8b13c9d0  3442b110  ori      $v0, $v0, 0xb110
0x8b13c9d4  ae020008  sw       $v0, 8($s0)
0x8b13c9d8  8fbf0014  lw       $ra, 0x14($sp)
0x8b13c9dc  8fb00010  lw       $s0, 0x10($sp)
0x8b13c9e0  24020001  addiu    $v0, $zero, 1
0x8b13c9e4  03e00008  jr       $ra
0x8b13c9e8  27bd0018  addiu    $sp, $sp, 0x18
0x8b13c9ec  3c020001  lui      $v0, 1
0x8b13c9f0  24424050  addiu    $v0, $v0, 0x4050        # -> 0x00014050
0x8b13c9f4  ae020008  sw       $v0, 8($s0)
0x8b13c9f8  8fbf0014  lw       $ra, 0x14($sp)
0x8b13c9fc  8fb00010  lw       $s0, 0x10($sp)
0x8b13ca00  24020001  addiu    $v0, $zero, 1
0x8b13ca04  03e00008  jr       $ra
0x8b13ca08  27bd0018  addiu    $sp, $sp, 0x18
0x8b13ca0c  27bdffc0  addiu    $sp, $sp, -0x40
0x8b13ca10  afb10034  sw       $s1, 0x34($sp)
0x8b13ca14  afb20038  sw       $s2, 0x38($sp)
0x8b13ca18  00c08825  move     $s1, $a2
0x8b13ca1c  00a09025  move     $s2, $a1
0x8b13ca20  00c02825  move     $a1, $a2
0x8b13ca24  afbf003c  sw       $ra, 0x3c($sp)
0x8b13ca28  afb00030  sw       $s0, 0x30($sp)
0x8b13ca2c  0ec4f1b8  jal      0x8b13c6e0
0x8b13ca30  00808025  move     $s0, $a0
0x8b13ca34  8e23000c  lw       $v1, 0xc($s1)
0x8b13ca38  8e270004  lw       $a3, 4($s1)
0x8b13ca3c  8e260000  lw       $a2, ($s1)
0x8b13ca40  00031140  sll      $v0, $v1, 5
0x8b13ca44  00431023  subu     $v0, $v0, $v1
0x8b13ca48  00021080  sll      $v0, $v0, 2
0x8b13ca4c  00431021  addu     $v0, $v0, $v1
0x8b13ca50  26100002  addiu    $s0, $s0, 2
0x8b13ca54  000210c0  sll      $v0, $v0, 3
0x8b13ca58  02002025  move     $a0, $s0
0x8b13ca5c  24050027  addiu    $a1, $zero, 0x27
0x8b13ca60  afa70014  sw       $a3, 0x14($sp)
0x8b13ca64  afa20018  sw       $v0, 0x18($sp)
0x8b13ca68  0ec600e5  jal      0x8b180394
0x8b13ca6c  afa60010  sw       $a2, 0x10($sp)
0x8b13ca70  24060040  addiu    $a2, $zero, 0x40
0x8b13ca74  02002025  move     $a0, $s0
0x8b13ca78  0ec600f7  jal      0x8b1803dc
0x8b13ca7c  24050040  addiu    $a1, $zero, 0x40
0x8b13ca80  0ec4f0d7  jal      0x8b13c35c
0x8b13ca84  02402025  move     $a0, $s2
0x8b13ca88  02402025  move     $a0, $s2
0x8b13ca8c  0ec4ef2e  jal      0x8b13bcb8
0x8b13ca90  27a50010  addiu    $a1, $sp, 0x10
0x8b13ca94  02002025  move     $a0, $s0
0x8b13ca98  00003025  move     $a2, $zero
0x8b13ca9c  0ec600f7  jal      0x8b1803dc
