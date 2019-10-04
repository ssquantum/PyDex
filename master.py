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
sys.path.append(r'./saia1')
from saia1.main import main_window # image analysis
from saia1.reimage import reim_window # analysis for survival probability
sys.path.append(r'./ancam')
from ancam.cameraHandler import camera # manages Andor camera
from savim.imsaver import event_handler # saves images

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
    im_save    = pyqtSignal(np.ndarray) # send an incoming image to saver

    def __init__(self, pop_up=1, state_config='.\\state'):
        super().__init__()
        t0 = time.localtime()
        self.ancam_config = '.\\ancam\\ExExposure_config.dat'
        self.save_config = '.\\config\\config.dat'
        self.restore_state(file_name=state_config)
        self.init_UI()
        self.cam = camera(config_file=self.ancam_config) # Andor camera
        self.cam.AcquireEnd.connect(self.receive) # receive the most recent image
        # self.cam.verbosity = True # for debugging
        self.sv = event_handler(self.save_config) # image saver        
        self.im_save.connect(self.sv.respond)
        # choose which image analyser to use from number images in sequence
        if pop_up:
            m, ok = QInputDialog.getInt( # user chooses image analyser
                self, 'Initiate Image Analyser(s)',
                'Select the number of images per sequence\n(0 for survival probability)',
                value=0, min=0, max=10)
        else:
            m = 0
        if m == 0:
            self.mw = [reim_window(self.sv.dirs_dict['Results Path: '])]
            self.mw[0].setGeometry(100, 250, 850, 700)
            self.mw[0].show()
            self._m = 2 # number of images per experimental sequence
        else:
            self._m = m # number of images per experimental sequence
            self.mw = []
            for i in range(m):
                self.mw.append(main_window(
                    results_path =self.sv.dirs_dict['Results Path: '],
                    im_store_path=self.sv.dirs_dict['Image Storage Path: '],
                    name=str(i)))
                self.mw[i].show()
                
        # set a timer to update the dates 10s after midnight:
        QTimer.singleShot((86410 - 3600*t0[3] - 60*t0[4] - t0[5])*1e3, 
            self.reset_dates)
        
        self.status_label.setText('Initialised')

        self._k = 0 # number of images processed
        
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
            self._n = nfn # [Py]DExTer file number
        else: self._n = 0
        
    def make_label_edit(self, label_text, layout, position=[0,0, 1,1],
            default_text='', validator=0):
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
        line_edit.setValidator(validator)
        return label, line_edit
        
    def init_UI(self):
        """Create all of the widget objects required"""
        self.centre_widget = QWidget()
        self.centre_widget.layout = QGridLayout()
        self.centre_widget.setLayout(self.centre_widget.layout)
        self.setCentralWidget(self.centre_widget)
        
        #### validators for user input ####
        # reg_exp = QRegExp(r'([0-9]+(\.[0-9]+)?,?)+')
        # comma_validator = QRegExpValidator(reg_exp) # floats and commas
        # double_validator = QDoubleValidator() # floats
        # int_validator = QIntValidator()       # integers
        
        #### menubar at top gives options ####
        menubar = self.menuBar()
 
        show_windows = menubar.addMenu('Windows')
        menu_items = []
        for window_title in ['Image Analyser', 'Camera Status', 
            'Image Saver', 'Monitoring']:
            menu_items.append(QAction(window_title, self)) 
            menu_items[-1].triggered.connect(self.show_window)
            show_windows.addAction(menu_items[-1])
        
        #### status of the master program ####
        self.status_label = QLabel('Initiating...', self)
        self.centre_widget.layout.addWidget(self.status_label, 0,0, 1,1)
        
        self.Dx_label = QLabel('Dx #: '+str(self._n), self)
        self.centre_widget.layout.addWidget(self.Dx_label, 1,0, 1,1)

        self.acquire_button = QPushButton('Start acquisition', self, 
                                                        checkable=True)
        self.acquire_button.clicked[bool].connect(self.start_acquisitions)
        self.acquire_button.resize(self.acquire_button.sizeHint())
        self.centre_widget.layout.addWidget(self.acquire_button, 2,0, 1,1)
        
        #### choose main window position and dimensions: (xpos,ypos,width,height)
        self.setGeometry(50, 50, 800, 150)
        self.setWindowTitle('PyDex Master')
        # self.setWindowIcon(QIcon('docs/tempicon.png'))

    def show_window(self):
        """Show the window of the submodule or adjust its settings."""
        if self.sender().text() == 'Image Analyser':
            for mw in self.mw:
                mw.show()
        elif self.sender().text() == 'Camera Status':
            text, ok = QInputDialog.getText( 
                self, 'Camera Status',
                'Current state: ' + self.cam.AF.GetStatus() + '\n' +
                'Choose a new config file: ',
                text=self.ancam_config)
            if text and ok and not self.acquire_button.isChecked():
                check = self.cam.ApplySettingsFromConfig(text)
                if not any(check):
                    self.status_label.setText('Camera settings were reset.')
                    self.ancam_config = text
                else:
                    self.status_label.setText(
                        'Failed to update camera settings.')
        elif self.sender().text() == 'Image Saver':
            text, ok = QInputDialog.getText( 
                self, 'Image Saver',
                self.sv.print_dirs(self.sv.dirs_dict.items()) + 
        '\nEnter the path to a config file to reset the image saver: ',
        text=self.save_config)
            if text and ok:
                self.im_save.disconnect()
                self.sv = event_handler(text)
                if self.sv.image_storage_path:
                    self.status_label.setText('Image Saver was reset.')
                    self.im_save.connect(self.sv.respond)
                    self.save_config = text
                else:
                    self.status_label.setText('Failed to find config file.')
        elif self.sender().text() == 'Monitoring':
            pass

    def synchronise(self, option='check', verbose=0):
        """Check the run number in each of the associated modules.
        option: 'check' = simply check if they're in sync
                'reset' = if out of sync, reset to master's run #
        """
        checks = []
        if int(self.sv.dfn) != self._n:
            checks.append(0)
            if verbose: print('Image saver # %s /= run # %s'%(
                                self.sv.dfn, self._n))
        for mw in self.mw:
            if mw.image_handler.fid != self._n:
                checks.append(0)
                if verbose: 
                    print('Image analysis # %s /= run # %s'%(
                            mw.image_handler.fid, self._n))
        if self._k != self._n*self._m + self._k % self._m:
            checks.append(0)
            if verbose:
                print('Lost sync: %s images taken in %s runs'%(
                    self._k, self._n))

    def receive(self, im=0):
        """Update the Dexter file number in all associated modules,
        then send the image array to be saved and analysed.
        Temporarily incrementing the image number after every acquisition
        and then using this to define the Dx run #, but we should define
        the Dx run # from the start of the sequence."""
        self.sv.dfn = str(self._n) # Dexter file number
        imn = self._k % self._m # ID number of image in sequence
        self.sv.imn = str(imn) 
        self.im_save.emit(im)
        if self._m != 2:
            self.mw[imn].image_handler.fid = self._n
            self.mw[imn].event_im.emit(im)
        else: # survival probability uses a master window
            self.mw[0].image_handler.fid = self._n
            self.mw[0].mws[imn].image_handler.fid = self._n
            self.mw[0].mws[imn].event_im.emit(im)
        self._k += 1 # another image was taken

    def start_run(self, option='normal'):
        """Tell DExTer to do a run of its current sequence
        option: 'normal'   = single run
                'multirun' = loop over sequence changing variables"""
        self.synchronise()
        return 1

    def end_run(self, dxn=0):
        """Receive confirmation from DExTer that the run with ID
        dxn completed successfully"""
        if dxn == self._n:
            
            self._n += 1
            self.Dx_label.setText('Dx #: '+str(self._n)
                        + ', Im #: ' + str(self._k % self._m)
                        + '\nTotal images taken: ' + str(self._k))
        

    def reset_dates(self):
        """Make sure that the dates in the image saving and analysis 
        programs are correct."""
        t0 = time.localtime()
        self.sv.date = time.strftime(
                "%d %b %B %Y", t0).split(" ") # day short_month long_month year
        for mw in self.mw:
            mw.date = self.sv.date
        QTimer.singleShot((86410 - 3600*t0[3] - 60*t0[4] - t0[5])*1e3, 
            self.reset_dates)
            
    def reset_camera(self, ancam_config='./ancam/ExExposure_config.dat'):
        """Close the camera and then start it up again with the new setting.
        Sometimes after being in crop mode the camera fails to reset the 
        ROI and so must be closed and restarted."""
        self.cam.SafeShutdown()
        self.cam = camera(config_file=ancam_config) # Andor camera
        self.status_label.setText('Camera settings were reset.')
        self.ancam_config = ancam_config
        

    def start_acquisitions(self, toggle):
        """Take the number of acquisitions stated in the num_acquisitions
        text edit. These are set running on the camera's thread. While
        the camera thread is runnning, the button to start acquisitions 
        will be disabled."""
        if toggle:            
            self.status_label.setText('Acquiring...')
            self.acquire_button.setText('Stop acquisition')
            self.cam.start()
        else:
            unprocessed_ims = self.cam.EmptyBuffer()
            for im in unprocessed_ims:
                # image dimensions: (# kscans, width pixels, height pixels)
                self.receive(im[0]) 
            self.cam.AF.AbortAcquisition()
            self.acquire_button.setText('Start acquisition')
            self.status_label.setText('Idle')
            
    def save_state(self, file_name='./state'):
        """Save the file number and date and config file paths so that they
        can be loaded again when the program is next started."""
        state = {'File#':self._n,
                        'Date':time.strftime("%d,%B,%Y", time.localtime()),
                'CameraConfig':self.ancam_config,
                  'SaveConfig':self.save_config}
        with open(file_name, 'w+') as f:
            for key, val in state.items():
                f.write(key+'='+str(val)+'\n')

    def closeEvent(self, event):
        """Proper shut down procedure"""
        self.cam.SafeShutdown()
        for mw in self.mw:
            mw.close()
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
        sys.exit(app.exec_()) # when the window is closed, the python code also stops
   
if __name__ == "__main__":
    run()