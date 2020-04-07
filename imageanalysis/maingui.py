"""Single Atom Image Analysis
Stefan Spence 26/02/19

 - receive an image as an array from a pyqtSignal
 - set an ROI on the image and take an integrated count from the pixels
 - determine atom presence by comparison with a threshold count
 - plot a histogram of signal counts, which defines the threshold
"""
__version__ = '1.3'
import os
import sys
import time
import numpy as np
import pyqtgraph as pg    # not as flexible as matplotlib but works a lot better with qt
# some python packages use PyQt4, some use PyQt5...
try:
    from PyQt4.QtCore import pyqtSignal, QRegExp
    from PyQt4.QtGui import (QApplication, QPushButton, QWidget, QLabel, QAction,
            QGridLayout, QMainWindow, QMessageBox, QLineEdit, QIcon, QFileDialog,
            QDoubleValidator, QIntValidator, QComboBox, QMenu, QActionGroup, 
            QTabWidget, QVBoxLayout, QFont, QRegExpValidator, QInputDialog) 
except ImportError:
    from PyQt5.QtCore import pyqtSignal, QRegExp
    from PyQt5.QtGui import (QIcon, QDoubleValidator, QIntValidator, 
        QFont, QRegExpValidator)
    from PyQt5.QtWidgets import (QActionGroup, QVBoxLayout, QMenu, 
        QFileDialog, QComboBox, QMessageBox, QLineEdit, QGridLayout, 
        QApplication, QPushButton, QAction, QMainWindow, QWidget,
        QLabel, QTabWidget, QInputDialog)
import logging
logger = logging.getLogger(__name__)
import imageHandler as ih # process images to build up a histogram
import histoHandler as hh # collect data from histograms together
import fitCurve as fc   # custom class to get best fit parameters using curve_fit
          
####    ####    ####    ####

def remove_slot(signal, slot, reconnect=True):
    """Make sure all instances of slot are disconnected
    from signal. Prevents multiple connections to the same 
    slot. If reconnect=True, then reconnect slot to signal."""
    while True: # make sure that the slot is only connected once 
        try: signal.disconnect(slot)
        except TypeError: break
    if reconnect: signal.connect(slot)

####    ####    ####    ####

# main GUI window contains all the widgets                
class main_window(QMainWindow):
    """Main GUI window managing an instance of SAIA.

    Use Qt to produce the window where the histogram plot is shown.
    A simple interface allows the user to control the limits of the plot 
    and number of bins in the histogram. Separate tabs are made for 
    settings, the histogram, histogram statistics,
    displaying an image, and plotting histogram statistics.
     - The imageHandler module manages variables associated with individual 
        files and creates the histogram
     - The histoHandler module manages variables associated with the 
        collection of files in several histograms
     - The fitCurve module stores common functions for curve fitting.
    This GUI was produced with help from http://zetcode.com/gui/pyqt5/.
    Keyword arguments:
    results_path  -- directory to save log file and results to.
    im_store_path -- the directory where images are saved.
    name          -- an ID for this window, prepended to saved files.
    im_handler    -- an instance of image_handler
    hist_handler  -- an instance of histo_handler
    edit_ROI      -- whether the user can edit the ROI"""
    event_im = pyqtSignal([np.ndarray, bool])

    def __init__(self, results_path='.', im_store_path='.', name='',
                im_handler=None, hist_handler=None, edit_ROI=False):
        super().__init__()
        self.name = name  # name is displayed in the window title
        self.image_handler = im_handler if im_handler else ih.image_handler() # class to process images
        self.histo_handler = hist_handler if hist_handler else hh.histo_handler() # class to process histograms
        self.multirun = False # whether currently doing a multirun or not
        pg.setConfigOption('background', 'w') # set graph background default white
        pg.setConfigOption('foreground', 'k') # set graph foreground default black
        self.date = time.strftime("%d %b %B %Y", time.localtime()).split(" ") # day short_month long_month year
        self.log_file_name = results_path + 'log.dat' # in case init_log fails
        self.last_path = results_path # path history helps user get to the file they want
        self.init_log(results_path) # write header to the log file that collects histograms
        self.image_storage_path = im_store_path # used for loading image files
        self.init_UI(edit_ROI)  # make the widgets
        self.t0 = time.time() # time of initiation
        self.int_time = 0     # time taken to process an image
        self.plot_time = 0    # time taken to plot the graph
        self.set_bins() # connect signals

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
       

    def init_UI(self, edit_ROI=False):
        """Create all of the widget objects required
        edit_ROI - toggle whether the user can change the ROI"""
        self.centre_widget = QWidget()
        self.tabs = QTabWidget()       # make tabs for each main display 
        self.centre_widget.layout = QVBoxLayout()
        self.centre_widget.layout.addWidget(self.tabs)
        self.centre_widget.setLayout(self.centre_widget.layout)
        self.setCentralWidget(self.centre_widget)
        
        # validators for user input
        double_validator = QDoubleValidator() # floats
        int_validator    = QIntValidator()    # integers
        int_validator.setBottom(0) # don't allow -ve numbers

        # change font size
        font = QFont()
        font.setPixelSize(14)

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
        
        # histogram menu saves/loads/resets histogram and gives binning options
        hist_menu =  menubar.addMenu('Histogram')

        save_hist = QAction('Save histogram', self) # save current hist to csv
        save_hist.triggered.connect(self.save_hist_data)
        hist_menu.addAction(save_hist)

        reset_hist = QAction('Reset histogram', self) # reset hist without loading new data
        reset_hist.triggered.connect(self.load_empty_hist)
        hist_menu.addAction(reset_hist)
        
        load_menu = QMenu('Load histogram data', self)  # drop down menu for loading hist
        load_dir = QAction('From Files', self) # from image files (using file browser)
        load_dir.triggered.connect(self.load_from_files)
        load_menu.addAction(load_dir)
        load_fnums = QAction('From File Numbers', self) # from image file numbers
        load_fnums.triggered.connect(self.load_from_file_nums)
        load_menu.addAction(load_fnums)
        load_csv = QAction('From csv', self) # from csv of hist data
        load_csv.triggered.connect(self.load_from_csv)
        load_menu.addAction(load_csv)
        hist_menu.addMenu(load_menu)

        bin_menu = QMenu('Binning', self) # drop down menu for binning options
        bin_options = QActionGroup(bin_menu)  # group together the options
        self.bin_actions = []
        for action_label in ['Automatic', 'Manual', 'No Display', 'No Update']:
            self.bin_actions.append(QAction(
                action_label, bin_menu, checkable=True, 
                checked=action_label=='Automatic')) # default is auto
            bin_menu.addAction(self.bin_actions[-1])
            bin_options.addAction(self.bin_actions[-1])
        self.bin_actions[0].setChecked(True) # make sure default is auto
        bin_options.setExclusive(True) # only one option checked at a time
        bin_options.triggered.connect(self.set_bins) # connect the signal
        hist_menu.addMenu(bin_menu)
        
        fit_menu = QMenu('Fitting', self) # drop down menu for fitting options
        self.fit_options = QActionGroup(fit_menu)  # group together the options
        self.fit_methods = []
        for action_label in ['separate gaussians', 'double poissonian', 
                            'single gaussian', 'double gaussian']:
            self.fit_methods.append(QAction(action_label, fit_menu, checkable=True, 
                checked=action_label=='double gaussian')) # set default
            fit_menu.addAction(self.fit_methods[-1])
            self.fit_options.addAction(self.fit_methods[-1])
        self.fit_methods[-1].setChecked(True) # set last method as checked: double gaussian
        self.fit_options.setExclusive(True) # only one option checked at a time
        hist_menu.addMenu(fit_menu)

        # load plots from log files
        varplot_menu = menubar.addMenu('Plotting')

        load_varplot = QAction('Load from log file', self)
        load_varplot.triggered.connect(self.load_from_log)
        varplot_menu.addAction(load_varplot)

        #### tab for settings  ####
        settings_tab = QWidget()
        settings_grid = QGridLayout()
        settings_tab.setLayout(settings_grid)
        self.tabs.addTab(settings_tab, "Settings")

        # allow user to change window name
        name_label = QLabel('Window name: ', self)
        settings_grid.addWidget(name_label, 0,0, 1,1)
        self.name_edit = QLineEdit(self)
        settings_grid.addWidget(self.name_edit, 0,1, 1,1)
        self.name_edit.setText(self.name) # default
        self.name_edit.textChanged[str].connect(self.reset_name)

        # get user to set the image size in pixels
        # get user to set the image size in pixels
        self.pic_width_edit = QLineEdit(self)
        self.pic_height_edit = QLineEdit(self)
        for i, label in enumerate([['Image width: ', self.pic_width_edit, self.image_handler.pic_width], 
                ['Image height', self.pic_height_edit, self.image_handler.pic_height]]):
            textlabel = QLabel(label[0], self)
            settings_grid.addWidget(textlabel, 1,2*i, 1,1)
            settings_grid.addWidget(label[1], 1,2*i+1, 1,1)
            label[1].setText(str(label[2])) # default
            label[1].textChanged.connect(self.pic_size_text_edit)
            label[1].setValidator(int_validator)

        # get image size from loading an image
        # load_im_size = QPushButton('Load size from image', self)
        # load_im_size.clicked.connect(self.load_im_size) # load image size from image
        # load_im_size.resize(load_im_size.sizeHint())
        # settings_grid.addWidget(load_im_size, 1,2, 1,1)

        # get user to set ROI:
        # centre of ROI x position
        roi_xc_label = QLabel('ROI x_c: ', self)
        settings_grid.addWidget(roi_xc_label, 2,0, 1,1)
        self.roi_x_edit = QLineEdit(self)
        settings_grid.addWidget(self.roi_x_edit, 2,1, 1,1)
        self.roi_x_edit.setText('1')  # default
        self.roi_x_edit.textEdited[str].connect(self.roi_text_edit)
        self.roi_x_edit.setValidator(int_validator) # only numbers
        # whether or not the user can change this window's ROI
        self.roi_x_edit.setEnabled(edit_ROI) 
        
        # centre of ROI y position
        roi_yc_label = QLabel('ROI y_c: ', self)
        settings_grid.addWidget(roi_yc_label, 2,2, 1,1)
        self.roi_y_edit = QLineEdit(self)
        settings_grid.addWidget(self.roi_y_edit, 2,3, 1,1)
        self.roi_y_edit.setText('1')  # default
        self.roi_y_edit.textEdited[str].connect(self.roi_text_edit)
        self.roi_y_edit.setValidator(int_validator) # only numbers
        self.roi_y_edit.setEnabled(edit_ROI)
        
        # ROI size
        roi_l_label = QLabel('ROI size: ', self)
        settings_grid.addWidget(roi_l_label, 4,0, 1,1)
        self.roi_l_edit = QLineEdit(self)
        settings_grid.addWidget(self.roi_l_edit, 4,1, 1,1)
        self.roi_l_edit.setText('1')  # default
        self.roi_l_edit.textEdited[str].connect(self.roi_text_edit)
        self.roi_l_edit.setValidator(int_validator) # only numbers
        self.roi_l_edit.setEnabled(edit_ROI)

        # EMCCD bias offset
        bias_offset_label = QLabel('EMCCD bias offset: ', self)
        settings_grid.addWidget(bias_offset_label, 5,0, 1,1)
        self.bias_offset_edit = QLineEdit(self)
        settings_grid.addWidget(self.bias_offset_edit, 5,1, 1,1)
        self.bias_offset_edit.setText(str(self.image_handler.bias)) # default
        self.bias_offset_edit.editingFinished.connect(self.CCD_stat_edit)
        self.bias_offset_edit.setValidator(int_validator) # only ints

        # label to show last file analysed
        self.recent_label = QLabel('', self)
        settings_grid.addWidget(self.recent_label, 7,0, 1,4)
        
        #### tab for histogram ####
        hist_tab = QWidget()
        hist_grid = QGridLayout()
        hist_tab.setLayout(hist_grid)
        self.tabs.addTab(hist_tab, "Histogram")

        # main subplot of histogram
        self.hist_canvas = pg.PlotWidget()
        self.hist_canvas.getAxis('bottom').tickFont = font
        self.hist_canvas.getAxis('left').tickFont = font
        self.hist_canvas.setTitle("Histogram of CCD counts")
        hist_grid.addWidget(self.hist_canvas, 1,0, 6,8)  # allocate space in the grid
        
        # adjustable parameters: min/max counts, number of bins
        # min counts:
        min_counts_label = QLabel('Min. Counts: ', self)
        hist_grid.addWidget(min_counts_label, 0,0, 1,1)
        self.min_counts_edit = QLineEdit(self)
        hist_grid.addWidget(self.min_counts_edit, 0,1, 1,1)
        self.min_counts_edit.textChanged[str].connect(self.bins_text_edit)
        self.min_counts_edit.setValidator(int_validator)
        
        # max counts:
        max_counts_label = QLabel('Max. Counts: ', self)
        hist_grid.addWidget(max_counts_label, 0,2, 1,1)
        self.max_counts_edit = QLineEdit(self)
        hist_grid.addWidget(self.max_counts_edit, 0,3, 1,1)
        self.max_counts_edit.textChanged[str].connect(self.bins_text_edit)
        self.max_counts_edit.setValidator(int_validator)
        
        # number of bins
        num_bins_label = QLabel('# Bins: ', self)
        hist_grid.addWidget(num_bins_label, 0,4, 1,1)
        self.num_bins_edit = QLineEdit(self)
        hist_grid.addWidget(self.num_bins_edit, 0,5, 1,1)
        self.num_bins_edit.textChanged[str].connect(self.bins_text_edit)
        self.num_bins_edit.setValidator(int_validator)

        # user can set the threshold
        self.thresh_toggle = QPushButton('User Threshold: ', self)
        self.thresh_toggle.setCheckable(True)
        self.thresh_toggle.clicked[bool].connect(self.set_thresh)
        hist_grid.addWidget(self.thresh_toggle, 0,6, 1,1)
        # user inputs threshold
        self.thresh_edit = QLineEdit(self)
        hist_grid.addWidget(self.thresh_edit, 0,7, 1,1)
        self.thresh_edit.textChanged[str].connect(self.bins_text_edit)
        self.thresh_edit.setValidator(int_validator)
        
        #### tab for current histogram statistics ####
        stat_tab = QWidget()
        stat_grid = QGridLayout()
        stat_tab.setLayout(stat_grid)
        self.tabs.addTab(stat_tab, 'Histogram Statistics')

        # user variable value
        user_var_label = QLabel('User Variable: ', self)
        stat_grid.addWidget(user_var_label, 0,0, 1,1)
        self.var_edit = QLineEdit(self)
        self.var_edit.editingFinished.connect(self.set_user_var)
        stat_grid.addWidget(self.var_edit, 0,1, 1,3)
        self.var_edit.setText('0')  # default
        self.var_edit.setValidator(double_validator) # only numbers

        self.stat_labels = {}  # dictionary of stat labels
        # get the list of labels from the histogram handler
        for i, label_text in enumerate(self.histo_handler.stats.keys()):
            new_label = QLabel(label_text, self) # description
            stat_grid.addWidget(new_label, i+1,0, 1,1)
            self.stat_labels[label_text] = QLabel('', self) # value
            stat_grid.addWidget(self.stat_labels[label_text], i+1,1, 1,1)
            
        # update statistics
        self.stat_update_button = QPushButton('Update statistics', self)
        self.stat_update_button.clicked[bool].connect(self.display_fit)
        stat_grid.addWidget(self.stat_update_button, i+3,0, 1,1)

        # do Gaussian/Poissonian fit - peaks and widths
        self.fit_update_button = QPushButton('Get best fit', self)
        self.fit_update_button.clicked[bool].connect(self.display_fit)
        stat_grid.addWidget(self.fit_update_button, i+3,1, 1,1)

        # quickly add the current histogram statistics to the plot
        add_to_plot = QPushButton('Add to plot', self)
        add_to_plot.clicked[bool].connect(self.add_stats_to_plot)
        stat_grid.addWidget(add_to_plot, i+3,2, 1,1)

        #### tab for viewing images ####
        im_tab = QWidget()
        im_grid = QGridLayout()
        im_tab.setLayout(im_grid)
        self.tabs.addTab(im_tab, 'Image')
        # display the pic size widgets on this tab as well
        im_size_label = QLabel('Image Size in Pixels: ', self)
        im_grid.addWidget(im_size_label, 0,0, 1,1)
        self.pic_size_label = QLabel('', self)
        im_grid.addWidget(self.pic_size_label, 0,1, 1,1)
        self.pic_size_label.setText('(%s,%s)'%(self.image_handler.pic_width, self.image_handler.pic_height)) # default

        # toggle to continuously plot images as they come in
        self.im_show_toggle = QPushButton('Auto-display last image', self)
        self.im_show_toggle.setCheckable(True)
        self.im_show_toggle.clicked[bool].connect(self.set_im_show)
        im_grid.addWidget(self.im_show_toggle, 0,2, 1,1)
        
        im_grid_pos = 0 # starting column. 
        # centre of ROI x position
        self.xc_label = QLabel('ROI x_c: 0', self)
        im_grid.addWidget(self.xc_label, 7,im_grid_pos, 1,1)
        
        # centre of ROI y position
        self.yc_label = QLabel('ROI y_c: 0', self)
        im_grid.addWidget(self.yc_label, 7,im_grid_pos+2, 1,1)
        
        # ROI size
        self.l_label = QLabel('ROI size: 1', self)
        im_grid.addWidget(self.l_label, 7,im_grid_pos+4, 1,1)
        
        # display last image if toggle is True
        im_widget = pg.GraphicsLayoutWidget() # containing widget
        viewbox = im_widget.addViewBox() # plot area to display image
        self.im_canvas = pg.ImageItem() # the image
        viewbox.addItem(self.im_canvas)
        im_grid.addWidget(im_widget, 1,im_grid_pos, 6,8)
        # make an ROI that the user can drag
        self.roi = pg.ROI([0,0], [1,1], movable=False) 
        self.roi.sigRegionChangeFinished.connect(self.user_roi)
        viewbox.addItem(self.roi)
        self.roi.setZValue(10)   # make sure the ROI is drawn above the image
        # make a histogram to control the intensity scaling
        self.im_hist = pg.HistogramLUTItem()
        self.im_hist.setImageItem(self.im_canvas)
        im_widget.addItem(self.im_hist)
        
        # edits to allow the user to fix the intensity limits
        vmin_label = QLabel('Min. intensity: ', self)
        im_grid.addWidget(vmin_label, 8,im_grid_pos, 1,1)
        self.vmin_edit = QLineEdit(self)
        im_grid.addWidget(self.vmin_edit, 8,im_grid_pos+1, 1,1)
        self.vmin_edit.setText('')  # default auto from image
        self.vmin_edit.setValidator(int_validator) # only integers
        vmax_label = QLabel('Max. intensity: ', self)
        im_grid.addWidget(vmax_label, 8,im_grid_pos+2, 1,1)
        self.vmax_edit = QLineEdit(self)
        im_grid.addWidget(self.vmax_edit, 8,im_grid_pos+3, 1,1)
        self.vmax_edit.setText('')  # default auto from image
        self.vmax_edit.setValidator(int_validator) # only integers


        #### tab for plotting variables ####
        plot_tab = QWidget()
        plot_grid = QGridLayout()
        plot_tab.setLayout(plot_grid)
        self.tabs.addTab(plot_tab, 'Plotting')

        # main plot
        self.varplot_canvas = pg.PlotWidget()
        self.varplot_canvas.getAxis('bottom').tickFont = font
        self.varplot_canvas.getAxis('left').tickFont = font
        plot_grid.addWidget(self.varplot_canvas, 0,1, 6,8)
        
        # x and y labels
        self.plot_labels = [QComboBox(self), QComboBox(self)]
        for i in range(len(self.plot_labels)):
            # add options
            self.plot_labels[i].addItems(list(self.histo_handler.stats.keys())) 
            # connect buttons to update functions
            self.plot_labels[i].activated[str].connect(self.update_varplot_axes)
        # empty text box for the user to write their xlabel
        self.plot_labels.append(QLineEdit(self))
        # position labels in grid
        plot_grid.addWidget(self.plot_labels[0], 7,3, 1,1) # bottom middle
        plot_grid.addWidget(self.plot_labels[1], 2,0, 1,1) # middle left
        plot_grid.addWidget(self.plot_labels[2], 7,4, 1,1) # bottom middle

        # button to clear plot data (it's still saved in the log file)
        clear_varplot = QPushButton('Clear plot', self)
        clear_varplot.clicked[bool].connect(self.clear_varplot)
        plot_grid.addWidget(clear_varplot, 7,0, 1,1)

        # button to save plot data to separate file (it's also in the log file)
        save_varplot = QPushButton('Save plot data', self)
        save_varplot.clicked[bool].connect(self.save_varplot)
        plot_grid.addWidget(save_varplot, 5,0, 1,1)

        #### choose main window position and dimensions: (xpos,ypos,width,height)
        self.setGeometry(100, 150, 850, 500)
        self.setWindowTitle(self.name+' - Single Atom Image Analyser -')
        self.setWindowIcon(QIcon('docs/tempicon.png'))
        
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
        self.roi.setPos(xc - l//2, yc - l//2)
        self.roi.setSize(l, l)

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
        self.roi_x_edit.setText(str(xc))
        self.roi_y_edit.setText(str(yc))
        self.roi_l_edit.setText(str(l))
        
    def bins_text_edit(self, text):
        """Update the histogram bins every time a text edit is made by the user
        to one of the line edit widgets.
        Don't update the histogram binning if the multirun is going because it
        can affect the statistics."""
        # bin_actions = [Auto, Manual, No Display, No Update]
        if self.bin_actions[1].isChecked() and not self.multirun: 
            new_vals = [
                self.min_counts_edit.text(), self.max_counts_edit.text(), self.num_bins_edit.text()]          
            # if the line edit widget is empty, take an estimate from histogram values
            if new_vals[0] == '' and self.image_handler.ind > 0: # min
                new_vals[0] = min(self.image_handler.stats['Counts'])
            if new_vals[1] == '' and self.image_handler.ind > 0: # max
                new_vals[1] = max(self.image_handler.stats['Counts'])
            elif not any(v == '' for v in new_vals[:2]) and int(new_vals[1]) < int(new_vals[0]):
                # can't have max < min
                new_vals[1] = max(self.image_handler.stats['Counts'])
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
                except ValueError: pass # user switched toggle before inputing text
                self.plot_current_hist(self.image_handler.histogram, self.hist_canvas) # doesn't update thresh
            else:
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
            if len(self.image_handler.stats['Counts']) > 30 and not any(self.image_handler.stats['Atom detected']):
                logger.warning('Analysis '+self.name+' detected zero atoms in the last 30 shots.')
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
                if ('Loading probability' in y_label or 'Fidelity' in y_label 
        or 'Background peak count' in y_label or 'Signal peak count' in y_label):
                    # add widget for errorbars
                    # estimate sensible beam width at the end of the errorbar
                    if np.size(self.histo_handler.xvals)//2:
                        beam_width = 0.1*(self.histo_handler.xvals[1]
                                                - self.histo_handler.xvals[0])
                    else:
                        beam_width = 0.2
                    err_bars = pg.ErrorBarItem(x=self.histo_handler.xvals, 
                        y=self.histo_handler.yvals, 
                        height=np.array(self.histo_handler.stats['Error in '+y_label]),
                        beam=beam_width) # plot with error bars
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
        if not self.multirun: # don't interrupt multirun
            remove_slot(self.event_im, self.update_plot, not toggle) # remove slot
            remove_slot(self.event_im, self.update_plot_only, toggle) # reconnect
            self.bins_text_edit('reset') # update histogram

    def set_im_show(self, toggle):
        """If the toggle is True, always update the widget with the last image.
        Note that disconnecting all slots means that this toggle might have to
        be reset when other buttons are pressed."""
        remove_slot(self.event_im, self.update_im, toggle)

    def swap_signals(self):
        """Disconnect the image_handler process signal from the signal
        and (re)connect the update plot"""
        remove_slot(self.event_im, self.update_plot_only, self.thresh_toggle.isChecked())
        remove_slot(self.event_im, self.update_plot, not self.thresh_toggle.isChecked())
    
    def set_bins(self, action=None):
        """Check which of the bin action menu bar options is checked.
        If the toggle is Automatic, use automatic histogram binning.
        If the toggle is Manual, read in values from the line edit 
        widgets.
        If the toggle is No Display, processes files but doesn't show on histogram
        If the toggle is No Update, files are not processed for the histogram."""
        if not self.multirun: # don't interrupt multirun
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
                remove_slot(self.event_im, self.update_plot, False)
                remove_slot(self.event_im, self.update_plot_only, False)
                # set the text of the most recent file
                remove_slot(self.event_im, self.show_recent_file, True) # might need a better label
                # just process the image
                if self.bin_actions[2].isChecked():
                    remove_slot(self.event_im, self.image_handler.process, True)
                
            
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
        self.im_canvas.setImage(im)
        vmin, vmax = np.min(im), np.max(im)
        if self.vmin_edit.text():
            vmin = int(self.vmin_edit.text())
        if self.vmax_edit.text():
            vmax = int(self.vmax_edit.text())
        self.im_hist.setLevels(vmin, vmax)
        
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
        with open(self.log_file_name, 'a') as f:
            f.write(','.join(list(map(str, self.histo_handler.temp_vals.values()))) + '\n')

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
                logger.warning(warnmsg)
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
        self.image_storage_path = im_store_path # used for loading image files
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