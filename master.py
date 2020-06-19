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
import sys
import time
import copy
import numpy as np
from collections import OrderedDict
try:
    from PyQt4.QtCore import QThread, pyqtSignal, QEvent, QRegExp, QTimer
    from PyQt4.QtGui import (QApplication, QPushButton, QWidget, QLabel, 
        QAction, QGridLayout, QMainWindow, QMessageBox, QLineEdit, QIcon, 
        QFileDialog, QDoubleValidator, QIntValidator, QComboBox, QMenu, 
        QActionGroup, QTabWidget, QVBoxLayout, QFont, QRegExpValidator, 
        QInputDialog) 
except ImportError:
    from PyQt5.QtCore import QThread, pyqtSignal, QEvent, QRegExp, QTimer
    from PyQt5.QtGui import (QIcon, QDoubleValidator, QIntValidator, 
        QFont, QRegExpValidator)
    from PyQt5.QtWidgets import (QApplication, QPushButton, QWidget, 
        QTabWidget, QAction, QMainWindow, QLabel, QInputDialog, QGridLayout,
        QMessageBox, QLineEdit, QFileDialog, QComboBox, QActionGroup, QMenu,
        QVBoxLayout)
# change directory to this file's location
os.chdir(os.path.dirname(os.path.realpath(__file__)))
import warnings
warnings.filterwarnings('ignore') # not interested in RuntimeWarning from mean of empty slice
import logging
import logerrs
logerrs.setup_log()
logger = logging.getLogger(__name__)
sys.path.append('./imageanalysis')
from imageanalysis.settingsgui import settings_window
from imageanalysis.atomChecker import atom_window
sys.path.append('./andorcamera')
from andorcamera.cameraHandler import camera # manages Andor camera
sys.path.append('./saveimages')
from saveimages.imsaver import event_handler # saves images
sys.path.append('./networking')
from networking.runid import runnum # synchronises run number, sends signals
from networking.networker import TCPENUM, remove_slot # enum for DExTer produce-consumer loop cases
sys.path.append('./sequences')
from sequences.sequencePreviewer import Previewer
from strtypes import intstrlist

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
            ('SaveConfig',str), ('MasterGeometry',intstrlist), ('AnalysisGeometry',intstrlist), 
            ('SequencesGeometry',intstrlist)])
        self.stats = OrderedDict([('File#', 0), ('Date', time.strftime("%d,%B,%Y")), 
            ('CameraConfig', '.\\andorcamera\\Standard modes\\ExExposure_config.dat'), 
            ('SaveConfig', '.\\config\\config.dat'), ('MasterGeometry', [10, 10, 500, 150]), 
            ('AnalysisGeometry', [1400, 400, 600, 500]), 
            ('SequencesGeometry', [20, 100, 1000, 800])])
        self.camera_pause = 0 # time in seconds to wait for camera to start acquisition.
        self.ts = {label:time.time() for label in ['init', 'waiting', 'blocking',
            'msg start', 'msg end']}
        sv_dirs = event_handler.get_dirs(self.stats['SaveConfig'])
        # if not any(os.path.exists(svd) for svd in sv_dirs.values()): # ask user to choose valid config file
        startn = self.restore_state(file_name=state_config)
        # choose which image analyser to use from number images in sequence
        self.init_UI(startn)
        # initialise the thread controlling run # and emitting images
        self.rn = runnum(camera(config_file=self.stats['CameraConfig']), # Andor camera
                event_handler(self.stats['SaveConfig']), # image saver
                image_analysis(results_path =sv_dirs['Results Path: '],
                    im_store_path=sv_dirs['Image Storage Path: ']), # image analysis
                atom_window(last_im_path=sv_dirs['Image Storage Path: ']), # check if atoms are in ROIs to trigger experiment
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
        
        self.mon_win = MonitorStatus()
        self.mon_win.start_button.clicked.connect(self.start_monitor)
        self.mon_win.stop_button.clicked.connect(self.stop_monitor)
        self.rn.monitor.textin[str].connect(self.mon_win.set_label)
        self.rn.monitor.textin.connect(self.mon_win.set_connected)
        # set a timer to update the dates 2s after midnight:
        t0 = time.localtime()
        QTimer.singleShot((86402 - 3600*t0[3] - 60*t0[4] - t0[5])*1e3, 
            self.reset_dates)

    def idle_state(self):
        """When the master thread is not processing user events, it is in the idle states.
        The status label is also used as an indicator for DExTer's current state."""
        self.status_label.setText('Idle')

    def restore_state(self, file_name='./state'):
        """Use the data stored in the given file to restore the file # for
        synchronisation if it is the same day, and use the same config files."""
        try:
            with open(file_name, 'r') as f:
                for line in f:
                    if len(line.split('=')) == 2: # there should only be one = per line
                        key, val = line.replace('\n','').split('=') 
                        try:
                            self.stats[key] = self.types[key](val)
                        except KeyError as e:
                            logger.warning('Failed to load PyDex state line: '+line+'\n'+str(e))
        except FileNotFoundError as e: 
            logger.warning('PyDex master settings could not find the state file.\n'+str(e))
        if self.stats['Date'] == time.strftime("%d,%B,%Y"): # restore file number
            return self.stats['File#'] # [Py]DExTer file number
        else: return 0
        
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
 
        show_windows = menubar.addMenu('Windows')
        menu_items = []
        for window_title in ['Image Analyser', 'Camera Status', 
            'Image Saver', 'TCP Server', 'Sequence Previewer',
            'Atom Checker', 'Monitor']:
            menu_items.append(QAction(window_title, self)) 
            menu_items[-1].triggered.connect(self.show_window)
            show_windows.addAction(menu_items[-1])

        sync_menu = menubar.addMenu('Run Settings')
        self.sync_toggle = QAction('Sync with DExTer', sync_menu, 
                checkable=True, checked=True)
        self.sync_toggle.setChecked(True)
        self.sync_toggle.toggled.connect(self.sync_mode)
        sync_menu.addAction(self.sync_toggle)

        self.check_rois = QAction('Trigger on atoms loaded', sync_menu, 
                checkable=True, checked=False)
        self.check_rois.setChecked(False)
        self.check_rois.setEnabled(False) # not functional yet
        sync_menu.addAction(self.check_rois) 

        reset_date = QAction('Reset date', sync_menu, checkable=False)
        reset_date.triggered.connect(self.reset_dates)
        sync_menu.addAction(reset_date)
        
        #### status of the master program ####
        self.status_label = QLabel('Initiating...', self)
        self.centre_widget.layout.addWidget(self.status_label, 0,0, 1,3)
        
        Dx_label = QLabel('Run #: ', self)
        self.centre_widget.layout.addWidget(Dx_label, 1,0, 1,1)
        self.Dx_label = QLabel(str(startn), self)
        self.centre_widget.layout.addWidget(self.Dx_label, 1,1, 1,1)

        # actions that can be carried out 
        self.actions = QComboBox(self)
        self.actions.addItems(['Run sequence', 'Multirun run',
            'Pause multirun', 'Resume multirun', 'Cancel multirun',
            'TCP load sequence','TCP load sequence from string',
            'Save DExTer sequence', 'Cancel Python Mode', 
            'Resync DExTer', 'Start acquisition'])
        self.actions.resize(self.actions.sizeHint())
        self.centre_widget.layout.addWidget(self.actions, 2,0,1,1)

        self.action_button = QPushButton('Go', self, checkable=False)
        self.action_button.clicked[bool].connect(self.start_action)
        self.action_button.resize(self.action_button.sizeHint())
        self.centre_widget.layout.addWidget(self.action_button, 2,1, 1,1)

        # text box to allow user to specify DExTer sequence file 
        _, self.seq_edit = self.make_label_edit('DExTer sequence file: ', 
            self.centre_widget.layout, position=[3,0,1,1])
        # button to load sequence location from file browser
        self.seq_browse = QPushButton('Browse', self, checkable=False)
        self.seq_browse.clicked[bool].connect(self.browse_sequence)
        self.seq_browse.resize(self.seq_browse.sizeHint())
        self.centre_widget.layout.addWidget(self.seq_browse, 3,2, 1,1)
        
        #### choose main window position, dimensions: (xpos,ypos,width,height)
        self.setGeometry(*self.stats['MasterGeometry'])
        self.setWindowTitle('PyDex Master')
        self.setWindowIcon(QIcon('docs/pydexicon.png'))

    def reset_dates(self, auto=True):
        """Reset the date in the image saving and analysis, 
        then display the updated date"""
        t0 = time.localtime()
        self.stats['Date'] = time.strftime("%d,%B,%Y", t0)
        date = self.rn.reset_dates(t0)
        if not hasattr(self.sender(), 'text'): # don't set timer if user pushed button
            QTimer.singleShot((86402 - 3600*t0[3] - 60*t0[4] - t0[5])*1e3, 
                self.reset_dates) # set the next timer to reset dates
        logger.info(time.strftime("Date reset: %d %B %Y", t0))

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
                remove_slot(self.rn.im_save, self.rn.sv.add_item, False)
                self.rn.sv = event_handler(text)
                if self.rn.sv.image_storage_path:
                    self.status_label.setText('Image Saver config: '+text)
                    remove_slot(self.rn.im_save, self.rn.sv.add_item, True)
                    self.stats['SaveConfig'] = text
                else:
                    self.status_label.setText('Failed to find config file.')

        elif self.sender().text() == 'Sequence Previewer':
            self.rn.seq.show()
        elif self.sender().text() == 'TCP Server':
            info = 'Trigger server is running.\n' if self.rn.trigger.isRunning() else 'Trigger server stopped.\n'
            if self.rn.server.isRunning():
                msgs = self.rn.server.get_queue()
                info += "TCP server is running. %s queued message(s)."%len(msgs)
                info += '\nCommand Enum | Length |\t Message\n'
                for enum, textlength, text in msgs[:5]:
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
                self.rn.seq.mr.mr_queue = []
                self.rn.multirun = False
                self.rn.reset_server(force=True) # stop and then restart the servers
                self.rn.server.add_message(TCPENUM['TCP read'], 'Sync DExTer run number\n'+'0'*2000) 
            elif reply == QMessageBox.No:
                self.rn.reset_server(force=False) # restart the server if it stopped
        elif self.sender().text() == 'Atom Checker':
            self.rn.check.showMaximized()
        elif self.sender().text() == 'Monitor':
            self.mon_win.show()
            
    def start_monitor(self, toggle=True):
        """Send a TCP command to the monitor to start its acquisition."""
        self.mon_win.start_check()
        self.rn.monitor.add_message(self.rn._n, 'start')
        
    def stop_monitor(self, toggle=True):
        """Send a TCP command to the monitor to stop its acquisition."""
        self.mon_win.start_check()
        self.rn.monitor.add_message(self.rn._n, 'stop')

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
        except: logger.warning('Andor camera safe shutdown failed') # probably not initialised
        self.rn.cam = camera(config_file=ancam_config) # Andor camera
        remove_slot(self.rn.cam.AcquireEnd, self.rn.receive, True) # connect signal
        self.status_label.setText('Camera settings config: '+ancam_config)
        self.stats['CameraConfig'] = ancam_config

    def start_action(self):
        """Perform the action currently selected in the actions combobox.
        Run sequence:   Start the camera acquisition, then make 
                        DExTer perform a single run of the 
                        sequence that is currently loaded.
        Multirun run:   Start the camera acquisition, then make 
                        DExTer perform a multirun with the preloaded
                        multirun settings.
        TCP load sequence from string: Tell DExTer to load in the sequence
                        from a string in XML format.
        TCP load sequence:  Tell DExTer to load in the sequence file at
                        the location in the 'DExTer sequence file' label.
        Cancel python mode: send the text 'python mode off' which triggers
                        DExTer to exit python mode.
        Resync DExTer:  send a null message just to resync the run number.
        Start acquisition:  start the camera acquiring without telling
                        DExTer to run. Used in unsynced mode."""
        action_text = self.actions.currentText()
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
            else: logger.warning('Master: Tried to start camera acquisition but camera is not initialised.')
        elif action_text == 'Start acquisition' and self.action_button.text() == 'Stop acquisition':
            self.actions.setEnabled(True)
            self.action_button.setText('Go')
            self.end_run()

        if self.rn.server.isRunning():
            if action_text == 'Run sequence':
                # queue up messages: start acquisition, check run number
                self.action_button.setEnabled(False) # only process 1 run at a time
                self.rn._k = 0 # reset image per run count 
                self.rn.server.add_message(TCPENUM['TCP read'], 'start acquisition\n'+'0'*2000) 
                self.rn.monitor.add_message(self.rn._n, 'update run number')
            elif action_text == 'Multirun run':
                if self.rn.seq.mr.check_table():
                    if not self.sync_toggle.isChecked():
                        self.sync_toggle.setChecked(True) # it's better to multirun in synced mode
                        logger.warning('Multirun has changed the "sync with DExTer" setting.')
                    status = self.rn.seq.mr.check_mr_params(self.rn.sv.results_path) # add to queue if valid
                    self.check_mr_queue() # prevent multiple multiruns occurring simultaneously
                else: 
                    QMessageBox.warning(self, 'Invalid multirun', 
                        'All cells in the multirun table must be populated.')
            elif action_text == 'Resume multirun':
                self.rn.multirun_resume(self.status_label.text())
            elif action_text == 'Pause multirun':
                if 'multirun' in self.status_label.text():
                    self.rn.multirun_go(False, stillrunning=True)
            elif action_text == 'Cancel multirun':
                if 'multirun' in self.status_label.text() or self.rn.multirun:
                    if self.rn.check.checking:
                        self.rn.check.rh.trigger.emit(1) # send software trigger to end
                    self.rn.multirun_go(False)
                    self.rn.seq.mr.ind = 0
                    self.rn.seq.mr.reset_sequence(self.rn.seq.tr.copy())
            elif action_text == 'TCP load sequence from string':
                self.rn.server.add_message(TCPENUM[action_text], self.rn.seq.tr.seq_txt)
            elif action_text == 'TCP load sequence':
                self.rn.server.add_message(TCPENUM[action_text], self.seq_edit.text()+'\n'+'0'*2000)
            elif action_text == 'Save DExTer sequence':
                self.rn.server.add_message(TCPENUM['Save sequence'], 'save log file automatic name\n'+'0'*2000)
            elif action_text == 'Cancel Python Mode':
                self.rn.server.add_message(TCPENUM['TCP read'], 'python mode off\n'+'0'*2000)
                self.rn.server.add_message(TCPENUM['TCP read'], 'Resync DExTer\n'+'0'*2000) # for when it reconnects
            elif action_text ==  'Resync DExTer':
                self.rn.server.add_message(TCPENUM['TCP read'], 'Resync DExTer\n'+'0'*2000)

    def trigger_exp_start(self, n=None):
        """Atom checker sends signal saying all ROIs have atoms in, start the experiment"""
        self.rn.check.timer.stop() # in case the timer was going to trigger the experiment as well
        remove_slot(self.rn.trigger.dxnum, self.reset_cam_signals, True) # swap signals when msg confirmed
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
        remove_slot(self.rn.cam.AcquireEnd, self.rn.receive, not self.rn.multirun) # send images to analysis
        remove_slot(self.rn.cam.AcquireEnd, self.rn.mr_receive, self.rn.multirun)
        remove_slot(self.rn.cam.AcquireEnd, self.rn.check_receive, False)
        remove_slot(self.rn.trigger.dxnum, self.reset_cam_signals, False) # only trigger once
        self.rn.trigger.add_message(TCPENUM['TCP read'], 'Go!'*600) # flush TCP
            
    def sync_mode(self, toggle=True):
        """Toggle whether to receive the run number from DExTer,
        or whether to increment the run number every time the expected
        number of images per sequence is received."""
        remove_slot(self.rn.cam.AcquireEnd, self.rn.receive, toggle) 
        remove_slot(self.rn.cam.AcquireEnd, self.rn.unsync_receive, not toggle)
                
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
            if not self.rn.multirun: 
                self.rn.multirun = True
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
                remove_slot(self.rn.check.rh.trigger, self.trigger_exp_start, True) 
                self.rn.atomcheck_go() # start camera acuiring
            elif self.rn.cam.initialised:
                self.rn.cam.start() # start acquisition
                self.wait_for_cam() # wait for camera to initialise before running
            else: 
                logger.warning('Run %s started without camera acquisition.'%(self.rn._n))
            self.rn.server.priority_messages([(TCPENUM['Save sequence'], 'save log file automatic name\n'+'0'*2000),
                (TCPENUM['Run sequence'], 'single run '+str(self.rn._n)+'\n'+'0'*2000),
                (TCPENUM['TCP read'], 'finished run '+str(self.rn._n)+'\n'+'0'*2000)]) # second message confirms end
        elif 'start measure' in msg:
            remove_slot(self.rn.seq.mr.progress, self.status_label.setText, True)
            if self.check_rois.isChecked(): # start experiment when ROIs have atoms
                remove_slot(self.rn.check.rh.trigger, self.trigger_exp_start, True) 
                self.rn.atomcheck_go() # start camera acquiring
            elif self.rn.cam.initialised:
                self.rn.cam.start() # start acquisition
                self.wait_for_cam()
            else: logger.warning('Run %s started without camera acquisition.'%(self.rn._n))
            if 'restart' not in msg: self.rn.multirun_go(msg) # might be resuming multirun instead of starting a new one
        elif 'multirun run' in msg:
            if self.check_rois.isChecked(): # start experiment when ROIs have atoms
                remove_slot(self.rn.check.rh.trigger, self.trigger_exp_start, True) 
                self.rn.atomcheck_go() # start camera in internal trigger mode
            self.rn.multirun_step(msg)
            self.rn._k = 0 # reset image per run count
        elif 'save and reset histogram' in msg:
            self.rn.multirun_save(msg)
        elif 'end multirun' in msg:
            remove_slot(self.rn.seq.mr.progress, self.status_label.setText, False)
            self.rn.multirun_end(msg)
            # self.rn.server.save_times()
            self.end_run(msg)
        elif 'STOPPED' in msg:
            self.status_label.setText(msg)
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
        remove_slot(self.rn.check.rh.trigger, self.trigger_exp_start, False)
        if self.rn.trigger.connected:
            remove_slot(self.rn.trigger.textin, self.rn.trigger.clear_queue, True)
            self.rn.trigger.add_message(TCPENUM['TCP read'], 'end connection'*150)
        try:
            unprocessed = self.rn.cam.EmptyBuffer()
            self.rn.cam.AF.AbortAcquisition()
        except Exception as e: 
            logger.warning('Failed to abort camera acquisition at end of run.\n'+str(e))
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

    def save_state(self, file_name='./state'):
        """Save the file number and date and config file paths so that they
        can be loaded again when the program is next started."""
        self.stats['File#'] = self.rn._n
        with open(file_name, 'w+') as f:
            for key, val in self.stats.items():
                f.write(key+'='+str(val)+'\n')

    def closeEvent(self, event):
        """Proper shut down procedure"""
        try:
            self.rn.cam.SafeShutdown()
        except Exception as e: logger.warning('camera safe shutdown failed.\n'+str(e))
        self.rn.check.send_rois() # give ROIs from atom checker to image analysis
        self.rn.sw.save_settings('.\\imageanalysis\\default.config')
        for key, g in [['AnalysisGeometry', self.rn.sw.geometry()], 
            ['SequencesGeometry', self.rn.seq.geometry()], ['MasterGeometry', self.geometry()]]:
            self.stats[key] = [g.x(), g.y(), g.width(), g.height()]
        for obj in self.rn.sw.mw + self.rn.sw.rw + [self.rn.sw, self.rn.seq, 
                self.rn.server, self.rn.trigger, self.rn.check, self.mon_win]:
            obj.close()
        self.save_state()
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