"""Stefan Spence 25.09.20
Plot a DAQ monitor measurement with time stamps
"""
import os
import sys
import time
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.dates as dates

purple = '#68246D'
yellow = '#FFD53A'
cyan   = '#00AEEF'
red    = '#BE1E2D'

measure_folder = r'Z:\Tweezer\Experimental Results\2020\November\17'

data = np.loadtxt(os.path.join(measure_folder, '3-4OPpower.csv'), delimiter=',')

plt.figure()
plt.plot(dates.num2date(data[:,-1]/3600/24), data[:,1]*1e3, '.', color=purple)
plt.ylabel('Repump Monitor Signal (mV)', color=purple)

# plot temperature
Tdata = np.loadtxt(r'Z:\Tweezer\Experimental Results\2020\November\17\Laser  Table Temperature-data-2020-11-18 09_10_55.csv', delimiter=',',skiprows=1)
ax = plt.gca().twinx()
i0 = np.argmin(abs(Tdata[:,0]/1e3-min(data[:,-1])))
i1 = np.argmin(abs(Tdata[:,0]/1e3-max(data[:,-1])))
ax.plot(dates.num2date(Tdata[i0:i1+1, 0]/1e3/3600/24), Tdata[i0:i1+1,1], color=red, alpha=0.7)
ax.set_ylabel('Temperature ($^\circ$)', color=red)
plt.gca().xaxis.set_major_formatter(dates.DateFormatter("%d - %H:%M"))
plt.gcf().autofmt_xdate()
plt.tight_layout()
plt.show()