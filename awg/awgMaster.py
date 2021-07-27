"""m4i.6622 AWG master script
Stefan Spence 27.06.20
 - Import functions and classes to control AWG
 - Give a simple interface for user control
 - Communicate with PyDex and DExTer via TCP

26.05.2021
 - Rearrangement commands added
 - AWG now instantiated via rearrangement class imported from rearrangementHandler

07.06.2021 
 - Important to note that now save/load/setSeg functions are defined differently
   depending if rearr is on or off. They get redefined in rearrHandler.set_functions
   - If rearr off, will use same functions as previously and nothing changes.
   
"""
import time
import os
os.chdir(os.path.dirname(os.path.realpath(__file__)))
import sys
sys.path.append('..')
from collections import OrderedDict
from PyQt5.QtCore import QThread, pyqtSignal, QTimer
from PyQt5.QtGui import (QIcon, QDoubleValidator, QIntValidator, 
    QFont, QRegExpValidator)
from PyQt5.QtWidgets import (QApplication, QPushButton, QWidget, 
    QTabWidget, QAction, QMainWindow, QLabel, QInputDialog, QGridLayout,
    QMessageBox, QLineEdit, QFileDialog, QComboBox, QActionGroup, QMenu,
    QVBoxLayout, QTextBrowser)
import logging
import logerrs
logerrs.setup_log()
logger = logging.getLogger(__name__)
from awgHandler import AWG
from awgPlotter import plot_playback
from pyspcm import spcm_dwGetParam_i32, byref, int32
import fileWriter as fw
from networking.networker import PyServer, reset_slot
from networking.client import PyClient
import rearrHandler

####    ####    ####    ####

class awg_window(QMainWindow):
    """A basic GUI to take in commands from the user.
    
    Initiates the AWG and a TCP server and client for communication.
    Keyword arguments:
    config_file -- path to the file that saved the previous settings.
    """
    def __init__(self, config_file='.\\state', AWG_channels=[0], 
            default_seq=r'Z:\Tweezer\Code\Python 3.5\PyDex\awg\AWG template sequences\single_static_32segs.txt'):
        super().__init__()
        # self.types = OrderedDict([('FileName',str), ('segment',int)])
        self.stats = OrderedDict([('FileName', 0), ('segment', 0)])
        self.t_load = 0 # time taken to transfer data onto card
        self.init_UI()
        self.server = PyServer(host='', port=8626) # TCP server to message PyDex
        self.server.start()
        self.client = PyClient(host='129.234.190.164', port=8623) # TCP client to message PyDex
        self.client.textin[str].connect(self.respond) # carry out the command in the msg
        self.client.start()
        self.rr = rearrHandler.rearrange(AWG_channels) # opens AWG card via rearr class and initiates
        self.rr.awg.load(default_seq) # load basic data
        self.auto_plot = False # whether to automatically display the new sequence
        self.idle_state()

    def init_UI(self):
        """Create all of the widget objects to display on the interface."""
        self.centre_widget = QWidget()
        self.centre_widget.layout = QGridLayout()
        self.centre_widget.setLayout(self.centre_widget.layout)
        self.setCentralWidget(self.centre_widget)

        cmd_info = QLabel('Type the command into the line edit then press enter. Available commands:\n' + 
            'load=file_path    --- load segment metadata, steps, and parameters from the json file file_path.\n'+
            'save=file_path    --- save segment metadata, steps, and parameters to json in directory file_path.\n'+
            'set_data=[[...]]  --- set segment data: [channel, segment, parameter name, value].\n'+
            'set_step=[...]    --- set step data: [step, segment, # loops, next step, condition].\n'+
            'reset_tcp         --- check the TCP server and client status. If the server has stopped, then restart it.\n'+
            'send_trigger      --- manually send a TCP message to trigger DExTer.\n'+
            'auto_plot=0/1     --- if True, automatically plot the sequence when it\'s loaded.\n'+
            'start_awg         --- manually start the AWG.\n'+
            'stop_awg          --- manually stop the AWG.\n'+
            'reset_awg=[...]   --- create a new AWG instance with channels [ch1, ch2, ...] activated. \n'+
            '\n'+
            '~~~ Rearrangement Commands ~~~\n'+ 
            'rearr_on= config_path    --- activate rearrangment. To refresh rearrangement, do rearr_on again \n'+
            'rearr_off                --- deactivate rearrangment \n'+
            'rearrange=01110##..##    --- binary string triggers rearr step calculation'
            )
        self.centre_widget.layout.addWidget(cmd_info, 0,0, 1,1)
        self.status_label = QTextBrowser() #QLabel('Initiating...', self)
        self.centre_widget.layout.addWidget(self.status_label, 1,0, 1,1)
        # The user types the command into the line edit, then presses enter:
        self.edit = QLineEdit('', self)
        self.edit.returnPressed.connect(self.respond)
        self.centre_widget.layout.addWidget(self.edit, 2,0, 1,1)
        
    def idle_state(self):
        """When the master thread is not responding user events."""
        self.set_status('Idle.')

    def reset_tcp(self, force=False):
        """Check if the TCP threads are running. If not, reset them.""" 
        for tcp in [self.client, self.server]: # 
            if tcp.isRunning():
                if force:
                    tcp.close()
                    tcp.clear_queue()
                    time.sleep(0.1) # give time for it to close
                    tcp.start()
            else: 
                tcp.start()

    def set_status(self, txt):
        """Set the first 100 characters of a message returned to the
        TCP server."""
        self.status_label.append(time.strftime("%d/%m/%Y %H:%M:%S") + '>> \t ' + txt[:100])

    def respond(self, cmd=None):
        """Respond the command requested by the user. Command can also be
        sent by TCP message to the client."""
                    
        
        if cmd == None: 
            cmd = self.edit.text()
        else:
            pass
           # self.set_status('Received string = '+cmd.replace('#','').split('=')[1])  # print what occupancy string is received

        if 'load' in cmd and 'rload' not in cmd:
            self.set_status('Loading AWG data...')
            try:     
                path = cmd.split('=')[1].strip('file:///')
                if self.rr.rearrToggle == False:
                    self.rr.awg.load(path)    # NB load is defined differently in rearrHandler, depending if rearrToggle is true/false
                elif self.rr.rearrToggle == True:
                    self.rr.rearr_load(path)
                if self.auto_plot:
                    plot_playback(self.rr.awg.filedata)
                self.set_status('File loaded from '+path)
            except Exception as e:
                self.set_status('Failed to load AWG data from '+cmd.split('=')[1])
                logger.error('Failed to load AWG data from '+cmd.split('=')[1]+'\n'+str(e))
        elif 'save' in cmd:
            try: 
                path = cmd.split('=')[1]
                if self.rr.rearrToggle==False:
                    self.rr.awg.saveData(path)
                elif self.rr.rearrToggle == True: 
                    self.rr.rearr_saveData(path)
                    
                self.set_status('File saved to '+path)                    
            except Exception as e:
                logger.error('Failed to save AWG data to '+cmd.split('=')[1]+'\n'+str(e))
        elif 'reset_server' in cmd:
            self.reset_tcp()
            if self.server.isRunning(): status = 'Server running.'
            else: status = 'Server stopped.'
            if self.client.isRunning(): status = 'Client running.'
            else: status = 'Client stopped.'
            self.set_status(status)
        elif 'send_trigger' in cmd:
            # self.server.add_message(0, 'Trigger sent to DExTer.\n'+'0'*1600)
            self.set_status('Triggering DExTer not yet supported.')
        elif 'auto_plot' in cmd:
            try:
                self.auto_plot = eval(cmd.split('=')[1])
                plot_playback(self.rr.awg.filedata)
            except Exception as e: 
                logger.error('Failed to evaluate command:\t%s\n'%cmd + str(e))
        elif 'start_awg' in cmd:
            self.rr.awg.start()
            if spcm_dwGetParam_i32 (AWG.hCard, AWG.registers[3], byref(int32(0))) == 0:
                self.set_status('AWG started.')
            else:
                self.set_status('AWG crashed. Use the reset_awg coommand.')
                print(spcm_dwGetParam_i32 (AWG.hCard, AWG.registers[3], byref(int32(0))))
        elif 'stop_awg' in cmd:
            self.rr.awg.stop()
            self.set_status('AWG stopped.')
        elif 'set_data' in cmd:    
            self.set_status('Received string = '+cmd.replace('#','').split('=')[1])  # print what occupancy string is received

            #try:
            t = time.time()
            if self.rr.rearrToggle == False:
                self.rr.awg.loadSeg(eval(cmd.split('=')[1])) # NB loadSeg defined differently in rearrHandler if rearrToggle = true/false
            elif self.rr.rearrToggle == True:
                self.rr.rearr_loadSeg(eval(cmd.split('=')[1]))

            self.set_status('Set data: '+cmd.split('=')[1])
            self.t_load = time.time() - t
          #  except Exception as e:
            #logger.error('Failed to set AWG data: '+cmd.split('=')[1]+'\n'+str(e))
            self.server.add_message(1,'go'*1000)
        elif 'set_step' in cmd:  
            try:
                self.rr.awg.setStep(*eval(cmd.split('=')[1]))
                self.set_status('Set step: '+cmd.split('=')[1])
            except Exception as e:
                logger.error('Failed to set AWG step: '+cmd.split('=')[1]+'\n'+str(e))
        elif 'reset_awg' in cmd:
            self.renewAWG(cmd)
        # elif 'get_times' in cmd:
            logger.info("Data transfer time: %.4g s"%self.t_load)
        
        
        elif 'rearrange' in cmd:   # recevive occupancy string from Pydex
            if self.rr.rearrToggle==True:
                try:
                    self.rr.setRearrSeg(cmd.replace('#','').split('=')[1])
                #  self.set_status('Received string = '+cmd.replace('#','').split('=')[1])  # print what occupancy string is received
                except Exception as e:
                    logger.error('Failed to calculate steps: '+cmd.replace('#','').split('=')[1]+'\n'+str(e))
            elif self.rr.rearrToggle == False:
                pass   # If rearr mode is off, ignore rearr TCP strings from AWG

        elif 'rearr_on' in cmd:
         #   try:   
            self.renewAWG('chans=[0]')
            self.rr.awg.load(r'Z:\Tweezer\Code\Python 3.5\PyDex\awg\AWG template sequences\rearr_base.txt') # load basic data
            self.rr.activate_rearr(toggle=True)
            if '=' in cmd:  # if equals, then load in the specified rearragement config file.
                self.rr.rr_config = cmd.partition('=')[2].strip('file:///')
            self.set_status('Calculating moves...')
            self.rr.calculateAllMoves()
            self.set_status('Moves uploaded') 
            #self.rr.awg.start().
            if spcm_dwGetParam_i32 (AWG.hCard, AWG.registers[3], byref(int32(0))) == 0:
                self.set_status('AWG started.')
            else:
                self.set_status('AWG crashed. Use the reset_awg coommand.')
                print(spcm_dwGetParam_i32 (AWG.hCard, AWG.registers[3], byref(int32(0))))
                
           # except Exception as e:
           #     logger.error('Failed to calculate all rearrangement segments: '+cmd.split('=')[1]+'\n'+str(e))               
        
        elif 'rearr_off' in cmd:
            self.rr.activate_rearr(toggle=False)
            self.set_status('Rearrangement is now off.')
            if self.rr.OGfile is not None:
                self.rr.awg.load(self.rr.OGfile)
                self.set_status('Loaded: '+self.rr.OGfile)
        
        elif cmd.split('=')[0] == 'rload':    # required in order to overwrite the original file saved in rearrHandler.
            try:
                path = cmd.split('=')[1].strip('file:///')
                self.rr.OGfile = None
                self.rr.rearr_load(path)
            except Exception as e:
                self.set_status('Failed to load AWG data from '+cmd.split('=')[1])
                logger.error('Failed to load AWG data from '+cmd.split('=')[1]+'\n'+str(e))
            
        else:
            self.set_status('Command not recognised:\t %s'%cmd)
        self.edit.setText('') # reset cmd edit
       # self.set_status(cmd)
                        
    def renewAWG(self, cmd="chans=[0]"):
        try: 
            eval(cmd.split('=')[1])
        except Exception as e:
            self.set_status('Invalid renew command: '+cmd)
            logger.error('Could not renew AWG.\n'+str(e))
            return 0
        self.rr.awg.restart()
        self.rr.awg.newCard()
        self.rr.awg = None
        self.rr.awg = AWG(eval(cmd.split('=')[1]))#
        self.rr.awg.setNumSegments(8)
        # self.awg.setTrigger(0) # 0 software, 1 ext0
        self.rr.awg.setSegDur(0.002)
        self.set_status('New instance of AWG created.')
        
    def closeEvent(self, event):
        """Safely shut down when the user closes the window."""
        self.rr.awg.restart()
        self.client.close()
        self.server.close()
        event.accept()        

if __name__ == "__main__":
    app = QApplication.instance()
    standalone = app is None # false if there is already an app instance
    if standalone: # if there isn't an instance, make one
        app = QApplication(sys.argv) 

    boss = awg_window()
    boss.show()
    if standalone: # if an app instance was made, execute it
        sys.exit(app.exec_())