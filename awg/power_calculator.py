"""Stefan Spence 18.09.20
Data from our calibration of measured diffraction efficiency as a function
of AWG RF driving power and frequency.
"""
import numpy as np
import matplotlib.pyplot as plt
import sys
sys.path.append(r'Z:\Tweezer\Code\Python 3.5\PyDex\awg')
from spcm_home_functions import contour_dict, DE_RF_dict, ampAdjuster1d, ampAdjuster2d

#### for a given frequency and RF power in, what is the expected output optical power?
def estimate_optical_power(frequency, RF_power):
    """Return the expected optical power for the given AWG frequency and RF power,
    as a fraction of the optical power at 166MHz, 220mV"""
    # find the closest frequency in the calibration curve
    i = np.argmin([abs(float(f) - frequency) for f in DE_RF_dict.keys()]) 
    key = list(DE_RF_dict.keys())[i]
    # find the closest RF power in the calibration
    i = np.argmin(abs(RF_power - np.array(DE_RF_dict[key]['RF Amplitude (mV)']))) 
    return key, DE_RF_dict[key]['RF Amplitude (mV)'][i], DE_RF_dict[key]['Diffraction Efficiency'][i]

f, rf, p = estimate_optical_power(140, 220)
print('Expected output power at %s MHz, %.4g mV: %.4g %%'%(f, rf, p*100))



#### for a given frequency and desired output optical power, what is the required RF power in mV?

f = 166 # AWG frequency in MHz
p = 0.5 # optical power as a fraction of that at 166 MHz, 220mV
print('Required RF power to get %.3g%% output at %s MHz: %.4g mV'%(p*100, f, ampAdjuster1d(f, p)))

## for multiple frequencies
freqs = np.linspace(135, 190, 200) # frequency in MHz
power = 0.5 # optical power as a fraction of that at 166 MHz, 220mV
plt.figure(0)
plt.plot(freqs, ampAdjuster1d(freqs, power))
plt.xlabel('AWG Frequency (MHz)')
plt.ylabel('RF power (mV) \nrequired for %.3g%% output'%(power*100))

## for multiple powers
freq = 166 # frequency in MHz
powers = np.linspace(0.01,1,200) # optical power as a fraction of that at 166 MHz, 220mV
plt.figure(1)
plt.plot(powers*100, ampAdjuster2d(powers, freq)[:,0])
plt.xlabel('Requested Optical Power (%)')
plt.ylabel('RF power (mV) \nrequired at %s MHz'%(freq))



## test agreement:
# diff = np.zeros((len(freqs), len(powers)))
# for i, F in enumerate(freqs):
#     for j, P in enumerate(powers):
#         diff[i,j] = ampAdjuster1d(F, P) - ampAdjuster2d(P, F)[0]
# 
# plt.figure(2)
# # the amp adjuster uses discrete optical powers, whereas amp ramp uses discrete frequencies
# # as a result, stripes of disagreement up to 5mV can be seen.
# im = plt.imshow(diff, extent = (min(freqs), max(freqs), min(powers), max(powers)), origin = 'lower', cmap = 'RdYlBu', aspect = 'auto')
# plt.colorbar(im, orientation='vertical')
# plt.title('Difference in RF power between \ninterpolation functions (mV)')
# plt.xlabel('Frequency (MHz)')
# plt.ylabel('Requested Optical Power')
plt.show()