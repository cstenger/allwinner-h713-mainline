#!/usr/bin/env python3
"""Offline-only mutations: execute changed source in memory, never board tools."""
import importlib.util,io,json,pathlib,unittest
ROOT=pathlib.Path(__file__).resolve().parents[3]
spec=importlib.util.spec_from_file_location('warm_tests',ROOT/'tools/hdmi/test-warm-shared.py')
t=importlib.util.module_from_spec(spec);spec.loader.exec_module(t)
C=t.VideoAndAbrupt
cases=[
 ('video gate removed',t.c,'if require_video:out[\'reasons\'].extend(evaluate_video(rec))','if False:out[\'reasons\'].extend(evaluate_video(rec))','test_video_gate_rejects_missing_unlocked_stalled_or_rejected_video'),
 ('comparison ignores video',t.c,'evaluate(cold,require_video),evaluate(warm,require_video)','evaluate(cold),evaluate(warm)','test_compare_enforces_video_on_both_boots'),
 ('abrupt accepts orderly markers',t.r,"markers+[b'U-Boot SPL '","[b'reboot: Restarting system']+[b'U-Boot SPL '",'test_abrupt_uart_requires_own_markers_and_exactly_one_reset'),
 ('extra reset accepted',t.r,'if self.spl>self.spl_max:','if False:','test_abrupt_uart_requires_own_markers_and_exactly_one_reset'),
 ('boot guard disabled',t.r,"if P('/proc/sys/kernel/random/boot_id').read_text().strip()!=expected:",'if False:','test_abrupt_trigger_guards_boot_and_health_before_and_after_sync'),
 ('post-sync guard removed',t.r,'os.sync()\nguard()','os.sync()','test_abrupt_trigger_guards_boot_and_health_before_and_after_sync'),
 ('reset intent not persisted',t.r,"self.note('REBOOT REQUESTED '+self.reset+' boot_stop='+self.boot_stop)","self.note('reset without intent')",'test_reset_intent_is_saved_before_a_failed_request_and_never_retried'),
 ('baseline health gate removed',t.r,"if not res['passed']:raise RuntimeError('cold session unhealthy; warm test not started: '","if False:raise RuntimeError('cold session unhealthy; warm test not started: '",'test_unhealthy_baseline_never_requests_a_reset'),
]
results=[]
for name,module,old,new,test in cases:
    source=pathlib.Path(module.__file__).read_text()
    assert source.count(old)==1,(name,source.count(old))
    try:
        exec(compile(source.replace(old,new),module.__file__,'exec'),module.__dict__)
        log=io.StringIO();res=unittest.TextTestRunner(stream=log).run(unittest.TestSuite([C(test)]))
        caught=not res.wasSuccessful();results.append({'mutation':name,'test':test,'caught':caught,'output':log.getvalue()})
    finally:exec(compile(source,module.__file__,'exec'),module.__dict__)
print(json.dumps(results,indent=2))
assert all(x['caught'] for x in results),'surviving mutation'
