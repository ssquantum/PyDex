"""Single Atom Image Analysis
Stefan Spence 26/02/19

 - receive an image as an array from a pyqtSignal
 - set an ROI on the image and take an integrated count from the pixels
 - determine atom presence by comparison with a threshold count
 - plot a histogram of signal counts, which defines the threshold

Assume that there are two peaks in the histogram 

"""
__version__ = '1.3'
import os
import sys
import time
import numpy as np
from astropy.stats import binom_conf_interval
import pyqtgraph as pg    # not as flexible as matplotlib but works a lot better with qt
# some python packages use PyQt4, some use PyQt5...
try:
    from PyQt4.QtCore import QThread, pyqtSignal, QEvent, QRegExp
    from PyQt4.QtGui import (QApplication, QPushButton, QWidget, QLabel, QAction,
            QGridLayout, QMainWindow, QMessageBox, QLineEdit, QIcon, QFileDialog,
            QDoubleValidator, QIntValidator, QComboBox, QMenu, QActionGroup, 
            QTabWidget, QVBoxLayout, QFont, QRegExpValidator, QInputDialog) 
except ImportError:
    from PyQt5.QtCore import QThread, pyqtSignal, QEvent, QRegExp
    from PyQt5.QtGui import (QGridLayout, QMessageBox, QLineEdit, QIcon, 
            QFileDialog, QDoubleValidator, QIntValidator, QComboBox, QMenu, 
            QActionGroup, QVBoxLayout, QFont, QRegExpValidator)
    from PyQt5.QtWidgets import (QApplication, QPushButton, QWidget, QTabWidget,
        QAction, QMainWindow, QLabel, QInputDialog)
import imageHandler as ih # process images to build up a histogram
import histoHandler as hh # collect data from histograms together
import directoryWatcher as dw # use watchdog to get file creation events
import fitCurve as fc   # custom class to get best fit parameters using curve_fit
          
####    ####    ####    ####

# main GUI window contains all the widgets                
class main_window(QMainWindow):
    """Main GUI window managing an instance of SAIA.

    Use Qt to produce the window where the histogram plot is shown.
    A simple interface allows the user to control the limits of the plot 
    and number of bins in the histogram. Separate tabs are made for 
    settings, multirun options, the histogram, histogram statistics,
    displaying an image, and plotting histogram statistics.
     - The imageHandler module manages variables associated with individual 
        files and creates the histogram
     - The histoHandler module manages variables associated with the 
        collection of files in several histograms
     - The fitCurve module stores common functions for curve fitting.
    This GUI was produced with help from http://zetcode.com/gui/pyqt5/.
    Keyword arguments:
    results_path -- directory to save log file and results to."""
    event_im = pyqtSignal(np.ndarray)

    def __init__(self, results_path='./'):
        super().__init__()
        self.bias = 697   # bias off set from EMCCD
        self.Nr   = 8.8   # read-out noise from EMCCD
        self.image_handler = ih.image_handler() # class to process images
        self.histo_handler = hh.histo_handler() # class to process histograms
        self.hist_num = 0 # ID number for the next histogram 
        pg.setConfigOption('background', 'w') # set graph background default white
        pg.setConfigOption('foreground', 'k') # set graph foreground default black
        self.date = time.strftime("%d %b %B %Y", time.localtime()).split(" ") # day short_month long_month year
        self.init_log(results_path) # write header to the log file that collects histograms
        self.init_UI()  # make the widgets
        self.t0 = time.time() # time of initiation
        self.int_time = 0     # time taken to process an image
        self.plot_time = 0    # time taken to plot the graph

    def init_log(self, results_path='./'):
        """Create a directory for today's date as a subdirectory in the log file path
        then write the header to the log file path defined in config.dat"""
        # make subdirectory if it doesn't already exist
        results_path = os.path.join(results_path, 
                    '/%s/%s/%s'%(self.date[3],self.date[2],self.date[0]))
        try:
            os.makedirs(results_path, exist_ok=True)
        except PermissionError:  # couldn't access the path, start a log file here
            results_path = './%s/%s/%s'%(self.date[3],self.date[2],self.date[0])
            os.makedirs(results_path, exist_ok=True)

        # log is saved in a dated subdirectory and the file name also has the date
        self.log_file_name = os.path.join(results_path, 
                   'log'+self.date[0]+self.date[1]+self.date[3]+'.dat')  
        # write the header to the log file
        if not os.path.isfile(self.log_file_name): # don't overwrite if it already exists
            with open(self.log_file_name, 'w+') as f:
                f.write('#Single Atom Image Analyser Log File: collects histogram data\n')
                f.write('#include --[]\n')
                f.write('#'+', '.join(self.histo_handler.stats_dict.keys())+'\n')
       

    def init_UI(self):
        """Create all of the widget objects required"""
        # grid layout: central main plot, params above, dir watcher status at bottom
        self.centre_widget = QWidget()
        self.tabs = QTabWidget()                   # make tabs for each main display 
        self.centre_widget.layout = QVBoxLayout()
        self.centre_widget.layout.addWidget(self.tabs)
        self.centre_widget.setLayout(self.centre_widget.layout)
        self.setCentralWidget(self.centre_widget)
        
        # validators for user input
        reg_exp = QRegExp(r'([0-9]+(\.[0-9]+)?,?)+')
        comma_validator = QRegExpValidator(reg_exp) # floats and commas
        double_validator = QDoubleValidator() # floats
        int_validator = QIntValidator()       # integers

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
        # load_fnums.triggered.connect(self.load_from_file_nums)
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
        bin_options.setExclusive(True) # only one option checked at a time
        bin_options.triggered.connect(self.set_bins) # connect the signal
        hist_menu.addMenu(bin_menu)

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

        # get user to set the image size in pixels
        size_label = QLabel('Image size in pixels: ', self)
        settings_grid.addWidget(size_label, 0,0, 1,1)
        self.pic_size_edit = QLineEdit(self)
        settings_grid.addWidget(self.pic_size_edit, 0,1, 1,1)
        self.pic_size_edit.setText(str(self.image_handler.pic_size)) # default
        self.pic_size_edit.textChanged[str].connect(self.pic_size_text_edit)
        self.pic_size_edit.setValidator(int_validator)

        # get image size from loading an image
        load_im_size = QPushButton('Load size from image', self)
        load_im_size.clicked.connect(self.load_im_size) # load image size from image
        load_im_size.resize(load_im_size.sizeHint())
        settings_grid.addWidget(load_im_size, 0,2, 1,1)

        # get ROI centre from loading an image
        load_roi = QPushButton('Get ROI from image', self)
        load_roi.clicked.connect(self.load_roi) # load roi centre from image
        load_roi.resize(load_im_size.sizeHint())
        settings_grid.addWidget(load_roi, 1,2, 1,1)

        # get user to set ROI:
        # centre of ROI x position
        roi_xc_label = QLabel('ROI x_c: ', self)
        settings_grid.addWidget(roi_xc_label, 1,0, 1,1)
        self.roi_x_edit = QLineEdit(self)
        settings_grid.addWidget(self.roi_x_edit, 1,1, 1,1)
        self.roi_x_edit.setText('0')  # default
        self.roi_x_edit.textEdited[str].connect(self.roi_text_edit)
        self.roi_x_edit.setValidator(int_validator) # only numbers
        
        # centre of ROI y position
        roi_yc_label = QLabel('ROI y_c: ', self)
        settings_grid.addWidget(roi_yc_label, 2,0, 1,1)
        self.roi_y_edit = QLineEdit(self)
        settings_grid.addWidget(self.roi_y_edit, 2,1, 1,1)
        self.roi_y_edit.setText('0')  # default
        self.roi_y_edit.textEdited[str].connect(self.roi_text_edit)
        self.roi_y_edit.setValidator(int_validator) # only numbers
        
        # ROI size
        roi_l_label = QLabel('ROI size: ', self)
        settings_grid.addWidget(roi_l_label, 3,0, 1,1)
        self.roi_l_edit = QLineEdit(self)
        settings_grid.addWidget(self.roi_l_edit, 3,1, 1,1)
        self.roi_l_edit.setText('1')  # default
        self.roi_l_edit.textEdited[str].connect(self.roi_text_edit)
        self.roi_l_edit.setValidator(int_validator) # only numbers

        # EMCCD bias offset
        bias_offset_label = QLabel('EMCCD bias offset: ', self)
        settings_grid.addWidget(bias_offset_label, 4,0, 1,1)
        self.bias_offset_edit = QLineEdit(self)
        settings_grid.addWidget(self.bias_offset_edit, 4,1, 1,1)
        self.bias_offset_edit.setText(str(self.bias)) # default
        self.bias_offset_edit.editingFinished.connect(self.CCD_stat_edit)
        self.bias_offset_edit.setValidator(double_validator) # only floats

        # EMCCD readout noise
        read_noise_label = QLabel('EMCCD read-out noise: ', self)
        settings_grid.addWidget(read_noise_label, 5,0, 1,1)
        self.read_noise_edit = QLineEdit(self)
        settings_grid.addWidget(self.read_noise_edit, 5,1, 1,1)
        self.read_noise_edit.setText(str(self.Nr)) # default
        self.read_noise_edit.editingFinished.connect(self.CCD_stat_edit)
        self.read_noise_edit.setValidator(double_validator) # only floats
        
        # label to show last file analysed
        self.recent_label = QLabel('', self)
        settings_grid.addWidget(self.recent_label, 6,0, 1,4)
        

        #### tab for multi-run settings ####
        multirun_tab = QWidget()
        multirun_grid = QGridLayout()
        multirun_tab.setLayout(multirun_grid)
        self.tabs.addTab(multirun_tab, "Multirun")

        # dictionary for multirun settings
        self.mr = {'# omit':0, '# hist':100, 'var list':[], 
                'prefix':'0', 'o':0, 'h':0, 'v':0, 
                'measure':0}

        # user chooses an ID as a prefix for the histogram files
        measure_label = QLabel('Measure prefix: ', self)
        multirun_grid.addWidget(measure_label, 0,0, 1,1)
        self.measure_edit = QLineEdit(self)
        multirun_grid.addWidget(self.measure_edit, 0,1, 1,1)
        self.measure_edit.setText(str(self.mr['prefix']))
        
        # user chooses a variable to include in the multi-run
        entry_label = QLabel('User variable: ', self)
        multirun_grid.addWidget(entry_label, 1,0, 1,1)
        self.entry_edit = QLineEdit(self)
        multirun_grid.addWidget(self.entry_edit, 1,1, 1,1)
        self.entry_edit.returnPressed.connect(self.add_var_to_multirun)
        self.entry_edit.setValidator(comma_validator)
        # add the current variable to list
        add_var_button = QPushButton('Add to list', self)
        add_var_button.clicked.connect(self.add_var_to_multirun)
        add_var_button.resize(add_var_button.sizeHint())
        multirun_grid.addWidget(add_var_button, 1,2, 1,1)
        # display current list of user variables
        var_list_label = QLabel('Current list: ', self)
        multirun_grid.addWidget(var_list_label, 2,0, 1,1)
        self.multirun_vars = QLabel('', self)
        multirun_grid.addWidget(self.multirun_vars, 2,1, 1,1)
        # clear the current list of user variables
        clear_vars_button = QPushButton('Clear list', self)
        clear_vars_button.clicked.connect(self.clear_multirun_vars)
        clear_vars_button.resize(clear_vars_button.sizeHint())
        multirun_grid.addWidget(clear_vars_button, 2,2, 1,1)
        
        # choose how many files to omit before starting the next histogram
        omit_label = QLabel('Omit the first N files: ', self)
        multirun_grid.addWidget(omit_label, 3,0, 1,1)
        self.omit_edit = QLineEdit(self)
        multirun_grid.addWidget(self.omit_edit, 3,1, 1,1)
        self.omit_edit.setText(str(self.mr['# omit'])) # default
        self.omit_edit.setValidator(int_validator)

        # choose how many files to have in one histogram
        hist_size_label = QLabel('# files in the histogram: ', self)
        multirun_grid.addWidget(hist_size_label, 4,0, 1,1)
        self.multirun_hist_size = QLineEdit(self)
        multirun_grid.addWidget(self.multirun_hist_size, 4,1, 1,1)
        self.multirun_hist_size.setText(str(self.mr['# hist'])) # default
        self.multirun_hist_size.setValidator(int_validator)

        # choose the directory to save histograms and measure files to
        multirun_dir_button = QPushButton('Choose directory to save to: ', self)
        multirun_grid.addWidget(multirun_dir_button, 5,0, 1,1)
        multirun_dir_button.clicked.connect(self.choose_multirun_dir)
        multirun_dir_button.resize(multirun_dir_button.sizeHint())
        # default directory is the results folder
        self.multirun_save_dir = QLabel(self.get_default_path(), self)
        multirun_grid.addWidget(self.multirun_save_dir, 5,1, 1,1)

        # start/abort the multirun
        self.multirun_switch = QPushButton('Start', self, checkable=True)
        self.multirun_switch.clicked[bool].connect(self.multirun_go)
        multirun_grid.addWidget(self.multirun_switch, 6,1, 1,1)
        # pause/restart the multirun
        self.multirun_pause = QPushButton('Resume', self)
        self.multirun_pause.clicked.connect(self.multirun_resume)
        multirun_grid.addWidget(self.multirun_pause, 6,2, 1,1)

        # display current progress
        self.multirun_progress = QLabel(
            'User variable: , omit 0 of 0 files, 0 of 100 histogram files, 0% complete')
        multirun_grid.addWidget(self.multirun_progress, 712,0, 1,3)

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
        self.min_counts_edit.setValidator(double_validator)
        
        # max counts:
        max_counts_label = QLabel('Max. Counts: ', self)
        hist_grid.addWidget(max_counts_label, 0,2, 1,1)
        self.max_counts_edit = QLineEdit(self)
        hist_grid.addWidget(self.max_counts_edit, 0,3, 1,1)
        self.max_counts_edit.textChanged[str].connect(self.bins_text_edit)
        self.max_counts_edit.setValidator(double_validator)
        
        # number of bins
        num_bins_label = QLabel('# Bins: ', self)
        hist_grid.addWidget(num_bins_label, 0,4, 1,1)
        self.num_bins_edit = QLineEdit(self)
        hist_grid.addWidget(self.num_bins_edit, 0,5, 1,1)
        self.num_bins_edit.textChanged[str].connect(self.bins_text_edit)
        self.num_bins_edit.setValidator(double_validator)

        # user can set the threshold
        self.thresh_toggle = QPushButton('User Threshold: ', self)
        self.thresh_toggle.setCheckable(True)
        self.thresh_toggle.clicked[bool].connect(self.set_thresh)
        hist_grid.addWidget(self.thresh_toggle, 0,6, 1,1)
        # user inputs threshold
        self.thresh_edit = QLineEdit(self)
        hist_grid.addWidget(self.thresh_edit, 0,7, 1,1)
        self.thresh_edit.textChanged[str].connect(self.bins_text_edit)
        self.thresh_edit.setValidator(double_validator)
        
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
        stat_grid.addWidget(self.var_edit, 0,1, 1,1)
        self.var_edit.setText('0')  # default
        self.var_edit.setValidator(double_validator) # only numbers

        self.stat_labels = {}  # dictionary of stat labels
        # get the list of labels from the histogram handler
        for i, label_text in enumerate(self.histo_handler.stats_dict.keys()):
            new_label = QLabel(label_text, self) # description
            stat_grid.addWidget(new_label, i+1,0, 1,1)
            self.stat_labels[label_text] = QLabel('', self) # value
            stat_grid.addWidget(self.stat_labels[label_text], i+1,1, 1,1)
            
        # update statistics
        self.stat_update_button = QPushButton('Update statistics', self)
        self.stat_update_button.clicked[bool].connect(self.update_stats)
        stat_grid.addWidget(self.stat_update_button, i+2,0, 1,1)

        # do Gaussian/Poissonian fit - peaks and widths
        self.fit_update_button = QPushButton('Get best fit', self)
        self.fit_update_button.clicked[bool].connect(self.update_fit)
        stat_grid.addWidget(self.fit_update_button, i+2,1, 1,1)

        # do a Gaussian fit just to the background peak
        self.fit_bg_button = QPushButton('Fit background', self)
        self.fit_bg_button.clicked[bool].connect(self.fit_bg_gaussian)
        stat_grid.addWidget(self.fit_bg_button, i+2,2, 1,1)

        # quickly add the current histogram statistics to the plot
        add_to_plot = QPushButton('Add to plot', self)
        add_to_plot.clicked[bool].connect(self.add_stats_to_plot)
        stat_grid.addWidget(add_to_plot, i+3,1, 1,1)

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
        self.pic_size_label.setText(str(self.image_handler.pic_size)) # default

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
        self.roi = pg.ROI([0,0], [1,1]) 
        self.roi.addScaleHandle([1,1], [0.5,0.5]) # allow user to adjust ROI size
        viewbox.addItem(self.roi)
        self.roi.setZValue(10)   # make sure the ROI is drawn above the image
        # signal emitted when user stops dragging ROI
        self.roi.sigRegionChangeFinished.connect(self.user_roi) 
        # make a histogram to control the intensity scaling
        self.im_hist = pg.HistogramLUTItem()
        self.im_hist.setImageItem(self.im_canvas)
        im_widget.addItem(self.im_hist)
        # self.im_canvas.show()


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
            self.plot_labels[i].addItems(list(self.histo_handler.stats_dict.keys())) 
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
        self.setGeometry(100, 100, 850, 700)
        self.setWindowTitle('Single Atom Image Analyser')
        self.setWindowIcon(QIcon('docs/tempicon.png'))
        
    #### #### user input functions #### #### 

    def set_user_var(self, text=''):
        """When the user finishes editing the var_edit line edit, update the displayed 
        user variable and assign it in the temp_vals of the histo_handler"""
        self.histo_handler.temp_vals['User variable'] = self.var_edit.text()
        self.stat_labels['User variable'].setText(self.var_edit.text())

    def user_roi(self, pos):
        """The user drags an ROI and this updates the ROI centre and width"""
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
            
    def pic_size_text_edit(self, text):
        """Update the specified size of an image in pixels when the user 
        edits the text in the line edit widget"""
        if text: # can't convert '' to int
            self.image_handler.pic_size = int(text)
            self.pic_size_label.setText(str(self.image_handler.pic_size))

    def CCD_stat_edit(self):
        """Update the values used for the EMCCD bias offset and readout noise"""
        if self.bias_offset_edit.text(): # check the label isn't empty
            self.bias = float(self.bias_offset_edit.text())
        if self.read_noise_edit.text():
            self.Nr = float(self.read_noise_edit.text())

    def add_var_to_multirun(self):
        """When the user hits enter or the 'Add to list' button, add the 
        text from the entry edit to the list of user variables that will 
        be used for the multi-run. For speed, you can enter a range in 
        the form start,stop,step,repeat. If the multi-run has already
        started, do nothing."""
        if not self.multirun_switch.isChecked():
            new_var = list(map(float, [v for v in self.entry_edit.text().split(',') if v]))
            if np.size(new_var) == 1: # just entered a single variable
                self.mr['var list'].append(new_var[0])
                # empty the text edit so that it's quicker to enter a new variable
                self.entry_edit.setText('') 

            elif np.size(new_var) == 3: # range, with no repeats
                self.mr['var list'] += list(np.arange(new_var[0], new_var[1], new_var[2]))
            elif np.size(new_var) == 4: # range, with repeats
                self.mr['var list'] += list(np.arange(new_var[0], new_var[1],
                                            new_var[2]))*int(new_var[3])
            # display the whole list
            self.multirun_vars.setText(','.join(list(map(str, self.mr['var list']))))

    def clear_multirun_vars(self):
        """Reset the list of user variables to be used in the multi-run.
        If the multi-run is already running, don't do anything"""
        if not self.multirun_switch.isChecked():
            self.mr['var list'] = []
            self.multirun_vars.setText('')

    def choose_multirun_dir(self):
        """Allow the user to choose the directory where the histogram .csv
        files and the measure .dat file will be saved as part of the multi-run"""
        default_path = self.get_default_path()
        try:
            dir_path = QFileDialog.getExistingDirectory(self, "Select Directory", default_path)
            self.multirun_save_dir.setText(dir_path)
        except OSError:
            pass # user cancelled - file not found
        
    def roi_text_edit(self, text):
        """Update the ROI position and size every time a text edit is made by
        the user to one of the line edit widgets"""
        xc, yc, l = [self.roi_x_edit.text(),
                            self.roi_y_edit.text(), self.roi_l_edit.text()]
        if any([v == '' for v in [xc, yc, l]]):
            xc, yc, l = 0, 0, 1 # default takes the top left pixel
        else:
            xc, yc, l = list(map(int, [xc, yc, l])) # crashes if the user inputs float
        
        if (xc - l//2 < 0 or yc - l//2 < 0 
            or xc + l//2 > self.image_handler.pic_size 
            or yc + l//2 > self.image_handler.pic_size):
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
        
    def bins_text_edit(self, text):
        """Update the histogram bins every time a text edit is made by the user
        to one of the line edit widgets.
        Don't update the histogram binning if the multirun is going because it
        can affect the statistics."""
        # bin_actions = [Auto, Manual, No Display, No Update]
        if self.bin_actions[1].isChecked() and not self.multirun_switch.isChecked(): 
            new_vals = [
                self.min_counts_edit.text(), self.max_counts_edit.text(), self.num_bins_edit.text()]          
            # if the line edit widget is empty, take an estimate from histogram values
            if new_vals[0] == '' and self.image_handler.im_num > 0: # min
                new_vals[0] = min(self.image_handler.counts[:self.image_handler.im_num])
            if new_vals[1] == '' and self.image_handler.im_num > 0: # max
                new_vals[1] = max(self.image_handler.counts[:self.image_handler.im_num])
            elif not any([v == '' for v in new_vals[:2]]) and int(new_vals[1]) < int(new_vals[0]):
                # can't have max < min
                new_vals[1] = max(self.image_handler.counts[:self.image_handler.im_num])
            if new_vals[2] == '' and self.image_handler.im_num > 0: # num bins
                # min 17 bins. Increase with # images and with separation
                new_vals[2] = int(17 + 5e-5 * self.image_handler.im_num**2 + 
                    ((float(new_vals[1]) - float(new_vals[0]))/float(new_vals[1]))**2 * 15)
            if any([v == '' for v in new_vals]) and self.image_handler.im_num == 0:
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
                self.plot_current_hist(self.image_handler.histogram) # doesn't update thresh
            else:
                self.plot_current_hist(self.image_handler.hist_and_thresh) # updates thresh
            
    
    #### #### toggle functions #### #### 

    def dappend(self, key, value):
        """Shorthand for appending a new value to the array in the histo_handler
        dictionary with the given key. Also update the temp values so that they
        are always the most recent value. Then update the label in the statistics
        tab to display the new value."""
        self.histo_handler.stats_dict[key] = np.append(
                self.histo_handler.stats_dict[key], 
                np.array(value).astype(self.histo_handler.stats_dict[key].dtype))
        self.histo_handler.temp_vals[key] = value
        self.stat_labels[key].setText(str(value))

    def update_stats(self, toggle=True):
        """Update the statistics from the current histogram in order to save them
        image_handler uses a peak finding algorithm to get the peak positions and widths
        from these a threshold can be set. If the user thresh_toggle is checked then the
        threshold will not be updated.
        The histo_handler stores temporary values that we might not yet want to add to
        the plot."""
        if self.image_handler.im_num > 0: # only update if a histogram exists
            if self.thresh_toggle.isChecked(): # using manual threshold
                self.plot_current_hist(self.image_handler.histogram) # update hist and peak stats, keep thresh
            else:
                self.plot_current_hist(self.image_handler.hist_and_thresh) # update hist and get peak stats
            above_idxs = np.where(self.image_handler.atom > 0)[0] # index of images with counts above threshold
            atom_count = np.size(above_idxs)  # number of images with counts above threshold
            above = self.image_handler.counts[above_idxs] # counts above threshold
            below_idxs = np.where(self.image_handler.atom[:self.image_handler.im_num] == 0)[0] # index of images with counts below threshold
            empty_count = np.size(below_idxs) # number of images with counts below threshold
            below = self.image_handler.counts[below_idxs] # counts below threshold
            # use the binomial distribution to get 1 sigma confidence intervals:
            conf = binom_conf_interval(atom_count, atom_count + empty_count, interval='jeffreys')
            loading_prob = atom_count/self.image_handler.im_num # fraction of images above threshold
            uplperr = conf[1] - loading_prob # 1 sigma confidence above mean
            lolperr = loading_prob - conf[0] # 1 sigma confidence below mean
            # store the calculated histogram statistics as temp, don't add to plot
            self.histo_handler.temp_vals['Hist ID'] = int(self.hist_num)
            file_list = [x for x in self.image_handler.files if x]
            self.histo_handler.temp_vals['Start file #'] = min(map(int, file_list))
            self.histo_handler.temp_vals['End file #'] = max(map(int, file_list))
            self.histo_handler.temp_vals['ROI xc ; yc ; size'] = ' ; '.join([self.roi_x_edit.text(), 
                                                self.roi_y_edit.text(), self.roi_l_edit.text()])
            self.histo_handler.temp_vals['User variable'] = float(self.var_edit.text())
            self.histo_handler.temp_vals['Number of images processed'] = self.image_handler.im_num
            self.histo_handler.temp_vals['Counts above : below threshold'] = str(atom_count) + ' : ' + str(empty_count)
            self.histo_handler.temp_vals['Loading probability'] = np.around(loading_prob, 4)
            self.histo_handler.temp_vals['Error in Loading probability'] = np.around((uplperr+lolperr)*0.5, 4)
            self.histo_handler.temp_vals['Lower Error in Loading probability'] = np.around(lolperr, 4)
            self.histo_handler.temp_vals['Upper Error in Loading probability'] = np.around(uplperr, 4)
            if np.size(self.image_handler.peak_counts) == 2:
                self.histo_handler.temp_vals['Background peak count'] = int(self.image_handler.peak_counts[0])
                # assume bias offset is self.bias, readout noise standard deviation Nr
                if self.Nr**2+self.image_handler.peak_counts[0]-self.bias > 0:
                    self.histo_handler.temp_vals['sqrt(Nr^2 + Nbg)'] = int((self.Nr**2+self.image_handler.peak_counts[0]-self.bias)**0.5)
                else: # don't take the sqrt of a -ve number
                    self.histo_handler.temp_vals['sqrt(Nr^2 + Nbg)'] = 0
                bgw = self.image_handler.peak_widths[0] # fitted background peak width
                self.histo_handler.temp_vals['Background peak width'] = int(bgw)
                self.histo_handler.temp_vals['Error in Background peak count'] = np.around(self.image_handler.peak_widths[0] / empty_count**0.5, 2)
                self.histo_handler.temp_vals['Background mean'] = np.around(np.mean(below), 1)
                self.histo_handler.temp_vals['Background standard deviation'] = np.around(np.std(below, ddof=1), 1)
                self.histo_handler.temp_vals['Signal peak count'] = int(self.image_handler.peak_counts[1])
                # assume bias offset is self.bias, readout noise standard deviation Nr
                if self.Nr**2+self.image_handler.peak_counts[1]-self.bias > 0:
                    self.histo_handler.temp_vals['sqrt(Nr^2 + Ns)'] = int((self.Nr**2+self.image_handler.peak_counts[1]-self.bias)**0.5)
                else: # don't take the sqrt of a -ve number
                    self.histo_handler.temp_vals['sqrt(Nr^2 + Ns)'] = 0
                siw = self.image_handler.peak_widths[1] # fitted signal peak width
                self.histo_handler.temp_vals['Signal peak width'] = int(siw)
                self.histo_handler.temp_vals['Error in Signal peak count'] = np.around(self.image_handler.peak_widths[1] / atom_count**0.5, 2)
                self.histo_handler.temp_vals['Signal mean'] = np.around(np.mean(above), 1)
                self.histo_handler.temp_vals['Signal standard deviation'] = np.around(np.std(above, ddof=1), 1)
                sep = self.image_handler.peak_counts[1] - self.image_handler.peak_counts[0] # separation of fitted peaks
                self.histo_handler.temp_vals['Separation'] = int(sep)
                seperr = np.sqrt(self.image_handler.peak_widths[0]**2 / empty_count
                                + self.image_handler.peak_widths[1]**2 / atom_count) # propagated error in separation
                self.histo_handler.temp_vals['Error in Separation'] = np.around(seperr, 2)
                self.histo_handler.temp_vals['Fidelity'] = self.image_handler.fidelity
                self.histo_handler.temp_vals['Error in Fidelity'] = self.image_handler.err_fidelity
                self.histo_handler.temp_vals['S/N'] = np.around(sep / np.sqrt(bgw**2 + siw**2), 2)
                # fractional error in the error is 1/sqrt(2N - 2)
                self.histo_handler.temp_vals['Error in S/N'] = np.around(
                    self.histo_handler.temp_vals['S/N'] * np.sqrt((seperr/sep)**2 + 
                    (bgw**2/(2*empty_count - 2) + siw**2/(2*atom_count - 2))/(bgw**2 + siw**2)), 2)
            else:
                for key in ['Background peak count', 'sqrt(Nr^2 + Nbg)', 'Background peak width', 
                'Error in Background peak count', 'Signal peak count', 'sqrt(Nr^2 + Ns)', 
                'Signal peak width', 'Error in Signal peak count', 'Separation', 'Error in Separation', 
                'Fidelity', 'Error in Fidelity', 'S/N', 'Error in S/N']:
                    self.histo_handler.temp_vals[key] = 0
            self.histo_handler.temp_vals['Threshold'] = int(self.image_handler.thresh)
            # display the new statistics in the labels
            for key, val in self.histo_handler.temp_vals.items():
                self.stat_labels[key].setText(str(val))

    def fit_gaussians(self, store_stats=False):
        """Update the histogram and fit two Gaussians, splitting the data at the threshold
        then use the fits to calculate histogram statistics, and set the threshold where the 
        fidelity is maximum. If the store_stats Boolean is True, append the calculated values
        to the histo_handler's statistics dictionary."""
        bins, occ, thresh = self.image_handler.histogram()  # get histogram
        bin_mid = (bins[1] - bins[0]) * 0.5 # from edge of bin to middle
        diff = abs(bins - thresh)   # minimum is at the threshold
        thresh_i = np.argmin(diff)  # index of the threshold
        # split the histogram at the threshold value
        best_fits = [fc.fit(bins[:thresh_i]+bin_mid, occ[:thresh_i]),
                        fc.fit(bins[thresh_i:-1]+bin_mid, occ[thresh_i:])]
        for bf in best_fits:
            try:
                bf.estGaussParam()         # get estimate of parameters
                # parameters are: amplitude, centre, standard deviation
                bf.getBestFit(bf.gauss)    # get best fit parameters
            except: return 0               # fit failed, do nothing
        # update image handler's values for peak parameters
        self.image_handler.peak_heights = np.array((best_fits[0].ps[0], best_fits[1].ps[0]))
        self.image_handler.peak_counts = np.array((best_fits[0].ps[1], best_fits[1].ps[1]))
        self.image_handler.peak_widths = np.array((best_fits[0].ps[2], best_fits[1].ps[2]))
        # update threshold to where fidelity is maximum
        if not self.thresh_toggle.isChecked(): # update thresh if not set by user
            self.image_handler.search_fidelity(best_fits[0].ps[1], best_fits[0].ps[2], 
                                                            best_fits[1].ps[1], n=100)
        else:
            self.image_handler.fidelity, self.image_handler.err_fidelity = np.around(
                            self.image_handler.get_fidelity(), 4) # round to 4 d.p.

        self.plot_current_hist(self.image_handler.histogram) # clear then update histogram plot
        for bf in best_fits:
            xs = np.linspace(min(bf.x), max(bf.x), 100) # interpolate
            self.hist_canvas.plot(xs, bf.gauss(xs, *bf.ps), pen='b') # plot best fit
        # update atom statistics
        self.image_handler.atom[:self.image_handler.im_num] = self.image_handler.counts[
            :self.image_handler.im_num] // self.image_handler.thresh   # update atom presence
        above_idxs = np.where(self.image_handler.atom > 0)[0] # index of images with counts above threshold
        atom_count = np.size(above_idxs)  # number of images with counts above threshold
        above = self.image_handler.counts[above_idxs] # counts above threshold
        below_idxs = np.where(self.image_handler.atom[:self.image_handler.im_num] == 0)[0] # index of images with counts below threshold
        empty_count = np.size(below_idxs) # number of images with counts below threshold
        below = self.image_handler.counts[below_idxs] # counts below threshold
        loading_prob = atom_count/self.image_handler.im_num # loading probability
        # use the binomial distribution to get 1 sigma confidence intervals:
        conf = binom_conf_interval(atom_count, atom_count + empty_count, interval='jeffreys') 
        uplperr = conf[1] - loading_prob # 1 sigma confidence above mean
        lolperr = loading_prob - conf[0] # 1 sigma confidence below mean
        # store the calculated histogram statistics as temp, don't add to plot
        if store_stats:
            self.histo_handler.temp_vals['Hist ID'] = int(self.hist_num)
            self.histo_handler.temp_vals['User variable'] = float(self.var_edit.text())
            file_list = [x for x in self.image_handler.files if x]
            self.histo_handler.temp_vals['Start file #'] = min(map(int, file_list))
            self.histo_handler.temp_vals['End file #'] = max(map(int, file_list))
            self.histo_handler.temp_vals['ROI xc ; yc ; size'] = ' ; '.join(
                                    [self.roi_x_edit.text(), self.roi_y_edit.text(), self.roi_l_edit.text()])
            self.histo_handler.temp_vals['Number of images processed'] = self.image_handler.im_num
            self.histo_handler.temp_vals['Counts above : below threshold'] = str(atom_count) + ' : ' + str(empty_count)
            self.histo_handler.temp_vals['Loading probability'] = np.around(loading_prob, 4)
            self.histo_handler.temp_vals['Error in Loading probability'] = np.around((uplperr + lolperr)*0.5, 4)
            self.histo_handler.temp_vals['Lower Error in Loading probability'] = np.around(lolperr, 4)
            self.histo_handler.temp_vals['Upper Error in Loading probability'] = np.around(uplperr, 4)
            self.histo_handler.temp_vals['Background peak count'] = int(best_fits[0].ps[1])
            # assume bias offset is self.bias, readout noise standard deviation Nr
            if self.Nr**2+best_fits[0].ps[1]-self.bias > 0:
                self.histo_handler.temp_vals['sqrt(Nr^2 + Nbg)'] = int((self.Nr**2+best_fits[0].ps[1]-self.bias)**0.5)
            else: # don't take the sqrt of a -ve number
                self.histo_handler.temp_vals['sqrt(Nr^2 + Nbg)'] = 0
            bgw = best_fits[0].ps[2] # fitted background peak width
            self.histo_handler.temp_vals['Background peak width'] = int(bgw)
            self.histo_handler.temp_vals['Error in Background peak count'] = np.around(best_fits[0].ps[2] / empty_count**0.5, 2)
            self.histo_handler.temp_vals['Background mean'] = np.around(np.mean(below), 1)
            self.histo_handler.temp_vals['Background standard deviation'] = np.around(np.std(below, ddof=1), 1)
            self.histo_handler.temp_vals['Signal peak count'] = int(best_fits[1].ps[1])
            # assume bias offset is self.bias, readout noise standard deviation Nr
            if self.Nr**2+best_fits[1].ps[1]-self.bias > 0:
                self.histo_handler.temp_vals['sqrt(Nr^2 + Ns)'] = int((self.Nr**2+best_fits[1].ps[1]-self.bias)**0.5)
            else:
                self.histo_handler.temp_vals['sqrt(Nr^2 + Ns)'] = 0
            siw = best_fits[1].ps[2] # fitted signal peak width
            self.histo_handler.temp_vals['Signal peak width'] = int(siw)
            self.histo_handler.temp_vals['Error in Signal peak count'] = np.around(best_fits[1].ps[2] / atom_count**0.5, 2)
            self.histo_handler.temp_vals['Signal mean'] = np.around(np.mean(above), 1)
            self.histo_handler.temp_vals['Signal standard deviation'] = np.around(np.std(above, ddof=1), 1)
            sep = best_fits[1].ps[1] - best_fits[0].ps[1] # separation of fitted peak centres
            self.histo_handler.temp_vals['Separation'] = int(sep)
            seperr = np.sqrt(best_fits[0].ps[2]**2 / empty_count + best_fits[1].ps[2]**2 / atom_count) # error in separation
            self.histo_handler.temp_vals['Error in Separation'] = np.around(seperr, 2)
            self.histo_handler.temp_vals['Fidelity'] = self.image_handler.fidelity
            self.histo_handler.temp_vals['Error in Fidelity'] = self.image_handler.err_fidelity
            self.histo_handler.temp_vals['S/N'] = np.around(sep / np.sqrt(bgw**2 + siw**2), 2)
            # fractional error in the error is 1/sqrt(2N - 2)
            self.histo_handler.temp_vals['Error in S/N'] = np.around(
                        self.histo_handler.temp_vals['S/N'] * np.sqrt((seperr/sep)**2 + 
                        (bgw**2/(2*empty_count - 2) + siw**2/(2*atom_count - 2))/(bgw**2 + siw**2)), 2)
            self.histo_handler.temp_vals['Threshold'] = int(self.image_handler.thresh)
            # display the new statistics in the labels
            for key, val in self.histo_handler.temp_vals.items():
                self.stat_labels[key].setText(str(val))
        return 1 # fit successful

    def update_fit(self, toggle=True):
        """Fit Gaussians to the peaks and use it to get a better estimate of the 
        peak centres and widths. The peaks are not quite Poissonian because of the
        bias from dark counts. Use the fits to get histogram statistics, then set 
        the threshold to maximise fidelity. Iterate until the threshold converges."""
        success = 0
        if self.image_handler.im_num > 0: # only update if a histogram exists
            oldthresh = self.image_handler.thresh # store the last value
            diff = 1                              # convergence criterion
            for i in range(20):          # shouldn't need many iterations
                if diff < 0.0015:
                    break
                success = self.fit_gaussians()
                diff = abs(oldthresh - self.image_handler.thresh) / float(oldthresh)
            if success: # fit_gaussians returns 0 if it fails
                self.fit_gaussians(store_stats=True) # add new stats to histo_handler
        return success  
            
    def fit_bg_gaussian(self, store_stats=False):
        """Assume that there is only one peak in the histogram as there is no single
        atom signal. Fit a Gaussian to this peak."""
        n = self.image_handler.im_num # number of images processed
        c = self.image_handler.counts[:n] # integrated counts
        bins, occ, _ = self.image_handler.histogram()  # get histogram
        bin_mid = (bins[1] - bins[0]) * 0.5 # from edge of bin to middle
        # make a Gaussian fit to the peak
        best_fit = fc.fit(bins[:-1]+bin_mid, occ)
        try:
            best_fit.estGaussParam()
            # parameters are: amplitude, centre, standard deviation
            best_fit.getBestFit(best_fit.gauss)    # get best fit parameters
        except: return 0               # fit failed, do nothing
        # calculate mean and std dev from the data
        mu, sig = np.mean(c), np.std(c, ddof=1)
        # best_fit.ps = [best_fit.ps[0], mu, sig] # use the peak from the fit
        lperr = np.around(binom_conf_interval(0, n, interval='jeffreys')[1], 4) # upper 1 sigma confidence
        # update image handler's values for peak parameters
        self.image_handler.peak_heights = np.array((best_fit.ps[0], 0))
        self.image_handler.peak_counts = np.array((best_fit.ps[1], 0))
        self.image_handler.peak_widths = np.array((best_fit.ps[2], 0))
        self.plot_current_hist(self.image_handler.histogram) # clear then update histogram plot
        xs = np.linspace(min(best_fit.x), max(best_fit.x), 100) # interpolate
        self.hist_canvas.plot(xs, best_fit.gauss(xs, *best_fit.ps), pen='b') # plot best fit
        # store the calculated histogram statistics as temp, don't add to plot
        self.histo_handler.temp_vals['Hist ID'] = int(self.hist_num)
        file_list = [x for x in self.image_handler.files if x]
        self.histo_handler.temp_vals['Start file #'] = min(map(int, file_list))
        self.histo_handler.temp_vals['End file #'] = max(map(int, file_list))
        self.histo_handler.temp_vals['ROI xc ; yc ; size'] = ' ; '.join(
                        [self.roi_x_edit.text(), self.roi_y_edit.text(), self.roi_l_edit.text()])
        self.histo_handler.temp_vals['User variable'] = float(self.var_edit.text())
        self.histo_handler.temp_vals['Number of images processed'] = n
        self.histo_handler.temp_vals['Counts above : below threshold'] = '0 : ' + str(n)
        self.histo_handler.temp_vals['Loading probability'] = 0
        self.histo_handler.temp_vals['Error in Loading probability'] = lperr
        self.histo_handler.temp_vals['Lower Error in Loading probability'] = 0
        self.histo_handler.temp_vals['Upper Error in Loading probability'] = lperr
        self.histo_handler.temp_vals['Background peak count'] = int(best_fit.ps[1])
        # assume bias offset is self.bias, readout noise standard deviation Nr
        if self.Nr**2+mu-self.bias:
            self.histo_handler.temp_vals['sqrt(Nr^2 + Nbg)'] = int((self.Nr**2+mu-self.bias)**0.5)
        else: # don't take the sqrt of a -ve number
            self.histo_handler.temp_vals['sqrt(Nr^2 + Nbg)'] = 0
        self.histo_handler.temp_vals['Background peak width'] = int(best_fit.ps[2])
        self.histo_handler.temp_vals['Error in Background peak count'] = np.around(best_fit.ps[2] / n**0.5, 4)
        self.histo_handler.temp_vals['Background mean'] = np.around(mu, 1)
        self.histo_handler.temp_vals['Background standard deviation'] = np.around(sig, 1)
        self.histo_handler.temp_vals['Signal peak count'] = 0
        self.histo_handler.temp_vals['sqrt(Nr^2 + Ns)'] = 0
        self.histo_handler.temp_vals['Signal peak width'] = 0
        self.histo_handler.temp_vals['Error in Signal peak count'] = 0
        self.histo_handler.temp_vals['Signal mean'] = 0
        self.histo_handler.temp_vals['Signal standard deviation'] = 0
        self.histo_handler.temp_vals['Separation'] = 0
        self.histo_handler.temp_vals['Error in Separation'] = 0
        self.histo_handler.temp_vals['Fidelity'] = 0
        self.histo_handler.temp_vals['Error in Fidelity'] = 0
        self.histo_handler.temp_vals['S/N'] = 0
        self.histo_handler.temp_vals['Error in S/N'] = 0
        self.histo_handler.temp_vals['Threshold'] = int(self.image_handler.thresh)
        # display the new statistics in the labels
        for key, val in self.histo_handler.temp_vals.items():
            self.stat_labels[key].setText(str(val))
            
    
    def update_varplot_axes(self, label=''):
        """The user selects which variable they want to display on the plot
        The variables are read from the x and y axis QComboBoxes
        Then the plot is updated"""
        if np.size(self.histo_handler.stats_dict['Hist ID']) > 0:
            self.histo_handler.xvals = self.histo_handler.stats_dict[
                                str(self.plot_labels[0].currentText())] # set x values
            
            y_label = str(self.plot_labels[1].currentText())
            self.histo_handler.yvals = self.histo_handler.stats_dict[y_label] # set y values
            
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
                        height=self.histo_handler.stats_dict['Error in '+y_label],
                        beam=beam_width) # plot with error bars
                    self.varplot_canvas.addItem(err_bars)
            except Exception: pass # probably wrong length of arrays

    def clear_varplot(self):
        """Clear the plot of histogram statistics by resetting the histo_handler.
        The data is not lost since it has been appended to the log file."""
        self.histo_handler.__init__ () # empty the stored arrays
        self.varplot_canvas.clear()    # clear the displayed plot
        self.hist_num = 0

    def set_thresh(self, toggle):
        """If the toggle is true, the user supplies the threshold value and it is
        kept constant using the image_handler.histogram() function. Otherwise,
        update the threshold with image_handler.hist_and_thresh()"""
        if toggle and not self.multirun_switch.isChecked(): # don't interrupt multirun
            try: # disconnect all slots because it might be connected several times
                self.event_im.disconnect()
            except Exception: pass # if already disconnected
            self.event_im.connect(self.update_plot_only)
            self.bins_text_edit('reset') # update histogram
        elif not toggle and not self.multirun_switch.isChecked():
            try: # disconnect all slots (including imshow...)
                self.event_im.disconnect()
            except Exception: pass # if already disconnected
            self.event_im.connect(self.update_plot)
        
    def set_im_show(self, toggle):
        """If the toggle is True, always update the widget with the last image.
        Note that disconnecting all slots means that this toggle might have to
        be reset when other buttons are pressed."""
        if toggle:
            self.event_im.connect(self.update_im)
        else:
            try: # note: it could have been connected several times
                self.event_im.disconnect(self.update_im)
            except Exception: pass # if it's already been disconnected 

    def multirun_go(self, toggle):
        """Initiate the multi-run: omit N files, save a histogram of M files, and
        repeat for the user variables in the list. If the button is pressed during
        the multi-run, save the current histogram, save the measure file, then
        return to normal operation of the dir_watcher"""
        if toggle and np.size(self.mr['var list']) > 0:
            self.check_reset()
            self.plot_current_hist(self.image_handler.histogram)
            try: # disconnect all slots
                self.event_im.disconnect() 
            except Exception: pass # already disconnected
            if self.multirun_save_dir.text() == '':
                self.choose_multirun_dir()
            self.event_im.connect(self.multirun_step)
            self.mr['# omit'] = int(self.omit_edit.text()) # number of files to omit
            self.mr['# hist'] = int(self.multirun_hist_size.text()) # number of files in histogram                
            self.mr['o'], self.mr['h'], self.mr['v'] = 0, 0, 0 # counters for different stages of multirun
            self.mr['prefix'] = self.measure_edit.text() # prefix for histogram files 
            self.multirun_switch.setText('Abort')
            self.clear_varplot() # varplot cleared so it only has multirun data
            self.multirun_progress.setText(       # update progress label
                'User variable: %s, omit %s of %s files, %s of %s histogram files, 0%% complete'%(
                    self.mr['var list'][self.mr['v']], self.mr['o'], self.mr['# omit'],
                    self.mr['h'], self.mr['# hist']))
        else: # cancel the multi-run
            self.set_bins() # reconnect the dir_watcher
            self.multirun_switch.setText('Start') # reset button text
            self.multirun_progress.setText(       # update progress label
                'Stopped at - User variable: %s, omit %s of %s files, %s of %s histogram files, %.3g%% complete'%(
                    self.mr['var list'][self.mr['v']], self.mr['o'], self.mr['# omit'],
                    self.mr['h'], self.mr['# hist'], 100 * ((self.mr['# omit'] + self.mr['# hist']) * 
                    self.mr['v'] + self.mr['o'] + self.mr['h']) / (self.mr['# omit'] + self.mr['# hist']) / 
                    np.size(self.mr['var list'])))

    def multirun_resume(self):
        """If the button is clicked, resume the multi-run where it was left off.
        If the multirun is already running, do nothing."""
        if not self.multirun_switch.isChecked(): 
            self.multirun_switch.setChecked(True)
            self.multirun_switch.setText('Abort')
            try: # disconnect all slots
                self.event_im.disconnect() 
            except Exception: pass # already disconnected
            self.event_im.connect(self.multirun_step)

    def swap_signals(self):
        """Disconnect the image_handler process signal from the dir_watcher event
        and (re)connect the update plot"""
        try: # disconnect all slots
            self.event_im.disconnect() 
        except Exception: pass
        if self.thresh_toggle.isChecked():
            self.event_im.connect(self.update_plot_only)
        elif not self.thresh_toggle.isChecked():
            self.event_im.connect(self.update_plot)
    
    def set_bins(self, action=None):
        """Check which of the bin action menu bar options is checked.
        If the toggle is Automatic, use automatic histogram binning.
        If the toggle is Manual, read in values from the line edit 
        widgets.
        If the toggle is No Display, processes files but doesn't show on histogram
        If the toggle is No Update, files are not processed for the histogram."""
        if not self.multirun_switch.isChecked(): # don't interrupt multirun
            if self.bin_actions[1].isChecked(): # manual
                self.swap_signals()  # disconnect image handler, reconnect plot
                self.bins_text_edit('reset')            
            elif self.bin_actions[0].isChecked(): # automatic
                self.swap_signals()  # disconnect image handler, reconnect plot
                self.image_handler.bin_array = []
                if self.thresh_toggle.isChecked():
                    self.plot_current_hist(self.image_handler.histogram)
                else:
                    self.plot_current_hist(self.image_handler.hist_and_thresh)
            elif self.bin_actions[2].isChecked() or self.bin_actions[3].isChecked(): # No Display or No Update
                try: # disconnect all slots
                    self.event_im.disconnect()
                except Exception: pass # if it's already been disconnected 

                # set the text of the most recent file
                # self.event_im.connect(self.recent_label.setText) # might need a better label
                # just process the image
                if self.bin_actions[2].isChecked():
                    self.event_im.connect(self.image_handler.process)
                
            
    #### #### canvas functions #### #### 
        
    def plot_current_hist(self, hist_function):
        """Reset the plot to show the current data stored in the image handler.
        hist_function is used to make the histogram and allows the toggling of
        different functions that may or may not update the threshold value."""
        # update the histogram and threshold estimate
        bins, occ, thresh = hist_function()
        self.hist_canvas.clear()
        self.hist_canvas.plot(bins, occ, stepMode=True, pen='k',
                                fillLevel=0, brush = (220,220,220,220)) # histogram
        self.hist_canvas.plot([thresh]*2, [0, max(occ)], pen='r') # threshold line
    
    def update_im(self, event_im):
        """Receive the image array emitted from the event signal
        display the image in the image canvas."""
        self.im_canvas.setImage(event_im)
        self.im_hist.setLevels(np.min(event_im), np.max(event_im))
        
    def update_plot(self, event_im):
        """Receive the event path emitted from the system event handler signal
        process the file in the event path with the image handler and update
        the figure"""
        # add the count
        t1 = time.time()
        self.image_handler.process(event_im)
        t2 = time.time()
        self.int_time = t2 - t1
        # display the name of the most recent file
        self.recent_label.setText('Just processed image '
            + self.image_handler.files[self.image_handler.im_num])
        self.plot_current_hist(self.image_handler.hist_and_thresh) # update the displayed plot
        self.plot_time = time.time() - t2

    def update_plot_only(self, event_im):
        """Receive the event path emitted from the system event handler signal
        process the file in the event path with the image handler and update
        the figure but without changing the threshold value"""
        # add the count
        t1 = time.time()
        self.image_handler.process(event_im)
        t2 = time.time()
        self.int_time = t2 - t1
        # display the name of the most recent file
        self.recent_label.setText('Just processed image '
            + self.image_handler.files[self.image_handler.im_num])
        self.plot_current_hist(self.image_handler.histogram) # update the displayed plot
        self.plot_time = time.time() - t2

    def multirun_step(self, event_im):
        """Receive event paths emitted from the system event handler signal
        for the first '# omit' events, only save the files
        then for '# hist' events, add files to a histogram,
        save the histogram 
        repeat this for the user variables in the multi-run list,
        then return to normal operation as set by the histogram binning"""
        if self.mr['v'] < np.size(self.mr['var list']):
            if self.mr['o'] < self.mr['# omit']: # don't process, just copy
                self.recent_label.setText('Just omitted image '
                    + self.image_handler.files[self.image_handler.im_num])
                self.mr['o'] += 1 # increment counter
            elif self.mr['h'] < self.mr['# hist']: # add to histogram
                # add the count to the histogram
                t1 = time.time()
                self.image_handler.process(event_im)
                t2 = time.time()
                self.int_time = t2 - t1
                # display the name of the most recent file
                self.recent_label.setText('Just processed image '
                    + self.image_handler.files[self.image_handler.im_num])
                self.plot_current_hist(self.image_handler.hist_and_thresh) # update the displayed plot
                self.plot_time = time.time() - t2
                self.mr['h'] += 1 # increment counter

            if self.mr['o'] == self.mr['# omit'] and self.mr['h'] == self.mr['# hist']:
                self.mr['o'], self.mr['h'] = 0, 0 # reset counters
                self.var_edit.setText(str(self.mr['var list'][self.mr['v']])) # set user variable
                self.bins_text_edit(text='reset') # set histogram bins 
                success = self.update_fit()       # get best fit
                if not success:                   # if fit fails, use peak search
                    self.update_stats()
                    print(
                        '\nWarning: multi-run fit failed at ' +
                        self.mr['prefix'] + '_' + str(self.mr['v']) + '.csv')
                self.save_hist_data(
                    save_file_name=os.path.join(
                        self.multirun_save_dir.text(), self.mr['prefix']) 
                            + '_' + str(self.mr['v']) + '.csv', 
                    confirm=False)# save histogram
                self.image_handler.reset_arrays() # clear histogram
                self.mr['v'] += 1 # increment counter
            
        if self.mr['v'] == np.size(self.mr['var list']):
            self.save_varplot(
                save_file_name=os.path.join(
                    self.multirun_save_dir.text(), self.mr['prefix']) 
                        + '.dat', 
                confirm=False)# save measure file
            # reconnect previous signals to dir_watcher
            self.multirun_switch.setChecked(False) # reset multi-run button
            self.multirun_switch.setText('Start')  # reset multi-run button text
            self.set_bins() # reconnects dir_watcher with given histogram binning settings
            self.mr['o'], self.mr['h'], self.mr['v'] = 0, 0, 0 # reset counters
            self.mr['measure'] += 1 # completed a measure successfully
            self.mr['prefix'] = str(self.mr['measure']) # suggest new measure as file prefix
            self.measure_edit.setText(self.mr['prefix'])

        self.multirun_progress.setText( # update progress label
            'User variable: %s, omit %s of %s files, %s of %s histogram files, %.3g%% complete'%(
                self.mr['var list'][self.mr['v']], self.mr['o'], self.mr['# omit'],
                self.mr['h'], self.mr['# hist'], 100 * ((self.mr['# omit'] + self.mr['# hist']) * 
                self.mr['v'] + self.mr['o'] + self.mr['h']) / (self.mr['# omit'] + self.mr['# hist']) / 
                np.size(self.mr['var list'])))


    def add_stats_to_plot(self, toggle=True):
        """Take the current histogram statistics from the Histogram Statistics labels
        and add the values to the variable plot, saving the parameters to the log
        file at the same time. If any of the labels are empty, replace them with 0."""
        # append current statistics to the histogram handler's list
        for key in self.stat_labels.keys():
            self.dappend(key, self.stat_labels[key].text() if self.stat_labels[key].text() else 0)
        self.update_varplot_axes()  # update the plot with the new values
        self.hist_num = np.size(self.histo_handler.stats_dict['Hist ID']) # index for histograms
        # append histogram stats to log file:
        with open(self.log_file_name, 'a') as f:
            f.write(','.join(list(map(str, self.histo_handler.temp_vals.values()))) + '\n')


    #### #### save and load data functions #### ####

    def get_default_path(self, default_path=''):
        """If the directory watcher is active, set its results path attribute as the
        default path when a file browser is opened.
        default_path: set the default path if the directory watcher isn't running"""
        return os.path.dirname(self.log_file_name)


    def load_im_size(self):
        """Get the user to select an image file and then use this to get the image size"""
        default_path = self.get_default_path()
        try:
            if 'PyQt4' in sys.modules:
                file_name = QFileDialog.getOpenFileName(
                    self, 'Select A File', default_path, 'Images (*.asc);;all (*)')
            elif 'PyQt5' in sys.modules:
                file_name, _ = QFileDialog.getOpenFileName(
                    self, 'Select A File', default_path, 'Images (*.asc);;all (*)')
            self.image_handler.set_pic_size(file_name) # sets image handler's pic size
            self.pic_size_edit.setText(str(self.image_handler.pic_size)) # update loaded value
            self.pic_size_label.setText(str(self.image_handler.pic_size)) # update loaded value
        except OSError:
            pass # user cancelled - file not found


    def load_roi(self):
        """Get the user to select an image file and then use this to get the ROI centre"""
        default_path = self.get_default_path()
        try:
            if 'PyQt4' in sys.modules:
                file_name = QFileDialog.getOpenFileName(
                    self, 'Select A File', default_path, 'Images (*.asc);;all (*)')
            elif 'PyQt5' in sys.modules:
                file_name, _ = QFileDialog.getOpenFileName(
                    self, 'Select A File', default_path, 'Images (*.asc);;all (*)')
            # get pic size from this image in case the user forgot to set it
            self.image_handler.set_pic_size(file_name) # sets image handler's pic size
            self.pic_size_edit.setText(str(self.image_handler.pic_size)) # update loaded value
            self.pic_size_label.setText(str(self.image_handler.pic_size)) # update loaded value
            # get the position of the max count
            self.image_handler.set_roi(im_name=file_name) # sets xc and yc
            self.roi_x_edit.setText(str(self.image_handler.xc)) # update loaded value
            self.roi_y_edit.setText(str(self.image_handler.yc)) 
            self.roi_l_edit.setText(str(self.image_handler.roi_size))
            self.xc_label.setText(str(self.image_handler.xc))
            self.yc_label.setText(str(self.image_handler.yc))
            self.l_label.setText(str(self.image_handler.roi_size))
            self.roi.setPos(self.image_handler.xc - self.image_handler.roi_size//2, 
            self.image_handler.yc - self.image_handler.roi_size//2) # set ROI in image display
            self.roi.setSize(self.image_handler.roi_size, self.image_handler.roi_size)
        except OSError:
            pass # user cancelled - file not found


    def save_hist_data(self, trigger=None, save_file_name='', confirm=True):
        """Prompt the user to give a directory to save the histogram data, then save"""
        default_path = self.get_default_path()
        try:
            if not save_file_name and 'PyQt4' in sys.modules:
                save_file_name = QFileDialog.getSaveFileName(
                    self, 'Save File', default_path, 'csv(*.csv);;all (*)')
            elif not save_file_name and 'PyQt5' in sys.modules:
                save_file_name, _ = QFileDialog.getSaveFileName(
                    self, 'Save File', default_path, 'csv(*.csv);;all (*)')
            # don't update the threshold  - trust the user to have already set it
            # if not self.thresh_toggle.isChecked(): # update the threshold unless it's set manually
            #     self.plot_current_hist(self.image_handler.hist_and_thresh)
            self.add_stats_to_plot()
            # include most recent histogram stats as the top two lines of the header
            self.image_handler.save_state(save_file_name,
                         hist_header=list(self.histo_handler.temp_vals.keys()),
                         hist_stats=list(self.histo_handler.temp_vals.values())) # save histogram
            try: 
                hist_num = self.histo_handler.stats_dict['Hist ID'][-1]
            except IndexError: # if there are no values in the stats_dict yet
                hist_num = -1
            if confirm:
                msg = QMessageBox()
                msg.setIcon(QMessageBox.Information)
                msg.setText("File saved to "+save_file_name+"\n"+
                        "and appended histogram %s to log file."%hist_num)
                msg.setStandardButtons(QMessageBox.Ok)
                msg.exec_()
        except OSError:
            pass # user cancelled - file not found

    def save_varplot(self, save_file_name='', confirm=True):
        """Save the data in the current plot, which is held in the histoHandler's
        dictionary and saved in the log file, to a new file."""
        default_path = self.get_default_path()
        try:
            if not save_file_name and 'PyQt4' in sys.modules:
                save_file_name = QFileDialog.getSaveFileName(
                    self, 'Save File', default_path, 'dat(*.dat);;all (*)')
            elif not save_file_name and 'PyQt5' in sys.modules:
                save_file_name, _ = QFileDialog.getSaveFileName(
                    self, 'Save File', default_path, 'dat(*.dat);;all (*)')
            with open(save_file_name, 'w+') as f:
                f.write('#Single Atom Image Analyser Log File: collects histogram data\n')
                f.write('#include --[]\n')
                f.write('#'+', '.join(self.histo_handler.stats_dict.keys())+'\n')
                for i in range(len(self.histo_handler.stats_dict['Hist ID'])):
                    f.write(','.join(list(map(str, [v[i] for v in 
                        self.histo_handler.stats_dict.values()])))+'\n')
            if confirm:
                msg = QMessageBox()
                msg.setIcon(QMessageBox.Information)
                msg.setText("Plot data saved to file "+save_file_name)
                msg.setStandardButtons(QMessageBox.Ok)
                msg.exec_()
        except OSError:
            pass # user cancelled - file not found
        
    def check_reset(self):
        """Ask the user if they would like to reset the current data stored"""
        reply = QMessageBox.question(self, 'Confirm Data Replacement',
            "Do you want to discard the current data?", 
            QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel, QMessageBox.Cancel)
        if reply == QMessageBox.Cancel:
            return 0
        elif reply == QMessageBox.Yes:
            self.image_handler.reset_arrays() # gets rid of old data
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

    def load_from_files(self, trigger=None):
        """Prompt the user to select image files to process, then sequentially process
        them and update the histogram"""
        default_path = self.get_default_path()
        if self.check_reset():
            try:
                self.recent_label.setText('Processing files...') # comes first otherwise not executed
                if 'PyQt4' in sys.modules:
                    file_list = QFileDialog.getOpenFileNames(
                        self, 'Select Files', default_path, 'Images(*.asc);;all (*)')
                elif 'PyQt5' in sys.modules:
                    file_list, _ = QFileDialog.getOpenFileNames(
                        self, 'Select Files', default_path, 'Images(*.asc);;all (*)')
                for file_name in file_list:
                    try:
                        im_vals = self.image_handler.process(file_name)
                        self.image_handler.process(im_vals)
                        self.recent_label.setText(
                            'Just processed: '+os.path.basename(file_name)) # only updates at end of loop
                    except:
                        print("\n WARNING: failed to load "+file_name) # probably file size was wrong
                self.update_stats()
                if self.recent_label.text == 'Processing files...':
                    self.recent_label.setText('Finished Processing')
            except OSError:
                pass # user cancelled - file not found

    # def load_from_file_nums(self, trigger=None):
    #     """Prompt the user to enter a range of image file numbers.
    #     Use these to select the image files from the current image storage path.
    #     Sequentially process the images then update the histogram"""
    #     default_range = ''
    #     if self.image_handler.im_num > 0: # defualt load all files in folder
    #         default_range = '0 - ' + str(self.image_handler.im_num)
    #     text, ok = QInputDialog.getText( # user inputs the range
    #         self, 'Choose file numbers to load from','Range of file numbers: ',
    #         text=default_range)
    #     if ok and text and self.dir_watcher: # if user cancels or empty text, do nothing
    #         for file_range in text.split(','):
    #             minmax = file_range.split('-')
    #             if np.size(minmax) == 1: # only entered one file number
    #                 file_list = [
    #                     os.path.join(self.dir_watcher.image_storage_path, self.dir_watcher.event_handler.species)
    #                     + '_' + self.dir_watcher.event_handler.date + '_' + minmax[0].replace(' ','') + '.asc']
    #             if np.size(minmax) == 2:
    #                 file_list = [
    #                     os.path.join(self.dir_watcher.image_storage_path, self.dir_watcher.event_handler.species)
    #                     + '_' + self.dir_watcher.event_handler.date + '_' + dfn + '.asc' for dfn in list(map(str, 
    #                         range(int(minmax[0]), int(minmax[1]))))] 
    #         for file_name in file_list:
    #             try:
    #                 im_vals = self.image_handler.load_full_im(file_name)
    #                 self.image_handler.process(im_vals)
    #                 self.recent_label.setText(
    #                     'Just processed: '+os.path.basename(file_name)) # only updates at end of loop
    #             except:
    #                 print("\n WARNING: failed to load "+file_name) # probably file size was wrong
    #         self.update_stats()
    #         if self.recent_label.text == 'Processing files...':
    #             self.recent_label.setText('Finished Processing')

    def load_from_csv(self, trigger=None):
        """Prompt the user to select a csv file to load histogram data from.
        It must have the specific layout that the image_handler saves in."""
        default_path = self.get_default_path() 
        if self.check_reset():
            try:
                # the implementation of QFileDialog changed...
                if 'PyQt4' in sys.modules: 
                    file_name = QFileDialog.getOpenFileName(
                        self, 'Select A File', default_path, 'csv(*.csv);;all (*)')
                elif 'PyQt5' in sys.modules:
                    file_name, _ = QFileDialog.getOpenFileName(
                        self, 'Select A File', default_path, 'csv(*.csv);;all (*)')
                self.image_handler.load_from_csv(file_name)
                self.update_stats()
            except OSError:
                pass # user cancelled - file not found

    def load_image(self, trigger=None):
        """Prompt the user to select an image file to display"""
        default_path = self.get_default_path()
        try:
            if 'PyQt4' in sys.modules:
                file_name = QFileDialog.getOpenFileName(
                    self, 'Select A File', default_path, 'Images (*.asc);;all (*)')
            elif 'PyQt5' in sys.modules:
                file_name, _ = QFileDialog.getOpenFileName(
                    self, 'Select A File', default_path, 'Images (*.asc);;all (*)')
            if file_name:  # avoid crash if the user cancelled
                self.update_im(file_name)
        except OSError:
            pass # user cancelled - file not found

    def load_from_log(self, trigger=None):
        """Prompt the user to select the log file then pass it to the histohandler"""
        default_path = self.get_default_path()
        try:
            # the implementation of QFileDialog changed...
            if 'PyQt4' in sys.modules: 
                file_name = QFileDialog.getOpenFileName(
                    self, 'Select A File', default_path, 'dat(*.dat);;all (*)')
            elif 'PyQt5' in sys.modules:
                file_name, _ = QFileDialog.getOpenFileName(
                    self, 'Select A File', default_path, 'dat(*.dat);;all (*)')
            success = self.histo_handler.load_from_log(file_name)
            if not success:
                print('Data was not loaded from the log file.')
            self.update_varplot_axes()
        except OSError:
            pass # user cancelled - file not found


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

    def closeEvent(self, event, confirm=True):
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
        if reply == QMessageBox.Yes:
            self.save_hist_data()         # save current state
            event.accept()
        elif reply == QMessageBox.No:
            event.accept()
        else:
            event.ignore()        

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