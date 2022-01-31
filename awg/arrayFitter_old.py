# -*- coding: utf-8 -*-
"""
Created on Mon Jan 24 14:48:38 2022

@author: DPH0ZZ67
"""

from PIL import Image
import numpy as np
import pyqtgraph as pg
import sys
if '.' not in sys.path: sys.path.append('.')
if '..' not in sys.path: sys.path.append('..')
from strtypes import error, warning, info
from imageanalysis.fitCurve import fit
from scipy.optimize import minimize


##### helper functions #####
def _transform(M):
    """Rotate loaded image so it displays with original coordinate frame"""
    return np.flipud(M).T

def _inverse(M):
    """Rotate array so that is displays with same dimensions as the image"""
    return np.flipud(M.T)

#####   ######  ######

class imageArray:
    """Fit Gaussians to an array of spots in an image"""
    _labels = ['xc', 'w', 'yc', 'h', 'Amplitude']
    
    def __init__(self, dims=(3,3), roi_size=40, pixelconv=3.6e-6):
        self._n = dims[0]*dims[1]  # number of spots to fit
        self._s = dims             # rows, cols of trap array 
        self._imvals = np.zeros((512,512))
        self._d = roi_size   # crop the image down to 2d x 2d pixels
        self.rois = [(1,1,1,1,1) for i in range(self._n)] # xc, w, yc, h, A
        
    def loadImage(self, filename):
        self._imvals = np.array(Image.open(filename), dtype=float)[:,:,0]
        return self._imvals.copy()
    
    def fitImage(self, filename=''):
        """Loop over spots in images and fit Gaussians"""
        if filename:
            im = self.loadImage(filename)
        else: 
            im = self._imvals.copy()
        
        if np.size(np.shape(im)) == 2:
            for i in range(self._n):
                xc, yc = np.unravel_index(np.argmax(im), im.shape)
                l0 = xc - self._d if xc-self._d>0 else 0 # don't overshoot boundary
                l1 = yc - self._d if yc-self._d>0 else 0
                im2 = im[l0:xc+self._d, l1:yc+self._d] # better for fitting to use zoom in
                self.rois[i] = self.fitGauss(im2, xc, yc) # fit 2D Gaussian to max pixel region 
                try: # then block that region out of the image
                    im[l0:xc+self._d, l1:yc+self._d] = np.zeros(np.shape(im2)) + np.min(im)
                except (IndexError, ValueError): pass
                
    def fitGauss(self, im, x0, y0):
        """Fit x and y Gaussians to a cropped image. Return xc, w, yc, h, A.
        |r| is distance from the origin in bottom-left corner."""
        ps = []
        for i in range(2): # do Gaussian fit along each axis
            vals = np.sum(im, axis=i)
            f = fit(np.arange(len(vals)), vals)
            f.estGaussParam()
            f.p0 = f.p0[:2] + [f.p0[2]*2, np.min(vals)]
            f.getBestFit(f.offGauss) 
            ps += [f.ps[1]+x0 if i else f.ps[1]+y0, abs(f.ps[2])] # centre, width
        return (*ps, f.ps[0])
            
    def plotContours(self, widget):
        """Plot the stored image and outline of the fitted ROIs onto the widget"""
        viewbox = widget.addViewBox()
        viewbox.addItem(pg.ImageItem(_transform(self._imvals)))
        for i, (xc, w, yc, h, A) in enumerate(self.rois): # note: image coordinates inverted
            e = pg.EllipseROI((xc-w-self._d, self._imvals.shape[0]-yc-h+self._d), (2*w, 2*h),  # origin is bottom-left
                    movable=False, rotatable=False, resizable=False, pen=pg.intColor(i, self._n))
            viewbox.addItem(e)
            s = pg.ROI((xc-2*self._d, self._imvals.shape[0]-yc), (2*self._d, 2*self._d),  # origin is bottom-left
                    movable=False, rotatable=False, resizable=False, pen='w')
            viewbox.addItem(s)
            for h in e.getHandles():
                e.removeHandle(h)
                
    def getScaleFactors(self, verbose=0):
        """Sort the ROIs and return an array of suggested scale factors to 
        make the intensities uniform."""
        # sort ROIs by x coordinate        
        self.rois = np.array(sorted(self.rois, key=lambda p: p[0]))
        lx, ly = self._s
        for i in range(ly): # sort columns by y coordinate
            self.rois[i*lx:(i+1)*lx,:] = np.array(sorted(self.rois[i*lx:(i+1)*lx,:], key=lambda p: p[2]))
        # make array of desired scale factors
        target = np.array([i[-1] for i in self.rois]).reshape(self._s)
        target = np.min(target) / target # normalise and invert
        def func(xy):
            return np.linalg.norm(np.outer(xy[:lx], xy[lx:]) - target)
        result = minimize(func, np.ones(lx + ly))
        if verbose:
            info('Array scale factors ' + result.message + '\n' + 'Cost: %s'%result.fun)
        if verbose > 1: 
            info('Target:\n' + str(target.T) + '\nResult:\n' + str(
                np.outer(result.x[lx:], result.x[:lx])))
        return (result.x[lx:], result.x[:lx]) # note: taking transform
        