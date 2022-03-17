"""PyDex - Experimental Control
Stefan Spence 30/08/19

 - A managing script to control separate modules of an experiment:
    creating experimental sequences, queueing a multi-run of
    sequences, controlling an Andor camera to take images, 
    saving images and synchronising with the sequence,
    analysing images, monitoring channels throughout several
    sequence, and displaying results.
"""
import os
os.system("color") # allows error/warning/info messages to print in colour
import sys
import time
import copy
import numpy as np
from collections import OrderedDict
from PyQt5.QtCore import QThread, pyqtSignal, QEvent, QRegExp, QTimer
from PyQt5.QtGui import (QIcon, QDoubleValidator, QIntValidator, 
        QFont, QRegExpValidator)
from PyQt5.QtWidgets import (QApplication, QPushButton, QWidget, 
        QTabWidget, QAction, QMainWindow, QLabel, QInputDialog, QGridLayout,
        QMessageBox, QLineEdit, QFileDialog, QComboBox, QActionGroup, QMenu,
        QVBoxLayout, QShortcut)
# change directory to this file's location
os.chdir(os.path.dirname(os.path.realpath(__file__)))
import warnings
warnings.filterwarnings('ignore') # not interested in RuntimeWarning from mean of empty slice
sys.path.append('./imageanalysis')
from imageanalysis.settingsgui import settings_window
from imageanalysis.atomChecker2 import atom_window
sys.path.append('./andorcamera')
from andorcamera.cameraHandler import camera # manages Andor camera
sys.path.append('./saveimages')
from saveimages.imsaver import event_handler # saves images
sys.path.append('./networking')
from networking.runid import runnum # synchronises run number, sends signals
from networking.networker import TCPENUM, reset_slot # enum for DExTer produce-consumer loop cases
sys.path.append('./sequences')
from sequences.sequencePreviewer import Previewer
sys.path.append('./dds')
from dds.DDScoms import DDSComWindow
from strtypes import intstrlist, error, warning, info

####    ####    ####    ####

class MonitorStatus(QMainWindow):
    """A window to display the status of the separate monitor program.
    Communications are carried out over TCP."""
    def __init__(self):
        super().__init__()
        self.connected = False # Whether connection with monitor has been confirmed
        self.i = 5 # index for checking connection
        self.centre_widget = QWidget()
        layout = QGridLayout()
        self.centre_widget.setLayout(layout)
        self.setCentralWidget(self.centre_widget)

        self.status = QLabel('Unconfirmed.') # show current status
        layout.addWidget(self.status, 0,0, 1,2)
        
        self.start_button = QPushButton('Start', self, checkable=False)
        layout.addWidget(self.start_button, 1,0, 1,1)
        
        self.stop_button = QPushButton('Stop', self, checkable=False)
        layout.addWidget(self.stop_button, 1,1, 1,1)
        
        self.setWindowTitle('- Check Monitor Connection -')
        self.setWindowIcon(QIcon('docs/daqicon.png'))
        
    def set_label(self, text):
        self.status.setText('Message at ' + time.strftime('%H:%M') +': '+ text)
        
    def set_connected(self, text=''):
        self.connected = True
        
    def start_check(self, n=5):
        """Check whether a TCP message has been received from the monitor.
        n -- number of seconds to wait before assuming the connection is broken."""
        self.i = n
        QTimer.singleShot(1e3, self.check_connected) 
        
    def check_connected(self):
        if not self.connected and self.i:
            self.status.setText('Waiting for response. %s seconds remaining.'%self.i)
            self.i -= 1
            QTimer.singleShot(1e3, self.check_connected) 
        elif self.i == 0:
            self.status.setText('Lost TCP connection with monitor.')
        elif self.connected and 'Waiting' in self.status.text():
            self.status.setText('Connection confirmed.')

####    ####    ####    ####

class Master(QMainWindow):
    """A manager to synchronise and control experiment modules.
    
    Initiates the Andor camera and connects its completed acquisition
    signal to the image analysis and the image saving modules.
    Uses the queue module to create the list of sequences to run,
    and the bridge module to communicate with Dexter.
    This master module will define the run number. It must confirm that
    each Dexter sequence has run successfully in order to stay synchronised.
    Keyword arguments:
    state_config -- path to the file that saved the previous state.
                    Default directories for camera settings and image 
                    saving are also saved in this file.
    image_analysis -- a class inheriting QMainWindow that can perform all of the
                    required image analysis methods
    """
    def __init__(self, state_config='.\\state', image_analysis=settings_window):
        super().__init__()
        self.types = OrderedDict([('File#',int), ('Date',str), ('CameraConfig',str), 
            ('SaveConfig',str), ('AnalysisConfig',eval), ('MasterGeometry',intstrlist), 
            ('AtomCheckerROIs', eval), ('AnalysisGeometry',intstrlist), 
            ('SequencesGeometry',intstrlist), ('TempXMLPath', str)])
        self.stats = OrderedDict([('File#', 0), ('Date', time.strftime("%d,%B,%Y")), 
            ('CameraConfig', '.\\andorcamera\\Standard modes\\ExExposure_config.dat'), 
            ('SaveConfig', '.\\config\\config.dat'), ('AnalysisConfig', {'pic_width':512,
                'pic_height':512,'ROIs':'[[1, 1, 1, 1, 1], [1, 1, 1, 1, 1]]','bias':697,'image_path':'.',
                'results_path':'.','last_image':'.','window_pos':'[550, 20, 10, 200, 600, 400]','num_images':2,
                'num_saia':4,'num_reim':1,'num_coim':0}), 
            ('AtomCheckerROIs',[[1, 1, 1, 1, 1], [1, 1, 1, 1, 1]]),
            ('MasterGeometry', [10, 10, 500, 150]), ('AnalysisGeometry', [1400, 400, 600, 500]), 
            ('SequencesGeometry', [20, 100, 1000, 800]), 
            ('TempXMLPath', r'X:\\Sequence Log\\temp.xml')])
        self.camera_pause = 0 # time in seconds to wait for camera to start acquisition.
        self.ts = {label:time.time() for label in ['init', 'waiting', 'blocking',
            'msg start', 'msg end']}
        sv_dirs = event_handler.get_dirs(self.stats['SaveConfig'])
        # if not any(os.path.exists(svd) for svd in sv_dirs.values()): # ask user to choose valid config file
        startn = self.restore_state(file_name=state_config)
        # choose which image analyser to use from number images in sequence
        self.init_UI(startn)
        # initialise the thread controlling run # and emitting images
        CsROIs, RbROIs = self.get_atomchecker_rois()
        self.rn = runnum(camera(config_file=self.stats['CameraConfig']), # Andor camera
                event_handler(self.stats['SaveConfig']), # image saver
                image_analysis(results_path =sv_dirs['Results Path: '],
                    im_store_path=sv_dirs['Image Storage Path: '],
                    config_settings=self.stats['AnalysisConfig']), # image analysis
                atom_window(last_im_path=sv_dirs['Image Storage Path: '],
                    Cs_rois=CsROIs, Rb_rois=RbROIs), # check if atoms are in ROIs to trigger experiment
                Previewer(), # sequence editor
                n=startn, m=2, k=0) 
        # now the signals are connected, send camera settings to image analysis
        if self.rn.cam.initialised > 2:
            check = self.rn.cam.ApplySettingsFromConfig(self.stats['CameraConfig'])
        
        self.rn.server.dxnum.connect(self.Dx_label.setText) # synchronise run number
        self.rn.server.textin.connect(self.respond) # read TCP messages
        self.status_label.setText('Initialising...')
        QTimer.singleShot(0, self.idle_state) # takes a while for other windows to load
        
        # self.rn.check.showMaximized()
        self.rn.seq.setGeometry(*self.stats['SequencesGeometry'])
        self.rn.seq.show()
        self.rn.sw.setGeometry(*self.stats['AnalysisGeometry'])
        self.rn.sw.show()
        self.rn.sw.show_analyses(show_all=True)
        
        self.mon_win = MonitorStatus() # display communication with DAQ monitor
        self.mon_win.start_button.clicked.connect(self.start_monitor)
        self.mon_win.stop_button.clicked.connect(self.stop_monitor)
        self.rn.monitor.textin[str].connect(self.mon_win.set_label)
        self.rn.monitor.textin.connect(self.mon_win.set_connected)
        self.dds_win = DDSComWindow() # display communication with DDS
        self.dds_win.msg[str].connect(lambda msg: self.rn.ddstcp1.add_message(self.rn._n, msg))
        self.rn.ddstcp1.textin[str].connect(lambda msg: self.dds_win.set_status(' received >> '+msg))
        # set a timer to update the dates at 5am:
        t0 = time.localtime()
        self.date_reset = 0 # whether the dates are waiting to be reset or not
        QTimer.singleShot((29*3600 - 3600*t0[3] - 60*t0[4] - t0[5])*1e3, 
            self.reset_dates)
            

    def idle_state(self):
        """When the master thread is not processing user events, it is in the idle states.
        The status label is also used as an indicator for DExTer's current state."""
        self.status_label.setText('Idle')

    def restore_state(self, file_name=''):
        """Use the data stored in the given file to restore the file # for
        synchronisation if it is the same day, and use the same config files."""
        if not file_name:
            try:
                file_name, _ = QFileDialog.getOpenFileName(self, 'Load the PyDex Master State', '', 'all (*)')
            except OSError: return 0
        try:
            with open(file_name, 'r') as f:
                for line in f:
                    if len(line.split('=')) == 2: # there should only be one = per line
                        key, val = line.replace('\n','').split('=') 
                        try:
                            self.stats[key] = self.types[key](val)
                        except KeyError as e:
                            warning('Failed to load PyDex state line: '+line+'\n'+str(e))
        except FileNotFoundError as e: 
            warning('PyDex master settings could not find the state file.\n'+str(e))
        d = self.stats['Date']
        self.apply_state()
        if d == time.strftime("%d,%B,%Y"): # restore file number
            return self.stats['File#'] # [Py]DExTer file number
        else: return 0
        
    def get_atomchecker_rois(self):
        """Compatability with old states which didn't have Rb and Cs ROIs for atomChecker"""
        try: 
            CsROIs, RbROIs = self.stats['AtomCheckerROIs']
        except ValueError as e: 
            error("Couldn't load atomChecker ROIs: \n"+str(self.stats['AtomCheckerROIs'])+'\n'+str(e))
            CsROIs, RbROIs  = [[1,1,1,1,1]],  [[1,1,1,1,1]]
        return CsROIs, RbROIs

    def apply_state(self):
        """Reset the date, camera config, image analysis config, and geometries"""
        try:
            self.reset_dates(savestate=False) # date
            self.rn.sv.reset_dates(self.stats['SaveConfig']) # image saver
            sv_dirs = self.rn.sv.get_dirs(self.stats['SaveConfig'])
            self.stats['AnalysisConfig']['results_path'] = sv_dirs['Results Path: ']
            self.stats['AnalysisConfig']['image_path'] = sv_dirs['Image Storage Path: ']
            self.rn.sw.load_settings(stats=self.stats['AnalysisConfig'])
            CsROIs, RbROIs = self.get_atomchecker_rois()
            self.rn.check.set_rois(CsROIs, 'Cs')
            self.rn.check.set_rois(RbROIs, 'Rb')
            self.rn.sw.reset_analyses()
            if self.rn.cam.initialised > 2: # camera
                if self.rn.cam.AF.GetStatus() == 'DRV_ACQUIRING':
                    self.rn.cam.AF.AbortAcquisition()
                check = self.rn.cam.ApplySettingsFromConfig(self.stats['CameraConfig'])
                if not any(check):
                    self.status_label.setText('Camera settings config: '+self.stats['CameraConfig'])
                else:
                    self.status_label.setText('Failed to update camera settings.')
            else: self.reset_camera(self.stats['CameraConfig'])
        except AttributeError: pass # haven't made runid yet 
        except Exception as e: print('Master could not set state:\n'+str(e))
            
        
    def make_label_edit(self, label_text, layout, position=[0,0, 1,1],
            default_text='', validator=False):
        """Make a QLabel with an accompanying QLineEdit and add them to the 
        given layout with an input validator. The position argument should
        be [row number, column number, row width, column width]."""
        label = QLabel(label_text, self)
        layout.addWidget(label, *position)
        line_edit = QLineEdit(self)
        if np.size(position) == 4:
            position[1] += 1
        layout.addWidget(line_edit, *position)
        line_edit.setText(default_text) 
        if validator:
            line_edit.setValidator(validator)
        return label, line_edit
        
    def init_UI(self, startn=0):
        """Create all of the widget objects required
        startn: the initial run number loaded from previous state"""
        self.centre_widget = QWidget()
        self.centre_widget.layout = QGridLayout()
        self.centre_widget.setLayout(self.centre_widget.layout)
        self.setCentralWidget(self.centre_widget)
        
        #### menubar at top gives options ####
        menubar = self.menuBar()

        state_menu = menubar.addMenu('Config')
        load_state = QAction('Load state', state_menu, checkable=False)
        load_state.triggered.connect(self.restore_state)
        state_menu.addAction(load_state)
        save_state = QAction('Save state', state_menu, checkable=False)
        save_state.triggered.connect(self.save_state)
        state_menu.addAction(save_state)

        show_windows = menubar.addMenu('Windows')
        menu_items = []
        for window_title in ['Image Analyser', 'Camera Status', 
            'Image Saver', 'TCP Server', 'Multirun',
            'Atom Checker', 'Monitor', 'DDS', 'Show all']:
            menu_items.append(QAction(window_title, self)) 
            menu_items[-1].triggered.connect(self.show_window)
            show_windows.addAction(menu_items[-1])

        sync_menu = menubar.addMenu('Run Settings')
        self.sync_toggle = QAction('Sync with DExTer', sync_menu, 
                checkable=True, checked=True)
        self.sync_toggle.setChecked(True)
        self.sync_toggle.toggled.connect(self.sync_mode)
        sync_menu.addAction(self.sync_toggle)

        self.send_data = QAction('Send data to influxdb', sync_menu, 
            checkable=True, checked=False)
        self.send_data.toggled[bool].connect(self.set_inflxdb_toggle)
        sync_menu.addAction(self.send_data)

        self.check_rois = QAction('Trigger on atoms loaded', sync_menu, 
                checkable=True, checked=False)
        self.check_rois.setChecked(False)
        # self.check_rois.setEnabled(False) # not functional yet
        sync_menu.addAction(self.check_rois) 

        self.rearr_rois = QAction('Rearrange ROIs', sync_menu, 
                checkable=True, checked=False)
        self.rearr_rois.setChecked(False)
        self.rearr_rois.toggled[bool].connect(self.set_rearranging)
        sync_menu.addAction(self.rearr_rois) 

        reset_date = QAction('Reset date', sync_menu, checkable=False)
        reset_date.triggered.connect(self.reset_dates)
        sync_menu.addAction(reset_date)

        check_sizes = QAction('Print stored data size', sync_menu, checkable=False)
        check_sizes.triggered.connect(self.check_sizes)
        sync_menu.addAction(check_sizes)
        
        #### status of the master program ####
        self.status_label = QLabel('Initiating...', self)
        self.centre_widget.layout.addWidget(self.status_label, 0,0, 1,3)
        
        Dx_label = QLabel('Run #: ', self)
        self.centre_widget.layout.addWidget(Dx_label, 1,0, 1,1)
        self.Dx_label = QLabel(str(startn), self)
        self.centre_widget.layout.addWidget(self.Dx_label, 1,1, 1,1)

        # actions that can be carried out 
        self.actions = QComboBox(self)
        self.actions.addItems(['Run sequence (F2)', 'Multirun run (F3)', 'Pause multirun (F4)', 
            'Resume multirun (F5)', 'Cancel multirun (Esc)', 'Skip multirun histogram (F6)', 
            'Send sequence to DExTer (F7)','Get sequence from DExTer (F8)',
            'Get sequence from BareDExTer',
            'Save DExTer sequence', 'End Python Mode', 
            'Resync DExTer', 'Start acquisition'])
        self.actions.resize(self.actions.sizeHint())
        self.centre_widget.layout.addWidget(self.actions, 2,0,1,1)
        
        # shortcuts
        self.shortcuts=[QShortcut('F2', self)]
        self.shortcuts[0].activated.connect(lambda: self.start_action('Run sequence'))
        self.shortcuts.append(QShortcut('F3', self))
        self.shortcuts[1].activated.connect(lambda: self.start_action('Multirun run'))
        self.shortcuts.append(QShortcut('F4', self))
        self.shortcuts[2].activated.connect(lambda: self.start_action('Pause multirun'))
        self.shortcuts.append(QShortcut('F5', self))
        self.shortcuts[3].activated.connect(lambda: self.start_action('Resume multirun'))
        self.shortcuts.append(QShortcut('Esc', self))
        self.shortcuts[4].activated.connect(lambda: self.start_action('Cancel multirun'))
        self.shortcuts.append(QShortcut('F6', self))
        self.shortcuts[5].activated.connect(lambda: self.start_action('Skip multirun histogram'))
        self.shortcuts.append(QShortcut('F7', self))
        self.shortcuts[6].activated.connect(lambda: self.start_action('Send sequence to DExTer'))
        self.shortcuts.append(QShortcut('F8', self))
        self.shortcuts[7].activated.connect(lambda: self.start_action('Get sequence from DExTer'))
        

        self.action_button = QPushButton('Go (F10)', self, checkable=False)
        self.action_button.setShortcut('F10')
        self.action_button.clicked.connect(self.start_action)
        self.action_button.resize(self.action_button.sizeHint())
        self.centre_widget.layout.addWidget(self.action_button, 2,1, 1,1)

        #### choose main window position, dimensions: (xpos,ypos,width,height)
        self.setGeometry(*self.stats['MasterGeometry'])
        self.setWindowTitle('PyDex Master')
        self.setWindowIcon(QIcon('docs/pydexicon.png'))

    def reset_dates(self, auto=True, savestate=True):
        """Reset the date in the image saving and analysis, 
        then display the updated date. Don't reset during multirun."""
        if not self.rn.seq.mr.multirun:
            self.date_reset = 0 # whether the dates are waiting to be reset or not
            t0 = time.localtime()
            self.stats['Date'] = time.strftime("%d,%B,%Y", t0)
            date = self.rn.reset_dates(t0)
            if not hasattr(self.sender(), 'text'): # don't set timer if user pushed button
                QTimer.singleShot((29*3600 - 3600*t0[3] - 60*t0[4] - t0[5])*1e3, 
                    self.reset_dates) # set the next timer to reset dates
            info(time.strftime("Date reset: %d %B %Y", t0))
            results_path = os.path.join(self.stats['AnalysisConfig']['results_path'], *time.strftime('%Y,%B,%d').split(','))
            os.makedirs(results_path, exist_ok=True)
            if savestate: self.save_state(os.path.join(results_path, 'PyDexState'+time.strftime("%d%b%y")+'.txt'))
        else:
            self.date_reset = 1 # whether the dates are waiting to be reset or not

    def show_window(self):
        """Show the window of the submodule or adjust its settings."""
        if self.sender().text() == 'Image Analyser':
            self.rn.sw.show()

        elif self.sender().text() == 'Camera Status':
            if self.rn.cam.initialised:
                msg = 'Current state: ' + self.rn.cam.AF.GetStatus() + '\nChoose a new config file: '
            else: msg = 'Camera not initialised. See log file for details. Press OK to retry.'
            newfile = self.rn.sw.try_browse(title='Choose new config file', 
                    file_type='config (*.dat);;all (*)', 
                    defaultpath=os.path.dirname(self.stats['CameraConfig']))
            text, ok = QInputDialog.getText( self, 'Camera Status', msg, 
                    text=newfile if newfile else self.stats['CameraConfig'])
            if text and ok:
                if self.rn.cam.initialised > 2:
                    if self.rn.cam.AF.GetStatus() == 'DRV_ACQUIRING':
                        self.rn.cam.AF.AbortAcquisition()
                    check = self.rn.cam.ApplySettingsFromConfig(text)
                    if not any(check):
                        self.status_label.setText('Camera settings config: '+text)
                        self.stats['CameraConfig'] = text
                    else:
                        self.status_label.setText('Failed to update camera settings.')
                else: self.reset_camera(text)
                    
        elif self.sender().text() == 'Image Saver':
            text, ok = QInputDialog.getText( 
                self, 'Image Saver',
                self.rn.sv.print_dirs(self.rn.sv.dirs_dict.items()) + 
        '\nEnter the path to a config file to reset the image saver: ',
        text=self.stats['SaveConfig'])
            if text and ok:
                reset_slot(self.rn.im_save, self.rn.sv.add_item, False)
                self.rn.sv = event_handler(text)
                if self.rn.sv.image_storage_path:
                    self.status_label.setText('Image Saver config: '+text)
                    reset_slot(self.rn.im_save, self.rn.sv.add_item, True)
                    self.stats['SaveConfig'] = text
                else:
                    self.status_label.setText('Failed to find config file.')

        elif self.sender().text() == 'Multirun':
            self.rn.seq.show()
        elif self.sender().text() == 'TCP Server':
            info = 'Trigger server is running.\n' if self.rn.trigger.isRunning() else 'Trigger server stopped.\n'
            info += 'Monitor server is running.\n' if self.rn.monitor.isRunning() else 'Monitor server stopped.\n'
            info += 'AWG1 server is running.\n' if self.rn.awgtcp1.isRunning() else 'AWG1 server stopped.\n'
            info += 'AWG2 server is running.\n' if self.rn.awgtcp2.isRunning() else 'AWG2 server stopped.\n'
            info += 'DDS1 server is running.\n' if self.rn.ddstcp1.isRunning() else 'DDS1 server stopped.\n'
            info += 'DDS2 server is running.\n' if self.rn.ddstcp2.isRunning() else 'DDS2 server stopped.\n'
            info += 'SLM server is running.\n' if self.rn.slmtcp.isRunning() else 'SLM server stopped.\n'
            info += 'MWG server is running.\n' if self.rn.mwgtcp.isRunning() else 'MWG server stopped.\n'
            info += 'BareDExTer server is running.\n' if self.rn.seqtcp.isRunning() else 'BareDExTer server stopped.\n'
            if self.rn.server.isRunning():
                msgs = self.rn.server.get_queue()
                info += "TCP server is running. %s queued message(s)."%len(msgs)
                info += '\nCommand Enum | Length |\t Message\n'
                for enum, text in msgs[:5]:
                    textlength = len(text)
                    info += enum + ' | ' + text[:20]
                    if textlength > 20:  info += '...'
                    info += '\n'
                if len(msgs) > 5:
                    info += '...\n'
            else:
                info += "TCP server stopped."
            reply = QMessageBox.question(self, 'TCP Server Status', 
                info+"\nDo you want to restart the server?", 
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if reply == QMessageBox.Yes:
                self.action_button.setEnabled(True)
                self.rn.seq.mr.mr_queue.clear()
                self.rn.seq.mr.multirun = False
                self.rn.reset_server(force=True) # stop and then restart the servers
                self.rn.server.add_message(TCPENUM['TCP read'], 'Sync DExTer run number\n'+'0'*2000) 
            elif reply == QMessageBox.No:
                self.rn.reset_server(force=False) # restart the server if it stopped
        elif self.sender().text() == 'Atom Checker':
            self.rn.check.showMaximized()
        elif self.sender().text() == 'Monitor':
            self.mon_win.show()
        elif self.sender().text() == 'DDS':
            self.dds_win.show()
        elif self.sender().text() == 'Show all':
            for obj in [self.mon_win, self.rn.sw, self.rn.seq] + self.rn.sw.mw + self.rn.sw.rw:
                obj.close()
                obj.show()
            
    def start_monitor(self, toggle=True):
        """Send a TCP command to the monitor to start its acquisition."""
        self.mon_win.start_check()
        self.rn.monitor.add_message(self.rn._n, 'start')
        
    def stop_monitor(self, toggle=True):
        """Send a TCP command to the monitor to stop its acquisition."""
        self.mon_win.start_check()
        self.rn.monitor.add_message(self.rn._n, 'stop')

    def set_rearranging(self, toggle=False):
        """In rearranging mode, the first image is sent to the atom checker"""
        self.rn.rearranging = toggle
        reset_slot(self.rn.check.rh['Cs'].rearrange, self.rn.send_rearr_msg, toggle)
        reset_slot(self.rn.check.rh['Rb'].rearrange, self.rn.send_rearr2_msg, toggle)
        self.rn.set_m(self.rn.sw._m)

    def browse_sequence(self, toggle=True):
        """Open the file browser to search for a sequence file, then insert
        the file path into the DExTer sequence file line edit
        start_dir: the directory to open initially."""
        try:
            if 'PyQt4' in sys.modules:
                file_name = QFileDialog.getOpenFileName(
                    self, 'Select A Sequence', '', 'Sequence (*.xml);;all (*)')
            elif 'PyQt5' in sys.modules:
                file_name, _ = QFileDialog.getOpenFileName(
                    self, 'Select A Sequence', '', 'Sequence (*.xml);;all (*)')
            if file_name:
                self.seq_edit.setText(file_name.replace('/','\\'))
                self.rn.seq.load_seq_from_file(file_name)
        except OSError:
            pass # user cancelled - file not found


    def reset_camera(self, ancam_config='./andorcamera/ExExposure_config.dat'):
        """Close the camera and then start it up again with the new setting.
        Sometimes after being in crop mode the camera fails to reset the 
        ROI and so must be closed and restarted."""
        try:
            self.rn.cam.SafeShutdown()
        except: warning('Andor camera safe shutdown failed') # probably not initialised
        self.rn.cam = camera(config_file=ancam_config) # Andor camera
        reset_slot(self.rn.cam.AcquireEnd, self.rn.receive, True) # connect signal
        self.status_label.setText('Camera settings config: '+ancam_config)
        self.stats['CameraConfig'] = ancam_config

    def start_action(self, action_text=''):
        """Perform the action currently selected in the actions combobox.
        Run sequence:   Start the camera acquisition, then make 
                        DExTer perform a single run of the 
                        sequence that is currently loaded.
        Multirun run:   Start the camera acquisition, then make 
                        DExTer perform a multirun with the preloaded
                        multirun settings.
        Send sequence to DExTer: Tell DExTer to load in the sequence
                        from a string in XML format.
        End Python Mode: send the text 'python mode off' which triggers
                        DExTer to exit python mode.
        Resync DExTer:  send a null message just to resync the run number.
        Start acquisition:  start the camera acquiring without telling
                        DExTer to run. Used in unsynced mode."""
        if not action_text: action_text = self.actions.currentText()
        if action_text == 'Start acquisition' and self.action_button.text() == 'Go':
            if self.rn.cam.initialised > 2:
                if self.sync_toggle.isChecked():
                    QMessageBox.warning(self, 'Unscyned acquisition', 
                        'Warning: started acquisition in synced mode. Without messages to DExTer, the file ID will not update.'+
                        '\nTry unchecking: "Run Settings" > "Sync with DExTer".')
                self.actions.setEnabled(False) # don't process other actions in this mode
                self.rn._k = 0 # reset image per run count
                self.action_button.setText('Stop acquisition')
                self.rn.cam.start() # start acquisition
                self.wait_for_cam() # wait for camera to initialise before running
                self.status_label.setText('Camera acquiring')
            else: warning('Master: Tried to start camera acquisition but camera is not initialised.')
        elif action_text == 'Start acquisition' and self.action_button.text() == 'Stop acquisition':
            self.actions.setEnabled(True)
            self.action_button.setText('Go')
            self.end_run()

        if self.rn.server.isRunning():
            if 'Run sequence' in action_text:
                # queue up messages: start acquisition, check run number
                self.action_button.setEnabled(False) # only process 1 run at a time
                self.rn._k = 0 # reset image per run count 
                self.rn.server.add_message(TCPENUM['TCP read'], 'start acquisition\n'+'0'*2000) 
                self.rn.monitor.add_message(self.rn._n, 'update run number')
            elif 'Multirun run' in action_text:
                if self.rn.seq.mr.check_table():
                    if not self.sync_toggle.isChecked():
                        self.sync_toggle.setChecked(True) # it's better to multirun in synced mode
                        warning('Multirun has changed the "sync with DExTer" setting.')
                    status = self.rn.seq.mr.check_mr_params(self.rn.sv.results_path) # add to queue if valid
                    self.check_mr_queue() # prevent multiple multiruns occurring simultaneously
                    if self.rn.seq.mr.QueueWindow.isVisible():
                        self.rn.seq.mr.queue_ui.updateList()
                else: 
                    QMessageBox.warning(self, 'Invalid multirun', 
                        'All cells in the multirun table must be populated with float values.')
            elif 'Resume multirun' in action_text:
                self.rn.multirun_resume(self.status_label.text())
                if self.rn.cam.initialised:
                    self.rn.cam.start() # start acquisition
                    self.wait_for_cam() # wait for camera to initialise before running
                else: 
                    warning('Run %s started without camera acquisition.'%(self.rn._n))
            elif 'Pause multirun' in action_text:
                if self.rn.seq.mr.multirun:
                    self.rn.multirun_go(False, stillrunning=True)
            elif 'Cancel multirun' in action_text:
                if self.rn.seq.mr.multirun:
                    if self.rn.check.checking:
                        self.rn.check.rh['Cs'].trigger.emit(1) # send software trigger to end
                    self.rn.multirun_go(False)
                    self.rn.seq.mr.ind = 0
                    self.rn.seq.mr.reset_sequence(self.rn.seq.tr.copy())
            elif 'Skip multirun histogram' in action_text:
                if self.rn.seq.mr.multirun:
                    self.rn.skip_mr_hist()
            elif 'Send sequence to DExTer' in action_text:
                self.rn.server.add_message(TCPENUM['TCP load sequence from string'], self.rn.seq.tr.seq_txt)
                self.rn.seqtcp.add_message(TCPENUM['TCP load sequence from string'], self.rn.seq.tr.seq_txt)
            elif 'Get sequence from DExTer' in action_text:
                self.rn.server.add_message(TCPENUM['TCP read'], 'send sequence xml\n'+'0'*2000) # Dx adds sequence to msg queue
                for i in range(5):
                    self.rn.server.add_message(TCPENUM['TCP read'], 'replaced with sequence\n') # needs some time to get msg
                # also send this sequence to BareDExTer
                QTimer.singleShot(0.5, lambda:self.rn.seqtcp.add_message(TCPENUM['TCP load sequence from string'], self.rn.seq.tr.seq_txt))
            elif 'Get sequence from BareDExTer' in action_text:
                self.rn.seqtcp.add_message(TCPENUM['TCP read'], 'send sequence xml\n'+'0'*2000) # Dx adds sequence to msg queue
                for i in range(5):
                    self.rn.seqtcp.add_message(TCPENUM['TCP read'], 'replaced with sequence\n') # needs some time to get msg
            elif 'Save DExTer sequence' in action_text:
                self.rn.server.add_message(TCPENUM['Save sequence'], 'save log file automatic name\n'+'0'*2000)
            elif 'End Python Mode' in action_text:
                self.rn.server.add_message(TCPENUM['TCP read'], 'python mode off\n'+'0'*2000)
                self.rn.server.add_message(TCPENUM['TCP read'], 'Resync DExTer\n'+'0'*2000) # for when it reconnects
            elif 'Resync DExTer' in action_text:
                self.rn.server.add_message(TCPENUM['TCP read'], 'Resync DExTer\n'+'0'*2000)

    def trigger_exp_start(self, n=None):
        """Atom checker sends signal saying all ROIs have atoms in, start the experiment"""
        self.rn.check.timer.stop() # in case the timer was going to trigger the experiment as well
        reset_slot(self.rn.trigger.dxnum, self.reset_cam_signals, True) # swap signals when msg confirmed
        self.rn.trigger.add_message(TCPENUM['TCP read'], 'Go!'*600) # trigger experiment
        # QTimer.singleShot(20, self.resend_exp_trigger) # wait in ms
        
    def resend_exp_trigger(self, wait=20):
        """DExTer doesn't always receive the first trigger, send another.
        wait -- time in ms before checking if the message was received."""
        if self.rn.check.checking:
            self.rn.trigger.add_message(TCPENUM['TCP read'], 'Go!'*600) # in case the first fails
            QTimer.singleShot(wait, self.resend_exp_trigger) # wait in ms
        
    def reset_cam_signals(self, toggle=True):
        """Stop sending images to the atom checker, send them to image analysis instead"""
        self.rn.check.checking = False
        reset_slot(self.rn.cam.AcquireEnd, self.rn.receive, not self.rn.seq.mr.multirun) # send images to analysis
        reset_slot(self.rn.cam.AcquireEnd, self.rn.mr_receive, self.rn.seq.mr.multirun)
        reset_slot(self.rn.cam.AcquireEnd, self.rn.check_receive, False)
        reset_slot(self.rn.trigger.dxnum, self.reset_cam_signals, False) # only trigger once
        self.rn.trigger.add_message(TCPENUM['TCP read'], 'Go!'*600) # flush TCP
            
    def sync_mode(self, toggle=True):
        """Toggle whether to receive the run number from DExTer,
        or whether to increment the run number every time the expected
        number of images per sequence is received."""
        reset_slot(self.rn.cam.AcquireEnd, self.rn.receive, toggle) 
        reset_slot(self.rn.cam.AcquireEnd, self.rn.unsync_receive, not toggle)

    def set_inflxdb_toggle(self, toggle=False):
        """Whether to send data to influxdb database"""
        self.rn.sw.send_data = toggle
                
    def wait_for_cam(self, timeout=10):
        """Wait (timeout / 10) ms, periodically checking whether the camera
        has started acquiring yet."""
        for i in range(int(timeout)):
            if self.rn.cam.AF.GetStatus() == 'DRV_ACQUIRING':
                time.sleep(self.camera_pause) # wait for camera to initialise
                break
            time.sleep(1e-4) # poll camera status to check if acquiring

    def check_mr_queue(self):
        """Check whether it is appropriate to start the queued multiruns.
        This prevents multiple multiruns being sent to DExTer at the same time."""
        num_mrs = len(self.rn.seq.mr.mr_queue) # number of multiruns queued
        if num_mrs:
            if not self.rn.seq.mr.multirun and not self.rn.seq.mr.QueueWindow.isVisible(): 
                self.rn.seq.mr.multirun = True
                self.rn.server.add_message(TCPENUM['TCP read'], # send the first multirun to DExTer
                    'start measure %s'%(self.rn.seq.mr.mr_param['measure'] + num_mrs - 1)+'\n'+'0'*2000)
            else: QTimer.singleShot(10e3, self.check_mr_queue) # check again in 10s.
            
    def respond(self, msg=''):
        """Read the text from a TCP message and then execute the appropriate function."""
        self.ts['msg start'] = time.time()
        self.ts['waiting'] = time.time() - self.ts['msg end']
        if 'finished run' in msg:
            self.end_run(msg)
        elif 'start acquisition' in msg:
            self.status_label.setText('Running')
            if self.check_rois.isChecked(): # start experiment when ROIs have atoms
                reset_slot(self.rn.check.rh['Cs'].trigger, self.trigger_exp_start, True) 
                self.rn.atomcheck_go() # start camera acuiring
            elif self.rn.cam.initialised:
                self.rn.cam.start() # start acquisition
                self.wait_for_cam() # wait for camera to initialise before running
            else: 
                warning('Run %s started without camera acquisition.'%(self.rn._n))
            self.rn.server.priority_messages([(TCPENUM['Save sequence'], 'save log file automatic name\n'+'0'*2000),
                (TCPENUM['Run sequence'], 'single run '+str(self.rn._n)+'\n'+'0'*2000),
                (TCPENUM['TCP read'], 'finished run '+str(self.rn._n)+'\n'+'0'*2000)]) # second message confirms end
        elif 'start measure' in msg:
            reset_slot(self.rn.seq.mr.progress, self.status_label.setText, True)
            if self.check_rois.isChecked(): # start experiment when ROIs have atoms
                reset_slot(self.rn.check.rh['Cs'].trigger, self.trigger_exp_start, True) 
                self.rn.atomcheck_go() # start camera acquiring
            elif self.rn.cam.initialised:
                self.rn.cam.start() # start acquisition
                self.wait_for_cam()
            else: warning('Run %s started without camera acquisition.'%(self.rn._n))
            if 'restart' not in msg: self.rn.multirun_go(msg) # might be resuming multirun instead of starting a new one
        elif 'multirun run' in msg:
            if self.check_rois.isChecked(): # start experiment when ROIs have atoms
                reset_slot(self.rn.check.rh['Cs'].trigger, self.trigger_exp_start, True) 
                self.rn.atomcheck_go() # start camera in internal trigger mode
            self.rn.multirun_step(msg)
            # self.rn._k = 0 # reset image per run count
        elif 'save and reset histogram' in msg:
            self.rn.multirun_save(msg)
        elif 'end multirun' in msg:
            reset_slot(self.rn.seq.mr.progress, self.status_label.setText, False)
            self.rn.multirun_end(msg)
            # self.rn.server.save_times()
            self.end_run(msg)
        elif 'STOPPED' in msg:
            self.status_label.setText(msg)
            if self.date_reset: # reset dates at end of multirun
                self.reset_dates()
        elif 'AWG1 ' in msg[:10]: # send command to AWG to set new data
            self.rn.awgtcp1.priority_messages([(self.rn._n, msg.replace('AWG1 ', '').split('||||||||')[0])])
        elif 'AWG2 ' in msg[:10]: # send command to AWG to set new data
            self.rn.awgtcp2.priority_messages([(self.rn._n, msg.replace('AWG2 ', '').split('||||||||')[0])])
        elif 'DDS1 ' in msg[:10]: # send command to DDS to set new data
            self.rn.ddstcp1.priority_messages([(self.rn._n, msg.replace('DDS1 ', '').split('||||||||')[0])])
        elif 'DDS2 ' in msg[:10]: # send command to DDS to set new data
            self.rn.ddstcp2.priority_messages([(self.rn._n, msg.replace('DDS2 ', '').split('||||||||')[0])])
        elif 'SLM ' in msg[:10]: # send command to SLM to set new data
            self.rn.slmtcp.priority_messages([(self.rn._n, msg.replace('SLM ', '').split('||||||||')[0])])
        elif 'MWG ' in msg[:10]: # send command to MW generator to set new data
            self.rn.mwgtcp.priority_messages([(self.rn._n, msg.replace('MWG ', '').split('||||||||')[0])])
        elif 'LVData' in msg: 
            try:
                # self.rn.seq.tr.load_xml_str(msg) # for some reason LV can't sent strings longer than 2453 ...
                self.rn.seq.tr.load_xml(self.stats['TempXMLPath'])
                self.rn.seq.reset_UI()
                if self.rn.seq.display_toggle.isChecked(): self.rn.seq.set_sequence()
                self.status_label.setText('Sequence has been set from DExTer.')
            except TypeError as e: error("Tried to load invalid sequence.\n"+str(e))
        self.ts['msg end'] = time.time()
        self.ts['blocking'] = time.time() - self.ts['msg start']
        # self.print_times()
                
    def end_run(self, msg=''):
        """At the end of a single run or a multirun, stop the acquisition,
        check for unprocessed images, and check synchronisation.
        First, disconnect the server.textin signal from this slot to it
        only triggers once."""
        self.action_button.setEnabled(True) # allow another command to be sent
         # reset atom checker trigger
        reset_slot(self.rn.check.rh['Cs'].trigger, self.trigger_exp_start, False)
        if self.rn.trigger.connected:
            reset_slot(self.rn.trigger.textin, self.rn.trigger.clear_queue, True)
            self.rn.trigger.add_message(TCPENUM['TCP read'], 'end connection'*150)
        try:
            unprocessed = self.rn.cam.EmptyBuffer()
            self.rn.cam.AF.AbortAcquisition()
        except Exception as e: 
            warning('Failed to abort camera acquisition at end of run.\n'+str(e))
        # if unprocessed:
        #     reply = QMessageBox.question(self, 'Unprocessed Images',
        # "Process the remaining %s images from the buffer?"%len(unprocessed), 
        #         QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        #     if reply == QMessageBox.Yes:
        #         for im in unprocessed:
        #             # image dimensions: (# kscans, width pixels, height pixels)
        #             self.rn.receive(im[0]) 
        self.idle_state()
        
    def print_times(self, keys=['waiting', 'blocking']):
        """Print the timings between messages."""
        print(*[key + ': %.4g,\t'%self.ts[key] for key in keys])

    def check_sizes(self, reset=False):
        """Print the length of lists and arrays to help find where memory is being used.
        reset: whether to clear all of the arrays."""
        print("Image analysis:")
        for mw in self.rn.sw.mw + self.rn.sw.rw:
            print(mw.name, '\t', 
                "image_handler max length: ", max(map(np.size, mw.image_handler.stats.values())),
                "\thisto_handler max length: ", max(map(np.size, mw.histo_handler.stats.values())))
        print("TCP Network:")
        for label, tcp in zip(['DExTer', 'Digital trigger', 'DAQ', 'AWG1', 'AWG2', 'DDS1', 'DDS2', 'SLM', 'MWG'],
                [self.rn.server, self.rn.trigger, self.rn.monitor, self.rn.awgtcp1, self.rn.awgtcp2, 
                    self.rn.ddstcp1, self.rn.ddstcp2, self.rn.slmtcp, self.rn.mwgtcp]):
            print(label, ': %s messages'%len(tcp.get_queue()))
        print("Mutlirun queue length: ", len(self.rn.seq.mr.mr_queue))
        if reset:
            for mw in self.rn.sw.mw + self.rn.sw.rw:
                mw.image_handler.reset_arrays()
                mw.histo_handler.reset_arrays()

    def save_state(self, file_name=''):
        """Save the file number and date and config file paths so that they
        can be loaded again when the program is next started."""
        if not file_name:
            try:
                file_name, _ = QFileDialog.getSaveFileName(self, 'Save the PyDex Master State', '', 'all (*)')
            except OSError: return ''
        if not file_name: file_name = './state' # in case user cancels
        self.stats['File#'] = self.rn._n
        self.stats['AnalysisConfig'] = dict(self.rn.sw.stats)
        self.stats['AtomCheckerROIs'] = [self.rn.check.get_rois('Cs'), self.rn.check.get_rois('Rb')]
        self.rn.sw.save_settings()
        for key, g in [['AnalysisGeometry', self.rn.sw.geometry()], 
            ['SequencesGeometry', self.rn.seq.geometry()], ['MasterGeometry', self.geometry()]]:
            self.stats[key] = [g.x(), g.y(), g.width(), g.height()]
        with open(file_name, 'w+') as f:
            for key, val in self.stats.items():
                f.write(key+'='+str(val)+'\n')

    def closeEvent(self, event):
        """Proper shut down procedure"""
        reply = QMessageBox.question(self, 'Confirm Action',
                "Sure you want to quit?", QMessageBox.Yes |
                QMessageBox.No, QMessageBox.No)
        if reply == QMessageBox.No:
            event.ignore()
        elif reply == QMessageBox.Yes:
            try:
                self.rn.cam.SafeShutdown()
            except Exception as e: warning('camera safe shutdown failed.\n'+str(e))
            # self.rn.check.send_rois() # give ROIs from atom checker to image analysis
            for obj in self.rn.sw.mw + self.rn.sw.rw + [self.rn.sw, self.rn.seq, 
                    self.rn.server, self.rn.trigger, self.rn.monitor, self.rn.awgtcp1, 
                    self.rn.awgtcp2, self.rn.ddstcp1, self.rn.ddstcp2, self.rn.mwgtcp,
                    self.rn.check, self.mon_win, self.dds_win, self.rn.seq.mr.QueueWindow]:
                obj.close()
            self.save_state('./state')
            event.accept()
        
####    ####    ####    #### 

def run():
    """Initiate an app to run the program
    if running in Pylab/IPython then there may already be an app instance"""
    app = QApplication.instance()
    standalone = app is None # false if there is already an app instance
    if standalone: # if there isn't an instance, make one
        app = QApplication(sys.argv) 
        
    boss = Master()
    boss.show()
    if standalone: # if an app instance was made, execute it
        sys.exit(app.exec_()) # when the window is closed, python code stops
   
if __name__ == "__main__":
    run()
