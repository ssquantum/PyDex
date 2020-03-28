"""Single Atom Image Analysis
Stefan Spence 14/03/19

Separate out the imageHandler class for processing single atom images from the
director watcher and Qt GUI. This allows it to be imported for other purposes.
Assuming that image files are ASCII and the first column is the row number.
"""
import os
import sys
import numpy as np
from collections import OrderedDict
import time
from scipy.signal import find_peaks
from scipy.stats import norm
from skimage.filters import threshold_minimum
from astropy.stats import binom_conf_interval
from analysis import Analysis
import logging
logger = logging.getLogger(__name__)

def est_param(h):
    """Generator function to estimate the parameters for a Guassian fit. 
    Use scipy to find search for peaks. Assume first that the peaks have arbitrary
    separation then increase the separation until there are only two peaks or less found.
    Return the positions, heights, and widths of peaks.
    The positions and widths are in terms of indexes in the input array."""
    d   = 1    # required minimal horizontal distance between neighbouring peaks
    inc = np.size(h)//500 * 5 + 1 # increment to increase distance by
    num_peaks = 10
    while num_peaks > 2:
        peak_inds, properties = find_peaks(h, width=0, distance=d) # properties is a dict
        num_peaks = np.size(peak_inds)
        d += inc   # increase the width of the peaks we're searching for

    return peak_inds, properties['prominences'], properties['widths']

####    ####    ####    ####
        
# convert an image into its pixel counts to put into a histogram
class image_handler(Analysis):
    """Analyse individual image files and create a histogram.
    
    Load an ROI image centred on the atom, integrate the counts,
    then compare to the threshold.
    Inherits the types and stats dictionaries, and reset_arrays, 
    load, and save methods from Analysis."""
    def __init__(self):
        super().__init__()
        self.types = OrderedDict([('File ID', int), # number ID of image
            ('Counts', float), # integrated counts over the ROI
            ('Atom detected', int), # compare counts with threshold value
            ('ROI centre count', float), # count at the centre of the ROI
            ('Max xpos', int), # horizontal positions of max pixel
            ('Max ypos', int), # vertical positions of max pixel
            ('Mean bg count', float), # mean counts outside ROI - estimate bg
            ('Bg s.d.', float),# standard deviation outside of ROI
            ('Include', bool)])# whether to include in further analysis
        self.stats = OrderedDict([(key, []) for key in self.types.keys()]) # standard deviation of counts outside ROI
        
        self.delim = ' '                # delimieter to use when opening image files
        self.bias = 697                 # bias offset from EMCCD
        self.peak_indexes = [0,0]       # indexes of peaks in histogram
        self.peak_heights = [0,0]       # heights of peaks in histogram
        self.peak_widths  = [0,0]       # widths of peaks in histogram
        self.peak_centre  = [0,0]       # peak position in counts in histogram
        self.fidelity     = 0           # fidelity of detecting atom presence
        self.err_fidelity = 0           # error in fidelity
        self.mask      = np.zeros((1,1))# normalised mask to apply to image for ROI
        self.xc        = 1              # ROI centre x position 
        self.yc        = 1              # ROI centre y position
        self.roi_size  = 1              # ROI length in pixels. default 1 takes top left pixel
        self.pic_size  = 512            # number of pixels in an image
        self.thresh    = 1              # initial threshold for atom detection
        self.fid       = 0              # file ID number for the next image
        self.ind       = 0              # number of images processed
        self.im_vals   = np.array([])   # the data from the last image is accessible to an image_handler instance
        self.bin_array = []             # if bins for the histogram are supplied, plotting can be faster
    
    def process(self, im, include=True):
        """Fill in the next index of counts by integrating over
        the ROI. Append file ID, xc, yc, mean, stdv as well.
        Keyword arguments:
        im      -- image array to be processed
        include -- whether to include the image in further analysis
        """
        full_im = im - self.bias # remove the bias offset, it's arbitrary
        try:
            self.im_vals = full_im * self.mask # get the ROI
            not_roi = full_im * (1-self.mask)
        except ValueError as e:
            s0 = np.shape(self.mask)
            self.im_vals = np.zeros(s0)
            not_roi = np.zeros(s0)
            include = False
            s1 = np.shape(im)
            logger.error("Received image was wrong shape (%s,%s) for analyser's ROI (%s,%s)"%(
                s1[0],s1[1],s0[0],s0[1]))
        # background statistics: mean count and standard deviation across image
        N = np.sum(1-self.mask)
        self.stats['Mean bg count'].append(np.sum(not_roi) / N)
        self.stats['Bg s.d.'].append(
            np.sqrt(np.sum((not_roi - self.stats['Mean bg count'][-1])**2) / (N - 1)))
        # sum of counts in the ROI of the image gives the signal
        self.stats['Counts'].append(np.sum(self.im_vals)) 
        # file ID number should be updated externally before each event
        self.stats['File ID'].append(str(self.fid))  
        # the pixel value at the centre of the ROI
        try:
            self.stats['ROI centre count'].append(full_im[self.xc, self.yc])
        except IndexError as e:
            logger.error('ROI centre (%s, %s) outside of image size %s'%(
                self.xc, self.yc, self.pic_size))
            self.stats['ROI centre count'].append(0)
        # position of the (first) max intensity pixel
        xmax, ymax = np.unravel_index(np.argmax(full_im), full_im.shape)
        self.stats['Max xpos'].append(xmax)
        self.stats['Max ypos'].append(ymax)
        self.stats['Include'].append(include)
        self.ind += 1
            
    def get_fidelity(self, thresh=None):
        """Calculate the fidelity assuming a normal distribution for peak 1
        centred about p1 with std dev w1 and peak 2 centred around
        p2 with std dev w2. Optionally supply a threshold thresh, otherwise
        use self.thresh"""
        if thresh is None:
            thresh = self.thresh
        if np.size(self.peak_indexes) == 2: # must have already calculated peak parameters
            # fidelity = 1 - P(false positives) - P(false negatives)
            fidelity = norm.cdf(thresh, self.peak_centre[0], self.peak_widths[0]
                            ) - norm.cdf(thresh, self.peak_centre[1], self.peak_widths[1])
            # error is largest fidelity - smallest fidelity from uncertainty in peaks
            err_fidelity = norm.cdf(thresh, self.peak_centre[0] - self.peak_widths[0],
                self.peak_widths[0]) - norm.cdf(thresh, self.peak_centre[1] - self.peak_widths[1],
                self.peak_widths[1]) - norm.cdf(thresh, self.peak_centre[0] + self.peak_widths[0],
                self.peak_widths[0]) + norm.cdf(thresh, self.peak_centre[1] - self.peak_widths[1],
                self.peak_widths[1])
            return fidelity, err_fidelity
        else:
            return -1, -1  # calculation failed

    def search_fidelity(self, p1, pw1, p2, n=10):
        """Take n values for the threshold between positions p1 and 
        p1 + 15*pw1 or p2, whichever is smaller. Calculate the threshold for 
        each value. Choose the threshold that first gives a fidelity > 0.9999,
        or if that isn't possible, the threshold that maximises the fidelity.
        Keyword arguments:
        p1  -- the background peak mean, used to guess a lower limit.
        pw1 -- the width of the background peak, used to guess an upper limit.
        p2  -- the upper limit for the threshold if it's smaller than p1+15*pw1
                (the signal peak mean).
        n   -- the number of thresholds to take between the peaks
        """
        uplim = max(p1+pw1+1, min([p1+15*pw1, p2])) # highest possible value for the threshold 
        threshes = np.linspace(p1+pw1, uplim, n) # n points between peaks
        fid, err_fid = 0, 0  # store the previous value of the fidelity
        for thresh in threshes[1:]: # threshold should never be at the background peak p1
            f, fe = self.get_fidelity(thresh) # calculate fidelity for given threshold
            if f > fid:
                fid, err_fid = f, fe
                self.thresh = thresh # the threshold at which there is max fidelity
                if fid > 0.9999:
                    break
        # set to max value, round to 4 d.p.
        self.fidelity, self.err_fidelity = np.around([fid, err_fid] , 4)
            
    def hist_and_thresh(self):
        """Make a histogram of the photon counts and determine a threshold for 
        single atom presence by iteratively checking the fidelity."""
        bins, occ, _ = self.histogram()
        self.thresh = np.mean(bins) # initial guess
        self.peaks_and_thresh() # in case peak calculation fails
        # if np.size(self.peak_indexes) == 2: # est_param will only find one peak if the number of bins is small
        #     # set the threshold where the fidelity is max
        #     self.search_fidelity(self.peak_centre[0], self.peak_widths[0] ,self.peak_centre[1])
        try: 
            thresh = threshold_minimum(np.array(self.stats['Counts']), len(bins))
        except RuntimeError as e:
            thresh = -1
        if thresh > 0: 
            self.thresh = thresh
        # atom is present if the counts are above threshold
        self.stats['Atom detected'] = [x // self.thresh for x in self.stats['Counts']]
        self.fidelity, self. err_fidelity = np.around(self.get_fidelity(), 4)
        return bins, occ, self.thresh

    def histogram(self):
        """Make a histogram of the photon counts but don't update the threshold"""
        if np.size(self.bin_array) > 0: 
            occ, bins = np.histogram(self.stats['Counts'], self.bin_array) # fixed bins. 
        else:
            try:
                lo, hi = min(self.stats['Counts'])*0.97, max(self.stats['Counts'])*1.02
                # scale number of bins with number of files in histogram and with separation of peaks
                num_bins = int(15 + self.ind//100 + (abs(hi - abs(lo))/hi)**2*15) 
                occ, bins = np.histogram(self.stats['Counts'], bins=np.linspace(lo, hi, num_bins+1)) # no bins provided by user
            except: 
                occ, bins = np.histogram(self.stats['Counts'])
        if np.size(self.stats['Counts']): # don't do anything to an empty list
            # get the indexes of peak positions, heights, and widths
            self.peak_indexes, self.peak_heights, self.peak_widths = est_param(occ)
            if np.size(self.peak_indexes) == 2: # est_param will only find one peak if the number of bins is small
                self.peak_centre = bins[self.peak_indexes] + 0.5*(bins[1] - bins[0])
                # convert widths from indexes into counts
                # assume the peak_width is the FWHM, although scipy docs aren't clear
                self.peak_widths = [(bins[1] - bins[0]) * self.peak_widths[0]/2., # /np.sqrt(2*np.log(2)), 
                                    (bins[1] - bins[0]) * self.peak_widths[1]/2.] # /np.sqrt(2*np.log(2))]
            else: 
                cs = np.sort(self.stats['Counts']) 
                mid = len(cs) // 2 # index of the middle of the counts array
                self.peak_heights = [np.max(occ), np.max(occ)]
                self.peak_centre = [np.mean(cs[:mid]), np.mean(cs[mid:])]
                self.peak_widths = [np.std(cs[:mid]), np.std(cs[mid:])]
                
            # atom is present if the counts are above threshold
            self.stats['Atom detected'] = [x // self.thresh for x in self.stats['Counts']]
        return bins, occ, self.thresh
        
    def peaks_and_thresh(self):
        """Get an estimate of the peak positions and standard deviations given a set threshold
        Then set the threshold as 5 standard deviations above background
        returns:
        images processed, loading probability, error in loading probability, bg count, bg width, 
        signal count, signal width, separation, fidelity, error in fidelity, threshold"""
        # split histograms at threshold then get mean and stdev:
        ascend = np.sort(self.stats['Counts'])
        bg = ascend[ascend < self.thresh]     # background
        signal = ascend[ascend > self.thresh] # signal above threshold
        bg_peak = np.mean(bg)
        bg_stdv = np.std(bg, ddof=1)
        at_peak = np.mean(signal)
        at_stdv = np.std(signal, ddof=1)
        self.thresh = bg_peak + 5*bg_stdv # update threshold
        return self.ind, bg_peak, bg_stdv, at_peak, at_stdv, self.thresh

    def create_square_mask(self):
        """Use the current ROI dimensions to create a mask for the image.
        The square mask is zero outside the ROI and 1 inside the ROI."""
        if (self.xc + self.roi_size//2 < self.pic_size and 
                self.xc - self.roi_size//2 >= 0 and 
                self.yc + self.roi_size//2 < self.pic_size and 
                self.yc - self.roi_size//2 >= 0):
            self.mask = np.zeros((self.pic_size, self.pic_size))
            self.mask[self.xc - self.roi_size//2 : (
                self.xc + self.roi_size//2 + self.roi_size%2),
                self.yc - self.roi_size//2 : (
                self.yc + self.roi_size//2 + self.roi_size%2)
                ] = np.ones((self.roi_size, self.roi_size))

    def set_pic_size(self, im_name):
        """Set the pic size by looking at the number of columns in a file
        Keyword arguments:
        im_name    -- absolute path to the image file to load"""
        im_vals = np.genfromtxt(im_name, delimiter=self.delim)
        self.pic_size = int(np.size(im_vals[0]) - 1) # the first column of ASCII image is row number
        self.create_square_mask()
        return self.pic_size

    def set_roi(self, im_name='', dimensions=[]):
        """Set the ROI for the image either by finding the position of the max 
        in the file im_name, or by taking user supplied dimensions [xc, yc, 
        roi_size]. The default is to use supplied dimensions.
        Keyword arguments:
        im_name    -- absolute path to the image file to load
        dimensions -- user-supplied dimensions to set the ROI to [xc, yc, size]"""
        success = 0
        if np.size(dimensions) != 0:
            self.xc, self.yc, self.roi_size = list(map(int, dimensions))
            success = 1
        elif len(im_name) != 0:
            # presume the supplied image has an atom in and take the max
            # pixel's position at the centre of the ROI
            im_vals = self.load_full_im(im_name)
            xcs, ycs  = np.where(im_vals == np.max(im_vals))
            self.xc, self.yc = xcs[0], ycs[0]
            success = 1
        if success:
            self.create_square_mask()
        return success

    def load_full_im(self, im_name):
        """return an array with the values of the pixels in an image.
        Assume that the first column is the column number.
        Keyword arguments:
        im_name    -- absolute path to the image file to load"""
        # np.array(Image.open(im_name)) # for bmp images
        # return np.genfromtxt(im_name, delimiter=self.delim)#[:,1:] # first column gives column number
        return np.loadtxt(im_name, delimiter=self.delim,
                              usecols=range(1,self.pic_size+1))