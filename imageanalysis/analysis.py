"""Single Atom Image Analysis
Stefan Spence 14/11/19

This template for analysis classes fixes the result structure so that files
can be saved and loaded consistently.
The idea for this analysis structure was taken from CsPyController, 
a similar software produced by Martin Lichtman and group
https://github.com/QuantumQuadrate/CsPyController/
See chapter 9 of his thesis for discussion: 
https://apps.dtic.mil/dtic/tr/fulltext/u2/1010895.pdf
"""
import sys
import numpy as np
from collections import OrderedDict
try:
    from PyQt4.QtCore import QThread
except ImportError:
    from PyQt5.QtCore import QThread
import logging
logger = logging.getLogger(__name__)
sys.path.append('.')
sys.path.append('..')
from strtypes import BOOL

####    ####    ####    ####
        
class Analysis(QThread):
    """A template for analysis classes.
    It is recommended that properties which will have many elements
    (e.g. collecting counts from series of images) are stored in lists.
    These are collected in an ordered dictionary to keep them labelled.
    Also store the type for use when loading from file.
    These inherited properties must be initiated with super().__init__(...)
    so that the methods load() and save() can access them
    """
    # inherited properties:
    ind = 0 # a counter for the number of events processed
    bf  = None # class for fitting function to histogram data

    def __init__(self, type_labels=[('File ID', str)]):
        super().__init__()
        # note: all lists in the stats dictionary should have the same length.
        self.types = OrderedDict(type_labels)
        self.stats = OrderedDict([(key, []) for key in self.types.keys()])
        
        # class-specific properties:

    def reset_arrays(self):
        """Reset all of the data to empty"""
        for key in self.stats.keys():
            self.stats[key] = []
        self.ind = 0   
        self.bf  = None
        
    def process(self, data, *args, **kwargs):
        """React to a single instance of incoming data.
        args: a tuple of arguments passed after the data argument
        kwargs: a dictionary of keyword arguments.
        Override this function in the child class."""
        self.ind += 1
            
    def load(self, file_name, *args, **kwargs):
        """Load back data stored in csv. 
        First row is metadata column headings
        Second row is metadata values
        Third row is data column headings
        Then data follows."""
        head = [[],[],[]]
        with open(file_name, 'r') as f:
            for i in range(3):
                row = f.readline()
                if row[:2] == '# ':
                    head[i] = row[2:].replace('\n','').split(',')

        data = np.genfromtxt(file_name, delimiter=',', dtype=str)
        if np.size(data) < len(self.stats.keys()):
            return 0 # insufficient data to load

        try:
            n = len(data[:,0]) # number of processed events
        except IndexError:
            n = 1
            data = np.array([data])
        for key in self.stats.keys():
            index = np.where([k == key for k in head[2]])[0]
            if np.size(index): # if the key is in the header
                self.stats[key] += list(map(self.types[key], data[:,index[0]]))
            else: # keep lists the same size: fill with zeros.
                self.stats[key] += list(map(self.types[key], [0]*n))
        self.ind = np.size(self.stats[key]) # length of last array
        return head # success

    def save(self, file_name, meta_head=[], meta_vals=[], *args, **kwargs):
        """Save the processed data to csv. 
        First row is metadata column headings as list
        Second row is metadata values as list
        Third row is data column headings
        Then data follows.
        """
        # data converted to the correct type
        out_arr = np.array([list(map(self.types[key], val))
                for key, val in self.stats.items()], dtype=str).T

        header = ','.join(meta_head) + '\n'
        header += ','.join(meta_vals) + '\n'
        header += ','.join(list(self.stats.keys()))
        
        try:
            np.savetxt(file_name, out_arr, fmt='%s', delimiter=',', header=header)
        except PermissionError as e:
            logger.error('Analysis denied permission to save file: \n'+str(e))