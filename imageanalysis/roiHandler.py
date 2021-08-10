"""Single Atom Image Analysis
Stefan Spence 13/04/20

Allocate ROIs on an image and assign thresholds to determine
atom presence
"""
import sys
import time
import numpy as np
import pyqtgraph as pg
from skimage.filters import threshold_minimum
from collections import OrderedDict
from PyQt5.QtCore import pyqtSignal
from PyQt5.QtGui import QFont
from PyQt5.QtCore import QRect
from PyQt5.QtWidgets import QWidget, QLineEdit, QCheckBox
if '.' not in sys.path: sys.path.append('.')
if '..' not in sys.path: sys.path.append('..')
from strtypes import error, warning, info
from maingui import int_validator, nat_validator
from fitCurve import fit

####    ####    ####    ####

class ROI(QWidget):
    """The properties of a ROI: imshape ((width, height) of image) 
    xc (centre pixel x-coordinate), yc (centre pixel y-coordinate), 
    width (in pixels), height (in pixels), threhsold (for 
    determining atom presence), counts (array of integrated 
    counts within the ROI), ID (number to identify this ROI),
    autothresh (boolean toggle for automatically updating threshold)."""
    def __init__(self, imshape, xc, yc, width, height, threshold=1, 
            counts=1000, ID=0, autothresh=False):
        super().__init__()
        self.x = xc
        self.y = yc
        self.w = width
        self.h = height
        self.t = threshold
        self.c = np.zeros(counts)
        self.i = 0 # number of images processed
        self.id = ID
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
        self.mask_type = 'rect' # what type of mask is being used
        self.ps = np.zeros(4) # parameters for gauss mask
        self.d = 3 # number of pixels around centre point to use for gauss mask

    def create_rect_mask(self, image_shape=None):
        """Use the current ROI dimensions to create a mask for the image.
        The rect mask is zero outside the ROI and 1 inside the ROI."""
        if np.size(image_shape) == 2:
            self.s = image_shape # store the shape of the image
        if (self.x + self.w//2 < self.s[0] and 
                self.x - self.w//2 >= 0 and 
                self.y + self.h//2 < self.s[1] and 
                self.y - self.h//2 >= 0):
            self.roi.maxBounds = QRect(0, 0, self.s[0]+1, self.s[1]+1)
            self.mask = np.zeros(self.s)
            self.mask[self.x - self.w//2 : (self.x + self.w//2 + self.w%2),
                self.y - self.h//2 : (self.y + self.h//2 + self.h%2)
                ] = np.ones((self.w, self.h))
            self.mask_type = 'rect'
        else: warning('ROI tried to create invalid mask.\n' + 
            'shape %s, x %s, y %s, w %s, h %s'%(self.s, self.x, self.y, self.w, self.h))

    def create_gauss_mask(self, im=0):
        """Fit a 2D Gaussian to the given image and use it to create a mask.
        The Gaussian is fitted around the maximum intensity pixel."""
        try:
            if np.size(np.shape(im)) == 2:
                self.s = np.shape(im)
                self.mask = np.zeros(np.shape(im))
                xc, yc = np.unravel_index(np.argmax(im), im.shape)
                if self.autothresh:
                    self.t = int(0.5*(np.max(im) + np.min(im))) # threshold in middle of histogram
                    self.threshedit.setText(str(self.t))
                d = self.d # = round(np.size(im[im > self.t])**0.5) # guess PSF size from pixels > threshold
                l0 = xc - d if xc-d>0 else 0
                l1 = yc - d if yc-d>0 else 0
                im2 = im[l0:xc+d, l1:yc+d] # better for fitting to use zoom in
                self.ps = np.zeros(4)
                for i in range(2): # do Gaussian fit along each axis
                    vals = np.sum(im2, axis=i)
                    f = fit(np.arange(len(vals)), vals)
                    f.estGaussParam()
                    f.p0 = f.p0[:2] + [f.p0[2]*2, np.min(vals)]
                    f.getBestFit(f.offGauss) # only interested in the width
                    self.ps[2*i], self.ps[2*i+1] = f.ps[1], abs(f.ps[2]) # centre, width
                xy = np.meshgrid(range(d+xc-l0), range(d+yc-l1))
                self.mask[l0:xc+d, l1:yc+d] = np.exp( # fill in 2D Gaussian
                    -2*(xy[0]-self.ps[0])**2 / self.ps[1]**2 -2*(xy[1]-self.ps[2])**2 / self.ps[3]**2) 
                self.mask /= np.sum(self.mask) # normalise (we care about integrated counts)
                y, h, x, w = map(int, map(round, self.ps)) # ROI coordinates must be int
                self.mask_type = 'gauss'
                if not np.isfinite(self.mask).all(): # need mask to have only finite values
                    self.resize(l0+x, l1+y, 1, 1, True) # update stored ROI values and make square mask
                else: self.resize(l0+x, l1+y, w, h, False) # update stored ROI values
        except Exception as e: error('ROI %s failed to set Gaussian mask\n'%self.id+str(e))
        
    def translate_mask(self, xc, yc):
        """Take the new positions as the centre of the ROI and recreate the mask."""
        self.x, self.y = xc, yc
        if self.mask_type == 'rect':
            self.create_rect_mask()
        elif self.mask_type == 'gauss':
            l0 = xc - self.d if xc-self.d>0 else 0
            l1 = yc - self.d if yc-self.d>0 else 0
            xy = np.meshgrid(range(l0, self.d+xc), range(l1, self.d+yc))
            try:
                self.mask = np.zeros(self.s)
                self.mask[l0:xc+self.d, l1:yc+self.d] = np.exp( # fill in 2D Gaussian
                        -2*(xy[0]-xc)**2 / self.ps[1]**2 -2*(xy[1]-yc)**2 / self.ps[3]**2) 
                self.mask /= np.sum(self.mask) # normalise (we care about integrated counts)
            except Exception as e: error('ROI %s failed to set Gaussian mask\n'%self.id+str(e))
        
    
    def resize(self, xc, yc, width, height, create_sq_mask=True):
        """Reset the position and dimensions of the ROI"""
        self.x, self.y, self.w, self.h = xc, yc, width, height
        self.roi.setPos(xc - width//2, yc - height//2)
        self.roi.setSize((width, height))
        self.label.setPos(xc, yc)
        for key, val in zip(self.edits.keys(), [xc, yc, width, height]):
            self.edits[key].setText(str(val))
        if create_sq_mask: self.create_rect_mask()

    def atom(self):
        """A list of whether the counts are above threshold"""
        return [x // self.t for x in self.c[:self.i]]

    def LP(self):
        """Calculate the loading probability from images above threshold"""
        return np.size(self.c[self.c > self.t]) / np.size(self.c[:self.i]) if self.i>0 else 0

    def thresh(self):
        """Automatically choose a threshold based on the counts"""
        try: 
            thresh = threshold_minimum(np.array(self.c[:self.i]), 25)
            int(np.log(thresh)) # ValueError if thresh <= 0 
            self.t = int(thresh)
        except (ValueError, RuntimeError, OverflowError): 
            try:
                self.t = int(0.5*(max(self.c) + min(self.c[:self.i])))
                int(np.log(self.t)) # ValueError if thresh <= 0 
            except (ValueError, TypeError, OverflowError):
                self.t = 1
        self.threshedit.setText(str(self.t))

    def set_vals(self, val=''):
        """Update the ROI from the line edit values."""
        coords = [x.text() for x in self.edits.values()] # xc, yc, width, height
        if all(x for x in coords): # check none are empty
            self.resize(*map(int, coords))
        if self.threshedit.text() and not self.autothresh.isChecked():
            self.t = int(self.threshedit.text())

####    ####    ####    ####

# convert an image into its pixel counts to check for atoms
class roi_handler(QWidget):
    """Determine the presence of atoms in ROIs of an image
    
    For each of the ROIs, keep a list of counts to compare to
    threshold to discern if an atom is present.
    Keyword arguments:
    rois     -- list of ROI (xc,yc,wwidth,height)
    im_shape -- dimensions of the image in pixels"""
    trigger = pyqtSignal(int)
    rearrange = pyqtSignal(str)

    def __init__(self, rois=[(1,1,1,1,1)], im_shape=(512,512)):
        super().__init__()
        self.ROIs = [ROI(im_shape,*r, ID=i) for i, r in enumerate(rois)]
        self.shape = im_shape # image dimensions in pixels
        self.bias  = 697      # bias offset to subtract from image counts
        self.delim = ' '      # delimiter used to save/load files
        
    def create_rois(self, n):
        """Change the list of ROIs to have length n"""
        self.ROIs = self.ROIs[:n]
        for i in range(len(self.ROIs), n): # make new ROIs
            self.ROIs.append(ROI(self.shape, 1,1,1,1, ID=i))

    def resize_rois(self, ROIlist):
        """Convenience function for setting multiple ROIs"""
        for i, roi in enumerate(ROIlist):
            try: 
                self.ROIs[i].resize(*roi[:-1])
                self.ROIs[i].t = roi[-1]
                self.ROIs[i].threshedit.setText(str(roi[-1]))
            except (IndexError, ValueError) as e: warning(
                "Failed to resize ROI "+str(i)+": %s\n"%roi + str(e))

    def reset_count_lists(self, ids=[]):
        """Empty the lists of counts in the ROIs with the gives IDs"""
        for i in ids:
            try: 
                self.ROIs[i].c = np.zeros(1000)
                self.ROIs[i].i = 0
            except IndexError: pass

    def process(self, im, include=True):
        """Add the integrated counts in each ROI to their lists.
        emit success = 1 if all ROIs have an atom
        emit a string of which ROIs are occupied, e.g. '0110'"""
        success = 1
        atomstring = ''
        for r in self.ROIs:
            try:
                counts = np.sum(im * r.mask) - self.bias * r.w * r.h
                success = 1 if abs(counts) // r.t and success else 0
                atomstring += str(int(abs(counts) > r.t))
                r.c[r.i%1000] = counts
                r.i += 1
            except ValueError as e:
                error("Image was wrong shape %s for atom checker's ROI%s %s"%(
                    np.shape(im), r.id, r.s) + str(e))
        try:
            1 // (1 - success) # ZeroDivisionError if success = 1
        except ZeroDivisionError: 
            self.trigger.emit(success) # only emit if successful
        self.rearrange.emit(atomstring)
        
    def set_pic_size(self, im_name):
        """Set the pic size by looking at the number of columns in a file
        First column is just the index of the row.
        Keyword arguments:
        im_name    -- absolute path to the image file to load"""
        shape = np.genfromtxt(im_name, delimiter=self.delim).shape
        try: self.cam_pic_size_changed(shape[1]-1, shape[0])
        except IndexError: self.cam_pic_size_changed(shape[0]-1, 1)

    def set_bias(self, bias):
        """Update the bias offset subtracted from all image counts."""
        self.bias = bias
        
    def cam_pic_size_changed(self, width, height):
        """Receive new image dimensions from Andor camera"""
        if self.shape != (width, height):
            self.shape = (width, height)
        for r in self.ROIs:
            if r.s != self.shape:
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
            error('Image analysis failed to load image '+im_name+'\n'+str(e))
            return np.zeros(self.shape)
