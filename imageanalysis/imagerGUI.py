"""Multi Atom Image Analysis Interface [imagerGUI (iGUI)]
Referred to as SIMON: Simple Image MONitoring in GUI, but iGUI throughout code.
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
from PyQt5.QtCore import pyqtSignal, QThread, pyqtSlot, Qt, QEvent, QRegularExpression
from PyQt5.QtGui import (QIcon, QDoubleValidator, QIntValidator, 
        QFont, QRegExpValidator, QColor, QRegularExpressionValidator)
from PyQt5.QtWidgets import (QActionGroup, QVBoxLayout, QMenu, 
        QFileDialog, QComboBox, QMessageBox, QLineEdit, QGridLayout, 
        QApplication, QPushButton, QAction, QMainWindow, QWidget,
        QLabel, QTabWidget, QInputDialog, QHBoxLayout, QTableWidget,
        QCheckBox, QFormLayout, QCheckBox, QStatusBar,QTableWidgetItem, 
        QSizePolicy,QAbstractScrollArea,QFileDialog)
if '..' not in sys.path: sys.path.append('..')
from strtypes import error, warning, info
import imageHandler as ih # process images to build up a histogram
import histoHandler as hh # collect data from histograms together
import fitCurve as fc   # custom class to get best fit parameters using curve_fit
from datetime import datetime
from copy import deepcopy

from multiAtomImageAnalyser import MultiAtomImageAnalyser
from stefan import StefanGUI
from roi_colors import get_group_roi_color
from helpers import convert_str_to_list
import resources


####    ####    ####    ####

# validators for user input
double_validator = QDoubleValidator() # floats
int_validator    = QIntValidator()    # integers
int_validator.setBottom(-1) # don't allow -ve numbers apart from -1
nat_validator    = QIntValidator()    # natural numbers 
nat_validator.setBottom(1) # > 0
non_neg_validator    = QIntValidator()    # integers
non_neg_validator.setBottom(0) # don't allow -ve numbers

non_neg_int_or_empty_string_regexp = QRegularExpression('(^[0-9]+$|^$)')
non_neg_int_or_empty_string_validator = QRegularExpressionValidator(non_neg_int_or_empty_string_regexp) # used so that an empty string still triggers editingFinished

int_or_empty_string_regexp = QRegularExpression('((^-?[1])|(^[0-9])+$|^$)')
int_or_empty_string_validator = QRegularExpressionValidator(int_or_empty_string_regexp) # used so that an empty string still triggers editingFinished

counts_plot_roi_offset = 0.2 # the +/- value that the counts plotting can use so that points don't all bunch up
stylesheet_read_only = 'QLineEdit {background-color: #DDDDDD}'

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
    
    signal_advance_image_count = pyqtSignal(object,object) # advances the image count in the MAIA
    signal_send_new_rois = pyqtSignal(object,bool) # new rois to send to coords. bool is whether to lock to group zero
    signal_send_new_num_images = pyqtSignal(object) # send new number of images to the MAIA
    signal_send_maia_image = pyqtSignal(np.ndarray,object,object)
    signal_send_emccd_bias =pyqtSignal(object) # send EMCCD bias to the controller and MAIA
    signal_set_num_roi_groups = pyqtSignal(object) # used to set the number of ROI groups
    signal_set_num_rois_per_group = pyqtSignal(object) # used to set the number of ROIs per group
    signal_request_maia_data = pyqtSignal(int) # request all data from MAIA for use in STEFANs
    signal_tv_data_refresh = pyqtSignal() # requests an information update for the Threshold Viewer from MAIA
    signal_tv_data_to_maia = pyqtSignal(list) # sends updated threshold data from the TV back to MAIA
    signal_send_results_path = pyqtSignal(str) # sends results path to MAIA
    signal_send_hist_id = pyqtSignal(int) # sends hist ID to MAIA
    signal_send_file_id = pyqtSignal(int) # sends the file ID to MAIA
    signal_send_user_variables = pyqtSignal(list) # sends user variables to MAIA
    signal_send_measure_prefix = pyqtSignal(str) # sends the measure prefix to MAIA
    signal_save = pyqtSignal(object) # asks MAIA to save the data when the queue is empty
    signal_clear_data_and_queue = pyqtSignal() # asks MAIA to immediately clear its data and queue
    signal_get_state = pyqtSignal(dict,str) # asks MAIA to get its current state and send it back
    signal_set_state = pyqtSignal(dict) # asks MAIA to set the state parameters
    signal_cleanup = pyqtSignal() # connects the close event to the cleanup function if the iGUI is the main window
    signal_add_request_to_queue = pyqtSignal(str) # adds a request to the MAIA queue to be processed with the image queue
    signal_set_rearr_images = pyqtSignal(list) # sends rearrangement image indicies back to the controller

    def __init__(self, num_images=2, results_path='.', hist_id=0, file_id=2000, user_variables=[0], measure_prefix='Measure0'):
        super().__init__()
        self.name = 'SIMON: Simple Image MONitoring'  # name is displayed in the window title
        self.setWindowTitle(self.name)

        self.init_UI()
        self.init_maia_thread()

        self.stefans = []
        self.rearr_images = []
        self.tv = None # ThresholdViewer

        self.update_rois()

        self.set_results_path(results_path)
        self.set_hist_id(hist_id)
        self.set_file_id(file_id)
        self.set_user_variables(user_variables)
        self.set_measure_prefix(measure_prefix)

        self.update_num_images(num_images)
        self.set_num_roi_groups()
        self.set_num_rois_per_group()
        self.update_emccd_bias(670)
        self.update_rearr_images()

    def closeEvent(self, event):
        """Processing performed when the iGUI window is closed. This calls 
        the events for iGUI cleanup iff the iGUI window is the main 
        application.
        """
        self.signal_cleanup.emit()

    def cleanup(self):
        """Events to do when this main window is closed. This only fires 
        if the self.signal_cleanup is connected at runtime (to avoid this 
        firing in the usual PyDex methods)."""
        self.destroy_all_stefans()
        self.maia_thread.quit()
        self.destroy_threshold_viewer()
        self.debug = None

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
        self.signal_send_emccd_bias.connect(self.maia.update_emccd_bias)
        self.signal_request_maia_data.connect(self.maia.recieve_data_request)
        self.signal_tv_data_refresh.connect(self.maia.recieve_tv_data_request)
        self.signal_tv_data_to_maia.connect(self.maia.recieve_tv_threshold_data)
        self.signal_send_new_num_images.connect(self.maia.update_num_images)
        self.signal_send_results_path.connect(self.maia.update_results_path)
        self.signal_send_hist_id.connect(self.maia.update_hist_id)
        self.signal_send_file_id.connect(self.maia.update_file_id)
        self.signal_send_user_variables.connect(self.maia.update_user_variables)
        self.signal_send_measure_prefix.connect(self.maia.update_measure_prefix)
        self.signal_save.connect(self.maia.request_save)
        self.signal_clear_data_and_queue.connect(self.maia.clear_data_and_queue)
        self.signal_get_state.connect(self.maia.get_state)
        self.signal_set_state.connect(self.maia.set_state)
        self.signal_add_request_to_queue.connect(self.maia.add_request_to_queue)

        self.maia.signal_file_id.connect(self.recieve_file_id_from_maia)
        self.maia.signal_next_image_num.connect(self.recieve_next_image_num)
        self.maia.signal_draw_image.connect(self.draw_image)
        self.maia.signal_status_message.connect(self.status_bar_message)
        self.maia.signal_roi_coords.connect(self.recieve_roi_coords)
        self.maia.signal_num_roi_groups.connect(self.recieve_num_roi_groups)
        self.maia.signal_num_rois_per_group.connect(self.recieve_num_rois_per_group)
        self.maia.signal_emccd_bias.connect(self.recieve_emccd_bias)
        self.maia.signal_data_for_stefan.connect(self.recieve_maia_data_for_stefan)
        self.maia.signal_data_for_tv.connect(self.recieve_maia_data_for_tv)
        self.maia.signal_num_images.connect(self.recieve_num_images)
        self.maia.signal_results_path.connect(self.recieve_results_path)
        self.maia.signal_hist_id.connect(self.recieve_hist_id)
        self.maia.signal_user_variables.connect(self.recieve_user_variables)
        self.maia.signal_measure_prefix.connect(self.recieve_measure_prefix)
        self.maia.signal_state.connect(self.save_state) # generally will be disconnected in favour of PyDex controller

        # Start MAIA thread
        self.maia_thread.start()

    def init_UI(self):
        """Create all of the widget objects required"""

        self.centre_widget = QWidget()
        self.centre_widget.layout = QVBoxLayout()
        self.centre_widget.setLayout(self.centre_widget.layout)
        self.setCentralWidget(self.centre_widget)

        layout_save_locations = QHBoxLayout()
        layout_save_locations.addWidget(QLabel('Results path:'))
        self.box_results_path = QLineEdit()
        self.box_results_path.setReadOnly(True)
        self.box_results_path.setStyleSheet(stylesheet_read_only)
        layout_save_locations.addWidget(self.box_results_path)

        layout_save_locations.addWidget(QLabel('Measure prefix:'))
        self.box_measure_prefix = QLineEdit()
        self.box_measure_prefix.setReadOnly(True)
        self.box_measure_prefix.setStyleSheet(stylesheet_read_only)
        layout_save_locations.addWidget(self.box_measure_prefix)

        self.centre_widget.layout.addLayout(layout_save_locations)

        layout_options = QHBoxLayout()

        layout_options.addWidget(QLabel('Hist. ID:'))
        self.box_hist_id = QLineEdit()
        self.box_hist_id.setReadOnly(True)
        self.box_hist_id.setStyleSheet(stylesheet_read_only)
        # self.box_hist_id.setEnabled(True)
        layout_options.addWidget(self.box_hist_id)

        layout_options.addWidget(QLabel('Current File ID:'))
        self.box_current_file_id = QLineEdit()
        self.box_current_file_id.setReadOnly(True)
        self.box_current_file_id.setStyleSheet(stylesheet_read_only)
        layout_options.addWidget(self.box_current_file_id)

        layout_options.addWidget(QLabel('User variables:'))
        self.box_user_variables = QLineEdit()
        self.box_user_variables.setReadOnly(True)
        self.box_user_variables.setStyleSheet(stylesheet_read_only)
        layout_options.addWidget(self.box_user_variables)
        self.centre_widget.layout.addLayout(layout_options)

        layout_roi_options = QHBoxLayout()
        layout_roi_options.addWidget(QLabel('Number of ROI groups:'))
        self.box_number_roi_groups = QLineEdit()
        self.box_number_roi_groups.setValidator(non_neg_int_or_empty_string_validator)
        self.box_number_roi_groups.setText(str(3))
        self.box_number_roi_groups.editingFinished.connect(self.set_num_roi_groups)
        layout_roi_options.addWidget(self.box_number_roi_groups)

        layout_roi_options.addWidget(QLabel('Number of ROIs/group:'))
        self.box_number_rois = QLineEdit()
        self.box_number_rois.setValidator(non_neg_int_or_empty_string_validator)
        self.box_number_rois.setText(str(2))
        self.box_number_rois.editingFinished.connect(self.set_num_rois_per_group)
        layout_roi_options.addWidget(self.box_number_rois)

        self.button_lock_roi_groups = QCheckBox('Lock ROI group geometry to group 0')
        self.button_lock_roi_groups.clicked.connect(self.update_rois)
        layout_roi_options.addWidget(self.button_lock_roi_groups)

        self.button_show_roi_details = QPushButton('Show Threshold Viewer')
        self.button_show_roi_details.clicked.connect(self.create_threshold_viewer)
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
        self.box_number_images.setValidator(non_neg_int_or_empty_string_validator)
        self.box_number_images.setText(str(2))
        self.box_number_images.editingFinished.connect(self.update_num_images)
        layout_image_options.addRow('Number of images/run:', self.box_number_images)

        self.box_display_image_num = QLineEdit()
        self.box_display_image_num.setValidator(int_or_empty_string_validator)
        self.box_display_image_num.setText(str(0))
        layout_image_options.addRow('display image #:',self.box_display_image_num)
        
        self.box_current_image_num = QLineEdit()
        self.box_current_image_num.setReadOnly(True)
        self.box_current_image_num.setStyleSheet(stylesheet_read_only)
        layout_image_options.addRow('current image #:',self.box_current_image_num)

        self.box_next_image_num = QLineEdit()
        self.box_next_image_num.setReadOnly(True)
        self.box_next_image_num.setStyleSheet(stylesheet_read_only)
        layout_image_options.addRow('next image #:',self.box_next_image_num)

        self.button_advance_image = QPushButton('Advance image count')
        self.button_advance_image.clicked.connect(self.advance_image_count)
        layout_image_options.addRow('',self.button_advance_image)

        self.box_emccd_bias = QLineEdit()
        self.box_emccd_bias.setValidator(double_validator)
        # self.box_emccd_bias.setText(600)
        self.box_emccd_bias.editingFinished.connect(self.update_emccd_bias)
        layout_image_options.addRow('EMCCD bias',self.box_emccd_bias)

        self.box_rearr_images = QLineEdit()
        self.box_rearr_images.editingFinished.connect(self.update_rearr_images)
        layout_image_options.addRow('Rearr. images:',self.box_rearr_images)

        self.button_debug = QPushButton('Show Debug Window')
        self.button_debug.clicked.connect(self.create_debug_window)
        layout_image_options.addRow('',self.button_debug)

        layout_image.addLayout(layout_image_options)
        self.centre_widget.layout.addLayout(layout_image)

        layout_stefans = QVBoxLayout()
        layout_stefans.addWidget(QLabel('<h3>Simple Thus EFficient ANalysers (STEFANs)</h3>'))

        layout_stefans_options = QHBoxLayout()

        self.button_new_stefan = QPushButton('Launch new STEFAN')
        self.button_new_stefan.clicked.connect(self.launch_new_stefan)
        layout_stefans_options.addWidget(self.button_new_stefan)

        self.button_update_stefans = QPushButton('Update all STEFANs')
        self.button_update_stefans.clicked.connect(self.update_all_stefans)
        layout_stefans_options.addWidget(self.button_update_stefans)

        self.button_show_stefans = QPushButton('Show all STEFANs')
        self.button_show_stefans.clicked.connect(self.show_all_stefans)
        layout_stefans_options.addWidget(self.button_show_stefans)

        self.button_destroy_stefans = QPushButton('Destroy all STEFANs')
        self.button_destroy_stefans.clicked.connect(self.destroy_all_stefans)
        layout_stefans_options.addWidget(self.button_destroy_stefans)
        
        layout_stefans.addLayout(layout_stefans_options)
        self.centre_widget.layout.addLayout(layout_stefans)

        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)

    def set_results_path(self,results_path):
        """Forwards a results path to MAIA to be set."""
        self.signal_send_results_path.emit(results_path)

    def advance_image_count(self,file_id=None,image_num=None):
        """Requests the MAIA to update the File ID and image count. None can
        be passed for either value to let MAIA iterate from the values it 
        already has stored, otherwise it will iterate from the specified 
        values."""
        self.signal_advance_image_count.emit(file_id,image_num)

    def update_rearr_images(self,rearr_images=None):
        """Updates the rearrangement images and then passes this number back
        to the PyDex controller so that it know which images to send to 
        ALEX."""
        if rearr_images is None:
            rearr_images = self.box_rearr_images.text()
        try:
            rearr_images = convert_str_to_list(rearr_images,raise_exception_if_empty=False)
            rearr_images = [int(x) for x in rearr_images]
            rearr_images = list(dict.fromkeys(rearr_images))
        except:
            self.box_rearr_images.setText(str(self.rearr_images))
        else:
            if self.rearr_images != rearr_images:
                self.rearr_images = rearr_images
                self.signal_set_rearr_images.emit(self.rearr_images)
            self.box_rearr_images.setText(str(self.rearr_images))
    
    @pyqtSlot(str)
    def recieve_results_path(self,results_path):
        """Recieves the results path from MAIA to set in the GUI."""
        self.box_results_path.setText(results_path)

    def set_hist_id(self,hist_id):
        """Forwards a hist ID to MAIA to be set. The hist ID is used when 
        saving the files. In runid.py > runnum it is called runnum._n."""
        self.signal_send_hist_id.emit(hist_id)
    
    @pyqtSlot(int)
    def recieve_hist_id(self,hist_id):
        """Recieves the hist ID from MAIA to set in the GUI."""
        self.box_hist_id.setText(str(hist_id))

    def set_user_variables(self,user_variables):
        """Forwards the user variables to MAIA to be set. The hist ID is used 
        when saving the files."""
        self.signal_send_user_variables.emit(user_variables)
    
    @pyqtSlot(list)
    def recieve_user_variables(self,user_variables):
        """Recieves the user variables from MAIA to set in the GUI."""
        self.box_user_variables.setText(str(user_variables))

    def set_measure_prefix(self,measure_prefix):
        """Forwards a measure prefix to MAIA to be set. The is for display 
        purposes only."""
        self.signal_send_measure_prefix.emit(measure_prefix)
    
    @pyqtSlot(str)
    def recieve_measure_prefix(self,measure_prefix):
        """Recieves the measure prefix from MAIA to set in the GUI."""
        self.box_measure_prefix.setText(str(measure_prefix))


    @pyqtSlot(str)
    def status_bar_error(self,message):
        self.status_bar.setStyleSheet('background-color : pink')
        time_str = datetime.now().strftime('%H:%M:%S')
        self.status_bar.showMessage('MAIA @ {}: {}'.format(time_str,message))
        print('MAIA @ {}: {}'.format(time_str,message))

    @pyqtSlot(str)
    def status_bar_message(self,message):
        self.status_bar.setStyleSheet('background-color : #BBCCEE')
        time_str = datetime.now().strftime('%H:%M:%S')
        self.status_bar.showMessage('MAIA @ {}: {}'.format(time_str,message))
        print('MAIA @ {}: {}'.format(time_str,message))

    def generate_test_image(self):
        atom_xs = [1,10,20,30]
        atom_ys = [1,10,20,30]
        for _ in range(100):
            image = np.random.rand(100,50)*1000
            atoms = np.zeros_like(image)
            for x in atom_xs:
                for y in atom_ys:
                    if np.random.random_sample() > 0.5:
                        atoms[x:x+2,y:y+2] = 2000
            image += atoms
            self.recieve_image(image)

    def update_rois(self,new_roi_coords=None):
        if type(new_roi_coords) is bool: # button presses send their boolean in the signal so ignore this
            new_roi_coords = None
        lock_to_group_zero = self.button_lock_roi_groups.isChecked()
        print('iGUI update ROIs:',new_roi_coords,lock_to_group_zero)
        self.signal_send_new_rois.emit(new_roi_coords,lock_to_group_zero)

    def update_num_images(self,new_num_images=None):
        if new_num_images is None:
            try:
                new_num_images = int(self.box_number_images.text())
                if new_num_images < 0:
                    new_num_images = 0
            except ValueError:
                print('num images "{}" is not valid'.format(self.box_number_images.text()))
                new_num_images = None
        self.signal_send_new_num_images.emit(new_num_images)

    @pyqtSlot(int)
    def recieve_num_images(self,num_images):
        self.box_number_images.setText(str(num_images))

    def recieve_image(self,image,file_id=None,image_num=None):
        """Recieves an image from the rest of PyDex and forwards it to the 
        MAIA. The file ID and image number can be manually specified 
        or can just be left as None to let the MAIA assign the file ID 
        and image number."""
        print('iGUI recieved image: file_id, image_num =',file_id,image_num)
        self.signal_send_maia_image.emit(image,file_id,image_num)

    def get_draw_image_num(self):
        """Returns the image number that the iGUI should show. Sets to -1 
        (show all images) if there is not a valid number in the box."""
        try:
            draw_image_num = int(self.box_display_image_num.text())
        except ValueError: # not a valid number in the box
            self.box_display_image_num.setText(str(-1))
            draw_image_num = int(self.box_display_image_num.text())
        return draw_image_num


    @pyqtSlot(np.ndarray,int)
    def draw_image(self,image,image_num):
        """Draws an image array in the main image window. The ROIs are then
        redrawn. Only draws the image if the correct index is displayed in 
        the GUI. Set to -1 to draw all images.

        Parameters
        ----------
        image : array
            The image to draw in array format.
        image_num : int
            The index of the image, used to decide whether it is drawn in the 
            GUI or not.
        """
        draw_image_num = self.get_draw_image_num()
        if (image_num == draw_image_num) or (draw_image_num < 0):
            self.im_canvas.setImage(image)
        self.box_current_image_num.setText(str(image_num))

    def set_file_id(self,file_id):
        self.signal_send_file_id.emit(file_id)

    @pyqtSlot(int)
    def recieve_file_id_from_maia(self,file_id):
        self.box_current_file_id.setText(str(file_id))

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
                
                color = get_group_roi_color(group_num,roi_num)
                roi_box = pg.ROI([x,y],[w,h],translateSnap=True)
                roi_label = pg.TextItem('{}:{}'.format(group_num,roi_num), color, anchor=(0.5,1))
                font = QFont()
                font.setPixelSize(16)
                roi_label.setFont(font)
                roi_label.setPos(x+w//2,y+h) # in bottom left corner
                if (self.button_lock_roi_groups.isChecked()) and (roi_num*group_num != 0):
                    roi_box.setPen(color, width=1)
                else:
                    roi_box.setPen(color, width=3)
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
        try:
            num_roi_groups = int(self.box_number_roi_groups.text())
            if num_roi_groups < 1:
                num_roi_groups = 1
        except ValueError: # invalid value in box
            num_roi_groups = None
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
        try:
            num_rois_per_group = int(self.box_number_rois.text())
            if num_rois_per_group < 1:
                num_rois_per_group = 1
        except ValueError: # invalid value in box
            num_rois_per_group = None
        self.signal_set_num_rois_per_group.emit(num_rois_per_group)

    def update_emccd_bias(self,new_emccd_bias=None):
        if new_emccd_bias is None:
            try:
                new_emccd_bias = int(self.box_emccd_bias.text())
            except ValueError:
                print('EMCCD bias "{}" is not valid'.format(self.box_emccd_bias.text()))
                new_emccd_bias = None
        self.signal_send_emccd_bias.emit(new_emccd_bias)

    @pyqtSlot(int)
    def recieve_emccd_bias(self,emccd_bias):
        self.box_emccd_bias.setText(str(emccd_bias))

    def save(self,hist_id=None):
        """Sends save request to MAIA.
        
        Parameters
        ----------
        hist_id : int or None
            The file ID to save the data to. MAIA _should_ already know this,
            but this can be respecified to ensure that nothing gets out of
            sync.
        """
        self.signal_save.emit(hist_id)
    
    def clear_data_and_queue(self):
        """Requests MAIA immediately clears all its data and queue. This 
        function should only really be used if a multirun is cancelled. 
        Normally data will be cleared once MAIA has finished saving it.
        """
        self.signal_clear_data_and_queue.emit()

    def add_request_to_queue(self,request):
        """Adds a request to MAIA that will be processed in the queue. This
        means that the request will be carried in the order it was recieved
        (i.e. after any images that came before it). This prevents situations
        where the queue was occupied but the request was processed first.
        
        Parameters
        request : ['clear']
            The request MAIA should carry out.
        """
        self.signal_add_request_to_queue.emit(request)

    #%% state saving/loading methods
    def request_get_state(self,filename=''):
        """Requests the MAIA to return its state information that will then
        be saved by the iGUI when the get_state_from_maia is called.
        
        Parameters
        ----------
        filename : str
            The filename that the state should be saved to. This will be 
            passed back to the state saving function.
        """
        params = {}
        params['draw_image_num'] = self.get_draw_image_num()
        params['lock_roi_groups'] = int(self.button_lock_roi_groups.isChecked())
        print(params)
        self.signal_get_state.emit(params,filename)
        
    @pyqtSlot(dict,str)
    def save_state(self,state,filename):
        """Gets a state from MAIA and saves it in the specified location. This
        function will be disconnected in favor of the PyDex save_state function
        when using the full PyDex program. It currently does nothing when 
        just running the iGUI alone.

        Parameters
        ----------
        state : list
            MAIA state as returned by self.maia.get_state
        filename : str
            The filename to store the state to.
        """
        print('iGUI recieved state {} to be stored to {}'.format(state,filename))

    def set_state(self,params):
        """Sets the state of the iGUI and MAIA with the MAIA state dictionary.
        """
        self.box_display_image_num.setText(str(params['draw_image_num']))
        self.button_lock_roi_groups.setChecked(params['lock_roi_groups'])
        self.signal_set_state.emit(params)

    #%% iGUI <-> Stefan methods
    def status_bar_stefan_message(self,message,stefan_index=None):
        if stefan_index == None:
            stefan_index = '?'
        self.status_bar.setStyleSheet('background-color : #CCDDAA')
        time_str = datetime.now().strftime('%H:%M:%S')
        self.status_bar.showMessage('STEFAN {} @ {}: {}'.format(stefan_index,time_str,message))
        print('STEFAN {} @ {}: {}'.format(stefan_index,time_str,message))

    def launch_new_stefan(self):
        """Creates a new STEFAN"""
        stefan = StefanGUI(self,len(self.stefans))
        stefan.show()
        self.stefans.append(stefan)

    def update_all_stefans(self):
        """Forces all STEFANs (shown or hidden) to request an update."""
        # [stefan.request_update() for stefan in self.stefans]
        for stefan_index,_ in enumerate(self.stefans):
            self.signal_request_maia_data.emit(stefan_index)

    def show_all_stefans(self):
        """Forces all STEFANs to redisplay on the GUI."""
        [stefan.show() for stefan in self.stefans]

    def destroy_all_stefans(self):
        """Destroys all open STEFANs."""
        self.stefans = []
    
    def recieve_stefan_data_request(self,stefan):
        stefan_index = self.stefans.index(stefan)
        # self.status_bar_stefan_message('Requested MAIA data.',stefan_index)
        self.signal_request_maia_data.emit(stefan_index)

    @pyqtSlot(list,int)
    def recieve_maia_data_for_stefan(self,counts,stefan_index):
        stefan = self.stefans[stefan_index]
        stefan.update(counts)

    #%% iGUI <-> ThresholdViewer methods
    def create_threshold_viewer(self):
        self.tv = ThresholdViewer(self)
        self.tv.show()
    
    def destroy_threshold_viewer(self):
        self.tv = None

    def tv_request_data_refresh(self):
        """Triggered by the Threshold Viewer to request an update on the 
        threshold information from the MAIA."""
        self.signal_tv_data_refresh.emit()
    
    @pyqtSlot(list)
    def recieve_maia_data_for_tv(self,threshold_data):
        try:
            self.tv.recieve_maia_threshold_data(threshold_data)
        except AttributeError: # threshold viewer no longer exists
            pass

    def tv_send_data_to_maia(self,threshold_data):
        """Recieves threshold data from the Threshold Viewer and sends it to
        the MAIA."""
        self.signal_tv_data_to_maia.emit(threshold_data)

    #%% iGUI <-> DebugWindow functions
    def create_debug_window(self):
        self.debug = DebugWindow(self)
        self.debug.show()

    #%% legacy functions used elsewhere in PyDex that were stored in the old settings_window
    def try_browse(self, title='Select a File', file_type='all (*)', 
                   open_func=QFileDialog.getOpenFileName, defaultpath='.'):
        """Opens a file dialog and retrieves a file name from the browser.
        This function is taken from the old SettingsWindow class and is used 
        when navigating for new camera parameters.

        Parameters
        ----------
        title : string
            String to display at the top of the file browser window
        defaultpath : string
            directory to open first
        file_type : string
            types of files that can be selected
        open_func : function
            the function to use to open the file browser
        """
        try:
            if 'PyQt4' in sys.modules:
                file_name = open_func(self, title, defaultpath, file_type)
            elif 'PyQt5' in sys.modules:
                file_name, _ = open_func(self, title, defaultpath, file_type)
            if type(file_name) == str: self.last_path = file_name 
            return file_name
        except OSError: return '' # probably user cancelled

class ThresholdViewer(QMainWindow):
    """Class to view the thresholds of the ROIs. Launched from the iGUI when
    the 'Show Thresholds' button pressed. Runs in the same thread as the 
    iGUI because it is only a display widget.
    """
    name = 'Threshold Viewer'

    def __init__(self,imagerGUI):
        super().__init__()
        self.setWindowTitle(self.name)
        self.iGUI = imagerGUI

        self.manualthresh_icon = QIcon(":manualthresh.svg")
        self.autothresh_icon = QIcon(":autothresh.svg")

        self.init_UI()
        self.refresh()

    def init_UI(self):
        self.centre_widget = QWidget()
        self.centre_widget.layout = QVBoxLayout()
        self.centre_widget.setLayout(self.centre_widget.layout)
        self.setCentralWidget(self.centre_widget)

        self.button_refresh = QPushButton('Refresh')
        self.button_refresh.clicked.connect(self.refresh)
        self.centre_widget.layout.addWidget(self.button_refresh)

        self.centre_widget.layout.addWidget(QLabel('ROIs sorted by ROI index. IDs are group:ROI.'))
        self.centre_widget.layout.addWidget(QLabel('Right click to toggle Autothresh or Manualthresh.'))

        self.button_show_only_group_zero = QCheckBox('Copy group 0 settings across groups')
        self.centre_widget.layout.addWidget(self.button_show_only_group_zero)
        self.button_show_only_group_zero.stateChanged.connect(self.toggle_show_only_group_zero)

        self.table = QTableWidget()
        self.table.itemChanged.connect(self.get_data_from_table)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self.table_right_clicked)
        self.centre_widget.layout.addWidget(self.table)

        self.button_toggle_all_autothresh = QPushButton('Toggle all Autothresh')
        self.button_toggle_all_autothresh.clicked.connect(self.toggle_all_autothresh)
        self.centre_widget.layout.addWidget(self.button_toggle_all_autothresh)

        self.button_update = QPushButton('Send to MAIA')
        self.button_update.clicked.connect(self.update)
        self.centre_widget.layout.addWidget(self.button_update)

        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)

    def status_bar_message(self,message):
        self.status_bar.setStyleSheet('background-color : #EEEEBB')
        time_str = datetime.now().strftime('%H:%M:%S')
        self.status_bar.showMessage('{}: {}'.format(time_str,message))
        print('TV @ {}: {}'.format(time_str,message))

    def refresh(self):
        """Sends a request to the MAIA via the iGUI to get the latest 
        information about the ROIs that exist and their current thresholds."""
        self.status_bar_message('Requesting information update from MAIA')
        self.iGUI.tv_request_data_refresh()

    def recieve_maia_threshold_data(self,data):
        """Processing to be performed after the MAIA has send back the 
        threshold data. This involves populating the table."""
        self.status_bar_message('Recieved threshold data from MAIA')
        print(data)
        self.data = data[0]
        self.copy_im_data = ['' if x is None else str(x) for x in data[1]]
        print('TV recieved copy_image data',self.copy_im_data)
        self.populate_table_with_data()

    def toggle_show_only_group_zero(self):
        """After showing/hiding all other groups, the data is recollected 
        from the table to overwrite any groups with data different to group
        zero."""
        self.populate_table_with_data()
        self.get_data_from_table()

    def populate_table_with_data(self):
        """Get the data from the threshold viewer data table and sends it 
        back to iGUI to be saved or for the thresholds to be updated."""
        data = self.data
        self.table.blockSignals(True) # don't want signalling to happen whilst we're populating the table
        self.table.clear()

        self.num_roi_groups = len(data)
        self.num_rois_per_group = len(data[0])
        self.num_images = len(data[0][0])
        
        data_sorted_by_roi = list(map(list, zip(*data))) # transpose the data array to sort it by ROI rather than ROI group

        if self.button_show_only_group_zero.isChecked():
            self.table.setRowCount(self.num_rois_per_group+1)
        else:
            self.table.setRowCount(self.num_roi_groups*self.num_rois_per_group+1)
        self.table.setColumnCount(self.num_images)

        horizontal_headers = ['Image {}'.format(i) for i in range(self.num_images)]
        self.table.setHorizontalHeaderLabels(horizontal_headers)

        vertical_header_labels = []
        roi_data = data_sorted_by_roi[0][0]
        for image_num, copy_im_number in enumerate(self.copy_im_data):
            newVal = QTableWidgetItem(str(copy_im_number))
            newVal.setBackground(QColor('lightGray'))
            self.table.setItem(0, image_num, newVal)
        vertical_header_labels.append('Copy Im')

        for roi_num, roi in enumerate(data_sorted_by_roi):
            for group_num, roi_data in enumerate(roi):
                if (self.button_show_only_group_zero.isChecked()) and (group_num != 0):
                    continue
                for image_num, threshold_data in enumerate(roi_data):
                    # newVal = QTableWidgetItem(str('{}:{} Im{}'.format(group_num,roi_num,image_num)))
                    newVal = QTableWidgetItem(str(threshold_data[0]))
                    if threshold_data[1]: # autothresh is enabled
                        newVal.setIcon(self.autothresh_icon)
                    else:
                        newVal.setIcon(self.manualthresh_icon)
                    newVal.setBackground(QColor(get_group_roi_color(group_num,roi_num)))
                    self.table.setItem(self.get_table_index(group_num,roi_num), image_num, newVal)
                vertical_header_labels.append('{}:{}'.format(group_num,roi_num))
        self.table.setVerticalHeaderLabels(vertical_header_labels)

        self.table.blockSignals(False)

    def get_table_index(self,group_num,roi_num):
        """Returns the index corresponding to the correct row in the table for 
        given group and ROI indicies.
        """
        if self.button_show_only_group_zero.isChecked():
            return roi_num + 1
        else:
            return roi_num*self.num_roi_groups+group_num + 1

    def get_roi_group_nums_from_index(self,index):
        index = index - 1 # remove copy im row
        if self.button_show_only_group_zero.isChecked():
            group_num = 0
            roi_num = index
        else:
            group_num = index % self.num_roi_groups
            roi_num = index // self.num_roi_groups
        return group_num, roi_num

    def get_data_from_table(self):
        new_data = deepcopy(self.data)
        
        self.copy_im_data = [self.table.item(0,image).text() for image in range(self.num_images)]

        for group in range(self.num_roi_groups):
            for roi in range(self.num_rois_per_group):
                for image in range(self.num_images):
                    if self.button_show_only_group_zero.isChecked():
                        table_index = self.get_table_index(0,roi)
                        autothresh = self.data[0][roi][image][1]
                    else:
                        table_index = self.get_table_index(group,roi)
                        autothresh = self.data[group][roi][image][1]
                    try:
                        value = round(float(self.table.item(table_index,image).text()))
                    except ValueError:
                        self.populate_table_with_data() # ignore the new data if a value is invalid
                        return
                    new_data[group][roi][image][0] = value
                    new_data[group][roi][image][1] = autothresh
        self.data = new_data
        self.populate_table_with_data()
        self.button_update.setStyleSheet('background-color: #BBCCEE')

    def table_right_clicked(self):
        image_num = self.table.currentColumn()
        group_num, roi_num = self.get_roi_group_nums_from_index(self.table.currentRow())
        # print('right clicked {}:{} Im{}'.format(group_num,roi_num,image_num))
        self.set_autothresh(group_num,roi_num,image_num)
        self.populate_table_with_data()

    def set_autothresh(self,group_num,roi_num,image_num,value=None):
        if value == None:
            self.data[group_num][roi_num][image_num][1] = not self.data[group_num][roi_num][image_num][1]
        else:
            self.data[group_num][roi_num][image_num][1] = value

    def toggle_all_autothresh(self):
        value = not self.data[0][0][0][1]
        for group_num in range(self.num_roi_groups):
            for roi_num in range(self.num_rois_per_group):
                for image_num in range(self.num_images):
                    self.set_autothresh(group_num,roi_num,image_num,value)
        self.populate_table_with_data()

    def update(self):
        self.get_data_from_table() # forces the copy settings across groups checkbox to be updated
        self.iGUI.tv_send_data_to_maia([self.data,self.copy_im_data])
        self.status_bar_message('Sent threshold data to MAIA')
        self.button_update.setStyleSheet('')
        # self.iGUI.destroy_threshold_viewer()

class DebugWindow(QMainWindow):
    """Class to allow simple debugging of the iGUI by triggering commands that 
    will come from the rest of Pydex when needed.
    """

    def __init__(self,imagerGUI):
        super().__init__()
        self.name = 'Debug Window'
        self.setWindowTitle(self.name)
        self.iGUI = imagerGUI

        self.init_UI()

    def init_UI(self):
        self.centre_widget = QWidget()
        self.centre_widget.layout = QVBoxLayout()
        self.centre_widget.setLayout(self.centre_widget.layout)
        self.setCentralWidget(self.centre_widget)

        self.button_set_results_path = QPushButton('Set results path')
        self.button_set_results_path.clicked.connect(self.set_test_results_path)
        self.centre_widget.layout.addWidget(self.button_set_results_path)

        self.button_set_hist_id = QPushButton('Set hist. ID')
        self.button_set_hist_id.clicked.connect(self.set_test_hist_id)
        self.centre_widget.layout.addWidget(self.button_set_hist_id)

        self.button_set_file_id = QPushButton('Set file ID')
        self.button_set_file_id.clicked.connect(self.set_test_file_id)
        self.centre_widget.layout.addWidget(self.button_set_file_id)

        self.button_set_user_variables = QPushButton('Set user variables')
        self.button_set_user_variables.clicked.connect(self.set_test_user_variables)
        self.centre_widget.layout.addWidget(self.button_set_user_variables)

        self.button_set_measure_prefix = QPushButton('Set measure prefix')
        self.button_set_measure_prefix.clicked.connect(self.set_test_measure_prefix)
        self.centre_widget.layout.addWidget(self.button_set_measure_prefix)

        self.button_test_image = QPushButton('Generate 100 test images')
        self.button_test_image.clicked.connect(self.iGUI.generate_test_image)
        self.centre_widget.layout.addWidget(self.button_test_image)

        self.button_update_rois = QPushButton('Update ROIs')
        self.button_update_rois.clicked.connect(self.iGUI.update_rois)
        self.centre_widget.layout.addWidget(self.button_update_rois)

        self.button_save_data = QPushButton('Save data')
        self.button_save_data.clicked.connect(self.save)
        self.centre_widget.layout.addWidget(self.button_save_data)

        self.button_clear_data_and_queue = QPushButton('Clear data and queue')
        self.button_clear_data_and_queue.clicked.connect(self.iGUI.clear_data_and_queue)
        self.centre_widget.layout.addWidget(self.button_clear_data_and_queue)

        self.button_save_state = QPushButton('Save state')
        self.button_save_state.clicked.connect(self.save_state)
        self.centre_widget.layout.addWidget(self.button_save_state)

    def set_test_results_path(self):
        self.iGUI.set_results_path(r'Z:\Tweezer\People\Dan\code\pydex test dump')

    def set_test_hist_id(self):
        self.iGUI.set_hist_id(7)

    def set_test_file_id(self):
        self.iGUI.set_file_id(1998)

    def set_test_user_variables(self):
        self.iGUI.set_user_variables([200,100,50])

    def set_test_measure_prefix(self):
        self.iGUI.set_measure_prefix('Measure18')

    def save(self):
        self.iGUI.save()
    
    def save_state(self):
        self.iGUI.request_get_state('')

def run():
    """Initiate an app to run the program
    if running in Pylab/IPython then there may already be an app instance"""
    app = QApplication.instance()
    standalone = app is None # false if there is already an app instance
    if standalone: # if there isn't an instance, make one
        app = QApplication(sys.argv) 
    
    main_win = ImagerGUI()
    main_win.signal_cleanup.connect(main_win.cleanup)
    main_win.show()
    if standalone: # if an app instance was made, execute it
        sys.exit(app.exec_()) # when the window is closed, the python code also stops

if __name__ == "__main__":
    # change directory to this file's location
    os.chdir(os.path.dirname(os.path.realpath(__file__))) 
    run()
    