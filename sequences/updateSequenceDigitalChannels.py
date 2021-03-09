"""Stefan Spence 23/02/21
Convert sequences which had different digital channel layout
"""
import sys
sys.path.append('') # otherwise cwd isn't in sys.path 
import os
os.chdir(r'Z:\Tweezer\Code\Python 3.5\PyDex\sequences')
from lxml import etree
from translator import translate, tdict
from sequencePreviewer import Previewer
try:
    from PyQt4.QtGui import QApplication
except ImportError:
    from PyQt5.QtWidgets import QApplication

import time
t = translate()
t0 = time.time()
t.load_xml(r"Z:\Tweezer\Experimental Results\2020\December\18\Measure10\sequences\Measure10_base.xml")
t1 = time.time()
# t.seq_tree[1][tdict.get('Routine name in')][1].text = "My new routine"
# t.seq_tree[1][tdict.get('Routine description in')][1].text = "An example of editing sequences"

esc = t.seq_tree[1][tdict.get('Experimental sequence cluster in')] # shorthand
num_s = len(esc[tdict.get('Sequence header top')]) - 2 # total number of timesteps
# change some time step lengths - make sure to keep sequence header top and sequence header middle the same

oldchans = [37, 38, 39, 21, 22, 23] # all fast digitals
newchans = [11, 12, 10, 15, 14, 13] # slow digitals

# take value from the fast digital and put it into the slow digital
for i in range(num_s):
    for o, n in zip(oldchans, newchans):
        esc[tdict.get('Slow digital channels')][i + n*num_s + 3][1].text = esc[
            tdict.get('Fast digital channels')][i + o*num_s + 3][1].text
        esc[tdict.get('Fast digital channels')][i + o*num_s + 3][1].text ='0'
    
t2 = time.time()
t.write_to_file(r'Z:\Tweezer\Experimental Results\2021\March\03\Cs_Rabi_osc.xml')

# if len(sys.argv) > 1 and sys.argv[1] == '-timeit':
#     t3 = time.time()
#     t.write_to_str()
#     t4 = time.time()
#     print('Timings test:')
#     tests = {'Load from XML':t1-t0, 'Edit channels':t2-t1, 'Write to XML file':t3-t2, 'Write to XML string':t4-t3}
#     for key, val in tests.items():
#         print(key + ': %.3g ms'%(val*1e3))

if False: ## set to True if you want to preview the sequence
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