"""Single Atom Image Analysis
Stefan Spence 14/03/19

Separate out the imageHandler class for processing single atom images from the
director watcher and Qt GUI. This allows it to be imported for other purposes.
Assume that there are two peaks in the histogram which are separated by a 
region of zeros.
Assuming that image files are ASCII and the first column is the row number.
"""
import os
import sys
import numpy as np
import time
from scipy.signal import find_peaks
from scipy.stats import norm
from astropy.stats import binom_conf_interval

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
class image_handler:
    """Analyse individual image files and create a histogram.
    
    Load an ROI image centred on the atom, integrate the counts,
    then compare to the threshold. For speed, make an array of 
    counts with length n. If the number of images analysed exceeds 
    (n-10) of this length then append another n elements to the array.
    The variables stored in relation to an individual image file are:
        """
    def __init__(self):
        self.delim = ' '                # delimieter to use when opening files
        self.n = 10000                  # length of array for storing counts
        self.counts = np.zeros(self.n)  # integrated counts over the ROI
        self.mid_count = np.zeros(self.n)# count at the centre of the ROI
        self.mean_count = np.zeros(self.n) # list of mean counts in image - estimates background 
        self.std_count  = np.zeros(self.n) # list of standard deviation of counts in image
        self.xc_list = np.zeros(self.n) # horizontal positions of max pixel
        self.yc_list = np.zeros(self.n) # vertical positions of max pixel
        self.atom = np.zeros(self.n)    # deduce presence of an atom by comparison with threshold
        self.files = np.array(['']*(self.n)) # number ID of image
        self.peak_indexes = [0,0]       # indexes of peaks in histogram
        self.peak_heights = [0,0]       # heights of peaks in histogram
        self.peak_widths  = [0,0]       # widths of peaks in histogram
        self.peak_counts  = [0,0]       # peak position in counts in histogram
        self.fidelity     = 0           # fidelity of detecting atom presence
        self.err_fidelity = 0           # error in fidelity
        self.xc        = 0              # ROI centre x position 
        self.yc        = 0              # ROI centre y position
        self.roi_size  =  1             # ROI length in pixels. default 1 takes top left pixel
        self.pic_size  = 512            # number of pixels in an image
        self.thresh    = 1              # initial threshold for atom detection
        self.fid       = 0              # file ID number for the next image
        self.im_num    = 0              # number of images processed
        self.im_vals   = np.array([])   # the data from the last image is accessible to an image_handler instance
        self.bin_array = []             # if bins for the histogram are supplied, plotting can be faster
        
    def set_pic_size(self, im_name):
        """Set the pic size by looking at the number of columns in a file
        Keyword arguments:
        im_name    -- absolute path to the image file to load"""
        im_vals = np.genfromtxt(im_name, delimiter=self.delim)
        self.pic_size = int(np.size(im_vals[0]) - 1) # the first column of ASCII image is row number
        return self.pic_size

    def reset_arrays(self):
        """Reset all of the histogram array data to zero"""
        self.files = np.array(['']*(self.n)) # labels of files. 
        self.counts = np.zeros(self.n)  # integrated counts over ROI
        self.mid_count = np.zeros(self.n)  # max count in the image
        self.mean_count = np.zeros(self.n) # list of mean counts in image - estimates background 
        self.std_count = np.zeros(self.n)  # list of standard deviation of counts in image
        self.xc_list = np.zeros(self.n) # horizontal positions of max pixel
        self.yc_list = np.zeros(self.n) # vertical positions of max pixel
        self.atom = np.zeros(self.n)    # deduce presence of an atom by comparison with threshold
        self.im_num = 0                 # number of images processed
        
        
    def load_full_im(self, im_name):
        """return an array with the values of the pixels in an image.
        Assume that the first column is the column number.
        Keyword arguments:
        im_name    -- absolute path to the image file to load"""
        # np.array(Image.open(im_name)) # for bmp images
        # return np.genfromtxt(im_name, delimiter=self.delim)#[:,1:] # first column gives column number
        return np.loadtxt(im_name, delimiter=self.delim,
                              usecols=range(1,self.pic_size+1))
        
    def process(self, im_vals):
        """Get the data from an image. If the arrays have reached their max
        size, then expand them before getting data from the image.
        Keyword arguments:
        im_vals    -- image array to be processed"""
        try:
            self.add_count(im_vals)
        except IndexError: # this is a bad exception - the error might be from a bad ROI rather than reaching the end of the arrays
            # filled the array of size n so add more elements
            if self.im_num % (self.n - 10) == 0 and self.im_num > self.n / 2:
                self.counts = np.append(self.counts, np.zeros(self.n))
                self.mid_count = np.append(self.mid_count, np.zeros(self.n))
                self.mean_count = np.append(self.mean_count, np.zeros(self.n)) 
                self.std_count = np.append(self.std_count, np.zeros(self.n))
                self.xc_list = np.append(self.xc_list, np.zeros(self.n))
                self.yc_list = np.append(self.yc_list, np.zeros(self.n))
                self.atom = np.append(self.atom, np.zeros(self.n))
                self.files = np.append(self.files, np.array(['']*self.n))
            self.add_count(im_vals)

    def add_count(self, full_im):
        """Fill in the next index of the counts by summing over the ROI region and then 
        getting a counts/pixel. 
        Fill in the next index of the file, xc, yc, mean, stdv arrays.
        Keyword arguments:
        im_vals    -- image array to be processed"""
        not_roi = full_im.copy()
        # get the ROI
        if self.roi_size % 2: # odd ROI length (+1 to upper bound)
            # ROI
            self.im_vals = full_im[self.xc-self.roi_size//2:self.xc+self.roi_size//2+1,
            self.yc-self.roi_size//2:self.yc+self.roi_size//2+1]
            # background outside the ROI
            not_roi[self.xc-self.roi_size//2:self.xc+self.roi_size//2+1,
            self.yc-self.roi_size//2:self.yc+self.roi_size//2+1] = np.zeros(np.shape(self.im_vals))
        else:                 # even ROI length
            # ROI
            self.im_vals = full_im[self.xc-self.roi_size//2:self.xc+self.roi_size//2,
            self.yc-self.roi_size//2:self.yc+self.roi_size//2]
            # background outside the ROI
            not_roi[self.xc-self.roi_size//2:self.xc+self.roi_size//2,
            self.yc-self.roi_size//2:self.yc+self.roi_size//2] = np.zeros(np.shape(self.im_vals))

        # background statistics: mean count and standard deviation across image
        N = np.size(full_im) - np.size(self.im_vals)
        self.mean_count[self.im_num] = np.sum(not_roi) / N
        self.std_count[self.im_num] = np.sqrt(np.sum((not_roi[not_roi>0]-self.mean_count[self.im_num])**2) / (N - 1))
        # sum of counts in the ROI of the image gives the signal
        self.counts[self.im_num] = np.sum(self.im_vals) # / np.size(self.im_vals) # mean
        self.files[self.im_num] = self.fid  # file ID number should be updated at each event
        # the pixel value at the centre of the ROI
        self.mid_count[self.im_num] = full_im[self.xc, self.yc]
        # position of the (first) max intensity pixel
        self.xc_list[self.im_num], self.yc_list[self.im_num] = np.unravel_index(np.argmax(full_im), full_im.shape)
        self.im_num += 1
            
    def get_fidelity(self, thresh=None):
        """Calculate the fidelity assuming a normal distribution for peak 1
        centred about p1 with std dev w1 and peak 2 centred around
        p2 with std dev w2. Optionally supply a threshold thresh, otherwise
        use self.thresh"""
        if thresh is None:
            thresh = self.thresh

        if np.size(self.peak_indexes) == 2: # must have already calculated peak parameters
            # fidelity = 1 - P(false positives) - P(false negatives)
            fidelity = norm.cdf(thresh, self.peak_counts[0], self.peak_widths[0]
                            ) - norm.cdf(thresh, self.peak_counts[1], self.peak_widths[1])
            # error is largest fidelity - smallest fidelity from uncertainty in peaks
            err_fidelity = norm.cdf(thresh, self.peak_counts[0] - self.peak_widths[0],
                self.peak_widths[0]) - norm.cdf(thresh, self.peak_counts[1] - self.peak_widths[1],
                self.peak_widths[1]) - norm.cdf(thresh, self.peak_counts[0] + self.peak_widths[0],
                self.peak_widths[0]) + norm.cdf(thresh, self.peak_counts[1] - self.peak_widths[1],
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
        p1  -- the lower limit for the threshold (the background peak mean).
        pw1 -- the width of the background peak, used to guess an upper limit.
        p2  -- the upper limit for the threshold if it's smaller than p1+15*pw1
                (the signal peak mean).
        n   -- the number of thresholds to take between the peaks
        """
        uplim = min([p1 + 15*pw1, p2]) # highest possible value for the threshold 
        threshes = np.linspace(p1, uplim, n) # n points between peaks
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
        self.thresh = np.mean(bins) # in case peak calculation fails
        if np.size(self.peak_indexes) == 2: # est_param will only find one peak if the number of bins is small
            # set the threshold where the fidelity is max
            self.search_fidelity(self.peak_counts[0], self.peak_widths[0] ,self.peak_counts[1])
        # atom is present if the counts are above threshold
        self.atom[:self.im_num] = self.counts[:self.im_num] // self.thresh 
        return bins, occ, self.thresh

    def histogram(self):
        """Make a histogram of the photon counts but don't update the threshold"""
        if np.size(self.bin_array) > 0: 
            occ, bins = np.histogram(self.counts[:self.im_num], self.bin_array) # fixed bins. 
        else:
            try:
                lo, hi = min(self.counts[:self.im_num]), max(self.counts[:self.im_num])
                # scale number of bins with number of files in histogram and with separation of peaks
                num_bins = int(17 + 5e-5 * self.im_num**2 + ((hi - lo)/hi)**2*15) 
            except: 
                lo, hi, num_bins = 0, 1, 10
            occ, bins = np.histogram(self.counts[:self.im_num], bins=num_bins) # no bins provided by user
        # get the indexes of peak positions, heights, and widths
        self.peak_indexes, self.peak_heights, self.peak_widths = est_param(occ)
        self.peak_counts = bins[self.peak_indexes] + 0.5*(bins[1] - bins[0])
        if np.size(self.peak_indexes) == 2: # est_param will only find one peak if the number of bins is small
            # convert widths from indexes into counts
            # assume the peak_width is the FWHM, although scipy docs aren't clear
            self.peak_widths = [(bins[1] - bins[0]) * self.peak_widths[0]/2., # /np.sqrt(2*np.log(2)), 
                                (bins[1] - bins[0]) * self.peak_widths[1]/2.] # /np.sqrt(2*np.log(2))]
        # atom is present if the counts are above threshold
        self.atom[:self.im_num] = self.counts[:self.im_num] // self.thresh
        return bins, occ, self.thresh
        

    def peaks_and_thresh(self):
        """Get an estimate of the peak positions and standard deviations given a set threshold
        Then set the threshold as 5 standard deviations above background
        returns:
        images processed, loading probability, error in loading probability, bg count, bg width, 
        signal count, signal width, separation, fidelity, error in fidelity, threshold"""
        # split histograms at threshold then get mean and stdev:
        ascend = np.sort(self.counts[:self.im_num])
        bg = ascend[ascend < self.thresh]     # background
        signal = ascend[ascend > self.thresh] # signal above threshold
        bg_peak = np.mean(bg)
        bg_stdv = np.std(bg, ddof=1)
        at_peak = np.mean(signal)
        at_stdv = np.std(signal, ddof=1)
        sep = at_peak - bg_peak
        self.thresh = bg_peak + 5*bg_stdv # update threshold
        # atom is present if the counts are above threshold
        self.atom[:self.im_num] = self.counts[:self.im_num] // self.thresh 
        atom_count = np.size(np.where(self.atom > 0)[0])  # images with counts above threshold
        empty_count = np.size(np.where(self.atom[:self.im_num] == 0)[0])
        load_prob = np.around(atom_count / self.im_num, 4)
        # use the binomial distribution to get 1 sigma confidence intervals:
        conf = binom_conf_interval(atom_count, atom_count + empty_count, interval='jeffreys')
        load_err = np.around(conf[1] - conf[0], 4)
        self.fidelity, self. err_fidelity = np.around(self.get_fidelity(), 4)
        return np.array(self.im_num, load_prob, load_err, bg_peak, bg_stdv, at_peak,
                at_stdv, sep, self.fidelity, self.err_fidelity, self.thresh)

    
    def set_roi(self, im_name='', dimensions=[]):
        """Set the ROI for the image either by finding the position of the max 
        in the file im_name, or by taking user supplied dimensions [xc, yc, 
        roi_size]. The default is to use supplied dimensions.
        Keyword arguments:
        im_name    -- absolute path to the image file to load
        dimensions -- user-supplied dimensions to set the ROI to [xc, yc, size]"""
        if np.size(dimensions) != 0:
            self.xc, self.yc, self.roi_size = list(map(int, dimensions))
            return 1
        elif len(im_name) != 0:
            # presume the supplied image has an atom in and take the max
            # pixel's position at the centre of the ROI
            im_vals = self.load_full_im(im_name)
            xcs, ycs  = np.where(im_vals == np.max(im_vals))
            self.xc, self.yc = xcs[0], ycs[0]
            return 1
        else:
            # print("set_roi usage: supply im_name to get xc, yc or supply dimensions [xc, yc, l]")
            return 0 
        
    def load_from_csv(self, file_name):
        """Load back in the counts data from a stored csv file, leaving space
        in the arrays to add new data as well
        Keyword arguments:
        file_name -- the absolute path to the file to load from"""
        data = np.genfromtxt(file_name, delimiter=',')
        with open(file_name, 'r') as f:
            header = f.readline() # check the column headings, might vary between csv files.
        if np.size(data): # check that the file wasn't empty
            i = 0
            self.files = np.concatenate((self.files[:self.im_num], data[:,i], np.array(['']*self.n)))
            self.counts = np.concatenate((self.counts[:self.im_num], data[:,i+1], np.zeros(self.n)))
            self.atom = np.concatenate((self.atom[:self.im_num], data[:,i+2], np.zeros(self.n)))
            if 'Max Count' in header or 'ROI Centre Count' in header:
                self.mid_count = np.concatenate((self.mid_count[:self.im_num], data[:,i+3], np.zeros(self.n)))
                i += 4
            else: # retain compatability with older csv files that don't contain max count
                self.mid_count = np.concatenate((self.mid_count[:self.im_num], np.zeros(self.n + np.size(data[:,i]))))
                i += 3
            self.xc_list = np.concatenate((self.xc_list[:self.im_num], data[:,i], np.zeros(self.n)))
            self.yc_list = np.concatenate((self.yc_list[:self.im_num], data[:,i+1], np.zeros(self.n)))
            self.mean_count = np.concatenate((self.mean_count[:self.im_num], data[:,i+2], np.zeros(self.n)))
            self.std_count = np.concatenate((self.std_count[:self.im_num], data[:,i+3], np.zeros(self.n)))
            self.im_num += np.size(data[:,0]) # now we have filled this many extra columns.

    def save_state(self, save_file_name, hist_header=None, hist_stats=None):
        """Save the processed data to csv. 
        
        The column headings are: 
            File, Counts, Atom Detected (threshold), ROI Centre Count, 
            X-pos (max pix), Y-pos (max pix), Mean Count outside of ROI, 
            standard deviation
        Keyword arguments:
        save_file_name -- the absolute path and name of the file to save to
        hist_header    -- a list of strings for the headings of histogram statistics
        hist_stats     -- a list of histogram statistics associated with this histogram
        """
        # atom is present if the counts are above threshold
        self.atom[:self.im_num] = self.counts[:self.im_num] // self.thresh 
        # histogram data
        out_arr = np.array((self.files[:self.im_num], self.counts[:self.im_num], 
            self.atom[:self.im_num], self.mid_count[:self.im_num], self.xc_list[:self.im_num], 
            self.yc_list[:self.im_num], self.mean_count[:self.im_num],
            self.std_count[:self.im_num])).T
        header = ''
        # if there is histogram data, add this in as well
        if np.size(hist_header) > 1 and np.size(hist_stats) > 1:
            header += ','.join(hist_header)
            header += '\n' + ','.join(list(map(str, hist_stats))) + '\n'
        header += 'File, Counts, Atom Detected (threshold=%s), ROI Centre Count, X-pos (max pix), Y-pos (max pix), Mean Count, s.d.'
        np.savetxt(save_file_name, out_arr, fmt='%s', delimiter=',',
                header=header%int(self.thresh))

####    ####    ####    ####