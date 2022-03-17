"""
25/05/2021 Vincent Brooks
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

07/06/2021
Made key change: load, save and loadSeg functions are redefined depending if rearrToggle == True/False (rearr on/off)
 - Functions are set in rearrange.set_functions which is called when rearrange Toggle is changed.
    - This avoid lots of IF statements in other methods, since functions set at top level, makes cleaner, makes faster.

Made change to how moves are calculated: instead of loading all moves to card, now segment data is added to a dictionary
 which during setRearrSeg is uploaded to the card via awg.setSegment. The reason for this is that setSegment method is fast
 and doing it this way removes segment limit from card. Also solves trigger synchronisation issue.


RVB SUGGESTIONS FOR FUTURE CHANGES:
 - If you want to add a new type of rearrangement in future, I recommend: 
      1. Make a method which redefines calculateAllMoves and calculateSteps depending on the type selected (e.g. 1D or 2x1D or 2D)
         (see the set_functions method for inspiration)
      2. This will allow you to change the rearrangement logic, while keeping the existing methods + functionality.                     

"""

from awgHandler import AWG
from spcm_home_functions import phase_minimise

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
    def __init__(self, AWG_channels=[0], name='AWG1'):
                
        # Rearrangement variables
        
        self.awg = AWG(AWG_channels) # opens AWG card and initiates
        self.awg.setNumSegments(32)
        self.activate_rearr(False)
        self.name = name
        
        self.movesDict = {}           # dictionary will be populated when segments are calculated
        self.segmentCounter = 0       # Rearranging: increments by 1 each time calculateAllMoves uploaded a new segment
        self.rr_config = r'Z:\Tweezer\Code\Python 3.5\PyDex\awg\rearr_config_files\rearr_config.txt'  # default location of rearrange config file
        self.loadRearrParams()        # Load rearrangment parameters from a config file   
        self.lastRearrStep = 0        # Tells AWG what segment to go to at end of rearrangement
        self.OGfile = None
        self.set_functions()
    
    def activate_rearr(self, toggle = False):
        """Turn rearranging ON or OFF. Calls set_functions whenever rearrToggle is changed so that there 
           is no mixup.
           Args: 
               - toggle: True or False.
        """
        self.rearrToggle = toggle
        self.set_functions()
        
    
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
        t0 = time.time()
        # reinitialise values
        self.segmentCounter = 0 # RESET the segment counter when recalculating segments
        self.movesDict={}
        self.loadRearrParams()
        self.lastRearrStep=0
        
        req_n_segs = self.rParam['headroom_segs']   #  Add 10 to required num of rearr segs for appending auxilliary moves afterwards
        #self.awg.setNumSegments(req_n_segs)
        start_key = self.fstring(self.initial_freqs) # Static array at initial trap freqs 
        self.createRearrSegment(start_key+'si', seg=0)

        # rearrMode = use_exact: rearrangement only occurs if AT LEAST the target number of atoms is loaded
        if self.rearrMode == 'use_exact':
            
            end_key = self.fstring(self.target_freqs) # Static array at target trap freqs
            if self.rParam['power_ramp'] == False:
                self.createRearrSegment(end_key+'st', seg=2)
                self.segmentCounter = 3
            if self.rParam['power_ramp'] == True:
                self.createRearrSegment(end_key+'r', seg=2)   # ramp target sites up to a freq_amp value.
                self.createRearrSegment(end_key+'st', seg=3)
                self.segmentCounter = 4
        
            if len(self.initial_freqs) < len(self.target_freqs):
                print('WARNING: more target frequencies than initial frequencies! \n '
                            'Moves not calculated.')
            
            else:   # proceed if fewer target traps than initial traps 
                for m in range(len(self.target_freqs)):  # loop over m means we can deal with cases nLoaded < nTarget
                    for x in combinations(start_key, len(self.target_freqs)-m):
                        nloaded="".join(x)
                        self.createRearrSegment(nloaded+'m'+''.join(self.fstring(self.target_freqs[:len(nloaded)])), seg=1) # dont supply seg arg here so that data is not set
            #self.r_setStep(0,0,1,0,1)
            
        # rearrMode = use_all: ANY atom which is loaded will be rearranged to make as large a complete array as possible.
        elif self.rearrMode == 'use_all':
            
            # Generate each segment
            for j in range(len(start_key)):
                nloaded = len(start_key)-j   
                end_key = self.fstring([1]*nloaded)  # Creat segment: static array at target trap freqs
                
                self.createRearrSegment(end_key+'st', seg=2)
                self.segmentCounter = 3
                
                for x in combinations(start_key, nloaded):   #  for each of the possible number of traps being loaded
                    self.createRearrSegment(''.join(x)+'m'+''.join(self.fstring([1]*nloaded)),seg=1)
            
        self.setBaseRearrangeSteps()    # Once all moves calculated, set the base segments which are constant during rearrangement

        t1 = time.time()
        print('All move data calculated in '+str(round(t1-t0,3))+' seconds.')     
                           
    def createRearrSegment(self, key, seg=None):
        """
        Pass a key to this function which will:
            1. Parse the key to determine if static or moving or ramping
            2. Using default inputs from rParams dictionary, generate data
            3. Assign the data to movesDict with the given key. 
        
        Args:
            key - of the form:
                        - 0123si (static, use initial array freqs)
                        - 0123st (static, use target array freqs)
                        - 0134m012 (moving, from initial array (sites 0134) -> target array (sites01)
                        - 012r   (power ramping, use target array freqs)               
        """
        if seg == None:  # specify the exact segment in the card, else it will default to 1 (the rearranging moving seg is 1)
            seg = 1
        # STATIC TRAP
        if 's' in key:
            duration = self.rParam['static_duration_[ms]']
            if 'si' in key:                # Initial array of static traps
                f1 = self.flist(key.partition('s')[0], self.initial_freqs)
                fa = self.getRearrFreqAmps(self.rearr_freq_amp, len(f1))
            elif 'st' in key:              # Target array of static traps
                if self.rearrMode =='use_exact':
                    f1 = self.flist(key.partition('s')[0], self.target_freqs)
                elif self.rearrMode == 'use_all':
                    f1 = self.flist(key.partition('s')[0], self.initial_freqs)
                    
                if self.rParam['power_ramp']:
                    fa = self.getRearrFreqAmps(self.rParam['final_freq_amp'], len(f1))
                    
            if self.rParam['phase_adjust'] == True and len(f1) > 1:
                phase = list(phase_minimise(freqs=f1, dur=duration, sampleRate=self.awg.sample_rate.value/1e6, freqAmps=fa))
            else:
                phase = [0]*len(f1)
            data = self.awg.dataGen(seg,
                                self.rParam['channel'],
                                'static',                               # action
                                self.rParam['static_duration_[ms]'],
                                f1,
                                1,9, # pointless legacy arguments 
                                self.rParam['tot_amp_[mV]'],
                                fa,         # tone freq. amps
                                phase,                      #  tone phases
                                self.rParam['freq_adjust'],     
                                self.rParam['amp_adjust'])
        # MOVING TRAP    
        elif 'm' in key: # Move from initial array to target array of static traps
            f1 = self.flist(key.partition('m')[0], self.initial_freqs)
            fa = self.getRearrFreqAmps(self.rearr_freq_amp, len(f1)) 
            if self.rearrMode == 'use_exact':
                f2 = self.flist(key.partition('m')[2], self.target_freqs)
            elif self.rearrMode == 'use_all':
                f2 = self.flist(key.partition('m')[2], self.initial_freqs)
                
            data = self.awg.dataGen(seg,
                                self.rParam['channel'],
                                'moving',
                                self.rParam['moving_duration_[ms]'],
                                f1,
                                f2,
                                self.rParam['hybridicity'],
                                self.rParam['tot_amp_[mV]'],
                                self.getRearrFreqAmps(self.rearr_freq_amp, len(f1)),   # start freq amps
                                self.getRearrFreqAmps(self.rearr_freq_amp, len(f2)),   # end freq amps
                                [0]*len(f1),   # freq phases
                                self.rParam['freq_adjust'],     
                                self.rParam['amp_adjust'])
            duration = self.rParam['moving_duration_[ms]']
        # RAMPING TRAP
        elif 'r' in key: # Ramp target array frequency amplitudes up to make use of freed-up RF power.            
            f2 = self.flist(key.partition('r')[0], self.target_freqs)  
            data = self.awg.dataGen(seg,
                                self.rParam['channel'],
                                'ramp',
                                self.rParam['ramp_duration_[ms]'],
                                f2,
                                1,9, # pointless legacy arguments
                                self.rParam['tot_amp_[mV]'],
                                self.getRearrFreqAmps(self.rearr_freq_amp, len(f2)),   # start freq amps
                                self.getRearrFreqAmps(self.rParam["final_freq_amp"], len(f2)),   # end freq amps
                                [0]*len(f2),   # freq phases
                                self.rParam['freq_adjust'],     
                                self.rParam['amp_adjust'])
            duration = self.rParam['ramp_duration_[ms]']
        
        self.movesDict[key] = [data]   # List of data saves to movesDict, can be inserted to setSegment during rearrangement.
        
        if len(self.awg.channel_enable) == 2:
            # assume active channels are either 0 or 1
            chan2 = 1 - self.rParam['channel']
            f3 = self.rParam['alt_freqs']
            if self.rParam['phase_adjust'] == True and len(f3) > 1:
                phase = list(phase_minimise(freqs=f3, dur=duration, sampleRate=self.awg.sample_rate.value/1e6, freqAmps=[1]*len(f3)))
            else:
                phase = [0]*len(f3)
            
            # has to be moving so that the duration of data is right (static does loops)
            data2 = self.awg.dataGen(seg, chan2, 'moving', duration, 
                        f3, f3, 1, # frequencies
                        self.rParam['alt_amp_[mV]'], [1]*len(f3), [1]*len(f3), # amps
                        phase, #phase
                        self.rParam['freq_adjust'], self.rParam['amp_adjust'])
            self.movesDict[key].insert(chan2, data2)
            
        if seg is not None or 1:   # If you have specified the segment argument, it will set segment (used ininitial setup of rearr)
            self.awg.setSegment(seg, *self.movesDict[key]) # because of garbage awgHandler code, need to call setSegment immediately after datagen
    
    def r_setStep(self, *args):
        """Calls the AWG set step function and also updates the filedata dictionary.
        Args same as setStep. 
        # NOTE this function might actually be unecessary... (regular setStep might already update filedata dictionary)
        """
        self.awg.setStep(*args)
        #keys = ['step_value','segment_value','num_of_loops','next_step','condition'] # order arguments correctly
        for i in range(len(self.awg.stepOrder)):
            self.awg.filedata['steps']['step_'+str(args[0])][self.awg.stepOrder[i]]=args[i]

    def setBaseRearrangeSteps(self):
        """ Set the steps to follow during the rearrangement (only segment 1 will be changed during routine)
        """

        # Setting the steps:  (probably a cleaner way to do this)
        
        self.r_setStep(0, 0, 1, 1, 1)   # Static traps until TTL received  
        self.r_setStep(1, 1, 1, 2, 2)   # Moving traps for fixed duration, automatically moves to next step 
            
        if self.rParam['power_ramp']==False:  
            self.r_setStep(2, 2, 1, self.lastRearrStep, 1)  # Static traps on at target site until triggered.
        elif self.rParam['power_ramp'] == True: 
            self.r_setStep(2, 2, 1, 3, 2) 
            self.r_setStep(3, 3, 1, self.lastRearrStep, 1)  # Static traps on at target site until triggered.
        
        

    def setRearrSeg(self, occupancyStr):
        """Calculate the  rearrangement step required. 
           Args: 
               - occupancyStr = string of 0's & 1's e.g. '0101010' 
           
            Basically then converts this to a key, which is used to look in movesDict for the correct
            data, which is then sent to card via awg.setSegment.
        
        """


        keyStr = self.convertBinaryOccupancy(occupancyStr)
        
        if len(keyStr)<len(self.target_freqs) and self.rearrMode=='use_exact':
            moveKey = keyStr+'m'+''.join(self.fstring(keyStr))
            self.awg.setSegment(1,*self.movesDict[moveKey], verbosity=False) 
            
            
        
        else:    
            # WARNINGS to notify you there's a user error in setting # ROIs.
            if len(occupancyStr) > len(self.initial_freqs):
                print('WARNING: There are '+str(np.abs(len(occupancyStr)-len(self.initial_freqs)))+' fewer traps than PyDex ROIs')
                print(occupancyStr, self.initial_freqs)
                
            if len(occupancyStr) < len(self.initial_freqs):
                print('WARNING: There are '+str(np.abs(len(occupancyStr)-len(self.initial_freqs)))+' more traps than PyDex ROIs')
            
            if self.rearrMode == 'use_exact':
                moveKey = keyStr[-len(self.target_freqs):]+'m'+''.join(self.fstring(self.target_freqs))
                self.awg.setSegment(1, *self.movesDict[moveKey], verbosity=False)        # segment 1 is always the move segment (0 static, 1 move, 2 static //OR// 2 ramp, 3 static)
                
            
            elif self.rearrMode == 'use_all':
                moveKey = keyStr + 'm'+''.join(self.fstring([1]*len(keyStr)))
                self.awg.setSegment(1, *self.movesDict[moveKey], verbosity=False)        # segment 1 is always the move segment (0 static, 1 move, 2 static //OR// 2 ramp, 3 static)
                
                endKey = self.fstring(['1']*len(keyStr)) +'st'
                self.awg.setSegment(2, *self.movesDict[moveKey], verbosity=False)        # segment 1 is always the move segment (0 static, 1 move, 2 static //OR// 2 ramp, 3 static)


           
        


        
        

    
                
                
    
            
                    
    def loadRearrParams(self):
        """Load rearrangement parameters from a config file, i.e. params like
        Amp adjust, phases, duration etc. For the moment just set the manually"""    
        # self.rParam={"amp_adjust":True, 
        #               "freq_adjust":False, 
        #               "tot_amp_[mV]":280, 
        #               "channel":0, 
        #               "static_duration_[ms]":1, "moving_duration_[ms]":1, "ramp_duration_[ms]":5,
        #               "hybridicity":0, 
        #               "initial_freqs":[190.,177.5,165.,152.5,140.], 
        #               "target_freqs":[190.],
        #               "headroom_segs":10, 
        #               "rearrMode":"use_all",
        #               "rearr_freq_amps":0.13,  # If default, rearr freq amps are 1/(n traps). else they are float
        #               "power_ramp":True,
        #               "final_freq_amp": 0.5,
        #               "phase_adjust" : False,
        #               }
        
        with open(self.rr_config) as json_file:
            self.rParam = json.load(json_file)
        self.rearrMode = self.rParam["rearrMode"]
        self.initial_freqs = self.rParam['initial_freqs']
        self.target_freqs = self.rParam['target_freqs']
        self.rearr_freq_amp = self.rParam['rearr_freq_amps']       # Initialises frequency amplitudes during rearrangment to default 1/len(initial_freqs)
        try:
            self.awg.setSegDur(self.rParam['static_duration_[ms]'])
        except AttributeError:
            print("Loading rearr params but couldn't set static trap duration")
            
       # self.saveRearrParams()


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
        print('  - Sample rate is = '+str(self.awg.sample_rate.value))
        print('  - Max duration / segment = ', 4e9/(2*self.awg.num_segment*self.awg.sample_rate.value*len(self.awg.channel_enable))*1e3,' ms')
        print('  - Initial frequencies = '+str(self.initial_freqs))
        print('  - Target frequencies = '+str(self.target_freqs))
        #print('  - Segment keys = '+str(self.movesDict))
        print('  - Rearranging freq_amps are = ', self.rearr_freq_amp)
        print('')
         
    def getRearrFreqAmps(self, value = 'default', n_traps=1):
        """Set the frequency amplitudes during rearrangment either to default or to some fixed amplitude.
            When rearr is initialised, default freq amps are 1/(# initial traps)
            From python command terminal can set value to something fixed, applied globally across all rearr freq amps.
            e.g. set freq_amp = 0.2 and in all steps it will be 2.
            """

        if type(value) == str:
            return [round(1/len(self.initial_freqs),3)]*n_traps
        else:
            if np.shape(value):
                return list(map(float, value))
            else:
                return [float(value)]*n_traps


    def rearr_load(self,file_dir='Z:\Tweezer\Experimental\AOD\m4i.6622 - python codes\Sequence Replay tests\metadata_bin\\20200819\\20200819_165335.txt'):
        
        """
        A method that receives as a single input a metadata file as generated by the self.save() method.
        It assumes no user input other than the full path to the file, so no checks are performed.
        Potential errors will be flagged as the dataGen and setSegment methods
        
        Rearrangment: this is a modified version of the load function copied for awgHandler. If rearrangment is active, 
        loaded files segments will be appended to rearrangmeent segments & re-indexed
        Steps will be reindexed to start after rearrangement is complete.
        """
        
        if self.OGfile is None:
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

        if self.rParam['power_ramp'] == False: # this if statement is duplicated in setBaseREarrangeSteps()
            self.lastRearrStep = 3
        else:
            self.lastRearrStep = 4
        self.setBaseRearrangeSteps()   # Call this again to reset the base card segments, (to update lastRearrStep)
        for i in range(stepNumber):
            # If rearrToggle is true, then here we want last rearr step to move onto 1st loaded step.
            stepArguments = [lsteps['step_'+str(i)][x] for x in AWG.stepOrder]

            stepArguments[0] += self.lastRearrStep         # reindex step number starting from last rearrange step.
            stepArguments[1] += self.lastRearrStep      # reindex segments starting from last segment 
            if stepArguments[3] != 0:                      # reindex NEXT step number starting from last rearrange step
                stepArguments[3] += self.lastRearrStep     # unless next step is 0
            # stepArguments[4]=2 # set all trigs to 2 --- don't change this!
            if i ==stepNumber-1: 
                stepArguments[4]=1 # last trigger should be 1
            #print(stepArguments)

            self.awg.setStep(*stepArguments)   
        
        #self.calculateSteps('1'*len(self.initial_freqs))   #  after load, run calculateSteps to set triggers correctly.

    def printMovesDict(self):
        for key in self.movesDict:
            #if 'ru' in key:
            print(key) 
    
    def rearr_loadSeg(self, cmd):
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
        self.awg.loadSeg(cmd)

    def saveRearrParams(self, savedir= r'Z:\Tweezer\Code\Python 3.5\PyDex\awg\rearr_config_files'):
        """Save the rearrangement parameters used to a metadata file. """
        with open(savedir+r'\{}rearr_config.txt'.format(self.name), 'w') as fp:
            json.dump(self.rParam, fp, indent=1, separators=(',',':'))
        
            
    def rearr_saveData(self, path):
        """If rearranging is ON, replace awgHandler.save method with THIS method.
            - We no longer save the curent filedata, instead a COPY of the original file loaded in. 
        """

        #print('save path = ' + path)
        self.saveRearrParams(path.rpartition('\\')[0])  # saves rearr_config.txt to measure file
        if self.OGfile is not None:  # avoid error if you haven't loaded in a file after rearranging.
            self.copyOriginal(path)     # saves AWGparams_base (the base AWG file without rearr segs)

    
    def copyOriginal(self, save_path):
        """This function serves to COPY the loaded in file, which gets saved to the relevant Measure folder. 
           It copies the unmodified AWGparam file and saves it (to avoid saving all the rearrangement steps too)"""
        shutil.copy(self.OGfile, save_path)
           
    def fstring(self, freqs):
        """Convert a list [150, 160, 170]~MHz to '012' """
        return ( "".join(str(i) for i in range(len(freqs))) )
        
    def flist(self, fstring, freq_list):
        """Given a string of e.g. '0123' and an array (initial/target), convert this to a list of freqs
            Args: 
                fstring   - string of integer numbers from 0 to 9 in ascending order.
                freq_list - array of freqs (either initial or target) which get sliced depending on fstring supplied
                    
            e.g. if fstring = 0134 and freq_list = [190.,180.,170.,160.,150.],
                will return [190.,180.,160.,150.]
            
            """
        return [freq_list[int(k)] for k in list(fstring)]     #   returns list of frequencies
    
    def convertBinaryOccupancy(self, occupancyStr = '11010'):
        """Convert the string of e.g 010101 received from pyDex image analysis to 
        a string of occupied sites """
        occupied = ''
        j = 0
        for _ in range(len(occupancyStr)): # unless they're all occupied, we won't need every iteration
            try: 
               i = occupancyStr.index('1',j)
               occupied += str(i)
               j = i+1
            except ValueError: 
                break
        
        if occupied == '':    # deal with the case of zero atoms being loaded
            occupied = '0'
        
        return occupied

    def set_functions(self):
        """
        WARNING: ISSUES WITH THIS WAY OF DOING IT. ALTHOUGH SEEMS LIKE IT SHOULD BE FIND, WE HAVE SEEN
        THAT IT CAUSES ISSUES FOR SOME REASON AND DOESN'T WORK
        Depending if rearrangement is on or off, redefine certain functions to behave differently.      
        By setting the function as soon as rearrangement is ON/OFF, avoids lots of IF statements in other
        functions which is cleaner and makes faster.
        """
        if self.rearrToggle == False:  # If rearrangement is OFF
            pass
           # self.load = self.awg.load
           # self.loadSeg = self.awg.loadSeg
          #  self.save = self.awg.saveData
          #  print('using regular functions')
       
        elif self.rearrToggle == True: # If rearrangement is ON
            pass
           # self.load = self.rearr_load
            #self.loadSeg = self.rearr_loadSeg
           # self.save = self.rearr_saveData
            #print('using rearr version of functions')
    
    def phase_adjust(self, N):
        """Analytic expression (Schroeder paper) to adjust phases to give a lower crest factor
           - Args = N : number of traps 
           Returns array of phases in degrees """
        phi = np.zeros(N)
        for i in range(N):
            phi[i] = -np.pi/2-np.pi*(i+1)**2/N
        phi = phi /np.pi * 180
        return(phi)
         
                                    
if __name__ == "__main__":
    r = rearrange()   

















     
        