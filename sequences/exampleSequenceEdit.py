"""Networking - Sequence Translator
Stefan Spence 13/10/19

 - Edit experimental sequences using python dictionaries
 - This is only faster than DExTer's GUI if you're editing 
multiple channels at the same time.
"""
import sys
from lxml import etree
sys.path.append('') # otherwise cwd isn't in sys.path 
from translator import translate, tdict
from sequencePreviewer import Previewer
try:
    from PyQt4.QtGui import QApplication
except ImportError:
    from PyQt5.QtWidgets import QApplication

import time
t = translate()
t0 = time.time()
t.load_xml(r"Z:/Tweezer/Experimental Results/2022/May/19/fast_enable_on.xml")
t1 = time.time()
# t.set_routine_name("Dual RSC")
# t.set_routine_description("Use only RB2 for RSC")

# the event list contains metadata for events.
# if you remove or add a timestep, make sure to add its index to an event.
#eventlist = t.get_evl()[2:]
#index = 0
#eventlist[index][2][1].text = 'Replaced MOT event' # event name
#new_indices = [0,1] # event indices
#if new_indices: 
#    for i in reversed(range(2, len(eventlist[index][3]))):
#        eventlist[index][3].remove(eventlist[index][3][i])
#    eventlist[index][3][1].text = str(len(new_indices))
#    for i in new_indices:
#        etree.SubElement(eventlist[index][3], '{http://www.ni.com/LVData}I32')
#        etree.SubElement(eventlist[index][3][-1], '{http://www.ni.com/LVData}Name')
#        eventlist[index][3][-1][0].text = 'Numeric Control'
#        etree.SubElement(eventlist[index][3][-1], '{http://www.ni.com/LVData}Val')
#        eventlist[index][3][-1][1].text = str(i)
#eventlist[index][4][1].text = 'C:\\Users\\lab\\Desktop\\DExTer 1.1\\Events\\Cs MOT load.evt' # path
#eventlist[index][5][1].text = '1' # routine specific event?
            
esc = t.get_esc() # shorthand
num_s = len(esc[tdict.get('Sequence header top')]) - 2 # total number of timesteps
#for timestep in [0,1]: 
#    for position in [2, 9]: # sequence header top or middle
#        step = esc[position][timestep+2]
#        step[2][1].text = 'Replaced MOT event' # event name
#        step[3][1].text = str(timestep*149 + 1) # time step length
#        # trigger details:
#        step[4][2][1].text = '0.0' # analogue voltage
#        step[4][3][1].text = 'Digital trigger' # type of trigger
#        step[4][4][1].text = '0' # channel
#        step[4][5][1].text = '0' # trigger this time step?
#        # GPIB routine data
#        step[5][2][1].text = 'Do nothing' # GPIB event name
#        step[5][3][1].text = '0' # GPIB on/off
#        step[6][1].text = 'initiate' if timestep else 'MOT load' # time step name
#        step[7][1].text = '0' # Hide event steps
#        step[8][1].text = '1' # populate multirun
#        step[9][-1].text = '1' # time unit (us, ms, s)
#        step[10][1].text = str(timestep) # event ID
#        step[11][1].text = '0' # skip step

# change some time step lengths - make sure to keep sequence header top and sequence header middle the same
#for timestep in [8]:
#    for position in [2, 9]:
#        esc[position][timestep+2][tdict.get('Time step length')][1].text = '30'
            
# turn on some digital channels
# channel = 17
# for timestep in range(num_s):
#     esc[tdict.get('Fast digital channels')][timestep + channel*num_s + 3][1].text = '1' # store booleans as int 0 = False, 1 = True

channel = 20
for timestep in range(num_s):
    esc[tdict.get('Fast digital channels')][timestep + channel*num_s + 3][1].text = '1' # store booleans as int 0 = False, 1 = True

channel = 9
for timestep in range(num_s):
    esc[tdict.get('Slow digital channels')][timestep + channel*num_s + 3][1].text = '1' # store booleans as int 0 = False, 1 = True

# channel = 8
# for timestep in range(num_s):
#     esc[tdict.get('Slow digital channels')][timestep + channel*num_s + 3][1].text = '1' # store booleans as int 0 = False, 1 = True


# channel = 54
# for timestep in list(range(28, 225,4))+list(range(228, 520,20)) + list(range(236,520,20)):
#     esc[tdict.get('Fast digital channels')][timestep + channel*num_s + 3][1].text = '1' # store booleans as int 0 = False, 1 = True
    
# change some analogue voltages
#for timestep in [7, 8, 9]:
#    for channel in [0]:
#        esc[tdict.get('Fast analogue array')][timestep + channel*num_s + 3][3][1].text = '2.4'

# use list.index('') to find a channel by its name
#chan_names_list = [x[3][1].text for x in esc[tdict.get('Slow analogue names')][2:]]
#chan_names = ['E/W shims (X)', 'U/D shims (Y)', 'N/S shims (Z)']
#shim_values = [0.5, 0.05, -0.005]
#for timestep in range(2, num_s):
#    for i in range(len(shim_values)):
#        channel = chan_names_list.index(chan_names[i])
#        esc[tdict.get('Slow analogue array')][timestep + channel*num_s + 3][3][1].text = str(shim_values[i])

t2 = time.time()
t.write_to_file(r"Z:\Tweezer\Experimental Results\2022\May\19\fast_enable_on.xml")
if len(sys.argv) > 1 and sys.argv[1] == '-timeit':
    t3 = time.time()
    t.write_to_str()
    t4 = time.time()
    print('Timings test:')
    tests = {'Load from XML':t1-t0, 'Edit channels':t2-t1, 'Write to XML file':t3-t2, 'Write to XML string':t4-t3}
    for key, val in tests.items():
        print(key + ': %.3g ms'%(val*1e3))
else:
    # display the edited sequence
    app = QApplication.instance()
#    standalone = app is None # false if there is already an app instance
#    if standalone: # if there isn't an instance, make one
#        app = QApplication(sys.argv) 
#    boss = Previewer(t)
#    boss.set_sequence()
#    boss.show()
#    if standalone: # if an app instance was made, execute it
#        sys.exit(app.exec_())