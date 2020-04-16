# -*- coding: utf-8 -*-
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
import os
import numpy as np
import logging
logger = logging.getLogger(__name__)

# Ctype files stored here: C:\Users\Lab\AppData\Local\Enthought\Canopy\App\appdata\canopy-2.1.9.3717.win-x86_64\Lib\ctypes

# From the Andor manual: the sensitivity and read noise for a given acquisition setting
# the ordering is as given in the Andor manual
Sensitivity = np.array([16, 9.37, 5.1, 16.3, 8.28, 4.86, 17.9, 8.51, 4.5, 17.6, 8.68, 4.46, 4.09, 3.19, 1.52, 4.1, 3.2, 1.48, 4.18, 3.19, 1.49]) # in e- per AD count
ReadNoise   = np.array([14.5, 17.5, 16.33, 7.18, 8.45, 11.46, 4.01, 5.56, 8.69, 1.45, 2.06, 3.43, 3.42, 3.89, 6.78, 1.77, 2.06, 3.67, 0.85, 1.01, 1.88]) # in counts

class Andor:
    """Class containing a library of functions for operating the Andor camera."""
    
    def __init__(self, dllpath="Z:\\Tweezer\\Code\\Python 3.5\\PyDex\\andorcamera\\atmcd64d"):
        super().__init__() # required for multiple inheritence
        self.OS = platform.system()
        self.architecture = platform.architecture()[0]
        
        try:            
            self.dll = cdll.LoadLibrary(dllpath) # note dll path must be absolute, not relative
        except OSError:
            logger.exception('Andor functions dll file not found.')
    
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
        self.TriggerMode    = None      # The trigger mode used in acquisitions. See manual.
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
        
        self.kscans         = None      # Number of kinetic scans
        self.naccumulate     = None      # Number of accumulations to take (number of scans to add together)

    def Initialize(self):
        '''Initialize the Andor camera'''
        tekst = c_char()  
        error = self.dll.Initialize(byref(tekst))
        self.verbose(error, sys._getframe().f_code.co_name)
        return error

    def verbose(self, errorcode, function=''):
        """Set verbosity of camera error outputs"""
        if self.verbosity:
            print("[%s]: %s" %(function, ERROR_CODE[errorcode]))

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
        self.TriggerMode = mode
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
        return error

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
              index - EM mode shift speed - conventional mode shift speed
                0:         17.0                         3.0
                1:         10.0                         1.0
                2:          5.0                         0.08
                3:          1.0 """
        error = self.dll.SetHSSpeed(itype,index)
        self.verbose(error, sys._getframe().f_code.co_name)
        self.hsspeed = index
        return error

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
           when in Software Trigger mode. [Doesn't work with iXon Ultra].
           """
        error = self.dll.SendSoftwareTrigger()
        self.verbose(error, sys._getframe().f_code.co_name)
        return error 

    def IsTriggerModeAvailable(self, iTriggerMode):
        """Check if the camera supports a given trigger mode.
             NB: It does not support software trigger (mode 10)"""
        ciTriggerMode = c_int(iTriggerMode)
        error = self.dll.IsTriggerModeAvailable(ciTriggerMode)
        self.verbose(error, sys._getframe().f_code.co_name)

    def GetAcquiredData(self, dimx, dimy):
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
        imageArray = np.reshape(imageArray, (self.kscans, dimx, dimy))
        return imageArray

    def GetOldestImage(self, dimx, dimy, numKinScans=1):
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
        imageArray = np.reshape(imageArray, (self.kscans, dimx, dimy))
        return imageArray

    def GetImages(self, first, last, dimx, dimy):
        """Update the data array with the specified series of images from the 
        circular buffer. If the specified series is out of range (i.e. the 
        images have been overwritten or have not yet been acquired then an error
        will be returned.
        Inputs:
            first - index of first image in buffer to retrieve.
            last - index of last image in buffer to retrieve.
            dimx - number of pixels in horizontal direction.
            dimy - number of pixels in vertical direction."""
        dim = int(dimx*dimy *  self.kscans) 
        cfirst = c_int(first)
        clast = c_int(last)
        carr = (c_int * dim * (last-first+1))()
        csize = c_int(dim * (last-first+1))
        cvalidfirst = c_int()
        cvalidlast = c_int()
        error = self.dll.GetImages(cfirst, clast, carr, csize, 
                                byref(cvalidfirst), byref(cvalidlast))
        self.verbose(error, sys._getframe().f_code.co_name)
        
        imageArray = []        
        for i in range(len(carr)):
            imageArray.append(carr[i])
        imageArray = imageArray[:]
        imageArray = np.reshape(imageArray, 
                            ((last-first+1), self.kscans, dimx, dimy))
        return imageArray
        
    def GetNumberAvailableImages(self):
        """Return the number of available images in the circular buffer. 
        This is the total number of images during an acquisition.
        If any images are overwritten in the circular buffer they no 
        longer can be retrieved and the information returned will treat 
        overwritten images as not available."""
        cfirst = c_int()
        clast = c_int()
        error = self.dll.GetNumberAvailableImages(byref(cfirst), byref(clast))
        self.verbose(error, sys._getframe().f_code.co_name)
        return (cfirst.value, clast.value)
        
    def GetNumberNewImages(self):
        """Return the number of new images (i.e. images which have not yet 
        been retrieved) in the circular buffer. If any images are 
        overwritten in the circular buffer they can no longer be retrieved 
        and the information returned will treat overwritten images as 
        having been retrieved."""
        cfirst = c_int()
        clast = c_int()
        error = self.dll.GetNumberNewImages(byref(cfirst), byref(clast))
        self.verbose(error, sys._getframe().f_code.co_name)
        return (cfirst.value, clast.value)


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
        error = self.dll.GetAcquisitionTimings(
                        byref(exposure),byref(accumulate),byref(kinetic))
        self.exposure = exposure.value
        self.accumulate = accumulate.value
        self.kinetic = kinetic.value
        self.verbose(error, sys._getframe().f_code.co_name)
        return error
        
    def GetSizeOfCircularBuffer(self):
        """The maximum number of images the circular buffer can store based 
        on the current acquisition settings."""
        cindex = c_int()
        error = self.dll.GetSizeOfCircularBuffer(byref(cindex))
        self.verbose(error, sys._getframe().f_code.co_name)
        return cindex.value

    def SetNumberKinetics(self, numKinScans):
        """This function will set the number of scans to be taken during a 
        single acquisition sequence. This will only take effect if the 
        acquisition mode is Kinetic Series."""
        cnumscans = c_int(numKinScans)
        error = self.dll.SetNumberKinetics(cnumscans)
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
        
    def SetFastKineticsEx(self, exposedRows, seriesLength, time, mode, 
                                    hbin, vbin, offset):
        """Set the parameters to be used when taking a fast kinetics 
        acquisition.
        Inputs:
          exposedRows - sub-area height in rows.
          seriesLength - number in series.
          time - exposure time in seconds.
          mode - binning mode (0 - FVB , 4 - Image).
          hbin - horizontal binning.
          vbin - vertical binning (only used when in image mode).
          offset - offset of first row to be used in Fast Kinetics from 
          the bottom of the CCD."""
        cexposedRows = c_int(exposedRows)
        cseriesLength = c_int(seriesLength)
        ctime = c_float(time)
        cmode = c_int(mode)
        chbin = c_int(hbin)
        cvbin = c_int(vbin)
        coffset = c_int(offset)
        error = self.dll.SetFastKineticsEx(cexposedRows, cseriesLength, 
            ctime, cmode, chbin, cvbin, coffset)
        self.verbose(error, sys._getframe().f_code.co_name)
        return error
        
    def SetFastKineticsStorageMode(self, mode):
        """Increase the number of frames which can be acquired in fast 
        kinetics mode when using vertical binning. When ‘binning in storage 
        area’ is selected the offset cannot be adjusted from the bottom of 
        the sensor and the maximum signal level will be reduced.
        Inputs:
          mode - vertically bin in readout register (0)                 
                     vertically bin in storage area (1)"""
        cmode = c_int(mode)
        error = self.dll.SetFastKineticsStorageMode(cmode)
        self.verbose(error, sys._getframe().f_code.co_name)
        return error
   
        
    def SetNumberAccumulations(self, number):
        """Set the number of scans accumulated in memory. This will only 
        take effect if the acquisition mode is either Accumulate or 
        Kinetic Series.
        Inputs:
          number - number of scans to accumulate"""
        cnumber = c_int(number)
        error = self.dll.SetNumberAccumulations(cnumber)
        self.verbose(error, sys._getframe().f_code.co_name)
        self.naccumulate = number
        return error
        
    def SetFrameTransferMode(self, mode):
        """ This function will set whether an acquisition will readout in Frame 
            Transfer Mode. If the acquisition mode is Single Scan or Fast Kinetics 
            this call will have no affect."""
        cmode = c_int(mode)
        error = self.dll.SetFrameTransferMode(cmode)
        self.verbose(error, sys._getframe().f_code.co_name)
        return error

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
        self.verbose(error, sys._getframe().f_code.co_name)
        return error
        
    def SetAcqStatusEvent(self, statusEvent):
        """Pass a Win32 Event handle to the driver to inform the user software 
        that the camera has started exposing or that the camera has finished 
        exposing. To determine what event has occurred call GetCameraEventStatus. 
        This may give the user software an opportunity to perform other actions 
        that will not affect the readout of the current acquisition. 
        The SetPCIMode function must be called to enable/disable the events 
        from the driver.
        Inputs:
            statusEvent - Win32 event handle."""
        cstatusEvent = c_int(statusEvent)
        error = self.dll.SetAcqStatusEvent(cstatusEvent)
        self.verbose(error, sys._getframe().f_code.co_name)
        return error
        
    def SetPCIMode(self, mode, value):
        """With the CCI23 card, events can be sent when the camera is 
        starting to expose and when it has finished exposing. This function 
        will control whether those events happen or not.
        Inputs:
            mode - currently must be set to 1
            value - 0 to disable the events, 1 to enable"""
        cmode = c_int(mode)
        cvalue = c_int(value)
        error = self.dll.SetPCIMode(cmode, cvalue)
        self.verbose(error, sys._getframe().f_code.co_name)
        return error
        
    def SetCameraStatusEnable(self, Enable):
        """Mask out certain types of acquisition status events. The default 
        notifies on every type of event but this may cause missed events if 
        different types of event occur very close together. The bits in the 
        mask correspond to the following event types:
            Use0 - Fire pulse down event
            Use1 - Fire pulse up event
        Set the corresponding bit to 0 to disable the event type and 1 to 
        enable the event type.
        Inputs:
            Enable - bitmask with bits set for those events about which you 
                        wish to be notified."""
        cEnable = (Enable)
        error = self.dll.SetCameraStatusEnable(cEnable)
        self.verbose(error, sys._getframe().f_code.co_name)
        return error
        
    def GetCameraEventStatus(self):
        """Return if the system is exposing or not.
        WARNING - there is a bug with this function that causes crashes
        on fast acquisitions in versions earlier than SDK 2.78.5"""
        ccamStatus = ()
        error = self.dll.GetCameraEventStatus(byref(ccamStatus))
        self.verbose(error, sys._getframe().f_code.co_name)
        return ccamStatus.value
        
    def SetIsolatedCropMode(
            self, active, cropheight, cropwidth, vbin, hbin):
        """Reduce the dimensions of the CCD by excluding some rows or 
        columns to achieve higher throughput. Operate in either Full 
        Vertical Binning or Imaging read modes. Note: It is important to 
        ensure that no light falls on the excluded region otherwise 
        the acquired data will be corrupted.
        Inputs:
          active - Crop mode active:
            1 - Crop mode is ON.
            0 - Crop mode is OFF.
          cropheight - The selected crop height. 
            This value must be between 1 and the CCD height.
          cropwidth - The selected crop width. 
            This value must be between 1 and the CCD width.
          vbin - The selected vertical binning.
          hbin - The selected horizontal binning."""
        cactive = c_int(active)
        ccropheight = c_int(cropheight)
        ccropwidth = c_int(cropwidth)
        cvbin = c_int(vbin)
        chbin = c_int(hbin)
        error = self.dll.SetIsolatedCropMode(
                cactive, ccropheight, ccropwidth, cvbin, chbin)
        self.verbose(error, sys._getframe().f_code.co_name)
        return error

    def SetIsolatedCropModeEx(
        self, active, cropheight, cropwidth, 
        vbin, hbin, cropleft, cropbottom):
        """*** Returns DRV_NOT_AVAILABLE for iXon Ultra 11783 ***
        Reduces the dimensions of the CCD by excluding some rows or 
        columns to achieve higher throughput. Can only be used in Image 
        readout mode with the EM output amplifier. Note: It is important to 
        ensure that no light falls on the excluded region otherwise the 
        acquired data will be corrupted.
        The following centralized regions of interest are recommended 
        to achieve the fastest possible frame rates:
        (ROI, Crop Left Start Position, Crop Right Position, Crop Bottom 
        Start Position, Crop Top Position)
        (32 x 32, 241, 272, 240, 271)
        (64 x 64, 219, 282, 224, 287)
        (96 x 96, 209, 304, 208, 303)
        (128 x 128, 189, 316, 192, 319)
        (256 x 256, 123, 378, 128, 383)
        (496 x 4, 8, 503, 254, 257)
        (496 x 16, 8, 503, 249, 262)
        Inputs:
            active - Crop mode active.:
                1 - Crop mode is ON.
                0 - Crop mode is OFF.
            cropheight - The selected crop height. 
                This value must be between 1 and the CCD height.
            cropwidth - The selected crop width. 
                This value must be between 1 and the CCD width.
            vbin - vbinThe selected vertical binning.
            hbin - hbinThe selected horizontal binning.
            cropleft - The selected crop left start position
            cropbottom - The selected crop bottom start position"""
        cactive = c_int(active)
        ccropheight = c_int(cropheight)
        ccropwidth = c_int(cropwidth)
        cvbin = c_int(vbin)
        chbin = c_int(hbin)
        ccropleft = c_int(cropleft)
        ccropbottom = c_int(cropbottom)
        error = self.dll.SetIsolatedCropModeEx(cactive, ccropheight, ccropwidth, cvbin, chbin, ccropleft, ccropbottom)
        self.verbose(error, sys._getframe().f_code.co_name)
        return error
    
    def SetIsolatedCropModeType(self, mode):
        """Set the method by which data is transferred in isolated crop 
        mode. The default method is High Speed where multiple frames may be 
        stored in the storage area of the sensor before they are read out.  
        In Low Latency mode, each cropped frame is read out as it happens. 
        Inputs:
            mode - 0 – High Speed.  1 – Low Latency."""
        cmode = c_int(mode)
        error = self.dll.SetIsolatedCropModeType(cmode)
        self.verbose(error, sys._getframe().f_code.co_name)
        return error
        
    def SetDMAParameters(self, MaxImagesPerDMA, SecondsPerDMA):
        """To facilitate high image readout rates the controller card may 
        wait for multiple images to be acquired before notifying the SDK 
        that new data is available. Without this facility, there is a 
        chance that hardware interrupts may be lost as the operating system 
        does not have enough time to respond to each interrupt. The 
        drawback to this is that you will not get the data for an image 
        until all images for that interrupt have been acquired.
        Inputs:
            MaxImagesPerDMA - Override to the number of images per DMA if 
                the calculated value is higher than this. (Default=0, ie. 
                no override)
            SecondsPerDMA - Minimum amount of time to elapse between 
                interrrupts. (Default=0.03s)"""
        cMaxImagesPerDMA = c_int(MaxImagesPerDMA)
        cSecondsPerDMA = c_float(SecondsPerDMA)
        error = self.dll.SetDMAParameters(cMaxImagesPerDMA, cSecondsPerDMA)
        self.verbose(error, sys._getframe().f_code.co_name)
        return error
        
    def GetKeepCleanTime(self):
        """Return the time to perform a keep clean cycle. Use after all the 
        acquisitions settings have been set. The value returned is the 
        actual time used in subsequent acquisitions."""
        cKeepCleanTime = c_float()
        error = self.dll.GetKeepCleanTime(byref(cKeepCleanTime))
        self.verbose(error, sys._getframe().f_code.co_name)
        return cKeepCleanTime.value
        
    def GetReadOutTime(self):
        """Return the time to readout data from a sensor. Use after all the 
        acquisitions settings have been set. The value returned is the 
        actual times used in subsequent acquisitions."""
        cReadOutTime = c_float()
        error = self.dll.GetReadOutTime(byref(cReadOutTime))
        self.verbose(error, sys._getframe().f_code.co_name)
        return cReadOutTime.value


"""Dictionary of what each error code means. 
   Full list can be found in SDK manual."""
ERROR_CODE = {
        20001: "DRV_ERROR_CODES",
        20002: "DRV_SUCCESS",
        20003: "DRV_VXDNOTINSTALLED",
        20004: "DRV_ERROR_SCAN",
        20005: "DRV_ERROR_CHECK_SUM",
        20006: "DRV_ERROR_FILELOAD",
        20007: "DRV_UNKNOWN_FUNCTION",
        20008: "DRV_ERROR_VXD_INIT",
        20009: "DRV_ERROR_ADDRESS",
        20010: "DRV_ERROR_PAGELOCK",
        20011: "DRV_ERROR_PAGE_UNLOCK",
        20012: "DRV_ERROR_BOARDTEST",
        20013: "DRV_ERROR_ACK",
        20014: "DRV_ERROR_UP_FIFO",
        20015: "DRV_ERROR_PATTERN",
        20017: "DRV_ACQUISITION_ERRORS",
        20018: "DRV_ACQ_BUFFER",
        20019: "DRV_ACQ_DOWNFIFO_FULL",
        20020: "DRV_PROC_UNKNOWN_INSTRUCTION",
        20021: "DRV_ILLEGAL_OP_CODE",
        20022: "DRV_KINETIC_TIME_NOT_MET",
        20023: "DRV_ACCUM_TIME_NOT_MET",
        20024: "DRV_NO_NEW_DATA",
        20026: "DRV_SPOOLERROR",
        20033: "DRV_TEMPERATURE_CODES",
        20034: "DRV_TEMPERATURE_OFF",
        20035: "DRV_TEMPERATURE_NOT_STABILIZED",
        20036: "DRV_TEMPERATURE_STABILIZED",
        20037: "DRV_TEMPERATURE_NOT_REACHED",
        20038: "DRV_TEMPERATURE_OUT_RANGE",
        20039: "DRV_TEMPERATURE_NOT_SUPPORTED",
        20040: "DRV_TEMPERATURE_DRIFT",
        20049: "DRV_GENERAL_ERRORS",
        20050: "DRV_INVALID_AUX",
        20051: "DRV_COF_NOTLOADED",
        20052: "DRV_FPGAPROG",
        20053: "DRV_FLEXERROR",
        20054: "DRV_GPIBERROR",
        20064: "DRV_DATATYPE",
        20065: "DRV_DRIVER_ERRORS",
        20066: "DRV_P1INVALID",
        20067: "DRV_P2INVALID",
        20068: "DRV_P3INVALID",
        20069: "DRV_P4INVALID",
        20070: "DRV_INIERROR",
        20071: "DRV_COFERROR",
        20072: "DRV_ACQUIRING",
        20073: "DRV_IDLE",
        20074: "DRV_TEMPCYCLE",
        20075: "DRV_NOT_INITIALIZED",
        20076: "DRV_P5INVALID",
        20077: "DRV_P6INVALID",
        20078: "DRV_INVALID_MODE",
        20079: "DRV_INVALID_FILTER",
        20080: "DRV_I2CERRORS",
        20081: "DRV_DRV_I2CDEVNOTFOUND",
        20082: "DRV_I2CTIMEOUT",
        20083: "DRV_P7INVALID",
        20089: "DRV_USBERROR",
        20090: "DRV_IOCERROR",
        20091: "DRV_NOT_SUPPORTED",
        20093: "DRV_USB_INTERRUPT_ENDPOINT_ERROR",
        20094: "DRV_RANDOM_TRACK_ERROR",
        20095: "DRV_INVALID_TRIGGER_MODE",
        20096: "DRV_LOAD_FIRMWARE_ERROR",
        20097: "DRV_DIVIDE_BY_ZERO_ERROR",
        20098: "DRV_INVALID_RINGEXPOSURES",
        20099: "DRV_BINNING_ERROR",
        20100: "DRV_INVALID_AMPLIFIER",
        20115: "DRV_ERROR_MAP",
        20116: "DRV_ERROR_UNMAP",
        20117: "DRV_ERROR_MDL",
        20118: "DRV_ERROR_UNMDL",
        20119: "DRV_ERROR_BUFFSIZE",
        20121: "DRV_ERROR_NOHANDLE",
        20130: "DRV_GATING_NOT_AVAILABLE",
        20131: "DRV_FPGA_VOLTAGE_ERROR",
        20990: "DRV_ERROR_NOCAMERA",
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