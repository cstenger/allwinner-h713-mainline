"""Exact NVOS ioctl codec. Only the NVIDIA control node may be opened."""
import ctypes as C
import os
import stat
import sys
from protocol import Call,need,Refused,DEVICE,DISPLAY,SIZES,CACHE_FLAGS

class Alloc(C.Structure):
    _fields_=[('root',C.c_uint32),('parent',C.c_uint32),('object',C.c_uint32),('klass',C.c_uint32),
              ('params',C.c_uint64),('size',C.c_uint32),('status',C.c_uint32)]
class Control(C.Structure):
    _fields_=[('root',C.c_uint32),('object',C.c_uint32),('command',C.c_uint32),('flags',C.c_uint32),
              ('params',C.c_uint64),('size',C.c_uint32),('status',C.c_uint32)]
class Free(C.Structure):
    _fields_=[('root',C.c_uint32),('parent',C.c_uint32),('object',C.c_uint32),('status',C.c_uint32)]
IOCTLS={'alloc':0xc020462b,'control':0xc020462a,'free':0xc0104629}

def native_ioctl(fd,request,data,mutate):
    """One libc syscall wrapper, deliberately bypassing fcntl's EINTR retry."""
    need(mutate is True and type(data) is bytearray,'mutable ioctl buffer required')
    buffer=(C.c_ubyte*len(data)).from_buffer(data)
    libc=C.CDLL(None,use_errno=True)
    function=libc.ioctl
    function.argtypes=[C.c_int,C.c_ulong,C.c_void_p]
    function.restype=C.c_int
    C.set_errno(0)
    result=function(fd,request,C.cast(buffer,C.c_void_p))
    if result<0:
        error=C.get_errno()
        raise OSError(error,os.strerror(error))
    return result

def verify_abi(abi):
    need(sys.byteorder=='little' and C.sizeof(C.c_void_p)==8,'requires the audited 64-bit little-endian ABI')
    for cls,name in [(Alloc,'NVOS21_PARAMETERS'),(Control,'NVOS54_PARAMETERS'),(Free,'NVOS00_PARAMETERS')]:
        need(C.sizeof(cls)==abi[name],'outer ABI size mismatch')
    need(Alloc.params.offset==abi['NVOS21_PARAMETERS.pAllocParms'] and
         Control.params.offset==abi['NVOS54_PARAMETERS.params'] and
         Alloc.status.offset==abi['NVOS21_PARAMETERS.status'] and
         Control.status.offset==abi['NVOS54_PARAMETERS.status'],'outer ABI member offset mismatch')
    need(IOCTLS==dict(alloc=abi['ioctl_alloc'],control=abi['ioctl_control'],free=abi['ioctl_free']),'ioctl ABI mismatch')
    names={0x201:'NV0000_CTRL_GPU_GET_ATTACHED_IDS_PARAMS',0x205:'NV0000_CTRL_GPU_GET_ID_INFO_V2_PARAMS',
      0x21b:'NV0000_CTRL_GPU_GET_PCI_INFO_PARAMS',0x730250:'NV0073_CTRL_SPECIFIC_GET_CONNECTOR_DATA_PARAMS',
      0x730107:'NV0073_CTRL_SYSTEM_GET_SUPPORTED_PARAMS',0x730108:'NV0073_CTRL_SYSTEM_GET_CONNECT_STATE_PARAMS',
      0x73010a:'NV0073_CTRL_SYSTEM_GET_HOTPLUG_STATE_PARAMS'}
    need(all(SIZES[code]==abi[name] for code,name in names.items()),'query ABI size mismatch')
    need(abi['NV0080_ALLOC_PARAMETERS']==56 and abi['NV0000_CTRL_GPU_GET_PCI_INFO_PARAMS.bus']==8 and
         abi['NV0000_CTRL_GPU_GET_PCI_INFO_PARAMS.slot']==10 and abi['cached_flags']==CACHE_FLAGS==0x31,'parameter ABI mismatch')
    need([abi[name] for name in ['attached_ids_command','gpu_info_command','pci_command','connector_command']]==
         [0x201,0x205,0x21b,0x730250],'metadata command ABI mismatch')

class Transport:
    def __init__(self,fd,ioctl_fn=native_ioctl,close_fn=os.close):
        need(type(fd) is int and fd>=0,'invalid control fd')
        self.fd=fd;self.ioctl=ioctl_fn;self.close_fn=close_fn
        self.root=None;self.root_attempted=False;self.free_attempted=False;self.closed=False
        self.allocations=[]

    def admit_root(self,root):
        need(self.root is None and self.root_attempted and root not in (0,DEVICE,DISPLAY),'root admission')
        self.root=root

    def exchange(self,call):
        need(not self.closed and not self.free_attempted,'transport closed/cleanup already attempted')
        call.validate(self.root)  # immediately before encoding and the sole ioctl site
        if call.kind=='alloc':
            if call.code==0x41:
                need(not self.root_attempted,'root allocated at most once');self.root_attempted=True
            else:
                need(self.allocations==([] if call.code==0x80 else [0x80]),'allocation lifecycle order')
                self.allocations.append(call.code)
        if call.kind=='control' and call.object==DISPLAY:
            need(self.allocations==[0x80,0x73],'no display query before object allocation')
        if call.kind=='free':self.free_attempted=True
        payload=(C.c_uint32*len(call.words))(*call.words)
        pointer=C.addressof(payload) if call.words else 0
        size=len(call.words)*4
        if call.kind=='alloc':
            original=(call.root,call.parent,call.object,call.code,pointer,size)
            obj=Alloc(*original,0xffffffff)
        elif call.kind=='control':
            original=(call.root,call.object,call.code,0,pointer,size)
            obj=Control(*original,0xffffffff)
        else:
            original=(call.root,0,call.root)
            obj=Free(*original,0xffffffff)
        data=bytearray(bytes(obj))
        self.ioctl(self.fd,IOCTLS[call.kind],data,True)  # no automatic application retry
        returned=type(obj).from_buffer_copy(data)
        if call.kind=='alloc':
            check=(returned.root,returned.parent,returned.object,returned.klass,returned.params,returned.size)
            if call.code==0x41:
                need(check[:2]==original[:2] and check[3:]==original[3:],'root envelope changed')
            else:need(check==original,'allocation envelope changed')
            words=(returned.object,) if call.code==0x41 else ()
        elif call.kind=='control':
            check=(returned.root,returned.object,returned.command,returned.flags,returned.params,returned.size)
            need(check==original,'control envelope changed')
            words=tuple(payload)
        else:
            need((returned.root,returned.parent,returned.object)==original,'free envelope changed')
            words=()
        return dict(status=returned.status,words=words)

    def close(self):
        if not self.closed:
            self.closed=True
            self.close_fn(self.fd)


def open_control():
    path='/dev/nvidiactl'
    before=os.stat(path,follow_symlinks=False)
    need(stat.S_ISCHR(before.st_mode) and before.st_uid==0 and
         (os.major(before.st_rdev),os.minor(before.st_rdev))==(195,255),'control node identity; refuse before open')
    fd=os.open(path,os.O_RDWR|os.O_CLOEXEC|os.O_NOFOLLOW)
    try:
        after=os.fstat(fd)
        need(stat.S_ISCHR(after.st_mode) and after.st_uid==0 and after.st_rdev==before.st_rdev and
             (after.st_dev,after.st_ino)==(before.st_dev,before.st_ino),'opened node differs')
        return Transport(fd)
    except BaseException:
        os.close(fd);raise
