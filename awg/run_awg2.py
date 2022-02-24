import sys
import numpy as np
from PyQt5.QtWidgets import QApplication
from awgMaster import awg_window
app = QApplication.instance()
standalone = app is None # false if there is already an app instance
if standalone: # if there isn't an instance, make one
    app = QApplication(sys.argv) 

boss = awg_window(config_file='./state2', AWG_channels=[0,1], 
            default_seq=r'Z:/Tweezer/Code/Python 3.5/PyDex/awg/AWG template sequences/2channel_static.txt',
            rearr_base_path=r'Z:\Tweezer\Code\Python 3.5\PyDex\awg\AWG template sequences\rearr_base2.txt',
            server_port=8629, clientIP='129.234.190.164', client_port=8628)

fdir = 'Z:/Tweezer/Experimental/Setup and characterisation/Settings and calibrations/tweezer calibrations/AWG calibrations'
boss.rr.awg.setCalibration(0, fdir+'/814_H_calFile_17.02.2022.txt', 
    freqs = np.linspace(85,110,100), powers = np.linspace(0,1,200))
boss.rr.awg.setCalibration(1, fdir+'/814_V_calFile_17.02.2022.txt', 
    freqs = np.linspace(85,115,100), powers = np.linspace(0,1,200))

boss.rr.awg.setSampleRate(int(1024e6))
boss.rr.awg.start()

boss.show()
if standalone: # if an app instance was made, execute it
    sys.exit(app.exec_())