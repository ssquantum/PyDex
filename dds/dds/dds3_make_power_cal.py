import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from scipy.interpolate import interp1d

plt.style.use('default')

df = pd.read_csv('dds3_power_calibration.csv')

lasers = ['0','1','2','High field imaging','4']

# df = pd.DataFrame()
# df['# DDS'] = np.linspace(0,1,200)
# for laser in lasers:
#     df[laser] = df['# DDS']

#%% High field AOM calibration
label = 'High field imaging'
raw_df = pd.read_csv('high_field_amp.csv')

amplitudes = raw_df['Amplitude']
powers = raw_df['Power (mW)']

df_1557 = pd.DataFrame(data = {'amplitude': amplitudes, 'power': powers})
df_1557.sort_values('amplitude', inplace=True, ignore_index=True)
df_1557['power'] = df_1557['power']/df_1557['power'].max()
max_1557_amp = df_1557['power'].idxmax()
df_1557.at[max_1557_amp+1:,'power'] = 1.05

plt.scatter(df_1557['amplitude'],df_1557['power'])
plt.show()

amp_to_power_1557 = interp1d(df_1557['amplitude'],df_1557['power'])

df[label] = amp_to_power_1557(df['# DDS'])
df[label] = df[label]/(df[label][df[label] <= 1].max())
df[label][df[label] > 1] = 1.05

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

df.to_csv('dds3_power_calibration.csv',index=False)
