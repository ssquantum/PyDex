"""Stefan Spence 18.09.20
Data from our calibration of measured diffraction efficiency as a function
of AWG RF driving power and frequency.
"""
import numpy as np
import matplotlib.pyplot as plt
import sys
import json
sys.path.append(r'Z:\Tweezer\Code\Python 3.5\PyDex\awg')
from spcm_home_functions import load_calibration, ampAdjuster2d
from scipy.interpolate import interp1d
from mpl_toolkits.mplot3d import Axes3D

fdir = r'Z:\Tweezer\Experimental\Setup and characterisation\Settings and calibrations\tweezer calibrations\AWG calibrations'
filename = fdir + r'\814_H_calFile_17.02.2022.txt'
calibration = load_calibration(filename,
            fs = np.linspace(85,110,100), power = np.linspace(0,1,200))

with open(filename) as json_file:
        calFile = json.load(json_file) 

def get_de(freq, amp, de_dict):
    """Find closest frequency and return the expected diffraction efficiency for the give RF amp"""
    i = np.argmin([abs(float(f) - freq) for f in de_dict.keys()]) 
    key = list(de_dict.keys())[i]
    func = interp1d(de_dict[key]['RF Amplitude (mV)'], de_dict[key]['Diffraction Efficiency'])
    return key, amp, func(amp)


#%% reconstruct diffraction efficiency from dictionary of contours
import matplotlib
fig = plt.figure()
cmap = matplotlib.cm.get_cmap('plasma')
ax = fig.gca(projection = '3d')
cdict = calFile["Power_calibration"]
for key in cdict.keys():
    ax.plot(cdict[key]['Frequency (MHz)'], cdict[key]['RF Amplitude (mV)'], 
            np.ones(len(cdict[key]['Frequency (MHz)']))*float(key), color=cmap(float(key)))
plt.xlabel('Frequency (MHz)')
plt.ylabel('RF Amplitude (mV)')

#%%
#### for a given frequency and RF power in, what is the expected output optical power?
f, rf, de = get_de(100, 140, calFile["DE_RF_calibration"])
print('Expected output power at %s MHz, %.4g mV: %.4g %%'%(f, rf, de*100))



#### for a given frequency and desired output optical power, what is the required RF power in mV?

f = 100 # AWG frequency in MHz
p = 1 # optical power as a fraction of that at the reference value (166 MHz, 220mV for 938, 100MHz, 150mV for 814)
print('Required RF power to get %.3g%% output at %s MHz: %.4g mV'%(p*100, f, ampAdjuster2d(f, p, calibration)))

## for multiple frequencies
freqs = np.linspace(85, 110, 200) # frequency in MHz
power = 0.3 
plt.figure(0)
plt.plot(freqs, ampAdjuster2d(freqs, power, calibration))
plt.xlabel('AWG Frequency (MHz)')
plt.ylabel('RF power (mV) \nrequired for %.3g%% output'%(power*100))

## for multiple powers
freq = 100 # frequency in MHz
powers = np.linspace(0.0,1,200) # optical power as a fraction of the reference
plt.figure(1)
plt.plot(powers*100, ampAdjuster2d(freq, powers, calibration))
plt.xlabel('Requested Optical Power (%)')
plt.ylabel('RF power (mV) \nrequired at %s MHz'%(freq))

plt.show()