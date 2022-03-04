import numpy as np
from thorlabs_tsi_sdk import tl_camera
import sys
import time
if '..' not in sys.path: sys.path.append('..')
from strtypes import info, error, warning
from .camera_class import Image

class TCamera(tl_camera.TLCameraSDK):
    
    def __init__(self, exposure=1, blacklevel=0, gain=0, roi=None, serial_no=''):
        super().__init__()
        self.exposure = exposure
        self.blacklevel = blacklevel
        self.gain = gain
        self.im = None # last image taken
        
        available_cams = self.discover_available_cameras()
        if available_cams:
            info("Found cams: " + str(available_cams))
            if not serial_no:
                serial_no = available_cams[0]
            self.cam = self.open_camera(serial_no)
            info("Connected to model %s SN %s"%(self.cam.model, serial_no))
            self.update_exposure(self.exposure)
            self.update_blacklevel(self.blacklevel)
            self.update_gain(self.gain)
            self.set_roi(roi)
            self.cam.disarm() # set_roi arms the camera
            self.cam.frames_per_trigger_zero_for_unlimited = 1
            self.cam.arm(1) # software trigger takes 1 image and stores it in buffer
        else: 
            warning("No cameras connected.")
            self.cam = None
        
        
    def __del__(self):
        if self.cam: self.cam.dispose()
        self.dispose()
        
    def connect(self, serial_no):
        """connect to a new camera.
        serial_no:     str the serial number of the new camera"""
        if self.cam: 
            self.cam.disarm()
            self.cam.dispose()
        self.cam  = self.open_camera(serial_no)
    
    def update_exposure(self,exposure=None):
        """Sets and gets exposure time in ms."""
        if exposure != None:
            self.cam.exposure_time_us = int(exposure*1e3)
        self.exposure = self.cam.exposure_time_us/1e3
        return self.exposure

    def update_blacklevel(self,blacklevel):
        """Set blacklevel compensation on or off."""
        self.cam.black_level = int(blacklevel)
        self.blacklevel = self.cam.black_level
        return self.blacklevel
    
    def update_gain(self,gain=None):
        """Set and gets the gain level of the camera.
        
        Parameters:
            gain: gain of the camera. Between 0 - 480.
        """
        if gain != None:
            self.cam.gain = int(gain)
        self.gain = self.cam.gain
        return self.gain
            
    def check_im(self):
        return self.im is None

    def acquire(self, sleep=10e-3):
        """Acquires a single array from the camera with the current settings."""
        self.im = None
        self.cam.issue_software_trigger()
        try:
            while self.check_im():
                self.im = self.cam.get_pending_frame_or_null()
                time.sleep(sleep)
            array = self.im.image_buffer #acquire an image
            if (array == 255).sum() > 0:
                warning('Image saturated.')
            array[array > 255] = 255
            return np.uint8(array)
        except AttributeError as e:
            error("ThorCam could not acquire image\n"+str(e))
            return np.zeros((self.roi[3]-self.roi[1]+1, self.roi[2]-self.roi[0]+1), dtype=np.uint8)
            
    def take_image(self):
        """Gets an image from the camera and returns it in an object containing
        the current camera settings.

        Returns:
            Image object containing the array from the camera and current 
            camera parameters.
        """
        array = self.acquire()
        return Image(array,self.exposure,self.blacklevel,self.roi,self.gain)

    def set_roi(self,roi):
        """Sets the roi applied to images taken by the camera.

        Parameters:
            roi: None for no roi or [xmin,ymin,xmax,ymax]
        """
        if not roi:
            roi = self.get_default_roi()
        self.roi = roi
        self.cam.disarm()
        self.cam.roi = tl_camera.ROI(*roi)
        self.cam.arm(1)
        
    def get_default_roi(self):
        """Set the camera ROI to be the full sensor size"""
        r = self.cam.roi_range
        return [r.upper_left_x_pixels_min, r.upper_left_y_pixels_min,
            r.lower_right_x_pixels_max, r.lower_right_y_pixels_max]

    def get_roi(self):
        return self.roi

    def auto_gain_exposure(self):
        exposure = self.update_exposure()
        gain = self.update_gain()
        while True:
            image = self.take_image()
            max_pixel = image.get_max_pixel(correct_bgnd=False)
            print(exposure,gain,max_pixel)
            if max_pixel < 200:
                if exposure < 0.1:
                    exposure += 0.1
                elif exposure < 85:
                    exposure *= 1.1
                else:
                        gain += 1
            elif max_pixel > 250:
                if gain > 1:
                    gain -= 1
                elif exposure < 1:
                    exposure -= 0.1
                else:                
                    exposure *= 0.9
            else:
                break
            if exposure < 0.05:
                exposure = 0.07
            exposure = self.update_exposure(exposure)
            gain = self.update_gain(gain)
        
        return exposure, gain