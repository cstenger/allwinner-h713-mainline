#!/usr/bin/env python3
import copy
import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('observer',Path(__file__).with_name('regression-observer.py'))
o = importlib.util.module_from_spec(spec);spec.loader.exec_module(o)


def rows(states):
    return [dict(boot_id='same-boot',uptime=i*5,signal=state,errors={k:0 for k in o.ERRORS},
                 owner_ready='Y',owner_failed='N',frames=i*300,
                 services={n:dict(ActiveState='active',NRestarts='0',ExecMainStartTimestampMonotonic='123') for n in o.UNITS})
            for i,state in enumerate(states)]


class Tests(unittest.TestCase):
    def test_recovery_requires_loss_and_sustained_return(self):
        good=rows(['locked 1280x720','none']+['locked 1280x720']*4)
        self.assertEqual(o.analyze(good,'recovery')['result'],'PASS')
        for bad in [rows(['locked 1280x720']*5),good[:3],good[:-1]+[dict(good[-1],signal='none')]]:
            with self.assertRaises(ValueError):o.analyze(bad,'recovery')

    def test_errors_restart_boot_change_and_gaps_fail(self):
        good=rows(['locked 1280x720','none']+['locked 1280x720']*4)
        for fault in ['boot','gap','counter','owner','restart','replaced','missing']:
            bad=copy.deepcopy(good)
            if fault=='boot':bad[-1]['boot_id']='other'
            if fault=='gap':bad[-1]['uptime']+=20
            if fault=='counter':bad[-1]['errors']['xruns']=1
            if fault=='owner':bad[-1]['owner_failed']='Y'
            if fault=='restart':bad[-1]['services'][o.UNITS[0]]['NRestarts']='1'
            if fault=='replaced':bad[-1]['services'][o.UNITS[0]]['ExecMainStartTimestampMonotonic']='456'
            if fault=='missing':del bad[-1]['services'][o.UNITS[0]]
            with self.subTest(fault=fault),self.assertRaises(ValueError):o.analyze(bad,'recovery')

    def test_soak_requires_duration_uninterrupted_lock_and_frames(self):
        good=rows(['locked 1280x720']*1441)
        self.assertEqual(o.analyze(good,'soak')['seconds'],7200)
        bads=[good[:-1],copy.deepcopy(good),copy.deepcopy(good)]
        bads[1][100]['signal']='none';bads[2][-1]['frames']=1
        for bad in bads:
            with self.assertRaises(ValueError):o.analyze(bad,'soak')

    def test_soak_rejects_interruptions_hidden_between_signal_samples(self):
        good=rows(['locked 1280x720']*1441)
        for fault in ('renderer','counter','inactive'):
            bad=copy.deepcopy(good)
            if fault=='renderer':
                for row in bad[100:]:row['services']['h713-hdmi-video.service']['ExecMainStartTimestampMonotonic']='456'
            if fault=='counter':
                for row in bad[100:]:row['frames']-=30000
            if fault=='inactive':bad[100]['services']['h713-hdmi-video.service']['ActiveState']='inactive'
            # Overall frame rate still exceeds 50 fps: averaging cannot detect this.
            self.assertGreaterEqual(bad[-1]['frames']-bad[0]['frames'],50*7200)
            with self.subTest(fault=fault),self.assertRaises(ValueError):o.analyze(bad,'soak')

    def test_recovery_allows_new_renderer_after_source_loss(self):
        good=rows(['locked 1280x720','none']+['locked 1280x720']*4)
        for row in good[2:]:row['services']['h713-hdmi-video.service']['ExecMainStartTimestampMonotonic']='456'
        self.assertEqual(o.analyze(good,'recovery')['result'],'PASS')

    def test_guarded_discard_remains_a_strict_failure_requiring_review(self):
        data=rows(['locked 1280x720','none']+['locked 1280x720']*4)
        data[0]['errors']['rejected']=1
        with self.assertRaisesRegex(ValueError,'frame rejection requires review'):
            o.analyze(data,'recovery')


if __name__=='__main__':unittest.main()
