#!/usr/bin/env python3
"""Inspect completed markers in a still-growing host PCM capture (read-only)."""
import argparse
import importlib.util
import json
from pathlib import Path
import numpy as np

spec=importlib.util.spec_from_file_location('analysis',Path(__file__).with_name('audio-endurance-analysis.py'))
analysis=importlib.util.module_from_spec(spec);spec.loader.exec_module(analysis)
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('directory',type=Path)
parser.add_argument('--seconds',type=int,default=3600)
args=parser.parse_args()
path=args.directory/'capture.raw'
frames=path.stat().st_size//4
markers=[]
with path.open('rb') as stream:
    for index,source in enumerate(analysis.marker_frames(args.seconds)):
        start=max(0,source-5*analysis.RATE)
        end=source+5*analysis.RATE+analysis.MARKER_FRAMES
        if end>frames:break
        stream.seek(start*4)
        data=np.frombuffer(stream.read((end-start)*4),dtype='<i2').reshape(-1,2)
        offset,score=analysis.locate(data[:,0],analysis.marker(index))
        markers.append({'source_frame':source,'capture_frame':start+offset,'correlation':score})
result={'captured_seconds':frames/analysis.RATE,'completed_markers':len(markers),
        'minimum_marker_correlation':min((m['correlation'] for m in markers),default=None)}
if len(markers)>=3:
    x=np.array([m['source_frame'] for m in markers],dtype=float)
    y=np.array([m['capture_frame'] for m in markers])
    slope,offset=np.polyfit(x,y,1)
    result.update(source_relative_drift_ppm=float((slope-1)*1e6),
                  maximum_timing_residual_frames=float(np.max(np.abs(y-(slope*x+offset)))),
                  maximum_adjacent_interval_change_frames=float(np.max(np.abs(np.diff(y,n=2)))))
print(json.dumps(result))
