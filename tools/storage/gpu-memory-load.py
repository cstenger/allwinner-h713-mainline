#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0
"""Bounded offscreen Panfrost load; no display ownership or storage writes."""
import argparse
import ctypes as c
import json
import os
import time


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--seconds', type=int, default=600)
    a = p.parse_args()
    assert 1 <= a.seconds <= 600
    def bind(lib, name, result, *args):
        fn = getattr(lib, name); fn.restype = result; fn.argtypes = list(args)
        return fn
    ptr, integer, uint = c.c_void_p, c.c_int, c.c_uint
    egl, gl, gbm = [c.CDLL(n) for n in ('libEGL.so.1', 'libGLESv2.so.2', 'libgbm.so.1')]
    create = bind(gbm, 'gbm_create_device', ptr, integer)
    fd = os.open('/dev/dri/renderD129', os.O_RDWR | os.O_CLOEXEC)
    device = create(fd); assert device
    display = bind(egl, 'eglGetPlatformDisplay', ptr, uint, ptr, ptr)(0x31D7, device, None)
    major, minor = integer(), integer()
    assert bind(egl, 'eglInitialize', uint, ptr, ptr, ptr)(display, c.byref(major), c.byref(minor))
    assert bind(egl, 'eglBindAPI', uint, uint)(0x30A0)
    attrs = (integer*13)(0x3033, 0, 0x3040, 4, 0x3024, 8, 0x3023, 8, 0x3022, 8, 0x3021, 8, 0x3038)
    config, count = ptr(), integer()
    assert bind(egl, 'eglChooseConfig', uint, ptr, ptr, ptr, integer, ptr)(display, attrs, c.byref(config), 1, c.byref(count)) and count.value
    ctxattrs = (integer*3)(0x3098, 2, 0x3038)
    context = bind(egl, 'eglCreateContext', ptr, ptr, ptr, ptr, ptr)(display, config, None, ctxattrs)
    assert context
    assert bind(egl, 'eglMakeCurrent', uint, ptr, ptr, ptr, ptr)(display, None, None, context)
    renderer = bind(gl, 'glGetString', c.c_char_p, uint)(0x1F01).decode()
    assert 'Panfrost' in renderer, renderer
    shader_create = bind(gl, 'glCreateShader', uint, uint)
    shader_source = bind(gl, 'glShaderSource', None, uint, integer, ptr, ptr)
    shader_compile = bind(gl, 'glCompileShader', None, uint)
    shader_get = bind(gl, 'glGetShaderiv', None, uint, uint, ptr)
    shaders = []
    for kind, text in [(0x8B31, b'attribute vec2 p; void main(){gl_Position=vec4(p,0.,1.);}'),
                       (0x8B30, b'precision mediump float; void main(){gl_FragColor=vec4(gl_FragCoord.xy/vec2(3840.,2160.),0.25,1.);}')]:
        shader = shader_create(kind); source = c.c_char_p(text)
        shader_source(shader, 1, c.byref(source), None); shader_compile(shader)
        ok = integer(); shader_get(shader, 0x8B81, c.byref(ok)); assert ok.value
        shaders.append(shader)
    program = bind(gl, 'glCreateProgram', uint)()
    for shader in shaders: bind(gl, 'glAttachShader', None, uint, uint)(program, shader)
    bind(gl, 'glBindAttribLocation', None, uint, uint, c.c_char_p)(program, 0, b'p')
    bind(gl, 'glLinkProgram', None, uint)(program)
    ok = integer(); bind(gl, 'glGetProgramiv', None, uint, uint, ptr)(program, 0x8B82, c.byref(ok)); assert ok.value
    bind(gl, 'glUseProgram', None, uint)(program)
    fbo, rb = uint(), uint()
    bind(gl, 'glGenFramebuffers', None, integer, ptr)(1, c.byref(fbo))
    bind(gl, 'glBindFramebuffer', None, uint, uint)(0x8D40, fbo)
    bind(gl, 'glGenRenderbuffers', None, integer, ptr)(1, c.byref(rb))
    bind(gl, 'glBindRenderbuffer', None, uint, uint)(0x8D41, rb)
    bind(gl, 'glRenderbufferStorage', None, uint, uint, integer, integer)(0x8D41, 0x8056, 3840, 2160)
    bind(gl, 'glFramebufferRenderbuffer', None, uint, uint, uint, uint)(0x8D40, 0x8CE0, 0x8D41, rb)
    assert bind(gl, 'glCheckFramebufferStatus', uint, uint)(0x8D40) == 0x8CD5
    quad = (c.c_float*8)(-1,-1,1,-1,-1,1,1,1)
    bind(gl, 'glEnableVertexAttribArray', None, uint)(0)
    bind(gl, 'glVertexAttribPointer', None, uint, integer, uint, c.c_ubyte, integer, ptr)(0,2,0x1406,0,0,quad)
    bind(gl, 'glViewport', None, integer, integer, integer, integer)(0,0,3840,2160)
    draw = bind(gl, 'glDrawArrays', None, uint, integer, integer)
    finish = bind(gl, 'glFinish', None)
    draw(5,0,4); finish()
    pixel = (c.c_ubyte*4)()
    bind(gl, 'glReadPixels', None, integer, integer, integer, integer, uint, uint, ptr)(1920,1080,1,1,0x1908,0x1401,pixel)
    assert abs(pixel[0]-128)<24 and abs(pixel[1]-128)<24, list(pixel)
    print(json.dumps({'renderer':renderer,'pixel':list(pixel),'size':[3840,2160]}),flush=True)
    started = time.monotonic(); frames = 0
    while time.monotonic()-started < a.seconds:
        frame_start = time.monotonic()
        draw(5,0,4); finish(); frames += 1
        assert bind(gl, 'glGetError', uint)() == 0
        time.sleep(max(0,1/30-(time.monotonic()-frame_start)))
    print(json.dumps({'frames':frames,'seconds':time.monotonic()-started}),flush=True)
    bind(egl, 'eglMakeCurrent', uint, ptr, ptr, ptr, ptr)(display,None,None,None)
    bind(egl, 'eglDestroyContext', uint, ptr, ptr)(display,context)
    bind(egl, 'eglTerminate', uint, ptr)(display)
    bind(gbm, 'gbm_device_destroy', None, ptr)(device)
    os.close(fd)


if __name__ == '__main__':
    main()
