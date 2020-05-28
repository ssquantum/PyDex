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
            ranges = [self.coerce_range(self.lvl)] + ranges
        self.channels = channels
        self.vranges = ranges
        self.task = None
        remove_slot(self.finished, self.end_task, True)

    def coerce_range(self, vrange):
        """Force vrange to be the closest larger voltage range."""
        ind = np.abs(np.array(self.vrs)-vrange).argmin()
        if self.vrs[ind] > vrange*1.2:
            return self.vrs[ind]
        else:
            try: return self.vrs[ind+1]
            except IndexError: return self.vrs[-1]

    def end_task(self):
        """Make sure that tasks are closed when we're done using them, 
        so that resources can be reallocated."""
        if hasattr(self.task, 'close'):
            self.task.close()
            self.task = None 

    def trigger_analog_input(self,devport, edge_selection, timeout=20):
        """
        Configures the input channel and sample clock. Sets the task to trigger when PFI0 recieves a trigger
        """
        max_num_samples = 2
        with nidaqmx.Task() as task:
            task.ai_channels.add_ai_voltage_chan("Dev1/ai1",terminal_config = const.TerminalConfiguration.DIFFERENTIAL)
            task.timing.cfg_samp_clk_timing(self.sample_rate, active_edge=const.Edge.RISING) 
            task.triggers.start_trigger.cfg_dig_edge_start_trig("/Dev1/PFI0", trigger_edge=const.Edge.RISING)
            task.register_done_event(task.close) # close the task when finished
            data = task.read(number_of_samples_per_channel=self.n_samples, timeout=timeout)
            self.acquired.emit(np.array(data))

    def run(self):
        """Read the input from the trigger channel. When it surpasses the set trigger level, start an acquisition."""
        self.task = nidaqmx.Task()
        for v, chan in zip(self.vranges, self.channels):
            c = self.task.ai_channels.add_ai_voltage_chan(chan, terminal_config=const.TerminalConfiguration.DIFFERENTIAL) 
            c.ai_rng_high = v # set voltage range
            c.ai_rng_low = -v
        self.task.timing.cfg_samp_clk_timing(self.sample_rate, sample_mode=const.AcquisitionType.CONTINUOUS, 
            samps_per_chan=self.n_samples+10000) # set sample rate and number of samples
        while self.TTL_arrived == False:
            try:
                TTL = self.task.read()[self.trig] # read a single value from the trigger channel
            except TypeError:
                TTL = self.task.read() # if there is only one channel
            if TTL < self.lvl: 
                self.TTL_arrived = False
            if TTL > self.lvl and self.TTL_arrived == False: 
                self.TTL_arrived = True
                data = self.task.read(number_of_samples_per_channel=self.n_samples)
                if np.size(np.shape(data)) == 1:
                    data = [data] # if there's only one channel, still make it a 2D array
                self.acquired.emit(np.array(data))

    def analogue_acquisition(self):
        """Take a single acquisition on the specified channels."""
        with nidaqmx.Task() as task:
            for v, chan in zip(self.vranges, self.channels):
                c = task.ai_channels.add_ai_voltage_chan(chan, terminal_config=const.TerminalConfiguration.DIFFERENTIAL) 
                c.ai_rng_high = v # set voltage range
                c.ai_rng_low = -v
            task.timing.cfg_samp_clk_timing(self.sample_rate, sample_mode=const.AcquisitionType.CONTINUOUS, 
                samps_per_chan=self.n_samples+1000)
            data = task.read(number_of_samples_per_channel=self.n_samples)
            # task.wait_until_done(-1)
            if np.size(np.shape(data)) == 1:
                data = [data] # if there's only one channel, still make it a 2D array
            self.acquired.emit(np.array(data))

    def digital_acquisition(self):
        """Read in data from all of the digital input channels"""                                                                                                 
        with nidaqmx.Task() as task:
            for i in range(4): task.di_channels.add_di_chan("Dev1/port0/line"+str(i))
            #task.timing.cfg_samp_clk_timing(self.sample_rate) # set sample rate
            data = task.read(number_of_samples_per_channel=self.n_samples)
            task.wait_until_done(-1)   