"""Stefan Spence 15.01.20

Display histograms using PyDex:
load histogram results from a log file, then plot the histograms using the appropriate 
histogram csv file
"""
import numpy as np
import matplotlib.pyplot as plt
plt.rcParams.update({'font.size': 12})
import sys
sys.path.append(r'Z:\Tweezer\People\Stefan\general-python')
sys.path.append(r'Z:\Tweezer\Code\Python 3.5\PyDex')
from fitandgraph import fit, graph
from imageanalysis.histoHandler import histo_handler
from scipy.optimize import curve_fit

# choose all of the options to plot
fdir = r'Z:\Tweezer\Experimental Results\2020\June\18\Measure2' # directory files are stored in 
hh = histo_handler()
hh.load(fdir+r'\ROI1.Im0.Measure2.dat') # load the log/measure file containing histogram statistics to plot
# hh.sort_dict() # sort the histograms in ascending order of user_var measured
prestring = r'\ROI1.Im0.' # prestring at the start of the histogram csv files
num_bins = 25   # number of bins to make the histograms with
var_unit = '$\mu$s' # units for the user variable
def conv(x): 
    """conversion function for the user variable"""
    return x#-2*(16.41*x + 65.04-95.12) 
# I = 2*power *(convert from measured power to total MOT power) / np.pi / beamwaist**2 / Isat

# calculate the contrast to noise ratio
sep = np.array(hh.stats['Separation']) # atomic fluorescence signal
bg_width = np.array(hh.stats['Background peak width']) # standard deviation of fit to background peak
at_width = np.array(hh.stats['Signal peak width']) # standard deviation of fit to signal peak
Nbg_shots = np.array(hh.stats['Number of images processed'])*(1-np.array(hh.stats['Loading probability'])) # number of images in background
Nat_shots = np.array(hh.stats['Number of images processed'])*np.array(hh.stats['Loading probability']) # number of images in signal peak
SN = sep / np.sqrt(bg_width**2 + at_width**2) # contrast to noise ratio
# fractional error in the error is 1/sqrt(2N-2)
SNerr = SN * np.sqrt((at_width/sep)**2/Nat_shots + np.sqrt(2*bg_width**2/np.sqrt(2*Nbg_shots-2) + 2*at_width**2/np.sqrt(2*Nat_shots-2))/(bg_width**2 + at_width**2))

# produce the grid of subplots
fig, ax = plt.subplots(len(hh.stats['File ID'])-12, num=0, sharex=True, 
                       gridspec_kw={'hspace': 0.8}, figsize=(8,9))
plt.subplots_adjust(left=0.1, right=0.95, top=0.95, bottom=0.07)
ax[-1].set_xlabel('Counts')
ax[-1].set_ylabel('Occurrence')

xlim = np.array((hh.stats['Background mean'][0],hh.stats['Signal mean'][0]))
# add the histograms to the respective subplots
for i in range(len(hh.stats['File ID'])-12):    
    # load the histogram data from the csv file
    histdata = np.genfromtxt(fdir+prestring+str(int(hh.stats['File ID'][i]))+'.csv', delimiter=',')
    # replot the histogram
    occ, bins, patches = ax[i].hist(histdata[:,1], bins=num_bins)
    # plt.figure()
    # plt.hist(histdata[:,1], bins=num_bins)
    # plot threshold
    ax[i].plot([hh.stats['Threshold'][i]]*2, ax[i].get_ylim(), 'k:')
    # add a title with histogram statistics
    ax[i].set_title('Loading Probability: $%s\pm %.1g$, Bg: $%s\pm %s$, Atom: $%s\pm %s$, Fidelity: $%s\pm %s$'%(
    hh.stats['Loading probability'][i], hh.stats['Error in Loading probability'][i], 
    hh.stats['Background peak count'][i], hh.stats['Error in Background peak count'][i], 
    hh.stats['Signal peak count'][i], hh.stats['Error in Signal peak count'][i], 
    hh.stats['Fidelity'][i], hh.stats['Error in Fidelity'][i]),
    fontsize=10, pad=9)
    # search for appropriate horizontal axis limits
    if min(bins) < xlim[0]:
        xlim[0] = min(bins)
    if max(bins) > xlim[1]:
        xlim[1] = max(bins)

for i in range(len(ax)): # update the horizontal axis limits
    ax[i].set_xlim(xlim)
    # add text with the user variable
    ax[i].text(np.mean(xlim),np.mean(ax[i].get_ylim()),'%.3g'%(conv(hh.stats['User variable'][i]))+' '+var_unit)
    print('var: %.3g'%(conv(hh.stats['User variable'][i]))+' '+var_unit+ '   -- S/N: %.3g +/- %.1g'%(SN[i],SNerr[i]))
    
plt.show()


# stats:  'File ID',
#         'Start file #',
#         'End file #',
#         'ROI xc ; yc ; size',
#         'Counts above : below threshold',
#         'User variable',
#         'Number of images processed', 
#         'Loading probability', 
#         'Error in Loading probability',
#         'Lower Error in Loading probability',
#         'Upper Error in Loading probability',
#         'Background peak count', 
#         'Error in Background peak count', 
#         'Background peak width',
#         'sqrt(Nr^2 + Nbg)', 
#         'Background mean', 
#         'Background standard deviation', 
#         'Signal peak count', 
#         'Error in Signal peak count',
#         'Signal peak width', 
#         'sqrt(Nr^2 + Ns)',
#         'Signal mean', 
#         'Signal standard deviation', 
#         'Separation',
#         'Error in Separation',
#         'Fidelity', 
#         'Error in Fidelity',
#         'S/N',
#         'Error in S/N',
#         'Threshold',
#         'Include'.
