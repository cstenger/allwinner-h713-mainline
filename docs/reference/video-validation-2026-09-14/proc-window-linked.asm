# Linked VA = file offset + 0x8b100000; verified by constant/string references.
8b1a59e0 addiu    $sp, $sp, -0x48
8b1a59e4 lui      $v0, 0x8b20
8b1a59e8 addiu    $v0, $v0, 0x743c
8b1a59ec sw       $s4, 0x40($sp)
8b1a59f0 lui      $s4, 0x8b20
8b1a59f4 sw       $v0, 0x14($sp)
8b1a59f8 sw       $s1, 0x34($sp)
8b1a59fc addiu    $v0, $zero, 0x1a
8b1a5a00 sw       $s2, 0x38($sp)
8b1a5a04 addiu    $s4, $s4, 0x7430
8b1a5a08 lui      $s2, 0x8b21
8b1a5a0c lui      $s1, 0x8b21
8b1a5a10 sw       $s0, 0x30($sp)
8b1a5a14 sw       $s3, 0x3c($sp)
8b1a5a18 sw       $v0, 0x10($sp)
8b1a5a1c move     $s3, $a1
8b1a5a20 move     $s0, $a0
8b1a5a24 move     $a3, $s4
8b1a5a28 addiu    $a2, $s2, -0x7f2c
8b1a5a2c addiu    $a1, $s1, -0x7f18
8b1a5a30 sw       $s4, 0x18($sp)
8b1a5a34 sw       $ra, 0x44($sp)
8b1a5a38 jal      0x8b150068
8b1a5a3c addiu    $a0, $zero, 3
8b1a5a40 lw       $v0, 0x10($s3)
8b1a5a44 beqz     $v0, 0x8b1a5d78
8b1a5a48 addiu    $a3, $s0, 6
8b1a5a4c lw       $t5, 0x28($v0)
8b1a5a50 lw       $t4, 0x30($v0)
8b1a5a54 lw       $t3, 8($s3)
8b1a5a58 lw       $t2, 0xc($s3)
8b1a5a5c lbu      $t7, 4($s3)
8b1a5a60 lw       $t6, ($s3)
8b1a5a64 sw       $v0, 0xbc($s0)
8b1a5a68 addiu    $v0, $zero, 3
8b1a5a6c sw       $v0, 0x14($s0)
8b1a5a70 addiu    $v0, $zero, 2
8b1a5a74 sw       $v0, 0x18($s0)
8b1a5a78 addiu    $t1, $s0, 0x10
8b1a5a7c move     $v0, $a3
8b1a5a80 addiu    $t0, $s0, 0xc
8b1a5a84 addiu    $v1, $s0, 5
8b1a5a88 sb       $t7, 7($s0)
8b1a5a8c sw       $t6, 8($s0)
8b1a5a90 addiu    $a2, $sp, 0x20
8b1a5a94 addiu    $a1, $sp, 0x28
8b1a5a98 move     $a0, $s0
8b1a5a9c sw       $t1, 0x1c($sp)
8b1a5aa0 sw       $t0, 0x18($sp)
8b1a5aa4 addiu    $a3, $zero, 2
8b1a5aa8 sw       $v0, 0x14($sp)
8b1a5aac sw       $v1, 0x10($sp)
8b1a5ab0 sw       $t3, 0x20($sp)
8b1a5ab4 sw       $t2, 0x24($sp)
8b1a5ab8 sw       $t5, 0x28($sp)
8b1a5abc jal      0x8b1a56b8
8b1a5ac0 sw       $t4, 0x2c($sp)
8b1a5ac4 lbu      $v0, 6($s0)
8b1a5ac8 lw       $v1, 0xc($s0)
8b1a5acc lw       $a0, 0x10($s0)
8b1a5ad0 lbu      $a3, 5($s0)
8b1a5ad4 addiu    $a2, $sp, 0x20
8b1a5ad8 sw       $v0, 0x10($sp)
8b1a5adc sw       $v1, 0x14($sp)
8b1a5ae0 sw       $a0, 0x18($sp)
8b1a5ae4 addiu    $a1, $sp, 0x28
8b1a5ae8 jal      0x8b1a58b0
8b1a5aec move     $a0, $s0
8b1a5af0 lui      $v0, 0x8b20
8b1a5af4 lw       $v0, 0x71c4($v0)
8b1a5af8 lw       $v1, 0xc($s0)
8b1a5afc lw       $a0, 0x10($s0)
8b1a5b00 addu     $v1, $v0, $v1
8b1a5b04 srl      $v1, $v1, 2
8b1a5b08 addu     $v0, $v0, $a0
8b1a5b0c ori      $a0, $zero, 0x8000
8b1a5b10 srl      $v0, $v0, 1
8b1a5b14 sltu     $a0, $v1, $a0
8b1a5b18 sw       $v1, 0x24($s0)
8b1a5b1c bnez     $a0, 0x8b1a5b40
8b1a5b20 sw       $v0, 0x28($s0)
8b1a5b24 lw       $a0, 0x14($s0)
8b1a5b28 lui      $a1, 1
8b1a5b2c sltu     $v1, $v1, $a1
8b1a5b30 addiu    $a0, $a0, 1
8b1a5b34 bnez     $v1, 0x8b1a5b40
8b1a5b38 sw       $a0, 0x14($s0)
8b1a5b3c sw       $zero, 0x24($s0)
8b1a5b40 lui      $v1, 1
8b1a5b44 sltu     $v0, $v0, $v1
8b1a5b48 beql     $v0, $zero, 0x8b1a5d68
8b1a5b4c lw       $v0, 0x18($s0)
8b1a5b50 lw       $a2, 0xbc($s0)
8b1a5b54 lw       $v0, 8($s0)
8b1a5b58 lw       $v1, 0x10($s3)
8b1a5b5c lw       $a1, 0x18($a2)
8b1a5b60 lw       $t0, 0x24($sp)
8b1a5b64 lw       $a0, 0x2c($sp)
8b1a5b68 lbu      $t6, 7($s0)
8b1a5b6c addiu    $v0, $v0, 1
8b1a5b70 lw       $t5, 8($s3)
8b1a5b74 lw       $t4, 0xc($s3)
8b1a5b78 lw       $a3, 0x18($v1)
8b1a5b7c lw       $t2, 0x14($v1)
8b1a5b80 lw       $t1, 0x20($sp)
8b1a5b84 lw       $t3, 0x28($sp)
8b1a5b88 addu     $v0, $v0, $a1
8b1a5b8c addu     $v0, $v0, $t6
8b1a5b90 slt      $a1, $a0, $t0
8b1a5b94 move     $t6, $t0
8b1a5b98 movz     $t6, $a0, $a1
8b1a5b9c sw       $t6, 0x1c($s0)
8b1a5ba0 sw       $t1, 0x80($s0)
8b1a5ba4 sw       $t0, 0x88($s0)
8b1a5ba8 sw       $t5, 0xa0($s0)
8b1a5bac sw       $t4, 0xa8($s0)
8b1a5bb0 sw       $v0, 0x20($s0)
8b1a5bb4 sw       $t2, 0x3c($s0)
8b1a5bb8 sw       $t3, 0x40($s0)
8b1a5bbc sw       $a3, 0x44($s0)
8b1a5bc0 sw       $a0, 0x48($s0)
8b1a5bc4 sw       $t2, 0x4c($s0)
8b1a5bc8 sw       $t3, 0xb0($s0)
8b1a5bcc sw       $a0, 0xb8($s0)
8b1a5bd0 sw       $zero, 0x7c($s0)
8b1a5bd4 sw       $zero, 0x84($s0)
8b1a5bd8 sw       $zero, 0x9c($s0)
8b1a5bdc sw       $zero, 0xa4($s0)
8b1a5be0 sw       $zero, 0xac($s0)
8b1a5be4 sw       $zero, 0xb4($s0)
8b1a5be8 sw       $a3, 0x54($s0)
8b1a5bec lw       $v0, 0x90($s0)
8b1a5bf0 lw       $t3, 0x24($v1)
8b1a5bf4 lw       $t2, 0x2c($v1)
8b1a5bf8 lw       $a0, 0x14($a2)
8b1a5bfc subu     $v1, $v0, $t1
8b1a5c00 lw       $a3, 0x14($s3)
8b1a5c04 slt      $v0, $t1, $v0
8b1a5c08 addiu    $a1, $zero, 0x10
8b1a5c0c addiu    $v1, $v1, 0x10
8b1a5c10 movz     $v1, $a1, $v0
8b1a5c14 sw       $t1, 0x50($s0)
8b1a5c18 sw       $t0, 0x58($s0)
8b1a5c1c sw       $t1, 0x70($s0)
8b1a5c20 sw       $t0, 0x78($s0)
8b1a5c24 sw       $a0, 0x2c($s0)
8b1a5c28 sw       $a0, 0x30($s0)
8b1a5c2c sw       $a1, 0x38($s0)
8b1a5c30 sw       $t3, 0x6c($s0)
8b1a5c34 sw       $t2, 0x74($s0)
8b1a5c38 sw       $v1, 0x34($s0)
8b1a5c3c lbu      $v1, 5($a3)
8b1a5c40 lbu      $v0, 4($a3)
8b1a5c44 lui      $a1, 0x1062
8b1a5c48 sll      $v1, $v1, 8
8b1a5c4c or       $v1, $v1, $v0
8b1a5c50 mul      $t3, $t1, $v1
8b1a5c54 addiu    $a1, $a1, 0x4dd3
8b1a5c58 lw       $v0, ($s0)
8b1a5c5c addiu    $a2, $zero, 0x3e8
8b1a5c60 subu     $v1, $a2, $v1
8b1a5c64 lw       $t2, 0x24($v0)
8b1a5c68 move     $a0, $s0
8b1a5c6c mult     $t3, $a1
8b1a5c70 sra      $t3, $t3, 0x1f
8b1a5c74 mfhi     $v0
8b1a5c78 sra      $v0, $v0, 6
8b1a5c7c subu     $v0, $v0, $t3
8b1a5c80 sw       $v0, 0x5c($s0)
8b1a5c84 lbu      $v0, 7($a3)
8b1a5c88 lbu      $t3, 6($a3)
8b1a5c8c sll      $v0, $v0, 8
8b1a5c90 or       $v0, $v0, $t3
8b1a5c94 subu     $v0, $v1, $v0
8b1a5c98 mul      $v0, $v0, $t1
8b1a5c9c mult     $v0, $a1
8b1a5ca0 sra      $v0, $v0, 0x1f
8b1a5ca4 mfhi     $v1
8b1a5ca8 sra      $v1, $v1, 6
8b1a5cac subu     $v0, $v1, $v0
8b1a5cb0 sw       $v0, 0x60($s0)
8b1a5cb4 lbu      $v0, 9($a3)
8b1a5cb8 lbu      $v1, 8($a3)
8b1a5cbc sll      $v0, $v0, 8
8b1a5cc0 or       $v0, $v0, $v1
8b1a5cc4 mul      $v1, $t0, $v0
8b1a5cc8 subu     $a2, $a2, $v0
8b1a5ccc mult     $v1, $a1
8b1a5cd0 sra      $v1, $v1, 0x1f
8b1a5cd4 mfhi     $v0
8b1a5cd8 sra      $v0, $v0, 6
8b1a5cdc subu     $v0, $v0, $v1
8b1a5ce0 sw       $v0, 0x64($s0)
8b1a5ce4 lbu      $v0, 0xb($a3)
8b1a5ce8 lbu      $v1, 0xa($a3)
8b1a5cec sll      $v0, $v0, 8
8b1a5cf0 or       $v0, $v0, $v1
8b1a5cf4 subu     $v0, $a2, $v0
8b1a5cf8 mul      $v0, $v0, $t0
8b1a5cfc mult     $v0, $a1
8b1a5d00 sra      $v0, $v0, 0x1f
8b1a5d04 mfhi     $a1
8b1a5d08 sra      $a1, $a1, 6
8b1a5d0c subu     $v0, $a1, $v0
8b1a5d10 jalr     $t2
8b1a5d14 sw       $v0, 0x68($s0)
8b1a5d18 lui      $v0, 0x8b20
8b1a5d1c addiu    $v0, $v0, 0x7468
8b1a5d20 sw       $v0, 0x14($sp)
8b1a5d24 addiu    $v0, $zero, 0x68
8b1a5d28 move     $a3, $s4
8b1a5d2c addiu    $a2, $s2, -0x7f2c
8b1a5d30 addiu    $a1, $s1, -0x7f18
8b1a5d34 sw       $s4, 0x18($sp)
8b1a5d38 sw       $v0, 0x10($sp)
8b1a5d3c jal      0x8b150068
8b1a5d40 addiu    $a0, $zero, 3
8b1a5d44 lw       $s0, 0x30($sp)
8b1a5d48 lw       $s1, 0x34($sp)
8b1a5d4c lw       $s2, 0x38($sp)
8b1a5d50 lw       $s3, 0x3c($sp)
8b1a5d54 lw       $s4, 0x40($sp)
8b1a5d58 lw       $ra, 0x44($sp)
8b1a5d5c addiu    $v0, $zero, 1
8b1a5d60 jr       $ra
8b1a5d64 addiu    $sp, $sp, 0x48
8b1a5d68 sw       $zero, 0x28($s0)
8b1a5d6c addiu    $v0, $v0, 1
8b1a5d70 b        0x8b1a5b50
8b1a5d74 sw       $v0, 0x18($s0)
8b1a5d78 lui      $v0, 0x8b20
8b1a5d7c addiu    $v0, $v0, 0x7468
8b1a5d80 sw       $v0, 0x14($sp)
8b1a5d84 addiu    $v0, $zero, 0x1c
8b1a5d88 move     $a3, $s4
8b1a5d8c addiu    $a2, $s2, -0x7f2c
8b1a5d90 addiu    $a1, $s1, -0x7f18
8b1a5d94 sw       $s4, 0x18($sp)
8b1a5d98 sw       $v0, 0x10($sp)
8b1a5d9c jal      0x8b150068
8b1a5da0 addiu    $a0, $zero, 3
8b1a5da4 lui      $v0, 0x8b20
8b1a5da8 addiu    $v0, $v0, 0x7448
8b1a5dac sw       $v0, 0x14($sp)
8b1a5db0 addiu    $v0, $zero, 0x1d
8b1a5db4 move     $a3, $s4
8b1a5db8 addiu    $a2, $s2, -0x7f2c
8b1a5dbc addiu    $a1, $s1, -0x7f18
8b1a5dc0 sw       $v0, 0x10($sp)
8b1a5dc4 jal      0x8b150068
8b1a5dc8 addiu    $a0, $zero, 1
8b1a5dcc lw       $s0, 0x30($sp)
8b1a5dd0 lw       $s1, 0x34($sp)
8b1a5dd4 lw       $s2, 0x38($sp)
8b1a5dd8 lw       $s3, 0x3c($sp)
8b1a5ddc lw       $s4, 0x40($sp)
8b1a5de0 lw       $ra, 0x44($sp)
8b1a5de4 move     $v0, $zero
8b1a5de8 jr       $ra
8b1a5dec addiu    $sp, $sp, 0x48
8b1a5df0 lw       $a1, 0xbc($a0)
8b1a5df4 lui      $v0, 0xba18
8b1a5df8 lw       $v1, 0x20($v0)
8b1a5dfc lbu      $a1, 0xc($a1)
8b1a5e00 addiu    $a2, $zero, 1
8b1a5e04 addiu    $a3, $zero, 0xf00
8b1a5e08 ins      $v1, $a1, 0x18, 8
8b1a5e0c sw       $v1, 0x20($v0)
8b1a5e10 lw       $a1, 0x14($v0)
8b1a5e14 lui      $v1, 0x8b20
8b1a5e18 lw       $v1, 0x71c4($v1)
8b1a5e1c ins      $a1, $zero, 0x1c, 4
8b1a5e20 sw       $a1, 0x14($v0)
8b1a5e24 lw       $a1, 0x40($v0)
8b1a5e28 ins      $a1, $a2, 0x1f, 1
8b1a5e2c sw       $a1, 0x40($v0)
8b1a5e30 lw       $a1, 0x50($v0)
8b1a5e34 lhu      $a2, 0x1c($a0)
8b1a5e38 ins      $a1, $a2, 0, 0x10
8b1a5e3c sw       $a1, 0x50($v0)
8b1a5e40 lw       $a1, 0x50($v0)
8b1a5e44 lhu      $a2, 0x20($a0)
8b1a5e48 ins      $a1, $a2, 0x10, 0x10
8b1a5e4c sw       $a1, 0x50($v0)
8b1a5e50 lw       $a1, 0xc($a0)
8b1a5e54 lw       $t0, 0x10($a0)
8b1a5e58 lw       $t1, 0x14($v0)
8b1a5e5c xor      $v1, $a1, $v1
8b1a5e60 xor      $a2, $a1, $t0
8b1a5e64 sltiu    $a2, $a2, 1
8b1a5e68 movn     $a2, $zero, $v1
8b1a5e6c ins      $t1, $a2, 0x1b, 1
8b1a5e70 sw       $t1, 0x14($v0)
8b1a5e74 lw       $v1, 8($v0)
8b1a5e78 ins      $v1, $a1, 0, 0x16
8b1a5e7c sw       $v1, 8($v0)
8b1a5e80 lw       $v1, 0x3c($v0)
8b1a5e84 ins      $v1, $t0, 0, 0x16
8b1a5e88 sw       $v1, 0x3c($v0)
8b1a5e8c lw       $v1, ($v0)
8b1a5e90 ins      $v1, $a3, 0x10, 0x10
8b1a5e94 sw       $v1, ($v0)
8b1a5e98 lw       $v1, 4($v0)
8b1a5e9c ins      $v1, $a3, 0, 0x10
8b1a5ea0 sw       $v1, 4($v0)
8b1a5ea4 lhu      $a1, 0x24($a0)
8b1a5ea8 lw       $v1, ($v0)
8b1a5eac ins      $v1, $a1, 0, 0x10
8b1a5eb0 sw       $v1, ($v0)
8b1a5eb4 lhu      $a1, 0x28($a0)
8b1a5eb8 lw       $v1, 0x38($v0)
8b1a5ebc ins      $v1, $a1, 0, 0x10
8b1a5ec0 sw       $v1, 0x38($v0)
8b1a5ec4 lw       $v1, 8($v0)
8b1a5ec8 lw       $a1, 0x14($a0)
8b1a5ecc ins      $v1, $a1, 0x1c, 3
8b1a5ed0 sw       $v1, 8($v0)
8b1a5ed4 lw       $v1, 8($v0)
8b1a5ed8 lw       $a1, 0x18($a0)
8b1a5edc ins      $v1, $a1, 0x18, 3
8b1a5ee0 sw       $v1, 8($v0)
8b1a5ee4 lw       $v1, 0x34($v0)
8b1a5ee8 lhu      $a1, 0x48($a0)
8b1a5eec ins      $v1, $a1, 0, 0x10
8b1a5ef0 sw       $v1, 0x34($v0)
8b1a5ef4 lw       $v1, 0x34($v0)
8b1a5ef8 lhu      $a1, 0x40($a0)
8b1a5efc ins      $v1, $a1, 0x10, 0x10
8b1a5f00 sw       $v1, 0x34($v0)
8b1a5f04 lw       $v1, 0x2c($v0)
8b1a5f08 lhu      $a1, 0x50($a0)
8b1a5f0c ins      $v1, $a1, 0, 0x10
8b1a5f10 sw       $v1, 0x2c($v0)
8b1a5f14 lw       $v1, 0x30($v0)
8b1a5f18 lhu      $a2, 0x58($a0)
8b1a5f1c ins      $v1, $a2, 0, 0x10
8b1a5f20 sw       $v1, 0x30($v0)
8b1a5f24 lw       $v1, 0x30($a0)
8b1a5f28 lw       $a2, 0x2c($v0)
8b1a5f2c addiu    $v1, $v1, 4
8b1a5f30 andi     $v1, $v1, 0xffff
8b1a5f34 ins      $a2, $v1, 0x10, 0x10
8b1a5f38 sw       $a2, 0x2c($v0)
8b1a5f3c lw       $v1, 4($v0)
8b1a5f40 lhu      $a2, 0x38($a0)
8b1a5f44 ins      $v1, $a2, 0x10, 0x10
8b1a5f48 sw       $v1, 4($v0)
8b1a5f4c lw       $v1, 0x44($v0)
8b1a5f50 lhu      $a2, 0x2c($a0)
8b1a5f54 ins      $v1, $a2, 0, 0x10
8b1a5f58 sw       $v1, 0x44($v0)
8b1a5f5c lw       $v1, 0x38($v0)
8b1a5f60 lhu      $a0, 0x34($a0)
8b1a5f64 ins      $v1, $a0, 0x10, 0x10
8b1a5f68 sw       $v1, 0x38($v0)
8b1a5f6c lw       $v1, 0x40($v0)
8b1a5f70 ins      $v1, $a1, 0, 0x10
8b1a5f74 sw       $v1, 0x40($v0)
8b1a5f78 lw       $v1, 0x30($v0)
8b1a5f7c ins      $v1, $zero, 0x12, 2
8b1a5f80 sw       $v1, 0x30($v0)
8b1a5f84 jr       $ra
8b1a5f88 nop      
8b1a5f8c addiu    $sp, $sp, -0x38
8b1a5f90 lw       $t4, 0x3c($a0)
8b1a5f94 lw       $t3, 0x44($a0)
8b1a5f98 lw       $t2, 0x50($a0)
8b1a5f9c lw       $a3, 0x58($a0)
8b1a5fa0 lw       $v0, 0x6c($a0)
8b1a5fa4 lw       $t0, 0x70($a0)
8b1a5fa8 lw       $v1, 0x74($a0)
8b1a5fac lw       $t1, 0x78($a0)
8b1a5fb0 lui      $a0, 0x8b20
8b1a5fb4 lw       $a0, 0x71c0($a0)
8b1a5fb8 addiu    $a2, $zero, 0x1111
8b1a5fbc sw       $ra, 0x34($sp)
8b1a5fc0 sw       $t1, 0x30($a1)
8b1a5fc4 sw       $v1, 0x2c($a1)
8b1a5fc8 sw       $t0, 0x28($a1)
8b1a5fcc sw       $v0, 0x24($a1)
8b1a5fd0 sw       $a3, 0x20($a1)
8b1a5fd4 sw       $t2, 0x1c($a1)
8b1a5fd8 sw       $t3, 0x18($a1)
8b1a5fdc sw       $t4, 0x14($a1)
8b1a5fe0 sw       $a0, 0x10($a1)
8b1a5fe4 sw       $a0, 0xc($a1)
8b1a5fe8 sw       $a2, 8($a1)
8b1a5fec sw       $a2, 4($a1)
8b1a5ff0 sw       $v0, 0x1c($sp)
8b1a5ff4 lui      $v0, 0x8b21
8b1a5ff8 addiu    $v0, $v0, -0x7e04
8b1a5ffc sw       $v0, 0x18($sp)
8b1a6000 lui      $v0, 0x8b20
8b1a6004 addiu    $v0, $v0, 0x7308
8b1a6008 sw       $v0, 0x14($sp)
8b1a600c lui      $a3, 0x8b21
8b1a6010 addiu    $v0, $zero, 0x11b
8b1a6014 lui      $a2, 0x8b21
8b1a6018 lui      $a1, 0x8b21
8b1a601c addiu    $a3, $a3, -0x7e1c
8b1a6020 addiu    $a2, $a2, -0x7f2c
8b1a6024 addiu    $a1, $a1, -0x7f18
8b1a6028 addiu    $a0, $zero, 3
8b1a602c sw       $v0, 0x10($sp)
8b1a6030 sw       $v1, 0x20($sp)
8b1a6034 sw       $t0, 0x24($sp)
8b1a6038 jal      0x8b150068
8b1a603c sw       $t1, 0x28($sp)
8b1a6040 lw       $ra, 0x34($sp)
8b1a6044 jr       $ra
8b1a6048 addiu    $sp, $sp, 0x38
8b1a604c lui      $v0, 0xba14
8b1a6050 lw       $a2, 0x514($v0)
8b1a6054 lhu      $a0, ($a1)
8b1a6058 ins      $a2, $a0, 0x10, 0x10
8b1a605c sw       $a2, 0x514($v0)
8b1a6060 lw       $a2, 0x514($v0)
8b1a6064 lhu      $a3, 8($a1)
8b1a6068 ins      $a2, $a3, 0, 0x10
8b1a606c sw       $a2, 0x514($v0)
8b1a6070 lw       $t0, 0x518($v0)
8b1a6074 lhu      $a2, 4($a1)
8b1a6078 ins      $t0, $a2, 0x10, 0x10
8b1a607c sw       $t0, 0x518($v0)
8b1a6080 lw       $t0, 0x518($v0)
8b1a6084 lhu      $a1, 0xc($a1)
8b1a6088 ins      $t0, $a1, 0, 0x10
8b1a608c sw       $t0, 0x518($v0)
8b1a6090 lw       $t0, 0x524($v0)
8b1a6094 ins      $t0, $a0, 0x10, 0x10
8b1a6098 sw       $t0, 0x524($v0)
8b1a609c lw       $t0, 0x524($v0)
8b1a60a0 ins      $t0, $a3, 0, 0x10
8b1a60a4 sw       $t0, 0x524($v0)
8b1a60a8 lw       $t0, 0x528($v0)
8b1a60ac ins      $t0, $a2, 0x10, 0x10
8b1a60b0 sw       $t0, 0x528($v0)
8b1a60b4 lw       $t0, 0x528($v0)
8b1a60b8 ins      $t0, $a1, 0, 0x10
8b1a60bc sw       $t0, 0x528($v0)
8b1a60c0 lw       $v1, 0x148($v0)
8b1a60c4 ins      $v1, $a3, 0x10, 0x10
8b1a60c8 sw       $v1, 0x148($v0)
8b1a60cc lw       $v1, 0x148($v0)
8b1a60d0 ins      $v1, $a1, 0, 0x10
8b1a60d4 sw       $v1, 0x148($v0)
8b1a60d8 lw       $v1, 0x14c($v0)
8b1a60dc ins      $v1, $a0, 0x10, 0x10
8b1a60e0 sw       $v1, 0x14c($v0)
8b1a60e4 lw       $v1, 0x14c($v0)
8b1a60e8 ins      $v1, $a2, 0, 0x10
8b1a60ec sw       $v1, 0x14c($v0)
8b1a60f0 lw       $v1, 0x160($v0)
8b1a60f4 ins      $v1, $a1, 0, 0x10
8b1a60f8 sw       $v1, 0x160($v0)
8b1a60fc lw       $v1, 0x160($v0)
8b1a6100 ins      $v1, $a3, 0x10, 0x10
8b1a6104 sw       $v1, 0x160($v0)
8b1a6108 lw       $v1, 0x164($v0)
8b1a610c ins      $v1, $a2, 0, 0x10
8b1a6110 sw       $v1, 0x164($v0)
8b1a6114 lw       $v1, 0x164($v0)
8b1a6118 ins      $v1, $a0, 0x10, 0x10
8b1a611c sw       $v1, 0x164($v0)
8b1a6120 jr       $ra
8b1a6124 nop      
8b1a6128 addiu    $sp, $sp, -0x38
8b1a612c lui      $v0, 0x8b20
8b1a6130 addiu    $v0, $v0, 0x743c
8b1a6134 sw       $s1, 0x24($sp)
8b1a6138 lui      $s1, 0x8b20
8b1a613c sw       $s2, 0x28($sp)
8b1a6140 sw       $s3, 0x2c($sp)
8b1a6144 sw       $s4, 0x30($sp)
8b1a6148 addiu    $s1, $s1, 0x7494
8b1a614c move     $s2, $a1
8b1a6150 sw       $v0, 0x14($sp)
8b1a6154 lui      $s4, 0x8b21
8b1a6158 lui      $s3, 0x8b21
8b1a615c addiu    $v0, $zero, 0x9b
8b1a6160 sw       $s0, 0x20($sp)
8b1a6164 ext      $s2, $s2, 0x16, 1
8b1a6168 move     $s0, $a0
8b1a616c move     $a3, $s1
8b1a6170 addiu    $a2, $s4, -0x7f2c
8b1a6174 addiu    $a1, $s3, -0x7f18
8b1a6178 sw       $v0, 0x10($sp)
8b1a617c sw       $s1, 0x18($sp)
8b1a6180 sw       $ra, 0x34($sp)
8b1a6184 jal      0x8b150068
8b1a6188 addiu    $a0, $zero, 3
8b1a618c bnez     $s2, 0x8b1a61e0
8b1a6190 lui      $t2, 0xba14
8b1a6194 lui      $v0, 0x8b20
8b1a6198 addiu    $v0, $v0, 0x7468
8b1a619c sw       $v0, 0x14($sp)
8b1a61a0 addiu    $v0, $zero, 0xa6
8b1a61a4 move     $a3, $s1
8b1a61a8 addiu    $a2, $s4, -0x7f2c
8b1a61ac addiu    $a1, $s3, -0x7f18
8b1a61b0 sw       $s1, 0x18($sp)
8b1a61b4 addiu    $a0, $zero, 3
8b1a61b8 jal      0x8b150068
8b1a61bc sw       $v0, 0x10($sp)
8b1a61c0 lw       $s0, 0x20($sp)
8b1a61c4 lw       $s1, 0x24($sp)
8b1a61c8 lw       $s2, 0x28($sp)
8b1a61cc lw       $s3, 0x2c($sp)
8b1a61d0 lw       $s4, 0x30($sp)
8b1a61d4 lw       $ra, 0x34($sp)
8b1a61d8 jr       $ra
8b1a61dc addiu    $sp, $sp, 0x38
8b1a61e0 lw       $v0, 0x114($t2)
8b1a61e4 ins      $v0, $zero, 0x1f, 1
8b1a61e8 sw       $v0, 0x114($t2)
8b1a61ec lw       $v1, 0xb0($s0)
8b1a61f0 lw       $a0, 0x104($t2)
8b1a61f4 lhu      $t0, 0xac($s0)
8b1a61f8 srl      $a3, $v1, 0x1f
8b1a61fc addu     $v0, $v1, $a3
8b1a6200 andi     $v0, $v0, 1
8b1a6204 subu     $v0, $v0, $a3
8b1a6208 addu     $v0, $v0, $v1
8b1a620c andi     $v0, $v0, 0xffff
8b1a6210 ins      $a0, $v0, 0x10, 0x10
8b1a6214 sw       $a0, 0x104($t2)
8b1a6218 lw       $v0, 0x104($t2)
8b1a621c move     $a0, $s0
8b1a6220 ins      $v0, $t0, 0, 0x10
8b1a6224 sw       $v0, 0x104($t2)
8b1a6228 lw       $v0, 0x108($t2)
8b1a622c lhu      $v1, 0xb4($s0)
8b1a6230 ins      $v0, $v1, 0, 0x10
8b1a6234 sw       $v0, 0x108($t2)
8b1a6238 lw       $v1, 0xb8($s0)
8b1a623c lw       $a3, 0x108($t2)
8b1a6240 srl      $t0, $v1, 0x1f
8b1a6244 addu     $v0, $v1, $t0
8b1a6248 andi     $v0, $v0, 1
8b1a624c andi     $v1, $v1, 0xffff
8b1a6250 subu     $v0, $v0, $t0
8b1a6254 addu     $v0, $v1, $v0
8b1a6258 andi     $v0, $v0, 0xffff
8b1a625c ins      $a3, $v0, 0x10, 0x10
8b1a6260 sw       $a3, 0x108($t2)
8b1a6264 lw       $v0, 0x134($t2)
8b1a6268 ins      $v0, $zero, 0x1f, 1
8b1a626c sw       $v0, 0x134($t2)
8b1a6270 lw       $v0, 0x124($t2)
8b1a6274 lhu      $a3, 0xa0($s0)
8b1a6278 lhu      $a2, 0x9c($s0)
8b1a627c ins      $v0, $a3, 0x10, 0x10
8b1a6280 sw       $v0, 0x124($t2)
8b1a6284 lw       $v0, 0x124($t2)
8b1a6288 ins      $v0, $a2, 0, 0x10
8b1a628c sw       $v0, 0x124($t2)
8b1a6290 lw       $v0, 0x128($t2)
8b1a6294 lhu      $a2, 0xa8($s0)
8b1a6298 ins      $v0, $a2, 0x10, 0x10
8b1a629c sw       $v0, 0x128($t2)
8b1a62a0 lw       $v0, 0x128($t2)
8b1a62a4 lhu      $a2, 0xa4($s0)
8b1a62a8 ins      $v0, $a2, 0, 0x10
8b1a62ac sw       $v0, 0x128($t2)
8b1a62b0 lw       $v0, 0x11c($t2)
8b1a62b4 ins      $v0, $v1, 0x10, 0x10
8b1a62b8 sw       $v0, 0x11c($t2)
8b1a62bc lw       $v0, 0x11c($t2)
8b1a62c0 addiu    $v1, $zero, 1
8b1a62c4 ins      $v0, $v1, 0xf, 1
8b1a62c8 sw       $v0, 0x11c($t2)
8b1a62cc jal      0x8b1a5df0
8b1a62d0 nop      
8b1a62d4 lw       $v1, 0xd40($t2)
8b1a62d8 lhu      $a0, 0x80($s0)
8b1a62dc lhu      $a2, 0x7c($s0)
8b1a62e0 addiu    $a1, $s0, 0x5c
8b1a62e4 ins      $v1, $a0, 0x10, 0x10
8b1a62e8 sw       $v1, 0xd40($t2)
8b1a62ec lw       $v1, 0xd40($t2)
8b1a62f0 move     $a0, $s0
8b1a62f4 ins      $v1, $a2, 0, 0x10
8b1a62f8 sw       $v1, 0xd40($t2)
8b1a62fc lhu      $a2, 0x88($s0)
