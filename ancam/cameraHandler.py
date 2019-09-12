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
import matplotlib.pyplot as plt
import win32event
from AndorFunctions import Andor, ERROR_CODE # Import iXon control functions.

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
    Finished = pyqtSignal(int) # emit when the acquisition thread finishes

    def __init__(self, config_file="./AndorCam_config.dat"):
        super().__init__()         # Initialise the parent classes
        self.AF = Andor()          # functions for Andor camera
        self.AF.verbosity = False  # Set True for debugging
        self.AF.connected = False
        
        self.idle_time = 0     # time between acquisitions
        self.t0 = time.time()  # time at start of acquisition
        self.t1 = 0  # time time just after get acquisition
        self.t2 = time.time()  # time after emitting signals
        
        self.timeout      = 5e3 # number of milliseconds to wait for acquire
        
        if self.AF.OS == "Windows" and self.AF.architecture == "64bit":
            self.CameraConnect()
            if self.AF.connected == True:
                self.AF.SetDriverEvent(int(self.AcquisitionEvent))
                self.ApplySettingsFromConfig(config_file=config_file) 
                # self.StabiliseTemperature()
        else:
            print("Requires Windows 64 bit")
            
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
            print("Connection error: " + ERROR_CODE[err]) 
        
    def ApplySettings(self, setPointT=-20, coolerMode=1, shutterMode=2, 
            outamp=0, hsspeed=2, vsspeed=4, preampgain=3, EMgain=1, 
            ROI=None, cropMode=0, readmode=4, acqumode=5, triggerMode=7,
            frameTransf=0, fastTrigger=0, expTime=70e-6, verbosity=False):
        """Apply user settings.
        Keyword arguments:
        setPointT   -- temperature set point in degrees Celsius. 
        coolerMode  -- 1: temperature maintained on camera shutdown
                       2: ambient temperature on camera shutdown
        shutterMode -- typ=1: TTL high to open shutter
                       mod=1: internal shutter permanently open
                       mod=2: internal shutter permanently closed
        outamp      -- output amplification setting.
                        0: electron multiplication/conventional
                        1: conventional/extended NIR mode
        hsspeed     -- Horizontal shift speed (MHz)
                        0: 17.0
                        1: 10.0
                        2:  5.0 
                        3:  1.0
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
        verbosity   -- True for debugging info."""
        errors = []
        errors.append(self.AF.SetTemperature(setPointT))
        errors.append(self.AF.CoolerON())
        errors.append(self.AF.SetCoolerMode(coolerMode))
        errors.append(self.AF.SetShutter(1, shutterMode))
        errors.append(self.AF.SetHSSpeed(outamp, hsspeed)) 
        errors.append(self.AF.SetVSSpeed(vsspeed))
        errors.append(self.AF.SetPreAmpGain(preampgain))
        errors.append(self.AF.SetEMCCDGain(EMgain))
        self.AF.ROI = ROI 
        errors.append(self.SetROI(self.AF.ROI, cropMode=cropMode))
        errors.append(self.AF.SetReadMode(readmode))
        errors.append(self.AF.SetAcquisitionMode(acqumode))
        errors.append(self.AF.SetTriggerMode(triggerMode))
        errors.append(self.AF.SetFastExtTrigger(fastTrigger))
        errors.append(self.AF.SetFrameTransferMode(frameTransf))
        errors.append(self.AF.SetExposureTime(expTime))
        errors.append(self.AF.GetAcquisitionTimings())
        if abs(expTime - self.AF.exposure)/self.AF.exposure > 0.01:
            print("WARNING: Tried to set exposure time %.3g s"%expTime + 
                " but acquisition settings require min. exposure time " +
                "%.3g s."%self.Af.exposure)
        self.AF.verbosity = verbosity
        check_success = [e != 'DRV_SUCCESS' for e in errors]
        if any(check_success):
            print("WARNING: Didn't get DRV_SUCCESS for setting " + 
                str(check_success.index(True)))

    def ApplySettingsFromConfig(self, config_file="./AndorCam_config.dat"):
        """Read in a configuration file and apply camera settings from it.
        See the DocString for ApplySettings for descriptions of the 
        parameters.
        Keyword arguments:
        config_file -- the file used to load in config settings."""
        try:
            with open(config_file, 'r') as config_file:
                config_data = config_file.read().split("\n")
        except FileNotFoundError:
            print("config.dat file not found. This file is required to load camera settings.")
            return 0

        cvals = []
        for row in config_data:
            if row[:2] != '18':
                cvals.append(int(row.split('=')[-1]))
            else: # exposure time is a float
                cvals.append(float(row.split('=')[-1]))
                
        errors = []
        errors.append(self.AF.SetTemperature(cvals[0]))
        errors.append(self.AF.CoolerON())
        errors.append(self.AF.SetCoolerMode(cvals[1]))
        errors.append(self.AF.SetShutter(1, cvals[2]))    
        errors.append(self.AF.SetHSSpeed(cvals[3], cvals[4])) 
        errors.append(self.AF.SetVSSpeed(cvals[5]))   
        errors.append(self.AF.SetPreAmpGain(cvals[6]))
        errors.append(self.AF.SetEMCCDGain(cvals[7]))
        self.AF.ROI = (cvals[8], cvals[9], cvals[10], cvals[11])
        errors.append(self.SetROI(self.AF.ROI, cropMode=cvals[12]))
        errors.append(self.AF.SetReadMode(cvals[13]))
        errors.append(self.AF.SetAcquisitionMode(cvals[14]))
        errors.append(self.AF.SetTriggerMode(cvals[15]))
        errors.append(self.AF.SetFrameTransferMode(cvals[16]))
        errors.append(self.AF.SetFastExtTrigger(cvals[17]))
        errors.append(self.AF.SetExposureTime(cvals[18]))
        errors.append(self.AF.GetAcquisitionTimings())
        if abs(cvals[18] - self.AF.exposure)/self.AF.exposure > 0.01:
            print("WARNING: Tried to set exposure time %.3g s"%cvals[18] + 
                " but acquisition settings require min. exposure time " +
                "%.3g s."%self.Af.exposure)
        self.AF.verbosity = bool(cvals[19])
        self.AF.kscans = 1
        check_success = [e != 'DRV_SUCCESS' for e in errors]
        if any(check_success):
            print("WARNING: Didn't get DRV_SUCCESS for setting " + 
                str(check_success.index(True)))

    def SetROI(self, ROI, cropMode=0):
        """Specify an ROI on the camera to image. If none specified, use 
        the entire CCD. 
           Parameters:
               - ROI: A tuple of the form (hstart, hend, vstart, vend)
               - cropMode: reduce the effective area of the CCD by cropping.
                        0: off         1: on
        """
        error = ''
        if ROI == None:
            hstart,hend,vstart,vend = (
                1, self.AF.DetectorWidth, 1, self.AF.DetectorHeight)
        else:
            hstart,hend,vstart,vend = ROI
        self.AF.ROIwidth = hend - hstart + 1
        self.AF.ROIheight = vend - vstart + 1
        if cropMode:
            error = self.AF.SetIsolatedCropModeEx(
                cropMode, self.AF.ROIheight, self.AF.ROIwidth, 
                1, 1, hstart, vstart)
        else:
            error = self.AF.SetImage(1,1,hstart,hend,vstart,vend)
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
                self.AF.ROIwidth, self.AF.ROIheight, self.AF.kscans)
            self.lastImage = im
            self.AcquireEnd.emit(im[0]) 
            if self.AF.verbosity:
                self.PlotAcquisition(im)
           
    # run method is called when the thread is started     
    def run(self):
        """Start an Acquisition and wait for a signal to abort"""
        self.idle_time = time.time() - self.t2 # time since last acquisition
        self.AF.StartAcquisition()
        # i = 0
        while self.AF.GetStatus() == 'DRV_ACQUIRING':
            self.t0 = time.time() 
            result = win32event.WaitForSingleObject(
                            self.AcquisitionEvent, win32event.INFINITE)
            if result == win32event.WAIT_OBJECT_0: # get image
                self.lastImage = self.AF.GetOldestImage(
                    self.AF.ROIwidth, self.AF.ROIheight, self.AF.kscans)
                self.t1 = time.time() 
                if self.lastImage.any(): # sometimes last image is empty
                    self.AcquireEnd.emit(self.lastImage[0]) # emit signals
            # reset windows signal to trigger the next acquisition
            self.AcquisitionEvent = win32event.CreateEvent(None, 
                                                0, 0, 'Acquisition')
            self.AF.SetDriverEvent(int(self.AcquisitionEvent))                    
            self.t2 = time.time()
            # print(i, end=' ')
            # i += 1
    
    def TakeAcquisitions(self, n=1):
        """Taking a series of n acquisitions sequentially.
        Assuming external mode, the camera will wait for an external trigger
        to take an acquisition."""
        for i in range():
            self.AF.StartAcquisition()
            result = win32event.WaitForSingleObject(
                            self.AcquisitionEvent, self.timeout)
            if result == win32event.WAIT_OBJECT_0:
                self.Acquire()
            elif result == win32event.WAIT_TIMEOUT and self.verbosity:
                print('Acquisition timeout ', i)
        self.Finished.emit(1)
        
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

    def PlotAcquisition(self, images):
        """Display the list of images in separate subplots"""
        plt.close('all')
        f = plt.figure()
        for i in range(self.AF.kscans):
            axi = f.add_subplot(1,self.AF.kscans,i+1)
            axi.imshow(images[i])
            axi.title.set_text('F frame' +str(i+1))   
            plt.show()

    def SafeShutdown(self):
        """Shut down the camera after closing the internal shutter
        and the temperature controller. Wait until the temperature
        settles so that the heating rate isn't too high, then shut
        down."""
        self.ApplySettings(coolerMode=0, shutterMode=2, EMgain=0)
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
    iXon = camera()
    iXon.verbosity = True
    iXon.timeout = 20e3
    iXon.CheckCurrentSettings()
    iXon.run()
    iXon.SafeShutdown()