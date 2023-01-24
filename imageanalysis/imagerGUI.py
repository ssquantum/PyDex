"""Multi Atom Image Analysis Interface [imagerGUI (iGUI)]
Dan Ruttley 2023-01-20
Code written to follow PEP8 conventions with max line length 120 characters.

 - receive an image as an array from a pyqtSignal
 - set multiple ROIs on the image and take an integrated count from the pixels
 - determine atom presence by comparison with a threshold count
 - plot a histogram of signal counts, which defines the threshold
"""
__version__ = '1.3'
import os
import sys
import time
import numpy as np
import pyqtgraph as pg    # not as flexible as matplotlib but works a lot better with qt
from PyQt5.QtCore import pyqtSignal, QThread, pyqtSlot
from PyQt5.QtGui import (QIcon, QDoubleValidator, QIntValidator, 
        QFont, QRegExpValidator)
from PyQt5.QtWidgets import (QActionGroup, QVBoxLayout, QMenu, 
        QFileDialog, QComboBox, QMessageBox, QLineEdit, QGridLayout, 
        QApplication, QPushButton, QAction, QMainWindow, QWidget,
        QLabel, QTabWidget, QInputDialog, QHBoxLayout, QTableWidget,
        QCheckBox, QFormLayout, QCheckBox, QStatusBar)
if '..' not in sys.path: sys.path.append('..')
from strtypes import error, warning, info
import imageHandler as ih # process images to build up a histogram
import histoHandler as hh # collect data from histograms together
import fitCurve as fc   # custom class to get best fit parameters using curve_fit
from datetime import datetime

from multiAtomImageAnalyser import MultiAtomImageAnalyser

####    ####    ####    ####

# validators for user input
double_validator = QDoubleValidator() # floats
int_validator    = QIntValidator()    # integers
int_validator.setBottom(0) # don't allow -ve numbers
nat_validator    = QIntValidator()    # natural numbers 
nat_validator.setBottom(1) # > 0

counts_plot_roi_offset = 0.2 # the +/- value that the counts plotting can use so that points don't all bunch up

####    ####    ####    ####

def reset_slot(signal, slot, reconnect=True):
    """Make sure all instances of slot are disconnected from signal. Prevents multiple connections to the same slot. If 
    reconnect=True, then reconnect slot to signal."""
    while True: # make sure that the slot is only connected once 
        try: signal.disconnect(slot)
        except TypeError: break
    if reconnect: signal.connect(slot)

####    ####    ####    ####

# main GUI window contains all the widgets                
class ImagerGUI(QMainWindow):
    """Main GUI window managing the MAIA (multi-atom image analyser).

    Keyword arguments:
    results_path  -- directory to save log file and results to.
    im_store_path -- the directory where images are saved.
    name          -- an ID for this window, prepended to saved files.
    im_handler    -- an instance of image_handler
    hist_handler  -- an instance of histo_handler
    edit_ROI      -- whether the user can edit the ROI"""
    event_im = pyqtSignal([np.ndarray, bool]) # [numpy array, include in hists?]
    
    signal_advance_image_count = pyqtSignal() # advances the image count in the MAIA
    signal_send_new_rois = pyqtSignal(object,bool) # new rois to send to coords. bool is whether to lock to group zero
    signal_send_maia_image = pyqtSignal(np.ndarray)
    signal_set_num_roi_groups = pyqtSignal(object) # used to set the number of ROI groups
    signal_set_num_rois_per_group = pyqtSignal(object) # used to set the number of ROIs per group

    def __init__(self):
        super().__init__()
        self.name = 'SIMON: Simple Image MONitoring'  # name is displayed in the window title
        self.setWindowTitle(self.name)

        self.init_UI()
        self.init_maia_thread()

        # pg.setConfigOption('background', 'w') # set graph background default white
        # pg.setConfigOption('foreground', 'k') # set graph foreground default black

        # self.next_image = self.maia.next_image # image number to assign the next incoming array to
        # self.num_images = self.maia.get_num_images()

        # self.file_id = 0
        # self.user_variable = 0

        # self.init_UI()  # make the widgets
    
    def init_maia_thread(self):
        self.maia_thread = QThread()
        self.maia = MultiAtomImageAnalyser()
        self.maia.moveToThread(self.maia_thread)

        ## iGUI and MAIA communicate over signals and slots to ensure thread
        ## safety so connect the signals and slots here before starting the 
        ## MAIA.
        ## See https://stackoverflow.com/questions/35527439/

        self.signal_advance_image_count.connect(self.maia.advance_image_count)
        self.signal_send_new_rois.connect(self.maia.update_roi_coords)
        self.signal_send_maia_image.connect(self.maia.recieve_image)
        self.signal_set_num_roi_groups.connect(self.maia.update_num_roi_groups)
        self.signal_set_num_rois_per_group.connect(self.maia.update_num_rois_per_group)

        self.maia.signal_next_image_num.connect(self.recieve_next_image_num)
        self.maia.signal_draw_image.connect(self.draw_image)
        self.maia.signal_status_message.connect(self.status_bar_message)
        self.maia.signal_roi_coords.connect(self.recieve_roi_coords)
        self.maia.signal_num_roi_groups.connect(self.recieve_num_roi_groups)
        self.maia.signal_num_rois_per_group.connect(self.recieve_num_rois_per_group)
        
        # Start MAIA thread
        self.maia_thread.start()    

    def init_UI(self):
        """Create all of the widget objects required"""

        self.centre_widget = QWidget()
        self.centre_widget.layout = QVBoxLayout()
        self.centre_widget.setLayout(self.centre_widget.layout)
        self.setCentralWidget(self.centre_widget)

        layout_options = QHBoxLayout()
        layout_options.addWidget(QLabel('Current File ID:'))
        self.box_current_file_id = QLineEdit()
        self.box_current_file_id.setReadOnly(True)
        layout_options.addWidget(self.box_current_file_id)

        layout_options.addWidget(QLabel('User variables:'))
        self.box_user_variables = QLineEdit()
        self.box_user_variables.setReadOnly(True)
        layout_options.addWidget(self.box_user_variables)
        self.centre_widget.layout.addLayout(layout_options)

        layout_roi_options = QHBoxLayout()
        layout_roi_options.addWidget(QLabel('Number of ROI groups:'))
        self.box_number_roi_groups = QLineEdit()
        self.box_number_roi_groups.setValidator(int_validator)
        self.box_number_roi_groups.setText(str(1))
        self.box_number_roi_groups.editingFinished.connect(self.set_num_roi_groups)
        layout_roi_options.addWidget(self.box_number_roi_groups)

        layout_roi_options.addWidget(QLabel('Number of ROIs/group:'))
        self.box_number_rois = QLineEdit()
        self.box_number_rois.setValidator(int_validator)
        self.box_number_rois.setText(str(3))
        self.box_number_rois.editingFinished.connect(self.set_num_rois_per_group)
        layout_roi_options.addWidget(self.box_number_rois)

        self.button_lock_roi_groups = QCheckBox('Lock ROI group geometry to group 0')
        layout_roi_options.addWidget(self.button_lock_roi_groups)

        self.button_show_roi_details = QPushButton('Show ROI details')
        # self.button_clear_data.clicked.connect(self.clear_data)
        layout_roi_options.addWidget(self.button_show_roi_details)
        self.centre_widget.layout.addLayout(layout_roi_options)

        layout_image = QHBoxLayout()
        im_widget = pg.GraphicsLayoutWidget() # containing widget
        viewbox = im_widget.addViewBox() # plot area to display image
        self.im_canvas = pg.ImageItem() # the image
        viewbox.addItem(self.im_canvas)
        layout_image.addWidget(im_widget)

        layout_image_options = QFormLayout()
        self.box_number_images = QLineEdit()
        self.box_number_images.setValidator(int_validator)
        self.box_number_images.setText(str(2))
        # self.box_number_images.editingFinished.connect(self.update_num_images)
        layout_image_options.addRow('Number of images/run:', self.box_number_images)

        self.box_display_image_num = QLineEdit()
        self.box_display_image_num.setValidator(int_validator)
        self.box_display_image_num.setText(str(0))
        layout_image_options.addRow('display image #:',self.box_display_image_num)
        
        self.box_current_image_num = QLineEdit()
        self.box_current_image_num.setReadOnly(True)
        layout_image_options.addRow('current image #:',self.box_current_image_num)

        self.box_next_image_num = QLineEdit()
        self.box_next_image_num.setReadOnly(True)
        layout_image_options.addRow('next image #:',self.box_next_image_num)

        self.button_advance_image = QPushButton('Advance image count')
        self.button_advance_image.clicked.connect(self.signal_advance_image_count.emit)
        layout_image_options.addRow('',self.button_advance_image)
                
        self.button_test_image = QPushButton('Generate test image')
        self.button_test_image.clicked.connect(self.generate_test_image)
        layout_image_options.addRow('',self.button_test_image)

        self.button_update_rois = QPushButton('Update ROIs')
        self.button_update_rois.clicked.connect(self.update_rois)
        layout_image_options.addRow('',self.button_update_rois)

        layout_image.addLayout(layout_image_options)
        self.centre_widget.layout.addLayout(layout_image)

        layout_stefans = QVBoxLayout()
        layout_stefans.addWidget(QLabel('<h3>Simple Thus EFficient ANalysers (STEFANs)</h3>'))

        layout_stefans_options = QHBoxLayout()

        self.button_new_stefan = QPushButton('Launch new STEFAN')
        layout_stefans_options.addWidget(self.button_new_stefan)

        self.button_show_stefans = QPushButton('Show all STEFANs')
        layout_stefans_options.addWidget(self.button_show_stefans)

        self.button_destroy_stefans = QPushButton('Destroy all STEFANs')
        layout_stefans_options.addWidget(self.button_destroy_stefans)
        
        layout_stefans.addLayout(layout_stefans_options)
        self.centre_widget.layout.addLayout(layout_stefans)

        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)

    @pyqtSlot(str)
    def status_bar_error(self,message):
        self.status_bar.setStyleSheet('background-color : pink')
        time_str = datetime.now().strftime('%H:%M:%S')
        self.status_bar.showMessage('MAIA @ {}: {}'.format(time_str,message))
        print('MAIA @ {}: {}'.format(time_str,message))

    @pyqtSlot(str)
    def status_bar_message(self,message):
        self.status_bar.setStyleSheet('background-color : #EEEEBB')
        time_str = datetime.now().strftime('%H:%M:%S')
        self.status_bar.showMessage('MAIA @ {}: {}'.format(time_str,message))
        print('MAIA @ {}: {}'.format(time_str,message))

    def generate_test_image(self):
        image = np.random.rand(100,50)*1000
        atom = np.zeros_like(image)
        atom[30:32,30:32] = 2000
        image += atom
        self.signal_send_maia_image.emit(image)

    def update_rois(self,new_roi_coords=None):
        if new_roi_coords == False: # seems like button press is sending False so add this to fix
            new_roi_coords = None
        lock_to_group_zero = self.button_lock_roi_groups.isChecked()
        print('iGUI update ROIs:',new_roi_coords,lock_to_group_zero)
        self.signal_send_new_rois.emit(new_roi_coords,lock_to_group_zero)

    @pyqtSlot(np.ndarray,int)
    def draw_image(self,image,image_num):
        """Draws an image array in the main image window. The ROIs are then
        redrawn.

        Parameters
        ----------
        image : array
            The image to draw in array format.
        """
        print('image_num:',image_num)
        self.im_canvas.setImage(image)
        self.box_current_image_num.setText(str(image_num))

    @pyqtSlot(int)
    def recieve_next_image_num(self,next_image_num):
        self.box_next_image_num.setText(str(next_image_num))

    @pyqtSlot(list)
    def recieve_roi_coords(self,roi_coords):
        """Recieves new ROI coordinates from the MAIA and draws these on the
        image canvas.

        Parameters
        ----------
        roi_coords : list of list of list (see MAIA for format)
        """
        viewbox = self.im_canvas.getViewBox()
        for item in viewbox.allChildren(): # remove unused ROIs
            if ((type(item) == pg.graphicsItems.ROI.ROI or 
                    type(item) == pg.graphicsItems.TextItem.TextItem)):
                viewbox.removeItem(item)
        
        self.roi_boxes = []

        for group_num, group in enumerate(roi_coords):
            group_boxes = []
            for roi_num, [x,y,w,h] in enumerate(group):
                
                roi_box = pg.ROI([x,y],[w,h],translateSnap=True)
                roi_label = pg.TextItem('{}:{}'.format(group_num,roi_num), pg.intColor(roi_num), anchor=(0,1))
                font = QFont()
                font.setPixelSize(16)
                roi_label.setFont(font)
                roi_label.setPos(x+w//2,y+h//2) # in bottom left corner
                roi_box.setPen(pg.intColor(roi_num), width=3)
                viewbox.addItem(roi_box)
                viewbox.addItem(roi_label)
                roi_box.sigRegionChangeFinished.connect(self.set_rois_from_image)
                group_boxes.append(roi_box)
            self.roi_boxes.append(group_boxes)

    def set_rois_from_image(self):
        roi_coords = []
        for group in self.roi_boxes:
            group_coords = []
            for r in group:
                [x,y] = [int(x) for x in r.pos()]
                [w,h] = [int(x) for x in r.size()]
                group_coords.append([x,y,w,h])
            roi_coords.append(group_coords)
        self.update_rois(roi_coords)

    @pyqtSlot(int)
    def recieve_num_roi_groups(self,num_roi_groups):
        """Recieves the number of ROI groups from the MAIA and updates the 
        number in the GUI.

        Parameters
        ----------
        num_roi_groups : int
            The number of ROI groups in the MAIA.
        """
        self.box_number_roi_groups.setText(str(num_roi_groups))

    def set_num_roi_groups(self):
        """Sets the number of ROI groups in the MAIA with the number in the GUI.
        """
        num_roi_groups = int(self.box_number_roi_groups.text())
        if num_roi_groups < 1:
            num_roi_groups = 1
        self.signal_set_num_roi_groups.emit(num_roi_groups)

    @pyqtSlot(int)
    def recieve_num_rois_per_group(self,num_rois_per_group):
        """Recieves the number of ROIs per group from the MAIA and updates the 
        number in the GUI.

        Parameters
        ----------
        num_rois_per_group : int
            The number of ROIs per group in the MAIA.
        """
        self.box_number_rois.setText(str(num_rois_per_group))

    def set_num_rois_per_group(self):
        """Sets the number of ROI groups in the MAIA with the number in the GUI.
        """
        num_rois_per_group = int(self.box_number_rois.text())
        if num_rois_per_group < 1:
            num_rois_per_group = 1
        self.signal_set_num_rois_per_group.emit(num_rois_per_group)

def run():
    """Initiate an app to run the program
    if running in Pylab/IPython then there may already be an app instance"""
    app = QApplication.instance()
    standalone = app is None # false if there is already an app instance
    if standalone: # if there isn't an instance, make one
        app = QApplication(sys.argv) 
    
    main_win = ImagerGUI()
    main_win.show()
    if standalone: # if an app instance was made, execute it
        sys.exit(app.exec_()) # when the window is closed, the python code also stops

if __name__ == "__main__":
    # change directory to this file's location
    os.chdir(os.path.dirname(os.path.realpath(__file__))) 
    run()
