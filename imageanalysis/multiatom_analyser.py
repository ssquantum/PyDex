"""Multi-Atom Image Analysis

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
from PyQt5.QtCore import pyqtSignal, QRegExp
from PyQt5.QtGui import (QIcon, QDoubleValidator, QIntValidator, 
        QFont, QRegExpValidator)
from PyQt5.QtWidgets import (QActionGroup, QVBoxLayout, QMenu, 
        QFileDialog, QComboBox, QMessageBox, QLineEdit, QGridLayout, 
        QApplication, QPushButton, QAction, QMainWindow, QWidget,
        QLabel, QTabWidget, QInputDialog, QHBoxLayout, QTableWidget,
        QCheckBox, QFormLayout)
if '..' not in sys.path: sys.path.append('..')
from strtypes import error, warning, info
import imageHandler as ih # process images to build up a histogram
import histoHandler as hh # collect data from histograms together
import fitCurve as fc   # custom class to get best fit parameters using curve_fit

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
    """Make sure all instances of slot are disconnected
    from signal. Prevents multiple connections to the same 
    slot. If reconnect=True, then reconnect slot to signal."""
    while True: # make sure that the slot is only connected once 
        try: signal.disconnect(slot)
        except TypeError: break
    if reconnect: signal.connect(slot)

####    ####    ####    ####

class ROI():
    """Container ROI class containing the bear minimum information needed 
    by the MAIA to ensure efficiency.
    """
    def __init__(self, x, y, width, height, threshold=1000, autothresh = True,
                 plot = True, num_images=1):
        self.x = x
        self.y = y
        self.w = width
        self.h = height
        self.t = threshold
        self.autothresh = autothresh
        self.plot = plot

        self.counts = [[]] # List to store the counts in. Each element is the list for each image.
        self.update_num_images(num_images)

    def get_gui_elements(self):
        """Create objects that will be used by the MAIA class to populate the 
        GUI.
        """
        self.box_x = QLineEdit()
        self.box_y = QLineEdit()
        self.box_w = QLineEdit()
        self.box_h = QLineEdit()
        self.box_t = QLineEdit()
        for value, box in zip([self.x, self.y, self.w, self.h, self.t],
                              [self.box_x, self.box_y, self.box_w, self.box_h, self.box_t]):
            box.setValidator(int_validator)
            box.setText(str(value))

        self.toggle_autothresh  = QCheckBox()
        self.toggle_autothresh.setChecked(self.autothresh)
        self.toggle_plot  = QCheckBox()
        self.toggle_plot.setChecked(self.plot)

        return self.box_x, self.box_y, self.box_w, self.box_h, self.box_t, self.toggle_autothresh,self.toggle_plot

    def get_image_roi(self,index):
        self.image_roi = pg.ROI([self.x,self.y],[self.w,self.h],translateSnap=True)
        self.image_label = pg.TextItem('ROI'+str(index), pg.intColor(index), anchor=(0,1))
        font = QFont()
        font.setPixelSize(16)
        self.image_label.setFont(font)
        self.image_label.setPos(self.x+self.w//2, self.y+self.h//2) # in bottom left corner

        return self.image_roi, self.image_label

    def update_params(self):
        if all([box.text() for box in [self.box_x, self.box_y, self.box_w, self.box_h, self.box_t]]):
            self.x = int(self.box_x.text())
            self.y = int(self.box_y.text())
            self.w = int(self.box_w.text())
            self.h = int(self.box_h.text())
            self.t = int(self.box_t.text())
            self.autothresh = self.toggle_autothresh.isChecked()
            self.plot = self.toggle_plot.isChecked()

            self.calculate_occupancy()
            return True
        else: return False

    def update_num_images(self,num_images):
        """Creates the correct number of elements in the counts list to 
        reflect the number of images set. Data is preserved if the number of
        images is increased.
        
        Parameters
        ----------
        num_images : int
            The number of images the roi should expect to recieve in a sequence.
        """        
        print('update to images:',num_images)
        self.counts = self.counts[:num_images]
        for i in range(len(self.counts), num_images): # make new ROIs
            self.counts.append([])
        
    def clear_data(self):
        """Deletes all current counts data."""
        self.counts = [[] for _ in range(len(self.counts))]

    def calculate_occupancy(self):
        """Processess the counts and determines if the roi was occupied or
        unoccupied for each image.
        
        Returns
        -------
        list of list
            Same format as the ROI.counts list but in binary occupations.
        """
        self.occupancy = [list(x > self.t for x in y) for y in self.counts]
        return self.occupancy

# main GUI window contains all the widgets                
class main_window(QMainWindow):
    """Main GUI window managing the MAIA (multi-atom image analyser).

    Keyword arguments:
    results_path  -- directory to save log file and results to.
    im_store_path -- the directory where images are saved.
    name          -- an ID for this window, prepended to saved files.
    im_handler    -- an instance of image_handler
    hist_handler  -- an instance of histo_handler
    edit_ROI      -- whether the user can edit the ROI"""
    event_im = pyqtSignal([np.ndarray, bool]) # [numpy array, include in hists?]

    def __init__(self, results_path='.', im_store_path='.', name='Multi Atom Image Analyser',
                im_handler=None, hist_handler=None, edit_ROI=True):
        super().__init__()
        self.name = name  # name is displayed in the window title
        self.setObjectName(name)
        self.image_handler = im_handler if im_handler else ih.image_handler() # class to process images
        self.image_handler.name = name
        self.histo_handler = hist_handler if hist_handler else hh.histo_handler() # class to process histograms
        self.multirun = '' # whether currently doing a multirun or not
        pg.setConfigOption('background', 'w') # set graph background default white
        pg.setConfigOption('foreground', 'k') # set graph foreground default black
        self.date = time.strftime("%d %b %B %Y", time.localtime()).split(" ") # day short_month long_month year
        self.log_file_name = results_path + 'log.dat' # in case init_log fails
        self.last_path = results_path # path history helps user get to the file they want
        self.next_image = 0 # image number to assign the next incoming array to
        
        self.num_images = 2
        self.rois = [ROI(1,1,4,4,1000,num_images=self.num_images)]
        self.counts_plots = []

        self.init_log(results_path) # write header to the log file that collects histograms
        self.image_storage_path = im_store_path # used for loading image files
        self.init_UI(edit_ROI)  # make the widgets
        # self.t0 = time.time() # time of initiation
        # self.int_time = 0     # time taken to process an image
        # self.plot_time = 0    # time taken to plot the graph
        # self.set_bins() # connect signals

        self.event_im.connect(self.process_image)

    def init_log(self, results_path='.'):
        """Create a directory for today's date as a subdirectory in the log file path
        then write the header to the log file path defined in config.dat"""
        # make subdirectory if it doesn't already exist
        results_path = os.path.join(results_path, 
                    r'%s\%s\%s'%(self.date[3],self.date[2],self.date[0]))
        try:
            os.makedirs(results_path, exist_ok=True)
        except PermissionError:  # couldn't access the path, start a log file here
            results_path = r'.\%s\%s\%s'%(self.date[3],self.date[2],self.date[0])
            os.makedirs(results_path, exist_ok=True)

        # log is saved in a dated subdirectory and the file name also has the date
        self.last_path = results_path
        self.log_file_name = os.path.join(results_path, 
                   self.name+'log'+self.date[0]+self.date[1]+self.date[3]+'.dat')  
        # write the header to the log file
        if not os.path.isfile(self.log_file_name): # don't overwrite if it already exists
            with open(self.log_file_name, 'w+') as f:
                f.write('#Single Atom Image Analyser Log File: collects histogram data\n')
                f.write('#include --[]\n')
                f.write('#'+', '.join(self.histo_handler.stats.keys())+'\n')
       

    def init_UI(self, edit_ROI=True):
        """Create all of the widget objects required
        edit_ROI - toggle whether the user can change the ROI"""

        self.centre_widget = QWidget()
        self.tabs = QTabWidget()       # make tabs for each main display 
        self.centre_widget.layout = QVBoxLayout()
        # self.centre_widget.layout.addWidget(self.tabs)
        self.centre_widget.setLayout(self.centre_widget.layout)
        self.setCentralWidget(self.centre_widget)

        layout_options = QHBoxLayout()
        layout_options.addWidget(QLabel('Number of images:'))
        self.box_number_images = QLineEdit()
        self.box_number_images.setValidator(int_validator)
        self.box_number_images.setText(str(self.num_images))
        self.box_number_images.editingFinished.connect(self.update_num_images)
        layout_options.addWidget(self.box_number_images)
        layout_options.addWidget(QLabel('Number of ROIs:'))
        self.box_number_rois = QLineEdit()
        self.box_number_rois.setValidator(int_validator)
        self.box_number_rois.setText(str(len(self.rois)))
        self.box_number_rois.editingFinished.connect(self.create_new_rois)
        layout_options.addWidget(self.box_number_rois)
        self.button_clear_data = QPushButton('Clear all data')
        self.button_clear_data.clicked.connect(self.clear_data)
        layout_options.addWidget(self.button_clear_data)

        self.button_test_image = QPushButton('Generate test image')
        self.button_test_image.clicked.connect(self.generate_test_image)
        layout_options.addWidget(self.button_test_image)
        self.centre_widget.layout.addLayout(layout_options)

        layout_image_rois = QGridLayout()
        layout_image_options = QHBoxLayout()
        self.box_display_image_num = QLineEdit()
        self.box_display_image_num.setValidator(int_validator)
        self.box_display_image_num.setText(str(0))
        layout_image_options.addWidget(QLabel('display image:'))
        layout_image_options.addWidget(self.box_display_image_num)
        self.label_next_image = QLabel('Next image: 0')
        layout_image_options.addWidget(self.label_next_image)
        self.button_skip_image = QPushButton('Skip image')
        self.button_skip_image.clicked.connect(self.advance_next_image)
        layout_image_options.addWidget(self.button_skip_image)
        layout_image_rois.addLayout(layout_image_options,0,0,1,4)
        im_widget = pg.GraphicsLayoutWidget() # containing widget
        viewbox = im_widget.addViewBox() # plot area to display image
        self.im_canvas = pg.ImageItem() # the image
        viewbox.addItem(self.im_canvas)
        layout_image_rois.addWidget(im_widget, 1,0,3,4)
        #### table has all of the values for the ROIs ####
        self.table_rois = QTableWidget(len(self.rois), 7)
        self.table_rois.setHorizontalHeaderLabels(['x', 'y', 'w', 'h', 'Threshold', 'Auto-thresh', 'Plot'])
        self.update_table()
        layout_image_rois.addWidget(self.table_rois, 0,4,4,4)
        self.centre_widget.layout.addLayout(layout_image_rois)

        self.layout_plots = QHBoxLayout()
        self.centre_widget.layout.addLayout(self.layout_plots)

        self.update_num_images()
        self.create_counts_plots()

        return

    def create_new_rois(self):
        """Update number of ROIs then display them. ROI data is cleared to 
        avoid images being out of sync between ROIs."""
        n = int(self.box_number_rois.text())
        self.rois = self.rois[:n]
        for i in range(len(self.rois), n): # make new ROIs
            self.rois.append(ROI(1,1,4,4,num_images=self.num_images))
        
        for r in self.rois:
            r.clear_data()

        self.update_table()
        self.display_rois()
        self.redraw_counts_plots()

    def update_table(self):
        self.table_rois.setRowCount(len(self.rois))
        for i, r in enumerate(self.rois):
            for j, label in enumerate(list(r.get_gui_elements())):
                try:
                    label.editingFinished.connect(self.set_rois_from_table)
                except AttributeError:
                    label.stateChanged.connect(self.set_rois_from_table)
                self.table_rois.setCellWidget(i, j, label)
        self.table_rois.setVerticalHeaderLabels([str(x) for x in list(range(len(self.rois)))])
        
    def set_rois_from_table(self):
        if all([r.update_params() for r in self.rois]): # only triggers if there is not an empty box
            self.update_table()
        self.display_rois()
        self.redraw_counts_plots()

    def generate_test_image(self):
        self.event_im.emit(np.random.rand(100,50)*1000, True)

    def process_image(self,image,include):
        if self.next_image == int(self.box_display_image_num.text()):
            self.im_canvas.setImage(image)
        plot_x_offset = np.random.uniform(-counts_plot_roi_offset,counts_plot_roi_offset)
        for i, r in enumerate(self.rois):
            xmin = np.max([0,r.x])
            ymin = np.max([0,r.y])
            xmax = np.min([image.shape[0],r.x+r.w])
            ymax = np.min([image.shape[1],r.y+r.h])
            counts = image[xmin:xmax,ymin:ymax].sum()  # numpy sum far more efficient that python's sum(array)
            r.counts[self.next_image].append(counts)
            if r.plot:
                plot = self.counts_plots[self.next_image].scatter_plot
                if counts < r.t:
                    plot.addPoints(x=[i+plot_x_offset],y=[counts],pen=pg.intColor(i),brush=pg.mkColor(0.95))
                else:
                    plot.addPoints(x=[i+plot_x_offset],y=[counts],pen=pg.intColor(i),brush=pg.intColor(i))

        self.advance_next_image()
        self.display_rois()

    def advance_next_image(self):
        self.next_image += 1
        if self.next_image >= self.num_images:
            self.next_image = 0
        self.label_next_image.setText('Next image: {}'.format(self.next_image))

    def display_rois(self):
        viewbox = self.im_canvas.getViewBox()
        for item in viewbox.allChildren(): # remove unused ROIs
            if ((type(item) == pg.graphicsItems.ROI.ROI or 
                    type(item) == pg.graphicsItems.TextItem.TextItem)):
                viewbox.removeItem(item)

        for i, r in enumerate(self.rois):
            image_roi, image_label = r.get_image_roi(i)
                # reset_slot(r.roi.sigRegionChangeFinished, self.user_roi, True) 
                # reset_slot(r.threshedit.textEdited, self.update_plots, True)
            image_roi.setZValue(10)   # make sure the ROI is drawn above the image
            image_roi.setPen(pg.intColor(i), width=3)
            viewbox.addItem(image_roi)
            viewbox.addItem(image_label)
            image_roi.sigRegionChangeFinished.connect(self.set_rois_from_image)

    def redraw_counts_plots(self):
        for image, plot in enumerate(self.counts_plots):
            for line in plot.threshold_lines:
                plot.removeItem(line)
            plot.threshold_lines = []
            plot.scatter_plot.clear() # replot all points

            for i, r in enumerate(self.rois):
                line = pg.PlotDataItem([i-counts_plot_roi_offset,i+counts_plot_roi_offset],[r.t,r.t],pen={'color': 'k', 'width': 2})
                plot.addItem(line)
                plot.threshold_lines.append(line)
                plot_x_offsets = np.random.uniform(-counts_plot_roi_offset,counts_plot_roi_offset, size=len(r.counts[image]))
                for counts, plot_x_offset in zip(r.counts[image],plot_x_offsets):
                    if counts < r.t:
                        plot.scatter_plot.addPoints(x=[i+plot_x_offset],y=[counts],pen=pg.intColor(i),brush=pg.mkColor(0.95))
                    else:
                        plot.scatter_plot.addPoints(x=[i+plot_x_offset],y=[counts],pen=pg.intColor(i),brush=pg.intColor(i))

    def set_rois_from_image(self):
        """Sets the location of the ROIs in the table by the values currently
        drawn on the image.
        """
        for r in self.rois:
            [r.x,r.y] = [int(x) for x in r.image_roi.pos()]
            [r.w,r.h] = [int(x) for x in r.image_roi.size()]
        self.display_rois()
        self.update_table()

    def update_num_images(self):
        try:
            int(self.box_number_images.text())
        except ValueError:
            return
        if int(self.box_number_images.text()) < 1:
            self.box_number_images.setText(str(1))
        self.num_images = int(self.box_number_images.text())
        for r in self.rois:
            r.update_num_images(self.num_images)
        self.create_counts_plots()

    def create_counts_plots(self):
        font = QFont()
        font.setPixelSize(14)
        num_images = self.num_images

        for i in range(len(self.counts_plots)-1,num_images-1,-1): # stop displaying unneeded widgets
            self.layout_plots.itemAt(i).widget().setParent(None)

        self.counts_plots = self.counts_plots[:num_images] # remove unneeded widgets
        
        for i in range(len(self.counts_plots), num_images): # make new widgets if needed
            counts_plot = pg.PlotWidget()
            counts_plot.setTitle('Image {}'.format(i))
            counts_plot.getAxis('bottom').tickFont = font
            counts_plot.getAxis('left').tickFont = font
            counts_plot.scatter_plot = pg.ScatterPlotItem()
            counts_plot.addItem(counts_plot.scatter_plot)
            counts_plot.threshold_lines = []
            self.layout_plots.addWidget(counts_plot)
            self.counts_plots.append(counts_plot)

        self.redraw_counts_plots()

    def clear_data(self):
        for r in self.rois:
            r.clear_data()
        self.redraw_counts_plots()

class SingleAtomImageAnalyser(pg.PlotWidget):
    """Class to show display relating to individual ROIs (e.g. loading 
    probability, single-site recapture probability)."""
    def __init__(self, rois, image=0, conditions=None):
        """Initiates the class with the list of rois so that the SAIA can 
        obtain needed data."""
        super().__init__()
        self.rois = rois
        self.
    
    def create_counts_plots(self):
        self.plot = pg.PlotWidget()
        self.plot.scatter_plot = pg.ScatterPlotItem()
        self.plot.addItem(self.plot.scatter_plot)
        self.plot.threshold_lines = []
        self.layout_plots.addWidget(self.plot)

        self.redraw_counts_plots()

'''
    #### #### user input functions #### #### 

    def reset_name(self, text=''):
        """Take a new name for the window, display it in the window title."""
        self.name = self.name_edit.text()
        self.setWindowTitle(self.name+' - Single Atom Image Analyser -')

    def set_user_var(self, text=''):
        """When the user finishes editing the var_edit line edit, update the displayed 
        user variable and assign it in the temp_vals of the histo_handler"""
        if self.var_edit.text():
            self.histo_handler.temp_vals['User variable'
                ] = self.histo_handler.types['User variable'](self.var_edit.text())
        self.stat_labels['User variable'].setText(self.var_edit.text())
            
    def pic_size_text_edit(self, text):
        """Update the specified size of an image in pixels when the user 
        edits the text in the line edit widget"""
        width, height = self.pic_width_edit.text(), self.pic_height_edit.text()
        if width and height: # can't convert '' to int
            self.image_handler.pic_width = int(width)
            self.image_handler.pic_height = int(height)
            self.image_handler.create_rect_mask()
            self.pic_size_label.setText('('+width+','+height+')')

    def CCD_stat_edit(self, emg=1, pag=4.5, Nr=8.8, acq_change=False):
        """Update the values used for the EMCCD bias offset and readout noise"""
        if self.bias_offset_edit.text(): # check the label isn't empty
            self.image_handler.bias = int(self.bias_offset_edit.text())
        if acq_change: # If the acquisition settings have been changed by the camera
            self.histo_handler.emg, self.histo_handler.pag, self.histo_handler.Nr = emg, pag, Nr
            self.histo_handler.dg = 2.0 if self.histo_handler.emg > 1 else 1.0 # multiplicative noise factor
        
    def roi_text_edit(self, text):
        """Update the ROI position and size every time a text edit is made by
        the user to one of the line edit widgets"""
        xc, yc, l = [self.roi_x_edit.text(),
                            self.roi_y_edit.text(), self.roi_l_edit.text()]
        if any(v == '' for v in [xc, yc, l]):
            xc, yc, l = 1, 1, 1 # default 
        else:
            xc, yc, l = list(map(int, [xc, yc, l])) # crashes if the user inputs float
            
        if any(v > max(self.image_handler.pic_width, self.image_handler.pic_height) for v in [xc, yc, l]):
            xc, yc, l = 1, 1, 1
        
        if (xc - l//2 < 0 or yc - l//2 < 0 
            or xc + l//2 > self.image_handler.pic_width 
            or yc + l//2 > self.image_handler.pic_height):
            l = 2*min([xc, yc])  # can't have the boundary go off the edge
        if int(l) == 0:
            l = 1 # can't have zero width
        self.image_handler.set_roi(dimensions=list(map(int, [xc, yc, l])))
        self.xc_label.setText('ROI x_c = '+str(xc)) 
        self.yc_label.setText('ROI y_c = '+str(yc))
        self.l_label.setText('ROI size = '+str(l))
        # update ROI on image canvas
        # note: setting the origin as top left because image is inverted
        self.roi.setSize((l, l)) 
        self.roi.setPos(xc - l//2, yc - l//2) 

    def user_roi(self, pos):
        """Update position of ROI"""
        x0, y0 = self.roi.pos()  # lower left corner of bounding rectangle
        xw, yw = self.roi.size() # widths
        l = int(0.5*(xw+yw))  # want a square ROI
        # note: setting the origin as bottom left but the image has origin top left
        xc, yc = int(x0 + l//2), int(y0 + l//2)  # centre
        self.image_handler.set_roi(dimensions=[xc, yc, l])
        self.xc_label.setText('ROI x_c = '+str(xc)) 
        self.yc_label.setText('ROI y_c = '+str(yc))
        self.l_label.setText('ROI size = '+str(l))
        self.roi_l_edit.setText(str(l)) 
        self.roi_x_edit.setText(str(xc))
        self.roi_y_edit.setText(str(yc))
        
    def bins_text_edit(self, text):
        """Update the histogram bins every time a text edit is made by the user
        to one of the line edit widgets."""
        # bin_actions = [Auto, Manual, No Display, No Update]
        if self.bin_actions[1].isChecked(): 
            new_vals = [
                self.min_counts_edit.text(), self.max_counts_edit.text(), self.num_bins_edit.text()]          
            # if the line edit widget is empty, take an estimate from histogram values
            if new_vals[0] == '' and self.image_handler.ind > 0: # min
                new_vals[0] = min(self.image_handler.stats['Counts'])
            if new_vals[1] == '' and self.image_handler.ind > 0: # max
                new_vals[1] = max(self.image_handler.stats['Counts'])
            elif not any(v == '' for v in new_vals[:2]) and int(new_vals[1]) < int(new_vals[0]):
                return 0  # can't have min > max
            if new_vals[2] == '' and self.image_handler.ind > 0: # num bins
                # min 17 bins. Increase with # images and with separation
                new_vals[2] = int(17 + self.image_handler.ind//100 + 
                    ((float(new_vals[1]) - float(new_vals[0]))/float(new_vals[1]))**2 * 15)
            if any(v == '' for v in new_vals) and self.image_handler.ind == 0:
                new_vals = [0, 1, 10] # catch all
            if int(new_vals[2] if new_vals[2] else 0) < 2:  # 0 bins causes value error
                new_vals[2] = 10
            min_bin, max_bin, num_bins = list(map(int, new_vals))
            # set the new values for the bins of the image handler
            self.image_handler.bin_array = np.linspace(min_bin, max_bin, num_bins)
            # set the new threshold if supplied
        if self.thresh_toggle.isChecked():
            try:
                self.image_handler.thresh = float(self.thresh_edit.text())
                self.stat_labels['Threshold'].setText(str(int(self.image_handler.thresh)))
            except (KeyError, ValueError): pass # user switched toggle before inputing text
            if not (self.bin_actions[2].isChecked() or self.bin_actions[3].isChecked()):
                self.plot_current_hist(self.image_handler.histogram, self.hist_canvas) # doesn't update thresh
        else:
            if not (self.bin_actions[2].isChecked() or self.bin_actions[3].isChecked()):
                self.plot_current_hist(self.image_handler.hist_and_thresh, self.hist_canvas) # updates thresh
            
    #### #### toggle functions #### #### 

    def display_fit(self, toggle=True, fit_method='quick'):
        """Plot the best fit calculated by histo_handler.process
        and display the histogram statistics in the stat_labels"""
        success = self.update_fit(fit_method=fit_method)
        if success: 
            for key in self.histo_handler.stats.keys(): # update the text labels
                self.stat_labels[key].setText(str(self.histo_handler.temp_vals[key]))
            self.plot_current_hist(self.image_handler.histogram, self.hist_canvas)
            if (len(self.image_handler.stats['Counts']) > 50 and not any(self.image_handler.stats['Atom detected'][-50:]) 
                    and 'Im0' in self.objectName()):
                warning('Zero atoms detected in the last 50 shots of analysis '
                    +self.name+' '+self.multirun+' histogram %s.'%self.histo_handler.temp_vals['File ID']) 
            bf = self.histo_handler.bf # short hand
            if bf and bf.bffunc and type(bf.ps)!=type(None): # plot the curve on the histogram
                xs = np.linspace(min(bf.x), max(bf.x), 200)
                self.hist_canvas.plot(xs, bf.bffunc(xs, *bf.ps), pen='b')
        return success

    def update_fit(self, toggle=True, fit_method='quick'):
        """Use the histo_handler.process function to get histogram
        statistics and a best fit from the current data."""
        sendertext = ''
        if hasattr(self.sender(), 'text'): # could be called by a different sender
            sendertext = self.sender().text()
        if fit_method == 'check action' or sendertext == 'Get best fit':
            try: fit_method = self.fit_options.checkedAction().text()
            except AttributeError: fit_method = 'quick'
        elif sendertext == 'Update statistics':
            fit_method = 'quick'
        return self.histo_handler.process(self.image_handler, self.stat_labels['User variable'].text(), 
            fix_thresh=self.thresh_toggle.isChecked(), method=fit_method)

    def update_varplot_axes(self, label=''):
        """The user selects which variable they want to display on the plot
        The variables are read from the x and y axis QComboBoxes
        Then the plot is updated"""
        if np.size(self.histo_handler.stats['File ID']) > 0:
            self.histo_handler.xvals = np.array(self.histo_handler.stats[
                                str(self.plot_labels[0].currentText())]) # set x values
            
            y_label = str(self.plot_labels[1].currentText())
            self.histo_handler.yvals = np.array(self.histo_handler.stats[y_label]) # set y values
            
            self.varplot_canvas.clear()  # remove previous data
            try:
                self.varplot_canvas.plot(self.histo_handler.xvals, 
                            self.histo_handler.yvals, pen=None, symbol='o')
                # add error bars if available:
                if ('Fidelity' in y_label 
        or 'Background peak count' in y_label or 'Signal peak count' in y_label
        or 'survival probability' in y_label or 'Condition met' in y_label):
                    # add widget for errorbars
                    # estimate sensible beam width at the end of the errorbar
                    err_bars = pg.ErrorBarItem(x=self.histo_handler.xvals, y=self.histo_handler.yvals, 
                        height=2*np.array(self.histo_handler.stats['Error in '+y_label]), beam=0) 
                    self.varplot_canvas.addItem(err_bars)
                elif 'Loading probability' in y_label:
                    err_bars = pg.ErrorBarItem(x=self.histo_handler.xvals, y=self.histo_handler.yvals, 
                        top=np.array(self.histo_handler.stats['Upper Error in '+y_label]),
                        bottom=np.array(self.histo_handler.stats['Lower Error in '+y_label]), beam=0) 
                    self.varplot_canvas.addItem(err_bars)
            except Exception: pass # probably wrong length of arrays

    def clear_varplot(self):
        """Clear the plot of histogram statistics by resetting the histo_handler.
        The data is not lost since it has been appended to the log file."""
        self.histo_handler.reset_arrays() # empty the stored arrays
        self.varplot_canvas.clear()    # clear the displayed plot

    def set_thresh(self, toggle):
        """If the toggle is true, the user supplies the threshold value and it is
        kept constant using the image_handler.histogram() function. Otherwise,
        update the threshold with image_handler.hist_and_thresh()"""
        reset_slot(self.event_im, self.update_plot, not toggle) # remove slot
        reset_slot(self.event_im, self.update_plot_only, toggle) # reconnect
        self.bins_text_edit('reset') # update histogram

    def set_im_show(self, toggle):
        """If the toggle is True, always update the widget with the last image."""
        reset_slot(self.event_im, self.update_im, toggle)

    def swap_signals(self):
        """Disconnect the image_handler process signal from the signal
        and (re)connect the update plot"""
        reset_slot(self.event_im, self.update_plot_only, self.thresh_toggle.isChecked())
        reset_slot(self.event_im, self.update_plot, not self.thresh_toggle.isChecked())
    
    def set_bins(self, action=None):
        """Check which of the bin action menu bar options is checked.
        If the toggle is Automatic, use automatic histogram binning.
        If the toggle is Manual, read in values from the line edit 
        widgets.
        If the toggle is No Display, processes files but doesn't show on histogram
        If the toggle is No Update, files are not processed for the histogram."""
        reset_slot(self.event_im, self.image_handler.process, False)
        if self.bin_actions[1].isChecked(): # manual
            self.swap_signals()  # disconnect image handler, reconnect plot
            self.bins_text_edit('reset')            
        elif self.bin_actions[0].isChecked(): # automatic
            self.swap_signals()  # disconnect image handler, reconnect plot
            self.image_handler.bin_array = []
            if self.image_handler.ind > 0:
                if self.thresh_toggle.isChecked():
                    self.plot_current_hist(self.image_handler.histogram, self.hist_canvas)
                else:
                    self.plot_current_hist(self.image_handler.hist_and_thresh, self.hist_canvas)
        elif self.bin_actions[2].isChecked() or self.bin_actions[3].isChecked(): # No Display or No Update
            reset_slot(self.event_im, self.update_plot, False)
            reset_slot(self.event_im, self.update_plot_only, False)
            # set the text of the most recent file
            reset_slot(self.event_im, self.show_recent_file, True) # might need a better label
            # just process the image
            if self.bin_actions[2].isChecked():
                reset_slot(self.event_im, self.image_handler.process, True)
                
            
    #### #### canvas functions #### #### 

    def show_recent_file(self, im=0):
        """Display the file ID of the last processed file"""
        self.recent_label.setText('Most recent image: '
                            + str(self.image_handler.fid))

    def plot_current_hist(self, hist_function, hist_canvas):
        """Plot the histogram from the given image_handler on
        the given histogram canvas hist_canvas.
        hist_function is used to make the histogram and allows the toggling of
        different functions that may or may not update the threshold value."""
        # update the histogram and threshold estimate
        bins, occ, thresh = hist_function()
        hist_canvas.clear()
        hist_canvas.plot(bins, occ, stepMode=True, pen='k',
                                fillLevel=0, brush = (220,220,220,220)) # histogram
        hist_canvas.plot([thresh]*2, [0, max(occ)], pen='r') # threshold line
    
    def update_im(self, im, include=True):
        """Receive the image array emitted from the event signal
        display the image in the image canvas.
        event_im: [image (np.ndarray), include? (bool)]"""
        try:
            self.im_canvas.setImage(im)
            h = self.im_canvas.getHistogram()
            vmin, vmax = np.min(im), np.max(im)
            if self.vmin_edit.text():
                vmin = int(self.vmin_edit.text())
            if self.vmax_edit.text():
                vmax = int(self.vmax_edit.text())
            self.im_hist.setLevels(vmin, vmax)
        except ValueError as e:
            error('Cannot plot image. Probably CCD saturated.\n'+str(e))

    def update_plot(self, im, include=True):
        """Receive the event image and whether it's valid emitted from the 
        camera. Process the image array with the image handler and update
        the figure.
        event_im: [image (np.ndarray), include? (bool)]"""
        # add the count
        t1 = time.time()
        self.image_handler.process(im, include)
        t2 = time.time()
        self.int_time = t2 - t1
        # display the name of the most recent file
        self.recent_label.setText('Just processed image '
                            + str(self.image_handler.fid))
        self.plot_current_hist(self.image_handler.hist_and_thresh, self.hist_canvas) # update the displayed plot
        self.plot_time = time.time() - t2

    def update_plot_only(self, im, include=True):
        """Receive the event image and whether it's valid emitted from the 
        camera. Process the image array with the image handler and update
        the figure but without changing the threshold value.
        event_im: [image (np.ndarray), include? (bool)]"""
        # add the count
        t1 = time.time()
        self.image_handler.process(im, include)
        t2 = time.time()
        self.int_time = t2 - t1
        # display the name of the most recent file
        self.recent_label.setText('Just processed image '
                            + str(self.image_handler.fid))
        self.plot_current_hist(self.image_handler.histogram, self.hist_canvas) # update the displayed plot
        self.plot_time = time.time() - t2

    def add_stats_to_plot(self, toggle=True):
        """Take the current histogram statistics from the Histogram Statistics labels
        and add the values to the variable plot, saving the parameters to the log
        file at the same time. If any of the labels are empty, replace them with 0."""
        # append current statistics to the histogram handler's list
        for key in self.stat_labels.keys():
            value = self.histo_handler.types[key](self.stat_labels[key].text()) if self.stat_labels[key].text() else 0
            self.histo_handler.stats[key].append(value)
            self.histo_handler.temp_vals[key] = value
        self.update_varplot_axes()  # update the plot with the new values
        self.histo_handler.ind = np.size(self.histo_handler.stats['File ID']) # index for histograms
        # append histogram stats to log file:
        try:
            with open(self.log_file_name, 'a') as f:
                f.write(','.join(list(map(str, self.histo_handler.temp_vals.values()))) + '\n')
        except (PermissionError, FileNotFoundError) as e:
            error("Analyser "+str(self.name)+" could not open file "+str(self.log_file_name) + 
                "\n" + str(e))

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
            if type(file_name) == str: self.last_path = file_name 
            return file_name
        except OSError: return '' # probably user cancelled

    def load_im_size(self):
        """Get the user to select an image file and then use this to get the image size"""
        file_name = self.try_browse(file_type='Images (*.asc);;all (*)', default_path=self.image_storage_path)
        if file_name:
            width, height = self.image_handler.set_pic_size(file_name) # sets image handler's pic size
            self.pic_width_edit.setText(str(width)) # update loaded value
            self.pic_height_edit.setText(str(height)) # update loaded value
            self.pic_size_label.setText('(%s,%s)'%(width, height)) # update loaded value

    def save_hist_data(self, trigger=None, save_file_name='', confirm=True):
        """Prompt the user to give a directory to save the histogram data, then save"""
        if not save_file_name:
            save_file_name = self.try_browse(title='Save File', file_type='csv(*.csv);;all (*)', 
                        open_func=QFileDialog.getSaveFileName)
        if save_file_name:
            # don't update the threshold  - trust the user to have already set it
            self.add_stats_to_plot()
            warnmsg = ''
            if not all(self.image_handler.stats['Include']):
                warnmsg = 'The user should check histogram ' + save_file_name + \
                    '\nAnalysis has flagged image %s as potentially mislabelled'%(
                        self.image_handler.stats['File ID'][next(i for i, x in enumerate(
                            self.image_handler.stats['Include']) if not x)])
                warning(warnmsg)
            # include most recent histogram stats as the top two lines of the header
            self.image_handler.save(save_file_name,
                         meta_head=list(self.histo_handler.temp_vals.keys()),
                         meta_vals=map(str, self.histo_handler.temp_vals.values())) # save histogram
            try: 
                hist_num = self.histo_handler.stats['File ID'][-1]
            except IndexError: # if there are no values in the stats yet
                hist_num = -1
            if confirm:
                msg = QMessageBox()
                msg.setIcon(QMessageBox.Information)
                msg.setText("File saved to "+save_file_name+"\n"+
                        "and appended histogram %s to log file.\n"%hist_num
                        +warnmsg)
                msg.setStandardButtons(QMessageBox.Ok)
                msg.exec_()

    def save_varplot(self, save_file_name='', confirm=True):
        """Save the data in the current plot, which is held in the histoHandler's
        dictionary and saved in the log file, to a new file."""
        if not save_file_name:
            save_file_name = self.try_browse(title='Save File', file_type='dat(*.dat);;all (*)',
                            open_func=QFileDialog.getSaveFileName)
        if save_file_name:
            self.histo_handler.save(save_file_name, meta_head=['SAIA Log file. Include:'],
                meta_vals=map(str, [i for i, incl in enumerate(self.histo_handler.stats['Include']) if incl]))
            if confirm:
                msg = QMessageBox()
                msg.setIcon(QMessageBox.Information)
                msg.setText("Plot data saved to file "+save_file_name)
                msg.setStandardButtons(QMessageBox.Ok)
                msg.exec_()
        
    def check_reset(self):
        """Ask the user if they would like to reset the current data stored"""
        reply = QMessageBox.question(self, 'Confirm Data Replacement',
            "Do you want to discard the current data?", 
            QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel, QMessageBox.Cancel)
        if reply == QMessageBox.Cancel:
            return 0
        elif reply == QMessageBox.Yes:
            self.image_handler.reset_arrays() # gets rid of old data
            self.histo_handler.bf = None
        return 1

    def load_empty_hist(self):
        """Prompt the user with options to save the data and then reset the 
        histogram"""
        reply = QMessageBox.question(self, 'Confirm reset', 
            'Save the current histogram before resetting?',
            QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel,
            QMessageBox.Cancel)
        if reply == QMessageBox.Cancel:
            return 0
        elif reply == QMessageBox.Yes:
            self.save_hist_data()  # prompt user for file name then save
            self.image_handler.reset_arrays() # get rid of old data
            self.hist_canvas.clear() # remove old histogram from display
        elif reply == QMessageBox.No:
            self.image_handler.reset_arrays() # get rid of old data
            self.hist_canvas.clear() # remove old histogram from display

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
                    warning("Failed to load image file: "+file_name+'\n'+str(e)) 
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
        image_storage_path = self.image_storage_path #+ '\%s\%s\%s'%(self.date[3],self.date[2],self.date[0])
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
            self.plot_current_hist(self.image_handler.histogram, self.hist_canvas)
            self.histo_handler.process(self.image_handler, self.stat_labels['User variable'].text(), 
                        fix_thresh=self.thresh_toggle.isChecked(), method='quick')
            if self.recent_label.text == 'Processing files...':
                self.recent_label.setText('Finished Processing')
        return im_list

    def load_from_csv(self, trigger=None):
        """Prompt the user to select a csv file to load histogram data from.
        It must have the specific layout that the image_handler saves in."""
        if self.check_reset():
            file_name = self.try_browse(file_type='csv(*.csv);;all (*)')
            if file_name:
                header = self.image_handler.load(file_name)
                if self.image_handler.ind > 0:
                    self.display_fit()
                    
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

    def load_from_log(self, trigger=None):
        """Prompt the user to select the log file then pass it to the histohandler"""
        file_name = self.try_browse(file_type='dat(*.dat);;all (*)')
        if file_name:
            success = self.histo_handler.load(file_name)
            if not success:
                print('Data was not loaded from the log file.')
            self.update_varplot_axes()

    #### #### testing functions #### #### 
        
    def print_times(self, unit="s"):
        """Display the times measured for functions"""
        scale = 1
        if unit == "ms" or unit == "milliseconds":
            scale *= 1e3
        elif unit == "us" or unit == "microseconds":
            scale *= 1e6
        else:
            unit = "s"
        print("Image processing duration: %.4g "%(
                self.int_time*scale)+unit)
        print("Image plotting duration: %.4g "%(
                self.plot_time*scale)+unit)
        
    #### #### UI management functions #### #### 

    def hard_reset(self, results_path='.', im_store_path='.', name='',
        im_handler=None, hist_handler=None):
        """Re-initialise to default"""
        self.name = name  # name is displayed in the window title
        self.image_handler = im_handler if im_handler else ih.image_handler() # class to process images
        self.histo_handler = hist_handler if hist_handler else hh.histo_handler() # class to process histograms
        self.date = time.strftime("%d %b %B %Y", time.localtime()).split(" ") # day short_month long_month year
        self.init_log(results_path) # write header to the log file that collects histograms
        self.image_storage_path = os.path.join(im_store_path, time.strftime(r"%Y\%B\%d")) # loading image files
        self.init_UI()  # make the widgets
        self.t0 = time.time() # time of initiation
        self.int_time = 0     # time taken to process an image
        self.plot_time = 0    # time taken to plot the graph
        self.set_bins() # connect signals

    def closeEvent(self, event, confirm=False):
        """Prompt user to save data on closing
        Keyword arguments:
        event   -- the PyQt closeEvent
        confirm -- toggle whether to display a pop-up window asking to save
            before closing."""
        if confirm:
            reply = QMessageBox.question(self, 'Confirm Action',
                "Save before closing?", QMessageBox.Yes |
                QMessageBox.No | QMessageBox.Cancel, QMessageBox.Cancel)
        else: reply = QMessageBox.No
        if reply == QMessageBox.Cancel:
            event.ignore()
        elif reply == QMessageBox.Yes or reply == QMessageBox.No:
            if reply == QMessageBox.Yes:
                self.save_hist_data()   # save current state
            event.accept()
        
####    ####    ####    #### 
'''

def run():
    """Initiate an app to run the program
    if running in Pylab/IPython then there may already be an app instance"""
    app = QApplication.instance()
    standalone = app is None # false if there is already an app instance
    if standalone: # if there isn't an instance, make one
        app = QApplication(sys.argv) 
        
    main_win = main_window()
    main_win.show()
    if standalone: # if an app instance was made, execute it
        sys.exit(app.exec_()) # when the window is closed, the python code also stops

if __name__ == "__main__":
    # change directory to this file's location
    os.chdir(os.path.dirname(os.path.realpath(__file__))) 
    run()
