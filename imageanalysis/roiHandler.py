"""Single Atom Image Analysis
Stefan Spence 13/04/20

Allocate ROIs on an image and assign thresholds to determine
atom presence
"""
import sys
import numpy as np
from scipy.stats import norm
from skimage.filters import threshold_minimum
import logging
logger = logging.getLogger(__name__)

####    ####    ####    ####

class ROI:
    """The properties of a ROI: imshape ((width, height) of image) 
    xc (centre pixel x-coordinate), yc (centre pixel y-coordinate), 
    width (in pixels), height (in pixels), threhsold (for 
    determining atom presence), counts (list of integrated 
    counts within the ROI), ID (number to identify this ROI)."""
    def __init__(self, imshape, xc, yc, width, height, threshold=1, counts=[], ID=0):
        self.x = xc
        self.y = yc
        self.w = width
        self.h = height
        self.t = threshold
        self.c = counts
        self.i = ID
        self.create_rect_mask(imshape)

    def create_rect_mask(self, image_shape):
        """Use the current ROI dimensions to create a mask for the image.
        The rect mask is zero outside the ROI and 1 inside the ROI."""
        self.s = image_shape # store the shape of the image
        if (self.x + self.w//2 < self.s[0] and 
                self.x - self.w//2 >= 0 and 
                self.y + self.h//2 < self.s[1] and 
                self.y - self.h//2 >= 0):
            self.mask = np.zeros(self.s)
            self.mask[self.x - self.w//2 : (self.x + self.w//2 + self.w%2),
                self.y - self.h//2 : (self.y + self.h//2 + self.h%2)
                ] = np.ones((self.w, self.h))

    def resize(self, xc, yc, width, height):
        """Reset the position and dimensions of the ROI"""
        self.x, self.y, self.w, self.h = xc, yc, width, height

    def atom(self):
        """A list of whether the counts are above threshold"""
        return [x // self.t for x in self.c]

    def LP(self):
        """Calculate the loading probability from images above threshold"""
        return sum(1 for x in self.c if x > self.t)

    def thresh(self):
        """Automatically choose a threshold based on the counts"""
        try: 
            lo, hi = min(self.c)*0.97, max(self.c)*1.02
            num_bins = int(15 + len(self.c)//100 + (abs(hi - abs(lo))/hi)**2*15) 
            thresh = threshold_minimum(np.array(self.c), num_bins)
            int(np.log(thresh)) # ValueError if thresh <= 0 
            self.t = thresh
        except (ValueError, RuntimeError, OverflowError): 
            try:
                max(self.c) # ValueError if empty list
                self.t = np.mean(self.c)
            except (ValueError, TypeError):
                self.t = 1

####    ####    ####    ####

# convert an image into its pixel counts to check for atoms
class roi_handler:
    """Determine the presence of atoms in ROIs of an image
    
    For each of the ROIs, keep a list of counts to compare to
    threshold to discern if an atom is present"""
    def __init__(self, num_rois=1, im_shape=(512,512)):
        self.ROIs = [ROI(im_shape,1,1,1,1) for i in range(num_rois)]
        self.shape = im_shape
        self.delim = ' '
    
    def process(self, im):
        """Add the integrated counts in each ROI to their lists.
        Return success = 1 if all ROIs have an atom, otherwise 0"""
        success = 1
        for r in self.ROIs:
            try:
                counts = np.sum(im * r.mask)
                success = 1 if abs(counts) // r.t and success else 0
                r.c.append(counts) 
            except ValueError as e:
                s0 = np.shape(im)
                logger.error("Image was wrong shape (%s,%s) for atom checker's ROI %s (%s,%s)"%(
                    s0[0], s0[1], r.i, r.s[0], r.s[1]) + str(e))
        return success

    def set_pic_size(self, im_name):
        """Set the pic size by looking at the number of columns in a file
        Keyword arguments:
        im_name    -- absolute path to the image file to load"""
        self.shape = np.genfromtxt(im_name, delimiter=self.delim).shape
        try: self.shape[1] -= 1
        except IndexError: self.shape = (self.shape[0], 1)
        for r in self.ROIs:
            r.create_rect_mask(self.shape)
        