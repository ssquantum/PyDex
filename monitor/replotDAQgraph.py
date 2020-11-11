"""Stefan Spence 25.09.20
Plot a DAQ monitor measurement with time stamps
"""
import os
import sys
import time
import numpy as np
import matplotlib.pyplot as plt

measure_folder = r'Z:\Tweezer\Experimental Results\2020\November\10\Measure11'

data = np.loadtxt(os.path.join(measure_folder, 'DAQgraph.csv'), delimiter=',')

plt.figure()
plt.plot(data[:,0], data[:,2]*1e3, '.')
l = len(data[:,0])
plt.xticks(*np.array([[data[i,0], time.strftime('%H:%M:%S', time.gmtime(data[i,-1]))] for i in range(0,l,l//5)], dtype=object).T)
plt.ylabel('RB1 Monitor Signal (mV)')
# plt.gcf().autofmt_xdate()
plt.xticks(rotation=45)
plt.tight_layout()
plt.show()