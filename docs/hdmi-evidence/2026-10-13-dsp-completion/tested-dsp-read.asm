
build/hdmi-dsp-completion/h713-hdmi-dsp-probe.ko:	file format elf64-littleaarch64

Disassembly of section .text:

00000000000003d8 <dsp_read>:
     3d8: d503233f     	paciasp
     3dc: d101c3ff     	sub	sp, sp, #0x70
     3e0: a9017bfd     	stp	x29, x30, [sp, #0x10]
     3e4: 52801009     	mov	w9, #0x80               // =128
     3e8: 5280020a     	mov	w10, #0x10              // =16
     3ec: a9026ffc     	stp	x28, x27, [sp, #0x20]
     3f0: 5280200b     	mov	w11, #0x100             // =256
     3f4: 5280040c     	mov	w12, #0x20              // =32
     3f8: a90367fa     	stp	x26, x25, [sp, #0x30]
     3fc: 5280030d     	mov	w13, #0x18              // =24
     400: 910043fd     	add	x29, sp, #0x10
     404: a9045ff8     	stp	x24, x23, [sp, #0x40]
     408: 529e1018     	mov	w24, #0xf080            // =61568
     40c: aa0203fb     	mov	x27, x2
     410: a90557f6     	stp	x22, x21, [sp, #0x50]
     414: 2a0103f6     	mov	w22, w1
     418: 72a05f58     	movk	w24, #0x2fa, lsl #16
     41c: a9064ff4     	stp	x20, x19, [sp, #0x60]
     420: d5384108     	mrs	x8, SP_EL0
     424: 2a0003f3     	mov	w19, w0
     428: f9420908     	ldr	x8, [x8, #0x410]
     42c: 7100001f     	cmp	w0, #0x0
     430: 1a890157     	csel	w23, w10, w9, eq
     434: 1a8b0195     	csel	w21, w12, w11, eq
     438: 9a8d0159     	csel	x25, x10, x13, eq
     43c: f90007e8     	str	x8, [sp, #0x8]
     440: 94000000     	bl	0x440 <dsp_read+0x68>
		0000000000000440:  R_AARCH64_CALL26	ktime_get
     444: 8b180018     	add	x24, x0, x24
     448: 94000000     	bl	0x448 <dsp_read+0x70>
		0000000000000448:  R_AARCH64_CALL26	ktime_get
     44c: 9000001a     	adrp	x26, 0x0 <read_word>
		000000000000044c:  R_AARCH64_ADR_PREL_PG_HI21	.bss+0x38
     450: f9400348     	ldr	x8, [x26]
		0000000000000450:  R_AARCH64_LDST64_ABS_LO12_NC	.bss+0x38
     454: b9400104     	ldr	w4, [x8]
     458: 6a17009f     	tst	w4, w23
     45c: d50331bf     	dmb	oshld
     460: 2a0403e9     	mov	w9, w4
     464: 1a9f17e8     	cset	w8, eq
     468: eb18001f     	cmp	x0, x24
     46c: ca090129     	eor	x9, x9, x9
     470: b5000009     	cbnz	x9, 0x470 <dsp_read+0x98>
     474: 1a9fd509     	csinc	w9, w8, wzr, le
     478: 37000249     	tbnz	w9, #0x0, 0x4c0 <dsp_read+0xe8>
     47c: 52800060     	mov	w0, #0x3                // =3
     480: 52800141     	mov	w1, #0xa                // =10
     484: 52800042     	mov	w2, #0x2                // =2
     488: 94000000     	bl	0x488 <dsp_read+0xb0>
		0000000000000488:  R_AARCH64_CALL26	usleep_range_state
     48c: d503203f     	yield
     490: 94000000     	bl	0x490 <dsp_read+0xb8>
		0000000000000490:  R_AARCH64_CALL26	ktime_get
     494: f9400348     	ldr	x8, [x26]
		0000000000000494:  R_AARCH64_LDST64_ABS_LO12_NC	.bss+0x38
     498: b9400104     	ldr	w4, [x8]
     49c: d50331bf     	dmb	oshld
     4a0: 2a0403e8     	mov	w8, w4
     4a4: 6a170089     	ands	w9, w4, w23
     4a8: ca080108     	eor	x8, x8, x8
     4ac: b5000008     	cbnz	x8, 0x4ac <dsp_read+0xd4>
     4b0: 1a9f17e8     	cset	w8, eq
     4b4: 34000069     	cbz	w9, 0x4c0 <dsp_read+0xe8>
     4b8: eb18001f     	cmp	x0, x24
     4bc: 54fffe0d     	b.le	0x47c <dsp_read+0xa4>
     4c0: 12003ed6     	and	w22, w22, #0xffff
     4c4: 34000508     	cbz	w8, 0x564 <dsp_read+0x18c>
     4c8: 90000000     	adrp	x0, 0x0 <read_word>
		00000000000004c8:  R_AARCH64_ADR_PREL_PG_HI21	.rodata.str1.1+0x209
     4cc: 91000000     	add	x0, x0, #0x0
		00000000000004cc:  R_AARCH64_ADD_ABS_LO12_NC	.rodata.str1.1+0x209
     4d0: 2a1303e1     	mov	w1, w19
     4d4: 2a1603e2     	mov	w2, w22
     4d8: 2a0403e3     	mov	w3, w4
     4dc: 94000000     	bl	0x4dc <dsp_read+0x104>
		00000000000004dc:  R_AARCH64_CALL26	_printk
     4e0: d53b4237     	mrs	x23, DAIF
     4e4: d50343df     	msr	DAIFSet, #0x3
     4e8: 90000018     	adrp	x24, 0x0 <read_word>
		00000000000004e8:  R_AARCH64_ADR_PREL_PG_HI21	.bss+0x10
     4ec: 53103ec9     	lsl	w9, w22, #16
     4f0: f9400348     	ldr	x8, [x26]
		00000000000004f0:  R_AARCH64_LDST64_ABS_LO12_NC	.bss+0x38
     4f4: d50332bf     	dmb	oshst
     4f8: 8b190108     	add	x8, x8, x25
     4fc: b9000109     	str	w9, [x8]
     500: 39400308     	ldrb	w8, [x24]
		0000000000000500:  R_AARCH64_LDST8_ABS_LO12_NC	.bss+0x10
     504: 36000488     	tbz	w8, #0x0, 0x594 <dsp_read+0x1bc>
     508: f940035c     	ldr	x28, [x26]
		0000000000000508:  R_AARCH64_LDST64_ABS_LO12_NC	.bss+0x38
     50c: 94000000     	bl	0x50c <dsp_read+0x134>
		000000000000050c:  R_AARCH64_CALL26	ktime_get
     510: b9400388     	ldr	w8, [x28]
     514: d50331bf     	dmb	oshld
     518: 2a0803e9     	mov	w9, w8
     51c: ca090129     	eor	x9, x9, x9
     520: b5000009     	cbnz	x9, 0x520 <dsp_read+0x148>
     524: 6a15011f     	tst	w8, w21
     528: 540008e0     	b.eq	0x644 <dsp_read+0x26c>
     52c: 91406008     	add	x8, x0, #0x18, lsl #12  // =0x18000
     530: 911a8114     	add	x20, x8, #0x6a0
     534: 94000000     	bl	0x534 <dsp_read+0x15c>
		0000000000000534:  R_AARCH64_CALL26	ktime_get
     538: eb14001f     	cmp	x0, x20
     53c: 540005e2     	b.hs	0x5f8 <dsp_read+0x220>
     540: d503203f     	yield
     544: b9400388     	ldr	w8, [x28]
     548: d50331bf     	dmb	oshld
     54c: 2a0803e9     	mov	w9, w8
     550: 6a15011f     	tst	w8, w21
     554: ca090129     	eor	x9, x9, x9
     558: b5000009     	cbnz	x9, 0x558 <dsp_read+0x180>
     55c: 54fffec1     	b.ne	0x534 <dsp_read+0x15c>
     560: 14000039     	b	0x644 <dsp_read+0x26c>
     564: 90000003     	adrp	x3, 0x0 <read_word>
		0000000000000564:  R_AARCH64_ADR_PREL_PG_HI21	.rodata.str1.1+0x3d2
     568: 91000063     	add	x3, x3, #0x0
		0000000000000568:  R_AARCH64_ADD_ABS_LO12_NC	.rodata.str1.1+0x3d2
     56c: 12800db8     	mov	w24, #-0x6e             // =-110
     570: 90000008     	adrp	x8, 0x0 <read_word>
		0000000000000570:  R_AARCH64_ADR_PREL_PG_HI21	.bss+0x40
     574: 52800029     	mov	w9, #0x1                // =1
     578: 90000000     	adrp	x0, 0x0 <read_word>
		0000000000000578:  R_AARCH64_ADR_PREL_PG_HI21	.rodata.str1.1+0x24c
     57c: 91000000     	add	x0, x0, #0x0
		000000000000057c:  R_AARCH64_ADD_ABS_LO12_NC	.rodata.str1.1+0x24c
     580: 2a1303e1     	mov	w1, w19
     584: 2a1603e2     	mov	w2, w22
     588: 39000109     	strb	w9, [x8]
		0000000000000588:  R_AARCH64_LDST8_ABS_LO12_NC	.bss+0x40
     58c: 94000000     	bl	0x58c <dsp_read+0x1b4>
		000000000000058c:  R_AARCH64_CALL26	_printk
     590: 1400005d     	b	0x704 <dsp_read+0x32c>
     594: f9400348     	ldr	x8, [x26]
		0000000000000594:  R_AARCH64_LDST64_ABS_LO12_NC	.bss+0x38
     598: b9400108     	ldr	w8, [x8]
     59c: d50331bf     	dmb	oshld
     5a0: 2a0803e9     	mov	w9, w8
     5a4: ca090129     	eor	x9, x9, x9
     5a8: b5000009     	cbnz	x9, 0x5a8 <dsp_read+0x1d0>
     5ac: 6a15011f     	tst	w8, w21
     5b0: 540004a0     	b.eq	0x644 <dsp_read+0x26c>
     5b4: 5290d408     	mov	w8, #0x86a0             // =34464
     5b8: 72a00028     	movk	w8, #0x1, lsl #16
     5bc: 910fa51c     	add	x28, x8, #0x3e9
     5c0: 528218e0     	mov	w0, #0x10c7             // =4295
     5c4: 94000000     	bl	0x5c4 <dsp_read+0x1ec>
		00000000000005c4:  R_AARCH64_CALL26	__const_udelay
     5c8: d503203f     	yield
     5cc: f9400348     	ldr	x8, [x26]
		00000000000005cc:  R_AARCH64_LDST64_ABS_LO12_NC	.bss+0x38
     5d0: b9400108     	ldr	w8, [x8]
     5d4: d50331bf     	dmb	oshld
     5d8: 2a0803e9     	mov	w9, w8
     5dc: ca090129     	eor	x9, x9, x9
     5e0: b5000009     	cbnz	x9, 0x5e0 <dsp_read+0x208>
     5e4: 6a15011f     	tst	w8, w21
     5e8: 540002e0     	b.eq	0x644 <dsp_read+0x26c>
     5ec: d10fa79c     	sub	x28, x28, #0x3e9
     5f0: f10fa79f     	cmp	x28, #0x3e9
     5f4: 54fffe6a     	b.ge	0x5c0 <dsp_read+0x1e8>
     5f8: b90007ff     	str	wzr, [sp, #0x4]
     5fc: d51b4237     	msr	DAIF, x23
     600: 94000000     	bl	0x600 <dsp_read+0x228>
		0000000000000600:  R_AARCH64_CALL26	ktime_get
     604: 90000008     	adrp	x8, 0x0 <read_word>
		0000000000000604:  R_AARCH64_ADR_PREL_PG_HI21	.bss+0x18
     608: 3940030a     	ldrb	w10, [x24]
		0000000000000608:  R_AARCH64_LDST8_ABS_LO12_NC	.bss+0x10
     60c: aa0003f7     	mov	x23, x0
     610: b9400109     	ldr	w9, [x8]
		0000000000000610:  R_AARCH64_LDST32_ABS_LO12_NC	.bss+0x18
     614: 11000529     	add	w9, w9, #0x1
     618: b9000109     	str	w9, [x8]
		0000000000000618:  R_AARCH64_LDST32_ABS_LO12_NC	.bss+0x18
     61c: 3600098a     	tbz	w10, #0x0, 0x74c <dsp_read+0x374>
     620: f9400340     	ldr	x0, [x26]
		0000000000000620:  R_AARCH64_LDST64_ABS_LO12_NC	.bss+0x38
     624: 910013e1     	add	x1, sp, #0x4
     628: 2a1503e2     	mov	w2, w21
     62c: 52986a03     	mov	w3, #0xc350             // =50000
     630: 94000086     	bl	0x848 <h713_dsp_wait_clear>
     634: 529e1014     	mov	w20, #0xf080            // =61568
     638: 2a0003f8     	mov	w24, w0
     63c: 72a05f54     	movk	w20, #0x2fa, lsl #16
     640: 14000068     	b	0x7e0 <dsp_read+0x408>
     644: d51b4237     	msr	DAIF, x23
     648: 90000008     	adrp	x8, 0x0 <read_word>
		0000000000000648:  R_AARCH64_ADR_PREL_PG_HI21	.bss+0x14
     64c: 529e1014     	mov	w20, #0xf080            // =61568
     650: b9400109     	ldr	w9, [x8]
		0000000000000650:  R_AARCH64_LDST32_ABS_LO12_NC	.bss+0x14
     654: 72a05f54     	movk	w20, #0x2fa, lsl #16
     658: 11000529     	add	w9, w9, #0x1
     65c: b9000109     	str	w9, [x8]
		000000000000065c:  R_AARCH64_LDST32_ABS_LO12_NC	.bss+0x14
     660: 94000000     	bl	0x660 <dsp_read+0x288>
		0000000000000660:  R_AARCH64_CALL26	ktime_get
     664: 8b140017     	add	x23, x0, x20
     668: 94000000     	bl	0x668 <dsp_read+0x290>
		0000000000000668:  R_AARCH64_CALL26	ktime_get
     66c: f9400348     	ldr	x8, [x26]
		000000000000066c:  R_AARCH64_LDST64_ABS_LO12_NC	.bss+0x38
     670: b9400104     	ldr	w4, [x8]
     674: d50331bf     	dmb	oshld
     678: 6a15009f     	tst	w4, w21
     67c: 2a0403e9     	mov	w9, w4
     680: 1a9f07e8     	cset	w8, ne
     684: eb17001f     	cmp	x0, x23
     688: ca090129     	eor	x9, x9, x9
     68c: b5000009     	cbnz	x9, 0x68c <dsp_read+0x2b4>
     690: 1a9fd509     	csinc	w9, w8, wzr, le
     694: 37000249     	tbnz	w9, #0x0, 0x6dc <dsp_read+0x304>
     698: 52800060     	mov	w0, #0x3                // =3
     69c: 52800141     	mov	w1, #0xa                // =10
     6a0: 52800042     	mov	w2, #0x2                // =2
     6a4: 94000000     	bl	0x6a4 <dsp_read+0x2cc>
		00000000000006a4:  R_AARCH64_CALL26	usleep_range_state
     6a8: d503203f     	yield
     6ac: 94000000     	bl	0x6ac <dsp_read+0x2d4>
		00000000000006ac:  R_AARCH64_CALL26	ktime_get
     6b0: f9400348     	ldr	x8, [x26]
		00000000000006b0:  R_AARCH64_LDST64_ABS_LO12_NC	.bss+0x38
     6b4: b9400104     	ldr	w4, [x8]
     6b8: d50331bf     	dmb	oshld
     6bc: 2a0403e8     	mov	w8, w4
     6c0: 6a150089     	ands	w9, w4, w21
     6c4: ca080108     	eor	x8, x8, x8
     6c8: b5000008     	cbnz	x8, 0x6c8 <dsp_read+0x2f0>
     6cc: 1a9f07e8     	cset	w8, ne
     6d0: 35000069     	cbnz	w9, 0x6dc <dsp_read+0x304>
     6d4: eb17001f     	cmp	x0, x23
     6d8: 54fffe0d     	b.le	0x698 <dsp_read+0x2c0>
     6dc: 34000328     	cbz	w8, 0x740 <dsp_read+0x368>
     6e0: f9400348     	ldr	x8, [x26]
		00000000000006e0:  R_AARCH64_LDST64_ABS_LO12_NC	.bss+0x38
     6e4: 2a1f03f8     	mov	w24, wzr
     6e8: 8b190108     	add	x8, x8, x25
     6ec: b9400108     	ldr	w8, [x8]
     6f0: d50331bf     	dmb	oshld
     6f4: 2a0803e9     	mov	w9, w8
     6f8: ca090129     	eor	x9, x9, x9
     6fc: b5000009     	cbnz	x9, 0x6fc <dsp_read+0x324>
     700: b9000368     	str	w8, [x27]
     704: d5384108     	mrs	x8, SP_EL0
     708: f9420908     	ldr	x8, [x8, #0x410]
     70c: f94007e9     	ldr	x9, [sp, #0x8]
     710: eb09011f     	cmp	x8, x9
     714: 54000981     	b.ne	0x844 <dsp_read+0x46c>
     718: 2a1803e0     	mov	w0, w24
     71c: a9464ff4     	ldp	x20, x19, [sp, #0x60]
     720: a94557f6     	ldp	x22, x21, [sp, #0x50]
     724: a9445ff8     	ldp	x24, x23, [sp, #0x40]
     728: a94367fa     	ldp	x26, x25, [sp, #0x30]
     72c: a9426ffc     	ldp	x28, x27, [sp, #0x20]
     730: a9417bfd     	ldp	x29, x30, [sp, #0x10]
     734: 9101c3ff     	add	sp, sp, #0x70
     738: d50323bf     	autiasp
     73c: d65f03c0     	ret
     740: 90000003     	adrp	x3, 0x0 <read_word>
		0000000000000740:  R_AARCH64_ADR_PREL_PG_HI21	.rodata.str1.1+0x431
     744: 91000063     	add	x3, x3, #0x0
		0000000000000744:  R_AARCH64_ADD_ABS_LO12_NC	.rodata.str1.1+0x431
     748: 17ffff89     	b	0x56c <dsp_read+0x194>
     74c: 94000000     	bl	0x74c <dsp_read+0x374>
		000000000000074c:  R_AARCH64_CALL26	ktime_get
     750: 529e1014     	mov	w20, #0xf080            // =61568
     754: 72a05f54     	movk	w20, #0x2fa, lsl #16
     758: 8b140018     	add	x24, x0, x20
     75c: 94000000     	bl	0x75c <dsp_read+0x384>
		000000000000075c:  R_AARCH64_CALL26	ktime_get
     760: f9400348     	ldr	x8, [x26]
		0000000000000760:  R_AARCH64_LDST64_ABS_LO12_NC	.bss+0x38
     764: b9400108     	ldr	w8, [x8]
     768: d50331bf     	dmb	oshld
     76c: 6a15011f     	tst	w8, w21
     770: 2a0803ea     	mov	w10, w8
     774: 1a9f17e9     	cset	w9, eq
     778: eb18001f     	cmp	x0, x24
     77c: ca0a014a     	eor	x10, x10, x10
     780: b500000a     	cbnz	x10, 0x780 <dsp_read+0x3a8>
     784: 1a9fd52a     	csinc	w10, w9, wzr, le
     788: 3700024a     	tbnz	w10, #0x0, 0x7d0 <dsp_read+0x3f8>
     78c: 52800020     	mov	w0, #0x1                // =1
     790: 52800041     	mov	w1, #0x2                // =2
     794: 52800042     	mov	w2, #0x2                // =2
     798: 94000000     	bl	0x798 <dsp_read+0x3c0>
		0000000000000798:  R_AARCH64_CALL26	usleep_range_state
     79c: d503203f     	yield
     7a0: 94000000     	bl	0x7a0 <dsp_read+0x3c8>
		00000000000007a0:  R_AARCH64_CALL26	ktime_get
     7a4: f9400348     	ldr	x8, [x26]
		00000000000007a4:  R_AARCH64_LDST64_ABS_LO12_NC	.bss+0x38
     7a8: b9400108     	ldr	w8, [x8]
     7ac: d50331bf     	dmb	oshld
     7b0: 2a0803e9     	mov	w9, w8
     7b4: ca090129     	eor	x9, x9, x9
     7b8: b5000009     	cbnz	x9, 0x7b8 <dsp_read+0x3e0>
     7bc: 6a15010a     	ands	w10, w8, w21
     7c0: 1a9f17e9     	cset	w9, eq
     7c4: 3400006a     	cbz	w10, 0x7d0 <dsp_read+0x3f8>
     7c8: eb18001f     	cmp	x0, x24
     7cc: 54fffe0d     	b.le	0x78c <dsp_read+0x3b4>
     7d0: 7100013f     	cmp	w9, #0x0
     7d4: 12800da9     	mov	w9, #-0x6e              // =-110
     7d8: b90007e8     	str	w8, [sp, #0x4]
     7dc: 1a8913f8     	csel	w24, wzr, w9, ne
     7e0: 94000000     	bl	0x7e0 <dsp_read+0x408>
		00000000000007e0:  R_AARCH64_CALL26	ktime_get
     7e4: d29ef9e8     	mov	x8, #0xf7cf             // =63439
     7e8: cb170009     	sub	x9, x0, x23
     7ec: 90000000     	adrp	x0, 0x0 <read_word>
		00000000000007ec:  R_AARCH64_ADR_PREL_PG_HI21	.rodata.str1.1+0x161
     7f0: 91000000     	add	x0, x0, #0x0
		00000000000007f0:  R_AARCH64_ADD_ABS_LO12_NC	.rodata.str1.1+0x161
     7f4: f2bc6a68     	movk	x8, #0xe353, lsl #16
     7f8: 2a1303e1     	mov	w1, w19
     7fc: f2d374a8     	movk	x8, #0x9ba5, lsl #32
     800: 2a1603e2     	mov	w2, w22
     804: 2a1803e4     	mov	w4, w24
     808: f2e41888     	movk	x8, #0x20c4, lsl #48
     80c: 9b487d28     	smulh	x8, x9, x8
     810: 9347fd09     	asr	x9, x8, #7
     814: 8b48fd28     	add	x8, x9, x8, lsr #63
     818: 91019103     	add	x3, x8, #0x64
     81c: 94000000     	bl	0x81c <dsp_read+0x444>
		000000000000081c:  R_AARCH64_CALL26	_printk
     820: 34fff218     	cbz	w24, 0x660 <dsp_read+0x288>
     824: 90000008     	adrp	x8, 0x0 <read_word>
		0000000000000824:  R_AARCH64_ADR_PREL_PG_HI21	.bss+0x1c
     828: b94007e4     	ldr	w4, [sp, #0x4]
     82c: 90000003     	adrp	x3, 0x0 <read_word>
		000000000000082c:  R_AARCH64_ADR_PREL_PG_HI21	.rodata.str1.1+0x3c1
     830: 91000063     	add	x3, x3, #0x0
		0000000000000830:  R_AARCH64_ADD_ABS_LO12_NC	.rodata.str1.1+0x3c1
     834: b9400109     	ldr	w9, [x8]
		0000000000000834:  R_AARCH64_LDST32_ABS_LO12_NC	.bss+0x1c
     838: 11000529     	add	w9, w9, #0x1
     83c: b9000109     	str	w9, [x8]
		000000000000083c:  R_AARCH64_LDST32_ABS_LO12_NC	.bss+0x1c
     840: 17ffff4c     	b	0x570 <dsp_read+0x198>
     844: 94000000     	bl	0x844 <dsp_read+0x46c>
		0000000000000844:  R_AARCH64_CALL26	__stack_chk_fail
