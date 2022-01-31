# -*- coding: utf-8 -*-
"""
Created on Mon Jan 24 14:48:38 2022

@author: DPH0ZZ67
"""

from PIL import Image
import numpy as np
import pyqtgraph as pg
import pandas as pd
import sys
if '.' not in sys.path: sys.path.append('.')
if '..' not in sys.path: sys.path.append('..')
from strtypes import error, warning, info
from imageanalysis.fitCurve import fit
from scipy.optimize import minimize, curve_fit

##### helper functions #####
def _transform(M):
    """Rotate loaded image so it displays with original coordinate frame"""
    return np.flipud(M).T

def _inverse(M):
    """Rotate array so that is displays with same dimensions as the image"""
    return np.flipud(M.T)
    
##### Gaussian functions #####

def gauss2D(xy_tuple,yc,w,xc,h,I0,theta):
    (x,y) = xy_tuple
    a = (np.cos(theta)**2)/(2*w**2) + (np.sin(theta)**2)/(2*h**2)
    b = -(np.sin(2*theta))/(4*w**2) + (np.sin(2*theta))/(4*h**2)
    c = (np.sin(theta)**2)/(2*w**2) + (np.cos(theta)**2)/(2*h**2)
    g = I0*np.exp( - (a*((x-xc)**2) + 2*b*(x-xc)*(y-yc) + c*((y-yc)**2)))
    return g.ravel()

def gauss(x, A, x0, sig, y0):
    return A * np.exp( - (x-x0)**2 /sig**2 / 2) + y0

#####   ######  ######

class imageArray:
    """Fit Gaussians to an array of spots in an image"""
    
    def __init__(self, dims=(3,3), roi_size=40, pixelconv=3.6e-6, fitmode='sum'):
        self._n = dims[0]*dims[1]  # number of spots to fit
        self._s = dims             # rows, cols of trap array 
        self._imvals = np.zeros((512,512))
        self._d = roi_size   # crop the image down to 2d x 2d pixels
        if fitmode == 'gauss2d':
            self._labels = list(gauss2D.__code__.co_varnames[1:7])
            self.fitfunc = self.fitGauss2D
        else:
            self._labels = ['xc', 'w', 'yc', 'h', 'I0']
            if fitmode == 'gauss':
                self.fitfunc = self.fitGaussAmp
            else: self.fitfunc = self.fitGaussSum
        self._labels += [x+'_err' for x in self._labels] 
        self.df = pd.DataFrame(columns=self._labels) # xc, w, yc, h, I for each ROI
        
    def loadImage(self, filename, imshape=(1024,1280)):
        if 'bmp' in filename:
            self._imvals = np.array(Image.open(filename), dtype=float)[:,:,0]
        elif 'png' in filename:
            self._imvals = np.array(Image.open(filename).getdata()).reshape(imshape)
        return self._imvals.copy()
    
    def fitImage(self, filename=''):
        """Loop over spots in images and fit Gaussians"""
        if filename:
            im = self.loadImage(filename)
        else: 
            im = self._imvals.copy()
            
        self.df = pd.DataFrame(columns=self._labels) # reset dataframe 
        
        if np.size(np.shape(im)) == 2:
            for i in range(self._n):
                yc, xc = np.unravel_index(np.argmax(im), im.shape)
                l0 = xc - self._d if xc-self._d>0 else 0 # don't overshoot boundary
                l1 = yc - self._d if yc-self._d>0 else 0
                im2 = im[l1:yc+self._d, l0:xc+self._d] # better for fitting to use zoom in
                self.df = self.df.append(self.fitfunc(im2, xc, yc), ignore_index=True) # fit
                try: # then block that region out of the image
                    im[l1:yc+self._d, l0:xc+self._d] = np.zeros(np.shape(im2)) + np.min(im)
                except (IndexError, ValueError): pass

        # sort ROIs by x coordinate        
        lx, ly = self._s
        self.df = self.df.sort_values('xc')
        for i in range(ly): # sort columns by y coordinate
            self.df.iloc[i*lx:(i+1)*lx] = self.df.iloc[i*lx:(i+1)*lx].sort_values('yc')
        
                
    def fitGaussAmp(self, im, x0, y0):
        """Fit x and y Gaussians to a cropped image. Return xc,w,yc,h,I0 with errors"""
        ps = []
        perrs = []
        I, Ierr = 0, 0
        for i, c in enumerate([x0, y0]): # do Gaussian fit along each axis
            vals = np.sum(im, axis=i)
            d = len(vals)
            popt, pcov = curve_fit(gauss, np.arange(-d/2, d/2)+c, vals, 
                p0=[np.max(vals), c, d/8, np.min(vals)])
            perr = np.sqrt(np.diag(pcov))
            ps += [popt[1], abs(popt[2])]
            perrs += [perr[1], perr[2]]
            I += popt[0] + popt[-1]
            Ierr = perr[0]**2 + perr[-1]**2
        outarr = np.array([*ps, I/2, *perrs, np.sqrt(Ierr)/2])
        return pd.DataFrame(outarr.reshape(1,len(outarr)), columns=self._labels)
        
        
    def fitGaussSum(self, im, x0, y0):
        """Fit x and y Gaussians to a cropped image. Use the sum of the image as I0"""
        df = self.fitGaussAmp(im, x0, y0)
        df['I0'] = np.sum(im)
        return df
            
    def fitGauss2D(self, im, x0, y0):
        """Fit a 2D Gaussian to cropped image. Return xc,w,yc,h,I0,theta with errors"""
        dx, dy = np.shape(im)
        x,y = np.meshgrid(np.arange(-dx/2,dx/2)+x0, np.arange(-dy/2,dy/2)+y0)
        popt, pcov = curve_fit(gauss2D, (x,y), im.ravel(), p0=[y0,dy/4,x0,dx/4,np.max(im),0])
        perr = np.sqrt(np.diag(pcov)) 
        outarr = np.concatenate((popt,perr))
        return pd.DataFrame(outarr.reshape(1,len(outarr)), columns=self._labels)
            
    def plotContours(self, widget):
        """Plot the stored image and outline of the fitted ROIs onto the widget"""
        viewbox = widget.addViewBox()
        viewbox.addItem(pg.ImageItem(_transform(self._imvals)))
        for i, df in self.df.iterrows(): # note: image coordinates inverted
            e = pg.EllipseROI((df['xc']-self._d*0.5, self._imvals.shape[0]-df['yc']-self._d*0.25), (2*df['w'], 2*df['h']),  # origin is bottom-left
                    movable=False, rotatable=False, resizable=False, pen=pg.intColor(i, self._n))
            viewbox.addItem(e)
            for h in e.getHandles():
                e.removeHandle(h)
            s = pg.ROI((df['xc']-self._d, self._imvals.shape[0]-df['yc']-self._d), (2*self._d, 2*self._d),  # origin is bottom-left
                    movable=False, rotatable=False, resizable=False, pen='w')
            viewbox.addItem(s)
                
    def getScaleFactors(self, verbose=0):
        """Sort the ROIs and return an array of suggested scale factors to 
        make the intensities uniform."""
        lx, ly = self._s
        # make array of desired scale factors
        target = self.df['I0'].values.reshape(self._s)
        target = np.min(target) / target # normalise and invert
        def func(xy):
            return np.linalg.norm(np.outer(xy[:lx], xy[lx:]) - target)
        p0 = np.ones(lx + ly)
        result = minimize(func, p0, bounds=(p0*0,p0))
        if verbose:
            info('Array scale factors ' + result.message + '\n' + 'Cost: %s'%result.fun)
        if verbose > 1: 
            info('Target:\n' + str(target.T) + '\nResult:\n' + str(
                np.outer(result.x[lx:], result.x[:lx])))
        return (result.x[lx:], result.x[:lx]) # note: taking transform
        