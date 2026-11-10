#!/usr/bin/env python3
"""Replay the observed live denial offline. No GPU transport/device imports."""
import json
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parent))
from protocol import Snapshot,Refused

class Denied:
    def __init__(self):
        self.events=json.loads((Path(__file__).parent/'fixtures/device-access-denied.json').read_text())
        self.cursor=0;self.closed=0;self.root=None;self.calls=[]
    def admit_root(self,root):self.root=root
    def exchange(self,call):
        request,reply=self.events[self.cursor:self.cursor+2]
        assert request['phase']=='intent' and reply['phase']=='returned'
        assert (call.kind,hex(call.code),list(call.words))==(request['kind'],request['code'],request['words'])
        self.cursor+=2;self.calls.append(call)
        return dict(status=reply['status'],words=tuple(reply['words']))
    def close(self):self.closed+=1

class Replay(unittest.TestCase):
    def test_observed_permission_failure(self):
        backend=Denied();session=Snapshot(backend)
        with self.assertRaisesRegex(Refused,'RM failure'):session.run()
        self.assertEqual(backend.cursor,12);self.assertEqual(backend.closed,1)
        self.assertEqual([c.code for c in backend.calls],[0x41,0x201,0x21b,0x205,0x80,0])
        self.assertIsNone(session.cleanup_error)
        self.assertEqual(backend.calls[-1].object,backend.root)
        self.assertFalse(any(c.code>=0x730000 for c in backend.calls))
        with self.assertRaises(Refused):session.run()
        self.assertEqual(len(backend.calls),6)

if __name__=='__main__':unittest.main(verbosity=2)
