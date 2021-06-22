"""PyDex - DDS
Lewis McArd, Stefan Spence 24.11.20

 - communicate with a DDS board via serial USB port.
"""
import serial
import time
import sys
import os
import json
os.system("color") # allows error/warning/info messages to print in colour
import glob
import datetime
import pickle
import numpy as np
import matplotlib.pyplot as plt
from collections import OrderedDict

from PyQt5 import QtCore, QtGui, QtWidgets

if '.' not in sys.path: sys.path.append('.')
if '..' not in sys.path: sys.path.append('..')
from networking.client import PyClient, reset_slot


class CustomComboBox(QtWidgets.QComboBox):
    popupRequest = QtCore.pyqtSignal()
    def showPopup(self): # override to add in signal
        self.popupRequest.emit()
        super(CustomComboBox, self).showPopup()

class Ui_MainWindow(object):
    mode_options = ['single tone', 'RAM', 'single tone + ramp', 'RAM + ramp', 'FPGA'] # allowed modes of operation

    amp_options = ['fixed amp', 'manual on/off', 'amp scaling']

    RAM_functions = ['Linear', 'Gaussian', 'Minimum Jerk', 'Exponential', 'Logarithmic']
    RAM_data_type = OrderedDict([('RAM Frequency', np.array([0,0])),
                        ('RAM Phase', np.array([0,1])),
                        ('RAM Amplitude', np.array([1,0])),
                        ('RAM Polar', np.array([1,1]))])

    RAM_controls = OrderedDict([("Disable", np.array([0,0,0,0])),
                    ("Burst. Profiles 0 - 1", np.array([0,0,0,1])),
                    ("Burst. Profiles 0 - 2", np.array([0,0,1,0])),
                    ("Burst. Profiles 0 - 3", np.array([0,0,1,1])),
                    ("Burst. Profiles 0 - 4", np.array([0,1,0,0])),
                    ("Burst. Profiles 0 - 5", np.array([0,1,0,1])),
                    ("Burst. Profiles 0 - 6", np.array([0,1,1,0])),
                    ("Burst. Profiles 0 - 7", np.array([0,1,1,1])),
                    ("Continuous. Profiles 0 - 1", np.array([1,0,0,0])),
                    ("Continuous. Profiles 0 - 2", np.array([1,0,0,1])),
                    ("Continuous. Profiles 0 - 3", np.array([1,0,1,0])),
                    ("Continuous. Profiles 0 - 4", np.array([1,0,1,1])),
                    ("Continuous. Profiles 0 - 5", np.array([1,1,0,0])),
                    ("Continuous. Profiles 0 - 6", np.array([1,1,0,1])),
                    ("Continuous. Profiles 0 - 7", np.array([1,1,1,1]))])

    RAM_profile_mode = OrderedDict([("Direct", np.array([0,0,0])),
                        ("Ramp-up", np.array([0,0,1])),
                        ("Bidirectional ramp", np.array([0,1,0])),
                        ("Continuous bidirectional ramp", np.array([0,1,1])),
                        ("Continuous recirculate", np.array([1,0,0]))])

    DRG_modes = ['DRG Frequency', 'DRG Phase', 'DRG Amplitude']
    
    COMlabels = ['RB1A', 'RB2', 'RB3', 'RB4', 'RB1B']

    def __init__(self, port=8624, host='localhost', alim=1):
        super(Ui_MainWindow, self).__init__()

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
        self.AMP_scale = 0


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
        self.FPGA_params = np.zeros(3)
        #FPGA control
        #Matched_latency_en = 2
        #Data_assembler_hold = 1
        #Parallel_en = 0
    
    def dbl_fixup(self, txt=''):
        """Correct the text input to match the valid range."""
        try: val = float(txt)
        except ValueError: return txt
        if val < self.dbl_validator.bottom():
            return str(self.dbl_validator.bottom())
        elif val > self.dbl_validator.top():
            return str(self.dbl_validator.top())
        else: return txt

    def respond(self, cmd=None):
        """Respond to the command sent by TCP message to the client.
        The syntax is:  option=value
        If setting new data, the value syntax is: 
            [[port1,profile1,key1,val1],[port2,profile2,key2,val2],...]"""
        try:
            value = cmd.split('=')[1] 
        except: 
            self.Display_func('Command not understood: '+str(cmd))
            return 0                

        if any(x in cmd for x in['Freq', 'Phase', 'Amp']) and 'aux' not in cmd:
            self.mode = 'single tone'
        elif any(x in cmd for x in['Start_add', 'End_add', 'Step_rate', 'aux']):
            self.mode = 'RAM'
                
        if 'set_data' in cmd:
            try:
                value_list = eval(value) # nested list of parameters to change
            except Exception as e: 
                self.Display_func('Failed to evaluate command: '+cmd)
                return 0
            prv_port = '' # keep track of which port we're communicating on
            success = [0 for i in range(len(value_list))]
            for i, (port, profile, key, val) in enumerate(value_list):
                # Set parameters. 
                try:
                    if 'Freq' in key and 'aux' not in profile:
                        self.fout[int(port.replace('COM',''))-7, int(profile[1])] = float(val)
                    elif 'Phase' in key and 'aux' not in profile:
                        self.tht[int(port.replace('COM',''))-7, int(profile[1])] = float(val)
                    elif 'Amp' in key and 'aux' not in profile:
                        self.amp[int(port.replace('COM',''))-7, int(profile[1])] = float(val)
                    elif 'Start_add' in key:
                        self.Start_Address[int(port.replace('COM',''))-7, int(profile[1])] = float(val)
                    elif 'End_add' in key:
                        self.End_Address[int(port.replace('COM',''))-7, int(profile[1])] = float(val)
                    elif 'Step_rate' in key:
                        self.Rate[int(port.replace('COM',''))-7, int(profile[1])] = float(val)
                    elif 'Freq' in key and 'aux' in profile:
                        self.FTW[int(port.replace('COM',''))-7] = float(val)
                    elif 'Phase' in key and 'aux' in profile:
                        self.POW[int(port.replace('COM',''))-7] = float(val)
                    elif 'Amp' in key and 'aux' in profile:
                        self.AMW[int(port.replace('COM',''))-7] = float(val)
                        self.load_DDS_ram = True
                    else: raise Exception('Tried to set invalid parameter')
                    success[i] = 1
                except Exception as e: print(e) # pass # key could be for ramp
                    
                if 'ramp' in self.mode:
                    try:
                        label = self.centralwidget.findChild(QtWidgets.QLineEdit, key)
                        label.setText('%s'%val)
                        success[i] = 1
                    except Exception as e: print(e) #pass # key could be for ST or RAM
                # if we need to change port
                if not self.connected or (port != self.COM_no.currentText() and 
                        port in [self.COM_no.itemText(i) for i in range(self.COM_no.count())]):
                    self.Disconnect_func()
                    self.COM_no.setCurrentText(port)
                    self.PortConfig_func()
                self.applyAmpValidators()
                # programme the DDS with the current data
                if port != prv_port:
                    if 'ramp' in self.mode:
                        self.checkBox.setChecked(True)
                    if 'single tone' in self.mode:
                        self.Programme_STP_func()
                    elif 'RAM' in self.mode:
                        self.Programme_DDS_RAM_func()
                    prv_port = port
            self.redisplay_profiles()
            self.Display_func('Set parameters %s'%str([val for i, val in enumerate(value_list) if success[i]]))
        elif 'set_mode' in cmd:
            if value in self.mode_options:
                self.mode = value
            else: 
                self.mode = 'single tone'
            self.Display_func('Changed to '+self.mode+' mode.')
        elif 'set_manual_on/off' in cmd:
            if value in self.amp_options:
                item = self.centralwidget.findChild(QtWidgets.QRadioButton, value)
                item.setChecked(True) # triggers OSK_func
                if value == 'manual on/off' and 'RAM' in self.mode:
                    self.OSK_man.setChecked(True)
                elif 'RAM' in self.mode: 
                    self.OSK_man.setChecked(False)
                self.Display_func('Changed to %s.'%value)
        elif 'load_RAM_playback' in cmd:
            self.file_open_DDS_RAM_func(value)
        elif 'set_RAM_data_type' in cmd:
            if value in self.RAM_data_type.keys():
                self.RAM_data.setCurrentText(value) # triggers disable_modes_DRG_func
                self.Display_func('Changed RAM data type to %s.'%value)
        elif 'set_internal_control' in cmd:
            if value in self.RAM_controls.keys():
                self.Int_ctrl.setCurrentText(value)
                self.Display_func('Changed RAM internal control to %s.'%value)
        elif 'set_ramp_mode' in cmd:
            if value in self.DRG_modes:
                item = self.centralwidget.findChild(QtWidgets.QRadioButton, value)
                item.setChecked(True) # requires 
                self.Display_func('Changed DRG mode to %s.'%value if item.isChecked() else 'none')
        elif 'save_STP' in cmd:
            self.save_STP(value)
        elif 'load_STP' in cmd:
            self.load_STP(value)
        elif 'save_all' in cmd:
            self.save_all(value)
        elif 'load_all' in cmd:
            self.load_all(value)
        elif 'programme' in cmd:
            if 'single tone' in self.mode:
                self.Programme_STP_func()
            elif 'RAM' in self.mode:
                self.Programme_DDS_RAM_func()
                
    def search_dic(self, iterable, value):
        for i, x in enumerate(iterable):
            if all(x == value):
                return i
        return 0
    
    def powercal(self, amp):
        """Recalibrate the amplitude to account for AOM nonlinearity"""
        return cals[self.ind](amp)
    
    def plot_RAM_playback_data(self):
        """pop-up plot of RAM playback data to check that it's right"""
        for i in range(len(self.AMW)):
            try:
                plt.plot(np.around(2**14 *self.powercal(np.absolute(
                        self.RAM_modulation_data[i][0,:])/ np.amax(
                            self.RAM_modulation_data[i][0, :])*self.AMW[i]), decimals = 0),
                    label=str(i))
            except (IndexError, TypeError): pass
        plt.show()
                    
    def redisplay_profiles(self):
        """Set the stored STP and RAM profile data into the text labels."""
        for i in range(8):
            try: 
                self.centralwidget.findChild(QtWidgets.QLineEdit, 'Freq_P%s'%i).setText('%s'%self.fout[self.ind,i])
                self.centralwidget.findChild(QtWidgets.QLineEdit, 'Phase_P%s'%i).setText('%s'%self.tht[self.ind,i])
                self.centralwidget.findChild(QtWidgets.QLineEdit, 'Amp_P%s'%i).setText('%s'%self.amp[self.ind,i])
                self.centralwidget.findChild(QtWidgets.QLineEdit, 'Start_add_P%s'%i).setText('%s'%self.Start_Address[self.ind,i])
                self.centralwidget.findChild(QtWidgets.QLineEdit, 'End_add_P%s'%i).setText('%s'%self.End_Address[self.ind,i])
                self.centralwidget.findChild(QtWidgets.QLineEdit, 'Step_rate_P%s'%i).setText('%s'%self.Rate[self.ind,i])
                self.centralwidget.findChild(QtWidgets.QCheckBox, 'ND_P%s'%i).setChecked(bool(self.No_dwell[self.ind,i]))
                self.centralwidget.findChild(QtWidgets.QCheckBox, 'ZC_P%s'%i).setChecked(bool(self.Zero_crossing[self.ind,i]))
                self.centralwidget.findChild(QtWidgets.QComboBox, 'Mode_P%s'%i).setCurrentIndex(self.search_dic(self.RAM_profile_mode.values(), self.RAM_playback_mode[self.ind,i]))
            except Exception as e: self.Display_func("Couldn't display stored parameter:\n"+str(e)) # key could be for ramp
        try:
            self.Phase_aux.setText(str(self.POW[self.ind]))
            self.Freq_aux.setText(str(self.FTW[self.ind]))
            self.Amp_aux.setText(str(self.AMW[self.ind]))
            self.RAM_fname.setText(self.RAM_data_filename[self.ind])
        except Exception as e: self.Display_func("Couldn't display stored parameter:\n"+str(e))
        
    def load_STP(self, fname=''):
        """Input the values from the STP file into the stored data and line edits."""
        try:
            if not fname:
                fname, _ = QtWidgets.QFileDialog.getOpenFileName(
                    self.centralwidget, 'Open STP File', '', 'txt(*.txt);;all (*)')
            if os.path.exists(fname): # if user cancels then fname is empty str
                data = np.loadtxt(fname, delimiter=',')
                self.fout = data[:5,:]
                self.tht = data[5:10,:]
                self.amp = data[10:15,:]
                self.redisplay_profiles()
                self.applyAmpValidators()
        except Exception as e:
            self.Display_func('Could not load STP from %s\n'%fname+str(e))
            
    def load_RAMprofile(self, fname=''):
        """Input the values from the RAM file into the stored data and line edits."""
        try:
            if not fname:
                fname, _ = QtWidgets.QFileDialog.getOpenFileName(
                    self.centralwidget, 'Open RAM Profile', '', 'txt(*.txt);;all (*)')
            if os.path.exists(fname): # if user cancels then fname is empty str
                data = np.loadtxt(fname, delimiter=',')
                self.Start_Address    = data[:5,:]
                self.End_Address      = data[5:10,:]
                self.Rate             = data[10:15,:]
                self.No_dwell         = data[15:20,:]
                self.Zero_crossing    = data[20:25,:]
                self.RAM_playback_mode = data[25:,:].reshape(5,8,3)
                self.redisplay_profiles()
        except Exception as e:
            self.Display_func('Could not load RAM profiles from %s\n'%fname+str(e))

    def load_all(self, fname=''):
        """Take STP, RAM and auxiliary parameters from a file."""
        try:
            if not fname:
                fname, _ = QtWidgets.QFileDialog.getOpenFileName(
                    self.centralwidget, 'Open STP File', '', 'txt(*.txt);;all (*)')
            if os.path.exists(fname): # if user cancels then fname is empty str
                with open(fname) as f:
                    data = json.load(f)
                for key, val in data.items():
                    if 'RAM_data_filename' in key:
                        self.Display_func('RAM data files were: %s'%val)
#                        self.RAM_data_filename = val
                    else:
                        setattr(self, key, np.array(val, dtype=float))
                self.redisplay_profiles()
                self.applyAmpValidators()
                self.Display_func('Loaded parameters from %s'%fname)
        except Exception as e:
            self.Display_func('Could not load params from %s\n'%fname+str(e))
            
    def save_data(self, data, fname='', mode='STP'):
        """Save data to a file."""
        try:
            if not fname:
                fname, _ = QtWidgets.QFileDialog.getSaveFileName(
                    self.centralwidget, 'Save File', '', 'txt(*.txt);;all (*)')
            if 'all params' in mode:
                with open(fname, 'w') as f:
                    json.dump(data, f)
            else: np.savetxt(fname, data, delimiter = ',')
            self.Display_func(mode+' saved to %s'%fname)
        except (OSError, FileNotFoundError, IndexError) as e:
            self.Display_func('Could not save '+mode+' to %s\n'%fname+str(e))

    def save_STP(self, fname=''):
        """Save all the single tone profile parameters to a text file."""
        data = np.array([self.fout, self.tht, self.amp]).reshape(15,8)
        self.save_data(data, fname, mode='STP')
            
    def save_RAMprofile(self, fname=''):
        """Save the RAM playback parameters to a text file."""
        data = np.append(np.array([self.Start_Address, self.End_Address, 
                    self.Rate, self.No_dwell, self.Zero_crossing]).reshape(25,8), 
                    self.RAM_playback_mode.reshape(15,8), axis=0)
        self.save_data(data, fname, mode='RAM profiles')

    def save_all(self, fname=''):
        """Save STP, RAM, and auxiliary parameters to a text file."""
        try:
            data = OrderedDict()
            for key in ['FTW', 'POW', 'AMW']:
                data[key] = list(getattr(self, key).astype(str))
            for key in ['fout', 'tht', 'amp', 'Start_Address', 
                    'End_Address', 'Rate', 'No_dwell', 'Zero_crossing']:
                data[key] = [list(x) for x in getattr(self, key).astype(str)]
            data['RAM_playback_mode'] = [[list(y) for y in x] for x in self.RAM_playback_mode.astype(str)]
            data['RAM_data_filename'] = self.RAM_data_filename
        except ValueError as e: self.Display_func("Failed to save parameters:\n"+str(e))
        self.save_data(data, fname, mode='all params')
       
    def enter_ramp_mode(self):
        """When ramp mode checkbox is checked, let pydex know it's in ramp mode"""
        if self.checkBox.isChecked() and not 'ramp' in self.mode:
            self.mode += ' + ramp'

    def enter_STP_mode(self):
        """When STP programme button is pressed, set mode to single tone"""
        self.mode = 'single tone'
        self.enter_ramp_mode()

    def enter_RAM_mode(self):
        """When RAM programme button is pressed, set mode to RAM"""
        self.mode = 'RAM'
        self.enter_ramp_mode()

    def reload_RAM(self):
        """If the aux Amp parameter is changed, reload the RAM 
        data saved on the DDS when it's next programmed."""
        self.load_DDS_ram = True

    def applyAmpValidators(self):
        """Apply a validator to the text inputs on the amplitude
        in order to limit the output."""
        self.dbl_validator.setTop(self.Alim)
        # for the STPs
        for x in map(lambda y: getattr(self, y), ['Amp_P%s'%i for i in range(8)]):
            x.setText(self.dbl_fixup(x.text())) # limit allowed amplitude
        # for the RAM playback
        self.Amp_aux.setText(self.dbl_fixup(self.Amp_aux.text()))
        # for the DRG: only want a validator if in amp mode.
        if self.DRG_amp_cntrl.isChecked():
            self.Sweep_start.setText(self.dbl_fixup(self.Sweep_start.text()))
            self.Sweep_end.setText(self.dbl_fixup(self.Sweep_end.text()))
        
    def set_amp_lim(self):
        """Set validators on inputs that define amplitudes"""
        self.Alim = float(self.Amp_lim.text()) if self.Amp_lim.text() else 0.5
        self.applyAmpValidators()

    def PortSetup(self):
        """Display the list of available COM ports in the combobox"""
        self.COM_no.clear()
        ports = self.Get_serial_ports_func()
        self.COM_no.addItem('--')
        for jc in range(len(ports)):
            self.COM_no.addItem(ports[jc])
        
    def setupUi_coms(self, MainWindow):
        MainWindow.setObjectName("MainWindow")
        MainWindow.resize(837, 600)
        self.mw = MainWindow
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
        
        self.label_COM7 = QtWidgets.QLabel(self.Coms)
        self.label_COM7.setGeometry(QtCore.QRect(10, 75, 91, 16))
        self.label_COM7.setObjectName("label_COM7")
        self.label_COM8 = QtWidgets.QLabel(self.Coms)
        self.label_COM8.setGeometry(QtCore.QRect(10, 90, 91, 16))
        self.label_COM8.setObjectName("label_COM8")
        self.label_COM9 = QtWidgets.QLabel(self.Coms)
        self.label_COM9.setGeometry(QtCore.QRect(10, 105, 91, 16))
        self.label_COM9.setObjectName("label_COM9")
        self.label_COM10 = QtWidgets.QLabel(self.Coms)
        self.label_COM10.setGeometry(QtCore.QRect(10, 120, 91, 16))
        self.label_COM10.setObjectName("label_COM10")
        self.label_COM11 = QtWidgets.QLabel(self.Coms)
        self.label_COM11.setGeometry(QtCore.QRect(10, 135, 91, 16))
        self.label_COM11.setObjectName("label_COM11")

        ### Connect device button ###
        self.Connect = QtWidgets.QPushButton(self.Coms)
        self.Connect.setGeometry(QtCore.QRect(210, 20, 111, 41))
        self.Connect.setObjectName("Connect")
        self.Connect.clicked.connect(self.PortConfig_func)

        ### Disconnect device button ###
        self.Disconnect = QtWidgets.QPushButton(self.Coms)
        self.Disconnect.setGeometry(QtCore.QRect(210, 70, 111, 41))
        self.Disconnect.setObjectName("Disconnect")
        self.Disconnect.clicked.connect(self.Disconnect_func)

        ### Debug request
        self.Debug = QtWidgets.QPushButton(self.Coms)
        self.Debug.setGeometry(QtCore.QRect(210, 120, 111, 41))
        self.Debug.setObjectName("Debug")
        self.Debug.clicked.connect(self.debug_func)

        ### TCP communication with PyDex
        self.PyDexTCP = QtWidgets.QPushButton(self.Coms)
        self.PyDexTCP.setGeometry(QtCore.QRect(330, 20, 111, 41))
        self.PyDexTCP.setObjectName("PyDex_TCP_reset")
        self.PyDexTCP.clicked.connect(self.Pydex_tcp_reset)

        self.GB_Aux = QtWidgets.QGroupBox(self.Coms)
        self.GB_Aux.setGeometry(QtCore.QRect(540, 10, 270, 200))
        self.GB_Aux.setAutoFillBackground(True)
        self.GB_Aux.setObjectName("GB_Aux")
        self.Freq_aux = QtWidgets.QLineEdit(self.GB_Aux)
        self.Freq_aux.setGeometry(QtCore.QRect(70, 20, 151, 21))
        self.Freq_aux.setObjectName("Freq_aux")
        self.Freq_aux.editingFinished.connect(self.update_RAM_values_func)
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
        self.Phase_aux.editingFinished.connect(self.update_RAM_values_func)
        self.label_AMWunits = QtWidgets.QLabel(self.GB_Aux)
        self.label_AMWunits.setGeometry(QtCore.QRect(230, 100, 25, 16))
        self.label_AMWunits.setObjectName("label_AMWunits")
        self.label_AMW = QtWidgets.QLabel(self.GB_Aux)
        self.label_AMW.setGeometry(QtCore.QRect(10, 100, 65, 16))
        self.label_AMW.setObjectName("label_AMW")
        self.Amp_aux = QtWidgets.QLineEdit(self.GB_Aux)
        self.Amp_aux.setGeometry(QtCore.QRect(70, 100, 151, 21))
        self.Amp_aux.setObjectName("Amp_aux")
        self.Amp_aux.editingFinished.connect(self.update_RAM_values_func)
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
        self.Single_tone = QtWidgets.QWidget()
        self.Single_tone.setObjectName("Single_tone")

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
        self.Amp_fix_STP.toggled.connect(self.OSK_func)

        ### Profile amplitude scale ###
        self.Amp_scl_STP = QtWidgets.QRadioButton(self.GB_ProgSTP)
        self.Amp_scl_STP.setGeometry(QtCore.QRect(10, 60, 120, 17))
        self.Amp_scl_STP.setStatusTip("Enables the user to set the amplitude of the profile (0-1)")
        self.Amp_scl_STP.setAccessibleDescription("")
        self.Amp_scl_STP.setObjectName("amp scaling")
        self.Amp_scl_STP.toggled.connect(self.OSK_func)

        ### Manual amplitude switch ###
        self.OSK_STP = QtWidgets.QRadioButton(self.GB_ProgSTP)
        self.OSK_STP.setGeometry(QtCore.QRect(10, 90, 101, 17))
        self.OSK_STP.setObjectName("manual on/off")
        self.OSK_STP.setStatusTip("Enables manual on/off the the single tone profiles (active high)")
        self.OSK_STP.toggled.connect(self.OSK_func)

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
        self.Prog_STP.clicked.connect(self.Programme_STP_func)
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
        self.S_add_P0 = QtWidgets.QLineEdit(self.GB_ram_P0)
        self.S_add_P0.setGeometry(QtCore.QRect(90, 20, 51, 21))
        self.S_add_P0.setObjectName("Start_add_P0")
        self.S_add_P0.i = 0
        self.S_add_P0.editingFinished.connect(self.set_ram_start)

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
        self.E_add_P0 = QtWidgets.QLineEdit(self.GB_ram_P0)
        self.E_add_P0.setGeometry(QtCore.QRect(90, 50, 51, 21))
        self.E_add_P0.setObjectName("End_add_P0")
        self.E_add_P0.i = 0
        self.E_add_P0.editingFinished.connect(self.set_ram_end)

        ### Step rate ###
        self.SR_P0 = QtWidgets.QLineEdit(self.GB_ram_P0)
        self.SR_P0.setGeometry(QtCore.QRect(90, 80, 51, 21))
        self.SR_P0.setObjectName("Step_rate_P0")
        self.SR_P0.i = 0
        self.SR_P0.editingFinished.connect(self.set_ram_rate)

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
        self.ZC_P0 = QtWidgets.QCheckBox(self.GB_ram_P0)
        self.ZC_P0.setGeometry(QtCore.QRect(10, 110, 91, 17))
        self.ZC_P0.setObjectName("ZC_P0")
        self.ZC_P0.toggled.connect(lambda:self.ZC_func(self.ZC_P0.isChecked(), 0))

        ### No Dwell ###
        self.ND_P0 = QtWidgets.QCheckBox(self.GB_ram_P0)
        self.ND_P0.setGeometry(QtCore.QRect(160, 110, 91, 17))
        self.ND_P0.setObjectName("ND_P0")
        self.ND_P0.toggled.connect(lambda:self.ND_func(self.ND_P0.isChecked(), 0))

        ### List of functions to playback ###
        #self.Function_P0 = QtWidgets.QComboBox(self.GB_ram_P0)
        #self.Function_P0.setGeometry(QtCore.QRect(160, 50, 91, 22))
        #self.Function_P0.setObjectName("Function_P0")
        #for jc in range(len(self.RAM_functions)):
        #    self.Function_P0.addItem(self.RAM_functions[jc])

        ##### Profile 1 #####
        self.GB_ram_P1 = QtWidgets.QGroupBox(self.DDS_RAM)
        self.GB_ram_P1.setGeometry(QtCore.QRect(10, 180, 261, 141))
        self.GB_ram_P1.setAutoFillBackground(True)
        self.GB_ram_P1.setObjectName("GB_ram_P1")

        self.S_add_P1 = QtWidgets.QLineEdit(self.GB_ram_P1)
        self.S_add_P1.setGeometry(QtCore.QRect(90, 20, 51, 21))
        self.S_add_P1.setObjectName("Start_add_P1")
        self.S_add_P1.i = 1
        self.S_add_P1.editingFinished.connect(self.set_ram_start)

        self.label_89 = QtWidgets.QLabel(self.GB_ram_P1)
        self.label_89.setGeometry(QtCore.QRect(10, 20, 71, 16))
        self.label_89.setObjectName("label_89")

        self.label_90 = QtWidgets.QLabel(self.GB_ram_P1)
        self.label_90.setGeometry(QtCore.QRect(160, 80, 21, 16))
        self.label_90.setObjectName("label_90")

        self.label_91 = QtWidgets.QLabel(self.GB_ram_P1)
        self.label_91.setGeometry(QtCore.QRect(10, 50, 71, 16))
        self.label_91.setObjectName("label_91")

        self.E_add_P1 = QtWidgets.QLineEdit(self.GB_ram_P1)
        self.E_add_P1.setGeometry(QtCore.QRect(90, 50, 51, 21))
        self.E_add_P1.setObjectName("End_add_P1")
        self.E_add_P1.i = 1
        self.E_add_P1.editingFinished.connect(self.set_ram_end)

        self.SR_P1 = QtWidgets.QLineEdit(self.GB_ram_P1)
        self.SR_P1.setGeometry(QtCore.QRect(90, 80, 51, 21))
        self.SR_P1.setObjectName("Step_rate_P1")
        self.SR_P1.i = 1
        self.SR_P1.editingFinished.connect(self.set_ram_rate)

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

        self.ZC_P1 = QtWidgets.QCheckBox(self.GB_ram_P1)
        self.ZC_P1.setGeometry(QtCore.QRect(10, 110, 91, 17))
        self.ZC_P1.setObjectName("ZC_P1")
        self.ZC_P1.toggled.connect(lambda:self.ZC_func(self.ZC_P1.isChecked(), 1))


        self.ND_P1 = QtWidgets.QCheckBox(self.GB_ram_P1)
        self.ND_P1.setGeometry(QtCore.QRect(160, 110, 91, 17))
        self.ND_P1.setObjectName("ND_P1")
        self.ND_P1.toggled.connect(lambda:self.ND_func(self.ND_P1.isChecked(), 1))


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

        self.S_add_P2 = QtWidgets.QLineEdit(self.GB_ram_P2)
        self.S_add_P2.setGeometry(QtCore.QRect(90, 20, 51, 21))
        self.S_add_P2.setObjectName("Start_add_P2")
        self.S_add_P2.i = 2
        self.S_add_P2.editingFinished.connect(self.set_ram_start)

        self.label_97 = QtWidgets.QLabel(self.GB_ram_P2)
        self.label_97.setGeometry(QtCore.QRect(10, 20, 71, 16))
        self.label_97.setObjectName("label_97")

        self.label_98 = QtWidgets.QLabel(self.GB_ram_P2)
        self.label_98.setGeometry(QtCore.QRect(160, 80, 21, 16))
        self.label_98.setObjectName("label_98")

        self.label_99 = QtWidgets.QLabel(self.GB_ram_P2)
        self.label_99.setGeometry(QtCore.QRect(10, 50, 71, 16))
        self.label_99.setObjectName("label_99")

        self.E_add_P2 = QtWidgets.QLineEdit(self.GB_ram_P2)
        self.E_add_P2.setGeometry(QtCore.QRect(90, 50, 51, 21))
        self.E_add_P2.setObjectName("End_add_P2")
        self.E_add_P2.i = 2
        self.E_add_P2.editingFinished.connect(self.set_ram_end)

        self.SR_P2 = QtWidgets.QLineEdit(self.GB_ram_P2)
        self.SR_P2.setGeometry(QtCore.QRect(90, 80, 51, 21))
        self.SR_P2.setObjectName("Step_rate_P2")
        self.SR_P2.i = 2
        self.SR_P2.editingFinished.connect(self.set_ram_rate)

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


        self.ZC_P2 = QtWidgets.QCheckBox(self.GB_ram_P2)
        self.ZC_P2.setGeometry(QtCore.QRect(10, 110, 91, 17))
        self.ZC_P2.setObjectName("ZC_P2")
        self.ZC_P2.toggled.connect(lambda:self.ZC_func(self.ZC_P2.isChecked(), 2))

        self.ND_P2 = QtWidgets.QCheckBox(self.GB_ram_P2)
        self.ND_P2.setGeometry(QtCore.QRect(160, 110, 91, 17))
        self.ND_P2.setObjectName("ND_P2")
        self.ND_P2.toggled.connect(lambda:self.ND_func(self.ND_P2.isChecked(), 2))

        #self.Function_P2 = QtWidgets.QComboBox(self.GB_ram_P2)
        #self.Function_P2.setGeometry(QtCore.QRect(160, 50, 91, 22))
        #self.Function_P2.setObjectName("Function_P2")
        #for jc in range(len(self.RAM_functions)):
        #    self.Function_P2.addItem(self.RAM_functions[jc])
        
        self.GB_ram_P3 = QtWidgets.QGroupBox(self.DDS_RAM)
        self.GB_ram_P3.setGeometry(QtCore.QRect(280, 20, 261, 141))
        self.GB_ram_P3.setAutoFillBackground(True)
        self.GB_ram_P3.setObjectName("GB_ram_P3")

        self.S_add_P3 = QtWidgets.QLineEdit(self.GB_ram_P3)
        self.S_add_P3.setGeometry(QtCore.QRect(90, 20, 51, 21))
        self.S_add_P3.setObjectName("Start_add_P3")
        self.S_add_P3.i = 3
        self.S_add_P3.editingFinished.connect(self.set_ram_start)


        self.label_121 = QtWidgets.QLabel(self.GB_ram_P3)
        self.label_121.setGeometry(QtCore.QRect(10, 20, 71, 16))
        self.label_121.setObjectName("label_121")

        self.label_122 = QtWidgets.QLabel(self.GB_ram_P3)
        self.label_122.setGeometry(QtCore.QRect(160, 80, 21, 16))
        self.label_122.setObjectName("label_122")

        self.label_123 = QtWidgets.QLabel(self.GB_ram_P3)
        self.label_123.setGeometry(QtCore.QRect(10, 50, 71, 16))
        self.label_123.setObjectName("label_123")

        self.E_add_P3 = QtWidgets.QLineEdit(self.GB_ram_P3)
        self.E_add_P3.setGeometry(QtCore.QRect(90, 50, 51, 21))
        self.E_add_P3.setObjectName("End_add_P3")
        self.E_add_P3.i = 3
        self.E_add_P3.editingFinished.connect(self.set_ram_end)

        self.SR_P3 = QtWidgets.QLineEdit(self.GB_ram_P3)
        self.SR_P3.setGeometry(QtCore.QRect(90, 80, 51, 21))
        self.SR_P3.setObjectName("Step_rate_P3")
        self.SR_P3.i = 3
        self.SR_P3.editingFinished.connect(self.set_ram_rate)

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


        self.ZC_P3 = QtWidgets.QCheckBox(self.GB_ram_P3)
        self.ZC_P3.setGeometry(QtCore.QRect(10, 110, 91, 17))
        self.ZC_P3.setObjectName("ZC_P3")
        self.ZC_P3.toggled.connect(lambda:self.ZC_func(self.ZC_P3.isChecked(), 3))

        self.ND_P3 = QtWidgets.QCheckBox(self.GB_ram_P3)
        self.ND_P3.setGeometry(QtCore.QRect(160, 110, 91, 17))
        self.ND_P3.setObjectName("ND_P3")
        self.ND_P0.toggled.connect(lambda:self.ND_func(self.ND_P3.isChecked(), 3))

        # self.Function_P3 = QtWidgets.QComboBox(self.GB_ram_P3)
        # self.Function_P3.setGeometry(QtCore.QRect(160, 50, 91, 22))
        # self.Function_P3.setObjectName("Function_P3")
        # for jc in range(len(self.RAM_functions)):
        #     self.Function_P3.addItem(self.RAM_functions[jc])

        self.GB_ram_P4 = QtWidgets.QGroupBox(self.DDS_RAM)
        self.GB_ram_P4.setGeometry(QtCore.QRect(280, 180, 261, 141))
        self.GB_ram_P4.setAutoFillBackground(True)
        self.GB_ram_P4.setObjectName("GB_ram_P4")

        self.S_add_P4 = QtWidgets.QLineEdit(self.GB_ram_P4)
        self.S_add_P4.setGeometry(QtCore.QRect(90, 20, 51, 21))
        self.S_add_P4.setObjectName("Start_add_P4")
        self.S_add_P4.i = 4
        self.S_add_P4.editingFinished.connect(self.set_ram_start)

        self.label_117 = QtWidgets.QLabel(self.GB_ram_P4)
        self.label_117.setGeometry(QtCore.QRect(10, 20, 71, 16))
        self.label_117.setObjectName("label_117")

        self.label_118 = QtWidgets.QLabel(self.GB_ram_P4)
        self.label_118.setGeometry(QtCore.QRect(160, 80, 21, 16))
        self.label_118.setObjectName("label_118")

        self.label_119 = QtWidgets.QLabel(self.GB_ram_P4)
        self.label_119.setGeometry(QtCore.QRect(10, 50, 71, 16))
        self.label_119.setObjectName("label_119")

        self.E_add_P4 = QtWidgets.QLineEdit(self.GB_ram_P4)
        self.E_add_P4.setGeometry(QtCore.QRect(90, 50, 51, 21))
        self.E_add_P4.setObjectName("End_add_P4")
        self.E_add_P4.i = 4
        self.E_add_P4.editingFinished.connect(self.set_ram_end)

        self.SR_P4 = QtWidgets.QLineEdit(self.GB_ram_P4)
        self.SR_P4.setGeometry(QtCore.QRect(90, 80, 51, 21))
        self.SR_P4.setObjectName("Step_rate_P4")
        self.SR_P4.i = 4
        self.SR_P4.editingFinished.connect(self.set_ram_rate)

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


        self.ZC_P4 = QtWidgets.QCheckBox(self.GB_ram_P4)
        self.ZC_P4.setGeometry(QtCore.QRect(10, 110, 91, 17))
        self.ZC_P4.setObjectName("ZC_P4")
        self.ZC_P4.toggled.connect(lambda:self.ZC_func(self.ZC_P4.isChecked(), 4))

        self.ND_P4 = QtWidgets.QCheckBox(self.GB_ram_P4)
        self.ND_P4.setGeometry(QtCore.QRect(160, 110, 91, 17))
        self.ND_P4.setObjectName("ND_P4")
        self.ND_P4.toggled.connect(lambda:self.ND_func(self.ND_P4.isChecked(), 4))

        # self.Function_P4 = QtWidgets.QComboBox(self.GB_ram_P4)
        # self.Function_P4.setGeometry(QtCore.QRect(160, 50, 91, 22))
        # self.Function_P4.setObjectName("Function_P4")
        # for jc in range(len(self.RAM_functions)):
        #     self.Function_P4.addItem(self.RAM_functions[jc])

        self.GB_ram_P5 = QtWidgets.QGroupBox(self.DDS_RAM)
        self.GB_ram_P5.setGeometry(QtCore.QRect(280, 340, 261, 141))
        self.GB_ram_P5.setAutoFillBackground(True)
        self.GB_ram_P5.setObjectName("GB_ram_P5")

        self.S_add_P5 = QtWidgets.QLineEdit(self.GB_ram_P5)
        self.S_add_P5.setGeometry(QtCore.QRect(90, 20, 51, 21))
        self.S_add_P5.setObjectName("Start_add_P5")
        self.S_add_P5.i = 5
        self.S_add_P5.editingFinished.connect(self.set_ram_start)

        self.label_125 = QtWidgets.QLabel(self.GB_ram_P5)
        self.label_125.setGeometry(QtCore.QRect(10, 20, 71, 16))
        self.label_125.setObjectName("label_125")

        self.label_126 = QtWidgets.QLabel(self.GB_ram_P5)
        self.label_126.setGeometry(QtCore.QRect(160, 80, 21, 16))
        self.label_126.setObjectName("label_126")

        self.label_127 = QtWidgets.QLabel(self.GB_ram_P5)
        self.label_127.setGeometry(QtCore.QRect(10, 50, 71, 16))
        self.label_127.setObjectName("label_127")

        self.E_add_P5 = QtWidgets.QLineEdit(self.GB_ram_P5)
        self.E_add_P5.setGeometry(QtCore.QRect(90, 50, 51, 21))
        self.E_add_P5.setObjectName("End_add_P5")
        self.E_add_P5.i = 5
        self.E_add_P5.editingFinished.connect(self.set_ram_end)

        self.SR_P5 = QtWidgets.QLineEdit(self.GB_ram_P5)
        self.SR_P5.setGeometry(QtCore.QRect(90, 80, 51, 21))
        self.SR_P5.setObjectName("Step_rate_P5")
        self.SR_P5.i = 5
        self.SR_P5.editingFinished.connect(self.set_ram_rate)

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

        self.ZC_P5 = QtWidgets.QCheckBox(self.GB_ram_P5)
        self.ZC_P5.setGeometry(QtCore.QRect(10, 110, 91, 17))
        self.ZC_P5.setObjectName("ZC_P5")
        self.ZC_P5.toggled.connect(lambda:self.ZC_func(self.ZC_P5.isChecked(), 5))

        self.ND_P5 = QtWidgets.QCheckBox(self.GB_ram_P5)
        self.ND_P5.setGeometry(QtCore.QRect(160, 110, 91, 17))
        self.ND_P5.setObjectName("ND_P5")
        self.ND_P5.toggled.connect(lambda:self.ND_func(self.ND_P5.isChecked(), 5))

        # self.Function_P5 = QtWidgets.QComboBox(self.GB_ram_P5)
        # self.Function_P5.setGeometry(QtCore.QRect(160, 50, 91, 22))
        # self.Function_P5.setObjectName("Function_P5")
        # for jc in range(len(self.RAM_functions)):
        #     self.Function_P5.addItem(self.RAM_functions[jc])

        self.GB_ram_P6 = QtWidgets.QGroupBox(self.DDS_RAM)
        self.GB_ram_P6.setGeometry(QtCore.QRect(550, 20, 261, 141))
        self.GB_ram_P6.setAutoFillBackground(True)
        self.GB_ram_P6.setObjectName("GB_ram_P6")

        self.S_add_P6 = QtWidgets.QLineEdit(self.GB_ram_P6)
        self.S_add_P6.setGeometry(QtCore.QRect(90, 20, 51, 21))
        self.S_add_P6.setObjectName("Start_add_P6")
        self.S_add_P6.i = 6
        self.S_add_P6.editingFinished.connect(self.set_ram_start)

        self.label_137 = QtWidgets.QLabel(self.GB_ram_P6)
        self.label_137.setGeometry(QtCore.QRect(10, 20, 71, 16))
        self.label_137.setObjectName("label_137")

        self.label_138 = QtWidgets.QLabel(self.GB_ram_P6)
        self.label_138.setGeometry(QtCore.QRect(160, 80, 21, 16))
        self.label_138.setObjectName("label_138")

        self.label_139 = QtWidgets.QLabel(self.GB_ram_P6)
        self.label_139.setGeometry(QtCore.QRect(10, 50, 71, 16))
        self.label_139.setObjectName("label_139")

        self.E_add_P6 = QtWidgets.QLineEdit(self.GB_ram_P6)
        self.E_add_P6.setGeometry(QtCore.QRect(90, 50, 51, 21))
        self.E_add_P6.setObjectName("End_add_P6")
        self.E_add_P6.i = 6
        self.E_add_P6.editingFinished.connect(self.set_ram_end)

        self.SR_P6 = QtWidgets.QLineEdit(self.GB_ram_P6)
        self.SR_P6.setGeometry(QtCore.QRect(90, 80, 51, 21))
        self.SR_P6.setObjectName("Step_rate_P6")
        self.SR_P6.i = 6
        self.SR_P6.editingFinished.connect(self.set_ram_rate)

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

        self.ZC_P6 = QtWidgets.QCheckBox(self.GB_ram_P6)
        self.ZC_P6.setGeometry(QtCore.QRect(10, 110, 91, 17))
        self.ZC_P6.setObjectName("ZC_P6")
        self.ZC_P6.toggled.connect(lambda:self.ZC_func(self.ZC_P6.isChecked(), 6))

        self.ND_P6 = QtWidgets.QCheckBox(self.GB_ram_P6)
        self.ND_P6.setGeometry(QtCore.QRect(160, 110, 91, 17))
        self.ND_P6.setObjectName("ND_P6")
        self.ND_P6.toggled.connect(lambda:self.ND_func(self.ND_P6.isChecked(), 6))

        # self.Function_P6 = QtWidgets.QComboBox(self.GB_ram_P6)
        # self.Function_P6.setGeometry(QtCore.QRect(160, 50, 91, 22))
        # self.Function_P6.setObjectName("Function_P6")
        # for jc in range(len(self.RAM_functions)):
        #     self.Function_P6.addItem(self.RAM_functions[jc])

        self.GB_ram_P7 = QtWidgets.QGroupBox(self.DDS_RAM)
        self.GB_ram_P7.setGeometry(QtCore.QRect(550, 180, 261, 141))
        self.GB_ram_P7.setAutoFillBackground(True)
        self.GB_ram_P7.setObjectName("GB_ram_P7")

        self.S_add_P7 = QtWidgets.QLineEdit(self.GB_ram_P7)
        self.S_add_P7.setGeometry(QtCore.QRect(90, 20, 51, 21))
        self.S_add_P7.setObjectName("Start_add_P7")
        self.S_add_P7.i = 7
        self.S_add_P7.editingFinished.connect(self.set_ram_start)

        self.label_141 = QtWidgets.QLabel(self.GB_ram_P7)
        self.label_141.setGeometry(QtCore.QRect(10, 20, 71, 16))
        self.label_141.setObjectName("label_141")

        self.label_142 = QtWidgets.QLabel(self.GB_ram_P7)
        self.label_142.setGeometry(QtCore.QRect(160, 80, 21, 16))
        self.label_142.setObjectName("label_142")

        self.label_143 = QtWidgets.QLabel(self.GB_ram_P7)
        self.label_143.setGeometry(QtCore.QRect(10, 50, 71, 16))
        self.label_143.setObjectName("label_143")

        self.E_add_P7 = QtWidgets.QLineEdit(self.GB_ram_P7)
        self.E_add_P7.setGeometry(QtCore.QRect(90, 50, 51, 21))
        self.E_add_P7.setObjectName("End_add_P7")
        self.E_add_P7.i = 7
        self.E_add_P7.editingFinished.connect(self.set_ram_end)

        self.SR_P7 = QtWidgets.QLineEdit(self.GB_ram_P7)
        self.SR_P7.setGeometry(QtCore.QRect(90, 80, 51, 21))
        self.SR_P7.setObjectName("Step_rate_P7")
        self.SR_P7.i = 7
        self.SR_P7.editingFinished.connect(self.set_ram_rate)

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

        self.ZC_P7 = QtWidgets.QCheckBox(self.GB_ram_P7)
        self.ZC_P7.setGeometry(QtCore.QRect(10, 110, 91, 17))
        self.ZC_P7.setObjectName("ZC_P7")
        self.ZC_P7.toggled.connect(lambda:self.ZC_func(self.ZC_P7.isChecked(), 7))

        self.ND_P7 = QtWidgets.QCheckBox(self.GB_ram_P7)
        self.ND_P7.setGeometry(QtCore.QRect(160, 110, 91, 17))
        self.ND_P7.setObjectName("ND_P7")
        self.ND_P7.toggled.connect(lambda:self.ND_func(self.ND_P7.isChecked(), 7))


        # self.Function_P7 = QtWidgets.QComboBox(self.GB_ram_P7)
        # self.Function_P7.setGeometry(QtCore.QRect(160, 50, 91, 22))
        # self.Function_P7.setObjectName("Function_P7")
        # for jc in range(len(self.RAM_functions)):
        #     self.Function_P7.addItem(self.RAM_functions[jc])

        ##### RAM Programming options #####
        self.GB_ProgRAM = QtWidgets.QGroupBox(self.DDS_RAM)
        self.GB_ProgRAM.setGeometry(QtCore.QRect(550, 340, 261, 141))
        self.GB_ProgRAM.setAutoFillBackground(True)
        self.GB_ProgRAM.setObjectName("GB_ProgRAM")

        self.OSK_man = QtWidgets.QRadioButton(self.GB_ProgRAM)
        self.OSK_man.setGeometry(QtCore.QRect(10, 80, 101, 17))
        self.OSK_man.setObjectName("OSK_man")
        self.OSK_man.toggled.connect(self.Amplitude_RAM_func)

        self.RAM_prog = QtWidgets.QPushButton(self.GB_ProgRAM)
        self.RAM_prog.setGeometry(QtCore.QRect(130, 90, 111, 41))
        font = QtGui.QFont()
        font.setPointSize(10)
        self.RAM_prog.setFont(font)
        self.RAM_prog.setAutoFillBackground(True)
        self.RAM_prog.setObjectName("RAM_prog")
        self.RAM_prog.clicked.connect(self.Programme_DDS_RAM_func)
        self.RAM_prog.clicked.connect(self.enter_RAM_mode)

        self.RAM_data = QtWidgets.QComboBox(self.GB_ProgRAM)
        self.RAM_data.setGeometry(QtCore.QRect(100, 20, 141, 22))
        self.RAM_data.setObjectName("RAM_data")
        for keys in self.RAM_data_type.keys():
            self.RAM_data.addItem(keys)
        self.RAM_data.currentIndexChanged.connect(self.disable_modes_DRG_func)

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
        
        # load default STP profile
        self.load_STP('dds/defaultSTP.txt')
        self.load_RAMprofile('dds/defaultRAM.txt')

    def setupUi_DRG(self, MainWindow):

        self.Ramp_gen = QtWidgets.QWidget()
        self.Ramp_gen.setEnabled(True)
        self.Ramp_gen.setObjectName("Ramp_gen")

        self.checkBox = QtWidgets.QCheckBox(self.Ramp_gen)
        self.checkBox.setGeometry(QtCore.QRect(10, 10, 180, 41))
        self.checkBox.setObjectName("checkBox")
        self.checkBox.toggled.connect(lambda:self.switch_DRG_func(self.checkBox.isChecked(), 0))
        self.checkBox.toggled.connect(self.enter_ramp_mode)

        self.DRG_mode_GB = QtWidgets.QGroupBox(self.Ramp_gen)
        self.DRG_mode_GB.setGeometry(QtCore.QRect(10, 50, 391, 111))
        self.DRG_mode_GB.setAutoFillBackground(True)
        self.DRG_mode_GB.setCheckable(False)
        self.DRG_mode_GB.setObjectName("DRG_mode_GB")

        self.DRG_freq_cntrl = QtWidgets.QRadioButton(self.DRG_mode_GB)
        self.DRG_freq_cntrl.setGeometry(QtCore.QRect(20, 20, 121, 17))
        self.DRG_freq_cntrl.setObjectName("DRG Frequency")
        self.DRG_freq_cntrl.toggled.connect(lambda:self.DGR_parameter_func(self.DRG_freq_cntrl))
        self.DRG_freq_cntrl.setEnabled(False) # Disbale since we know frequency is the RAM default.

        self.DRG_phase_cntrl = QtWidgets.QRadioButton(self.DRG_mode_GB)
        self.DRG_phase_cntrl.setGeometry(QtCore.QRect(20, 50, 121, 17))
        self.DRG_phase_cntrl.setObjectName("DRG Phase")
        self.DRG_phase_cntrl.toggled.connect(lambda:self.DGR_parameter_func(self.DRG_phase_cntrl))

        self.DRG_amp_cntrl = QtWidgets.QRadioButton(self.DRG_mode_GB)
        self.DRG_amp_cntrl.setGeometry(QtCore.QRect(20, 80, 121, 17))
        self.DRG_amp_cntrl.setObjectName("DRG Amplitude")
        self.DRG_amp_cntrl.setChecked(True)
        self.DGR_destination = np.array([1,1])
        self.DRG_amp_cntrl.toggled.connect(lambda:self.DGR_parameter_func(self.DRG_amp_cntrl))

        self.DRG_options_GB = QtWidgets.QGroupBox(self.Ramp_gen)
        self.DRG_options_GB.setGeometry(QtCore.QRect(10, 380, 391, 111))
        self.DRG_options_GB.setAutoFillBackground(True)
        self.DRG_options_GB.setObjectName("DRG_options_GB")

        self.AutoclearDRG = QtWidgets.QCheckBox(self.DRG_options_GB)
        self.AutoclearDRG.setGeometry(QtCore.QRect(20, 20, 211, 17))
        self.AutoclearDRG.setObjectName("AutoclearDRG")
        self.AutoclearDRG.toggled.connect(lambda:self.switch_DRG_func(self.AutoclearDRG.isChecked(), 1))

        self.Clear_DRA = QtWidgets.QCheckBox(self.DRG_options_GB)
        self.Clear_DRA.setGeometry(QtCore.QRect(20, 50, 201, 17))
        self.Clear_DRA.setObjectName("Clear_DRA")
        self.Clear_DRA.toggled.connect(lambda:self.switch_DRG_func(self.Clear_DRA.isChecked(), 2))

        self.Load_DRR = QtWidgets.QCheckBox(self.DRG_options_GB)
        self.Load_DRR.setGeometry(QtCore.QRect(20, 80, 201, 17))
        self.Load_DRR.setObjectName("Load_DRR")
        self.Load_DRR.toggled.connect(lambda:self.switch_DRG_func(self.Load_DRR.isChecked(), 3))

        self.No_dwell_high = QtWidgets.QCheckBox(self.DRG_options_GB)
        self.No_dwell_high.setGeometry(QtCore.QRect(270, 20, 201, 17))
        self.No_dwell_high.setObjectName("No_dwell_high")
        self.No_dwell_high.toggled.connect(lambda:self.switch_DRG_func(self.No_dwell_high.isChecked(), 4))

        self.No_dwell_low = QtWidgets.QCheckBox(self.DRG_options_GB)
        self.No_dwell_low.setGeometry(QtCore.QRect(270, 50, 201, 17))
        self.No_dwell_low.setObjectName("No_dwell_low")
        self.No_dwell_low.toggled.connect(lambda:self.switch_DRG_func(self.No_dwell_low.isChecked(), 5))

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

        ### FPGA communication select
        self.FPGA_coms = QtWidgets.QGroupBox(self.FPGA_playback)
        self.FPGA_coms.setGeometry(QtCore.QRect(10, 50, 391, 111))
        self.FPGA_coms.setAutoFillBackground(True)
        self.FPGA_coms.setObjectName("FPGA_coms")

        self.FPGA_port_no = QtWidgets.QComboBox(self.FPGA_coms)
        self.FPGA_port_no.setGeometry(QtCore.QRect(268, 41, 91, 41))
        self.FPGA_port_no.setObjectName("FPGA_port_no")
        self.FPGA_port_no.addItem('--')

        self.label_149 = QtWidgets.QLabel(self.FPGA_coms)
        self.label_149.setGeometry(QtCore.QRect(170, 50, 91, 16))
        self.label_149.setObjectName("label_149")

        self.FPGA_file_select = QtWidgets.QGroupBox(self.FPGA_playback)
        self.FPGA_file_select.setGeometry(QtCore.QRect(10, 170, 391, 151))
        self.FPGA_file_select.setAutoFillBackground(True)
        self.FPGA_file_select.setObjectName("FPGA_file_select")

        self.Hex_file_radio = QtWidgets.QRadioButton(self.FPGA_file_select)
        self.Hex_file_radio.setGeometry(QtCore.QRect(20, 30, 82, 17))
        self.Hex_file_radio.setObjectName("Hex_file_radio")

        self.Coe_radio = QtWidgets.QRadioButton(self.FPGA_file_select)
        self.Coe_radio.setGeometry(QtCore.QRect(20, 60, 111, 17))
        self.Coe_radio.setObjectName("Coe_radio")
        self.Coe_radio.setChecked(True)
        self.Coe_radio.toggled.connect(self.Memory_file_type_func)

        self.LOAD_file_FPGA = QtWidgets.QPushButton(self.FPGA_file_select)
        self.LOAD_file_FPGA.setGeometry(QtCore.QRect(250, 50, 111, 41))
        font = QtGui.QFont()
        font.setPointSize(10)
        self.LOAD_file_FPGA.setFont(font)
        self.LOAD_file_FPGA.setAutoFillBackground(True)
        self.LOAD_file_FPGA.setObjectName("LOAD_file_FPGA")
        self.LOAD_file_FPGA.clicked.connect(self.file_open_FPGA_file_func)


        self.Generate_mem_FPGA = QtWidgets.QPushButton(self.FPGA_file_select)
        self.Generate_mem_FPGA.setGeometry(QtCore.QRect(250, 100, 111, 41))
        font = QtGui.QFont()
        font.setPointSize(10)
        self.Generate_mem_FPGA.setFont(font)
        self.Generate_mem_FPGA.setAutoFillBackground(True)
        self.Generate_mem_FPGA.setObjectName("Generate_mem_FPGA")
        self.Generate_mem_FPGA.clicked.connect(self.generate_FPGA_mem_file_func)

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
        self.Matched_lat.toggled.connect(lambda:self.switch_DRG_func(self.Matched_lat.isChecked(), 2))

        ##Set the last hold control options
        self.Hold_last = QtWidgets.QCheckBox(self.GB_ProgFPGA)
        self.Hold_last.setGeometry(QtCore.QRect(10, 60, 121, 17))
        self.Hold_last.setObjectName("Hold_last")
        self.Hold_last.toggled.connect(lambda:self.switch_DRG_func(self.Hold_last.isChecked(), 1))

        self.Prog_FPGA = QtWidgets.QPushButton(self.GB_ProgFPGA)
        self.Prog_FPGA.setGeometry(QtCore.QRect(130, 90, 111, 41))
        font = QtGui.QFont()
        font.setPointSize(10)
        self.Prog_FPGA.setFont(font)
        self.Prog_FPGA.setAutoFillBackground(True)
        self.Prog_FPGA.setObjectName("Prog_FPGA")

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
        self.Enable_FPGA_chck.toggled.connect(lambda:self.switch_DRG_func(self.Enable_FPGA_chck.isChecked(), 0))

        ## For FPGA systems where you can update the PLL paramters using a memory file
        self.FPGA_PLL = QtWidgets.QGroupBox(self.FPGA_playback)
        self.FPGA_PLL.setGeometry(QtCore.QRect(410, 170, 391, 151))
        self.FPGA_PLL.setAutoFillBackground(True)
        self.FPGA_PLL.setObjectName("FPGA_PLL")

        self.Hex_file_radio2 = QtWidgets.QRadioButton(self.FPGA_PLL)
        self.Hex_file_radio2.setGeometry(QtCore.QRect(20, 30, 82, 17))
        self.Hex_file_radio2.setObjectName("Hex_file_radio2")

        self.Coe_file_radio2 = QtWidgets.QRadioButton(self.FPGA_PLL)
        self.Coe_file_radio2.setGeometry(QtCore.QRect(20, 60, 111, 17))
        self.Coe_file_radio2.setObjectName("Coe_file_radio2")
        self.Coe_file_radio2.setChecked(True)
        self.Coe_file_radio2.toggled.connect(self.PLL_memory_file_type_func)

        self.Gen_PLL_file = QtWidgets.QPushButton(self.FPGA_PLL)
        self.Gen_PLL_file.setGeometry(QtCore.QRect(250, 100, 111, 41))
        font = QtGui.QFont()
        font.setPointSize(10)
        self.Gen_PLL_file.setFont(font)
        self.Gen_PLL_file.setAutoFillBackground(True)
        self.Gen_PLL_file.setObjectName("Gen_PLL_file")

        self.PLL_clk_out = QtWidgets.QLineEdit(self.FPGA_PLL)
        self.PLL_clk_out.setGeometry(QtCore.QRect(200, 30, 151, 21))
        self.PLL_clk_out.setObjectName("PLL_clk_out")

        self.label_18 = QtWidgets.QLabel(self.FPGA_PLL)
        self.label_18.setGeometry(QtCore.QRect(140, 30, 61, 16))
        self.label_18.setObjectName("label_18")

        self.label_12 = QtWidgets.QLabel(self.FPGA_PLL)
        self.label_12.setGeometry(QtCore.QRect(360, 30, 21, 16))
        self.label_12.setObjectName("label_12")

        self.FPGA_PLL.setEnabled(False)
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
        self.actionLoad_DDS_RAM.triggered.connect(self.file_open_DDS_RAM_func)

        self.actionUser_guide = QtWidgets.QAction(MainWindow)
        self.actionUser_guide.setObjectName("actionUser_guide")
        self.actionUser_guide.triggered.connect(self.launch_help_func)

        self.actionClose = QtWidgets.QAction(MainWindow)
        self.actionClose.setObjectName("actionClose")
        self.actionClose.triggered.connect(self.Disconnect_func)

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
        self.label_COM7.setText(_translate("MainWindow", "COM7: "+self.COMlabels[0]))
        self.label_COM8.setText(_translate("MainWindow", "COM8: "+self.COMlabels[1]))
        self.label_COM9.setText(_translate("MainWindow", "COM9: "+self.COMlabels[2]))
        self.label_COM10.setText(_translate("MainWindow", "COM10: "+self.COMlabels[3]))
        self.label_COM11.setText(_translate("MainWindow", "COM11: "+self.COMlabels[4]))
        self.Connect.setText(_translate("MainWindow", "Connect"))
        self.Disconnect.setText(_translate("MainWindow", "Disconnect"))

        self.GB_Aux.setTitle(_translate("MainWindow", "Auxillary parameter sources"))
        self.Freq_aux.setText(_translate("MainWindow", "110.00"))
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

        self.tabWidget.setTabText(self.tabWidget.indexOf(self.Coms), _translate("MainWindow", "Communication"))
        self.GB_P0.setTitle(_translate("MainWindow", "000 Profile 0"))
        self.Freq_P0.setText(_translate("MainWindow", "0.00"))
        self.label.setText(_translate("MainWindow", "Frequency"))
        self.label_2.setText(_translate("MainWindow", "MHz"))
        self.label_3.setText(_translate("MainWindow", "Deg"))
        self.label_4.setText(_translate("MainWindow", "Phase"))
        self.Phase_P0.setText(_translate("MainWindow", "0.00"))
        self.Amp_P0.setText(_translate("MainWindow", "1"))
        self.label_6.setText(_translate("MainWindow", "Amplitude"))
        self.GB_P1.setTitle(_translate("MainWindow", "100 Profile 1"))
        self.Freq_P1.setText(_translate("MainWindow", "0.00"))
        self.label_26.setText(_translate("MainWindow", "Frequency"))
        self.label_27.setText(_translate("MainWindow", "MHz"))
        self.label_28.setText(_translate("MainWindow", "Deg"))
        self.label_29.setText(_translate("MainWindow", "Phase"))
        self.Phase_P1.setText(_translate("MainWindow", "0.00"))
        self.Amp_P1.setText(_translate("MainWindow", "1"))
        self.label_30.setText(_translate("MainWindow", "Amplitude"))
        self.GB_P2.setTitle(_translate("MainWindow", "010 Profile 2"))
        self.Freq_P2.setText(_translate("MainWindow", "0.00"))
        self.label_36.setText(_translate("MainWindow", "Frequency"))
        self.label_37.setText(_translate("MainWindow", "MHz"))
        self.label_38.setText(_translate("MainWindow", "Deg"))
        self.label_39.setText(_translate("MainWindow", "Phase"))
        self.Phase_P2.setText(_translate("MainWindow", "0.00"))
        self.Amp_P2.setText(_translate("MainWindow", "1"))
        self.label_40.setText(_translate("MainWindow", "Amplitude"))
        self.GB_P3.setTitle(_translate("MainWindow", "110 Profile 3"))
        self.Freq_P3.setText(_translate("MainWindow", "0.00"))
        self.label_41.setText(_translate("MainWindow", "Frequency"))
        self.label_42.setText(_translate("MainWindow", "MHz"))
        self.label_43.setText(_translate("MainWindow", "Deg"))
        self.label_44.setText(_translate("MainWindow", "Phase"))
        self.Phase_P3.setText(_translate("MainWindow", "0.00"))
        self.Amp_P3.setText(_translate("MainWindow", "1"))
        self.label_45.setText(_translate("MainWindow", "Amplitude"))
        self.GB_P4.setTitle(_translate("MainWindow", "001 Profile 4"))
        self.Freq_P4.setText(_translate("MainWindow", "0.00"))
        self.label_46.setText(_translate("MainWindow", "Frequency"))
        self.label_47.setText(_translate("MainWindow", "MHz"))
        self.label_48.setText(_translate("MainWindow", "Deg"))
        self.label_49.setText(_translate("MainWindow", "Phase"))
        self.Phase_P4.setText(_translate("MainWindow", "0.00"))
        self.Amp_P4.setText(_translate("MainWindow", "1"))
        self.label_50.setText(_translate("MainWindow", "Amplitude"))
        self.GB_P5.setTitle(_translate("MainWindow", "101 Profile 5"))
        self.Freq_P5.setText(_translate("MainWindow", "0.00"))
        self.label_51.setText(_translate("MainWindow", "Frequency"))
        self.label_52.setText(_translate("MainWindow", "MHz"))
        self.label_53.setText(_translate("MainWindow", "Deg"))
        self.label_54.setText(_translate("MainWindow", "Phase"))
        self.Phase_P5.setText(_translate("MainWindow", "0.00"))
        self.Amp_P5.setText(_translate("MainWindow", "1"))
        self.label_55.setText(_translate("MainWindow", "Amplitude"))
        self.GB_P6.setTitle(_translate("MainWindow", "011 Profile 6"))
        self.Freq_P6.setText(_translate("MainWindow", "0.00"))
        self.label_56.setText(_translate("MainWindow", "Frequency"))
        self.label_57.setText(_translate("MainWindow", "MHz"))
        self.label_58.setText(_translate("MainWindow", "Deg"))
        self.label_59.setText(_translate("MainWindow", "Phase"))
        self.Phase_P6.setText(_translate("MainWindow", "0.00"))
        self.Amp_P6.setText(_translate("MainWindow", "1"))
        self.label_60.setText(_translate("MainWindow", "Amplitude"))
        self.GB_P7.setTitle(_translate("MainWindow", "111 Profile 7"))
        self.Freq_P7.setText(_translate("MainWindow", "0.00"))
        self.label_61.setText(_translate("MainWindow", "Frequency"))
        self.label_62.setText(_translate("MainWindow", "MHz"))
        self.label_63.setText(_translate("MainWindow", "Deg"))
        self.label_64.setText(_translate("MainWindow", "Phase"))
        self.Phase_P7.setText(_translate("MainWindow", "0.00"))
        self.Amp_P7.setText(_translate("MainWindow", "1"))
        self.label_65.setText(_translate("MainWindow", "Amplitude"))
        self.GB_ProgSTP.setTitle(_translate("MainWindow", "Options"))
        self.Amp_fix_STP.setText(_translate("MainWindow", "Amplitude fixed"))
        self.Amp_scl_STP.setText(_translate("MainWindow", "Amplitude scaling"))
        self.OSK_STP.setText(_translate("MainWindow", "Manual on/off"))
        self.Prog_STP.setText(_translate("MainWindow", "Programme"))
        self.tabWidget.setTabText(self.tabWidget.indexOf(self.Single_tone), _translate("MainWindow", "Single tone mode"))
        self.GB_ram_P0.setTitle(_translate("MainWindow", "000 Profile 0"))
        self.S_add_P0.setText(_translate("MainWindow", "0"))
        self.label_76.setText(_translate("MainWindow", "Start address"))
        self.label_78.setText(_translate("MainWindow", "µs"))
        self.label_79.setText(_translate("MainWindow", "End address"))
        self.E_add_P0.setText(_translate("MainWindow", "0"))
        self.SR_P0.setText(_translate("MainWindow", "1"))
        self.label_80.setText(_translate("MainWindow", "Step rate"))
        self.ZC_P0.setText(_translate("MainWindow", "Zero-crossing"))
        self.ND_P0.setText(_translate("MainWindow", "No Dwell"))
        self.GB_ram_P1.setTitle(_translate("MainWindow", "100 Profile 1"))
        self.S_add_P1.setText(_translate("MainWindow", "0"))
        self.label_89.setText(_translate("MainWindow", "Start address"))
        self.label_90.setText(_translate("MainWindow", "µs"))
        self.label_91.setText(_translate("MainWindow", "End address"))
        self.E_add_P1.setText(_translate("MainWindow", "0"))
        self.SR_P1.setText(_translate("MainWindow", "1"))
        self.label_92.setText(_translate("MainWindow", "Step rate"))
        self.ZC_P1.setText(_translate("MainWindow", "Zero-crossing"))
        self.ND_P1.setText(_translate("MainWindow", "No Dwell"))
        self.GB_ram_P2.setTitle(_translate("MainWindow", "010 Profile 2"))
        self.S_add_P2.setText(_translate("MainWindow", "0"))
        self.label_97.setText(_translate("MainWindow", "Start address"))
        self.label_98.setText(_translate("MainWindow", "µs"))
        self.label_99.setText(_translate("MainWindow", "End address"))
        self.E_add_P2.setText(_translate("MainWindow", "0"))
        self.SR_P2.setText(_translate("MainWindow", "1"))
        self.label_100.setText(_translate("MainWindow", "Step rate"))
        self.ZC_P2.setText(_translate("MainWindow", "Zero-crossing"))
        self.ND_P2.setText(_translate("MainWindow", "No Dwell"))
        self.GB_ram_P4.setTitle(_translate("MainWindow", "001 Profile 4"))
        self.S_add_P4.setText(_translate("MainWindow", "0"))
        self.label_117.setText(_translate("MainWindow", "Start address"))
        self.label_118.setText(_translate("MainWindow", "µs"))
        self.label_119.setText(_translate("MainWindow", "End address"))
        self.E_add_P4.setText(_translate("MainWindow", "0"))
        self.SR_P4.setText(_translate("MainWindow", "1"))
        self.label_120.setText(_translate("MainWindow", "Step rate"))
        self.ZC_P4.setText(_translate("MainWindow", "Zero-crossing"))
        self.ND_P4.setText(_translate("MainWindow", "No Dwell"))
        self.GB_ram_P3.setTitle(_translate("MainWindow", "110 Profile 3"))
        self.S_add_P3.setText(_translate("MainWindow", "0"))
        self.label_121.setText(_translate("MainWindow", "Start address"))
        self.label_122.setText(_translate("MainWindow", "µs"))
        self.label_123.setText(_translate("MainWindow", "End address"))
        self.E_add_P3.setText(_translate("MainWindow", "0"))
        self.SR_P3.setText(_translate("MainWindow", "1"))
        self.label_124.setText(_translate("MainWindow", "Step rate"))
        self.ZC_P3.setText(_translate("MainWindow", "Zero-crossing"))
        self.ND_P3.setText(_translate("MainWindow", "No Dwell"))
        self.GB_ram_P5.setTitle(_translate("MainWindow", "101 Profile 5"))
        self.S_add_P5.setText(_translate("MainWindow", "0"))
        self.label_125.setText(_translate("MainWindow", "Start address"))
        self.label_126.setText(_translate("MainWindow", "µs"))
        self.label_127.setText(_translate("MainWindow", "End address"))
        self.E_add_P5.setText(_translate("MainWindow", "0"))
        self.SR_P5.setText(_translate("MainWindow", "1"))
        self.label_128.setText(_translate("MainWindow", "Step rate"))
        self.ZC_P5.setText(_translate("MainWindow", "Zero-crossing"))
        self.ND_P5.setText(_translate("MainWindow", "No Dwell"))
        self.GB_ram_P6.setTitle(_translate("MainWindow", "011 Profile 6"))
        self.S_add_P6.setText(_translate("MainWindow", "0"))
        self.label_137.setText(_translate("MainWindow", "Start address"))
        self.label_138.setText(_translate("MainWindow", "µs"))
        self.label_139.setText(_translate("MainWindow", "End address"))
        self.E_add_P6.setText(_translate("MainWindow", "0"))
        self.SR_P6.setText(_translate("MainWindow", "1"))
        self.label_140.setText(_translate("MainWindow", "Step rate"))
        self.ZC_P6.setText(_translate("MainWindow", "Zero-crossing"))
        self.ND_P6.setText(_translate("MainWindow", "No Dwell"))
        self.GB_ram_P7.setTitle(_translate("MainWindow", "111 Profile 7"))
        self.S_add_P7.setText(_translate("MainWindow", "0"))
        self.label_141.setText(_translate("MainWindow", "Start address"))
        self.label_142.setText(_translate("MainWindow", "µs"))
        self.label_143.setText(_translate("MainWindow", "End address"))
        self.E_add_P7.setText(_translate("MainWindow", "0"))
        self.SR_P7.setText(_translate("MainWindow", "1"))
        self.label_144.setText(_translate("MainWindow", "Step rate"))
        self.ZC_P7.setText(_translate("MainWindow", "Zero-crossing"))
        self.ND_P7.setText(_translate("MainWindow", "No Dwell"))
        self.GB_ProgRAM.setTitle(_translate("MainWindow", "Options"))
        self.OSK_man.setText(_translate("MainWindow", "Manual on/off"))
        self.RAM_prog.setText(_translate("MainWindow", "Programme"))
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
        self.label_81.setText(_translate("MainWindow", "µs"))
        self.label_82.setText(_translate("MainWindow", "µs"))
        self.tabWidget.setTabText(self.tabWidget.indexOf(self.Ramp_gen), _translate("MainWindow", "DDS ramp generator"))


        self.FPGA_file_select.setTitle(_translate("MainWindow", "File selection and processing"))
        self.Hex_file_radio.setText(_translate("MainWindow", "Hex file"))
        self.Coe_radio.setText(_translate("MainWindow", "COE file"))
        self.LOAD_file_FPGA.setText(_translate("MainWindow", "Load"))
        self.Generate_mem_FPGA.setText(_translate("MainWindow", "Generate"))
        self.GB_ProgFPGA.setTitle(_translate("MainWindow", "Options"))
        self.Matched_lat.setText(_translate("MainWindow", "Matched latency"))
        self.Hold_last.setText(_translate("MainWindow", "Hold last value"))
        self.Prog_FPGA.setText(_translate("MainWindow", "Programme"))
        self.label_11.setText(_translate("MainWindow", "FM Gain"))
        self.Enable_FPGA_chck.setText(_translate("MainWindow", "Enable FPGA programming"))
        self.FPGA_PLL.setTitle(_translate("MainWindow", "FPGA update rate options"))
        self.Hex_file_radio2.setText(_translate("MainWindow", "Hex file"))
        self.Coe_file_radio2.setText(_translate("MainWindow", "COE file"))
        self.Gen_PLL_file.setText(_translate("MainWindow", "Generate"))
        self.PLL_clk_out.setText(_translate("MainWindow", "0.00"))
        self.label_18.setText(_translate("MainWindow", "Rate"))
        self.label_12.setText(_translate("MainWindow", "MHz"))
        self.label_19.setText(_translate("MainWindow", "FPGA programmer messages"))
        self.FPGA_coms.setTitle(_translate("MainWindow", "FPGA communications"))
        self.label_149.setText(_translate("MainWindow", "Programmer ID"))
        self.tabWidget.setTabText(self.tabWidget.indexOf(self.FPGA_playback), _translate("MainWindow", "FPGA playback"))

        self.menuFile.setTitle(_translate("MainWindow", "File"))
        self.menuHelp.setTitle(_translate("MainWindow", "Help"))
        self.actionRAM_editor.setText(_translate("MainWindow", "Open RAM editor"))
        self.actionLoad_stp.setText(_translate("MainWindow", "Load singe tone profile"))
        self.actionSave_stp.setText(_translate("MainWindow", "Save singe tone profile"))
        self.actionLoad_RAM.setText(_translate("MainWindow", "Load DDS RAM profile"))
        self.actionSave_RAM.setText(_translate("MainWindow", "Save DDS RAM profile"))
        self.actionLoad_all.setText(_translate("MainWindow", "Load all parameters"))
        self.actionSave_all.setText(_translate("MainWindow", "Save all parameters"))
        self.actionLoad_DDS_RAM.setText(_translate("MainWindow", "Load DDS RAM playback"))
        self.actionUser_guide.setText(_translate("MainWindow", "User guide"))
        self.actionClose.setText(_translate("MainWindow", "Close"))

    def Pydex_tcp_reset(self, force=False):
        if self.tcp.isRunning():
            if force:
                self.tcp.close()
                time.sleep(0.1) # give time for it to close
                self.tcp.start()
        else: self.tcp.start()
        self.Display_func('PyDex TCP server is ' + 'running.' if self.tcp.isRunning() else 'stopped.')

    def Get_serial_ports_func(self):
        """ Lists serial port names which are connected

            :raises EnvironmentError:
                On unsupported or unknown platforms
            :returns:
                A list of the serial ports available on the system
        """
        if sys.platform.startswith('win'):
            ports = ['COM%s' % (i + 1) for i in range(256)]
        elif sys.platform.startswith('linux') or sys.platform.startswith('cygwin'):
            # this excludes your current terminal "/dev/tty"
            ports = glob.glob('/dev/tty[A-Za-z]*')
        else:
            raise EnvironmentError('Unsupported platform. Check Get serial ports function in code.')
        result = []
        for port in ports:
            try:
                s = serial.Serial(port)
                s.close()
                result.append(port)
            except (OSError, serial.SerialException):
                pass
        return result

    def PortConfig_func(self):
        """
        Port configurations. Note these are kept behind the scenes. Confirm with the EWS on the values
        """

        self.port = str(self.COM_no.currentText()) #'COM4'
        if self.port == '--':
            self.Display_func('Please set the COM port number.')
        else:
            if not(self.connected):
                try:

                    self.ser = serial.Serial(
                        port=self.port,
                        baudrate=115200,
                        parity=serial.PARITY_NONE,
                        stopbits=serial.STOPBITS_ONE,
                        bytesize= serial.EIGHTBITS)

                    self.Display_func('Opened port sucessfully')
                    self.connected = True
                    self.debug_func(25)
                    time.sleep(0.05)
                    self.ind = (int(self.port.replace('COM',''))-7)%len(self.COMlabels)
                    self.mw.setWindowTitle(
                        'DDS GUI -- '+self.port+': '+self.COMlabels[self.ind])
                    self.redisplay_profiles()
                    self.reload_RAM()
                except Exception as e:
                    self.Display_func('Failed opening port, check port properties and COM name.\n'+str(e))
            else:
                self.get_message_func()

    def Display_func(self, x):
        """
        Display any messages from the DDS with a time stamp.
        """
        now = datetime.datetime.now()
        # dd/mm/YY H:M:S
        dt_string = now.strftime("%d/%m/%Y %H:%M:%S")
        self.Serial_com.append(dt_string + '>> \t ' + str(x))

    def Disconnect_func(self):
        if self.connected:
            self.connected = False

            self.ser.close()
            self.Display_func('Disconnected from ' + self.port)
            self.mw.setWindowTitle('DDS GUI -- disconnected')
        else:
            self.Display_func("Disconnected. But from what? Make sure you're connected to a device first.")

    def OSK_func(self):
        """Toggle between STP amplitude options:
        0 = fixed, 1 = manual on/off, 2 = amp scaling"""
        for i, label in enumerate(self.amp_options): # check which option is current
            if self.centralwidget.findChild(QtWidgets.QRadioButton, label).isChecked():
                break
        self.AMP_scale = i//2
        self.OSK_enable = i%2
        self.Manual_OSK = i%2
        
    def Amplitude_RAM_func(self):
        if self.OSK_man.isChecked() == True:
            self.AMP_scale = 0
            self.OSK_enable = 1
            self.Manual_OSK = 1
        else:
            self.AMP_scale = 0
            self.OSK_enable = 0
            self.Manual_OSK = 0

    def ZC_func(self, state, ID):
        """
        This function updates the storage of the zero-crossings.
        """
        if state:
            self.Zero_crossing[ID] = 1
        else:
            self.Zero_crossing[ID] = 0

    def ND_func(self, state, ID):
        """
        This function updates the storage of the no dwell.
        """
        if state:
            self.No_dwell[ID] = 1
        else:
            self.No_dwell[ID] = 0

    def switch_DRG_func(self, state, ID):
        if state:
            self.DGR_params[ID] = 1
        else:
            self.DGR_params[ID] = 0

    def disable_modes_DRG_func(self):

        NTS = self.RAM_data_type.get(str(self.RAM_data.currentText())) # Do not allow this state
        ID =  2*(NTS[0]) + NTS[1]
        if ID == 0:
            self.DRG_freq_cntrl.setChecked(False)
            self.DRG_freq_cntrl.setEnabled(False)
            self.DRG_phase_cntrl.setEnabled(True)
            self.DRG_amp_cntrl.setEnabled(True)
        elif ID == 1:
            self.DRG_phase_cntrl.setChecked(False)
            self.DRG_phase_cntrl.setEnabled(False)
            self.DRG_freq_cntrl.setEnabled(True)
            self.DRG_amp_cntrl.setEnabled(True)
        elif ID == 2:
            self.DRG_amp_cntrl.setChecked(False)
            self.DRG_amp_cntrl.setEnabled(False)
            self.DRG_freq_cntrl.setEnabled(True)
            self.DRG_phase_cntrl.setEnabled(True)
        else:
            self.DRG_amp_cntrl.setChecked(False)
            self.DRG_amp_cntrl.setEnabled(False)
            self.DRG_freq_cntrl.setEnabled(True)
            self.DRG_phase_cntrl.setChecked(False)
            self.DRG_phase_cntrl.setEnabled(False)

    def DGR_parameter_func(self, button):

        NTS = self.RAM_data_type.get(str(self.RAM_data.currentText())) # Do not allow this state
        ID =  2*(NTS[0]) + NTS[1]

        if button.text() == 'Frequency (MHz)':
            if ID != 0:
                self.DGR_destination = np.array([0,0])
            else:
                self.Display_func('Modulation type selection error. Check RAM and ramp generator.')

        elif button.text() == 'Phase (Deg)':

            if ID != 1:
                self.DGR_destination = np.array([0,1])
            else:
                self.Display_func('Modulation type selection error. Check RAM and ramp generator.')
        elif button.text() == 'Amplitude':
            if ID != 3 and ID != 2:
                self.DGR_destination = np.array([1,1])
            else:
                self.Display_func('Modulation type selection error. Check RAM and ramp generator.')
        else:
            self.Display_func(button.text())
        
        self.applyAmpValidators() # set limit on Amp if in Amp mode
        
    def set_stp_freq(self):
        try:
            self.fout[self.ind, self.mw.sender().i] = abs(float(self.mw.sender().text()))
        except ValueError: pass
        
    def set_stp_tht(self):
        try:
            self.tht[self.ind, self.mw.sender().i] = abs(float(self.mw.sender().text()))
        except ValueError: pass
        
    def set_stp_amp(self):
        val = self.dbl_fixup(self.mw.sender().text())
        self.amp[self.ind, self.mw.sender().i] = abs(float(val))
        self.mw.sender().setText(val)
        
    def set_ram_start(self):
        try:
            self.Start_Address[self.ind, self.mw.sender().i] = abs(float(self.mw.sender().text()))
        except ValueError: pass
        
    def set_ram_end(self):
        try:
            self.End_Address[self.ind, self.mw.sender().i] = abs(float(self.mw.sender().text()))
        except ValueError: pass
        
    def set_ram_rate(self):
        try:
            self.Rate[self.ind, self.mw.sender().i] = abs(float(self.mw.sender().text()))
        except ValueError: pass
        
    def set_ram_mode(self, text):
        try:
            self.RAM_playback_mode[self.ind, self.mw.sender().i, :] = self.RAM_profile_mode.get(text)
        except ValueError: pass
    
    def update_RAM_values_func(self):
        try:
            self.POW[self.ind] = abs(float(self.Phase_aux.text()))
            self.FTW[self.ind] = abs(float(self.Freq_aux.text()))
            self.AMW[self.ind] = abs(float(self.Amp_aux.text())%1.0001)
        except Exception as e:
            self.Display_func('Please make sure you use a real, positive number.\n'+str(e))
        try:
            self.RAM_playback_dest = self.RAM_data_type.get(str(self.RAM_data.currentText()))
            self.Int_profile_cntrl = self.RAM_controls.get(str(self.Int_ctrl.currentText()))
        except Exception as e:
            self.Display_func('Error setting additional playback information.\n'+str(e))

    def update_DRG_values_func(self):
        try:
            self.DRG_Start = abs(float(self.Sweep_start.text()))
            self.DRG_End = abs(float(self.Sweep_end.text()))
            self.DRG_P_stp_Size = abs(float(self.Pos_step.text()))
            self.DRG_N_stpSize = abs(float(self.Neg_step.text()))
            self.DRG_P_stp_Rate = abs(float(self.Pos_step_rate.text()))
            self.DRG_N_stp_Rate = abs(float(self.Neg_step_rate.text()))

        except:
            self.Display_func('Please make sure you use a real, positive number.')

    def Programme_STP_func(self):
        self.Display_func('\n --------------------------------- \n')
        self.RAM_enable = 0
        if self.DGR_params[0] == 1:
            self.update_DRG_values_func()
            self.DGR_register_func()

        # cfr1_old = self.CFR1.copy()
        # cfr2_old = self.CFR2.copy()

        #Send any changes to the registers to the DDS
        self.CFR1_register_loader()
        self.CFR2_register_loader()

        #Update the control registers if there has been a chnage
        # if all(cfr1_old == self.CFR1) == False:
        pack = ['{0:02x}'.format(23), '0'] # Second element is for the check sum
        Sum = int(pack[0], 16)

        for ic in range(4):
            a = np.packbits(self.CFR1[8*ic: 8*(ic+1)])[0]
            pack.append('{0:02x}'.format(a))
            Sum += int(pack[ic + 2], 16)

        sum_check = '{:0{width}x}'.format(int(np.binary_repr(np.invert(np.array([Sum], dtype = np.uint8))[0] + 1),2), width=2)

        if sum_check == '100':
            sum_check = '00'
            # sum_check = '{0:02x}'.format(sum_check)
        pack[1] = sum_check
        if self.connected:
            self.Send_serial_func(pack)

        ### CFR2

        # if all(cfr2_old == self.CFR2) == False:
        pack = ['{0:02x}'.format(1), '0']
        Sum = int(pack[0], 16)

        for ic in range(4):
            a = np.packbits(self.CFR2[8*ic: 8*(ic+1)])[0]
            pack.append('{0:02x}'.format(a))
            Sum += int(pack[ic + 2], 16)

        sum_check = '{:0{width}x}'.format(int(np.binary_repr(np.invert(np.array([Sum], dtype = np.uint8))[0] + 1),2), width=2)

        if sum_check == '100':
            sum_check = '00'
            # sum_check = '{0:02x}'.format(sum_check)
        pack[1] = sum_check
        if self.connected:
            self.Send_serial_func(pack)

        #Encode the parameters and send to the PSoC
        self.profile_register_func()
        
    def Programme_DDS_RAM_func(self):
        self.RAM_enable = 0
        # Make sure that RAM mode is disabled
        cfr1_old = self.CFR1.copy()

        #Send any changes to the registers to the DDS
        self.CFR1_register_loader()


        #Update the control registers if there has been a chnage
        if all(cfr1_old == self.CFR1) == False:
            pack = ['{0:02x}'.format(23), '0'] # Second element is for the check sum
            Sum = int(pack[0], 16)

            for ic in range(4):
                a = np.packbits(self.CFR1[8*ic: 8*(ic+1)])[0]
                pack.append('{0:02x}'.format(a))
                Sum += int(pack[ic + 2], 16)

            sum_check = '{:0{width}x}'.format(int(np.binary_repr(np.invert(np.array([Sum], dtype = np.uint8))[0] + 1),2), width=2)

            if sum_check == '100':
                sum_check = '00'
                # sum_check = '{0:02x}'.format(sum_check)
            pack[1] = sum_check
            if self.connected:
                self.Send_serial_func(pack)


        #Get the values in the text boxes
        #self.update_RAM_values_func()
        if self.DGR_params[0] == 1:
            self.update_DRG_values_func()
            self.DGR_register_func()

        #Encode the parameters and send to the PSoC
        self.profile_RAM_register_func(False) # False means set profile 0 only


        #FTW Programme, this in necessary if the RAM destination is amplitude.
        pack = ['{0:02x}'.format(7), '0']
        Sum = int(pack[0], 16)

        data = int(np.around((2**32 *(abs(self.FTW[self.ind])/1000)), decimals = 0)) #Note AD9910 has a clock frequency of 1 GHz or 1000 MHz
        if data >= 2**31:
            data = 2**31
        FTW = self.bin_array(data, 32)

        for ic in range(4):
            a = np.packbits(FTW[8*ic: 8*(ic+1)])[0]
            pack.append('{0:02x}'.format(a))
            Sum += int(pack[ic + 2], 16)

        sum_check = '{:0{width}x}'.format(int(np.binary_repr(np.invert(np.array([Sum], dtype = np.uint8))[0] + 1),2), width=2)

        if sum_check == '100':
            sum_check = '00'
            # sum_check = '{0:02x}'.format(sum_check)
        pack[1] = sum_check
        if self.connected:
            self.Send_serial_func(pack)

        # POW Programme, not necessary for an AOM but included for completeness
        pack = ['{0:02x}'.format(8), '0']
        Sum = int(pack[0], 16)

        data = int(np.around((2**16 *(abs(self.POW[self.ind])/360)), decimals = 0)) #Note AD9910 has a clock frequency of 1 GHz or 1000 MHz
        if data >= 2**16:
            data = 2**16-1
        POW = self.bin_array(data, 16)

        for ic in range(2):
            a = np.packbits(POW[8*ic: 8*(ic+1)])[0]
            pack.append('{0:02x}'.format(a))
            Sum += int(pack[ic + 2], 16)

        sum_check = '{:0{width}x}'.format(int(np.binary_repr(np.invert(np.array([Sum], dtype = np.uint8))[0] + 1),2), width=2)

        if sum_check == '100':
            sum_check = '00'
            # sum_check = '{0:02x}'.format(sum_check)
        pack[1] = sum_check
        if self.connected:
            self.Send_serial_func(pack)


        #Send the RAM data. Note this is sent backwards. Because reasons
        try:
            # Make sure that wwe have RAM data loaded
            RAM_data_reg = np.zeros((1024, 32), dtype = np.bool_())

            if len(self.RAM_modulation_data[self.ind][0,:]) >= 1024:
                self.Display_func('Data is too long and will be truncated')
                end = 1024
            else:
                end = len(self.RAM_modulation_data[self.ind][0,:])


            NTS = self.RAM_data_type.get(str(self.RAM_data.currentText())) # Do not allow this state
            ID =  2*(NTS[0]) + NTS[1]

            pack = ['{0:02x}'.format(22), '0']
            Sum = int(pack[0], 16)
            if ID == 0: # If the ramp generator is modulating frequency
                data = np.around((2**32 *(np.absolute(self.RAM_modulation_data[self.ind][0,:])/1000)), decimals = 0) #Note AD9910 has a clock frequency of 1 GHz or 1000 MHz
                ind_high = np.where(data >= 2**31)[0]
                data[ind_high] = 2**31
                ind = 32

            elif ID == 1: # If the ramp generator is modulating phase
                data = np.around((2**16 *(np.absolute(self.RAM_modulation_data[self.ind][0,:])/360)), decimals = 0)
                ind_high = np.where(data >= 2**16)[0]
                data[ind_high] = 2**16 - 1
                ind = 16

            elif ID == 2: # modulating amplitude
                data = np.around(2**14 *self.powercal(np.absolute(self.RAM_modulation_data[self.ind][0,:])/ np.amax(self.RAM_modulation_data[self.ind][0, :])*self.AMW[self.ind]), decimals = 0)
                ind_high = np.where(data >= 2**14)[0]
                data[ind_high] = 2**14- 1
                ind = 14
            else:
                data = np.around((2**16 *(np.absolute(self.RAM_modulation_data[self.ind][0,:])/360)), decimals = 0)
                ind_high = np.where(data >= 2**16)[0]
                data[ind_high] = 2**16- 1
                ind = 16

                data2 = np.around((2**14 *(np.absolute(self.RAM_modulation_data[self.ind][1,:])/ np.amax(self.RAM_modulation_data[self.ind][1, :]))), decimals = 0)
                ind_high = np.where(data >= 2**14)[0]
                data[ind_high] = 2**14- 1



            for ic in range(end):
                RAM_data_reg[ic, 0: ind] = self.bin_array(int(data[ic]), ind)
                if ID ==3:
                    RAM_data_reg[ic, ind: 32] = self.bin_array(int(data2[ic]), 14)

            if self.load_DDS_ram:
                for ic in range(1024):
                    for jc in range(4):

                        a = np.packbits(RAM_data_reg[-1-ic, 8*jc: 8*(jc+1) ])[0]
                        pack.append('{0:02x}'.format(a))
                        Sum += int(pack[ic + 2], 16)

                sum_check = '{:0{width}x}'.format(int(np.binary_repr(np.invert(np.array([Sum], dtype = np.uint8))[0] + 1),2), width=2)

                if sum_check == '100':
                    sum_check = '00'
                    # sum_check = '{0:02x}'.format(sum_check)
                pack[1] = sum_check
                #print(sum_check)

                if self.connected:
#                    time.sleep(0.5)
                    self.Send_serial_func(pack)
                self.load_DDS_ram = False # Save time and not rewrite the Ram
        except Exception as e:
            self.Display_func("Make sure the RAM data has been loaded: "+str(e))

#        time.sleep(5)
        self.profile_RAM_register_func(True)

        self.RAM_enable = 1
        cfr1_old = self.CFR1.copy()
        cfr2_old = self.CFR2.copy()

        #Send any changes to the registers to the DDS
        self.CFR1_register_loader()
        self.CFR2_register_loader()

        #Update the control registers if there has been a chnage
        if all(cfr1_old == self.CFR1) == False:
            pack = ['{0:02x}'.format(23), '0'] # Second element is for the check sum
            Sum = int(pack[0], 16)

            for ic in range(4):
                a = np.packbits(self.CFR1[8*ic: 8*(ic+1)])[0]
                pack.append('{0:02x}'.format(a))
                Sum += int(pack[ic + 2], 16)

            sum_check = '{:0{width}x}'.format(int(np.binary_repr(np.invert(np.array([Sum], dtype = np.uint8))[0] + 1),2), width=2)

            if sum_check == '100':
                sum_check = '00'
                # sum_check = '{0:02x}'.format(sum_check)
            pack[1] = sum_check
            if self.connected:
                self.Send_serial_func(pack)

        ### CFR2

        if all(cfr2_old == self.CFR2) == False:
            pack = ['{0:02x}'.format(1), '0']
            Sum = int(pack[0], 16)

            for ic in range(4):
                a = np.packbits(self.CFR2[8*ic: 8*(ic+1)])[0]
                pack.append('{0:02x}'.format(a))
                Sum += int(pack[ic + 2], 16)

            sum_check = '{:0{width}x}'.format(int(np.binary_repr(np.invert(np.array([Sum], dtype = np.uint8))[0] + 1),2), width=2)

            if sum_check == '100':
                sum_check = '00'
                # sum_check = '{0:02x}'.format(sum_check)
            pack[1] = sum_check
            if self.connected:
                self.Send_serial_func(pack)



    def CFR1_register_loader(self):
        """
        Rewrites register 1 on the DDS. This is rather invloved. Look at the AD9910 datasheet.
        """
        #self.RAM_enable = 0## disables RAM functionality (default). 1 = enables RAM functionality (required for both load/retrieve and playback operation).
        #RAM_playback_dest = np.array([0,0]) #RAM Playback CFR1[30:29] | Destination Bits Control Parameter | Bits Assigned
        #Manual_OSK = 0 #Ineffective unless CFR1[9:8] = 10b. 0 = OSK pin inoperative (default). 1 = OSK pin enabled for manual OSK control 22 Inverse sinc filter enable 0 = inverse sinc filter bypassed (default).

        sinc_filter = 0 #inverse sinc filter active.

        #Int_profile_cntrl = np.array([0,0,0,0]) #Ineffective unless CFR1[31] = 1. These bits are effective without the need for an I/O update. See Table 14 for details. Default is 0000b.

        Sine_output =  0 # Cosine  = 0 output of the DDS is selected (default). Sine = 1 output of the DDS is selected.
        Autoclear_phase = 0 # 0 = normal operation of the DDS phase accumulator (default). 1 = synchronously resets the DDS phase accumulator anytime I/O_UPDATE is asserted or a profile change occurs.

        Clear_phase_acc = 0 # 0 = normal operation of the DDS phase accumulator (default). 1 = asynchronous, static reset of the DDS phase accumulator.
        Load_ARR = 0 #@ I/O update Ineffective unless CFR1[9:8] = 11b. 0 = normal operation of the OSK amplitude ramp rate timer (default). 1 = OSK amplitude ramp rate timer reloaded anytime I/O_UPDATE is asserted or a PROFILE[2:0] change occurs.
        OSK_enable = 0 #The output shift keying enable bit. 0 = OSK disabled (default). 1 = OSK enabled.
        Auto_OSK = 0 #Ineffective unless CFR1[9] = 1. 0 = manual OSK enabled (default).1 = automatic OSK enabled.
        Dgtl_power_down = 0 #This bit is effective without the need for an I/O update. 0 = clock signals to the digital core are active (default). 1 = clock signals to the digital core are disabled.
        DAC_power_down = 0 #0 = DAC clock signals and bias circuits are active (default). 1 = DAC clock signals and bias circuits are disabled.
        REFCLK = 0 #input power-down This bit is effective without the need for an I/O update. 0 = REFCLK input circuits and PLL are active (default). 1 = REFCLK input circuits and PLL are disabled.
        Aux_DAC_power_down = 0 #0 = auxiliary DAC clock signals and bias circuits are active (default). 1 = auxiliary DAC clock signals and bias circuits are disabled.
        Ext_power_down = 0 #0 = assertion of the EXT_PWR_DWN pin affects full power-down (default). 1 = assertion of the EXT_PWR_DWN pin affects fast recovery power-down.
        SDIO = 0 #input only 0 = configures the SDIO pin for bidirectional operation; 2-wire serial programming mode (default). 1 = configures the serial data I/O pin (SDIO) as an input only pin; 3-wire serial programming mode.
        LSB  = 0#first 0 = configures the serial I/O port for MSB-first format (

        #############################################################################################
        self.CFR1[0] = self.RAM_enable
        self.CFR1[1:3] = self.RAM_playback_dest
        self.CFR1[8] = self.Manual_OSK
        self.CFR1[9] = sinc_filter
        self.CFR1[11:15] = self.Int_profile_cntrl
        self.CFR1[15] = Sine_output
        self.CFR1[16] = self.DGR_params[3]
        self.CFR1[17] = self.DGR_params[1]
        self.CFR1[18] = Autoclear_phase
        self.CFR1[19] = self.DGR_params[2]
        self.CFR1[20] = Clear_phase_acc
        self.CFR1[21] = Load_ARR
        self.CFR1[22] = self.OSK_enable
        self.CFR1[23] = Auto_OSK
        self.CFR1[24] = Dgtl_power_down
        self.CFR1[25] = DAC_power_down
        self.CFR1[26] = REFCLK

        self.CFR1[27] = Aux_DAC_power_down
        self.CFR1[28] = Ext_power_down
        self.CFR1[30] = SDIO
        self.CFR1[31] = LSB

    def CFR2_register_loader(self):
        """
        Rewrites register 2 on the DDS. This is rather invloved. Look at the AD9910 datasheet.
        """
        #AMP_scale = 0 #Enable amplitude scale from single tone profiles Ineffective if CFR2[19 ] = 1 or CFR1[31] = 1 or CFR1[9] = 1. 0 = the amplitude scaler is bypassed and shut down for power conservation (default). 1 = the amplitude is scaled by the ASF from the active profile.
        Internal_I_O = 0 #update active This bit is effective without the need for an I/O update.
        SYNC_CLK_en = 0 # 0 = the SYNC_CLK pin is disabled; static Logic 0 output. 1 = the SYNC_CLK pin generates a clock signal at 0.25 fSYSCLK; used for synchronization of the serial I/O port (default).
        DGT_ramp_des = np.array([0,0]) # See Table 11 for details. Default is 00b. See the Digital Ramp Generator (DRG) section for details.

        Rd_eff_FTW = 0 #a serial I/O port read operation of the FTW register reports the contents of the FTW register (default). 1 = a serial I/O port read operation of the FTW register reports the actual 32-bit word appearing at the input to the DDS phase accumulator.
        I_O_update_rate = np.array([0,0]) #Ineffective unless CFR2[23] = 1. Sets the prescale ratio of the divider that clocks the auto I/O update timer as follows:

        PDCLK_en = 1 #0 = the PDCLK pin is disabled and forced to a static Logic 0 state; the internal clock signal continues to operate and provide timing to the data assembler. 1 = the internal PDCLK signal appears at the PDCLK pin (default).
        PDCLK_inv = 0 # 0 = normal PDCLK polarity; Q-data associated with Logic 1, I-data with Logic 0 (default). 1 = inverted PDCLK polarity.
        TxEnable_inv = 0 # 0 = no inversion. 1 = inversion.

        #Matched_latency_en = 0# 0 = simultaneous application of amplitude, phase, and frequency changes to the DDS arrive at the output in the order listed (default). 1 = simultaneous application of amplitude, phase, and frequency changes to the DDS arrive at the output simultaneously.
        #Data_assembler_hold = 1 #hold last value Ineffective unless CFR2[4] = 1. 0 = the data assembler of the parallel data port internally forces zeros on the data path and ignores the signals on the D[15:0] and F[1:0] pins while the TxENABLE pin is Logic 0 (default). This implies that the destination of the data at the parallel data port is amplitude when TxENABLE is Logic 0. 1 = the data assembler of the parallel data port internally forces the last value received on the D[15:0] and F[1:0] pins while the TxENABLE pin is Logic 1.
        Sync_val_dsbl = 0 #0 = enables the SYNC_SMP_ERR pin to indicate (active high) detection of a synchronization pulse sampling error. 1 = the SYNC_SMP_ERR pin is forced to a static Logic 0 condition (default).
        #Parallel_en = 1  #See the Parallel Data Port Modulation Mode section for more details. 0 = disables parallel data port modulation functionality (default). 1 = enables parallel data port modulation functionality.
        #FM_gain = np.array([1,0,1,1]) #See the Parallel Data Port Modulation Mode section for more details. Default is 0000b.

        #############################################################################################
        self.CFR2[7] = self.AMP_scale
        self.CFR2[8] = Internal_I_O
        self.CFR2[9] = SYNC_CLK_en
        self.CFR2[10:12] = self.DGR_destination
        self.CFR2[12] = self.DGR_params[0]
        self.CFR2[13] = self.DGR_params[4]
        self.CFR2[14] = self.DGR_params[5]
        self.CFR2[15] = Rd_eff_FTW
        self.CFR2[16:18] = I_O_update_rate
        self.CFR2[20] = PDCLK_en
        self.CFR2[21] = PDCLK_inv
        self.CFR2[22] = TxEnable_inv

        self.CFR2[24] = self.FPGA_params[2]
        self.CFR2[25] = self.FPGA_params[1]
        self.CFR2[26] = Sync_val_dsbl
        self.CFR2[27] = self.FPGA_params[0]
        self.CFR2[28:32] = self.FM_gain_value

    def profile_register_func(self):
        """
        Convert decimal values into hex strings
        """
        fout, amp, tht = self.fout[self.ind], self.amp[self.ind], self.tht[self.ind]
        for ic in range(8):
            profile = np.zeros(64, dtype = np.bool_())
            if fout[ic] != 0.0:
                f = int(np.around((2**32 *(fout[ic]/1000)), decimals = 0)) #Note AD9910 has a clock frequency of 1 GHz or 1000 MHz
                if f > 2**31:
                    self.Display_func("Aliasing is likely to occur. Limiting frequency to 400 MHz.")
                    f = 2**31

                a = int(np.around(2**14 * abs(self.powercal(amp[ic])), decimals = 0)) # power calibration
                if a == 2**14:
                    a =2**14 -1
                if a > 2**14:
                    self.Display_func("Amplitude overflow")
                    a =2**14 -1

                p = int(np.around((2**16 *(tht[ic]/360)), decimals = 0))
                if p >= 2**16:
                    self.Display_func("Phase overflow")
                    p =2**16 -1

                profile[2:16] = self.bin_array(a, 14)
                profile[16:32] = self.bin_array(p, 16)
                profile[32:64] = self.bin_array(f, 32)

                pack = ['{0:02x}'.format((ic + 14)), '0'] #This is the address of the profile being loading
                Sum = int(pack[0], 16)

                for jc in range(8):
                    a = np.packbits(profile[8*jc: 8*(jc+1)])[0]
                    pack.append('{0:02x}'.format(a))
                    Sum += int(pack[jc + 2], 16)
                sum_check = '{:0{width}x}'.format(int(np.binary_repr(np.invert(np.array([Sum], dtype = np.uint8))[0] + 1),2), width=2)

                if sum_check == '100':
                    sum_check = '00'
                    # sum_check = '{0:02x}'.format(sum_check) # not sure what this line is supposed to be doing...
                pack[1] = sum_check

                if self.connected:
                    self.Send_serial_func(pack)

            else:
                #self.Display_func("Profile " + str(ic) + " skipped. Invalid frequency entered.")
                continue

    def profile_RAM_register_func(self, switch):
        """
        Convert the RAM profile data into the format required by the DDS

        The switch is used to write the concatenated wavefroms to the DDS, i.e. profile 0 is the write profile
        The correct profile data is set after the RAM is programmed.
        """
        Start_Address = self.Start_Address[self.ind]
        End_Address = self.End_Address[self.ind]
        Rate = self.Rate[self.ind]
        RAM_playback_mode = self.RAM_playback_mode[self.ind]
        Zero_crossing = self.Zero_crossing[self.ind]
        No_dwell = self.No_dwell[self.ind]
        
        for ic in range(8):
            if not(switch):
                if ic != 0:
                    break

            RAM_profile = np.zeros(64, dtype = np.bool_())
            #Prevent negative addresses
            if Start_Address[ic] < 0:
                self.Display_func("Adjusting start address of profile " + str(ic))
                Start_Address[ic] = 0

            if End_Address[ic] < 0:
                self.Display_func("Adjusting end address of profile " + str(ic))
                Start_Address[ic] = Start_Address[ic] + 1

            #Prevent addresses over 1024
            if Start_Address[ic] >= 1023:
                self.Display_func("Adjusting start address of profile " + str(ic))
                Start_Address[ic] = 1022

            if End_Address[ic] >= 1024:
                self.Display_func("Adjusting end address of profile " + str(ic))
                End_Address[ic] = 1023

            #Prevent start > end address
            if switch:
                if End_Address[ic] <= Start_Address[ic]:
                    #self.Display_func("Error in start and end addresses of profile " + str(ic) + " skipping")
                    continue
                if End_Address[ic] == Start_Address[ic]:
                    #self.Display_func("Error in start and end addresses of profile " + str(ic) + " skipping")
                    continue

            #Prevent negative or zero step rates
            if Rate[ic] <= 0:
                self.Display_func("Adjusting step rate of profile " + str(ic))
                Rate[ic] = 0.004
            if Rate[ic] > 262.14:
                self.Display_func("Adjusting step rate of profile " + str(ic))
                Rate[ic] = 262.14


            RAM_profile[61:64] = RAM_playback_mode[ic, :]
            RAM_profile[60] = Zero_crossing[ic]
            RAM_profile[58] = No_dwell[ic]

            RAM_profile[8:24] = self.bin_array(int(np.around((Rate[ic]*250), decimals = 0)), 16) #Refresh rate is given by f_clk/4 = 250 MHz
            if switch:
                RAM_profile[24:34] = self.bin_array(int(np.around((End_Address[ic]))), 10)
                RAM_profile[40:50] = self.bin_array(int(np.around((Start_Address[ic]))), 10)
            else:
                RAM_profile[24:34] = self.bin_array(int(1023), 10)
                RAM_profile[40:50] = self.bin_array(int(0), 10)



            pack = ['{0:02x}'.format((ic + 14)), '0'] #This is the address of the profile being loading
            Sum = int(pack[0], 16)

            for jc in range(8):
                a = np.packbits(RAM_profile[8*jc: 8*(jc+1)])[0]
                pack.append('{0:02x}'.format(a))
                Sum += int(pack[jc + 2], 16)

            sum_check = '{:0{width}x}'.format(int(np.binary_repr(np.invert(np.array([Sum], dtype = np.uint8))[0] + 1),2), width=2)

            if sum_check == '100':
                sum_check = '00'
                # sum_check = '{0:02x}'.format(sum_check)
            pack[1] = sum_check

            if self.connected:
                self.Send_serial_func(pack)

    def DGR_register_func(self):
        """
        Convert the DRG data into the format required by the DDS
        """
        try:
            ID =  int(2*self.DGR_destination[0] + self.DGR_destination[1])

            if self.DRG_Start < 0:
                self.Display_func("Adjusting lower limit of ramp")
                self.DRG_Start = 0

            if self.DRG_Start >= self.DRG_End:
                self.Display_func("Check the limits of the ramp generator")

            if ID == 0: # If the ramp generator is modulating frequency
                lower = int(np.around((2**32 *(self.DRG_Start/1000)), decimals = 0)) #Note AD9910 has a clock frequency of 1 GHz or 1000 MHz
                if lower >= 2**31:
                    self.Display_func("Ramp generator - aliasing is likely to occur. Limiting frequency to 400 MHz.")
                    lower = 2**31
                upper = int(np.around((2**32 *(self.DRG_End/1000)), decimals = 0)) #Note AD9910 has a clock frequency of 1 GHz or 1000 MHz
                if upper >= 2**31:
                    self.Display_func("Ramp generator - aliasing is likely to occur. Limiting frequency to 400 MHz.")
                    upper = 2**31

                pos_step = int(np.around((2**32 *(abs(self.DRG_P_stp_Size) /1000)), decimals = 0)) #Note AD9910 has a clock frequency of 1 GHz or 1000 MHz
                neg_step = int(np.around((2**32 *(abs(self.DRG_N_stpSize  /1000))), decimals = 0)) #Note AD9910 has a clock frequency of 1 GHz or 1000 MHz

                if pos_step <= 0:
                    pos_step = 1
                if neg_step <= 0:
                    neg_step = 1

                if pos_step >= 2**32:
                    pos_step = 2**32 - 1
                if neg_step == 2**32:
                    neg_step = 2**32 - 1

                ind = 32

            elif ID == 1: # If the ramp generator is modulating phase
                lower = int(np.around((2**16 *(self.DRG_Start/360)), decimals = 0))
                if lower >= 2**16:
                    self.Display_func("Phase overflow")
                    lower = 2**16 - 1
                upper = int(np.around((2**16 *(self.DRG_End/360)), decimals = 0))
                if upper >= 2**16:
                    self.Display_func("Phase overflow")
                    upper = 2**16 - 1

                pos_step = int(np.around((2**16 *(abs(self.DRG_P_stp_Size) /360)), decimals = 0))
                neg_step = int(np.around((2**16 *(abs(self.DRG_N_stpSize  /360))), decimals = 0))

                if pos_step <= 0:
                    pos_step = 1
                if neg_step <= 0:
                    neg_step = 1

                if pos_step >= 2**16:
                    pos_step = 2**16 - 1
                if neg_step == 2**16:
                    neg_step = 2**16 - 1

                ind = 16

            else:

                self.AMP_scale = 0
                lower = int(np.around((2**14 * abs(self.DRG_Start)), decimals = 0))
                if lower >= 2**14:
                    self.Display_func("Amplitude overflow")
                    lower = 2**14 - 1
                upper = int(np.around((2**14 * abs(self.DRG_End)), decimals = 0))
                if upper >= 2**14:
                    self.Display_func("Amplitude overflow")
                    upper = 2**14 - 1
                pos_step = int(np.around((2**14 *(abs(self.DRG_P_stp_Size))), decimals = 0))
                neg_step = int(np.around((2**14 *(abs(self.DRG_N_stpSize))), decimals = 0))

                if pos_step <= 0:
                    pos_step = 1
                if neg_step <= 0:
                    neg_step = 1

                if pos_step >= 2**14:
                    pos_step = 2**14 - 1
                if neg_step == 2**14:
                    neg_step = 2**14 - 1

                ind = 14

            #Prevent negative or zero step rates

            if self.DRG_P_stp_Rate <= 0:
                self.Display_func("Adjusting positive step rate of ramp")
                self.DRG_P_stp_Rate = (4/1000)
            if self.DRG_P_stp_Rate > (4*(2**16-1)/1000):
                self.Display_func("Adjusting positive step rate of ramp")
                self.DRG_P_stp_Rate = (4*(2**16-1)/1000)

            if self.DRG_N_stp_Rate <= 0:
                self.Display_func("Adjusting negative step rate of ramp")
                self.DRG_N_stp_Rate = (4/1000)
            if self.DRG_N_stp_Rate > (4*(2**16-1)/1000):
                self.Display_func("Adjusting negative step rate of ramp")
                self.DRG_N_stp_Rate = (4*(2**16-1)/1000)

        except:
            self.Display_func("Ensure all values of the ramp generator are correctly set")

        try:

            DRG_reg1 = np.zeros(64, dtype = np.bool_())
            DRG_reg2 = np.zeros(64, dtype = np.bool_())
            DRG_reg3 = np.zeros(32, dtype = np.bool_())


            # Make sure that the phase and amplitude binary reps are MSB aligned
            DRG_reg1[0: ind] = self.bin_array(upper, ind)
            DRG_reg1[32: 32 + ind] = self.bin_array(lower, ind)

            DRG_reg2[0: ind] = self.bin_array(neg_step, ind)
            DRG_reg2[32: 32 + ind] = self.bin_array(pos_step, ind)

            DRG_reg3[0:16] = self.bin_array(int(np.around((self.DRG_N_stp_Rate*250), decimals = 0)), 16) #Refresh rate is given by f_clk/4 = 250 MHz
            DRG_reg3[16:32] = self.bin_array(int(np.around((self.DRG_P_stp_Rate*250), decimals = 0)), 16) #Refresh rate is given by f_clk/4 = 250 MHz

            pack1 = ['{0:02x}'.format(11), '0']
            Sum = int(pack1[0], 16)
            for ic in range(8):
                a = np.packbits(DRG_reg1[8*ic: 8*(ic+1)])[0]
                pack1.append('{0:02x}'.format(a))
                Sum += int(pack1[ic + 2], 16)
            sum_check = '{:0{width}x}'.format(int(np.binary_repr(np.invert(np.array([Sum], dtype = np.uint8))[0] + 1),2), width=2)

            if sum_check == '100':
                sum_check = '00'
                # sum_check = '{0:02x}'.format(sum_check)
            pack1[1] = sum_check

            if self.connected:
                self.Send_serial_func(pack1)

            pack2 = ['{0:02x}'.format(12), '0']
            Sum = int(pack2[0], 16)

            for ic in range(8):
                a = np.packbits(DRG_reg2[8*ic: 8*(ic+1)])[0]
                pack2.append('{0:02x}'.format(a))
                Sum += int(pack2[ic + 2], 16)
            sum_check = '{:0{width}x}'.format(int(np.binary_repr(np.invert(np.array([Sum], dtype = np.uint8))[0] + 1),2), width=2)

            if sum_check == '100':
                sum_check = '00'
                # sum_check = '{0:02x}'.format(sum_check)
            pack2[1] = sum_check

            if self.connected:
                self.Send_serial_func(pack2)

            pack3 = ['{0:02x}'.format(13), '0']
            Sum = int(pack3[0], 16)

            for ic in range(4):
                a = np.packbits(DRG_reg3[8*ic: 8*(ic+1)])[0]
                pack3.append('{0:02x}'.format(a))
                Sum += int(pack3[ic + 2], 16)
            sum_check = '{:0{width}x}'.format(int(np.binary_repr(np.invert(np.array([Sum], dtype = np.uint8))[0] + 1),2), width=2)

            if sum_check == '100':
                sum_check = '00'
                # sum_check = '{0:02x}'.format(sum_check)
            pack3[1] = sum_check

            if self.connected:
                self.Send_serial_func(pack3)
        except:
            self.Display_func("Failed to write DGR")

    def Send_serial_func(self, CMDStr):
        """
        Sends the CMD string to the DDS.
        """
        print(CMDStr)
        # self.Display_func(CMDStr)
        #print(len(CMDStr))
#        time.sleep(0.1)
        try:
            for ic in range(len(CMDStr)):
#                time.sleep(0.001)
                self.ser.write(bytearray.fromhex(CMDStr[ic]))
                #print(bytearray.fromhex(CMDStr[ic]))

            self.get_message_func()

        except (OSError, serial.SerialException):
            self.Disconnect_func()
            self.Display_func('COM port is no longer conected. Could not send message.')
        
    def get_message_func(self):
        out = ''
        if self.connected:
#            time.sleep(0.01)
            try:
                while self.ser.inWaiting() > 0:
                    out += self.ser.read(1).decode('utf-8')
            except:
                self.Display_func('Values sent from driver did not make sense.')
            if out != '':
                self.Display_func(out)


    def file_open_DDS_RAM_func(self, name=''):
        """
        User input: points the system towards the RAM data for the DDS.

        """
        if not name:
            name, _ = QtWidgets.QFileDialog.getOpenFileName(
                self.centralwidget, 'Open RAM data file', '', 'csv(*.csv);;all (*)')

        try:
            self.RAM_modulation_data[self.ind] = np.loadtxt(name, delimiter = ',') 
            self.RAM_data_filename[self.ind] = os.path.basename(name)
            self.RAM_fname.setText(self.RAM_data_filename[self.ind])
            self.Display_func("DDS RAM data loaded from: " + name)
            self.load_DDS_ram = True
        except:
            self.Display_func("Data load failed")
            self.load_DDS_ram = False
            
    def launch_help_func(self):
        try:
            os.system('cmd /c "explorer.exe "GUI files\AD9910_DSS_user_guide.pdf" "')
            self.Display_func("Jesus Lana, read a book.")
        except:
            self.Display_func("User guide has been moved.")

    def bin_array(self, num, m):
        """Convert a positive integer num into an m-bit bit vector"""
        return np.array(list(np.binary_repr(num).zfill(m))).astype(np.int8)

    def debug_func(self, value=24):
        """Requests the PSoC to debug the DDS registers"""
        pack = ['{0:02x}'.format(24), '0'] # Second element is for the check sum
        Sum = int(pack[0], 16)

        sum_check = '{:0{width}x}'.format(int(np.binary_repr(np.invert(np.array([Sum], dtype = np.uint8))[0] + 1),2), width=2)

        if sum_check == '100':
            sum_check = '00'
            # sum_check = '{0:02x}'.format(sum_check)

        pack[1] = sum_check
        if self.connected:
            self.Send_serial_func(pack)
        else:
            self.Display_func('Nothing to debug yet (not connected to anything)')

    def switch_FPGA_func(self, state, ID):
        if state:
            self.FPGA_params[ID] = 1
        else:
            self.FPGA_params[ID] = 0

    def Programme_FPGA(self):
        ## Flash the FPGA memeory files


        ## Change the DDS parameters
        gain = int(self.FM_gain.currentText()) #'COM4'
        self.FM_gain_value = self.bin_array(gain, 4)

        cfr1_old = self.CFR1.copy()
        cfr2_old = self.CFR2.copy()

        #Send any changes to the registers to the DDS
        self.CFR1_register_loader()
        self.CFR2_register_loader()

        #Update the control registers if there has been a chnage
        if all(cfr1_old == self.CFR1) == False:
            pack = ['{0:02x}'.format(23), '0'] # Second element is for the check sum
            Sum = int(pack[0], 16)

            for ic in range(4):
                a = np.packbits(self.CFR1[8*ic: 8*(ic+1)])[0]
                pack.append('{0:02x}'.format(a))
                Sum += int(pack[ic + 2], 16)

            sum_check = '{:0{width}x}'.format(int(np.binary_repr(np.invert(np.array([Sum], dtype = np.uint8))[0] + 1),2), width=2)

            if sum_check == '100':
                sum_check = '00'
                # sum_check = '{0:02x}'.format(sum_check)
            pack[1] = sum_check
            if self.connected:
                self.Send_serial_func(pack)

        ### CFR2

        if all(cfr2_old == self.CFR2) == False:
            pack = ['{0:02x}'.format(1), '0']
            Sum = int(pack[0], 16)

            for ic in range(4):
                a = np.packbits(self.CFR2[8*ic: 8*(ic+1)])[0]
                pack.append('{0:02x}'.format(a))
                Sum += int(pack[ic + 2], 16)

            sum_check = '{:0{width}x}'.format(int(np.binary_repr(np.invert(np.array([Sum], dtype = np.uint8))[0] + 1),2), width=2)

            if sum_check == '100':
                sum_check = '00'
                # sum_check = '{0:02x}'.format(sum_check)
            pack[1] = sum_check
            if self.connected:
                self.Send_serial_func(pack)

        #if self.Memory_file_generated and FPGA_port_no != '--':
        #else:
        #   self.FPGA_display_func('Please ensure the memory file has been generated and the FPGA programmer ID is selected.')


    def file_open_FPGA_file_func(self):
        """
        User input: points the system towards the RAM data for the DDS.

        """

        name = QtWidgets.QFileDialog.getOpenFileName(MainWindow, 'Open File')

        try:
            self.FPGA_modulation_data = np.loadtxt(name[0], delimiter = ',') #file = open(name,'r')
            self.FPGA_display_func("Data loaded from > \t " + name[0] )
            self.load_FPGA_file = True
        except:
            self.FPGA_display_func("Data load failed")
            self.load_FPGA_file = False

    def Quartus_program(self):

    	cof_file = "DecConversion"
    	cable = "USB-Blaster"
    	port = "USB-0"
    	outfile = "DecPWM"

    	os.chdir(writedir)
    	self.FPGA_display_func("Updating FPGA memory files")
    	os.system("quartus_cdb --update_mif " + ProjName)

    	self.FPGA_display_func("Assembling files")
    	os.system("quartus_asm " + ProjName)

    	self.FPGA_display_func("Converting programming files")
    	os.system("quartus_cpf --convert " + cof_file + ".cof")

    	self.FPGA_display_func("Writing to FPGA")
    	os.system("quartus_pgm -c " + cable + " -m JTAG -o ipv;" + outfile + ".jic")

    def Mojo_program(self):

    	cof_file = "DecConversion"
    	cable = "USB-Blaster"
    	port = "USB-0"
    	outfile = "DecPWM"

    	os.chdir(writedir)
    	self.FPGA_display_func("Updating FPGA memory files")
    	os.system("quartus_cdb --update_mif " + ProjName)

    	self.FPGA_display_func("Assembling files")
    	os.system("quartus_asm " + ProjName)

    	self.FPGA_display_func("Converting programming files")
    	os.system("quartus_cpf --convert " + cof_file + ".cof")

    	self.FPGA_display_func("Writing to FPGA")
    	os.system("quartus_pgm -c " + cable + " -m JTAG -o ipv;" + outfile + ".jic")


    def Memory_file_type_func(self):
        if self.Coe_radio.isChecked() == True:
            self.memory_type = True
        else:
            self.memory_type = False

    def PLL_memory_file_type_func(self):
        if self.Coe_file_radio2.isChecked() == True:
            self.pll_type = True
        else:
            self.pll_type = False

    def generate_FPGA_mem_file_func(self):
        """
        This function produces the memory files for the FPGA.
        Notes:
        -COE files are for xilinx FPGAs
        -HEX files are for Altera/intel FPGAs
        -Check emeory size of each FPGA

        """

        if self.load_FPGA_file:
            '''Convert the raw data into the tuning words understood by the DDS'''
            try:
                addressing = self.FPGA_modulation_data[0,:] #The type of modulation
                data = self.FPGA_modulation_data[1,:]
                Pauses = self.FPGA_modulation_data[2,:]

                TW = np.zeros(len(self.FPGA_modulation_data[1,:]))


                #Amplitude
                ind = np.where(addressing == 0)[0]
                if len(ind) > 0:
                    TW[ind] = np.around((data[ind])*2**14, decimals = 0)*4 #The 4 bit shifts the data left

                #Phase
                ind = np.where(addressing == 1)[0]
                if len(ind) > 0:
                    TW[ind] = np.around((data[ind]/360)*2**16, decimals = 0)

                #frequency
                ind = np.where(addressing == 2)[0]
                if len(ind) > 0:
                    TW[ind] = np.around((data[ind]/1e9)*2**32, decimals = 0) #Note that the frequency here is in Hz

                    #Calculate the maxmimum bit needed and the FM gain
                    GAIN_value =  32 - int(np.ceil(np.log2(np.amax(TW[ind]))))

                    self.FPGA_display_func('Setting the FM gain to ' + str(16-GAIN_value) +'. Please ensure this is what you expect.')
                    self.FM_gain.setCurrentIndex(16-GAIN_value)

            except:
                self.FPGA_display_func('File of the wrong shape. See manual for the correct dimensions.')
                return 0



            if self.memory_type:
                ''' If an xilinx FPGA then generate a coe file.'''
                if len(TW) >= XILINX:
                    self.FPGA_display_func('Data overflow will occur')

                ### Hex file (memory file) creator ###
                file = open('ROM.coe', "w")

                for im in range(XILINX):
                    if im <= len(TW)-2:

                        if addressing[im] == 2:
                            data_bits = np.binary_repr(int(TW[im]), width = 32)
                            # trim off the 16 LSBs
                            data_bits = data_bits[GAIN_value : GAIN_value + 16]
                            #trimmed[im] = 1e9*(int(data_bits, 2)*2**(16-ind))/2**32
                        else:
                            if int(TW[im]) >= 2**16:
                                TW[im] = 2**16 - 1
                            data_bits = np.binary_repr(int(TW[im]), width = 16)
                        data_add_bits = np.binary_repr(int(addressing[im]), width = 2)

                        #Add the End of cycle, pause and data address bits
                        data_bin = '0' + str(int(Pauses[im]))  + data_bits + data_add_bits


                    elif im == len(TW)-1:
                        if addressing[im] == 2:
                            data_bits = np.binary_repr(int(TW[im]), width = 32)
                            # trim off the 16 LSBs
                            data_bits = data_bits[GAIN_value : GAIN_value + 16]
                            #trimmed[im] = 1e9*(int(data_bits, 2)*2**(16-ind))/2**32
                        else:
                            if int(TW[im]) >= 2**16:
                                TW[im] = 2**16 - 1
                            data_bits = np.binary_repr(int(TW[im]), width = 16)

                        data_add_bits = np.binary_repr(int(addressing[im]), width = 2)

                        #Add the End of cycle, pause and data address bits
                        data_bin = '1' + str(int(Pauses[im])) + data_bits + data_add_bits

                    else:
                        # Set the rest of the file to the previous value
                        ap, bp, cp = '0', '0', '0'
                        data_bin = np.binary_repr(0, width = 20)

                    file.write(data_bin) # hex file end
                    file.write('\n')

                file.write('\n')
                file.close()
                self.FPGA_display_func('COE memory file successfully created')

            else:
                ''' If an altera FPGA then generate a hex file.'''

                if len(TW) >= ALTERA:
                    self.FPGA_display_func('Data overflow will occur')

                ### Hex file (memory file) creator ###
                file = open('ROM.hex', "w")
                # Please see: https://en.wikipedia.org/wiki/Intel_HEX
                # Hex file formating
                record = 0      # Intel HEX has six standard record types: 0 is for data type
                count = 3           # Byte count, two hex digits (one hex digit pair), indicating the number of bytes (hex digit pairs) in the data field.
                                    # 20 bits of data requires 3 bytes
                countbits = '{:0{width}x}'.format(int(np.binary_repr(count),2), width=2)              #number of bytes representing the data change
                record_type = '{:0{width}x}'.format(int(np.binary_repr(record),2), width=2)          #record type of data string

                for im in range(ALTERA): # Do not change, this is set by the FPGA
                    # Address requires four hex digits
                    addressbits = np.binary_repr(im)
                    address_hex = '{:0{width}x}'.format(int(addressbits,2), width=4)
                    ep, fp = [address_hex [i:i+2] for i in range(0, len(address_hex), 2)]
                    if im <= len(TW)-2:

                        if addressing[im] == 2:
                            data_bits = np.binary_repr(int(TW[im]), width = 32)
                            # trim off the 16 LSBs
                            data_bits = data_bits[GAIN_value : GAIN_value + 16]
                            #trimmed[im] = 1e9*(int(data_bits, 2)*2**(16-ind))/2**32
                        else:
                            if int(TW[im]) >= 2**16:
                                TW[im] = 2**16 - 1
                            data_bits = np.binary_repr(int(TW[im]), width = 16)
                        data_add_bits = np.binary_repr(int(addressing[im]), width = 2)

                        #Add the End of cycle, pause and data address bits
                        data_hex = '{:0{width}x}'.format(int('0' + str(int(Pauses[im]))  + data_bits + data_add_bits, 2), width=6)
                        ap, bp, cp = [data_hex[i:i+2] for i in range(0, len(data_hex), 2)]

                    elif im == len(TW)-1:
                        if addressing[im] == 2:
                            data_bits = np.binary_repr(int(TW[im]), width = 32)
                            # trim off the 16 LSBs
                            data_bits = data_bits[GAIN_value : GAIN_value + 16]
                            #trimmed[im] = 1e9*(int(data_bits, 2)*2**(16-ind))/2**32
                        else:
                            if int(TW[im]) >= 2**16:
                                TW[im] = 2**16 - 1
                            data_bits = np.binary_repr(int(TW[im]), width = 16)
                        data_add_bits = np.binary_repr(int(addressing[im]), width = 2)

                        #Add the End of cycle, pause and data address bits
                        data_hex = '{:0{width}x}'.format(int('1' + str(int(Pauses[im]))  + data_bits + data_add_bits, 2), width=6)
                        ap, bp, cp = [data_hex[i:i+2] for i in range(0, len(data_hex), 2)]


                    else:
                        # Set the rest of the file to the previous value
                        ap, bp, cp = '0', '0', '0'
                        data_bites = np.binary_repr(0, width = 24)
                        data_hex = '{:0{width}x}'.format(int(data_bites,2), width=6)
                    dig_sum = record + count + int(ap, 16) + int(bp, 16) + int(cp, 16) + int(ep, 16) + int(fp, 16)

                    #two's complementary conversion - error checking see wiki page
                    sum_check = '{:0{width}x}'.format(int(np.binary_repr(np.invert(np.array([dig_sum], dtype = np.uint8))[0] + 1),2), width=2)
                    if sum_check == '100':
                        sum_check = '00'

                    file.write(':' + countbits.upper() + address_hex.upper() + record_type.upper() + data_hex.upper() + sum_check.upper()) # hex file end
                    file.write('\n')

                file.write(':00000001FF') # hex file end
                file.write('\n')
                file.close()
                self.FPGA_display_func('Hex memory file successfully created')
            self.Memory_file_generated = True
        else:
            self.FPGA_display_func('No file is selected yet. You should do that.')
            self.Memory_file_generated = False

    def FPGA_display_func(self, x):
        """
        Display any messages from the FPGA with a time stamp.
        """
        now = datetime.datetime.now()
        # dd/mm/YY H:M:S
        dt_string = now.strftime("%d/%m/%Y %H:%M:%S")
        self.fpga_PROGRAMMER_dia.append(dt_string + '>> \t ' + str(x))

if __name__ == "__main__":
    ################################################################################
    ### Set paths here
    home_path = os.getcwd()+'/'
    
    SavePrefix = home_path + "dds/Data_Files/AOM Driver Saved files/"
    
    now = datetime.datetime.now()
    date_str = now.strftime("%d_%m_%Y")
    
    Today_file = SavePrefix + date_str + "/"
    
    if os.path.exists(home_path + "dds/Data_Files/") == False:
        os.makedirs(home_path + "dds/Data_Files/")
    if os.path.exists(SavePrefix) == False:
        os.makedirs(SavePrefix)
    
    ## FPGA memory size
    ALTERA = 2**14
    XILINX = 2**16
    
    ###############################################################################
    # power calibration accounting for AOM nonlinearity
    from scipy.interpolate import interp1d
    try:
        cal = np.loadtxt('dds/power_calibration.csv', delimiter=',').T
        cals = [interp1d(cal[i+1], cal[0], fill_value='extrapolate') for i in range(len(cal)-1)]
#        cals = [interp1d(np.linspace(0,1,10), np.linspace(0,1,10), fill_value='extrapolate')
#                for i in range(5)]
        alim = 1.0
    except OSError as e:
        print('\033[31m' + '####\tERROR\t' + time.strftime('%d.%m.%Y\t%H:%M:%S'))
        print('\tCould not load power calibration file:\n' + str(e) + '\n', '\033[m')
        cals = [interp1d(np.linspace(0,1,10), np.linspace(0,1,10), fill_value='extrapolate')
                for i in range(5)]
        alim = 0.5
    
    app = QtWidgets.QApplication(sys.argv)
    MainWindow = QtWidgets.QMainWindow()
    ui = Ui_MainWindow(port=8624, host='129.234.190.164', alim=alim)
    ui.setupUi_coms(MainWindow)
    def closeEvent(event):
        """actions to carry out before closing the window"""
        ui.save_STP('dds/defaultSTP.txt')
        event.accept()
    MainWindow.closeEvent = closeEvent

    MainWindow.show()
    sys.exit(app.exec_())
