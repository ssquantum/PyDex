"""Stefan Spence 25.09.20
Plot a DAQ monitor measurement with time stamps
"""
import os
import sys
import time
import numpy as np
import matplotlib.pyplot as plt

measure_folder = r'Z:\Tweezer\Experimental Results\2020\October\01\Measure9'

data = np.loadtxt(os.path.join(measure_folder, 'DAQgraph.csv'), delimiter=',')

plt.figure()
plt.plot(data[:,0], data[:,1]*1e3, '.')
plt.xlabel('Shot Number')
plt.ylabel('RB1 Monitor Signal (mV)')

# get times from files
sys.path.append(r'Z:\Tweezer\Code\Python 3.5\PyDex')
sys.path.append(r'Z:\Tweezer\Code\Python 3.5\PyDex\imageanalysis')
from histoHandler import histo_handler
from scipy.interpolate import interp1d

hh = histo_handler()
_ = hh.load(os.path.join(measure_folder, 'ROI0.Im0.' + os.path.split(measure_folder)[1]+ '.dat'))
ax = plt.gca()
ax1 = ax.twiny()
ax1.set_xlim(ax.get_xlim())
pts = slice(0, len(hh.stats['End file #']), len(hh.stats['End file #']) // 5)
ax1.set_xticks(hh.stats['End file #'][pts])
ax1.set_xticklabels([
    time.ctime(
        os.path.getmtime(
            os.path.join(measure_folder, 'ROI0.Im0.' +str(i)+'.csv')
            )
        ).split(' ')[4]
    for i in hh.stats['File ID'][pts]]
)
plt.show()
# plt.gcf().autofmt_xdate()
plt.xticks(rotation=45)
plt.tight_layout()