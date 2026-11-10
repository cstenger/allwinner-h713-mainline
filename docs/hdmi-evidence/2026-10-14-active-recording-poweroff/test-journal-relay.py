import errno,importlib.util,unittest
from pathlib import Path
spec=importlib.util.spec_from_file_location('relay',Path(__file__).with_name('journal-relay.py'))
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
class Relay(unittest.TestCase):
 def test_reopens_after_hangup_and_preserves_partial_writes(self):
  opened=[];closed=[];sent=[]
  def opener(path,flags):opened.append(path);return len(opened)
  def writer(fd,data):
   if fd==1:raise OSError(errno.EIO,'simulated getty hangup')
   count=min(3,len(data));sent.append(data[:count]);return count
  w=m.UartWriter(opener=opener,writer=writer,closer=closed.append,sleep=lambda _:None)
  w.emit(b'stop recorder\n');w.finish()
  self.assertEqual(opened,['/dev/ttyS0','/dev/ttyS0']);self.assertEqual(closed,[1,2])
  self.assertEqual(b''.join(sent),b'stop recorder\n')
 def test_missing_uart_is_bounded(self):
  elapsed=[0]
  def opener(path,flags):raise OSError(errno.ENXIO,'no UART')
  def sleep(seconds):elapsed[0]+=seconds
  w=m.UartWriter(opener=opener,clock=lambda:elapsed[0],sleep=sleep)
  with self.assertRaises(OSError):w.emit(b'data')
  self.assertGreaterEqual(elapsed[0],5);self.assertLess(elapsed[0],5.1)
if __name__=='__main__':unittest.main()
