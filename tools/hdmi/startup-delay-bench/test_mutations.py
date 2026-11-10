#!/usr/bin/env python3
"""Ensure safety oracles reject selected broken variants, entirely offline."""
import io
import json
from pathlib import Path
import unittest
from unittest.mock import patch

import build
import hdmi_delay_bench as helper
from test_delay_bench import Delay


def main():
    original = Path(helper.__file__).read_text()
    mutations = [
        ('one-second-wait', 'self.delay_ms * 1_000_000', 'self.delay_ms * 500_000',
         'test_delayed_wrapper_orders_wait_markers_ddc_and_scp'),
        ('skip-post-wait-checks', '        self.preflight()\n        end =', '        end =',
         'test_post_delay_boot_graph_pin_owner_drift_refuse_before_holds'),
        ('allow-current-failed-boot', 'require(self.boot != EXCLUDED_BOOT,', 'require(True,',
         'test_current_failed_boot_refuses_before_any_delay_or_holds'),
        ('allow-fault-arguments', "require(not args.signal_arg,", 'require(True,',
         'test_invalid_cli_and_fault_arguments_refuse'),
    ]
    result=[]
    try:
        for name, before, after, test in mutations:
            if original.count(before)!=1:raise RuntimeError('mutation anchor changed: '+name)
            exec(compile(original.replace(before,after),helper.__file__,'exec'),helper.__dict__)
            stream=io.StringIO()
            outcome=unittest.TextTestRunner(stream=stream).run(unittest.TestSuite([Delay(test)]))
            result.append({'mutation':name,'detected':not outcome.wasSuccessful(),
                           'failures':len(outcome.failures),'errors':len(outcome.errors)})
            exec(compile(original,helper.__file__,'exec'),helper.__dict__)
        transform=build.transform
        def late(source,digest):
            value=transform(source,digest)
            wait='        if delay_bench is not None:delay_bench.wait()\n'
            anchor="        run(['insmod',str(args.bundle/'h713-ddc-pins.ko'),'run=1'])\n"
            return value.replace(wait,'').replace(anchor,anchor+wait)
        for name, replacement in (
            ('skip-wait',lambda source,digest:transform(source,digest).replace(
                '        if delay_bench is not None:delay_bench.wait()\n','')),
            ('wait-after-ddc-claim',late)):
            with patch.object(build,'transform',replacement):
                outcome=unittest.TextTestRunner(stream=io.StringIO()).run(unittest.TestSuite([
                    Delay('test_delayed_wrapper_orders_wait_markers_ddc_and_scp')]))
            result.append({'mutation':name,'detected':not outcome.wasSuccessful(),
                           'failures':len(outcome.failures),'errors':len(outcome.errors)})
    finally:
        exec(compile(original,helper.__file__,'exec'),helper.__dict__)
    print(json.dumps({'schema':'h713-delay-mutation-results-v1','results':result},indent=2))
    if not all(value['detected'] for value in result):raise SystemExit(1)


if __name__=='__main__':main()
