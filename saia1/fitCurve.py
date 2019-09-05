"""Single Atom Image Analysis
Stefan Spence 37/07/19

class to fit a Poissonian or Gaussian to a given set of data
"""
import numpy as np
from scipy.optimize import curve_fit
from scipy.special import factorial

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
    param -- optional best fit parameter estimate"""
    def __init__(self, xdat=0, ydat=0, erry=None, param=None):
        self.x    = xdat   # independent variable
        self.y    = ydat   # measured dependent variable
        self.yerr = erry   # errors in dependent variable
        self.p0   = param  # guess of parameters for fit
        self.ps   = param  # best fit parameters
        self.perrs = None  # error on best fit parameters

    def estGaussParam(self):
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
        self.p0 = [A, x0, e2_width/2.] #, np.min(self.y)]
    
    def offGauss(self, x, A, x0, wx, y0):
        """Gaussian function centred at x0 with amplitude A, 1/e^2 width wx
        and background offset y0"""
        return A * np.exp( -2 * (x-x0)**2 /wx**2) + y0

    def gauss(self, x, A, x0, sig):
        """Gaussian function centred at x0 with amplitude A, and standard deviation sig"""
        return A * np.exp( - (x-x0)**2 /sig**2 / 2)
    
    def poisson(self, x, mu, A):
        """Poisson distribution with mean mu, amplitude A"""
        return A * np.power(mu,x) * np.exp(-mu) / factorial(x)
    
    def getBestFit(self, fn):
        """Use scipy.optimize.curve_fit to get the best fit to the supplied data
        using the supplied function fn
        Returns tuple of best fit parameters and their errors"""
        popt, pcov = curve_fit(fn, self.x, self.y, p0=self.p0, sigma=self.yerr,
                                maxfev=80000)
        self.ps = popt
        self.perrs = np.sqrt(np.diag(pcov))
    