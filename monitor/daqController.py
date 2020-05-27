"""PyDex Monitoring
Stefan Spence 27/05/20

Acquire data from the NI USB-6211 DAQ.
A GUI displays the data as it's acquired, and collects statistics
from multiple traces.
More information on the DAQ is available at:
https://documentation.help/NI-DAQmx-Key-Concepts/documentation.pdf
We use the python module: https://nidaqmx-python.readthedocs.io
"""
import os
import sys
import time 
import nidaqmx
import nidaqmx.constants as const
import numpy as np
import pyqtgraph as pg
from collections import OrderedDict
# some python packages use PyQt4, some use PyQt5...
try:
    from PyQt4.QtCore import QThread, pyqtSignal
    from PyQt4.QtGui import QApplication
except ImportError:
    from PyQt5.QtCore import QThread, pyqtSignal
    from PyQt5.QtWidgets import QApplication
import logging
logger = logging.getLogger(__name__)
sys.path.append('.')
sys.path.append('..')
from strtypes import strlist, BOOL
from mythread import remove_slot

class worker(QThread):
    """Acquire data from the NI USB-6211 DAQ.
    When running, start a task to read from all of the 
    selected channels. It waits for the analogue trigger
    channel to surpass the trigger level, then acquires.
    
    Arguments:
    rate         -- sampling rate in samples/second
    duration     -- how long to sample for in seconds
    trigger_chan -- which channel to use as the trigger
    trigger_lvl  -- voltage threshold for analogue trigger
    trigger_edge -- rising or falling edge to trigger on
    channels     -- which channels to acquire
    ranges       -- max voltage the channel can measure (0.2, 1, 5, 10)"""
    acquired = pyqtSignal(np.ndarray) # acquired data

    def __init__(self, rate, duration, trigger_chan='Dev1/ai0', 
            trigger_lvl=1.0, trigger_edge='rising', 
            channels=['Dev1/ai0'], ranges=[5]):
        super().__init__()
        self.vrs = [0.2, 1.0, 5.0, 10.0] # allowed voltage ranges
        self.TTL_arrived = False # Used to ensure only 1 data aquisition per pulse
        self.sample_rate = rate
        self.time = duration
        self.n_samples = int(rate * duration) # number of samples to acquire
        self.lvl  = trigger_lvl
        self.edge = trigger_edge
        try:
            self.trig = channels.index(trigger_chan)
        except ValueError: # want the trigger channel to be in the list of channels
            self.trig = 0
            channels = [trigger_chan] + channels
            # choose appropriate voltage range for trigger channel
            ind = np.abs(np.array(self.vrs)-self.lvl).argmin()
            if self.vrs[ind] > self.lvl*1.2:
                ranges = [self.vrs[ind]] + ranges
            else:
                try:
                    ranges = [self.vrs[ind+1]] + ranges
                except IndexError:
                    ranges = [self.vrs[-1]] + ranges
        self.channels = channels
        self.vranges = ranges

    def trigger_analog_input(self,devport, edge_selection):
        """
        Configures the input channel and sample clock. Sets the task to trigger when PFI0 recieves a trigger
        """
        max_num_samples = 2
        task = nidaqmx.Task()
        task.ai_channels.add_ai_voltage_chan("Dev1/ai1",terminal_config = const.TerminalConfiguration.DIFFERENTIAL)
        task.timing.cfg_samp_clk_timing(self.sample_rate,active_edge=const.Edge.RISING) 
        task.triggers.start_trigger.cfg_dig_edge_start_trig("/Dev1/PFI0", trigger_edge=const.Edge.RISING)
        return task
        
    def measure_analog_io_on_trigger(self,taskhandle):
        taskhandle.read(number_of_samples_per_channel=self.n_samples)
        taskhandle.StartTask()
        taskhandle.register_done_event(taskhandle.close) # close the task when finished

    def run(self):
        """Read the input from the trigger channel. When it surpasses the set trigger level, start an acquisition."""
        with nidaqmx.Task() as task:
            for v, chan in zip(self.vranges, self.channels):
                c = task.ai_channels.add_ai_voltage_chan(chan, terminal_config=const.TerminalConfiguration.DIFFERENTIAL) 
                c.ai_rng_high = v # set voltage range
                c.ai_rng_low = -v
            task.timing.cfg_samp_clk_timing(self.sample_rate, sample_mode=const.AcquisitionType.CONTINUOUS, 
                samps_per_chan=self.n_samples+1000) # set sample rate and number of samples
            while self.TTL_arrived == False:
                try:
                    TTL = task.read()[self.trig] # read a single value from the trigger channel
                except TypeError:
                    TTL = task.read() # if there is only one channel
                if TTL < self.lvl: 
                    self.TTL_arrived = False
                if TTL > self.lvl and self.TTL_arrived == False: 
                    self.TTL_arrived = True
                    data = task.read(number_of_samples_per_channel=self.n_samples)
                    # task.wait_until_done(-1)
                    if np.size(np.shape(data)) == 1:
                        data = [data] # if there's only one channel, still make it a 2D array
                    self.acquired.emit(np.array(data))

    def digital_acquisition(self, n_samples=1000):
        """Read in data from all of the digital input channels"""                                                                                                 
        with nidaqmx.Task() as task:
            for i in range(4): task.di_channels.add_di_chan("Dev1/port0/line"+str(i))
            #task.timing.cfg_samp_clk_timing(self.sample_rate) # set sample rate
            data = task.read(number_of_samples_per_channel=n_samples)
            task.wait_until_done(-1)   
