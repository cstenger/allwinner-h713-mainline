
local/h713-lab/extracted/stock-super/vendor/lib/modules/snd_alsa_trid.ko:	file format elf32-littlearm

Disassembly of section .text:

00009774 <aud_dsp1_read_reg>:
    9774: e92d47f0     	push	{r4, r5, r6, r7, r8, r9, r10, lr}
    9778: e52de004     	str	lr, [sp, #-0x4]!
    977c: ebfffffe     	bl	0x977c <aud_dsp1_read_reg+0x8> @ imm = #-0x8
    9780: e59fa0b0     	ldr	r10, [pc, #0xb0]        @ 0x9838 <aud_dsp1_read_reg+0xc4>
    9784: e1a04000     	mov	r4, r0
    9788: e30c834f     	movw	r8, #0xc34f
    978c: ebfffffe     	bl	0x978c <aud_dsp1_read_reg+0x18> @ imm = #-0x8
    9790: e3a09000     	mov	r9, #0
    9794: e1a06000     	mov	r6, r0
    9798: e1a07001     	mov	r7, r1
    979c: e1a0000a     	mov	r0, r10
    97a0: ebfffffe     	bl	0x97a0 <aud_dsp1_read_reg+0x2c> @ imm = #-0x8
    97a4: e1a05000     	mov	r5, r0
    97a8: ebfffffe     	bl	0x97a8 <aud_dsp1_read_reg+0x34> @ imm = #-0x8
    97ac: e0500006     	subs	r0, r0, r6
    97b0: e0c11007     	sbc	r1, r1, r7
    97b4: ebffff93     	bl	0x9608 <ktime_to_us>    @ imm = #-0x1b4
    97b8: e1580000     	cmp	r8, r0
    97bc: e0d93001     	sbcs	r3, r9, r1
    97c0: aa000001     	bge	0x97cc <aud_dsp1_read_reg+0x58> @ imm = #0x4
    97c4: e59f0070     	ldr	r0, [pc, #0x70]         @ 0x983c <aud_dsp1_read_reg+0xc8>
    97c8: e8bd87f0     	pop	{r4, r5, r6, r7, r8, r9, r10, pc}
    97cc: e3150010     	tst	r5, #16
    97d0: 1afffff1     	bne	0x979c <aud_dsp1_read_reg+0x28> @ imm = #-0x3c
    97d4: e1a01804     	lsl	r1, r4, #16
    97d8: e59f0060     	ldr	r0, [pc, #0x60]         @ 0x9840 <aud_dsp1_read_reg+0xcc>
    97dc: e59f5054     	ldr	r5, [pc, #0x54]         @ 0x9838 <aud_dsp1_read_reg+0xc4>
    97e0: e30c834f     	movw	r8, #0xc34f
    97e4: ebfffffe     	bl	0x97e4 <aud_dsp1_read_reg+0x70> @ imm = #-0x8
    97e8: ebfffffe     	bl	0x97e8 <aud_dsp1_read_reg+0x74> @ imm = #-0x8
    97ec: e3a09000     	mov	r9, #0
    97f0: e1a06000     	mov	r6, r0
    97f4: e1a07001     	mov	r7, r1
    97f8: e1a00005     	mov	r0, r5
    97fc: ebfffffe     	bl	0x97fc <aud_dsp1_read_reg+0x88> @ imm = #-0x8
    9800: e1a04000     	mov	r4, r0
    9804: ebfffffe     	bl	0x9804 <aud_dsp1_read_reg+0x90> @ imm = #-0x8
    9808: e0500006     	subs	r0, r0, r6
    980c: e0c11007     	sbc	r1, r1, r7
    9810: ebffff7c     	bl	0x9608 <ktime_to_us>    @ imm = #-0x210
    9814: e1580000     	cmp	r8, r0
    9818: e0d93001     	sbcs	r3, r9, r1
    981c: baffffe8     	blt	0x97c4 <aud_dsp1_read_reg+0x50> @ imm = #-0x60
    9820: e3140020     	tst	r4, #32
    9824: 0afffff3     	beq	0x97f8 <aud_dsp1_read_reg+0x84> @ imm = #-0x34
    9828: e59f0010     	ldr	r0, [pc, #0x10]         @ 0x9840 <aud_dsp1_read_reg+0xcc>
    982c: ebfffffe     	bl	0x982c <aud_dsp1_read_reg+0xb8> @ imm = #-0x8
    9830: e6ff0070     	uxth	r0, r0
    9834: e8bd87f0     	pop	{r4, r5, r6, r7, r8, r9, r10, pc}
