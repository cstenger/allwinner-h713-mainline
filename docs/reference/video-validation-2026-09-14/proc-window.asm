8b1a62c0 addiu    $sp, $sp, -0x48
8b1a62c4 lui      $v0, 0x8b20
8b1a62c8 addiu    $v0, $v0, 0x743c
8b1a62cc sw       $s4, 0x40($sp)
8b1a62d0 lui      $s4, 0x8b20
8b1a62d4 sw       $v0, 0x14($sp)
8b1a62d8 sw       $s1, 0x34($sp)
8b1a62dc addiu    $v0, $zero, 0x1a
8b1a62e0 sw       $s2, 0x38($sp)
8b1a62e4 addiu    $s4, $s4, 0x7430
8b1a62e8 lui      $s2, 0x8b21
8b1a62ec lui      $s1, 0x8b21
8b1a62f0 sw       $s0, 0x30($sp)
8b1a62f4 sw       $s3, 0x3c($sp)
8b1a62f8 sw       $v0, 0x10($sp)
8b1a62fc move     $s3, $a1
8b1a6300 move     $s0, $a0
8b1a6304 move     $a3, $s4
8b1a6308 addiu    $a2, $s2, -0x7f2c
8b1a630c addiu    $a1, $s1, -0x7f18
8b1a6310 sw       $s4, 0x18($sp)
8b1a6314 sw       $ra, 0x44($sp)
8b1a6318 jal      0x8b150068
8b1a631c addiu    $a0, $zero, 3
8b1a6320 lw       $v0, 0x10($s3)
8b1a6324 beqz     $v0, 0x8b1a6658
8b1a6328 addiu    $a3, $s0, 6
8b1a632c lw       $t5, 0x28($v0)
8b1a6330 lw       $t4, 0x30($v0)
8b1a6334 lw       $t3, 8($s3)
8b1a6338 lw       $t2, 0xc($s3)
8b1a633c lbu      $t7, 4($s3)
8b1a6340 lw       $t6, ($s3)
8b1a6344 sw       $v0, 0xbc($s0)
8b1a6348 addiu    $v0, $zero, 3
8b1a634c sw       $v0, 0x14($s0)
8b1a6350 addiu    $v0, $zero, 2
8b1a6354 sw       $v0, 0x18($s0)
8b1a6358 addiu    $t1, $s0, 0x10
8b1a635c move     $v0, $a3
8b1a6360 addiu    $t0, $s0, 0xc
8b1a6364 addiu    $v1, $s0, 5
8b1a6368 sb       $t7, 7($s0)
8b1a636c sw       $t6, 8($s0)
8b1a6370 addiu    $a2, $sp, 0x20
8b1a6374 addiu    $a1, $sp, 0x28
8b1a6378 move     $a0, $s0
8b1a637c sw       $t1, 0x1c($sp)
8b1a6380 sw       $t0, 0x18($sp)
8b1a6384 addiu    $a3, $zero, 2
8b1a6388 sw       $v0, 0x14($sp)
8b1a638c sw       $v1, 0x10($sp)
8b1a6390 sw       $t3, 0x20($sp)
8b1a6394 sw       $t2, 0x24($sp)
8b1a6398 sw       $t5, 0x28($sp)
8b1a639c jal      0x8b1a56b8
8b1a63a0 sw       $t4, 0x2c($sp)
8b1a63a4 lbu      $v0, 6($s0)
8b1a63a8 lw       $v1, 0xc($s0)
8b1a63ac lw       $a0, 0x10($s0)
8b1a63b0 lbu      $a3, 5($s0)
8b1a63b4 addiu    $a2, $sp, 0x20
8b1a63b8 sw       $v0, 0x10($sp)
8b1a63bc sw       $v1, 0x14($sp)
8b1a63c0 sw       $a0, 0x18($sp)
8b1a63c4 addiu    $a1, $sp, 0x28
8b1a63c8 jal      0x8b1a58b0
8b1a63cc move     $a0, $s0
8b1a63d0 lui      $v0, 0x8b20
8b1a63d4 lw       $v0, 0x71c4($v0)
8b1a63d8 lw       $v1, 0xc($s0)
8b1a63dc lw       $a0, 0x10($s0)
8b1a63e0 addu     $v1, $v0, $v1
8b1a63e4 srl      $v1, $v1, 2
8b1a63e8 addu     $v0, $v0, $a0
8b1a63ec ori      $a0, $zero, 0x8000
8b1a63f0 srl      $v0, $v0, 1
8b1a63f4 sltu     $a0, $v1, $a0
8b1a63f8 sw       $v1, 0x24($s0)
8b1a63fc bnez     $a0, 0x8b1a6420
8b1a6400 sw       $v0, 0x28($s0)
8b1a6404 lw       $a0, 0x14($s0)
8b1a6408 lui      $a1, 1
8b1a640c sltu     $v1, $v1, $a1
8b1a6410 addiu    $a0, $a0, 1
8b1a6414 bnez     $v1, 0x8b1a6420
8b1a6418 sw       $a0, 0x14($s0)
8b1a641c sw       $zero, 0x24($s0)
8b1a6420 lui      $v1, 1
8b1a6424 sltu     $v0, $v0, $v1
8b1a6428 beql     $v0, $zero, 0x8b1a6648
8b1a642c lw       $v0, 0x18($s0)
8b1a6430 lw       $a2, 0xbc($s0)
8b1a6434 lw       $v0, 8($s0)
8b1a6438 lw       $v1, 0x10($s3)
8b1a643c lw       $a1, 0x18($a2)
8b1a6440 lw       $t0, 0x24($sp)
8b1a6444 lw       $a0, 0x2c($sp)
8b1a6448 lbu      $t6, 7($s0)
8b1a644c addiu    $v0, $v0, 1
8b1a6450 lw       $t5, 8($s3)
8b1a6454 lw       $t4, 0xc($s3)
8b1a6458 lw       $a3, 0x18($v1)
8b1a645c lw       $t2, 0x14($v1)
8b1a6460 lw       $t1, 0x20($sp)
8b1a6464 lw       $t3, 0x28($sp)
8b1a6468 addu     $v0, $v0, $a1
8b1a646c addu     $v0, $v0, $t6
8b1a6470 slt      $a1, $a0, $t0
8b1a6474 move     $t6, $t0
8b1a6478 movz     $t6, $a0, $a1
8b1a647c sw       $t6, 0x1c($s0)
8b1a6480 sw       $t1, 0x80($s0)
8b1a6484 sw       $t0, 0x88($s0)
8b1a6488 sw       $t5, 0xa0($s0)
8b1a648c sw       $t4, 0xa8($s0)
8b1a6490 sw       $v0, 0x20($s0)
8b1a6494 sw       $t2, 0x3c($s0)
8b1a6498 sw       $t3, 0x40($s0)
8b1a649c sw       $a3, 0x44($s0)
8b1a64a0 sw       $a0, 0x48($s0)
8b1a64a4 sw       $t2, 0x4c($s0)
8b1a64a8 sw       $t3, 0xb0($s0)
8b1a64ac sw       $a0, 0xb8($s0)
8b1a64b0 sw       $zero, 0x7c($s0)
8b1a64b4 sw       $zero, 0x84($s0)
8b1a64b8 sw       $zero, 0x9c($s0)
8b1a64bc sw       $zero, 0xa4($s0)
8b1a64c0 sw       $zero, 0xac($s0)
8b1a64c4 sw       $zero, 0xb4($s0)
8b1a64c8 sw       $a3, 0x54($s0)
8b1a64cc lw       $v0, 0x90($s0)
8b1a64d0 lw       $t3, 0x24($v1)
8b1a64d4 lw       $t2, 0x2c($v1)
8b1a64d8 lw       $a0, 0x14($a2)
8b1a64dc subu     $v1, $v0, $t1
8b1a64e0 lw       $a3, 0x14($s3)
8b1a64e4 slt      $v0, $t1, $v0
8b1a64e8 addiu    $a1, $zero, 0x10
8b1a64ec addiu    $v1, $v1, 0x10
8b1a64f0 movz     $v1, $a1, $v0
8b1a64f4 sw       $t1, 0x50($s0)
8b1a64f8 sw       $t0, 0x58($s0)
8b1a64fc sw       $t1, 0x70($s0)
8b1a6500 sw       $t0, 0x78($s0)
8b1a6504 sw       $a0, 0x2c($s0)
8b1a6508 sw       $a0, 0x30($s0)
8b1a650c sw       $a1, 0x38($s0)
8b1a6510 sw       $t3, 0x6c($s0)
8b1a6514 sw       $t2, 0x74($s0)
8b1a6518 sw       $v1, 0x34($s0)
8b1a651c lbu      $v1, 5($a3)
8b1a6520 lbu      $v0, 4($a3)
8b1a6524 lui      $a1, 0x1062
8b1a6528 sll      $v1, $v1, 8
8b1a652c or       $v1, $v1, $v0
8b1a6530 mul      $t3, $t1, $v1
8b1a6534 addiu    $a1, $a1, 0x4dd3
8b1a6538 lw       $v0, ($s0)
8b1a653c addiu    $a2, $zero, 0x3e8
8b1a6540 subu     $v1, $a2, $v1
8b1a6544 lw       $t2, 0x24($v0)
8b1a6548 move     $a0, $s0
8b1a654c mult     $t3, $a1
8b1a6550 sra      $t3, $t3, 0x1f
8b1a6554 mfhi     $v0
8b1a6558 sra      $v0, $v0, 6
8b1a655c subu     $v0, $v0, $t3
8b1a6560 sw       $v0, 0x5c($s0)
8b1a6564 lbu      $v0, 7($a3)
8b1a6568 lbu      $t3, 6($a3)
8b1a656c sll      $v0, $v0, 8
8b1a6570 or       $v0, $v0, $t3
8b1a6574 subu     $v0, $v1, $v0
8b1a6578 mul      $v0, $v0, $t1
8b1a657c mult     $v0, $a1
8b1a6580 sra      $v0, $v0, 0x1f
8b1a6584 mfhi     $v1
8b1a6588 sra      $v1, $v1, 6
8b1a658c subu     $v0, $v1, $v0
8b1a6590 sw       $v0, 0x60($s0)
8b1a6594 lbu      $v0, 9($a3)
8b1a6598 lbu      $v1, 8($a3)
8b1a659c sll      $v0, $v0, 8
8b1a65a0 or       $v0, $v0, $v1
8b1a65a4 mul      $v1, $t0, $v0
8b1a65a8 subu     $a2, $a2, $v0
8b1a65ac mult     $v1, $a1
8b1a65b0 sra      $v1, $v1, 0x1f
8b1a65b4 mfhi     $v0
8b1a65b8 sra      $v0, $v0, 6
8b1a65bc subu     $v0, $v0, $v1
8b1a65c0 sw       $v0, 0x64($s0)
8b1a65c4 lbu      $v0, 0xb($a3)
8b1a65c8 lbu      $v1, 0xa($a3)
8b1a65cc sll      $v0, $v0, 8
8b1a65d0 or       $v0, $v0, $v1
8b1a65d4 subu     $v0, $a2, $v0
8b1a65d8 mul      $v0, $v0, $t0
8b1a65dc mult     $v0, $a1
8b1a65e0 sra      $v0, $v0, 0x1f
8b1a65e4 mfhi     $a1
8b1a65e8 sra      $a1, $a1, 6
8b1a65ec subu     $v0, $a1, $v0
8b1a65f0 jalr     $t2
8b1a65f4 sw       $v0, 0x68($s0)
8b1a65f8 lui      $v0, 0x8b20
8b1a65fc addiu    $v0, $v0, 0x7468
8b1a6600 sw       $v0, 0x14($sp)
8b1a6604 addiu    $v0, $zero, 0x68
8b1a6608 move     $a3, $s4
8b1a660c addiu    $a2, $s2, -0x7f2c
8b1a6610 addiu    $a1, $s1, -0x7f18
8b1a6614 sw       $s4, 0x18($sp)
8b1a6618 sw       $v0, 0x10($sp)
8b1a661c jal      0x8b150068
8b1a6620 addiu    $a0, $zero, 3
8b1a6624 lw       $s0, 0x30($sp)
8b1a6628 lw       $s1, 0x34($sp)
8b1a662c lw       $s2, 0x38($sp)
8b1a6630 lw       $s3, 0x3c($sp)
8b1a6634 lw       $s4, 0x40($sp)
8b1a6638 lw       $ra, 0x44($sp)
8b1a663c addiu    $v0, $zero, 1
8b1a6640 jr       $ra
8b1a6644 addiu    $sp, $sp, 0x48
8b1a6648 sw       $zero, 0x28($s0)
8b1a664c addiu    $v0, $v0, 1
8b1a6650 b        0x8b1a6430
8b1a6654 sw       $v0, 0x18($s0)
8b1a6658 lui      $v0, 0x8b20
8b1a665c addiu    $v0, $v0, 0x7468
8b1a6660 sw       $v0, 0x14($sp)
8b1a6664 addiu    $v0, $zero, 0x1c
8b1a6668 move     $a3, $s4
8b1a666c addiu    $a2, $s2, -0x7f2c
8b1a6670 addiu    $a1, $s1, -0x7f18
8b1a6674 sw       $s4, 0x18($sp)
8b1a6678 sw       $v0, 0x10($sp)
8b1a667c jal      0x8b150068
8b1a6680 addiu    $a0, $zero, 3
8b1a6684 lui      $v0, 0x8b20
8b1a6688 addiu    $v0, $v0, 0x7448
8b1a668c sw       $v0, 0x14($sp)
8b1a6690 addiu    $v0, $zero, 0x1d
8b1a6694 move     $a3, $s4
8b1a6698 addiu    $a2, $s2, -0x7f2c
8b1a669c addiu    $a1, $s1, -0x7f18
8b1a66a0 sw       $v0, 0x10($sp)
8b1a66a4 jal      0x8b150068
8b1a66a8 addiu    $a0, $zero, 1
8b1a66ac lw       $s0, 0x30($sp)
8b1a66b0 lw       $s1, 0x34($sp)
8b1a66b4 lw       $s2, 0x38($sp)
8b1a66b8 lw       $s3, 0x3c($sp)
8b1a66bc lw       $s4, 0x40($sp)
8b1a66c0 lw       $ra, 0x44($sp)
8b1a66c4 move     $v0, $zero
8b1a66c8 jr       $ra
8b1a66cc addiu    $sp, $sp, 0x48
8b1a66d0 lw       $a1, 0xbc($a0)
8b1a66d4 lui      $v0, 0xba18
8b1a66d8 lw       $v1, 0x20($v0)
8b1a66dc lbu      $a1, 0xc($a1)
8b1a66e0 addiu    $a2, $zero, 1
8b1a66e4 addiu    $a3, $zero, 0xf00
8b1a66e8 ins      $v1, $a1, 0x18, 8
8b1a66ec sw       $v1, 0x20($v0)
8b1a66f0 lw       $a1, 0x14($v0)
8b1a66f4 lui      $v1, 0x8b20
8b1a66f8 lw       $v1, 0x71c4($v1)
8b1a66fc ins      $a1, $zero, 0x1c, 4
8b1a6700 sw       $a1, 0x14($v0)
8b1a6704 lw       $a1, 0x40($v0)
8b1a6708 ins      $a1, $a2, 0x1f, 1
8b1a670c sw       $a1, 0x40($v0)
8b1a6710 lw       $a1, 0x50($v0)
8b1a6714 lhu      $a2, 0x1c($a0)
8b1a6718 ins      $a1, $a2, 0, 0x10
8b1a671c sw       $a1, 0x50($v0)
8b1a6720 lw       $a1, 0x50($v0)
8b1a6724 lhu      $a2, 0x20($a0)
8b1a6728 ins      $a1, $a2, 0x10, 0x10
8b1a672c sw       $a1, 0x50($v0)
8b1a6730 lw       $a1, 0xc($a0)
8b1a6734 lw       $t0, 0x10($a0)
8b1a6738 lw       $t1, 0x14($v0)
8b1a673c xor      $v1, $a1, $v1
8b1a6740 xor      $a2, $a1, $t0
8b1a6744 sltiu    $a2, $a2, 1
8b1a6748 movn     $a2, $zero, $v1
8b1a674c ins      $t1, $a2, 0x1b, 1
8b1a6750 sw       $t1, 0x14($v0)
8b1a6754 lw       $v1, 8($v0)
8b1a6758 ins      $v1, $a1, 0, 0x16
8b1a675c sw       $v1, 8($v0)
8b1a6760 lw       $v1, 0x3c($v0)
8b1a6764 ins      $v1, $t0, 0, 0x16
8b1a6768 sw       $v1, 0x3c($v0)
8b1a676c lw       $v1, ($v0)
8b1a6770 ins      $v1, $a3, 0x10, 0x10
8b1a6774 sw       $v1, ($v0)
8b1a6778 lw       $v1, 4($v0)
8b1a677c ins      $v1, $a3, 0, 0x10
8b1a6780 sw       $v1, 4($v0)
8b1a6784 lhu      $a1, 0x24($a0)
8b1a6788 lw       $v1, ($v0)
8b1a678c ins      $v1, $a1, 0, 0x10
8b1a6790 sw       $v1, ($v0)
8b1a6794 lhu      $a1, 0x28($a0)
8b1a6798 lw       $v1, 0x38($v0)
8b1a679c ins      $v1, $a1, 0, 0x10
8b1a67a0 sw       $v1, 0x38($v0)
8b1a67a4 lw       $v1, 8($v0)
8b1a67a8 lw       $a1, 0x14($a0)
8b1a67ac ins      $v1, $a1, 0x1c, 3
8b1a67b0 sw       $v1, 8($v0)
8b1a67b4 lw       $v1, 8($v0)
8b1a67b8 lw       $a1, 0x18($a0)
8b1a67bc ins      $v1, $a1, 0x18, 3
8b1a67c0 sw       $v1, 8($v0)
8b1a67c4 lw       $v1, 0x34($v0)
8b1a67c8 lhu      $a1, 0x48($a0)
8b1a67cc ins      $v1, $a1, 0, 0x10
8b1a67d0 sw       $v1, 0x34($v0)
8b1a67d4 lw       $v1, 0x34($v0)
8b1a67d8 lhu      $a1, 0x40($a0)
8b1a67dc ins      $v1, $a1, 0x10, 0x10
8b1a67e0 sw       $v1, 0x34($v0)
8b1a67e4 lw       $v1, 0x2c($v0)
8b1a67e8 lhu      $a1, 0x50($a0)
8b1a67ec ins      $v1, $a1, 0, 0x10
8b1a67f0 sw       $v1, 0x2c($v0)
8b1a67f4 lw       $v1, 0x30($v0)
8b1a67f8 lhu      $a2, 0x58($a0)
8b1a67fc ins      $v1, $a2, 0, 0x10
8b1a6800 sw       $v1, 0x30($v0)
8b1a6804 lw       $v1, 0x30($a0)
8b1a6808 lw       $a2, 0x2c($v0)
8b1a680c addiu    $v1, $v1, 4
8b1a6810 andi     $v1, $v1, 0xffff
8b1a6814 ins      $a2, $v1, 0x10, 0x10
8b1a6818 sw       $a2, 0x2c($v0)
8b1a681c lw       $v1, 4($v0)
8b1a6820 lhu      $a2, 0x38($a0)
8b1a6824 ins      $v1, $a2, 0x10, 0x10
8b1a6828 sw       $v1, 4($v0)
8b1a682c lw       $v1, 0x44($v0)
8b1a6830 lhu      $a2, 0x2c($a0)
8b1a6834 ins      $v1, $a2, 0, 0x10
8b1a6838 sw       $v1, 0x44($v0)
8b1a683c lw       $v1, 0x38($v0)
8b1a6840 lhu      $a0, 0x34($a0)
8b1a6844 ins      $v1, $a0, 0x10, 0x10
8b1a6848 sw       $v1, 0x38($v0)
8b1a684c lw       $v1, 0x40($v0)
8b1a6850 ins      $v1, $a1, 0, 0x10
8b1a6854 sw       $v1, 0x40($v0)
8b1a6858 lw       $v1, 0x30($v0)
8b1a685c ins      $v1, $zero, 0x12, 2
8b1a6860 sw       $v1, 0x30($v0)
8b1a6864 jr       $ra
8b1a6868 nop      
8b1a686c addiu    $sp, $sp, -0x38
8b1a6870 lw       $t4, 0x3c($a0)
8b1a6874 lw       $t3, 0x44($a0)
8b1a6878 lw       $t2, 0x50($a0)
8b1a687c lw       $a3, 0x58($a0)
8b1a6880 lw       $v0, 0x6c($a0)
8b1a6884 lw       $t0, 0x70($a0)
8b1a6888 lw       $v1, 0x74($a0)
8b1a688c lw       $t1, 0x78($a0)
8b1a6890 lui      $a0, 0x8b20
8b1a6894 lw       $a0, 0x71c0($a0)
8b1a6898 addiu    $a2, $zero, 0x1111
8b1a689c sw       $ra, 0x34($sp)
8b1a68a0 sw       $t1, 0x30($a1)
8b1a68a4 sw       $v1, 0x2c($a1)
8b1a68a8 sw       $t0, 0x28($a1)
8b1a68ac sw       $v0, 0x24($a1)
8b1a68b0 sw       $a3, 0x20($a1)
8b1a68b4 sw       $t2, 0x1c($a1)
8b1a68b8 sw       $t3, 0x18($a1)
8b1a68bc sw       $t4, 0x14($a1)
8b1a68c0 sw       $a0, 0x10($a1)
8b1a68c4 sw       $a0, 0xc($a1)
8b1a68c8 sw       $a2, 8($a1)
8b1a68cc sw       $a2, 4($a1)
8b1a68d0 sw       $v0, 0x1c($sp)
8b1a68d4 lui      $v0, 0x8b21
8b1a68d8 addiu    $v0, $v0, -0x7e04
8b1a68dc sw       $v0, 0x18($sp)
8b1a68e0 lui      $v0, 0x8b20
8b1a68e4 addiu    $v0, $v0, 0x7308
8b1a68e8 sw       $v0, 0x14($sp)
8b1a68ec lui      $a3, 0x8b21
8b1a68f0 addiu    $v0, $zero, 0x11b
8b1a68f4 lui      $a2, 0x8b21
8b1a68f8 lui      $a1, 0x8b21
8b1a68fc addiu    $a3, $a3, -0x7e1c
8b1a6900 addiu    $a2, $a2, -0x7f2c
8b1a6904 addiu    $a1, $a1, -0x7f18
8b1a6908 addiu    $a0, $zero, 3
8b1a690c sw       $v0, 0x10($sp)
8b1a6910 sw       $v1, 0x20($sp)
8b1a6914 sw       $t0, 0x24($sp)
8b1a6918 jal      0x8b150068
8b1a691c sw       $t1, 0x28($sp)
8b1a6920 lw       $ra, 0x34($sp)
8b1a6924 jr       $ra
8b1a6928 addiu    $sp, $sp, 0x38
8b1a692c lui      $v0, 0xba14
8b1a6930 lw       $a2, 0x514($v0)
8b1a6934 lhu      $a0, ($a1)
8b1a6938 ins      $a2, $a0, 0x10, 0x10
8b1a693c sw       $a2, 0x514($v0)
8b1a6940 lw       $a2, 0x514($v0)
8b1a6944 lhu      $a3, 8($a1)
8b1a6948 ins      $a2, $a3, 0, 0x10
8b1a694c sw       $a2, 0x514($v0)
8b1a6950 lw       $t0, 0x518($v0)
8b1a6954 lhu      $a2, 4($a1)
8b1a6958 ins      $t0, $a2, 0x10, 0x10
8b1a695c sw       $t0, 0x518($v0)
8b1a6960 lw       $t0, 0x518($v0)
8b1a6964 lhu      $a1, 0xc($a1)
8b1a6968 ins      $t0, $a1, 0, 0x10
8b1a696c sw       $t0, 0x518($v0)
8b1a6970 lw       $t0, 0x524($v0)
8b1a6974 ins      $t0, $a0, 0x10, 0x10
8b1a6978 sw       $t0, 0x524($v0)
8b1a697c lw       $t0, 0x524($v0)
8b1a6980 ins      $t0, $a3, 0, 0x10
8b1a6984 sw       $t0, 0x524($v0)
8b1a6988 lw       $t0, 0x528($v0)
8b1a698c ins      $t0, $a2, 0x10, 0x10
8b1a6990 sw       $t0, 0x528($v0)
8b1a6994 lw       $t0, 0x528($v0)
8b1a6998 ins      $t0, $a1, 0, 0x10
8b1a699c sw       $t0, 0x528($v0)
8b1a69a0 lw       $v1, 0x148($v0)
8b1a69a4 ins      $v1, $a3, 0x10, 0x10
8b1a69a8 sw       $v1, 0x148($v0)
8b1a69ac lw       $v1, 0x148($v0)
8b1a69b0 ins      $v1, $a1, 0, 0x10
8b1a69b4 sw       $v1, 0x148($v0)
8b1a69b8 lw       $v1, 0x14c($v0)
8b1a69bc ins      $v1, $a0, 0x10, 0x10
8b1a69c0 sw       $v1, 0x14c($v0)
8b1a69c4 lw       $v1, 0x14c($v0)
8b1a69c8 ins      $v1, $a2, 0, 0x10
8b1a69cc sw       $v1, 0x14c($v0)
8b1a69d0 lw       $v1, 0x160($v0)
8b1a69d4 ins      $v1, $a1, 0, 0x10
8b1a69d8 sw       $v1, 0x160($v0)
8b1a69dc lw       $v1, 0x160($v0)
8b1a69e0 ins      $v1, $a3, 0x10, 0x10
8b1a69e4 sw       $v1, 0x160($v0)
8b1a69e8 lw       $v1, 0x164($v0)
8b1a69ec ins      $v1, $a2, 0, 0x10
8b1a69f0 sw       $v1, 0x164($v0)
8b1a69f4 lw       $v1, 0x164($v0)
8b1a69f8 ins      $v1, $a0, 0x10, 0x10
8b1a69fc sw       $v1, 0x164($v0)
8b1a6a00 jr       $ra
8b1a6a04 nop      