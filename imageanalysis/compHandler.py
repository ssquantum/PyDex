"""Single Atom Image Analysis
Stefan Spence 23/03/21

a class to compare histograms

"""
import numpy as np
from collections import OrderedDict
from analysis import Analysis, BOOL
from astropy.stats import binom_conf_interval

class comp_handler(Analysis):
    """Manage statistics from several histograms.
    
    Append histogram statistics to a list. This analysis
    calculates generic survival probabilities.
    befores  -- list of image_handlers from before histograms
    afters   -- list of image_handlers statistics from after histograms
    nhists   -- # of histograms being analysed
    names    -- str labels for each histogram
    inp_cond -- input condition for each histogram (atom present?)
    out_cond -- output condition for each histogram (atom survived?)
    """
    def __init__(self, befores, afters, nhists=1, inp_cond=[True], out_cond=[True]):
        super().__init__()
        self.befores = befores
        self.afters = afters
        self.nhists = nhists # number of histograms being analysed
        self.c0 = inp_cond  # input conditions (atom present?)
        self.c1 = out_cond  # output conditions (atom survived?)
        # histogram statistics and variables for plotting:
        self.types = OrderedDict([('File ID', int),
        ('User variable', float),
        ('Number of images processed', int), 
        *zip(['Loading probability %s'%x.name for x in befores], [float]*nhists),
        *zip(['Survival probability %s'%x.name for x in afters], [float]*nhists),
        *zip(['Error in Survival probability %s'%x.name for x in afters], [float]*nhists),
        *zip(['%s atom survival probability'%i for i in range(nhists+1)], [float]*(nhists+1)),
        *zip(['Error in %s atom survival probability'%i for i in range(nhists+1)], [float]*(nhists+1)),
        ('Condition met', float),
        ('Error in Condition met', float),
        ('Include', BOOL)])
        self.stats = OrderedDict([(key, []) for key in self.types.keys()])
        # variables that won't be saved for plotting:
        self.temp_vals = OrderedDict([(key,0) for key in self.stats.keys()])

        self.hist_ids = OrderedDict([('%s survival'%x.name, []) for x in afters] + 
            [('%s atom'%i, []) for i in range(nhists+1)] + 
            [('Condition met', [])]) # file IDs to recreate histograms
        self.xvals = [] # variables to plot on the x axis
        self.yvals = [] # variables to plot on the y axis

    def conf(self, success, total):
        """Return the Binomial confidence at 1 sigma"""
        try:
            sp = success / total
            conf = binom_conf_interval(success, total, interval='jeffreys')
            uperr = conf[1] - sp # 1 sigma confidence above mean
            loerr = sp - conf[0] # 1 sigma confidence below mean
            return sp, uperr, loerr, 0.5*(uperr+loerr)
        except ValueError as e:
            return 0, 0, 0, 0
        
    def process(self, user_var, natoms=-1, include=True):
        """Calculate the statistics from the current histograms.
        Keyword arguments:
        user_var: the user variable associated with this calculation
        natoms: include files where natoms were loaded (instead of fixed condition)
        include: whether to include the values in further analysis.
        """
        try: 
            s = self.befores[0].stats['File ID']
            ids = np.arange(min(s), max(s)+1) # list of all file IDs (hopefully)
            loading = np.empty((self.nhists, len(ids)))
        except (IndexError, ValueError): return 0
        
        if natoms >= 0: # don't mind which ROIs the atoms are in
            c0 = [1]*self.nhists
        else: c0 = self.c0 # a specific condition
            
        for i, s in enumerate(self.befores): # find the file IDs that have atoms in all before histograms
            name = s.name
            s.stats['Atom detected'] = [x // s.thresh for x in s.stats['Counts']] # recalculate atom detected
            s = s.stats
            t = int(c0[i])
            # if i == 0:
            #     ids = set(np.array(s['File ID'])[np.where(np.array(s['Atom detected']) > 0, t, not t)])
            # else: 
            #     ids = ids & set(np.array(s['File ID'])[np.where(np.array(s['Atom detected']) > 0, t, not t)])
            self.temp_vals['Loading probability %s'%name] = (np.array(s['Atom detected']) > 0).sum() / len(s['Atom detected'])
            beforeids = np.array(s['File ID'])[np.where(np.array(s['Atom detected']) > 0, t, not t).astype(bool)]
            loading[i] = np.isin(ids, beforeids).astype(int)

        loading = loading.sum(axis=0) # number of atoms in each image
        if natoms >= 0: # files containing natoms
            ids = ids[loading==natoms]
        else: # files satisfying all the conditions
            ids = ids[loading==np.max(loading)]
        
        self.temp_vals['Number of images processed'] = len(ids)
        survive = np.empty((self.nhists, len(ids)), dtype=bool)
        condition = set(ids)

        for i, s in enumerate(self.afters): 
            name = s.name
            s.stats['Atom detected'] = [x // s.thresh for x in s.stats['Counts']] # recalculate atom detected
            s = s.stats
            afterids = np.array(s['File ID'])[np.array(s['Atom detected']) > 0]
            survive[i] = np.isin(ids, afterids)
            sp, _, _, err = self.conf(survive[i].sum(), len(ids))
            self.temp_vals['Survival probability %s'%name] = sp
            self.temp_vals['Error in Survival probability %s'%name] = err
            if not self.c1[i]: afterids = np.array(s['File ID'])[np.array(s['Atom detected']) <= 0]
            condition = condition & set(ids[np.isin(ids, afterids)])

        for i, x in enumerate(survive):
            self.hist_ids['%s survival'%self.afters[i].name] = ids[x]
            
        try:
            sp, _, _, err = self.conf(len(condition), len(ids))
            self.temp_vals['Condition met'] = sp
            self.temp_vals['Error in Condition met'] = err
            self.hist_ids['Condition met'] = np.array(list(condition))
            numatoms = survive.sum(axis=0)
            for i in range(self.nhists+1):
                self.hist_ids['%s atom'%i] = ids[numatoms == i]
                sp, _, _, err = self.conf(len(self.hist_ids['%s atom'%i]), len(numatoms))
                self.temp_vals['%s atom survival probability'%i] = sp
                self.temp_vals['Error in %s atom survival probability'%i] = err
        except ZeroDivisionError as e: pass
        
        self.temp_vals['User variable'] = self.types['User variable'](user_var) if user_var else 0.0
        self.temp_vals['Include'] = include
        self.temp_vals['File ID'] = int(self.ind)
        return 1