"""Single Atom Image Analysis
Stefan Spence 23/03/21

a class to compare histograms

"""
import numpy as np
from collections import OrderedDict
from analysis import Analysis, BOOL

class comp_handler(Analysis):
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
        ('User variable', float),
        ('Total', int), 
        ('None', int), 
        ('Some', int),
        ('All', int),
        ('Permutations', eval),
        ('Include', BOOL)])
        self.stats = OrderedDict([(key, []) for key in self.types.keys()])
        # variables that won't be saved for plotting:
        self.temp_vals = OrderedDict([(key,0) for key in self.stats.keys()])

        self.xvals = [] # variables to plot on the x axis
        self.yvals = [] # variables to plot on the y axis
        
    def sort_dict(self, lead='User variable'):
        """Sort the arrays in stats dict such that they are all ordered 
        with the item given by lead ascending.
        Keyword arguments:
        lead -- a key in the stats that defines the item to sort by."""
        idxs = np.argsort(self.stats[lead])
        for key in self.stats.keys():
            self.stats[key] = [self.stats[key][i] for i in idxs]

    def process(self, befores, afters, user_var, include=True):
        """Calculate the statistics from the current histograms.
        Keyword arguments:
        befores: dict of histogram statistics from before histograms
        afters: dict of histogram statistics from after histograms
        user_var: the user variable associated with this calculation
        include: whether to include the values in further analysis.
        """
        o = befores.pop(0)
        ids = set(o['File ID'][np.where(o['Atom detected'] > 0, True, False)])
        for s in befores: # find the file IDs that have atoms in all before histograms
            ids = ids & set(s['File ID'][np.where(s['Atom detected'] > 0, True, False)])

        o = afters.pop(0)
        atoms = set(o['File ID'][np.where(o['Atom detected'][ids] > 0, True, False)])
        full = atoms
        some = atoms
        none = set(o['File ID'][np.where(o['Atom detected'][ids] == 0, True, False)])
        for s in afters:
            full = atoms & set(s['File ID'][np.where(s['Atom detected'][ids] > 0, True, False)])
            # one but not the other: atoms ^ set()
            some = atoms | set(s['File ID'][np.where(s['Atom detected'][ids] > 0, True, False)])
            none = none & set(s['File ID'][np.where(s['Atom detected'][ids] == 0, True, False)])

        some = some - full
        self.temp_vals['Total'] = len(ids)
        self.temp_vals['User variable'] = self.types['User variable'](user_var) if user_var else 0.0
        self.temp_vals['None'] = len(none)
        self.temp_vals['Some'] = len(some)
        self.temp_vals['All']  = len(full)
        ol = set(o['File ID'][np.where(o['Atom detected'][ids] == 0, True, False)]
            ) & set(s['File ID'][np.where(s['Atom detected'][ids] > 0, True, False)])
        lo = set(o['File ID'][np.where(o['Atom detected'][ids] > 0, True, False)]
            ) & set(s['File ID'][np.where(s['Atom detected'][ids] == 0, True, False)])
        self.temp_vals['Permutations'] = [len(ol), len(lo)]
        self.temp_vals['Include'] = include