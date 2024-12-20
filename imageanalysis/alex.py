"""
ALEX: Atom Loading Enhancement for eXperiment

Similar to MAIA and iGUI ("SIMON"), but this widget handles images that are to
be used for rearrangement. All processing by this widget is handled in the main
thread as quick processing is essential for good rearrangement.

"""
import os
import sys
import time
import numpy as np
import pyqtgraph as pg
from copy import deepcopy

import logging
logging.basicConfig(format='%(asctime)s %(levelname)s:%(message)s', level=logging.DEBUG)
from collections import OrderedDict
from PyQt5.QtCore import pyqtSignal, QTimer
from PyQt5.QtGui import QIcon, QFont, QColor
from PyQt5.QtWidgets import (QMenu, QFileDialog, QMessageBox, QLineEdit, 
        QGridLayout, QWidget, QApplication, QPushButton, QAction, QMainWindow, 
        QLabel, QTableWidget, QHBoxLayout, QVBoxLayout, QCheckBox, QFormLayout,
        QStatusBar,QTableWidgetItem)
if '.' not in sys.path: sys.path.append('.')
if '..' not in sys.path: sys.path.append('..')
from strtypes import intstrlist, listlist, error, warning, info
from maingui import reset_slot # single atom image analysis
# from roiHandler import ROI, roi_handler
from multiAtomImageAnalyser import ROI, ROIGroup
from imagerGUI import (nat_validator, int_validator, non_neg_validator,
                       stylesheet_read_only, ThresholdViewer)
from roi_colors import get_group_roi_color
from helpers import calculate_threshold
import resources
from stefan import StefanGUI

####    ####    ####    ####

class alex(QMainWindow):
    """GUI window displaying rearrangement ROIs and the counts recorded in them.

    Keyword arguments:
    last_im_path -- the directory where images are saved.
    Cs_rois         -- list of ROI coordinates (xc, yc, width, height, autothresh, plot).
    Rb_rois         -- list of ROI coordinates (xc, yc, width, height, autothresh, plot).
    image_shape  -- shape of the images being taken, in pixels (x,y).
    name         -- an ID for this window, prepended to saved files.
    """
    event_im = pyqtSignal(np.ndarray) # image taken by the camera as np array
    roi_values = pyqtSignal(list) # list of ROIs (x, y, w, h, threshold)
    signal_rearr_strings = pyqtSignal(list) # list of rearrangement strings to send over TCP
     
    def __init__(self,state=None):
        super().__init__()
        self.setObjectName('ALEX')

        self.ihs = [] # list containing image handlers
        self.init_UI() # adjust widgets from main_window

        self.next_ih_num = 0
        self.file_id = 0 # this is a fallback id if one isn't recieved with the image
        
        if state is not None:
            self.set_state(state)

    def make_checkbox(self, r, i, atom):
        """Assign properties to checkbox so that it can be easily associated with an ROI"""
        r.plottoggle = QCheckBox(self, checked=True) # plot the line?
        r.plottoggle.i = i
        r.plottoggle.atom = atom
        r.plottoggle.stateChanged[int].connect(self.show_line)
                
    def init_UI(self):
        """Create all the widgets and position them in the layout"""
        self.centre_widget = QWidget()
        layout = QVBoxLayout() # make tabs for each main display 
        self.centre_widget.setLayout(layout)
        self.setCentralWidget(self.centre_widget)

        font = QFont() 
        font.setPixelSize(16) # make text size bigger

        pg.setConfigOption('background', 'w') # set graph background default white
        pg.setConfigOption('foreground', 'k') # set graph foreground default black

        hbox = QHBoxLayout()
        layout.addLayout(hbox)
        # toggle to continuously plot images as they come in
        self.button_update = QPushButton('Update histograms', self)
        self.button_update.clicked.connect(self.update)
        hbox.addWidget(self.button_update)

        # self.hist_toggle = QPushButton('Auto-update histograms', self)
        # self.hist_toggle.setCheckable(True)
        # self.hist_toggle.setChecked(True)
        # self.hist_toggle.clicked[bool].connect(self.set_hist_update)
        # hbox.addWidget(self.hist_toggle)
        
        # toggle whether to update histograms or not
        self.im_show_toggle = QPushButton('Auto-display last image', self)
        self.im_show_toggle.setCheckable(True)
        self.im_show_toggle.setChecked(True)
        self.im_show_toggle.clicked[bool].connect(self.set_im_show)
        hbox.addWidget(self.im_show_toggle)

        self.button_clear = QPushButton('Clear counts', self)
        self.button_clear.clicked.connect(self.clear)
        hbox.addWidget(self.button_clear)

        self.box_next_image_num = QLineEdit()
        self.box_next_image_num.setReadOnly(True)
        self.box_next_image_num.setStyleSheet(stylesheet_read_only)
        hbox.addWidget(QLabel('next image #:'))
        hbox.addWidget(self.box_next_image_num)

        hbox.addWidget(QLabel('# images:'))
        self.box_num_images = QLineEdit()
        self.box_num_images.setValidator(nat_validator)
        self.box_num_images.editingFinished.connect(self.set_num_images)
        self.box_num_images.setText(str(1))
        hbox.addWidget(self.box_num_images)

        self.button_show_roi_details = QPushButton('Show Threshold Viewer')
        self.button_show_roi_details.clicked.connect(self.create_threshold_viewer)
        hbox.addWidget(self.button_show_roi_details)

        self.button_debug = QPushButton('Show Debug Window')
        self.button_debug.clicked.connect(self.create_debug_window)
        hbox.addWidget(self.button_debug)

        self.layout_images = QHBoxLayout()
        layout.addLayout(self.layout_images)
        self.set_num_images()

        self.setWindowTitle('ALEX: Atom Loading Enhancement for eXperiment')
        self.setWindowIcon(QIcon('docs/atomcheckicon.png'))

    def make_image_handlers(self,num_images):
        """Called when the number of images is updated to change the layout 
        as required."""

        for _ in range(num_images,len(self.ihs)): # delete unneeded image handlers
            ih = self.ihs.pop()
            ih.setParent(None)
        for _ in range(len(self.ihs), num_images): # make new image handlers
            ih = ImageHandler()
            self.ihs.append(ih)
            self.layout_images.addWidget(ih)

    def create_threshold_viewer(self):
        self.tv = RearrangementThresholdViewer(self)
        self.tv.refresh()
        self.tv.show()

    def create_debug_window(self):
        self.debug = AlexDebugWindow(self)
        self.debug.show()

    def clear(self):
        """Clears the current counts data stored in the image handlers."""
        [[group.clear() for group in ih.roi_groups] for ih in self.ihs]

    def update(self):
        """Asks the image handlers to update their STEFANs."""
        [ih.recieve_stefan_data_request() for ih in self.ihs]

    def set_state(self,params):
        """Sets the ROIs and their thresholds from the state parameters.
        
        Parameters
        ----------
        params : list of lists
            List of the ROI coordinates and thresholds for the different 
            image handlers.
            
            Format is [[[ih0group0roi0.x,.y,.w,.h,.thresh,.autothresh],[ih0group0roi1],...],
                       [[ih0group1roi0],...]],
                       [[ih1group0roi0],...]],...]
            """
        self.box_num_images.setText(str(len(params)))
        self.set_num_images()
        for ih, ih_params in zip(self.ihs,params):
            ih.set_params(ih_params)

    def get_state(self):
        """Gets the state of the ALEX to be saved in the PyDex state files."""
        return [ih.get_params() for ih in self.ihs]

    def set_num_images(self):
        num_images = self.box_num_images.text()
        try:
            num_images = int(num_images)
        except ValueError:
            logging.error('{} is not a valid number of images.'.format(num_images))
            self.box_num_images.setText(str(len(self.ihs)))
            return
        else:
            if (num_images > 0) and (num_images != len(self.ihs)):
                logging.debug('Setting number of images to {}'.format(num_images))
                self.make_image_handlers(num_images)
                self.box_num_images.setText(str(len(self.ihs)))

    def set_im_show(self, toggle):
        """If the toggle is True, always update the display with the last image."""
        reset_slot(self.event_im, self.update_im, toggle)
        
    def set_hist_update(self, toggle=True):
        """Whether the histograms auto update for each new image."""
        reset_slot(self.event_im, self.update_plots, toggle)

    def update_im(self, im):
        """Display the image in the image canvas."""
        self.im_canvas.setImage(im)

    def get_threshold_viewer_data(self):
        """Extracts the ROI counts lists from the ROI objects contained within
        the ROI group objects."""
        thresholds = []

        num_awgs = len(self.ihs[0].awg_keys)
        max_num_rois = [] # find the max number of rois to display in the TV

        for awg in range(num_awgs):
            max_num_rois.append(max([ih.roi_groups[awg].get_num_rois() for ih in self.ihs]))
        print(max_num_rois)

        thresholds = []
        for group in range(num_awgs):
            num_rois = max_num_rois[group]
            group_thresholds = []
            for roi in range(num_rois):
                ih_thresholds = []
                for ih in self.ihs:
                    try:
                        ih_thresholds.append(ih.roi_groups[group].rois[roi].get_threshold_data()[0])
                    except IndexError: # this group:roi doesn't exist so just pad with empty data
                        ih_thresholds.append([0,False])
                group_thresholds.append(ih_thresholds)
            thresholds.append(group_thresholds)
            
        copy_im_threshs = [None for _ in self.ihs] # copy_im_threshs not implemented for ALEX

        tv_data = [thresholds,copy_im_threshs]
        return tv_data

    def tv_request_data_refresh(self):
        tv_data = self.get_threshold_viewer_data()
        try:
            self.tv.recieve_maia_threshold_data(tv_data)
        except AttributeError:
            pass # threshold viewer doesn't exist yet

    def tv_send_data_to_maia(self,threshold_viewer_data):
        """Recieves data from the threshold viewer and passes this to the 
        ROIs contained in the image handlers."""
        threshold_data = threshold_viewer_data[0]
        copy_im_threshs = threshold_viewer_data[1]

        for image_num, ih in enumerate(self.ihs):
            thresh_data = [[[roi[image_num]] for roi in group] for group in threshold_data]
            print(thresh_data)
            ih.update_roi_threshs(thresh_data)

        self.copy_im_threshs = copy_im_threshs # copy_im_threshs not implemented for ALEX

        self.calculate_thresholds()
        self.tv.refresh()
    
    def calculate_thresholds(self):
        for ih in self.ihs:
            for group in ih.roi_groups:
                for roi in group.rois:
                    for image in range(len(roi.counts)):
                        if roi.autothreshs[image]:
                            values = np.fromiter(roi.counts[image].values(), dtype=float)
                            roi.thresholds[image] = calculate_threshold(values)

    def recieve_image(self,image,ih_num=None,file_id=None):
        """Recieves an image from the rest of PyDex processes it as quickly
        as possible to process rearrangement before displaying it. 
        Non-essential GUI elements will be updated when this process is
        complete."""
        if ih_num is None:
            ih_num = self.next_ih_num
        if ih_num > len(self.ihs):
            logging.error('ALEX does not have an image handler with index '
                          '{}. Ignoring this image.'.format(ih_num))
            return
        if file_id is None:
            file_id = self.file_id
        logging.debug('Recieved image for handler {} with file ID {}'.format(
                      ih_num,file_id))
        self.get_occupancies_from_image(image,ih_num)
        self.store_counts_in_rois(image,ih_num,file_id)

        if self.im_show_toggle.isChecked():
            self.ihs[ih_num].draw_image(image)
        
        self.next_ih_num = (ih_num + 1)%(len(self.ihs))
        self.file_id = file_id + 1
        self.box_next_image_num.setText(str(self.next_ih_num))

    def get_occupancies_from_image(self,image,ih_num):
        ih = self.ihs[ih_num]
        occupancies = []
        invert_occupancies = [b.isChecked() for b in ih.buttons_invert]
        for group_i,[group,invert] in enumerate(zip(ih.roi_groups,invert_occupancies)):
            group_occupancy = ''
            for roi in group.rois:
                occupancy_bit = image[roi.x:roi.x+roi.w,roi.y:roi.y+roi.h].sum() > roi.thresholds[0]
                if invert:
                    occupancy_bit = not occupancy_bit
                group_occupancy += str(int(occupancy_bit))
            logging.debug('{} occupancy {}'.format(ih.roi_labels[group_i],
                                                   group_occupancy))
            group_occupancy += 'RH'+str(ih_num)
            occupancies.append(group_occupancy)
        self.signal_rearr_strings.emit(occupancies)

    def store_counts_in_rois(self,image,ih_num,file_id):
        ih = self.ihs[ih_num]
        for group in ih.roi_groups:
            for roi in group.rois:
                roi.counts[0][file_id] = image[roi.x:roi.x+roi.w,roi.y:roi.y+roi.h].sum()
        self.calculate_thresholds()

    #%% Debug functions
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

####    ####    ####    #### 

class ImageHandler(QWidget):
    """This class is created once for each image to process the image and 
    generate the ROI string. It also contains the widget objects that are
    displayed in the image."""

    awg_keys = {1:'Cs', 2:'Rb/RbCs'}

    def __init__(self):
        super().__init__()
        self._create_widgets()

    def _create_widgets(self):
        """Creates the subwidgets for this image handler."""
        layout = QVBoxLayout()

        self.roi_labels = ['AWG{} ({})'.format(i+1, self.awg_keys[i+1]) 
                      for i in range(len(self.awg_keys))]
        self.roi_groups = [ROIGroup(num_images=1) for _ in self.roi_labels]
        
        self.box_num_roiss = []
        self.buttons_invert = []

        rois_layout = QVBoxLayout()
        layout.addLayout(rois_layout)
        for label in self.roi_labels:
            roi_layout = QHBoxLayout()
            box_num_rois = QLineEdit()
            box_num_rois.setValidator(non_neg_validator)
            box_num_rois.editingFinished.connect(self.update_num_rois)
            button_invert = QCheckBox('Invert occupancy')
            roi_layout.addWidget(QLabel('# '+label+' ROIs'))
            roi_layout.addWidget(box_num_rois)
            roi_layout.addWidget(button_invert)
            rois_layout.addLayout(roi_layout)
            self.box_num_roiss.append(box_num_rois)
            self.buttons_invert.append(button_invert)
        
        im_widget = pg.GraphicsLayoutWidget() # containing widget
        viewbox = im_widget.addViewBox() # plot area to display image
        viewbox.setAspectLocked()
        self.im_canvas = pg.ImageItem() # the image
        viewbox.addItem(self.im_canvas)
        layout.addWidget(im_widget)

        self._create_stefans()

        for label,stefan in zip(self.roi_labels,self.stefans):
            layout.addWidget(QLabel('<h3>{}</h3>'.format(label)))
            layout.addWidget(stefan)

        self.setLayout(layout)

        self.update_num_rois()

    def _create_stefans(self):
        """Creates the STEFAN analysers used to plot the counts data for each
        ROI group. A lot of options are manually set and hidden for use in the
        ALEX."""
        self.stefans = [StefanGUI(self,0,False) for _ in self.roi_groups]

        for stefan in self.stefans:
            stefan.change_mode('counts')
            stefan.button_group.setChecked(True)

    def update_num_rois(self):
        """Takes the number of rois from the boxes and updates them to draw 
        that many rois."""
        for label, group, box_num in zip(self.roi_labels,self.roi_groups,
                                         self.box_num_roiss):
            num_rois = box_num.text()
            try:
                num_rois = int(num_rois)
            except ValueError:
                logging.error('{} is not a valid number of ROIs.'.format(num_rois))
                box_num.setText(str(group.get_num_rois()))
                continue
            else:
                if num_rois != group.get_num_rois():
                    logging.debug('Setting number of ROIs for {}'
                                  ' rearrangement handler to {}'.format(
                                  label,num_rois))
                    group.set_num_rois(num_rois)
                    box_num.setText(str(num_rois))
        self.update_roi_coords()

    def set_params(self,params):
        """Sets the parameters of the image handler from a state params file.
        Set Alex.set_state docstring for format."""
        roi_data = [[roi[:4] for roi in group] for group in params[0]]
        thresh_data = [[[roi[4:6]] for roi in group] for group in params[0]]

        self.update_roi_coords(roi_data)
        self.update_roi_threshs(thresh_data)

        invert_data = params[1]
        print('invert_data',invert_data)
        for button,invert in zip(self.buttons_invert,invert_data):
            button.setChecked(invert)

    def get_params(self):
        """Gets the params to be saved to the PyDex state."""
        roi_thresh_data = []
        for group in self.roi_groups:
            group_params = []
            for coords, thresh in zip(group.get_roi_coords(),group.get_threshold_data()):
                group_params.append(coords + [thresh[0][0]]+[thresh[0][1]])
            roi_thresh_data.append(group_params)
        
        return [roi_thresh_data,[b.isChecked() for b in self.buttons_invert]]

    def update_roi_coords(self, new_roi_coords=None):
        """Sets new coordinates for the ROIs and updates them on the GUI.

        Parameters
        ----------
        roi_coords : list of list of list or None
            list of the format [[[x,y,w,h],...],...] where ROI coordinates
            are sorted into their groups. None does not change the ROIs. 
            Default is None.
        """
        if new_roi_coords != None:
            for box_num,coords in zip(self.box_num_roiss, new_roi_coords):
                box_num.setText(str(len(coords)))
            self.update_num_rois()
            [group.set_roi_coords(coords) for group,coords in 
             zip(self.roi_groups,new_roi_coords)]
        self.draw_rois()

    def update_roi_threshs(self,roi_threshs):
        """Sets the new thresholds for the ROIs when loading from a state.
        It is assumed that the number of ROIs is correct."""
        [group.set_threshold_data(threshs) for group,threshs in 
             zip(self.roi_groups,roi_threshs)]

    def set_rois_from_image(self):
        roi_coords = []
        for group in self.roi_boxes:
            group_coords = []
            for r in group:
                [x,y] = [int(x) for x in r.pos()]
                [w,h] = [int(x) for x in r.size()]
                group_coords.append([x,y,w,h])
            roi_coords.append(group_coords)
        self.update_roi_coords(roi_coords)

    def draw_rois(self):
        """Draws the ROIs on the box."""
        viewbox = self.im_canvas.getViewBox()
        for item in viewbox.allChildren(): # remove unused ROIs
            if ((type(item) == pg.graphicsItems.ROI.ROI or 
                    type(item) == pg.graphicsItems.TextItem.TextItem)):
                viewbox.removeItem(item)
        
        self.roi_boxes = []

        for group_num, group in enumerate(self.roi_groups):
            group_boxes = []
            for roi_num, [x,y,w,h] in enumerate(group.get_roi_coords()):
                
                color = get_group_roi_color(roi_num,group_num)
                roi_box = pg.ROI([x,y],[w,h],translateSnap=True)
                roi_label = pg.TextItem('{}:{}'.format(
                                        self.awg_keys[group_num+1],roi_num),
                                        color, anchor=(0.5,1))
                font = QFont()
                font.setPixelSize(16)
                roi_label.setFont(font)
                roi_label.setPos(x+w//2,y+h) # in bottom left corner
                roi_box.setPen(color, width=3)
                viewbox.addItem(roi_box)
                viewbox.addItem(roi_label)
                roi_box.sigRegionChangeFinished.connect(self.set_rois_from_image)
                group_boxes.append(roi_box)
            self.roi_boxes.append(group_boxes)

    def draw_image(self,image):
        self.im_canvas.setImage(image)

    def get_roi_counts(self):
        """Extracts the ROI counts lists from the ROI objects contained within
        the ROI group objects. This returns an object sorted the alternative
        way around compared to MAIA (i.e. by group then ROI) so that STEFAN
        data is plotted by ROI group."""
        max_num_rois = max([group.get_num_rois() for group in self.roi_groups])
        counts = []
        for roi in range(max_num_rois):
            roi_counts = {}
            for group_num, group in enumerate(self.roi_groups):
                try:
                    roi_counts[group_num] = group.rois[roi].counts
                except IndexError:
                    pass # this group does not have the max num of rois
            counts.append(roi_counts)
        return counts
    
    def get_roi_thresholds(self):
        """Extracts the ROI counts lists from the ROI objects contained within
        the ROI group objects."""
        max_num_rois = max([group.get_num_rois() for group in self.roi_groups])
        thresholds = []
        for roi in range(max_num_rois):
            roi_thresholds = {}
            for group_num, group in enumerate(self.roi_groups):
                try:
                    roi_thresholds[group_num] = group.rois[roi].get_threshold_data()
                except IndexError:
                    pass # this group does not have the max num of rois
            thresholds.append(roi_thresholds)
        return thresholds

    def recieve_stefan_data_request(self,*args):
        """This function is called when the STEFAN requests the data to update
        the graph."""
        counts = self.get_roi_counts()
        thresholds = self.get_roi_thresholds()
        print(counts)
        for stefan_i,stefan in enumerate(self.stefans):
            stefan_counts = []
            stefan_thresholds = []
            i=0
            for count,thresh in zip(counts,thresholds):
                logging.debug('Appending ROI {} data'.format(i))
                i+=1
                try:
                    stefan_counts.append([count[stefan_i]])
                    stefan_thresholds.append([thresh[stefan_i]])
                except KeyError as e:
                    print(e)
            stefan.update([stefan_counts,stefan_thresholds,None])

class RearrangementThresholdViewer(ThresholdViewer):
    """Threshold Viewer for ALEX. Adapted for the one used by the iGUI so 
    most functions are contained in the imagerGUI Python file."""

    def __init__(self, alex):
        self.name = 'ALEX Threshold Viewer'
        super().__init__(alex)
        self.button_update.setText('Send to ALEX')
        self.button_show_only_group_zero.setEnabled(False)

    def refresh(self):
        """Sends a request to ALEX to get the latest information about the ROIs
         that exist and their current thresholds."""
        self.status_bar_message('Requesting information update from ALEX')
        self.iGUI.tv_request_data_refresh()

    def populate_table_with_data(self):
        """This function is redefined from the base ThresholdViewer class to 
        allow different ROI groups to have different number of ROIs and to
        sort thresholds by group instead of by ROI."""
        data = self.data
        self.table.blockSignals(True) # don't want signalling to happen whilst we're populating the table
        self.table.clear()

        self.num_roi_groups = len(data)
        self.num_rois_per_group = len(data[0])
        self.num_images = len(data[0][0])

        self.table.setRowCount(np.sum([len(group) for group in data]))
        self.table.setColumnCount(self.num_images)

        horizontal_headers = ['Image {}'.format(i) for i in range(self.num_images)]
        self.table.setHorizontalHeaderLabels(horizontal_headers)

        vertical_header_labels = []

        row_number = 0
        for group_num, group_data in enumerate(data):
            for roi_num, roi_data in enumerate(group_data):
                for image_num, threshold_data in enumerate(roi_data):
                    newVal = QTableWidgetItem(str(threshold_data[0]))
                    if threshold_data[1]: # autothresh is enabled
                        newVal.setIcon(self.autothresh_icon)
                    else:
                        newVal.setIcon(self.manualthresh_icon)
                    newVal.setBackground(QColor(get_group_roi_color(roi_num,group_num)))
                    self.table.setItem(row_number, image_num, newVal)
                vertical_header_labels.append('AWG{}:{}'.format(group_num+1,roi_num))
                row_number += 1
        self.table.setVerticalHeaderLabels(vertical_header_labels)

        self.table.blockSignals(False)

    def get_data_from_table(self):
        """Get the data from the threshold viewer data table and sends it 
        back to ALEX to be saved or for the thresholds to be updated.
        
        Reimplemented as ALEX orders data in tables differently to the iGUI
        threshold viewer."""
        new_data = deepcopy(self.data)
        
        self.copy_im_data = [self.table.item(0,image).text() for image in range(self.num_images)]

        table_index = 0
        for group_num, group in enumerate(self.data):
            for roi_num, roi in enumerate(group):
                for image_num, [_,autothresh] in enumerate(roi):
                    try:
                        print(group_num,roi_num,table_index,image_num)
                        value = round(float(self.table.item(table_index,image_num).text()))
                    except ValueError:
                        self.populate_table_with_data() # ignore the new data if a value is invalid
                        return
                    new_data[group_num][roi_num][image_num][0] = value
                    new_data[group_num][roi_num][image_num][1] = autothresh
                table_index += 1
        self.data = new_data
        self.populate_table_with_data()
        self.button_update.setStyleSheet('background-color: #BBCCEE')

    def toggle_all_autothresh(self):
        """Reimplemented as ALEX orders data in tables differently to the iGUI
        threshold viewer."""
        value = not self.data[0][0][0][1]
        for group in self.data:
            for roi in group:
                for image in roi:
                    image[1] = value
        self.populate_table_with_data()

    def get_table_index(self, group_num, roi_num):
        """Redefined from parent class to respect the new ordering in ALEX
        Threshold Viewer. This isn't implemented because you can normally 
        just keep track of this by using an iterating variable."""
        raise NotImplementedError('get_table_index not implemented for ALEX '
                                  'threshold viewer ordering system.')

    def get_roi_group_nums_from_index(self, index):
        """Redefined from parent class to respect the new ordering in ALEX
        Threshold Viewer."""
        roi_labels = []
        for group_num, group in enumerate(self.data):
            for roi_num, _ in enumerate(group):
                roi_labels.append([group_num,roi_num])
        
        group_roi_num = roi_labels[index]
        return group_roi_num[0],group_roi_num[1]
    
class AlexDebugWindow(QMainWindow):
    """Class to allow simple debugging of the iGUI by triggering commands that 
    will come from the rest of Pydex when needed.
    """

    def __init__(self,alex):
        super().__init__()
        self.name = 'ALEX Debug Window'
        self.setWindowTitle(self.name)
        self.alex = alex

        self.init_UI()

    def init_UI(self):
        self.centre_widget = QWidget()
        self.centre_widget.layout = QVBoxLayout()
        self.centre_widget.setLayout(self.centre_widget.layout)
        self.setCentralWidget(self.centre_widget)

        self.button_test_image = QPushButton('Generate 100 test images')
        self.button_test_image.clicked.connect(self.alex.generate_test_image)
        self.centre_widget.layout.addWidget(self.button_test_image)

        self.button_load_state = QPushButton('Load test state')
        self.button_load_state.clicked.connect(self.load_test_state)
        self.centre_widget.layout.addWidget(self.button_load_state)

    def load_test_state(self):
        true = True
        params = [[
        [
            [
                4,
                15,
                2,
                2,
                747,
                true,
                true
            ],
            [
                8,
                15,
                2,
                2,
                776,
                true,
                true
            ],
            [
                12,
                15,
                2,
                2,
                723,
                true,
                true
            ],
            [
                15,
                15,
                2,
                2,
                722,
                true,
                true
            ],
            [
                19,
                15,
                2,
                2,
                845,
                true,
                true
            ],
            [
                22,
                15,
                2,
                2,
                721,
                true,
                true
            ],
            [
                26,
                15,
                2,
                2,
                716,
                true,
                true
            ],
            [
                30,
                15,
                2,
                2,
                780,
                true,
                true
            ],
            [
                34,
                15,
                2,
                2,
                763,
                true,
                true
            ]
        ],
        [
            [
                5,
                13,
                2,
                2,
                797,
                true,
                true
            ],
            [
                8,
                13,
                2,
                2,
                892,
                true,
                true
            ],
            [
                11,
                13,
                2,
                2,
                899,
                true,
                true
            ],
            [
                13,
                13,
                2,
                2,
                819,
                true,
                true
            ],
            [
                16,
                13,
                2,
                2,
                935,
                true,
                true
            ],
            [
                19,
                13,
                2,
                2,
                1086,
                true,
                true
            ],
            [
                21,
                13,
                2,
                2,
                964,
                true,
                true
            ],
            [
                24,
                13,
                2,
                2,
                851,
                true,
                true
            ],
            [
                26,
                13,
                2,
                2,
                833,
                true,
                true
            ],
            [
                29,
                13,
                2,
                2,
                941,
                true,
                true
            ],
            [
                32,
                13,
                2,
                2,
                892,
                true,
                true
            ],
            [
                34,
                13,
                2,
                2,
                931,
                true,
                true
            ],
            [
                37,
                13,
                2,
                2,
                914,
                true,
                true
            ],
            [
                39,
                13,
                2,
                2,
                938,
                true,
                true
            ]
        ]
        ]]
        self.alex.set_state(params)
        params = self.alex.get_state()
        print(params)
        self.alex.set_state(params)

def run():
    """Initiate an app to run the program
    if running in Pylab/IPython then there may already be an app instance"""
    app = QApplication.instance()
    standalone = app is None # false if there is already an app instance
    if standalone: # if there isn't an instance, make one
        app = QApplication(sys.argv) 
        
    boss = alex()
    boss.showMaximized()
    if standalone: # if an app instance was made, execute it
        sys.exit(app.exec_()) # when the window is closed, the python code also stops
            
if __name__ == "__main__":
    # change directory to PyDex folder
    os.chdir(os.path.dirname(os.path.realpath(__file__))) 
    run()