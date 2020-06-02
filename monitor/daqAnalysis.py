"""PyDex Monitoring Analysis
Stefan Spence 01/06/20

 - Take a trace acquired by the DAQ
 - Choose slices to take an average and std dev of.
 - Accumulate a slice for every trace taken
"""
import os
import sys
sys.path.append('.')
sys.path.append('..')
import numpy as np
from collections import OrderedDict
from strtypes import strlist, listlist
import logging
logger = logging.getLogger(__name__)


class daqSlice:
    """Analyse the data from part of a DAQ measurement.
    Slice properties: name, indexes, channels to apply to.
    For each trace, take the run number, mean, and std dev."""
    def __init__(self, name='', start=0, end=1, channels=OrderedDict([('Dev2/ai0',0)])):
        self.name = name
        self.i0   = start
        self.i1   = end
        self.inds = slice(start, end+1)
        self.size = end - start
        self.runs = []
        self.channels = channels
        self.stats = OrderedDict([(chan, OrderedDict([
            ('mean',[]), ('stdv',[])])) for chan in channels.keys()])
        
    def process(self, data, n):
        """Apply the slice to the given data, extract the mean and std dev.
        Note that the data must have shape to match the expected # channels.
        data -- measured voltages [[measurement] * # channels]
        n    -- the run number to identify this point with."""
        self.runs.append(n)
        for chan, i in self.channels.items():
            try:
                row = data[i]
                self.stats[chan]['mean'].append(np.mean(row[self.inds]))
                self.stats[chan]['stdv'].append(np.std(row[self.inds], ddof=1))
            except IndexError as e:
                logger.error('Data wrong shape to take slice at %s.\n'%n + str(e))

        
####    ####    ####    ####
            
class daqCollection:
    """Handle a collection of daqSlice classes.
    param -- list of parameters to create daqSlice: [name,start,end,channels].
    channels -- list of channels used in the measurement.
    """

    def __init__(self, param=[['Slice0',0,1,OrderedDict([('Dev2/ai0',0)])]],
            channels=['Dev2/ai0']):
        self.slices = [daqSlice(*p) for p in param]
        self.channels = channels
        self.ind = 0 # number of shots processed

    def reset_arrays(self):
        """Reset all of the data to empty"""
        for s in self.slices:
            for c in s.stats.keys():
                s.stats[c] = OrderedDict([('mean',[]), ('stdv',[])])
        self.ind = 0   
        
    def process(self, data, n):
        """Send the data to all of the slices. It must have the right shape."""
        for s in self.slices:
            s.process(data, n)
        self.ind += 1
            
    def load(self, file_name):
        """Load back data stored in csv. 
        First row is metadata column headings
        Second row is metadata values
        Third row is data column headings
        Then data follows."""
        pass
        
    def save(self, file_name, meta_head=[], meta_vals=[]):
        """Save the processed data to csv. 
        First row is metadata column headings as list
        Second row is metadata values as list
        Third row is number of slices and list of channels measured
        Then data follows.
        """
        try:
            with open(file_name, 'w+') as f:
                f.write('# '+'; '.join(meta_head) + '\n')
                f.write('# '+'; '.join(meta_vals) + '\n')
                f.write('# '+str(len(self.slices)) + " slices; ['" + 
                        "', '".join(self.channels) + "']\n")
                for s in self.slices:
                    f.write(s.name + "; %s; %s; ['"%(s.i0, s.i1) + 
                        "', '".join(s.channels.keys()) + "']\n")
                    f.write('runs: ' + str(s.runs) + '\n')
                    for key, val in s.stats.items():
                        f.write(key + ' mean: ' + str(val['mean'])+'\n')
                        f.write(key + ' stdv: ' + str(val['stdv'])+'\n')
        except PermissionError as e:
            logger.error('DAQ Analysis denied permission to save file: \n'+str(e))