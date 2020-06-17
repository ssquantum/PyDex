"""Networking - Sequence Translator
Stefan Spence 13/10/19

 - Edit experimental sequences using python dictionaries
 - This is only faster than DExTer's GUI if you're editing 
multiple channels at the same time.
"""
import sys
sys.path.append('') # otherwise cwd isn't in sys.path 
from translator import translate, event_list, header_cluster, channel_names, analogue_cluster
import matplotlib.pyplot as plt
import numpy as np
import matplotlib.cm as cm
from sequencePreviewer import Previewer
try:
    from PyQt4.QtGui import QApplication
except ImportError:
    from PyQt5.QtWidgets import QApplication

import time
font = {'family' : 'normal',
        'size'   : 12}

plt.rcParams.update({'font.size':6})


t = translate()
t0 = time.time()
# t.load_xml('sequences\\SequenceFiles\\BECSequence_200302.xml')
t.load_xml('sequences\\SequenceFiles\\FirstBECSequence_200104.xml')
t1 = time.time()
t.seq_dic['Routine name in'] = "My new routine"
t.seq_dic['Routine description in'] = "An example of editing sequences"

esc = t.seq_dic['Experimental sequence cluster in']
timebase = [0]
totaltime = 0

steprange = range(10,30) #NB this is the range [start,stop)
fastanalouges = [1,2]
slowanalouges = [8,9,14]

### Figures
SequenceFig , axes = plt.subplots(len(fastanalouges)+len(slowanalouges),1,sharex=True)
axes[-1].set_xlabel('Time/ms')
color=iter(cm.tab20(np.linspace(0,1,10)))

### Time Base ###
for i in steprange[0:-1]: #Because the last timestep values aren't used
    print(i)
    header  = esc['Sequence header top'][i]
    if header['Skip Step'] == '0':
        
        if header['Time unit'] == '2': #Seconds
            newtime = float(header['Time step length'])*1000
        if header['Time unit'] == '1': #milliseconds
            newtime = float(header['Time step length'])
        if header['Time unit'] == '0':
            newtime = float(header['Time step length'])/1000

        totaltime += newtime #float(header['Time step length'])  
        timebase.append(totaltime)
        timebase.append(totaltime)
# print(timebase)
# voltages =[] 


## Fast Anlouges ###
j = 0
for channel in fastanalouges:
    c = next(color)
    oldvoltage= float(esc['Fast analogue array'][channel]['Voltage'][steprange[0]])
    #Set up arrays to store
    ramps = [esc['Fast analogue array'][channel]['Ramp?'][steprange[0]]]
    voltages = [oldvoltage]

    for i in steprange[1:]: # Because the first timestep values have already been assigned 
        if esc['Sequence header top'][i]['Skip Step'] == '0':
            ramps.append(esc['Fast analogue array'][channel]['Ramp?'][i])
            print(ramps[-1])
            # print(esc['Fast analogue array'][channel]['Voltage'][i])
            newvoltage = float(esc['Fast analogue array'][channel]['Voltage'][i])
            print(i,ramps[-2],oldvoltage,newvoltage,esc['Sequence header top'][i]['Time step length'])
            if ramps[-2] =='1': #NB becuse of how ramping works this needs to be the previous step
                print('ramping')
                voltages.append(newvoltage)
            elif ramps[-2] == '0':
                voltages.append(oldvoltage)
            voltages.append(newvoltage)
            oldvoltage = newvoltage
    
    print(len(timebase),len(voltages))
    print(timebase,voltages)

    axes[j].plot(timebase,voltages,color = c)
    axes[j].set_ylabel(esc['Fast analogue names']['Name'][channel])
    # print(esc['Fast analogue names'].keys())
    j += 1

for channel in slowanalouges:
    c = next(color)
    oldvoltage= float(esc['Slow analogue array'][channel]['Voltage'][steprange[0]])
    #Set up arrays to store
    ramps = [esc['Slow analogue array'][channel]['Ramp?'][steprange[0]]]
    voltages = [oldvoltage]

    for i in steprange[1:]: # Because the first timestep values have already been assigned 
        if esc['Sequence header top'][i]['Skip Step'] == '0':
            ramps.append(esc['Slow analogue array'][channel]['Ramp?'][i])
            print(ramps[-1])
            # print(esc['Slow analogue array'][channel]['Voltage'][i])
            newvoltage = float(esc['Slow analogue array'][channel]['Voltage'][i])
            print(i,ramps[-2],oldvoltage,newvoltage,esc['Sequence header top'][i]['Time step length'])
            if ramps[-2] =='1': #NB becuse of how ramping works this needs to be the previous step
                print('ramping')
                voltages.append(newvoltage)
            elif ramps[-2] == '0':
                voltages.append(oldvoltage)
            voltages.append(newvoltage)
            oldvoltage = newvoltage
    
    print(len(timebase),len(voltages))
    print(timebase,voltages)

    axes[j].plot(timebase,voltages,color = c)
    axes[j].set_ylabel(esc['Slow analogue names']['Name'][channel])
    # print(esc['Slow analogue names'].keys())
    j += 1

# plt.plot(esc['Fast analogue array'][2]['Voltage'])
plt.show()
#the event list contains metadata for events.
# if you remove or add a timestep, make sure to add its index to an event.
t.seq_dic['Event list array in'][0] = event_list(
            name='Replaced MOT event',
            routinespec=True,
            indices=[0,1],
            path='C:\\Users\\lab\\Desktop\\DExTer 1.1\\Events\\Cs MOT load.evt')

# esc = t.seq_dic['Experimental sequence cluster in'] # shorthand

# # the total number of timesteps is given by len(t.seq_dic['Experimental sequence cluster in']['Sequence header top'])
# for timestep in [0,1]: 
#     for position in ['top', 'middle']:
#         esc['Sequence header '+position][timestep] = header_cluster(
#             skip=False,     # skip step
#             ename='Replaced MOT event', # event name
#             hide=False,     # hide event steps
#             ID=str(timestep),      # event ID
#             tsname='initiate' if timestep else 'MOT load', # time step name
#             populate=False, # populate multirun
#             tslen=timestep*149 + 1,# time step length
#             tunit=1,        # time unit (us, ms, s)
#             # Trigger details:
#             dora=0,         # digital or analogue trigger
#             trigger=0,      # trigger this time step
#             channel=0,      # channel to trigger from
#             av=0.0,         # analogue voltage (V) to trigger at
#             # GPIB details:
#             gpibevent=0,    # GPIB event name (DO nothing, Initial setup, RF ramp 1, RF ramp 2, RF ramp 3, Spin flip, RF off, Remote)
#             gpibon=0)       # GPIB on/off

# # change some time step lengths - make sure to keep sequence header top and sequence header middle the same
# for timestep in [8]:
#     for position in ['top', 'middle']:
#         esc['Sequence header '+position][timestep]['Time step length'] = 30
            
# # turn on some digital channels
# for timestep in [4, 5, 6]:
#     for channel in [2,3]:
#         esc['Fast digital channels'][timestep][channel] = 1 # store booleans as int 0 = False, 1 = True
#     for channel in [0, 1]:
#         esc['Slow digital channels'][timestep][channel] = 1

# # change some analogue voltages
# for timestep in [7, 8, 9]:
#     for channel in [0]:
#         esc['Fast analogue array'][channel]['Voltage'][timestep] = 2.4

# # use list.index('') to find a channel by its name
# channel_names = ['E/W shims (X)', 'U/D shims (Y)', 'N/S shims (Z)']
# shim_values = [0.5, 0.05, -0.005]
# for timestep in range(2, len(esc['Sequence header top'])):
#     for i in range(len(shim_values)):
#         channel = esc['Slow analogue names']['Name'].index(channel_names[i])
#         esc['Slow analogue array'][channel]['Voltage'][timestep] = shim_values[i]

# t2 = time.time()
# t.write_to_file('sequences\\SequenceFiles\\example.xml')
if len(sys.argv) > 1 and sys.argv[1] == '-timeit':
    t3 = time.time()
    t.write_to_str()
    t4 = time.time()
    print('Timings test:')
    tests = {'Load from XML':t1-t0, 'Edit dictionary':t2-t1, 'Write to XML file':t3-t2, 'Write to XML string':t4-t3}
    for key, val in tests.items():
        print(key + ': %.3g ms'%(val*1e3))
else:
    # display the edited sequence
    app = QApplication.instance()
    standalone = app is None # false if there is already an app instance
    if standalone: # if there isn't an instance, make one
        app = QApplication(sys.argv) 
    boss = Previewer(t)
    boss.show()
    if standalone: # if an app instance was made, execute it
        sys.exit(app.exec_())