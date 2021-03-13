"""m4i.6622 AWG master script
Stefan Spence 27.06.20
 - Import functions and classes to control AWG
 - Give a simple interface for user control
 - Communicate with PyDex and DExTer via TCP
"""
import time
import os
os.chdir(os.path.dirname(os.path.realpath(__file__)))
os.system("color") # allows error/warning/info messages to print in colour
import sys
from collections import OrderedDict
from PyQt5.QtCore import QThread, pyqtSignal, QTimer
from PyQt5.QtGui import (QIcon, QDoubleValidator, QIntValidator, 
    QFont, QRegExpValidator)
from PyQt5.QtWidgets import (QApplication, QPushButton, QWidget, 
    QTabWidget, QAction, QMainWindow, QLabel, QInputDialog, QGridLayout,
    QMessageBox, QLineEdit, QFileDialog, QComboBox, QActionGroup, QMenu,
    QVBoxLayout, QTextBrowser)
if '.' not in sys.path: sys.path.append('.')
if '..' not in sys.path: sys.path.append('..')
from strtypes import error, warning, info
from awgHandler import AWG
from pyspcm import spcm_dwGetParam_i32, byref, int32
import fileWriter as fw
from networking.networker import PyServer, reset_slot
from networking.client import PyClient

####    ####    ####    ####

class awg_window(QMainWindow):
    """A basic GUI to take in commands from the user.
    
    Initiates the AWG and a TCP server and client for communication.
    Keyword arguments:
    config_file -- path to the file that saved the previous settings.
    """
    def __init__(self, config_file='.\\state', AWG_channels=[0,1], 
            default_seq=r'Z:\Tweezer\Code\Python 3.5\PyDex\awg\AWG template sequences\single_static.txt'):
        super().__init__()
        # self.types = OrderedDict([('FileName',str), ('segment',int)])
        self.stats = OrderedDict([('FileName', 0), ('segment', 0)])
        self.t_load = 0 # time taken to transfer data onto card
        self.init_UI()
        # self.server = PyServer(host='', port=8621) # TCP server to message DExTer
        # self.server.textin[str].connect(self.set_status) # display the returned msg
        # self.server.start()
        self.client = PyClient(host='129.234.190.164', port=8623) # TCP client to mess#age PyDex
        self.client.textin[str].connect(self.respond) # carry out the command in the msg
        self.client.start()
        self.awg = AWG(AWG_channels) # opens AWG card and initiates
        self.awg.load(default_seq) # load basic data
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
            'start_awg         --- manually start the AWG.\n'+
            'stop_awg          --- manually stop the AWG.\n'+
            'reset_awg=[...]   --- create a new AWG instance with channels [ch1, ch2, ...] activated.')
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
        for tcp in [self.client]: # , self.server
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
        if 'load' in cmd:
            self.set_status('Loading AWG data...')
            try: 
                path = cmd.split('=')[1]
                self.awg.load(path)
                self.set_status('File loaded from '+path)
            except Exception as e:
                self.set_status('Failed to load AWG data from '+cmd.split('=')[1])
                error('Failed to load AWG data from '+cmd.split('=')[1]+'\n'+str(e))
        elif 'save' in cmd:
            try: 
                path = cmd.split('=')[1]
                self.awg.saveData(path)
                self.set_status('File saved to '+path)
            except Exception as e:
                error('Failed to save AWG data to '+cmd.split('=')[1]+'\n'+str(e))
        elif 'reset_server' in cmd:
            self.reset_tcp()
            # if self.server.isRunning(): status = 'Server running.'
            # else: status = 'Server stopped.'
            if self.client.isRunning(): status += 'Client running.'
            else: status = 'Client stopped.'
            self.set_status(status)
        elif 'send_trigger' in cmd:
            # self.server.add_message(0, 'Trigger sent to DExTer.\n'+'0'*1600)
            self.status('Triggering DExTer not yet supported.')
        elif 'start_awg' in cmd:
            self.awg.start()
            if spcm_dwGetParam_i32 (AWG.hCard, AWG.registers[3], byref(int32(0))) == 0:
                self.set_status('AWG started.')
            else:
                self.set_status('AWG crashed. Use the reset_awg coommand.')
        elif 'stop_awg' in cmd:
            self.awg.stop()
            self.set_status('AWG stopped.')
        elif 'set_data' in cmd:
            try:
                t = time.time()
                self.awg.loadSeg(eval(cmd.split('=')[1]))
                self.set_status('Set data: '+cmd.split('=')[1])
                self.t_load = time.time() - t
            except Exception as e:
                error('Failed to set AWG data: '+cmd.split('=')[1]+'\n'+str(e))
        elif 'set_step' in cmd:
            try:
                self.awg.setStep(*eval(cmd.split('=')[1]))
                self.set_status('Set step: '+cmd.split('=')[1])
            except Exception as e:
                error('Failed to set AWG step: '+cmd.split('=')[1]+'\n'+str(e))
        elif 'reset_awg' in cmd:
            self.renewAWG(cmd)
        elif 'get_times' in cmd:
            info("Data transfer time: %.4g s"%self.t_load)
        else:
            self.set_status('Command not recognised.')
        self.edit.setText('') # reset cmd edit
                        
    def renewAWG(self, cmd="chans=[0,1]"):
        try: 
            eval(cmd.split('=')[1])
        except Exception as e:
            self.set_status('Invalid renew command: '+cmd)
            error('Could not renew AWG.\n'+str(e))
            return 0
        self.awg.restart()
        self.awg.newCard()
        self.awg = None
        self.awg = AWG(eval(cmd.split('=')[1]))#
        self.awg.setNumSegments(8)
        # self.awg.setTrigger(0) # 0 software, 1 ext0
        self.awg.setSegDur(0.002)
        self.set_status('New instance of AWG created.')
        
    def closeEvent(self, event):
        """Safely shut down when the user closes the window."""
        self.awg.restart()
        self.client.close()
        # self.server.close()
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