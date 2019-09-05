"""ExCon - Experimental Control
Stefan Spence 30/08/19

 - A managing script to control separate modules of an experiment:
    creating experimental sequences, queueing a multi-run of
    sequences, controlling an Andor camera to take images, 
    saving images and synchronising with the sequence,
    analysing images, monitoring channels throughout several
    sequence, and displaying results.
"""
import os
import sys
import time
import numpy as np
try:
    from PyQt4.QtGui import QApplication
except ImportError:
    from PyQt5.QtWidgets import QApplication
# change directory to this file's location
os.chdir(os.path.dirname(os.path.realpath(__file__)))
from saia1.main import main_window  # image analysis
from ancam.cameraHandler import camera # manages Andor camera

class master:
    """A manager to synchronise and control experiment modules.
    
    Initiates the Andor camera and connects its completed acquisition
    signal to the image analysis and the image saving modules.
    Uses the queue module to create the list of sequences to run,
    and the bridge module to communicate with Dexter.
    This master module will define the run number. It must confirm that
    each Dexter sequence has run successfully in order to stay synchronised.
    """
    def __init__(self):
        self.cam = camera(config_file='./ancam/AndorCam_config.dat') # Andor camera
        self.mw = main_window('./saia1/config/config.dat') # image analysis
        self.mw.event_im = self.cam.AcquireEnd1 # signal receiving image array
        self.cam.AcquireEnd2.connect(self.update_fid) # sync the image analysis run number
        self.mw.show()

        self._n = 0 # run synchronisation number

    def update_fid(self, im=0):
        """Update the image analysis module's next file ID number
        so that it stays synchronised."""
        self.mw.image_handler.fid = self._n

    def close(self):
        """Proper shut down procedure"""
        self.cam.SafeShutdown()
        self.mw.close()
        
####    ####    ####    #### 

def run():
    """Initiate an app to run the program
    if running in Pylab/IPython then there may already be an app instance"""
    app = QApplication.instance()
    standalone = app is None # false if there is already an app instance
    if standalone: # if there isn't an instance, make one
        app = QApplication(sys.argv) 
        
    boss = master()
    if standalone: # if an app instance was made, execute it
        sys.exit(app.exec_()) # when the window is closed, the python code also stops
   
if __name__ == "__main__":
    run()