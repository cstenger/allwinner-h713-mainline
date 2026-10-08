
docs/hdmi-evidence/2026-10-07-android-audio/audio.primary.ares.so:     file format elf32-littlearm


Disassembly of section .text:

00011364 <_Z13Sound_Connectm@@Base>:
   11364:	b570      	push	{r4, r5, r6, lr}
   11366:	b084      	sub	sp, #16
   11368:	4604      	mov	r4, r0
   1136a:	4815      	ldr	r0, [pc, #84]	@ (113c0 <_Z13Sound_Connectm@@Base+0x5c>)
   1136c:	4478      	add	r0, pc
   1136e:	6800      	ldr	r0, [r0, #0]
   11370:	6806      	ldr	r6, [r0, #0]
   11372:	b30e      	cbz	r6, 113b8 <_Z13Sound_Connectm@@Base+0x54>
   11374:	6870      	ldr	r0, [r6, #4]
   11376:	42a0      	cmp	r0, r4
   11378:	d01e      	beq.n	113b8 <_Z13Sound_Connectm@@Base+0x54>
   1137a:	4912      	ldr	r1, [pc, #72]	@ (113c4 <_Z13Sound_Connectm@@Base+0x60>)
   1137c:	f240 651e 	movw	r5, #1566	@ 0x61e
   11380:	4a11      	ldr	r2, [pc, #68]	@ (113c8 <_Z13Sound_Connectm@@Base+0x64>)
   11382:	4b12      	ldr	r3, [pc, #72]	@ (113cc <_Z13Sound_Connectm@@Base+0x68>)
   11384:	4479      	add	r1, pc
   11386:	447a      	add	r2, pc
   11388:	e9cd 5000 	strd	r5, r0, [sp]
   1138c:	447b      	add	r3, pc
   1138e:	2003      	movs	r0, #3
   11390:	9402      	str	r4, [sp, #8]
   11392:	f007 eb76 	blx	18a80 <__aeabi_memclr@@Base+0x14c>
   11396:	f008 ea44 	blx	19820 <__aeabi_memclr@@Base+0xeec>
   1139a:	4620      	mov	r0, r4
   1139c:	f008 ea48 	blx	19830 <__aeabi_memclr@@Base+0xefc>
   113a0:	b148      	cbz	r0, 113b6 <_Z13Sound_Connectm@@Base+0x52>
   113a2:	490b      	ldr	r1, [pc, #44]	@ (113d0 <_Z13Sound_Connectm@@Base+0x6c>)
   113a4:	4605      	mov	r5, r0
   113a6:	4a0b      	ldr	r2, [pc, #44]	@ (113d4 <_Z13Sound_Connectm@@Base+0x70>)
   113a8:	2003      	movs	r0, #3
   113aa:	4479      	add	r1, pc
   113ac:	4623      	mov	r3, r4
   113ae:	447a      	add	r2, pc
   113b0:	f007 eb66 	blx	18a80 <__aeabi_memclr@@Base+0x14c>
   113b4:	e001      	b.n	113ba <_Z13Sound_Connectm@@Base+0x56>
   113b6:	6074      	str	r4, [r6, #4]
   113b8:	2500      	movs	r5, #0
   113ba:	4628      	mov	r0, r5
   113bc:	b004      	add	sp, #16
   113be:	bd70      	pop	{r4, r5, r6, pc}
   113c0:	998c      	ldr	r1, [sp, #560]	@ 0x230
   113c2:	0000      	movs	r0, r0
   113c4:	5f73      	ldrsh	r3, [r6, r5]
   113c6:	ffff 40d1 	vshr.u64	q10, <illegal reg q0.5>, #1
   113ca:	ffff 3cd9 			@ <UNDEFINED> instruction: 0xffff3cd9
   113ce:	ffff 5f4d 	vqrdmlsh.s<illegal width 64>	<illegal reg q10.5>, <illegal reg q7.5>, d13[0]
   113d2:	ffff 5da0 			@ <UNDEFINED> instruction: 0xffff5da0
   113d6:	ffff b5b0 	vsli.64	d27, d16, #63	@ 0x3f
   113da:	b08a      	sub	sp, #40	@ 0x28
   113dc:	4604      	mov	r4, r0
   113de:	4813      	ldr	r0, [pc, #76]	@ (1142c <_Z13Sound_Connectm@@Base+0xc8>)
   113e0:	efc0 0050 	vmov.i32	q8, #0	@ 0x00000000
   113e4:	4478      	add	r0, pc
   113e6:	6805      	ldr	r5, [r0, #0]
   113e8:	6828      	ldr	r0, [r5, #0]
   113ea:	9009      	str	r0, [sp, #36]	@ 0x24
   113ec:	a802      	add	r0, sp, #8
   113ee:	f100 0208 	add.w	r2, r0, #8
   113f2:	f942 0acf 	vst1.64	{d16-d17}, [r2]
   113f6:	2200      	movs	r2, #0
   113f8:	9208      	str	r2, [sp, #32]
   113fa:	f243 020e 	movw	r2, #12302	@ 0x300e
   113fe:	e9cd 1202 	strd	r1, r2, [sp, #8]
   11402:	9405      	str	r4, [sp, #20]
   11404:	f008 e984 	blx	19710 <__aeabi_memclr@@Base+0xddc>
   11408:	4909      	ldr	r1, [pc, #36]	@ (11430 <_Z13Sound_Connectm@@Base+0xcc>)
   1140a:	2003      	movs	r0, #3
   1140c:	9b05      	ldr	r3, [sp, #20]
   1140e:	4a09      	ldr	r2, [pc, #36]	@ (11434 <_Z13Sound_Connectm@@Base+0xd0>)
   11410:	4479      	add	r1, pc
   11412:	9400      	str	r4, [sp, #0]
   11414:	447a      	add	r2, pc
   11416:	f007 eb34 	blx	18a80 <__aeabi_memclr@@Base+0x14c>
   1141a:	9809      	ldr	r0, [sp, #36]	@ 0x24
   1141c:	6829      	ldr	r1, [r5, #0]
   1141e:	1a08      	subs	r0, r1, r0
   11420:	bf04      	itt	eq
   11422:	b00a      	addeq	sp, #40	@ 0x28
   11424:	bdb0      	popeq	{r4, r5, r7, pc}
   11426:	f007 eb5c 	blx	18ae0 <__aeabi_memclr@@Base+0x1ac>
   1142a:	bf00      	nop
   1142c:	98ec      	ldr	r0, [sp, #944]	@ 0x3b0
   1142e:	0000      	movs	r0, r0
   11430:	5ee7      	ldrsh	r7, [r4, r3]
   11432:	ffff 4871 	vqrshrun.s64	d20, <illegal reg q8.5>, #1
   11436:	Address 0x11436 is out of bounds.


00011438 <_Z23Get_Audio_Standard_ModePc@@Base>:
   11438:	b5f0      	push	{r4, r5, r6, r7, lr}
   1143a:	b089      	sub	sp, #36	@ 0x24
   1143c:	4604      	mov	r4, r0
   1143e:	4830      	ldr	r0, [pc, #192]	@ (11500 <_Z23Get_Audio_Standard_ModePc@@Base+0xc8>)
   11440:	4930      	ldr	r1, [pc, #192]	@ (11504 <_Z23Get_Audio_Standard_ModePc@@Base+0xcc>)
   11442:	efc0 0050 	vmov.i32	q8, #0	@ 0x00000000
   11446:	4478      	add	r0, pc
   11448:	466a      	mov	r2, sp
   1144a:	4479      	add	r1, pc
   1144c:	6800      	ldr	r0, [r0, #0]
   1144e:	680e      	ldr	r6, [r1, #0]
   11450:	6800      	ldr	r0, [r0, #0]
   11452:	6831      	ldr	r1, [r6, #0]
   11454:	9108      	str	r1, [sp, #32]
   11456:	210c      	movs	r1, #12
   11458:	f942 0ac1 	vst1.64	{d16-d17}, [r2], r1
   1145c:	2800      	cmp	r0, #0
   1145e:	f942 0a8f 	vst1.32	{d16-d17}, [r2]
   11462:	d043      	beq.n	114ec <_Z23Get_Audio_Standard_ModePc@@Base+0xb4>
   11464:	6840      	ldr	r0, [r0, #4]
   11466:	f243 010c 	movw	r1, #12300	@ 0x300c
   1146a:	466d      	mov	r5, sp
