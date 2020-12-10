import numpy as np
from numpy.random import shuffle
import matplotlib.pyplot as plt
import os
import sys
import time
sys.path.append(r'Z:\Tweezer\Code\Python 3.5\PyDex\networking')
from networker import PyServer, TCPENUM
from awgHandler import AWG
from PyQt5.QtCore import QThread, pyqtSignal
from PyQt5.QtWidgets import QApplication 


daqs = PyServer(host='', port=8622) # server for DAQ
# daqs.textin.connect(...)
daqs.start()
# dxs = PyServer(host='', port=8620) # server for DExTer
# dxs.start()

t = AWG([0,1])
t.setNumSegments(8)
t.setTrigger(0) # software trigger
t.setSegDur(0.002)
t.load(r'Z:\Tweezer\Code\Python 3.5\PyDex\awg\AWG template sequences\test amp_adjust\single_static.txt')
t.start()

app = QApplication.instance()
standalone = app is None # false if there is already an app instance
if standalone: # if there isn't an instance, make one
    app = QApplication(sys.argv) 



fs = np.arange(120, 220)
shuffle(fs)
fs = [f for x in zip(np.ones(len(fs))*166, fs) for f in x]
amps = np.arange(1,220)
shuffle(amps)
amps = [a for x in zip(np.ones(len(amps))*220, amps) for a in x]
fdir = r'Z:\Tweezer\Experimental Results\2020\December\04\AWGcalibration'
os.mkdir(fdir, exist_ok=True)
daqs.add_message(0, fdir+'=save_dir')
daqs.add_message(0, 'reset graph')
for f in fs:
    for a in amps:
        daqs.add_message(int(a), 'sets n') # sets the amplitude for reference
        daqs.add_message(int(a), 'sets n') # sets the amplitude for reference
        t.setSegment(1, t.dataGen(1,0,'static',1,[f],1,9, a,[1],[0],False,False), 
                        t.dataGen(1,1,'static',1,[f],1,9, a,[1],[0],False,False))
        time.sleep(0.2)
        daqs.add_message(int(a), 'start') # tells the DAQ to acquire
        daqs.add_message(int(a), 'measure') # tells DAQ to add the measurement to the next message
        daqs.add_message(int(a), 'readout') # reads the measurement
        time.sleep(0.1)

    daqs.add_message(int(a), '%.3gMHz.csv=graph_file'%f)
    time.sleep(0.01)
    daqs.add_message(int(a), 'save graph')
    time.sleep(0.01)
    daqs.add_message(int(a), 'reset graph')
    
t.stop()