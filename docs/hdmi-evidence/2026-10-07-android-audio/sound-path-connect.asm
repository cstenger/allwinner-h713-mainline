
docs/hdmi-evidence/2026-10-07-android-audio/libmspsound.so:     file format elf32-littlearm


Disassembly of section .text:

00013abc <Sound_Path_Connect@@Base>:
   13abc:	e92d 4ff0 	stmdb	sp!, {r4, r5, r6, r7, r8, r9, sl, fp, lr}
   13ac0:	b093      	sub	sp, #76	@ 0x4c
   13ac2:	4604      	mov	r4, r0
   13ac4:	48a9      	ldr	r0, [pc, #676]	@ (13d6c <Sound_Path_Connect@@Base+0x2b0>)
   13ac6:	4aaa      	ldr	r2, [pc, #680]	@ (13d70 <Sound_Path_Connect@@Base+0x2b4>)
   13ac8:	efc0 0050 	vmov.i32	q8, #0	@ 0x00000000
   13acc:	4478      	add	r0, pc
   13ace:	a90c      	add	r1, sp, #48	@ 0x30
   13ad0:	447a      	add	r2, pc
   13ad2:	4623      	mov	r3, r4
   13ad4:	f8d0 b000 	ldr.w	fp, [r0]
   13ad8:	f8db 0000 	ldr.w	r0, [fp]
   13adc:	9012      	str	r0, [sp, #72]	@ 0x48
   13ade:	2000      	movs	r0, #0
   13ae0:	f941 0acf 	vst1.64	{d16-d17}, [r1]
   13ae4:	2100      	movs	r1, #0
   13ae6:	9011      	str	r0, [sp, #68]	@ 0x44
   13ae8:	e9cd 000a 	strd	r0, r0, [sp, #40]	@ 0x28
   13aec:	e9cd 0008 	strd	r0, r0, [sp, #32]
   13af0:	f88d 001f 	strb.w	r0, [sp, #31]
   13af4:	2003      	movs	r0, #3
   13af6:	f008 eb34 	blx	1c160 <get_node_from_cabinetindex@@Base+0x738>
   13afa:	f10d 011f 	add.w	r1, sp, #31
   13afe:	4620      	mov	r0, r4
   13b00:	f009 e96e 	blx	1cde0 <get_node_from_cabinetindex@@Base+0x13b8>
   13b04:	f241 3a0a 	movw	sl, #4874	@ 0x130a
   13b08:	f2c0 0a06 	movt	sl, #6
   13b0c:	b168      	cbz	r0, 13b2a <Sound_Path_Connect@@Base+0x6e>
   13b0e:	4450      	add	r0, sl
   13b10:	f100 0af6 	add.w	sl, r0, #246	@ 0xf6
   13b14:	9812      	ldr	r0, [sp, #72]	@ 0x48
   13b16:	f8db 1000 	ldr.w	r1, [fp]
   13b1a:	1a08      	subs	r0, r1, r0
   13b1c:	bf02      	ittt	eq
   13b1e:	4650      	moveq	r0, sl
   13b20:	b013      	addeq	sp, #76	@ 0x4c
   13b22:	e8bd 8ff0 	ldmiaeq.w	sp!, {r4, r5, r6, r7, r8, r9, sl, fp, pc}
   13b26:	f008 eb6c 	blx	1c200 <get_node_from_cabinetindex@@Base+0x7d8>
   13b2a:	f89d 001f 	ldrb.w	r0, [sp, #31]
   13b2e:	b1f0      	cbz	r0, 13b6e <Sound_Path_Connect@@Base+0xb2>
   13b30:	4d90      	ldr	r5, [pc, #576]	@ (13d74 <Sound_Path_Connect@@Base+0x2b8>)
   13b32:	f004 0007 	and.w	r0, r4, #7
   13b36:	2101      	movs	r1, #1
   13b38:	08e6      	lsrs	r6, r4, #3
   13b3a:	447d      	add	r5, pc
   13b3c:	fa01 f900 	lsl.w	r9, r1, r0
   13b40:	5da8      	ldrb	r0, [r5, r6]
   13b42:	ea19 0f00 	tst.w	r9, r0
   13b46:	d015      	beq.n	13b74 <Sound_Path_Connect@@Base+0xb8>
   13b48:	488b      	ldr	r0, [pc, #556]	@ (13d78 <Sound_Path_Connect@@Base+0x2bc>)
   13b4a:	f240 778c 	movw	r7, #1932	@ 0x78c
   13b4e:	4a8b      	ldr	r2, [pc, #556]	@ (13d7c <Sound_Path_Connect@@Base+0x2c0>)
   13b50:	4478      	add	r0, pc
   13b52:	4b8b      	ldr	r3, [pc, #556]	@ (13d80 <Sound_Path_Connect@@Base+0x2c4>)
   13b54:	447a      	add	r2, pc
   13b56:	6800      	ldr	r0, [r0, #0]
   13b58:	447b      	add	r3, pc
   13b5a:	6800      	ldr	r0, [r0, #0]
   13b5c:	4989      	ldr	r1, [pc, #548]	@ (13d84 <Sound_Path_Connect@@Base+0x2c8>)
   13b5e:	4479      	add	r1, pc
   13b60:	e9cd 7100 	strd	r7, r1, [sp]
   13b64:	2103      	movs	r1, #3
   13b66:	f008 ebd4 	blx	1c310 <get_node_from_cabinetindex@@Base+0x8e8>
   13b6a:	2001      	movs	r0, #1
   13b6c:	e003      	b.n	13b76 <Sound_Path_Connect@@Base+0xba>
   13b6e:	f1aa 0a07 	sub.w	sl, sl, #7
   13b72:	e7cf      	b.n	13b14 <Sound_Path_Connect@@Base+0x58>
   13b74:	2000      	movs	r0, #0
   13b76:	a90b      	add	r1, sp, #44	@ 0x2c
   13b78:	aa11      	add	r2, sp, #68	@ 0x44
   13b7a:	9006      	str	r0, [sp, #24]
   13b7c:	4620      	mov	r0, r4
   13b7e:	f009 e938 	blx	1cdf0 <get_node_from_cabinetindex@@Base+0x13c8>
   13b82:	b140      	cbz	r0, 13b96 <Sound_Path_Connect@@Base+0xda>
   13b84:	4a81      	ldr	r2, [pc, #516]	@ (13d8c <Sound_Path_Connect@@Base+0x2d0>)
   13b86:	2003      	movs	r0, #3
   13b88:	2100      	movs	r1, #0
   13b8a:	447a      	add	r2, pc
   13b8c:	f008 eae8 	blx	1c160 <get_node_from_cabinetindex@@Base+0x738>
   13b90:	f1aa 0a04 	sub.w	sl, sl, #4
   13b94:	e7be      	b.n	13b14 <Sound_Path_Connect@@Base+0x58>
   13b96:	980b      	ldr	r0, [sp, #44]	@ 0x2c
   13b98:	e9cd 6504 	strd	r6, r5, [sp, #16]
   13b9c:	2801      	cmp	r0, #1
   13b9e:	db16      	blt.n	13bce <Sound_Path_Connect@@Base+0x112>
   13ba0:	f10d 0830 	add.w	r8, sp, #48	@ 0x30
   13ba4:	2600      	movs	r6, #0
   13ba6:	2500      	movs	r5, #0
   13ba8:	9811      	ldr	r0, [sp, #68]	@ 0x44
   13baa:	5981      	ldr	r1, [r0, r6]
   13bac:	4430      	add	r0, r6
   13bae:	910c      	str	r1, [sp, #48]	@ 0x30
   13bb0:	6841      	ldr	r1, [r0, #4]
   13bb2:	910d      	str	r1, [sp, #52]	@ 0x34
   13bb4:	6880      	ldr	r0, [r0, #8]
   13bb6:	900e      	str	r0, [sp, #56]	@ 0x38
   13bb8:	4640      	mov	r0, r8
   13bba:	f009 e922 	blx	1ce00 <get_node_from_cabinetindex@@Base+0x13d8>
   13bbe:	2800      	cmp	r0, #0
   13bc0:	f040 808f 	bne.w	13ce2 <Sound_Path_Connect@@Base+0x226>
   13bc4:	980b      	ldr	r0, [sp, #44]	@ 0x2c
   13bc6:	3501      	adds	r5, #1
   13bc8:	360c      	adds	r6, #12
   13bca:	4285      	cmp	r5, r0
   13bcc:	dbec      	blt.n	13ba8 <Sound_Path_Connect@@Base+0xec>
   13bce:	aa0a      	add	r2, sp, #40	@ 0x28
   13bd0:	4620      	mov	r0, r4
   13bd2:	2100      	movs	r1, #0
   13bd4:	f8cd 900c 	str.w	r9, [sp, #12]
   13bd8:	f009 e91a 	blx	1ce10 <get_node_from_cabinetindex@@Base+0x13e8>
   13bdc:	b9b8      	cbnz	r0, 13c0e <Sound_Path_Connect@@Base+0x152>
   13bde:	980a      	ldr	r0, [sp, #40]	@ 0x28
   13be0:	b1a8      	cbz	r0, 13c0e <Sound_Path_Connect@@Base+0x152>
   13be2:	f10d 0824 	add.w	r8, sp, #36	@ 0x24
   13be6:	ad0a      	add	r5, sp, #40	@ 0x28
   13be8:	2701      	movs	r7, #1
   13bea:	6801      	ldr	r1, [r0, #0]
   13bec:	b929      	cbnz	r1, 13bfa <Sound_Path_Connect@@Base+0x13e>
   13bee:	4641      	mov	r1, r8
   13bf0:	f008 ee6e 	blx	1c8d0 <get_node_from_cabinetindex@@Base+0xea8>
   13bf4:	2800      	cmp	r0, #0
   13bf6:	f040 8085 	bne.w	13d04 <Sound_Path_Connect@@Base+0x248>
   13bfa:	4620      	mov	r0, r4
   13bfc:	4639      	mov	r1, r7
   13bfe:	462a      	mov	r2, r5
   13c00:	f009 e906 	blx	1ce10 <get_node_from_cabinetindex@@Base+0x13e8>
   13c04:	b918      	cbnz	r0, 13c0e <Sound_Path_Connect@@Base+0x152>
   13c06:	980a      	ldr	r0, [sp, #40]	@ 0x28
   13c08:	3701      	adds	r7, #1
   13c0a:	2800      	cmp	r0, #0
   13c0c:	d1ed      	bne.n	13bea <Sound_Path_Connect@@Base+0x12e>
   13c0e:	980b      	ldr	r0, [sp, #44]	@ 0x2c
   13c10:	2801      	cmp	r0, #1
   13c12:	db1a      	blt.n	13c4a <Sound_Path_Connect@@Base+0x18e>
   13c14:	2600      	movs	r6, #0
   13c16:	2501      	movs	r5, #1
   13c18:	f10d 0830 	add.w	r8, sp, #48	@ 0x30
   13c1c:	f04f 0900 	mov.w	r9, #0
   13c20:	9811      	ldr	r0, [sp, #68]	@ 0x44
   13c22:	950f      	str	r5, [sp, #60]	@ 0x3c
   13c24:	5981      	ldr	r1, [r0, r6]
   13c26:	4430      	add	r0, r6
   13c28:	910c      	str	r1, [sp, #48]	@ 0x30
   13c2a:	6841      	ldr	r1, [r0, #4]
   13c2c:	910d      	str	r1, [sp, #52]	@ 0x34
   13c2e:	9906      	ldr	r1, [sp, #24]
   13c30:	6880      	ldr	r0, [r0, #8]
   13c32:	900e      	str	r0, [sp, #56]	@ 0x38
   13c34:	4640      	mov	r0, r8
   13c36:	f008 edac 	blx	1c790 <get_node_from_cabinetindex@@Base+0xd68>
   13c3a:	2800      	cmp	r0, #0
   13c3c:	d155      	bne.n	13cea <Sound_Path_Connect@@Base+0x22e>
   13c3e:	980b      	ldr	r0, [sp, #44]	@ 0x2c
   13c40:	f109 0901 	add.w	r9, r9, #1
   13c44:	360c      	adds	r6, #12
   13c46:	4581      	cmp	r9, r0
   13c48:	dbea      	blt.n	13c20 <Sound_Path_Connect@@Base+0x164>
   13c4a:	2000      	movs	r0, #0
   13c4c:	ebb0 2f94 	cmp.w	r0, r4, lsr #10
   13c50:	d105      	bne.n	13c5e <Sound_Path_Connect@@Base+0x1a2>
   13c52:	e9dd 3104 	ldrd	r3, r1, [sp, #16]
   13c56:	9a03      	ldr	r2, [sp, #12]
   13c58:	5cc8      	ldrb	r0, [r1, r3]
   13c5a:	4310      	orrs	r0, r2
   13c5c:	54c8      	strb	r0, [r1, r3]
   13c5e:	aa0a      	add	r2, sp, #40	@ 0x28
   13c60:	4620      	mov	r0, r4
   13c62:	2100      	movs	r1, #0
   13c64:	f009 e8d4 	blx	1ce10 <get_node_from_cabinetindex@@Base+0x13e8>
   13c68:	b9b8      	cbnz	r0, 13c9a <Sound_Path_Connect@@Base+0x1de>
   13c6a:	980a      	ldr	r0, [sp, #40]	@ 0x28
   13c6c:	b1a8      	cbz	r0, 13c9a <Sound_Path_Connect@@Base+0x1de>
   13c6e:	f10d 0824 	add.w	r8, sp, #36	@ 0x24
   13c72:	ae0a      	add	r6, sp, #40	@ 0x28
   13c74:	2701      	movs	r7, #1
   13c76:	6801      	ldr	r1, [r0, #0]
   13c78:	2901      	cmp	r1, #1
   13c7a:	d104      	bne.n	13c86 <Sound_Path_Connect@@Base+0x1ca>
   13c7c:	4641      	mov	r1, r8
   13c7e:	f008 ee28 	blx	1c8d0 <get_node_from_cabinetindex@@Base+0xea8>
   13c82:	2800      	cmp	r0, #0
   13c84:	d14e      	bne.n	13d24 <Sound_Path_Connect@@Base+0x268>
   13c86:	4620      	mov	r0, r4
   13c88:	4639      	mov	r1, r7
   13c8a:	4632      	mov	r2, r6
   13c8c:	f009 e8c0 	blx	1ce10 <get_node_from_cabinetindex@@Base+0x13e8>
   13c90:	b918      	cbnz	r0, 13c9a <Sound_Path_Connect@@Base+0x1de>
   13c92:	980a      	ldr	r0, [sp, #40]	@ 0x28
   13c94:	3701      	adds	r7, #1
   13c96:	2800      	cmp	r0, #0
   13c98:	d1ed      	bne.n	13c76 <Sound_Path_Connect@@Base+0x1ba>
   13c9a:	a908      	add	r1, sp, #32
   13c9c:	4620      	mov	r0, r4
   13c9e:	f008 ed80 	blx	1c7a0 <get_node_from_cabinetindex@@Base+0xd78>
   13ca2:	2800      	cmp	r0, #0
   13ca4:	f47f af36 	bne.w	13b14 <Sound_Path_Connect@@Base+0x58>
   13ca8:	4e3c      	ldr	r6, [pc, #240]	@ (13d9c <Sound_Path_Connect@@Base+0x2e0>)
   13caa:	9808      	ldr	r0, [sp, #32]
   13cac:	447e      	add	r6, pc
   13cae:	6831      	ldr	r1, [r6, #0]
   13cb0:	4288      	cmp	r0, r1
   13cb2:	f4bf af2f 	bcs.w	13b14 <Sound_Path_Connect@@Base+0x58>
   13cb6:	f44f 75ac 	mov.w	r5, #344	@ 0x158
   13cba:	fb00 6005 	mla	r0, r0, r5, r6
   13cbe:	3004      	adds	r0, #4
   13cc0:	f008 eda6 	blx	1c810 <get_node_from_cabinetindex@@Base+0xde8>
   13cc4:	b930      	cbnz	r0, 13cd4 <Sound_Path_Connect@@Base+0x218>
   13cc6:	9808      	ldr	r0, [sp, #32]
   13cc8:	fb00 6005 	mla	r0, r0, r5, r6
   13ccc:	3004      	adds	r0, #4
   13cce:	f009 e8a8 	blx	1ce20 <get_node_from_cabinetindex@@Base+0x13f8>
   13cd2:	b390      	cbz	r0, 13d3a <Sound_Path_Connect@@Base+0x27e>
   13cd4:	f500 20c0 	add.w	r0, r0, #393216	@ 0x60000
   13cd8:	f500 5088 	add.w	r0, r0, #4352	@ 0x1100
   13cdc:	f500 7a00 	add.w	sl, r0, #512	@ 0x200
   13ce0:	e718      	b.n	13b14 <Sound_Path_Connect@@Base+0x58>
   13ce2:	4a29      	ldr	r2, [pc, #164]	@ (13d88 <Sound_Path_Connect@@Base+0x2cc>)
   13ce4:	4607      	mov	r7, r0
   13ce6:	447a      	add	r2, pc
   13ce8:	e002      	b.n	13cf0 <Sound_Path_Connect@@Base+0x234>
   13cea:	4a2a      	ldr	r2, [pc, #168]	@ (13d94 <Sound_Path_Connect@@Base+0x2d8>)
   13cec:	4607      	mov	r7, r0
   13cee:	447a      	add	r2, pc
   13cf0:	2003      	movs	r0, #3
   13cf2:	2100      	movs	r1, #0
   13cf4:	463b      	mov	r3, r7
   13cf6:	f008 ea34 	blx	1c160 <get_node_from_cabinetindex@@Base+0x738>
   13cfa:	f507 20c0 	add.w	r0, r7, #393216	@ 0x60000
   13cfe:	f500 5a88 	add.w	sl, r0, #4352	@ 0x1100
   13d02:	e707      	b.n	13b14 <Sound_Path_Connect@@Base+0x58>
   13d04:	4606      	mov	r6, r0
   13d06:	980a      	ldr	r0, [sp, #40]	@ 0x28
   13d08:	2100      	movs	r1, #0
   13d0a:	4633      	mov	r3, r6
   13d0c:	6840      	ldr	r0, [r0, #4]
   13d0e:	4a20      	ldr	r2, [pc, #128]	@ (13d90 <Sound_Path_Connect@@Base+0x2d4>)
   13d10:	9000      	str	r0, [sp, #0]
   13d12:	2003      	movs	r0, #3
   13d14:	447a      	add	r2, pc
   13d16:	f008 ea24 	blx	1c160 <get_node_from_cabinetindex@@Base+0x738>
   13d1a:	f506 20c0 	add.w	r0, r6, #393216	@ 0x60000
   13d1e:	f500 5aa4 	add.w	sl, r0, #5248	@ 0x1480
   13d22:	e6f7      	b.n	13b14 <Sound_Path_Connect@@Base+0x58>
   13d24:	4a1c      	ldr	r2, [pc, #112]	@ (13d98 <Sound_Path_Connect@@Base+0x2dc>)
   13d26:	2003      	movs	r0, #3
   13d28:	2100      	movs	r1, #0
   13d2a:	447a      	add	r2, pc
   13d2c:	f008 ea18 	blx	1c160 <get_node_from_cabinetindex@@Base+0x738>
   13d30:	f241 4a80 	movw	sl, #5248	@ 0x1480
   13d34:	f2c0 0a06 	movt	sl, #6
   13d38:	e6ec      	b.n	13b14 <Sound_Path_Connect@@Base+0x58>
   13d3a:	9808      	ldr	r0, [sp, #32]
   13d3c:	f44f 71ac 	mov.w	r1, #344	@ 0x158
   13d40:	9b06      	ldr	r3, [sp, #24]
   13d42:	f04f 0a00 	mov.w	sl, #0
   13d46:	fb00 6201 	mla	r2, r0, r1, r6
   13d4a:	2b00      	cmp	r3, #0
   13d4c:	4623      	mov	r3, r4
   13d4e:	f852 1f08 	ldr.w	r1, [r2, #8]!
   13d52:	bf04      	itt	eq
   13d54:	3101      	addeq	r1, #1
   13d56:	6011      	streq	r1, [r2, #0]
   13d58:	4a11      	ldr	r2, [pc, #68]	@ (13da0 <Sound_Path_Connect@@Base+0x2e4>)
   13d5a:	e9cd 0100 	strd	r0, r1, [sp]
   13d5e:	2003      	movs	r0, #3
   13d60:	447a      	add	r2, pc
   13d62:	2100      	movs	r1, #0
   13d64:	f008 e9fc 	blx	1c160 <get_node_from_cabinetindex@@Base+0x738>
   13d68:	e6d4      	b.n	13b14 <Sound_Path_Connect@@Base+0x58>
   13d6a:	bf00      	nop
   13d6c:	b210      	sxth	r0, r2
   13d6e:	0000      	movs	r0, r0
   13d70:	59ef      	ldr	r7, [r5, r7]
   13d72:	ffff de12 	vcvt.f32.u32	d29, d2, #1
   13d76:	0000      	movs	r0, r0
   13d78:	b190      	cbz	r0, 13da0 <Sound_Path_Connect@@Base+0x2e4>
   13d7a:	0000      	movs	r0, r0
   13d7c:	27bf      	movs	r7, #191	@ 0xbf
   13d7e:	ffff 23cb 			@ <UNDEFINED> instruction: 0xffff23cb
   13d82:	ffff 3b4c 	vtbx.8	d19, {d15-d18}, d12
   13d86:	ffff 55fd 	vsli.64	<illegal reg q10.5>, <illegal reg q14.5>, #63	@ 0x3f
   13d8a:	ffff 23ac 	vsubw.u<illegal width 64>	q9, <illegal reg q15.5>, d28
   13d8e:	ffff 4145 			@ <UNDEFINED> instruction: 0xffff4145
   13d92:	ffff 2f08 			@ <UNDEFINED> instruction: 0xffff2f08
   13d96:	ffff 4aea 	vtbx.8	d20, {d31-<overflow reg d33}, d26
   13d9a:	ffff d1dc 	vsra.u64	<illegal reg q14.5>, q6, #1
   13d9e:	0000      	movs	r0, r0
   13da0:	4d94      	ldr	r5, [pc, #592]	@ (13ff4 <Sound_PEQ_Init@@Base+0x34>)
   13da2:	Address 0x13da2 is out of bounds.

