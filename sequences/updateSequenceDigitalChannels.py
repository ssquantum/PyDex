"""Stefan Spence 23/02/21
Convert sequences which had different digital channel layout
"""
import sys
from lxml import etree
sys.path.append('') # otherwise cwd isn't in sys.path 
from translator import translate, tdict
from sequencePreviewer import Previewer
try:
    from PyQt4.QtGui import QApplication
except ImportError:
    from PyQt5.QtWidgets import QApplication

import time
t = translate()
t0 = time.time()
t.load_xml('SequenceFiles\\testing\\0_17 September 2019_09 30 18.xml')
t1 = time.time()
# t.seq_tree[1][tdict.get('Routine name in')][1].text = "My new routine"
# t.seq_tree[1][tdict.get('Routine description in')][1].text = "An example of editing sequences"

esc = t.seq_tree[1][tdict.get('Experimental sequence cluster in')] # shorthand
num_s = len(esc[tdict.get('Sequence header top')]) - 2 # total number of timesteps
# change some time step lengths - make sure to keep sequence header top and sequence header middle the same

oldchans = [37, 38, 39, 21, 22, 23] # all fast digitals
newchans = [11, 12, 10, 15, 14, 13] # slow digitals

# take value from the fast digital and put it into the slow digital
for t in range(num_s):
    for o, n in zip(oldchans, newchans):
        esc[tdict.get('Slow digital channels')][t + n*num_s + 3][1].text = esc[
            tdict.get('Fast digital channels')][t + o*num_s + 3][1].text
    
t2 = time.time()
t.write_to_file('SequenceFiles\\testing\\example.xml')
if len(sys.argv) > 1 and sys.argv[1] == '-timeit':
    t3 = time.time()
    t.write_to_str()
    t4 = time.time()
    print('Timings test:')
    tests = {'Load from XML':t1-t0, 'Edit channels':t2-t1, 'Write to XML file':t3-t2, 'Write to XML string':t4-t3}
    for key, val in tests.items():
        print(key + ': %.3g ms'%(val*1e3))
elif len(sys.argv) > 1 and sys.argv[1] == '-display':
    # display the edited sequence
    app = QApplication.instance()
    standalone = app is None # false if there is already an app instance
    if standalone: # if there isn't an instance, make one
        app = QApplication(sys.argv) 
    boss = Previewer(t)
    boss.set_sequence()
    boss.show()
    if standalone: # if an app instance was made, execute it
        sys.exit(app.exec_())