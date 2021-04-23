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
    calculates generic survival probabilities.
    nhists   -- # of histograms being analysed
    names    -- str labels for each histogram
    inp_cond -- input condition for each histogram (atom present?)
    out_cond -- output condition for each histogram (atom survived?)
    """
    def __init__(self, nhists=1, names=[''], inp_cond=[True], out_cond=[True]):
        super().__init__()
        self.nhist = nhists # number of histograms being analysed
        self.names = names  # names of histograms
        self.c0 = inp_cond  # input conditions (atom present?)
        self.c1 = out_cond  # output conditions (atom survived?)
        # histogram statistics and variables for plotting:
        self.types = OrderedDict([('File ID', int),
        ('User variable', float),
        ('Number of images processed', int), 
        *zip(['Loading probability %s'%self.names[i] for i in range(nhists)], [float]*nhists),
        *zip(['Survival probability %s'%self.names[i] for i in range(nhists)], [float]*nhists),
        *zip(['%s atom survival probability'%i for i in range(nhists)], [float]*nhists),
        ('Condition met', float),
        ('01 cases', float),
        ('10 cases', float),
        ('Include', BOOL)])
        self.stats = OrderedDict([(key, []) for key in self.types.keys()])
        # variables that won't be saved for plotting:
        self.temp_vals = OrderedDict([(key,0) for key in self.stats.keys()])

        self.indxs = [] # survival histogram file IDs
        self.xvals = [] # variables to plot on the x axis
        self.yvals = [] # variables to plot on the y axis
        
    def process(self, befores, afters, user_var, include=True):
        """Calculate the statistics from the current histograms.
        Keyword arguments:
        befores: dict of histogram statistics from before histograms
        afters: dict of histogram statistics from after histograms
        user_var: the user variable associated with this calculation
        include: whether to include the values in further analysis.
        """
        for i, s in befores: # find the file IDs that have atoms in all before histograms
            s = s.stats
            t = self.c0[i]
            if i == 0:
                ids = set(np.array(s['File ID'])[np.where(np.array(s['Atom detected']) > 0, t, not t)])
            else: 
                ids = ids & set(np.array(s['File ID'])[np.where(s['Atom detected'] > 0, t, not t)])
            self.temp_vals['Loading probability %s'%self.names[i]] = (np.array(s['Atom detected']) > 0).sum() / len(s['Atom detected'])
        
        ids = np.array(list(ids))
        self.temp_vals['Number of images processed'] = len(ids)
        survive = np.empty((len(afters), len(ids)))
        condition = ids

        for i, s in afters: 
            s = s.stats
            t = int(self.c1[i])
            afterids = np.array(s['File ID'])[np.array(s['Atom detected']) > 0]
            survive[i] = np.isin(ids, afterids).astype(int)
            self.temp_vals['Survival probability %s'%self.names[i]] = survive[i].sum() / len(afterids)
            condition = condition & set(np.array(s['File ID'])[np.where(np.array(s['Atom detected']) > 0, t, 1-t)])

        self.indxs = [ids[i] for i in survive] # so that survival histogram can be retreived
            
        self.temp_vals['Condition met'] = len(condition) / len(ids)
        natoms = list(survive.sum(axis=0))
        for i in range(self.nhists):
            self.temp_vals['%s atom survival probability'%i] = natoms.count(i) / len(natoms)

        self.temp_vals['User variable'] = self.types['User variable'](user_var) if user_var else 0.0
        self.temp_vals['Include'] = include