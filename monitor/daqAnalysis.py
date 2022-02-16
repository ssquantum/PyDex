"""PyDex Monitoring Analysis
Stefan Spence 01/06/20

 - Take a trace acquired by the DAQ
 - Choose slices to take an average and std dev of.
 - Accumulate a slice for every trace taken
"""
import os
import re
import sys
if '.' not in sys.path: sys.path.append('.')
if '..' not in sys.path: sys.path.append('..')
import time
import numpy as np
try:
    from PyQt4.QtCore import pyqtSignal, QThread
except ImportError:
    from PyQt5.QtCore import pyqtSignal, QThread
from collections import OrderedDict
from strtypes import strlist, listlist, BOOL, error, warning, info
from networking.client import simple_msg
import sys

def channel_stats(text):
    """Convert a string list of channel settings into an 
    ordered dictionary: "[['Dev4/ai0', '', '1.0', '0.0', '0', '0', '0']]"
    -> OrderedDict([('Dev4/ai0', {'label':'', 'offset':1.0,
        'range':0, 'acquire':0, 'plot':0})])
    """
    d = OrderedDict()
    keys = ['label', 'scale', 'offset', 'range', 'acquire', 'plot']
    types = [str, float, float, float, BOOL, BOOL]
    for channel in map(strlist, re.findall("\[['\w,\s\./]+\]", text)):
        d[channel[0]] = OrderedDict([(keys[i], types[i](val)) 
                for i, val in enumerate(channel[1:])])
    return d

####    ####    ####    ####

class daqSlice:
    """Analyse the data from part of a DAQ measurement.
    Slice properties: name, indexes, channels to apply to.
    For each trace, take the run number, mean, and std dev."""
    def __init__(self, name='', start=0, end=1, channels=OrderedDict([('Dev4/ai0',0)])):
        self.name = name
        self.i0   = start
        self.i1   = end
        self.inds = slice(start, end+1) # the indices to use for the slice
        self.size = end - start
        self.channels = channels # dict of channelname, index
        self.stats = OrderedDict([(chan, OrderedDict([
            ('mean',[]), ('stdv',[])])) for chan in channels.keys()])

        self.blurbstr = "POST /write?db=arduino HTTP/1.1\nHost: 129.234.190.191\n"
        self.blurbstr += "User-Agent: PyDex\nConnection: close\n"
        self.blurbstr += "Content-Type: application/x-www-form-urlencoded\n"
        self.blurbstr += "Content-Length: %s\n\n"
        self.datastr = 'Experiment,SOURCE=DAQmonitor,name="%s",channel0="%s" '%(name, list(self.channels.keys())[0])
                
    def process(self, data, ind, send_data=False):
        """Apply the slice to the given data, extract the mean and std dev.
        Note that the data must have shape to match the expected # channels.
        data -- measured voltages [[measurement] * # channels].
        ind  -- index of the channel to assign the data to."""
        for chan, i in self.channels.items():
            if i == ind:
                try:
                    row = data[0] # i if multiple channels are being measured simultaneously
                    self.stats[chan]['mean'].append(np.mean(row[self.inds]))
                    self.stats[chan]['stdv'].append(np.std(row[self.inds], ddof=1))
                    if send_data:
                        try: # send results via TCP to influxdb
                            datastr = self.datastr + "mean_V=%.6f,stdv_V=%.6f "%(self.stats[chan]['mean'][-1], self.stats[chan]['stdv'][-1])
                            datastr += str(int(time.time()*1e9)) + '\n'
                            msg = self.blurbstr%len(datastr) + datastr
                            _ = simple_msg('129.234.190.191', 8086, msg)
                        except Exception as e:
                            error("DAQ analysis failed to send results to influxdb\n"+str(e))
                except IndexError as e:
                    error('Data wrong shape to take slice at %s.\n'%i + str(e))
            else: # just to keep them all the same length
                self.stats[chan]['mean'].append(np.nan) 
                self.stats[chan]['stdv'].append(np.nan)

        
####    ####    ####    ####
            
class daqCollection(QThread):
    """Handle a collection of daqSlice classes.
    param -- list of parameters to create daqSlice: [name,start,end,channels].
    channels -- list of channels used in the measurement.
    """
    acq_settings = pyqtSignal(str, str) # emit loaded DAQ acquisition settings

    def __init__(self, param=[['Slice0',0,1,OrderedDict([('Dev4/ai0',0)])]],
            channels=['Dev4/ai0']):
        super().__init__()
        self.slices = [daqSlice(*p) for p in param]
        self.channels = channels
        self.ind = 0 # number of shots processed
        self.runs = [] # run number for identifying the trace
        self.times = [] # time the run was taken

    def reset_arrays(self, *args):
        """Reset all of the data to empty"""
        self.runs = []
        self.times = []
        for s in self.slices:
            for c in s.stats.keys():
                s.stats[c] = OrderedDict([('mean',[]), ('stdv',[])])
        self.ind = 0   

    def add_slice(self, name, start, end, channels):
        """Add another slice to the set. Also empties lists.
        name     -- a label to identify the slice
        start    -- first index
        end      -- last index
        channels -- OrderedDict of channel names and indexes"""
        self.slices.append(daqSlice(name, start, end, channels))
        self.reset_arrays() # make sure they're the same length
        
    def process(self, data, n, ind, send_data=False):
        """Send the data to all of the slices. It must have the right shape."""
        self.runs.append(n)
        self.times.append(time.time())
        for s in self.slices:
            s.process(data, ind, send_data)
        self.ind += 1
            
    def load(self, file_name):
        """Load back data stored in csv. Metadata for the DAQ 
        acquisition and the slices are stored in the header. 
        Then data follows."""
        head = [[],[],[],[],[]] # get metadata
        with open(file_name, 'r') as f:
            for i in range(5):
                row = f.readline()
                if row[:2] == '# ':
                    head[i] = row[2:].replace('\n','')
        self.acq_settings.emit(head[0], head[1]) # acquisition settings
        self.slices = []
        self.channels = list(channel_stats(head[1]).keys())
        for sstr in head[3].split('; '): # slice settings
            str1, chanstr = sstr.split('[')
            name, si0, si1 = str1.split(', ')
            chans = chanstr.replace(']','').split(', ')
            self.add_slice(name, int(si0), int(si1), chans)
        data = np.genfromtxt(file_name, delimiter=',')
        if np.size(data) > 1: # load data into lists
            self.runs = list(map(int, data[:,0]))
            self.times = list(map(float, data[:,-1]))
            nchans = (len(data[0]) - 1) // 2 # number of channels
            i = 1
            for s in self.slices:
                for chan, stats in s.stats.items():
                    stats['mean'] = list(data[:,i])
                    stats['stdv'] = list(data[:,i+nchans])
                    i += 1

        
    def save(self, file_name, meta_head=[], meta_vals=[]):
        """Save the processed data to csv. 
        First row is metadata column headings as list
        Second row is metadata values as list
        Third row is slice settings column headings
        Fourth row is slice settings values
        Fifth row is data column headings
        Then data follows.
        """
        header = ', '.join(meta_head) + '\n'
        header += ', '.join(meta_vals) + '\n'
        header += 'name, start index, end index, [channels]; ...\n'
        header += '; '.join([s.name+", %s, %s, ['"%(s.i0, s.i1)
            + "', '".join(self.channels) + "']" for s in self.slices]) +'\n'
        header += 'Run, ' + ', '.join([s.name + '//' + chan + val for val in [
            ' mean', ' stdv'] for s in self.slices for chan in s.stats.keys()]
            ) + ', Time since epoch (s)'
        try:
            out_arr = np.array([self.runs] + [s.stats[chan][val] for val in 
                ['mean', 'stdv'] for s in self.slices for chan in 
                s.stats.keys()] + [self.times]).T
            np.savetxt(file_name, out_arr, delimiter=',', fmt='%s', header=header)
        except (PermissionError, FileNotFoundError) as e:
            error('DAQ Analysis denied permission to save file: \n'+str(e))