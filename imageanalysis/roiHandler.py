"""Single Atom Image Analysis
Stefan Spence 13/04/20

Allocate ROIs on an image and assign thresholds to determine
atom presence
"""
import sys
import numpy as np
import pyqtgraph as pg
from skimage.filters import threshold_minimum
from collections import OrderedDict
try:
    from PyQt4.QtCore import pyqtSignal
    from PyQt4.QtGui import QFont, QWidget, QLineEdit, QCheckBox, QRect
except ImportError:
    from PyQt5.QtCore import pyqtSignal
    from PyQt5.QtGui import QFont
    from PyQt5.QtCore import QRect
    from PyQt5.QtWidgets import QWidget, QLineEdit, QCheckBox
import logging
logger = logging.getLogger(__name__)
from maingui import int_validator, nat_validator

####    ####    ####    ####

class ROI(QWidget):
    """The properties of a ROI: imshape ((width, height) of image) 
    xc (centre pixel x-coordinate), yc (centre pixel y-coordinate), 
    width (in pixels), height (in pixels), threhsold (for 
    determining atom presence), counts (list of integrated 
    counts within the ROI), ID (number to identify this ROI),
    autothresh (boolean toggle for automatically updating threshold)."""
    def __init__(self, imshape, xc, yc, width, height, threshold=1, 
            counts=[], ID=0, autothresh=True):
        super().__init__()
        self.x = xc
        self.y = yc
        self.w = width
        self.h = height
        self.t = threshold
        self.c = counts
        self.i = ID
        self.label = pg.TextItem('ROI'+str(ID), pg.intColor(ID), anchor=(0,1))
        font = QFont()
        font.setPixelSize(16) 
        self.label.setFont(font)
        self.label.setPos(xc+width//2, yc+height//2) # in bottom left corner
        self.roi = pg.ROI((xc-width//2, yc-height//2), (width,height), 
            movable=True, translateSnap=True, )
        self.roi.setPen(pg.intColor(ID), width=3) # box outlining the ROI
        self.edits = OrderedDict(zip(['x','y','w','h'], # display ROI values
            [QLineEdit(str(val), self) for val in [xc, yc, width, height]]))
        self.threshedit = QLineEdit(str(threshold), self)
        for i, edit in enumerate(list(self.edits.values()) + [self.threshedit]):
            edit.setValidator(int_validator if i < 2 else nat_validator)
            edit.textEdited[str].connect(self.set_vals) # only triggered by user, not setText
        self.autothresh = QCheckBox(self) # toggle whether to auto update threshold
        self.autothresh.setChecked(autothresh)
        self.create_rect_mask(imshape) # the values of the image included in ROI

    def create_rect_mask(self, image_shape=None):
        """Use the current ROI dimensions to create a mask for the image.
        The rect mask is zero outside the ROI and 1 inside the ROI."""
        if np.size(image_shape) == 2:
            self.s = image_shape # store the shape of the image
        self.roi.maxBounds = QRect(0, 0, self.s[0]+1, self.s[1]+1)
        self.mask = np.zeros(self.s)
        if (self.x + self.w//2 < self.s[0] and 
                self.x - self.w//2 >= 0 and 
                self.y + self.h//2 < self.s[1] and 
                self.y - self.h//2 >= 0):
            self.mask[self.x - self.w//2 : (self.x + self.w//2 + self.w%2),
                self.y - self.h//2 : (self.y + self.h//2 + self.h%2)
                ] = np.ones((self.w, self.h))
        else: logger.warning('ROI tried to create invalid mask.\n' + 
            'shape %s, x %s, y %s, w %s, h %s'%(self.s, self.x, self.y, self.w, self.h))

    def resize(self, xc, yc, width, height):
        """Reset the position and dimensions of the ROI"""
        self.x, self.y, self.w, self.h = xc, yc, width, height
        self.roi.setPos(xc - width//2, yc - height//2)
        self.roi.setSize((width, height))
        self.label.setPos(xc, yc)
        for key, val in zip(self.edits.keys(), [xc, yc, width, height]):
            self.edits[key].setText(str(val))
        self.create_rect_mask()

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
            self.t = int(thresh)
        except (ValueError, RuntimeError, OverflowError): 
            try:
                max(self.c) # ValueError if empty list
                self.t = int(np.mean(self.c))
            except (ValueError, TypeError):
                self.t = 1
        self.threshedit.setText(str(self.t))

    def set_vals(self, val=''):
        """Update the ROI from the line edit values."""
        coords = [x.text() for x in self.edits.values()] # xc, yc, width, height
        if all(x for x in coords): # check none are empty
            self.resize(*map(int, coords))
        if self.threshedit and not self.autothresh.isChecked():
            self.t = int(self.threshedit)

####    ####    ####    ####

# convert an image into its pixel counts to check for atoms
class roi_handler:
    """Determine the presence of atoms in ROIs of an image
    
    For each of the ROIs, keep a list of counts to compare to
    threshold to discern if an atom is present.
    Keyword arguments:
    rois     -- list of ROI (xc,yc,wwidth,height)
    im_shape -- dimensions of the image in pixels"""
    trigger = pyqtSignal(int)

    def __init__(self, rois=[(1,1,1,1)], im_shape=(512,512)):
        self.ROIs = [ROI(im_shape,*r, ID=i) for i, r in enumerate(rois)]
        self.shape = im_shape
        self.delim = ' '

    def create_rois(self, n):
        """Change the list of ROIs to have length n"""
        self.ROIs = self.ROIs[:n]
        for i in range(len(self.ROIs), n): # make new ROIs
            self.ROIs.append(ROI(self.shape, 1,1,1,1, ID=i))

    def process(self, im, include=True):
        """Add the integrated counts in each ROI to their lists.
        Return success = 1 if all ROIs have an atom, otherwise 0"""
        success = 1
        for r in self.ROIs:
            try:
                counts = np.sum(im * r.mask)
                success = 1 if abs(counts) // r.t and success else 0
                r.c.append(counts) 
            except ValueError as e:
                logger.error("Image was wrong shape %s for atom checker's ROI%s %s"%(
                    np.shape(im), r.i, r.s) + str(e))
        try:
            1 // (1 - success) # ZeroDivisionError if success = 1
        except ZeroDivisionError: 
            self.trigger.emit(success) # only emit if successful

    def set_pic_size(self, im_name):
        """Set the pic size by looking at the number of columns in a file
        First column is just the index of the row.
        Keyword arguments:
        im_name    -- absolute path to the image file to load"""
        self.shape = np.genfromtxt(im_name, delimiter=self.delim).shape
        try: self.shape = (self.shape[1]-1, self.shape[0])
        except IndexError: self.shape = (1, self.shape[0]-1)
        for r in self.ROIs:
            r.create_rect_mask(self.shape)
        
    def load_full_im(self, im_name):
        """return an array with the values of the pixels in an image.
        Assume that the first column is the column number.
        Keyword arguments:
        im_name    -- absolute path to the image file to load"""
        try: 
            return np.loadtxt(im_name, delimiter=self.delim,
                              usecols=range(1,self.shape[0]+1)).reshape(self.shape)
        except IndexError as e:
            logger.error('Image analysis failed to load image '+im_name+'\n'+str(e))
            return np.zeros(self.shape)