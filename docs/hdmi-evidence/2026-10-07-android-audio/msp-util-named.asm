
docs/hdmi-evidence/2026-10-07-android-audio/libmsp_util.so:     file format elf32-littlearm


Disassembly of section .text:

00002af0 <BH_AUD_Init@@Base-0x12>:
    2af0:	44784801 	ldrbtmi	r4, [r8], #-2049	@ 0xfffff7ff
    2af4:	bf4cf000 	svclt	0x004cf000
    2af8:	00001f3a 	andeq	r1, r0, sl, lsr pc
    2afc:	f7ff4770 			@ <UNDEFINED> instruction: 0xf7ff4770
    2b00:	Address 0x2b00 is out of bounds.


00002b02 <BH_AUD_Init@@Base>:
    2b02:	2000      	movs	r0, #0
    2b04:	4770      	bx	lr

00002b06 <BH_AUD_Uninit@@Base>:
    2b06:	2000      	movs	r0, #0
    2b08:	4770      	bx	lr
    2b0a:	d4d4      	bmi.n	2ab6 <BH_AUD_Init@@Base-0x4c>

00002b0c <BH_AUD_DoAction@@Base>:
    2b0c:	b5b0      	push	{r4, r5, r7, lr}
    2b0e:	b084      	sub	sp, #16
    2b10:	b1e0      	cbz	r0, 2b4c <BH_AUD_DoAction@@Base+0x40>
    2b12:	6845      	ldr	r5, [r0, #4]
    2b14:	4b44      	ldr	r3, [pc, #272]	@ (2c28 <BH_AUD_DoAction@@Base+0x11c>)
    2b16:	447b      	add	r3, pc
    2b18:	f3c5 2407 	ubfx	r4, r5, #8, #8
    2b1c:	f853 2024 	ldr.w	r2, [r3, r4, lsl #2]
    2b20:	eb03 0384 	add.w	r3, r3, r4, lsl #2
    2b24:	685b      	ldr	r3, [r3, #4]
    2b26:	429a      	cmp	r2, r3
    2b28:	da4f      	bge.n	2bca <BH_AUD_DoAction@@Base+0xbe>
    2b2a:	4c40      	ldr	r4, [pc, #256]	@ (2c2c <BH_AUD_DoAction@@Base+0x120>)
    2b2c:	468e      	mov	lr, r1
    2b2e:	447c      	add	r4, pc
    2b30:	f8d4 c000 	ldr.w	ip, [r4]
    2b34:	eb02 0442 	add.w	r4, r2, r2, lsl #1
    2b38:	eb0c 0484 	add.w	r4, ip, r4, lsl #2
    2b3c:	6821      	ldr	r1, [r4, #0]
    2b3e:	42a9      	cmp	r1, r5
    2b40:	d007      	beq.n	2b52 <BH_AUD_DoAction@@Base+0x46>
    2b42:	3201      	adds	r2, #1
    2b44:	340c      	adds	r4, #12
    2b46:	429a      	cmp	r2, r3
    2b48:	dbf8      	blt.n	2b3c <BH_AUD_DoAction@@Base+0x30>
    2b4a:	e03e      	b.n	2bca <BH_AUD_DoAction@@Base+0xbe>
    2b4c:	2002      	movs	r0, #2
    2b4e:	b004      	add	sp, #16
    2b50:	bdb0      	pop	{r4, r5, r7, pc}
    2b52:	6862      	ldr	r2, [r4, #4]
    2b54:	f002 010f 	and.w	r1, r2, #15
    2b58:	f3c2 1303 	ubfx	r3, r2, #4, #4
    2b5c:	4419      	add	r1, r3
    2b5e:	2b00      	cmp	r3, #0
    2b60:	bf1e      	ittt	ne
    2b62:	f3c2 2303 	ubfxne	r3, r2, #8, #4
    2b66:	4419      	addne	r1, r3
    2b68:	2b00      	cmpne	r3, #0
    2b6a:	d014      	beq.n	2b96 <BH_AUD_DoAction@@Base+0x8a>
    2b6c:	f3c2 3303 	ubfx	r3, r2, #12, #4
    2b70:	4419      	add	r1, r3
    2b72:	b183      	cbz	r3, 2b96 <BH_AUD_DoAction@@Base+0x8a>
    2b74:	f3c2 4303 	ubfx	r3, r2, #16, #4
    2b78:	4419      	add	r1, r3
    2b7a:	2b00      	cmp	r3, #0
    2b7c:	bf1e      	ittt	ne
    2b7e:	f3c2 5303 	ubfxne	r3, r2, #20, #4
    2b82:	4419      	addne	r1, r3
    2b84:	2b00      	cmpne	r3, #0
    2b86:	d006      	beq.n	2b96 <BH_AUD_DoAction@@Base+0x8a>
    2b88:	f3c2 6303 	ubfx	r3, r2, #24, #4
    2b8c:	4419      	add	r1, r3
    2b8e:	2b00      	cmp	r3, #0
    2b90:	bf18      	it	ne
    2b92:	eb01 7112 	addne.w	r1, r1, r2, lsr #28
    2b96:	6882      	ldr	r2, [r0, #8]
    2b98:	4291      	cmp	r1, r2
    2b9a:	bf18      	it	ne
    2b9c:	2400      	movne	r4, #0
    2b9e:	d114      	bne.n	2bca <BH_AUD_DoAction@@Base+0xbe>
    2ba0:	6861      	ldr	r1, [r4, #4]
    2ba2:	2950      	cmp	r1, #80	@ 0x50
    2ba4:	dd14      	ble.n	2bd0 <BH_AUD_DoAction@@Base+0xc4>
    2ba6:	2951      	cmp	r1, #81	@ 0x51
    2ba8:	d01d      	beq.n	2be6 <BH_AUD_DoAction@@Base+0xda>
    2baa:	f240 1211 	movw	r2, #273	@ 0x111
    2bae:	4291      	cmp	r1, r2
    2bb0:	d025      	beq.n	2bfe <BH_AUD_DoAction@@Base+0xf2>
    2bb2:	f241 1211 	movw	r2, #4369	@ 0x1111
    2bb6:	4291      	cmp	r1, r2
    2bb8:	d132      	bne.n	2c20 <BH_AUD_DoAction@@Base+0x114>
    2bba:	e9d0 c103 	ldrd	ip, r1, [r0, #12]
    2bbe:	e9d0 2305 	ldrd	r2, r3, [r0, #20]
    2bc2:	68a4      	ldr	r4, [r4, #8]
    2bc4:	f8cd e000 	str.w	lr, [sp]
    2bc8:	e01e      	b.n	2c08 <BH_AUD_DoAction@@Base+0xfc>
    2bca:	2004      	movs	r0, #4
    2bcc:	b004      	add	sp, #16
    2bce:	bdb0      	pop	{r4, r5, r7, pc}
    2bd0:	2901      	cmp	r1, #1
    2bd2:	d01c      	beq.n	2c0e <BH_AUD_DoAction@@Base+0x102>
    2bd4:	2911      	cmp	r1, #17
    2bd6:	d123      	bne.n	2c20 <BH_AUD_DoAction@@Base+0x114>
    2bd8:	e9d0 2103 	ldrd	r2, r1, [r0, #12]
    2bdc:	68a3      	ldr	r3, [r4, #8]
    2bde:	4610      	mov	r0, r2
    2be0:	4672      	mov	r2, lr
    2be2:	4798      	blx	r3
    2be4:	e017      	b.n	2c16 <BH_AUD_DoAction@@Base+0x10a>
    2be6:	f100 0514 	add.w	r5, r0, #20
    2bea:	e9d0 c103 	ldrd	ip, r1, [r0, #12]
    2bee:	6a00      	ldr	r0, [r0, #32]
    2bf0:	68a4      	ldr	r4, [r4, #8]
    2bf2:	cd2c      	ldmia	r5, {r2, r3, r5}
    2bf4:	e9cd 5000 	strd	r5, r0, [sp]
    2bf8:	f8cd e008 	str.w	lr, [sp, #8]
    2bfc:	e004      	b.n	2c08 <BH_AUD_DoAction@@Base+0xfc>
    2bfe:	e9d0 c103 	ldrd	ip, r1, [r0, #12]
    2c02:	4673      	mov	r3, lr
    2c04:	6942      	ldr	r2, [r0, #20]
    2c06:	68a4      	ldr	r4, [r4, #8]
    2c08:	4660      	mov	r0, ip
    2c0a:	47a0      	blx	r4
    2c0c:	e003      	b.n	2c16 <BH_AUD_DoAction@@Base+0x10a>
    2c0e:	68c0      	ldr	r0, [r0, #12]
    2c10:	4671      	mov	r1, lr
    2c12:	68a2      	ldr	r2, [r4, #8]
    2c14:	4790      	blx	r2
    2c16:	2800      	cmp	r0, #0
    2c18:	bf1e      	ittt	ne
    2c1a:	2007      	movne	r0, #7
    2c1c:	b004      	addne	sp, #16
    2c1e:	bdb0      	popne	{r4, r5, r7, pc}
    2c20:	2000      	movs	r0, #0
    2c22:	b004      	add	sp, #16
    2c24:	bdb0      	pop	{r4, r5, r7, pc}
    2c26:	bf00      	nop
    2c28:	ee22 ffff 	mcr	15, 1, pc, cr2, cr15, {7}	@ <UNPREDICTABLE>
    2c2c:	2346      	movs	r3, #70	@ 0x46
	...

00002c30 <BH_AUD_DoConnect@@Base>:
    2c30:	b580      	push	{r7, lr}
    2c32:	b082      	sub	sp, #8
    2c34:	b140      	cbz	r0, 2c48 <BH_AUD_DoConnect@@Base+0x18>
    2c36:	6803      	ldr	r3, [r0, #0]
    2c38:	b149      	cbz	r1, 2c4e <BH_AUD_DoConnect@@Base+0x1e>
    2c3a:	2b01      	cmp	r3, #1
    2c3c:	d014      	beq.n	2c68 <BH_AUD_DoConnect@@Base+0x38>
    2c3e:	b983      	cbnz	r3, 2c62 <BH_AUD_DoConnect@@Base+0x32>
    2c40:	68c0      	ldr	r0, [r0, #12]
    2c42:	f44f 4103 	mov.w	r1, #33536	@ 0x8300
    2c46:	e007      	b.n	2c58 <BH_AUD_DoConnect@@Base+0x28>
    2c48:	2002      	movs	r0, #2
    2c4a:	b002      	add	sp, #8
    2c4c:	bd80      	pop	{r7, pc}
    2c4e:	2b01      	cmp	r3, #1
    2c50:	d012      	beq.n	2c78 <BH_AUD_DoConnect@@Base+0x48>
    2c52:	b933      	cbnz	r3, 2c62 <BH_AUD_DoConnect@@Base+0x32>
    2c54:	6841      	ldr	r1, [r0, #4]
    2c56:	68c0      	ldr	r0, [r0, #12]
    2c58:	b002      	add	sp, #8
    2c5a:	e8bd 4080 	ldmia.w	sp!, {r7, lr}
    2c5e:	f000 be9d 	b.w	399c <BP_AUD_GetYBinByIndicator@@Base+0x80>
    2c62:	2005      	movs	r0, #5
    2c64:	b002      	add	sp, #8
    2c66:	bd80      	pop	{r7, pc}
    2c68:	e9d0 3c02 	ldrd	r3, ip, [r0, #8]
    2c6c:	6901      	ldr	r1, [r0, #16]
    2c6e:	4660      	mov	r0, ip
    2c70:	9200      	str	r2, [sp, #0]
    2c72:	f44f 4203 	mov.w	r2, #33536	@ 0x8300
    2c76:	e006      	b.n	2c86 <BH_AUD_DoConnect@@Base+0x56>
    2c78:	e9d0 c301 	ldrd	ip, r3, [r0, #4]
    2c7c:	e9d0 e103 	ldrd	lr, r1, [r0, #12]
    2c80:	9200      	str	r2, [sp, #0]
    2c82:	4662      	mov	r2, ip
    2c84:	4670      	mov	r0, lr
    2c86:	f000 eeb4 	blx	39f0 <MAPI_AUD_SetSourceSelectPort>
    2c8a:	b002      	add	sp, #8
    2c8c:	bd80      	pop	{r7, pc}
    2c8e:	d4d4      	bmi.n	2c3a <BH_AUD_DoConnect@@Base+0xa>

00002c90 <BP_AUD_GetPresetVersion@@Base>:
    2c90:	2800      	cmp	r0, #0
    2c92:	bf04      	itt	eq
    2c94:	2001      	moveq	r0, #1
    2c96:	4770      	bxeq	lr
    2c98:	4905      	ldr	r1, [pc, #20]	@ (2cb0 <BP_AUD_GetPresetVersion@@Base+0x20>)
    2c9a:	4479      	add	r1, pc
    2c9c:	69ca      	ldr	r2, [r1, #28]
    2c9e:	2a01      	cmp	r2, #1
    2ca0:	bf1c      	itt	ne
    2ca2:	2011      	movne	r0, #17
    2ca4:	4770      	bxne	lr
    2ca6:	6809      	ldr	r1, [r1, #0]
    2ca8:	68c9      	ldr	r1, [r1, #12]
    2caa:	6001      	str	r1, [r0, #0]
    2cac:	2000      	movs	r0, #0
    2cae:	4770      	bx	lr
    2cb0:	320a      	adds	r2, #10
	...

00002cb4 <BP_AUD_GetFullVersion@@Base>:
    2cb4:	b5f0      	push	{r4, r5, r6, r7, lr}
    2cb6:	b083      	sub	sp, #12
    2cb8:	4604      	mov	r4, r0
    2cba:	480f      	ldr	r0, [pc, #60]	@ (2cf8 <BP_AUD_GetFullVersion@@Base+0x44>)
    2cbc:	4f0f      	ldr	r7, [pc, #60]	@ (2cfc <BP_AUD_GetFullVersion@@Base+0x48>)
    2cbe:	2522      	movs	r5, #34	@ 0x22
    2cc0:	4478      	add	r0, pc
    2cc2:	447f      	add	r7, pc
    2cc4:	6800      	ldr	r0, [r0, #0]
    2cc6:	6839      	ldr	r1, [r7, #0]
    2cc8:	4a0d      	ldr	r2, [pc, #52]	@ (2d00 <BP_AUD_GetFullVersion@@Base+0x4c>)
    2cca:	4b0e      	ldr	r3, [pc, #56]	@ (2d04 <BP_AUD_GetFullVersion@@Base+0x50>)
    2ccc:	312c      	adds	r1, #44	@ 0x2c
    2cce:	6800      	ldr	r0, [r0, #0]
    2cd0:	447a      	add	r2, pc
    2cd2:	4e0d      	ldr	r6, [pc, #52]	@ (2d08 <BP_AUD_GetFullVersion@@Base+0x54>)
    2cd4:	447b      	add	r3, pc
    2cd6:	447e      	add	r6, pc
    2cd8:	e9cd 5600 	strd	r5, r6, [sp]
    2cdc:	9102      	str	r1, [sp, #8]
    2cde:	2101      	movs	r1, #1
    2ce0:	f000 ee8e 	blx	3a00 <trid_debug_log>
    2ce4:	2c00      	cmp	r4, #0
    2ce6:	bf1f      	itttt	ne
    2ce8:	6838      	ldrne	r0, [r7, #0]
    2cea:	6ac1      	ldrne	r1, [r0, #44]	@ 0x2c
    2cec:	6b00      	ldrne	r0, [r0, #48]	@ 0x30
    2cee:	6060      	strne	r0, [r4, #4]
    2cf0:	bf18      	it	ne
    2cf2:	6021      	strne	r1, [r4, #0]
    2cf4:	b003      	add	sp, #12
    2cf6:	bdf0      	pop	{r4, r5, r6, r7, pc}
    2cf8:	21b8      	movs	r1, #184	@ 0xb8
    2cfa:	0000      	movs	r0, r0
    2cfc:	31e2      	adds	r1, #226	@ 0xe2
    2cfe:	0000      	movs	r0, r0
    2d00:	ecde ffff 	ldcl	15, cr15, [lr], {255}	@ 0xff
    2d04:	ed73 ffff 	ldcl	15, cr15, [r3, #-1020]!	@ 0xfffffc04
    2d08:	ed87 ffff 	stc	15, cr15, [r7, #1020]	@ 0x3fc

00002d0c <BP_AUD_Init@@Base>:
    2d0c:	e92d 4ff0 	stmdb	sp!, {r4, r5, r6, r7, r8, r9, sl, fp, lr}
    2d10:	b087      	sub	sp, #28
    2d12:	4c87      	ldr	r4, [pc, #540]	@ (2f30 <BP_AUD_Init@@Base+0x224>)
    2d14:	2200      	movs	r2, #0
    2d16:	2501      	movs	r5, #1
    2d18:	447c      	add	r4, pc
    2d1a:	61e2      	str	r2, [r4, #28]
    2d1c:	b330      	cbz	r0, 2d6c <BP_AUD_Init@@Base+0x60>
    2d1e:	2901      	cmp	r1, #1
    2d20:	db24      	blt.n	2d6c <BP_AUD_Init@@Base+0x60>
    2d22:	6a82      	ldr	r2, [r0, #40]	@ 0x28
    2d24:	e9d0 5607 	ldrd	r5, r6, [r0, #28]
    2d28:	e9d0 3705 	ldrd	r3, r7, [r0, #20]
    2d2c:	eb00 0902 	add.w	r9, r0, r2
    2d30:	9406      	str	r4, [sp, #24]
    2d32:	4405      	add	r5, r0
    2d34:	6a44      	ldr	r4, [r0, #36]	@ 0x24
    2d36:	eb00 0b03 	add.w	fp, r0, r3
    2d3a:	9a06      	ldr	r2, [sp, #24]
    2d3c:	4406      	add	r6, r0
    2d3e:	4404      	add	r4, r0
    2d40:	eb00 0807 	add.w	r8, r0, r7
    2d44:	e9c2 0b00 	strd	r0, fp, [r2]
    2d48:	e9c2 8502 	strd	r8, r5, [r2, #8]
    2d4c:	e9c2 6404 	strd	r6, r4, [r2, #16]
    2d50:	f8c2 9018 	str.w	r9, [r2, #24]
    2d54:	6902      	ldr	r2, [r0, #16]
    2d56:	428a      	cmp	r2, r1
    2d58:	d107      	bne.n	2d6a <BP_AUD_Init@@Base+0x5e>
    2d5a:	4976      	ldr	r1, [pc, #472]	@ (2f34 <BP_AUD_Init@@Base+0x228>)
    2d5c:	2208      	movs	r2, #8
    2d5e:	4479      	add	r1, pc
    2d60:	f000 ee56 	blx	3a10 <strncmp>
    2d64:	b130      	cbz	r0, 2d74 <BP_AUD_Init@@Base+0x68>
    2d66:	2502      	movs	r5, #2
    2d68:	e000      	b.n	2d6c <BP_AUD_Init@@Base+0x60>
    2d6a:	2510      	movs	r5, #16
    2d6c:	4628      	mov	r0, r5
    2d6e:	b007      	add	sp, #28
    2d70:	e8bd 8ff0 	ldmia.w	sp!, {r4, r5, r6, r7, r8, r9, sl, fp, pc}
    2d74:	4970      	ldr	r1, [pc, #448]	@ (2f38 <BP_AUD_Init@@Base+0x22c>)
    2d76:	4658      	mov	r0, fp
    2d78:	2204      	movs	r2, #4
    2d7a:	4479      	add	r1, pc
    2d7c:	f000 ee48 	blx	3a10 <strncmp>
    2d80:	b108      	cbz	r0, 2d86 <BP_AUD_Init@@Base+0x7a>
    2d82:	2503      	movs	r5, #3
    2d84:	e7f2      	b.n	2d6c <BP_AUD_Init@@Base+0x60>
    2d86:	f10b 0208 	add.w	r2, fp, #8
    2d8a:	9605      	str	r6, [sp, #20]
    2d8c:	e9cd 9503 	strd	r9, r5, [sp, #12]
    2d90:	ca07      	ldmia	r2, {r0, r1, r2}
    2d92:	4408      	add	r0, r1
    2d94:	eb00 0902 	add.w	r9, r0, r2
    2d98:	f1b9 0f01 	cmp.w	r9, #1
    2d9c:	db12      	blt.n	2dc4 <BP_AUD_Init@@Base+0xb8>
    2d9e:	4f67      	ldr	r7, [pc, #412]	@ (2f3c <BP_AUD_Init@@Base+0x230>)
    2da0:	f10b 0a14 	add.w	sl, fp, #20
    2da4:	2504      	movs	r5, #4
    2da6:	447f      	add	r7, pc
    2da8:	f8da 0000 	ldr.w	r0, [sl]
    2dac:	4639      	mov	r1, r7
    2dae:	2204      	movs	r2, #4
    2db0:	4458      	add	r0, fp
    2db2:	f000 ee2e 	blx	3a10 <strncmp>
    2db6:	2800      	cmp	r0, #0
    2db8:	d1d8      	bne.n	2d6c <BP_AUD_Init@@Base+0x60>
    2dba:	f10a 0a04 	add.w	sl, sl, #4
    2dbe:	f1b9 0901 	subs.w	r9, r9, #1
    2dc2:	d1f1      	bne.n	2da8 <BP_AUD_Init@@Base+0x9c>
    2dc4:	495e      	ldr	r1, [pc, #376]	@ (2f40 <BP_AUD_Init@@Base+0x234>)
    2dc6:	4640      	mov	r0, r8
    2dc8:	2204      	movs	r2, #4
    2dca:	4479      	add	r1, pc
    2dcc:	f000 ee20 	blx	3a10 <strncmp>
    2dd0:	b108      	cbz	r0, 2dd6 <BP_AUD_Init@@Base+0xca>
    2dd2:	2505      	movs	r5, #5
    2dd4:	e7ca      	b.n	2d6c <BP_AUD_Init@@Base+0x60>
    2dd6:	f8d8 0010 	ldr.w	r0, [r8, #16]
    2dda:	2204      	movs	r2, #4
    2ddc:	4959      	ldr	r1, [pc, #356]	@ (2f44 <BP_AUD_Init@@Base+0x238>)
    2dde:	4440      	add	r0, r8
    2de0:	4479      	add	r1, pc
    2de2:	f000 ee16 	blx	3a10 <strncmp>
    2de6:	b108      	cbz	r0, 2dec <BP_AUD_Init@@Base+0xe0>
    2de8:	2506      	movs	r5, #6
    2dea:	e7bf      	b.n	2d6c <BP_AUD_Init@@Base+0x60>
    2dec:	f8d8 600c 	ldr.w	r6, [r8, #12]
    2df0:	e9dd a904 	ldrd	sl, r9, [sp, #16]
    2df4:	2e01      	cmp	r6, #1
    2df6:	db0d      	blt.n	2e14 <BP_AUD_Init@@Base+0x108>
    2df8:	4d53      	ldr	r5, [pc, #332]	@ (2f48 <BP_AUD_Init@@Base+0x23c>)
    2dfa:	f108 0714 	add.w	r7, r8, #20
    2dfe:	447d      	add	r5, pc
    2e00:	6838      	ldr	r0, [r7, #0]
    2e02:	4629      	mov	r1, r5
    2e04:	2204      	movs	r2, #4
    2e06:	4440      	add	r0, r8
    2e08:	f000 ee02 	blx	3a10 <strncmp>
    2e0c:	b9f0      	cbnz	r0, 2e4c <BP_AUD_Init@@Base+0x140>
    2e0e:	3704      	adds	r7, #4
    2e10:	3e01      	subs	r6, #1
    2e12:	d1f5      	bne.n	2e00 <BP_AUD_Init@@Base+0xf4>
    2e14:	494d      	ldr	r1, [pc, #308]	@ (2f4c <BP_AUD_Init@@Base+0x240>)
    2e16:	4650      	mov	r0, sl
    2e18:	2204      	movs	r2, #4
    2e1a:	4479      	add	r1, pc
    2e1c:	f000 edf8 	blx	3a10 <strncmp>
    2e20:	b1b0      	cbz	r0, 2e50 <BP_AUD_Init@@Base+0x144>
    2e22:	484c      	ldr	r0, [pc, #304]	@ (2f54 <BP_AUD_Init@@Base+0x248>)
    2e24:	f44f 77b0 	mov.w	r7, #352	@ 0x160
    2e28:	4a4b      	ldr	r2, [pc, #300]	@ (2f58 <BP_AUD_Init@@Base+0x24c>)
    2e2a:	4478      	add	r0, pc
    2e2c:	4b4b      	ldr	r3, [pc, #300]	@ (2f5c <BP_AUD_Init@@Base+0x250>)
    2e2e:	447a      	add	r2, pc
    2e30:	6800      	ldr	r0, [r0, #0]
    2e32:	447b      	add	r3, pc
    2e34:	6800      	ldr	r0, [r0, #0]
    2e36:	494a      	ldr	r1, [pc, #296]	@ (2f60 <BP_AUD_Init@@Base+0x254>)
    2e38:	4479      	add	r1, pc
    2e3a:	e9cd 7100 	strd	r7, r1, [sp]
    2e3e:	2101      	movs	r1, #1
    2e40:	f8cd a008 	str.w	sl, [sp, #8]
    2e44:	f000 eddc 	blx	3a00 <trid_debug_log>
    2e48:	2508      	movs	r5, #8
    2e4a:	e78f      	b.n	2d6c <BP_AUD_Init@@Base+0x60>
    2e4c:	2507      	movs	r5, #7
    2e4e:	e78d      	b.n	2d6c <BP_AUD_Init@@Base+0x60>
    2e50:	f8da 6008 	ldr.w	r6, [sl, #8]
    2e54:	2e01      	cmp	r6, #1
    2e56:	db0d      	blt.n	2e74 <BP_AUD_Init@@Base+0x168>
    2e58:	4d3d      	ldr	r5, [pc, #244]	@ (2f50 <BP_AUD_Init@@Base+0x244>)
    2e5a:	f10a 070c 	add.w	r7, sl, #12
    2e5e:	447d      	add	r5, pc
    2e60:	6838      	ldr	r0, [r7, #0]
    2e62:	4629      	mov	r1, r5
    2e64:	2204      	movs	r2, #4
    2e66:	4450      	add	r0, sl
    2e68:	f000 edd2 	blx	3a10 <strncmp>
    2e6c:	b958      	cbnz	r0, 2e86 <BP_AUD_Init@@Base+0x17a>
    2e6e:	3704      	adds	r7, #4
    2e70:	3e01      	subs	r6, #1
    2e72:	d1f5      	bne.n	2e60 <BP_AUD_Init@@Base+0x154>
    2e74:	493b      	ldr	r1, [pc, #236]	@ (2f64 <BP_AUD_Init@@Base+0x258>)
    2e76:	4648      	mov	r0, r9
    2e78:	2204      	movs	r2, #4
    2e7a:	4479      	add	r1, pc
    2e7c:	f000 edc8 	blx	3a10 <strncmp>
    2e80:	b118      	cbz	r0, 2e8a <BP_AUD_Init@@Base+0x17e>
    2e82:	250a      	movs	r5, #10
    2e84:	e772      	b.n	2d6c <BP_AUD_Init@@Base+0x60>
    2e86:	2509      	movs	r5, #9
    2e88:	e770      	b.n	2d6c <BP_AUD_Init@@Base+0x60>
    2e8a:	f8d9 6008 	ldr.w	r6, [r9, #8]
    2e8e:	2e01      	cmp	r6, #1
    2e90:	db0d      	blt.n	2eae <BP_AUD_Init@@Base+0x1a2>
    2e92:	4d35      	ldr	r5, [pc, #212]	@ (2f68 <BP_AUD_Init@@Base+0x25c>)
    2e94:	f109 070c 	add.w	r7, r9, #12
    2e98:	447d      	add	r5, pc
    2e9a:	6838      	ldr	r0, [r7, #0]
    2e9c:	4629      	mov	r1, r5
    2e9e:	2204      	movs	r2, #4
    2ea0:	4448      	add	r0, r9
    2ea2:	f000 edb6 	blx	3a10 <strncmp>
    2ea6:	b960      	cbnz	r0, 2ec2 <BP_AUD_Init@@Base+0x1b6>
    2ea8:	3704      	adds	r7, #4
    2eaa:	3e01      	subs	r6, #1
    2eac:	d1f5      	bne.n	2e9a <BP_AUD_Init@@Base+0x18e>
    2eae:	492f      	ldr	r1, [pc, #188]	@ (2f6c <BP_AUD_Init@@Base+0x260>)
    2eb0:	4620      	mov	r0, r4
    2eb2:	2204      	movs	r2, #4
    2eb4:	4625      	mov	r5, r4
    2eb6:	4479      	add	r1, pc
    2eb8:	f000 edaa 	blx	3a10 <strncmp>
    2ebc:	b118      	cbz	r0, 2ec6 <BP_AUD_Init@@Base+0x1ba>
    2ebe:	250c      	movs	r5, #12
    2ec0:	e754      	b.n	2d6c <BP_AUD_Init@@Base+0x60>
    2ec2:	250b      	movs	r5, #11
    2ec4:	e752      	b.n	2d6c <BP_AUD_Init@@Base+0x60>
    2ec6:	68ae      	ldr	r6, [r5, #8]
    2ec8:	2e01      	cmp	r6, #1
    2eca:	db0d      	blt.n	2ee8 <BP_AUD_Init@@Base+0x1dc>
    2ecc:	4d28      	ldr	r5, [pc, #160]	@ (2f70 <BP_AUD_Init@@Base+0x264>)
    2ece:	f104 070c 	add.w	r7, r4, #12
    2ed2:	447d      	add	r5, pc
    2ed4:	6838      	ldr	r0, [r7, #0]
    2ed6:	4629      	mov	r1, r5
    2ed8:	2204      	movs	r2, #4
    2eda:	4420      	add	r0, r4
    2edc:	f000 ed98 	blx	3a10 <strncmp>
    2ee0:	b958      	cbnz	r0, 2efa <BP_AUD_Init@@Base+0x1ee>
    2ee2:	3704      	adds	r7, #4
    2ee4:	3e01      	subs	r6, #1
    2ee6:	d1f5      	bne.n	2ed4 <BP_AUD_Init@@Base+0x1c8>
    2ee8:	4922      	ldr	r1, [pc, #136]	@ (2f74 <BP_AUD_Init@@Base+0x268>)
    2eea:	2204      	movs	r2, #4
    2eec:	9803      	ldr	r0, [sp, #12]
    2eee:	4479      	add	r1, pc
    2ef0:	f000 ed8e 	blx	3a10 <strncmp>
    2ef4:	b118      	cbz	r0, 2efe <BP_AUD_Init@@Base+0x1f2>
    2ef6:	250e      	movs	r5, #14
    2ef8:	e738      	b.n	2d6c <BP_AUD_Init@@Base+0x60>
    2efa:	250d      	movs	r5, #13
    2efc:	e736      	b.n	2d6c <BP_AUD_Init@@Base+0x60>
    2efe:	9c03      	ldr	r4, [sp, #12]
    2f00:	68a6      	ldr	r6, [r4, #8]
    2f02:	2e01      	cmp	r6, #1
    2f04:	db0d      	blt.n	2f22 <BP_AUD_Init@@Base+0x216>
    2f06:	4d1c      	ldr	r5, [pc, #112]	@ (2f78 <BP_AUD_Init@@Base+0x26c>)
    2f08:	f104 070c 	add.w	r7, r4, #12
    2f0c:	447d      	add	r5, pc
    2f0e:	6838      	ldr	r0, [r7, #0]
    2f10:	4629      	mov	r1, r5
    2f12:	2204      	movs	r2, #4
    2f14:	4420      	add	r0, r4
    2f16:	f000 ed7c 	blx	3a10 <strncmp>
    2f1a:	b938      	cbnz	r0, 2f2c <BP_AUD_Init@@Base+0x220>
    2f1c:	3704      	adds	r7, #4
    2f1e:	3e01      	subs	r6, #1
    2f20:	d1f5      	bne.n	2f0e <BP_AUD_Init@@Base+0x202>
    2f22:	9906      	ldr	r1, [sp, #24]
    2f24:	2001      	movs	r0, #1
    2f26:	2500      	movs	r5, #0
    2f28:	61c8      	str	r0, [r1, #28]
    2f2a:	e71f      	b.n	2d6c <BP_AUD_Init@@Base+0x60>
    2f2c:	250f      	movs	r5, #15
    2f2e:	e71d      	b.n	2d6c <BP_AUD_Init@@Base+0x60>
    2f30:	318c      	adds	r1, #140	@ 0x8c
    2f32:	0000      	movs	r0, r0
    2f34:	ec33 ffff 	ldc	15, cr15, [r3], #-1020	@ 0xfffffc04
    2f38:	ec9c ffff 	ldc	15, cr15, [ip], {255}	@ 0xff
    2f3c:	ebfe ffff 			@ <UNDEFINED> instruction: 0xebfeffff
    2f40:	ec73 ffff 	ldcl	15, cr15, [r3], #-1020	@ 0xfffffc04
    2f44:	ec62 ffff 	stcl	15, cr15, [r2], #-1020	@ 0xfffffc04
    2f48:	ec13 ffff 	ldc	15, cr15, [r3], {255}	@ 0xff
    2f4c:	ecc1 ffff 	stcl	15, cr15, [r1], {255}	@ 0xff
    2f50:	ec41 ffff 	mcrr	15, 15, pc, r1, cr15	@ <UNPREDICTABLE>
    2f54:	204e      	movs	r0, #78	@ 0x4e
    2f56:	0000      	movs	r0, r0
    2f58:	eb80 ffff 			@ <UNDEFINED> instruction: 0xeb80ffff
    2f5c:	ecae ffff 	stc	15, cr15, [lr], #1020	@ 0x3fc
    2f60:	ec76 ffff 	ldcl	15, cr15, [r6], #-1020	@ 0xfffffc04
    2f64:	eb2f ffff 			@ <UNDEFINED> instruction: 0xeb2fffff
    2f68:	ec0c ffff 	stc	15, cr15, [ip], {255}	@ 0xff
    2f6c:	ebf3 ffff 			@ <UNDEFINED> instruction: 0xebf3ffff
    2f70:	eac8 ffff 			@ <UNDEFINED> instruction: 0xeac8ffff
    2f74:	eab1 ffff 			@ <UNDEFINED> instruction: 0xeab1ffff
    2f78:	ea80 ffff 			@ <UNDEFINED> instruction: 0xea80ffff

00002f7c <BP_AUD_Uninit@@Base>:
    2f7c:	4807      	ldr	r0, [pc, #28]	@ (2f9c <BP_AUD_Uninit@@Base+0x20>)
    2f7e:	4478      	add	r0, pc
    2f80:	69c1      	ldr	r1, [r0, #28]
    2f82:	2901      	cmp	r1, #1
    2f84:	bf1c      	itt	ne
    2f86:	2011      	movne	r0, #17
    2f88:	4770      	bxne	lr
    2f8a:	efc0 0050 	vmov.i32	q8, #0	@ 0x00000000
    2f8e:	f940 0acd 	vst1.64	{d16-d17}, [r0]!
    2f92:	f940 0acf 	vst1.64	{d16-d17}, [r0]
    2f96:	2000      	movs	r0, #0
    2f98:	4770      	bx	lr
    2f9a:	bf00      	nop
    2f9c:	2f26      	cmp	r7, #38	@ 0x26
	...

00002fa0 <BP_AUD_GetFileHead@@Base>:
    2fa0:	4906      	ldr	r1, [pc, #24]	@ (2fbc <BP_AUD_GetFileHead@@Base+0x1c>)
    2fa2:	4479      	add	r1, pc
    2fa4:	69ca      	ldr	r2, [r1, #28]
    2fa6:	2a01      	cmp	r2, #1
    2fa8:	bf1c      	itt	ne
    2faa:	2011      	movne	r0, #17
    2fac:	4770      	bxne	lr
    2fae:	2800      	cmp	r0, #0
    2fb0:	bf0f      	iteee	eq
    2fb2:	2001      	moveq	r0, #1
    2fb4:	6809      	ldrne	r1, [r1, #0]
    2fb6:	6001      	strne	r1, [r0, #0]
    2fb8:	2000      	movne	r0, #0
    2fba:	4770      	bx	lr
    2fbc:	2f02      	cmp	r7, #2
	...

00002fc0 <BP_AUD_GetDepository@@Base>:
    2fc0:	4906      	ldr	r1, [pc, #24]	@ (2fdc <BP_AUD_GetDepository@@Base+0x1c>)
    2fc2:	4479      	add	r1, pc
    2fc4:	69ca      	ldr	r2, [r1, #28]
    2fc6:	2a01      	cmp	r2, #1
    2fc8:	bf1c      	itt	ne
    2fca:	2011      	movne	r0, #17
    2fcc:	4770      	bxne	lr
    2fce:	2800      	cmp	r0, #0
    2fd0:	bf0f      	iteee	eq
    2fd2:	2001      	moveq	r0, #1
    2fd4:	6849      	ldrne	r1, [r1, #4]
    2fd6:	6001      	strne	r1, [r0, #0]
    2fd8:	2000      	movne	r0, #0
    2fda:	4770      	bx	lr
    2fdc:	2ee2      	cmp	r6, #226	@ 0xe2
	...

00002fe0 <BP_AUD_GetModule@@Base>:
    2fe0:	b510      	push	{r4, lr}
    2fe2:	4c14      	ldr	r4, [pc, #80]	@ (3034 <BP_AUD_GetModule@@Base+0x54>)
    2fe4:	447c      	add	r4, pc
    2fe6:	69e2      	ldr	r2, [r4, #28]
    2fe8:	2a01      	cmp	r2, #1
    2fea:	bf1c      	itt	ne
    2fec:	2011      	movne	r0, #17
    2fee:	bd10      	popne	{r4, pc}
    2ff0:	2900      	cmp	r1, #0
    2ff2:	bf04      	itt	eq
    2ff4:	2001      	moveq	r0, #1
    2ff6:	bd10      	popeq	{r4, pc}
    2ff8:	6862      	ldr	r2, [r4, #4]
    2ffa:	e9d2 c302 	ldrd	ip, r3, [r2, #8]
    2ffe:	f8d2 e010 	ldr.w	lr, [r2, #16]
    3002:	2200      	movs	r2, #0
    3004:	4463      	add	r3, ip
    3006:	600a      	str	r2, [r1, #0]
    3008:	449e      	add	lr, r3
    300a:	f1be 0f01 	cmp.w	lr, #1
    300e:	db0f      	blt.n	3030 <BP_AUD_GetModule@@Base+0x50>
    3010:	f8d4 c004 	ldr.w	ip, [r4, #4]
    3014:	f10c 0214 	add.w	r2, ip, #20
    3018:	6814      	ldr	r4, [r2, #0]
    301a:	4464      	add	r4, ip
    301c:	68a3      	ldr	r3, [r4, #8]
    301e:	4283      	cmp	r3, r0
    3020:	d004      	beq.n	302c <BP_AUD_GetModule@@Base+0x4c>
    3022:	3204      	adds	r2, #4
    3024:	f1be 0e01 	subs.w	lr, lr, #1
    3028:	d1f6      	bne.n	3018 <BP_AUD_GetModule@@Base+0x38>
    302a:	e000      	b.n	302e <BP_AUD_GetModule@@Base+0x4e>
    302c:	600c      	str	r4, [r1, #0]
    302e:	2200      	movs	r2, #0
    3030:	4610      	mov	r0, r2
    3032:	bd10      	pop	{r4, pc}
    3034:	2ec0      	cmp	r6, #192	@ 0xc0
	...

00003038 <BP_AUD_GetGraph@@Base>:
    3038:	4906      	ldr	r1, [pc, #24]	@ (3054 <BP_AUD_GetGraph@@Base+0x1c>)
    303a:	4479      	add	r1, pc
    303c:	69ca      	ldr	r2, [r1, #28]
    303e:	2a01      	cmp	r2, #1
    3040:	bf1c      	itt	ne
    3042:	2011      	movne	r0, #17
    3044:	4770      	bxne	lr
    3046:	2800      	cmp	r0, #0
    3048:	bf0f      	iteee	eq
    304a:	2001      	moveq	r0, #1
    304c:	6889      	ldrne	r1, [r1, #8]
    304e:	6001      	strne	r1, [r0, #0]
    3050:	2000      	movne	r0, #0
    3052:	4770      	bx	lr
    3054:	2e6a      	cmp	r6, #106	@ 0x6a
	...

00003058 <BP_AUD_GetActionNum@@Base>:
    3058:	4602      	mov	r2, r0
    305a:	4809      	ldr	r0, [pc, #36]	@ (3080 <BP_AUD_GetActionNum@@Base+0x28>)
    305c:	4478      	add	r0, pc
    305e:	69c0      	ldr	r0, [r0, #28]
    3060:	2801      	cmp	r0, #1
    3062:	bf1c      	itt	ne
    3064:	2011      	movne	r0, #17
    3066:	4770      	bxne	lr
    3068:	2001      	movs	r0, #1
    306a:	2a00      	cmp	r2, #0
    306c:	bf1f      	itttt	ne
    306e:	2900      	cmpne	r1, #0
    3070:	6910      	ldrne	r0, [r2, #16]
    3072:	4410      	addne	r0, r2
    3074:	6900      	ldrne	r0, [r0, #16]
    3076:	bf1c      	itt	ne
    3078:	6008      	strne	r0, [r1, #0]
    307a:	2000      	movne	r0, #0
    307c:	4770      	bx	lr
    307e:	bf00      	nop
    3080:	2e48      	cmp	r6, #72	@ 0x48
	...

00003084 <BP_AUD_GetConnectNum@@Base>:
    3084:	4602      	mov	r2, r0
    3086:	4809      	ldr	r0, [pc, #36]	@ (30ac <BP_AUD_GetConnectNum@@Base+0x28>)
    3088:	4478      	add	r0, pc
    308a:	69c0      	ldr	r0, [r0, #28]
    308c:	2801      	cmp	r0, #1
    308e:	bf1c      	itt	ne
    3090:	2011      	movne	r0, #17
    3092:	4770      	bxne	lr
    3094:	2001      	movs	r0, #1
    3096:	2a00      	cmp	r2, #0
    3098:	bf1f      	itttt	ne
    309a:	2900      	cmpne	r1, #0
    309c:	6910      	ldrne	r0, [r2, #16]
    309e:	4410      	addne	r0, r2
    30a0:	6880      	ldrne	r0, [r0, #8]
    30a2:	bf1c      	itt	ne
    30a4:	6008      	strne	r0, [r1, #0]
    30a6:	2000      	movne	r0, #0
    30a8:	4770      	bx	lr
    30aa:	bf00      	nop
    30ac:	2e1c      	cmp	r6, #28
	...

000030b0 <BP_AUD_GetConnectByIndex@@Base>:
    30b0:	4603      	mov	r3, r0
    30b2:	480f      	ldr	r0, [pc, #60]	@ (30f0 <BP_AUD_GetConnectByIndex@@Base+0x40>)
    30b4:	4478      	add	r0, pc
    30b6:	69c0      	ldr	r0, [r0, #28]
    30b8:	2801      	cmp	r0, #1
    30ba:	bf1c      	itt	ne
    30bc:	2011      	movne	r0, #17
    30be:	4770      	bxne	lr
    30c0:	2b00      	cmp	r3, #0
    30c2:	f04f 0001 	mov.w	r0, #1
    30c6:	bf18      	it	ne
    30c8:	2a00      	cmpne	r2, #0
    30ca:	d100      	bne.n	30ce <BP_AUD_GetConnectByIndex@@Base+0x1e>
    30cc:	4770      	bx	lr
    30ce:	6918      	ldr	r0, [r3, #16]
    30d0:	4418      	add	r0, r3
    30d2:	6883      	ldr	r3, [r0, #8]
    30d4:	428b      	cmp	r3, r1
    30d6:	d906      	bls.n	30e6 <BP_AUD_GetConnectByIndex@@Base+0x36>
    30d8:	68c3      	ldr	r3, [r0, #12]
    30da:	eb01 0181 	add.w	r1, r1, r1, lsl #2
    30de:	4418      	add	r0, r3
    30e0:	eb00 0081 	add.w	r0, r0, r1, lsl #2
    30e4:	e000      	b.n	30e8 <BP_AUD_GetConnectByIndex@@Base+0x38>
    30e6:	2000      	movs	r0, #0
    30e8:	6010      	str	r0, [r2, #0]
    30ea:	2000      	movs	r0, #0
    30ec:	4770      	bx	lr
    30ee:	bf00      	nop
    30f0:	2df0      	cmp	r5, #240	@ 0xf0
	...

000030f4 <BP_AUD_GetActionByIndex@@Base>:
    30f4:	4603      	mov	r3, r0
    30f6:	480e      	ldr	r0, [pc, #56]	@ (3130 <BP_AUD_GetActionByIndex@@Base+0x3c>)
    30f8:	4478      	add	r0, pc
    30fa:	69c0      	ldr	r0, [r0, #28]
    30fc:	2801      	cmp	r0, #1
    30fe:	bf1c      	itt	ne
    3100:	2011      	movne	r0, #17
    3102:	4770      	bxne	lr
    3104:	2b00      	cmp	r3, #0
    3106:	f04f 0001 	mov.w	r0, #1
    310a:	bf18      	it	ne
    310c:	2a00      	cmpne	r2, #0
    310e:	d100      	bne.n	3112 <BP_AUD_GetActionByIndex@@Base+0x1e>
    3110:	4770      	bx	lr
    3112:	6918      	ldr	r0, [r3, #16]
    3114:	4418      	add	r0, r3
    3116:	6903      	ldr	r3, [r0, #16]
    3118:	428b      	cmp	r3, r1
    311a:	d904      	bls.n	3126 <BP_AUD_GetActionByIndex@@Base+0x32>
    311c:	eb00 0181 	add.w	r1, r0, r1, lsl #2
    3120:	6949      	ldr	r1, [r1, #20]
    3122:	4408      	add	r0, r1
    3124:	e000      	b.n	3128 <BP_AUD_GetActionByIndex@@Base+0x34>
    3126:	2000      	movs	r0, #0
    3128:	6010      	str	r0, [r2, #0]
    312a:	2000      	movs	r0, #0
    312c:	4770      	bx	lr
    312e:	bf00      	nop
    3130:	2dac      	cmp	r5, #172	@ 0xac
	...

00003134 <BP_AUD_GetMuxByIndex@@Base>:
    3134:	4b0d      	ldr	r3, [pc, #52]	@ (316c <BP_AUD_GetMuxByIndex@@Base+0x38>)
    3136:	447b      	add	r3, pc
    3138:	69db      	ldr	r3, [r3, #28]
    313a:	2b01      	cmp	r3, #1
    313c:	bf1c      	itt	ne
    313e:	2011      	movne	r0, #17
    3140:	4770      	bxne	lr
    3142:	2800      	cmp	r0, #0
    3144:	f04f 0301 	mov.w	r3, #1
    3148:	bf18      	it	ne
    314a:	2a00      	cmpne	r2, #0
    314c:	d101      	bne.n	3152 <BP_AUD_GetMuxByIndex@@Base+0x1e>
    314e:	4618      	mov	r0, r3
    3150:	4770      	bx	lr
    3152:	68c3      	ldr	r3, [r0, #12]
    3154:	428b      	cmp	r3, r1
    3156:	d904      	bls.n	3162 <BP_AUD_GetMuxByIndex@@Base+0x2e>
    3158:	eb00 0181 	add.w	r1, r0, r1, lsl #2
    315c:	6949      	ldr	r1, [r1, #20]
    315e:	4408      	add	r0, r1
    3160:	e000      	b.n	3164 <BP_AUD_GetMuxByIndex@@Base+0x30>
    3162:	2000      	movs	r0, #0
    3164:	2300      	movs	r3, #0
    3166:	6010      	str	r0, [r2, #0]
    3168:	4618      	mov	r0, r3
    316a:	4770      	bx	lr
    316c:	2d6e      	cmp	r5, #110	@ 0x6e
	...

00003170 <BP_AUD_GetMuxById@@Base>:
    3170:	b5b0      	push	{r4, r5, r7, lr}
    3172:	4b12      	ldr	r3, [pc, #72]	@ (31bc <BP_AUD_GetMuxById@@Base+0x4c>)
    3174:	447b      	add	r3, pc
    3176:	69db      	ldr	r3, [r3, #28]
    3178:	2b01      	cmp	r3, #1
    317a:	bf1c      	itt	ne
    317c:	2011      	movne	r0, #17
    317e:	bdb0      	popne	{r4, r5, r7, pc}
    3180:	2800      	cmp	r0, #0
    3182:	f04f 0301 	mov.w	r3, #1
    3186:	bf18      	it	ne
    3188:	2a00      	cmpne	r2, #0
    318a:	d101      	bne.n	3190 <BP_AUD_GetMuxById@@Base+0x20>
    318c:	4618      	mov	r0, r3
    318e:	bdb0      	pop	{r4, r5, r7, pc}
    3190:	f8d0 e00c 	ldr.w	lr, [r0, #12]
    3194:	f1be 0f01 	cmp.w	lr, #1
    3198:	db0b      	blt.n	31b2 <BP_AUD_GetMuxById@@Base+0x42>
    319a:	f100 0c14 	add.w	ip, r0, #20
    319e:	2300      	movs	r3, #0
    31a0:	f85c 4023 	ldr.w	r4, [ip, r3, lsl #2]
    31a4:	4404      	add	r4, r0
    31a6:	69e5      	ldr	r5, [r4, #28]
    31a8:	428d      	cmp	r5, r1
    31aa:	d003      	beq.n	31b4 <BP_AUD_GetMuxById@@Base+0x44>
    31ac:	3301      	adds	r3, #1
    31ae:	4573      	cmp	r3, lr
    31b0:	dbf6      	blt.n	31a0 <BP_AUD_GetMuxById@@Base+0x30>
    31b2:	2400      	movs	r4, #0
    31b4:	2300      	movs	r3, #0
    31b6:	6014      	str	r4, [r2, #0]
    31b8:	4618      	mov	r0, r3
    31ba:	bdb0      	pop	{r4, r5, r7, pc}
    31bc:	2d30      	cmp	r5, #48	@ 0x30
	...

000031c0 <BP_AUD_GetMuxInByIndex@@Base>:
    31c0:	4b0d      	ldr	r3, [pc, #52]	@ (31f8 <BP_AUD_GetMuxInByIndex@@Base+0x38>)
    31c2:	447b      	add	r3, pc
    31c4:	69db      	ldr	r3, [r3, #28]
    31c6:	2b01      	cmp	r3, #1
    31c8:	bf1c      	itt	ne
    31ca:	2011      	movne	r0, #17
    31cc:	4770      	bxne	lr
    31ce:	2800      	cmp	r0, #0
    31d0:	f04f 0301 	mov.w	r3, #1
    31d4:	bf18      	it	ne
    31d6:	2a00      	cmpne	r2, #0
    31d8:	d101      	bne.n	31de <BP_AUD_GetMuxInByIndex@@Base+0x1e>
    31da:	4618      	mov	r0, r3
    31dc:	4770      	bx	lr
    31de:	6a03      	ldr	r3, [r0, #32]
    31e0:	428b      	cmp	r3, r1
    31e2:	d904      	bls.n	31ee <BP_AUD_GetMuxInByIndex@@Base+0x2e>
    31e4:	6a43      	ldr	r3, [r0, #36]	@ 0x24
    31e6:	4418      	add	r0, r3
    31e8:	eb00 1041 	add.w	r0, r0, r1, lsl #5
    31ec:	e000      	b.n	31f0 <BP_AUD_GetMuxInByIndex@@Base+0x30>
    31ee:	2000      	movs	r0, #0
    31f0:	2300      	movs	r3, #0
    31f2:	6010      	str	r0, [r2, #0]
    31f4:	4618      	mov	r0, r3
    31f6:	4770      	bx	lr
    31f8:	2ce2      	cmp	r4, #226	@ 0xe2
	...

000031fc <BP_AUD_GetMuxInById@@Base>:
    31fc:	b580      	push	{r7, lr}
    31fe:	4b14      	ldr	r3, [pc, #80]	@ (3250 <BP_AUD_GetMuxInById@@Base+0x54>)
    3200:	447b      	add	r3, pc
    3202:	69db      	ldr	r3, [r3, #28]
    3204:	2b01      	cmp	r3, #1
    3206:	bf1c      	itt	ne
    3208:	2011      	movne	r0, #17
    320a:	bd80      	popne	{r7, pc}
    320c:	2800      	cmp	r0, #0
    320e:	f04f 0301 	mov.w	r3, #1
    3212:	bf18      	it	ne
    3214:	2a00      	cmpne	r2, #0
    3216:	d101      	bne.n	321c <BP_AUD_GetMuxInById@@Base+0x20>
    3218:	4618      	mov	r0, r3
    321a:	bd80      	pop	{r7, pc}
    321c:	f8d0 c020 	ldr.w	ip, [r0, #32]
    3220:	f1bc 0f01 	cmp.w	ip, #1
    3224:	db0c      	blt.n	3240 <BP_AUD_GetMuxInById@@Base+0x44>
    3226:	6a43      	ldr	r3, [r0, #36]	@ 0x24
    3228:	eb00 0e03 	add.w	lr, r0, r3
    322c:	2300      	movs	r3, #0
    322e:	f8de 0010 	ldr.w	r0, [lr, #16]
    3232:	4288      	cmp	r0, r1
    3234:	d006      	beq.n	3244 <BP_AUD_GetMuxInById@@Base+0x48>
    3236:	3301      	adds	r3, #1
    3238:	f10e 0e20 	add.w	lr, lr, #32
    323c:	4563      	cmp	r3, ip
    323e:	dbf6      	blt.n	322e <BP_AUD_GetMuxInById@@Base+0x32>
    3240:	f04f 0e00 	mov.w	lr, #0
    3244:	2300      	movs	r3, #0
    3246:	f8c2 e000 	str.w	lr, [r2]
    324a:	4618      	mov	r0, r3
    324c:	bd80      	pop	{r7, pc}
    324e:	bf00      	nop
    3250:	2ca4      	cmp	r4, #164	@ 0xa4
	...

00003254 <BP_AUD_GetMuxOutByIndex@@Base>:
    3254:	4b0d      	ldr	r3, [pc, #52]	@ (328c <BP_AUD_GetMuxOutByIndex@@Base+0x38>)
    3256:	447b      	add	r3, pc
    3258:	69db      	ldr	r3, [r3, #28]
    325a:	2b01      	cmp	r3, #1
    325c:	bf1c      	itt	ne
    325e:	2011      	movne	r0, #17
    3260:	4770      	bxne	lr
    3262:	2800      	cmp	r0, #0
    3264:	f04f 0301 	mov.w	r3, #1
    3268:	bf18      	it	ne
    326a:	2a00      	cmpne	r2, #0
    326c:	d101      	bne.n	3272 <BP_AUD_GetMuxOutByIndex@@Base+0x1e>
    326e:	4618      	mov	r0, r3
    3270:	4770      	bx	lr
    3272:	6a83      	ldr	r3, [r0, #40]	@ 0x28
    3274:	428b      	cmp	r3, r1
    3276:	d904      	bls.n	3282 <BP_AUD_GetMuxOutByIndex@@Base+0x2e>
    3278:	6ac3      	ldr	r3, [r0, #44]	@ 0x2c
    327a:	4418      	add	r0, r3
    327c:	eb00 1041 	add.w	r0, r0, r1, lsl #5
    3280:	e000      	b.n	3284 <BP_AUD_GetMuxOutByIndex@@Base+0x30>
    3282:	2000      	movs	r0, #0
    3284:	2300      	movs	r3, #0
    3286:	6010      	str	r0, [r2, #0]
    3288:	4618      	mov	r0, r3
    328a:	4770      	bx	lr
    328c:	2c4e      	cmp	r4, #78	@ 0x4e
	...

00003290 <BP_AUD_GetMuxOutById@@Base>:
    3290:	b580      	push	{r7, lr}
    3292:	4b14      	ldr	r3, [pc, #80]	@ (32e4 <BP_AUD_GetMuxOutById@@Base+0x54>)
    3294:	447b      	add	r3, pc
    3296:	69db      	ldr	r3, [r3, #28]
    3298:	2b01      	cmp	r3, #1
    329a:	bf1c      	itt	ne
    329c:	2011      	movne	r0, #17
    329e:	bd80      	popne	{r7, pc}
    32a0:	2800      	cmp	r0, #0
    32a2:	f04f 0301 	mov.w	r3, #1
    32a6:	bf18      	it	ne
    32a8:	2a00      	cmpne	r2, #0
    32aa:	d101      	bne.n	32b0 <BP_AUD_GetMuxOutById@@Base+0x20>
    32ac:	4618      	mov	r0, r3
    32ae:	bd80      	pop	{r7, pc}
    32b0:	f8d0 c028 	ldr.w	ip, [r0, #40]	@ 0x28
    32b4:	f1bc 0f01 	cmp.w	ip, #1
    32b8:	db0c      	blt.n	32d4 <BP_AUD_GetMuxOutById@@Base+0x44>
    32ba:	6ac3      	ldr	r3, [r0, #44]	@ 0x2c
    32bc:	eb00 0e03 	add.w	lr, r0, r3
    32c0:	2300      	movs	r3, #0
    32c2:	f8de 0010 	ldr.w	r0, [lr, #16]
    32c6:	4288      	cmp	r0, r1
    32c8:	d006      	beq.n	32d8 <BP_AUD_GetMuxOutById@@Base+0x48>
    32ca:	3301      	adds	r3, #1
    32cc:	f10e 0e20 	add.w	lr, lr, #32
    32d0:	4563      	cmp	r3, ip
    32d2:	dbf6      	blt.n	32c2 <BP_AUD_GetMuxOutById@@Base+0x32>
    32d4:	f04f 0e00 	mov.w	lr, #0
    32d8:	2300      	movs	r3, #0
    32da:	f8c2 e000 	str.w	lr, [r2]
    32de:	4618      	mov	r0, r3
    32e0:	bd80      	pop	{r7, pc}
    32e2:	bf00      	nop
    32e4:	2c10      	cmp	r4, #16
	...

000032e8 <BP_AUD_IsMux@@Base>:
    32e8:	b580      	push	{r7, lr}
    32ea:	4b12      	ldr	r3, [pc, #72]	@ (3334 <BP_AUD_IsMux@@Base+0x4c>)
    32ec:	447b      	add	r3, pc
    32ee:	69db      	ldr	r3, [r3, #28]
    32f0:	2b01      	cmp	r3, #1
    32f2:	bf1c      	itt	ne
    32f4:	2011      	movne	r0, #17
    32f6:	bd80      	popne	{r7, pc}
    32f8:	f8d0 e00c 	ldr.w	lr, [r0, #12]
    32fc:	f04f 0c00 	mov.w	ip, #0
    3300:	f882 c000 	strb.w	ip, [r2]
    3304:	f1be 0f01 	cmp.w	lr, #1
    3308:	db11      	blt.n	332e <BP_AUD_IsMux@@Base+0x46>
    330a:	f100 0c14 	add.w	ip, r0, #20
    330e:	f8dc 3000 	ldr.w	r3, [ip]
    3312:	4403      	add	r3, r0
    3314:	69db      	ldr	r3, [r3, #28]
    3316:	428b      	cmp	r3, r1
    3318:	d005      	beq.n	3326 <BP_AUD_IsMux@@Base+0x3e>
    331a:	f10c 0c04 	add.w	ip, ip, #4
    331e:	f1be 0e01 	subs.w	lr, lr, #1
    3322:	d1f4      	bne.n	330e <BP_AUD_IsMux@@Base+0x26>
    3324:	e001      	b.n	332a <BP_AUD_IsMux@@Base+0x42>
    3326:	2001      	movs	r0, #1
    3328:	7010      	strb	r0, [r2, #0]
    332a:	f04f 0c00 	mov.w	ip, #0
    332e:	4660      	mov	r0, ip
    3330:	bd80      	pop	{r7, pc}
    3332:	bf00      	nop
    3334:	2bb8      	cmp	r3, #184	@ 0xb8
	...

00003338 <BP_AUD_MuxInId2Index@@Base>:
    3338:	b5b0      	push	{r4, r5, r7, lr}
    333a:	4603      	mov	r3, r0
    333c:	4823      	ldr	r0, [pc, #140]	@ (33cc <BP_AUD_MuxInId2Index@@Base+0x94>)
    333e:	4478      	add	r0, pc
    3340:	69c0      	ldr	r0, [r0, #28]
    3342:	2801      	cmp	r0, #1
    3344:	bf1c      	itt	ne
    3346:	2011      	movne	r0, #17
    3348:	bdb0      	popne	{r4, r5, r7, pc}
    334a:	2b00      	cmp	r3, #0
    334c:	f04f 0001 	mov.w	r0, #1
    3350:	bf18      	it	ne
    3352:	2a00      	cmpne	r2, #0
    3354:	d100      	bne.n	3358 <BP_AUD_MuxInId2Index@@Base+0x20>
    3356:	bdb0      	pop	{r4, r5, r7, pc}
    3358:	f04f 30ff 	mov.w	r0, #4294967295	@ 0xffffffff
    335c:	f1a1 0c01 	sub.w	ip, r1, #1
    3360:	6010      	str	r0, [r2, #0]
    3362:	f8d3 e020 	ldr.w	lr, [r3, #32]
    3366:	45f4      	cmp	ip, lr
    3368:	d219      	bcs.n	339e <BP_AUD_MuxInId2Index@@Base+0x66>
    336a:	f1be 0f01 	cmp.w	lr, #1
    336e:	db14      	blt.n	339a <BP_AUD_MuxInId2Index@@Base+0x62>
    3370:	6a58      	ldr	r0, [r3, #36]	@ 0x24
    3372:	eb00 1041 	add.w	r0, r0, r1, lsl #5
    3376:	4418      	add	r0, r3
    3378:	2300      	movs	r3, #0
    337a:	3810      	subs	r0, #16
    337c:	eb0c 0403 	add.w	r4, ip, r3
    3380:	4574      	cmp	r4, lr
    3382:	4674      	mov	r4, lr
    3384:	bfb8      	it	lt
    3386:	2400      	movlt	r4, #0
    3388:	eba0 1544 	sub.w	r5, r0, r4, lsl #5
    338c:	682d      	ldr	r5, [r5, #0]
    338e:	428d      	cmp	r5, r1
    3390:	d015      	beq.n	33be <BP_AUD_MuxInId2Index@@Base+0x86>
    3392:	3301      	adds	r3, #1
    3394:	3020      	adds	r0, #32
    3396:	459e      	cmp	lr, r3
    3398:	d1f0      	bne.n	337c <BP_AUD_MuxInId2Index@@Base+0x44>
    339a:	2000      	movs	r0, #0
    339c:	bdb0      	pop	{r4, r5, r7, pc}
    339e:	f1be 0f01 	cmp.w	lr, #1
    33a2:	dbfa      	blt.n	339a <BP_AUD_MuxInId2Index@@Base+0x62>
    33a4:	6a58      	ldr	r0, [r3, #36]	@ 0x24
    33a6:	4418      	add	r0, r3
    33a8:	f100 0310 	add.w	r3, r0, #16
    33ac:	2000      	movs	r0, #0
    33ae:	681c      	ldr	r4, [r3, #0]
    33b0:	428c      	cmp	r4, r1
    33b2:	d007      	beq.n	33c4 <BP_AUD_MuxInId2Index@@Base+0x8c>
    33b4:	3001      	adds	r0, #1
    33b6:	3320      	adds	r3, #32
    33b8:	4570      	cmp	r0, lr
    33ba:	dbf8      	blt.n	33ae <BP_AUD_MuxInId2Index@@Base+0x76>
    33bc:	e7ed      	b.n	339a <BP_AUD_MuxInId2Index@@Base+0x62>
    33be:	ebac 0004 	sub.w	r0, ip, r4
    33c2:	4418      	add	r0, r3
    33c4:	6010      	str	r0, [r2, #0]
    33c6:	2000      	movs	r0, #0
    33c8:	bdb0      	pop	{r4, r5, r7, pc}
    33ca:	bf00      	nop
    33cc:	2b66      	cmp	r3, #102	@ 0x66
	...

000033d0 <BP_AUD_MuxOutId2Index@@Base>:
    33d0:	b5b0      	push	{r4, r5, r7, lr}
    33d2:	4603      	mov	r3, r0
    33d4:	4823      	ldr	r0, [pc, #140]	@ (3464 <BP_AUD_MuxOutId2Index@@Base+0x94>)
    33d6:	4478      	add	r0, pc
    33d8:	69c0      	ldr	r0, [r0, #28]
    33da:	2801      	cmp	r0, #1
    33dc:	bf1c      	itt	ne
    33de:	2011      	movne	r0, #17
    33e0:	bdb0      	popne	{r4, r5, r7, pc}
    33e2:	2b00      	cmp	r3, #0
    33e4:	f04f 0001 	mov.w	r0, #1
    33e8:	bf18      	it	ne
    33ea:	2a00      	cmpne	r2, #0
    33ec:	d100      	bne.n	33f0 <BP_AUD_MuxOutId2Index@@Base+0x20>
    33ee:	bdb0      	pop	{r4, r5, r7, pc}
    33f0:	f04f 30ff 	mov.w	r0, #4294967295	@ 0xffffffff
    33f4:	f1a1 0c01 	sub.w	ip, r1, #1
    33f8:	6010      	str	r0, [r2, #0]
    33fa:	f8d3 e028 	ldr.w	lr, [r3, #40]	@ 0x28
    33fe:	45f4      	cmp	ip, lr
    3400:	d219      	bcs.n	3436 <BP_AUD_MuxOutId2Index@@Base+0x66>
    3402:	f1be 0f01 	cmp.w	lr, #1
    3406:	db14      	blt.n	3432 <BP_AUD_MuxOutId2Index@@Base+0x62>
    3408:	6ad8      	ldr	r0, [r3, #44]	@ 0x2c
    340a:	eb00 1041 	add.w	r0, r0, r1, lsl #5
    340e:	4418      	add	r0, r3
    3410:	2300      	movs	r3, #0
    3412:	3810      	subs	r0, #16
    3414:	eb0c 0403 	add.w	r4, ip, r3
    3418:	4574      	cmp	r4, lr
    341a:	4674      	mov	r4, lr
    341c:	bfb8      	it	lt
    341e:	2400      	movlt	r4, #0
    3420:	eba0 1544 	sub.w	r5, r0, r4, lsl #5
    3424:	682d      	ldr	r5, [r5, #0]
    3426:	428d      	cmp	r5, r1
    3428:	d015      	beq.n	3456 <BP_AUD_MuxOutId2Index@@Base+0x86>
    342a:	3301      	adds	r3, #1
    342c:	3020      	adds	r0, #32
    342e:	459e      	cmp	lr, r3
    3430:	d1f0      	bne.n	3414 <BP_AUD_MuxOutId2Index@@Base+0x44>
    3432:	2000      	movs	r0, #0
    3434:	bdb0      	pop	{r4, r5, r7, pc}
    3436:	f1be 0f01 	cmp.w	lr, #1
    343a:	dbfa      	blt.n	3432 <BP_AUD_MuxOutId2Index@@Base+0x62>
    343c:	6ad8      	ldr	r0, [r3, #44]	@ 0x2c
    343e:	4418      	add	r0, r3
    3440:	f100 0310 	add.w	r3, r0, #16
    3444:	2000      	movs	r0, #0
    3446:	681c      	ldr	r4, [r3, #0]
    3448:	428c      	cmp	r4, r1
    344a:	d007      	beq.n	345c <BP_AUD_MuxOutId2Index@@Base+0x8c>
    344c:	3001      	adds	r0, #1
    344e:	3320      	adds	r3, #32
    3450:	4570      	cmp	r0, lr
    3452:	dbf8      	blt.n	3446 <BP_AUD_MuxOutId2Index@@Base+0x76>
    3454:	e7ed      	b.n	3432 <BP_AUD_MuxOutId2Index@@Base+0x62>
    3456:	ebac 0004 	sub.w	r0, ip, r4
    345a:	4418      	add	r0, r3
    345c:	6010      	str	r0, [r2, #0]
    345e:	2000      	movs	r0, #0
    3460:	bdb0      	pop	{r4, r5, r7, pc}
    3462:	bf00      	nop
    3464:	2ace      	cmp	r2, #206	@ 0xce
	...

00003468 <BP_AUD_GetNodeCount@@Base>:
    3468:	b5b0      	push	{r4, r5, r7, lr}
    346a:	4a12      	ldr	r2, [pc, #72]	@ (34b4 <BP_AUD_GetNodeCount@@Base+0x4c>)
    346c:	447a      	add	r2, pc
    346e:	69d3      	ldr	r3, [r2, #28]
    3470:	2b01      	cmp	r3, #1
    3472:	bf1c      	itt	ne
    3474:	2011      	movne	r0, #17
    3476:	bdb0      	popne	{r4, r5, r7, pc}
    3478:	b1b1      	cbz	r1, 34a8 <BP_AUD_GetNodeCount@@Base+0x40>
    347a:	6992      	ldr	r2, [r2, #24]
    347c:	f04f 33ff 	mov.w	r3, #4294967295	@ 0xffffffff
    3480:	600b      	str	r3, [r1, #0]
    3482:	f8d2 e008 	ldr.w	lr, [r2, #8]
    3486:	f1be 0f01 	cmp.w	lr, #1
    348a:	db0b      	blt.n	34a4 <BP_AUD_GetNodeCount@@Base+0x3c>
    348c:	f102 0c0c 	add.w	ip, r2, #12
    3490:	2300      	movs	r3, #0
    3492:	f85c 4023 	ldr.w	r4, [ip, r3, lsl #2]
    3496:	4414      	add	r4, r2
    3498:	6aa5      	ldr	r5, [r4, #40]	@ 0x28
    349a:	4285      	cmp	r5, r0
    349c:	d006      	beq.n	34ac <BP_AUD_GetNodeCount@@Base+0x44>
    349e:	3301      	adds	r3, #1
    34a0:	4573      	cmp	r3, lr
    34a2:	dbf6      	blt.n	3492 <BP_AUD_GetNodeCount@@Base+0x2a>
    34a4:	2000      	movs	r0, #0
    34a6:	bdb0      	pop	{r4, r5, r7, pc}
    34a8:	2001      	movs	r0, #1
    34aa:	bdb0      	pop	{r4, r5, r7, pc}
    34ac:	6ae0      	ldr	r0, [r4, #44]	@ 0x2c
    34ae:	6008      	str	r0, [r1, #0]
    34b0:	2000      	movs	r0, #0
    34b2:	bdb0      	pop	{r4, r5, r7, pc}
    34b4:	2a38      	cmp	r2, #56	@ 0x38
	...

000034b8 <BP_AUD_GetItemCount@@Base>:
    34b8:	e92d 43f0 	stmdb	sp!, {r4, r5, r6, r7, r8, r9, lr}
    34bc:	4b22      	ldr	r3, [pc, #136]	@ (3548 <BP_AUD_GetItemCount@@Base+0x90>)
    34be:	447b      	add	r3, pc
    34c0:	69df      	ldr	r7, [r3, #28]
    34c2:	2f01      	cmp	r7, #1
    34c4:	d136      	bne.n	3534 <BP_AUD_GetItemCount@@Base+0x7c>
    34c6:	b3da      	cbz	r2, 3540 <BP_AUD_GetItemCount@@Base+0x88>
    34c8:	f8d3 e018 	ldr.w	lr, [r3, #24]
    34cc:	f04f 33ff 	mov.w	r3, #4294967295	@ 0xffffffff
    34d0:	6013      	str	r3, [r2, #0]
    34d2:	f8de 4008 	ldr.w	r4, [lr, #8]
    34d6:	2c01      	cmp	r4, #1
    34d8:	db2f      	blt.n	353a <BP_AUD_GetItemCount@@Base+0x82>
    34da:	f10e 0c30 	add.w	ip, lr, #48	@ 0x30
    34de:	f04f 0800 	mov.w	r8, #0
    34e2:	e008      	b.n	34f6 <BP_AUD_GetItemCount@@Base+0x3e>
    34e4:	2500      	movs	r5, #0
    34e6:	454d      	cmp	r5, r9
    34e8:	db27      	blt.n	353a <BP_AUD_GetItemCount@@Base+0x82>
    34ea:	f8de 4008 	ldr.w	r4, [lr, #8]
    34ee:	f108 0801 	add.w	r8, r8, #1
    34f2:	45a0      	cmp	r8, r4
    34f4:	da21      	bge.n	353a <BP_AUD_GetItemCount@@Base+0x82>
    34f6:	eb0e 0388 	add.w	r3, lr, r8, lsl #2
    34fa:	68dd      	ldr	r5, [r3, #12]
    34fc:	eb0e 0605 	add.w	r6, lr, r5
    3500:	6ab3      	ldr	r3, [r6, #40]	@ 0x28
    3502:	4283      	cmp	r3, r0
    3504:	d1f3      	bne.n	34ee <BP_AUD_GetItemCount@@Base+0x36>
    3506:	f8d6 902c 	ldr.w	r9, [r6, #44]	@ 0x2c
    350a:	f1b9 0f01 	cmp.w	r9, #1
    350e:	dbe9      	blt.n	34e4 <BP_AUD_GetItemCount@@Base+0x2c>
    3510:	eb0c 0705 	add.w	r7, ip, r5
    3514:	2500      	movs	r5, #0
    3516:	f857 3025 	ldr.w	r3, [r7, r5, lsl #2]
    351a:	4433      	add	r3, r6
    351c:	6a5c      	ldr	r4, [r3, #36]	@ 0x24
    351e:	428c      	cmp	r4, r1
    3520:	d003      	beq.n	352a <BP_AUD_GetItemCount@@Base+0x72>
    3522:	3501      	adds	r5, #1
    3524:	454d      	cmp	r5, r9
    3526:	dbf6      	blt.n	3516 <BP_AUD_GetItemCount@@Base+0x5e>
    3528:	e7dd      	b.n	34e6 <BP_AUD_GetItemCount@@Base+0x2e>
    352a:	6adb      	ldr	r3, [r3, #44]	@ 0x2c
    352c:	6013      	str	r3, [r2, #0]
    352e:	f8d6 902c 	ldr.w	r9, [r6, #44]	@ 0x2c
    3532:	e7d8      	b.n	34e6 <BP_AUD_GetItemCount@@Base+0x2e>
    3534:	2011      	movs	r0, #17
    3536:	e8bd 83f0 	ldmia.w	sp!, {r4, r5, r6, r7, r8, r9, pc}
    353a:	2000      	movs	r0, #0
    353c:	e8bd 83f0 	ldmia.w	sp!, {r4, r5, r6, r7, r8, r9, pc}
    3540:	2001      	movs	r0, #1
    3542:	e8bd 83f0 	ldmia.w	sp!, {r4, r5, r6, r7, r8, r9, pc}
    3546:	bf00      	nop
    3548:	29e6      	cmp	r1, #230	@ 0xe6
	...

0000354c <BP_AUD_GetPathDirectorActionCount@@Base>:
    354c:	b5b0      	push	{r4, r5, r7, lr}
    354e:	4a12      	ldr	r2, [pc, #72]	@ (3598 <BP_AUD_GetPathDirectorActionCount@@Base+0x4c>)
    3550:	447a      	add	r2, pc
    3552:	69d3      	ldr	r3, [r2, #28]
    3554:	2b01      	cmp	r3, #1
    3556:	bf1c      	itt	ne
    3558:	2011      	movne	r0, #17
    355a:	bdb0      	popne	{r4, r5, r7, pc}
    355c:	b1a9      	cbz	r1, 358a <BP_AUD_GetPathDirectorActionCount@@Base+0x3e>
    355e:	6912      	ldr	r2, [r2, #16]
    3560:	f8d2 c008 	ldr.w	ip, [r2, #8]
    3564:	f1bc 0f01 	cmp.w	ip, #1
    3568:	db0b      	blt.n	3582 <BP_AUD_GetPathDirectorActionCount@@Base+0x36>
    356a:	f102 0e0c 	add.w	lr, r2, #12
    356e:	2300      	movs	r3, #0
    3570:	f85e 4023 	ldr.w	r4, [lr, r3, lsl #2]
    3574:	4414      	add	r4, r2
    3576:	69e5      	ldr	r5, [r4, #28]
    3578:	4285      	cmp	r5, r0
    357a:	d008      	beq.n	358e <BP_AUD_GetPathDirectorActionCount@@Base+0x42>
    357c:	3301      	adds	r3, #1
    357e:	4563      	cmp	r3, ip
    3580:	dbf6      	blt.n	3570 <BP_AUD_GetPathDirectorActionCount@@Base+0x24>
    3582:	2000      	movs	r0, #0
    3584:	6008      	str	r0, [r1, #0]
    3586:	2012      	movs	r0, #18
    3588:	bdb0      	pop	{r4, r5, r7, pc}
    358a:	2001      	movs	r0, #1
    358c:	bdb0      	pop	{r4, r5, r7, pc}
    358e:	6ae0      	ldr	r0, [r4, #44]	@ 0x2c
    3590:	6008      	str	r0, [r1, #0]
    3592:	2000      	movs	r0, #0
    3594:	bdb0      	pop	{r4, r5, r7, pc}
    3596:	bf00      	nop
    3598:	2954      	cmp	r1, #84	@ 0x54
	...

0000359c <BP_AUD_GetPathDirectorActionByIndex@@Base>:
    359c:	b570      	push	{r4, r5, r6, lr}
    359e:	4b17      	ldr	r3, [pc, #92]	@ (35fc <BP_AUD_GetPathDirectorActionByIndex@@Base+0x60>)
    35a0:	447b      	add	r3, pc
    35a2:	69dd      	ldr	r5, [r3, #28]
    35a4:	2d01      	cmp	r5, #1
    35a6:	bf1c      	itt	ne
    35a8:	2011      	movne	r0, #17
    35aa:	bd70      	popne	{r4, r5, r6, pc}
    35ac:	b1aa      	cbz	r2, 35da <BP_AUD_GetPathDirectorActionByIndex@@Base+0x3e>
    35ae:	691b      	ldr	r3, [r3, #16]
    35b0:	f8d3 c008 	ldr.w	ip, [r3, #8]
    35b4:	f1bc 0f01 	cmp.w	ip, #1
    35b8:	db0b      	blt.n	35d2 <BP_AUD_GetPathDirectorActionByIndex@@Base+0x36>
    35ba:	f103 0e0c 	add.w	lr, r3, #12
    35be:	2400      	movs	r4, #0
    35c0:	f85e 5024 	ldr.w	r5, [lr, r4, lsl #2]
    35c4:	441d      	add	r5, r3
    35c6:	69ee      	ldr	r6, [r5, #28]
    35c8:	4286      	cmp	r6, r0
    35ca:	d008      	beq.n	35de <BP_AUD_GetPathDirectorActionByIndex@@Base+0x42>
    35cc:	3401      	adds	r4, #1
    35ce:	4564      	cmp	r4, ip
    35d0:	dbf6      	blt.n	35c0 <BP_AUD_GetPathDirectorActionByIndex@@Base+0x24>
    35d2:	2000      	movs	r0, #0
    35d4:	6010      	str	r0, [r2, #0]
    35d6:	2012      	movs	r0, #18
    35d8:	bd70      	pop	{r4, r5, r6, pc}
    35da:	2001      	movs	r0, #1
    35dc:	bd70      	pop	{r4, r5, r6, pc}
    35de:	6ae8      	ldr	r0, [r5, #44]	@ 0x2c
    35e0:	4288      	cmp	r0, r1
    35e2:	d906      	bls.n	35f2 <BP_AUD_GetPathDirectorActionByIndex@@Base+0x56>
    35e4:	eb05 0081 	add.w	r0, r5, r1, lsl #2
    35e8:	6b00      	ldr	r0, [r0, #48]	@ 0x30
    35ea:	4428      	add	r0, r5
    35ec:	6010      	str	r0, [r2, #0]
    35ee:	2000      	movs	r0, #0
    35f0:	bd70      	pop	{r4, r5, r6, pc}
    35f2:	2000      	movs	r0, #0
    35f4:	6010      	str	r0, [r2, #0]
    35f6:	2013      	movs	r0, #19
    35f8:	bd70      	pop	{r4, r5, r6, pc}
    35fa:	bf00      	nop
    35fc:	2904      	cmp	r1, #4
	...

00003600 <BP_AUD_GetMuxDirector@@Base>:
    3600:	b570      	push	{r4, r5, r6, lr}
    3602:	4b19      	ldr	r3, [pc, #100]	@ (3668 <BP_AUD_GetMuxDirector@@Base+0x68>)
    3604:	447b      	add	r3, pc
    3606:	69dd      	ldr	r5, [r3, #28]
    3608:	2d01      	cmp	r5, #1
    360a:	bf1c      	itt	ne
    360c:	2011      	movne	r0, #17
    360e:	bd70      	popne	{r4, r5, r6, pc}
    3610:	2900      	cmp	r1, #0
    3612:	bf02      	ittt	eq
    3614:	2a00      	cmpeq	r2, #0
    3616:	2001      	moveq	r0, #1
    3618:	bd70      	popeq	{r4, r5, r6, pc}
    361a:	691b      	ldr	r3, [r3, #16]
    361c:	f8d3 c008 	ldr.w	ip, [r3, #8]
    3620:	f1bc 0f01 	cmp.w	ip, #1
    3624:	db0b      	blt.n	363e <BP_AUD_GetMuxDirector@@Base+0x3e>
    3626:	f103 0e0c 	add.w	lr, r3, #12
    362a:	2400      	movs	r4, #0
    362c:	f85e 5024 	ldr.w	r5, [lr, r4, lsl #2]
    3630:	441d      	add	r5, r3
    3632:	69ee      	ldr	r6, [r5, #28]
    3634:	4286      	cmp	r6, r0
    3636:	d00c      	beq.n	3652 <BP_AUD_GetMuxDirector@@Base+0x52>
    3638:	3401      	adds	r4, #1
    363a:	4564      	cmp	r4, ip
    363c:	dbf6      	blt.n	362c <BP_AUD_GetMuxDirector@@Base+0x2c>
    363e:	2900      	cmp	r1, #0
    3640:	bf1c      	itt	ne
    3642:	2000      	movne	r0, #0
    3644:	6008      	strne	r0, [r1, #0]
    3646:	2a00      	cmp	r2, #0
    3648:	bf1c      	itt	ne
    364a:	2000      	movne	r0, #0
    364c:	6010      	strne	r0, [r2, #0]
    364e:	2012      	movs	r0, #18
    3650:	bd70      	pop	{r4, r5, r6, pc}
    3652:	2900      	cmp	r1, #0
    3654:	bf1c      	itt	ne
    3656:	6a68      	ldrne	r0, [r5, #36]	@ 0x24
    3658:	6008      	strne	r0, [r1, #0]
    365a:	b112      	cbz	r2, 3662 <BP_AUD_GetMuxDirector@@Base+0x62>
    365c:	6aa8      	ldr	r0, [r5, #40]	@ 0x28
    365e:	4428      	add	r0, r5
    3660:	6010      	str	r0, [r2, #0]
    3662:	2000      	movs	r0, #0
    3664:	bd70      	pop	{r4, r5, r6, pc}
    3666:	bf00      	nop
    3668:	28a0      	cmp	r0, #160	@ 0xa0
	...

0000366c <BP_AUD_GetPathDeviceIndex@@Base>:
    366c:	b5f0      	push	{r4, r5, r6, r7, lr}
    366e:	468c      	mov	ip, r1
    3670:	4917      	ldr	r1, [pc, #92]	@ (36d0 <BP_AUD_GetPathDeviceIndex@@Base+0x64>)
    3672:	4479      	add	r1, pc
    3674:	69ca      	ldr	r2, [r1, #28]
    3676:	2a01      	cmp	r2, #1
    3678:	bf1c      	itt	ne
    367a:	2011      	movne	r0, #17
    367c:	bdf0      	popne	{r4, r5, r6, r7, pc}
    367e:	f1bc 0f00 	cmp.w	ip, #0
    3682:	d014      	beq.n	36ae <BP_AUD_GetPathDeviceIndex@@Base+0x42>
    3684:	690b      	ldr	r3, [r1, #16]
    3686:	689a      	ldr	r2, [r3, #8]
    3688:	b15a      	cbz	r2, 36a2 <BP_AUD_GetPathDeviceIndex@@Base+0x36>
    368a:	f103 040c 	add.w	r4, r3, #12
    368e:	2500      	movs	r5, #0
    3690:	f854 6025 	ldr.w	r6, [r4, r5, lsl #2]
    3694:	441e      	add	r6, r3
    3696:	69f7      	ldr	r7, [r6, #28]
    3698:	4287      	cmp	r7, r0
    369a:	d00a      	beq.n	36b2 <BP_AUD_GetPathDeviceIndex@@Base+0x46>
    369c:	3501      	adds	r5, #1
    369e:	4295      	cmp	r5, r2
    36a0:	d3f6      	bcc.n	3690 <BP_AUD_GetPathDeviceIndex@@Base+0x24>
    36a2:	f04f 30ff 	mov.w	r0, #4294967295	@ 0xffffffff
    36a6:	f8cc 0000 	str.w	r0, [ip]
    36aa:	2012      	movs	r0, #18
    36ac:	bdf0      	pop	{r4, r5, r6, r7, pc}
    36ae:	2001      	movs	r0, #1
    36b0:	bdf0      	pop	{r4, r5, r6, r7, pc}
    36b2:	68c9      	ldr	r1, [r1, #12]
    36b4:	6a30      	ldr	r0, [r6, #32]
    36b6:	6889      	ldr	r1, [r1, #8]
    36b8:	4288      	cmp	r0, r1
    36ba:	d203      	bcs.n	36c4 <BP_AUD_GetPathDeviceIndex@@Base+0x58>
    36bc:	f8cc 0000 	str.w	r0, [ip]
    36c0:	2000      	movs	r0, #0
    36c2:	bdf0      	pop	{r4, r5, r6, r7, pc}
    36c4:	f04f 30ff 	mov.w	r0, #4294967295	@ 0xffffffff
    36c8:	f8cc 0000 	str.w	r0, [ip]
    36cc:	2015      	movs	r0, #21
    36ce:	bdf0      	pop	{r4, r5, r6, r7, pc}
    36d0:	2832      	cmp	r0, #50	@ 0x32
	...

000036d4 <BP_AUD_GetPathName@@Base>:
    36d4:	b580      	push	{r7, lr}
    36d6:	4a11      	ldr	r2, [pc, #68]	@ (371c <BP_AUD_GetPathName@@Base+0x48>)
    36d8:	447a      	add	r2, pc
    36da:	69d3      	ldr	r3, [r2, #28]
    36dc:	2b01      	cmp	r3, #1
    36de:	bf1c      	itt	ne
    36e0:	2011      	movne	r0, #17
    36e2:	bd80      	popne	{r7, pc}
    36e4:	2900      	cmp	r1, #0
    36e6:	bf04      	itt	eq
    36e8:	2001      	moveq	r0, #1
    36ea:	bd80      	popeq	{r7, pc}
    36ec:	6911      	ldr	r1, [r2, #16]
    36ee:	f8d1 e008 	ldr.w	lr, [r1, #8]
    36f2:	f1be 0f01 	cmp.w	lr, #1
    36f6:	bfbc      	itt	lt
    36f8:	2012      	movlt	r0, #18
    36fa:	bd80      	poplt	{r7, pc}
    36fc:	f101 0c0c 	add.w	ip, r1, #12
    3700:	2300      	movs	r3, #0
    3702:	f85c 2023 	ldr.w	r2, [ip, r3, lsl #2]
    3706:	440a      	add	r2, r1
    3708:	69d2      	ldr	r2, [r2, #28]
    370a:	4282      	cmp	r2, r0
    370c:	d004      	beq.n	3718 <BP_AUD_GetPathName@@Base+0x44>
    370e:	3301      	adds	r3, #1
    3710:	4573      	cmp	r3, lr
    3712:	dbf6      	blt.n	3702 <BP_AUD_GetPathName@@Base+0x2e>
    3714:	2012      	movs	r0, #18
    3716:	bd80      	pop	{r7, pc}
    3718:	2000      	movs	r0, #0
    371a:	bd80      	pop	{r7, pc}
    371c:	27cc      	movs	r7, #204	@ 0xcc
	...

00003720 <BP_AUD_IsValidPath@@Base>:
    3720:	b510      	push	{r4, lr}
    3722:	4a14      	ldr	r2, [pc, #80]	@ (3774 <BP_AUD_IsValidPath@@Base+0x54>)
    3724:	447a      	add	r2, pc
    3726:	69d3      	ldr	r3, [r2, #28]
    3728:	2b01      	cmp	r3, #1
    372a:	bf1c      	itt	ne
    372c:	2011      	movne	r0, #17
    372e:	bd10      	popne	{r4, pc}
    3730:	2900      	cmp	r1, #0
    3732:	bf04      	itt	eq
    3734:	2001      	moveq	r0, #1
    3736:	bd10      	popeq	{r4, pc}
    3738:	6912      	ldr	r2, [r2, #16]
    373a:	f8d2 e008 	ldr.w	lr, [r2, #8]
    373e:	f1be 0f01 	cmp.w	lr, #1
    3742:	db0b      	blt.n	375c <BP_AUD_IsValidPath@@Base+0x3c>
    3744:	f102 0c0c 	add.w	ip, r2, #12
    3748:	2300      	movs	r3, #0
    374a:	f85c 4023 	ldr.w	r4, [ip, r3, lsl #2]
    374e:	4414      	add	r4, r2
    3750:	69e4      	ldr	r4, [r4, #28]
    3752:	4284      	cmp	r4, r0
    3754:	d004      	beq.n	3760 <BP_AUD_IsValidPath@@Base+0x40>
    3756:	3301      	adds	r3, #1
    3758:	4573      	cmp	r3, lr
    375a:	dbf6      	blt.n	374a <BP_AUD_IsValidPath@@Base+0x2a>
    375c:	2200      	movs	r2, #0
    375e:	e000      	b.n	3762 <BP_AUD_IsValidPath@@Base+0x42>
    3760:	2201      	movs	r2, #1
    3762:	f1b0 30ff 	subs.w	r0, r0, #4294967295	@ 0xffffffff
    3766:	bf18      	it	ne
    3768:	2001      	movne	r0, #1
    376a:	4010      	ands	r0, r2
    376c:	7008      	strb	r0, [r1, #0]
    376e:	2000      	movs	r0, #0
    3770:	bd10      	pop	{r4, pc}
    3772:	bf00      	nop
    3774:	2780      	movs	r7, #128	@ 0x80
	...

00003778 <BP_AUD_GetYBin@@Base>:
    3778:	2900      	cmp	r1, #0
    377a:	bf04      	itt	eq
    377c:	2001      	moveq	r0, #1
    377e:	4770      	bxeq	lr
    3780:	4a07      	ldr	r2, [pc, #28]	@ (37a0 <BP_AUD_GetYBin@@Base+0x28>)
    3782:	447a      	add	r2, pc
    3784:	6952      	ldr	r2, [r2, #20]
    3786:	6893      	ldr	r3, [r2, #8]
    3788:	4283      	cmp	r3, r0
    378a:	bf9c      	itt	ls
    378c:	2014      	movls	r0, #20
    378e:	4770      	bxls	lr
    3790:	eb02 0080 	add.w	r0, r2, r0, lsl #2
    3794:	68c0      	ldr	r0, [r0, #12]
    3796:	4410      	add	r0, r2
    3798:	6008      	str	r0, [r1, #0]
    379a:	2000      	movs	r0, #0
    379c:	4770      	bx	lr
    379e:	bf00      	nop
    37a0:	2722      	movs	r7, #34	@ 0x22
	...

000037a4 <BP_AUD_GetYBinCount@@Base>:
    37a4:	2800      	cmp	r0, #0
    37a6:	bf04      	itt	eq
    37a8:	2001      	moveq	r0, #1
    37aa:	4770      	bxeq	lr
    37ac:	4903      	ldr	r1, [pc, #12]	@ (37bc <BP_AUD_GetYBinCount@@Base+0x18>)
    37ae:	4479      	add	r1, pc
    37b0:	6949      	ldr	r1, [r1, #20]
    37b2:	6889      	ldr	r1, [r1, #8]
    37b4:	6001      	str	r1, [r0, #0]
    37b6:	2000      	movs	r0, #0
    37b8:	4770      	bx	lr
    37ba:	bf00      	nop
    37bc:	26f6      	movs	r6, #246	@ 0xf6
	...

000037c0 <BP_AUD_GetDeviceCount@@Base>:
    37c0:	2800      	cmp	r0, #0
    37c2:	bf04      	itt	eq
    37c4:	2001      	moveq	r0, #1
    37c6:	4770      	bxeq	lr
    37c8:	4903      	ldr	r1, [pc, #12]	@ (37d8 <BP_AUD_GetDeviceCount@@Base+0x18>)
    37ca:	4479      	add	r1, pc
    37cc:	68c9      	ldr	r1, [r1, #12]
    37ce:	6889      	ldr	r1, [r1, #8]
    37d0:	6001      	str	r1, [r0, #0]
    37d2:	2000      	movs	r0, #0
    37d4:	4770      	bx	lr
    37d6:	bf00      	nop
    37d8:	26da      	movs	r6, #218	@ 0xda
	...

000037dc <BP_AUD_GetDevice@@Base>:
    37dc:	2900      	cmp	r1, #0
    37de:	bf04      	itt	eq
    37e0:	2001      	moveq	r0, #1
    37e2:	4770      	bxeq	lr
    37e4:	4a07      	ldr	r2, [pc, #28]	@ (3804 <BP_AUD_GetDevice@@Base+0x28>)
    37e6:	447a      	add	r2, pc
    37e8:	68d2      	ldr	r2, [r2, #12]
    37ea:	6893      	ldr	r3, [r2, #8]
    37ec:	4283      	cmp	r3, r0
    37ee:	bf9c      	itt	ls
    37f0:	2015      	movls	r0, #21
    37f2:	4770      	bxls	lr
    37f4:	eb02 0080 	add.w	r0, r2, r0, lsl #2
    37f8:	68c0      	ldr	r0, [r0, #12]
    37fa:	4410      	add	r0, r2
    37fc:	6008      	str	r0, [r1, #0]
    37fe:	2000      	movs	r0, #0
    3800:	4770      	bx	lr
    3802:	bf00      	nop
    3804:	26be      	movs	r6, #190	@ 0xbe
	...

00003808 <BP_AUD_GetUserDataByName@@Base>:
    3808:	e92d 47f0 	stmdb	sp!, {r4, r5, r6, r7, r8, r9, sl, lr}
    380c:	b082      	sub	sp, #8
    380e:	4688      	mov	r8, r1
    3810:	4923      	ldr	r1, [pc, #140]	@ (38a0 <BP_AUD_GetUserDataByName@@Base+0x98>)
    3812:	4605      	mov	r5, r0
    3814:	4479      	add	r1, pc
    3816:	69c8      	ldr	r0, [r1, #28]
    3818:	2801      	cmp	r0, #1
    381a:	d109      	bne.n	3830 <BP_AUD_GetUserDataByName@@Base+0x28>
    381c:	2d00      	cmp	r5, #0
    381e:	f04f 0001 	mov.w	r0, #1
    3822:	bf18      	it	ne
    3824:	f1b8 0f00 	cmpne.w	r8, #0
    3828:	d117      	bne.n	385a <BP_AUD_GetUserDataByName@@Base+0x52>
    382a:	b002      	add	sp, #8
    382c:	e8bd 87f0 	ldmia.w	sp!, {r4, r5, r6, r7, r8, r9, sl, pc}
    3830:	481c      	ldr	r0, [pc, #112]	@ (38a4 <BP_AUD_GetUserDataByName@@Base+0x9c>)
    3832:	f44f 7749 	mov.w	r7, #804	@ 0x324
    3836:	4a1c      	ldr	r2, [pc, #112]	@ (38a8 <BP_AUD_GetUserDataByName@@Base+0xa0>)
    3838:	4478      	add	r0, pc
    383a:	4b1c      	ldr	r3, [pc, #112]	@ (38ac <BP_AUD_GetUserDataByName@@Base+0xa4>)
    383c:	447a      	add	r2, pc
    383e:	6800      	ldr	r0, [r0, #0]
    3840:	447b      	add	r3, pc
    3842:	6800      	ldr	r0, [r0, #0]
    3844:	491a      	ldr	r1, [pc, #104]	@ (38b0 <BP_AUD_GetUserDataByName@@Base+0xa8>)
    3846:	4479      	add	r1, pc
    3848:	e9cd 7100 	strd	r7, r1, [sp]
    384c:	2101      	movs	r1, #1
    384e:	f000 e8d8 	blx	3a00 <trid_debug_log>
    3852:	2011      	movs	r0, #17
    3854:	b002      	add	sp, #8
    3856:	e8bd 87f0 	ldmia.w	sp!, {r4, r5, r6, r7, r8, r9, sl, pc}
    385a:	698c      	ldr	r4, [r1, #24]
    385c:	f8d4 9008 	ldr.w	r9, [r4, #8]
    3860:	f1b9 0f01 	cmp.w	r9, #1
    3864:	db0e      	blt.n	3884 <BP_AUD_GetUserDataByName@@Base+0x7c>
    3866:	f104 0a0c 	add.w	sl, r4, #12
    386a:	2700      	movs	r7, #0
    386c:	f85a 0027 	ldr.w	r0, [sl, r7, lsl #2]
    3870:	4629      	mov	r1, r5
    3872:	1826      	adds	r6, r4, r0
    3874:	1d30      	adds	r0, r6, #4
    3876:	f000 e8d4 	blx	3a20 <strcmp>
    387a:	b128      	cbz	r0, 3888 <BP_AUD_GetUserDataByName@@Base+0x80>
    387c:	3701      	adds	r7, #1
    387e:	454f      	cmp	r7, r9
    3880:	dbf4      	blt.n	386c <BP_AUD_GetUserDataByName@@Base+0x64>
    3882:	e005      	b.n	3890 <BP_AUD_GetUserDataByName@@Base+0x88>
    3884:	2700      	movs	r7, #0
    3886:	e003      	b.n	3890 <BP_AUD_GetUserDataByName@@Base+0x88>
    3888:	f8c8 6000 	str.w	r6, [r8]
    388c:	f8d4 9008 	ldr.w	r9, [r4, #8]
    3890:	2016      	movs	r0, #22
    3892:	454f      	cmp	r7, r9
    3894:	bf38      	it	cc
    3896:	2000      	movcc	r0, #0
    3898:	b002      	add	sp, #8
    389a:	e8bd 87f0 	ldmia.w	sp!, {r4, r5, r6, r7, r8, r9, sl, pc}
    389e:	bf00      	nop
    38a0:	2690      	movs	r6, #144	@ 0x90
    38a2:	0000      	movs	r0, r0
    38a4:	1640      	asrs	r0, r0, #25
    38a6:	0000      	movs	r0, r0
    38a8:	e172      	b.n	3b90 <BP_AUD_GetYBinByIndicator@@Base+0x274>
    38aa:	ffff e246 	vmlal.u<illegal width 64>	q15, d15, d6[0]
    38ae:	ffff e1d5 	vsra.u64	q15, <illegal reg q2.5>, #1
    38b2:	Address 0x38b2 is out of bounds.


000038b4 <BP_AUD_GetDataNodeByIndex@@Base>:
    38b4:	4684      	mov	ip, r0
    38b6:	f1bc 0f00 	cmp.w	ip, #0
    38ba:	f04f 0001 	mov.w	r0, #1
    38be:	bf18      	it	ne
    38c0:	2a00      	cmpne	r2, #0
    38c2:	d100      	bne.n	38c6 <BP_AUD_GetDataNodeByIndex@@Base+0x12>
    38c4:	4770      	bx	lr
    38c6:	2001      	movs	r0, #1
    38c8:	2900      	cmp	r1, #0
    38ca:	bf48      	it	mi
    38cc:	4770      	bxmi	lr
    38ce:	f8dc 302c 	ldr.w	r3, [ip, #44]	@ 0x2c
    38d2:	428b      	cmp	r3, r1
    38d4:	bf81      	itttt	hi
    38d6:	eb0c 0081 	addhi.w	r0, ip, r1, lsl #2
    38da:	6b00      	ldrhi	r0, [r0, #48]	@ 0x30
    38dc:	4460      	addhi	r0, ip
    38de:	6010      	strhi	r0, [r2, #0]
    38e0:	bf88      	it	hi
    38e2:	2000      	movhi	r0, #0
    38e4:	4770      	bx	lr

000038e6 <BP_AUD_GetNodeItemByIndex@@Base>:
    38e6:	4684      	mov	ip, r0
    38e8:	f1bc 0f00 	cmp.w	ip, #0
    38ec:	f04f 0001 	mov.w	r0, #1
    38f0:	bf18      	it	ne
    38f2:	2a00      	cmpne	r2, #0
    38f4:	d100      	bne.n	38f8 <BP_AUD_GetNodeItemByIndex@@Base+0x12>
    38f6:	4770      	bx	lr
    38f8:	2001      	movs	r0, #1
    38fa:	2900      	cmp	r1, #0
    38fc:	bf48      	it	mi
    38fe:	4770      	bxmi	lr
    3900:	f8dc 302c 	ldr.w	r3, [ip, #44]	@ 0x2c
    3904:	428b      	cmp	r3, r1
    3906:	bf81      	itttt	hi
    3908:	eb01 00c1 	addhi.w	r0, r1, r1, lsl #3
    390c:	eb0c 0080 	addhi.w	r0, ip, r0, lsl #2
    3910:	3030      	addhi	r0, #48	@ 0x30
    3912:	6010      	strhi	r0, [r2, #0]
    3914:	bf88      	it	hi
    3916:	2000      	movhi	r0, #0
    3918:	4770      	bx	lr
    391a:	d4d4      	bmi.n	38c6 <BP_AUD_GetDataNodeByIndex@@Base+0x12>

0000391c <BP_AUD_GetYBinByIndicator@@Base>:
    391c:	e92d 4ff0 	stmdb	sp!, {r4, r5, r6, r7, r8, r9, sl, fp, lr}
    3920:	b081      	sub	sp, #4
    3922:	4682      	mov	sl, r0
    3924:	f1ba 0f00 	cmp.w	sl, #0
    3928:	f04f 0001 	mov.w	r0, #1
    392c:	bf1c      	itt	ne
    392e:	4690      	movne	r8, r2
    3930:	2a00      	cmpne	r2, #0
    3932:	d102      	bne.n	393a <BP_AUD_GetYBinByIndicator@@Base+0x1e>
    3934:	b001      	add	sp, #4
    3936:	e8bd 8ff0 	ldmia.w	sp!, {r4, r5, r6, r7, r8, r9, sl, fp, pc}
    393a:	4814      	ldr	r0, [pc, #80]	@ (398c <BP_AUD_GetYBinByIndicator@@Base+0x70>)
    393c:	4478      	add	r0, pc
    393e:	6947      	ldr	r7, [r0, #20]
    3940:	f8d7 b008 	ldr.w	fp, [r7, #8]
    3944:	f1bb 0f00 	cmp.w	fp, #0
    3948:	d013      	beq.n	3972 <BP_AUD_GetYBinByIndicator@@Base+0x56>
    394a:	f107 050c 	add.w	r5, r7, #12
    394e:	4689      	mov	r9, r1
    3950:	2600      	movs	r6, #0
    3952:	f855 0026 	ldr.w	r0, [r5, r6, lsl #2]
    3956:	220f      	movs	r2, #15
    3958:	183c      	adds	r4, r7, r0
    395a:	4650      	mov	r0, sl
    395c:	1d21      	adds	r1, r4, #4
    395e:	f000 e858 	blx	3a10 <strncmp>
    3962:	2800      	cmp	r0, #0
    3964:	bf04      	itt	eq
    3966:	69a0      	ldreq	r0, [r4, #24]
    3968:	4548      	cmpeq	r0, r9
    396a:	d009      	beq.n	3980 <BP_AUD_GetYBinByIndicator@@Base+0x64>
    396c:	3601      	adds	r6, #1
    396e:	455e      	cmp	r6, fp
    3970:	d3ef      	bcc.n	3952 <BP_AUD_GetYBinByIndicator@@Base+0x36>
    3972:	2000      	movs	r0, #0
    3974:	f8c8 0000 	str.w	r0, [r8]
    3978:	2017      	movs	r0, #23
    397a:	b001      	add	sp, #4
    397c:	e8bd 8ff0 	ldmia.w	sp!, {r4, r5, r6, r7, r8, r9, sl, fp, pc}
    3980:	f8c8 4000 	str.w	r4, [r8]
    3984:	2000      	movs	r0, #0
    3986:	b001      	add	sp, #4
    3988:	e8bd 8ff0 	ldmia.w	sp!, {r4, r5, r6, r7, r8, r9, sl, fp, pc}
    398c:	2568      	movs	r5, #104	@ 0x68
    398e:	0000      	movs	r0, r0
    3990:	f240 0c34 	movw	ip, #52	@ 0x34
    3994:	f2c0 0c00 	movt	ip, #0
    3998:	44fc      	add	ip, pc
    399a:	4760      	bx	ip
    399c:	f240 0c38 	movw	ip, #56	@ 0x38
    39a0:	f2c0 0c00 	movt	ip, #0
    39a4:	44fc      	add	ip, pc
    39a6:	4760      	bx	ip

Disassembly of section .plt:

000039b0 <.plt>:
    39b0:	e52de004 	push	{lr}		@ (str lr, [sp, #-4]!)
    39b4:	e28fe600 	add	lr, pc, #0, 12
    39b8:	e28eea01 	add	lr, lr, #4096	@ 0x1000
    39bc:	e5bef4cc 	ldr	pc, [lr, #1228]!	@ 0x4cc
    39c0:	d4d4d4d4 	ldrble	sp, [r4], #1236	@ 0x4d4
    39c4:	d4d4d4d4 	ldrble	sp, [r4], #1236	@ 0x4d4
    39c8:	d4d4d4d4 	ldrble	sp, [r4], #1236	@ 0x4d4
    39cc:	d4d4d4d4 	ldrble	sp, [r4], #1236	@ 0x4d4
    39d0:	e28fc600 	add	ip, pc, #0, 12
    39d4:	e28cca01 	add	ip, ip, #4096	@ 0x1000
    39d8:	e5bcf4b4 	ldr	pc, [ip, #1204]!	@ 0x4b4
    39dc:	d4d4d4d4 	ldrble	sp, [r4], #1236	@ 0x4d4
    39e0:	e28fc600 	add	ip, pc, #0, 12
    39e4:	e28cca01 	add	ip, ip, #4096	@ 0x1000
    39e8:	e5bcf4a8 	ldr	pc, [ip, #1192]!	@ 0x4a8
    39ec:	d4d4d4d4 	ldrble	sp, [r4], #1236	@ 0x4d4
    39f0:	e28fc600 	add	ip, pc, #0, 12
    39f4:	e28cca01 	add	ip, ip, #4096	@ 0x1000
    39f8:	e5bcf49c 	ldr	pc, [ip, #1180]!	@ 0x49c
    39fc:	d4d4d4d4 	ldrble	sp, [r4], #1236	@ 0x4d4
    3a00:	e28fc600 	add	ip, pc, #0, 12
    3a04:	e28cca01 	add	ip, ip, #4096	@ 0x1000
    3a08:	e5bcf490 	ldr	pc, [ip, #1168]!	@ 0x490
    3a0c:	d4d4d4d4 	ldrble	sp, [r4], #1236	@ 0x4d4
    3a10:	e28fc600 	add	ip, pc, #0, 12
    3a14:	e28cca01 	add	ip, ip, #4096	@ 0x1000
    3a18:	e5bcf484 	ldr	pc, [ip, #1156]!	@ 0x484
    3a1c:	d4d4d4d4 	ldrble	sp, [r4], #1236	@ 0x4d4
    3a20:	e28fc600 	add	ip, pc, #0, 12
    3a24:	e28cca01 	add	ip, ip, #4096	@ 0x1000
    3a28:	e5bcf478 	ldr	pc, [ip, #1144]!	@ 0x478
    3a2c:	d4d4d4d4 	ldrble	sp, [r4], #1236	@ 0x4d4
