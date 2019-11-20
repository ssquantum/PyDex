"""Single Atom Image Analysis
Stefan Spence 15/04/19

a class to collect and calculate histogram statistics

"""
import numpy as np
from collections import OrderedDict
from astropy.stats import binom_conf_interval
from analysis import Analysis
import fitCurve as fc

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
        self.Nr = 8.8   # read-out noise from EMCCD
        
    def sort_dict(self, lead='User variable'):
        """Sort the arrays in stats dict such that they are all ordered 
        with the item given by lead ascending.
        Keyword arguments:
        lead -- a key in the stats that defines the item to sort by."""
        idxs = np.argsort(self.stats[lead])
        for key in self.stats.keys():
            self.stats[key] = self.stats[key][idxs]

    def process(self, ih, user_var, new_thresh=True, method='quick'):
        """Calculate the statistics from the current histogram.
        Keyword arguments:
        ih: an instance of the image_handler Analysis class, generates the histogram
        user_var: the user variable associated with this calculation
        thresh_toggle: True - update the threshold value, False - keep old threshold
        method: 'quick' - image_handler uses a peak finding algorithm 
                'double gaussian' - fit a double Guassian function
                'separate gaussians' - split the histogram at the threshold and fit Gaussians
                'double poissonian' - fit a double Poissonian function
                'single gaussian' - fit a single Gaussian to background peak
        """
        if ih.ind > 0: # only update if a histogram exists
            if new_thresh: # using manual threshold
                bins, occ, thresh = ih.histogram() # update hist and peak stats, keep thresh
            else:
                bins, occ, thresh = ih.hist_and_thresh() # update hist and get peak stats

            bin_mid = (bins[1] - bins[0]) * 0.5 # from edge of bin to middle

            self.bf = fc.fit(bins[:-1] + bin_mid, occ) # class for fitting function to data

            if method == 'quick':
                A0, A1 = ih.peak_heights
                mu0, mu1 = ih.peak_centre
                sig0, sig1 = ih.peak_widths
            elif method == 'double gaussian':
                self.bf.p0s=[ih.peak_heights[0], ih.peak_centre[0], ih.peak_widths[0],
                        ih.peak_heights[1], ih.peak_centre[1], ih.peak_widths[1]]
                try:
                    # parameters are: amplitude, centre, standard deviation
                    self.bf.getBestFit(self.bf.double_gauss)     # get best fit parameters
                except: return 0  # fit failed, do nothing
                if self.bf.ps[1] < self.bf.ps[4]:
                    A0, mu0, sig0, A1, mu1, sig1 = self.bf.ps
                else: A1, mu1, sig1, A0, mu0, sig0 = self.bf.ps

            elif method == 'separate gaussians': # separate Gaussian fit for bg/signal
                diff = abs(bins - thresh)   # minimum is at the threshold
                thresh_i = np.argmin(diff)  # index of the threshold
                # split the histogram at the threshold value
                best_fits = [fc.fit(bins[:thresh_i]+bin_mid, occ[:thresh_i]),
                                fc.fit(bins[thresh_i:-1]+bin_mid, occ[thresh_i:])]
                for b in best_fits:
                    try:
                        b.estGaussParam()         # get estimate of parameters
                        b.getBestFit(b.gauss)    # get best fit parameters
                    except: return 0    
                A0, mu0, sig0 = best_fits[0].ps
                A1, mu1, sig1 = best_fits[1].ps
                self.bf.p0s = list(best_fits[0].p0s) + list(best_fits[1].p0s)
                self.bf.ps = list(best_fits[0].ps) + list(best_fits[1].ps)
                self.bf.bffunc = self.bf.double_gauss

            elif method == 'double poissonian':
                self.bf.p0s=[ih.peak_heights[0], ih.peak_centre[0],
                        ih.peak_heights[1], ih.peak_centre[1]]
                try:
                    # parameters are: mean, amplitude
                    self.bf.getBestFit(self.bf.double_poisson) 
                except: return 0  
                A0, mu0, A1, mu1 = self.bf.ps
                sig0, sig1 = np.sqrt(mu0), np.sqrt(mu1)

            elif method == 'single gaussian':
                try:
                    self.bf.estGaussParam()
                    self.bf.getBestFit(self.bf.gauss) # get best fit parameters
                except: return 0            # fit failed, do nothing
                A0, mu0, sig0 = self.bf.ps
                A1, mu1, sig1 = 0, 0, 0 

            ih.peak_heights = [A0, A1]
            ih.peak_centre = [mu0, mu1]
            ih.peak_widths = [sig0, sig1]
        
            # update threshold to where fidelity is maximum
            if new_thresh: # update thresh if not set by user
                ih.search_fidelity(mu0, sig0, mu1, n=100)
            else:
                ih.fidelity, ih.err_fidelity = np.around(ih.get_fidelity(), 4) # round to 4 d.p.

            # update atom statistics
            ih.stats['Atom detected'] = [count // ih.thresh for count in ih.stats['Counts']]

            above_idxs = np.where(np.array(ih.stats['Atom detected']) > 0)[0] # index of images with counts above threshold
            atom_count = np.size(above_idxs)  # number of images with counts above threshold
            above = np.array(ih.stats['Counts'])[above_idxs] # counts above threshold
            below_idxs = np.where(np.array(ih.stats['Atom detected']) == 0)[0] # index of images with counts below threshold
            empty_count = np.size(below_idxs) # number of images with counts below threshold
            below = np.array(ih.stats['Counts'])[below_idxs] # counts below threshold
            # use the binomial distribution to get 1 sigma confidence intervals:
            conf = binom_conf_interval(atom_count, atom_count + empty_count, interval='jeffreys')
            loading_prob = atom_count/ih.ind # fraction of images above threshold
            uplperr = conf[1] - loading_prob # 1 sigma confidence above mean
            lolperr = loading_prob - conf[0] # 1 sigma confidence below mean

            # store the calculated histogram statistics as temp
            self.temp_vals['File ID'] = int(self.ind)
            file_list = [x for x in ih.stats['File ID'] if x]
            self.temp_vals['Start file #'] = min(map(int, file_list))
            self.temp_vals['End file #'] = max(map(int, file_list))
            self.temp_vals['ROI xc ; yc ; size'] = ' ; '.join(list(map(str, [ih.xc, ih.yc, ih.roi_size])))
            self.temp_vals['User variable'] = float(user_var) if user_var else 0.0
            self.temp_vals['Number of images processed'] = ih.ind
            self.temp_vals['Counts above : below threshold'] = str(atom_count) + ' : ' + str(empty_count)
            self.temp_vals['Loading probability'] = np.around(loading_prob, 4)
            self.temp_vals['Error in Loading probability'] = np.around((uplperr+lolperr)*0.5, 4)
            self.temp_vals['Lower Error in Loading probability'] = np.around(lolperr, 4)
            self.temp_vals['Upper Error in Loading probability'] = np.around(uplperr, 4)
            if np.size(ih.peak_centre) == 2:
                self.temp_vals['Background peak count'] = int(mu0)
                # assume bias offset is self.bias, readout noise standard deviation Nr
                if self.Nr**2+mu0 > 0:
                    self.temp_vals['sqrt(Nr^2 + Nbg)'] = int((
                        ih.roi_size*self.Nr**2+mu0)**0.5)
                else: # don't take the sqrt of a -ve number
                    self.temp_vals['sqrt(Nr^2 + Nbg)'] = 0
                self.temp_vals['Background peak width'] = int(sig0)
                self.temp_vals['Error in Background peak count'] = np.around(sig0 / empty_count**0.5, 2)
                self.temp_vals['Background mean'] = np.around(np.mean(below), 1) if np.size(below) else 0
                self.temp_vals['Background standard deviation'] = np.around(np.std(below, ddof=1), 1) if np.size(below) else 0
                self.temp_vals['Signal peak count'] = int(mu1)
                # assume bias offset is self.bias, readout noise standard deviation Nr
                if self.Nr**2+mu1 > 0:
                    self.temp_vals['sqrt(Nr^2 + Ns)'] = int((
                        ih.roi_size*self.Nr**2+mu1)**0.5)
                else: # don't take the sqrt of a -ve number
                    self.temp_vals['sqrt(Nr^2 + Ns)'] = 0
                self.temp_vals['Signal peak width'] = int(sig1)
                self.temp_vals['Error in Signal peak count'] = np.around(sig1 / atom_count**0.5, 2)
                self.temp_vals['Signal mean'] = np.around(np.mean(above), 1) if np.size(above) else 0
                self.temp_vals['Signal standard deviation'] = np.around(np.std(above, ddof=1), 1) if np.size(above) else 0
                sep = mu1 - mu0 # separation of fitted peaks
                self.temp_vals['Separation'] = int(sep)
                seperr = np.sqrt(sig0**2 / empty_count + sig1**2 / atom_count) # propagated error in separation
                self.temp_vals['Error in Separation'] = np.around(seperr, 2)
                self.temp_vals['Fidelity'] = ih.fidelity
                self.temp_vals['Error in Fidelity'] = ih.err_fidelity
                self.temp_vals['S/N'] = np.around(sep / np.sqrt(sig0**2 + sig1**2), 2)
                # fractional error in the error is 1/sqrt(2N - 2)
                self.temp_vals['Error in S/N'] = np.around(
                    self.temp_vals['S/N'] * np.sqrt((seperr/sep)**2 + (sig0**2/(2*empty_count - 2) 
                    + sig1**2/(2*atom_count - 2))/(sig0**2 + sig1**2)), 2) if (empty_count>1 and atom_count>1) else 0.0
            else:
                for key in ['Background peak count', 'sqrt(Nr^2 + Nbg)', 'Background peak width', 
                'Error in Background peak count', 'Signal peak count', 'sqrt(Nr^2 + Ns)', 
                'Signal peak width', 'Error in Signal peak count', 'Separation', 'Error in Separation', 
                'Fidelity', 'Error in Fidelity', 'S/N', 'Error in S/N']:
                    self.temp_vals[key] = 0
            self.temp_vals['Threshold'] = int(ih.thresh)
        return 1 # fit successful

    def update_fit(self, ih, user_var, new_thresh=True, method='quick'):
        """Fit functions to the peaks and use it to get a better estimate of the 
        peak centres and widths. Use the fits to get histogram statistics, then set 
        the threshold to maximise fidelity. Iterate until the threshold converges.
        ih: an instance of the image_handler Analysis class, generates the histogram
        user_var: the user variable associated with this calculation
        thresh_toggle: True - update the threshold value, False - keep old threshold
        method: 'quick' - image_handler uses a peak finding algorithm 
                'dbl gauss' - fit a double Guassian function
                'split gauss' - split the histogram at the threshold and fit Gaussians
                'dbl poisson' - fit a double Poissonian function
                'sgl gauss' - fit a single Gaussian to background peak"""
        success = 0
        if ih.ind > 0: # only update if a histogram exists
            oldthresh = ih.thresh # store the last value
            diff = 1              # convergence criterion
            for i in range(20):   # shouldn't need many iterations
                if diff < 0.0015:
                    break
                success = self.process(ih, user_var, new_thresh, method)
                diff = abs(oldthresh - ih.thresh) / float(oldthresh)
            if success: # process returns 0 if it fails
                self.process(ih, user_var, new_thresh, method)
        return success  