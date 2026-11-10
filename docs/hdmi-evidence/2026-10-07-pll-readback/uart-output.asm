0x8b19d2e4  2402000a  addiu    $v0, $zero, 0xa
0x8b19d2e8  1082000a  beq      $a0, $v0, 0x8b19d314
0x8b19d2ec  3c03b750  lui      $v1, 0xb750
0x8b19d2f0  8c62107c  lw       $v0, 0x107c($v1)        # -> 0xb750107c
0x8b19d2f4  7c420040  ext      $v0, $v0, 1, 1
0x8b19d2f8  5040fffd  beql     $v0, $zero, 0x8b19d2f0
0x8b19d2fc  3c03b750  lui      $v1, 0xb750
0x8b19d300  8c621000  lw       $v0, 0x1000($v1)        # -> 0xb7501000
0x8b19d304  7c823804  ins      $v0, $a0, 0, 8
0x8b19d308  ac621000  sw       $v0, 0x1000($v1)        # -> 0xb7501000
0x8b19d30c  03e00008  jr       $ra
0x8b19d310  00000000  nop      
0x8b19d314  8c62107c  lw       $v0, 0x107c($v1)        # -> 0xb750107c
0x8b19d318  7c420040  ext      $v0, $v0, 1, 1
0x8b19d31c  5040fffd  beql     $v0, $zero, 0x8b19d314
0x8b19d320  3c03b750  lui      $v1, 0xb750
0x8b19d324  8c621000  lw       $v0, 0x1000($v1)        # -> 0xb7501000
0x8b19d328  2405000d  addiu    $a1, $zero, 0xd
0x8b19d32c  7ca23804  ins      $v0, $a1, 0, 8
0x8b19d330  ac621000  sw       $v0, 0x1000($v1)        # -> 0xb7501000
0x8b19d334  1000ffee  b        0x8b19d2f0
0x8b19d338  3c03b750  lui      $v1, 0xb750
