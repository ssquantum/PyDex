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
import resources

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
     
    def __init__(self, last_im_path='.', Cs_rois=[[1,1,1,1,True,True]], Rb_rois=[[1,1,1,1,True,True]],
                 image_shape=(512,512), name=''):
        super().__init__()
        self.name = name
        self.setObjectName(name)
        self.last_im_path = last_im_path

        self.ihs = [] # list containing image handlers
        self.init_UI() # adjust widgets from main_window
        
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
        self.hist_toggle = QPushButton('Auto-update histograms', self)
        self.hist_toggle.setCheckable(True)
        self.hist_toggle.setChecked(True)
        self.hist_toggle.clicked[bool].connect(self.set_hist_update)
        hbox.addWidget(self.hist_toggle)
        
        # toggle whether to update histograms or not
        self.im_show_toggle = QPushButton('Auto-display last image', self)
        self.im_show_toggle.setCheckable(True)
        self.im_show_toggle.clicked[bool].connect(self.set_im_show)
        hbox.addWidget(self.im_show_toggle)
        
        # reset the list of counts in each ROI displayed in the plots
        self.reset_button = QPushButton('Reset plots', self)
        self.reset_button.clicked.connect(self.reset_plots)
        hbox.addWidget(self.reset_button)

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

        self.layout_images = QHBoxLayout()
        layout.addLayout(self.layout_images)
        self.set_num_images()

        self.setWindowTitle(self.name+'ALEX: Atom Loading Enhancement for eXperiment')
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
        self.tv.show()

    #### #### user input functions #### ####

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

    def recieve_image(self,image,file_id=None,image_num=None):
        """Recieves an image from the iGUI and adds it to the processing queue.
        If the file_id and image num are set then these will be added to the
        queue along with the image and used to set the values for the next 
        image.
        """
        self.queue.append([image,file_id,image_num])
        self.signal_status_message.emit('Recieved ID {} Im {} and placed in queue'.format(file_id,image_num))
        self.signal_draw_image.emit(image,image_num)
        self.advance_image_count(file_id,image_num)

    def set_im_show(self, toggle):
        """If the toggle is True, always update the display with the last image."""
        reset_slot(self.event_im, self.update_im, toggle)
        
    def set_hist_update(self, toggle=True):
        """Whether the histograms auto update for each new image."""
        reset_slot(self.event_im, self.update_plots, toggle)

    def change_timeout(self, newval):
        """Time in seconds to wait before sending the trigger to continue the 
        experiment. Default is 0 which waits indefinitely."""
        try:
            self.timer.t0 = float(newval)
        except ValueError: pass

    def user_roi(self, roi):
        """The user drags an ROI and this updates the ROI centre and width"""
        # find which ROI was dragged
        for r in self.rh['Cs'].ROIs + self.rh['Rb'].ROIs:
            if r.roi == roi:
                break
        x0, y0 = roi.pos()  # lower left corner of bounding rectangle
        w, h = map(int, roi.size()) # width, height
        xc, yc = int(x0 + w//2), int(y0 + h//2) # centre of ROI
        r.w, r.h = w, h
        r.label.setPos(x0, y0)
        r.translate_mask(xc, yc)
        for key, val in zip(r.edits.keys(), [xc, yc, w, h]):
            r.edits[key].setText(str(val))

    def emit_rois(self, toggle=0, atom='Cs'):
        """Emit the signal with the list of ROIs"""
        self.roi_values.emit(self.get_rois(atom))
        
    def get_rois(self, atom='Cs'):
        """Return list of ROIs"""
        return [[r.x, r.y, r.w, r.h, r.t, r.autothresh.isChecked(), r.plottoggle.isChecked()] for r in self.rh[atom].ROIs]

    def send_trigger(self, toggle=0):
        """Emit the roi_handler's trigger signal to start the experiment"""
        if self.checking: self.rh['Cs'].trigger.emit(1)

    #### #### automatic ROI assignment #### ####
    
    def set_rois(self, ROIlist, atom='Cs'):
        """Set the ROI list as the new ROIs"""
        self.rh[atom].create_rois(len(ROIlist), label=atom+' ')
        self.create_new_rois(atom=atom) # populates the table widget
        self.rh[atom].resize_rois(ROIlist)
        
        self.rois_edit[atom].blockSignals(True)
        self.rois_edit[atom].setText(str(len(ROIlist)))
        self.rois_edit[atom].blockSignals(False)

        self.display_rois()

    def make_roi_grid(self, toggle=True, method='', atom='Cs'):
        """Create a grid of ROIs and assign them to analysers that are using the
        same image. Methods:
        Single ROI       -- make all ROIs the same as the first analyser's 
        Square grid      -- evenly divide the image into a square region for
            each of the analysers on this image.  
        2D Gaussian masks-- fit 2D Gaussians to atoms in the image."""
        rh = self.rh[atom]
        method = method if method else self.sender().text()
        pos, shape =rh.ROIs[0].roi.pos(), rh.ROIs[0].roi.size()
        if method == 'Single ROI':
            for r in rh.ROIs:
                r.resize(*map(int, [pos[0], pos[1], shape[0], shape[1]]))
        elif method == 'Square grid':
            n = len(rh.ROIs) # number of ROIs
            d = int((n - 1)**0.5 + 1)  # number of ROIs per row
            X = int(rh.shape[0] / d) # horizontal distance between ROIs
            Y = int(rh.shape[1] / int((n - 3/4)**0.5 + 0.5)) # vertical distance
            for i in range(n): # ID of ROI
                try:
                    newx, newy = int(X * (i%d + 0.5)), int(Y * (i//d + 0.5))
                    if any([newx//rh.shape[0], newy//rh.shape[1]]):
                        warning('Tried to set square ROI grid with (xc, yc) = (%s, %s)'%(newx, newy)+
                        ' outside of the image')
                        newx, newy = 0, 0
                    rh.ROIs[i].resize(*map(int, [newx, newy, 1, 1]))
                except ZeroDivisionError as e:
                    error('Invalid parameters for square ROI grid: '+
                        'x - %s, y - %s, pic size - %s, roi size - %s.\n'%(
                            pos[0], pos[1], rh.shape[0], (shape[0], shape[1]))
                        + 'Calculated width - %s, height - %s.\n'%(X, Y) + str(e))
        elif method == '2D Gaussian masks':
            try: 
                im = self.im_canvas.image.copy() - rh.bias
                if np.size(np.shape(im)) == 2:
                    for r in rh.ROIs:
                        r.create_gauss_mask(im) # fit 2D Gaussian to max pixel region
                        # then block that region out of the image
                        try:
                            im[r.x-r.w : r.x+r.w+1, r.y-r.h:r.y+r.h+1] = np.zeros((2*r.w+1, 2*r.h+1)) + np.min(im)
                        except (IndexError, ValueError): pass
            except AttributeError: pass

    #### #### canvas functions #### ####
    
    def remove_legend_item(self, legend, pos):
        try:
            sample, label = legend.items[pos]
            legend.items.remove((sample, label))  # remove from itemlist
            legend.layout.removeItem(sample)  # remove from layout
            sample.close()  # remove from drawing
            legend.layout.removeItem(label)
            label.close()
            legend.updateSize()
        except IndexError as e: pass
    
    def update_lines_list(self, atom='Cs'):
        """Add and remove lines from the plot to match up the list of ROIs"""
        ROIs = self.rh[atom].ROIs
        # add extra lines for new ROIs
        pw = self.plots[atom]['plot']
        for i in range(len(self.plots[atom]['counts']), len(ROIs)):
            self.plots[atom]['counts'].append(pw.plot(np.zeros(1000)+i*1.1, name=ROIs[i].id, pen=pg.intColor(i)))
            self.plots[atom]['thresh'].append(pw.addLine(y=i*1.1+1, pen=pg.intColor(i)))
        # remove excess lines
        for i in reversed(range(len(ROIs), len(self.plots[atom]['counts']))):
            self.remove_legend_item(self.plots[atom]['legend'], i) 
            self.plots[atom]['plot'].removeItem(self.plots[atom]['counts'][i])
            self.plots[atom]['plot'].removeItem(self.plots[atom]['thresh'][i])
            self.plots[atom]['counts'].pop(i)
            self.plots[atom]['thresh'].pop(i)
            
    def update_table(self, atom='Cs'):
        """Set the rows with the line edit widgets from each ROI."""
        self.tables[atom].setRowCount(len(self.rh[atom].ROIs))
        for i, r in enumerate(self.rh[atom].ROIs):
            self.make_checkbox(r, i, atom)
            for j, label in enumerate(list(r.edits.values())+[r.threshedit, r.autothresh, r.plottoggle]): 
                self.tables[atom].setCellWidget(i, j, label)
            
    def create_new_rois(self, n='', atom=''):
        """Update number of ROIs then display them"""
        atom = atom if atom else self.sender().name
        if n: 
            self.rh[atom].create_rois(int(n), label=atom+' ')
        # update table
        self.update_table(atom)
        self.update_lines_list(atom)
        self.display_rois()
        
    def display_rois(self, n=''):
        """Add the ROIs from the roi_handler to the viewbox if they're
        not already displayed."""
        ROIs = self.rh['Cs'].ROIs + self.rh['Rb'].ROIs
        viewbox = self.im_canvas.getViewBox()
        for item in viewbox.allChildren(): # remove unused ROIs
            if ((type(item) == pg.graphicsItems.ROI.ROI or 
                    type(item) == pg.graphicsItems.TextItem.TextItem) and 
                    item not in [r.roi for r in ROIs] + [r.label for r in ROIs]):
                viewbox.removeItem(item)
        
        for atom in ['Cs', 'Rb']:
            for i, r in enumerate(self.rh[atom].ROIs):
                if r.roi not in viewbox.allChildren():
                    reset_slot(r.roi.sigRegionChangeFinished, self.user_roi, True) 
                    reset_slot(r.threshedit.textEdited, self.update_plots, True)
                    r.roi.setZValue(10)   # make sure the ROI is drawn above the image
                    viewbox.addItem(r.roi)
                    viewbox.addItem(r.label)
                    
    def show_line(self, toggle=0, i=0, atom='Cs'):
        """Display the lines of counts if the toggle is true"""
        i, atom = self.sender().i, self.sender().atom
        if toggle:
            self.plots[atom]['counts'][i].show()
            self.plots[atom]['thresh'][i].show()
        else:
            self.plots[atom]['counts'][i].hide()
            self.plots[atom]['thresh'][i].hide()
                        
    def update_plots(self, im=0, include=1):
        """Plot the history of counts in each ROI in the associated plots"""
        for atom in ['Cs', 'Rb']:
            for i, r in enumerate(self.rh[atom].ROIs):
                try:
                    label = 'ROI %s, LP=%.3g'%(r.id, r.LP())
                    self.plots[atom]['counts'][i].setData(r.c[:r.i], name=label,
                            pen=pg.intColor(i)) # history of counts
                    if r.autothresh.isChecked(): r.thresh() # update threshold
                    self.plots[atom]['thresh'][i].setValue(r.t) # plot threshold
                    self.plots[atom]['legend'].items[i][1].setText(label)
                except (IndexError, ValueError): pass
                
    
    def reset_plots(self):
        """Empty the lists of counts in the ROIs and update the plots."""
        for atom in ['Cs', 'Rb']:
            self.rh[atom].reset_count_lists(range(len(self.rh[atom].ROIs)))
            for p in self.plots[atom]['counts']:
                try:
                    for l in p: l.setData([1])
                except TypeError:
                    pass

    def update_im(self, im):
        """Display the image in the image canvas."""
        self.im_canvas.setImage(im)

    def show_ROI_masks(self, toggle=True):
        """Make an image out of all of the masks from the ROIs and display it."""
        im = np.zeros(self.rh['Cs'].shape)
        for roi in [self.rh['Cs'].ROIs + self.rh['Rb'].ROIs]:
            try: im += roi.mask
            except ValueError as e: error('ROI %s has mask of wrong shape\n'%roi.id+str(e))
        self.update_im(im)

    #### #### save and load data functions #### ####

    def get_default_path(self, default_path=''):
        """Get a default path for saving/loading images
        default_path: set the default path if the function doesn't find one."""
        return default_path if default_path else os.path.dirname(self.last_im_path)

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
            return file_name
        except OSError: return '' # probably user cancelled

    def load_from_files(self, trigger=None):
        """Prompt the user to select image files to process using the file
        browser.
        Keyword arguments:
            trigger:        Boolean passed from the QObject that triggers
                            this function."""
        im_list = []
        file_list = self.try_browse(title='Select Files', 
                file_type='Images(*.asc);;all (*)', 
                open_func=QFileDialog.getOpenFileNames)
        for file_name in file_list:
            try:
                im_vals = self.rh['Cs'].load_full_im(file_name)
                im_list.append(im_vals)
            except Exception as e: # probably file size was wrong
                warning("Failed to load image file: "+file_name+'\n'+str(e)) 
        return im_list

    def load_image(self, trigger=None):
        """Prompt the user to select an image file to display"""
        file_name = self.try_browse(file_type='Images (*.asc);;all (*)')
        if file_name:  # avoid crash if the user cancelled
            self.last_im_path = file_name
            self.rh['Cs'].set_pic_size(file_name) # get image size
            im_vals = self.rh['Cs'].load_full_im(file_name)
            self.update_im(im_vals) # display image
        
    def make_ave_im(self):
        """Make an average image from the files selected by the user and 
        display it."""
        im_list = self.load_from_files()
        if len(im_list):
            aveim = np.zeros(np.shape(im_list[0]))
        else: return 0 # no images selected
        for im in im_list:
            aveim += im
        self.update_im(aveim / len(im_list))
        return 1

    def save_roi_hists(self, file_name='AtomCheckerHist.csv', atom='Cs'):
        """Save the histogram data from the ROIs"""
        if not file_name:
            file_name = self.try_browse(title='Select File', 
                file_type='csv(*.csv);;all (*)', 
                open_func=QFileDialog.getSaveFileName)
        if file_name:
            try:
                out_arr = np.zeros((len(self.rh[atom].ROIs)*2, self.rh[atom].ROIs[0].i))
                head0 = ''
                head1 = ''
                head2 = ''
                for i, r in enumerate(self.rh[atom].ROIs):
                    out_arr[2*i] = r.c
                    out_arr[2*i+1] = np.array(r.atom())
                    head0 += 'ROI%s LP, ROI%s Thresh, '%(r.id, r.id)
                    head1 += '%s, %s, '%(r.LP(), r.t)
                    head2 += 'ROI%s Counts, ROI%s Atom, '%(r.id, r.id)
                if len(head0):
                    header = head0[:-2] + '\n' + head1[:-2] + '\n' + head2[:-2]
                else: header = '.\n.\n.'
                np.savetxt(file_name, out_arr.T, fmt='%s', delimiter=',', header=header)
            except (ValueError, IndexError, PermissionError) as e:
                error("AtomChecker couldn't save file %s\n"%file_name+str(e))

    def save_rois(self, file_name='', ROIlist=[]):
        """Save the coordinates and thresholds of the ROIs"""
        if not file_name:
            file_name = self.try_browse(title='Select File', file_type='txt(*.txt);;all (*)', 
                open_func=QFileDialog.getSaveFileName)
        if file_name:
            try:
                with open(file_name, 'w+') as f:
                    f.write(str(ROIlist))
            except (ValueError, IndexError, PermissionError) as e:
                error("AtomChecker couldn't save file %s\n"%file_name+str(e))   
    
    def save_cs_rois(self, file_name=''):
        self.save_rois(file_name, [[int(x.text()) for x in list(r.edits.values())+[r.threshedit]] for r in self.rh['Cs'].ROIs])
    
    def save_rb_rois(self, file_name=''):
        self.save_rois(file_name, [[int(x.text()) for x in list(r.edits.values())+[r.threshedit]] for r in self.rh['Rb'].ROIs])
        
    def load_rois(self, file_name='', atom='Cs'):
        """Load the coordinates and thresholds of the ROIs"""
        if not file_name:
            file_name = self.try_browse(title='Select File', file_type='txt(*.txt);;all (*)', 
                open_func=QFileDialog.getOpenFileName)
        if file_name:
            try:
                with open(file_name, 'r') as f:
                    ROIlist = eval(f.readline())
                self.rois_edit[atom].setText(str(len(ROIlist))) # triggers create_new_rois
                self.rh[atom].resize_rois(ROIlist)
            except (ValueError, IndexError, PermissionError) as e:
                error("AtomChecker couldn't save file %s\n"%file_name+str(e))     

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
        print(thresholds)
        return tv_data

    def tv_request_data_refresh(self):
        tv_data = self.get_threshold_viewer_data()
        try:
            self.tv.recieve_maia_threshold_data(tv_data)
        except AttributeError:
            pass # threshold viewer doesn't exist yet

    def tv_send_data_to_maia(self):
        pass
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

        roi_layout = QFormLayout()
        layout.addLayout(roi_layout)
        for label in self.roi_labels:
            box_num_rois = QLineEdit()
            box_num_rois.setValidator(non_neg_validator)
            box_num_rois.editingFinished.connect(self.update_num_rois)
            print(label,box_num_rois)
            roi_layout.addRow('# '+label+' ROIs',box_num_rois)
            self.box_num_roiss.append(box_num_rois)
        
        im_widget = pg.GraphicsLayoutWidget() # containing widget
        viewbox = im_widget.addViewBox() # plot area to display image
        self.im_canvas = pg.ImageItem() # the image
        viewbox.addItem(self.im_canvas)
        layout.addWidget(im_widget)

        self.setLayout(layout)

        self.update_num_rois()

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
            [group.set_roi_coords(coords) for group,coords in 
             zip(self.roi_groups,new_roi_coords)]
        self.draw_rois()

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

        for group_num, group in enumerate(self.data):
            for roi_num, roi in enumerate(group):
                for image_num, [_,autothresh] in enumerate(roi):
                    table_index = self.get_table_index(group_num,roi_num)
                    try:
                        value = round(float(self.table.item(table_index,image_num).text()))
                    except ValueError:
                        self.populate_table_with_data() # ignore the new data if a value is invalid
                        return
                    new_data[group][roi][image_num][0] = value
                    new_data[group][roi][image_num][1] = autothresh
        self.data = new_data
        self.populate_table_with_data()
        self.button_update.setStyleSheet('background-color: #BBCCEE')

    def get_table_index(self, group_num, roi_num):
        """Redefined from parent class to respect the new ordering in ALEX
        Threshold Viewer."""
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