import numpy as np
from numpy.random import shuffle
import matplotlib.pyplot as plt
import os
import sys
import time
sys.path.append(r'Z:\Tweezer\Code\Python 3.5\PyDex\networking')
from networker import PyServer, TCPENUM
# from awgHandler import AWG
from PyQt5.QtCore import QThread, pyqtSignal
from PyQt5.QtWidgets import QApplication 

from PIL import Image
os.environ['PATH'] = r'Z:\Tweezer\Code\Python 3.5\thorcam control\dlls'
from thorlabs_tsi_sdk.tl_camera import TLCameraSDK

fdir = r'Z:\Tweezer\Experimental Results\2020\December\11\AWGcalibration5'
img_path = os.path.join(fdir, 'images')
os.makedirs(img_path, exist_ok=True)

daqs = PyServer(host='', port=8622) # server for DAQ
daqs.start()
awgtcp = PyServer(host='', port=8623) # AWG program runs separately
awgtcp.start()

# t = AWG([0,1])
# t.setNumSegments(8)
# t.setTrigger(0) # software trigger
# t.setSegDur(0.002)
# t.load(r'Z:\Tweezer\Code\Python 3.5\PyDex\awg\AWG template sequences\test amp_adjust\single_static.txt')
# t.start()

app = QApplication.instance()
standalone = app is None # false if there is already an app instance
if standalone: # if there isn't an instance, make one
    app = QApplication(sys.argv) 



fs = np.arange(120, 220)
shuffle(fs)
fcalibration = 166
#fs = [f for x in zip(np.ones(len(fs))*166, fs) for f in x]
amps = np.arange(1,220)
shuffle(amps)
acalibration = 220
#amps = [a for x in zip(np.ones(len(amps))*220, amps) for a in x]
os.makedirs(fdir, exist_ok=True)
daqs.add_message(0, fdir+'=save_dir')
daqs.add_message(0, 'reset graph')

with TLCameraSDK() as sdk:
    available_cameras = sdk.discover_available_cameras()
    if len(available_cameras) < 1:
        print("no cameras detected")
    
    with sdk.open_camera(available_cameras[0]) as camera:
        camera.exposure_time_us = 3500  # set exposure to 3.5 ms
        camera.frames_per_trigger_zero_for_unlimited = 1  # start camera in continuous mode
        camera.image_poll_timeout_ms = 1000  # 1 second polling timeout
        old_roi = camera.roi  # store the current roi
        """
        uncomment the line below to set a region of interest (ROI) on the camera
        """
        camera.roi = (1108, 268, 1200, 328)  # set roi to be at (xmin,ymin,xmax,ymax)
        
        """
        uncomment the lines below to set the gain of the camera and read it back in decibels
        """
        #if camera.gain_range.max > 0:
        #    db_gain = 6.0
        #    gain_index = camera.convert_decibels_to_gain(db_gain)
        #    camera.gain = gain_index
        #    print(f"Set camera gain to {camera.convert_gain_to_decibels(camera.gain)}")
        
        camera.arm(2)
        i = 1
        for f in fs:
            for a in amps:
                print([f,a], end='-')
                daqs.add_message(i, 'sets n') # sets the amplitude for reference
                daqs.add_message(i, 'sets n') # sets the amplitude for reference
                # t.setSegment(1, t.dataGen(1,0,'static',1,[f],1,9, a,[1],[0],False,False), 
                #                 t.dataGen(1,1,'static',1,[f],1,9, a,[1],[0],False,False))
                awgtcp.add_message(i, 'set_data=[[0,0,"freqs_input_[MHz]",%s,0],[0,0,"tot_amp_[mV]",%s,0],'%(f,a)
                    +'[1,0,"freqs_input_[MHz]",%s,0],[1,0,"tot_amp_[mV]",%s,0]]'%(f,a))
                time.sleep(0.5)
                daqs.add_message(i, 'start') # tells the DAQ to acquire
                daqs.add_message(i, 'measure') # tells DAQ to add the measurement to the next message
                daqs.add_message(i, 'readout') # reads the measurement
                
                camera.issue_software_trigger()
                frame = camera.get_pending_frame_or_null()
                if frame is not None:
                    np.savetxt(img_path+'\\i'+str(i)+'f'+str(f)+'a'+str(a)+'.csv', frame.image_buffer, delimiter=",")
                else:
                    print("camera timeout reached, skipping this image")
                i += 1
                time.sleep(0.2)
        
            print(['calibration',fcalibration,acalibration], end='-')
            daqs.add_message(i, 'sets n') # sets the amplitude for reference
            daqs.add_message(i, 'sets n') # sets the amplitude for reference
            # t.setSegment(1, t.dataGen(1,0,'static',1,[f],1,9, a,[1],[0],False,False), 
            #                 t.dataGen(1,1,'static',1,[f],1,9, a,[1],[0],False,False))
            awgtcp.add_message(i, 'set_data=[[0,0,"freqs_input_[MHz]",%s,0],[0,0,"tot_amp_[mV]",%s,0],'%(fcalibration,acalibration)
                +'[1,0,"freqs_input_[MHz]",%s,0],[1,0,"tot_amp_[mV]",%s,0]]'%(fcalibration,acalibration))
            time.sleep(0.5)
            daqs.add_message(i, 'start') # tells the DAQ to acquire
            daqs.add_message(i, 'measure') # tells DAQ to add the measurement to the next message
            daqs.add_message(i, 'readout') # reads the measurement
            
            camera.issue_software_trigger()
            frame = camera.get_pending_frame_or_null()
            if frame is not None:
                np.savetxt(img_path+'\\i'+str(i)+'f'+str(fcalibration)+'a'+str(acalibration)+'calibration.csv', frame.image_buffer, delimiter=",")
            else:
                print("camera timeout reached, skipping this image")
            i += 1
            time.sleep(0.1)
        
        daqs.add_message(i, 'DAQgraph.csv=graph_file'%f)
        time.sleep(0.1)
        daqs.add_message(i, 'save graph')
        time.sleep(0.1)
        # daqs.add_message(i, 'reset graph')

        # t.stop()
        camera.disarm()
        
daqs.close()
awgtcp.close()