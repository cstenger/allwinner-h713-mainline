#!/usr/bin/env python3
"""Plot measured source-relative marker drift and its residuals."""
import argparse
import csv
import json
import os
from pathlib import Path
import numpy as np
os.environ.setdefault('MPLCONFIGDIR','/tmp/h713-matplotlib')
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('result',type=Path)
parser.add_argument('output',type=Path,help='PNG output; SVG and CSV also written')
args=parser.parse_args()
result=json.loads(args.result.read_text())
a=result.get('signal_analysis',result)
x=np.array([m['source_frame'] for m in a['markers']],dtype=float)
y=np.array([m['capture_frame'] for m in a['markers']])
slope=1+a['source_relative_drift_ppm']/1e6
offset=a['latency_offset_frames']
t=(x-x[0])/48000/60
observed=(y-x-(y[0]-x[0]))/48
fitted=(slope-1)*(x-x[0])/48
residual=y-(slope*x+offset)
fig,axes=plt.subplots(2,1,figsize=(9,6),sharex=True,layout='constrained')
axes[0].plot(t,observed,'o',markersize=3,label='Measured marker positions')
axes[0].plot(t,fitted,label='Linear fit')
axes[0].set_ylabel('Relative offset (ms)')
axes[0].legend(loc='upper left')
axes[0].set_title(f"HDMI source-to-capture drift: {a['source_relative_drift_ppm']:.2f} ppm")
axes[1].plot(t,residual,'o-',markersize=3,linewidth=.8)
axes[1].axhline(0,color='0.5',linewidth=.8)
axes[1].set_ylabel('Fit residual (frames)')
axes[1].set_xlabel('Time from first marker (minutes)')
for ax in axes:ax.grid(alpha=.25)
args.output.parent.mkdir(parents=True,exist_ok=True)
fig.savefig(args.output,dpi=160)
fig.savefig(args.output.with_suffix('.svg'))
with args.output.with_suffix('.csv').open('w') as stream:
 writer=csv.writer(stream)
 writer.writerow(['minutes','source_frame','capture_frame','relative_offset_ms','fit_residual_frames','correlation'])
 for i,m in enumerate(a['markers']):writer.writerow([t[i],x[i],y[i],observed[i],residual[i],m['correlation']])
print(args.output)
