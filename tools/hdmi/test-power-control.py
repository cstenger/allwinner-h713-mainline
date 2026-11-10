#!/usr/bin/env python3
"""Exercise the actual driver's coldplug/unknown power-sampling body."""
from pathlib import Path
import subprocess
import tempfile
import unittest


class PowerControl(unittest.TestCase):
    def test_cold_zero_is_unknown_then_connection_and_availability_transitions(self):
        text = (Path(__file__).resolve().parents[2] / 'modules/hdmi-v4l2/h713-hdmi-v4l2.c').read_text()
        start = text.index('static void h713_power_sample(')
        brace, depth = text.index('{', start), 0
        for end in range(brace, len(text)):
            depth += (text[end] == '{') - (text[end] == '}')
            if depth == 0:
                break
        body = text[start:end+1]
        harness = r'''
#include <stdbool.h>
#include <assert.h>
struct v4l2_ctrl {struct {int val;} cur; bool active;};
struct h713_capture {struct v4l2_ctrl *power_present; bool power_valid,power_seen_present;};
static unsigned int sensed;
static bool readable=true;
static bool h713_read_power(struct h713_capture *c,unsigned int *v) {*v=sensed;return readable;}
static void v4l2_ctrl_lock(struct v4l2_ctrl *c) {}
static void v4l2_ctrl_unlock(struct v4l2_ctrl *c) {}
static void __v4l2_ctrl_s_ctrl(struct v4l2_ctrl *c,unsigned int v) {c->cur.val=v;}
static void v4l2_ctrl_activate(struct v4l2_ctrl *c,bool active) {c->active=active;}
#define pr_info(...) ((void)0)
'''
        main = r'''
int main(void) {
 struct v4l2_ctrl ctrl={0}; struct h713_capture c={.power_present=&ctrl};
 /* Observed cold boot: attached source but cache initially zero. */
 sensed=0;h713_power_sample(&c);assert(!ctrl.active && !c.power_valid);
 h713_power_sample(&c);assert(!ctrl.active);
 /* First positive qualifies subsequent negative samples. */
 sensed=1;h713_power_sample(&c);assert(ctrl.active && ctrl.cur.val==1);
 sensed=0;h713_power_sample(&c);assert(ctrl.active && ctrl.cur.val==0);
 /* Unavailable data never overwrites the last validated state. */
 sensed=1;readable=false;h713_power_sample(&c);assert(!ctrl.active && ctrl.cur.val==0);
 readable=true;h713_power_sample(&c);assert(ctrl.active && ctrl.cur.val==1);
 return 0;
}
'''
        with tempfile.TemporaryDirectory() as directory:
            source, binary = Path(directory)/'test.c', Path(directory)/'test'
            source.write_text(harness+body+main)
            subprocess.run(['cc', '-std=c11', '-Wall', '-Werror', str(source), '-o', str(binary)], check=True, capture_output=True)
            subprocess.run([str(binary)], check=True, capture_output=True)


if __name__ == '__main__':
    unittest.main()
