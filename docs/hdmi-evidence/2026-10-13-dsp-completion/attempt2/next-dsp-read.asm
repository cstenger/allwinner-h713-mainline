
build/hdmi-dsp-stock-completion/h713-hdmi-dsp-probe.ko:	file format elf64-littleaarch64

Disassembly of section .text:

00000000000003d8 <dsp_read>:
     3d8: d503233f     	paciasp
     3dc: d101c3ff     	sub	sp, sp, #0x70
     3e0: a9017bfd     	stp	x29, x30, [sp, #0x10]
     3e4: 52801009     	mov	w9, #0x80               // =128
     3e8: 5280020a     	mov	w10, #0x10              // =16
     3ec: a9026ffc     	stp	x28, x27, [sp, #0x20]
     3f0: 529e101b     	mov	w27, #0xf080            // =61568
     3f4: 5280200b     	mov	w11, #0x100             // =256
     3f8: a90367fa     	stp	x26, x25, [sp, #0x30]
     3fc: 5280040c     	mov	w12, #0x20              // =32
     400: 5280030d     	mov	w13, #0x18              // =24
     404: a9045ff8     	stp	x24, x23, [sp, #0x40]
     408: 910043fd     	add	x29, sp, #0x10
     40c: 72a05f5b     	movk	w27, #0x2fa, lsl #16
     410: a90557f6     	stp	x22, x21, [sp, #0x50]
     414: 2a0103f5     	mov	w21, w1
     418: a9064ff4     	stp	x20, x19, [sp, #0x60]
     41c: d5384108     	mrs	x8, SP_EL0
     420: aa0203f4     	mov	x20, x2
     424: f9420908     	ldr	x8, [x8, #0x410]
     428: 7100001f     	cmp	w0, #0x0
     42c: 2a0003f3     	mov	w19, w0
     430: 1a890158     	csel	w24, w10, w9, eq
     434: 1a8b0196     	csel	w22, w12, w11, eq
     438: 1a8d0159     	csel	w25, w10, w13, eq
     43c: f90007e8     	str	x8, [sp, #0x8]
     440: 94000000     	bl	0x440 <dsp_read+0x68>
		0000000000000440:  R_AARCH64_CALL26	ktime_get
     444: 8b1b001c     	add	x28, x0, x27
     448: 94000000     	bl	0x448 <dsp_read+0x70>
		0000000000000448:  R_AARCH64_CALL26	ktime_get
     44c: 9000001a     	adrp	x26, 0x0 <read_word>
		000000000000044c:  R_AARCH64_ADR_PREL_PG_HI21	.bss+0x40
     450: f9400348     	ldr	x8, [x26]
		0000000000000450:  R_AARCH64_LDST64_ABS_LO12_NC	.bss+0x40
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
		0000000000000494:  R_AARCH64_LDST64_ABS_LO12_NC	.bss+0x40
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
     4c4: 340006e8     	cbz	w8, 0x5a0 <dsp_read+0x1c8>
     4c8: 90000000     	adrp	x0, 0x0 <read_word>
		00000000000004c8:  R_AARCH64_ADR_PREL_PG_HI21	.rodata.str1.1+0x25d
     4cc: 91000000     	add	x0, x0, #0x0
		00000000000004cc:  R_AARCH64_ADD_ABS_LO12_NC	.rodata.str1.1+0x25d
     4d0: 2a1303e1     	mov	w1, w19
     4d4: 2a1503e2     	mov	w2, w21
     4d8: 2a1703e3     	mov	w3, w23
     4dc: 94000000     	bl	0x4dc <dsp_read+0x104>
		00000000000004dc:  R_AARCH64_CALL26	_printk
     4e0: 90000008     	adrp	x8, 0x0 <read_word>
		00000000000004e0:  R_AARCH64_ADR_PREL_PG_HI21	.bss+0x10
     4e4: 39400108     	ldrb	w8, [x8]
		00000000000004e4:  R_AARCH64_LDST8_ABS_LO12_NC	.bss+0x10
     4e8: 340008e8     	cbz	w8, 0x604 <dsp_read+0x22c>
     4ec: f9400358     	ldr	x24, [x26]
		00000000000004ec:  R_AARCH64_LDST64_ABS_LO12_NC	.bss+0x40
     4f0: d50332bf     	dmb	oshst
     4f4: 53103ea8     	lsl	w8, w21, #16
     4f8: 8b39431c     	add	x28, x24, w25, uxtw
     4fc: b9000388     	str	w8, [x28]
     500: 94000000     	bl	0x500 <dsp_read+0x128>
		0000000000000500:  R_AARCH64_CALL26	ktime_get
     504: 8b1b001b     	add	x27, x0, x27
     508: 94000000     	bl	0x508 <dsp_read+0x130>
		0000000000000508:  R_AARCH64_CALL26	ktime_get
     50c: b9400317     	ldr	w23, [x24]
     510: d50331bf     	dmb	oshld
     514: 2a1703e8     	mov	w8, w23
     518: eb1b001f     	cmp	x0, x27
     51c: ca080108     	eor	x8, x8, x8
     520: b5000008     	cbnz	x8, 0x520 <dsp_read+0x148>
     524: 0a1602e8     	and	w8, w23, w22
     528: 7a40d900     	ccmp	w8, #0x0, #0x0, le
     52c: 54000201     	b.ne	0x56c <dsp_read+0x194>
     530: 52800060     	mov	w0, #0x3                // =3
     534: 52800141     	mov	w1, #0xa                // =10
     538: 52800042     	mov	w2, #0x2                // =2
     53c: 94000000     	bl	0x53c <dsp_read+0x164>
		000000000000053c:  R_AARCH64_CALL26	usleep_range_state
     540: d503203f     	yield
     544: 94000000     	bl	0x544 <dsp_read+0x16c>
		0000000000000544:  R_AARCH64_CALL26	ktime_get
     548: b9400317     	ldr	w23, [x24]
     54c: d50331bf     	dmb	oshld
     550: 2a1703e8     	mov	w8, w23
     554: ca080108     	eor	x8, x8, x8
     558: b5000008     	cbnz	x8, 0x558 <dsp_read+0x180>
     55c: 6a1602e8     	ands	w8, w23, w22
     560: 54000061     	b.ne	0x56c <dsp_read+0x194>
     564: eb1b001f     	cmp	x0, x27
     568: 54fffe4d     	b.le	0x530 <dsp_read+0x158>
     56c: 340014c8     	cbz	w8, 0x804 <dsp_read+0x42c>
     570: b9400388     	ldr	w8, [x28]
     574: d50331bf     	dmb	oshld
     578: 2a0803e9     	mov	w9, w8
     57c: ca090129     	eor	x9, x9, x9
     580: b5000009     	cbnz	x9, 0x580 <dsp_read+0x1a8>
     584: b9000288     	str	w8, [x20]
     588: 90000008     	adrp	x8, 0x0 <read_word>
		0000000000000588:  R_AARCH64_ADR_PREL_PG_HI21	.bss+0x14
     58c: b9400109     	ldr	w9, [x8]
		000000000000058c:  R_AARCH64_LDST32_ABS_LO12_NC	.bss+0x14
     590: 2a1f03f8     	mov	w24, wzr
     594: 11000529     	add	w9, w9, #0x1
     598: b9000109     	str	w9, [x8]
		0000000000000598:  R_AARCH64_LDST32_ABS_LO12_NC	.bss+0x14
     59c: 1400008b     	b	0x7c8 <dsp_read+0x3f0>
     5a0: 90000014     	adrp	x20, 0x0 <read_word>
		00000000000005a0:  R_AARCH64_ADR_PREL_PG_HI21	.rodata.str1.1+0x426
     5a4: 91000294     	add	x20, x20, #0x0
		00000000000005a4:  R_AARCH64_ADD_ABS_LO12_NC	.rodata.str1.1+0x426
     5a8: 12800db8     	mov	w24, #-0x6e             // =-110
     5ac: f9400348     	ldr	x8, [x26]
		00000000000005ac:  R_AARCH64_LDST64_ABS_LO12_NC	.bss+0x40
     5b0: 90000009     	adrp	x9, 0x0 <read_word>
		00000000000005b0:  R_AARCH64_ADR_PREL_PG_HI21	.bss+0x48
     5b4: 5280002a     	mov	w10, #0x1               // =1
     5b8: 3900012a     	strb	w10, [x9]
		00000000000005b8:  R_AARCH64_LDST8_ABS_LO12_NC	.bss+0x48
     5bc: 53103ea2     	lsl	w2, w21, #16
     5c0: 90000000     	adrp	x0, 0x0 <read_word>
		00000000000005c0:  R_AARCH64_ADR_PREL_PG_HI21	.rodata.str1.1+0x9a
     5c4: 91000000     	add	x0, x0, #0x0
		00000000000005c4:  R_AARCH64_ADD_ABS_LO12_NC	.rodata.str1.1+0x9a
     5c8: 8b394108     	add	x8, x8, w25, uxtw
     5cc: b9400101     	ldr	w1, [x8]
     5d0: d50331bf     	dmb	oshld
     5d4: 2a0103e8     	mov	w8, w1
     5d8: ca080108     	eor	x8, x8, x8
     5dc: b5000008     	cbnz	x8, 0x5dc <dsp_read+0x204>
     5e0: 94000000     	bl	0x5e0 <dsp_read+0x208>
		00000000000005e0:  R_AARCH64_CALL26	_printk
     5e4: 90000000     	adrp	x0, 0x0 <read_word>
		00000000000005e4:  R_AARCH64_ADR_PREL_PG_HI21	.rodata.str1.1+0x2a0
     5e8: 91000000     	add	x0, x0, #0x0
		00000000000005e8:  R_AARCH64_ADD_ABS_LO12_NC	.rodata.str1.1+0x2a0
     5ec: 2a1303e1     	mov	w1, w19
     5f0: 2a1503e2     	mov	w2, w21
     5f4: aa1403e3     	mov	x3, x20
     5f8: 2a1703e4     	mov	w4, w23
     5fc: 94000000     	bl	0x5fc <dsp_read+0x224>
		00000000000005fc:  R_AARCH64_CALL26	_printk
     600: 14000072     	b	0x7c8 <dsp_read+0x3f0>
     604: d53b4237     	mrs	x23, DAIF
     608: d50343df     	msr	DAIFSet, #0x3
     60c: 90000018     	adrp	x24, 0x0 <read_word>
		000000000000060c:  R_AARCH64_ADR_PREL_PG_HI21	.bss+0x18
     610: 39400308     	ldrb	w8, [x24]
		0000000000000610:  R_AARCH64_LDST8_ABS_LO12_NC	.bss+0x18
     614: 34000228     	cbz	w8, 0x658 <dsp_read+0x280>
     618: 94000000     	bl	0x618 <dsp_read+0x240>
		0000000000000618:  R_AARCH64_CALL26	ktime_get
     61c: f9400348     	ldr	x8, [x26]
		000000000000061c:  R_AARCH64_LDST64_ABS_LO12_NC	.bss+0x40
     620: d50332bf     	dmb	oshst
     624: 53103ea9     	lsl	w9, w21, #16
     628: 910013e1     	add	x1, sp, #0x4
     62c: 2a1603e2     	mov	w2, w22
     630: 8b394108     	add	x8, x8, w25, uxtw
     634: b9000109     	str	w9, [x8]
     638: 91406009     	add	x9, x0, #0x18, lsl #12  // =0x18000
     63c: f9400348     	ldr	x8, [x26]
		000000000000063c:  R_AARCH64_LDST64_ABS_LO12_NC	.bss+0x40
     640: 911a8123     	add	x3, x9, #0x6a0
     644: aa0803e0     	mov	x0, x8
     648: 940000af     	bl	0x904 <h713_dsp_wait_clear_until>
     64c: d51b4237     	msr	DAIF, x23
     650: 34000620     	cbz	w0, 0x714 <dsp_read+0x33c>
     654: 14000021     	b	0x6d8 <dsp_read+0x300>
     658: f9400348     	ldr	x8, [x26]
		0000000000000658:  R_AARCH64_LDST64_ABS_LO12_NC	.bss+0x40
     65c: d50332bf     	dmb	oshst
     660: 53103ea9     	lsl	w9, w21, #16
     664: 8b394108     	add	x8, x8, w25, uxtw
     668: b9000109     	str	w9, [x8]
     66c: f9400348     	ldr	x8, [x26]
		000000000000066c:  R_AARCH64_LDST64_ABS_LO12_NC	.bss+0x40
     670: b9400108     	ldr	w8, [x8]
     674: d50331bf     	dmb	oshld
     678: 2a0803e9     	mov	w9, w8
     67c: ca090129     	eor	x9, x9, x9
     680: b5000009     	cbnz	x9, 0x680 <dsp_read+0x2a8>
     684: 6a16011f     	tst	w8, w22
     688: 54000440     	b.eq	0x710 <dsp_read+0x338>
     68c: 5290d408     	mov	w8, #0x86a0             // =34464
     690: 72a00028     	movk	w8, #0x1, lsl #16
     694: 910fa51c     	add	x28, x8, #0x3e9
     698: 528218e0     	mov	w0, #0x10c7             // =4295
     69c: 94000000     	bl	0x69c <dsp_read+0x2c4>
		000000000000069c:  R_AARCH64_CALL26	__const_udelay
     6a0: d503203f     	yield
     6a4: f9400348     	ldr	x8, [x26]
		00000000000006a4:  R_AARCH64_LDST64_ABS_LO12_NC	.bss+0x40
     6a8: b9400108     	ldr	w8, [x8]
     6ac: d50331bf     	dmb	oshld
     6b0: 2a0803e9     	mov	w9, w8
     6b4: ca090129     	eor	x9, x9, x9
     6b8: b5000009     	cbnz	x9, 0x6b8 <dsp_read+0x2e0>
     6bc: 6a16011f     	tst	w8, w22
     6c0: 54000280     	b.eq	0x710 <dsp_read+0x338>
     6c4: d10fa79c     	sub	x28, x28, #0x3e9
     6c8: f10fa79f     	cmp	x28, #0x3e9
     6cc: 54fffe6a     	b.ge	0x698 <dsp_read+0x2c0>
     6d0: b90007e8     	str	w8, [sp, #0x4]
     6d4: d51b4237     	msr	DAIF, x23
     6d8: 94000000     	bl	0x6d8 <dsp_read+0x300>
		00000000000006d8:  R_AARCH64_CALL26	ktime_get
     6dc: 90000008     	adrp	x8, 0x0 <read_word>
		00000000000006dc:  R_AARCH64_ADR_PREL_PG_HI21	.bss+0x20
     6e0: 3940030a     	ldrb	w10, [x24]
		00000000000006e0:  R_AARCH64_LDST8_ABS_LO12_NC	.bss+0x18
     6e4: aa0003f7     	mov	x23, x0
     6e8: b9400109     	ldr	w9, [x8]
		00000000000006e8:  R_AARCH64_LDST32_ABS_LO12_NC	.bss+0x20
     6ec: 11000529     	add	w9, w9, #0x1
     6f0: b9000109     	str	w9, [x8]
		00000000000006f0:  R_AARCH64_LDST32_ABS_LO12_NC	.bss+0x20
     6f4: 340008ea     	cbz	w10, 0x810 <dsp_read+0x438>
     6f8: f9400340     	ldr	x0, [x26]
		00000000000006f8:  R_AARCH64_LDST64_ABS_LO12_NC	.bss+0x40
     6fc: 910013e1     	add	x1, sp, #0x4
     700: 2a1603e2     	mov	w2, w22
     704: 940000a5     	bl	0x998 <h713_dsp_wait_clear>
     708: 2a0003f8     	mov	w24, w0
     70c: 14000064     	b	0x89c <dsp_read+0x4c4>
     710: d51b4237     	msr	DAIF, x23
     714: 90000008     	adrp	x8, 0x0 <read_word>
		0000000000000714:  R_AARCH64_ADR_PREL_PG_HI21	.bss+0x1c
     718: b9400109     	ldr	w9, [x8]
		0000000000000718:  R_AARCH64_LDST32_ABS_LO12_NC	.bss+0x1c
     71c: 11000529     	add	w9, w9, #0x1
     720: b9000109     	str	w9, [x8]
		0000000000000720:  R_AARCH64_LDST32_ABS_LO12_NC	.bss+0x1c
     724: 94000000     	bl	0x724 <dsp_read+0x34c>
		0000000000000724:  R_AARCH64_CALL26	ktime_get
     728: 8b1b0018     	add	x24, x0, x27
     72c: 94000000     	bl	0x72c <dsp_read+0x354>
		000000000000072c:  R_AARCH64_CALL26	ktime_get
     730: f9400348     	ldr	x8, [x26]
		0000000000000730:  R_AARCH64_LDST64_ABS_LO12_NC	.bss+0x40
     734: b9400117     	ldr	w23, [x8]
     738: d50331bf     	dmb	oshld
     73c: 6a1602ff     	tst	w23, w22
     740: 2a1703e9     	mov	w9, w23
     744: 1a9f07e8     	cset	w8, ne
     748: eb18001f     	cmp	x0, x24
     74c: ca090129     	eor	x9, x9, x9
     750: b5000009     	cbnz	x9, 0x750 <dsp_read+0x378>
     754: 1a9fd509     	csinc	w9, w8, wzr, le
     758: 37000249     	tbnz	w9, #0x0, 0x7a0 <dsp_read+0x3c8>
     75c: 52800060     	mov	w0, #0x3                // =3
     760: 52800141     	mov	w1, #0xa                // =10
     764: 52800042     	mov	w2, #0x2                // =2
     768: 94000000     	bl	0x768 <dsp_read+0x390>
		0000000000000768:  R_AARCH64_CALL26	usleep_range_state
     76c: d503203f     	yield
     770: 94000000     	bl	0x770 <dsp_read+0x398>
		0000000000000770:  R_AARCH64_CALL26	ktime_get
     774: f9400348     	ldr	x8, [x26]
		0000000000000774:  R_AARCH64_LDST64_ABS_LO12_NC	.bss+0x40
     778: b9400117     	ldr	w23, [x8]
     77c: d50331bf     	dmb	oshld
     780: 2a1703e8     	mov	w8, w23
     784: 6a1602e9     	ands	w9, w23, w22
     788: ca080108     	eor	x8, x8, x8
     78c: b5000008     	cbnz	x8, 0x78c <dsp_read+0x3b4>
     790: 1a9f07e8     	cset	w8, ne
     794: 35000069     	cbnz	w9, 0x7a0 <dsp_read+0x3c8>
     798: eb18001f     	cmp	x0, x24
     79c: 54fffe0d     	b.le	0x75c <dsp_read+0x384>
     7a0: 34000328     	cbz	w8, 0x804 <dsp_read+0x42c>
     7a4: f9400348     	ldr	x8, [x26]
		00000000000007a4:  R_AARCH64_LDST64_ABS_LO12_NC	.bss+0x40
     7a8: 2a1f03f8     	mov	w24, wzr
     7ac: 8b394108     	add	x8, x8, w25, uxtw
     7b0: b9400108     	ldr	w8, [x8]
     7b4: d50331bf     	dmb	oshld
     7b8: 2a0803e9     	mov	w9, w8
     7bc: ca090129     	eor	x9, x9, x9
     7c0: b5000009     	cbnz	x9, 0x7c0 <dsp_read+0x3e8>
     7c4: b9000288     	str	w8, [x20]
     7c8: d5384108     	mrs	x8, SP_EL0
     7cc: f9420908     	ldr	x8, [x8, #0x410]
     7d0: f94007e9     	ldr	x9, [sp, #0x8]
     7d4: eb09011f     	cmp	x8, x9
     7d8: 54000941     	b.ne	0x900 <dsp_read+0x528>
     7dc: 2a1803e0     	mov	w0, w24
     7e0: a9464ff4     	ldp	x20, x19, [sp, #0x60]
     7e4: a94557f6     	ldp	x22, x21, [sp, #0x50]
     7e8: a9445ff8     	ldp	x24, x23, [sp, #0x40]
     7ec: a94367fa     	ldp	x26, x25, [sp, #0x30]
     7f0: a9426ffc     	ldp	x28, x27, [sp, #0x20]
     7f4: a9417bfd     	ldp	x29, x30, [sp, #0x10]
     7f8: 9101c3ff     	add	sp, sp, #0x70
     7fc: d50323bf     	autiasp
     800: d65f03c0     	ret
     804: 90000014     	adrp	x20, 0x0 <read_word>
		0000000000000804:  R_AARCH64_ADR_PREL_PG_HI21	.rodata.str1.1+0x485
     808: 91000294     	add	x20, x20, #0x0
		0000000000000808:  R_AARCH64_ADD_ABS_LO12_NC	.rodata.str1.1+0x485
     80c: 17ffff67     	b	0x5a8 <dsp_read+0x1d0>
     810: 94000000     	bl	0x810 <dsp_read+0x438>
		0000000000000810:  R_AARCH64_CALL26	ktime_get
     814: 8b1b0018     	add	x24, x0, x27
     818: 94000000     	bl	0x818 <dsp_read+0x440>
		0000000000000818:  R_AARCH64_CALL26	ktime_get
     81c: f9400348     	ldr	x8, [x26]
		000000000000081c:  R_AARCH64_LDST64_ABS_LO12_NC	.bss+0x40
     820: b9400108     	ldr	w8, [x8]
     824: d50331bf     	dmb	oshld
     828: 6a16011f     	tst	w8, w22
     82c: 2a0803ea     	mov	w10, w8
     830: 1a9f17e9     	cset	w9, eq
     834: eb18001f     	cmp	x0, x24
     838: ca0a014a     	eor	x10, x10, x10
     83c: b500000a     	cbnz	x10, 0x83c <dsp_read+0x464>
     840: 1a9fd52a     	csinc	w10, w9, wzr, le
     844: 3700024a     	tbnz	w10, #0x0, 0x88c <dsp_read+0x4b4>
     848: 52800020     	mov	w0, #0x1                // =1
     84c: 52800041     	mov	w1, #0x2                // =2
     850: 52800042     	mov	w2, #0x2                // =2
     854: 94000000     	bl	0x854 <dsp_read+0x47c>
		0000000000000854:  R_AARCH64_CALL26	usleep_range_state
     858: d503203f     	yield
     85c: 94000000     	bl	0x85c <dsp_read+0x484>
		000000000000085c:  R_AARCH64_CALL26	ktime_get
     860: f9400348     	ldr	x8, [x26]
		0000000000000860:  R_AARCH64_LDST64_ABS_LO12_NC	.bss+0x40
     864: b9400108     	ldr	w8, [x8]
     868: d50331bf     	dmb	oshld
     86c: 2a0803e9     	mov	w9, w8
     870: ca090129     	eor	x9, x9, x9
     874: b5000009     	cbnz	x9, 0x874 <dsp_read+0x49c>
     878: 6a16010a     	ands	w10, w8, w22
     87c: 1a9f17e9     	cset	w9, eq
     880: 3400006a     	cbz	w10, 0x88c <dsp_read+0x4b4>
     884: eb18001f     	cmp	x0, x24
     888: 54fffe0d     	b.le	0x848 <dsp_read+0x470>
     88c: 7100013f     	cmp	w9, #0x0
     890: 12800da9     	mov	w9, #-0x6e              // =-110
     894: b90007e8     	str	w8, [sp, #0x4]
     898: 1a8913f8     	csel	w24, wzr, w9, ne
     89c: 94000000     	bl	0x89c <dsp_read+0x4c4>
		000000000000089c:  R_AARCH64_CALL26	ktime_get
     8a0: d29ef9e8     	mov	x8, #0xf7cf             // =63439
     8a4: cb170009     	sub	x9, x0, x23
     8a8: 90000000     	adrp	x0, 0x0 <read_word>
		00000000000008a8:  R_AARCH64_ADR_PREL_PG_HI21	.rodata.str1.1+0x1b5
     8ac: 91000000     	add	x0, x0, #0x0
		00000000000008ac:  R_AARCH64_ADD_ABS_LO12_NC	.rodata.str1.1+0x1b5
     8b0: f2bc6a68     	movk	x8, #0xe353, lsl #16
     8b4: 2a1303e1     	mov	w1, w19
     8b8: f2d374a8     	movk	x8, #0x9ba5, lsl #32
     8bc: 2a1503e2     	mov	w2, w21
     8c0: 2a1803e4     	mov	w4, w24
     8c4: f2e41888     	movk	x8, #0x20c4, lsl #48
     8c8: 9b487d28     	smulh	x8, x9, x8
     8cc: 9347fd09     	asr	x9, x8, #7
     8d0: 8b48fd28     	add	x8, x9, x8, lsr #63
     8d4: 91019103     	add	x3, x8, #0x64
     8d8: 94000000     	bl	0x8d8 <dsp_read+0x500>
		00000000000008d8:  R_AARCH64_CALL26	_printk
     8dc: 34fff258     	cbz	w24, 0x724 <dsp_read+0x34c>
     8e0: 90000008     	adrp	x8, 0x0 <read_word>
		00000000000008e0:  R_AARCH64_ADR_PREL_PG_HI21	.bss+0x24
     8e4: b94007f7     	ldr	w23, [sp, #0x4]
     8e8: 90000014     	adrp	x20, 0x0 <read_word>
		00000000000008e8:  R_AARCH64_ADR_PREL_PG_HI21	.rodata.str1.1+0x415
     8ec: 91000294     	add	x20, x20, #0x0
		00000000000008ec:  R_AARCH64_ADD_ABS_LO12_NC	.rodata.str1.1+0x415
     8f0: b9400109     	ldr	w9, [x8]
		00000000000008f0:  R_AARCH64_LDST32_ABS_LO12_NC	.bss+0x24
     8f4: 11000529     	add	w9, w9, #0x1
     8f8: b9000109     	str	w9, [x8]
		00000000000008f8:  R_AARCH64_LDST32_ABS_LO12_NC	.bss+0x24
     8fc: 17ffff2c     	b	0x5ac <dsp_read+0x1d4>
     900: 94000000     	bl	0x900 <dsp_read+0x528>
		0000000000000900:  R_AARCH64_CALL26	__stack_chk_fail
