"""Single Atom Image Analysis
Stefan Spence 15/04/19

a class to collect histogram statistics

"""
import numpy as np
from collections import OrderedDict

class histo_handler:
    """Manage statistics from several histograms.
    
    Append histogram statistics to a list. These are defined in
    an ordered dictionary so that they can each be individually managed
    and the labels retain the insertion order (to keep the values next to their
    errors). A second dictionary allows for temporarily storing values.
    """
    def __init__(self):
        # histogram statistics and variables for plotting:
        self.stats_dict = OrderedDict([('Hist ID',np.array([], dtype=int)),
        ('Start file #',np.array([], dtype=int)),
        ('End file #',np.array([], dtype=int)),
        ('ROI xc ; yc ; size',np.array([], dtype=str)),
        ('Counts above : below threshold',np.array([], dtype=str)),
        ('User variable',np.array([], dtype=float)),
        ('Number of images processed',np.array([], dtype=int)), 
        ('Loading probability',np.array([], dtype=float)), 
        ('Error in Loading probability',np.array([], dtype=float)),
        ('Lower Error in Loading probability',np.array([], dtype=float)),
        ('Upper Error in Loading probability',np.array([], dtype=float)),
        ('Background peak count',np.array([], dtype=int)), 
        ('Error in Background peak count',np.array([], dtype=float)), 
        ('Background peak width',np.array([], dtype=int)),
        ('sqrt(Nr^2 + Nbg)',np.array([], dtype=int)), 
        ('Background mean',np.array([], dtype=float)), 
        ('Background standard deviation',np.array([], dtype=float)), 
        ('Signal peak count',np.array([], dtype=int)), 
        ('Error in Signal peak count',np.array([], dtype=float)),
        ('Signal peak width',np.array([], dtype=int)), 
        ('sqrt(Nr^2 + Ns)',np.array([], dtype=int)),
        ('Signal mean',np.array([], dtype=float)), 
        ('Signal standard deviation',np.array([], dtype=float)), 
        ('Separation',np.array([], dtype=float)),
        ('Error in Separation',np.array([], dtype=float)),
        ('Fidelity',np.array([], dtype=float)), 
        ('Error in Fidelity',np.array([], dtype=float)),
        ('S/N',np.array([], dtype=float)),
        ('Error in S/N',np.array([], dtype=float)),
        ('Threshold',np.array([], dtype=float))])
        # variables that won't be saved for plotting:
        self.temp_vals = OrderedDict([(key,0) for key in self.stats_dict.keys()])
        self.xvals    = [] # variables to plot on the x axis
        self.yvals    = [] # variables to plot on the y axis
        
    def load_from_log(self, fname):
        """load data from a log file. Expect the first 3 rows to be comments.
        The 3rd row gives the column headings. If one of the keys from the 
        dictionary is not in the column headings, fill its array with zeros.
        Keyword arguments:
        fname -- the absolute path to the file to load from"""
        header=''
        with open(fname, 'r') as f:
            rows = f.read().split('\n')
        rows = list(filter(None, rows)) # get rid of empty row, usually from \n at end of file
        # get headers
        try:
            header = rows[2]
        except IndexError:
            print('Load from log warning: Invalid log file. Data was not loaded.')
            return 0
        # remove comments, retain compatability with old column heading
        header = header.replace('#', '').replace(
                'loading', 'Loading').replace('fidelity', 'Fidelity')
        # make list
        header = np.array(header.replace('Histogram', 'Hist ID').split(', '))
        # get data
        if np.size(rows) < 4:
            return 0 # no data to be loaded
        data = np.array([rows[i+3].split(',') for i in range(len(rows)-3)])
        if np.size(data) < np.size(header):
            return 0 # insufficient to be loaded
        n = len(data[:,0]) # number of points on the plot
        for key in self.stats_dict.keys():
            index = np.where(header == key)[0]
            if np.size(index): # if the key is in the header
                self.stats_dict[key] = np.array(data[:,index], dtype=self.stats_dict[key].dtype).reshape(n)
            else: # load an empty array
                self.stats_dict[key] = np.zeros(n, dtype=self.stats_dict[key].dtype)
        return 1 # success
    
    def sort_dict(self, lead='User variable'):
        """Sort the arrays in the stats_dict such that they are all ordered 
        with the item given by lead ascending.
        Keyword arguments:
        lead -- a key in the stats_dict that defines the item to sort by."""
        idxs = np.argsort(self.stats_dict[lead])
        for key in self.stats_dict.keys():
            self.stats_dict[key] = self.stats_dict[key][idxs]