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
from saia1.main import main_window  # image analysis
sys.path.append(r'./ancam')
from ancam.cameraHandler import camera # manages Andor camera

class Master(QMainWindow):
    """A manager to synchronise and control experiment modules.
    
    Initiates the Andor camera and connects its completed acquisition
    signal to the image analysis and the image saving modules.
    Uses the queue module to create the list of sequences to run,
    and the bridge module to communicate with Dexter.
    This master module will define the run number. It must confirm that
    each Dexter sequence has run successfully in order to stay synchronised.
    """
    def __init__(self):
        super().__init__()
        self.init_UI()
        self.cam = camera(config_file='./ancam/AndorCam_config.dat') # Andor camera
        self.cam.AcquireEnd2.connect(self.update_fid) # sync the image analysis run number
        self.cam.Finished.connect(self.reset_acquire_buttons)
        self.cam.verbosity = True # for debugging
        self.mw = main_window('./saia1/config/config.dat') # image analysis
        self.mw.setGeometry(100, 250, 850, 700)
        self.mw.event_im = self.cam.AcquireEnd1 # signal receiving image array
        self.mw.swap_signals() # connect slots to the signal
        self.mw.show()
        
        self.status_label.setText('Initialised')

        self._n = 0 # run synchronisation number
        
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
        reg_exp = QRegExp(r'([0-9]+(\.[0-9]+)?,?)+')
        comma_validator = QRegExpValidator(reg_exp) # floats and commas
        double_validator = QDoubleValidator() # floats
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
        
        self.acquire_button = QPushButton('Start acquisition', self, 
                                                        checkable=True)
        self.acquire_button.clicked[bool].connect(self.start_acquisitions)
        self.acquire_button.resize(self.acquire_button.sizeHint())
        self.centre_widget.layout.addWidget(self.acquire_button, 1,0, 1,1)
        
                
        #### choose main window position and dimensions: (xpos,ypos,width,height)
        self.setGeometry(50, 50, 800, 150)
        self.setWindowTitle('PyDex Master')
        # self.setWindowIcon(QIcon('docs/tempicon.png'))
        
    def show_window(self):
        """Make the selected window pop up"""
        if self.sender().text() == 'Image Analyser':
            self.mw.show()
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

    def update_fid(self, im=0):
        """Update the image analysis module's next file ID number
        so that it stays synchronised."""
        self.mw.image_handler.fid = self._n
        
    def reset_acquire_buttons(self, success=0):
        """Once the camera has finished taken the set number of acquisitions
        reset the acquire buttons so that the user can see it's finished."""
        self.acquire_button.setEnabled(True)
        self.status_label.setText('Idle'  if success else 'Acquisition failed')

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
        self.mw.close()
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