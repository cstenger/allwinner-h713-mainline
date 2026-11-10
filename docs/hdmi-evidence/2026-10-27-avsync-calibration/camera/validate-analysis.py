"""Independent known-timing data and mutations for retimed offset analysis."""
from pathlib import Path
import types
import numpy as np
SOURCE=(Path(__file__).parent/'analyze-recordings.py').read_text()

def load(source):
    module=types.ModuleType('camera_analysis');module.__file__=str(Path(__file__).parent/'analyze-recordings.py')
    exec(compile(source,module.__file__,'exec'),module.__dict__)
    return module

def fixture(offset_ms, speed=8):
    source=np.array([0,.7,1.8,2.7,4.1,4.9,6.1,7.1])
    onset=3+source*speed
    t=np.arange(0,onset[-1]+2,1/30);v=np.full(len(t),12.)
    at=np.arange(0,t[-1],.005);env=np.full(len(at),.0001)
    for f in onset:
        v[(t>=f)&(t<f+.0666667*speed)]=100
        beep=f+offset_ms/1000*speed
        # Smooth envelope gives a known half-height crossing at the true onset.
        env+=.01*np.clip((at-(beep-.02))/.04,0,1)*np.clip(((beep+.4+.02)-at)/.04,0,1)
    return t,v,at,env

def sign_and_scale(m):
    r=m.measure(*fixture(-40),2,62)
    assert abs(r['offset_ms']['median']+40)<3,r

def response(m):
    a=m.measure(*fixture(-40),2,62)['offset_ms']['median']
    b=m.measure(*fixture(30),2,62)['offset_ms']['median']
    assert abs((b-a)-70)<1,(a,b)

def wrong_cadence(m):
    try:m.measure(*fixture(-40,4),2,40)
    except AssertionError:return
    raise AssertionError('4x material accepted as 8x')

for f in (sign_and_scale,response,wrong_cadence):f(load(SOURCE));print('PASS',f.__name__)
for test,old,new in [(sign_and_scale,'(beep-flash)*1000/SLOW','(flash-beep)*1000/SLOW'),(response,'(beep-flash)*1000/SLOW','(beep-flash)*1000'),(wrong_cadence,'assert abs(fitted_slow-SLOW) < .1 and residual < .2, (fitted_slow, residual)','pass')]:
    assert old in SOURCE
    try:test(load(SOURCE.replace(old,new)))
    except AssertionError:print('CAUGHT',test.__name__)
    else:raise AssertionError('mutant survived: '+test.__name__)
