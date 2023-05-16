"""Sequence Plotter
Dan Ruttley 17/03/23

 - Generate plots of voltages throughout a sequence.
"""
import numpy as np
import matplotlib.pyplot as plt
import sys
sys.path.append(r'Z:\Tweezer\Code\Python 3.5\PyDex\sequences')
sys.path.append(r'Z:\Tweezer\Code\Python 3.5\PyDex')
from lxml import etree
sys.path.append('') # otherwise cwd isn't in sys.path 
from translator import translate, tdict
from sequencePreviewer import Previewer
try:
    from PyQt4.QtGui import QApplication
except ImportError:
    from PyQt5.QtWidgets import QApplication

import time



plt.style.use('default')

def check_timestep_skipped(timestep):
    position = 2
    return bool(int(esc[position][timestep+2][tdict.get('Skip Step')][1].text))

def remove_skipped_timesteps(timesteps):
    skipped = np.array([check_timestep_skipped(timestep) for timestep in timesteps])
    # print(skipped)
    timesteps = timesteps[~skipped]
    return timesteps

def get_time_unit(timestep):
    units = ['us','ms','s']
    multiplier_ms = [0.001,1,1000]
    position = 2
    index = int(esc[position][timestep+2][tdict.get('Time unit')][4].text)
    return units[index], multiplier_ms[index]

def get_time_float(timestep):
    position = 2
    return float(esc[position][timestep+2][tdict.get('Time step length')][1].text)

def get_time_ms(timestep):
    """Returns in the time in ms of a timestep."""
    return get_time_float(timestep)*get_time_unit(timestep)[1]

def get_fdo_val(channel,timestep):
    num_s = len(esc[tdict.get('Sequence header top')]) - 2 # total number of timesteps
    start = int(esc[tdict.get('Fast digital channels')][timestep + channel*num_s + 3][1].text)
    end = start
        
    return [start,end]

def get_sdo_val(channel,timestep):
    num_s = len(esc[tdict.get('Sequence header top')]) - 2 # total number of timesteps
    start = int(esc[tdict.get('Slow digital channels')][timestep + channel*num_s + 3][1].text)
    end = start
        
    return [start,end]

def get_fao_val(channel,timestep):
    num_s = len(esc[tdict.get('Sequence header top')]) - 2 # total number of timesteps
    ramp = bool(int(esc[tdict.get('Fast analogue array')][timestep + channel*num_s + 3][2][1].text))
    start = float(esc[tdict.get('Fast analogue array')][timestep + channel*num_s + 3][3][1].text)
    
    if ramp:
        end = float(esc[tdict.get('Fast analogue array')][timestep+1 + channel*num_s + 3][3][1].text)
    else:
        end = start
        
    return [start,end]

def get_sao_val(channel,timestep):
    num_s = len(esc[tdict.get('Sequence header top')]) - 2 # total number of timesteps
    ramp = bool(int(esc[tdict.get('Slow analogue array')][timestep + channel*num_s + 3][2][1].text))
    start = float(esc[tdict.get('Slow analogue array')][timestep + channel*num_s + 3][3][1].text)
    
    if ramp:
        end = float(esc[tdict.get('Slow analogue array')][timestep+1 + channel*num_s + 3][3][1].text)
    else:
        end = start
        
    return [start,end]

def get_times_ms(timesteps):
    return np.array([get_time_ms(timestep) for timestep in timesteps])

def get_fdo_vals(channel,timesteps):
    return np.array([get_fdo_val(channel,timestep) for timestep in timesteps],dtype=bool)

def get_sdo_vals(channel,timesteps):
    return np.array([get_sdo_val(channel,timestep) for timestep in timesteps],dtype=bool)

def get_fao_vals(channel,timesteps):
    return np.array([get_fao_val(channel,timestep) for timestep in timesteps])

def get_sao_vals(channel,timesteps):
    return np.array([get_sao_val(channel,timestep) for timestep in timesteps])

def plot_times_channel(durations,channel,**kwargs):
    times = np.cumsum(durations)
    times = np.repeat(times, 2)
    times = np.concatenate([np.array([0]),times])
    times = times[:-1]
    channel = [item for sublist in channel for item in sublist]    
    plt.plot(times,channel,**kwargs)
    
t = translate()
t.load_xml(r"Z:\Tweezer\Experimental Results\2023\May\03\Measure15\sequences\Measure15_3.xml")
esc = t.get_esc() # shorthand

#%%
timesteps = np.arange(1035,1056)
timesteps = remove_skipped_timesteps(timesteps) # note currently the ramps etc. will still take into account skipped timesteps

times = get_times_ms(timesteps)

power_1065 = get_fao_vals(2,timesteps)
ns_shims = get_sao_vals(14,timesteps)
B_field= ns_shims*4.78/8

ttl_mw = get_fdo_vals(25,timesteps)
# shutter_1557 = get_sdo_vals(2,timesteps)
# pulse_1557 = shutter_1557*(~ttl_1557)


fig, axs = plt.subplots(2,1,sharex=True)

plt.sca(axs[0])
plot_times_channel(times,power_1065,c='tab:red',label='_1065 power')
plot_times_channel(times,ttl_mw,c='tab:green',label='MW pulse')
plt.ylabel('1065 power (V)')
plt.legend()

plt.sca(axs[1])
plot_times_channel(times,B_field,c='tab:blue',label='_B field')
plt.ylabel('magnetic field (G)')
# plt.axhline(197.3,c='k',linestyle='--')

plt.xlabel('time after 817 starts to merge (ms)')

fig.tight_layout()

plt.show()