#from strtypes import error, warning, info
import json
import os


rParam={"amp_adjust":True, "freq_adjust":False, "tot_amp_[mV]":280, 
         "channel":0, "static_duration_[ms]":1,
         "hybridicity":0, "initial_freqs":[190.,170.,150.],   # check this high to low
          "target_freqs":[190.],
           "headroom_segs":10,"moving_duration_[ms]":1}


os.chdir(r'C:\Users\lldj44\Desktop\pydex_modifications\rearr_working_modifictions')
with open('rParam.json', 'w') as fp:
    json.dump(rParam, fp, indent=0)

with open('rParam.json') as json_file:
    data = json.load(json_file)

print(data)