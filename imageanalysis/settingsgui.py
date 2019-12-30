"""Single Atom Image Analysis (SAIA) Settings
Stefan Spence 26/02/19

 - control the ROIs across all SAIA instances
 - update other image statistics like read noise, bias offset
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
            QTabWidget, QVBoxLayout, QRegExpValidator) 
except ImportError:
    from PyQt5.QtCore import pyqtSignal, QRegExp
    from PyQt5.QtGui import (QIcon, QDoubleValidator, QIntValidator, 
        QRegExpValidator, QFont)
    from PyQt5.QtWidgets import (QActionGroup, QVBoxLayout, QMenu, 
        QFileDialog, QMessageBox, QLineEdit, QGridLayout, QWidget,
        QApplication, QPushButton, QAction, QMainWindow, QTabWidget,
        QLabel)
import logging
logger = logging.getLogger(__name__)
from maingui import main_window, remove_slot # single atom image analysis
from reimage import reim_window # analysis for survival probability

####    ####    ####    ####

# main GUI window contains all the widgets                
class settings_window(QMainWindow):
    """Main GUI window managing settings for all instances of SAIA.

    Keyword arguments:
    nsaia         -- number of maingui.main_window instances to create
    nreim         -- number of reimage.reim_window instances to create
    results_path  -- the directory where result csv or dat files are saved.
    im_store_path -- the directory where images are saved. Default
    """
    m_changed = pyqtSignal(int) # gives the number of images per run

    def __init__(self, nsaia=1, nreim=0, results_path='.', im_store_path='.'):
        super().__init__()
        self.types = OrderedDict([('pic_size',int), ('xc',int), ('yc',int), ('roi_size',int), 
            ('bias',float), ('Nr', float), ('image_path', str), ('results_path', str)])
        self.stats = OrderedDict([('pic_size',1), ('xc',0), ('yc',0), ('roi_size',1), 
            ('bias',697), ('Nr', 8.8), ('image_path', im_store_path), ('results_path', results_path)])
        self.load_settings() # load default
        self.date = time.strftime("%d %b %B %Y", time.localtime()).split(" ") # day short_month long_month year
        self.results_path = results_path # used for saving results
        self.image_storage_path = im_store_path # used for loading image files
        self._m = nsaia # number of images per run 
        self._a = nsaia # number of SAIA instances
        self.mw = [main_window(results_path, im_store_path, str(i)) for i in range(nsaia)] # saia instances
        self.mw_inds = list(range(nsaia)) # the index, m, of the image in the sequence to use 
        self.rw = [] # re-image analysis instances
        self.rw_inds = [] # which saia instances are used for the re-image instances
        if np.size(self.mw) >= nreim*2:
            self.rw = [reim_window(self.mw[2*i].event_im, [self.mw[2*i].image_handler, self.mw[2*i+1].image_handler],
                results_path, im_store_path, 'RW'+str(i)) for i in range(nreim)]
            self.rw_inds = [str(2*i)+','+str(2*i+1) for i in range(nreim)]
        self.init_UI()  # make the widgets

    def reset_dates(self, date):
        """Reset the dates in all of the saia instances"""
        self.date = date
        for mw in self.mw + self.rw:
            mw.date = date
        
    def find(self, image_number):
        """Generate the indices there image number is found in the list
        of main_window Analyser image indices."""
        for i in range(len(self.mw_inds)):
            if self.mw_inds[i] == image_number:
                yield i

    def init_UI(self):
        """Create all of the widget objects required"""
        # validators for user input
        semico_validator = QRegExpValidator(QRegExp(r'((\d+,\d+);?)+')) # ints, semicolons and commas
        comma_validator = QRegExpValidator(QRegExp(r'([0-%s]+,?)+'%(self._m-1))) # ints and commas
        double_validator = QDoubleValidator() # floats
        int_validator = QIntValidator()       # integers

        #### menubar at top gives options ####
        menubar = self.menuBar()
        
        hist_menu =  menubar.addMenu('Histogram')
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
        bin_options.triggered.connect(self.set_all_windows) # connect the signal
        hist_menu.addMenu(bin_menu)
        
        fit_menu = QMenu('Fitting', self) # drop down menu for fitting options
        self.fit_options = QActionGroup(fit_menu)  # group together the options
        for action_label in ['separate gaussians', 'double poissonian', 
                            'single gaussian', 'double gaussian']:
            fit_method = QAction(action_label, fit_menu, checkable=True, 
                checked=action_label=='double gaussian') # set default
            fit_menu.addAction(fit_method)
            self.fit_options.addAction(fit_method)
        fit_method.setChecked(True) # set last method as checked: double gaussian
        self.fit_options.setExclusive(True) # only one option checked at a time
        self.fit_options.triggered.connect(self.set_all_windows)
        hist_menu.addMenu(fit_menu)

        # image menubar allows you to display images
        im_menu = menubar.addMenu('Image')
        load_im = QAction('Load Image', self) # display a loaded image
        load_im.triggered.connect(self.load_image)
        im_menu.addAction(load_im)
        
        make_im_menu = QMenu('Make Average Image', self) # display ave. image
        make_im = QAction('From Files', self) # from image files (using file browser)
        make_im.triggered.connect(self.make_ave_im)
        make_im_menu.addAction(make_im)
        # make_im_fn = QAction('From File Numbers', self) # from image file numbers
        # make_im_fn.triggered.connect(self.make_ave_im)
        # make_im_menu.addAction(make_im_fn)
        im_menu.addMenu(make_im_menu)

        # central widget creates container for tabs
        self.centre_widget = QWidget()
        self.tabs = QTabWidget()       # make tabs for each main display 
        self.centre_widget.layout = QVBoxLayout()
        self.centre_widget.layout.addWidget(self.tabs)
        self.centre_widget.setLayout(self.centre_widget.layout)
        self.setCentralWidget(self.centre_widget)
        
        #### tab for settings  ####
        settings_tab = QWidget()
        settings_grid = QGridLayout()
        settings_tab.setLayout(settings_grid)
        self.tabs.addTab(settings_tab, "Analysers")
        
        # choose the number of image per run 
        m_label = QLabel('Number of images per run: ', self)
        settings_grid.addWidget(m_label, 0,0, 1,1)
        self.m_edit = QLineEdit(self)
        settings_grid.addWidget(self.m_edit, 0,1, 1,1)
        self.m_edit.setText(str(self._m)) # default
        self.m_edit.editingFinished.connect(self.im_inds_validator)
        self.m_edit.setValidator(int_validator)

        # choose the number of SAIA instances
        a_label = QLabel('Number of image analysers: ', self)
        settings_grid.addWidget(a_label, 0,2, 1,1)
        self.a_edit = QLineEdit(self)
        settings_grid.addWidget(self.a_edit, 0,3, 1,1)
        self.a_edit.setText(str(self._a)) # default
        self.a_edit.editingFinished.connect(self.im_inds_validator)
        self.a_edit.setValidator(int_validator)

        # choose which histogram to use for survival probability calculations
        aind_label = QLabel('Image indices for analysers: ', self)
        settings_grid.addWidget(aind_label, 1,0, 1,1)
        self.a_ind_edit = QLineEdit(self)
        settings_grid.addWidget(self.a_ind_edit, 1,1, 1,1)
        self.a_ind_edit.setText(','.join(map(str, self.mw_inds))) # default
        self.a_ind_edit.setValidator(comma_validator)

        # choose which histogram to use for survival probability calculations
        reim_label = QLabel('Histogram indices for re-imaging: ', self)
        settings_grid.addWidget(reim_label, 1,2, 1,1)
        self.reim_edit = QLineEdit(self)
        settings_grid.addWidget(self.reim_edit, 1,3, 1,1)
        self.reim_edit.setText('; '.join(map(str, self.rw_inds))) # default
        self.reim_edit.setValidator(semico_validator)

        # get user to set the image size in pixels
        size_label = QLabel('Image size in pixels: ', self)
        settings_grid.addWidget(size_label, 2,0, 1,1)
        self.pic_size_edit = QLineEdit(self)
        settings_grid.addWidget(self.pic_size_edit, 2,1, 1,1)
        self.pic_size_edit.setText(str(self.stats['pic_size'])) # default
        self.pic_size_edit.textChanged[str].connect(self.pic_size_text_edit)
        self.pic_size_edit.setValidator(int_validator)

        # get image size from loading an image
        load_im_size = QPushButton('Load size from image', self)
        load_im_size.clicked.connect(self.load_im_size) # load image size from image
        load_im_size.resize(load_im_size.sizeHint())
        settings_grid.addWidget(load_im_size, 2,2, 1,1)

        # EMCCD bias offset
        bias_offset_label = QLabel('EMCCD bias offset: ', self)
        settings_grid.addWidget(bias_offset_label, 3,0, 1,1)
        self.bias_offset_edit = QLineEdit(self)
        settings_grid.addWidget(self.bias_offset_edit, 3,1, 1,1)
        self.bias_offset_edit.setText(str(self.stats['bias'])) # default
        self.bias_offset_edit.editingFinished.connect(self.CCD_stat_edit)
        self.bias_offset_edit.setValidator(double_validator) # only floats

        # EMCCD readout noise
        read_noise_label = QLabel('EMCCD read-out noise: ', self)
        settings_grid.addWidget(read_noise_label, 4,0, 1,1)
        self.read_noise_edit = QLineEdit(self)
        settings_grid.addWidget(self.read_noise_edit, 4,1, 1,1)
        self.read_noise_edit.setText(str(self.stats['Nr'])) # default
        self.read_noise_edit.editingFinished.connect(self.CCD_stat_edit)
        self.read_noise_edit.setValidator(double_validator) # only floats
        
        reset_win = QPushButton('Reset Analyses', self) 
        reset_win.clicked.connect(self.reset_analyses)
        reset_win.resize(reset_win.sizeHint())
        settings_grid.addWidget(reset_win, 5,0, 1,1)

        load_set = QPushButton('Reload Default Settings', self) 
        load_set.clicked.connect(self.load_settings)
        load_set.resize(load_set.sizeHint())
        settings_grid.addWidget(load_set, 5,1, 1,1)
        
        show_win = QPushButton('Show Current Analyses', self) 
        show_win.clicked.connect(self.show_analyses)
        show_win.resize(show_win.sizeHint())
        settings_grid.addWidget(show_win, 5,2, 1,1)

        #### tab for ROI ####
        roi_tab = QWidget()
        roi_grid = QGridLayout()
        roi_tab.setLayout(roi_grid)
        self.tabs.addTab(roi_tab, "Region of Interest")

        # bottom corner of ROI grid x position
        roi_x_label = QLabel('Grid bottom xpos: ', self)
        roi_grid.addWidget(roi_x_label, 0,0, 1,1)
        self.roi_x_edit = QLineEdit(self)
        roi_grid.addWidget(self.roi_x_edit, 0,1, 1,1)
        self.roi_x_edit.setText('0')  # default
        self.roi_x_edit.setValidator(int_validator) # only numbers
        
        # bottom corner of ROI grid y position
        roi_y_label = QLabel('Grid bottom ypos: ', self)
        roi_grid.addWidget(roi_y_label, 0,2, 1,1)
        self.roi_y_edit = QLineEdit(self)
        roi_grid.addWidget(self.roi_y_edit, 0,3, 1,1)
        self.roi_y_edit.setText('0')  # default
        self.roi_y_edit.setValidator(int_validator) # only numbers
        
        # ROI size
        roi_l_label = QLabel('ROI size: ', self)
        roi_grid.addWidget(roi_l_label, 0,4, 1,1)
        self.roi_l_edit = QLineEdit(self)
        roi_grid.addWidget(self.roi_l_edit, 0,5, 1,1)
        self.roi_l_edit.setText('1')  # default
        self.roi_l_edit.setValidator(int_validator) # only numbers
        
        im_widget = pg.GraphicsLayoutWidget() # containing widget
        viewbox = im_widget.addViewBox() # plot area to display image
        self.im_canvas = pg.ImageItem() # the image
        viewbox.addItem(self.im_canvas)
        roi_grid.addWidget(im_widget, 1,0, 6,8)
        # display the ROI from each analyser
        self.replot_rois()

        # make a histogram to control the intensity scaling
        self.im_hist = pg.HistogramLUTItem()
        self.im_hist.setImageItem(self.im_canvas)
        im_widget.addItem(self.im_hist)

        # buttons to create a grid of ROIs
        for i, label in enumerate(['Single ROI', 'Square grid', '2D Gaussian masks']):
            button = QPushButton(label, self) 
            button.clicked.connect(self.make_roi_grid)
            button.resize(button.sizeHint())
            roi_grid.addWidget(button, 8,i, 1,1)

        #### choose main window position and dimensions: (xpos,ypos,width,height)
        self.setGeometry(100, 100, 850, 600)
        self.setWindowTitle('- Settings for Single Atom Image Analysers -')
        self.setWindowIcon(QIcon('docs/tempicon.png'))
        
    #### #### user input functions #### #### 
            
    def pic_size_text_edit(self, text=''):
        """Update the specified size of an image in pixels when the user 
        edits the text in the line edit widget"""
        if text: # can't convert '' to int
            self.stats['pic_size'] = int(text)
            for mw in self.mw + self.rw:
                mw.pic_size_edit.setText(text)
                mw.pic_size_label.setText(text)

    def CCD_stat_edit(self):
        """Update the values used for the EMCCD bias offset and readout noise"""
        if self.bias_offset_edit.text(): # check the label isn't empty
            self.stats['bias'] = float(self.bias_offset_edit.text())
        if self.read_noise_edit.text():
            self.stats['Nr'] = float(self.read_noise_edit.text())
        for mw in self.mw + self.rw:
            mw.bias_offset_edit.setText(str(self.stats['bias']))
            mw.read_noise_edit.setText(str(self.stats['Nr']))

    def roi_text_edit(self, text=''):
        """Update the ROI position and size every time a text edit is made by
        the user to one of the line edit widgets"""
        xc, yc, l = [self.roi_x_edit.text(),
                            self.roi_y_edit.text(), self.roi_l_edit.text()]
        if any([v == '' for v in [xc, yc, l]]):
            xc, yc, l = 0, 0, 1 # default takes the top left pixel
        else:
            xc, yc, l = list(map(int, [xc, yc, l])) # crashes if the user inputs float
        
        if (xc - l//2 < 0 or yc - l//2 < 0 
            or xc + l//2 > self.stats['pic_size'] 
            or yc + l//2 > self.stats['pic_size']):
            l = 2*min([xc, yc])  # can't have the boundary go off the edge
        if int(l) == 0:
            l = 1 # can't have zero width
        self.stats['xc'], self.stats['yc'], self.stats['roi_size'] = map(int, [xc, yc, l])

    #### image display functions ####

    def update_im(self, event_im):
        """Receive the image array emitted from the event signal
        display the image in the image canvas."""
        self.im_canvas.setImage(event_im)
        self.im_hist.setLevels(np.min(event_im), np.max(event_im))

    def replot_rois(self):
        """Once an ROI has been edited, redraw all of them on the image.
        The list of ROIs are stored with labels: [(label, ROI), ...].
        Since the labels might not be unique, we can't use a dictionary."""
        viewbox = self.im_canvas.getViewBox()
        self.rois = []
        for i, mw in enumerate(self.mw + self.rw):
            try: # change position and label of ROI
                x0, y0 = mw.roi.pos()  # lower left corner of bounding rectangle
                xw, yw = mw.roi.size() # widths
                l = int(0.5*(xw+yw))   # want a square ROI
                # note: setting the origin as bottom left but the image has origin top left
                xc, yc = int(x0 + l//2), int(y0 + l//2)  # centre
                self.rois[i][0].setText(mw.name)
                self.rois[i][0].setColor(pg.intColor(i))
                self.rois[i][0].setPos([xc, yc])
                self.rois[i][1].setPos(mw.roi.pos())
                self.rois[i][1].setSize(mw.roi.size())
            except IndexError: # make new ROI
                self.rois.append((pg.TextItem(mw.name, pg.intColor(i), anchor=(0.5,0.5)), 
                                  pg.ROI(mw.roi.pos(), mw.roi.size(), movable=False)))
                font = QFont()
                font.setPixelSize(16)
                self.rois[i][0].setFont(font)
                viewbox.addItem(self.rois[i][0])
                viewbox.addItem(self.rois[i][1])
            mw.roi.sigRegionChangeFinished.connect(self.replot_rois) 
            self.rois[i][1].setPen(pg.intColor(i), width=3) # set ROI boundary colour

    def make_roi_grid(self, toggle=True):
        """Create a grid of ROIs and assign them to analysers that are using the
        same image. Methods:
        Single ROI       -- make all ROIs the same as the first analyser's 
        Square grid      -- evenly divide the image into a square region for
            each of the analyser's on this image.  
        2D Gaussian masks-- fit 2D Gaussians to atoms in the image."""
        # self.find(i)
        pass
            
    #### #### toggle functions #### #### 

    def set_all_windows(self, action=None):
        """Find which of the binning options and fit methods is checked 
        and apply this to all of the image analysis windows."""
        for mw in self.mw[:self._a] + self.rw[:len(self.rw_inds)]:
            for i in range(len(self.bin_actions)):
                mw.bin_actions[i].setChecked(self.bin_actions[i].isChecked())
            mw.set_bins()
            for i in range(len(self.fit_options)):
                mw.fit_options[i].setChecked(self.fit_options[i].isChecked())

    #### #### save and load data functions #### ####

    def get_default_path(self, default_path=''):
        """Get a default path for saving/loading images
        default_path: set the default path if the function doesn't find one."""
        return os.path.dirname(self.log_file_name) if self.log_file_name else default_path

    def try_browse(self, title='Select a File', file_type='all (*)', 
                open_func=QFileDialog.getOpenFileName):
        """Open a file dialog and retrieve a file name from the browser.
        title: String to display at the top of the file browser window
        default_path: directory to open first
        file_type: types of files that can be selected
        open_func: the function to use to open the file browser"""
        default_path = self.get_default_path()
        try:
            if 'PyQt4' in sys.modules:
                file_name = open_func(self, title, default_path, file_type)
            elif 'PyQt5' in sys.modules:
                file_name, _ = open_func(self, title, default_path, file_type)
            return file_name
        except OSError: return '' # probably user cancelled

    def load_image(self, trigger=None):
        """Prompt the user to select an image file to display."""
        file_name = self.try_browse(file_type='Images (*.asc);;all (*)')
        if file_name:  # avoid crash if the user cancelled
            im_vals = self.image_handler.load_full_im(file_name)
            self.update_im(im_vals)
    
    def load_images(self):
        """Prompt the user to choose a selection of image files."""
        im_list = []
        file_list = self.try_browse(title='Select Files', 
                file_type='Images(*.asc);;all (*)', 
                open_func=QFileDialog.getOpenFileNames)
        for fname in file_list:
            try:
                im_list.append(self.image_handler.load_full_im(fname))
            except Exception as e: # probably file size was wrong
                logger.error("Failed to load image file: "+fname+'\n'+str(e))
        return im_list
                
        
    def make_ave_im(self):
        """Make an average image from the files selected by the user and 
        display it."""
        if self.sender().text() == 'From Files':
            im_list = self.load_images()
        else: im_list = []
        if len(im_list):
            aveim = np.zeros(np.shape(im_list[0]))
        else: return 0 # no images selected
        for im in im_list:
            aveim += im
        self.update_im(aveim / len(im_list))
        return 1

    def load_settings(self, fname='.\\imageanalysis\\default.config'):
        """Load the default settings from a config file"""
        try:
            with open(fname, 'r') as f:
                for line in f:
                    key, val = line.split('=') # there should only be one = per line
                    self.stats[key] = self.types[key](val)
        except FileNotFoundError as e: 
            logger.warning('Image analysis settings could not find the default config.\n'+str(e))
    
    def save_settings(self, fname='.\\imageanalysis\\default.config'):
        """Save the current settings to a config file"""
        with open(fname, 'w+') as f:
            for key, val in self.stats.items():
                f.write(key+'='+str(val)+'\n')

    def load_im_size(self):
        """Get the user to select an image file and then use this to get the image size"""
        file_name = self.try_browse(file_type='Images (*.asc);;all (*)')
        if file_name:
            im_vals = np.genfromtxt(file_name, delimiter=' ')
            self.stats['pic_size'] = int(np.size(im_vals[0]) - 1)
            self.pic_size_edit.setText(str(self.stats['pic_size'])) # update loaded value
            self.pic_size_label.setText(str(self.stats['pic_size'])) # update loaded value

    def load_roi(self):
        """Get the user to select an image file and then use this to get the ROI centre"""
        file_name = self.try_browse(file_type='Images (*.asc);;all (*)')
        if file_name:
            # get pic size from this image in case the user forgot to set it
            im_vals = np.genfromtxt(file_name, delimiter=' ')
            self.stats['pic_size'] = int(np.size(im_vals[0]) - 1)
            self.pic_size_edit.setText(str(self.stats['pic_size'])) # update loaded value
            # get the position of the max count
            xcs, ycs  = np.where(im_vals == np.max(im_vals))
            self.stats['xc'], self.stats['yc'] = xcs[0], ycs[0]
            self.roi_x_edit.setText(str(self.stats['xc'])) 
            self.roi_y_edit.setText(str(self.stats['yc'])) 
            self.roi_l_edit.setText(str(self.stats['roi_size']))

    def save_hist_data(self, trigger=None, save_file_name='', confirm=True):
        """Prompt the user to give a directory to save the histogram data, then save"""
        if not save_file_name:
            save_file_name = self.try_browse(title='Save File', file_type='csv(*.csv);;all (*)', 
                        open_func=QFileDialog.getSaveFileName)
        if save_file_name:
            # don't update the threshold  - trust the user to have already set it
            self.add_stats_to_plot()
            # include most recent histogram stats as the top two lines of the header
            # self.image_handler.save(save_file_name,
            #              meta_head=list(self.histo_handler.temp_vals.keys()),
            #              meta_vals=list(self.histo_handler.temp_vals.values())) # save histogram
            try: 
                hist_num = self.histo_handler.stats['File ID'][-1]
            except IndexError: # if there are no values in the stats yet
                hist_num = -1
            if confirm:
                msg = QMessageBox()
                msg.setIcon(QMessageBox.Information)
                msg.setText("File saved to "+save_file_name+"\n"+
                        "and appended histogram %s to log file."%hist_num)
                msg.setStandardButtons(QMessageBox.Ok)
                msg.exec_()

    def save_varplot(self, save_file_name='', confirm=True):
        """Save the data in the current plot, which is held in the histoHandler's
        dictionary and saved in the log file, to a new file."""
        if not save_file_name:
            self.try_browse(title='Save File', file_type='dat(*.dat);;all (*)',
                            open_func=QFileDialog.getSaveFileName)
        if save_file_name:
            with open(save_file_name, 'w+') as f:
                f.write('#Single Atom Image Analyser Log File: collects histogram data\n')
                f.write('#include --[]\n')
                f.write('#'+', '.join(self.histo_handler.stats.keys())+'\n')
                for i in range(len(self.histo_handler.stats['File ID'])):
                    f.write(','.join(list(map(str, [v[i] for v in 
                        self.histo_handler.stats.values()])))+'\n')
            if confirm:
                msg = QMessageBox()
                msg.setIcon(QMessageBox.Information)
                msg.setText("Plot data saved to file "+save_file_name)
                msg.setStandardButtons(QMessageBox.Ok)
                msg.exec_()
        
    def check_reset(self):
        """Ask the user if they would like to reset the current data stored"""
        reply = QMessageBox.question(self, 'Confirm Data Replacement',
            "Do you want to discard all the current data?", 
            QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel, QMessageBox.Cancel)
        if reply == QMessageBox.Cancel:
            return 0
        elif reply == QMessageBox.Yes:
            for mw in self.mw + self.rw:
                mw.image_handler.reset_arrays() # gets rid of old data
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
    
    def show_analyses(self):
        """Display the instances of SAIA, filling the screen"""
        for i in range(self._a):
            self.mw[i].setGeometry(40+i*400//self._a, 100, 850, 500)
            self.mw[i].show()
        for i in range(len(self.rw_inds)):
            self.rw[i].setGeometry(45+i*400//len(self.rw_inds), 200, 850, 500)
            self.rw[i].show()

    def im_inds_validator(self, text=''):
        """The validator on the 'Image indices for analysers' line edit
        should only allow indices within the number of images per run,
        and should be a list with length of the total number of image analysers."""
        up = int(self.m_edit.text())-1 # upper limit
        a = int(self.a_edit.text())
        if up < 10: # defines which image index is allowed
            regstr = '[0-%s]'%up
        elif up < 100: 
            regstr = '[0-9]|[1-%s][0-9]|%s[0-%s]'%(up//10 - 1, up//10, up%10)
        else: regstr = r'\d+'
        if a > 1: # must have indices for all _a analysers
            regstr = '('+regstr+r',){0,%s}'%(a-1) + regstr
        regexp_validator = QRegExpValidator(QRegExp(regstr))
        self.a_ind_edit.setValidator(regexp_validator)

    def reset_analyses(self):
        """Remake the analyses instances for SAIA and re-image"""
        QMessageBox.information(self, 'Resetting Analyses', 'Resetting image analysis windows. This may take a while.')
        for mw in self.mw + self.rw:
            mw.image_handler.reset_arrays()
            mw.histo_handler.reset_arrays()
            mw.date = time.strftime("%d %b %B %Y", time.localtime()).split(" ")
            mw.set_bins()
            mw.close() # closes the display
        
        m, a = map(int, [self.m_edit.text(), self.a_edit.text()])
        self._m = m
        # make sure there are the right numer of main_window instances
        if a > self._a:
            for i in range(self._a, a):
                self.mw.append(main_window(self.results_path, self.image_storage_path, str(i)))
                self.mw_inds.append(i if i < m else m-1)
        self._a = a
        for mw in self.mw:
            mw.swap_signals() # reconnect signals

        ainds = []
        try: # set which images in the sequence each image analyser will use.
            ainds = list(map(int, self.a_ind_edit.text().split(',')))
        except ValueError as e:
            logger.warning('Invalid syntax for image analysis indices: '+self.a_ind_edit.text()+'\n'+str(e))
        if len(ainds) != self._a: 
            logger.warning('Warning: there are %s image indices for the %s image analysers.\n'%(len(ainds), self._a))
        for i, a in enumerate(ainds):
            try: self.mw_inds[i] = a
            except IndexError as e: 
                logger.warning('Cannot set image index for image analyser %s.\n'%i+str(e))

        self.im_inds_validator('')
        self.a_ind_edit.setText(','.join(map(str, self.mw_inds)))

        rinds = self.reim_edit.text().split(';') # indices of SAIA instances used for re-imaging
        for i in range(len(rinds)): # check the list input from the user has the right syntax
            try: 
                j, k = map(int, rinds[i].split(','))
                if j >= self._a or k >= self._a:
                    rind = rinds.pop(i)
                    logger.warning('Invalid histogram indices for re-imaging: '+rind)
            except ValueError as e:
                rind = rinds.pop(i)
                logger.error('Invalid syntax for re-imaging histogram indices: '+rind+'\n'+str(e))    
            except IndexError:
                break # since we're popping elements from the list its length shortens
        self.rw_inds = rinds
        
        for i in range(min(len(self.rw_inds), len(self.rw))): # update current re-image instances
            j, k = map(int, self.rw_inds[i].split(','))
            self.rw[i].ih1 = self.mw[j].image_handler
            self.rw[i].ih2 = self.mw[k].image_handler
        for i in range(len(self.rw), len(self.rw_inds)): # add new re-image instances as required
            j, k = map(int, self.rw_inds[i].split(','))
            self.rw.append(reim_window(self.mw[j].event_im,
                    [self.mw[j].image_handler, self.mw[k].image_handler],
                    self.results_path, self.image_storage_path, 'RW'+str(i)))
            
        self.show_analyses()
        self.m_changed.emit(m) # let other modules know the value has changed, and reconnect signals
        
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
        
    main_win = settings_window()
    main_win.show()
    if standalone: # if an app instance was made, execute it
        sys.exit(app.exec_()) # when the window is closed, the python code also stops
            
if __name__ == "__main__":
    # change directory to this file's location
    os.chdir(os.path.dirname(os.path.realpath(__file__))) 
    run()