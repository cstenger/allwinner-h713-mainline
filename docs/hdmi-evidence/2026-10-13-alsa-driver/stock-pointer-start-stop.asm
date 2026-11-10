
local/h713-lab/extracted/stock-super/vendor/lib/modules/snd_alsa_trid.ko:	file format elf32-littlearm

Disassembly of section .text:

00003b18 <audbrg_ostream_flush>:
    3b18:      	push	{r4, r5, r6, lr}
    3b1c:      	str	lr, [sp, #-0x4]!
    3b20:      	bl	0x3b20 <audbrg_ostream_flush+0x8> @ imm = #-0x8
			00003b20:  R_ARM_CALL	__gnu_mcount_nc
    3b24:      	ldr	r4, [pc, #0x74]         @ 0x3ba0 <audbrg_ostream_flush+0x88>
    3b28:      	lsl	r3, r0, #6
    3b2c:      	mov	r2, #1
    3b30:      	mov	r1, r2
    3b34:      	add	r4, r3, r4
    3b38:      	mov	r5, r0
    3b3c:      	mov	r0, r4
    3b40:      	bl	0x3b40 <audbrg_ostream_flush+0x28> @ imm = #-0x8
			00003b40:  R_ARM_CALL	REG_Write_Mask
    3b44:      	mov	r2, #1
    3b48:      	mov	r1, #0
    3b4c:      	mov	r0, r4
    3b50:      	bl	0x3b50 <audbrg_ostream_flush+0x38> @ imm = #-0x8
			00003b50:  R_ARM_CALL	REG_Write_Mask
    3b54:      	mov	r0, #68
    3b58:      	ldr	r3, [pc, #0x44]         @ 0x3ba4 <audbrg_ostream_flush+0x8c>
    3b5c:      	mul	r0, r0, r5
    3b60:      	add	r2, r3, r0
    3b64:      	ldr	r1, [r2, #0x4]
    3b68:      	str	r1, [r2, #0x2c]
    3b6c:      	str	r1, [r2, #0x28]
    3b70:      	add	r2, r0, #48
    3b74:      	add	r0, r0, #64
    3b78:      	add	r2, r3, r2
    3b7c:      	add	r0, r3, r0
    3b80:      	ldr	r3, [r2, #0x4]!
    3b84:      	cmp	r3, #0
    3b88:      	ldrne	r1, [r3]
    3b8c:      	strne	r1, [r3, #0xc]
    3b90:      	strne	r1, [r3, #0x8]
    3b94:      	cmp	r2, r0
    3b98:      	bne	0x3b80 <audbrg_ostream_flush+0x68> @ imm = #-0x20
    3b9c:      	pop	{r4, r5, r6, pc}

00003cc0 <audbrg_ostream_start>:
    3cc0:      	push	{r4, r5, r6, lr}
    3cc4:      	str	lr, [sp, #-0x4]!
    3cc8:      	bl	0x3cc8 <audbrg_ostream_start+0x8> @ imm = #-0x8
			00003cc8:  R_ARM_CALL	__gnu_mcount_nc
    3ccc:      	cmp	r0, #0
    3cd0:      	beq	0x3d34 <audbrg_ostream_start+0x74> @ imm = #0x5c
    3cd4:      	ldr	r4, [r0, #0x30]
    3cd8:      	cmp	r4, #0
    3cdc:      	bne	0x3d3c <audbrg_ostream_start+0x7c> @ imm = #0x58
    3ce0:      	ldr	r5, [r0]
    3ce4:      	mov	r6, r0
    3ce8:      	mov	r0, r5
    3cec:      	bl	0x3cec <audbrg_ostream_start+0x2c> @ imm = #-0x8
			00003cec:  R_ARM_CALL	audbrg_ostream_flush
    3cf0:      	ldr	r3, [pc, #0x4c]         @ 0x3d44 <audbrg_ostream_start+0x84>
    3cf4:      	mov	r2, #36
    3cf8:      	mov	r1, r4
    3cfc:      	mla	r3, r2, r5, r3
    3d00:      	ldr	r0, [r3, #0x8c]
    3d04:      	str	r4, [r3, #0xa0]
    3d08:      	str	r4, [r3, #0xa4]
    3d0c:      	str	r0, [r3, #0x94]
    3d10:      	str	r0, [r3, #0x98]
    3d14:      	str	r4, [r3, #0x9c]
    3d18:      	ldr	r2, [r3, #0x90]
    3d1c:      	sub	r0, r0, #-2130706432
    3d20:      	bl	0x3d20 <audbrg_ostream_start+0x60> @ imm = #-0x8
			00003d20:  R_ARM_CALL	memset
    3d24:      	mov	r3, #1
    3d28:      	mov	r0, r4
    3d2c:      	str	r3, [r6, #0x30]
    3d30:      	pop	{r4, r5, r6, pc}
    3d34:      	mov	r0, #1
    3d38:      	pop	{r4, r5, r6, pc}
    3d3c:      	mov	r0, #0
    3d40:      	pop	{r4, r5, r6, pc}

00003e18 <audbrg_ostream_stop>:
    3e18:      	push	{r4, r5, r6, lr}
    3e1c:      	str	lr, [sp, #-0x4]!
    3e20:      	bl	0x3e20 <audbrg_ostream_stop+0x8> @ imm = #-0x8
			00003e20:  R_ARM_CALL	__gnu_mcount_nc
    3e24:      	subs	r4, r0, #0
    3e28:      	beq	0x3e50 <audbrg_ostream_stop+0x38> @ imm = #0x20
    3e2c:      	ldr	r0, [r4, #0x30]
    3e30:      	mov	r5, #0
    3e34:      	cmp	r0, #0
    3e38:      	popeq	{r4, r5, r6, pc}
    3e3c:      	ldr	r0, [r4]
    3e40:      	bl	0x3e40 <audbrg_ostream_stop+0x28> @ imm = #-0x8
			00003e40:  R_ARM_CALL	audbrg_ostream_flush
    3e44:      	str	r5, [r4, #0x30]
    3e48:      	mov	r0, r5
    3e4c:      	pop	{r4, r5, r6, pc}
    3e50:      	mov	r0, #1
    3e54:      	pop	{r4, r5, r6, pc}

00003f24 <audbrg_ostream_putdata2SW>:
    3f24:      	push	{r4, r5, r6, lr}
    3f28:      	str	lr, [sp, #-0x4]!
    3f2c:      	bl	0x3f2c <audbrg_ostream_putdata2SW+0x8> @ imm = #-0x8
			00003f2c:  R_ARM_CALL	__gnu_mcount_nc
    3f30:      	mov	r4, r0
    3f34:      	ldr	r0, [pc, #0x7c]         @ 0x3fb8 <audbrg_ostream_putdata2SW+0x94>
    3f38:      	bl	0x3f38 <audbrg_ostream_putdata2SW+0x14> @ imm = #-0x8
			00003f38:  R_ARM_CALL	REG_Read
    3f3c:      	mov	r5, r0
    3f40:      	ldr	r0, [pc, #0x74]         @ 0x3fbc <audbrg_ostream_putdata2SW+0x98>
    3f44:      	lsl	r3, r4, #6
    3f48:      	and	r5, r5, #240
    3f4c:      	add	r0, r3, r0
    3f50:      	bl	0x3f50 <audbrg_ostream_putdata2SW+0x2c> @ imm = #-0x8
			00003f50:  R_ARM_CALL	REG_Read
    3f54:      	mov	r3, #68
    3f58:      	ldr	r12, [pc, #0x60]        @ 0x3fc0 <audbrg_ostream_putdata2SW+0x9c>
    3f5c:      	mul	r3, r3, r4
    3f60:      	ldr	lr, [pc, #0x5c]         @ 0x3fc4 <audbrg_ostream_putdata2SW+0xa0>
    3f64:      	bic	r0, r0, #-16777216
    3f68:      	lsl	r0, r0, #4
    3f6c:      	ldr	lr, [lr, r4, lsl #2]
    3f70:      	add	r1, r12, r3
    3f74:      	orr	r0, r0, r5, lsl #24
    3f78:      	ldr	r2, [r1, #0x4]
    3f7c:      	sub	r2, r2, lr
    3f80:      	add	r0, r0, r2
    3f84:      	add	r2, r3, #48
    3f88:      	add	r3, r3, #64
    3f8c:      	add	r2, r12, r2
    3f90:      	add	r3, r12, r3
    3f94:      	str	r0, [r1, #0x28]
    3f98:      	ldr	r0, [r2, #0x4]!
    3f9c:      	cmp	r0, #0
    3fa0:      	ldrne	r12, [r1, #0x28]
    3fa4:      	strne	r12, [r0, #0x8]
    3fa8:      	cmp	r2, r3
    3fac:      	bne	0x3f98 <audbrg_ostream_putdata2SW+0x74> @ imm = #-0x1c
    3fb0:      	mov	r0, #0
    3fb4:      	pop	{r4, r5, r6, pc}
