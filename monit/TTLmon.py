"""Continuously monitor a TTL input to a DAQ.
Stefan Spence 11/09/19
From monitorV4.py created by Vincent Brooks

Start up a thread that continuously monitors an input into an NI DAQ.
When the signal goes above threshold, set TTL True and emit a signal, 
then wait for it to go low again before allowing the signal to be emitted
a second time.
"""
import os
import time 
import nidaqmx
import nidaqmx.constants
import numpy as np
import matplotlib.pyplot as plt
try:
    from PyQt4.QtCore import QThread, pyqtSignal
except ImportError:
    from PyQt5.QtCore import QThread, pyqtSignal



class monitor():
    """Class to aquire voltages from NI USB-6211 DAQ
    
    Required inputs: pulse length of the beam you want to measure
    Number of shots in the histogram you want to make
    Names of channels in a list (automatically scales up to number of names in list)
    NOTE: Channel ai0 must be the TTL input!"""
    def __init__(self, pulse_length = 0.055, nShots = 500, channelNames = ['TTL', 'V1', 'V2', 'V3'], saveName =None, saveDirectory = None, TTL_level=None):
        self.pulse_length = pulse_length           # Length of light exposure you want to measure (in s)
        self.channelNames = channelNames           # names of the channels you're aquiring on DAQ. First channel is the TTL!
        self.nShots = nShots                               
        self.n_samples = 100                              # N samples DAQ takes
        self.sample_rate = 3*1/(self.pulse_length/ self.n_samples)    # DAQ sample rate set by pulse time and desired shot number
        self.TTL_arrived = False        # Used to ensure only 1 data aquisition per pulse
        self.TTL_level = TTL_level          # Set the TTL trigger level required.
        
        self.i = 0                    # keeps track of current run number
        self.dataArray = np.zeros((self.nShots, len(self.channelNames)))   # This is the array the measurements go into and are saved form
        self.shotArray = np.zeros(nShots)

        
    '''Loops continuously waiting for arrival of TTL pulse.
       When TTL pulse arrives (greater than a threshold TTL level), the DAQ 
       takes 100 samples over the pulse time specified, which are averaged and appended
       to an array.
       The loop breaks when the number of shots reaches the number specified.
       Then, it saves a csv and plots the graph. (you can break early and save using command line)'''       
    def triggeredAquisition(self, livePlot = False):    
        with nidaqmx.Task() as task:
            task.ai_channels.add_ai_voltage_chan("Dev1/ai0:"+str(len(self.channelNames)-1))
            task.timing.cfg_samp_clk_timing(self.sample_rate) # set sample rate
            task.read()
            
            f, axs = plt.subplots(len(self.channelNames), sharex=True) # initiate plot
            if livePlot == True:
                l=0#.1
                plt.xlabel('shot number')
                plt.ylabel('voltage')
                plt.tight_layout()
                # plt.axis([np.min(self.dataArray)-l,np.max(self.shotArray)+l, np.min(self.dataArray)-l,np.max(self.dataArray)+l])
                col = ['r', 'b', 'g', 'y']
                lines = [axs[j].plot(0,j, color = col[j], linestyle = 'none', marker = '+', label = self.channelNames[j]) for j in range(len(self.channelNames))]
                for j in range(len(self.channelNames)):
                    axs[j].set_title(self.channelNames[j], fontsize = 8, y = 0.75)
                
            
            print('shots complete:')
            while self.i < self.nShots:
                TTL = task.read()[0]        # monitor the TTL input continuously
                
                if TTL < self.TTL_level: 
                    self.TTL_arrived = False
                
                if TTL > self.TTL_level and self.TTL_arrived == False: 
                    self.TTL_arrived = True

                    data = task.read(self.n_samples)
                    # call points > 3 std dev away outliers
                    # check = abs(data.T - np.mean(data, axis=1)) < 3* np.std(data, axis=1).T
                    # av = np.mean(data, axis = 1) # take an average
                    av = np.max(data, axis=1) # max is more stable to pulse shape changes.
                    self.dataArray[self.i] = av
                    print(str(self.i),end=' ')   # print shot which just got sampled
                    
                    
                    if livePlot == True:
                        for j in range(len(self.channelNames)):
                            self.shotArray[self.i] = self.i 
                            x, y = self.shotArray[:self.i+1], self.dataArray[:self.i+1,j]
                            lines[j][0].set_data(x, y)
                            if self.i > 2:
                                axs[j].set_xlim(min(x), max(x))
                                axs[j].set_ylim(min(y), max(y))

                            plt.pause(0.05)
                   
                    self.i += 1 
            self.save2csv()
    
    
    '''Look at the intensity profile of the shots with time.
        - Live plots the intensity curves sampled so you can watch if any discrepancies.
        - Doesn't save to csv, but you could just screenshot.
        chan_num: which channel to plot (index of dataArray)'''
    def measureShotProfile(self, chan_num=1):    
        with nidaqmx.Task() as task:
            task.ai_channels.add_ai_voltage_chan("Dev1/ai0:"+str(len(self.channelNames)-1))
            task.timing.cfg_samp_clk_timing(self.sample_rate) # set sample rate
            task.read()
            
            print('shots complete:')
            plt.figure()
            plt.xlim([0, self.pulse_length*1000])
            plt.xlabel('time / ms')
            plt.ylabel('voltage')
            
            while self.i < self.nShots:
                TTL = task.read()[0]
                
                if TTL < self.TTL_level: 
                    self.TTL_arrived = False
                
                if TTL > self.TTL_level and self.TTL_arrived == False: 
                    self.TTL_arrived = True

                    data = task.read(self.n_samples)
                    
                    t = 1000*np.linspace(0, self.n_samples/self.sample_rate, len(data[0]))
                    
                    plt.plot(t, data[chan_num], color = 'k', alpha = 0.15)
                    print(np.max(data[chan_num]))
                    #plt.draw()
                    plt.pause(0.05)

                    
                    print(str(self.i),end=' ')   # print shot which just got sampled
                    self.i += 1 
        plt.show()

  
                        
if __name__ == '__main__':

    # Select pulse length, number of shots and the names of the channels you want to monitor. 
    m = monitor(pulse_length    = 0.05, # s
                nShots          = 7000,   # number of shots in the histogram
                channelNames    = ['TTL / V', 'Cool Servo / V'], 
                saveName        = 'Log_Cool_Servo.csv',
                saveDirectory   = r'Z:\Tweezer\Experimental Results\2019\August\23',
                TTL_level       = 3.2 )
                
    m.triggeredAquisition(livePlot = True)
    # m.measureShotProfile(1)
    
    #m.plot_csv(showTTL = False, filterArray =True, shotRate = 1.71)
   
    
















