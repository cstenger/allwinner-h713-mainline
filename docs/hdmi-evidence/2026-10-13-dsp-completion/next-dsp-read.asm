
build/hdmi-dsp-completion-boundary/h713-hdmi-dsp-probe.ko:	file format elf64-littleaarch64

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
     408: 529e1017     	mov	w23, #0xf080            // =61568
     40c: aa0203fb     	mov	x27, x2
     410: a90557f6     	stp	x22, x21, [sp, #0x50]
     414: 2a0103f5     	mov	w21, w1
     418: 72a05f57     	movk	w23, #0x2fa, lsl #16
     41c: a9064ff4     	stp	x20, x19, [sp, #0x60]
     420: d5384108     	mrs	x8, SP_EL0
     424: 2a0003f3     	mov	w19, w0
     428: f9420908     	ldr	x8, [x8, #0x410]
     42c: 7100001f     	cmp	w0, #0x0
     430: 1a890158     	csel	w24, w10, w9, eq
     434: 1a8b0196     	csel	w22, w12, w11, eq
     438: 1a8d0159     	csel	w25, w10, w13, eq
     43c: f90007e8     	str	x8, [sp, #0x8]
     440: 94000000     	bl	0x440 <dsp_read+0x68>
		0000000000000440:  R_AARCH64_CALL26	ktime_get
     444: 8b17001c     	add	x28, x0, x23
     448: 94000000     	bl	0x448 <dsp_read+0x70>
		0000000000000448:  R_AARCH64_CALL26	ktime_get
     44c: 9000001a     	adrp	x26, 0x0 <read_word>
		000000000000044c:  R_AARCH64_ADR_PREL_PG_HI21	.bss+0x38
     450: f9400348     	ldr	x8, [x26]
		0000000000000450:  R_AARCH64_LDST64_ABS_LO12_NC	.bss+0x38
     454: b9400117     	ldr	w23, [x8]
     458: 6a1802ff     	tst	w23, w24
     45c: d50331bf     	dmb	oshld
     460: 2a1703e9     	mov	w9, w23
     464: 1a9f17e8     	cset	w8, eq
     468: eb1c001f     	cmp	x0, x28
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
     498: b9400117     	ldr	w23, [x8]
     49c: d50331bf     	dmb	oshld
     4a0: 2a1703e8     	mov	w8, w23
     4a4: 6a1802e9     	ands	w9, w23, w24
     4a8: ca080108     	eor	x8, x8, x8
     4ac: b5000008     	cbnz	x8, 0x4ac <dsp_read+0xd4>
     4b0: 1a9f17e8     	cset	w8, eq
     4b4: 34000069     	cbz	w9, 0x4c0 <dsp_read+0xe8>
     4b8: eb1c001f     	cmp	x0, x28
     4bc: 54fffe0d     	b.le	0x47c <dsp_read+0xa4>
     4c0: 12003eb5     	and	w21, w21, #0xffff
     4c4: b90007f7     	str	w23, [sp, #0x4]
     4c8: 34000508     	cbz	w8, 0x568 <dsp_read+0x190>
     4cc: 90000000     	adrp	x0, 0x0 <read_word>
		00000000000004cc:  R_AARCH64_ADR_PREL_PG_HI21	.rodata.str1.1+0x25d
     4d0: 91000000     	add	x0, x0, #0x0
		00000000000004d0:  R_AARCH64_ADD_ABS_LO12_NC	.rodata.str1.1+0x25d
     4d4: 2a1303e1     	mov	w1, w19
     4d8: 2a1503e2     	mov	w2, w21
     4dc: 2a1703e3     	mov	w3, w23
     4e0: 94000000     	bl	0x4e0 <dsp_read+0x108>
		00000000000004e0:  R_AARCH64_CALL26	_printk
     4e4: d53b4237     	mrs	x23, DAIF
     4e8: d50343df     	msr	DAIFSet, #0x3
     4ec: 90000018     	adrp	x24, 0x0 <read_word>
		00000000000004ec:  R_AARCH64_ADR_PREL_PG_HI21	.bss+0x10
     4f0: 39400308     	ldrb	w8, [x24]
		00000000000004f0:  R_AARCH64_LDST8_ABS_LO12_NC	.bss+0x10
     4f4: 340006c8     	cbz	w8, 0x5cc <dsp_read+0x1f4>
     4f8: 94000000     	bl	0x4f8 <dsp_read+0x120>
		00000000000004f8:  R_AARCH64_CALL26	ktime_get
     4fc: f9400348     	ldr	x8, [x26]
		00000000000004fc:  R_AARCH64_LDST64_ABS_LO12_NC	.bss+0x38
     500: 53103ea9     	lsl	w9, w21, #16
     504: d50332bf     	dmb	oshst
     508: 8b394108     	add	x8, x8, w25, uxtw
     50c: b9000109     	str	w9, [x8]
     510: f940035c     	ldr	x28, [x26]
		0000000000000510:  R_AARCH64_LDST64_ABS_LO12_NC	.bss+0x38
     514: b9400388     	ldr	w8, [x28]
     518: d50331bf     	dmb	oshld
     51c: 2a0803e9     	mov	w9, w8
     520: ca090129     	eor	x9, x9, x9
     524: b5000009     	cbnz	x9, 0x524 <dsp_read+0x14c>
     528: 6a16011f     	tst	w8, w22
     52c: 54000aa0     	b.eq	0x680 <dsp_read+0x2a8>
     530: 91406008     	add	x8, x0, #0x18, lsl #12  // =0x18000
     534: 911a8114     	add	x20, x8, #0x6a0
     538: 94000000     	bl	0x538 <dsp_read+0x160>
		0000000000000538:  R_AARCH64_CALL26	ktime_get
     53c: eb14001f     	cmp	x0, x20
     540: 54000822     	b.hs	0x644 <dsp_read+0x26c>
     544: d503203f     	yield
     548: b9400388     	ldr	w8, [x28]
     54c: d50331bf     	dmb	oshld
     550: 2a0803e9     	mov	w9, w8
     554: 6a16011f     	tst	w8, w22
     558: ca090129     	eor	x9, x9, x9
     55c: b5000009     	cbnz	x9, 0x55c <dsp_read+0x184>
     560: 54fffec1     	b.ne	0x538 <dsp_read+0x160>
     564: 14000047     	b	0x680 <dsp_read+0x2a8>
     568: 90000014     	adrp	x20, 0x0 <read_word>
		0000000000000568:  R_AARCH64_ADR_PREL_PG_HI21	.rodata.str1.1+0x426
     56c: 91000294     	add	x20, x20, #0x0
		000000000000056c:  R_AARCH64_ADD_ABS_LO12_NC	.rodata.str1.1+0x426
     570: 12800db8     	mov	w24, #-0x6e             // =-110
     574: f9400348     	ldr	x8, [x26]
		0000000000000574:  R_AARCH64_LDST64_ABS_LO12_NC	.bss+0x38
     578: 90000009     	adrp	x9, 0x0 <read_word>
		0000000000000578:  R_AARCH64_ADR_PREL_PG_HI21	.bss+0x40
     57c: 5280002a     	mov	w10, #0x1               // =1
     580: 3900012a     	strb	w10, [x9]
		0000000000000580:  R_AARCH64_LDST8_ABS_LO12_NC	.bss+0x40
     584: 53103ea2     	lsl	w2, w21, #16
     588: 90000000     	adrp	x0, 0x0 <read_word>
		0000000000000588:  R_AARCH64_ADR_PREL_PG_HI21	.rodata.str1.1+0x9a
     58c: 91000000     	add	x0, x0, #0x0
		000000000000058c:  R_AARCH64_ADD_ABS_LO12_NC	.rodata.str1.1+0x9a
     590: 8b394108     	add	x8, x8, w25, uxtw
     594: b9400101     	ldr	w1, [x8]
     598: d50331bf     	dmb	oshld
     59c: 2a0103e8     	mov	w8, w1
     5a0: ca080108     	eor	x8, x8, x8
     5a4: b5000008     	cbnz	x8, 0x5a4 <dsp_read+0x1cc>
     5a8: 94000000     	bl	0x5a8 <dsp_read+0x1d0>
		00000000000005a8:  R_AARCH64_CALL26	_printk
     5ac: 90000000     	adrp	x0, 0x0 <read_word>
		00000000000005ac:  R_AARCH64_ADR_PREL_PG_HI21	.rodata.str1.1+0x2a0
     5b0: 91000000     	add	x0, x0, #0x0
		00000000000005b0:  R_AARCH64_ADD_ABS_LO12_NC	.rodata.str1.1+0x2a0
     5b4: 2a1303e1     	mov	w1, w19
     5b8: 2a1503e2     	mov	w2, w21
     5bc: aa1403e3     	mov	x3, x20
     5c0: 2a1703e4     	mov	w4, w23
     5c4: 94000000     	bl	0x5c4 <dsp_read+0x1ec>
		00000000000005c4:  R_AARCH64_CALL26	_printk
     5c8: 1400005e     	b	0x740 <dsp_read+0x368>
     5cc: f9400348     	ldr	x8, [x26]
		00000000000005cc:  R_AARCH64_LDST64_ABS_LO12_NC	.bss+0x38
     5d0: d50332bf     	dmb	oshst
     5d4: 53103ea9     	lsl	w9, w21, #16
     5d8: 8b394108     	add	x8, x8, w25, uxtw
     5dc: b9000109     	str	w9, [x8]
     5e0: f9400348     	ldr	x8, [x26]
		00000000000005e0:  R_AARCH64_LDST64_ABS_LO12_NC	.bss+0x38
     5e4: b9400108     	ldr	w8, [x8]
     5e8: d50331bf     	dmb	oshld
     5ec: 2a0803e9     	mov	w9, w8
     5f0: ca090129     	eor	x9, x9, x9
     5f4: b5000009     	cbnz	x9, 0x5f4 <dsp_read+0x21c>
     5f8: 6a16011f     	tst	w8, w22
     5fc: 54000420     	b.eq	0x680 <dsp_read+0x2a8>
     600: 5290d408     	mov	w8, #0x86a0             // =34464
     604: 72a00028     	movk	w8, #0x1, lsl #16
     608: 910fa51c     	add	x28, x8, #0x3e9
     60c: 528218e0     	mov	w0, #0x10c7             // =4295
     610: 94000000     	bl	0x610 <dsp_read+0x238>
		0000000000000610:  R_AARCH64_CALL26	__const_udelay
     614: d503203f     	yield
     618: f9400348     	ldr	x8, [x26]
		0000000000000618:  R_AARCH64_LDST64_ABS_LO12_NC	.bss+0x38
     61c: b9400108     	ldr	w8, [x8]
     620: d50331bf     	dmb	oshld
     624: 2a0803e9     	mov	w9, w8
     628: ca090129     	eor	x9, x9, x9
     62c: b5000009     	cbnz	x9, 0x62c <dsp_read+0x254>
     630: 6a16011f     	tst	w8, w22
     634: 54000260     	b.eq	0x680 <dsp_read+0x2a8>
     638: d10fa79c     	sub	x28, x28, #0x3e9
     63c: f10fa79f     	cmp	x28, #0x3e9
     640: 54fffe6a     	b.ge	0x60c <dsp_read+0x234>
     644: d51b4237     	msr	DAIF, x23
     648: 94000000     	bl	0x648 <dsp_read+0x270>
		0000000000000648:  R_AARCH64_CALL26	ktime_get
     64c: 90000008     	adrp	x8, 0x0 <read_word>
		000000000000064c:  R_AARCH64_ADR_PREL_PG_HI21	.bss+0x18
     650: 3940030a     	ldrb	w10, [x24]
		0000000000000650:  R_AARCH64_LDST8_ABS_LO12_NC	.bss+0x10
     654: aa0003f7     	mov	x23, x0
     658: b9400109     	ldr	w9, [x8]
		0000000000000658:  R_AARCH64_LDST32_ABS_LO12_NC	.bss+0x18
     65c: 11000529     	add	w9, w9, #0x1
     660: b9000109     	str	w9, [x8]
		0000000000000660:  R_AARCH64_LDST32_ABS_LO12_NC	.bss+0x18
     664: 3600092a     	tbz	w10, #0x0, 0x788 <dsp_read+0x3b0>
     668: f9400340     	ldr	x0, [x26]
		0000000000000668:  R_AARCH64_LDST64_ABS_LO12_NC	.bss+0x38
     66c: 910013e1     	add	x1, sp, #0x4
     670: 2a1603e2     	mov	w2, w22
     674: 94000084     	bl	0x884 <h713_dsp_wait_clear>
     678: 2a0003f8     	mov	w24, w0
     67c: 14000068     	b	0x81c <dsp_read+0x444>
     680: d51b4237     	msr	DAIF, x23
     684: 90000008     	adrp	x8, 0x0 <read_word>
		0000000000000684:  R_AARCH64_ADR_PREL_PG_HI21	.bss+0x14
     688: b9400109     	ldr	w9, [x8]
		0000000000000688:  R_AARCH64_LDST32_ABS_LO12_NC	.bss+0x14
     68c: 11000529     	add	w9, w9, #0x1
     690: b9000109     	str	w9, [x8]
		0000000000000690:  R_AARCH64_LDST32_ABS_LO12_NC	.bss+0x14
     694: 94000000     	bl	0x694 <dsp_read+0x2bc>
		0000000000000694:  R_AARCH64_CALL26	ktime_get
     698: 529e1008     	mov	w8, #0xf080             // =61568
     69c: 72a05f48     	movk	w8, #0x2fa, lsl #16
     6a0: 8b080018     	add	x24, x0, x8
     6a4: 94000000     	bl	0x6a4 <dsp_read+0x2cc>
		00000000000006a4:  R_AARCH64_CALL26	ktime_get
     6a8: f9400348     	ldr	x8, [x26]
		00000000000006a8:  R_AARCH64_LDST64_ABS_LO12_NC	.bss+0x38
     6ac: b9400117     	ldr	w23, [x8]
     6b0: d50331bf     	dmb	oshld
     6b4: 6a1602ff     	tst	w23, w22
     6b8: 2a1703e9     	mov	w9, w23
     6bc: 1a9f07e8     	cset	w8, ne
     6c0: eb18001f     	cmp	x0, x24
     6c4: ca090129     	eor	x9, x9, x9
     6c8: b5000009     	cbnz	x9, 0x6c8 <dsp_read+0x2f0>
     6cc: 1a9fd509     	csinc	w9, w8, wzr, le
     6d0: 37000249     	tbnz	w9, #0x0, 0x718 <dsp_read+0x340>
     6d4: 52800060     	mov	w0, #0x3                // =3
     6d8: 52800141     	mov	w1, #0xa                // =10
     6dc: 52800042     	mov	w2, #0x2                // =2
     6e0: 94000000     	bl	0x6e0 <dsp_read+0x308>
		00000000000006e0:  R_AARCH64_CALL26	usleep_range_state
     6e4: d503203f     	yield
     6e8: 94000000     	bl	0x6e8 <dsp_read+0x310>
		00000000000006e8:  R_AARCH64_CALL26	ktime_get
     6ec: f9400348     	ldr	x8, [x26]
		00000000000006ec:  R_AARCH64_LDST64_ABS_LO12_NC	.bss+0x38
     6f0: b9400117     	ldr	w23, [x8]
     6f4: d50331bf     	dmb	oshld
     6f8: 2a1703e8     	mov	w8, w23
     6fc: 6a1602e9     	ands	w9, w23, w22
     700: ca080108     	eor	x8, x8, x8
     704: b5000008     	cbnz	x8, 0x704 <dsp_read+0x32c>
     708: 1a9f07e8     	cset	w8, ne
     70c: 35000069     	cbnz	w9, 0x718 <dsp_read+0x340>
     710: eb18001f     	cmp	x0, x24
     714: 54fffe0d     	b.le	0x6d4 <dsp_read+0x2fc>
     718: 34000328     	cbz	w8, 0x77c <dsp_read+0x3a4>
     71c: f9400348     	ldr	x8, [x26]
		000000000000071c:  R_AARCH64_LDST64_ABS_LO12_NC	.bss+0x38
     720: 2a1f03f8     	mov	w24, wzr
     724: 8b394108     	add	x8, x8, w25, uxtw
     728: b9400108     	ldr	w8, [x8]
     72c: d50331bf     	dmb	oshld
     730: 2a0803e9     	mov	w9, w8
     734: ca090129     	eor	x9, x9, x9
     738: b5000009     	cbnz	x9, 0x738 <dsp_read+0x360>
     73c: b9000368     	str	w8, [x27]
     740: d5384108     	mrs	x8, SP_EL0
     744: f9420908     	ldr	x8, [x8, #0x410]
     748: f94007e9     	ldr	x9, [sp, #0x8]
     74c: eb09011f     	cmp	x8, x9
     750: 54000981     	b.ne	0x880 <dsp_read+0x4a8>
     754: 2a1803e0     	mov	w0, w24
     758: a9464ff4     	ldp	x20, x19, [sp, #0x60]
     75c: a94557f6     	ldp	x22, x21, [sp, #0x50]
     760: a9445ff8     	ldp	x24, x23, [sp, #0x40]
     764: a94367fa     	ldp	x26, x25, [sp, #0x30]
     768: a9426ffc     	ldp	x28, x27, [sp, #0x20]
     76c: a9417bfd     	ldp	x29, x30, [sp, #0x10]
     770: 9101c3ff     	add	sp, sp, #0x70
     774: d50323bf     	autiasp
     778: d65f03c0     	ret
     77c: 90000014     	adrp	x20, 0x0 <read_word>
		000000000000077c:  R_AARCH64_ADR_PREL_PG_HI21	.rodata.str1.1+0x485
     780: 91000294     	add	x20, x20, #0x0
		0000000000000780:  R_AARCH64_ADD_ABS_LO12_NC	.rodata.str1.1+0x485
     784: 17ffff7b     	b	0x570 <dsp_read+0x198>
     788: 94000000     	bl	0x788 <dsp_read+0x3b0>
		0000000000000788:  R_AARCH64_CALL26	ktime_get
     78c: 529e1008     	mov	w8, #0xf080             // =61568
     790: 72a05f48     	movk	w8, #0x2fa, lsl #16
     794: 8b080018     	add	x24, x0, x8
     798: 94000000     	bl	0x798 <dsp_read+0x3c0>
		0000000000000798:  R_AARCH64_CALL26	ktime_get
     79c: f9400348     	ldr	x8, [x26]
		000000000000079c:  R_AARCH64_LDST64_ABS_LO12_NC	.bss+0x38
     7a0: b9400108     	ldr	w8, [x8]
     7a4: d50331bf     	dmb	oshld
     7a8: 6a16011f     	tst	w8, w22
     7ac: 2a0803ea     	mov	w10, w8
     7b0: 1a9f17e9     	cset	w9, eq
     7b4: eb18001f     	cmp	x0, x24
     7b8: ca0a014a     	eor	x10, x10, x10
     7bc: b500000a     	cbnz	x10, 0x7bc <dsp_read+0x3e4>
     7c0: 1a9fd52a     	csinc	w10, w9, wzr, le
     7c4: 3700024a     	tbnz	w10, #0x0, 0x80c <dsp_read+0x434>
     7c8: 52800020     	mov	w0, #0x1                // =1
     7cc: 52800041     	mov	w1, #0x2                // =2
     7d0: 52800042     	mov	w2, #0x2                // =2
     7d4: 94000000     	bl	0x7d4 <dsp_read+0x3fc>
		00000000000007d4:  R_AARCH64_CALL26	usleep_range_state
     7d8: d503203f     	yield
     7dc: 94000000     	bl	0x7dc <dsp_read+0x404>
		00000000000007dc:  R_AARCH64_CALL26	ktime_get
     7e0: f9400348     	ldr	x8, [x26]
		00000000000007e0:  R_AARCH64_LDST64_ABS_LO12_NC	.bss+0x38
     7e4: b9400108     	ldr	w8, [x8]
     7e8: d50331bf     	dmb	oshld
     7ec: 2a0803e9     	mov	w9, w8
     7f0: ca090129     	eor	x9, x9, x9
     7f4: b5000009     	cbnz	x9, 0x7f4 <dsp_read+0x41c>
     7f8: 6a16010a     	ands	w10, w8, w22
     7fc: 1a9f17e9     	cset	w9, eq
     800: 3400006a     	cbz	w10, 0x80c <dsp_read+0x434>
     804: eb18001f     	cmp	x0, x24
     808: 54fffe0d     	b.le	0x7c8 <dsp_read+0x3f0>
     80c: 7100013f     	cmp	w9, #0x0
     810: 12800da9     	mov	w9, #-0x6e              // =-110
     814: b90007e8     	str	w8, [sp, #0x4]
     818: 1a8913f8     	csel	w24, wzr, w9, ne
     81c: 94000000     	bl	0x81c <dsp_read+0x444>
		000000000000081c:  R_AARCH64_CALL26	ktime_get
     820: d29ef9e8     	mov	x8, #0xf7cf             // =63439
     824: cb170009     	sub	x9, x0, x23
     828: 90000000     	adrp	x0, 0x0 <read_word>
		0000000000000828:  R_AARCH64_ADR_PREL_PG_HI21	.rodata.str1.1+0x1b5
     82c: 91000000     	add	x0, x0, #0x0
		000000000000082c:  R_AARCH64_ADD_ABS_LO12_NC	.rodata.str1.1+0x1b5
     830: f2bc6a68     	movk	x8, #0xe353, lsl #16
     834: 2a1303e1     	mov	w1, w19
     838: f2d374a8     	movk	x8, #0x9ba5, lsl #32
     83c: 2a1503e2     	mov	w2, w21
     840: 2a1803e4     	mov	w4, w24
     844: f2e41888     	movk	x8, #0x20c4, lsl #48
     848: 9b487d28     	smulh	x8, x9, x8
     84c: 9347fd09     	asr	x9, x8, #7
     850: 8b48fd28     	add	x8, x9, x8, lsr #63
     854: 91019103     	add	x3, x8, #0x64
     858: 94000000     	bl	0x858 <dsp_read+0x480>
		0000000000000858:  R_AARCH64_CALL26	_printk
     85c: 34fff1d8     	cbz	w24, 0x694 <dsp_read+0x2bc>
     860: 90000008     	adrp	x8, 0x0 <read_word>
		0000000000000860:  R_AARCH64_ADR_PREL_PG_HI21	.bss+0x1c
     864: b94007f7     	ldr	w23, [sp, #0x4]
     868: 90000014     	adrp	x20, 0x0 <read_word>
		0000000000000868:  R_AARCH64_ADR_PREL_PG_HI21	.rodata.str1.1+0x415
     86c: 91000294     	add	x20, x20, #0x0
		000000000000086c:  R_AARCH64_ADD_ABS_LO12_NC	.rodata.str1.1+0x415
     870: b9400109     	ldr	w9, [x8]
		0000000000000870:  R_AARCH64_LDST32_ABS_LO12_NC	.bss+0x1c
     874: 11000529     	add	w9, w9, #0x1
     878: b9000109     	str	w9, [x8]
		0000000000000878:  R_AARCH64_LDST32_ABS_LO12_NC	.bss+0x1c
     87c: 17ffff3e     	b	0x574 <dsp_read+0x19c>
     880: 94000000     	bl	0x880 <dsp_read+0x4a8>
		0000000000000880:  R_AARCH64_CALL26	__stack_chk_fail
