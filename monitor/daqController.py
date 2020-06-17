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
from nidaqmx import * # imports errors, scale, stream_readers, stream_writers, task
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
    When running, start a task to read from all of the selected channels. 
    It waits for the analogue trigger channel to surpass the trigger level, 
    then acquires in a loop. To break the loop, set worker.stop = True.
    
    Arguments:
    rate         -- sampling rate in samples/second
    duration     -- how long to sample for in seconds
    trigger_chan -- which channel to use as the trigger
    trigger_lvl  -- voltage threshold for analogue trigger
    trigger_edge -- rising or falling edge to trigger on
    channels     -- which channels to acquire
    ranges       -- max voltage the channel can measure (0.2, 1, 5, 10)"""
    acquired = pyqtSignal(np.ndarray) # acquired data

    def __init__(self, rate, duration, trigger_chan='Dev2/ai0', 
            trigger_lvl=1.0, trigger_edge='rising', 
            channels=['Dev2/ai0'], ranges=[5]):
        super().__init__()
        self.vrs = [0.2, 1.0, 5.0, 10.0] # allowed voltage ranges
        self.stop = False # Used to ensure only 1 data aquisition per pulse
        self.sample_rate = rate 
        self.time = duration
        self.n_samples = int(rate * duration) # number of samples to acquire
        self.lvl  = trigger_lvl
        self.edge = const.Edge.RISING if 'rising' in trigger_edge else const.Edge.FALLING
        self.trig_chan = trigger_chan
        if 'ai' in trigger_chan: # if triggering off analogue input
            try: # then we want the trigger channel to be in the list of channels
                self.trig = channels.index(trigger_chan)
            except ValueError: 
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
            
    def check_stop(self):
        """Check if the thread has been told to stop"""
        return self.stop

    def end_task(self):
        """Make sure that tasks are closed when we're done using them, 
        so that resources can be reallocated."""
        self.stop = True
        if hasattr(self.task, 'close'):
            self.task.close()
            self.task = None 
        self.stop = False

    def acquire_callback(self, task, signaltype, callbackdata):
        """Upon receiving a hardware event, read from the task and emit the acquired data.
        task         -- handle for the task that registered the event 
        signaltype   -- the type of event that was registered (Sample Complete)
        callbackdata -- 'the value you passed in the callback data parameter'."""
        try:
            data = task.read(number_of_samples_per_channel=self.n_samples)
            self.acquired.emit(np.array(data))
        except Exception as e: logger.error("DAQ read failed\n"+str(e))

    def run(self):
        """Start a continuous acquisition, either with a digital trigger, or a
        fudged analogue trigger that reads continuously until the input is > TTL."""
        try:
            if 'di' in self.trig_chan: # digital trigger
                with nidaqmx.Task() as task:
                    for v, chan in zip(self.vranges, self.channels):
                        c = task.ai_channels.add_ai_voltage_chan(chan, 
                            terminal_config=const.TerminalConfiguration.DIFFERENTIAL) 
                        c.ai_rng_high = v # set voltage range
                        c.ai_rng_low = -v
                    task.timing.cfg_samp_clk_timing(self.sample_rate, 
                        sample_mode=const.AcquisitionType.CONTINUOUS, 
                        samps_per_chan=self.n_samples+10000,
                        active_edge=self.edge) # set sample rate and number of samples
                    task.triggers.start_trigger.cfg_dig_edge_start_trig(self.trig_chan, trigger_edge=self.edge)
                    task.register_signal_event(const.Signal.SAMPLE_COMPLETE, self.acquire_callback) # read when data has been acquired
                    while not self.check_stop():
                        time.sleep(0.01) # wait here until stop = True tells the task to close
                self.end_task()
            elif 'ai' in self.trig_chan: # fudged analogue trigger
                self.task = nidaqmx.Task()
                for v, chan in zip(self.vranges, self.channels):
                    c = self.task.ai_channels.add_ai_voltage_chan(chan, terminal_config=const.TerminalConfiguration.DIFFERENTIAL) 
                    c.ai_rng_high = v # set voltage range
                    c.ai_rng_low = -v
                self.task.timing.cfg_samp_clk_timing(self.sample_rate, sample_mode=const.AcquisitionType.CONTINUOUS, 
                    samps_per_chan=self.n_samples+10000) # set sample rate and number of samples
                while not self.check_stop():
                        try:
                            TTL = self.task.read()[self.trig] # read a single value from the trigger channel
                        except TypeError:
                            TTL = self.task.read() # if there is only one channel
                        if TTL > self.lvl: 
                            data = self.task.read(number_of_samples_per_channel=self.n_samples)
                            if np.size(np.shape(data)) == 1:
                                data = [data] # if there's only one channel, still make it a 2D array
                            self.acquired.emit(np.array(data))
                self.end_task()
        except Exception as e: logger.error("DAQ acquisition stopped.\n"+str(e))

    def analogue_acquisition(self):
        """Take a single acquisition on the specified channels."""
        try:
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
        except Exception as e: logger.error("DAQ read failed\n"+str(e))

    def digital_acquisition(self, devport="Dev2/port0/line"):
        """Read in data from all of the digital input channels"""                                                                                                 
        with nidaqmx.Task() as task:
            for i in range(4): task.di_channels.add_di_chan(devport+str(i))
            #task.timing.cfg_samp_clk_timing(self.sample_rate) # set sample rate
            data = task.read(number_of_samples_per_channel=self.n_samples)
            # task.wait_until_done(-1)   
            self.acquired.emit(np.array(data))
            
    def analogue_awg_out(self, channel, data, sample_rate, n_samples, acq_type=const.AcquisitionType.FINITE):
        """Write the data provided to the analogue output channel.
        channel     -- channel name, e.g. 'Dev2/ao0'
        data        -- numpy array of the data to write to the channel
        sample_rate -- the rate at which to take samples from the data
        n_samples   -- the number of samples to write. If n_samples > size(data) it will loop over the data
        acq_type    -- FINITE writes n_samples then stops, CONTINUOUS loops indefinitely."""
        try:
            with nidaqmx.Task() as task:
                task.ao_channels.add_ao_voltage_chan(channel)
                task.timing.cfg_samp_clk_timing(rate=sample_rate, sample_mode=acq_type, samps_per_chan=n_samples)
                writer = stream_writers.AnalogSingleChannelWriter(task.out_stream, auto_start=True)
                writer.write_many_sample(data)
                # task.wait_until_done() # blocks until the task has finished
                # task.stop() # end the task properly
        except Exception as e: logger.error("DAQ AO write failed.\n"+str(e))
            
    def digital_out(self, channel, data):
        """Write teh data provided to the digital output channel. Note that the 
        DO channels only support on-demand writing, they can't use clock timing.
        channel -- channel name, e.g. Dev2/port1/line0
        data    -- numpy array of the data to write, with the appropriate type."""
        try:
            with nidaqmx.Task() as task:
                task.do_channels.add_do_chan(channel)
                writer = stream_writers.DigitalSingleChannelWriter(task.out_stream)
                if data.dtype == bool: # type of write depends on type of data
                    func = writer.write_one_sample_one_line
                elif data.dtype == np.uint8:
                    func = writer.write_many_sample_port_byte
                elif data.dtype == np.uint16:
                    func = writer.write_many_sample_port_uint16
                elif data.dtype == np.uint32:
                    func = writer.write_many_sample_port_uint32
                else: raise(Exception('DAQ DO invalid data type '+str(data.dtype)))
                task.start() # have to start task first since it's on-demand
                func(data) # write data to output channel
                # task.wait_until_done() # blocks until the task has finished
                # task.stop() # end the task properly
        except Exception as e: logger.error("DAQ DO write failed.\n"+str(e))
        
    def counter_out(self, channel, high_time, low_time):
        """Start a continuous counter output channel which is high for high_time
        and low for low_time in units of seconds. The counter channels are Dev/ctr0
        and Dev/ctr1."""
        try:
            with nidaqmx.Task() as task:
                task.co_channels.add_co_pulse_chan_time(channel)
                task.cfg_implicit_timing(const.AcquisitionType.CONTINUOUS)
                task.start()
                task.write(nidaqmx.types.CtrTime(high_time=high_time, low_time=low_time))
        except Exception as e: logger.error("DAQ CO write failed.\n"+str(e))
        