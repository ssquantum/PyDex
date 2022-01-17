# -*- coding: cp1252 -*-
"""
Version 3 of the Python GUI for the DDS control.

Change log:
1. DDS module addresses
2. UART structure contains 5 bytes before data. See supporting documents.
3. Functions are split into separate files
4. add TCP communication with PyDex

"""
import serial
import time
import sys
import os
os.system("color") # allows error/warning/info messages to print in colour
import glob
import datetime
import pickle
import json
import numpy as np
from collections import OrderedDict

from PyQt5 import QtCore, QtGui, QtWidgets

from DDS_PSoC_functions import PSoC

if '.' not in sys.path: sys.path.append('.')
if '..' not in sys.path: sys.path.append('..')
from networking.client import PyClient, reset_slot

class CustomComboBox(QtWidgets.QComboBox):
    popupRequest = QtCore.pyqtSignal()
    def showPopup(self): # override to add in signal
        self.popupRequest.emit()
        super(CustomComboBox, self).showPopup()

class Ui_MainWindow(PSoC):
    
    mode_options = ['single tone', 'RAM', 'single tone + ramp', 'RAM + ramp', 'FPGA'] # allowed modes of operation

    amp_options = ['fixed amp', 'manual on/off', 'amp scaling']
    RAM_functions = ['Linear', 'Gaussian', 'Minimum Jerk', 'Exponential', 'Logarithmic']
    RAM_data_type = {'Frequency' : np.array([0,0]),
                        'Phase' : np.array([0,1]),
                        'Amplitude' : np.array([1,0]),
                        'Polar' : np.array([1,1])}

    RAM_controls = {"Disable" : np.array([0,0,0,0]),
                    "Burst. Profiles 0 - 1" : np.array([0,0,0,1]),
                    "Burst. Profiles 0 - 2" : np.array([0,0,1,0]),
                    "Burst. Profiles 0 - 3": np.array([0,0,1,1]),
                    "Burst. Profiles 0 - 4": np.array([0,1,0,0]),
                    "Burst. Profiles 0 - 5": np.array([0,1,0,1]),
                    "Burst. Profiles 0 - 6": np.array([0,1,1,0]),
                    "Burst. Profiles 0 - 7": np.array([0,1,1,1]),
                    "Continuous. Profiles 0 - 1": np.array([1,0,0,0]),
                    "Continuous. Profiles 0 - 2": np.array([1,0,0,1]),
                    "Continuous. Profiles 0 - 3": np.array([1,0,1,0]),
                    "Continuous. Profiles 0 - 4": np.array([1,0,1,1]),
                    "Continuous. Profiles 0 - 5": np.array([1,1,0,0]),
                    "Continuous. Profiles 0 - 6": np.array([1,1,0,1]),
                    "Continuous. Profiles 0 - 7": np.array([1,1,1,1])}

    RAM_profile_mode = {"Direct" : np.array([0,0,0]),
                        "Ramp-up" : np.array([0,0,1]),
                        "Bidirectional ramp" : np.array([0,1,0]),
                        "Continuous bidirectional ramp" : np.array([0,1,1]),
                        "Continuous recirculate" : np.array([1,0,0])}
    
    DRG_modes = ['DRG Frequency', 'DRG Phase', 'DRG Amplitude']

    COMlabels = ['420', '977', '1013', '1557', '']

    def __init__(self, port=8630, host='localhost', alim=1, Today_file='', 
                 enable_print = False #Prints additional information such as the serial data to the terminal or command line
                 ):
        super(Ui_MainWindow, self).__init__()
        #import DDS_PSoC_functions as PSoC
        self.enable_print = enable_print
        self.Today_file = Today_file

        #self.FPGA = FPGA
        self.connected = False
        
        self.mode = 'single tone'  # so PyDex knows which mode we're using.

        # TCP server for communication with PyDex
        self.tcp = PyClient(host=host, port=port)
        # reset_slot(self.tcp.dxnum, self.set_n, True)
        reset_slot(self.tcp.textin, self.respond, True)
        self.tcp.start()

        # store profiles for each COM port
        self.ind = 0 # which COM port's profiles are selected

        # For the single tone profiles
        self.fout = np.zeros((5,8))
        self.amp = np.zeros((5,8))
        self.tht = np.zeros((5,8))

        # For the RAM profiles
        self.Start_Address = np.zeros((5,8))
        self.End_Address = np.zeros((5,8))
        self.Rate = np.zeros((5,8))

        self.No_dwell = np.zeros((5,8))
        self.Zero_crossing = np.zeros((5,8))
        self.RAM_playback_mode = np.zeros((5, 8, 3))


        #Amplitude control
        self.OSK_enable = 0
        self.Manual_OSK = 0
        self.AMP_scale = 1

        self.load_FPGA_file = False
        self.memory_type = True # if true coe files else hex file
        self.pll_type = True # if true coe files else hex file
        self.Memory_file_generated = False

        self.FM_gain_value = np.array([0,0,0,0])

        # Auxillary control parameters
        self.FTW = np.ones(5)*110
        self.POW = np.zeros(5)
        self.AMW = np.ones(5)

        # Amplitude limit
        self.Alim = alim
        self.dbl_validator = QtGui.QDoubleValidator(0,self.Alim,6)
        self.dbl_validator.fixup = self.dbl_fixup
        
        #RAM playblack options
        self.RAM_enable = 0
        self.RAM_playback_dest = np.array([0,0])
        self.Int_profile_cntrl = np.array([0,0,0,0])

        self.RAM_modulation_data = [[]]*5
        self.RAM_data_filename = ['']*5

        #Register arrays
        self.CFR1 = np.zeros(32, dtype = np.bool_())
        self.CFR2 = np.zeros(32, dtype = np.bool_())
        self.RAM_reg = np.zeros(1024)

        self.DGR_params = np.zeros(6)
        self.FPGA_params = np.array([0,0,1])
        #FPGA control
        #Matched_latency_en = 2
        #Data_assembler_hold = 1
        #Parallel_en = 0


    def setupUi_coms(self, MainWindow):
        self.MainWindow = MainWindow
        MainWindow.setObjectName("MainWindow")
        MainWindow.resize(837, 600)
        self.centralwidget = QtWidgets.QWidget(MainWindow)
        self.centralwidget.setObjectName("centralwidget")

        self.tabWidget = QtWidgets.QTabWidget(self.centralwidget)
        self.tabWidget.setGeometry(QtCore.QRect(10, 10, 821, 531))
        self.tabWidget.setObjectName("tabWidget")

        self.Coms = QtWidgets.QWidget()
        self.Coms.setObjectName("Coms")

        ### Output display ###
        self.Serial_com = QtWidgets.QTextBrowser(self.Coms)
        self.Serial_com.setGeometry(QtCore.QRect(10, 280, 791, 192))
        self.Serial_com.setObjectName("Serial_com")

        self.label_147 = QtWidgets.QLabel(self.Coms)
        self.label_147.setGeometry(QtCore.QRect(10, 260, 91, 16))
        self.label_147.setObjectName("label_147")

        ### COM port number ###
        self.COM_no = CustomComboBox(self.Coms)
        self.COM_no.setGeometry(QtCore.QRect(108, 21, 91, 41))
        self.COM_no.setObjectName("COM_no")
        self.COM_no.addItem('--')
        self.COM_no.popupRequest.connect(self.PortSetup)
        
        self.label_148 = QtWidgets.QLabel(self.Coms)
        self.label_148.setGeometry(QtCore.QRect(10, 30, 91, 16))
        self.label_148.setObjectName("label_148")

        ### Connect device button ###
        self.Connect = QtWidgets.QPushButton(self.Coms)
        self.Connect.setGeometry(QtCore.QRect(210, 20, 111, 41))
        self.Connect.setObjectName("Connect")
        self.Connect.clicked.connect(self.Configure_serial_port)

        ### Disconnect device button ###
        self.Disconnect = QtWidgets.QPushButton(self.Coms)
        self.Disconnect.setGeometry(QtCore.QRect(330, 20, 111, 41))
        self.Disconnect.setObjectName("Disconnect")
        self.Disconnect.clicked.connect(self.Disconnect_serial_port)

        ### Debug request
        self.Debug = QtWidgets.QPushButton(self.Coms)
        self.Debug.setGeometry(QtCore.QRect(210, 120, 111, 41))
        self.Debug.setObjectName("Debug")
        self.Debug.clicked.connect(self.Register_debugger)
        
        ### TCP communication with PyDex
        self.PyDexTCP = QtWidgets.QPushButton(self.Coms)
        self.PyDexTCP.setGeometry(QtCore.QRect(330, 20, 111, 41))
        self.PyDexTCP.setObjectName("PyDex_TCP_reset")
        self.PyDexTCP.clicked.connect(self.Pydex_tcp_reset)

        self.Module_address = QtWidgets.QComboBox(self.Coms)
        self.Module_address.setGeometry(QtCore.QRect(108, 121, 91, 41))
        self.Module_address.setObjectName("Module_address")
        for jc in range(1,6):
            self.Module_address.addItem(str(jc))

        self.label_150 = QtWidgets.QLabel(self.Coms)
        self.label_150.setGeometry(QtCore.QRect(10, 130, 91, 16))
        self.label_150.setObjectName("label_150")


        self.GB_Aux = QtWidgets.QGroupBox(self.Coms)
        self.GB_Aux.setGeometry(QtCore.QRect(540, 10, 270, 200))
        self.GB_Aux.setAutoFillBackground(True)
        self.GB_Aux.setObjectName("GB_Aux")
        self.Freq_aux = QtWidgets.QLineEdit(self.GB_Aux)
        self.Freq_aux.setGeometry(QtCore.QRect(70, 20, 151, 21))
        self.Freq_aux.setObjectName("Freq_aux")
        self.Freq_aux.editingFinished.connect(self.set_ram_ftw)
        self.label_5 = QtWidgets.QLabel(self.GB_Aux)
        self.label_5.setGeometry(QtCore.QRect(10, 20, 65, 16))
        self.label_5.setObjectName("label_5")
        self.label_7 = QtWidgets.QLabel(self.GB_Aux)
        self.label_7.setGeometry(QtCore.QRect(230, 20, 25, 16))
        self.label_7.setObjectName("label_7")
        self.label_8 = QtWidgets.QLabel(self.GB_Aux)
        self.label_8.setGeometry(QtCore.QRect(230, 60, 25, 16))
        self.label_8.setObjectName("label_8")
        self.label_9 = QtWidgets.QLabel(self.GB_Aux)
        self.label_9.setGeometry(QtCore.QRect(10, 60, 65, 16))
        self.label_9.setObjectName("label_9")
        self.Phase_aux = QtWidgets.QLineEdit(self.GB_Aux)
        self.Phase_aux.setGeometry(QtCore.QRect(70, 60, 151, 21))
        self.Phase_aux.setObjectName("Phase_aux")
        self.Phase_aux.editingFinished.connect(self.set_ram_pow)
        self.label_AMWunits = QtWidgets.QLabel(self.GB_Aux)
        self.label_AMWunits.setGeometry(QtCore.QRect(230, 100, 25, 16))
        self.label_AMWunits.setObjectName("label_AMWunits")
        self.label_AMW = QtWidgets.QLabel(self.GB_Aux)
        self.label_AMW.setGeometry(QtCore.QRect(10, 100, 65, 16))
        self.label_AMW.setObjectName("label_AMW")
        self.Amp_aux = QtWidgets.QLineEdit(self.GB_Aux)
        self.Amp_aux.setGeometry(QtCore.QRect(70, 100, 151, 21))
        self.Amp_aux.setObjectName("Amp_aux")
        self.Amp_aux.editingFinished.connect(self.set_ram_amw)
        self.Amp_aux.editingFinished.connect(self.reload_RAM) # reload data if this parameter is changed
        self.Amp_aux.editingFinished.connect(lambda: self.Amp_aux.setText(self.dbl_fixup(self.Amp_aux.text())))
        self.label_ALIMunits = QtWidgets.QLabel(self.GB_Aux)
        self.label_ALIMunits.setGeometry(QtCore.QRect(230, 140, 25, 16))
        self.label_ALIMunits.setObjectName("label_ALIMunits")
        self.label_ALIM = QtWidgets.QLabel(self.GB_Aux)
        self.label_ALIM.setGeometry(QtCore.QRect(10, 140, 65, 16))
        self.label_ALIM.setObjectName("label_ALIM")
        self.Amp_lim = QtWidgets.QLineEdit(self.GB_Aux)
        self.Amp_lim.setGeometry(QtCore.QRect(70, 140, 151, 21))
        self.Amp_lim.setObjectName("Amp_lim")
        self.Amp_lim.editingFinished.connect(self.set_amp_lim) # reset validators on amp inputs
        self.label_RAMname = QtWidgets.QLabel(self.GB_Aux)
        self.label_RAMname.setGeometry(QtCore.QRect(10, 180, 65, 16))
        self.label_RAMname.setObjectName("label_RAMname")
        self.RAM_fname = QtWidgets.QLabel(self.GB_Aux)
        self.RAM_fname.setGeometry(QtCore.QRect(70, 180, 151, 16))
        self.RAM_fname.setObjectName("RAM_fname")



        self.tabWidget.addTab(self.Coms, "")
        self.setupUi_stp(MainWindow)

        ########################################################################################################################
    def setupUi_stp(self, MainWindow):

        self.Single_tone = QtWidgets.QWidget()
        self.Single_tone.setObjectName("Single_tone")

        ##### Profile 0 #####
        self.GB_P0 = QtWidgets.QGroupBox(self.Single_tone)

        self.GB_P0.setGeometry(QtCore.QRect(10, 20, 261, 141))
        self.GB_P0.setAutoFillBackground(True)
        self.GB_P0.setObjectName("GB_P0")

        self.Freq_P0 = QtWidgets.QLineEdit(self.GB_P0)
        self.Freq_P0.setGeometry(QtCore.QRect(70, 20, 151, 21))
        self.Freq_P0.setObjectName("Freq_P0")
        self.Freq_P0.i = 0
        self.Freq_P0.editingFinished.connect(self.set_stp_freq)

        self.label = QtWidgets.QLabel(self.GB_P0)
        self.label.setGeometry(QtCore.QRect(10, 20, 61, 16))
        self.label.setObjectName("label")

        self.label_2 = QtWidgets.QLabel(self.GB_P0)
        self.label_2.setGeometry(QtCore.QRect(230, 20, 21, 16))
        self.label_2.setObjectName("label_2")

        self.label_3 = QtWidgets.QLabel(self.GB_P0)
        self.label_3.setGeometry(QtCore.QRect(230, 60, 21, 16))
        self.label_3.setObjectName("label_3")

        self.label_4 = QtWidgets.QLabel(self.GB_P0)
        self.label_4.setGeometry(QtCore.QRect(10, 60, 61, 16))
        self.label_4.setObjectName("label_4")

        self.Phase_P0 = QtWidgets.QLineEdit(self.GB_P0)
        self.Phase_P0.setGeometry(QtCore.QRect(70, 60, 151, 21))
        self.Phase_P0.setObjectName("Phase_P0")
        self.Phase_P0.i = 0
        self.Phase_P0.editingFinished.connect(self.set_stp_tht)

        self.Amp_P0 = QtWidgets.QLineEdit(self.GB_P0)
        self.Amp_P0.setGeometry(QtCore.QRect(70, 100, 151, 21))
        self.Amp_P0.setObjectName("Amp_P0")
        self.Amp_P0.i = 0
        self.Amp_P0.editingFinished.connect(self.set_stp_amp)

        self.label_6 = QtWidgets.QLabel(self.GB_P0)
        self.label_6.setGeometry(QtCore.QRect(10, 100, 61, 16))
        self.label_6.setObjectName("label_6")

        ##### Profile 1 #####
        self.GB_P1 = QtWidgets.QGroupBox(self.Single_tone)
        self.GB_P1.setGeometry(QtCore.QRect(10, 180, 261, 141))
        self.GB_P1.setAutoFillBackground(True)
        self.GB_P1.setObjectName("GB_P1")

        self.Freq_P1 = QtWidgets.QLineEdit(self.GB_P1)
        self.Freq_P1.setGeometry(QtCore.QRect(70, 20, 151, 21))
        self.Freq_P1.setObjectName("Freq_P1")
        self.Freq_P1.i = 1
        self.Freq_P1.editingFinished.connect(self.set_stp_freq)

        self.label_26 = QtWidgets.QLabel(self.GB_P1)
        self.label_26.setGeometry(QtCore.QRect(10, 20, 61, 16))
        self.label_26.setObjectName("label_26")

        self.label_27 = QtWidgets.QLabel(self.GB_P1)
        self.label_27.setGeometry(QtCore.QRect(230, 20, 21, 16))
        self.label_27.setObjectName("label_27")

        self.label_28 = QtWidgets.QLabel(self.GB_P1)
        self.label_28.setGeometry(QtCore.QRect(230, 60, 21, 16))
        self.label_28.setObjectName("label_28")

        self.label_29 = QtWidgets.QLabel(self.GB_P1)
        self.label_29.setGeometry(QtCore.QRect(10, 60, 61, 16))
        self.label_29.setObjectName("label_29")

        self.Phase_P1 = QtWidgets.QLineEdit(self.GB_P1)
        self.Phase_P1.setGeometry(QtCore.QRect(70, 60, 151, 21))
        self.Phase_P1.setObjectName("Phase_P1")
        self.Phase_P1.i = 1
        self.Phase_P1.editingFinished.connect(self.set_stp_tht)

        self.Amp_P1 = QtWidgets.QLineEdit(self.GB_P1)
        self.Amp_P1.setGeometry(QtCore.QRect(70, 100, 151, 21))
        self.Amp_P1.setObjectName("Amp_P1")
        self.Amp_P1.i = 1
        self.Amp_P1.editingFinished.connect(self.set_stp_amp)

        self.label_30 = QtWidgets.QLabel(self.GB_P1)
        self.label_30.setGeometry(QtCore.QRect(10, 100, 61, 16))
        self.label_30.setObjectName("label_30")

        ##### Profile 2 #####
        self.GB_P2 = QtWidgets.QGroupBox(self.Single_tone)
        self.GB_P2.setGeometry(QtCore.QRect(10, 340, 261, 141))
        self.GB_P2.setAutoFillBackground(True)
        self.GB_P2.setObjectName("GB_P2")

        self.Freq_P2 = QtWidgets.QLineEdit(self.GB_P2)
        self.Freq_P2.setGeometry(QtCore.QRect(70, 20, 151, 21))
        self.Freq_P2.setObjectName("Freq_P2")
        self.Freq_P2.i = 2
        self.Freq_P2.editingFinished.connect(self.set_stp_freq)

        self.label_36 = QtWidgets.QLabel(self.GB_P2)
        self.label_36.setGeometry(QtCore.QRect(10, 20, 61, 16))
        self.label_36.setObjectName("label_36")

        self.label_37 = QtWidgets.QLabel(self.GB_P2)
        self.label_37.setGeometry(QtCore.QRect(230, 20, 21, 16))
        self.label_37.setObjectName("label_37")

        self.label_38 = QtWidgets.QLabel(self.GB_P2)
        self.label_38.setGeometry(QtCore.QRect(230, 60, 21, 16))
        self.label_38.setObjectName("label_38")

        self.label_39 = QtWidgets.QLabel(self.GB_P2)
        self.label_39.setGeometry(QtCore.QRect(10, 60, 61, 16))
        self.label_39.setObjectName("label_39")

        self.Phase_P2 = QtWidgets.QLineEdit(self.GB_P2)
        self.Phase_P2.setGeometry(QtCore.QRect(70, 60, 151, 21))
        self.Phase_P2.setObjectName("Phase_P2")
        self.Phase_P2.i = 2
        self.Phase_P2.editingFinished.connect(self.set_stp_tht)

        self.Amp_P2 = QtWidgets.QLineEdit(self.GB_P2)
        self.Amp_P2.setGeometry(QtCore.QRect(70, 100, 151, 21))
        self.Amp_P2.setObjectName("Amp_P2")
        self.Amp_P2.i = 2
        self.Amp_P2.editingFinished.connect(self.set_stp_amp)

        self.label_40 = QtWidgets.QLabel(self.GB_P2)
        self.label_40.setGeometry(QtCore.QRect(10, 100, 61, 16))
        self.label_40.setObjectName("label_40")

        ##### Profile 3 #####

        self.GB_P3 = QtWidgets.QGroupBox(self.Single_tone)
        self.GB_P3.setGeometry(QtCore.QRect(280, 20, 261, 141))
        self.GB_P3.setAutoFillBackground(True)
        self.GB_P3.setObjectName("GB_P3")

        self.Freq_P3 = QtWidgets.QLineEdit(self.GB_P3)
        self.Freq_P3.setGeometry(QtCore.QRect(70, 20, 151, 21))
        self.Freq_P3.setObjectName("Freq_P3")
        self.Freq_P3.i = 3
        self.Freq_P3.editingFinished.connect(self.set_stp_freq)

        self.label_41 = QtWidgets.QLabel(self.GB_P3)
        self.label_41.setGeometry(QtCore.QRect(10, 20, 61, 16))
        self.label_41.setObjectName("label_41")

        self.label_42 = QtWidgets.QLabel(self.GB_P3)
        self.label_42.setGeometry(QtCore.QRect(230, 20, 21, 16))
        self.label_42.setObjectName("label_42")

        self.label_43 = QtWidgets.QLabel(self.GB_P3)
        self.label_43.setGeometry(QtCore.QRect(230, 60, 21, 16))
        self.label_43.setObjectName("label_43")

        self.label_44 = QtWidgets.QLabel(self.GB_P3)
        self.label_44.setGeometry(QtCore.QRect(10, 60, 61, 16))
        self.label_44.setObjectName("label_44")

        self.Phase_P3 = QtWidgets.QLineEdit(self.GB_P3)
        self.Phase_P3.setGeometry(QtCore.QRect(70, 60, 151, 21))
        self.Phase_P3.setObjectName("Phase_P3")
        self.Phase_P3.i = 3
        self.Phase_P3.editingFinished.connect(self.set_stp_tht)

        self.Amp_P3 = QtWidgets.QLineEdit(self.GB_P3)
        self.Amp_P3.setGeometry(QtCore.QRect(70, 100, 151, 21))
        self.Amp_P3.setObjectName("Amp_P3")
        self.Amp_P3.i = 3
        self.Amp_P3.editingFinished.connect(self.set_stp_amp)

        self.label_45 = QtWidgets.QLabel(self.GB_P3)
        self.label_45.setGeometry(QtCore.QRect(10, 100, 61, 16))
        self.label_45.setObjectName("label_45")

        ##### Profile 4 #####

        self.GB_P4 = QtWidgets.QGroupBox(self.Single_tone)
        self.GB_P4.setGeometry(QtCore.QRect(280, 180, 261, 141))
        self.GB_P4.setAutoFillBackground(True)
        self.GB_P4.setObjectName("GB_P4")

        self.Freq_P4 = QtWidgets.QLineEdit(self.GB_P4)
        self.Freq_P4.setGeometry(QtCore.QRect(70, 20, 151, 21))
        self.Freq_P4.setObjectName("Freq_P4")
        self.Freq_P4.i = 4
        self.Freq_P4.editingFinished.connect(self.set_stp_freq)

        self.label_46 = QtWidgets.QLabel(self.GB_P4)
        self.label_46.setGeometry(QtCore.QRect(10, 20, 61, 16))
        self.label_46.setObjectName("label_46")

        self.label_47 = QtWidgets.QLabel(self.GB_P4)
        self.label_47.setGeometry(QtCore.QRect(230, 20, 21, 16))
        self.label_47.setObjectName("label_47")

        self.label_48 = QtWidgets.QLabel(self.GB_P4)
        self.label_48.setGeometry(QtCore.QRect(230, 60, 21, 16))
        self.label_48.setObjectName("label_48")

        self.label_49 = QtWidgets.QLabel(self.GB_P4)
        self.label_49.setGeometry(QtCore.QRect(10, 60, 61, 16))
        self.label_49.setObjectName("label_49")

        self.Phase_P4 = QtWidgets.QLineEdit(self.GB_P4)
        self.Phase_P4.setGeometry(QtCore.QRect(70, 60, 151, 21))
        self.Phase_P4.setObjectName("Phase_P4")
        self.Phase_P4.i = 4
        self.Phase_P4.editingFinished.connect(self.set_stp_tht)

        self.Amp_P4 = QtWidgets.QLineEdit(self.GB_P4)
        self.Amp_P4.setGeometry(QtCore.QRect(70, 100, 151, 21))
        self.Amp_P4.setObjectName("Amp_P4")
        self.Amp_P4.i = 4
        self.Amp_P4.editingFinished.connect(self.set_stp_amp)

        self.label_50 = QtWidgets.QLabel(self.GB_P4)
        self.label_50.setGeometry(QtCore.QRect(10, 100, 61, 16))
        self.label_50.setObjectName("label_50")

        self.GB_P5 = QtWidgets.QGroupBox(self.Single_tone)
        self.GB_P5.setGeometry(QtCore.QRect(280, 340, 261, 141))
        self.GB_P5.setAutoFillBackground(True)
        self.GB_P5.setObjectName("GB_P5")

        self.Freq_P5 = QtWidgets.QLineEdit(self.GB_P5)
        self.Freq_P5.setGeometry(QtCore.QRect(70, 20, 151, 21))
        self.Freq_P5.setObjectName("Freq_P5")
        self.Freq_P5.i = 5
        self.Freq_P5.editingFinished.connect(self.set_stp_freq)

        self.label_51 = QtWidgets.QLabel(self.GB_P5)
        self.label_51.setGeometry(QtCore.QRect(10, 20, 61, 16))
        self.label_51.setObjectName("label_51")

        self.label_52 = QtWidgets.QLabel(self.GB_P5)
        self.label_52.setGeometry(QtCore.QRect(230, 20, 21, 16))
        self.label_52.setObjectName("label_52")

        self.label_53 = QtWidgets.QLabel(self.GB_P5)
        self.label_53.setGeometry(QtCore.QRect(230, 60, 21, 16))
        self.label_53.setObjectName("label_53")

        self.label_54 = QtWidgets.QLabel(self.GB_P5)
        self.label_54.setGeometry(QtCore.QRect(10, 60, 61, 16))
        self.label_54.setObjectName("label_54")

        self.Phase_P5 = QtWidgets.QLineEdit(self.GB_P5)
        self.Phase_P5.setGeometry(QtCore.QRect(70, 60, 151, 21))
        self.Phase_P5.setObjectName("Phase_P5")
        self.Phase_P5.i = 5
        self.Phase_P5.editingFinished.connect(self.set_stp_tht)

        self.Amp_P5 = QtWidgets.QLineEdit(self.GB_P5)
        self.Amp_P5.setGeometry(QtCore.QRect(70, 100, 151, 21))
        self.Amp_P5.setObjectName("Amp_P5")
        self.Amp_P5.i = 5
        self.Amp_P5.editingFinished.connect(self.set_stp_amp)

        self.label_55 = QtWidgets.QLabel(self.GB_P5)
        self.label_55.setGeometry(QtCore.QRect(10, 100, 61, 16))
        self.label_55.setObjectName("label_55")

        ##### Profile 6 #####
        self.GB_P6 = QtWidgets.QGroupBox(self.Single_tone)
        self.GB_P6.setGeometry(QtCore.QRect(550, 20, 261, 141))
        self.GB_P6.setAutoFillBackground(True)
        self.GB_P6.setObjectName("GB_P6")

        self.Freq_P6 = QtWidgets.QLineEdit(self.GB_P6)
        self.Freq_P6.setGeometry(QtCore.QRect(70, 20, 151, 21))
        self.Freq_P6.setObjectName("Freq_P6")
        self.Freq_P6.i = 6
        self.Freq_P6.editingFinished.connect(self.set_stp_freq)

        self.label_56 = QtWidgets.QLabel(self.GB_P6)
        self.label_56.setGeometry(QtCore.QRect(10, 20, 61, 16))
        self.label_56.setObjectName("label_56")

        self.label_57 = QtWidgets.QLabel(self.GB_P6)
        self.label_57.setGeometry(QtCore.QRect(230, 20, 21, 16))
        self.label_57.setObjectName("label_57")

        self.label_58 = QtWidgets.QLabel(self.GB_P6)
        self.label_58.setGeometry(QtCore.QRect(230, 60, 21, 16))
        self.label_58.setObjectName("label_58")

        self.label_59 = QtWidgets.QLabel(self.GB_P6)
        self.label_59.setGeometry(QtCore.QRect(10, 60, 61, 16))
        self.label_59.setObjectName("label_59")

        self.Phase_P6 = QtWidgets.QLineEdit(self.GB_P6)
        self.Phase_P6.setGeometry(QtCore.QRect(70, 60, 151, 21))
        self.Phase_P6.setObjectName("Phase_P6")
        self.Phase_P6.i = 6
        self.Phase_P6.editingFinished.connect(self.set_stp_tht)

        self.Amp_P6 = QtWidgets.QLineEdit(self.GB_P6)
        self.Amp_P6.setGeometry(QtCore.QRect(70, 100, 151, 21))
        self.Amp_P6.setObjectName("Amp_P6")
        self.Amp_P6.i = 6
        self.Amp_P6.editingFinished.connect(self.set_stp_amp)

        self.label_60 = QtWidgets.QLabel(self.GB_P6)
        self.label_60.setGeometry(QtCore.QRect(10, 100, 61, 16))
        self.label_60.setObjectName("label_60")

        ##### Profile 7 #####
        self.GB_P7 = QtWidgets.QGroupBox(self.Single_tone)
        self.GB_P7.setGeometry(QtCore.QRect(550, 180, 261, 141))
        self.GB_P7.setAutoFillBackground(True)
        self.GB_P7.setObjectName("GB_P7")

        self.Freq_P7 = QtWidgets.QLineEdit(self.GB_P7)
        self.Freq_P7.setGeometry(QtCore.QRect(70, 20, 151, 21))
        self.Freq_P7.setObjectName("Freq_P7")
        self.Freq_P7.i = 7
        self.Freq_P7.editingFinished.connect(self.set_stp_freq)

        self.label_61 = QtWidgets.QLabel(self.GB_P7)
        self.label_61.setGeometry(QtCore.QRect(10, 20, 61, 16))
        self.label_61.setObjectName("label_61")

        self.label_62 = QtWidgets.QLabel(self.GB_P7)
        self.label_62.setGeometry(QtCore.QRect(230, 20, 21, 16))
        self.label_62.setObjectName("label_62")

        self.label_63 = QtWidgets.QLabel(self.GB_P7)
        self.label_63.setGeometry(QtCore.QRect(230, 60, 21, 16))
        self.label_63.setObjectName("label_63")

        self.label_64 = QtWidgets.QLabel(self.GB_P7)
        self.label_64.setGeometry(QtCore.QRect(10, 60, 61, 16))
        self.label_64.setObjectName("label_64")

        self.Phase_P7 = QtWidgets.QLineEdit(self.GB_P7)
        self.Phase_P7.setGeometry(QtCore.QRect(70, 60, 151, 21))
        self.Phase_P7.setObjectName("Phase_P7")
        self.Phase_P7.i = 7
        self.Phase_P7.editingFinished.connect(self.set_stp_tht)

        self.Amp_P7 = QtWidgets.QLineEdit(self.GB_P7)
        self.Amp_P7.setGeometry(QtCore.QRect(70, 100, 151, 21))
        self.Amp_P7.setObjectName("Amp_P7")
        self.Amp_P7.i = 7
        self.Amp_P7.editingFinished.connect(self.set_stp_amp)

        self.label_65 = QtWidgets.QLabel(self.GB_P7)
        self.label_65.setGeometry(QtCore.QRect(10, 100, 61, 16))
        self.label_65.setObjectName("label_65")

        ##### Programmer box #####
        self.GB_ProgSTP = QtWidgets.QGroupBox(self.Single_tone)
        self.GB_ProgSTP.setGeometry(QtCore.QRect(550, 340, 261, 141))
        self.GB_ProgSTP.setAutoFillBackground(True)
        self.GB_ProgSTP.setObjectName("GB_ProgSTP")

        ### Default is to assume the amplitude is 1 ###
        self.Amp_fix_STP = QtWidgets.QRadioButton(self.GB_ProgSTP)
        self.Amp_fix_STP.setGeometry(QtCore.QRect(10, 30, 120, 17))
        self.Amp_fix_STP.setStatusTip("Amplitude of all profiles is set to 1")
        self.Amp_fix_STP.setAccessibleDescription("")
        self.Amp_fix_STP.setObjectName("fixed amp")
        self.Amp_fix_STP.toggled.connect(self.Amplitude_Control_STP)

        ### Profile amplitude scale ###
        self.Amp_scl_STP = QtWidgets.QRadioButton(self.GB_ProgSTP)
        self.Amp_scl_STP.setGeometry(QtCore.QRect(10, 60, 120, 17))
        self.Amp_scl_STP.setStatusTip("Enables the user to set the amplitude of the profile (0-1)")
        self.Amp_scl_STP.setAccessibleDescription("")
        self.Amp_scl_STP.setObjectName("amp scaling")
        self.Amp_scl_STP.toggled.connect(self.Amplitude_Control_STP)

        ### Manual amplitude switch ###
        self.OSK_STP = QtWidgets.QRadioButton(self.GB_ProgSTP)
        self.OSK_STP.setGeometry(QtCore.QRect(10, 90, 101, 17))
        self.OSK_STP.setObjectName("manual on/off")
        self.OSK_STP.setStatusTip("Enables manual on/off the the single tone profiles (active high)")
        self.OSK_STP.toggled.connect(self.Amplitude_Control_STP)

        #Set the radio buttons to be part of a group
        self.STP_button_group = QtWidgets.QButtonGroup()
        self.STP_button_group.addButton(self.OSK_STP)
        self.STP_button_group.addButton(self.Amp_scl_STP)
        self.STP_button_group.addButton(self.Amp_fix_STP)

        self.Prog_STP = QtWidgets.QPushButton(self.GB_ProgSTP)
        self.Prog_STP.setGeometry(QtCore.QRect(130, 90, 111, 41))

        ### Programme button ###
        font = QtGui.QFont()
        font.setPointSize(10)
        self.Prog_STP.setFont(font)
        self.Prog_STP.setAutoFillBackground(True)
        self.Prog_STP.setObjectName("Prog_STP")
        self.Prog_STP.clicked.connect(self.Load_SingleToneProfiles)
        self.Prog_STP.clicked.connect(self.enter_STP_mode)
        self.Prog_STP.setStatusTip("Sends the single profile tones to the AOM driver. Make sure the driver is connected first.")

        self.tabWidget.addTab(self.Single_tone, "")
        self.setupUi_ram(MainWindow)

        ########################################################################################################################
    def setupUi_ram(self, MainWindow):
        self.DDS_RAM = QtWidgets.QWidget()
        self.DDS_RAM.setObjectName("DDS_RAM")

        ##### Profile 0 #####
        self.GB_ram_P0 = QtWidgets.QGroupBox(self.DDS_RAM)
        self.GB_ram_P0.setGeometry(QtCore.QRect(10, 20, 261, 141))
        self.GB_ram_P0.setAutoFillBackground(True)
        self.GB_ram_P0.setObjectName("GB_ram_P0")

        ### Start address ###
        self.Start_address_Prof0 = QtWidgets.QLineEdit(self.GB_ram_P0)
        self.Start_address_Prof0.setGeometry(QtCore.QRect(90, 20, 51, 21))
        self.Start_address_Prof0.setObjectName("Start_address_Prof0")
        self.Start_address_Prof0.i = 0
        self.Start_address_Prof0.editingFinished.connect(self.set_ram_start)

        self.label_76 = QtWidgets.QLabel(self.GB_ram_P0)
        self.label_76.setGeometry(QtCore.QRect(10, 20, 71, 16))
        self.label_76.setObjectName("label_76")

        self.label_78 = QtWidgets.QLabel(self.GB_ram_P0)
        self.label_78.setGeometry(QtCore.QRect(160, 80, 21, 16))
        self.label_78.setObjectName("label_78")

        self.label_79 = QtWidgets.QLabel(self.GB_ram_P0)
        self.label_79.setGeometry(QtCore.QRect(10, 50, 71, 16))
        self.label_79.setObjectName("label_79")

        ### End address ###
        self.End_address_Prof0 = QtWidgets.QLineEdit(self.GB_ram_P0)
        self.End_address_Prof0.setGeometry(QtCore.QRect(90, 50, 51, 21))
        self.End_address_Prof0.setObjectName("End_address_Prof0")
        self.End_address_Prof0.i = 0
        self.End_address_Prof0.editingFinished.connect(self.set_ram_end)

        ### Step rate ###
        self.StepRate_P0 = QtWidgets.QLineEdit(self.GB_ram_P0)
        self.StepRate_P0.setGeometry(QtCore.QRect(90, 80, 51, 21))
        self.StepRate_P0.setObjectName("StepRate_P0")
        self.StepRate_P0.i = 0
        self.StepRate_P0.editingFinished.connect(self.set_ram_rate)

        self.label_80 = QtWidgets.QLabel(self.GB_ram_P0)
        self.label_80.setGeometry(QtCore.QRect(10, 80, 61, 16))
        self.label_80.setObjectName("label_80")

        ### List of profile modes ###
        self.Mode_P0 = QtWidgets.QComboBox(self.GB_ram_P0)
        self.Mode_P0.setGeometry(QtCore.QRect(160, 20, 91, 22))
        self.Mode_P0.setAutoFillBackground(False)
        self.Mode_P0.setObjectName("Mode_P0")
        for keys in self.RAM_profile_mode.keys():
            self.Mode_P0.addItem(keys)
        self.Mode_P0.i = 0
        self.Mode_P0.currentTextChanged[str].connect(self.set_ram_mode)

        ### Zero crossing ###
        self.ZeroCrossing_Prof0 = QtWidgets.QCheckBox(self.GB_ram_P0)
        self.ZeroCrossing_Prof0.setGeometry(QtCore.QRect(10, 110, 91, 17))
        self.ZeroCrossing_Prof0.setObjectName("ZeroCrossing_Prof0")
        self.ZeroCrossing_Prof0.toggled.connect(lambda:self.Zero_crossings_update(self.ZeroCrossing_Prof0.isChecked(), 0))

        ### No Dwell ###
        self.NoDWell_Prof0 = QtWidgets.QCheckBox(self.GB_ram_P0)
        self.NoDWell_Prof0.setGeometry(QtCore.QRect(160, 110, 91, 17))
        self.NoDWell_Prof0.setObjectName("NoDWell_Prof0")
        self.NoDWell_Prof0.toggled.connect(lambda:self.No_Dwell_update(self.NoDWell_Prof0.isChecked(), 0))


        ##### Profile 1 #####
        self.GB_ram_P1 = QtWidgets.QGroupBox(self.DDS_RAM)
        self.GB_ram_P1.setGeometry(QtCore.QRect(10, 180, 261, 141))
        self.GB_ram_P1.setAutoFillBackground(True)
        self.GB_ram_P1.setObjectName("GB_ram_P1")

        self.Start_address_Prof1 = QtWidgets.QLineEdit(self.GB_ram_P1)
        self.Start_address_Prof1.setGeometry(QtCore.QRect(90, 20, 51, 21))
        self.Start_address_Prof1.setObjectName("Start_address_Prof1")
        self.Start_address_Prof1.i = 1
        self.Start_address_Prof1.editingFinished.connect(self.set_ram_start)

        self.label_89 = QtWidgets.QLabel(self.GB_ram_P1)
        self.label_89.setGeometry(QtCore.QRect(10, 20, 71, 16))
        self.label_89.setObjectName("label_89")

        self.label_90 = QtWidgets.QLabel(self.GB_ram_P1)
        self.label_90.setGeometry(QtCore.QRect(160, 80, 21, 16))
        self.label_90.setObjectName("label_90")

        self.label_91 = QtWidgets.QLabel(self.GB_ram_P1)
        self.label_91.setGeometry(QtCore.QRect(10, 50, 71, 16))
        self.label_91.setObjectName("label_91")

        self.End_address_Prof1 = QtWidgets.QLineEdit(self.GB_ram_P1)
        self.End_address_Prof1.setGeometry(QtCore.QRect(90, 50, 51, 21))
        self.End_address_Prof1.setObjectName("End_address_Prof1")
        self.End_address_Prof1.i = 1
        self.End_address_Prof1.editingFinished.connect(self.set_ram_end)

        self.StepRate_P1 = QtWidgets.QLineEdit(self.GB_ram_P1)
        self.StepRate_P1.setGeometry(QtCore.QRect(90, 80, 51, 21))
        self.StepRate_P1.setObjectName("StepRate_P1")
        self.StepRate_P1.i = 1
        self.StepRate_P1.editingFinished.connect(self.set_ram_rate)

        self.label_92 = QtWidgets.QLabel(self.GB_ram_P1)
        self.label_92.setGeometry(QtCore.QRect(10, 80, 61, 16))
        self.label_92.setObjectName("label_92")

        self.Mode_P1 = QtWidgets.QComboBox(self.GB_ram_P1)
        self.Mode_P1.setGeometry(QtCore.QRect(160, 20, 91, 22))
        self.Mode_P1.setAutoFillBackground(False)
        self.Mode_P1.setObjectName("Mode_P1")
        for keys in self.RAM_profile_mode.keys():
            self.Mode_P1.addItem(keys)
        self.Mode_P1.i = 1
        self.Mode_P1.currentTextChanged[str].connect(self.set_ram_mode)

        self.ZeroCrossing_Prof1 = QtWidgets.QCheckBox(self.GB_ram_P1)
        self.ZeroCrossing_Prof1.setGeometry(QtCore.QRect(10, 110, 91, 17))
        self.ZeroCrossing_Prof1.setObjectName("ZeroCrossing_Prof1")
        self.ZeroCrossing_Prof1.toggled.connect(lambda:self.Zero_crossings_update(self.ZeroCrossing_Prof1.isChecked(), 1))


        self.NoDWell_Prof1 = QtWidgets.QCheckBox(self.GB_ram_P1)
        self.NoDWell_Prof1.setGeometry(QtCore.QRect(160, 110, 91, 17))
        self.NoDWell_Prof1.setObjectName("NoDWell_Prof1")
        self.NoDWell_Prof1.toggled.connect(lambda:self.No_Dwell_update(self.NoDWell_Prof1.isChecked(), 1))


        #self.Function_P1 = QtWidgets.QComboBox(self.GB_ram_P1)
        #self.Function_P1.setGeometry(QtCore.QRect(160, 50, 91, 22))
        #self.Function_P1.setObjectName("Function_P1")
        #for jc in range(len(self.RAM_functions)):
        #    self.Function_P1.addItem(self.RAM_functions[jc])

        ##### Profile 2 #####
        self.GB_ram_P2 = QtWidgets.QGroupBox(self.DDS_RAM)
        self.GB_ram_P2.setGeometry(QtCore.QRect(10, 340, 261, 141))
        self.GB_ram_P2.setAutoFillBackground(True)
        self.GB_ram_P2.setObjectName("GB_ram_P2")

        self.Start_address_Prof2 = QtWidgets.QLineEdit(self.GB_ram_P2)
        self.Start_address_Prof2.setGeometry(QtCore.QRect(90, 20, 51, 21))
        self.Start_address_Prof2.setObjectName("Start_address_Prof2")
        self.Start_address_Prof2.i = 2
        self.Start_address_Prof2.editingFinished.connect(self.set_ram_start)

        self.label_97 = QtWidgets.QLabel(self.GB_ram_P2)
        self.label_97.setGeometry(QtCore.QRect(10, 20, 71, 16))
        self.label_97.setObjectName("label_97")

        self.label_98 = QtWidgets.QLabel(self.GB_ram_P2)
        self.label_98.setGeometry(QtCore.QRect(160, 80, 21, 16))
        self.label_98.setObjectName("label_98")

        self.label_99 = QtWidgets.QLabel(self.GB_ram_P2)
        self.label_99.setGeometry(QtCore.QRect(10, 50, 71, 16))
        self.label_99.setObjectName("label_99")

        self.End_address_Prof2 = QtWidgets.QLineEdit(self.GB_ram_P2)
        self.End_address_Prof2.setGeometry(QtCore.QRect(90, 50, 51, 21))
        self.End_address_Prof2.setObjectName("End_address_Prof2")
        self.End_address_Prof2.i = 2
        self.End_address_Prof2.editingFinished.connect(self.set_ram_end)

        self.StepRate_P2 = QtWidgets.QLineEdit(self.GB_ram_P2)
        self.StepRate_P2.setGeometry(QtCore.QRect(90, 80, 51, 21))
        self.StepRate_P2.setObjectName("StepRate_P2")
        self.StepRate_P2.i = 2
        self.StepRate_P2.editingFinished.connect(self.set_ram_rate)

        self.label_100 = QtWidgets.QLabel(self.GB_ram_P2)
        self.label_100.setGeometry(QtCore.QRect(10, 80, 61, 16))
        self.label_100.setObjectName("label_100")

        self.Mode_P2 = QtWidgets.QComboBox(self.GB_ram_P2)
        self.Mode_P2.setGeometry(QtCore.QRect(160, 20, 91, 22))
        self.Mode_P2.setAutoFillBackground(False)
        self.Mode_P2.setObjectName("Mode_P2")
        for keys in self.RAM_profile_mode.keys():
            self.Mode_P2.addItem(keys)
        self.Mode_P2.i = 2
        self.Mode_P2.currentTextChanged[str].connect(self.set_ram_mode)

        self.ZeroCrossing_Prof2 = QtWidgets.QCheckBox(self.GB_ram_P2)
        self.ZeroCrossing_Prof2.setGeometry(QtCore.QRect(10, 110, 91, 17))
        self.ZeroCrossing_Prof2.setObjectName("ZeroCrossing_Prof2")
        self.ZeroCrossing_Prof2.toggled.connect(lambda:self.Zero_crossings_update(self.ZeroCrossing_Prof2.isChecked(), 2))

        self.NoDWell_Prof2 = QtWidgets.QCheckBox(self.GB_ram_P2)
        self.NoDWell_Prof2.setGeometry(QtCore.QRect(160, 110, 91, 17))
        self.NoDWell_Prof2.setObjectName("NoDWell_Prof2")
        self.NoDWell_Prof2.toggled.connect(lambda:self.No_Dwell_update(self.NoDWell_Prof2.isChecked(), 2))

        #self.Function_P2 = QtWidgets.QComboBox(self.GB_ram_P2)
        #self.Function_P2.setGeometry(QtCore.QRect(160, 50, 91, 22))
        #self.Function_P2.setObjectName("Function_P2")
        #for jc in range(len(self.RAM_functions)):
        #    self.Function_P2.addItem(self.RAM_functions[jc])

        self.GB_ram_P4 = QtWidgets.QGroupBox(self.DDS_RAM)
        self.GB_ram_P4.setGeometry(QtCore.QRect(280, 180, 261, 141))
        self.GB_ram_P4.setAutoFillBackground(True)
        self.GB_ram_P4.setObjectName("GB_ram_P4")

        self.Start_address_Prof4 = QtWidgets.QLineEdit(self.GB_ram_P4)
        self.Start_address_Prof4.setGeometry(QtCore.QRect(90, 20, 51, 21))
        self.Start_address_Prof4.setObjectName("Start_address_Prof4")
        self.Start_address_Prof4.i = 4
        self.Start_address_Prof4.editingFinished.connect(self.set_ram_start)

        self.label_117 = QtWidgets.QLabel(self.GB_ram_P4)
        self.label_117.setGeometry(QtCore.QRect(10, 20, 71, 16))
        self.label_117.setObjectName("label_117")

        self.label_118 = QtWidgets.QLabel(self.GB_ram_P4)
        self.label_118.setGeometry(QtCore.QRect(160, 80, 21, 16))
        self.label_118.setObjectName("label_118")

        self.label_119 = QtWidgets.QLabel(self.GB_ram_P4)
        self.label_119.setGeometry(QtCore.QRect(10, 50, 71, 16))
        self.label_119.setObjectName("label_119")

        self.End_address_Prof4 = QtWidgets.QLineEdit(self.GB_ram_P4)
        self.End_address_Prof4.setGeometry(QtCore.QRect(90, 50, 51, 21))
        self.End_address_Prof4.setObjectName("End_address_Prof4")
        self.End_address_Prof4.i = 4
        self.End_address_Prof4.editingFinished.connect(self.set_ram_end)

        self.StepRate_P4 = QtWidgets.QLineEdit(self.GB_ram_P4)
        self.StepRate_P4.setGeometry(QtCore.QRect(90, 80, 51, 21))
        self.StepRate_P4.setObjectName("StepRate_P4")
        self.StepRate_P4.i = 4
        self.StepRate_P4.editingFinished.connect(self.set_ram_rate)

        self.label_120 = QtWidgets.QLabel(self.GB_ram_P4)
        self.label_120.setGeometry(QtCore.QRect(10, 80, 61, 16))
        self.label_120.setObjectName("label_120")

        self.Mode_P4 = QtWidgets.QComboBox(self.GB_ram_P4)
        self.Mode_P4.setGeometry(QtCore.QRect(160, 20, 91, 22))
        self.Mode_P4.setAutoFillBackground(False)
        self.Mode_P4.setObjectName("Mode_P4")
        for keys in self.RAM_profile_mode.keys():
            self.Mode_P4.addItem(keys)
        self.Mode_P4.i = 4
        self.Mode_P4.currentTextChanged[str].connect(self.set_ram_mode)

        self.ZeroCrossing_Prof4 = QtWidgets.QCheckBox(self.GB_ram_P4)
        self.ZeroCrossing_Prof4.setGeometry(QtCore.QRect(10, 110, 91, 17))
        self.ZeroCrossing_Prof4.setObjectName("ZeroCrossing_Prof4")
        self.ZeroCrossing_Prof4.toggled.connect(lambda:self.Zero_crossings_update(self.ZeroCrossing_Prof4.isChecked(), 4))

        self.NoDWell_Prof4 = QtWidgets.QCheckBox(self.GB_ram_P4)
        self.NoDWell_Prof4.setGeometry(QtCore.QRect(160, 110, 91, 17))
        self.NoDWell_Prof4.setObjectName("NoDWell_Prof4")
        self.NoDWell_Prof4.toggled.connect(lambda:self.No_Dwell_update(self.NoDWell_Prof4.isChecked(), 4))

        # self.Function_P4 = QtWidgets.QComboBox(self.GB_ram_P4)
        # self.Function_P4.setGeometry(QtCore.QRect(160, 50, 91, 22))
        # self.Function_P4.setObjectName("Function_P4")
        # for jc in range(len(self.RAM_functions)):
        #     self.Function_P4.addItem(self.RAM_functions[jc])

        self.GB_ram_P3 = QtWidgets.QGroupBox(self.DDS_RAM)
        self.GB_ram_P3.setGeometry(QtCore.QRect(280, 20, 261, 141))
        self.GB_ram_P3.setAutoFillBackground(True)
        self.GB_ram_P3.setObjectName("GB_ram_P3")

        self.Start_address_Prof3 = QtWidgets.QLineEdit(self.GB_ram_P3)
        self.Start_address_Prof3.setGeometry(QtCore.QRect(90, 20, 51, 21))
        self.Start_address_Prof3.setObjectName("Start_address_Prof3")
        self.Start_address_Prof3.i = 3
        self.Start_address_Prof3.editingFinished.connect(self.set_ram_start)

        self.label_121 = QtWidgets.QLabel(self.GB_ram_P3)
        self.label_121.setGeometry(QtCore.QRect(10, 20, 71, 16))
        self.label_121.setObjectName("label_121")

        self.label_122 = QtWidgets.QLabel(self.GB_ram_P3)
        self.label_122.setGeometry(QtCore.QRect(160, 80, 21, 16))
        self.label_122.setObjectName("label_122")

        self.label_123 = QtWidgets.QLabel(self.GB_ram_P3)
        self.label_123.setGeometry(QtCore.QRect(10, 50, 71, 16))
        self.label_123.setObjectName("label_123")

        self.End_address_Prof3 = QtWidgets.QLineEdit(self.GB_ram_P3)
        self.End_address_Prof3.setGeometry(QtCore.QRect(90, 50, 51, 21))
        self.End_address_Prof3.setObjectName("End_address_Prof3")
        self.End_address_Prof3.i = 3
        self.End_address_Prof3.editingFinished.connect(self.set_ram_end)

        self.StepRate_P3 = QtWidgets.QLineEdit(self.GB_ram_P3)
        self.StepRate_P3.setGeometry(QtCore.QRect(90, 80, 51, 21))
        self.StepRate_P3.setObjectName("StepRate_P3")
        self.StepRate_P3.i = 3
        self.StepRate_P3.editingFinished.connect(self.set_ram_rate)

        self.label_124 = QtWidgets.QLabel(self.GB_ram_P3)
        self.label_124.setGeometry(QtCore.QRect(10, 80, 61, 16))
        self.label_124.setObjectName("label_124")

        self.Mode_P3 = QtWidgets.QComboBox(self.GB_ram_P3)
        self.Mode_P3.setGeometry(QtCore.QRect(160, 20, 91, 22))
        self.Mode_P3.setAutoFillBackground(False)
        self.Mode_P3.setObjectName("Mode_P3")
        for keys in self.RAM_profile_mode.keys():
            self.Mode_P3.addItem(keys)
        self.Mode_P3.i = 3
        self.Mode_P3.currentTextChanged[str].connect(self.set_ram_mode)

        self.ZeroCrossing_Prof3 = QtWidgets.QCheckBox(self.GB_ram_P3)
        self.ZeroCrossing_Prof3.setGeometry(QtCore.QRect(10, 110, 91, 17))
        self.ZeroCrossing_Prof3.setObjectName("ZeroCrossing_Prof3")
        self.ZeroCrossing_Prof3.toggled.connect(lambda:self.Zero_crossings_update(self.ZeroCrossing_Prof3.isChecked(), 3))

        self.NoDWell_Prof3 = QtWidgets.QCheckBox(self.GB_ram_P3)
        self.NoDWell_Prof3.setGeometry(QtCore.QRect(160, 110, 91, 17))
        self.NoDWell_Prof3.setObjectName("NoDWell_Prof3")
        self.NoDWell_Prof0.toggled.connect(lambda:self.No_Dwell_update(self.NoDWell_Prof3.isChecked(), 3))

        # self.Function_P3 = QtWidgets.QComboBox(self.GB_ram_P3)
        # self.Function_P3.setGeometry(QtCore.QRect(160, 50, 91, 22))
        # self.Function_P3.setObjectName("Function_P3")
        # for jc in range(len(self.RAM_functions)):
        #     self.Function_P3.addItem(self.RAM_functions[jc])

        self.GB_ram_P5 = QtWidgets.QGroupBox(self.DDS_RAM)
        self.GB_ram_P5.setGeometry(QtCore.QRect(280, 340, 261, 141))
        self.GB_ram_P5.setAutoFillBackground(True)
        self.GB_ram_P5.setObjectName("GB_ram_P5")

        self.Start_address_Prof5 = QtWidgets.QLineEdit(self.GB_ram_P5)
        self.Start_address_Prof5.setGeometry(QtCore.QRect(90, 20, 51, 21))
        self.Start_address_Prof5.setObjectName("Start_address_Prof5")
        self.Start_address_Prof5.i = 5
        self.Start_address_Prof5.editingFinished.connect(self.set_ram_start)

        self.label_125 = QtWidgets.QLabel(self.GB_ram_P5)
        self.label_125.setGeometry(QtCore.QRect(10, 20, 71, 16))
        self.label_125.setObjectName("label_125")

        self.label_126 = QtWidgets.QLabel(self.GB_ram_P5)
        self.label_126.setGeometry(QtCore.QRect(160, 80, 21, 16))
        self.label_126.setObjectName("label_126")

        self.label_127 = QtWidgets.QLabel(self.GB_ram_P5)
        self.label_127.setGeometry(QtCore.QRect(10, 50, 71, 16))
        self.label_127.setObjectName("label_127")

        self.End_address_Prof5 = QtWidgets.QLineEdit(self.GB_ram_P5)
        self.End_address_Prof5.setGeometry(QtCore.QRect(90, 50, 51, 21))
        self.End_address_Prof5.setObjectName("End_address_Prof5")
        self.End_address_Prof5.i = 5
        self.End_address_Prof5.editingFinished.connect(self.set_ram_end)

        self.StepRate_P5 = QtWidgets.QLineEdit(self.GB_ram_P5)
        self.StepRate_P5.setGeometry(QtCore.QRect(90, 80, 51, 21))
        self.StepRate_P5.setObjectName("StepRate_P5")
        self.StepRate_P5.i = 5
        self.StepRate_P5.editingFinished.connect(self.set_ram_rate)

        self.label_128 = QtWidgets.QLabel(self.GB_ram_P5)
        self.label_128.setGeometry(QtCore.QRect(10, 80, 61, 16))
        self.label_128.setObjectName("label_128")

        self.Mode_P5 = QtWidgets.QComboBox(self.GB_ram_P5)
        self.Mode_P5.setGeometry(QtCore.QRect(160, 20, 91, 22))
        self.Mode_P5.setAutoFillBackground(False)
        self.Mode_P5.setObjectName("Mode_P5")
        for keys in self.RAM_profile_mode.keys():
            self.Mode_P5.addItem(keys)
        self.Mode_P5.i = 5
        self.Mode_P5.currentTextChanged[str].connect(self.set_ram_mode)

        self.ZeroCrossing_Prof5 = QtWidgets.QCheckBox(self.GB_ram_P5)
        self.ZeroCrossing_Prof5.setGeometry(QtCore.QRect(10, 110, 91, 17))
        self.ZeroCrossing_Prof5.setObjectName("ZeroCrossing_Prof5")
        self.ZeroCrossing_Prof5.toggled.connect(lambda:self.Zero_crossings_update(self.ZeroCrossing_Prof5.isChecked(), 5))

        self.NoDWell_Prof5 = QtWidgets.QCheckBox(self.GB_ram_P5)
        self.NoDWell_Prof5.setGeometry(QtCore.QRect(160, 110, 91, 17))
        self.NoDWell_Prof5.setObjectName("NoDWell_Prof5")
        self.NoDWell_Prof0.toggled.connect(lambda:self.No_Dwell_update(self.NoDWell_Prof5.isChecked(), 5))

        # self.Function_P5 = QtWidgets.QComboBox(self.GB_ram_P5)
        # self.Function_P5.setGeometry(QtCore.QRect(160, 50, 91, 22))
        # self.Function_P5.setObjectName("Function_P5")
        # for jc in range(len(self.RAM_functions)):
        #     self.Function_P5.addItem(self.RAM_functions[jc])

        self.GB_ram_P6 = QtWidgets.QGroupBox(self.DDS_RAM)
        self.GB_ram_P6.setGeometry(QtCore.QRect(550, 20, 261, 141))
        self.GB_ram_P6.setAutoFillBackground(True)
        self.GB_ram_P6.setObjectName("GB_ram_P6")

        self.Start_address_Prof6 = QtWidgets.QLineEdit(self.GB_ram_P6)
        self.Start_address_Prof6.setGeometry(QtCore.QRect(90, 20, 51, 21))
        self.Start_address_Prof6.setObjectName("Start_address_Prof6")
        self.Start_address_Prof6.i = 6
        self.Start_address_Prof6.editingFinished.connect(self.set_ram_start)

        self.label_137 = QtWidgets.QLabel(self.GB_ram_P6)
        self.label_137.setGeometry(QtCore.QRect(10, 20, 71, 16))
        self.label_137.setObjectName("label_137")

        self.label_138 = QtWidgets.QLabel(self.GB_ram_P6)
        self.label_138.setGeometry(QtCore.QRect(160, 80, 21, 16))
        self.label_138.setObjectName("label_138")

        self.label_139 = QtWidgets.QLabel(self.GB_ram_P6)
        self.label_139.setGeometry(QtCore.QRect(10, 50, 71, 16))
        self.label_139.setObjectName("label_139")

        self.End_address_Prof6 = QtWidgets.QLineEdit(self.GB_ram_P6)
        self.End_address_Prof6.setGeometry(QtCore.QRect(90, 50, 51, 21))
        self.End_address_Prof6.setObjectName("End_address_Prof6")
        self.End_address_Prof6.i = 6
        self.End_address_Prof6.editingFinished.connect(self.set_ram_end)

        self.StepRate_P6 = QtWidgets.QLineEdit(self.GB_ram_P6)
        self.StepRate_P6.setGeometry(QtCore.QRect(90, 80, 51, 21))
        self.StepRate_P6.setObjectName("StepRate_P6")
        self.StepRate_P6.i = 6
        self.StepRate_P6.editingFinished.connect(self.set_ram_rate)

        self.label_140 = QtWidgets.QLabel(self.GB_ram_P6)
        self.label_140.setGeometry(QtCore.QRect(10, 80, 61, 16))
        self.label_140.setObjectName("label_140")

        self.Mode_P6 = QtWidgets.QComboBox(self.GB_ram_P6)
        self.Mode_P6.setGeometry(QtCore.QRect(160, 20, 91, 22))
        self.Mode_P6.setAutoFillBackground(False)
        self.Mode_P6.setObjectName("Mode_P6")
        for keys in self.RAM_profile_mode.keys():
            self.Mode_P6.addItem(keys)
        self.Mode_P6.i = 6
        self.Mode_P6.currentTextChanged[str].connect(self.set_ram_mode)

        self.ZeroCrossing_Prof6 = QtWidgets.QCheckBox(self.GB_ram_P6)
        self.ZeroCrossing_Prof6.setGeometry(QtCore.QRect(10, 110, 91, 17))
        self.ZeroCrossing_Prof6.setObjectName("ZeroCrossing_Prof6")
        self.ZeroCrossing_Prof6.toggled.connect(lambda:self.Zero_crossings_update(self.ZeroCrossing_Prof6.isChecked(), 6))

        self.NoDWell_Prof6 = QtWidgets.QCheckBox(self.GB_ram_P6)
        self.NoDWell_Prof6.setGeometry(QtCore.QRect(160, 110, 91, 17))
        self.NoDWell_Prof6.setObjectName("NoDWell_Prof6")
        self.NoDWell_Prof6.toggled.connect(lambda:self.No_Dwell_update(self.NoDWell_Prof6.isChecked(), 6))

        # self.Function_P6 = QtWidgets.QComboBox(self.GB_ram_P6)
        # self.Function_P6.setGeometry(QtCore.QRect(160, 50, 91, 22))
        # self.Function_P6.setObjectName("Function_P6")
        # for jc in range(len(self.RAM_functions)):
        #     self.Function_P6.addItem(self.RAM_functions[jc])

        self.GB_ram_P7 = QtWidgets.QGroupBox(self.DDS_RAM)
        self.GB_ram_P7.setGeometry(QtCore.QRect(550, 180, 261, 141))
        self.GB_ram_P7.setAutoFillBackground(True)
        self.GB_ram_P7.setObjectName("GB_ram_P7")

        self.Start_address_Prof7 = QtWidgets.QLineEdit(self.GB_ram_P7)
        self.Start_address_Prof7.setGeometry(QtCore.QRect(90, 20, 51, 21))
        self.Start_address_Prof7.setObjectName("Start_address_Prof7")
        self.Start_address_Prof7.i = 7
        self.Start_address_Prof7.editingFinished.connect(self.set_ram_start)

        self.label_141 = QtWidgets.QLabel(self.GB_ram_P7)
        self.label_141.setGeometry(QtCore.QRect(10, 20, 71, 16))
        self.label_141.setObjectName("label_141")

        self.label_142 = QtWidgets.QLabel(self.GB_ram_P7)
        self.label_142.setGeometry(QtCore.QRect(160, 80, 21, 16))
        self.label_142.setObjectName("label_142")

        self.label_143 = QtWidgets.QLabel(self.GB_ram_P7)
        self.label_143.setGeometry(QtCore.QRect(10, 50, 71, 16))
        self.label_143.setObjectName("label_143")

        self.End_address_Prof7 = QtWidgets.QLineEdit(self.GB_ram_P7)
        self.End_address_Prof7.setGeometry(QtCore.QRect(90, 50, 51, 21))
        self.End_address_Prof7.setObjectName("End_address_Prof7")
        self.End_address_Prof7.i = 7
        self.End_address_Prof7.editingFinished.connect(self.set_ram_end)

        self.StepRate_P7 = QtWidgets.QLineEdit(self.GB_ram_P7)
        self.StepRate_P7.setGeometry(QtCore.QRect(90, 80, 51, 21))
        self.StepRate_P7.setObjectName("StepRate_P7")
        self.StepRate_P7.i = 7
        self.StepRate_P7.editingFinished.connect(self.set_ram_rate)

        self.label_144 = QtWidgets.QLabel(self.GB_ram_P7)
        self.label_144.setGeometry(QtCore.QRect(10, 80, 61, 16))
        self.label_144.setObjectName("label_144")

        self.Mode_P7 = QtWidgets.QComboBox(self.GB_ram_P7)
        self.Mode_P7.setGeometry(QtCore.QRect(160, 20, 91, 22))
        self.Mode_P7.setAutoFillBackground(False)
        self.Mode_P7.setObjectName("Mode_P7")
        for keys in self.RAM_profile_mode.keys():
            self.Mode_P7.addItem(keys)
        self.Mode_P7.i = 7
        self.Mode_P7.currentTextChanged[str].connect(self.set_ram_mode)

        self.ZeroCrossing_Prof7 = QtWidgets.QCheckBox(self.GB_ram_P7)
        self.ZeroCrossing_Prof7.setGeometry(QtCore.QRect(10, 110, 91, 17))
        self.ZeroCrossing_Prof7.setObjectName("ZeroCrossing_Prof7")
        self.ZeroCrossing_Prof7.toggled.connect(lambda:self.Zero_crossings_update(self.ZeroCrossing_Prof7.isChecked(), 7))

        self.NoDWell_Prof7 = QtWidgets.QCheckBox(self.GB_ram_P7)
        self.NoDWell_Prof7.setGeometry(QtCore.QRect(160, 110, 91, 17))
        self.NoDWell_Prof7.setObjectName("NoDWell_Prof7")
        self.NoDWell_Prof7.toggled.connect(lambda:self.No_Dwell_update(self.NoDWell_Prof7.isChecked(), 7))

        ##### RAM Programming options #####
        self.GB_ProgRAM = QtWidgets.QGroupBox(self.DDS_RAM)
        self.GB_ProgRAM.setGeometry(QtCore.QRect(550, 340, 261, 141))
        self.GB_ProgRAM.setAutoFillBackground(True)
        self.GB_ProgRAM.setObjectName("GB_ProgRAM")

        self.OSK_man = QtWidgets.QCheckBox(self.GB_ProgRAM)
        self.OSK_man.setGeometry(QtCore.QRect(10, 80, 101, 17))
        self.OSK_man.setObjectName("OSK_man")
        self.OSK_man.toggled.connect(self.Amplitude_Control_RAM)

        self.RAM_prog = QtWidgets.QPushButton(self.GB_ProgRAM)
        self.RAM_prog.setGeometry(QtCore.QRect(130, 90, 111, 41))
        font = QtGui.QFont()
        font.setPointSize(10)
        self.RAM_prog.setFont(font)
        self.RAM_prog.setAutoFillBackground(True)
        self.RAM_prog.setObjectName("RAM_prog")
        self.RAM_prog.clicked.connect(self.Load_RAM_playback)
        self.RAM_prog.clicked.connect(self.enter_RAM_mode)

        self.RAM_data = QtWidgets.QComboBox(self.GB_ProgRAM)
        self.RAM_data.setGeometry(QtCore.QRect(100, 20, 141, 22))
        self.RAM_data.setObjectName("RAM_data")
        for keys in self.RAM_data_type.keys():
            self.RAM_data.addItem(keys)
        self.RAM_data.currentIndexChanged.connect(self.disable_modulation_type_DRG)

        self.label_145 = QtWidgets.QLabel(self.GB_ProgRAM)
        self.label_145.setGeometry(QtCore.QRect(10, 20, 61, 16))
        self.label_145.setObjectName("label_145")

        self.label_146 = QtWidgets.QLabel(self.GB_ProgRAM)
        self.label_146.setGeometry(QtCore.QRect(10, 50, 81, 16))
        self.label_146.setObjectName("label_146")

        self.Int_ctrl = QtWidgets.QComboBox(self.GB_ProgRAM)
        self.Int_ctrl.setGeometry(QtCore.QRect(100, 50, 141, 22))
        self.Int_ctrl.setObjectName("Int_ctrl")

        for keys in self.RAM_controls.keys():
            self.Int_ctrl.addItem(keys)

        #self.RAM_blocks = QtWidgets.QLCDNumber(self.GB_ProgRAM)
        #self.RAM_blocks.setGeometry(QtCore.QRect(30, 100, 64, 23))
        #self.RAM_blocks.setDigitCount(4)
        #self.RAM_blocks.setObjectName("RAM_blocks")

        self.tabWidget.addTab(self.DDS_RAM, "")

        self.setupUi_DRG(MainWindow)
        
        # load default profiles
        self.load_all('dds/defaultDDS2.txt')
        
    def setupUi_DRG(self, MainWindow):

        self.Ramp_gen = QtWidgets.QWidget()
        self.Ramp_gen.setEnabled(True)
        self.Ramp_gen.setObjectName("Ramp_gen")

        self.checkBox = QtWidgets.QCheckBox(self.Ramp_gen)
        self.checkBox.setGeometry(QtCore.QRect(10, 10, 180, 41))
        self.checkBox.setObjectName("checkBox")
        self.checkBox.toggled.connect(lambda:self.DRG_features_update(self.checkBox.isChecked(), 0))
        self.checkBox.toggled.connect(self.enter_ramp_mode)

        self.DRG_mode_GB = QtWidgets.QGroupBox(self.Ramp_gen)
        self.DRG_mode_GB.setGeometry(QtCore.QRect(10, 50, 391, 111))
        self.DRG_mode_GB.setAutoFillBackground(True)
        self.DRG_mode_GB.setCheckable(False)
        self.DRG_mode_GB.setObjectName("DRG_mode_GB")

        self.DRG_freq_cntrl = QtWidgets.QRadioButton(self.DRG_mode_GB)
        self.DRG_freq_cntrl.setGeometry(QtCore.QRect(20, 20, 121, 17))
        self.DRG_freq_cntrl.setObjectName("DRG Frequency")
        self.DRG_freq_cntrl.toggled.connect(lambda:self.DGR_modulation_select(self.DRG_freq_cntrl))
        self.DRG_freq_cntrl.setEnabled(False) # Disbale since we know frequency is the RAM default.

        self.DRG_phase_cntrl = QtWidgets.QRadioButton(self.DRG_mode_GB)
        self.DRG_phase_cntrl.setGeometry(QtCore.QRect(20, 50, 121, 17))
        self.DRG_phase_cntrl.setObjectName("DRG Phase")
        self.DRG_phase_cntrl.toggled.connect(lambda:self.DGR_modulation_select(self.DRG_phase_cntrl))

        self.DRG_amp_cntrl = QtWidgets.QRadioButton(self.DRG_mode_GB)
        self.DRG_amp_cntrl.setGeometry(QtCore.QRect(20, 80, 121, 17))
        self.DRG_amp_cntrl.setObjectName("DRG Amplitude")
        self.DRG_amp_cntrl.setChecked(True)
        self.DGR_destination = np.array([1,1])
        self.DRG_amp_cntrl.toggled.connect(lambda:self.DGR_modulation_select(self.DRG_amp_cntrl))

        self.DRG_options_GB = QtWidgets.QGroupBox(self.Ramp_gen)
        self.DRG_options_GB.setGeometry(QtCore.QRect(10, 380, 391, 111))
        self.DRG_options_GB.setAutoFillBackground(True)
        self.DRG_options_GB.setObjectName("DRG_options_GB")

        self.AutoclearDRG = QtWidgets.QCheckBox(self.DRG_options_GB)
        self.AutoclearDRG.setGeometry(QtCore.QRect(20, 20, 211, 17))
        self.AutoclearDRG.setObjectName("AutoclearDRG")
        self.AutoclearDRG.toggled.connect(lambda:self.DRG_features_update(self.AutoclearDRG.isChecked(), 1))

        self.Clear_DRA = QtWidgets.QCheckBox(self.DRG_options_GB)
        self.Clear_DRA.setGeometry(QtCore.QRect(20, 50, 201, 17))
        self.Clear_DRA.setObjectName("Clear_DRA")
        self.Clear_DRA.toggled.connect(lambda:self.DRG_features_update(self.Clear_DRA.isChecked(), 2))

        self.Load_DRR = QtWidgets.QCheckBox(self.DRG_options_GB)
        self.Load_DRR.setGeometry(QtCore.QRect(20, 80, 201, 17))
        self.Load_DRR.setObjectName("Load_DRR")
        self.Load_DRR.toggled.connect(lambda:self.DRG_features_update(self.Load_DRR.isChecked(), 3))

        self.No_dwell_high = QtWidgets.QCheckBox(self.DRG_options_GB)
        self.No_dwell_high.setGeometry(QtCore.QRect(270, 20, 201, 17))
        self.No_dwell_high.setObjectName("No_dwell_high")
        self.No_dwell_high.toggled.connect(lambda:self.DRG_features_update(self.No_dwell_high.isChecked(), 4))

        self.No_dwell_low = QtWidgets.QCheckBox(self.DRG_options_GB)
        self.No_dwell_low.setGeometry(QtCore.QRect(270, 50, 201, 17))
        self.No_dwell_low.setObjectName("No_dwell_low")
        self.No_dwell_low.toggled.connect(lambda:self.DRG_features_update(self.No_dwell_low.isChecked(), 5))

        self.GB_Sweep_params = QtWidgets.QGroupBox(self.Ramp_gen)
        self.GB_Sweep_params.setGeometry(QtCore.QRect(10, 170, 391, 201))
        self.GB_Sweep_params.setAutoFillBackground(True)
        self.GB_Sweep_params.setObjectName("GB_Sweep_params")

        self.Sweep_start = QtWidgets.QLineEdit(self.GB_Sweep_params)
        self.Sweep_start.setGeometry(QtCore.QRect(120, 20, 151, 21))
        self.Sweep_start.setObjectName("Sweep_start")
        self.Sweep_start.editingFinished.connect(self.applyAmpValidators)

        self.label_10 = QtWidgets.QLabel(self.GB_Sweep_params)
        self.label_10.setGeometry(QtCore.QRect(10, 20, 61, 16))
        self.label_10.setObjectName("label_10")

        self.label_13 = QtWidgets.QLabel(self.GB_Sweep_params)
        self.label_13.setGeometry(QtCore.QRect(10, 50, 61, 16))
        self.label_13.setObjectName("label_13")

        self.Sweep_end = QtWidgets.QLineEdit(self.GB_Sweep_params)
        self.Sweep_end.setGeometry(QtCore.QRect(120, 50, 151, 21))
        self.Sweep_end.setObjectName("Sweep_end")
        self.Sweep_end.editingFinished.connect(self.applyAmpValidators)

        self.Pos_step = QtWidgets.QLineEdit(self.GB_Sweep_params)
        self.Pos_step.setGeometry(QtCore.QRect(120, 80, 151, 21))
        self.Pos_step.setObjectName("Pos_step")

        self.label_14 = QtWidgets.QLabel(self.GB_Sweep_params)
        self.label_14.setGeometry(QtCore.QRect(10, 80, 91, 16))
        self.label_14.setObjectName("label_14")

        self.Neg_step = QtWidgets.QLineEdit(self.GB_Sweep_params)
        self.Neg_step.setGeometry(QtCore.QRect(120, 110, 151, 21))
        self.Neg_step.setObjectName("Neg_step")

        self.label_15 = QtWidgets.QLabel(self.GB_Sweep_params)
        self.label_15.setGeometry(QtCore.QRect(10, 110, 91, 16))
        self.label_15.setObjectName("label_15")

        self.Pos_step_rate = QtWidgets.QLineEdit(self.GB_Sweep_params)
        self.Pos_step_rate.setGeometry(QtCore.QRect(120, 140, 151, 21))
        self.Pos_step_rate.setObjectName("Pos_step_rate")

        self.Neg_step_rate = QtWidgets.QLineEdit(self.GB_Sweep_params)
        self.Neg_step_rate.setGeometry(QtCore.QRect(120, 170, 151, 21))
        self.Neg_step_rate.setObjectName("Neg_step_rate")

        self.label_16 = QtWidgets.QLabel(self.GB_Sweep_params)
        self.label_16.setGeometry(QtCore.QRect(10, 140, 91, 16))
        self.label_16.setObjectName("label_16")

        self.label_17 = QtWidgets.QLabel(self.GB_Sweep_params)
        self.label_17.setGeometry(QtCore.QRect(10, 170, 91, 16))
        self.label_17.setObjectName("label_17")

        self.label_81 = QtWidgets.QLabel(self.GB_Sweep_params)
        self.label_81.setGeometry(QtCore.QRect(290, 140, 21, 16))
        self.label_81.setObjectName("label_81")

        self.label_82 = QtWidgets.QLabel(self.GB_Sweep_params)
        self.label_82.setGeometry(QtCore.QRect(290, 170, 21, 16))
        self.label_82.setObjectName("label_82")

        self.tabWidget.addTab(self.Ramp_gen, "")
        self.setupUi_FPGA(MainWindow)
        
        self.Amp_scl_STP.setChecked(True) # default mode amplitude scaling
        self.applyAmpValidators() # put limits on amp inputs


    def setupUi_FPGA(self, MainWindow):
        self.FPGA_playback = QtWidgets.QWidget()
        self.FPGA_playback.setObjectName("FPGA_playback")


        self.FPGA_file_select = QtWidgets.QGroupBox(self.FPGA_playback)
        self.FPGA_file_select.setGeometry(QtCore.QRect(10, 170, 391, 151))
        self.FPGA_file_select.setAutoFillBackground(True)
        self.FPGA_file_select.setObjectName("FPGA_file_select")


        self.LOAD_file_FPGA = QtWidgets.QPushButton(self.FPGA_file_select)
        self.LOAD_file_FPGA.setGeometry(QtCore.QRect(250, 50, 111, 41))
        font = QtGui.QFont()
        font.setPointSize(10)
        self.LOAD_file_FPGA.setFont(font)
        self.LOAD_file_FPGA.setAutoFillBackground(True)
        self.LOAD_file_FPGA.setObjectName("LOAD_file_FPGA")
        self.LOAD_file_FPGA.clicked.connect(self.file_open_FPGA_file_func)

        self.LOAD_file_FPGA.setStatusTip("Select the csv file to convert into a memory file.")


        self.Generate_mem_FPGA = QtWidgets.QPushButton(self.FPGA_file_select)
        self.Generate_mem_FPGA.setGeometry(QtCore.QRect(250, 100, 111, 41))
        font = QtGui.QFont()
        font.setPointSize(10)
        self.Generate_mem_FPGA.setFont(font)
        self.Generate_mem_FPGA.setAutoFillBackground(True)
        self.Generate_mem_FPGA.setObjectName("Generate_mem_FPGA")
        self.Generate_mem_FPGA.clicked.connect(self.generate_FPGA_mem_file_func)
        self.Generate_mem_FPGA.setStatusTip("Commit the conversion.")

        self.GB_ProgFPGA = QtWidgets.QGroupBox(self.FPGA_playback)
        self.GB_ProgFPGA.setGeometry(QtCore.QRect(550, 340, 261, 141))
        self.GB_ProgFPGA.setAutoFillBackground(True)
        self.GB_ProgFPGA.setObjectName("GB_ProgFPGA")

        ##Set the matched latency option
        self.Matched_lat = QtWidgets.QCheckBox(self.GB_ProgFPGA)
        self.Matched_lat.setGeometry(QtCore.QRect(10, 30, 111, 17))
        self.Matched_lat.setStatusTip("")
        self.Matched_lat.setAccessibleDescription("")
        self.Matched_lat.setObjectName("Matched_lat")
        self.Matched_lat.setChecked(True)
        self.Matched_lat.toggled.connect(lambda:self.switch_FPGA_func(self.Matched_lat.isChecked(), 2))

        ##Set the last hold control options
        self.Hold_last = QtWidgets.QCheckBox(self.GB_ProgFPGA)
        self.Hold_last.setGeometry(QtCore.QRect(10, 60, 121, 17))
        self.Hold_last.setObjectName("Hold_last")
        self.Hold_last.toggled.connect(lambda:self.switch_FPGA_func(self.Hold_last.isChecked(), 1))

        self.Prog_FPGA = QtWidgets.QPushButton(self.GB_ProgFPGA)
        self.Prog_FPGA.setGeometry(QtCore.QRect(130, 90, 111, 41))
        font = QtGui.QFont()
        font.setPointSize(10)
        self.Prog_FPGA.setFont(font)
        self.Prog_FPGA.setAutoFillBackground(True)
        self.Prog_FPGA.setObjectName("Prog_FPGA")
        #
        self.Prog_FPGA.clicked.connect(self.Altera_FPGA_program)
        self.Prog_FPGA.setStatusTip("Update the FPGA and AOM AOM driver. Make sure the FPGA is connected first.")


        ##Select the FM gain- only applicable for frequency
        self.FM_gain = QtWidgets.QComboBox(self.GB_ProgFPGA)
        self.FM_gain.setGeometry(QtCore.QRect(150, 50, 91, 21))
        self.FM_gain.setObjectName("FM_gain")

        for jc in range(16):
            self.FM_gain.addItem(str(jc))
        #self.COM_no.activated[str].connect(self.PortConfig)

        self.label_11 = QtWidgets.QLabel(self.GB_ProgFPGA)
        self.label_11.setGeometry(QtCore.QRect(150, 30, 47, 13))
        self.label_11.setObjectName("label_11")

        self.Enable_FPGA_chck = QtWidgets.QCheckBox(self.FPGA_playback)
        self.Enable_FPGA_chck.setGeometry(QtCore.QRect(10, 20, 161, 17))
        self.Enable_FPGA_chck.setObjectName("Enable_FPGA_chck")
        self.Enable_FPGA_chck.toggled.connect(lambda:self.switch_FPGA_func(FPGA.Enable_FPGA_chck.isChecked(), 0))

        ###

        self.fpga_PROGRAMMER_dia = QtWidgets.QTextBrowser(self.FPGA_playback)
        self.fpga_PROGRAMMER_dia.setGeometry(QtCore.QRect(10, 340, 531, 141))
        self.fpga_PROGRAMMER_dia.setObjectName("fpga_PROGRAMMER_dia")

        self.label_19 = QtWidgets.QLabel(self.FPGA_playback)
        self.label_19.setGeometry(QtCore.QRect(10, 320, 151, 16))
        self.label_19.setObjectName("label_19")

        self.tabWidget.addTab(self.FPGA_playback, "")

        self.setupUi_features(MainWindow)

    def setupUi_features(self, MainWindow):
        MainWindow.setCentralWidget(self.centralwidget)
        self.menubar = QtWidgets.QMenuBar(MainWindow)
        self.menubar.setGeometry(QtCore.QRect(0, 0, 837, 21))
        self.menubar.setObjectName("menubar")

        self.menuFile = QtWidgets.QMenu(self.menubar)
        self.menuFile.setObjectName("menuFile")

        self.menuHelp = QtWidgets.QMenu(self.menubar)
        self.menuHelp.setObjectName("menuHelp")

        MainWindow.setMenuBar(self.menubar)
        self.statusbar = QtWidgets.QStatusBar(MainWindow)
        self.statusbar.setObjectName("statusbar")
        MainWindow.setStatusBar(self.statusbar)

        self.actionRAM_editor = QtWidgets.QAction(MainWindow)
        self.actionRAM_editor.setObjectName("actionRAM_editor")

        self.actionLoad_stp = QtWidgets.QAction(MainWindow)
        self.actionLoad_stp.setObjectName("actionLoad_stp")
        self.actionLoad_stp.triggered.connect(self.load_STP)
        
        self.actionSave_stp = QtWidgets.QAction(MainWindow)
        self.actionSave_stp.setObjectName("actionSave_stp")
        self.actionSave_stp.triggered.connect(self.save_STP)

        self.actionLoad_RAM = QtWidgets.QAction(MainWindow)
        self.actionLoad_RAM.setObjectName("actionLoad_RAM")
        self.actionLoad_RAM.triggered.connect(self.load_RAMprofile)

        self.actionSave_RAM = QtWidgets.QAction(MainWindow)
        self.actionSave_RAM.setObjectName("actionSave_RAM")
        self.actionSave_RAM.triggered.connect(self.save_RAMprofile)

        self.actionSave_all = QtWidgets.QAction(MainWindow)
        self.actionSave_all.setObjectName("actionSave_all")
        self.actionSave_all.triggered.connect(self.save_all)

        self.actionLoad_all = QtWidgets.QAction(MainWindow)
        self.actionLoad_all.setObjectName("actionLoad_all")
        self.actionLoad_all.triggered.connect(self.load_all)

        self.actionLoad_DDS_RAM = QtWidgets.QAction(MainWindow)
        self.actionLoad_DDS_RAM.setObjectName("actionLoad_DDS_RAM")
        self.actionLoad_DDS_RAM.triggered.connect(self.Open_RAM_playback_file)

        self.actionUser_guide = QtWidgets.QAction(MainWindow)
        self.actionUser_guide.setObjectName("actionUser_guide")
        self.actionUser_guide.triggered.connect(self.launch_help_file)

        self.actionClose = QtWidgets.QAction(MainWindow)
        self.actionClose.setObjectName("actionClose")
        self.actionClose.triggered.connect(self.Disconnect_serial_port)

        self.menuFile.addAction(self.actionRAM_editor)
        self.menuFile.addAction(self.actionLoad_stp)
        self.menuFile.addAction(self.actionSave_stp)
        self.menuFile.addAction(self.actionLoad_RAM)
        self.menuFile.addAction(self.actionSave_RAM)
        self.menuFile.addAction(self.actionLoad_all)
        self.menuFile.addAction(self.actionSave_all)
        self.menuFile.addAction(self.actionLoad_DDS_RAM)
        self.menuFile.addAction(self.actionClose)

        self.menuHelp.addAction(self.actionUser_guide)

        self.menubar.addAction(self.menuFile.menuAction())
        self.menubar.addAction(self.menuHelp.menuAction())

        self.retranslateUi(MainWindow)
        self.tabWidget.setCurrentIndex(1)
        QtCore.QMetaObject.connectSlotsByName(MainWindow)

    def retranslateUi(self, MainWindow):
        _translate = QtCore.QCoreApplication.translate
        MainWindow.setWindowTitle(_translate("MainWindow", "DDS GUI -- disconnected"))
        self.label_147.setText(_translate("MainWindow", "Device messages"))
        self.label_148.setText(_translate("MainWindow", "COM Port number"))
        self.Connect.setText(_translate("MainWindow", "Connect"))
        self.Disconnect.setText(_translate("MainWindow", "Disconnect"))

        self.GB_Aux.setTitle(_translate("MainWindow", "Auxillary parameter sources"))
        self.Freq_aux.setText(_translate("MainWindow", "%.1f"%self.FTW[0]))
        self.label_5.setText(_translate("MainWindow", "Frequency"))
        self.label_7.setText(_translate("MainWindow", "MHz"))
        self.label_8.setText(_translate("MainWindow", "Deg"))
        self.label_9.setText(_translate("MainWindow", "Phase"))
        self.Phase_aux.setText(_translate("MainWindow", "0.00"))
        self.label_AMW.setText(_translate("MainWindow", "Amp"))
        self.label_AMWunits.setText(_translate("MainWindow", "0-1"))
        self.Amp_aux.setText(_translate("MainWindow", "1.00"))
        self.Debug.setText(_translate("MainWindow", "Debug"))
        self.PyDexTCP.setText(_translate("MainWindow", "Reset PyDex TCP"))
        self.label_ALIMunits.setText(_translate("MainWindow", "0-1"))
        self.label_ALIM.setText(_translate("MainWindow", "Amp lim"))
        self.label_RAMname.setText(_translate("MainWindow", "RAM file"))
        self.RAM_fname.setText(_translate("MainWindow", self.RAM_data_filename[self.ind]))
        self.Amp_lim.setText(_translate("MainWindow", str(self.Alim)))
        self.label_150.setText(_translate("MainWindow", "Module address"))

        self.tabWidget.setTabText(self.tabWidget.indexOf(self.Coms), _translate("MainWindow", "Communication"))
        self.GB_P0.setTitle(_translate("MainWindow", "000 Profile 0"))
        self.Freq_P0.setText(_translate("MainWindow", "0.00"))
        self.label.setText(_translate("MainWindow", "Frequency"))
        self.label_2.setText(_translate("MainWindow", "MHz"))
        self.label_3.setText(_translate("MainWindow", "Deg"))
        self.label_4.setText(_translate("MainWindow", "Phase"))
        self.Phase_P0.setText(_translate("MainWindow", "0.00"))
        self.Amp_P0.setText(_translate("MainWindow", "0.2"))
        self.label_6.setText(_translate("MainWindow", "Amplitude"))
        self.GB_P1.setTitle(_translate("MainWindow", "100 Profile 1"))
        self.Freq_P1.setText(_translate("MainWindow", "0.00"))
        self.label_26.setText(_translate("MainWindow", "Frequency"))
        self.label_27.setText(_translate("MainWindow", "MHz"))
        self.label_28.setText(_translate("MainWindow", "Deg"))
        self.label_29.setText(_translate("MainWindow", "Phase"))
        self.Phase_P1.setText(_translate("MainWindow", "0.00"))
        self.Amp_P1.setText(_translate("MainWindow", "0.2"))
        self.label_30.setText(_translate("MainWindow", "Amplitude"))
        self.GB_P2.setTitle(_translate("MainWindow", "010 Profile 2"))
        self.Freq_P2.setText(_translate("MainWindow", "0.00"))
        self.label_36.setText(_translate("MainWindow", "Frequency"))
        self.label_37.setText(_translate("MainWindow", "MHz"))
        self.label_38.setText(_translate("MainWindow", "Deg"))
        self.label_39.setText(_translate("MainWindow", "Phase"))
        self.Phase_P2.setText(_translate("MainWindow", "0.00"))
        self.Amp_P2.setText(_translate("MainWindow", "0.2"))
        self.label_40.setText(_translate("MainWindow", "Amplitude"))
        self.GB_P3.setTitle(_translate("MainWindow", "110 Profile 3"))
        self.Freq_P3.setText(_translate("MainWindow", "0.00"))
        self.label_41.setText(_translate("MainWindow", "Frequency"))
        self.label_42.setText(_translate("MainWindow", "MHz"))
        self.label_43.setText(_translate("MainWindow", "Deg"))
        self.label_44.setText(_translate("MainWindow", "Phase"))
        self.Phase_P3.setText(_translate("MainWindow", "0.00"))
        self.Amp_P3.setText(_translate("MainWindow", "0.2"))
        self.label_45.setText(_translate("MainWindow", "Amplitude"))
        self.GB_P4.setTitle(_translate("MainWindow", "001 Profile 4"))
        self.Freq_P4.setText(_translate("MainWindow", "0.00"))
        self.label_46.setText(_translate("MainWindow", "Frequency"))
        self.label_47.setText(_translate("MainWindow", "MHz"))
        self.label_48.setText(_translate("MainWindow", "Deg"))
        self.label_49.setText(_translate("MainWindow", "Phase"))
        self.Phase_P4.setText(_translate("MainWindow", "0.00"))
        self.Amp_P4.setText(_translate("MainWindow", "0.2"))
        self.label_50.setText(_translate("MainWindow", "Amplitude"))
        self.GB_P5.setTitle(_translate("MainWindow", "101 Profile 5"))
        self.Freq_P5.setText(_translate("MainWindow", "0.00"))
        self.label_51.setText(_translate("MainWindow", "Frequency"))
        self.label_52.setText(_translate("MainWindow", "MHz"))
        self.label_53.setText(_translate("MainWindow", "Deg"))
        self.label_54.setText(_translate("MainWindow", "Phase"))
        self.Phase_P5.setText(_translate("MainWindow", "0.00"))
        self.Amp_P5.setText(_translate("MainWindow", "0.2"))
        self.label_55.setText(_translate("MainWindow", "Amplitude"))
        self.GB_P6.setTitle(_translate("MainWindow", "011 Profile 6"))
        self.Freq_P6.setText(_translate("MainWindow", "0.00"))
        self.label_56.setText(_translate("MainWindow", "Frequency"))
        self.label_57.setText(_translate("MainWindow", "MHz"))
        self.label_58.setText(_translate("MainWindow", "Deg"))
        self.label_59.setText(_translate("MainWindow", "Phase"))
        self.Phase_P6.setText(_translate("MainWindow", "0.00"))
        self.Amp_P6.setText(_translate("MainWindow", "0.2"))
        self.label_60.setText(_translate("MainWindow", "Amplitude"))
        self.GB_P7.setTitle(_translate("MainWindow", "111 Profile 7"))
        self.Freq_P7.setText(_translate("MainWindow", "0.00"))
        self.label_61.setText(_translate("MainWindow", "Frequency"))
        self.label_62.setText(_translate("MainWindow", "MHz"))
        self.label_63.setText(_translate("MainWindow", "Deg"))
        self.label_64.setText(_translate("MainWindow", "Phase"))
        self.Phase_P7.setText(_translate("MainWindow", "0.00"))
        self.Amp_P7.setText(_translate("MainWindow", "0.2"))
        self.label_65.setText(_translate("MainWindow", "Amplitude"))
        self.GB_ProgSTP.setTitle(_translate("MainWindow", "Options"))
        self.Amp_fix_STP.setText(_translate("MainWindow", "Amplitude fixed"))
        self.Amp_scl_STP.setText(_translate("MainWindow", "Amplitude scaling"))
        self.OSK_STP.setText(_translate("MainWindow", "Manual on/off"))
        self.Prog_STP.setText(_translate("MainWindow", "Send"))
        self.tabWidget.setTabText(self.tabWidget.indexOf(self.Single_tone), _translate("MainWindow", "Single tone mode"))
        self.GB_ram_P0.setTitle(_translate("MainWindow", "000 Profile 0"))
        self.Start_address_Prof0.setText(_translate("MainWindow", "0"))
        self.label_76.setText(_translate("MainWindow", "Start address"))
        self.label_78.setText(_translate("MainWindow", "μs"))
        self.label_79.setText(_translate("MainWindow", "End address"))
        self.End_address_Prof0.setText(_translate("MainWindow", "0"))
        self.StepRate_P0.setText(_translate("MainWindow", "1"))
        self.label_80.setText(_translate("MainWindow", "Step rate"))
        self.ZeroCrossing_Prof0.setText(_translate("MainWindow", "Zero-crossing"))
        self.NoDWell_Prof0.setText(_translate("MainWindow", "No Dwell"))
        self.GB_ram_P1.setTitle(_translate("MainWindow", "100 Profile 1"))
        self.Start_address_Prof1.setText(_translate("MainWindow", "0"))
        self.label_89.setText(_translate("MainWindow", "Start address"))
        self.label_90.setText(_translate("MainWindow", "μs"))
        self.label_91.setText(_translate("MainWindow", "End address"))
        self.End_address_Prof1.setText(_translate("MainWindow", "0"))
        self.StepRate_P1.setText(_translate("MainWindow", "1"))
        self.label_92.setText(_translate("MainWindow", "Step rate"))
        self.ZeroCrossing_Prof1.setText(_translate("MainWindow", "Zero-crossing"))
        self.NoDWell_Prof1.setText(_translate("MainWindow", "No Dwell"))
        self.GB_ram_P2.setTitle(_translate("MainWindow", "010 Profile 2"))
        self.Start_address_Prof2.setText(_translate("MainWindow", "0"))
        self.label_97.setText(_translate("MainWindow", "Start address"))
        self.label_98.setText(_translate("MainWindow", "μs"))
        self.label_99.setText(_translate("MainWindow", "End address"))
        self.End_address_Prof2.setText(_translate("MainWindow", "0"))
        self.StepRate_P2.setText(_translate("MainWindow", "1"))
        self.label_100.setText(_translate("MainWindow", "Step rate"))
        self.ZeroCrossing_Prof2.setText(_translate("MainWindow", "Zero-crossing"))
        self.NoDWell_Prof2.setText(_translate("MainWindow", "No Dwell"))
        self.GB_ram_P4.setTitle(_translate("MainWindow", "001 Profile 4"))
        self.Start_address_Prof4.setText(_translate("MainWindow", "0"))
        self.label_117.setText(_translate("MainWindow", "Start address"))
        self.label_118.setText(_translate("MainWindow", "μs"))
        self.label_119.setText(_translate("MainWindow", "End address"))
        self.End_address_Prof4.setText(_translate("MainWindow", "0"))
        self.StepRate_P4.setText(_translate("MainWindow", "1"))
        self.label_120.setText(_translate("MainWindow", "Step rate"))
        self.ZeroCrossing_Prof4.setText(_translate("MainWindow", "Zero-crossing"))
        self.NoDWell_Prof4.setText(_translate("MainWindow", "No Dwell"))
        self.GB_ram_P3.setTitle(_translate("MainWindow", "110 Profile 3"))
        self.Start_address_Prof3.setText(_translate("MainWindow", "0"))
        self.label_121.setText(_translate("MainWindow", "Start address"))
        self.label_122.setText(_translate("MainWindow", "μs"))
        self.label_123.setText(_translate("MainWindow", "End address"))
        self.End_address_Prof3.setText(_translate("MainWindow", "0"))
        self.StepRate_P3.setText(_translate("MainWindow", "1"))
        self.label_124.setText(_translate("MainWindow", "Step rate"))
        self.ZeroCrossing_Prof3.setText(_translate("MainWindow", "Zero-crossing"))
        self.NoDWell_Prof3.setText(_translate("MainWindow", "No Dwell"))
        self.GB_ram_P5.setTitle(_translate("MainWindow", "101 Profile 5"))
        self.Start_address_Prof5.setText(_translate("MainWindow", "0"))
        self.label_125.setText(_translate("MainWindow", "Start address"))
        self.label_126.setText(_translate("MainWindow", "μs"))
        self.label_127.setText(_translate("MainWindow", "End address"))
        self.End_address_Prof5.setText(_translate("MainWindow", "0"))
        self.StepRate_P5.setText(_translate("MainWindow", "1"))
        self.label_128.setText(_translate("MainWindow", "Step rate"))
        self.ZeroCrossing_Prof5.setText(_translate("MainWindow", "Zero-crossing"))
        self.NoDWell_Prof5.setText(_translate("MainWindow", "No Dwell"))
        self.GB_ram_P6.setTitle(_translate("MainWindow", "011 Profile 6"))
        self.Start_address_Prof6.setText(_translate("MainWindow", "0"))
        self.label_137.setText(_translate("MainWindow", "Start address"))
        self.label_138.setText(_translate("MainWindow", "μs"))
        self.label_139.setText(_translate("MainWindow", "End address"))
        self.End_address_Prof6.setText(_translate("MainWindow", "0"))
        self.StepRate_P6.setText(_translate("MainWindow", "1"))
        self.label_140.setText(_translate("MainWindow", "Step rate"))
        self.ZeroCrossing_Prof6.setText(_translate("MainWindow", "Zero-crossing"))
        self.NoDWell_Prof6.setText(_translate("MainWindow", "No Dwell"))
        self.GB_ram_P7.setTitle(_translate("MainWindow", "111 Profile 7"))
        self.Start_address_Prof7.setText(_translate("MainWindow", "0"))
        self.label_141.setText(_translate("MainWindow", "Start address"))
        self.label_142.setText(_translate("MainWindow", "μs"))
        self.label_143.setText(_translate("MainWindow", "End address"))
        self.End_address_Prof7.setText(_translate("MainWindow", "0"))
        self.StepRate_P7.setText(_translate("MainWindow", "1"))
        self.label_144.setText(_translate("MainWindow", "Step rate"))
        self.ZeroCrossing_Prof7.setText(_translate("MainWindow", "Zero-crossing"))
        self.NoDWell_Prof7.setText(_translate("MainWindow", "No Dwell"))
        self.GB_ProgRAM.setTitle(_translate("MainWindow", "Options"))
        self.OSK_man.setText(_translate("MainWindow", "Manual on/off"))
        self.RAM_prog.setText(_translate("MainWindow", "Send"))
        self.label_145.setText(_translate("MainWindow", "Data type"))
        self.label_146.setText(_translate("MainWindow", "Internal control"))
        self.tabWidget.setTabText(self.tabWidget.indexOf(self.DDS_RAM), _translate("MainWindow", "DDS RAM mode"))

        self.checkBox.setText(_translate("MainWindow", "Enable Ramp generator"))
        self.DRG_mode_GB.setTitle(_translate("MainWindow", "Mode select"))
        self.DRG_freq_cntrl.setText(_translate("MainWindow", "Frequency (MHz)"))
        self.DRG_phase_cntrl.setText(_translate("MainWindow", "Phase (Deg)"))
        self.DRG_amp_cntrl.setText(_translate("MainWindow", "Amplitude"))
        self.DRG_options_GB.setTitle(_translate("MainWindow", "Options"))
        self.AutoclearDRG.setText(_translate("MainWindow", "Auto-clear ramp generator"))
        self.Clear_DRA.setText(_translate("MainWindow", "Clear ramp generator"))
        self.Load_DRR.setText(_translate("MainWindow", "Reset on profile change"))
        self.No_dwell_high.setText(_translate("MainWindow", "No-dwell high"))
        self.No_dwell_low.setText(_translate("MainWindow", "No-dwell low"))
        self.GB_Sweep_params.setTitle(_translate("MainWindow", "Sweep parameters"))
        self.Sweep_start.setText(_translate("MainWindow", "0.00"))
        self.label_10.setText(_translate("MainWindow", "Start"))
        self.label_13.setText(_translate("MainWindow", "End"))
        self.Sweep_end.setText(_translate("MainWindow", "0.00"))
        self.Pos_step.setText(_translate("MainWindow", "1"))
        self.label_14.setText(_translate("MainWindow", "Positive step size"))
        self.Neg_step.setText(_translate("MainWindow", "1"))
        self.label_15.setText(_translate("MainWindow", "Negative step size"))
        self.Pos_step_rate.setText(_translate("MainWindow", "1"))
        self.Neg_step_rate.setText(_translate("MainWindow", "1"))
        self.label_16.setText(_translate("MainWindow", "Positive step rate"))
        self.label_17.setText(_translate("MainWindow", "Negative step rate"))
        self.label_81.setText(_translate("MainWindow", "μs"))
        self.label_82.setText(_translate("MainWindow", "μs"))
        self.tabWidget.setTabText(self.tabWidget.indexOf(self.Ramp_gen), _translate("MainWindow", "DDS ramp generator"))


        self.FPGA_file_select.setTitle(_translate("MainWindow", "File selection and processing"))
        #self.Hex_file_radio.setText(_translate("MainWindow", "Hex file"))
        #self.Coe_radio.setText(_translate("MainWindow", "COE file"))
        self.LOAD_file_FPGA.setText(_translate("MainWindow", "Load"))
        self.Generate_mem_FPGA.setText(_translate("MainWindow", "Generate"))
        self.GB_ProgFPGA.setTitle(_translate("MainWindow", "Options"))
        self.Matched_lat.setText(_translate("MainWindow", "Matched latency"))
        self.Hold_last.setText(_translate("MainWindow", "Hold last value"))
        self.Prog_FPGA.setText(_translate("MainWindow", "Send"))
        self.label_11.setText(_translate("MainWindow", "FM Gain"))
        self.Enable_FPGA_chck.setText(_translate("MainWindow", "Enable FPGA programming"))
        #self.FPGA_PLL.setTitle(_translate("MainWindow", "FPGA update rate options"))
        #self.Hex_file_radio2.setText(_translate("MainWindow", "Hex file"))
        #self.Coe_file_radio2.setText(_translate("MainWindow", "COE file"))
        #self.Gen_PLL_file.setText(_translate("MainWindow", "Generate"))
        #self.PLL_clk_out.setText(_translate("MainWindow", "0.00"))
        #self.label_18.setText(_translate("MainWindow", "Rate"))
        #self.label_12.setText(_translate("MainWindow", "MHz"))
        self.label_19.setText(_translate("MainWindow", "FPGA programmer messages"))
        #self.FPGA_coms.setTitle(_translate("MainWindow", "FPGA communications"))
        #self.label_149.setText(_translate("MainWindow", "Programmer ID"))
        self.tabWidget.setTabText(self.tabWidget.indexOf(self.FPGA_playback), _translate("MainWindow", "FPGA playback"))

        self.menuFile.setTitle(_translate("MainWindow", "File"))
        self.menuHelp.setTitle(_translate("MainWindow", "Help"))
        self.actionRAM_editor.setText(_translate("MainWindow", "Open RAM editor"))
        self.actionLoad_stp.setText(_translate("MainWindow", "Load singe tone profile"))
        self.actionSave_stp.setText(_translate("MainWindow", "Save singe tone profile"))
        self.actionLoad_RAM.setText(_translate("MainWindow", "Load DDS RAM profile"))
        self.actionSave_RAM.setText(_translate("MainWindow", "Save DDS RAM profile"))
        self.actionLoad_all.setText(_translate("MainWindow", "Load all parameters"))
        self.actionSave_all.setText(_translate("MainWindow", "Save all parameters"))self.actionLoad_DDS_RAM.setText(_translate("MainWindow", "Load DDS RAM playback"))
        self.actionUser_guide.setText(_translate("MainWindow", "User guide"))
        self.actionClose.setText(_translate("MainWindow", "Close"))


if __name__ == "__main__":
    import sys
    ################################################################################
    ### Set paths here
    home_path = os.getcwd()+'/'
    
    SavePrefix = home_path + "Data_Files/AOM Driver Saved files/"
    
    now = datetime.datetime.now()
    date_str = now.strftime("%d_%m_%Y")
    
    today_file_path = SavePrefix + date_str + "/"
    
    ## FPGA memory size
    ALTERA = 2**14
    XILINX = 2**16
    
    if os.path.exists(home_path + "Data_Files/") == False:
        os.makedirs(home_path + "Data_Files/")
    if os.path.exists(SavePrefix) == False:
        os.makedirs(SavePrefix)

    app = QtWidgets.QApplication(sys.argv)
    MainWindow = QtWidgets.QMainWindow()
    ui = Ui_MainWindow(port=8630, host='129.234.190.164', alim=1, 
                       Today_file=today_file_path, enable_print = False)
    ui.setupUi_coms(MainWindow)
    
    def closeEvent(event):
        """actions to carry out before closing the window"""
        ui.save_all('dds/defaultDDS2.txt')
        event.accept()
    MainWindow.closeEvent = closeEvent

    MainWindow.show()
    sys.exit(app.exec_())
