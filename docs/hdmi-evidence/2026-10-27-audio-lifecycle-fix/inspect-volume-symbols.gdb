set pagination off
set confirm off
set debuginfod enabled off
set auto-load off
attach 422
thread 1
bt 12
python
import gdb,json,struct
f=gdb.newest_frame()
while f is not None and f.name()!='main':f=f.older()
if f is None:raise RuntimeError('main frame not found; no calls or writes')
f.select()
p=int(gdb.parse_and_eval('$x21'))
b=bytes(gdb.selected_inferior().read_memory(p,1048))
print('VOLUME_STATE '+json.dumps({'pointer':hex(p),'mute':struct.unpack_from('i',b,944)[0],'volume':struct.unpack_from('f',b,948)[0],'current_mute':struct.unpack_from('i',b,952)[0],'current_volume':struct.unpack_from('d',b,960)[0],'current_vol_i16':struct.unpack_from('q',b,984)[0],'negotiated':struct.unpack_from('i',b,1008)[0]}))
end
detach
quit
