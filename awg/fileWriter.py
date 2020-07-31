from pyspcm import *
from spcm_tools import *
from spcm_home_functions import *
import sys
import time
import json


def dataj(data,segVal,action,duration,*args):
    """
    This function stores the card segment metadata
    depending on the type of 'action' the segment is requested to perform.
    This architecture maintains a record of what the segments are
    and not a historical record of all the manipulations conducted so far. 
    
    data: Dictionary with the following structure:
        # filedata = {}
        # filedata["steps"]       = {} #Note that this is a dictionary
        # filedata["segments"]    = {} #Note that this is a dictionary
        # filedata["properties"]  = []
        # filedata["calibration"] = []
    
    segVal: The segment number. Assumes integer (int) from 0 to max_segments
    action: Acceptable values are :1(static), 2(move) and 3 (ramp)
    duration: Duration of a given segment in MILLIseconds (ms)
    *args: Number of arguments depend on the type of motion. 
    
    
    """
    seg = 'segment_'+str(segVal)
    data['segments'][seg]=[]
    ###########
    # Static
    ###########
    if action ==1: 
        if  len(args)==10:
            data["segments"][seg].append({
            'segment'             :segVal,
            'action_type'         :'static trap',
            'action_val'          :action,
            'duration_[ms]'       :duration,
            'freqs_input_[MHz]'   :args[0],
            'num_of_traps'        :args[1],
            'distance_[um]'       :args[2],
            'total_amp_[mV]'      :args[3],
            'freq_amp'            :args[4],
            'freq_phase_[deg]'    :args[5],
            'freq_adjust'         :args[6],
            'amp_adjust'          :args[7],
            'freqs_output_[Hz]'   :args[8],
            'num_of_samples'      :args[9]
            })
        else:
            print('wrong number of arguments')
    
    ###########
    # Moving
    #  moving(startFreq, endFreq,staticFreq,duration,a,tot_amp,freq_amp,freq_phase,freq_adjust,sampleRate):
    ###########    
    elif action ==2:
        if  len(args)==12:
            data["segments"][seg].append({
            'segment'           :segVal,
            'action_type'       :'moving trap',
            'action_val'        :action,
            'duration_[ms]'     :duration,
            'start_freq_[MHz]'  :args[0],
            'end_freq_[MHz]'    :args[1],
            'hybridicity'       :args[2],
            "tot_amp_[mV]"      :args[3],
            'start_amp'         :args[4],
            'final_amp'         :args[5],
            "freq_phase_[deg]"  :args[6],
            "freq_adjust"       :args[7],
            "amp_adjust"        :args[8],
            'start_output_[Hz]' :args[9],
            'end_output_[Hz]'   :args[10],
            'num_of_samples'    :args[11],
            
            
            })
            
        else:
            print("wrong number of arguments")
    
    
    ###########
    # Ramping
    # ramp(freqs=[170e6],numberOfTraps=4,distance=0.329*5,duration =0.1,tot_amp=220,startAmp=[1],endAmp=[0],freq_phase=[0],freqAdjust=True,ampAdjust=True,sampleRate = 625*10**6,umPerMHz =0.329)
    ###########    
    elif action == 3:

        if len(args)==11:
            data["segments"][seg].append({
            'segment'             :segVal,
            'action_type'         :'ramping trap',
            'action_val'          :action,
            'duration_[ms]'       :duration,
            'freqs_input_[MHz]'   :args[0],
            'num_of_traps'        :args[1],
            'distance_[um]'       :args[2],
            'tot_amp_[mV]'        :args[3],
            'start_amp'           :args[4],
            'final_amp'           :args[5],
            'freq_phase_[deg]'    :args[6],
            'freq_adjust'         :args[7],
            'amp_adjust'          :args[8],
            'freqs_output_[Hz]'   :args[9],
            'num_of_samples'      :args[10]
            })
        else:
            print("wrong number of arguments")
            
    data['segments'][seg]=data['segments'][seg][0]
            
            
           
def stepj(data,stepVal,segVal,loopNum,nextStep,condition):
    
    step = 'step_'+str(segVal)
    data["steps"][step]=[]

    
    data["steps"][step].append({
    'step_value'      :stepVal,
    'segment_value'   :segVal,
    'num_of_loops'    :loopNum,
    'next_step'       :nextStep,
    'condition'       :condition
    })
    
    data['steps'][step]=data['steps'][step][0]
    
    
def paramj(data, *args):
    
    paramLen = 11
    if len(args)==paramLen:
        args=args
    else:
        args = ['Error']*paramLen
        
    data["properties"]["card_settings"]=[]
    
    data["properties"]["card_settings"].append({
    'sample_rate_Hz'        :args[0],
    'num_of_segments'    :args[1],
    'start_step'         :args[2],
    'active_channels'    :args[3],
    'bytes_per_channel'  :args[4],
    'maximum_samples'    :args[5],
    'max_output_mV'     :args[6],
    'trig_mode'          :args[7],
    'trig_level0_main' :args[8],
    'trig_level1_aux'  :args[9],
    'static_duration_ms'    :args[10]
    })   
    
    data["properties"]["card_settings"] = data["properties"]["card_settings"][0]                         
            

# filedata = {}
# filedata["steps"]       = {} #Note that this is a dictionary
# filedata["segments"]    = {} #Note that this is a dictionary
# filedata["properties"]  = {}
# filedata["calibration"] = []
# 
# 
#               
# dataj(filedata,0,1,0.02,170,2,1.645*1)
# dataj(filedata,1,2,0.1,170,175,175,0)
# dataj(filedata,2,3,0.1,175,175,100,0)
# dataj(filedata,3,3,0.1,175,175,0,100)
# dataj(filedata,4,2,0.1,175,170,175,0)
# dataj(filedata,5,1,0.02,170,2,1.645*1)
# 
# stepj(filedata,0,0,1000,1,1)
# 
# paramj(filedata,1,2,3,4,5,6,7,8,9,10,11)
# ddate =time.strftime('%Y%m%d')
# ttime =time.strftime('%H%M%S')
# fname = ddate+"_"+ttime
# 
# mypath =  'S:\Tweezer\Experimental\AOD\m4i.6622 - python codes\Sequence Replay tests\metadata_bin\\'+ddate
# if not os.path.isdir(mypath):
#     os.makedirs(mypath)
# 
# with open(mypath+'\\'+fname+'.txt','w') as outfile:
#     json.dump(filedata,outfile,sort_keys = True,indent =4)

# with open(mypath+'\\'+fname+'.txt') as json_file:
#     d = json.load(json_file)   
#        


    