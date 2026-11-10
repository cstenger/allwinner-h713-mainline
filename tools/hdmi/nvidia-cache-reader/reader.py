#!/usr/bin/env python3
"""Cache-only NVIDIA reader core. Default offline; live RM backend deliberately absent."""
import argparse
from dataclasses import dataclass
import json
from pathlib import Path
import struct

VERSION = '615.78.08'
LIVE_RM_QUALIFIED = False
LIVE_BLOCKER = ('Live RM access is disabled: display queries and device allocation cross into '
                'GSP firmware; setup/query/teardown side effects have not been qualified. '
                'No device was opened and no ioctl was issued.')
SUPPORTED, CONNECT, CONFIG, STATE = 0x730107, 0x730108, 0x730109, 0x73010a
CACHED_FLAGS = 0x31  # METHOD_CACHED | DDC_DISABLE << 4 | LOAD_DISABLE << 5
DEVICE, DISPLAY, ROOT_CLASS = 0x10001, 0x10002, 0x41
SIZES = {SUPPORTED:12, CONNECT:16, CONFIG:24, STATE:12}

class Refused(ValueError):
    pass

def require(ok, message):
    if not ok:
        raise Refused(message)

def uint(value):
    require(type(value) is int and 0 <= value <= 0xffffffff, 'not a uint32')
    return value

@dataclass(frozen=True)
class Request:
    kind: str
    root: int
    parent: int
    object: int
    code: int
    params: tuple

    def validate(self):
        for value in (self.root,self.parent,self.object,self.code,*self.params):
            uint(value)
        if self.kind == 'alloc':
            if self.code == ROOT_CLASS:
                require((self.root,self.parent,self.object,self.params)==(0,0,0,()), 'root allocation shape')
            elif self.code == 0x80:
                # NV0080_ALLOC_PARAMETERS, device instance zero; remaining fields zero.
                require(self.root not in (0,DEVICE,DISPLAY) and self.parent==self.root and
                        self.object==DEVICE and self.params==(0,)*14, 'device allocation shape')
            elif self.code == 0x73:
                require(self.root not in (0,DEVICE,DISPLAY) and self.parent==DEVICE and
                        self.object==DISPLAY and not self.params, 'display allocation shape')
            else:
                raise Refused('allocation class not allowed')
        elif self.kind == 'control':
            require(self.root not in (0,DEVICE,DISPLAY) and self.parent==0 and
                    self.object==DISPLAY, 'control target')
            require(self.code in SIZES and len(self.params)*4==SIZES[self.code], 'control not allowed or wrong size')
            require(self.params[0]==0, 'subdevice must be zero')
            if self.code == CONNECT:
                require(self.params[1]==CACHED_FLAGS and self.params[2]!=0 and self.params[3]==0,
                        'only exact cached flags; nonzero mask; no retry')
            else:
                require(not any(self.params[1:]), 'nonzero query input/output placeholders')
        elif self.kind == 'free':
            require(self.root not in (0,DEVICE,DISPLAY) and self.parent==0 and
                    self.object==self.root and self.code==0 and not self.params, 'free only own root')
        else:
            raise Refused('operation not allowed')
        return self

    def words(self):
        self.validate()
        return struct.pack('<'+'I'*len(self.params),*self.params)

class Boundary:
    """Finite sequence checked at the last boundary before the offline transport.

    The transport cannot add a command through this interface. There is no live
    implementation; its lifecycle and failure cleanup are intentionally unqualified.
    """
    def __init__(self, transport):
        self.transport=transport
        self.index=0
        self.root=None
        self.mask=None
        self.failed=False
        self.trace=[]

    def expected(self):
        r=self.root
        if self.index==0:return Request('alloc',0,0,0,ROOT_CLASS,())
        if self.index==1:return Request('alloc',r,r,DEVICE,0x80,(0,)*14)
        if self.index==2:return Request('alloc',r,DEVICE,DISPLAY,0x73,())
        if self.index==3:return Request('control',r,0,DISPLAY,SUPPORTED,(0,0,0))
        if self.index==4:return Request('control',r,0,DISPLAY,CONNECT,(0,CACHED_FLAGS,self.mask,0))
        if self.index==5:return Request('control',r,0,DISPLAY,CONFIG,(0,0,0,0,0,0))
        if self.index==6:return Request('control',r,0,DISPLAY,STATE,(0,0,0))
        if self.index==7:return Request('free',r,0,r,0,())
        raise Refused('sequence already consumed; no retry')

    def send(self, request):
        require(not self.failed, 'sequence terminal after refusal; no retry or fallback')
        try:
            request.validate()
            require(request==self.expected(), 'unexpected command, order or handle')
            self.trace.append(request)
            reply=self.transport.exchange(request)
            require(type(reply) is dict and set(reply)=={'status','data'}, 'malformed response envelope')
            require(uint(reply['status'])==0, 'RM status failure; no fallback or retry')
            data=reply['data']
            require(type(data) in (tuple,list) and all(type(x) is int and 0<=x<=0xffffffff for x in data),
                    'malformed response words')
            if self.index==0:
                require(len(data)==1 and data[0] not in (0,DEVICE,DISPLAY), 'invalid own client handle')
                self.root=data[0]
            elif self.index in (1,2,7):
                require(not data, 'unexpected lifecycle response')
            else:
                require(len(data)==len(request.params) and data[0]==0, 'response size/subdevice changed')
                if request.code==SUPPORTED:
                    require(data[1]!=0 and not data[2]&~data[1], 'invalid supported masks')
                    self.mask=data[1]
                if request.code==CONNECT:
                    require(data[1]==CACHED_FLAGS and not data[2]&~self.mask and data[3]==0,
                            'cached result flags/mask/retry drift')
                if request.code==CONFIG:
                    require(data[1]==0 and not data[2]&~data[4], 'invalid config flags/event subscription mask')
                if request.code==STATE:
                    require(data[1] in (0,1), 'unknown state flags')
            self.index+=1
            return tuple(data)
        except BaseException:
            self.failed=True
            raise

    def run(self):
        require(self.index==0 and not self.failed, 'one offline sequence only; no resume or retry')
        frames={}
        while self.index<8:
            req=self.expected()
            result=self.send(req)
            if req.kind=='control':frames[hex(req.code)]=result
        return dict(mode='OFFLINE TRANSPORT RESULT',hardware_executed=False,live_rm_qualified=False,
                    supported_mask=frames[hex(SUPPORTED)][1],connected_mask=frames[hex(CONNECT)][2],
                    hotplug_config=frames[hex(CONFIG)],recorded_hotplug_state=frames[hex(STATE)],
                    physical_hpd='not measured',hdmi_port_mapping='not established by these masks',
                    requests=len(self.trace),automatic_retry=False,frames=frames)

class Replay:
    def __init__(self, frames):
        require(type(frames) is list and len(frames)==8, 'replay must contain exactly eight replies')
        self.frames=list(frames)
        self.trace=[]
    def exchange(self, request):
        self.trace.append(request)
        require(bool(self.frames), 'replay exhausted')
        return self.frames.pop(0)

def read_cached(root=Path('/')):
    """Only cached sysfs attributes; no NVIDIA/DRM ioctls, buses or device nodes."""
    paths=['sys/module/nvidia/version','sys/class/drm/card1-HDMI-A-1/status',
           'sys/class/drm/card1-HDMI-A-1/enabled','sys/class/drm/card1-HDMI-A-1/edid']
    data=[]
    for name in paths:
        with (root/name).open('rb') as f:
            value=f.read(4097)
        require(len(value)<=4096, 'oversized cached attribute')
        data.append(value)
    version,status,enabled=[value.decode('ascii').strip() for value in data[:3]]
    require(version==VERSION, 'driver version mismatch')
    require(status in ('connected','disconnected','unknown') and enabled in ('enabled','disabled'), 'invalid cached state')
    require(status=='disconnected' and enabled=='disabled' and not data[3], 'preserved bad state changed')
    return dict(mode='PASSIVE SYSFS CACHE ONLY',driver=version,status=status,enabled=enabled,edid_bytes=0,
                nvidia_control_calls=0,device_nodes_opened=0,physical_hpd='not measured',
                board_access=False,live_rm_qualified=False)

def live_reader():
    # Deliberately no device open or ioctl implementation to reach by accident.
    # This guard is not an execution-permission check; missing source assurance
    # cannot be replaced by --execute-approved.
    raise Refused(LIVE_BLOCKER)

def main():
    p=argparse.ArgumentParser(description=__doc__)
    g=p.add_mutually_exclusive_group()
    g.add_argument('--replay',type=Path)
    g.add_argument('--cached-files',action='store_true')
    g.add_argument('--execute-approved',action='store_true',help='refused: live RM transport not qualified')
    a=p.parse_args()
    if a.execute_approved:live_reader()
    elif a.replay:result=Boundary(Replay(json.loads(a.replay.read_text()))).run()
    elif a.cached_files:result=read_cached()
    else:
        result=dict(mode='OFFLINE PLAN ONLY',driver=VERSION,live_rm_qualified=LIVE_RM_QUALIFIED,
                    hardware_executed=False,candidate_commands=[hex(n) for n in SIZES],
                    cached_connection_flags=hex(CACHED_FLAGS),blocker=LIVE_BLOCKER)
    print(json.dumps(result,indent=2))

if __name__=='__main__':
    try:main()
    except (Refused,OSError,UnicodeError) as exc:
        raise SystemExit(str(exc))
