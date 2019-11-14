"""Single Atom Image Analysis
Stefan Spence 15/04/19

a class to collect and calculate histogram statistics

"""
import numpy as np
from collections import OrderedDict
from .analysis import Analysis

class histo_handler(Analysis):
    """Manage statistics from several histograms.
    
    Append histogram statistics to a list. These are defined in
    an ordered dictionary so that they can each be individually managed
    and the labels retain the insertion order (to keep the values next to their
    errors). A second dictionary allows for temporarily storing values.
    Inherits reset_arrays, load, and save functions from Analysis.
    """
    def __init__(self):
        super().__init__()
        # histogram statistics and variables for plotting:
        self.types = OrderedDict([('File ID', int),
        ('Start file #', int),
        ('End file #', int),
        ('ROI xc ; yc ; size', str),
        ('Counts above : below threshold', str),
        ('User variable', float),
        ('Number of images processed', int), 
        ('Loading probability', float), 
        ('Error in Loading probability', float),
        ('Lower Error in Loading probability', float),
        ('Upper Error in Loading probability', float),
        ('Background peak count', int), 
        ('Error in Background peak count', float), 
        ('Background peak width', float),
        ('sqrt(Nr^2 + Nbg)', float), 
        ('Background mean', float), 
        ('Background standard deviation', float), 
        ('Signal peak count', int), 
        ('Error in Signal peak count', float),
        ('Signal peak width', float), 
        ('sqrt(Nr^2 + Ns)', float),
        ('Signal mean', float), 
        ('Signal standard deviation', float), 
        ('Separation', float),
        ('Error in Separation', float),
        ('Fidelity', float), 
        ('Error in Fidelity', float),
        ('S/N', float),
        ('Error in S/N', float),
        ('Threshold', float)])
        self.stats = OrderedDict([(key, []) for key in self.types.keys()])
        # variables that won't be saved for plotting:
        self.temp_vals = OrderedDict([(key,0) for key in self.stats.keys()])
        self.xvals = [] # variables to plot on the x axis
        self.yvals = [] # variables to plot on the y axis
        
    def sort_dict(self, lead='User variable'):
        """Sort the arrays in the stats_dict such that they are all ordered 
        with the item given by lead ascending.
        Keyword arguments:
        lead -- a key in the stats_dict that defines the item to sort by."""
        idxs = np.argsort(self.stats[lead])
        for key in self.stats.keys():
            self.stats[key] = self.stats[key][idxs]