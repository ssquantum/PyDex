from scipy.signal import tukey
import numpy as np
import matplotlib.pyplot as plt
import os

fdir = r'Z:\Tweezer\Code\Python 3.5\PyDex\dds\dds\Data_Files'

np.savetxt(os.path.join(fdir, 'Tukey^2.csv'), np.array((tukey(1000,2/3)**2, np.zeros(1000))), delimiter=',')

t = np.linspace(0,1,1000)
bh = 0.35875 - 0.48829*np.cos(2*np.pi*t) +0.14128*np.cos(4*np.pi*t) - 0.01168*np.cos(6*np.pi*t)
np.savetxt(os.path.join(fdir, 'BlackmanHarris^2.csv'), np.array((bh**2, np.zeros(1000))), delimiter=',')


# plt.plot(tukey(1000,2/3)**2, label='Tukey$^2$')
# plt.plot(tukey(1000,2/3), label='Tukey')
# plt.plot(bh**2, label='Blackman-Harris$^2$')
# plt.plot(bh, label='Blackman-Harris')
# plt.legend()
# plt.show()