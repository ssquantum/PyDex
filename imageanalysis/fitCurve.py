"""Single Atom Image Analysis
Stefan Spence 37/07/19

class to fit a Poissonian or Gaussian to a given set of data
"""
import numpy as np
from scipy.optimize import curve_fit
from scipy.special import factorial
from scipy.stats import chisquare

class fit:
    """Collection of common functions for theoretical fits.
    
    Since good fitting often depends on a initial estimate, 
    the estGaussParam() function is used estimate parameters 
    for a Gaussian fit. The getBestFit(fn) function applies
    the function fn to (xdat, ydat), updating the best fit
    parameters ps and their errors perrs.
    Keyword arguments:
    xdat  -- independent variable array
    ydat  -- dependent variable array
    erry  -- errors in the dependent variable array
    param -- optional best fit parameter estimate
    func  -- a function used for best fits"""
    fitFuncs = ['offGauss', 'gauss', 'double_gauss', 'poisson', 
                'double_poisson']
    
    def __init__(self, xdat=0, ydat=0, erry=None, param=None, func=None):
        self.x    = xdat   # independent variable
        self.y    = ydat   # measured dependent variable
        self.yerr = erry   # errors in dependent variable
        self.p0   = param  # guess of parameters for fit
        self.ps   = param  # best fit parameters
        self.perrs = None  # error on best fit parameters
        self.bffunc= func  # function used for the best fit
        self.rchisq = None  # reduced chi-squared statistic for the most recent fit

    def estOffGaussParam(self):
        """Guess at the amplitude A, centre x0, width wx, and offset y0 of a 
        Gaussian"""
        A = np.max(self.y) - np.min(self.y)     # peak
        Aind = np.argmax(self.y)                # index of peak
        x0 = self.x[Aind]                       # centre        
        
        # the FWHM is defined where the function drops to half of its max
        try: 
            xm = self.x[Aind + np.where(self.y[Aind:] - np.min(self.y) < A/2.)[0][0]]
        except IndexError:
            xm = self.x[Aind - np.size(self.y[:Aind]) + np.where(self.y[:Aind] - np.min(self.y) < A/2.)[0][-1]]
        e2_width = np.sqrt(2/np.log(2)) * abs(x0 - xm)
        # parameters: [amplitude, centre, standard deviation] #, offset]
        self.p0 = [A, x0, e2_width/2., np.min(self.y)]
        
    def estGaussParam(self):
        self.estOffGaussParam()
        self.p0 = self.p0[:3]
    
    def offGauss(self, x, A, x0, FWHM, y0):
        """Gaussian function centred at x0 with amplitude A, Full width half maximum FWHM
        and background offset y0"""
        sigma=FWHM/(2*np.sqrt(2*np.log(2)))
        return A * np.exp( - (x-x0)**2 /(2*(sigma**2))) + y0

    def gauss(self, x, A, x0, sig):
        """Gaussian function centred at x0 with amplitude A, and standard 
        deviation sig"""
        return A * np.exp( - (x-x0)**2 /sig**2 / 2)
    
    def double_gauss(self, x, N, A, x0, sig0, x1, sig1):
        """Fit 2 Gaussian functions with independent centre x, 
        and standard deviation sig, but amplitudes that are coupled."""
        return N*(1-A)* np.exp(-(x-x0)**2 /2. /sig0**2
               ) + N*A* np.exp(-(x-x1)**2 /2. /sig1**2)
    
    def poisson(self, x, mu, A):
        """Poissononian with mean mu, amplitude A.
        large values of x will cause overflow, so use gaussian instead"""
        result = A * np.power(mu,x) * np.exp(-mu) / factorial(x)
        if np.size(result) > 1:
            nans = np.argwhere(np.logical_or(np.isnan(result), np.isinf(result)))
            result[nans] = A * np.exp(-(x[nans]-mu)**2 / (2*mu)) / np.sqrt(2*np.pi*mu)
        elif np.logical_or(np.isnan(result), np.isinf(result)):
            result = A * np.exp(-(x[nans]-mu)**2 / (2*mu)) / np.sqrt(2*np.pi*mu)
        return result
    
    def double_poisson(self, x, mu0, A0, mu1, A1):
        """The sum of two Poissonians with means mu0, mu1, and 
        amplitudes A0, A1."""
        return self.poisson(x, mu0, A0) + self.poisson(x, mu1, A1)
    
    def getBestFit(self, fn=None, **kwargs):
        """Use scipy.optimize.curve_fit to get the best fit to the supplied 
        data using the supplied function fn. Bounds and other keyword 
        arguments can be passed through.
        Returns tuple of best fit parameters and their errors"""
        if fn:
            self.bffunc = fn # store the function that was used to fit with
        else: fn = self.bffunc
        popt, pcov = curve_fit(fn, self.x, self.y, p0=self.p0, sigma=self.yerr,
                                maxfev=80000, **kwargs)
        self.ps = popt
        self.perrs = np.sqrt(np.diag(pcov))
        self.rchisq = chisquare(self.y, fn(self.x, *self.ps))[0] / (np.size(self.y) - np.size(self.ps))