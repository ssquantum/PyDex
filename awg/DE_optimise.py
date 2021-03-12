"""AWG calibration optimiser

Flatten the diffraction efficiency curve of the AWG using an optimiser
"""
import numpy as np
import matplotlib.pyplot as plt
import os
import sys
import time
sys.path.append(r'Z:\Tweezer\Code\Python 3.5\PyDex\networking')
from networker import PyServer, TCPENUM
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
    pwr   : output power desired as a fraction of the setpoint
    tol   : tolerance to match to setpoint
    sleep : time to sleep betewen setting AWG freq and taking measurement, seconds
    """
    def __init__(self, f0=135, f1=185, nfreqs=50, fset=166, pwr=1, tol=1e-3, sleep=0.5):
        self.status = 'checking' 
        # parameters
        self.f0 = f0 # lower bound
        self.f1 = f1 # upper bound
        self.nfreqs = nfreqs # number of frequencies
        self.fset = fset # setpoint
        self.pwr = pwr # amplitude
        self.tol = tol # tolerance
        self.sleep = sleep # sleep duration
        
        # 
        self.fs = np.linspace(f0, f1, nfreqs) # frequencies to test
        self.vs = np.ones(nfreqs)*200 # amplitude mV at those freqs
        self.v  = 200 # current amplitude being tried
        self.i  = 0 # current index being set
        self.setpoint = 1 # DAQ measurement to match to
        self.n = 0 # counter for number of measurements
    
        # setup
        self.s = PyServer(host='', port=8622) # server for DAQ
        self.s.textin.connect(self.respond)
        self.s.start()
        self.dxs = PyServer(host='', port=8620) # server for DExTer
        # self.dxs.textin.connect(self.respond)
        self.dxs.start()

        self.t = AWG([0,1])
        self.t.setNumSegments(8)
        self.t.setTrigger(0) # software trigger
        self.t.setSegDur(0.002)
        
        # segment, action, duration, freqs, numTraps, separation, freqAdjust, ampAdjust
        # self.t.setSegment(0, 1, 0.02, [fset], 1, 9, amp, [1], [0], False, False) # single trap
        # # step, segment, numLoops, nextStep, triggerCondition
        # self.t.setStep(0,0,1,0,1) # infinite loop
        # self.t.start()
        # self.t.setSegment(0, self.t.dataGen(0,0,'static',1,[fset],1,9, amp,[1],[0],False,False))
        # self.t.setStep(0,0,1,0,1)
        self.t.load(r'Z:\Tweezer\Code\Python 3.5\PyDex\awg\AWG template sequences\test amp_adjust\swap_static.txt')
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
            self.t.setSegment(0, self.t.dataGen(0,0,'static',1,[f],1,9, v,[self.pwr],[0],False,False))
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
        self.dxs.add_message(TCPENUM['Run sequence'], 'run the sequence\n'+'0'*1600)
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
            self.t.setSegment(0, self.t.dataGen(0,0,'static',1,[self.fset],1,9, 220,[self.pwr],[0],False,False))
            self.measure()
            time.sleep(self.sleep)
            self.t.setSegment(0, self.t.dataGen(0,0,'static',1,[self.fs[i]],1,9, self.vs[i],[self.pwr],[0],False,False))
            self.measure()
        except IndexError as e:
            print(e)
            
    def plot(self):
        plt.figure()
        plt.plot(self.fs, self.vs)
        plt.xlabel('Frequency (MHz)')
        plt.ylabel('RF amplitude to flatten (mV)')
        plt.show()
        
if __name__ == "__main__":
    app = QApplication.instance()
    standalone = app is None # false if there is already an app instance
    if standalone: # if there isn't an instance, make one
        app = QApplication(sys.argv) 
        
    o = Optimiser(f0=130, f1=190, nfreqs=61, fset=166, pwr=1, tol=1e-3, sleep=0.3)
    o.t.getParam(3)
    # o.restart()
    
    # from numpy.random import shuffle
    # fs = np.arange(120, 220)
    # # fs = np.delete(fs, np.array([154, 174, 152, 169, 155, 208, 140, 199, 173, 121, 189, 120])-120)
    # shuffle(fs)
    # amps = np.linspace(1,230,120)
    # shuffle(amps)
    # fdir = r'Z:\Tweezer\Code\Python 3.5\PyDex\awg\111020AWG_power_calibration'
    # os.mkdir(fdir, exist_ok=True)
    # o.s.textin.disconnect()
    # o.s.add_message(o.n, fdir+'=save_dir')
    # o.s.add_message(o.n, 'reset graph')
    # # for f in fs:
    #     for a in amps:
    #         o.n = int(a)
    #         o.s.add_message(o.n, 'sets n') # sets the amplitude for reference
    #         o.s.add_message(o.n, 'sets n') # sets the amplitude for reference
    #         o.t.setSegment(1, o.t.dataGen(1,0,'static',1,[f],1,9, a,[1],[0],False,False), 
    #                         o.t.dataGen(1,1,'static',1,[f],1,9, a,[1],[0],False,False))
    #         # o.t.loadSeg([[0,0,'freqs_input_[MHz]',f,0],[0,0,'tot_amp_[mV]',a,0]])
    #         o.measure()
    #     o.s.add_message(o.n, '%.3gMHz.csv=graph_file'%f)
    #     time.sleep(0.01)
    #     o.s.add_message(o.n, 'save graph')
    #     time.sleep(0.01)
    #     o.s.add_message(o.n, 'reset graph')
    #     
    # o.t.stop()