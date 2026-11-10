#!/usr/bin/env python3
"""Exercise the actual copy/worker C bodies with deterministic producer races.

This tests control flow, not DMA coherency or the timing of physical hardware.
No test code or instrumented module is installed on the board.
"""
from pathlib import Path
import subprocess
import tempfile
import unittest

SOURCE=Path(__file__).resolve().parents[2]/'modules/hdmi-v4l2/h713-hdmi-v4l2.c'


def function(text,name):
    start=text.index('static int '+name+'(');brace=text.index('{',start);depth=0
    for i in range(brace,len(text)):
        depth+=(text[i]=='{')-(text[i]=='}')
        if depth==0:return text[start:i+1]
    raise AssertionError('unclosed function')


STUBS=r'''
#include <stdint.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <errno.h>
typedef uint8_t u8; typedef uint32_t u32; typedef uint64_t u64;
#define V4L2_PIX_FMT_NV12 1
#define V4L2_FIELD_NONE 0
#define VB2_BUF_STATE_DONE 1
#define VB2_BUF_STATE_ERROR 2
#define H713_SIG_LOCKED 1
#define H713_SIG_HOLD 2
#define H713_BACKSTOP_MS 3000
#define H713_MISMATCH_MS 3000
#define pr_warn(...) ((void)0)
#define pr_info(...) ((void)0)
#define time_after(a,b) ((a)>(b))
#define msecs_to_jiffies(a) (a)
#define div_u64(a,b) ((a)/(b))
struct vb2_buffer { u64 timestamp; };
struct h713_buffer { struct {struct vb2_buffer vb2_buf; u64 timestamp; unsigned sequence,field;} vb; };
struct h713_capture { unsigned fourcc,plane_size,frame_size,width,height,stream_width,stream_height,sequence; int queue; };
struct h713_sig { unsigned state,width,height; };
static unsigned long frames_produced,frames_rejected,frames_overwritten,frames_delivered,jiffies;
static int verify_full=-1; static bool pair_mode=true;
static int step,fault,hash_calls,copied,done,queue_errors,buffer_errors,unsafe_delivery;
static u8 planes[2][64],destination[64]; static struct h713_buffer buffer;
static u8 *h713_plane(struct h713_capture *c,unsigned p) {return planes[p%2];}
static u32 h713_hash_plane(struct h713_capture *c,unsigned p) {
    hash_calls++;return p+10+(step==1 && fault==1 && hash_calls>=3);
}
static void h713_nv16_to_nv12(u8 *d,const u8 *y,const u8 *uv,unsigned w,unsigned h) {
    memset(d,step,8);copied=1;
}
static int h713_nv12_matches(u8 *d,const u8 *y,const u8 *uv,unsigned w,unsigned h) {return 1;}
static struct h713_buffer *h713_take_buffer(struct h713_capture *c) {return &buffer;}
static void h713_return_buffers(struct h713_capture *c,int state) {buffer_errors++;}
static void vb2_queue_error(int *q) {queue_errors++;}
static void vb2_buffer_done(struct vb2_buffer *b,int state) {
    if(state!=VB2_BUF_STATE_DONE) {buffer_errors++;return;}
    done++;if(step==1 && fault)unsafe_delivery++;
}
static u8 *vb2_plane_vaddr(struct vb2_buffer *b,int n) {return destination;}
static void vb2_set_plane_payload(struct vb2_buffer *b,int n,unsigned len) {}
static void h713_sig_snapshot(struct h713_capture *c,struct h713_sig *s) {
    s->state=H713_SIG_LOCKED;s->width=c->width;s->height=c->height;
}
static const char *h713_sig_name(unsigned state) {return "locked";}
static int h713_afbd_pair_index(struct h713_capture *c) {
    int idx=step%3;return step==1 && fault==2 && copied ? (idx+1)%3 : idx;
}
static bool kthread_should_stop(void) {return step>=2;}
static void usleep_range(int a,int b) {step++;jiffies++;hash_calls=0;copied=0;}
static u64 ktime_get_ns(void) {static u64 t;return t+=100000;}
static void h713_fill_black(struct h713_capture *c,u8 *d) {memset(d,0,8);}
static void h713_park_until_stopped(void) {}
'''

MAIN=r'''
int main(int argc,char **argv) {
    fault=atoi(argv[1]);
    struct h713_capture c={.fourcc=V4L2_PIX_FMT_NV12,.plane_size=4,.width=2,.height=2,.stream_width=2,.stream_height=2};
    int rc=h713_capture_thread_pair(&c);
    unsigned expected_rejects=fault?1:0, expected_delivered=fault?1:2;
    if(rc || frames_produced!=2 || frames_rejected!=expected_rejects || frames_delivered!=expected_delivered || done!=expected_delivered || unsafe_delivery || queue_errors || buffer_errors || c.sequence!=2) {
        fprintf(stderr,"fault=%d produced=%lu rejects=%lu delivered=%lu done=%d unsafe=%d queue=%d buffers=%d sequence=%u\n",fault,frames_produced,frames_rejected,frames_delivered,done,unsafe_delivery,queue_errors,buffer_errors,c.sequence);
        return 1;
    }
    return 0;
}
'''


class Tests(unittest.TestCase):
    def test_actual_worker_discards_raced_copy_then_delivers_next_good_frame(self):
        text=SOURCE.read_text();copy=function(text,'h713_copy_frame');worker=function(text,'h713_capture_thread_pair')
        guard='if (h713_copy_frame(cap, dst, (idx + 2) % 3) ||\n\t\t    h713_afbd_pair_index(cap) != idx)'
        self.assertEqual(worker.count(guard),1)
        with tempfile.TemporaryDirectory() as td:
            for mutated in (False,True):
                src=Path(td)/('mutant.c' if mutated else 'actual.c');exe=src.with_suffix('')
                src.write_text(STUBS+copy+'\n'+(worker.replace(guard,'if (0)') if mutated else worker)+MAIN)
                subprocess.run(['cc','-std=c11','-O1',str(src),'-o',str(exe)],check=True,capture_output=True)
                for fault in (0,1,2):
                    p=subprocess.run([str(exe),str(fault)],capture_output=True,text=True,timeout=5)
                    with self.subTest(mutated=mutated,fault=fault):
                        if mutated and fault:self.assertNotEqual(p.returncode,0,'guard bypass escaped detection')
                        else:self.assertEqual(p.returncode,0,p.stderr)


if __name__=='__main__':unittest.main()
