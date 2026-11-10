
local/h713-lab/extracted/stock-super/vendor/lib/modules/snd_alsa_trid.ko:	file format elf32-littlearm

Disassembly of section .text:

000039b8 <audbrg_ostream_ConfigMemMap>:
    39b8: e92d47f3     	push	{r0, r1, r4, r5, r6, r7, r8, r9, r10, lr}
    39bc: e52de004     	str	lr, [sp, #-0x4]!
    39c0: ebfffffe     	bl	0x39c0 <audbrg_ostream_ConfigMemMap+0x8> @ imm = #-0x8
			000039c0:  R_ARM_CALL	__gnu_mcount_nc
    39c4: e59fa094     	ldr	r10, [pc, #0x94]        @ 0x3a60 <audbrg_ostream_ConfigMemMap+0xa8>
    39c8: e1a05001     	mov	r5, r1
    39cc: e1a06000     	mov	r6, r0
    39d0: e59f808c     	ldr	r8, [pc, #0x8c]         @ 0x3a64 <audbrg_ostream_ConfigMemMap+0xac>
    39d4: e1a03000     	mov	r3, r0
    39d8: e59f4088     	ldr	r4, [pc, #0x88]         @ 0x3a68 <audbrg_ostream_ConfigMemMap+0xb0>
    39dc: e1a0200a     	mov	r2, r10
    39e0: e58d1000     	str	r1, [sp]
    39e4: e3a0109b     	mov	r1, #155
    39e8: e59f007c     	ldr	r0, [pc, #0x7c]         @ 0x3a6c <audbrg_ostream_ConfigMemMap+0xb4>
    39ec: e3a09801     	mov	r9, #65536
    39f0: ebfffffe     	bl	0x39f0 <audbrg_ostream_ConfigMemMap+0x38> @ imm = #-0x8
			000039f0:  R_ARM_CALL	printk
    39f4: e2853cff     	add	r3, r5, #65280
    39f8: e0857009     	add	r7, r5, r9
    39fc: e5886000     	str	r6, [r8]
    3a00: e28330ff     	add	r3, r3, #255
    3a04: e0866009     	add	r6, r6, r9
    3a08: e5843008     	str	r3, [r4, #0x8]
    3a0c: e58d7000     	str	r7, [sp]
    3a10: e1a03006     	mov	r3, r6
    3a14: e1a0200a     	mov	r2, r10
    3a18: e3a010a6     	mov	r1, #166
    3a1c: e59f004c     	ldr	r0, [pc, #0x4c]         @ 0x3a70 <audbrg_ostream_ConfigMemMap+0xb8>
    3a20: e5845004     	str	r5, [r4, #0x4]
    3a24: e584900c     	str	r9, [r4, #0xc]
    3a28: e5845028     	str	r5, [r4, #0x28]
    3a2c: e584502c     	str	r5, [r4, #0x2c]
    3a30: ebfffffe     	bl	0x3a30 <audbrg_ostream_ConfigMemMap+0x78> @ imm = #-0x8
			00003a30:  R_ARM_CALL	printk
    3a34: e59f3038     	ldr	r3, [pc, #0x38]         @ 0x3a74 <audbrg_ostream_ConfigMemMap+0xbc>
    3a38: e3a00000     	mov	r0, #0
    3a3c: e5847048     	str	r7, [r4, #0x48]
    3a40: e5849050     	str	r9, [r4, #0x50]
    3a44: e0853003     	add	r3, r5, r3
    3a48: e584706c     	str	r7, [r4, #0x6c]
    3a4c: e584304c     	str	r3, [r4, #0x4c]
    3a50: e5847070     	str	r7, [r4, #0x70]
    3a54: e5886004     	str	r6, [r8, #0x4]
    3a58: e28dd008     	add	sp, sp, #8
    3a5c: e8bd87f0     	pop	{r4, r5, r6, r7, r8, r9, r10, pc}
    3a60: c4 05 00 00  	.word	0x000005c4
			00003a60:  R_ARM_ABS32	.rodata
    3a64: 64 00 00 00  	.word	0x00000064
			00003a64:  R_ARM_ABS32	.bss
    3a68: a8 04 00 00  	.word	0x000004a8
			00003a68:  R_ARM_ABS32	.data
    3a6c: 63 0c 00 00  	.word	0x00000c63
			00003a6c:  R_ARM_ABS32	.rodata.str1.1
    3a70: 98 0c 00 00  	.word	0x00000c98
			00003a70:  R_ARM_ABS32	.rodata.str1.1
    3a74: ff ff 01 00  	.word	0x0001ffff

00003a78 <AudIf_GetHandle_ostream>:
    3a78: e92d4010     	push	{r4, lr}
    3a7c: e52de004     	str	lr, [sp, #-0x4]!
    3a80: ebfffffe     	bl	0x3a80 <AudIf_GetHandle_ostream+0x8> @ imm = #-0x8
			00003a80:  R_ARM_CALL	__gnu_mcount_nc
    3a84: e3500002     	cmp	r0, #2
    3a88: 9a000003     	bls	0x3a9c <AudIf_GetHandle_ostream+0x24> @ imm = #0xc
    3a8c: e59f0018     	ldr	r0, [pc, #0x18]         @ 0x3aac <AudIf_GetHandle_ostream+0x34>
    3a90: ebfffffe     	bl	0x3a90 <AudIf_GetHandle_ostream+0x18> @ imm = #-0x8
			00003a90:  R_ARM_CALL	printk
    3a94: e3a00000     	mov	r0, #0
    3a98: e8bd8010     	pop	{r4, pc}
    3a9c: e59f300c     	ldr	r3, [pc, #0xc]          @ 0x3ab0 <AudIf_GetHandle_ostream+0x38>
    3aa0: e3a02044     	mov	r2, #68
    3aa4: e0203092     	mla	r0, r2, r0, r3
    3aa8: e8bd8010     	pop	{r4, pc}
    3aac: cd 0c 00 00  	.word	0x00000ccd
			00003aac:  R_ARM_ABS32	.rodata.str1.1
    3ab0: a8 04 00 00  	.word	0x000004a8
			00003ab0:  R_ARM_ABS32	.data

00003ab4 <audbrg_ostream_interrupt_clearstatus>:
    3ab4: e52de004     	str	lr, [sp, #-0x4]!
    3ab8: ebfffffe     	bl	0x3ab8 <audbrg_ostream_interrupt_clearstatus+0x4> @ imm = #-0x8
			00003ab8:  R_ARM_CALL	__gnu_mcount_nc
    3abc: e3a02001     	mov	r2, #1
    3ac0: e2800004     	add	r0, r0, #4
    3ac4: e1a02012     	lsl	r2, r2, r0
    3ac8: e59f0004     	ldr	r0, [pc, #0x4]          @ 0x3ad4 <audbrg_ostream_interrupt_clearstatus+0x20>
    3acc: e1a01002     	mov	r1, r2
    3ad0: eafffffe     	b	0x3ad0 <audbrg_ostream_interrupt_clearstatus+0x1c> @ imm = #-0x8
			00003ad0:  R_ARM_JUMP24	REG_Write_Mask
    3ad4: 8c 83 14 06  	.word	0x0614838c

00003ad8 <audbrg_ostream_interrupt_enable>:
    3ad8: e92d4010     	push	{r4, lr}
    3adc: e52de004     	str	lr, [sp, #-0x4]!
    3ae0: ebfffffe     	bl	0x3ae0 <audbrg_ostream_interrupt_enable+0x8> @ imm = #-0x8
			00003ae0:  R_ARM_CALL	__gnu_mcount_nc
    3ae4: e3510000     	cmp	r1, #0
    3ae8: e2803004     	add	r3, r0, #4
    3aec: 13a01001     	movne	r1, #1
    3af0: e3a02001     	mov	r2, #1
    3af4: e1a04000     	mov	r4, r0
    3af8: 11a01311     	lslne	r1, r1, r3
    3afc: e59f0010     	ldr	r0, [pc, #0x10]         @ 0x3b14 <audbrg_ostream_interrupt_enable+0x3c>
    3b00: e1a02312     	lsl	r2, r2, r3
    3b04: ebfffffe     	bl	0x3b04 <audbrg_ostream_interrupt_enable+0x2c> @ imm = #-0x8
			00003b04:  R_ARM_CALL	REG_Write_Mask
    3b08: e1a00004     	mov	r0, r4
    3b0c: e8bd4010     	pop	{r4, lr}
    3b10: eafffffe     	b	0x3b10 <audbrg_ostream_interrupt_enable+0x38> @ imm = #-0x8
			00003b10:  R_ARM_JUMP24	audbrg_ostream_interrupt_clearstatus
    3b14: 88 83 14 06  	.word	0x06148388

00003b18 <audbrg_ostream_flush>:
    3b18: e92d4070     	push	{r4, r5, r6, lr}
    3b1c: e52de004     	str	lr, [sp, #-0x4]!
    3b20: ebfffffe     	bl	0x3b20 <audbrg_ostream_flush+0x8> @ imm = #-0x8
			00003b20:  R_ARM_CALL	__gnu_mcount_nc
    3b24: e59f4074     	ldr	r4, [pc, #0x74]         @ 0x3ba0 <audbrg_ostream_flush+0x88>
    3b28: e1a03300     	lsl	r3, r0, #6
    3b2c: e3a02001     	mov	r2, #1
    3b30: e1a01002     	mov	r1, r2
    3b34: e0834004     	add	r4, r3, r4
    3b38: e1a05000     	mov	r5, r0
    3b3c: e1a00004     	mov	r0, r4
    3b40: ebfffffe     	bl	0x3b40 <audbrg_ostream_flush+0x28> @ imm = #-0x8
			00003b40:  R_ARM_CALL	REG_Write_Mask
    3b44: e3a02001     	mov	r2, #1
    3b48: e3a01000     	mov	r1, #0
    3b4c: e1a00004     	mov	r0, r4
    3b50: ebfffffe     	bl	0x3b50 <audbrg_ostream_flush+0x38> @ imm = #-0x8
			00003b50:  R_ARM_CALL	REG_Write_Mask
    3b54: e3a00044     	mov	r0, #68
    3b58: e59f3044     	ldr	r3, [pc, #0x44]         @ 0x3ba4 <audbrg_ostream_flush+0x8c>
    3b5c: e0000590     	mul	r0, r0, r5
    3b60: e0832000     	add	r2, r3, r0
    3b64: e5921004     	ldr	r1, [r2, #0x4]
    3b68: e582102c     	str	r1, [r2, #0x2c]
    3b6c: e5821028     	str	r1, [r2, #0x28]
    3b70: e2802030     	add	r2, r0, #48
    3b74: e2800040     	add	r0, r0, #64
    3b78: e0832002     	add	r2, r3, r2
    3b7c: e0830000     	add	r0, r3, r0
    3b80: e5b23004     	ldr	r3, [r2, #0x4]!
    3b84: e3530000     	cmp	r3, #0
    3b88: 15931000     	ldrne	r1, [r3]
    3b8c: 1583100c     	strne	r1, [r3, #0xc]
    3b90: 15831008     	strne	r1, [r3, #0x8]
    3b94: e1520000     	cmp	r2, r0
    3b98: 1afffff8     	bne	0x3b80 <audbrg_ostream_flush+0x68> @ imm = #-0x20
    3b9c: e8bd8070     	pop	{r4, r5, r6, pc}
    3ba0: 14 81 14 06  	.word	0x06148114
    3ba4: a8 04 00 00  	.word	0x000004a8
			00003ba4:  R_ARM_ABS32	.data

00003ba8 <audbrg_ostream_config>:
    3ba8: e92d47f0     	push	{r4, r5, r6, r7, r8, r9, r10, lr}
    3bac: e52de004     	str	lr, [sp, #-0x4]!
    3bb0: ebfffffe     	bl	0x3bb0 <audbrg_ostream_config+0x8> @ imm = #-0x8
			00003bb0:  R_ARM_CALL	__gnu_mcount_nc
    3bb4: e3500000     	cmp	r0, #0
    3bb8: e59dc020     	ldr	r12, [sp, #0x20]
    3bbc: e59de024     	ldr	lr, [sp, #0x24]
    3bc0: 0a000038     	beq	0x3ca8 <audbrg_ostream_config+0x100> @ imm = #0xe0
    3bc4: e2414001     	sub	r4, r1, #1
    3bc8: e3540003     	cmp	r4, #3
    3bcc: 8a000035     	bhi	0x3ca8 <audbrg_ostream_config+0x100> @ imm = #0xd4
    3bd0: e35c0000     	cmp	r12, #0
    3bd4: e1a08003     	mov	r8, r3
    3bd8: 03a0cb03     	moveq	r12, #3072
    3bdc: e35e0002     	cmp	lr, #2
    3be0: e580c010     	str	r12, [r0, #0x10]
    3be4: 83a0c000     	movhi	r12, #0
    3be8: 9580e020     	strls	lr, [r0, #0x20]
    3bec: e1a06000     	mov	r6, r0
    3bf0: 8580c020     	strhi	r12, [r0, #0x20]
    3bf4: e5904020     	ldr	r4, [r0, #0x20]
    3bf8: e5903014     	ldr	r3, [r0, #0x14]
    3bfc: e5907000     	ldr	r7, [r0]
    3c00: e59f90a8     	ldr	r9, [pc, #0xa8]         @ 0x3cb0 <audbrg_ostream_config+0x108>
    3c04: e1a04604     	lsl	r4, r4, #12
    3c08: e5801018     	str	r1, [r0, #0x18]
    3c0c: e59f50a0     	ldr	r5, [pc, #0xa0]         @ 0x3cb4 <audbrg_ostream_config+0x10c>
    3c10: e1844223     	orr	r4, r4, r3, lsr #4
    3c14: e580201c     	str	r2, [r0, #0x1c]
    3c18: e59f0098     	ldr	r0, [pc, #0x98]         @ 0x3cb8 <audbrg_ostream_config+0x110>
    3c1c: e1844582     	orr	r4, r4, r2, lsl #11
    3c20: e3a020f0     	mov	r2, #240
    3c24: e0875005     	add	r5, r7, r5
    3c28: e1844401     	orr	r4, r4, r1, lsl #8
    3c2c: e7991107     	ldr	r1, [r9, r7, lsl #2]
    3c30: e1a05305     	lsl	r5, r5, #6
    3c34: e1a01e21     	lsr	r1, r1, #28
    3c38: e1a01201     	lsl	r1, r1, #4
    3c3c: ebfffffe     	bl	0x3c3c <audbrg_ostream_config+0x94> @ imm = #-0x8
			00003c3c:  R_ARM_CALL	REG_Write_Mask
    3c40: e7991107     	ldr	r1, [r9, r7, lsl #2]
    3c44: e1a00005     	mov	r0, r5
    3c48: e7f71251     	ubfx	r1, r1, #0x4, #0x18
    3c4c: ebfffffe     	bl	0x3c4c <audbrg_ostream_config+0xa4> @ imm = #-0x8
			00003c4c:  R_ARM_CALL	REG_Write
    3c50: e596100c     	ldr	r1, [r6, #0xc]
    3c54: e2850004     	add	r0, r5, #4
    3c58: e7993107     	ldr	r3, [r9, r7, lsl #2]
    3c5c: e2411001     	sub	r1, r1, #1
    3c60: e0811003     	add	r1, r1, r3
    3c64: e7f71251     	ubfx	r1, r1, #0x4, #0x18
    3c68: ebfffffe     	bl	0x3c68 <audbrg_ostream_config+0xc0> @ imm = #-0x8
			00003c68:  R_ARM_CALL	REG_Write
    3c6c: e5961010     	ldr	r1, [r6, #0x10]
    3c70: e285000c     	add	r0, r5, #12
    3c74: e1a01221     	lsr	r1, r1, #4
    3c78: ebfffffe     	bl	0x3c78 <audbrg_ostream_config+0xd0> @ imm = #-0x8
			00003c78:  R_ARM_CALL	REG_Write
    3c7c: e1a01004     	mov	r1, r4
    3c80: e2850010     	add	r0, r5, #16
    3c84: ebfffffe     	bl	0x3c84 <audbrg_ostream_config+0xdc> @ imm = #-0x8
			00003c84:  R_ARM_CALL	REG_Write
    3c88: e3a01000     	mov	r1, #0
    3c8c: e59f0028     	ldr	r0, [pc, #0x28]         @ 0x3cbc <audbrg_ostream_config+0x114>
    3c90: ebfffffe     	bl	0x3c90 <audbrg_ostream_config+0xe8> @ imm = #-0x8
			00003c90:  R_ARM_CALL	REG_Write
    3c94: e1a00007     	mov	r0, r7
    3c98: e1a01008     	mov	r1, r8
    3c9c: ebfffffe     	bl	0x3c9c <audbrg_ostream_config+0xf4> @ imm = #-0x8
			00003c9c:  R_ARM_CALL	audbrg_ostream_interrupt_enable
    3ca0: e3a00000     	mov	r0, #0
    3ca4: e8bd87f0     	pop	{r4, r5, r6, r7, r8, r9, r10, pc}
    3ca8: e3a00001     	mov	r0, #1
    3cac: e8bd87f0     	pop	{r4, r5, r6, r7, r8, r9, r10, pc}
    3cb0: 64 00 00 00  	.word	0x00000064
			00003cb0:  R_ARM_ABS32	.bss
    3cb4: 04 52 18 00  	.word	0x00185204
    3cb8: 44 20 14 06  	.word	0x06142044
    3cbc: 90 83 14 06  	.word	0x06148390

00003cc0 <audbrg_ostream_start>:
    3cc0: e92d4070     	push	{r4, r5, r6, lr}
    3cc4: e52de004     	str	lr, [sp, #-0x4]!
    3cc8: ebfffffe     	bl	0x3cc8 <audbrg_ostream_start+0x8> @ imm = #-0x8
			00003cc8:  R_ARM_CALL	__gnu_mcount_nc
    3ccc: e3500000     	cmp	r0, #0
    3cd0: 0a000017     	beq	0x3d34 <audbrg_ostream_start+0x74> @ imm = #0x5c
    3cd4: e5904030     	ldr	r4, [r0, #0x30]
    3cd8: e3540000     	cmp	r4, #0
    3cdc: 1a000016     	bne	0x3d3c <audbrg_ostream_start+0x7c> @ imm = #0x58
    3ce0: e5905000     	ldr	r5, [r0]
    3ce4: e1a06000     	mov	r6, r0
    3ce8: e1a00005     	mov	r0, r5
    3cec: ebfffffe     	bl	0x3cec <audbrg_ostream_start+0x2c> @ imm = #-0x8
			00003cec:  R_ARM_CALL	audbrg_ostream_flush
    3cf0: e59f304c     	ldr	r3, [pc, #0x4c]         @ 0x3d44 <audbrg_ostream_start+0x84>
    3cf4: e3a02024     	mov	r2, #36
    3cf8: e1a01004     	mov	r1, r4
    3cfc: e0233592     	mla	r3, r2, r5, r3
    3d00: e593008c     	ldr	r0, [r3, #0x8c]
    3d04: e58340a0     	str	r4, [r3, #0xa0]
    3d08: e58340a4     	str	r4, [r3, #0xa4]
    3d0c: e5830094     	str	r0, [r3, #0x94]
    3d10: e5830098     	str	r0, [r3, #0x98]
    3d14: e583409c     	str	r4, [r3, #0x9c]
    3d18: e5932090     	ldr	r2, [r3, #0x90]
    3d1c: e2400481     	sub	r0, r0, #-2130706432
    3d20: ebfffffe     	bl	0x3d20 <audbrg_ostream_start+0x60> @ imm = #-0x8
			00003d20:  R_ARM_CALL	memset
    3d24: e3a03001     	mov	r3, #1
    3d28: e1a00004     	mov	r0, r4
    3d2c: e5863030     	str	r3, [r6, #0x30]
    3d30: e8bd8070     	pop	{r4, r5, r6, pc}
    3d34: e3a00001     	mov	r0, #1
    3d38: e8bd8070     	pop	{r4, r5, r6, pc}
    3d3c: e3a00000     	mov	r0, #0
    3d40: e8bd8070     	pop	{r4, r5, r6, pc}
    3d44: a8 04 00 00  	.word	0x000004a8
			00003d44:  R_ARM_ABS32	.data
