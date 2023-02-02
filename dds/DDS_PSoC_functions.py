import serial
import time
import json
import sys
import os
import glob
import datetime
import pickle
import numpy as np
import matplotlib.pyplot as plt
from collections import OrderedDict
from PyQt5 import QtWidgets

# power calibration accounting for AOM nonlinearity
from scipy.interpolate import interp1d
try:
    cal = np.loadtxt('dds/dds2_power_calibration.csv', delimiter=',').T
    cals = [interp1d(cal[i+1], cal[0], fill_value='extrapolate') for i in range(len(cal)-1)]
    # cals = [interp1d(np.linspace(0,1,10), np.linspace(0,1,10), fill_value='extrapolate')
    #         for i in range(5)]
    alim = 1.0
except OSError as e:
    print('\033[31m' + '####\tERROR\t' + time.strftime('%d.%m.%Y\t%H:%M:%S'))
    print('\tCould not load power calibration file:\n' + str(e) + '\n', '\033[m')
    cals = [interp1d(np.linspace(0,1,10), np.linspace(0,1,10), fill_value='extrapolate')
            for i in range(5)]
    alim = 0.5
        
        

class PSoC(object):

    def Pydex_tcp_reset(self, force=False):
        if self.tcp.isRunning():
            if force:
                self.tcp.close()
                time.sleep(0.1) # give time for it to close
                self.tcp.start()
        else: self.tcp.start()
        self.Display_Message_DDS('PyDex TCP server is ' + 'running.' if self.tcp.isRunning() else 'stopped.')
        
    def Get_serial_port_list(self):
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

    def Configure_serial_port(self):
        """
        Port configurations. Note these are kept behind the scenes. Do not change the serial values - these must match those of the PSoC
        """
        self.port = str(self.COM_no.currentText()) #'COM4'
        if self.port == '--':
            self.Display_Message_DDS('Please set the COM port number.')
        else:
            if not(self.connected):
                try:

                    self.ser = serial.Serial(
                        port=self.port,
                        baudrate=115200,
                        parity=serial.PARITY_NONE,
                        stopbits=serial.STOPBITS_ONE,
                        bytesize= serial.EIGHTBITS)

                    #self.Display_Message_DDS('Opened port sucessfully')
                    time.sleep(0.05)
                    self.connected = True
                    self.PSoC_PC_handshake()
                    self.set_window_title(self.Module_address.currentText())
                    self.Display_Message_DDS('Connected to ' + self.port + 
                        ' / %s: '%self.ind+self.COMlabels[self.ind])
                except:
                    self.Display_Message_DDS('Failed opening port, check port properties and COM name.')
            else:
                self.Get_message_from_DDS()

    def Display_Message_DDS(self, x):
        """
        Display any messages from the DDS with a time stamp.
        """
        now = datetime.datetime.now()
        # dd/mm/YY H:M:S
        dt_string = now.strftime("%d/%m/%Y %H:%M:%S")
        self.Serial_com.append(dt_string + '>> \t ' + str(x))

    def Disconnect_serial_port(self):
        """
        Disconnect from the serial port.
        """
        if self.connected:
            self.connected = False

            self.ser.close()
            self.Display_Message_DDS('Disconnected from ' + self.port)
            self.MainWindow.setWindowTitle('DDS2 GUI -- disconnected')
        else:
            self.Display_Message_DDS("Disconnected. But from what? Make sure you're connected to a device first.")

    def Send_data_to_DDS(self, CMDStr):
        """
        Sends the command string to the DDS.
        """
        if self.enable_print:
            print(CMDStr)

        # self.Display_Message_DDS(CMDStr)
        time.sleep(0.1)
        for ic in range(len(CMDStr)):
            time.sleep(0.001)
            self.ser.write(bytearray.fromhex(CMDStr[ic]))
            #print(bytearray.fromhex(CMDStr[ic]))

        self.Get_message_from_DDS()

    def Get_message_from_DDS(self):

        out = ''
        if self.connected:
            time.sleep(0.01)
            try:
                while self.ser.inWaiting() > 0:
                    out += self.ser.read(1).decode('utf-8')
            except:
                self.Display_Message_DDS('Values sent from driver did not make sense.')
            if out != '':
                self.Display_Message_DDS(out)



    def Format_array_transmission(self, command_ID, Data_array, N_Bytes):
        """
        Prepares data ready for transmission.
        Byte 1 = DDS module addresses
        Byte 2 = Command/register addresses
        Byte 3 = Check sum
        Byte 4 =  Data length1
        Byte 5 =  Data length2
        Others = data

        Converts a binary array into a series of bytes.
        """

        DDS_Address = '{0:02x}'.format(int(self.Module_address.currentText()))
        Data_length2 = '{0:02x}'.format(1)
        Data_length1 = '{0:02x}'.format(N_Bytes)

        if N_Bytes == 0:
            Data_length2 = '{0:02x}'.format(0)
            Data_length1 = '{0:02x}'.format(0)

        pack = [DDS_Address, '{0:02x}'.format(command_ID), '0', Data_length1, Data_length2] # Second element is for the check sum
        Sum = 0

        for ic in range(len(pack)):
            Sum += int(pack[ic], 16)

        if int(N_Bytes) > 0:
            for ic in range(int(N_Bytes)):
                a = np.packbits(Data_array[8*ic: 8*(ic+1)])[0]
                pack.append('{0:02x}'.format(a))
                Sum += int(pack[ic + 5], 16)

        sum_check = '{:0{width}x}'.format(int(np.binary_repr(np.invert(np.array([Sum], dtype = np.uint8))[0] + 1),2), width=2)

        if sum_check == '100':
            sum_check = 0
            sum_check = '{0:02x}'.format(sum_check)
        pack[2] = sum_check

        if self.connected:
            self.Send_data_to_DDS(pack)


    def PSoC_PC_handshake(self):
        """Requests the PSoC to say hello on start-up. Displays version number."""

        self.Format_array_transmission(24, None, 0)

        if self.connected:
            time.sleep(0.1)
            self.Get_message_from_DDS()
        else:
            self.Display_Message_DDS('Nothing to greet yet (not connected to anything)')

    def Register_debugger(self):
        """Requests the PSoC to debug the DDS registers"""
        self.Format_array_transmission(23, None, 0)

        if self.connected:
            time.sleep(0.1)
            self.Get_message_from_DDS()
        else:
            self.Display_Message_DDS('Nothing to debug yet (not connected to anything)')


    def Amplitude_Control_STP(self):
        """Toggle between STP amplitude options:
        0 = fixed, 1 = manual on/off, 2 = amp scaling"""
        for i, label in enumerate(self.amp_options): # check which option is current
            if self.centralwidget.findChild(QtWidgets.QRadioButton, label).isChecked():
                break
        self.AMP_scale = i//2   #### is amp_scale bit flipped???
        self.OSK_enable = i%2
        self.Manual_OSK = i%2

    def Amplitude_Control_RAM(self):
        """
        This function switches which amplitude control method is being used while in RAM mode.
        """
        if self.OSK_man.isChecked() == True:
            self.AMP_scale = 1   ##### this used to be 0
            self.OSK_enable = 1
            self.Manual_OSK = 1
        else:
            self.AMP_scale = 1  ##### this used to be 0
            self.OSK_enable = 0
            self.Manual_OSK = 0

    def Zero_crossings_update(self, state, ID):
        """
        This function updates the storage of the zero-crossings.
        """
        if state:
            self.Zero_crossing[ID] = 1
        else:
            self.Zero_crossing[ID] = 0

    def No_Dwell_update(self, state, ID):
        """
        This function updates the storage of the no dwell.
        """
        if state:
            self.No_dwell[ID] = 1
        else:
            self.No_dwell[ID] = 0

    def DRG_features_update(self, state, ID):
        """
        This function updates the storage array for the features used by the digital ramp generator.
        DRG enable = 0
        Auto-clearDRG = 1
        Clear DRA = 2
        Load_DRR = 3
        No dwell high = 4
        No dwell low = 5

        """
        if state:
            self.DGR_params[ID] = 1
        else:
            self.DGR_params[ID] = 0

    def disable_modulation_type_DRG(self):
        """
        Reduces the number available options the user can modulate with. This is necessary to avoid conflicts with the internal modulation priority.
        """

        NOT_allowed = self.RAM_data_type.get(str(self.RAM_data.currentText())) # Do not allow this state
        NOT_allowed_ID =  2*(NOT_allowed[0]) + NOT_allowed[1]

        if NOT_allowed_ID == 0:
            self.DRG_freq_cntrl.setChecked(False)
            self.DRG_freq_cntrl.setEnabled(False)
            self.DRG_phase_cntrl.setEnabled(True)
            self.DRG_amp_cntrl.setEnabled(True)
        elif NOT_allowed_ID == 1:
            self.DRG_phase_cntrl.setChecked(False)
            self.DRG_phase_cntrl.setEnabled(False)
            self.DRG_freq_cntrl.setEnabled(True)
            self.DRG_amp_cntrl.setEnabled(True)
        elif NOT_allowed_ID == 2:
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

    def DGR_modulation_select(self, button):
        """
        Converts the DRG modulation type into the binary format the DDS understands.
        """
        NOT_allowed = self.RAM_data_type.get(str(self.RAM_data.currentText())) # Do not allow this state
        NOT_allowed_ID =  2*(NOT_allowed[0]) + NOT_allowed[1]

        if button.text() == 'Frequency (MHz)':
            if NOT_allowed_ID != 0:
                self.DGR_destination = np.array([0,0])
            else:
                self.Display_Message_DDS('Modulation type selection error. Check RAM and ramp generator.')

        elif button.text() == 'Phase (Deg)':

            if NOT_allowed_ID != 1:
                self.DGR_destination = np.array([0,1])
            else:
                self.Display_Message_DDS('Modulation type selection error. Check RAM and ramp generator.')
        elif button.text() == 'Amplitude':
            if NOT_allowed_ID != 3 and NOT_allowed_ID != 2:
                self.DGR_destination = np.array([1,1])
            else:
                self.Display_Message_DDS('Modulation type selection error. Check RAM and ramp generator.')
        else:
            self.Display_Message_DDS(button.text())
        self.applyAmpValidators() # set limit on Amp if in Amp mode
        

    def set_stp_freq(self):
        try:
            self.fout[self.ind, self.MainWindow.sender().i] = abs(float(self.MainWindow.sender().text()))
        except ValueError: pass
        
    def set_stp_tht(self):
        try:
            self.tht[self.ind, self.MainWindow.sender().i] = abs(float(self.MainWindow.sender().text()))
        except ValueError: pass
        
    def set_stp_amp(self):
        val = self.dbl_fixup(self.MainWindow.sender().text())
        self.amp[self.ind, self.MainWindow.sender().i] = abs(float(val))
        self.MainWindow.sender().setText(val)
        
    def set_ram_start(self):
        try:
            self.Start_Address[self.ind, self.MainWindow.sender().i] = abs(float(self.MainWindow.sender().text()))
        except ValueError: pass
        
    def set_ram_end(self):
        try:
            self.End_Address[self.ind, self.MainWindow.sender().i] = abs(float(self.MainWindow.sender().text()))
        except ValueError: pass
        
    def set_ram_rate(self):
        try:
            self.Rate[self.ind, self.MainWindow.sender().i] = abs(float(self.MainWindow.sender().text()))
        except ValueError: pass
        
    def set_ram_mode(self, text):
        try:
            self.RAM_playback_mode[self.ind, self.MainWindow.sender().i, :] = self.RAM_profile_mode.get(text)
        except ValueError: pass
    
    def set_ram_pow(self):
        try:
            self.POW[self.ind] = abs(float(self.Phase_aux.text()))
        except Exception as e:
            self.Display_Message_DDS('Please make sure you use a real, positive number.\n'+str(e))
            
    def set_ram_ftw(self):
        try:
            self.FTW[self.ind] = abs(float(self.Freq_aux.text()))
        except Exception as e:
            self.Display_Message_DDS('Please make sure you use a real, positive number.\n'+str(e))
            
    def set_ram_amw(self):
        try:
            self.AMW[self.ind] = abs(float(self.Amp_aux.text())%1.0001)
        except Exception as e:
            self.Display_Message_DDS('Please make sure you use a real, positive number.\n'+str(e))
    
               
    def update_values_RAM(self):
        """
        Update playback info for the RAM mode
        """
        try:
            self.RAM_playback_dest = self.RAM_data_type.get(str(self.RAM_data.currentText()))
            self.Int_profile_cntrl = self.RAM_controls.get(str(self.Int_ctrl.currentText()))
        except:
            self.Display_Message_DDS('Error setting additional playback information.')

    def update_DRG_Limit_values(self):
        """
        Update all the digital ramp generator limits.
        """
        try:
            self.DRG_Start = abs(float(self.Sweep_start.text()))
            self.DRG_End = abs(float(self.Sweep_end.text()))
            self.DRG_P_stp_Size = abs(float(self.Pos_step.text()))
            self.DRG_N_stpSize = abs(float(self.Neg_step.text()))
            self.DRG_P_stp_Rate = abs(float(self.Pos_step_rate.text()))
            self.DRG_N_stp_Rate = abs(float(self.Neg_step_rate.text()))

        except:
            self.Display_Message_DDS('Please make sure you use a real, positive number.')

    def Open_RAM_playback_file(self, name=''):
        """
        User input: points the system towards the RAM data for the DDS.

        """
        if not name:
            name, _ = QtWidgets.QFileDialog.getOpenFileName(
                self.centralwidget, 'Open RAM data file', '', 'csv(*.csv);;all (*)')

        try:
            self.RAM_modulation_data[self.ind] = np.loadtxt(name, delimiter = ',') #file = open(name,'r')
            self.RAM_data_filename[self.ind] = os.path.basename(name)
            self.RAM_fname.setText(self.RAM_data_filename[self.ind])
            self.Display_Message_DDS("DSS RAM data loaded from > \t " + name )
            self.load_DDS_ram = True
        except:
            self.Display_Message_DDS("Data load failed")
            self.load_DDS_ram = False



    def Load_SingleToneProfiles(self):
        """
        Format all the registers ready for UART transmission.
        """
        self.Display_Message_DDS('\n --------------------------------- \n')
        self.RAM_enable = 0
        #Get the values in the text boxes
        # self.update_values_STP()
        if self.DGR_params[0] == 1:
            self.update_DRG_Limit_values()
            self.Load_DGR()


        #Send any changes to the registers to the DDS
        self.CFR1_register_loader()
        self.CFR2_register_loader()

        #Update the control registers if there has been a chnage

        self.Format_array_transmission(0, self.CFR1, 4)
        self.Format_array_transmission(1, self.CFR2, 4)

        #Encode the parameters and send to the PSoC
        self.Format_profile_register_data()
        

    def Load_RAM_playback(self):
        """
        Format all the registers ready for UART transmission.
        """
        self.RAM_enable = 0
        # Make sure that RAM mode is disabled
        cfr1_old = self.CFR1.copy()
        #Send any changes to the registers to the DDS
        self.CFR1_register_loader()


        #Update the control registers if there has been a chnage
        self.Format_array_transmission(0, self.CFR1, 4)
        #Get the values in the text boxes
        self.update_values_RAM()

        if self.DGR_params[0] == 1:
            self.update_DRG_Limit_values()
            self.Load_DGR()

        #Encode the parameters and send to the PSoC
        self.Format_RAM_register_data(False) # False means set profile 0 only

        #FTW load
        data = int(np.around((2**32 *(abs(self.FTW[self.ind])/1000)), decimals = 0)) #Note AD9910 has a clock frequency of 1 GHz or 1000 MHz
        if data >= 2**31:
            data = 2**31
        FTW = self.bin_array(data, 32)
        # print(FTW)

        self.Format_array_transmission(7, FTW, 4)

        # POW load, not necessary for an AOM but included for completeness
        data = int(np.around((2**16 *(abs(self.POW[self.ind])/360)), decimals = 0)) #Note AD9910 has a clock frequency of 1 GHz or 1000 MHz
        if data >= 2**16:
            data = 2**16-1
        POW = self.bin_array(data, 16)
        # print(POW)

        self.Format_array_transmission(8, POW, 2)

        #Send the RAM data. Note this is sent backwards. Because reasons
        try:
            # Make sure that wwe have RAM data loaded
            RAM_data_reg = np.zeros((1024, 32), dtype = np.bool_())
            
            if len(self.RAM_modulation_data[self.ind][0,:]) >= 1024:
               self.Display_Message_DDS('Data is too long and will be truncated')
               end = 1024
            else:
                end = len(self.RAM_modulation_data[self.ind][0,:])


            NTS = self.RAM_data_type.get(str(self.RAM_data.currentText())) # Do not allow this state
            ID =  2*(NTS[0]) + NTS[1]
            
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

            elif ID == 2:
                data = np.around(2**14 *self.powercal(np.absolute(self.RAM_modulation_data[self.ind][0,:]
                        )/ np.amax(self.RAM_modulation_data[self.ind][0, :])*self.AMW[self.ind]), decimals = 0)
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
                end *= end

            DDS_Address = '{0:02x}'.format(int(self.Module_address.currentText()))
            command_ID = 22 #### i think this is right based off the old code
            # pack: 3rd element is for the check sum, data length is 4*5
            pack = [DDS_Address, '{0:02x}'.format(command_ID), '0','{0:02x}'.format(32),'{0:02x}'.format(128)] 
            Sum = 0

            for ic in range(len(pack)):
                Sum += int(pack[ic], 16)

            for ic in range(end):
                RAM_data_reg[ic, 0: ind] = self.bin_array(int(data[ic]), ind)
                if ID ==3:
                    RAM_data_reg[ic, ind: 32] = self.bin_array(int(data2[ic]), 14)

            #np.savetxt('debug.csv', RAM_data_reg, delimiter = ',')
            if self.load_DDS_ram:
                for ic in range(1024):
                    for jc in range(4):

                        a = np.packbits(RAM_data_reg[-1-ic, 8*jc: 8*(jc+1) ])[0]
                        pack.append('{0:02x}'.format(a))
                        Sum += int(pack[ic + 5], 16)

                sum_check = '{:0{width}x}'.format(int(np.binary_repr(np.invert(np.array([Sum], dtype = np.uint8))[0] + 1),2), width=2)

                if sum_check == '100':
                    sum_check = 0
                    sum_check = '{0:02x}'.format(sum_check)
                pack[2] = sum_check

                if self.connected:
                    # time.sleep(0.5)
                    self.Send_data_to_DDS(pack)
                    
                self.load_DDS_ram = False
        except Exception as e:
            self.Display_Message_DDS("Make sure the RAM data has been loaded.\n"+str(e))
            self.Display_Message_DDS("RAM data shape: "+str(np.shape(self.RAM_modulation_data[self.ind])))

        # time.sleep(5)
        self.Format_RAM_register_data(True)

        self.RAM_enable = 1

        #Send any changes to the registers to the DDS
        self.CFR1_register_loader()
        self.CFR2_register_loader()

        self.Format_array_transmission(0, self.CFR1, 4)

        ### CFR2

        self.Format_array_transmission(1, self.CFR2, 4)

        #self.Display_Message_DDS("RAM data sent")


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
#        OSK_enable = 0 #The output shift keying enable bit. 0 = OSK disabled (default). 1 = OSK enabled.
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

    def Format_profile_register_data(self):
        """
        Convert decimal values into hex strings
        """
        fout, amp, tht = self.fout[self.ind], self.amp[self.ind], self.tht[self.ind]
        for ic in range(8):
            profile = np.zeros(64, dtype = np.bool_())
            if fout[ic] != 0.0:
                f = int(np.around((2**32 *(fout[ic]/1000)), decimals = 0)) #Note AD9910 has a clock frequency of 1 GHz or 1000 MHz
                if f > 2**31:
                    self.Display_Message_DDS("Aliasing is likely to occur. Limiting frequency to 400 MHz.")
                    f = 2**31

                # a = int(np.around(2**14 * abs(amp[ic]), decimals = 0))
                a = int(np.around(2**14 * abs(self.powercal(amp[ic])), decimals = 0)) # power calibration
                if a == 2**14:
                    a =2**14 -1
                if a > 2**14:
                    self.Display_Message_DDS("Amplitude overflow")
                    a =2**14 -1

                p = int(np.around((2**16 *(tht[ic]/360)), decimals = 0))
                if p >= 2**16:
                    self.Display_Message_DDS("Phase overflow")
                    p =2**16 -1

                profile[2:16] = self.bin_array(a, 14)
                profile[16:32] = self.bin_array(p, 16)
                profile[32:64] = self.bin_array(f, 32)


                self.Format_array_transmission((ic + 14), profile, 8)
            else:
                continue

    def Format_RAM_register_data(self, switch):
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
                self.Display_Message_DDS("Adjusting start address of profile " + str(ic))
                Start_Address[ic] = 0

            if End_Address[ic] < 0:
                self.Display_Message_DDS("Adjusting end address of profile " + str(ic))
                Start_Address[ic] = Start_Address[ic] + 1

            #Prevent addresses over 1024

            if Start_Address[ic] >= 1023:
                self.Display_Message_DDS("Adjusting start address of profile " + str(ic))
                Start_Address[ic] = 1022

            if End_Address[ic] >= 1024:
                self.Display_Message_DDS("Adjusting start address of profile " + str(ic))
                End_Address[ic] = 1023

            #Prevent start > end address
            if switch:
                if End_Address[ic] <= Start_Address[ic]:
                    #self.Display_Message_DDS("Error in start and end addresses of profile " + str(ic) + " skipping")
                    continue
                if End_Address[ic] == Start_Address[ic]:
                    #self.Display_Message_DDS("Error in start and end addresses of profile " + str(ic) + " skipping")
                    continue

            #Prevent negative or zero step rates

            if Rate[ic] <= 0:
                self.Display_Message_DDS("Adjusting step rate of profile " + str(ic))
                Rate[ic] = 0.004
            if Rate[ic] > 262.14:
                self.Display_Message_DDS("Adjusting step rate of profile " + str(ic))
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


            self.Format_array_transmission((ic + 14), RAM_profile, 8)


    def Load_DGR(self):
        """
        Convert the DRG data into the format required by the DDS
        """
        try:
            ID =  int(2*self.DGR_destination[0] + self.DGR_destination[1])

            if self.DRG_Start < 0:
                self.Display_Message_DDS("Adjusting lower limit of ramp")
                self.DRG_Start = 0

            if self.DRG_Start >= self.DRG_End:
                self.Display_Message_DDS("Check the limits of the ramp generator")

            if ID == 0: # If the ramp generator is modulating frequency
                lower = int(np.around((2**32 *(self.DRG_Start/1000)), decimals = 0)) #Note AD9910 has a clock frequency of 1 GHz or 1000 MHz
                if lower >= 2**31:
                    self.Display_Message_DDS("Ramp generator - aliasing is likely to occur. Limiting frequency to 400 MHz.")
                    lower = 2**31
                upper = int(np.around((2**32 *(self.DRG_End/1000)), decimals = 0)) #Note AD9910 has a clock frequency of 1 GHz or 1000 MHz
                if upper >= 2**31:
                    self.Display_Message_DDS("Ramp generator - aliasing is likely to occur. Limiting frequency to 400 MHz.")
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
                    self.Display_Message_DDS("Phase overflow")
                    lower = 2**16 - 1
                upper = int(np.around((2**16 *(self.DRG_End/360)), decimals = 0))
                if upper >= 2**16:
                    self.Display_Message_DDS("Phase overflow")
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
                    self.Display_Message_DDS("Amplitude overflow")
                    lower = 2**14 - 1
                upper = int(np.around((2**14 * abs(self.DRG_End)), decimals = 0))
                if upper >= 2**14:
                    self.Display_Message_DDS("Amplitude overflow")
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
                self.Display_Message_DDS("Adjusting positive step rate of ramp")
                self.DRG_P_stp_Rate = (4/1000)
            if self.DRG_P_stp_Rate > (4*(2**16-1)/1000):
                self.Display_Message_DDS("Adjusting positive step rate of ramp")
                self.DRG_P_stp_Rate = (4*(2**16-1)/1000)

            if self.DRG_N_stp_Rate <= 0:
                self.Display_Message_DDS("Adjusting negative step rate of ramp")
                self.DRG_N_stp_Rate = (4/1000)
            if self.DRG_N_stp_Rate > (4*(2**16-1)/1000):
                self.Display_Message_DDS("Adjusting negative step rate of ramp")
                self.DRG_N_stp_Rate = (4*(2**16-1)/1000)

        except:
            self.Display_Message_DDS("Ensure all values of the ramp generator are correctly set")

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

            self.Format_array_transmission(11, DRG_reg1, 8)
            self.Format_array_transmission(12, DRG_reg2, 8)
            self.Format_array_transmission(13, DRG_reg3, 4)
        except:
            self.Display_Message_DDS("Failed to write DGR")

    def launch_help_file(self):
        """ Open the user guide."""
        try:
            os.system('cmd /c "explorer.exe "GUI files\AD9910_DSS_user_guide.pdf" "')
            self.Display_Message_DDS("Jesus Lana, read a book.")
        except:
            self.Display_Message_DDS("User guide has been moved.")

    def bin_array(self, num, m):
        """Convert a positive integer num into an m-bit bit vector"""
        return np.array(list(np.binary_repr(num).zfill(m))).astype(np.int8)
    
    
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
            self.Display_Message_DDS('Command not understood: '+str(cmd))
            return 0                

        if any(x in cmd for x in['Freq', 'Phase', 'Amp']) and 'aux' not in cmd:
            self.mode = 'single tone'
        elif any(x in cmd for x in['Start_add', 'End_add', 'Step_rate', 'aux']):
            self.mode = 'RAM'
                
        if 'set_data' in cmd:
            try:
                value_list = eval(value) # nested list of parameters to change
            except Exception as e: 
                self.Display_Message_DDS('Failed to evaluate command: '+cmd)
                return 0
            prv_module = '' # keep track of which port we're communicating on
            success = [0 for i in range(len(value_list))]
            for i, (module, profile, key, val) in enumerate(value_list):
                # Set parameters. 
                try:
                    if 'Freq' in key and 'aux' not in profile:
                        self.fout[int(module), int(profile[1])] = float(val)
                    elif 'Phase' in key and 'aux' not in profile:
                        self.tht[int(module), int(profile[1])] = float(val)
                    elif 'Amp' in key and 'aux' not in profile:
                        self.amp[int(module), int(profile[1])] = float(val)
                    elif 'Start_add' in key:
                        self.Start_Address[int(module), int(profile[1])] = float(val)
                    elif 'End_add' in key:
                        self.End_Address[int(module), int(profile[1])] = float(val)
                    elif 'Step_rate' in key:
                        self.Rate[int(module), int(profile[1])] = float(val)
                    elif 'Freq' in key and 'aux' in profile:
                        self.FTW[int(module)] = float(val)
                    elif 'Phase' in key and 'aux' in profile:
                        self.POW[int(module)] = float(val)
                    elif 'Amp' in key and 'aux' in profile:
                        self.AMW[int(module)] = float(val)
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
            modules_to_program = list(set([x[0] for x in value_list]))
            for module in modules_to_program:
                # quick hack to make DDS send message only after all GUI elements have been updated
                # if we need to change port
                print('have waited programming module {}',format(module))
                if not self.connected or (module != self.Module_address.currentText() and 
                        module in [self.Module_address.itemText(i) for i in range(self.Module_address.count())]):
                    self.Disconnect_serial_port()
                    self.Module_address.setCurrentText(module)
                    self.Configure_serial_port()
                self.applyAmpValidators()
                # programme the DDS with the current data
                if module != prv_module:
                    if 'ramp' in self.mode:
                        self.checkBox.setChecked(True)
                    if 'single tone' in self.mode:
                        self.Load_SingleToneProfiles()
                    elif 'RAM' in self.mode:
                        self.Load_RAM_playback()
                    prv_module = module
            self.redisplay_profiles()
            self.Display_Message_DDS('Set parameters %s'%str([val for i, val in enumerate(value_list) if success[i]]))
        elif 'set_mode' in cmd:
            if value in self.mode_options:
                self.mode = value
            else: 
                self.mode = 'single tone'
            self.Display_Message_DDS('Changed to '+self.mode+' mode.')
        elif 'set_manual_on/off' in cmd:
            if value in self.amp_options:
                item = self.centralwidget.findChild(QtWidgets.QRadioButton, value)
                item.setChecked(True) # triggers OSK_func
                if value == 'manual on/off' and 'RAM' in self.mode:
                    self.OSK_man.setChecked(True)
                elif 'RAM' in self.mode: 
                    self.OSK_man.setChecked(False)
                self.Display_Message_DDS('Changed to %s.'%value)
        elif 'load_RAM_playback' in cmd:
            self.Open_RAM_playback_file(value)
        elif 'set_RAM_data_type' in cmd:
            if value in self.RAM_data_type.keys():
                self.RAM_data.setCurrentText(value) # triggers disable_modes_DRG_func
                self.Display_Message_DDS('Changed RAM data type to %s.'%value)
        elif 'set_internal_control' in cmd:
            if value in self.RAM_controls.keys():
                self.Int_ctrl.setCurrentText(value)
                self.Display_Message_DDS('Changed RAM internal control to %s.'%value)
        elif 'set_ramp_mode' in cmd:
            if value in self.DRG_modes:
                item = self.centralwidget.findChild(QtWidgets.QRadioButton, value)
                item.setChecked(True) # requires 
                self.Display_Message_DDS('Changed DRG mode to %s.'%value if item.isChecked() else 'none')
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
                self.Load_SingleToneProfiles()
            elif 'RAM' in self.mode:
                self.Load_RAM_playback()
                
    def set_window_title(self, text='1'):
        """Every time the module is updated, redisplay the profiles"""
        self.port = str(self.COM_no.currentText())
        try: 
            self.ind = int(text)
        except ValueError:
            self.ind = 1
        self.MainWindow.setWindowTitle(
            'DDS2 GUI -- '+self.port+': '+self.COMlabels[self.ind])
        self.redisplay_profiles()
        # self.reload_RAM() # removed so that the DDS doesn't resend RAM data unnecessarily
                
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
                self.centralwidget.findChild(QtWidgets.QLineEdit, 'Start_address_Prof%s'%i).setText('%s'%self.Start_Address[self.ind,i])
                self.centralwidget.findChild(QtWidgets.QLineEdit, 'End_address_Prof%s'%i).setText('%s'%self.End_Address[self.ind,i])
                self.centralwidget.findChild(QtWidgets.QLineEdit, 'StepRate_P%s'%i).setText('%s'%self.Rate[self.ind,i])
                self.centralwidget.findChild(QtWidgets.QCheckBox, 'NoDWell_Prof%s'%i).setChecked(bool(self.No_dwell[self.ind,i]))
                self.centralwidget.findChild(QtWidgets.QCheckBox, 'ZeroCrossing_Prof%s'%i).setChecked(bool(self.Zero_crossing[self.ind,i]))
                self.centralwidget.findChild(QtWidgets.QComboBox, 'Mode_P%s'%i).setCurrentIndex(self.search_dic(self.RAM_profile_mode.values(), self.RAM_playback_mode[self.ind,i]))
            except Exception as e: self.Display_Message_DDS("Couldn't display stored parameter:\n"+str(e)) # key could be for ramp
        try:
            self.Phase_aux.setText(str(self.POW[self.ind]))
            self.Freq_aux.setText(str(self.FTW[self.ind]))
            self.Amp_aux.setText(str(self.AMW[self.ind]))
            self.RAM_fname.setText(self.RAM_data_filename[self.ind])
        except Exception as e: self.Display_Message_DDS("Couldn't display stored parameter:\n"+str(e))
        
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
            self.Display_Message_DDS('Could not load STP from %s\n'%fname+str(e))
            
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
            self.Display_Message_DDS('Could not load RAM profiles from %s\n'%fname+str(e))

    def load_all(self, fname=''):
        """Take STP, RAM and auxiliary parameters from a file."""
        try:
            if not fname:
                fname, _ = QtWidgets.QFileDialog.getOpenFileName(
                    self.centralwidget, 'Open File', '', 'txt(*.txt);;all (*)')
            if os.path.exists(fname): # if user cancels then fname is empty str
                with open(fname) as f:
                    data = json.load(f)
                for key, val in data.items():
                    if 'RAM_data_filename' in key:
                        self.Display_Message_DDS('RAM data files were: %s'%val)
#                        self.RAM_data_filename = val
                    else:
                        setattr(self, key, np.array(val, dtype=float))
                self.redisplay_profiles()
                self.applyAmpValidators()
                self.Display_Message_DDS('Loaded parameters from %s'%fname)
        except Exception as e:
            self.Display_Message_DDS('Could not load params from %s\n'%fname+str(e))
            
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
            self.Display_Message_DDS(mode+' saved to %s'%fname)
        except (OSError, FileNotFoundError, IndexError) as e:
            self.Display_Message_DDS('Could not save '+mode+' to %s\n'%fname+str(e))

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
        except ValueError as e: self.Display_Message_DDS("Failed to save parameters:\n"+str(e))
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
        ports = self.Get_serial_port_list()
        self.COM_no.addItem('--')
        for jc in range(len(ports)):
            self.COM_no.addItem(ports[jc])
    
    
    ####### FPGA bla bla bla
    

    def switch_FPGA_func(self, state, ID):
        """
        Update the storage array which contains the features used by the DDS while in parallel port modulation

        Enable_FPGA = 0
        Hold_last = 1
        Matched_latency = 2
        """
        if state:
            self.FPGA_params[ID] = 1
        else:
            self.FPGA_params[ID] = 0

    def Programme_FPGA(self):
        """Prepare the arrays which will be sent to the DDS """


        ## Change the DDS parameters
        self.FM_gain_value = self.bin_array(int(self.FM_gain.currentText()), 4)


        #Send any changes to the registers to the DDS
        self.CFR1_register_loader()
        self.CFR2_register_loader()


        self.Format_array_transmission(0, self.CFR1, 4)

        ### CFR2
        self.Format_array_transmission(1, self.CFR2, 4)

    def file_open_FPGA_file_func(self):
        """
        User input: points the system towards the RAM data for the DDS.

        """

        name = QtWidgets.QFileDialog.getOpenFileName(self.MainWindow, 'Open File')

        try:
            self.FPGA_modulation_data = np.loadtxt(name[0], delimiter = ',') #file = open(name,'r')
            self.FPGA_Display_Message_DDS("Data loaded from > \t " + name[0] )
            self.load_FPGA_file = True
        except:
            self.FPGA_Display_Message_DDS("Data load failed")
            self.load_FPGA_file = False


    def Altera_FPGA_program(self):
        """ Programme the DDS and FPGA with the desired files"""
        if self.FPGA_params[0] == 1:
            self.Programme_FPGA()

            cof_file = "JIC_filetemp"
            cable = "USB-Blaster"
            port = "USB-0"
            outfile = "output_file"
            ProjName = "AD9910_dual_DDS"

            error_code = 0

            if self.load_FPGA_file:

                if not(self.Memory_file_generated):
                    self.FPGA_Display_Message_DDS("This session did not generate a new HEX file despite loading a modulation file. The FPGA will be loaded with the last used file.")

            else:
                self.FPGA_Display_Message_DDS("This session did not load a new memory file. Reflashing the FPGA with the previous memory file")


            try:
                os.chdir("GUI files\FPGA data")

                error_code =+1
                self.FPGA_Display_Message_DDS("Updating FPGA memory files")
                x = os.system("quartus_cdb --update_mif " + ProjName)

                if x != 0:
                    raise NameError('System path error')

                error_code =+1
                self.FPGA_Display_Message_DDS("Assembling files")
                os.system("quartus_asm " + ProjName)

                if x != 0:
                    raise NameError('System path error')

                error_code =+1
                self.FPGA_Display_Message_DDS("Converting programming files")
                os.system("quartus_cpf --convert " + cof_file + ".cof")
                if x != 0:
                    raise NameError('System path error')

                error_code =+1
                self.FPGA_Display_Message_DDS("Writing to FPGA")
                os.system("quartus_pgm -c " + cable + " -m JTAG -o ipv;" + outfile + ".jic")
                if x != 0:
                    raise NameError('System path error')

                self.Memory_file_generated = False

            except:
                self.FPGA_Display_Message_DDS("Error loading the HEX file to the FPGA. Error code " + str(error_code))
        else:
            self.FPGA_Display_Message_DDS("FPGA feature not enabled. Enable the click box before attempting to flash the FPGA.")


    def generate_FPGA_mem_file_func(self):
        """
        This function produces the memory files for the FPGA.
        Notes:
        -hex files are for alera FPGAs

        -Check emeory size of each FPGA

        """
        ROM_depth = 14

        if self.load_FPGA_file:
            '''Convert the raw data into the tuning words understood by the DDS. NOTE: Xilinx only'''
            try:

                data = self.FPGA_modulation_data[1,:]
                Pauses = self.FPGA_modulation_data[0,:]

                Init_data = self.FPGA_modulation_data[2,:]

                Divider = Init_data[0]
                modulation_type = Init_data[1]
                Sweep_back = Init_data[2]

                TW = np.zeros(len(self.FPGA_modulation_data[1,:]))


                if modulation_type == 0:
                    if np.amax(data) > 0.25:
                        self.FPGA_Display_Message_DDS("Warning, check scaling of the amplitude. You might damage the amplifier!")

                    addressing = '00'
                    modulation_type = 'amplitude'
                    TW = np.around((data)*2**14, decimals = 0)*4 #The 4 bit shifts the data left

                elif modulation_type == 1:
                    addressing = '01'
                    modulation_type = 'phase'

                    #Create the freqeuncy tuning word
                    TW = np.around((data/(2*np.pi))*2**16, decimals = 0)

                elif modulation_type == 2:
                    addressing = '10'
                    modulation_type = 'frequency'

                    #Create the freqeuncy tuning word
                    TW = np.around((data/1e9)*2**32, decimals = 0)

                    #Calculate the maxmimum bit needed and the FM gain
                    ind =  32 - int(np.ceil(np.log2(np.amax(TW))))
                    self.FPGA_Display_Message_DDS('Ensure the FM gain is set to '+str(16-ind))

                    self.FM_gain.setCurrentText(str(16-ind))

                elif modulation_type == 3:
                    addressing = '11'
                    modulation_type = 'polar'
                else:
                    self.FPGA_Display_Message_DDS('Invalid, defaulting to freqeuncy')
                    addressing = '10'
                    modulation_type = 'frequency'

            except:
                self.FPGA_Display_Message_DDS('File of the wrong shape. See manual for the correct dimensions.')

            if len(TW) >= 2**ROM_depth -1 :
                self.FPGA_Display_Message_DDS('Data source too long: data overflow of the FPGA memory will occur and your trajectory will be truncated.')
            self.FPGA_Display_Message_DDS("_____ data length ---> " +  str(len(f)) + "/" + str(2**14 - 1) +"  _____")


            ### Coe file (memory file) creator ###
            try:
                name = home_path + "/GUI files/FPGA project/Rom.hex"

                file = open(name, "w")

                # Please see: https://en.wikipedia.org/wiki/Intel_HEX

                # Hex file formating
                record = 0      # Intel HEX has six standard record types: 0 is for data type
                count = 3           # Byte count, two hex digits (one hex digit pair), indicating the number of bytes (hex digit pairs) in the data field.
                                    # 20 bits of data requires 3 bytes

                countbits = '{:0{width}x}'.format(int(np.binary_repr(count),2), width=2)              #number of bytes representing the data change
                record_type = '{:0{width}x}'.format(int(np.binary_repr(record),2), width=2)          #record type of data string

                for ic in range(2**ROM_depth): # Do not change, this is set by the FPGA

                    addressbits = np.binary_repr(ic)
                    address_hex = '{:0{width}x}'.format(int(addressbits,2), width=4)
                    ep, fp = [address_hex [i:i+2] for i in range(0, len(address_hex), 2)]

                    if ic == 0:
                        data_bits = np.binary_repr(int(0), width = 15)+ str(int(Sweep_back)) + np.binary_repr(int(Divider), width = 8)
                        data_hex = '{:0{width}x}'.format(int(data_bits, 2), width=6)
                        ap, bp, cp = [data_hex[i:i+2] for i in range(0, len(data_hex), 2)]
                        print(data_hex)

                    else:
                        im = ic -1
                        if im <= len(TW)-2:

                            if modulation_type == 'frequency':
                                data_bits = np.binary_repr(int(TW[im]), width = 32)
                                # trim off the 16 LSBs
                                data_bits = data_bits[ind : ind + 16]
                                #trimmed[im] = 1e9*(int(data_bits, 2)*2**(16-ind))/2**32
                            else:
                                if int(TW[im]) >= 2**16:
                                    TW[im] = 2**16 -1
                                data_bits = np.binary_repr(int(TW[im]), width = 16)




                            #Add the End of cycle, pause and data address bits


                            data_hex = '{:0{width}x}'.format(int('0' + str(int(pauses[im])) + addressing + data_bits, 2), width=6)
                            ap, bp, cp = [data_hex[i:i+2] for i in range(0, len(data_hex), 2)]
                            #print(data_hex)

                        elif im == len(TW)-1:
                            if modulation_type == 'frequency':
                                data_bits = np.binary_repr(int(TW[im]), width = 32)
                                # trim off the 16 LSBs
                                data_bits = data_bits[ind : ind + 16]
                                #trimmed[im] = 1e9*(int(data_bits, 2)*2**(16-ind))/2**32
                            else:
                                data_bits = np.binary_repr(int(TW[im]), width = 16)

                            #Add in the end of cycle bit, repeat the last command but with the end of cycle bit high
                            data_hex = '{:0{width}x}'.format(int('1' + '0' + addressing + data_bits, 2), width=6)
                            ap, bp, cp = [data_hex[i:i+2] for i in range(0, len(data_hex), 2)]
                            print(data_hex)

                        else:
                            # Set the rest of the file to the previous value

                            data_bites = np.binary_repr(0, width = 24)
                            data_hex = '{:0{width}x}'.format(int('1' + '0' + '00' + np.binary_repr(0, width = 16), 2), width=6)
                            ap, bp, cp = [data_hex[i:i+2] for i in range(0, len(data_hex), 2)]
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
                self.FPGA_Display_Message_DDS('HEX memory file successfully created')
                self.Memory_file_generated = True
            except:
                self.FPGA_Display_Message_DDS('Error generating HEX file. Check "GUI files".')

        else:
            self.FPGA_Display_Message_DDS('No file is selected yet. You should do that.')
            self.Memory_file_generated = False

    def FPGA_Display_Message_DDS(self, x):
        """
        Display any messages from the FPGA with a time stamp.
        """
        now = datetime.datetime.now()
        # dd/mm/YY H:M:S
        dt_string = now.strftime("%d/%m/%Y %H:%M:%S")
        self.fpga_PROGRAMMER_dia.append(dt_string + '>> \t ' + str(x))
