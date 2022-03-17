import numpy as np
import matplotlib.pyplot as plt
import pandas as pd
import os
import sys
if not '..' in sys.path: sys.path.append('..')
import time
from thorlabscamera import TCamera, Camera, ImageHandler
from awgHandler import AWG, remoteAWG, phase_minimise
from arrayFitter import imageArray, _transform, _inverse
from PIL import Image

def limit(arr, ulim=1):
    arr[arr>ulim] = ulim
    arr[arr<0] = 0
    return arr

class normaliser:
    """Class to iteratively normalise an array of trap intensities using a CCD.
    awgparam:     str path to file to load awg segment data from
    image_dir:    str directory to save images in
    cam_roi:      list roi in pixel coordinates: [xmin,ymin,xmax,ymax]
    freq_amp_max: [CH0,CH1] cap the fractional optical power to avoid saturation
    rotate:       int degrees anticlockwise to rotate image (arrayFitter will rotate -90)
    remote:       bool True => send TCP messages to control the AWG
    camera:       str which ThorCam is being used. different SDK for scientific cameras
    exposure:     float exposure time for camera in ms
    awgtype:      str which AOD is being controlled; the 814 tweezer or 938"""
    def __init__(self, awgparam='Z:/Tweezer/Experimental/AOD/2D AOD/Array normalisation/6x1array.txt',
            image_dir='Z:/Tweezer/Experimental/AOD/2D AOD/Array normalisation/Normalised', 
            cam_roi=None, fit_roi_size=50, freq_amp_max=[1,1], rotate=0, remote=False,
            camera='uc480', exposure=3, awgtype='814'):
        self.i = 0 # iteration number
        
        # image rotation
        self.rotate = rotate // 90
        ### set up AWG
        if not remote:
            if '814' in awgtype:
                chans = [0,1]
                srate = int(1024e6)
            else:
                chans = [0]
                srate = int(625e6)
            self.awg = AWG(chans, sample_rate=srate)
        else: self.awg = remoteAWG(port=8628)
        fdir = 'Z:/Tweezer/Experimental/Setup and characterisation/Settings and calibrations/tweezer calibrations/AWG calibrations'
        if '814' in awgtype:
            self.awg.setCalibration(0, fdir+'/814_H_calFile_17.02.2022.txt', 
                    freqs = np.linspace(85,110,100), powers = np.linspace(0,1,200))
            self.awg.setCalibration(1, fdir+'/814_V_calFile_17.02.2022.txt', 
                    freqs = np.linspace(85,115,100), powers = np.linspace(0,1,200))
        self.awg.load(awgparam)
        self.awg.param_file = awgparam
        self.awg.setTrigger(0) # 0 software, 1 ext0
        seg = self.awg.filedata["segments"]["segment_0"]
        self.f0 = eval(seg["channel_0"]["freqs_input_[MHz]"])
        self.f1 = eval(seg["channel_1"]["freqs_input_[MHz]"])
        self.ncols = len(self.f0)
        self.nrows = len(self.f1)
        self.a0 = np.array(eval(seg["channel_0"]["freq_amp"]), dtype=float)
        self.a1 = np.array(eval(seg["channel_1"]["freq_amp"]), dtype=float)
        self.ulim = freq_amp_max
        self.amp = int(seg["channel_0"]["tot_amp_[mV]"])
        self.awg.start()
        
        #### set up camera
        if camera=='uc480':
            self.cam = Camera(exposure=exposure, gain=1, roi=cam_roi)
        else:
            self.cam = TCamera(exposure=exposure, gain=1, roi=cam_roi, serial_no='14119')
            
        
        #### image handler saves images
        self.imhand = ImageHandler(image_dir=image_dir,
            measure_params={'rows':self.nrows,'columns':self.ncols,'AWGparam_file':awgparam,
                        'Camera ROI':cam_roi, 'Fit ROI size':fit_roi_size, 'reference':1})
        self.imhand.create_dirs()
        
        #### fitr extracts trap positions and intensities from an image
        self.fitr = imageArray(dims=(self.ncols, self.nrows), roi_size=fit_roi_size, fitmode='sum')
        
    def re_init(self, exposure=3):
        self.awg.load(self.awg.param_file)
        seg = self.awg.filedata["segments"]["segment_0"]
        self.a0 = np.array(eval(seg["channel_0"]["freq_amp"]), dtype=float)
        self.a1 = np.array(eval(seg["channel_1"]["freq_amp"]), dtype=float)
        self.amp = int(seg["channel_0"]["tot_amp_[mV]"])
        self.awg.start()
        self.cam.update_exposure(3)
        self.prepare()
        
    def prepare(self):
        """Set camera and reference value to normalise to"""
        self.cam.auto_gain_exposure()
        self.cam.update_exposure(self.cam.exposure*0.6) # saturating is bad
        time.sleep(0.1)
        self.fitr.setRef(self.get_image(-1, -1, auto_exposure=False)) # reference image should not be rotated
        self.imhand.measure_params['reference'] = self.fitr.ref

    def unrotate(self, xmin, ymin, xmax, ymax, imxmax, imymax):
        """Undo the image transform to get unrotated points"""
        if self.rotate == -1:
            return ymin, imxmax - xmax, ymax, imxmax - xmin
        elif self.rotate == 1:
            return imymax - ymax, xmin, imymax - ymin, xmax
        elif self.rotate == 2:
            return imxmax - xmax, imymax - ymax, imxmax - xmin, imymax - ymin
        else: return xmin, ymin, xmax, ymax
        
        
    def process(self, arr):
        """Get intensities of traps in image and return correction factors"""
        self.fitr._imvals = arr
        self.fitr.fitImage()
        return self.fitr.getScaleFactors()
        
    def get_image(self, repetition, iteration=0, sleep=0.3, auto_exposure=False):
        """Take and save an image and a background image"""
        self.awg.start() # show array
        time.sleep(sleep)
        if auto_exposure:
            self.cam.auto_gain_exposure() # adjust exposure to avoid saturation
        image = self.cam.take_image()
        self.awg.stop()  # awg off gives background image
        time.sleep(sleep)
        bgnd = self.cam.take_image()
        image.add_background(bgnd)
        array = image.get_bgnd_corrected_array()
        image.add_property('intensity_correction_iteration',iteration)
        image.add_property('rep',repetition)
        self.imhand.save(image)
        return np.rot90(array, self.rotate)

    def get_images(self, reps=100, iteration=0, sleep=0.3):
        """Take images in a loop"""
        ave_im = np.zeros(self.get_image(-1,iteration,sleep).shape)
        self.awg.stop() # awg might crash if it's started twice
        time.sleep(sleep)
        for i in range(reps):
            ave_im += self.get_image(i, iteration, sleep)
        return ave_im / reps
        
    def normalise(self, num_ims=5, num_ave=3, precision=0.01, max_iter=7):
        """Take images and then produce corrections factors until desired precision
        or max iterations are reached.
        num_ims:     int number of images to take for each iteration of normalisation
        num_ave:     int number of sets to split the images into to take averages
        max_iter:    int stop the normalisation after this many iterations
        precision:   float stop the normalisation when cost is this value"""
        history = [[1, self.a0, self.a1]]
        for i in range(max_iter):
            # take images and calculate correction factors
            self.save_meta_param(i)
            c0 = np.zeros(self.ncols)
            c1 = np.zeros(self.nrows)
            for j in range(num_ave):
                ave_im = self.get_images(round(num_ims/num_ave), iteration=i)
                c = self.process(ave_im)
                c0 += c[1]
                c1 += c[0]
            # take new scale factors but don't let them go above the original
            self.a0 = limit(self.a0*c0/num_ave, ulim=self.ulim[0])
            self.a1 = limit(self.a1*c1/num_ave, ulim=self.ulim[1])
            self.awg.arrayGen(self.ncols, self.nrows, 0, freqs=[self.f0, self.f1], 
                amps=[self.a0, self.a1], AmV=self.amp, duration=1, 
                freqAdjust=True, ampAdjust=True, phaseAdjust=True)
            c = self.fitr.df['I0'].values.reshape(self.fitr._s)
            if any([I0 < 0 for I0 in c]):
                print('\nCamera saturated, aborting optimisation...')
                return history
            pack = [np.sum(np.abs(1 - c / self.fitr.ref)), self.a0, self.a1]
            history.append(pack)
            print(i, *[x+str(y) for x,y in zip(
                    ['\n Relative Error:  ', '\nCH1: ', '\nCH2: '], pack)])
            if pack[0] < precision:
                break
        # find min relative error and set values
        h = history[np.argmin([vals[0] for vals in history])]
        self.awg.arrayGen(self.ncols, self.nrows, 0, freqs=[self.f0, self.f1], 
                amps=[h[1], h[2]], AmV=self.amp, duration=1, 
                freqAdjust=True, ampAdjust=True, phaseAdjust=True)
        self.awg.filedata = eval(str(self.awg.filedata))
        self.awg.saveData(os.path.splitext(self.awg.param_file)[0] + '_normalised.txt')
        self.i = 0
        return history
        
    def step(self, amps, num_ims=5, sleep=0.3):
        """load amps onto the AWG, then take images and evaluate the cost function.
        amps:      1D array with amplitudes for both channels
        num_ims:   int number of images to average together
        sleep:     float ms duration to wait for AWG to turn on and camera to take images"""
        # take images and calculate correction factors
        self.a0 = np.array(amps[:self.ncols])
        self.a1 = np.array(amps[self.ncols:])
        self.awg.arrayGen(self.ncols, self.nrows, 0, freqs=[self.f0, self.f1], 
                amps=[self.a0, self.a1], AmV=self.amp, duration=1, 
                freqAdjust=True, ampAdjust=True, phaseAdjust=True)
        time.sleep(sleep)
        ave_im = self.get_images(num_ims, iteration=self.i, sleep=sleep)
        self.process(ave_im)
        #c = self.fitr.df['I0'] / self.fitr.ref # #c.std()/c.mean()
        return np.sum(np.abs(1 - self.fitr.df['I0'] / self.fitr.ref))
        
    def save_meta_param(self, i=0, basedir=''):
        if not basedir:
            basedir = self.imhand.image_dir
        if 'Iteration' not in basedir:
            iterdir = os.path.join(basedir, 'Iteration'+str(i))
        else: 
            iterdir = os.path.join(os.path.dirname(basedir), 'Iteration'+str(i))
        self.imhand.measure_params['AWGparams'] = self.awg.filedata
        self.imhand.create_dirs(iterdir)
        self.i = i
    
if __name__ == "__main__":
    boss = normaliser(image_dir='Z:/Tweezer/Experimental/AOD/2D AOD/Array normalisation/Measure0',
        cam_roi=[300,500,850,650], fit_roi_size=40, freq_amp_max=(0.35,1)) 
    history = boss.normalise()
    cost = [x[0] for x in history[1:]]
    plt.figure()
    plt.semilogy(np.arange(len(cost))+1, cost, 'o-')
    plt.xlabel('Iteration')
    plt.ylabel('Relative Error')
    plt.figure()
    boss.awg.start()
    time.sleep(0.5)
    plt.imshow(boss.cam.take_image().array)
    plt.show()
    