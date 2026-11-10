"""Strict one-snapshot RM protocol. No OS/device access in this module."""
from dataclasses import dataclass
import struct

VERSION='615.78.08'
DEVICE,DISPLAY=0x10001,0x10002
IDS,INFO,PCI=0x201,0x205,0x21b
SUPPORTED,CONNECT,CONFIG,STATE,CONNECTOR=0x730107,0x730108,0x730109,0x73010a,0x730250
CACHE_FLAGS=0x31
SIZES={IDS:128,INFO:32,PCI:12,SUPPORTED:12,CONNECT:16,STATE:12,CONNECTOR:72}
class Refused(ValueError):pass

def need(ok,message):
    if not ok:raise Refused(message)

def u32(x):
    need(type(x) is int and 0<=x<=0xffffffff,'expected uint32')
    return x

@dataclass(frozen=True)
class Call:
    kind:str
    root:int
    parent:int
    object:int
    code:int
    words:tuple

    def validate(self,own_root=None):
        for x in (self.root,self.parent,self.object,self.code,*self.words):u32(x)
        need(type(self.words) is tuple,'immutable parameter words required')
        if self.kind=='alloc' and self.code==0x41:
            need(own_root is None and (self.root,self.parent,self.object,self.words)==(0,0,0,()),'root allocation scope')
            return self
        need(own_root not in (None,0,DEVICE,DISPLAY) and self.root==own_root,'own client only')
        if self.kind=='alloc':
            if self.code==0x80:
                need(self.parent==own_root and self.object==DEVICE and len(self.words)==14 and
                     self.words[0]<32 and not any(self.words[1:]),'device allocation scope')
            elif self.code==0x73:
                need(self.parent==DEVICE and self.object==DISPLAY and not self.words,'display-common allocation scope')
            else:raise Refused('allocation class forbidden')
        elif self.kind=='control':
            need(self.parent==0 and self.code in SIZES and len(self.words)*4==SIZES[self.code],'control opcode/size forbidden')
            if self.code in (IDS,INFO,PCI):
                need(self.object==own_root,'root query target')
                if self.code==IDS:need(not any(self.words),'attached IDs output initialization')
                else:need(self.words[0]!=0xffffffff and not any(self.words[1:]),'GPU metadata query shape')
            else:
                need(self.object==DISPLAY and self.words[0]<4,'display query target/subdevice')
                if self.code==CONNECT:
                    need(self.words[1]==CACHE_FLAGS and self.words[2]!=0 and self.words[3]==0,'cached flags/mask/retry required')
                elif self.code==CONNECTOR:
                    bit=self.words[1]
                    need(bit and bit&(bit-1)==0 and not any(self.words[2:]),'static single-display connector metadata only')
                else:need(not any(self.words[1:]),'query outputs must start zero')
        elif self.kind=='free':
            need(self.parent==0 and self.object==own_root and self.code==0 and not self.words,'free only own root')
        else:raise Refused('operation forbidden')
        return self

    def packed(self):return struct.pack('<'+'I'*len(self.words),*self.words)

class Snapshot:
    def __init__(self,transport,pci=(0,12,0),record=lambda event:None):
        self.transport=transport;self.pci=pci;self.record=record;self.root=None
        self.used=False;self.closed=False;self.calls=[];self.failure=None;self.cleanup_error=None
        self.supported=None;self.subdevice=None;self.gpuid=None;self.device_instance=None

    def send(self,call):
        call.validate(self.root)
        self.calls.append(call)
        self.record(dict(phase='intent',kind=call.kind,code=hex(call.code),words=list(call.words)))
        reply=self.transport.exchange(call)
        need(type(reply) is dict and set(reply)=={'status','words'},'malformed reply')
        status=u32(reply['status'])
        words=reply['words'];need(type(words) is tuple and all(type(v) is int and 0<=v<=0xffffffff for v in words),'malformed words')
        self.record(dict(phase='returned',kind=call.kind,code=hex(call.code),status=status,words=list(words)))
        need(status==0,'RM failure; no retry or alternate detection')
        if call.kind=='alloc':
            if call.code==0x41:
                need(len(words)==1 and words[0] not in (0,DEVICE,DISPLAY),'invalid root handle')
                self.root=words[0]
                self.transport.admit_root(self.root)
            else:need(not words,'unexpected allocation result')
        elif call.kind=='free':need(not words,'unexpected free result')
        else:
            need(len(words)==len(call.words),'response length mismatch')
        return words

    def query(self,code,words,root=False):
        return self.send(Call('control',self.root,0,self.root if root else DISPLAY,code,tuple(words)))

    def cleanup(self):
        if self.closed:return
        self.closed=True
        try:
            if self.root is not None:self.send(Call('free',self.root,0,self.root,0,()))
        except BaseException as exc:self.cleanup_error=str(exc)
        finally:
            try:self.transport.close()
            except BaseException as exc:self.cleanup_error=(self.cleanup_error or '')+' close: '+str(exc)

    def run(self):
        need(not self.used,'one snapshot per session; no retry')
        self.used=True;result=None
        try:
            self.send(Call('alloc',0,0,0,0x41,()))
            ids=self.query(IDS,[0]*32,root=True)
            live=[x for x in ids if x!=0xffffffff]
            need(len(live)==1 and ids[0]==live[0] and all(x==0xffffffff for x in ids[1:]),
                 'exactly one already-attached GPU required; no attach or enumeration fallback')
            self.gpuid=live[0]
            pci=self.query(PCI,[self.gpuid,0,0],root=True)
            need(pci[0]==self.gpuid and (pci[1],pci[2]&65535,pci[2]>>16)==self.pci,'GPU PCI identity mismatch')
            info=self.query(INFO,[self.gpuid]+[0]*7,root=True)
            need(info[0]==self.gpuid and info[1]&1 and not info[1]&2 and info[2]<32 and info[3]<4,
                 'GPU must already be in use and not SLI; invalid device mapping')
            self.device_instance,self.subdevice=info[2:4]
            self.send(Call('alloc',self.root,self.root,DEVICE,0x80,(self.device_instance,)+(0,)*13))
            self.send(Call('alloc',self.root,DEVICE,DISPLAY,0x73,()))
            supported=self.query(SUPPORTED,[self.subdevice,0,0])
            need(supported[0]==self.subdevice and supported[1] and supported[1].bit_count()<=16 and
                 not supported[2]&~supported[1],'invalid/broad supported display masks')
            self.supported=supported[1]
            mapping=[]
            for i in range(32):
                bit=1<<i
                if not self.supported&bit:continue
                data=self.query(CONNECTOR,[self.subdevice,bit]+[0]*16)
                need(data[:2]==(self.subdevice,bit) and data[2] in (0,1) and data[4]<=4,'invalid connector metadata')
                entries=[dict(index=data[5+3*j],type=hex(data[6+3*j]),location=data[7+3*j]) for j in range(data[4])]
                mapping.append(dict(display_id=hex(bit),present=bool(data[2]&1),ddc_partners=hex(data[3]),
                                    connectors=entries,platform=data[17]))
            connected=self.query(CONNECT,[self.subdevice,CACHE_FLAGS,self.supported,0])
            need(connected[0]==self.subdevice and connected[1]==CACHE_FLAGS and
                 not connected[2]&~self.supported and connected[3]==0,'cached response flags/mask/retry mismatch')
            state=self.query(STATE,[self.subdevice,0,0])
            need(state[0]==self.subdevice and state[1] in (0,1),'invalid recorded state')
            hdmi=[int(x['display_id'],16) for x in mapping if x['present'] and
                  any(c['type']=='0x61' for c in x['connectors'])]
            result=dict(schema='nvidia-cache-snapshot-v2',snapshot_complete=True,driver=VERSION,
                gpu_id=hex(self.gpuid),pci=list(self.pci),device_instance=self.device_instance,subdevice=self.subdevice,
                supported_mask=hex(self.supported),connected_mask=hex(connected[2]),cached_flags=hex(CACHE_FLAGS),
                connector_mapping=mapping,hdmi_a_display_ids=[hex(x) for x in hdmi],
                hdmi_a_cached_connected=[dict(display_id=hex(x),connected=bool(x&connected[2])) for x in hdmi],
                hotplug_subscription='not queried; reader registers no subscriptions',recorded_hotplug_state=list(state),
                physical_hpd='not measured',atomic_snapshot=False,firmware_boundary='documented cached/query API contract; not firmware implementation proof',
                board_access=False,ddc_transactions_requested=False,load_detection_requested=False,automatic_retry=False)
        except BaseException as exc:
            self.failure=str(exc);raise
        finally:
            self.cleanup()
        need(self.cleanup_error is None,'snapshot collected but client cleanup failed: '+str(self.cleanup_error))
        result['own_client_freed']=True
        result['request_count']=len(self.calls)
        return result
