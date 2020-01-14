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
import numpy as np
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
import logging
import logerrs
logerrs.setup_log()
logger = logging.getLogger(__name__)
sys.path.append('./imageanalysis')
from imageanalysis.settingsgui import settings_window
sys.path.append('./andorcamera')
from andorcamera.cameraHandler import camera # manages Andor camera
sys.path.append('./saveimages')
from saveimages.imsaver import event_handler # saves images
sys.path.append('./networking')
from networking.runid import runnum # synchronises run number, sends signals
from networking.networker import TCPENUM, remove_slot # enum for DExTer produce-consumer loop cases
sys.path.append('./sequences')
from sequences.sequencePreviewer import Previewer

class Master(QMainWindow):
    """A manager to synchronise and control experiment modules.
    
    Initiates the Andor camera and connects its completed acquisition
    signal to the image analysis and the image saving modules.
    Uses the queue module to create the list of sequences to run,
    and the bridge module to communicate with Dexter.
    This master module will define the run number. It must confirm that
    each Dexter sequence has run successfully in order to stay synchronised.
    Keyword arguments:
    pop_up       -- 0: initiate a single instance of saia1.
                    1: open a dialog asking the user which image analyser.
    state_config -- path to the file that saved the previous state.
                    Default directories for camera settings and image 
                    saving are also saved in this file.
    """
    def __init__(self, pop_up=1, state_config='.\\state'):
        super().__init__()
        self.camera_pause = 0 # time in seconds to wait for camera to start acquisition.
        self.ancam_config = '.\\andorcamera\\ExExposure_config.dat' # if restore state fails
        self.save_config = '.\\config\\config.dat'
        self.ts = {label:time.time() for label in ['init', 'waiting', 'blocking',
            'msg start', 'msg end']}
        sv_dirs = event_handler.get_dirs(self.save_config)
        # if not any([os.path.exists(svd) for svd in sv_dirs.values()]): # ask user to choose valid config file
        startn = self.restore_state(file_name=state_config)
        # choose which image analyser to use from number images in sequence
        self.init_UI(startn)
        if pop_up: # also option to choose config file?
            m, ok = QInputDialog.getInt( # user chooses image analyser
                self, 'Initiate Image Analyser(s)',
                'Select the number of images per sequence\n(0 for survival probability)',
                value=0, min=0, max=100)
        else:
            m = 0
        # initialise the thread controlling run # and emitting images
        self.rn = runnum(camera(config_file=self.ancam_config), # Andor camera
                event_handler(self.save_config), # image saver
                settings_window(nsaia=m if m!=0 else 2, nreim=1 if m==0 else 1,
                    results_path =sv_dirs['Results Path: '],
                    im_store_path=sv_dirs['Image Storage Path: ']), # image analysis
                Previewer(), # sequence editor
                n=startn, m=m if m!=0 else 2, k=0) 
        
        self.rn.server.dxnum.connect(self.Dx_label.setText) # synchronise run number
        self.rn.server.textin.connect(self.respond) # read TCP messages
        self.status_label.setText('Initialising...')
        QTimer.singleShot(0, self.idle_state) # takes a while for other windows to load
        
        self.rn.seq.show()
        self.rn.sw.show()
        self.rn.sw.show_analyses()

    def idle_state(self):
        """When the master thread is not processing user events, it is in the idle states.
        The status label is also used as an indicator for DExTer's current state."""
        self.status_label.setText('Idle')

    def restore_state(self, file_name='./state'):
        """Use the data stored in the given file to restore the file # for
        synchronisation if it is the same day, and use the same config 
        files."""
        with open(file_name, 'r') as f:
            for row in f:
                if 'File#' in row:
                    nfn = int(row.split('=')[-1])
                elif 'Date' in row:
                    nd  = row.split('=')[-1].replace('\n','')
                elif 'CameraConfig' in row:
                    self.ancam_config = row.split('=')[-1].replace('\n','')
                elif 'SaveConfig' in row:
                    self.save_config = row.split('=')[-1].replace('\n','')
        if nd == time.strftime("%d,%B,%Y", time.localtime()): # restore file number
            return nfn # [Py]DExTer file number
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
            'Image Saver', 'TCP Server', 'Sequence Previewer']:
            menu_items.append(QAction(window_title, self)) 
            menu_items[-1].triggered.connect(self.show_window)
            show_windows.addAction(menu_items[-1])

        sync_menu = menubar.addMenu('Run Synchronisation')
        self.sync_toggle = QAction('Sync with DExTer', sync_menu, 
                checkable=True, checked=True)
        self.sync_toggle.setChecked(True)
        self.sync_toggle.toggled.connect(self.sync_mode)
        sync_menu.addAction(self.sync_toggle)
        
        #### status of the master program ####
        self.status_label = QLabel('Initiating...', self)
        self.centre_widget.layout.addWidget(self.status_label, 0,0, 1,3)
        
        Dx_label = QLabel('Dx #: ', self)
        self.centre_widget.layout.addWidget(Dx_label, 1,0, 1,1)
        self.Dx_label = QLabel(str(startn), self)
        self.centre_widget.layout.addWidget(self.Dx_label, 1,1, 1,1)

        # actions that can be carried out 
        self.actions = QComboBox(self)
        self.actions.addItems(['Run sequence', 'Multirun run',
            'Pause multirun', 'Resume multirun', 'Cancel multirun',
            'TCP load sequence','TCP load sequence from string',
            'Cancel Python Mode'])
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
        self.setGeometry(50, 50, 800, 150)
        self.setWindowTitle('PyDex Master')
        self.setWindowIcon(QIcon('docs/pydexicon.png'))

    def show_window(self):
        """Show the window of the submodule or adjust its settings."""
        if self.sender().text() == 'Image Analyser':
            self.rn.sw.show()

        elif self.sender().text() == 'Camera Status':
            if self.rn.cam.initialised:
                msg = 'Current state: ' + self.rn.cam.AF.GetStatus() + '\nChoose a new config file: '
            else: msg = 'Camera not initialised. See log file for details. Press OK to retry.'
            text, ok = QInputDialog.getText( self, 'Camera Status', msg, text=self.ancam_config)
            if text and ok:
                if self.rn.cam.initialised > 2:
                    if self.rn.cam.AF.GetStatus() == 'DRV_ACQUIRING':
                        self.rn.cam.AF.AbortAcquisition()
                    check = self.rn.cam.ApplySettingsFromConfig(text)
                    if not any(check):
                        self.status_label.setText('Camera settings config: '+text)
                        self.ancam_config = text
                    else:
                        self.status_label.setText('Failed to update camera settings.')
                else: self.reset_camera(text)
                    
        elif self.sender().text() == 'Image Saver':
            text, ok = QInputDialog.getText( 
                self, 'Image Saver',
                self.rn.sv.print_dirs(self.rn.sv.dirs_dict.items()) + 
        '\nEnter the path to a config file to reset the image saver: ',
        text=self.save_config)
            if text and ok:
                remove_slot(self.rn.im_save, self.rn.sv.add_item, False)
                self.rn.sv = event_handler(text)
                if self.rn.sv.image_storage_path:
                    self.status_label.setText('Image Saver config: '+text)
                    remove_slot(self.rn.im_save, self.rn.sv.add_item, True)
                    self.save_config = text
                else:
                    self.status_label.setText('Failed to find config file.')

        elif self.sender().text() == 'Sequence Previewer':
            self.rn.seq.show()
        elif self.sender().text() == 'TCP Server':
            if self.rn.server.isRunning():
                info = "TCP server is running. %s queued message(s)."%len(self.rn.server.msg_queue)
                info += '\nCommand Enum | Length |\t Message\n'
                for msg in self.rn.server.msg_queue[:5]:
                    msglen = int.from_bytes(msg[1], 'big')
                    info += ' | '.join([str(int.from_bytes(msg[0], 'big')), 
                            str(msglen), str(msg[2], 'mbcs')[:20]])
                    if msglen > 20:  info += '...'
                    info += '\n'
                if len(self.rn.server.msg_queue) > 5:
                    info += '...\n'
            else:
                info = "TCP server stopped."
            reply = QMessageBox.question(self, 'TCP Server Status', 
                info+"\nDo you want to restart the server?", 
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if reply == QMessageBox.Yes:
                self.action_button.setEnabled(True)
                self.rn.reset_server(force=True)

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
        self.ancam_config = ancam_config

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
                        the location in the 'Sequence file' label.
        Cancel python mode: send the text 'python mode off' which triggers
                        DExTer to exit python mode."""
        if self.rn.server.isRunning():
            action_text = self.actions.currentText()
            if action_text == 'Run sequence':
                # queue up messages: start acquisition, check run number
                self.action_button.setEnabled(False) # only process 1 run at a time
                self.rn._k = 0 # reset image per run count 
                self.rn.server.add_message(TCPENUM['TCP read'], 'start acquisition') 
            elif action_text == 'Multirun run':
                self.rn.server.add_message(TCPENUM['TCP read'], 'start measure '+str(self.rn.seq.mr.stats['measure'])) # set DExTer's message to send
            elif action_text == 'Resume multirun':
                self.rn.multirun_resume(self.status_label.text())
            elif action_text == 'Pause multirun':
                if 'multirun' in self.status_label.text():
                    self.rn.multirun_go(False)
            elif action_text == 'Cancel multirun':
                if 'multirun' in self.status_label.text():
                    self.rn.multirun_go(False)
                    self.rn.seq.mr.ind = 0
                    self.rn.seq.mr.reset_sequence(self.rn.seq.tr)
            elif action_text == 'TCP load sequence from string':
                self.rn.server.add_message(TCPENUM[action_text], self.rn.seq.tr.seq_txt)
            elif action_text == 'TCP load sequence':
                self.rn.server.add_message(TCPENUM[action_text], self.seq_edit.text())
            elif action_text == 'Cancel Python Mode':
                self.rn.server.add_message(TCPENUM['TCP read'], 'python mode off')
            
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
                
    def respond(self, msg=''):
        """Read the text from a TCP message and then execute the appropriate function."""
        self.ts['msg start'] = time.time()
        self.ts['waiting'] = time.time() - self.ts['msg end']
        if 'finished run' in msg:
            self.end_run(msg)
        elif 'start acquisition' in msg:
            if self.rn.cam.initialised:
                self.rn.cam.start() # start acquisition
                self.wait_for_cam() # wait for camera to initialise before running
            else: 
                logger.warning('Run %s started without camera acquisition.'%(self.rn._n))
            self.rn.server.priority_messages([(TCPENUM['Run sequence'], 'single run '+str(self.rn._n)),
                (TCPENUM['TCP read'], 'finished run '+str(self.rn._n))]) # second message confirms end
        elif 'start measure' in msg:
            remove_slot(self.rn.seq.mr.progress, self.status_label.setText, True)
            if self.rn.cam.initialised:
                self.rn.cam.start() # start acquisition
                self.wait_for_cam()
            else: logger.warning('Run %s started without camera acquisition.'%(self.rn._n))
            self.rn.multirun_go(msg)
        elif 'multirun run' in msg:
            self.rn.multirun_step(msg)
            self.rn._k = 0 # reset image per run count
        elif 'end multirun' in msg:
            remove_slot(self.rn.seq.mr.progress, self.status_label.setText, False)
            self.rn.server.save_times()
            self.end_run(msg)
        # auto save any sequence that was sent to be loaded (even if it was already an xml file)
        # elif '<Name>Event list cluster in</Name>' in msg: # DExTer also saves the sequences when it's run
        #     self.rn.seq.save_seq_file(os.path.join(self.rn.sv.sequences_path, str(self._n) + time.strftime('_%d %B %Y_%H %M %S') + '.xml'))
        self.ts['msg end'] = time.time()
        self.ts['blocking'] = time.time() - self.ts['msg start']
        print(str(self.rn._n), ': ', msg[:50])
        self.print_times()
                
    def end_run(self, msg=''):
        """At the end of a single run or a multirun, stop the acquisition,
        check for unprocessed images, and check synchronisation.
        First, disconnect the server.textin signal from this slot to it
        only triggers once."""
        self.action_button.setEnabled(True)
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
        self.rn.synchronise()
        self.idle_state()
        
    def print_times(self, keys=['waiting', 'blocking']):
        """Print the timings between messages."""
        print(*[key + ': %.4g,\t'%self.ts[key] for key in keys])

    def save_state(self, file_name='./state'):
        """Save the file number and date and config file paths so that they
        can be loaded again when the program is next started."""
        state = {'File#':self.rn._n,
                        'Date':time.strftime("%d,%B,%Y", time.localtime()),
                'CameraConfig':self.ancam_config,
                  'SaveConfig':self.save_config}
        with open(file_name, 'w+') as f:
            for key, val in state.items():
                f.write(key+'='+str(val)+'\n')

    def closeEvent(self, event):
        """Proper shut down procedure"""
        try:
            self.rn.cam.SafeShutdown()
        except Exception as e: logger.warning('camera safe shutdown failed.\n'+str(e))
        self.rn.sw.save_settings('.\\imageanalysis\\default.config')
        for obj in self.rn.sw.mw + self.rn.sw.rw + [self.rn.sw, self.rn.seq, self.rn.server]:
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