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
    from PyQt4.QtCore import QThread, pyqtSignal, QEvent, QRegExp
    from PyQt4.QtGui import (QApplication, QPushButton, QWidget, QLabel, 
        QAction, QGridLayout, QMainWindow, QMessageBox, QLineEdit, QIcon, 
        QFileDialog, QDoubleValidator, QIntValidator, QComboBox, QMenu, 
        QActionGroup, QTabWidget, QVBoxLayout, QFont, QRegExpValidator, 
        QInputDialog) 
except ImportError:
    from PyQt5.QtCore import QThread, pyqtSignal, QEvent, QRegExp
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
    """
    im_save    = pyqtSignal(np.ndarray) # send an incoming image to saver
    im_analyse = [pyqtSignal(np.ndarray)] # send an incoming image to analysis

    def __init__(self):
        super().__init__()
        self.init_UI()
        self.cam = camera(config_file='./ancam/AndorCam_config.dat') # Andor camera
        self.cam.AcquireEnd.connect(self.synchronise) # sync the image analysis run number
        # self.cam.verbosity = True # for debugging
        self.sv = event_handler('./config/config.dat') # image saver
        self.im_save.connect(self.sv.respond)
        self.mw = [main_window(self.sv.dirs_dict['Results Path: '] +
            r'\%s\%s\%s'%(self.sv.date[3],self.sv.date[2],self.sv.date[0]))] # image analysis
        self.mw[0].setGeometry(100, 250, 850, 700)
        self.mw[0].event_im = self.im_analyse # assign signal receiving image array
        self.mw[0].swap_signals() # connect slots to the signal
        self.mw[0].show()
        
        self.status_label.setText('Initialised')

        self._n = 0 # [Py]DExTer file number
        self._m = 1 # number of images per experimental sequence
        self._k = 0 # number of images processed
        
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
        int_validator = QIntValidator()       # integers
        
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

        _, self.num_im_per_seq_edit = self.make_label_edit('Number of images per sequence:', 
            self.centre_widget.layout, position=[1,0, 1,1],
            default_text='1', validator=int_validator) # signal connected with lock_imnum_button
        self.num_im_per_seq_edit.setReadOnly(True)
        self.lock_imnum_button = QPushButton('Lock', self, checkable=True)
        self.lock_imnum_button.setChecked()
        self.lock_imnum_button.clicked[bool].connect(self.lock_num_im_per_seq)
        self.lock_imnum_button.resize(self.lock_imnum_button.sizeHint())
        self.centre_widget.layout.addWidget(self.lock_imnum_button, 1,2, 1,1)
        
        self.acquire_button = QPushButton('Start acquisition', self, 
                                                        checkable=True)
        self.acquire_button.clicked[bool].connect(self.start_acquisitions)
        self.acquire_button.resize(self.acquire_button.sizeHint())
        self.centre_widget.layout.addWidget(self.acquire_button, 2,0, 1,1)
        
        #### choose main window position and dimensions: (xpos,ypos,width,height)
        self.setGeometry(50, 50, 800, 150)
        self.setWindowTitle('PyDex Master')
        # self.setWindowIcon(QIcon('docs/tempicon.png'))

    def lock_num_im_per_seq(self, toggle):
        """The number of images per sequence is locked unless this button is 
        toggled. This prevents the user from accidentally resetting the 
        image analyser."""
        if toggle:
            self.num_im_per_seq_edit.setReadOnly(True)
            self.num_im_per_seq_edit.editingFinished.disconnect()
        else:
            self.num_im_per_seq_edit.setReadOnly(False)
            self.num_im_per_seq_edit.editingFinished.connect(self.reset_analyser)

    def reset_analyser(self):
        """Create an instance of saia1 for each image that will be taken in 
        the sequence."""
        self._m = int(self.num_im_per_seq_edit.text())
        for mw in self.mw:
            mw.close()
        if self._m == 2: # calculates survival probability
            self.im_analyse = [pyqtSignal(np.ndarray)]*self._m
            self.mw = [reim_window(self.sv.dirs_dict['Results Path: '] +
                    r'\%s\%s\%s'%(self.sv.date[3],self.sv.date[2],self.sv.date[0]))]
            self.mw[0].mw0.event_im = self.im_analyse[0]
            self.mw[0].mw1.event_im = self.im_analyse[1]
            self.mw[0].swap_signals() # reconnects slots for mw1 and the main window
            self.mw[0].mw0.swap_signals() # reconnects slots for mw0
        else:
            self.im_analyse, self.mw = [], []
            for i in range(self._m):
                self.im_analyse.append(pyqtSignal(np.ndarray))
                self.mw.append(main_window(self.sv.dirs_dict['Results Path: '] +
                    r'\%s\%s\%s'%(self.sv.date[3],self.sv.date[2],self.sv.date[0])))
                self.mw[i].event_im = self.im_analyse[i] # assign signal
                self.mw[i].swap_signals() # connect signal
        
    def show_window(self):
        """Make the selected window pop up"""
        if self.sender().text() == 'Image Analyser':
            for mw in self.mw:
                mw.show()
        elif self.sender().text() == 'Camera Status':
            msg = QMessageBox()
            msg.setIcon(QMessageBox.Information)
            msg.setText(self.cam.AF.GetStatus())
            msg.setStandardButtons(QMessageBox.Ok)
            msg.exec_()
        elif self.sender().text() == 'Image Saver':
            pass
        elif self.sender().text() == 'Monitoring':
            pass

    def synchronise(self, im=0):
        """Update the Dexter file number in all associated modules,
        then send the image array to be saved and analysed."""
        self.sv.dfn = str(self._n) # Dexter file number
        self.sv.imn = str(self._k % self._m) # number of image in sequence
        self.im_save.emit(im)
        for mw in self.mw:
            mw.image_handler.fid = self._n
        self.im_analyse[self._k % self._m].emit(im)
        self._k += 1 # another image was taken
        if self._k % self._m == 0: # took all of the images in a sequence
            self._n += 1

    def reset_dates(self):
        """Make sure that the dates in the image saving and analysis 
        programs are correct."""
        self.sv.date = time.strftime(
                "%d %b %B %Y", time.localtime()).split(" ") # day short_month long_month year
        for mw in self.mw:
            mw.date = self.sv.date

    def start_acquisitions(self, toggle):
        """Take the number of acquisitions stated in the num_acquisitions
        text edit. These are set running on the camera's thread. While
        the camera thread is runnning, the button to start acquisitions 
        will be disabled."""
        if toggle:            
            self.status_label.setText('Acquiring...')
            self.cam.start()
        else:
            self.cam.AF.AbortAcquisition()
            self.status_label.setText('Idle')

    def closeEvent(self, event):
        """Proper shut down procedure"""
        self.cam.SafeShutdown()
        for mw in self.mw:
            mw.close()
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