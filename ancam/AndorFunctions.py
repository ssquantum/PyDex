"""
21/08/2019 Vincent Brooks
  * Python library of functions for controlling the Andor iXon 897 Ultra imaging camera.
    Based off the pyAndor code by Hamid Ohadi : https://github.com/hamidohadi/pyandor
    and the beta version of the Python SDK sent from Andor.

  * This module should serve only as a library for the simplest functions used
    to program the Andor camera. More complicated functions should be constructed
    in a separate script by importing this one.

  * Note on function syntax: The SDK is written in C. This module is a Python 
    wrapper for the C SDK. Each of the functions here basically translate the Pythonic
    input to one of the SDK functions into C and the C output back into Python.

  * The C functions are stored in a .dll file which is installed with the SDK and 
    in Solis.

  * The module ctypes is used to construct C variable types in Python, since you
    need to be specific in C. Each function also has an 'error'. This is a code which is 
    automatically returned from the camera whenever you send it a command. This 
    code corresponds to a status which can be found in the SDK manual. There is a
    dictionary at the bottom of this module which is used to convert error codes
    to meanings.
"""

import platform        # Can return information about the computer's operating system.
from ctypes import *   # Used to read and define C variables in Python.
import sys
import numpy as np

# Ctype files stored here: C:\Users\Lab\AppData\Local\Enthought\Canopy\App\appdata\canopy-2.1.9.3717.win-x86_64\Lib\ctypes

class Andor:
    """Class containing a library of functions for operating the Andor camera.
       """
    
    def __init__(self):
        super().__init__() # required for multiple inheritence
        self.OS = platform.system()
        self.architecture = platform.architecture()[0]

        self.dll = cdll.LoadLibrary(name="C:\Program Files\Andor SDK\\atmcd64d")
    
        self.verbosity      = True      # Amount of information to display when debugging
        self.coolerStatus   = None       # Cooler on (1) or off (0)?
        
        self.outamp         = None      # Output amplifier mode.
        self.gain           = None      # EMCCD gain value
        self.preampgain     = None      # preampgain value
        
        self.noADChannels   = None      # Number of analogue-to-digital channels in SDK
        self.channel        = None      # Index of channel we're using.
        
        self.noHSSpeeds     = None      # Number of horizontal shift speeds
        self.HSSpeeds       = None      # List of horizontal shift speeds available
        self.hsspeed        = None      # Index of current horizontal shift speed
        
        self.noVSSpeeds     = None      # Number of horizontal shift speeds
        self.VSSpeeds       = None      # List of horizontal shift speeds available
        self.vsspeed        = None      # Index of current vertical shift speed
        
        self.ReadMode       = None      # The readout mode used in acquisitions. We want 4: Image.
        self.exposure       = None      # Exposure time currently set
        self.accumulate     = None      # Accumulate time currently set
        self.kinetic        = None      # Kinetic cycle time currently set
        
        self.DetectorWidth  = None      # Width and height of the detector
        self.DetectorHeight = None      # Height of the detector
        
        self.hbin           = None      # Horizontal binning
        self.vbin           = None      # Vertical binning
        self.hstart         = None      # Horizontal pixel coordinate of acquisition region start
        self.hend           = None      # Horizontal pixel coordinate of acquisition region end
        self.vstart         = None      # Vertical pixel coordinate of acquisition region start
        self.vend           = None      # Vertical pixel coordinate of acquisition region end
        
        self.kscans          = None      # Number of kinetic scans

    def Initialize(self):
        '''Initialize the Andor camera'''
        tekst = c_char()  
        error = self.dll.Initialize(byref(tekst))
        self.verbose(error, sys._getframe().f_code.co_name)
        return error

    def verbose(self, errorcode, function=''):
        """Set verbosity of camera error outputs"""
        error = ERROR_CODE[errorcode]
        if self.verbosity:
            print("[%s]: %s" %(function, error))

    def ShutDown(self):
        """This function will close the AndorMCD system down."""
        error = self.dll.ShutDown()
        self.verbose(error, sys._getframe().f_code.co_name)
        return error

    def GetStatus(self):
        """Get the current status of the camera"""
        status = c_int()   # define an integer status
        error = self.dll.GetStatus(byref(status))    # access the dll library function 'Get status'
        self.status = ERROR_CODE[status.value]
        self.verbose(error, sys._getframe().f_code.co_name)
        return self.status
        
    def GetCameraSerialNumber(self):
        """Get the serial number of the camera.
           SN_microscope = 11783
           SN_tweezer = 11707"""
        serial = c_int()
        error = self.dll.GetCameraSerialNumber(byref(serial))
        self.serial = serial.value
        self.verbose(error, sys._getframe().f_code.co_name)
        return error

    def GetAvailableCameras(self):
        """Get the cameras which are currently available."""
        availableCameras = c_long()
        error = self.dll.GetCameraSerialNumber(byref(availableCameras))
        print(a)
        self.verbose(error, sys._getframe().f_code.co_name)
        return a
   
    def CoolerON(self):
        """Turn the cooler on"""
        error = self.dll.CoolerON()
        self.coolerStatus = 1
        self.verbose(error, sys._getframe().f_code.co_name)
        return error

    def CoolerOFF(self):
        """Turn the cooler off"""
        error = self.dll.CoolerOFF()
        self.coolerStatus = 0
        
        self.verbose(error, sys._getframe().f_code.co_name)
        return error

#    def IsCoolerOn(self):
#        """ NOTE THIS SEEMS BUGGED! ALWAYS RETURNS COOLER ON!
#            Check the status of the cooler
#                0: Cooler off
#                1: Cooler on """
#        iCoolerStatus = c_int()
#        error = self.dll.IsCoolerOn(byref(iCoolerStatus))
#        self.verbose(error, sys._getframe().f_code.co_name)
#        #self.coolerStatus = iCoolerStatus.value
#        print(iCoolerStatus.value)
#        return iCoolerStatus.value
    
    def SetCoolerMode(self, mode):
        """This function determines whether the cooler is switched off when 
           the camera is shut down.
           1: Temperature maintained on camera shutdown.
           0: Returns to ambient temperature on shutdown. """
        error = self.dll.SetCoolerMode(mode)
        self.verbose(error, sys._getframe().f_code.co_name)
        return error             

    def GetTemperatureF(self):
        """Get the current temperature (C) of the CCD as a float."""
        currentTemperature = c_float()
        error = self.dll.GetTemperatureF(byref(currentTemperature))
        self.verbose(error, sys._getframe().f_code.co_name)
        return(currentTemperature.value, error)
    
    def GetTemperature(self):
        """Get the current temperature (C) of the CCD as an integer to the 
           nearest degree."""
        currentTemperature = c_int()
        error = self.dll.GetTemperature(byref(currentTemperature))
        self.verbose(error, sys._getframe().f_code.co_name)
        return(currentTemperature.value, error)
               
    def SetTemperature(self, setpoint):
        """Set the setpoint temperature for the CCD in Celcius."""
        self.temperatureSetpoint = setpoint
        error = self.dll.SetTemperature(self.temperatureSetpoint)       
        self.verbose(error, sys._getframe().f_code.co_name)
        return error

    def GetTemperatureRange(self):
        """Return the range of temperatures (C) to which the atom can be cooled"""
        mintemp, maxtemp = c_int(), c_int()
        error = self.dll.GetTemperatureRange(byref(mintemp), byref(maxtemp))  
        self.verbose(error, sys._getframe().f_code.co_name)     
        print('cooler range: ', mintemp.value, maxtemp.value)        

    def SetShutter(self,typ,mode,closingtime=0,openingtime=0):
        """Controls both the internal shutter and the TTL output which goes 
           to an external shutter.
            typ: sets the TTL out to:
                0: low to open shutter
                1: high to open shutter
            mode: Controls the internal shutter.
                1: Permanently open
                2: Permanently closed
                Ignore 0, 4, 5
            closing time: external shutter close delay time
            opening time: external shutter open delay time  """
        error = self.dll.SetShutter(typ,mode,closingtime,openingtime)
        if mode == 2:
            self.shutterStatus = 0
        elif mode == 1:
            self.shutterStatus = 1
        self.verbose(error, sys._getframe().f_code.co_name)
        return error

    def SetTriggerMode(self, mode):
        ''' This function will set the trigger mode that the camera will operate in.
            mode:
                0 - internal
                1 - External
                6 - External Start
                7 - External Exposure (Bulb)
                9 - External FVB EM (only valid for EM Newton models in FVB mode)	
                10- Software Trigger
                12 - External Charge Shifting  '''
        cmode = c_int(mode)
        error = self.dll.SetTriggerMode(cmode)
        self.verbose(error, sys._getframe().f_code.co_name)
        return error

    def SetFastExtTrigger(self, mode):
        ''' Description:
            This function will enable fast external triggering. When fast 
            external triggering is enabled the system will NOT wait until a 
            Keep Clean cycle has been completed before accepting the next trigger. 
            Only works with trigger mode set to External.
            Mode: 
                0 - Off
                1 - On
        '''
        cmode = c_int(mode)
        error = self.dll.SetFastExtTrigger(cmode)
        self.verbose(error, sys._getframe().f_code.co_name)
        return error

    def SetPreAmpGain(self, PAG):
        """Set the pre-amp gain. The value can be 1, 2 or 3. 
           See the system booklet for what these correspond to."""        
        index = PAG - 1 # index goes 0,1,2. This corresponds to PAGs 1,2,3.
        error = self.dll.SetPreAmpGain(index)
        self.verbose(error, sys._getframe().f_code.co_name)
        self.preampgain = PAG
        return error

    def GetCurrentPreAmpGain(self):
        """Get the pre-amp gain the camera is currently set to."""
        cindex = c_int()
        cname = create_string_buffer(30)
        clen = c_int(30)
        error = self.dll.GetCurrentPreAmpGain(byref(cindex), byref(cname), clen)
        self.verbose(error, sys._getframe().f_code.co_name)
        self.preampgain = cindex.value + 1
            
    def GetEMCCDGain(self):
        """Get the current electron-multiplying gain setting."""
        gain = c_int()
        error = self.dll.GetEMCCDGain(byref(gain))
        self.gain = gain.value
        self.verbose(error, sys._getframe().f_code.co_name)
        return error
     
    def SetEMGainMode(self, gainMode=0):
        """Set the EMCCD Gain mode. 
            0: EM gain controlled by DAC in range 0-255 (default)
            1: EM gain controlled by DAC in range 0-4095
            2: Linear mode
            3: Real EM gain"""
        error = self.dll.SetEMGainMode(gainMode)
        self.verbose(error, sys._getframe().f_code.co_name)
        return error
        
    def SetEMCCDGain(self, gain):
        """Set the EMCCD gain value"""
        self.gain = gain
        error = self.dll.SetEMCCDGain(gain)
        self.verbose(error, sys._getframe().f_code.co_name)
        return error


    def SetOutputAmplifier(self, index=0):
        """Some EMCCD systems have the capability to use a second output amplifier. 
           This function will set the type of output amplifier to be used when reading 
           data from the head for these systems
            0: Standard EMCCD Gain register
            1: Conventional CCD register.        """
        error = self.dll.SetOutputAmplifier(index)
        self.verbose(error, sys._getframe().f_code.co_name)
        self.outamp = index
        return error

    def GetNumberADChannels(self):
        """As your Andor SDK system may be capable of operating with more than 
           one A-D converter, 
           this function will tell you the number available."""
        noADChannels = c_int()
        error = self.dll.GetNumberADChannels(byref(noADChannels))
        self.noADChannels = noADChannels.value
        self.verbose(error, sys._getframe().f_code.co_name)
        return error

    def SetADChannel(self, index=0):
        """This function will set the AD channel to one of the possible A-Ds of the system. 
           This AD channel will be used for all subsequent operations performed by the system.
           Index = 0 to noADChannels - 1. Since this is one, Index is 0."""
        error = self.dll.SetADChannel(index)
        self.verbose(error, sys._getframe().f_code.co_name)
        self.channel = index
        return error

    def GetBitDepth(self):
        """This function will retrieve the size in bits of the dynamic range 
           for any available AD channel."""
        bitDepth = c_int()
        self.bitDepths = []
        for i in range(self.noADChannels):
            self.dll.GetBitDepth(i,byref(bitDepth))
            self.bitDepths.append(bitDepth.value)

    def GetNumberHSSpeeds(self):
        """Get the number of possible camera horizontal shift speeds"""
        noHSSpeeds = c_int()
        error = self.dll.GetNumberHSSpeeds(self.channel, self.outamp, byref(noHSSpeeds))
        self.noHSSpeeds = noHSSpeeds.value
        self.verbose(error, sys._getframe().f_code.co_name)
        return ERROR_CODE[error]

    def GetHSSpeed(self):
        """Get the possible horizontal shift speeds"""
        HSSpeed = c_float()

        self.HSSpeeds = []
    
        for i in range(self.noHSSpeeds):
            self.dll.GetHSSpeed(self.channel, self.outamp, i, byref(HSSpeed))
            self.HSSpeeds.append(HSSpeed.value)

    def SetHSSpeed(self, itype, index):
        """Set the horizontal shift speed (the speed at which the pixels are 
           shifted into the output node during the readout phase of an acquisition).
              itype: the output amplification setting of the system
              index: indices correspond to different horizontal shift speeds (MHz)
                0: 17.0
                1: 10.0
                2:  5.0 
                3:  1.0 """
        error = self.dll.SetHSSpeed(itype,index)
        self.verbose(error, sys._getframe().f_code.co_name)
        self.hsspeed = index
        return ERROR_CODE[error]

    def GetNumberVSSpeeds(self):
        """Different models of camera have different numbers of vertical shift 
           speeds available. 
           Get the number available for our camera."""
        noVSSpeeds = c_int()
        error = self.dll.GetNumberVSSpeeds(byref(noVSSpeeds))
        self.noVSSpeeds = noVSSpeeds.value
        self.verbose(error, sys._getframe().f_code.co_name)
        return error
    
    def GetVSSpeed(self):
        """Given the number of VS speeds available, return the possible VS speeds."""
        VSSpeed = c_float()

        self.VSSpeeds = []

        for i in range(self.noVSSpeeds):
            self.dll.GetVSSpeed(i,byref(VSSpeed))
            self.VSSpeeds.append(VSSpeed.value)

    def SetVSSpeed(self, index=4):
        """Set the vertical shift speed.
            index: indices correspond to different vertical shift speeds (us / row).
                0: 0.3
                1: 0.5
                2: 0.9 
                3: 1.7
                4: 3.3 (default) """
        error = self.dll.SetVSSpeed(index)
        self.verbose(error, sys._getframe().f_code.co_name)
        self.vsspeed = index
        return error

    def AbortAcquisition(self):
        """This function aborts the current acquisition if one is active."""
        error = self.dll.AbortAcquisition()
        self.verbose(error, sys._getframe().f_code.co_name)
        return error

    def SetReadMode(self, mode=4):
        """This function will set the readout mode to be used on the subsequent acquisitions.
                0 Full Vertical Binning
                1 Multi-Track
                2 Random-Track
                3 Single-Track
                4 Image (default)"""

        error = self.dll.SetReadMode(mode)
        self.ReadMode = mode
        self.verbose(error, sys._getframe().f_code.co_name)
        return error

    def GetDetector(self):
        cw = c_int()
        ch = c_int()
        error = self.dll.GetDetector(byref(cw), byref(ch))
        self.verbose(error, sys._getframe().f_code.co_name)
        self.DetectorWidth = cw.value
        self.DetectorHeight = ch.value

    def SetImage(self,hbin,vbin,hstart,hend,vstart,vend):
        """Define the extent of the CCD and the binning."""
        self.hbin = hbin
        self.vbin = vbin
        self.hstart = hstart
        self.hend = hend
        self.vstart = vstart
        self.vend = vend
        
        error = self.dll.SetImage(hbin,vbin,hstart,hend,vstart,vend)
        self.verbose(error, sys._getframe().f_code.co_name)
        return error

    def SetAcquisitionMode(self, mode):
        """This function will set the acquisition mode to be used on the next 
           StartAcquisition command.
            1: Single Scan
            2: Accumulate
            3. Kinetics
            4: Fast Kinetics 
            5: Run till abort"""
        error = self.dll.SetAcquisitionMode(mode)
        self.verbose(error, sys._getframe().f_code.co_name)
        self.AcquisitionMode = mode
        return error

    def SetExposureTime(self, time):
        """Set the exposure time in for imaging
            units: [seconds]"""
        error = self.dll.SetExposureTime(c_float(time))
        self.exposure = time
        self.verbose(error, sys._getframe().f_code.co_name)
        return error

    def StartAcquisition(self):
        """This function starts an acquisition. The status of the acquisition 
           can be monitored via GetStatus()."""
        error = self.dll.StartAcquisition()
        self.dll.WaitForAcquisition()
        self.verbose(error, sys._getframe().f_code.co_name)
        return error

    def SendSoftwareTrigger(self):
        """This function sends an event to the camera to take an acquisition 
           when in Software Trigger mode. """
        error = self.dll.SendSoftwareTrigger()
        self.verbose(error, sys._getframe().f_code.co_name)
        return error 

    def IsTriggerModeAvailable(self, iTriggerMode):
        """Check if the camera supports a given trigger mode.
             NB: It does not support software trigger (mode 10)"""
        ciTriggerMode = c_int(iTriggerMode)
        error = self.dll.IsTriggerModeAvailable(ciTriggerMode)
        self.verbose(error, sys._getframe().f_code.co_name)

    def GetAcquiredData(self, dimx, dimy, numKinScans = 1):
        """Retrieve the image at the end of a camera acquisition.
        Parameters: 
            - width of ROI (pixels)
            - height of ROI (pixels)
            - number of kinetic scans in acquisition (kinetic mode only)"""
        dim = int(dimx*dimy *  self.kscans) 
        cimage = (c_int * dim)()
        error = self.dll.GetAcquiredData(pointer(cimage),dim)
        self.verbose(error, sys._getframe().f_code.co_name)

        imageArray = []        
        for i in range(len(cimage)):
            imageArray.append(cimage[i])
        imageArray = imageArray[:]
        imageArray = np.reshape(imageArray, (numKinScans, dimx, dimy))
        return imageArray

    def GetOldestImage(self, dimx, dimy, numKinScans = 1):
        """Retrieve the oldest stored image in the camera buffer 
        during a camera acquisition.
        Parameters: 
            - width of ROI (pixels)
            - height of ROI (pixels)
            - number of kinetic scans in acquisition (kinetic mode only)"""
        dim = int(dimx*dimy *  self.kscans) 
        cimage = (c_int * dim)()
        error = self.dll.GetOldestImage(cimage, dim)
        self.verbose(error, sys._getframe().f_code.co_name)

        imageArray = []        
        for i in range(len(cimage)):
            imageArray.append(cimage[i])
        imageArray = imageArray[:]
        imageArray = np.reshape(imageArray, (numKinScans, dimx, dimy))
        return imageArray

    def GetAcquisitionTimings(self):
        """Get the current timings that have been set.
            Returns:
            - Exposure time
            - Accumulate time
            - Kinetic cycle time
            """
        exposure   = c_float()
        accumulate = c_float()
        kinetic    = c_float()
        error = self.dll.GetAcquisitionTimings(byref(exposure),byref(accumulate),byref(kinetic))
        self.exposure = exposure.value
        self.accumulate = accumulate.value
        self.kinetic = kinetic.value
        self.verbose(error, sys._getframe().f_code.co_name)
        return error

    def SetNumberKinetics(self,numKinScans):
        """This function will set the number of scans (possibly accumulated 
           scans) to be taken during a single acquisition sequence. This will 
           only take effect if the acquisition mode is Kinetic Series."""
        
        error = self.dll.SetNumberKinetics(numKinScans)
        self.verbose(error, sys._getframe().f_code.co_name)
        self.kscans = numKinScans
        return error

    def SetKineticCycleTime(self, time):
        """This function will set the kinetic cycle time to the nearest valid 
           value not less than the given value. The actual time used is obtained 
           by GetAcquisitionTimings. """
        error = self.dll.SetKineticCycleTime(c_float(time))
        self.verbose(error, sys._getframe().f_code.co_name)
        return error

    def SetFrameTransferMode(self, mode):
        """ This function will set whether an acquisition will readout in Frame 
            Transfer Mode. If the acquisition mode is Single Scan or Fast Kinetics 
            this call will have no affect."""
        cmode = c_int(mode)
        error = self.dll.SetFrameTransferMode(cmode)
        self.verbose(error, sys._getframe().f_code.co_name)
        return (error)

    def SetDriverEvent(self, driverEvent):
        """Pass a Win32 Event handle to the SDK.
        The event will be set under the follow conditions:
        1) Acquisition completed or aborted.
        2) As each scan during an acquisition is completed.
        3) Temperature as stabilized, drifted from stabilization or could not be reached.
        Condition 1 and 2 can be tested via GetStatus(), while condition 3 checked via GetTemperature().
        Reset the event after it has been handled in order to receive additional triggers. 
        Before deleting the event you must call SetDriverEvent with NULL as the parameter.
        Parameters:
        driverEvent - Win32 event handle."""
        cdriverEvent = c_void_p(driverEvent)
        error = self.dll.SetDriverEvent(cdriverEvent)
        return (error)

"""(an incomplete) Dictionary of what each error code means. 
   Full list can be found in SDK manual."""
ERROR_CODE = {
    20001: "DRV_ERROR_CODES",
    20002: "DRV_SUCCESS",
    20003: "DRV_VXNOTINSTALLED",
    20006: "DRV_ERROR_FILELOAD",
    20007: "DRV_ERROR_VXD_INIT",
    20010: "DRV_ERROR_PAGELOCK",
    20011: "DRV_ERROR_PAGE_UNLOCK",
    20013: "DRV_ERROR_ACK",
    20024: "DRV_NO_NEW_DATA",
    20026: "DRV_SPOOLERROR",
    20034: "DRV_TEMP_OFF",
    20035: "DRV_TEMP_NOT_STABILIZED",
    20036: "DRV_TEMP_STABILIZED",
    20037: "DRV_TEMP_NOT_REACHED",
    20038: "DRV_TEMP_OUT_RANGE",
    20039: "DRV_TEMP_NOT_SUPPORTED",
    20040: "DRV_TEMP_DRIFT",
    20050: "DRV_COF_NOTLOADED",
    20053: "DRV_FLEXERROR",
    20066: "DRV_P1INVALID",
    20067: "DRV_P2INVALID",
    20068: "DRV_P3INVALID",
    20069: "DRV_P4INVALID",
    20070: "DRV_INIERROR",
    20071: "DRV_COERROR",
    20072: "DRV_ACQUIRING",
    20073: "DRV_IDLE",
    20074: "DRV_TEMPCYCLE",
    20075: "DRV_NOT_INITIALIZED",
    20076: "DRV_P5INVALID",
    20077: "DRV_P6INVALID",
    20078: "DRV_INVALID_MODE",
    20083: "P7_INVALID",
    20089: "DRV_USBERROR",
    20091: "DRV_NOT_SUPPORTED",
    20095: "DRV_INVALID_TRIGGER_MODE",
    20099: "DRV_BINNING_ERROR",
    20990: "DRV_NOCAMERA",
    20991: "DRV_NOT_SUPPORTED",
    20992: "DRV_NOT_AVAILABLE"
}

if __name__ == '__main__':
    # Call the functions for bugfixing.
    a = Andor()
    a.Initialize()
    #a.GetStatus()
    
    #a.SetTemperature(-20)
    #a.CoolerON()
    #a.CoolerOFF()
    #a.IsCoolerOn()  # Note: this seems to be bugged. Always returns that the cooler is on.

    #a.SetCoolerMode(1)    
    #a.SetShutter(1, 2)
    #a.SetTriggerMode(1)

    #a.GetCameraSerialNumber()
    #a.GetAvailableCameras()
    
    #a.GetTemperatureRange()
    #a.GetTemperature()
    a.GetTemperatureF()
   
    # Pre-amp gain
    #a.SetPreAmpGain(3)
    #a.GetCurrentPreAmpGain()
    
    #a.SetEMGainMode(0)
    #a.SetEMCCDGain(1)
    #a.GetEMCCDGain()
    
    #a.SetOutputAmplifier(0)
    #a.GetNumberADChannels()
    #a.SetADChannel()
    
    #a.GetNumberHSSpeeds()
    #a.GetHSSpeed()
    #a.SetHSSpeed(a.outamp, 2)
    #a.GetHSSpeed()

    #a.GetNumberVSSpeeds()
    #a.GetVSSpeed()
    #a.SetVSSpeed(4)
    #a.GetBitDepth()
    #print(a.vsspeed)
    
    
    #a.IsTriggerModeAvailable(12)
    
    
    #a.ShutDown()












