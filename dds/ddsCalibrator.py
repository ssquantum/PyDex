"""DDS power calibration"""
import numpy as np
import matplotlib.pyplot as plt
import os
import sys
import time
sys.path.append(r'Z:\Tweezer\Code\Python 3.5\PyDex')
sys.path.append(r'Z:\Tweezer\Code\Python 3.5\PyDex\networking')
from networker import PyServer
from PyQt5.QtWidgets import (QApplication, QWidget, QPushButton, QLabel, 
    QFileDialog, QBoxLayout, QLineEdit)

class calibrator(QWidget):
    def __init__(self, ):
        super().__init__()
        self.daq_tcp = PyServer(host='', port=8622) # server for DAQ
        self.daq_tcp.textin.connect(self.respond)
        self.daq_tcp.start()
        self.dds_tcp = PyServer(host='', port=8624) # server for DDS
        self.dds_tcp.start()
        
        layout = QBoxLayout(QBoxLayout.TopToBottom, self)
        self.maxamp = QLineEdit('0.5', self)
        layout.addWidget(self.maxamp)
        self.comport = QLineEdit('COM11', self)
        layout.addWidget(self.comport)
        self.profile = QLineEdit('P7', self)
        layout.addWidget(self.profile)
        self.status = QLabel('n = 0, amp = 0, power = 0')
        layout.addWidget(self.status)
        self.lastval = QLabel('')
        layout.addWidget(self.lastval)
        reset = QPushButton('Reset')
        reset.clicked.connect(self.reset)
        layout.addWidget(reset)
        programme = QPushButton('Programme DDS')
        programme.clicked.connect(self.programme)
        layout.addWidget(programme)
        measure = QPushButton('DAQ Measure')
        measure.clicked.connect(self.measure)
        layout.addWidget(measure)
        store = QPushButton('Store Result')
        store.clicked.connect(self.store)
        layout.addWidget(store)
        save = QPushButton('Save Results')
        save.clicked.connect(self.save)
        layout.addWidget(save)
        
        self.amps = np.linspace(0,float(self.maxamp.text()),15)
        # np.random.shuffle(self.amps)
        self.power = np.zeros(len(self.amps))
        self.n = 0 # index for counting
        
    def reset(self):
        try:
            self.amps = np.linspace(0,float(self.maxamp.text()),15)
            # np.random.shuffle(self.amps)
            self.power = np.zeros(len(self.amps))
            self.n = 0
        except Exception as e:
            self.status.setText('n = %s --- exception: '+str(e))
    
    def programme(self):
        try:
            self.dds_tcp.add_message(self.n, 'set_data=[["%s", "%s", "Amp", %s]]'%(self.comport.text(), self.profile.text(), self.amps[self.n])) 
            self.dds_tcp.add_message(self.n, 'programme=stp')
        except Exception as e:
            self.status.setText('n = %s --- exception: '+str(e))
        
    def measure(self):
        """Request a measurement from the DAQ"""
        self.daq_tcp.add_message(self.n, 'start')
        self.daq_tcp.add_message(self.n, 'measure')
        self.daq_tcp.add_message(self.n, 'readout')
    
    def respond(self, msg):
        self.lastval.setText(msg)

    def store(self): 
        try:
            self.power[self.n] = float(self.lastval.text())
            self.status.setText('n = %s, amp = %s, power = %s'%(
                self.n, self.amps[self.n], self.power[self.n]))
            self.n += 1
        except Exception as e:
            self.status.setText('n = %s --- exception: '+str(e))
        
    def save(self, fname=''):           
        if not fname:
            fname, _ = QFileDialog.getSaveFileName(self, 'Save File')                
        np.savetxt(fname, [self.amps, self.power], delimiter=',')
        plt.plot(self.amps, self.power, 'o-')
        plt.xlabel('DDS Amp')
        plt.ylabel('DAQ signal (V)')
        plt.show()
        
if __name__ == "__main__":
    app = QApplication.instance()
    standalone = app is None # false if there is already an app instance
    if standalone: # if there isn't an instance, make one
        app = QApplication(sys.argv) 
        
    boss = calibrator()    
    boss.show()
    if standalone: # if an app instance was made, execute it
        sys.exit(app.exec_()) # when the window is closed, python code stops