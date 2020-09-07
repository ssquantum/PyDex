
from pyspcm import *
from spcm_tools import *
from spcm_home_functions import *
from fileWriter import *
import sys
import os
import time
import json

# def statusChecker(N):
#    for i in range(N):
#        test = int64(0)
#        spcm_dwGetParam_i64(self.hCard,SPC_SEQMODE_STATUS,byref(test))
#        print(test.value)
#        time.sleep(0.1) 
    

    
    

class AWG:
    """
        This is for the trigger method.
        Consult the manual p.91 for more details.
        These are exclusively for EXT0 (main trigger).
        EXT1 supports triggers with only one level. 
        
        As a rule of thumb, Level 0 is the universal level (denoted as Level X)
        and Level 1 is the ancilla level for gating/window trigger modes (denoted as Level Y)
        """
        
        trig_mode = {
        0:  SPC_TMASK_SOFTWARE,
        1:  SPC_TM_POS,                    # Triggers on positive slope
        2:  SPC_TM_NEG,                    # Triggers on negatice slope
        3:  SPC_TM_POS | SPC_TM_REARM,     # Triggers on pos (Level X), rearms on Level Y to avoid noise triggering.
        4:  SPC_TM_NEG | SPC_TM_REARM,     # Triggers on neg (Level X), rearms on Level Y to avoid noise triggering.
        5:  SPC_TM_BOTH,                   # Triggers on pos or neg slope
        6:  SPC_TM_HIGH,                   # Triggers when above Level X (GATE)
        7:  SPC_TM_LOW,                    # Triggers when below Level X (GATE)
        8:  SPC_TM_WINENTER,               # Triggers when entering a window (pos or neg) defined by Level X and Level Y 
        9:  SPC_TM_WINLEAVE,               # Triggers when leaving a window (pos or neg) defined by Level X and Level Y 
        10: SPC_TM_INWIN,                  # Triggers while within a window defined by Level X and Level Y (GATE)
        11: SPC_TM_OUTSIDEWIN              # Triggers while outside a window defined by Level X and Level Y (GATE)
        }
        
        
        registers = {
        1:  SPC_SAMPLERATE,                # Samplerate of the card
        2:  SPC_SEQMODE_MAXSEGMENTS,       # Number of segments set on the card
        3:  SPC_SEQMODE_STARTSTEP,         # Initialisation step of the card
        4:  SPC_CHENABLE,                  # Checks the activated number
        5:  SPC_CHCOUNT,                   # Checks how many channels are active
        6:  SPC_TRIG_EXT0_LEVEL0,          # Checks what is the trigger level for Ext0
        7:  SPC_TRIG_EXT0_LEVEL1,          # Checks what is the trigger level for Ext1
        8:  SPC_TRIG_EXT0_MODE,            # Gives back what trigger mode is being used
        9:  SPC_SEQMODE_WRITESEGMENT,      # Checks which segment is chosen to be modified
        10: SPC_SEQMODE_SEGMENTSIZE        # Checks how many samples are registered in this segment. 
        }
        
        
        stepOptions = {
        1:  SPCSEQ_ENDLOOPONTRIG,          # Sequence Step will advance after receiving a flag command from a trigger
        2:  SPCSEQ_ENDLOOPALWAYS,          # Sequence Step will advance immediately after defined loops end. 
        3:  SPCSEQ_END                     # Sequence Step will be the terminating step for the replay. 
        }

        """
        The damage threshold of the AOD amplifier is 0 dBm. We add a precautionary
        upper limit to -1 dBm on the card.  
        """
        maxdBm= -1                                                                  # Max card output in dBm
        max_output =  round(math.sqrt(2*10**-3 * 50 *10 **(maxdBm/10))*1000)        # The conversion is from dBm to MILLIvolts (amplitude Vp, not Vpp). This assumes a 50 Ohm termination. 
        
        ###############################################################################################
        ########################## Defined in the spcm_home_functions.py ##############################
        ###############################################################################################
        umPerMHz =cal_umPerMHz        # Defines the conversion between micrometers and MHz for the AOD
        ###############################################################################################



    def __init__ (self, channel_enable = [0,1],sample_rate = MEGA(625), num_segment = int(16) , start_step=int(0)):
        """
        Static initialisation of the card
        These should be common for the class AWG.
        Changing these would affect all instances. 
        """
        self.hCard = spcm_hOpen (create_string_buffer (b'/dev/spcm0'))
        #self.hCard = spcm_hOpen (create_string_buffer (b'TCPIP::192.168.1.10::inst0::INSTR'))
        if self.hCard == None:
            sys.stdout.write("no card found...\n")
            exit ()
        
        #Initialisation of reading parameters and definition of memory type.
        self.lCardType     = int32 (0) 
        self.lSerialNumber = int32 (0)
        lFncType      = int32 (0)
        spcm_dwGetParam_i32 (self.hCard, SPC_PCITYP, byref (self.lCardType))                  # Enquiry of the pointer (lCardType.value) should return 484898. In manual p.56, this number should correspond to our device M4i.6622
        spcm_dwGetParam_i32 (self.hCard, SPC_PCISERIALNO, byref (self.lSerialNumber))         # Enquiry of the pointer should return 14926. This can be cross-checked with the Spectrum documentation (check the Certificate)
        spcm_dwGetParam_i32 (self.hCard, SPC_FNCTYPE, byref (lFncType))                  # Enquiry of the pointer should return 2. In manual p.59, this value corresponds to the arb. function generator. 
        spcm_dwSetParam_i32 (self.hCard, SPC_CLOCKOUT,   0)                              # Disables the clock output (tristate). A value of 1 enables on external connector. Check p.83 on manual for more details.
        
        
        ###################################################################
        # This is where the card metadata will be stored
        ###################################################################
        self.filedata = {}
        self.filedata["steps"]       = {}
        self.filedata["segments"]    = {} #Note that this is a dictionary
        self.filedata["properties"]  = {}
        self.filedata["calibration"] = []
        
        
        
        """
        Dynamic initialisation of the card.
        These are instance specific parameters.
        Changing these would affect the particular instance. 
        """
        # Setting the sample rate of the card.
        if sample_rate> MEGA(625):
            sys.stdout.write("Requested sample rate larger than maximum. Sample rate set at 625 MS/s")
            sample_rate = MEGA(625)
        self.sample_rate = sample_rate
        spcm_dwSetParam_i64 (self.hCard, SPC_SAMPLERATE, int32(self.sample_rate))    # Setting the sample rate for the card
        
        
        #Read out actual samplerate and store that in memory
        self.regSrate = int64 (0)                                        # Although we request a certain value, it does not mean that this is what the machine is capable of. 
        spcm_dwGetParam_i64 (self.hCard, SPC_SAMPLERATE, byref (self.regSrate))    # We instead store the one the machine will use in the end.  
        self.sample_rate = self.regSrate
        
        
        # Setting the card channel
        allowed_num_channels = (1,2,4)
        
        if type(channel_enable)==int and 0<=channel_enable <=3:
            self.channel_enable =  uint64(2**channel_enable)
        
        elif len(channel_enable) in allowed_num_channels:
            channel_enable = np.array(channel_enable)
    
            if max(channel_enable)>3 or min(channel_enable)<0:
                sys.stdout.write("Available channels span from 0 to 3. Channel set to [0,1].")
                channel_enable = np.array([0,1])
            self.channel_enable =  uint64(np.sum(2**channel_enable))                                   # Sets the value for the channel to open.
        else:
            channel_enable = np.array([0,1])
            self.channel_enable = uint64(3)
            sys.stdout.write("Card can register 1, 2 or 4 active channels at any given time. Channels set to [0,1].\n")
       
        # Setting the card into sequence replay
        if num_segment > int(65536):
            sys.stdout.write("Total number of segments capped at: 65536")
            num_segment = int(65536)
        elif num_segment <int(2):
            sys.stdout.write("Number of segments smaller than minimum. Segments set to 2.")
            num_segment = int(2)
        self.num_segment = int(2**int(math.ceil(math.log(num_segment)/math.log(2))))
        if self.num_segment != num_segment:
             sys.stdout.write("...number of segments must be power of two.\n Segments have been set to nearest power of two:{0:d}\n".format(self.num_segment))
        
        # Setting the first step in sequence
        if start_step > int(4096):
            sys.stdout.write("Total number of steps capped at maximum value: 4096")
            start_step = int(4096)
        elif start_step <int(0):
            sys.stdout.write("Initialisation step must be a positive integer. Set to default value: 0")
            start_step = int(0)
        self.start_step = start_step
        
        
        
        spcm_dwSetParam_i32 (self.hCard, SPC_CARDMODE,        SPC_REP_STD_SEQUENCE)  # Sets to Sequence Replay. Check p.66 of manual for list of available modes. 
        spcm_dwSetParam_i64 (self.hCard, SPC_CHENABLE,         self.channel_enable)  # Selects the 1st Channel to open.
        spcm_dwSetParam_i32 (self.hCard, SPC_SEQMODE_MAXSEGMENTS, self.num_segment)  # The entire memory will be divided in this many segments. I don't think you can easily partition it. 
        spcm_dwSetParam_i32 (self.hCard, SPC_SEQMODE_STARTSTEP,    self.start_step)  # This is the initialising step for the run.
        
        
        # Store active channel and verify memory size per sample.
        lSetChannels = int32 (0)
        lBytesPerSample = int32 (0)
        spcm_dwGetParam_i32 (self.hCard, SPC_CHCOUNT,     byref (lSetChannels))      # Checks the number of currently activated channels.
        spcm_dwGetParam_i32 (self.hCard, SPC_MIINST_BYTESPERSAMPLE,  byref (lBytesPerSample)) # Checks the number of bytes used in memory by one sample. p.59 of manual for more info
        
        
        for i in channel_enable:
            spcm_dwSetParam_i32 (self.hCard, SPC_ENABLEOUT0 + int(i) * (SPC_ENABLEOUT1 - SPC_ENABLEOUT0),  int32(1)) # Selects Channel 0+X (ENABLEOUT0+X) and enables it (1). - The X stands for the addition of a fixed constant. SPC_ENABLEOUT0 == 30091. SPC_ENABLEOUT1 == 30191 etc
        
        
        self.lSetChannels = lSetChannels                                        # Creating an instance parameter
        self.lBytesPerSample = lBytesPerSample                                  # Creating an instance parameter
    
        
        self.totalMemory =4*1024**3                                                  # Total memory available to the card (4 Gb).
        self.maxSamples = self.totalMemory/self.lBytesPerSample.value/self.num_segment          # Maximum number of samples based for a given number of segments. 
        self.maxDuration = math.floor(self.maxSamples/self.sample_rate.value*1000)                          # Maximum segment duration for given segment size. Given in MILLIseconds
        
        """
        The following line determines the output of the card.
        """
        if AWG.max_output>282:
            sys.stdout.write("Maximum output exceeds damage threshold of amplifier. Value set to -1dBm (~282 mV)")
            AWG.max_output = round(math.sqrt(2*10**-3 * 50 *10 **(-1/10))*1000)
        for i in channel_enable:
            spcm_dwSetParam_i32 (self.hCard, SPC_AMP0 + int(i) * (SPC_AMP1 - SPC_AMP0), int32 (AWG.max_output))  # Selects Amplifier 0+X (SPC_AMP0+X) and enables it (1). - The X stands for the addition of a fixed constant. SPC_AMP0 == 30010. SPC_APM1 == 30110, etc..
        
        self.trig_val    = 1
        self.trig_level0 = 2000
        self.trig_level1 = 0
        
        spcm_dwSetParam_i32 (self.hCard, SPC_TRIG_ORMASK,      SPC_TMASK_SOFTWARE) # SPC_TMASK_SOFTWARE: this is the default value of the ORMASK trigger. If not cleared it will override other modes. 
        # spcm_dwSetParam_i32 (self.hCard, SPC_TRIG_ORMASK,               SPC_TMASK_NONE)  #You must remove the software trigger otherwise it overwrites
        # spcm_dwSetParam_i32 (self.hCard, SPC_TRIG_ORMASK,               SPC_TMASK_EXT0)  # Sets trigger to EXT0 (main trigger)
        # spcm_dwSetParam_i32 (self.hCard, SPC_TRIG_EXT0_LEVEL0,        self.trig_level0)  # Sets the trigger level for Level0 (principle level)
        # spcm_dwSetParam_i32 (self.hCard, SPC_TRIG_EXT0_LEVEL1,        self.trig_level1)  # Sets the trigger level for Level1 (ancilla level)
        # spcm_dwSetParam_i32 (self.hCard, SPC_TRIG_EXT0_MODE,  AWG.trig_mode[self.trig_val])  # Sets the trigger mode
        spcm_dwSetParam_i32 (self.hCard, SPC_TRIGGEROUT,                             0)
        
        ##################################################################
        ### Creating the flag condition to ensure that the card will initialise only if there are no issues.
        ##########################################################################################################
        
        self.flag = [0 for x in range(self.num_segment)]
        self.stepMultiplier = 2 
        self.stepFlag = [0 for x in range(self.stepMultiplier*self.num_segment)]  #It does not need to have the same number of steps. We simply allocate a multiplier to the number of possible segments you can have.
        
        
        #######################################
        ### Intermediate communication between segment data and step data for static traps
        #######################################################################################
        self.rounding = 1024
        self.statDur = 0.002             # Duration of a single static trap segment in MILLIseconds. Total duration handled by Loops.
        #self.effDur = math.floor(self.sample_rate.value * (self.statDur*10**-3)/self.rounding)*self.rounding/self.sample_rate.value*10**3
        #self.statDur = round(self.effDur,7)
        self.staticDuration = {}        # Keeps track of the requested duration for each static trap. Will be converted in setStep method.
        
        
        #######################################
        ### Setting up the folder for the card metadata storage
        ############################################################
        self.ddate =time.strftime('%Y%m%d')
        self.dirPath = 'Z:\Tweezer\Experimental\AOD\m4i.6622 - python codes\Sequence Replay tests\metadata_bin'
        
        self.path =  self.dirPath+'\\'+self.ddate
        if not os.path.isdir(self.path):
            os.makedirs(self.path)
        
        
        
        
        
        
    def __str__(self):
        ### Note: The functionL szTypeToName shown below is defined in the spcm_tools.py
        sCardName = szTypeToName (self.lCardType.value) # M4i.6622-x8. It just reads out the value from earlier. 
        sys.stdout.write("Found: {0} sn {1:05d}\n".format(sCardName,self.lSerialNumber.value))
        
    def setSampleRate(self,new_sampleRate):
        
        """
        Changing the sample rate will have to also change the effective segment size for the duration of static traps.
        As always, we store the sample rate that the card stores, not the one that we introduced.
        """
        self.stop()  # Ensure that the card is not outputting something.
        
        if new_sampleRate> MEGA(625):
            sys.stdout.write("Requested sample rate larger than maximum. Sample rate set at 625 MS/s")
            new_sampleRate = MEGA(625)
        self.sample_rate = new_sampleRate
        spcm_dwSetParam_i64 (self.hCard, SPC_SAMPLERATE, int32(self.sample_rate))    # Setting the sample rate for the card
               
        
        #Read out actual samplerate and store that in memory
        self.regSrate = int64 (0)                                                 # Registered sample rate: Although we request a certain value, it does not mean that this is what the machine is capable of. 
        spcm_dwGetParam_i64 (self.hCard, SPC_SAMPLERATE, byref (self.regSrate))    # We instead store the one the machine will use in the end.  
        self.sample_rate = self.regSrate
        
        self.maxDuration = math.floor(self.maxSamples/self.sample_rate.value*1000) 
        minVal = self.rounding/self.sample_rate.value*10**3
        self.setSegDur(minVal)
    
    def setNumSegments(self,num_segment):
        if num_segment > int(65536):
            sys.stdout.write("Total number of segments capped at: 65536")
            num_segment = int(65536)
        elif num_segment <int(2):
            sys.stdout.write("Number of segments smaller than minimum. Segments set to 2.")
            num_segment = int(2)
        self.num_segment = int(2**int(math.ceil(math.log(num_segment)/math.log(2))))
        if self.num_segment != num_segment:
             sys.stdout.write("...number of segments must be power of two.\n Segments have been set to nearest power of two:{0:d}\n".format(self.num_segment))
        
        spcm_dwSetParam_i32 (self.hCard, SPC_SEQMODE_MAXSEGMENTS, self.num_segment)  # The entire memory will be divided in this many segments. 
        
        """
        The maximum number of samples needs to be recalculated now.
        """
        self.totalMemory =4*1024**3                                                             # Total memory available to the card (4 Gb).
        self.maxSamples = self.totalMemory/self.lBytesPerSample.value/self.num_segment          # Maximum number of samples based for a given number of segments. 
        self.maxDuration = math.floor(self.maxSamples/self.sample_rate.value*1000)              # Maximum segment duration for given segment size. Given in MILLIseconds
        self.flag = [0 for x in range(self.num_segment)]                                       # Redefines the flag counters for when loading the DMA buffer.
        
        
        
    def setStartStep(self,start_step):
        # Setting the first step in sequence
        if start_step > int(4096):
            sys.stdout.write("Total number of steps capped at maximum value: 4096")
            start_step = int(4096)
        elif start_step <int(0):
            sys.stdout.write("Initialisation step must be a positive integer. Set to default value: 0")
            start_step = int(0)
        self.start_step = start_step
        
        spcm_dwSetParam_i32 (self.hCard, SPC_SEQMODE_STARTSTEP,    self.start_step)  # This is the initialising step for the run.
    
    
    def setTrigger(self,trig_val = 1,trig_level0=2500,trig_level1=0):
        """
        This method sets the trigger options.
        The assumption is that you will be using an external (non-software trigger).
        Where relevant, follow the following convention:
        --- Level0 corresponds to the LOWER level.
        --- Level1 corresponds to the UPPER level (ancilla level).
        
        NOTE: trig_mode has been as a dictionary at the start of the class as a class parameter. 
        """
        self.stop()  #Ensures that the card is stopped when changing the trigger. 
        flag =0
        
        if 0<=trig_val<=11:
            self.trig_val = trig_val
        else:
            sys.stdout.write("trig_val can take values between 0 and 11. Check global parameters for definitions.\n Set to default value: 1")
            self.trig_val =1
            flag =1
            
        if -10000 <= trig_level0 <= 10000:
            self.trig_level0  = trig_level0
        else:
            sys.stdout.write("trig_level0 can take values between +- 10000 mV. Value has been set to 2500 mV (default)")
            self.trig_level0 = 2500
            flag =1
        if -10000<= trig_level1 <= 10000:
            self.trig_level1  = trig_level1
        else:
            sys.stdout.write("trig_level0 can take values between +- 10000 mV. Value has been set to 0 mV (default)")
            self.trig_level1 = 0
            flag =1
        
        if flag==0:
            if self.trig_val==0:
                spcm_dwSetParam_i32 (self.hCard, SPC_TRIG_ORMASK,      SPC_TMASK_SOFTWARE) 
                spcm_dwSetParam_i32 (self.hCard, SPC_TRIGGEROUT,                                  0)
            else:    
                spcm_dwSetParam_i32 (self.hCard, SPC_TRIG_ORMASK,                    SPC_TMASK_NONE)  # IMPORTANT that you remove the software trigger explicitely otherwise it overwrites subsequent commands
                spcm_dwSetParam_i32 (self.hCard, SPC_TRIG_ORMASK,                    SPC_TMASK_EXT0)  # Sets trigger to EXT0 (main trigger)
                spcm_dwSetParam_i32 (self.hCard, SPC_TRIG_EXT0_LEVEL0,        int(self.trig_level0))  # Sets the trigger level for Level0 (principle level)
                spcm_dwSetParam_i32 (self.hCard, SPC_TRIG_EXT0_LEVEL1,        int(self.trig_level1))  # Sets the trigger level for Level1 (ancilla level)
                spcm_dwSetParam_i32 (self.hCard, SPC_TRIG_EXT0_MODE,   AWG.trig_mode[self.trig_val])  # Sets the trigger mode
                spcm_dwSetParam_i32 (self.hCard, SPC_TRIGGEROUT,                                  0)
        else:
            sys.stdout.write("New trigger has not been set due to unresolved issues.")
        
    def channelConfig(self,channel,state):
        """
        Selects a channel and either enables or disables it.
        """
        flag=0
        
        if 0<= channel <= 3:
            self.channel = channel
        else:
            sys.stdout.write("There are 4 channels, ranging from 0 to 3")
            flag =1
            
        if state ==1 or state ==0:
            self.state = state
        else:
            sys.stdout.write("The state of the channel can either be ON (1) or OFF (0).")
            flag =1
        
        if flag==0:
            spcm_dwSetParam_i64 (self.hCard, SPC_ENABLEOUT0+int(self.channel)*100, self.state)
    
    def setMaxOutput(self,new_maxOutput):
        """
        Sets the max output level in MILLIvolts
        """
                                                                       
        new_output =  new_maxOutput
        if new_output>282:
            sys.stdout.write("Maximum output exceeds damage threshold of amplifier. Value set to -1dBm (~282 mV)")
            new_output = round(math.sqrt(2*10**-3 * 50 *10 **(-1/10))*1000)
        
        for i in channel_enable:
            spcm_dwSetParam_i32 (self.hCard, SPC_AMP0+i*100, int32 (new_output))               # Sets the maximum output of the card for Channel 0.          
            
    def setSegDur(self,new_segDur):
        """
        Sets the size (duration) of the segment in static traps.
        This segment will be looped an appropriate number of times to achieve the requested value.
        """
        self.statDur = new_segDur
        # if 0.0016384 <= new_segDur: 
        #     self.statDur = new_segDur             # Duration of a single static trap segment in MILLIseconds. Total duration handled by Loops.
        #     self
        #     self.effDur = round(math.floor(self.sample_rate.value * (self.statDur*10**-3)/self.rounding)*self.rounding/self.sample_rate.value*10**3,7)
        #     self.statDur = round(self.effDur,7)
        # else:
        #     sys.stdout.write("Segment size must be between 0.0016384 and 0.1 ms. Set to minimum allowed by sample rate.")
        #     minVal = self.rounding/self.sample_rate.value*10**3
        #     self.effDur = round(math.floor(self.sample_rate.value * (minVal*10**-3)/self.rounding)*self.rounding/self.sample_rate.value*10**3,7)
        #     self.statDur = round(self.effDur,7)
        
    def selectSegment(self,selSeg):
        spcm_dwSetParam_i32(self.hCard, SPC_SEQMODE_WRITESEGMENT,selSeg)    
    
    def getParam(self,param =1):
        
        """
        This function receives only one value and depending
        on the value used it will return the output of a GET function
        for a particular parameter (samplerate, number of segments etc...)
        """
        
        switcher = {
        1:  "The sample rate of the card is:  {0:d} Hz.\n",                        # Samplerate of the card
        2:  "The number of segments on the card is: {0:d}.\n ",                    # Number of segments set on the card
        3:  "The starting step of the sequence is: {0:d}.\n ",                     # Initialisation step of the card
        4:  "The activated channel is: {0:d}.\n",                                  # Checks the activated number
        5:  "The number of activated channels is: {0:d}.\n ",                      # Checks how many channels are active
        6:  "The trigger Level0 for EXT0 is: {0:d} mV.\n ",                        # Checks what is the trigger level for Ext0
        7:  "The trigger Level1 for EXT0 is: {0:d} mV.\n ",                        # Checks what is the trigger level for Ext1
        8:  "The trigger mode for EXT0 is:.\n ",                                   # Checks the trigger mode for EXT0
        9:  "The segment chosen for modification is: {0:d}.\n",                    # Checks which segment is chosen to be modified
        10: "This segment contains {0:d} samples. \n" 
        }
        
        options = {
        1:  "Sample rate.",                       
        2:  "Number of segments currently on card.",                  
        3:  "First Step in sequence.",                    
        4:  "Activated channel.",                                
        5:  "The number of activated channels.",                      
        6:  "The trigger Level0 for EXT0 (mV).",                        
        7:  "The trigger Level1 for EXT0(mV).",                        
        8:  "The trigger mode for EXT0.",
        9:  "The segment chosen for modification.\n",      # Checks which segment is chosen to be modified
        10: "The number of samples in chosen segment. \n"                                    
        }
        
        if 1 < param <= len(switcher):    
            dummy = int32(0)
            spcm_dwGetParam_i32 (self.hCard, AWG.registers[param], byref(dummy))
            if spcm_dwGetParam_i32 (self.hCard, AWG.registers[param], byref(dummy)) ==0:
                self.dummy =dummy.value
                sys.stdout.write(switcher[param].format(self.dummy))
            else: 
                self.errVal = spcm_dwGetParam_i32 (self.hCard, AWG.registers[param], byref(dummy))
                sys.stdout.write("Parameter could not be retrieved. Error Code: {0:d}".format(self.errVal))
        
        else:
            sys.stdout.write("Register number is between 1 and {0:d}. The options are:\n".format(len(switcher)))
            for x in options:
                sys.stdout.write("{}: {}\n".format(x,options[x]))
        
    def setSegment(self,segment,*args):
        """
        This method is responsible for sending the data to the card to be played.
        If the method receives multiple datasets it will multiplex them as necessary.
        """
        flag =0
               
        if segment > self.num_segment -1:
            sys.stdout.write("The card has been segmented into {0:d} parts.\n".format(self.num_segment))
            flag =1
        else:
            self.segment = segment
            
        
        if len(args) == self.lSetChannels.value:
            """
            Check that the number of datasets 
            is equal to the number of activated channels
            """
            
            if len(args) != 1:
                """
                If there is more than one dataset, 
                check that data are of equal size
                """
                if lenCheck(args):
                    self.numOfSamples = int(len(args[0])) # number of samples
                else:
                    sys.stdout.write("Data are of unequal length. Check the data durations.")
                    flag =1
            else:
                """
                Single channel case
                """
                self.numOfSamples = len(args)
        else:
            sys.stdout.write("Number of datasets does not match number of activated channels.")
            flag =1
               
            
            
        if flag==0:
            
            spcm_dwSetParam_i32(self.hCard, SPC_SEQMODE_WRITESEGMENT,self.segment)
            spcm_dwSetParam_i32(self.hCard, SPC_SEQMODE_SEGMENTSIZE, self.numOfSamples)

            # setup software buffer
            
            qwBufferSize = uint64 (self.numOfSamples * self.lBytesPerSample.value * self.lSetChannels.value) # Since we have only once active channel, and we want 64k samples, and each sample is 2bytes, then we need qwBufferSize worth of space.
            # we try to use continuous memory if available and big enough
            pvBuffer = c_void_p () ## creates a void pointer -to be changed later.
            qwContBufLen = uint64 (0)
            spcm_dwGetContBuf_i64 (self.hCard, SPCM_BUF_DATA, byref(pvBuffer), byref(qwContBufLen)) #assigns the pvBuffer the address of the memory block and qwContBufLen the size of the memory.
            #######################
            ### Diagnostic comments
            #######################
            #sys.stdout.write ("ContBuf length: {0:d}\n".format(qwContBufLen.value))
            if qwContBufLen.value >= qwBufferSize.value:
                sys.stdout.write("Using continuous buffer\n")
            else:
                pvBuffer = pvAllocMemPageAligned (qwBufferSize.value) ## This now makes pvBuffer a pointer to the memory block. (void types have no attributes, so it is better to think that it points to the block and not individual sample)
                #######################
                ### Diagnostic comments
                #######################
                #sys.stdout.write("Using buffer allocated by user program\n")
            
            # calculate the data
            pnBuffer = cast  (pvBuffer, ptr16) #this now discretises the block into individual 'memory boxes', one for each sample.
            
            
            #########
            # Setting up the data memory for segment X
            #######################################################
            
            if len(args) != 1:
                multi = multiplex(args)
            else:
                multi = args
            
             
        
            #############
            # Set the buffer memory
            ################################# 
            for i in range (0, int(self.lSetChannels.value*self.numOfSamples), 1):
                
                pnBuffer[i] = int16(int(multi[i]))
        
        self.flag[self.segment] = flag
        if flag==0:
            # we define the buffer for transfer and start the DMA transfer
            ###
            ####sys.stdout.write("Starting the DMA transfer and waiting until data is in board memory\n")
            ###
            spcm_dwDefTransfer_i64 (self.hCard, SPCM_BUF_DATA, SPCM_DIR_PCTOCARD, int32 (0), pvBuffer, uint64 (0), qwBufferSize)
            spcm_dwSetParam_i32 (self.hCard, SPC_M2CMD, M2CMD_DATA_STARTDMA | M2CMD_DATA_WAITDMA)
            sys.stdout.write("... segment number {0:d} has been transferred to board memory\n".format(segment))
            sys.stdout.write(".................................................................\n")
        
        else:
            sys.stdout.write("Card segment number {0:d} was not loaded due to unresolved errors\n".format(self.segment))
        
        
    
    def dataGen(self, segment, action, duration, *args):
        """
        segment : This is a redundant variable to the program, will be used for the metadata file. 
                  Limited by number of segments on the card.
        action  : type of action taken (static, moving, ramp, amplitude modulation )
        duration: duration (MILLIseconds) of the data placed in the card. Limited by number of segments on the card.
        args    : these are action specific both in number and meaning. They are detailed further below for each action individually.      
                
        """
        
        flag =0
        
        
        if segment > self.num_segment -1:
            sys.stdout.write("The card has been segmented into {0:d} parts.\n".format(self.num_segment))
            flag =1
        else:
            self.segment = segment
        
        """
        The following line is useful for when changes to the card data are done dynamically.
        It is possible that you change a segment from static to ramp.
        Even if you re-run the setStep, that segment might have some record of number of loops
        associated to it (from the static trap) resulting in incorrect number of loops. 
        This will then lead to an incorrect number of segment repetitions.
        For this reason, it is better to clean the staticDuration var if that segment
        is represented. This just drops the key from the dictionary.
        """
        if self.segment in self.staticDuration.keys():
            del self.staticDuration[self.segment]
        
        """
        In the duration bloc that follows, it is important that the if action==1 step
        occurs here, as this will also determine the size of the buffer memory.
        """
        
        if action == 1:                                            # If the action taken is a static trap, then register the desired value, and ascribe self.statDur to the segment.
            self.staticDuration[self.segment] = duration           # Writes down the requested duration for a static trap in a dictionary (__init__)
            self.duration = self.statDur
        
        elif action == 4:
            
            expectedbytes = round(self.sample_rate.value * (duration*10**-3)/self.rounding)
            if expectedbytes <1:
                expectedbytes =1
            expectedSamples = int(expectedbytes*self.rounding)
            
            """
            if you want to loop
            NOTE: This will change the total duration. The following function ensures the same number of cyles. 
    
            """
            #self.staticDuration[self.segment] = duration           # Adds requested duration in the register for the setLoop function to see
            #if 0< 1./KILO(args[5]) <= self.maxDuration:
            #    self.duration = 1./KILO(args[5]) *1e3             # The duration is converted into [MILLIseconds]
            
            """
            if you don't want to loop the amplitude modulation.
            """
            if 0< duration <= self.maxDuration:
                self.duration = duration
            

            
        elif 0< duration <= self.maxDuration:
            self.duration = duration
            
        else:
            sys.stdout.write("Duration must be between 0 and %.3g ms when using %s segments. \n"%(self.maxDuration,self.num_segment))
            sys.stdout.write("Segment size has been set to maximum.")
            self.duration = self.maxDuration
        
        
        memBytes =round(self.sample_rate.value * (self.duration*10**-3)/self.rounding) #number of bytes as a multiple of kB - FLOOR function for static traps
        
        
        if memBytes <1:
            """
            This is because certain combination of sample rates vs segment sizes for the static
            trap, might creates values like this: 0.999990234, which rounded down will give zero.
            This is to ensure that python numerics do not interfere. 
            """
            memBytes=1
            
        self.numOfSamples = int(memBytes*self.rounding) # number of samples
        

        
        actionOptions = {
            1:  "Creates a series of static traps.",                       
            2:  "Performs a move operation from freq1 to freq2.",                  
            3:  "Ramps freq1 from X% to Y% amplitude (increasing or decreasing)",
            4:  "Creates a static trap with a given amplitude modulation frequency and depth."                                                            
            }
        
        freqBounds=[120,225]
        
        
        
        
        #####################################################################
        # STATIC TRAPS
        #####################################################################
        
        if action == 1:
            """
            Generating static traps
            
            """
            staticOptions = {
            1:  "Starting Frequency [MHz].",                       
            2:  "Number of traps [integer].",                  
            3:  "Distance between traps [um].",
            4:  "Total Frequency Amplitude [mV]",
            5:  "Individual Freqency amplitudes [fraction of total amplitude]",
            6:  "Individual Frequency phase   [deg]" ,
            7:  "Frequency Adjustment  [True/False]",
            8:  "Amplitude Adjustment [True/False]"                                                          
            }
            
            
            
            if len(args)==len(staticOptions):
            
                f1         = args[0]
                numOfTraps = args[1] 
                distance   = args[2]
                tot_amp    = args[3]
                freq_amp   = args[4]
                freq_phase = args[5]
                fAdjust    = args[6]
                aAdjust    = args[7] 
                
                if type(f1) == str:
                    """
                    This is only to allow a cosmetic data storage in the JSON file.
                    """
                    f1 = eval(f1)
                
                ##############
                # In case argument is a list
                ######################################   
                if type(f1) == list or type(f1)==np.ndarray:
                    """
                    In case the user wants to place its own arbitrary frequencies, this will test
                    whether the frequencies are within the AOD bounds. 
                    """
                    minFreq = min(f1)
                    maxFreq = max(f1)
                    if minFreq >= freqBounds[0] and maxFreq <= freqBounds[1]:
                        if type(f1) == list:
                            self.f1 = MEGA(np.array(f1))
                        else:
                            self.f1 = MEGA(f1)
                        numOfTraps = len(self.f1)
                        
                    else:
                        sys.stdout.write("One of the requested frequencies is out the AOD bounds ({} - {} MHz).".format(minFreq,maxFreq))
                        self.f1 = MEGA(170)
                        flag =1

                else:   
                    if  freqBounds[0] <= f1+(numOfTraps-1)*distance/AWG.umPerMHz <= freqBounds[1]:
                        self.f1 = MEGA(f1)
                    else:
                        sys.stdout.write("Chosen starting frequency is out of the AOD frequency range. Value defaulted at 170 MHz")
                        self.f1 = MEGA(170)
                        flag =1
                    
                if 2 <= tot_amp <= 282:
                    self.tot_amp = tot_amp
                else:
                    sys.stdout.write("Chosen amplitude will damage the spectrum analyser.")
                    self.tot_amp = 50
                
                """
                The following two lines that convert the input into an expression 
                were created with a cosmetic idea in mind.
                The values stored as a list will be converted in a large column in JSON (when/if exported)
                whereas a string file will remain more compact.
                This just enables the flexibility of typing an actual list or loading a string from a file. 
                """
                if type(freq_amp)==str:
                    freq_amp = eval(freq_amp)
                if type(freq_phase)==str:
                    freq_phase = eval(freq_phase)
                    
                if abs(max(freq_amp)) <= 1 and len(freq_amp)==numOfTraps:
                    self.freq_amp = freq_amp
                elif abs(max(freq_amp))> 1:
                    sys.stdout.write("Amplitudes must only contain values between 0 and 1.\n")
                    self.freq_amp = [1]*numOfTraps
                    flag =1
                elif len(freq_amp) != numOfTraps:
                    sys.stdout.write("Number of amplitudes does not match number of traps.\n")
                    self.freq_amp = [1]*numOfTraps
                    flag = 1
                    
                if len(freq_phase)==numOfTraps:
                    self.freq_phase = freq_phase
                
                elif len(freq_phase) != numOfTraps:
                    sys.stdout.write("Number of phases does not match number of traps.\n")
                    self.freq_phase = [0]*numOfTraps
                    flag = 1
                
                if type(fAdjust) != bool:
                    sys.stdout.write("Frequency Adjustment is not a boolean.\n")
                    self.fAdjust = True
                    flag = 1
                else:
                    self.fAdjust = fAdjust
                    self.exp_freqs = self.f1
                    
                if type(aAdjust) != bool:
                    sys.stdout.write("Amplitude Adjustment is not a boolean.\n")
                    self.aAdjust = True
                    flag = 1
                else:
                    self.aAdjust = aAdjust
                
               
                self.exp_freqs = getFrequencies(action,self.f1,numOfTraps,distance,self.duration,self.fAdjust,self.sample_rate.value,AWG.umPerMHz)
                
                
                
                
                ##############
                #  Generate the Data
                #########################
                outData =  static(self.f1,numOfTraps,distance,self.duration,self.tot_amp,self.freq_amp,self.freq_phase,self.fAdjust,self.aAdjust,self.sample_rate.value,AWG.umPerMHz)            # Generates the requested data
                
                if type(f1)==np.ndarray or type(f1)==list :
                    f1 = str(list(f1))
                dataj(self.filedata,self.segment,action,duration,f1,numOfTraps,distance,self.tot_amp,str(self.freq_amp),str(self.freq_phase),str(self.fAdjust),str(self.aAdjust),str(self.exp_freqs),self.numOfSamples)                # Stores information in the filedata variable, to be written when card initialises. 
            
            
                         
                
            else: 
                sys.stdout.write("Static trap ancilla variables:\n")
                for x in staticOptions:
                    sys.stdout.write("{}: {}\n".format(x,staticOptions[x]))
                sys.stdout.write("\n")
                flag =1
        
        #####################################################################
        # MOVING TRAPS
        #####################################################################
        
        
        elif action == 2:
            """
            Generating moving traps
            moving(startFreq, endFreq,duration,a,tot_amp,startAmp,endAmp,freq_phase,freq_adjust,amp_adjust,sampleRate)
            """
            moveOptions = {
            1:  "Starting Frequency [MHz].",                       
            2:  "Ending Frequency [MHz].",                
            3:  "Hybridicity a [a=0: fully minimum jerk, a=1: fully linear].",
            4:  "Total amplitude [mV]",
            5:  "Individual starting frequency amplitudes [fraction of total amplitude]",
            6:  "Individual starting frequency amplitudes [fraction of total amplitude]",
            7:  "Individual Frequency phase   [deg]" ,
            8:  "Frequency Adjustment  [True/False]" ,
            9:  "Amplitude Adjustment  [True/False]"      
            }
            
            if len(args)==len(moveOptions):
                f1         = args[0]     # Starting frequency
                f2         = args[1]     # End Frequency
                a          = args[2]     # Hybridicity (a= 0 -> min jerk, a =1 -> linear )
                tot_amp    = args[3]     # Global amplitude control
                start_amp  = args[4]     # Invididual frequency amplitude control
                end_amp    = args[5]     # Invididual frequency amplitude control
                freq_phase = args[6]     # Individual frequency phase control
                fAdjust    = args[7]     # Boolean for frequency control
                aAdjust    = args[8]     # Boolean for amplitude control
                                       
                ###########################
                # Standarising the input into np.ndarrays
                ###########################################
                if type(f1 )== int or type(f1) == float:
                    f1 =  np.array([f1])
                if type(f2 )== int or type(f2) == float:
                    f2 =  np.array([f2])
                # The following lines might appear redundant,but note that it is np.array() and not np.array([]) as above.
                # The reason for the distinction is that the input still has a length even if you introduce a single value.
                # This will not have an effect if the input is already an np.ndarray().
                f1 =  np.array(f1)
                f2 =  np.array(f2)
                
                ################################
                # Check that the frequencies requested are within bounds.
                ####################################
                if freqBounds[0] <= min(f1) and max(f1) <= freqBounds[1]:
                    self.f1 = MEGA(f1)
                else:
                    sys.stdout.write("Start frequencies contain values out of AOD bounds [{} - {}].".format(freqBounds[0],freqBounds[1]))
                    flag = 1
                    
                if freqBounds[0] <= min(f2) and max(f2) <= freqBounds[1]:
                    self.f2 = MEGA(f2)
                else:
                    sys.stdout.write("End frequencies contain values out of AOD bounds [{} - {}].".format(freqBounds[0],freqBounds[1]))
                    flag = 1
                
                ##########################
                # Check that start and end frequencies are of equal length
                ###################################################################
                if len(f1) != len(f2):
                    sys.stdout.write("Start and End frequencies are of unequal length.")
                    flag =1
                
                #############################
                # Check that hybridicity is adequate
                ########################################    
                if 0 <= a <= 1:
                    self.a  = a
                else:
                    sys.stdout.write("Hybridicity parameter must lie between 0 (Min Jerk) and 1 (linear)")
                    flag =1
                    
                if 2<= tot_amp<= 282:
                    self.tot_amp = tot_amp
                else:
                    self.tot_amp = 120
                    sys.stdout.write("Maximum output voltage is 282 mV or -1 dBm. Set to 120 mV (Safe with Spec.Analyser).")
                    flag = 1
                
                ##############################
                # Check that individual frequency amp and phases are confirming
                ########################################################################
                if type(start_amp) == list:
                    self.start_amp = start_amp
                else:
                    self.start_amp = [1]*len(f1)
                    sys.stdout.write("Frequency amplitudes must be list.")
                    flag = 1
                    
                if type(end_amp) == list:
                    self.end_amp = end_amp
                else:
                    self.end_amp = [1]*len(f1)
                    sys.stdout.write("Frequency amplitudes must be list.")
                    flag = 1
                
                if type(freq_phase) == list:
                    self.freq_phase = freq_phase
                else:
                    self.freq_phase = [0]*len(f1)
                    sys.stdout.write("Phase must be list of lenght 2, i.e. [1,1]")
                    flag = 1
                
                ############################
                # Check that frequency and amplitude adjustment is boolean.
                #############################################################
                if type(fAdjust) == bool:
                    self.fAdjust = fAdjust
                else:
                    self.fAdjust = True
                    sys.stdout.write("Frequency Adjustment receives a boolean True/False")
                    flag = 1
                    
                if type(aAdjust) == bool:
                    self.aAdjust = aAdjust
                else:
                    self.aAdjust = True
                    sys.stdout.write("Amplitude Adjustment receives a boolean True/False")
                    flag = 1
                
                
                self.exp_start,self.exp_end = getFrequencies(action,self.f1,self.f2,self.duration,self.fAdjust,self.sample_rate.value)
                    
                
                if flag ==0:
                    outData =  moving(self.f1,self.f2,self.duration,self.a,self.tot_amp,self.start_amp,self.end_amp,self.freq_phase,self.fAdjust,self.aAdjust,self.sample_rate.value)
                    dataj(self.filedata,self.segment,action,self.duration,str(f1),str(f2),self.a,self.tot_amp,str(self.start_amp),str(self.end_amp),str(self.freq_phase),str(self.fAdjust),str(self.aAdjust),\
                    str(list(self.exp_start)),str(list(self.exp_end)),self.numOfSamples)
             

                
                
                
            else:
                sys.stdout.write("Moving trap ancilla variables:\n")
                for x in moveOptions:
                    sys.stdout.write("{}: {}\n".format(x,moveOptions[x]))
                sys.stdout.write("\n")
                flag =1
        
        #####################################################################
        # RAMPED TRAPS - ACTION 3
        #####################################################################
        
        
        elif action ==3:
            """
            Generating ramping of traps
            ramp(freqs=[170e6],numberOfTraps=4,distance=0.329*5,duration =0.1,tot_amp=220,startAmp=[1],endAmp=[0],freq_phase=[0],freqAdjust=True,ampAdjust=True,sampleRate = 625*10**6,umPerMHz =0.329)
            """
            rampOptions = {
            1:  "Frequency(ies) to be ramped [MHz].",
            2:  "Number of traps",
            3:  "Distance between traps",
            4:  "Global amplitude control [mV] up to a value 282" ,                     
            5:  "Individual amplitude(s) at start of ramp [fraction of total amplitude] (0 to 1).",                  
            6:  "Individual amplitude(s) at end of ramp   [fraction of total amplitude] (0 to 1)." ,
            7:  "Individual phase(s) for each frequency used [deg]",
            8:  "Frequency Adjustment  [True/False]",
            9:  "Amplitude adjustment [True/False]"                                                           
            }
            
            if len(args)==len(rampOptions):
                
                f1         = args[0]
                numOfTraps = args[1] 
                distance   = args[2]
                tot_amp    = args[3]
                startAmp   = args[4]
                endAmp     = args[5]
                freq_phase = args[6]
                fAdjust    = args[7]
                aAdjust    = args[8]
                
                if numOfTraps <= 0:
                    numOfTraps = 1
                    sys.stdout.write("Number of traps must be a positive integer.")
                    
                if type(f1) == list or type(f1)==np.ndarray:
                    """
                    In case the user wants to place its own arbitrary frequencies, this will test
                    whether the frequencies are within the AOD bounds. 
                    """
                    minFreq = min(f1)
                    maxFreq = max(f1)
                    if minFreq >= freqBounds[0] and maxFreq <= freqBounds[1]:
                        if type(f1) == list:
                            self.f1 = MEGA(np.array(f1))
                        else:
                            self.f1 = MEGA(f1)
                        numOfTraps = len(self.f1)
                        
                    else:
                        sys.stdout.write("One of the requested frequencies is out the AOD bounds ({} - {} MHz).".format(minFreq,maxFreq))
                        self.f1 = MEGA(170)
                        flag =1

                else:   
                    if  freqBounds[0] <= f1+(numOfTraps-1)*distance/AWG.umPerMHz <= freqBounds[1]:
                        self.f1 = MEGA(f1)
                    else:
                        sys.stdout.write("Chosen starting frequency is out of the AOD frequency range. Value defaulted at 170 MHz")
                        self.f1 = MEGA(170)
                        flag =1
                
                if 2<= tot_amp<= 282:
                    self.tot_amp = tot_amp
                else:
                    self.tot_amp = 120
                    sys.stdout.write("Maximum output voltage is 282 mV or -1 dBm. Set to 120 mV (Safe with Spec.Analyser).")
                    flag = 1
                
                
                if  type(startAmp)==list and type(endAmp)==list and len(startAmp) ==len(endAmp):
                    self.startAmp = startAmp
                    self.endAmp   = endAmp
                else:
                    sys.stdout.write("Starting and ending amplitudes must lists of equal size, with values lying between 0 and 1.")
                    flag =1
                    
                if type(freq_phase) == list:
                    self.freq_phase = freq_phase
                else:
                    self.freq_phase = [0]*len(f1)
                    sys.stdout.write("Phase must be list of lenght 2, i.e. [1,1]")
                    flag = 1
                
                ############################
                # Check that frequency and amplitude adjustment is boolean.
                #############################################################
                if type(fAdjust) == bool:
                    self.fAdjust = fAdjust
                else:
                    self.fAdjust = True
                    sys.stdout.write("Frequency Adjustment receives a boolean True/False")
                    flag = 1
              
                if type(aAdjust) == bool:
                    self.aAdjust = fAdjust
                else:
                    self.aAdjust = True
                    sys.stdout.write("Amplitude Adjustment receives a boolean True/False")
                    flag = 1  
                    
                
                self.exp_freqs = getFrequencies(action,self.f1,numOfTraps,distance,self.duration,self.fAdjust,self.sample_rate.value,AWG.umPerMHz)
                
                
                
                if flag==0:
                    #ramp(freqs=[170e6],numberOfTraps=4,distance=0.329*5,duration =0.1,tot_amp=220,startAmp=[1],endAmp=[0],freq_phase=[0],freqAdjust=True,ampAdjust=True,sampleRate = 625*10**6,umPerMHz =0.329)
                    outData = ramp(self.f1,numOfTraps,distance,self.duration,self.tot_amp,self.startAmp,self.endAmp,self.freq_phase,self.fAdjust,self.aAdjust,self.sample_rate.value,AWG.umPerMHz)
                    dataj(self.filedata,self.segment,action,self.duration, str(f1),numOfTraps,distance,self.tot_amp,str(self.startAmp),str(self.endAmp),str(self.freq_phase),str(self.fAdjust),str(self.aAdjust),str(self.exp_freqs),self.numOfSamples)
                    
                
                        
                
                
            else:
                sys.stdout.write("Ramp trap ancilla variables:\n")
                for x in rampOptions:
                    sys.stdout.write("{}: {}\n".format(x,rampOptions[x]))
                sys.stdout.write("\n")
                flag =1
        
        ############################################################################
        # AMPLITUDE MODULATION - ACTION 4
        #############################################################################
        
        
        if action == 4:
            """
            Amplitude modulation of a static trap
            """
            ampModOptions = {
            1:  "Starting Frequency [MHz].",                       
            2:  "Number of traps [integer].",                  
            3:  "Distance between traps [um].",
            4:  "Total Frequency Amplitude [mV]",
            5:  "Individual Freqency amplitudes [fraction of total amplitude]",
            6:  "Amplitude modulation frequency [kHz]",
            7:  "Modulation depth [fraction (0 to 1)]",
            8:  "Individual Frequency phase   [deg]" ,
            9:  "Frequency Adjustment  [True/False]",
            10:  "Amplitude Adjustment [True/False]"                                                          
            }
            
            
            
            if len(args)==len(ampModOptions):
            
                f1         = args[0]
                numOfTraps = args[1] 
                distance   = args[2]
                tot_amp    = args[3]
                freq_amp   = args[4]
                mod_freq   = args[5]
                mod_depth  = args[6]
                freq_phase = args[7]
                fAdjust    = args[8]
                aAdjust    = args[9] 
                
                self.numOfModCycles = round(1.*expectedSamples/self.numOfSamples,2)  # Number of amplitude modulation cycles within the given duration.
                
                if type(f1) == str:
                    """
                    This is only to allow a cosmetic data storage in the JSON file.
                    """
                    f1 = eval(f1)
                
                ##############
                # In case argument is a list
                ######################################   
                if type(f1) == list or type(f1)==np.ndarray:
                    """
                    In case the user wants to place its own arbitrary frequencies, this will test
                    whether the frequencies are within the AOD bounds. 
                    """
                    minFreq = min(f1)
                    maxFreq = max(f1)
                    if minFreq >= freqBounds[0] and maxFreq <= freqBounds[1]:
                        if type(f1) == list:
                            self.f1 = MEGA(np.array(f1))
                        else:
                            self.f1 = MEGA(f1)
                        numOfTraps = len(self.f1)
                        
                    else:
                        sys.stdout.write("One of the requested frequencies is out the AOD bounds ({} - {} MHz).".format(minFreq,maxFreq))
                        self.f1 = MEGA(170)
                        flag =1

                else:   
                    if  freqBounds[0] <= f1+(numOfTraps-1)*distance/AWG.umPerMHz <= freqBounds[1]:
                        self.f1 = MEGA(f1)
                    else:
                        sys.stdout.write("Chosen starting frequency is out of the AOD frequency range. Value defaulted at 170 MHz")
                        self.f1 = MEGA(170)
                        flag =1
                    
                if 2 <= tot_amp <= 282:
                    self.tot_amp = tot_amp
                else:
                    sys.stdout.write("Chosen amplitude will damage the spectrum analyser.")
                    self.tot_amp = 50
                
                
                if 0 <= mod_freq <= 2000:
                    """
                    Ensures that the amplitude modulation frequency 
                    does not start approaching the trap frequency.
                    """
                    self.mod_freq = KILO(mod_freq)
                else:
                    sys.stdout.write("Amplitude modulation frequency must lie between 0 and 2000 kHz")
                    flag =1
                
                
                
                """
                The following two lines that convert the input into an expression 
                were created with a cosmetic idea in mind.
                The values stored as a list will be converted in a large column in JSON (when/if exported)
                whereas a string file will remain more compact.
                This just enables the flexibility of typing an actual list or loading a string from a file. 
                """
                if type(freq_amp)==str:
                    freq_amp = eval(freq_amp)
                if type(freq_phase)==str:
                    freq_phase = eval(freq_phase)
                    
                if abs(max(freq_amp)) <= 1 and len(freq_amp)==numOfTraps:
                    self.freq_amp = freq_amp
                elif abs(max(freq_amp))> 1:
                    sys.stdout.write("Amplitudes must only contain values between 0 and 1.\n")
                    self.freq_amp = [1]*numOfTraps
                    flag =1
                elif len(freq_amp) != numOfTraps:
                    sys.stdout.write("Number of amplitudes does not match number of traps.\n")
                    self.freq_amp = [1]*numOfTraps
                    flag = 1
                
                ###############################################################
                # Amplitude modulation
                ##################################################################
                AODlimiter = 220 #limiting AWG output for the AOD (after amplifier).
                maxAmp = max(self.freq_amp)  # finds the maximum of the individual amplitudes
                maxpos = self.freq_amp.index(maxAmp)
                if self.tot_amp *maxAmp* (1+mod_depth) <= 220:
                    self.mod_depth = mod_depth
                else:
                    sugDepth = round(AODlimiter/self.tot_amp/maxAmp -1,2)
                    sugTotAmp = round(AODlimiter/(1+mod_depth)/maxAmp,2)
                    sugfreqAmp = round(AODlimiter/(1+mod_depth)/self.tot_amp,2)
                    sys.stdout.write("For these values of tot_amp and mod_depth, the output of the card will exceed 220 mV.\n")
                    sys.stdout.write("Either change tot_amp to {} mV, mod_depth to {}, or freqAmp position {} to {}.\n".format(sugTotAmp,sugDepth,maxpos,sugfreqAmp))
                    flag =1    
                        
                    
            
                if len(freq_phase)==numOfTraps:
                    self.freq_phase = freq_phase
                
                elif len(freq_phase) != numOfTraps:
                    sys.stdout.write("Number of phases does not match number of traps.\n")
                    self.freq_phase = [0]*numOfTraps
                    flag = 1
                
                if type(fAdjust) != bool:
                    sys.stdout.write("Frequency Adjustment is not a boolean.\n")
                    self.fAdjust = True
                    flag = 1
                else:
                    self.fAdjust = fAdjust
                    self.exp_freqs = self.f1
                    
                if type(aAdjust) != bool:
                    sys.stdout.write("Amplitude Adjustment is not a boolean.\n")
                    self.aAdjust = True
                    flag = 1
                else:
                    self.aAdjust = aAdjust
                
               
                self.exp_freqs = getFrequencies(action,self.f1,numOfTraps,distance,self.duration,self.fAdjust,self.sample_rate.value,AWG.umPerMHz)
                
                
                
                
                ##############
                #  Generate the Data
                #########################
                
                if flag ==0:
                    outData =  ampModulation(self.f1,numOfTraps,distance,self.duration,self.tot_amp,self.freq_amp,self.mod_freq,self.mod_depth,self.freq_phase,self.fAdjust,self.aAdjust,self.sample_rate.value,AWG.umPerMHz)            # Generates the requested data
                    
                    if type(f1)==np.ndarray or type(f1)==list :
                        f1 = str(list(f1))
                    dataj(self.filedata,self.segment,action,duration,f1,numOfTraps,distance,self.tot_amp,str(self.freq_amp),int(self.mod_freq/1000),self.mod_depth,str(self.freq_phase),\
                    str(self.fAdjust),str(self.aAdjust),str(self.exp_freqs),self.numOfSamples,self.duration,self.numOfModCycles)                # Stores information in the filedata variable, to be written when card initialises. 
                
  
                         
                
            else: 
                sys.stdout.write("Static trap ancilla variables:\n")
                for x in staticOptions:
                    sys.stdout.write("{}: {}\n".format(x,ampModOptions[x]))
                sys.stdout.write("\n")
                flag =1
        
        
        
        
        
        
        
        
        
        
        
              
        ######################################################################
        # TRANSFER OF DATA
        ######################################################################                      
                
        self.flag[self.segment] = flag
        if flag==0:
            sys.stdout.write("... data for segment {0:d} has been generated.\n".format(segment))
        else:
            sys.stdout.write("Data for segment {} were not generated due to unresolved errors\n".format(self.segment))
        
        return outData
        
        
        
    def setStep(self,stepNum,segNum,loopNum,nextStep, stepCondition ):
        
        stepFlag = 0
        
        #######################
        # Determining which Step to define
        #####################################
        if stepNum > int(4096):
            sys.stdout.write("[Issue with first parameter]\n Maximum number of steps is: 4096")
            stepFlag =1
        else:
            self.lStep = int(stepNum)  
            
        #######################
        # Determining which segment will be associated to this step
        ##############################################################       
        if 0 <= segNum <= self.num_segment:
            self.llSegment = int(segNum) # segment associated with data memory 0
        else:
            sys.stdout.write("[Issue with second parameter]\n The segment number must be a positive integer smaller than: {}".format(self.num_segment))
            stepFlag=1

        #######################
        # Determining how many times a segment will loop before moving to the exit condition
        ########################################################################################   
        
        if self.llSegment in self.staticDuration.keys():
            """
            This IF function is added as a mechanic to allow cross-talk between the Segment data memory 
            and the segment step memory. For static traps it is best to allow the smallest possible duration
            (set by self.statDur) and loop them to create the desired duration. 
        
            The segment to be controlled must have been flagged as a 'static' trap (in self.staticDurations).
            The number of loops is determined as total duration divided by segment duration. 
            """
            
            loopNum = int(self.staticDuration[self.llSegment]/self.statDur)
        
        if 0 < loopNum <= 1048575:
            self.llLoop =    int(loopNum) # this should correspond to about 10 seconds
        else:
            sys.stdout.write("[Issue with third parameter]\n The total number of loops must be smaller than: 1048575\n")
            stepFlag=1    

        #######################
        # Determining which Step will follow after the current one
        ###########################################################        
        if 0 <= nextStep <= int(4096):
            if nextStep == stepNum:
                sys.stdout.write("Next step sequence is the same as this step.\n Will cause an infinitely looped segment unless dynamically changed.")
            self.llNext = int(nextStep) # initialisation step: the step the card starts at. Can be arbitrarily chosen.
        else:
            sys.stdout.write("[Issue with fourth parameter]\n Next step must be positive integer smaller than: 4096")
            stepFlag=1
    
        availStepOptions = {
        1:  "End sequence step upon trigger signal.",                       
        2:  "End sequence step immediately after loops are completed.",                  
        3:  "Terminate the sequence after this step."
        }
        
        if 0 < stepCondition <= len(AWG.stepOptions):
            self.llCondition = AWG.stepOptions[stepCondition] # Leave this step immediately after loop terminates.
        
        else:
             sys.stdout.write("Valid numbers are between 1 and {0:d}. The options are:\n".format(len(AWG.stepOptions)))
             stepFlag=1
             for x in availStepOptions:
                sys.stdout.write("{}: {}\n".format(x,availStepOptions[x]))
        
        self.stepFlag[self.llSegment] = stepFlag
        
        if stepFlag ==0:
            """
            If no errors were found:
                1. write the metadata into the file
                2. convert the information to card-readable values
                3. transfer the information to the card.  
            """
            stepj(self.filedata,self.lStep,self.llSegment,self.llLoop,self.llNext,stepCondition)
            llvals=int64((self.llCondition<<32) | (self.llLoop<<32) | (self.llNext<<16) | self.llSegment)
            spcm_dwSetParam_i64(self.hCard,SPC_SEQMODE_STEPMEM0 + self.lStep,llvals)

    
    def setDirectory(self,dirPath='Z:\Tweezer\Experimental\AOD\m4i.6622 - python codes\Sequence Replay tests\metadata_bin'):
        self.ddate =time.strftime('%Y%m%d')
        
        if type(dirPath)==str:
            self.path =  dirPath+'\\'+self.ddate
            if not os.path.isdir(self.path):
                os.makedirs(self.path)
        else:
            sys.stdout.write("Input must be a string.")
            
    # def saveData(self):
    #     """
    #     First the card outputs the metadata file
    #     Second, we set the name of the file based on the day and time.
    #     Create a directory if needed and output the file before initialising
    #     """
    #     paramj(self.filedata,self.sample_rate.value,self.num_segment,self.start_step,self.lSetChannels.value,self.lBytesPerSample.value,int(self.maxSamples),\
    #     self.max_output,self.trig_val,self.trig_level0,self.trig_level1,self.statDur)
    #     
    #     self.ddate =time.strftime('%Y%m%d')     # Date in YYMMDD format
    #     self.ttime =time.strftime('%H%M%S')     # Time in HHMMSS format
    #     self.fname = self.ddate+"_"+self.ttime  # File name in YYMMDD_HHMMSS format
    #     
    #     
    #     self.path =  self.dirPath+'\\'+self.ddate
    #     if not os.path.isdir(self.path):
    #         os.makedirs(self.path)
    #     
    #     with open(self.path+'\\'+self.fname+'.txt','w') as outfile:
    #         json.dump(self.filedata,outfile,sort_keys = True,indent =4)
            
    
    def saveData(self, fpath=''):
        """
        First the card outputs the metadata file
        Second, we set the name of the file based on the day and time.
        Create a directory if needed and output the file before initialising
        """
        paramj(self.filedata,self.sample_rate.value,self.num_segment,self.start_step,self.lSetChannels.value,self.lBytesPerSample.value,int(self.maxSamples),\
        self.max_output,self.trig_val,self.trig_level0,self.trig_level1,self.statDur)        
        
        if not fpath:
            self.ddate =time.strftime('%Y%m%d')     # Date in YYMMDD format
            self.ttime =time.strftime('%H%M%S')     # Time in HHMMSS format
            self.path = os.path.join(self.dirPath, self.ddate)
            os.makedirs(self.path, exist_ok=True)
            fpath = os.path.join(self.path, self.ddate+"_"+self.ttime+'.txt')
        try:
            with open(fpath,'w') as outfile:
                json.dump(self.filedata,outfile,sort_keys = True,indent =4)
        except (FileNotFoundError, PermissionError) as e:
            print(e)
    
    
    
    
    
    
    def load(self,file_dir='Z:\Tweezer\Experimental\AOD\m4i.6622 - python codes\Sequence Replay tests\metadata_bin\\20200706\\20200706_170438.txt'):
        
        """
        You need to stop the card if you want to load a new file.
        I have tried a dynamic 'partial load' but the card dislikes it and outputs nothing.
        Dynamically changing just the segment (using setSegment(*args) ) works immediately nonetheless.
        """
        self.stop()                                      
        
        with open(file_dir) as json_file:
            lfile = json.load(json_file)
        
        lsegments = lfile['segments']                       # segments to be loaded
        lsteps = lfile['steps']                             # steps to be loaded
        lprop = lfile['properties']['card_settings']      # card properties to be loaded
        segNumber = len(lsegments)                          # number of segments to be loaded
        stepNumber = len(lsteps)                            # number of steps to be loaded
        
        
        self.setSampleRate(lprop['sample_rate_Hz'])                                             # Sets the sample rate (this must be first as it sets the pace for a few important parameters                                                  
        self.setNumSegments(lprop['num_of_segments'])                                               # Sets the number of segments for the card
        self.setStartStep(lprop['start_step'])                                                      # Sets the value of the first step. Arbitrarily set, but 0 is the convention we use. 
        self.setMaxOutput(lprop['max_output_mV'])                                                   # Sets the maximum output of the card given in MILLIvolts
        self.setSegDur(lprop['static_duration_ms'] )                                                # Sets the size of the static segment to be looped
        self.setTrigger(lprop['trig_mode'],lprop['trig_level0_main'],lprop['trig_level1_aux'])      # Sets the trigger based on mode
        
        
       
        
        for i in range(segNumber):
            if lsegments['segment_'+str(i)]['action_val'] == 1:
                order = ('segment','action_val','duration','freqs_input','num_of_traps','distance','total_amp','freq_amp','freq_phase','freq_adjust','amp_adjust')
                arguments = [lsegments['segment_'+str(i)][x] for x in order]
            
            elif lsegments['segment_'+str(i)]['action_val'] == 2:
                order = ('segment','action_val','duration','start_freq','end_freq','static_freq',"hybridicity")
                arguments = [lsegments['segment_'+str(i)][x] for x in order]
            
            elif lsegments['segment_'+str(i)]['action_val'] == 3:
                order = ('segment','action_val','duration','ramped_freq','static_freq',"initial_amp",'final_amp')
                arguments = [lsegments['segment_'+str(i)][x] for x in order]
            
            data = self.dataGen(*arguments)
            self.setSegment(arguments[0], data)
            
        for i in range(stepNumber):
            
            stepOrder = ("step_value","segment_value","num_of_loops","next_step","condition")
            stepArguments = [lsteps['step_'+str(i)][x] for x in stepOrder]
            
            self.setStep(*stepArguments)
        
   
    def start(self,saveFile=False,save_path ="",timeOut = 10000):
        if sum(self.flag)==0 and sum(self.stepFlag)==0:
            
            if saveFile ==True and save_path=="":
                self.saveData()
            else:
                self.saveData(save_path)   
            spcm_dwSetParam_i32 (self.hCard, SPC_TIMEOUT, int(timeOut))
            sys.stdout.write("\nStarting the card and waiting for ready interrupt\n(continuous and single restart will have timeout)\n")
            dwError = spcm_dwSetParam_i32 (self.hCard, SPC_M2CMD, M2CMD_CARD_START | M2CMD_CARD_ENABLETRIGGER | M2CMD_CARD_WAITPREFULL)
            if dwError == ERR_TIMEOUT:
                spcm_dwSetParam_i32 (self.hCard, SPC_M2CMD, M2CMD_CARD_STOP)
        else:
            y=[]
            yStep=[]
            for x in range(self.num_segment):
                if self.flag[x]!=0:
                    y.append(x)
            for x in range(len(self.stepFlag)):
                if self.stepFlag[x]!=0:
                    yStep.append(x)
            sys.stdout.write("\n Card was not initialiased due to unresolved issues in segments {}\n".format(y))
            sys.stdout.write("\n Card was not initialiased due to unresolved issues in steps {}\n".format(yStep))
            
            
    
    def stop(self):
        spcm_dwSetParam_i32 (self.hCard, SPC_M2CMD, M2CMD_CARD_STOP)
    
    def restart(self):
        spcm_dwSetParam_i32 (self.hCard, SPC_M2CMD, M2CMD_CARD_STOP)
        spcm_vClose (self.hCard)
        
    def __del__(self):
        """close the reference to the card when the instance is closed"""
        self.restart() 
        sys.stdout.write("\n Card instance was closed. \n")
    
    def multiChannel(self,f1,f2,duration):
        
        if 20 <= f1 <= 220:
            self.f1 = MEGA(f1)
        else:
            sys.stdout.write("Frequency not within bounds (20-220 MHz)")
        
        if 20 <= f2 <= 220:
            self.f2 = MEGA(f2)
        else:
            sys.stdout.write("Frequency not within bounds (20-220 MHz)")
         
        if 0 in self.staticDuration.keys():
            del self.staticDuration[0] 
        if 1 in self.staticDuration.keys():
            del self.staticDuration[1] 
        #self.staticDuration[0] = duration         # Writes down the requested duration for a static trap in a dictionary (__init__)
        #self.duration = self.statDur
        self.duration = duration
        
        
        memBytes =round(self.sample_rate.value * (self.duration*10**-3)/self.rounding) #number of bytes as a multiple of kB - FLOOR function for static traps
        
        if memBytes <1:
            memBytes=1
        self.numOfSamples = int(memBytes*self.rounding) # number of samples
            
           
        qwChEnable = uint64 (CHANNEL1 | CHANNEL2)                                   # Opens channels 0 and 1
        spcm_dwSetParam_i32 (self.hCard, SPC_CARDMODE,        SPC_REP_STD_SEQUENCE)  # Sets to Sequence Replay. Check p.66 of manual for list of available modes. 
        spcm_dwSetParam_i64 (self.hCard, SPC_CHENABLE,                  qwChEnable)  # Selects the 1st Channel to open.
        spcm_dwSetParam_i32 (self.hCard, SPC_SEQMODE_MAXSEGMENTS, self.num_segment)  # The entire memory will be divided in this many segments. I don't think you can easily partition it. 
        spcm_dwSetParam_i32 (self.hCard, SPC_SEQMODE_STARTSTEP,   0)  # This is the initialising step for the run.
        
        
        # Store active channel and verify memory size per sample.
        lSetChannels = int32 (0)
        lBytesPerSample = int32 (0)
        spcm_dwGetParam_i32 (self.hCard, SPC_CHCOUNT,     byref (lSetChannels))      # Checks the number of currently activated channels.
        spcm_dwGetParam_i32 (self.hCard, SPC_MIINST_BYTESPERSAMPLE,  byref (lBytesPerSample)) # Checks the number of bytes used in memory by one sample. p.59 of manual for more info
        
        self.lSetChannels    = lSetChannels                                         # Creating an instance parameter
        self.lBytesPerSample = lBytesPerSample                                      # Creating an instance parameter
        
        for i in range (0, lSetChannels.value):
            spcm_dwSetParam_i32 (self.hCard, SPC_AMP1 + i * (SPC_AMP1 - SPC_AMP0), int32 (AWG.max_output))
            spcm_dwSetParam_i32 (self.hCard, SPC_ENABLEOUT1 + i * (SPC_ENABLEOUT1 - SPC_ENABLEOUT0),  int32(1))
        
        
        spcm_dwSetParam_i32(self.hCard, SPC_SEQMODE_WRITESEGMENT,0)
        spcm_dwSetParam_i32(self.hCard, SPC_SEQMODE_SEGMENTSIZE, self.numOfSamples)
        
        
        qwBufferSize = uint64 (self.numOfSamples * self.lBytesPerSample.value * self.lSetChannels.value) # We have TWO actived channels, and we want 64k samples, and each sample is 2bytes, then we need qwBufferSize worth of space.
        pvBuffer = c_void_p () ## creates a void pointer -to be changed later.
        qwContBufLen = uint64 (0)
        spcm_dwGetContBuf_i64 (self.hCard, SPCM_BUF_DATA, byref(pvBuffer), byref(qwContBufLen)) #assigns the pvBuffer the address of the memory block and qwContBufLen the size of the memory.
       
       
        if qwContBufLen.value >= qwBufferSize.value:
            sys.stdout.write("Using continuous buffer\n")
        else:
            pvBuffer = pvAllocMemPageAligned (qwBufferSize.value) ## This now makes pvBuffer a pointer to the memory block. (void types have no attributes, so it is better to think that it points to the block and not individual sample)
        
        # calculate the data
        pnBuffer = cast  (pvBuffer, ptr16) #this now discretises the block into individual 'memory boxes', one for each sample.
        
        staticData1 =  moving([self.f1], [self.f1],self.duration,1,220,[1],[1],[0],False,False,self.sample_rate.value)#static([self.f1],1,1,self.duration,220,[1],[0],False,False,self.sample_rate.value,AWG.umPerMHz)            # Generates the requested data
        staticData2 =  moving([self.f1], [self.f1],self.duration,1,220,[1],[0],[0],False,False,self.sample_rate.value) # static([self.f2],1,1,self.duration,220,[1],[0],False,False,self.sample_rate.value,AWG.umPerMHz)           # Generates the requested data
        
        
        multi = multiplex(staticData1,staticData2) 
        
        #############
        # Set the buffer memory
        ################################# 
        for i in range (0, int(self.lSetChannels.value*self.numOfSamples), 1):
            
            pnBuffer[i] = int16(int(multi[i]))
        
        
        spcm_dwDefTransfer_i64 (self.hCard, SPCM_BUF_DATA, SPCM_DIR_PCTOCARD, int32 (0), pvBuffer, uint64 (0), qwBufferSize)
        spcm_dwSetParam_i32 (self.hCard, SPC_M2CMD, M2CMD_DATA_STARTDMA | M2CMD_DATA_WAITDMA)
        sys.stdout.write("... segment number {0:d} has been transferred to board memory\n".format(0))
        sys.stdout.write(".................................................................\n")
        
        
        

def rep(freq,srate):
    t.setSampleRate(MEGA(srate))
    t.setSegment(0,1,0.12,freq,1,0.329*4,20,[1],[0])
    t.start()
   
if __name__ == "__main__":
    
    t = AWG([1,2])
    t.setNumSegments(8)
    print(t.num_segment)
    print(t.maxDuration)
    # 0.329um/MHz
    # setup trigger and segment duration
    t.setTrigger(0) # 0 software, 1 ext0
    t.setSegDur(0.002)
   
    """11/08/2020 vincent 
    test parametric heating using AOD
        1. 1 Static trap @ 166MHz, 110mV until trigger
        2. Then modulate at x kHz for 100ms, then automatically return to 1 static trap"""
         
    
    #t.setSegment(0,1,0.02,[158,174],1,9, 220,[1,1],[0,0],False,False)
    #t.setSegment(1,4,50, [1158,174],1,9, 110,[1,1],137,0.05,[0,0],False,False)  
    # t.setStep(0,0,1,1,1)  
    # t.setStep(1,1,1,0,2)
    
    data01 = t.dataGen(0,1,0.02,[166],1,9, 220,[1],[0],False,False)
    data02 = t.dataGen(0,1,0.02,[180],1,9, 220,[1],[0],False,False)
    t.setSegment(0,data01,data02)
    
    
        
          
    # t.start(True)
    
    
    
    # 
    # ### STATIC/RAMP
    # # action/freq/num of traps/distance/duration/freq Adjust/sample rate/umPerMhz
    # getFrequencies(1,135e6,5,3,1,True,625e6,0.329)*10**-6 #static
    # getFrequencies(1,[135e6,170e6,220e6],5,3,1,True,625e6,0.329)*10**-6
    # 
    # ## MOVING
    # # action/freq/num of traps/distance/duration/freq Adjust/sample rate/umPerMhz
    # getFrequencies(2,[135e6],[200e6],1,True,625e6)*10**-6 #moving

