"""
22/08/2019 Vincent Brooks
Call the library of Python functions for running the Andor camera.
Use these to build more complex functions for running a sequence.

Some info on what the triggering options do:
    Z:\Mixture\Experimental\Design_overview\Imaging

"""
import os
import time
import numpy as np
import win32event
import logging
logger = logging.getLogger(__name__)
from AndorFunctions import Andor, ERROR_CODE, Sensitivity, ReadNoise

try:
    from PyQt4.QtCore import QThread, pyqtSignal, QEvent, pyqtSlot, QObject
except ImportError:
    from PyQt5.QtCore import QThread, pyqtSignal, QEvent, pyqtSlot, QObject

class camera(QThread):
    """Inherits the basic Andor camera functions and build more 
    complicated ones from them. 

    Initiate the Andor camera. An external TTL should be connected
    to the StartAcquisition slot to take an image. The Andor SDK is 
    connected to the signal AcquisitionEvent which is emitted when
    an acquisition is completed or aborted, or temperature updates."""
    AcquisitionEvent = win32event.CreateEvent(None, 0, 0, 'Acquisition')
    AcquireEnd = pyqtSignal(np.ndarray) # send to image analysis 
    # emit (EM gain, preamp gain, readout noise) when the acquisition settings are updated
    SettingsChanged = pyqtSignal([float, float, float, bool])
    # emit the smallest dimension of image height/width when ROI is updated
    ROIChanged = pyqtSignal([int, int])

    def __init__(self, config_file=".\\ExExposure_config.dat"):
        super().__init__()   # Initialise the parent classes
        self.lastImage   = np.zeros((32,32)) # last acquired image
        self.BufferSize  = 0 # number of images that can fit in the buffer

        self.emg = 1.0  # applied EM gain
        self.pag = 4.50 # preamp gain sensitivity (e- per AD count)
        self.Nr  = 8.8  # readout noise (counts)
        
        self.idle_time = 0    # time between acquisitions
        self.t0 = time.time() # time at start of acquisition
        self.t1 = 0  # time time just after get acquisition
        self.t2 = time.time() # time after emitting signals
        self.timeout = 5e3 # number of milliseconds to wait for acquire
        
        self.initialised = 0 # check whether the camera functions were loaded 
        try: 
            self.AF = Andor() # functions for Andor camera
            self.AF.verbosity = False  # Set True for debugging
            self.AF.connected = False
            self.initialised  = 1 # functions loaded but camera not connected
            if self.AF.OS == "Windows" and self.AF.architecture == "64bit":
                self.CameraConnect()
                self.initialised = 2 # camera connected, default config
                if self.AF.connected == True:
                    self.AF.SetDriverEvent(int(self.AcquisitionEvent))
                    self.ApplySettingsFromConfig(config_file=config_file) 
                    # self.StabiliseTemperature()
                    self.initialised = 3 # fully initialised
            else:
                logger.error("Andor SDK requires Windows 64 bit")
        except Exception as e:
            self.initialised = 0
            logger.warning('Andor EMCCD not initialised.\n'+str(e))
            
    def CameraConnect(self):
        """Connect to camera and check which one it is.
             Pull from it infomation including:
                 - The HShift speeds available
                 - The VShift speeds available
                 - The A/D channels available (and then set the one to use)
                 - The detector height and width 
                 - Set the output amplifer (required to determine the above)"""          
        err = self.AF.Initialize()
        if ERROR_CODE[err] == "DRV_SUCCESS":
            print("Camera connected.")
            self.AF.GetCameraSerialNumber()
            print('iXon serial number: ' + str(self.AF.serial))
            
            if self.AF.serial == 11783:
                print("Camera: Microscope")
            elif self.AF.serial == 11707:
                print("Camera: Tweezer")
            self.AF.connected = True
            
            self.AF.SetOutputAmplifier(self.AF.outamp)
            self.AF.GetNumberADChannels()
            self.AF.SetADChannel(self.AF.noADChannels-1)
    
            self.AF.GetNumberHSSpeeds()
            self.AF.GetHSSpeed()
            self.AF.GetNumberVSSpeeds()
            self.AF.GetVSSpeed()
            
            self.AF.GetDetector()

        else:
            raise(Exception("Connection error: " + ERROR_CODE[err])) 
        
    def ApplySettings(self, setPointT=-60, coolerMode=1, shutterMode=2, 
            outamp=0, hsspeed=2, vsspeed=4, preampgain=3, EMgain=1, 
            ROI=None, hbin=1, vbin=1, cropMode=0, readmode=4, acqumode=5, 
            triggerMode=7, frameTransf=0, fastTrigger=0, expTime=70e-6, 
            verbosity=False, numKin=1):
        """Apply user settings.
        Keyword arguments:
        setPointT   -- temperature set point in degrees Celsius. 
        coolerMode  -- 1: temperature maintained on camera shutdown
                       2: ambient temperature on camera shutdown
        shutterMode -- typ=1: TTL high to open shutter
                       mod=1: internal shutter permanently open
                       mod=2: internal shutter permanently closed
        outamp      -- output amplification setting.
                        0: electron multiplication
                        1: conventional
        hsspeed     -- Horizontal shift speed (MHz)
              value - EM mode shift speed - conventional mode shift speed
                0:         17.0                         3.0
                1:         10.0                         1.0
                2:          5.0                         0.08
                3:          1.0 
        vsspeed     -- Vertical shift speeds (us / row).
                        0: 0.3  
                        1: 0.5
                        2: 0.9 
                        3: 1.7
                        4: 3.3 (default)
        preampgain  -- Pre-amp gain setting. The value can be 1, 2 or 3. 
                    See the system booklet for what these correspond to.
        EMgain      -- electron-multiplying gain factor.
        ROI         -- Region of Interest on the CCD. A tuple of form:
                        (xmin, xmax, ymin, ymax).
        hbin        -- number of horizontal pixels to bin in software
        vbin        -- number of vertical pixels to bin in software
        cropMode    -- reduce the active area of the CCD to improve 
                        throughput.
                        0: off        1: on
        readmode    -- 4: imaging readout mode
        acqumode    -- Camera acquisition mode
                        1: Single Scan
                        2: Accumulate
                        3. Kinetics
                        4: Fast Kinetics 
                        5: Run till abort
        triggerMode -- Mode for camera triggering
                        0: internal
                        1: External
                        6: External Start
                        7: External Exposure (Bulb)
                        9: External FVB EM (only valid for EM Newton models)
                        10: Software Trigger
                        12: External Charge Shifting
        frameTransf -- enable/disable frame transfer mode (not compatible
                        with external exposure mode).
                        0: off        1: on        
        fastTrigger -- enable/disable fast external triggering
                        0: off        1: on
        expTime     -- exposure time when not in external exposure trigger
                        mode. Units: seconds.
        verbosity   -- True for debugging info
        numKin      -- number of scans in kinetic mode."""
        errors = []
        errors.append(ERROR_CODE[self.AF.CoolerON()])
        errors.append(ERROR_CODE[self.AF.SetCoolerMode(coolerMode)])
        errors.append(ERROR_CODE[self.AF.SetTemperature(setPointT)])
        errors.append(ERROR_CODE[self.AF.SetShutter(1, shutterMode)])
        errors.append(ERROR_CODE[self.AF.SetOutputAmplifier(outamp)])
        AmpMode = 12*outamp # the first 12 settings are EM gain mode
        errors.append(ERROR_CODE[self.AF.SetHSSpeed(outamp, hsspeed)]) 
        errors.append(ERROR_CODE[self.AF.SetVSSpeed(vsspeed)])
        errors.append(ERROR_CODE[self.AF.SetPreAmpGain(preampgain)])
        errors.append(ERROR_CODE[self.AF.SetEMCCDGain(EMgain)])
        self.emg = EMgain
        try:
            self.pag = Sensitivity[AmpMode + 3*hsspeed + preampgain - 1]
            self.Nr  = ReadNoise[AmpMode + 3*hsspeed + preampgain - 1]
        except IndexError as e:
            self.pag = 4.50
            self.Nr  = 8.8
            logger.warning('Invalid camera acquisition settings: '+
                'PAG '+str(preampgain)+', hsspeed '+str(hsspeed)+'\n'+str(e))
        self.AF.ROI = ROI 
        errors.append(ERROR_CODE[self.AF.SetReadMode(readmode)])
        errors.append(ERROR_CODE[self.AF.SetAcquisitionMode(acqumode)])
        if numKin > 1:
            errors.append(ERROR_CODE[self.AF.SetNumberKinetics(numKin)])
            # errors.append(ERROR_CODE[self.cam.AF.SetFastKineticsEx(
            #                     100, numKin, expTime, 4, 1, 1, 1)])
        self.AF.PrevTrigger = triggerMode # store the trigger mode so it can be reset later
        errors.append(ERROR_CODE[self.AF.SetTriggerMode(triggerMode)])
        errors.append(ERROR_CODE[self.AF.SetFastExtTrigger(fastTrigger)])
        errors.append(ERROR_CODE[self.AF.SetFrameTransferMode(frameTransf)])
        # crop mode requires frame transfer and external trigger modes
        errors.append(ERROR_CODE[self.SetROI(self.AF.ROI, hbin=hbin, 
                                            vbin=vbin, crop=cropMode)])
        errors.append(ERROR_CODE[self.AF.SetExposureTime(expTime)])
        errors.append(ERROR_CODE[self.AF.GetAcquisitionTimings()])
        self.BufferSize = self.AF.GetSizeOfCircularBuffer()
        if abs(expTime - self.AF.exposure)/expTime > 0.01:
            logger.warning("Tried to set exposure time %.3g s"%expTime + 
                " but acquisition settings require min. exposure time " +
                "%.3g s."%self.AF.exposure)
        self.AF.verbosity = verbosity
        check_success = [e != 'DRV_SUCCESS' for e in errors]
        if any(check_success):
            logger.warning("Didn't get DRV_SUCCESS for setting " + 
                str(check_success.index(True)))
        self.SettingsChanged.emit(self.emg, self.pag, self.Nr, True)
        return check_success

    def ApplySettingsFromConfig(self, config_file="./ExExposure_config.dat"):
        """Read in a configuration file and apply camera settings from it.
        See the DocString for ApplySettings for descriptions of the 
        parameters.
        Keyword arguments:
        config_file -- the file used to load in config settings."""
        try:
            with open(config_file, 'r') as config_file:
                config_data = config_file.read().split("\n")
        except FileNotFoundError:
            logger.warning("Andor camera config.dat file not found. "+
                "This file is required to load camera settings.")
            return [1]

        cvals = []
        for row in config_data:
            if row[:2] != '20':
                cvals.append(int(row.split('=')[-1]))
            else: # exposure time is a float
                cvals.append(float(row.split('=')[-1]))
                
        errors = []
        errors.append(ERROR_CODE[self.AF.CoolerON()])
        errors.append(ERROR_CODE[self.AF.SetTemperature(cvals[0])])
        errors.append(ERROR_CODE[self.AF.SetCoolerMode(cvals[1])])
        errors.append(ERROR_CODE[self.AF.SetShutter(1, cvals[2])])  
        errors.append(ERROR_CODE[self.AF.SetOutputAmplifier(cvals[3])])
        AmpMode = 12*cvals[3] # the first 12 settings are EM gain mode  
        errors.append(ERROR_CODE[self.AF.SetHSSpeed(cvals[3], cvals[4])]) 
        errors.append(ERROR_CODE[self.AF.SetVSSpeed(cvals[5])])   
        errors.append(ERROR_CODE[self.AF.SetPreAmpGain(cvals[6])])
        try:
            self.pag = Sensitivity[AmpMode + 3*cvals[4] + cvals[6] - 1]
            self.Nr  = ReadNoise[AmpMode + 3*cvals[4] + cvals[6] - 1]
        except IndexError as e:
            self.pag = 4.50
            self.Nr  = 8.8
            logger.warning('Invalid camera acquisition settings: '+
                'PAG '+str(cvals[6])+', hsspeed '+str(cvals[4])+'\n'+str(e))
        errors.append(ERROR_CODE[self.AF.SetEMCCDGain(cvals[7])])
        self.emg = cvals[7]
        self.AF.ROI = (cvals[9], cvals[10], cvals[12], cvals[13])
        errors.append(ERROR_CODE[self.AF.SetReadMode(cvals[15])])
        errors.append(ERROR_CODE[self.AF.SetAcquisitionMode(cvals[16])])
        if cvals[22] > 1:
            errors.append(ERROR_CODE[self.AF.SetNumberKinetics(cvals[22])])
        self.AF.PrevTrigger = cvals[17] # store the trigger mode so it can be reset later
        errors.append(ERROR_CODE[self.AF.SetTriggerMode(cvals[17])])
        errors.append(ERROR_CODE[self.AF.SetFrameTransferMode(cvals[18])])
        errors.append(ERROR_CODE[self.AF.SetFastExtTrigger(cvals[19])])
        # crop mode requires frame transfer and external trigger modes
        errors.append(ERROR_CODE[self.SetROI(self.AF.ROI, hbin=cvals[8],
                            vbin=cvals[11], crop=cvals[14])])
        errors.append(ERROR_CODE[self.AF.SetExposureTime(cvals[20])])
        errors.append(ERROR_CODE[self.AF.GetAcquisitionTimings()])
        self.BufferSize = self.AF.GetSizeOfCircularBuffer()
        if abs(cvals[20] - self.AF.exposure)/cvals[20] > 0.01:
            logger.warning("Tried to set exposure time %.3g s"%cvals[20] + 
                " but acquisition settings require min. exposure time " +
                "%.3g s."%self.AF.exposure)
        self.AF.verbosity = bool(cvals[21])
        self.AF.kscans = 1
        check_success = [e != 'DRV_SUCCESS' for e in errors]
        if any(check_success):
            logger.warning("Didn't get DRV_SUCCESS for setting " + 
                str(check_success.index(True)))
        self.SettingsChanged.emit(self.emg, self.pag, self.Nr, True)
        return check_success

    def SetROI(self, ROI, hbin=1, vbin=1, crop=0, slowcrop=1):
        """Specify an ROI on the camera to image. If none specified, use 
        the entire CCD. 
           Parameters:
               - ROI: A tuple of the form (hstart, hend, vstart, vend)
               - crop: reduce the effective area of the CCD by cropping.
                        0: off         1: on
               - slowcrop: 0: speed up by storing multiple frames
                           1: low latency by reading each frame as it happens
        """
        error = ''
        if ROI == None:
            hstart,hend,vstart,vend = (
                1, self.AF.DetectorWidth, 1, self.AF.DetectorHeight)
        else:
            hstart,hend,vstart,vend = ROI
        self.AF.ROIwidth = (hend - hstart + 1) // hbin
        self.AF.ROIheight = (vend - vstart + 1) // vbin
        if crop:
            error = self.AF.SetIsolatedCropModeEx(
                crop, self.AF.ROIheight, self.AF.ROIwidth, 
                hbin, vbin, hstart, vstart)
            self.AF.SetIsolatedCropModeType(slowcrop)
        else:
            error = self.AF.SetImage(hbin,vbin,hstart,hend,vstart,vend)
        self.ROIChanged.emit(self.AF.ROIwidth, self.AF.ROIheight)
        return error
            
    def CheckCurrentSettings(self):
        """Check what the camera is currently set to."""
        print("\nCamera status: " + self.AF.GetStatus())
        print("---------")
        print("Cooler status: " + str(self.AF.coolerStatus))
        print("Temperature: " + 
            str(np.around(self.AF.GetTemperatureF()[0], 3))+ " C")
        print("---------")
        print("Shutter Status: " + str(self.AF.shutterStatus))
        print("---------")
        print("Preamp gain mode: " + str(self.AF.preampgain))
        print("Output amplifier gain mode: " + str(self.AF.outamp))
        print("EM gain mode: " +str(self.AF.gain))
        print("---------")
        print("H. shift speed: " + 
            str(self.AF.HSSpeeds[self.AF.hsspeed]) + " MHz")
        print("V. shift speed: " + 
            str(np.around(self.AF.VSSpeeds[self.AF.vsspeed], 1)) + " us")
        print("---------")
        print("ROI: " + str(self.AF.ROI))
        print("---------")
                 
    def CheckTemperatureStable(self):
        """Check if the temperature is stable"""
        return ERROR_CODE[self.AF.GetTemperature()[1]] == 'DRV_TEMP_STABILIZED'
    
    def StabiliseTemperature(self):
        """Wait until temperature is stabilised."""
        while self.CheckTemperatureStable() is False:
            print(ERROR_CODE[self.AF.GetTemperature()[1]])
            print("T = %g C. [Setpoint = %g C]" % (
                self.AF.GetTemperature()[0], self.AF.temperatureSetpoint) 
                + " Stabilising...")
            time.sleep(10)
        
    def Acquire(self):
        """Retrieve a single image from the EMCCD.
        This is a slot to be triggered by an acquisition completed event.
        Since not every event is an acquisition event, check the status of
        the camera."""
        if self.AF.GetStatus() == 'DRV_IDLE':
            im = self.AF.GetAcquiredData(
                    self.AF.ROIwidth, self.AF.ROIheight)
            self.lastImage = im
            self.AcquireEnd.emit(im[0]) 
            if self.AF.verbosity:
                self.PlotAcquisition(im)
                
    def TakeAcquisitions(self, n=1):
        """Taking a series of n single acquisitions sequentially.
        Assuming external mode, the camera will wait for an external trigger
        to take an acquisition."""
        for i in range(n):
            self.AF.StartAcquisition()
            result = win32event.WaitForSingleObject(
                            self.AcquisitionEvent, self.timeout)
            if result == win32event.WAIT_OBJECT_0:
                self.Acquire()
            elif result == win32event.WAIT_TIMEOUT and self.AF.verbosity:
                print('Acquisition timeout ', i)
        self.finished.emit()
        
    def EmptyBuffer(self):
        """Get all of the images currently stored in the camera buffer
        that have not yet been retreived. The dimensions of the returned
        array are: (# images, # kinetic scans, ROI width, ROI height)."""
        istart, iend = self.AF.GetNumberNewImages()
        if iend > istart:
            if iend >= self.BufferSize:
                logger.warning("While emptying camera buffer: The camera buffer "
                    "was full, some images may have been overwritten")
            return self.AF.GetImages(istart, iend, self.AF.ROIwidth,
                                            self.AF.ROIheight)
        else: return []
            
    # run method is called when the thread is started     
    def run(self):
        """Start an Acquisition and wait for a signal to abort"""
        self.idle_time = time.time() - self.t2 # time since last acquisition
        self.AF.StartAcquisition()
        while self.AF.GetStatus() == 'DRV_ACQUIRING':
            self.t0 = time.time() 
            result = win32event.WaitForSingleObject(
                            self.AcquisitionEvent, win32event.INFINITE)
            if result == win32event.WAIT_OBJECT_0: # get image
                self.lastImage = self.AF.GetOldestImage(
                        self.AF.ROIwidth, self.AF.ROIheight)
                self.t1 = time.time() 
                if self.lastImage.any(): # sometimes last image is empty
                    self.AcquireEnd.emit(self.lastImage[0]) # emit signals
            self.t2 = time.time()
        
    def PrintTimes(self, unit="s"):
        """Display the times measured for functions"""
        scale = 1
        if unit == "ms" or unit == "milliseconds":
            scale *= 1e3
        elif unit == "us" or unit == "microseconds":
            scale *= 1e6
        else:
            unit = "s"
        print("Last idle time between acquisitions: %.4g "%(
                self.idle_time*scale)+unit)
        print("Last time taken to acquire image: %.4g "%(
                (self.t1 - self.t0)*scale)+unit)
        print("Last time taken to emit signals: %.4g "%(
                (self.t2 - self.t1)*scale)+unit)
        print("Readout time: %.4g "%(
                (self.AF.GetReadOutTime())*scale)+unit)
        print("Exposure time: %.4g "%(
                (self.AF.exposure)*scale)+unit)

    def PlotAcquisition(self, images):
        """Display the list of images in separate subplots"""
        pass

    def SafeShutdown(self):
        """Shut down the camera after closing the internal shutter
        and the temperature controller. Wait until the temperature
        settles so that the heating rate isn't too high, then shut
        down."""
        self.AF.SetCoolerMode(1) # maintain temperature on shutdown
        self.AF.SetShutter(1, 2) # close shutter
        self.AF.SetEMCCDGain(1)  # reset EM gain
        # self.AF.CoolerOFF() # let temperatere stabilise to ambient
        # temp, _ = self.AF.GetTemperature()
        # while temp < -10: # wait until temp > -10 deg C
        #     temp, _ = self.AF.GetTemperature()
        #     time.sleep(2)
        self.AF.SetDriverEvent(None)
        self.AF.ShutDown()


if __name__ == "__main__":
    # change directory to this file's location
    os.chdir(os.path.dirname(os.path.realpath(__file__))) 
    iXon = camera('./Standard modes/FULLCCD.dat')
    iXon.AF.verbosity = True
    iXon.timeout = 20e3
    iXon.CheckCurrentSettings()
    # iXon.start()
    # time.sleep(10)
    # iXon.AF.AbortAcquisition()
    # iXon.SafeShutdown()