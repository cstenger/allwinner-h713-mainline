#!/usr/bin/env python3
"""Prepare a trace-only module source variant; never builds or contacts a board."""
import argparse
import difflib
import hashlib
import json
from pathlib import Path
import shutil

ROOT=Path(__file__).resolve().parents[2]
BASELINE='2fcb471c3e5f553efc557beb80b558e7640e7ec1b8c930b57d1f94f975a79b10'
POWER_BASELINE='33b7a29155ac7c9f882501a95bedc4f68bf05227a041cee482b4005d6dec2e00'

def module_version(source):
    return 'reject-trace-power-v2' if sha(source.encode())==POWER_BASELINE else 'reject-trace-v1'

OLD_GUARD='''\t\tif (h713_copy_frame(cap, dst, (idx + 2) % 3) ||
\t\t    h713_afbd_pair_index(cap) != idx) {
\t\t\tcopy_ns += ktime_get_ns() - tick;
\t\t\tunstable++;
\t\t\tframes_rejected++;
\t\t\tcap->sequence++;
\t\t\tcontinue;
\t\t}'''
NEW_GUARD='''\t\tcopy_result = h713_copy_frame(cap, dst, (idx + 2) % 3);
\t\t/* Preserve short-circuit read order: -2 means not checked. */
\t\tpair_after = copy_result ? -2 : h713_afbd_pair_index(cap);
\t\tif (copy_result || pair_after != idx) {
\t\t\tu64 rejected_ns = ktime_get_ns() - tick;

\t\t\tcopy_ns += rejected_ns;
\t\t\tunstable++;
\t\t\tframes_rejected++;
\t\t\tcap->sequence++;
\t\t\t/* Emit only after the original rejection decision and accounting. */
\t\t\tpr_info_ratelimited("h713-hdmi-v4l2: reject=%lu produced=%lu copy_rc=%d pair_before=%d pair_after=%d copy_ns=%llu\\n",
\t\t\t\tframes_rejected, frames_produced, copy_result, idx,
\t\t\t\tpair_after, (unsigned long long)rejected_ns);
\t\t\tcontinue;
\t\t}'''


def sha(data):return hashlib.sha256(data).hexdigest()


def instrument(source):
    if sha(source.encode()) not in (BASELINE, POWER_BASELINE):raise RuntimeError('driver differs from accepted GF1/cold-2 source')
    declaration='\tint last = h713_afbd_pair_index(cap), idx;'
    if source.count(OLD_GUARD)!=1 or source.count(declaration)!=1:
        raise RuntimeError('diagnostic anchors are not unique')
    if 'MODULE_VERSION(' in source:raise RuntimeError('unexpected existing module version')
    return (source.replace(declaration,declaration+'\n\tint copy_result, pair_after;')
            .replace(OLD_GUARD,NEW_GUARD)+'\nMODULE_VERSION("'+module_version(source)+'");\n')


def build(output):
    original=(ROOT/'modules/hdmi-v4l2/h713-hdmi-v4l2.c').read_text()
    changed=instrument(original)
    output.mkdir(exist_ok=False,parents=True)
    module=output/'module';module.mkdir()
    for name in ('Makefile','h713-nv12.h','h713-signal.h'):
        shutil.copyfile(ROOT/'modules/hdmi-v4l2'/name,module/name)
    (module/'h713-hdmi-v4l2.c').write_text(changed)
    patch=''.join(difflib.unified_diff(original.splitlines(keepends=True),changed.splitlines(keepends=True),
                                     fromfile='a/h713-hdmi-v4l2.c',tofile='b/h713-hdmi-v4l2.c'))
    (output/'frame-reject-diagnostic.patch').write_text(patch)
    manifest={'schema':'h713-frame-reject-diagnostic-source-v1','baseline_source_sha256':sha(original.encode()),
              'diagnostic_source_sha256':sha(changed.encode()),'installed':False,'module_built':False,
              'loaded_module_version':module_version(original),
              'guard_semantics':'Original copy result and short-circuit pair read retained; same rejection/buffer decisions.',
              'trace':'Rate-limited after rejection decision: count, produced, copy return, before/after pair, copy wall time.',
              'pair_after_sentinel':{'-2':'pair not re-read because copy guard failed'},
              'limits':['New events only; cannot reconstruct the two historical triggers.',
                        'Logging can perturb later scheduling; not proof of original hardware timing.',
                        'Source package only: exact accepted kernel build/ABI and guarded cold installation remain required.']}
    (output/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    files=sorted(p for p in output.rglob('*') if p.is_file())
    (output/'SHA256SUMS').write_text(''.join(sha(p.read_bytes())+'  '+str(p.relative_to(output))+'\n' for p in files))
    return manifest


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('output',type=Path)
    print(json.dumps(build(parser.parse_args().output),indent=2))
