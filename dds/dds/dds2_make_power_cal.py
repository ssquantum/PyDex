import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from scipy.interpolate import interp1d

plt.style.use('default')

# df = pd.read_csv('dds2_power_calibration.csv')
df = pd.DataFrame()

lasers = ['','977','1557','1013','420']

df['# DDS'] = np.linspace(0,1,200)

for laser in lasers:
    df[laser] = df['# DDS']

#%% 1557nm calibration
DAQ_channel = ' Dev4/ai0'

DAQ_df = pd.read_csv(r"Z:\Tweezer\Experimental Results\2022\September\23\STIRAP AOM calibrations\1557\aux amp 1\0 to 1\DAQ_trace.csv",skiprows=2)

# plt.figure()
# plt.plot(DAQ_df['# Time (s)'],DAQ_df[DAQ_channel])
# plt.xlim(0,0.110)

start_cutoff_voltage = 0.3
start_index = DAQ_df[DAQ_df[DAQ_channel]>start_cutoff_voltage].index[0]
start_time = DAQ_df['# Time (s)'][start_index]

segment_time = 0.001
buffer_time = 0.0003

time = start_time+buffer_time

amplitudes = np.genfromtxt(r"Z:\Tweezer\Experimental Results\2022\September\23\STIRAP AOM calibrations\1557\aux amp 1\0 to 1\random_amp.csv", delimiter=',')[0][::20]
powers = []

for amplitude in amplitudes:
    power = DAQ_df[(DAQ_df['# Time (s)'] > time) & (DAQ_df['# Time (s)'] < time+segment_time-2*buffer_time)][DAQ_channel].mean()
    # plt.scatter([time],[power],c='C1')
    powers.append(power)
    time += segment_time*2
    
# plt.xlabel('time (s)')
# plt.ylabel('photodiode voltage (V)')
# plt.show()

df_1557 = pd.DataFrame(data = {'amplitude': amplitudes, 'power': powers})
df_1557.sort_values('amplitude', inplace=True, ignore_index=True)
df_1557['power'] = df_1557['power']/df_1557['power'].max()
max_1557_amp = df_1557['power'].idxmax()
df_1557.at[max_1557_amp+1:,'power'] = 1.05

plt.scatter(df_1557['amplitude'],df_1557['power'])
plt.show()

amp_to_power_1557 = interp1d(df_1557['amplitude'],df_1557['power'])

df['1557'] = amp_to_power_1557(df['# DDS'])
df['1557'] = df['1557']/(df['1557'][df['1557'] <= 1].max())
df['1557'][df['1557'] > 1] = 1.05

#%% 977nm calibration
DAQ_channel = ' Dev4/ai0'

DAQ_df = pd.read_csv(r"Z:\Tweezer\Experimental Results\2022\September\23\STIRAP AOM calibrations\977\0 to 0.25\DAQ_trace.csv",skiprows=2)
DAQ_df[DAQ_channel] = DAQ_df[DAQ_channel] - DAQ_df[DAQ_channel][(DAQ_df['# Time (s)'] > 0.11) & (DAQ_df['# Time (s)'] < 0.21)].mean()

# plt.figure()
# plt.plot(DAQ_df['# Time (s)'],DAQ_df[DAQ_channel])
# plt.xlim(-0.005,0.110)

start_cutoff_voltage = 0.025
start_index = DAQ_df[DAQ_df[DAQ_channel]>start_cutoff_voltage].index[0]
start_time = DAQ_df['# Time (s)'][start_index]

segment_time = 0.001
buffer_time = 0.0003

time = start_time+buffer_time

amplitudes = np.genfromtxt(r"Z:\Tweezer\Experimental Results\2022\September\23\STIRAP AOM calibrations\977\0 to 0.25\random_amp.csv", delimiter=',')[0][::20]
powers = []

for amplitude in amplitudes:
    power = DAQ_df[(DAQ_df['# Time (s)'] > time) & (DAQ_df['# Time (s)'] < time+segment_time-2*buffer_time)][DAQ_channel].mean()
    # plt.scatter([time],[power],c='C1')
    powers.append(power)
    time += segment_time*2
    
# plt.xlabel('time (s)')
# plt.ylabel('photodiode voltage (V)')
# plt.show()

# df = pd.DataFrame([amplitudes,powers],columns=['ampliude','power'])

df_977 = pd.DataFrame(data = {'amplitude': amplitudes, 'power': powers})
df_977.sort_values('amplitude', inplace=True, ignore_index=True)
df_977['power'] = df_977['power']/df_977['power'].max()
max_977_amp = df_977['power'].idxmax()
df_977.at[max_977_amp+1:,'power'] = 1.05

plt.scatter(df_977['amplitude'],df_977['power'])
plt.show()

amp_to_power_977 = interp1d(df_977['amplitude'],df_977['power'])

df['977'] = amp_to_power_977(df['# DDS'])
df['977'] = df['977']/(df['977'][df['977'] <= 1].max())
df['977'][df['977'] > 1] = 1.05

#%% 1013nm calibration
DAQ_channel = ' Dev4/ai0'

DAQ_df = pd.read_csv(r"Z:\Tweezer\Experimental Results\2022\September\23\STIRAP AOM calibrations\1013\0 to 0.4\DAQ_trace.csv",skiprows=2)
DAQ_df[DAQ_channel] = DAQ_df[DAQ_channel] - DAQ_df[DAQ_channel][(DAQ_df['# Time (s)'] > 0.11) & (DAQ_df['# Time (s)'] < 0.21)].mean()

# plt.figure()
# plt.plot(DAQ_df['# Time (s)'],DAQ_df[DAQ_channel])
# plt.xlim(-0.005,0.110)

start_cutoff_voltage = 0.025
start_index = DAQ_df[DAQ_df[DAQ_channel]>start_cutoff_voltage].index[0]
start_time = DAQ_df['# Time (s)'][start_index]

segment_time = 0.001
buffer_time = 0.0003

time = start_time+buffer_time

amplitudes = np.genfromtxt(r"Z:\Tweezer\Experimental Results\2022\September\23\STIRAP AOM calibrations\1013\0 to 0.4\random_amp.csv", delimiter=',')[0][::20]
powers = []

for amplitude in amplitudes:
    power = DAQ_df[(DAQ_df['# Time (s)'] > time) & (DAQ_df['# Time (s)'] < time+segment_time-2*buffer_time)][DAQ_channel].mean()
    # plt.scatter([time],[power],c='C1')
    powers.append(power)
    time += segment_time*2
    
# plt.xlabel('time (s)')
# plt.ylabel('photodiode voltage (V)')
# plt.show()

# df = pd.DataFrame([amplitudes,powers],columns=['ampliude','power'])

df_1013 = pd.DataFrame(data = {'amplitude': amplitudes, 'power': powers})
df_1013.sort_values('amplitude', inplace=True, ignore_index=True)
df_1013['power'] = df_1013['power']/df_1013['power'].max()
max_1013_amp = df_1013['power'].idxmax()
df_1013.at[max_1013_amp+1:,'power'] = 1.05

plt.scatter(df_1013['amplitude'],df_1013['power'])
plt.show()

amp_to_power_1013 = interp1d(df_1013['amplitude'],df_1013['power'])

df['1013'] = amp_to_power_1013(df['# DDS'])
df['1013'] = df['1013']/(df['1013'][df['1013'] <= 1].max())
df['1013'][df['1013'] > 1] = 1.05

#%% 420nm calibration
DAQ_channel = ' Dev4/ai0'

DAQ_df = pd.read_csv(r"Z:\Tweezer\Experimental Results\2022\September\23\STIRAP AOM calibrations\420\0 to 1\DAQ_trace.csv",skiprows=2)
DAQ_df[DAQ_channel] = DAQ_df[DAQ_channel] - DAQ_df[DAQ_channel][(DAQ_df['# Time (s)'] > 0.11) & (DAQ_df['# Time (s)'] < 0.21)].mean()

# plt.figure()
# plt.plot(DAQ_df['# Time (s)'],DAQ_df[DAQ_channel])
# plt.xlim(-0.005,0.110)

start_cutoff_voltage = 0.025
start_index = DAQ_df[DAQ_df[DAQ_channel]>start_cutoff_voltage].index[0]
start_time = DAQ_df['# Time (s)'][start_index]

segment_time = 0.001
buffer_time = 0.0003

time = start_time+buffer_time

amplitudes = np.genfromtxt(r"Z:\Tweezer\Experimental Results\2022\September\23\STIRAP AOM calibrations\420\0 to 1\random_amp.csv", delimiter=',')[0][::20]
powers = []

for amplitude in amplitudes:
    power = DAQ_df[(DAQ_df['# Time (s)'] > time) & (DAQ_df['# Time (s)'] < time+segment_time-2*buffer_time)][DAQ_channel].mean()
    # plt.scatter([time],[power],c='C1')
    powers.append(power)
    time += segment_time*2
    
# plt.xlabel('time (s)')
# plt.ylabel('photodiode voltage (V)')
# plt.show()

# df = pd.DataFrame([amplitudes,powers],columns=['ampliude','power'])

df_420 = pd.DataFrame(data = {'amplitude': amplitudes, 'power': powers})
df_420.sort_values(['amplitude','power'], inplace=True, ignore_index=True)
df_420 = df_420.drop(50) # drop the repeat of amp = 1 to avoid complications where these had slightly different values
df_420 = df_420[df_420['power']>0]
df_420['power'] = df_420['power']/df_420['power'].max()
max_420_amp = df_420['power'].idxmax()
df_420.at[max_420_amp+1:,'power'] = 1.05
df_420.at[0,'power'] = 0

plt.scatter(df_420['amplitude'],df_420['power'])
plt.show()

amp_to_power_420 = interp1d(df_420['amplitude'],df_420['power'])

df['420'] = amp_to_power_420(df['# DDS'])
df['420'] = df['420']/(df['420'][df['420'] <= 1].max())
df['420'][df['420'] > 1] = 1.05

#%% set all amp 0 to 0
for laser in lasers:
    df.at[0,laser] = 0

#%% plot and save all calibrations
plt.figure()
for laser in lasers[1:]:
    plt.scatter(df['# DDS'],df[laser],label=laser, alpha=0.5)
plt.xlabel('DDS amplitude')
plt.ylabel('relative power')
plt.legend()
plt.show()

df.to_csv('dds2_power_calibration.csv',index=False)
