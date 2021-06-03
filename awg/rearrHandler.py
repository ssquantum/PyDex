"""
25/05/2021
Moved rearrangement functions to seperate script to keep seperate from AWG base functions (tidier).
Now awgMaster instantiates rearrangementHandler which instantiates awgHandler.
 - awgHandler behaves as normal. 
 - Functions in rearrangmentHandler have access to AWG methods

Core rearrangement functions (1D array)
 - calculateAllMoves  : works out combinations of start and end tweezer AOD freqs and calculates all the
                        possible moves required to go from intial to targer array.
 - createRearrSegment : calls awg.dataGen to creaete the rearrangement segments. Many arguments are loaded from a
                        config file for convenience.
 - calculateSteps     : receives a string of the form 01110 and calculates segments needed to rearrange.
 - load               : modified version of awg.load which is only used if rearrangement is on. Edits the segments 
                        and steps of the loaded file to append to the existing rearrangement steps and segments.
                    

"""

from awgHandler import AWG

# Modules used for rearrangement
from itertools import combinations   # returns tuple of combinations
from scipy.special import comb      # calculates value of nCr
#import rearrange_extra_funcs as rxtra  # helper functions for rearrangement

import time
import json 
import numpy as np
import shutil

class rearrange():
    ### Rearrangement ###
    def __init__(self, AWG_channels=[0]):
                
        # Rearrangement variables
        
        self.awg = AWG(AWG_channels) # opens AWG card and initiates

        
        self.movesDict = {}           # dictionary will be populated when segments are calculated
        self.segmentCounter = 0       # Rearranging: increments by 1 each time calculateAllMoves uploaded a new segment
        self.rr_config = r'Z:\Tweezer\Code\Python 3.5\PyDex\awg\rearr_config.txt'  # default location of rearrange config file
        self.loadRearrParams()        # Load rearrangment parameters from a config file
        self.rearrToggle = False      # Toggle rearrangement on or off: important for appending loaded metadata file to rearr segments
        self.lastRearrStep = 0        # Tells AWG what segment to go to at end of rearrangement
    
    def calculateAllMoves(self):
        """Given the initial and target frequencies, calculate all the possible moves
            from start array to target array
            
            There are 2 modes: if self.rearrMode = 
                - use_exact: segments are for a fixed number (e.g. 5) initial sites sweeping to a 
                             fixed number of target sites (e.g. 2). If not enough atoms, do nothing,
                             if too many atoms, throw away extra
                - use_all  : segements are for a fixed number of of initial sites. The number of target
                             sites depends on how many atoms were loaded. Target array fills up as many 
                             sites as there are atoms.
            If self.rParam["power_ramp"] is True, then after rearrangment, traps will ramp up to new freq_amp.
            
            
            """
        
        # reinitialise values
        self.segmentCounter = 0 # RESET the segment counter when recalculating segments
        self.movesDict={}
        self.loadRearrParams()
        self.lastRearrStep=0
        
        # rearrMode = use_exact: rearrangement only occurs if AT LEAST the target number of atoms is loaded
        if self.rearrMode == 'use_exact':
            req_n_segs = comb(len(self.initial_freqs), len(self.target_freqs)) + self.rParam['headroom_segs'] + 3  # +3 for static initial, target & ramping array
            self.awg.setNumSegments(req_n_segs)    # n segments: combination of all moves + a few extra for other moves.
            
            start_key = self.fstring(self.initial_freqs) # Static array at initial trap freqs 
            self.createRearrSegment(start_key+'si')
            
            end_key = self.fstring(self.target_freqs) # Static array at target trap freqs
            self.createRearrSegment(end_key+'st')
            if self.rParam['power_ramp'] == True:
                self.createRearrSegment(end_key+'r')   # ramp target sites up to a freq_amp value.
        
            if len(self.initial_freqs) < len(self.target_freqs):
                print('WARNING: more target frequencies than initial frequencies! \n '
                            'Moves not calculated.')
            
            else:   # proceed if fewer target traps than initial traps 
                for x in combinations(start_key, len(self.target_freqs)):
                    self.createRearrSegment(''.join(x)+'m'+''.join(self.fstring(self.target_freqs)))
            self.r_setStep(0,0,1,0,1)
          #  print("TODO: self.filedata['steps'] = ")
            
            
        # rearrMode = use_all: ANY atom which is loaded will be rearranged to make as large a complete array as possible.
        elif self.rearrMode == 'use_all':
            start_key = self.fstring(self.initial_freqs) # Static array at initial trap freqs 
            
            # calculate number of segments required:
            req_n_segs = self.rParam['headroom_segs']   #  Add 10 to required num of rearr segs for appending auxilliary moves afterwards
            for j in range(len(start_key)):                          # Loop goes through number of sites loaded, e.g. 3/5, 4/5 etc
                nloaded = len(start_key)-j                            # and move combinations for each are added to req. num segments.
                req_n_segs += comb(len(start_key), nloaded) + 1   # +1 for target static array +1 for target ramping array
                if self.rParam['power_ramp']==True:
                    req_n_segs+=1
            self.awg.setNumSegments(req_n_segs)
            
            self.createRearrSegment(start_key+'si')
            
            # Generate each segment
            for j in range(len(start_key)):
                nloaded = len(start_key)-j   
                end_key = self.fstring(self.target_freqs[:j+1])  # Creat segemtn: static array at target trap freqs
                
                self.createRearrSegment(end_key+'st')  # if 5 sites, there's 5 possible end static arrays: 1,2,3,4, or 5 traps
                
                if self.rParam['power_ramp'] == True:
                    self.createRearrSegment(end_key+'r')   # ramp end trap amplitudes up to a new frequency amplitude. 
                
                for x in combinations(start_key, nloaded):   #  for each of the possible number of traps being loaded
                    self.createRearrSegment(''.join(x)+'m'+''.join(self.fstring([1]*nloaded)))
            self.r_setStep(0,0,1,0,1)
          #  print("TODO: self.filedata['steps'] = ")
            
        self.calculateSteps('1'*len(self.initial_freqs))   #  after calcualting all moves, run calculateSteps to avoid errors.
            
    def createRearrSegment(self, key):
        """
        Pass a key to this function which will:
            1. Parse the key to determine if static or moving or ramping
            2. Using default inputs from rParams dictionary, generate data
            3. Call setSegment to upload data to card for that segment
            4. Call setStep 
            5. Increment segment counter and append to movesDict dictionary
        By tying setSegment to the segmentCounter / moveDict in this function,
        you can't accidentally miss a segment index or overwrite it.
        
        Args:
            key - of the form:
                        - 0123si (static, use initial array freqs)
                        - 0123st (static, use target array freqs)
                        - 0134m012 (moving, from initial array (sites 0134) -> target array (sites01)
                        - 012r   (power ramping, use target array freqs)               
        """
        
        # STATIC TRAP
        if 's' in key:
            fa = self.rearr_freq_amp
            if 'si' in key:                # Initial array of static traps
                f1 = self.flist(key.partition('s')[0], self.initial_freqs)
            elif 'st' in key:              # Target array of static traps
                f1 = self.flist(key.partition('s')[0], self.target_freqs)
                if self.rParam['power_ramp']==True:
                    fa = self.rParam['final_freq_amp']
            data = self.awg.dataGen(self.segmentCounter,
                                self.rParam['channel'],
                                'static',                               # action
                                self.rParam['static_duration_[ms]'],
                                f1,
                                1,9, # pointless legacy arguments 
                                self.rParam['tot_amp_[mV]'],
                                [fa]*len(f1),         # tone freq. amps
                                [0]*len(f1),                      #  tone phases
                                self.rParam['freq_adjust'],     
                                self.rParam['amp_adjust'])
        # MOVING TRAP    
        elif 'm' in key: # Move from initial array to target array of static traps
            f1 = self.flist(key.partition('m')[0], self.initial_freqs) 
            f2 = self.flist(key.partition('m')[2], self.target_freqs)
            data = self.awg.dataGen(self.segmentCounter,
                                self.rParam['channel'],
                                'moving',
                                self.rParam['moving_duration_[ms]'],
                                f1,
                                f2,
                                self.rParam['hybridicity'],
                                self.rParam['tot_amp_[mV]'],
                                [self.rearr_freq_amp]*len(f1),   # start freq amps divide by n initial traps for consistent trap depth
                                [self.rearr_freq_amp]*len(f1),   # end freq amps
                                [0]*len(f1),   # freq phases
                                self.rParam['freq_adjust'],     
                                self.rParam['amp_adjust'])
        # RAMPING TRAP
        elif 'r' in key: # Ramp target array frequency amplitudes up to make use of freed-up RF power.            
            f2 = self.flist(key.partition('r')[0], self.target_freqs)  
            if self.rParam['final_freq_amp'] == 'default':   # If you say final freq amp is default it will divide through by n target sites
                ffa = 1/len(f2)                              # else it will go to the value you have specified.
            else:
                ffa = self.rParam['final_freq_amp']
            data = self.awg.dataGen(self.segmentCounter,
                                self.rParam['channel'],
                                'ramp',
                                self.rParam['ramp_duration_[ms]'],
                                f2,
                                1,9, # pointless legacy arguments
                                self.rParam['tot_amp_[mV]'],
                                [self.rearr_freq_amp]*len(f2),   # start freq amps
                                [ffa]*len(f2),   # end freq amps
                                [0]*len(f2),   # freq phases
                                self.rParam['freq_adjust'],     
                                self.rParam['amp_adjust'])
        
        self.awg.setSegment(self.segmentCounter,data)
        
        self.movesDict[key] = self.segmentCounter
        print(self.segmentCounter)
        self.segmentCounter += 1
    
    #   def setStep(self,stepNum,segNum,loopNum,nextStep, stepCondition ):
    def r_setStep(self, *args):
        """Calls the AWG set step function and also updates the filedata dictionary.
        Args same as setStep. """
        self.awg.setStep(*args)
        #keys = ['step_value','segment_value','num_of_loops','next_step','condition'] # order arguments correctly
        for i in range(len(self.awg.stepOrder)):
            self.awg.filedata['steps']['step_'+str(args[0])][self.awg.stepOrder[i]]=args[i]

    def calculateSteps(self, occupancyStr):
        """Assume the image has been converted to list of 0s and 1s.
            Convert this to a string of occupancies in the key format established
            choose the moves to do
            args:
                occupancyStr = string of 0's & 1's e.g. '0101010' 
                
            """
        t1 = time.time()
        keyStr = self.convertBinaryOccupancy(occupancyStr)
        
        # Warnings to flag a mismatch in number of PyDex atomchecker ROIs compared to number of active tweezer tones 
        if len(occupancyStr) > len(self.initial_freqs):
            print('WARNING: There are '+str(np.abs(len(occupancyStr)-len(self.initial_freqs)))+' fewer traps than PyDex ROIs')
            
        if len(occupancyStr) < len(self.initial_freqs):
            print('WARNING: There are '+str(np.abs(len(occupancyStr)-len(self.initial_freqs)))+' more traps than PyDex ROIs')
            
        if self.rearrMode == 'use_exact':# Only use cases where AT LEAST the target number of atoms was loaded into the initial array.
            stepKeys =  [''.join(self.fstring(self.initial_freqs))+'si', # n static traps
                        keyStr[-len(self.target_freqs):]+'m'+''.join(self.fstring(self.target_freqs)), # sweeps to fixed # target traps
                        ''.join(self.fstring(self.target_freqs))+'st'] # fixed # of static traps
                        
            if self.rParam['power_ramp'] == True:
                stepKeys.insert(-1, ''.join(self.fstring(self.target_freqs))+'r')
       
        elif self.rearrMode == 'use_all':
            stepKeys =  [''.join(self.fstring(self.initial_freqs))+'si', # initial number of static traps
                        keyStr+'m'+''.join(self.fstring([1]*len(keyStr))), # number of targets depends on number loaded
                        ''.join(self.fstring([1]*len(keyStr)))+'st'] # number of target static traps depends on number loaded
            if self.rParam['power_ramp'] == True:
                stepKeys.insert(-1, ''.join(self.fstring([1]*len(keyStr)))+'r')
     
        segList = [self.movesDict.get(key) for key in stepKeys]
        if self.rearrMode == 'use_exact' and len(keyStr) < len(self.target_freqs): 
            segList=[0,0,0]
       
        if None in segList:  # Warning should occur if number of ROIs mismatched so that a segment was not made.
            print('WARNING: One or more requested rearrangement segments do not exist!')
            print(stepKeys)
            print(segList)
        
        if len(keyStr) == 0:   # If no atoms loaded do nothing.
            self.r_setStep(0, 0, 1, 0, 1)
           # print("TODO: self.filedata['steps'] = ")
            
        
        else:
            if self.lastRearrStep == 0:
                trig = 1
            else:
                trig = 1#2
            
            self.r_setStep(0, segList[0], 1, 1, 1)   # Static traps until TTL received  
            self.r_setStep(1, segList[1], 1, 2, 2)   # Moving traps for fixed duration, automatically moves to next step 
            
            if self.rParam['power_ramp']==False:  
                self.r_setStep(2, segList[2], 1, self.lastRearrStep, trig)  # Static traps on at target site until triggered.
            elif self.rParam['power_ramp'] == True: 
                self.r_setStep(2, segList[2], 1, 3, 2) 
                self.r_setStep(3, segList[3], 1, self.lastRearrStep, trig)  # Static traps on at target site until triggered.
            
           # print("TODO: self.filedata['steps'] = ")
        t2=time.time()
       #print('steps calculated in ', t2-t1)
                
                
    
            
                    
    def loadRearrParams(self):
        """Load rearrangement parameters from a config file, i.e. params like
        Amp adjust, phases, duration etc. For the moment just set the manually"""    
        # self.rParam={"amp_adjust":True, 
        #              "freq_adjust":False, 
        #              "tot_amp_[mV]":280, 
        #              "channel":0, 
        #              "static_duration_[ms]":1, "moving_duration_[ms]":1, "ramp_duration_[ms]":5,
        #              "hybridicity":0, 
        #              "initial_freqs":[190.,177.5,165.,152.5,140.], 
        #              "target_freqs":[190.],
        #              "headroom_segs":10, 
        #              "rearrMode":"use_all",
        #              "rearr_freq_amps":0.13,  # If default, rearr freq amps are 1/(n traps). else they are float
        #              "power_ramp":True,
        #              "final_freq_amp": 0.5,
        #              }
        
        with open(self.rr_config) as json_file:
            self.rParam = json.load(json_file)
        
        self.rearrMode = self.rParam["rearrMode"]
        self.initial_freqs = self.rParam['initial_freqs']
        self.target_freqs = self.rParam['target_freqs']
        self.setRearrFreqAmps(self.rParam['rearr_freq_amps'])       # Initialises frequency amplitudes during rearrangment to default 1/len(initial_freqs)
        #self.saveRearrParams()

    def saveRearrParams(self, savedir= r'Z:\Tweezer\Code\Python 3.5\PyDex\awg'):
        """Save the rearrangement parameters used to a metadata file. """
        with open(savedir+'/rearr_config.txt', 'w') as fp:
            json.dump(self.rParam, fp, indent=1, separators=(',',':'))
    
    def printRearrInfo(self):
        """Print out the current status of the card, after changes have been applied by rearrangement functions."""
        if self.rearrToggle == True:
            print('Rearranging is ON')
            print('Rearrange mode is: '+self.rearrMode)
        elif self.rearrToggle == False:
            print('Rearranging is OFF')
        print('  - Config file used is: '+self.rr_config)
        print('  - Current active channels ='+str(self.awg.channel_enable))
        print('  - Card is partitioned into '+str(self.awg.num_segment)+' segments')
        # max duration per segment is (memory=4gB)/(2*n_segments*sample_rate*n_channels)
        print('  - Sample rate is = '+str(self.awg.sample_rate.value))
        print('  - Max duration / segment = ', 4e9/(2*self.awg.num_segment*self.awg.sample_rate.value*len(self.awg.channel_enable))*1e3,' ms')
        print('  - Initial frequencies = '+str(self.initial_freqs))
        print('  - Target frequencies = '+str(self.target_freqs))
        print('  - Segment keys = '+str(self.movesDict))
        print('  - Rearranging freq_amps are = ', self.rearr_freq_amp)
        print('')
         
    def setRearrFreqAmps(self, value = 'default'):
        """Set the frequency amplitudes during rearrangment either to default or to some fixed amplitude.
            When rearr is initialised, default freq amps are 1/(# initial traps)
            From python command terminal can set value to something fixed, applied globally across all rearr freq amps.
            e.g. set freq_amp = 0.2 and in all steps it will be 2.
            """

        if value == 'default':
            self.rearr_freq_amp = round(1/len(self.initial_freqs),3)
        else:
            self.rearr_freq_amp = float(value)    

    def dummySetStep(self):
        """function for testing - effectively runs calculateSteps"""
        print(self.rParam['power_ramp'])
       # print("TODO: self.filedata['steps'] = ")
        if self.rParam['power_ramp'] == True:
            self.r_setStep(0, 0, 1, 1, 1)   # Static traps until TTL received  
            self.r_setStep(1, 3, 1, 2, 2)   # Moving traps for fixed duration, automatically moves to next step   
            self.r_setStep(2, 2, 1, 3, 2) 
            self.r_setStep(3, 1, 1, 4, 1)  # Static traps on at target site until triggered.
        else:
            self.r_setStep(0, 0, 1, 1, 1)   # Static traps until TTL received  
            self.r_setStep(1, 3, 1, 2, 2)   # Moving traps for fixed duration, automatically moves to next step   
            self.r_setStep(2, 1, 1, 3, 1)  # Static traps on at target site until triggered.

    def load(self,file_dir='Z:\Tweezer\Experimental\AOD\m4i.6622 - python codes\Sequence Replay tests\metadata_bin\\20200819\\20200819_165335.txt'):
        
        """
        A method that receives as a single input a metadata file as generated by the self.save() method.
        It assumes no user input other than the full path to the file, so no checks are performed.
        Potential errors will be flagged as the dataGen and setSegment methods
        
        Rearrangment: this is a modified version of the load function. If rearrangment is active, 
        loaded files segments will be appended to rearrangmeent segments & re-indexed
        Steps will be reindexed to start after rearrangement is complete.
        """
        
        self.OGfile = file_dir    #  save the file directory when we load so that we can copy the untampered file
        
        with open(file_dir) as json_file:
            filedata = json.load(json_file)   # rearr: this and following used to be self.filedata, but that i think was wrong.
        
        
        
        lsegments = filedata['segments']                       # segments to be loaded
        lsteps = filedata['steps']                             # steps to be loaded
        lprop = filedata['properties']['card_settings']        # card properties to be loaded
        lchannels = eval(lprop["active_channels"])
        lchannels.sort()                                    # Ensuring that channels are read in ascending order.
        segNumber = len(lsegments)                          # number of segments to be loaded
        stepNumber = len(lsteps)                            # number of steps to be loaded
        
        for i in range(segNumber):
            """
            For each segment stored, go through all available channels
            and generate the data.
            
            Then, send the buffer to the card.
            
            """
            tempData =[]

            for j in lchannels:
                # Finds what action_val was used for this segment and channel
                actionUsed = lsegments['segment_'+str(i)]['channel_'+str(j)]['action_val']
                # Load the relevant parameters in the given order                       
                arguments = [lsegments['segment_'+str(i)]['channel_'+str(j)][x] for x in AWG.loadOrder[actionUsed]]
                # Generate the data and append them to the tempData variable.
                
                if self.rearrToggle==True:  # if rearranging is ON, then add segmentCounter to segment, arguments[0], to 
                    arguments[0] = arguments[0]+self.segmentCounter
                
                tempData.append(self.awg.dataGen(*arguments))
                
            
            # If rearranging on, then index loaded segments starting from index of last rearr segment to avoid overwriting.
            self.awg.setSegment(i+self.segmentCounter,*tempData)    

            
        for i in range(stepNumber):
            # If rearrToggle is true, then here we want last rearr step to move onto 1st loaded step.
            stepArguments = [lsteps['step_'+str(i)][x] for x in AWG.stepOrder]

            if self.rParam['power_ramp'] == False:    
                self.lastRearrStep = 3
            else:
                self.lastRearrStep = 4
            stepArguments[0] += self.lastRearrStep         # reindex step number starting from last rearrange step.
            stepArguments[1] = i + self.segmentCounter      # reindex segments starting from last segment 
            if stepArguments[3] != 0:                      # reindex NEXT step number starting from last rearrange step
                stepArguments[3] += self.lastRearrStep     # unless next step is 0
            stepArguments[4]=2 # set all trigs to 2
            self.awg.setStep(*stepArguments)   
        
        self.calculateSteps('1'*len(self.initial_freqs))   #  after load, run calculateSteps to set triggers correctly.

    
    def rearrLoadSeg(self, cmd):
        """If rearrangement is active, and we're multirunning, we need to reindex the multirun set_data commands starting
           from segment counter so that we change the right steps.
           
           awgHandler.loadSeg(listChanges)
           listChanges expects a list of lists in the following format:
            [[channel,segment,key_word1,new_value1,index],[channel,segment,key_word2,new_value2,index], ...]
            
            loop though and add self.segmentCounter to the segment in each command.
            
            """
        #set_data=[[0,1,"freqs_input_[MHz]",160.0,0]]
        for i in range(len(cmd)):
               cmd[i][1] += self.segmentCounter
        print(cmd)
        self.awg.loadSeg(cmd)

    
    def copyOriginal(self, save_path):
        """This function serves to COPY the loaded in file, which gets saved to the relevant Measure folder. 
           It copies the unmodified AWGparam file and saves it (to avoid saving all the rearrangement steps too)"""
        shutil.copy(self.OGfile, save_path+'/AWGparam_base.txt')
           
    def fstring(self, freqs):
        """Convert a list [150, 160, 170]~MHz to '012' """
        idxs = [a for (a, b) in enumerate(freqs)]   
        return("".join([str(int) for int in idxs]) )
        
    def flist(self, fstring, freq_list):
        """Given a string of e.g. '0123' and an array (initial/target), convert this to a list of freqs
            Args: 
                fstring   - string of integer numbers from 0 to 9 in ascending order.
                freq_list - array of freqs (either initial or target) which get sliced depending on fstring supplied
                    
            e.g. if fstring = 0134 and freq_list = [190.,180.,170.,160.,150.],
                will return [190.,180.,160.,150.]
            
            """
        idxs = [int(i) for i in list(fstring)]
        
        return [freq_list[k] for k in idxs]     #   returns list of frequencies
    
    def convertBinaryOccupancy(self, occupancyStr = '11010'):
        """Convert the string of e.g 010101 received from pyDex image analysis to 
        a string of occupied sites """
        occupied = ''
        for i in range(len(occupancyStr)):  # convert string of e.g. '00101' to '13'
            if occupancyStr[i] == '1': 
                occupied += str(i)
        if occupied == '':    # deal with the case of zero atoms being loaded
            occupied += '0'
        
        return occupied
         
                                    
if __name__ == "__main__":
    r = rearrange()        
        