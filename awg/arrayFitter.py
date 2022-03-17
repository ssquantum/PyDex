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
from itertools import combinations

##### helper functions #####
def _transform(M):
    """Rotate loaded image so it displays with original coordinate frame"""
    return np.rot90(M,-1)

def _inverse(M):
    """Rotate array so that is displays with same dimensions as the image"""
    return np.rot90(M, 1)
    
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
    """Fit Gaussians to an array of spots in an image
    x = horizontal = axis 1, y = vertical = axis 0"""
    
    def __init__(self, dims=(3,3), roi_size=40, pixelconv=3.6e-6, fitmode='sum'):
        self._n = dims[0]*dims[1]  # number of spots to fit
        self._s = dims             # cols, rows of trap array 
        self._imvals = np.zeros((512,512))
        self._dx = roi_size   # crop the image down to 2d x 2d pixels
        self._dy = roi_size   # crop the image down to 2d x 2d pixels
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
        self.ref = 1  # reference intensity
        
    def check_outlier(self, key='w'):
        """See if a value is an outlier based on the interquartile range from median"""
        return np.array(self.df[key].std() / self.df[key].mean() > 0.3).any()
        
    def autoROISize(self, filename='', imshape=(1024,1280), widget=None):
        """Choose ROI size automatically by fitting a Gaussian in an image."""
        self.fitImage(filename, imshape=imshape)
        for i in reversed(range(5)): # bad ROI size, try another
            if (self.df.isin([np.inf,-np.inf]).values.any() or self.df.isnull().values.any()
                    or self.check_outlier('w') or self.check_outlier('h')):
                self._dx = int((i+1)**2 * 5)
                self._dy = int((i+1)**2 * 5)
                try:
                    self.fitImage()
                except: pass
            else: break
        # check if ROIs overlap
        overx, overy = 0, 0
        xmins = np.array(sorted(self.df['xc'] - self._dx))
        xmaxs = np.array(sorted(self.df['xc'] + self._dx))
        ymins = np.array(sorted(self.df['yc'] - self._dy))
        ymaxs = np.array(sorted(self.df['yc'] + self._dy))
        # if any boxes are outside camera ROI
        if len(xmins[xmins < 0]):
            overx = np.abs(np.min(xmins[xmins<0]))
        if len(ymins[ymins < 0]):
            overy = np.abs(np.min(ymins[ymins<0]))
        if len(xmaxs[xmaxs > imshape[1]]):
            overx = max(overx, np.max(xmaxs[xmaxs > imshape[1]]) - imshape[1])
        if len(ymaxs[ymaxs > imshape[0]]):
            overy = max(overy, np.max(ymaxs[ymaxs > imshape[0]]) - imshape[0])
        # look at first row, compare first and second column
        if self._s[0] > 1:
            ox = (xmins[1] - xmaxs[0])/2.
            if ox < 0:
                overx = max(overx, np.abs(ox))
        # look at first column, compare first and second row
        if self._s[1] > 1:
            oy = (ymins[1] - ymaxs[0])/2.
            if oy < 0:
                overy = max(overy, np.abs(oy))
        # set new width, height of ROI        
        self._dx -= int(round(overx))
        self._dy -= int(round(overy))
        self.fitImage()
        info("imageArray fitter reset ROI width, height to %s, %s"%(self._dy, self._dx))
        xmins, xmaxs = self.df['xc'] - self._dx, self.df['xc'] + self._dx
        ymins, ymaxs = self.df['yc'] - self._dy, self.df['yc'] + self._dy
        # image could be cropped to: [xmin,ymin,xmax,ymax]
        bounds = list(map(int, [np.floor(min(xmins)), np.floor(min(ymins)), 
                    np.ceil(max(xmaxs)), np.ceil(max(ymaxs))]))
        # plot the bounds
        if widget:
            viewbox = self.plotContours(widget)
            s = pg.ROI((min(xmins), self._imvals.shape[0]-max(ymaxs)),   # origin is bottom-left
                    (max(xmaxs) - min(xmins), max(ymaxs) - min(ymins)),
                    movable=False, pen='w') # rotatable=False, resizable=False, 
            viewbox.addItem(s)
        return bounds
        
    def setRef(self, imarr):
        """Use an image to define the reference intensity as the mean of fitted 
        intensities in the image."""
        self._imvals = imarr
        self.fitImage()
        self.ref = self.df['I0'].mean()
        
    def setTarget(self, amps):
        """Use the fraction amplitudes between 0-1 to scale the reference intensity"""
        self.ref = self.ref * np.array(amps).reshape(self._s)
        
    def loadImage(self, filename, imshape=(1024,1280)):
        if 'bmp' in filename:
            self._imvals = np.array(Image.open(filename), dtype=float)[:,:,0]
        elif 'png' in filename:
            self._imvals = np.array(Image.open(filename).getdata()).reshape(imshape)
        return self._imvals.copy()
    
    def fitImage(self, filename='', imshape=(1024,1280)):
        """Loop over spots in images and fit Gaussians"""
        if filename:
            im = self.loadImage(filename, imshape=imshape)
        else: 
            im = self._imvals.copy()
            
        self.df = pd.DataFrame(columns=self._labels) # reset dataframe 
        
        if np.size(np.shape(im)) == 2:
            for i in range(self._n):
                yc, xc = np.unravel_index(np.argmax(im), im.shape)
                l0 = xc - self._dx if xc-self._dx>0 else 0 # don't overshoot boundary
                l1 = yc - self._dy if yc-self._dy>0 else 0
                im2 = im[l1:yc+self._dy, l0:xc+self._dx] # better for fitting to use zoom in
                self.df = self.df.append(self.fitfunc(im2, xc, yc), ignore_index=True) # fit
                try: # then block that region out of the image
                    im[l1:yc+self._dy, l0:xc+self._dx] = np.zeros(np.shape(im2)) + np.min(im)
                except (IndexError, ValueError): pass

        # sort ROIs by x coordinate        
        lx, ly = self._s
        self.df = self.df.sort_values('xc')
        if lx == 1: # one column, sort by y
            self.df = self.df.sort_values('yc')
        else:
            for i in range(lx): # sort columns by y coordinate
                self.df.iloc[i*ly:(i+1)*ly] = self.df.iloc[i*ly:(i+1)*ly].sort_values('yc')
        
                
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
            ps += [popt[1], abs(popt[2])*2]
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
        im = np.zeros(self._imvals.shape)
        dy, dx = im.shape
        for i, df in self.df.iterrows(): # note: image coordinates inverted
            x, y = np.meshgrid(np.arange(dx)*2 - df['xc'], 
                                np.arange(dy)*2 - df['yc'])
            im += gauss2D((x,y),df['yc'],df['w'],df['xc'],df['h'],1,0).reshape(dy, dx)
            e = pg.EllipseROI((df['xc']-df['h'], dy-df['yc']-df['w']), (2*df['h'], 2*df['w']),  # origin is bottom-left
                    movable=False, pen=pg.intColor(i, self._n))
            viewbox.addItem(e)
            for h in e.getHandles():
                e.removeHandle(h)
        viewbox.addItem(pg.ImageItem(_transform(im)))
        viewbox.addItem(pg.TextItem('Fit'))
        viewbox = widget.addViewBox()
        viewbox.addItem(pg.ImageItem(_transform(self._imvals)))
        viewbox.addItem(pg.TextItem('Image'))
        for i, df in self.df.iterrows(): # note: image coordinates inverted
            e = pg.EllipseROI((df['xc']-df['h'], dy-df['yc']-df['w']), (2*df['h'], 2*df['w']),  # origin is bottom-left
                    movable=False, pen=pg.intColor(i, self._n))
            viewbox.addItem(e)
            for h in e.getHandles():
                e.removeHandle(h)
            s = pg.ROI((df['xc']-self._dx, dy-df['yc']-self._dy), (self._dx*2, self._dy*2),  # origin is bottom-left
                    movable=False, pen=pg.intColor(i, self._n)) # rotatable=False, resizable=False, 
            viewbox.addItem(s)
        # size = widget.geometry()
        # size.setCoords(50,50,1200,int(1200*dy/dx))
        # widget.setGeometry(size)
        return viewbox
                
    def getScaleFactors(self, verbose=0):
        """Sort the ROIs and return an array of suggested scale factors to 
        make the intensities uniform."""
        lx, ly = self._s
        I0s = self.df['I0'].values.reshape(self._s)
        if np.shape(self.ref):
            self.ref = self.ref.reshape(self._s)
        # make array of desired scale factors
        target = self.ref / I0s
        def func(xy):
            return np.linalg.norm(np.outer(xy[:lx], xy[lx:]) - target)
        p0 = np.ones(lx + ly)
        result = minimize(func, p0, bounds=[[0,10]]*(lx+ly))
        if verbose:
            info('Array scale factors ' + result.message + '\n' + 'Cost: %s'%result.fun)
        if verbose > 1: 
            info("Intensities:\n"+str(I0s/self.ref))
            info('Target:\n' + str(target.T) + '\nResult:\n' + str(
                np.outer(result.x[lx:], result.x[:lx])))
        return (result.x[lx:], result.x[:lx]) # note: taking transform
        