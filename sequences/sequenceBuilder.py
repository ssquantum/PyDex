"""Stefan Spence 18/09/20
 - Load in events for the optimum Cs sequence
"""
import time
import os
import sys
sys.path.append(r'Z:\Tweezer\Code\Python 3.5\PyDex\sequences') 
sys.path.append(r'Z:\Tweezer\Code\Python 3.5\PyDex') 
from translator import translate, event_list, header_cluster, channel_names, analogue_cluster

t = translate() # this class manages the sequence
t.seq_dic['Routine name in'] = "Cs Opt Sequence "+time.strftime('%d.%m.%y')
t.seq_dic['Routine description in'] = "Load Cs in 938 tweezer, cool and image, OP to 4,4 then apply pulsed RSC cooling."

#### make sure the sequence starts empty
t.seq_dic['Event list array in'] = []
esc = t.seq_dic['Experimental sequence cluster in']  # shorthand
for i in range(len(esc['Sequence header top'])): 
    for position in ['top', 'middle']:
        esc['Sequence header '+position] = []
    for speed in ['Fast', 'Slow']:
        esc[speed+' digital channels'] = []
        for i in range(len(esc[speed+' analogue array'])):
            esc[speed+' analogue array'][i] = analogue_cluster(0)

temp = translate() # used just for loading sequences

#### choose the events you would like to add #### 
# note: the desired event to add is the first event in the xml file

fdir = r'Z:\Tweezer\Code\Python 3.5\PyDex\sequences\SequenceFiles'
savefilename = 'Cs 20 RSC Pulses Seq.xml'
filelist = ['Cs MOT.xml', 'Cs molasses.xml', 'Cs cool step 1.xml', 'Cs image.xml', 'Cs cool step 2.xml', 'Cs 4,4 OP.xml']
filelist += ['Cs Raman pulse.xml', 'Cs OP pulse.xml']*20
filelist += ['Cs F=4 pushout.xml', 'Cs image.xml']

def extract(give, take, index, event=0):
    """Append the event from the sequence in 'take' to the sequence in 'give'.
    'give' and 'take' are translate objects
    index -- number of steps already in sequence 'give'
    event -- index of the event in 'take' to add to 'give'"""
    t1 = take.seq_dic['Event list array in']
    t2 = take.seq_dic['Experimental sequence cluster in']
    g2 = give.seq_dic['Experimental sequence cluster in']
    give.seq_dic['Event list array in'].append(t1[event])
    give.seq_dic['Event list array in'][-1]['Event indices'] = [i for i in range(index, index+len(t1[event]['Event indices']))]
    i0 = sum(len(t3['Event indices']) for t3 in t1[:event]) # can't trust event indices to be correct
    for i in range(i0, i0+len(t1[event]['Event indices'])): 
        for position in ['top', 'middle']:
            g2['Sequence header '+position].append(t2['Sequence header '+position][i])
        for speed in ['Fast', 'Slow']:
            g2[speed+' digital channels'].append(t2[speed+' digital channels'][i])
            for chan, ch1 in zip(g2[speed+' analogue array'], t2[speed+' analogue array']):
                chan['Voltage'].append(ch1['Voltage'][i])
                chan['Ramp?'].append(ch1['Ramp?'][i])

#### build sequence from the events
ind = 0 # event index
for fn in filelist:
    temp.load_xml(os.path.join(fdir, fn))
    extract(t, temp, ind, 0)
    ind += len(temp.seq_dic['Event list array in'][0]['Event indices'])

# also need to add end step
extract(t, temp, ind, -1)

#### adjust some values in some time steps
channel_type = 'Fast analogue'
channel_names = ['Cs 4->4 OP Power']
channel_index = [temp.seq_dic['Experimental sequence cluster in'][channel_type+' names']['Name'].index(cn) for cn in channel_names]
values = [1.21]
for timestep in range(0, len(esc['Sequence header top'])):
    for channel, val in zip(channel_index, values):
        if 'analogue' in channel_type: # analogue array or digital channels
            esc[channel_type+' array'][channel]['Voltage'][timestep] = val    
        elif 'digital' in channel_type:
            esc[channel_type+' channels'][timestep][channel] = val # store booleans as int 0 = False, 1 = True

#### save the edited sequence
t.write_to_file(os.path.join(fdir, savefilename))


#### display the edited sequence 
from sequencePreviewer import Previewer
try:
    from PyQt4.QtGui import QApplication
except ImportError:
    from PyQt5.QtWidgets import QApplication



app = QApplication.instance()
standalone = app is None # false if there is already an app instance
if standalone: # if there isn't an instance, make one
    app = QApplication(sys.argv) 

boss = Previewer(t)
boss.showMaximized()
if standalone: # if an app instance was made, execute it
    sys.exit(app.exec_())