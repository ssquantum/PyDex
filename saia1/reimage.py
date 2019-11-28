"""Single Atom Re-Image Analyser
Stefan Spence 22/08/19
For use in a re-imaging sequence.

 - Create two main.py instances of SAIA to analyse different images 
 in a sequence
 - Display the survival histogram - if there's an atom in the 
 first image, then take the second image.
 - Allow the user to display the two running instances of main.py
"""
import os
import sys
import time
import functools
import numpy as np
from astropy.stats import binom_conf_interval
import pyqtgraph as pg    # not as flexible as matplotlib but works a lot better with qt
# some python packages use PyQt4, some use PyQt5...
try:
    from PyQt4.QtCore import QThread, pyqtSignal, QEvent, QRegExp, Qt
    from PyQt4.QtGui import (QApplication, QPushButton, QWidget, QLabel, QAction,
            QGridLayout, QMainWindow, QMessageBox, QLineEdit, QIcon, QFileDialog,
            QDoubleValidator, QIntValidator, QComboBox, QMenu, QActionGroup, 
            QTabWidget, QVBoxLayout, QFont, QRegExpValidator) 
except ImportError:
    from PyQt5.QtCore import QThread, pyqtSignal, QEvent, QRegExp, Qt
    from PyQt5.QtGui import (QGridLayout, QMessageBox, QLineEdit, QIcon, 
            QFileDialog, QDoubleValidator, QIntValidator, QComboBox, QMenu, 
            QActionGroup, QVBoxLayout, QFont, QRegExpValidator)
    from PyQt5.QtWidgets import (QApplication, QPushButton, QWidget, QTabWidget,
        QAction, QMainWindow, QLabel)
from maingui import main_window, remove_slot  # a single instance of SAIA

# main GUI window contains all the widgets                
class reim_window(main_window):
    """Main GUI window managing two sub-instance of SAIA.

    The 1st instance responds to the first image, and the 2nd
    instance responds to the second image produced in a sequence.
    Use Qt to produce the window where the histogram plot is shown.
    A simple interface allows the user to close or open the displays from
    the two instances of SAIA. Separate tabs are made for 
    settings, multirun options, the histogram, histogram statistics,
    displaying images, and plotting histogram statistics.
    This GUI was produced with help from http://zetcode.com/gui/pyqt5/.
    Keyword arguments:
    imhandlers    -- list of two instances of image_handler analysis classes.
    results_path  -- directory to save log file and results to.
    im_store_path -- the directory where images are saved.
    name          -- an ID for this window, prepended to saved files.
    signal        -- the signal that is used to trigger updates"""
    def __init__(self, imhandlers=[], results_path='.', im_store_path='.',
            name='', signal=pyqtSignal(np.ndarray)):
        super().__init__(results_path=results_path, 
                        im_store_path=im_store_path, name=name)
        self.adjust_UI() # adjust widgets from main_window

        self.ih1, self.ih2 = imhandlers # used to get histogram data
        self.event_im = signal # uses the signal from a SAIA instance
        
    def adjust_UI(self):
        """Edit the widgets created by main_window"""
        # self.hist_canvas.setTitle("Histogram of CCD counts")
        self.setWindowTitle(self.name+' - Single Atom Re-Image Analyser - ')

        # update the histogram when getting statistics
        self.stat_update_button.clicked[bool].connect(self.get_histogram)
        self.fit_update_button.clicked[bool].connect(self.get_histogram)
        self.fit_bg_button.clicked[bool].connect(self.get_histogram)

    #### #### canvas functions #### ####

    def get_histogram(self):
        """Take the histogram from the 'after' images where the 'before' images
        contained an atom"""
        t2 = 0
        atom = (np.array(self.ih1.stats['Counts']) // self.ih1.thresh).astype(bool)
        idxs = [i for i, val in enumerate(self.ih2.stats['File ID']) 
                if any(val == j for j in self.ih1.stats['File ID'][atom])]
        # take the after images when the before images contained atoms
        t1 = time.time()
        self.image_handler.stats['Mean bg count'] = [self.ih2.stats['Mean bg count'][i] for i in idxs]
        self.image_handler.stats['Bg s.d.']  = [self.ih2.stats['Bg s.d.'][i] for i in idxs]
        self.image_handler.stats['Counts']   = [self.ih2.stats['Counts'][i] for i in idxs]
        self.image_handler.stats['File ID']  = [self.ih2.stats['File ID'][i] for i in idxs]
        self.image_handler.stats['ROI centre count'] = [self.ih2.stats['ROI centre count'][i] for i in idxs]
        self.image_handler.stats['Max xpos'] = [self.ih2.stats['Max xpos'][i] for i in idxs]
        self.image_handler.stats['Max ypos'] = [self.ih2.stats['Max ypos'][i] for i in idxs]
        self.image_handler.ind = np.size(self.image_handler.stats['Counts']) - 1
        self.image_handler.stats['Atom detected'] = [self.ih2.stats['Atom Detected'][i] for i in idxs]
        self.image_handler.thresh            = self.ih1.thresh
        t2 = time.time()
        self.int_time = t2 - t1
        return t2
        
    def update_plot(self, event_im):
        """Receive the event path emitted from the system event handler signal.
        Take the histogram from the 'after' images where the 'before' images
        contained an atom and then update the figure."""
        t2 = self.get_histogram()
        # display the name of the most recent file
        if self.image_handler.ind > 0:
            self.recent_label.setText('Just processed image '
                        + self.image_handler.stats['File ID'][-1])
        self.plot_current_hist(self.image_handler.hist_and_thresh) # update the displayed plot
        self.plot_time = time.time() - t2

    def update_plot_only(self, event_im):
        """Receive the event path emitted from the system event handler signal.
        Take the histogram from the 'after' images where the 'before' images
        contained an atom and then update the figure without changing the 
        threshold value."""
        t2 = self.get_histogram()
        # display the name of the most recent file
        if self.image_handler.im_num > 0:
            self.recent_label.setText('Just processed image '
                        + self.image_handler.stats['File ID'][-1])
        self.plot_current_hist(self.image_handler.histogram) # update the displayed plot
        self.plot_time = time.time() - t2

    #### #### save and load data functions #### ####

    # def load_from_csv(self): # load histograms into the image_handlers

    #### #### user input functions #### ####

    #### #### toggle functions #### #### 
    