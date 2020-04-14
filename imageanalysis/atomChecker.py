"""PyDex Atom Checker
Stefan Spence 13/04/20

 - Display image array with ROIs
 - plot history of counts in ROI
 - compare counts to threshold
 - send signal when all ROIs have atoms
 - user can drag ROI or automatically arrange them
"""
import os
import sys
import time
import numpy as np
import pyqtgraph as pg
from collections import OrderedDict
# some python packages use PyQt4, some use PyQt5...
try:
    from PyQt4.QtCore import pyqtSignal, QRegExp
    from PyQt4.QtGui import (QApplication, QPushButton, QWidget, QLabel, QAction,
            QGridLayout, QMainWindow, QMessageBox, QLineEdit, QIcon, QFileDialog,
            QDoubleValidator, QIntValidator, QMenu, QActionGroup, QFont,
            QTableWidget, QTableWidgetItem, QTabWidget, QVBoxLayout, QRegExpValidator) 
except ImportError:
    from PyQt5.QtCore import pyqtSignal, QRegExp
    from PyQt5.QtGui import (QIcon, QDoubleValidator, QIntValidator, 
        QRegExpValidator, QFont)
    from PyQt5.QtWidgets import (QActionGroup, QVBoxLayout, QMenu, 
        QFileDialog, QMessageBox, QLineEdit, QGridLayout, QWidget,
        QApplication, QPushButton, QAction, QMainWindow, QTabWidget,
        QTableWidget, QTableWidgetItem, QLabel)
import logging
logger = logging.getLogger(__name__)
sys.path.append('.')
sys.path.append('..')
from strtypes import intstrlist, listlist
from maingui import remove_slot # single atom image analysis
from roiHandler import ROI, roi_handler

####    ####    ####    ####

class atom_window(QMainWindow):
    """GUI window displaying ROIs and the counts recorded in them

    Keyword arguments:
    im_store_path -- the directory where images are saved.
    num_rois      -- number of ROIs to initiate.
    image_shape   -- shape of the images being taken, in pixels (x,y).
    name          -- an ID for this window, prepended to saved files.
    """
    event_im = pyqtSignal([np.ndarray, bool])
    trigger = pyqtSignal(int)

    def __init__(self, im_store_path='.', num_rois=1, image_shape=(512,512), name=''):
        super().__init__()
        self.image_storage_path = im_store_path
        self.h = roi_handler(num_rois, image_shape)
        self.init_UI() # adjust widgets from main_window
        
    def init_UI(self):
        """Create all the widgets and position them in the layout"""
        self.centre_widget = QWidget()
        layout = QGridLayout()       # make tabs for each main display 
        self.centre_widget.setLayout(layout)
        self.setCentralWidget(self.centre_widget)

        # validators for user input
        double_validator = QDoubleValidator() # floats
        int_validator    = QIntValidator()    # integers
        int_validator.setBottom(0) # don't allow -ve numbers

        #### menubar at top gives options ####
        menubar = self.menuBar()

        # file menubar allows you to save/load data
        file_menu = menubar.addMenu('File')
        load_im = QAction('Load Image', self) # display a loaded image
        load_im.triggered.connect(self.load_image)
        file_menu.addAction(load_im)
        
        make_im_menu = QMenu('Make Average Image', self) # display ave. image
        make_im = QAction('From Files', self) # from image files (using file browser)
        make_im.triggered.connect(self.make_ave_im)
        make_im_menu.addAction(make_im)
        make_im_fn = QAction('From File Numbers', self) # from image file numbers
        make_im_fn.triggered.connect(self.make_ave_im)
        make_im_menu.addAction(make_im_fn)
        file_menu.addMenu(make_im_menu)

        pg.setConfigOption('background', 'w') # set graph background default white
        pg.setConfigOption('foreground', 'k') # set graph foreground default black


        #### display image with ROIs ####
        # toggle to continuously plot images as they come in
        self.im_show_toggle = QPushButton('Auto-display last image', self)
        self.im_show_toggle.setCheckable(True)
        self.im_show_toggle.clicked[bool].connect(self.set_im_show)
        layout.addWidget(self.im_show_toggle, 0,0, 1,1)

        im_widget = pg.GraphicsLayoutWidget() # containing widget
        viewbox = im_widget.addViewBox() # plot area to display image
        self.im_canvas = pg.ImageItem() # the image
        viewbox.addItem(self.im_canvas)
        layout.addWidget(im_widget, 1,0, 6,8)
        # make an ROI that the user can drag
        self.roi = pg.ROI([0,0], [1,1], movable=False) 
        self.roi.sigRegionChangeFinished.connect(self.user_roi)
        viewbox.addItem(self.roi)
        self.roi.setZValue(10)   # make sure the ROI is drawn above the image

        #### display plots of counts for each ROI ####
        
        

        # change font size
        font = QFont()
        font.setPixelSize(14)

        
    #### #### canvas functions #### ####


    #### #### save and load data functions #### ####

    def get_default_path(self, default_path=''):
        """Get a default path for saving/loading images
        default_path: set the default path if the function doesn't find one."""
        return default_path if default_path else os.path.dirname(self.last_path)

    def try_browse(self, title='Select a File', file_type='all (*)', 
                open_func=QFileDialog.getOpenFileName, default_path=''):
        """Open a file dialog and retrieve a file name from the browser.
        title: String to display at the top of the file browser window
        default_path: directory to open first
        file_type: types of files that can be selected
        open_func: the function to use to open the file browser"""
        default_path = self.get_default_path(default_path)
        try:
            if 'PyQt4' in sys.modules:
                file_name = open_func(self, title, default_path, file_type)
            elif 'PyQt5' in sys.modules:
                file_name, _ = open_func(self, title, default_path, file_type)
            self.last_path = file_name
            return file_name
        except OSError: return '' # probably user cancelled

    def load_from_files(self, trigger=None, process=1):
        """Prompt the user to select image files to process using the file
        browser.
        Keyword arguments:
            trigger:        Boolean passed from the QObject that triggers
                            this function.
            process:        1: process images and add to histogram.
                            0: return list of image arrays."""
        im_list = []
        if self.check_reset():
            file_list = self.try_browse(title='Select Files', 
                    file_type='Images(*.asc);;all (*)', 
                    open_func=QFileDialog.getOpenFileNames, 
                    default_path=self.image_storage_path)
            self.recent_label.setText('Processing files...') # comes first otherwise not executed
            for file_name in file_list:
                try:
                    im_vals = self.image_handler.load_full_im(file_name)
                    if process:
                        self.image_handler.process(im_vals)
                    else: im_list.append(im_vals)
                    self.recent_label.setText( # only updates at end of loop
                        'Just processed: '+os.path.basename(file_name)) 
                except Exception as e: # probably file size was wrong
                    logger.warning("Failed to load image file: "+file_name+'\n'+str(e)) 
            self.plot_current_hist(self.image_handler.histogram, self.hist_canvas)
            self.histo_handler.process(self.image_handler, self.stat_labels['User variable'].text(), 
                        fix_thresh=self.thresh_toggle.isChecked(), method='quick')
            if self.recent_label.text == 'Processing files...':
                self.recent_label.setText('Finished Processing')
        return im_list

    def load_from_file_nums(self, trigger=None, label='Im', process=1):
        """Prompt the user to enter a range of image file numbers.
        Use these to select the image files from the current image storage path.
        Sequentially process the images then update the histogram
        Keyword arguments:
            trigger:        Boolean passed from the QObject that triggers
                            this function.
            label:        part of the labelling convention for image files
            process:        1: process images and add to histogram.
                            0: return list of image arrays."""
        im_list = []
        try: # which image in the sequence is being used
            imid = str(int(self.name.split('Im')[1].replace('.','')))
        except:
            imid = '0'
        default_range = ''
        image_storage_path = self.image_storage_path + '\%s\%s\%s'%(
                self.date[3],self.date[2],self.date[0])  
        date = self.date[0]+self.date[1]+self.date[3]
        if self.image_handler.ind > 0: # defualt load all files in folder
            default_range = '0 - ' + str(self.image_handler.ind)
        text, ok = QInputDialog.getText( # user inputs the range
            self, 'Choose file numbers to load from','Range of file numbers: ',
            text=default_range)
        if ok and text and image_storage_path: # if user cancels or empty text, do nothing
            for file_range in text.split(','):
                minmax = file_range.split('-')
                if np.size(minmax) == 1: # only entered one file number
                    file_list = [
                        os.path.join(image_storage_path, label) + '_' + date + '_' + 
                        minmax[0].replace(' ','') + '_' + imid + '.asc']
                if np.size(minmax) == 2:
                    file_list = [
                        os.path.join(image_storage_path, label) + '_' + date + '_' + 
                        dfn + '_' + imid + '.asc' for dfn in list(map(str, 
                            range(int(minmax[0]), int(minmax[1]))))] 
            for file_name in file_list:
                try:
                    im_vals = self.image_handler.load_full_im(file_name)
                    if process:
                        self.image_handler.process(im_vals)
                    else: im_list.append(im_vals)
                    self.recent_label.setText(
                        'Just processed: '+os.path.basename(file_name)) # only updates at end of loop
                except:
                    print("\n WARNING: failed to load "+file_name) # probably file size was wrong
        return im_list

    def load_image(self, trigger=None):
        """Prompt the user to select an image file to display"""
        file_name = self.try_browse(file_type='Images (*.asc);;all (*)', 
                default_path=self.image_storage_path)
        if file_name:  # avoid crash if the user cancelled
            im_vals = self.image_handler.load_full_im(file_name)
            self.update_im(im_vals)
        
    def make_ave_im(self):
        """Make an average image from the files selected by the user and 
        display it."""
        if self.sender().text() == 'From Files':
            im_list = self.load_from_files(process=0)
        elif self.sender().text() == 'From File Numbers':
            im_list = self.load_from_file_nums(process=0)
        else: im_list = []
        if len(im_list):
            aveim = np.zeros(np.shape(im_list[0]))
        else: return 0 # no images selected
        for im in im_list:
            aveim += im
        self.update_im(aveim / len(im_list))
        return 1
