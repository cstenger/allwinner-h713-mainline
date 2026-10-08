
docs/hdmi-evidence/2026-10-07-android-audio/audio.primary.ares.so:     file format elf32-littlearm


Disassembly of section .text:

00009818 <_Z19connect_hdmiin_pathP18sunxi_audio_device@@Base>:
    9818:	b510      	push	{r4, lr}
    981a:	4922      	ldr	r1, [pc, #136]	@ (98a4 <_Z19connect_hdmiin_pathP18sunxi_audio_device@@Base+0x8c>)
    981c:	4604      	mov	r4, r0
    981e:	4a22      	ldr	r2, [pc, #136]	@ (98a8 <_Z19connect_hdmiin_pathP18sunxi_audio_device@@Base+0x90>)
    9820:	2003      	movs	r0, #3
    9822:	4479      	add	r1, pc
    9824:	447a      	add	r2, pc
    9826:	f00f e92c 	blx	18a80 <__aeabi_memclr@@Base+0x14c>
    982a:	f8d4 37a4 	ldr.w	r3, [r4, #1956]	@ 0x7a4
    982e:	491f      	ldr	r1, [pc, #124]	@ (98ac <_Z19connect_hdmiin_pathP18sunxi_audio_device@@Base+0x94>)
    9830:	2b01      	cmp	r3, #1
    9832:	4479      	add	r1, pc
    9834:	d113      	bne.n	985e <_Z19connect_hdmiin_pathP18sunxi_audio_device@@Base+0x46>
    9836:	4a1e      	ldr	r2, [pc, #120]	@ (98b0 <_Z19connect_hdmiin_pathP18sunxi_audio_device@@Base+0x98>)
    9838:	2003      	movs	r0, #3
    983a:	f8d4 37dc 	ldr.w	r3, [r4, #2012]	@ 0x7dc
    983e:	447a      	add	r2, pc
    9840:	f00f e91e 	blx	18a80 <__aeabi_memclr@@Base+0x14c>
    9844:	f8d4 07a0 	ldr.w	r0, [r4, #1952]	@ 0x7a0
    9848:	b180      	cbz	r0, 986c <_Z19connect_hdmiin_pathP18sunxi_audio_device@@Base+0x54>
    984a:	2802      	cmp	r0, #2
    984c:	d016      	beq.n	987c <_Z19connect_hdmiin_pathP18sunxi_audio_device@@Base+0x64>
    984e:	2801      	cmp	r0, #1
    9850:	d11d      	bne.n	988e <_Z19connect_hdmiin_pathP18sunxi_audio_device@@Base+0x76>
    9852:	f8d4 07dc 	ldr.w	r0, [r4, #2012]	@ 0x7dc
    9856:	2801      	cmp	r0, #1
    9858:	d816      	bhi.n	9888 <_Z19connect_hdmiin_pathP18sunxi_audio_device@@Base+0x70>
    985a:	2089      	movs	r0, #137	@ 0x89
    985c:	e015      	b.n	988a <_Z19connect_hdmiin_pathP18sunxi_audio_device@@Base+0x72>
    985e:	4a17      	ldr	r2, [pc, #92]	@ (98bc <_Z19connect_hdmiin_pathP18sunxi_audio_device@@Base+0xa4>)
    9860:	2003      	movs	r0, #3
    9862:	447a      	add	r2, pc
    9864:	e8bd 4010 	ldmia.w	sp!, {r4, lr}
    9868:	f00f b888 	b.w	1897c <__aeabi_memclr@@Base+0x48>
    986c:	4911      	ldr	r1, [pc, #68]	@ (98b4 <_Z19connect_hdmiin_pathP18sunxi_audio_device@@Base+0x9c>)
    986e:	2003      	movs	r0, #3
    9870:	4a11      	ldr	r2, [pc, #68]	@ (98b8 <_Z19connect_hdmiin_pathP18sunxi_audio_device@@Base+0xa0>)
    9872:	4479      	add	r1, pc
    9874:	447a      	add	r2, pc
    9876:	f00f e904 	blx	18a80 <__aeabi_memclr@@Base+0x14c>
    987a:	e008      	b.n	988e <_Z19connect_hdmiin_pathP18sunxi_audio_device@@Base+0x76>
    987c:	f8d4 07dc 	ldr.w	r0, [r4, #2012]	@ 0x7dc
    9880:	2801      	cmp	r0, #1
    9882:	d801      	bhi.n	9888 <_Z19connect_hdmiin_pathP18sunxi_audio_device@@Base+0x70>
    9884:	208f      	movs	r0, #143	@ 0x8f
    9886:	e000      	b.n	988a <_Z19connect_hdmiin_pathP18sunxi_audio_device@@Base+0x72>
    9888:	200a      	movs	r0, #10
    988a:	f00f ea2a 	blx	18ce0 <__aeabi_memclr@@Base+0x3ac>
    988e:	f8d4 07f4 	ldr.w	r0, [r4, #2036]	@ 0x7f4
    9892:	f8d4 17fc 	ldr.w	r1, [r4, #2044]	@ 0x7fc
    9896:	f00f ea2c 	blx	18cf0 <__aeabi_memclr@@Base+0x3bc>
    989a:	4620      	mov	r0, r4
    989c:	e8bd 4010 	ldmia.w	sp!, {r4, lr}
    98a0:	f00f b872 	b.w	18988 <__aeabi_memclr@@Base+0x54>
    98a4:	bf13      	iteet	ne
    98a6:	ffff d654 	vqshlune.s32	<illegal reg q14.5>, q2, #31
    98aa:	ffff bf03 			@ <UNDEFINED> instruction: 0xffffbf03
    98ae:	ffff b4e1 	vmlseq.i<illegal width 64>	<illegal reg q13.5>, <illegal reg q15.5>, d17[0]
    98b2:	ffff bec3 	vqrdmlahne.s<illegal width 64>	<illegal reg q13.5>, <illegal reg q15.5>, d3[0]
    98b6:	ffff ba06 	vtbl.8	d27, {d15-d17}, d6
    98ba:	ffff d4ae 	vraddhn.i<illegal width 128>	d29, <illegal reg q15.5>, q15
    98be:	Address 0x98be is out of bounds.


000098c0 <_Z15update_mts_modeP18sunxi_audio_device@@Base>:
    98c0:	b5f0      	push	{r4, r5, r6, r7, lr}
    98c2:	b089      	sub	sp, #36	@ 0x24
    98c4:	495c      	ldr	r1, [pc, #368]	@ (9a38 <_Z15update_mts_modeP18sunxi_audio_device@@Base+0x178>)
    98c6:	4479      	add	r1, pc
    98c8:	680d      	ldr	r5, [r1, #0]
    98ca:	6829      	ldr	r1, [r5, #0]
    98cc:	9108      	str	r1, [sp, #32]
    98ce:	f8d0 07a4 	ldr.w	r0, [r0, #1956]	@ 0x7a4
    98d2:	2802      	cmp	r0, #2
    98d4:	f040 80a7 	bne.w	9a26 <_Z15update_mts_modeP18sunxi_audio_device@@Base+0x166>
    98d8:	ae02      	add	r6, sp, #8
    98da:	efc0 0050 	vmov.i32	q8, #0	@ 0x00000000
    98de:	2000      	movs	r0, #0
    98e0:	4631      	mov	r1, r6
    98e2:	9001      	str	r0, [sp, #4]
    98e4:	f941 0acd 	vst1.64	{d16-d17}, [r1]!
    98e8:	6008      	str	r0, [r1, #0]
    98ea:	f00f ea12 	blx	18d10 <__aeabi_memclr@@Base+0x3dc>
    98ee:	4953      	ldr	r1, [pc, #332]	@ (9a3c <_Z15update_mts_modeP18sunxi_audio_device@@Base+0x17c>)
    98f0:	4604      	mov	r4, r0
    98f2:	4a53      	ldr	r2, [pc, #332]	@ (9a40 <_Z15update_mts_modeP18sunxi_audio_device@@Base+0x180>)
    98f4:	2003      	movs	r0, #3
    98f6:	4479      	add	r1, pc
    98f8:	4623      	mov	r3, r4
    98fa:	447a      	add	r2, pc
    98fc:	f00f e8c0 	blx	18a80 <__aeabi_memclr@@Base+0x14c>
    9900:	a801      	add	r0, sp, #4
    9902:	f44f 7116 	mov.w	r1, #600	@ 0x258
    9906:	f00f ea0c 	blx	18d20 <__aeabi_memclr@@Base+0x3ec>
    990a:	b108      	cbz	r0, 9910 <_Z15update_mts_modeP18sunxi_audio_device@@Base+0x50>
    990c:	9b02      	ldr	r3, [sp, #8]
    990e:	e077      	b.n	9a00 <_Z15update_mts_modeP18sunxi_audio_device@@Base+0x140>
    9910:	9801      	ldr	r0, [sp, #4]
    9912:	3801      	subs	r0, #1
    9914:	280b      	cmp	r0, #11
    9916:	d809      	bhi.n	992c <_Z15update_mts_modeP18sunxi_audio_device@@Base+0x6c>
    9918:	e8df f000 	tbb	[pc, r0]
    991c:	0a06      	lsrs	r6, r0, #8
    991e:	130c      	asrs	r4, r1, #12
    9920:	1e1c      	subs	r4, r3, #0
    9922:	2e24      	cmp	r6, #36	@ 0x24
    9924:	3730      	adds	r7, #48	@ 0x30
    9926:	7040      	strb	r0, [r0, #1]
    9928:	2301      	movs	r3, #1
    992a:	e068      	b.n	99fe <_Z15update_mts_modeP18sunxi_audio_device@@Base+0x13e>
    992c:	2300      	movs	r3, #0
    992e:	e066      	b.n	99fe <_Z15update_mts_modeP18sunxi_audio_device@@Base+0x13e>
    9930:	2302      	movs	r3, #2
    9932:	e064      	b.n	99fe <_Z15update_mts_modeP18sunxi_audio_device@@Base+0x13e>
    9934:	2302      	movs	r3, #2
    9936:	f04f 0c03 	mov.w	ip, #3
    993a:	2001      	movs	r0, #1
    993c:	2702      	movs	r7, #2
    993e:	9302      	str	r3, [sp, #8]
    9940:	e036      	b.n	99b0 <_Z15update_mts_modeP18sunxi_audio_device@@Base+0xf0>
    9942:	2005      	movs	r0, #5
    9944:	2704      	movs	r7, #4
    9946:	2302      	movs	r3, #2
    9948:	9004      	str	r0, [sp, #16]
    994a:	9703      	str	r7, [sp, #12]
    994c:	f04f 0c06 	mov.w	ip, #6
    9950:	9302      	str	r3, [sp, #8]
    9952:	e02c      	b.n	99ae <_Z15update_mts_modeP18sunxi_audio_device@@Base+0xee>
    9954:	2307      	movs	r3, #7
    9956:	e052      	b.n	99fe <_Z15update_mts_modeP18sunxi_audio_device@@Base+0x13e>
    9958:	2307      	movs	r3, #7
    995a:	2702      	movs	r7, #2
    995c:	9302      	str	r3, [sp, #8]
    995e:	f04f 0c08 	mov.w	ip, #8
    9962:	e010      	b.n	9986 <_Z15update_mts_modeP18sunxi_audio_device@@Base+0xc6>
    9964:	200a      	movs	r0, #10
    9966:	2307      	movs	r3, #7
    9968:	9004      	str	r0, [sp, #16]
    996a:	2009      	movs	r0, #9
    996c:	9003      	str	r0, [sp, #12]
    996e:	2704      	movs	r7, #4
    9970:	9302      	str	r3, [sp, #8]
    9972:	f04f 0c0b 	mov.w	ip, #11
    9976:	e01a      	b.n	99ae <_Z15update_mts_modeP18sunxi_audio_device@@Base+0xee>
    9978:	230c      	movs	r3, #12
    997a:	e040      	b.n	99fe <_Z15update_mts_modeP18sunxi_audio_device@@Base+0x13e>
    997c:	230c      	movs	r3, #12
    997e:	2702      	movs	r7, #2
    9980:	9302      	str	r3, [sp, #8]
    9982:	f04f 0c0d 	mov.w	ip, #13
    9986:	2001      	movs	r0, #1
    9988:	e012      	b.n	99b0 <_Z15update_mts_modeP18sunxi_audio_device@@Base+0xf0>
    998a:	200e      	movs	r0, #14
    998c:	230c      	movs	r3, #12
    998e:	9003      	str	r0, [sp, #12]
    9990:	2703      	movs	r7, #3
    9992:	9302      	str	r3, [sp, #8]
    9994:	f04f 0c0f 	mov.w	ip, #15
    9998:	2002      	movs	r0, #2
    999a:	e009      	b.n	99b0 <_Z15update_mts_modeP18sunxi_audio_device@@Base+0xf0>
    999c:	200e      	movs	r0, #14
    999e:	230c      	movs	r3, #12
    99a0:	9004      	str	r0, [sp, #16]
    99a2:	200d      	movs	r0, #13
    99a4:	9003      	str	r0, [sp, #12]
    99a6:	2704      	movs	r7, #4
    99a8:	9302      	str	r3, [sp, #8]
    99aa:	f04f 0c0f 	mov.w	ip, #15
    99ae:	2003      	movs	r0, #3
    99b0:	4924      	ldr	r1, [pc, #144]	@ (9a44 <_Z15update_mts_modeP18sunxi_audio_device@@Base+0x184>)
    99b2:	4a25      	ldr	r2, [pc, #148]	@ (9a48 <_Z15update_mts_modeP18sunxi_audio_device@@Base+0x188>)
    99b4:	4479      	add	r1, pc
    99b6:	f846 c020 	str.w	ip, [r6, r0, lsl #2]
    99ba:	447a      	add	r2, pc
    99bc:	2003      	movs	r0, #3
    99be:	f00f e860 	blx	18a80 <__aeabi_memclr@@Base+0x14c>
    99c2:	4630      	mov	r0, r6
    99c4:	6801      	ldr	r1, [r0, #0]
    99c6:	42a1      	cmp	r1, r4
    99c8:	d00c      	beq.n	99e4 <_Z15update_mts_modeP18sunxi_audio_device@@Base+0x124>
    99ca:	3004      	adds	r0, #4
    99cc:	3f01      	subs	r7, #1
    99ce:	d1f9      	bne.n	99c4 <_Z15update_mts_modeP18sunxi_audio_device@@Base+0x104>
    99d0:	9b03      	ldr	r3, [sp, #12]
    99d2:	1ed8      	subs	r0, r3, #3
    99d4:	2801      	cmp	r0, #1
    99d6:	d81b      	bhi.n	9a10 <_Z15update_mts_modeP18sunxi_audio_device@@Base+0x150>
    99d8:	4922      	ldr	r1, [pc, #136]	@ (9a64 <_Z15update_mts_modeP18sunxi_audio_device@@Base+0x1a4>)
    99da:	3604      	adds	r6, #4
    99dc:	4a22      	ldr	r2, [pc, #136]	@ (9a68 <_Z15update_mts_modeP18sunxi_audio_device@@Base+0x1a8>)
    99de:	4479      	add	r1, pc
    99e0:	447a      	add	r2, pc
    99e2:	e01a      	b.n	9a1a <_Z15update_mts_modeP18sunxi_audio_device@@Base+0x15a>
    99e4:	2c02      	cmp	r4, #2
    99e6:	d11e      	bne.n	9a26 <_Z15update_mts_modeP18sunxi_audio_device@@Base+0x166>
    99e8:	4918      	ldr	r1, [pc, #96]	@ (9a4c <_Z15update_mts_modeP18sunxi_audio_device@@Base+0x18c>)
    99ea:	2003      	movs	r0, #3
    99ec:	4a18      	ldr	r2, [pc, #96]	@ (9a50 <_Z15update_mts_modeP18sunxi_audio_device@@Base+0x190>)
    99ee:	9b03      	ldr	r3, [sp, #12]
    99f0:	4479      	add	r1, pc
    99f2:	447a      	add	r2, pc
    99f4:	f00f e844 	blx	18a80 <__aeabi_memclr@@Base+0x14c>
    99f8:	3604      	adds	r6, #4
    99fa:	e011      	b.n	9a20 <_Z15update_mts_modeP18sunxi_audio_device@@Base+0x160>
    99fc:	2310      	movs	r3, #16
    99fe:	9302      	str	r3, [sp, #8]
    9a00:	4914      	ldr	r1, [pc, #80]	@ (9a54 <_Z15update_mts_modeP18sunxi_audio_device@@Base+0x194>)
    9a02:	2003      	movs	r0, #3
    9a04:	4a14      	ldr	r2, [pc, #80]	@ (9a58 <_Z15update_mts_modeP18sunxi_audio_device@@Base+0x198>)
    9a06:	4479      	add	r1, pc
    9a08:	447a      	add	r2, pc
    9a0a:	f00f e83a 	blx	18a80 <__aeabi_memclr@@Base+0x14c>
    9a0e:	ae02      	add	r6, sp, #8
    9a10:	4912      	ldr	r1, [pc, #72]	@ (9a5c <_Z15update_mts_modeP18sunxi_audio_device@@Base+0x19c>)
    9a12:	4a13      	ldr	r2, [pc, #76]	@ (9a60 <_Z15update_mts_modeP18sunxi_audio_device@@Base+0x1a0>)
    9a14:	4479      	add	r1, pc
    9a16:	9b02      	ldr	r3, [sp, #8]
    9a18:	447a      	add	r2, pc
    9a1a:	2003      	movs	r0, #3
    9a1c:	f00f e830 	blx	18a80 <__aeabi_memclr@@Base+0x14c>
    9a20:	6830      	ldr	r0, [r6, #0]
    9a22:	f00f e986 	blx	18d30 <__aeabi_memclr@@Base+0x3fc>
    9a26:	9808      	ldr	r0, [sp, #32]
    9a28:	6829      	ldr	r1, [r5, #0]
    9a2a:	1a08      	subs	r0, r1, r0
    9a2c:	bf02      	ittt	eq
    9a2e:	2000      	moveq	r0, #0
    9a30:	b009      	addeq	sp, #36	@ 0x24
    9a32:	bdf0      	popeq	{r4, r5, r6, r7, pc}
    9a34:	f00f e854 	blx	18ae0 <__aeabi_memclr@@Base+0x1ac>
    9a38:	140a      	asrs	r2, r1, #16
    9a3a:	0001      	movs	r1, r0
    9a3c:	be3f      	bkpt	0x003f
    9a3e:	ffff c25a 	vrshr.u32	q14, q5, #1
    9a42:	ffff bd81 			@ <UNDEFINED> instruction: 0xffffbd81
    9a46:	ffff b378 	vrsra.u32	<illegal reg q13.5>, q12, #1
    9a4a:	ffff bd45 	vqrdmulh.s<illegal width 64>	<illegal reg q13.5>, <illegal reg q7.5>, d5[0]
    9a4e:	ffff c8da 			@ <UNDEFINED> instruction: 0xffffc8da
    9a52:	ffff bd2f 			@ <UNDEFINED> instruction: 0xffffbd2f
    9a56:	ffff b32a 	vsubw.u<illegal width 64>	<illegal reg q13.5>, <illegal reg q7.5>, d26
    9a5a:	ffff bd21 			@ <UNDEFINED> instruction: 0xffffbd21
    9a5e:	ffff b86e 	vtbx.8	d27, {d15}, d30
    9a62:	ffff bd57 	vcvt.u16.f16	<illegal reg q13.5>, <illegal reg q3.5>, #1
    9a66:	ffff e13d 	vsra.u32	d30, d29, #1
    9a6a:	Address 0x9a6a is out of bounds.


00009a6c <_Z16callback_processP18sunxi_audio_devicem@@Base>:
    9a6c:	b570      	push	{r4, r5, r6, lr}
    9a6e:	b098      	sub	sp, #96	@ 0x60
    9a70:	4604      	mov	r4, r0
    9a72:	4828      	ldr	r0, [pc, #160]	@ (9b14 <_Z16callback_processP18sunxi_audio_devicem@@Base+0xa8>)
    9a74:	4478      	add	r0, pc
    9a76:	6806      	ldr	r6, [r0, #0]
    9a78:	6830      	ldr	r0, [r6, #0]
    9a7a:	9017      	str	r0, [sp, #92]	@ 0x5c
    9a7c:	f894 00c0 	ldrb.w	r0, [r4, #192]	@ 0xc0
    9a80:	b138      	cbz	r0, 9a92 <_Z16callback_processP18sunxi_audio_devicem@@Base+0x26>
    9a82:	4925      	ldr	r1, [pc, #148]	@ (9b18 <_Z16callback_processP18sunxi_audio_devicem@@Base+0xac>)
    9a84:	2003      	movs	r0, #3
    9a86:	4a25      	ldr	r2, [pc, #148]	@ (9b1c <_Z16callback_processP18sunxi_audio_devicem@@Base+0xb0>)
    9a88:	4479      	add	r1, pc
    9a8a:	447a      	add	r2, pc
    9a8c:	f00e eff8 	blx	18a80 <__aeabi_memclr@@Base+0x14c>
    9a90:	e036      	b.n	9b00 <_Z16callback_processP18sunxi_audio_devicem@@Base+0x94>
    9a92:	460b      	mov	r3, r1
    9a94:	2903      	cmp	r1, #3
    9a96:	d11e      	bne.n	9ad6 <_Z16callback_processP18sunxi_audio_devicem@@Base+0x6a>
    9a98:	466d      	mov	r5, sp
    9a9a:	215c      	movs	r1, #92	@ 0x5c
    9a9c:	4628      	mov	r0, r5
    9a9e:	f00e efe0 	blx	18a60 <__aeabi_memclr@@Base+0x12c>
    9aa2:	481f      	ldr	r0, [pc, #124]	@ (9b20 <_Z16callback_processP18sunxi_audio_devicem@@Base+0xb4>)
    9aa4:	4629      	mov	r1, r5
    9aa6:	4a1f      	ldr	r2, [pc, #124]	@ (9b24 <_Z16callback_processP18sunxi_audio_devicem@@Base+0xb8>)
    9aa8:	4478      	add	r0, pc
    9aaa:	447a      	add	r2, pc
    9aac:	f00e efe0 	blx	18a70 <__aeabi_memclr@@Base+0x13c>
