"""AWG calibration optimiser

Flatten the diffraction efficiency curve of the AWG using an optimiser
"""
import numpy as np
import matplotlib.pyplot as plt
import sys
import time
sys.path.append(r'Z:\Tweezer\Code\Python 3.5\PyDex\networking')
from networker import PyServer
from awgHandler import AWG
from PyQt5.QtCore import QThread, pyqtSignal
from PyQt5.QtWidgets import QApplication 


class Optimiser():
    """Take measurements from the DAQ of the output optical power at different
    frequencies and use them to flatten the diffraction efficiency curve of 
    the AWG. Communicate with the DAQ by TCP.
    Take a measurement of the setpoint between every trial since the setpoint
    will probably vary over time.
    
    Arguments:
    f0    : bottom of frequency range, MHz
    f1    : top of frequency range, MHz
    nfreqs: number of frequencies to test in the range
    fset  : setpoint frequency, match the diffraction efficiency at this point, MHz
    amp   : reference amplitude to apply at the setpoint frequency, mV
    tol   : tolerance to match to setpoint
    sleep : time to sleep betewen setting AWG freq and taking measurement, seconds
    """
    def __init__(self, f0=135, f1=185, nfreqs=50, fset=166, amp=220, tol=1e-3, sleep=0.5):
        self.status = 'checking' 
        # parameters
        self.f0 = f0 # lower bound
        self.f1 = f1 # upper bound
        self.nfreqs = nfreqs # number of frequencies
        self.fset = fset # setpoint
        self.amp = amp # amplitude
        self.tol = tol # tolerance
        self.sleep = sleep # sleep duration
        
        # 
        self.fs = np.linspace(f0, f1, nfreqs) # frequencies to test
        self.vs = np.ones(nfreqs) # fractional amplitudes at those frequencies
        self.v  = 1 # current fractional amplitude being tried
        self.i  = 0 # current index being set
        self.setpoint = 1 # DAQ measurement to match to
        self.n = 0 # counter for number of measurements
    
        # setup
        self.s = PyServer(host='', port=8622)
        self.s.textin.connect(self.respond)
        self.s.start()
        self.t = AWG([0])
        self.t.setNumSegments(8)
        self.t.setTrigger(0) # software trigger
        self.t.setSegDur(0.002)
        
        # segment, action, duration, freqs, numTraps, separation, freqAdjust, ampAdjust
        # self.t.setSegment(0, 1, 0.02, [fset], 1, 9, amp, [1], [0], False, False) # single trap
        # # step, segment, numLoops, nextStep, triggerCondition
        # self.t.setStep(0,0,1,0,1) # infinite loop
        # self.t.start()
        self.t.setSegment(0, self.t.dataGen(0,0,'static',1,[fset],1,9, amp,[1],[0],False,False))
        self.t.setStep(0,0,1,0,1)
        self.t.start()

    def respond(self, msg=''):
        """TCP message can contain the measurement from the DAQ"""
        try:
            val = float(msg)
            if self.status == 'checking':
                self.setpoint = val
                self.status = 'comparing'
                f, v = self.fs[self.i], self.v
            elif self.status == 'comparing':
                self.status = 'checking'
                self.modify(val)
                f, v = self.fset, 1
            elif self.status == 'finished':
                return 0
                
            print('f:%.4g, v:%.4g'%(f,v), val, self.setpoint)
            self.t.setSegment(0, self.t.dataGen(0,0,'static',1,[f],1,9, self.amp,[v],[0],False,False))
            self.measure()
        
            self.n += 1
        except Exception as e: pass # print(msg, '\n', str(e)) # the command was probably 'start'
        
    def modify(self, newval):
        """Compare newval to setpoint. If within tolerance, move on to the next frequency.
        If not, try a new amplitude"""
        v = (newval - self.setpoint)/self.setpoint
        if abs(v) < self.tol: # store value
            self.vs[self.i] = self.v
            self.i += 1
            if self.i == self.nfreqs:
                self.status = 'finished'
                self.plot()
        else: # try new amplitude
            print(self.fs[self.i], v, -0.4*v)
            self.v -= 0.4*v
            if self.v < 0 or self.v > 1:
                self.v = 0.8
            
    def measure(self):
        """Request a measurement from the DAQ"""
        time.sleep(self.sleep)
        self.s.add_message(self.n, 'start')
        time.sleep(self.sleep)
        self.s.add_message(self.n, 'measure') # tells DAQ to add the measurement to the next message
        self.s.add_message(self.n, 'readout') # reads the measurement
        
    def restart(self):
        self.i = 0
        self.status = 'checking'
        self.measure()
        
    def check(self, i=0):
        try:
            self.status = 'finished'
            self.t.setSegment(0, self.t.dataGen(0,0,'static',1,[self.fset],1,9, self.amp,[1],[0],False,False))
            self.measure()
            time.sleep(self.sleep)
            self.t.setSegment(0, self.t.dataGen(0,0,'static',1,[self.fs[i]],1,9, self.amp,[self.vs[i]],[0],False,False))
            self.measure()
        except IndexError as e:
            print(e)
            
    def plot(self):
        plt.figure()
        plt.plot(self.fs, self.vs)
        plt.xlabel('Frequency (MHz)')
        plt.ylabel('Fractional Amplitude')
        plt.show()
        
if __name__ == "__main__":
    app = QApplication.instance()
    standalone = app is None # false if there is already an app instance
    if standalone: # if there isn't an instance, make one
        app = QApplication(sys.argv) 
        
    o = Optimiser(f0=120, f1=220, nfreqs=80, fset=166, amp=220, tol=1e-3, sleep=0.5)
    o.t.getParam(3)
    # o.restart()
    
    from numpy.random import shuffle
    fs = np.arange(120, 220)
    # fs = np.delete(fs, np.array([154, 174, 152, 169, 155, 208, 140, 199, 173, 121, 189, 120])-120)
    shuffle(fs)
    amps = np.linspace(5,250,120)
    shuffle(amps)
    fdir = r'Z:\Tweezer\Code\Python 3.5\PyDex\monitor\AWG_power_calibration'
    o.s.textin.disconnect()
    # o.s.add_message(o.n, fdir+'=save_dir')
    # for f in fs:
    #     for a in amps:
    #         o.t.setSegment(0, o.t.dataGen(0,0,'static',1,[f],1,9, a,[1],[0],False,False))
    #         o.n = int(a)
    #         o.measure()
    #     o.s.add_message(o.n, '%.3gMHz.csv=graph_file'%f)
    #     time.sleep(0.01)
    #     o.s.add_message(o.n, 'save graph')
    #     time.sleep(0.01)
    #     o.s.add_message(o.n, 'reset graph')
    #     
    # o.t.stop()