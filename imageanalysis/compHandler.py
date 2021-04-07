"""Single Atom Image Analysis
Stefan Spence 23/03/21

a class to compare histograms

"""
import numpy as np
from collections import OrderedDict
from analysis import Analysis, BOOL

class comp_handler(Analysis):
    """Manage statistics from several histograms.
    
    Append histogram statistics to a list. This analysis
    calculates generic survival probabilities starting
    with an arbitrary number of atoms: natoms.
    """
    def __init__(self, natoms=1):
        super().__init__()
        # histogram statistics and variables for plotting:
        self.types = OrderedDict([('File ID', int),
        ('User variable', float),
        ('Files included', int), 
        *zip(['Loading probability %s'%i for i in range(natoms)], [float]*natoms),
        *zip(['%s survive'%i for i in range(natoms)], [float]*natoms),
        ('01 cases', float),
        ('10 cases', float)
        ('Include', BOOL)])
        self.stats = OrderedDict([(key, []) for key in self.types.keys()])
        # variables that won't be saved for plotting:
        self.temp_vals = OrderedDict([(key,0) for key in self.stats.keys()])

        self.natom = natoms # number of histograms being analysed
        self.xvals = [] # variables to plot on the x axis
        self.yvals = [] # variables to plot on the y axis
        
    def single(self, before, after, user_var, include=True):
        """Simple survival probability if there's only 1 ROI"""
        ids = before['File ID'][np.where(before['Atom detected'] > 0, True, False)]


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
        n = len(ids)
        self.temp_vals['Total'] = n
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