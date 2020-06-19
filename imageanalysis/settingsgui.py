"""PyDex Image Analysis Settings
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
            QMenu, QActionGroup, QFont, QTableWidget, QTableWidgetItem, QTabWidget, 
            QVBoxLayout, QRegExpValidator) 
except ImportError:
    from PyQt5.QtCore import pyqtSignal, QRegExp
    from PyQt5.QtGui import (QIcon, QRegExpValidator, QFont)
    from PyQt5.QtWidgets import (QActionGroup, QVBoxLayout, QMenu, 
        QFileDialog, QMessageBox, QLineEdit, QGridLayout, QWidget,
        QApplication, QPushButton, QAction, QMainWindow, QTabWidget,
        QTableWidget, QTableWidgetItem, QLabel)
import logging
logger = logging.getLogger(__name__)
sys.path.append('.')
sys.path.append('..')
from strtypes import intstrlist, listlist
from maingui import main_window, remove_slot, int_validator, double_validator, nat_validator
from reimage import reim_window # analysis for survival probability
from roiHandler import ROI

####    ####    ####    ####

# main GUI window contains all the widgets                
class settings_window(QMainWindow):
    """Main GUI window managing settings for all instances of SAIA.

    Keyword arguments:
    nsaia         -- number of maingui.main_window instances to create
    nreim         -- number of reimage.reim_window instances to create
    results_path  -- the directory where result csv or dat files are saved.
    im_store_path -- the directory where images are saved. Default
    config_file   -- file name to load default configuration from
    """
    m_changed = pyqtSignal(int) # gives the number of images per run
    bias_changed = pyqtSignal(int) # gives the bias offset to subtract from counts in images

    def __init__(self, results_path='', im_store_path='', config_file='.\\imageanalysis\\default.config'):
        super().__init__()
        self.types = OrderedDict([('pic_width',int), ('pic_height',int), ('ROIs',listlist), 
            ('bias', int), ('image_path', str), ('results_path', str), ('last_image', str),
            ('window_pos',intstrlist), ('num_images',int), ('num_saia',int), ('num_reim',int)])
        self.stats = OrderedDict([('pic_width',512), ('pic_height',512), ('ROIs',[[1,1,1,1,1]]), 
            ('bias',697), ('image_path', im_store_path), ('results_path', results_path),
            ('last_image', ''), ('window_pos', [550, 20, 10, 200, 600, 400]),
            ('num_images',2), ('num_saia',2), ('num_reim',1)])
        self.load_settings(fname=config_file) # load default
        self.date = time.strftime("%d %b %B %Y", time.localtime()).split(" ") # day short_month long_month year
        self.results_path = results_path if results_path else self.stats['results_path'] # used for saving results
        self.last_path = self.stats['last_image'] # path history helps user get to the file they want
        self.image_storage_path = im_store_path if im_store_path else self.stats['image_path'] # used for loading image files
        self._m = self.stats['num_images'] # number of images per run 
        self._a = self.stats['num_saia'] # number of SAIA instances
        if len(self.stats['ROIs']) < self._a // self._m: # make the correct number of ROIs
            for i in range(len(self.stats['ROIs']), self._a // self._m):
                self.stats['ROIs'].append([1,1,1,1,1])
        self.mw = [main_window(results_path, im_store_path, 
            'ROI' + str(i//self._m) + '.Im' + str(i%self._m) + '.') for i in range(self._a)] # saia instances
        self.mw_inds = [i%self._m for i in range(self._a)] # the index of the image in the sequence to use 
        self.rw = [] # re-image analysis instances
        self.rw_inds = [] # which saia instances are used for the re-image instances
        if np.size(self.mw) >= self.stats['num_reim']*2:
            self.rw = [reim_window(self.mw[2*i].event_im, 
                [self.mw[2*i].image_handler, self.mw[2*i+1].image_handler],
                [self.mw[2*i].histo_handler, self.mw[2*i+1].histo_handler],
                results_path, im_store_path, 'ROI'+str(i)+'_Re_') for i in range(self.stats['num_reim'])]
            self.rw_inds = [str(2*i)+','+str(2*i+1) for i in range(self.stats['num_reim'])]
        self.rois = []  # list to hold ROI objects
        self.init_UI()  # make the widgets
        # make sure the analysis windows have the default settings:
        self.pic_size_text_edit()
        self.CCD_stat_edit()
        self.replot_rois()
        self.m_changed.emit(self._m)

    def reset_dates(self, date):
        """Reset the dates in all of the saia instances"""
        self.date = date
        for mw in self.mw + self.rw:
            mw.date = date
            mw.image_storage_path = os.path.join(self.image_storage_path, 
                date[3], date[2], date[0])
            try:
                results_path = mw.log_file_name.split('\\')[:-4]
                mw.init_log('\\'.join(results_path))
            except IndexError as e:
                logger.error('Settings window failed to re-initialise log file.\n'+str(e))
        
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
        self.fit_methods = []
        for action_label in ['separate gaussians', 'double poissonian', 
                            'single gaussian', 'double gaussian']:
            self.fit_methods.append(QAction(action_label, fit_menu, checkable=True, 
                checked=action_label=='double gaussian')) # set default
            fit_menu.addAction(self.fit_methods[-1])
            self.fit_options.addAction(self.fit_methods[-1])
        self.fit_methods[-1].setChecked(True) # set last method as checked: double gaussian
        self.fit_options.setExclusive(True) # only one option checked at a time
        self.fit_options.triggered.connect(self.set_all_windows)
        hist_menu.addMenu(fit_menu)

        fit_all = QAction('Fit all', self) 
        fit_all.triggered.connect(self.all_hists)
        hist_menu.addAction(fit_all)

        reset_all = QAction('Reset all', self) 
        reset_all.triggered.connect(self.all_hists)
        hist_menu.addAction(reset_all)

        save_all = QAction('Fit, Save, Reset all', self) 
        save_all.triggered.connect(self.all_hists)
        hist_menu.addAction(save_all)

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
        
        info_label = QLabel('In each run, the camera takes (# images per run).'+ 
            ' For each ROI, we create (# images per run) analysers.\nThe images'+
            ' are sent to these analysers in turn.\nIf you want to change the '+
            'order, use the comma-separated list in (Image indices for analyse'+
            'rs).\nIn total there will be (# images per run) x (# ROIs) analys'+
            'ers.\nEach re-image analyser uses 2 image analysers.')
        info_label.setFixedHeight(100)
        settings_grid.addWidget(info_label, 0,0, 1,4)
        
        # choose the number of image per run 
        m_label = QLabel('# images per run: ', self)
        settings_grid.addWidget(m_label, 1,0, 1,1)
        self.m_edit = QLineEdit(self)
        settings_grid.addWidget(self.m_edit, 1,1, 1,1)
        self.m_edit.setText(str(self._m)) # default
        self.m_edit.editingFinished.connect(self.im_inds_validator)
        self.m_edit.setValidator(int_validator)

        # choose the number of SAIA instances = #images x #ROIs
        a_label = QLabel('# ROIs: ', self) 
        settings_grid.addWidget(a_label, 1,2, 1,1)
        self.a_edit = QLineEdit(self)
        settings_grid.addWidget(self.a_edit, 1,3, 1,1)
        self.a_edit.setText(str(self._a//self._m)) # default
        self.a_edit.editingFinished.connect(self.im_inds_validator)
        self.a_edit.setValidator(nat_validator)

        # choose which histogram to use for survival probability calculations
        aind_label = QLabel('Image indices for analysers: ', self)
        settings_grid.addWidget(aind_label, 2,0, 1,1)
        self.a_ind_edit = QLineEdit(self)
        settings_grid.addWidget(self.a_ind_edit, 2,1, 1,1)
        self.a_ind_edit.setText(','.join(map(str, self.mw_inds))) # default
        self.a_ind_edit.setValidator(comma_validator)

        # choose which histogram to use for survival probability calculations
        reim_label = QLabel('# re-image analysers', self)
        settings_grid.addWidget(reim_label, 2,2, 1,1)
        self.reim_edit = QLineEdit(self)
        settings_grid.addWidget(self.reim_edit, 2,3, 1,1)
        self.reim_edit.setText(str(len(self.rw_inds)))
        self.reim_edit.setValidator(int_validator)
        # self.reim_edit.setText('; '.join(map(str, self.rw_inds))) # default # 'Histogram indices for re-imaging: '
        # self.reim_edit.setValidator(semico_validator)

        # get user to set the image size in pixels
        self.pic_width_edit = QLineEdit(self)
        self.pic_height_edit = QLineEdit(self)
        for i, label in enumerate([['Image width: ', self.pic_width_edit, 'pic_width'], 
                ['Image height', self.pic_height_edit, 'pic_height']]):
            button = QPushButton(label[0], self)
            button.clicked.connect(self.load_im_size) # load image size from image
            button.resize(button.sizeHint())
            settings_grid.addWidget(button, 3,2*i, 1,1)
            settings_grid.addWidget(label[1], 3,2*i+1, 1,1)
            label[1].textChanged.connect(self.pic_size_text_edit)
            label[1].setText(str(self.stats[label[2]])) # default
            label[1].setValidator(nat_validator)
        
        # user sets threshold for all analyses
        self.thresh_toggle = QPushButton('User Threshold: ', self)
        self.thresh_toggle.setCheckable(True)
        self.thresh_toggle.clicked.connect(self.set_thresh)
        settings_grid.addWidget(self.thresh_toggle, 4,0, 1,1)
        # user inputs threshold
        self.thresh_edit = QLineEdit(self)
        settings_grid.addWidget(self.thresh_edit, 4,1, 1,1)
        self.thresh_edit.textChanged.connect(self.set_thresh)
        self.thresh_edit.setValidator(int_validator)
        
        # EMCCD bias offset
        bias_offset_label = QLabel('EMCCD bias offset: ', self)
        settings_grid.addWidget(bias_offset_label, 5,0, 1,1)
        self.bias_offset_edit = QLineEdit(self)
        settings_grid.addWidget(self.bias_offset_edit, 5,1, 1,1)
        self.bias_offset_edit.setText(str(self.stats['bias'])) # default
        self.bias_offset_edit.editingFinished.connect(self.CCD_stat_edit)
        self.bias_offset_edit.setValidator(double_validator) # only floats
        
        # user variable value
        user_var_label = QLabel('User Variable: ', self)
        settings_grid.addWidget(user_var_label, 5,2, 1,1)
        self.var_edit = QLineEdit(self)
        self.var_edit.editingFinished.connect(self.set_user_var)
        settings_grid.addWidget(self.var_edit, 5,3, 1,1)
        self.var_edit.setText('0')  # default
        self.var_edit.setValidator(double_validator) # only numbers

        reset_win = QPushButton('Reset Analyses', self) 
        reset_win.clicked.connect(self.reset_analyses)
        reset_win.resize(reset_win.sizeHint())
        settings_grid.addWidget(reset_win, 6,0, 1,1)

        load_set = QPushButton('Reload Default Settings', self) 
        load_set.clicked.connect(self.load_settings)
        load_set.resize(load_set.sizeHint())
        settings_grid.addWidget(load_set, 6,1, 1,1)
        
        show_win = QPushButton('Show Current Analyses', self) 
        show_win.clicked.connect(self.show_analyses)
        show_win.resize(show_win.sizeHint())
        settings_grid.addWidget(show_win, 6,2, 1,1)
        
        #### tab for ROI ####
        roi_tab = QWidget()
        roi_grid = QGridLayout()
        roi_tab.setLayout(roi_grid)
        self.tabs.addTab(roi_tab, "Region of Interest")

        # display the ROI from each analyser
        im_widget = pg.GraphicsLayoutWidget() # containing widget
        viewbox = im_widget.addViewBox() # plot area to display image
        viewbox.enableAutoRange()
        self.im_canvas = pg.ImageItem() # the image
        viewbox.addItem(self.im_canvas)
        roi_grid.addWidget(im_widget, 4,0, 6,8)

        # table to set ROIs for main windows
        self.roi_table = QTableWidget(self._a//self._m, 5)
        self.roi_table.setHorizontalHeaderLabels(['ROI', 'xc', 'yc', 'w', 'h'])
        roi_grid.addWidget(self.roi_table, 0,0, 3,6)
        self.reset_table() # connects itemChanged signal to roi_table_edit()

        # set ROI for analysers from loaded default
        self.create_rois()

        # make a histogram to control the intensity scaling
        self.im_hist = pg.HistogramLUTItem()
        self.im_hist.setImageItem(self.im_canvas)
        im_widget.addItem(self.im_hist)

        # buttons to create a grid of ROIs
        for i, label in enumerate(['Single ROI', 'Square grid', '2D Gaussian masks']):
            button = QPushButton(label, self) 
            button.clicked.connect(self.make_roi_grid)
            button.resize(button.sizeHint())
            roi_grid.addWidget(button, 11,i, 1,1)

        button = QPushButton('Display masks', self) # button to display masks
        button.clicked.connect(self.show_ROI_masks)
        button.resize(button.sizeHint())
        roi_grid.addWidget(button, 11,i+1, 1,1)

        #### choose main window position and dimensions: (xpos,ypos,width,height)
        self.setWindowTitle('- Settings for Single Atom Image Analysers -')
        self.setWindowIcon(QIcon('docs/tempicon.png'))
        
    #### #### user input functions #### #### 

    def set_thresh(self, arg=''):
        """Sets the threshold in all of the analyser windows."""
        if not self.bin_actions[1].isChecked():
            msg = QMessageBox.information(self, 'Binning Mode', 
                'The histogram binning must be in manual mode in order to set the threshold.')
        for mw in self.mw + self.rw:
            if self.thresh_edit.text():
                mw.thresh_edit.setText(self.thresh_edit.text())
            mw.thresh_toggle.setChecked(self.thresh_toggle.isChecked())
            mw.set_thresh(self.thresh_toggle.isChecked()) # also calls bins_text_edit
            
    def pic_size_text_edit(self, text=''):
        """Update the specified size of an image in pixels when the user 
        edits the text in the line edit widget"""
        width, height = self.pic_width_edit.text(), self.pic_height_edit.text()
        if width and height: # can't convert '' to int
            self.stats['pic_width'] = int(width)
            self.stats['pic_height'] = int(height)
            for roi in self.rois:
                roi.s = (int(width), int(height))
            for mw in self.mw + self.rw:
                mw.pic_width_edit.setText(width)
                mw.pic_height_edit.setText(height)
                mw.pic_size_label.setText('('+width+', '+height+')')

    def CCD_stat_edit(self, emg=1, pag=4.5, Nr=8.8, acq_change=False):
        """Update the values used for the EMCCD bias offset, EM gain, preamp
        gain, and read noise.
        acq_change: True if the camera acquisition settings have been changed."""
        if self.bias_offset_edit.text(): # check the label isn't empty
            self.stats['bias'] = int(self.bias_offset_edit.text())
            self.bias_changed.emit(int(self.bias_offset_edit.text()))
        for mw in self.mw + self.rw:
            mw.bias_offset_edit.setText(str(self.stats['bias']))
            mw.CCD_stat_edit(emg, pag, Nr, acq_change)
        
    def set_user_var(self, text=''):
        """Update the user variable across all of the image analysers"""
        if self.var_edit.text():
            for mw in self.mw + self.rw:
                mw.var_edit.setText(self.var_edit.text())
                mw.set_user_var()

    def roi_table_edit(self, item):
        """When the user edits one of the cells in the table, update
        the corresponding ROI and display the new ROI."""
        if item.text():
            try:
                self.stats['ROIs'][item.row()][item.column()-1] = int(item.text())
                self.create_rois()
            except ValueError as e:
                logger.error('Invalid ROI value from table: '+item.text()+'\n'+str(e))
            except IndexError as e:
                logger.error('Not enough ROIs for table item %s\n'%item.row()+str(e))

    #### image display and ROI functions ####

    def cam_pic_size_changed(self, width, height):
        """Take the new image dimensions from the camera."""
        self.pic_width_edit.setText(str(width)) # triggers pic_size_text_edit
        self.pic_height_edit.setText(str(height))

    def update_im(self, image_array):
        """Receive the image array emitted from the event signal
        display the image in the image canvas."""
        im_vals = image_array - self.stats['bias']
        self.im_canvas.setImage(im_vals)
        self.im_hist.setLevels(np.min(im_vals), np.max(im_vals))

    def user_roi(self, roi):
        """The user drags an ROI and this updates the ROI centre and width"""
        # find which ROI was dragged
        i = 0
        for j, r in enumerate(self.rois):
            if r.roi == roi:
                i = j
                break
        x0, y0 = roi.pos()  # lower left corner of bounding rectangle
        w, h = roi.size() # widths
        # note: setting the origin as bottom left but the image has origin top left
        xc, yc = int(x0 + w//2), int(y0 + h//2)  # centre
        self.stats['ROIs'][i] = [xc, yc, int(w), int(h), r.t] # should never be indexerror
        r.label.setPos(x0, y0)
        r.w, r.h = int(w), int(h)
        r.translate_mask(xc, yc)
        self.replot_rois() # updates image analysis windows
        self.reset_table() # diplays ROI in table

    def set_rois(self, ROIlist):
        """Receive a list of ROI coordinates and use them to set the ROIs"""
        self.stats['ROIs'] = ROIlist
        self.create_rois()

    def create_rois(self):
        """Given xc, yc, and size from stats['ROIs'], create the
        ROIs that are displayed in the ROI tab and assign them to
        the image analysis windows."""
        viewbox = self.im_canvas.getViewBox()
        for i, mw in enumerate(self.mw[:self._a+1]):
            j = i // self._m
            try: 
                x, y, w, h, t = self.stats['ROIs'][j] # xc, yc, width, height, threshold
            except IndexError as e:
                logger.error('Not enough ROIs for main windows: %s\n'%j+str(e))
                self.stats['ROIs'].append([1,1,1,1,1])
                x, y, w, h, t = 1, 1, 1, 1, 1
            if not i % self._m: # for the first window in each set of _m
                try:
                    self.rois[j].roi.show()
                    self.rois[j].label.show()
                    self.rois[j].resize(x, y, w, h)
                    self.rois[j].t = t
                except IndexError: # make a new ROI 
                    self.rois.append(ROI((self.stats['pic_width'], self.stats['pic_height']), x, y, w, h, t, ID=j))
                    self.rois[j].roi.sigRegionChangeFinished.connect(self.user_roi) 
                    self.rois[j].roi.setZValue(10)   # make sure the ROI is drawn above the image
                    viewbox.addItem(self.rois[j].roi)
                    viewbox.addItem(self.rois[j].label)
            mw.roi_x_edit.setText(str(x)) # triggers roi_text_edit()
            mw.roi_y_edit.setText(str(y))
            mw.roi_l_edit.setText(str(w))
            mw.bias_offset_edit.setText(str(self.stats['bias']))
        for j in range(len(self.mw[:self._a+1])//self._m, len(self.rois)):
            self.rois[j].roi.hide() # remove extra ROIs
            self.rois[j].label.hide()

    def replot_rois(self, masks=[]):
        """Once an ROI has been edited, redraw all of them on the image.
        The list of ROIs are stored with labels: [(label, ROI), ...].
        Each ROI is applied to _m windows for _m images per sequence."""
        for i, mw in enumerate(self.mw):
            j = i // self._m   # apply the ROI to _m windows
            try: # update the ROI in the image analysis windows
                mw.roi.setPos(*self.stats['ROIs'][j][:2]) # triggers user_roi()
                if masks: mw.image_handler.mask = masks[j] # allows non-square mask
            except IndexError as e:
                logger.error('Failed to set main window ROI %s.\n'%j+str(e))

    def make_roi_grid(self, toggle=True, method=''):
        """Create a grid of ROIs and assign them to analysers that are using the
        same image. Methods:
        Single ROI       -- make all ROIs the same as the first analyser's 
        Square grid      -- evenly divide the image into a square region for
            each of the analysers on this image.  
        2D Gaussian masks-- fit 2D Gaussians to atoms in the image."""
        newmasks = [] # list of masks to pass on to analysis windows
        for r in self.rois: # disconnect slot, otherwise signal is triggered infinitely
            remove_slot(r.roi.sigRegionChangeFinished, self.user_roi, False)
        method = method if method else self.sender().text()
        pos, shape = self.rois[0].roi.pos(), self.rois[0].roi.size()
        if method == 'Single ROI':
            for i in range(len(self.rois)):
                self.stats['ROIs'][i] = list(map(int, [pos[0], pos[1], shape[0], shape[1], self.stats['ROIs'][i][-1]]))
                self.rois[i].resize(*map(int, [pos[0], pos[1], shape[0], shape[1]]))
        elif method == 'Square grid':
            d = int((self._a - 1)**0.5 + 1)  # number of ROIs per row
            X = int(self.stats['pic_width'] / d) # horizontal distance between ROIs
            Y = int(self.stats['pic_height'] / int((self._a - 3/4)**0.5 + 0.5)) # vertical distance
            for i in range(self._a // self._m): # ID of ROI
                try:
                    newpos = [int(X * (i%d + 0.5)),
                            int(Y * (i//d + 0.5))]
                    if any([newpos[0]//self.stats['pic_width'], newpos[1]//self.stats['pic_height']]):
                        logger.warning('Tried to set square ROI grid with (xc, yc) = (%s, %s)'%(newpos[0], newpos[1])+
                        ' outside of the image')
                        newpos = [0,0]
                    self.stats['ROIs'][i] = list(map(int, [newpos[0], newpos[1], shape[0], shape[1], self.stats['ROIs'][i][-1]]))
                    self.rois[i].resize(*map(int, [newpos[0], newpos[1], 1, 1]))
                except ZeroDivisionError as e:
                    logger.error('Invalid parameters for square ROI grid: '+
                        'x - %s, y - %s, pic size - (%s, %s), roi size - %s.\n'%(
                            pos[0], pos[1], self.stats['pic_width'], self.stats['pic_height'], (shape[0], shape[1]))
                        + 'Calculated width - %s, height - %s.\n'%(X, Y) + str(e))
        elif method == '2D Gaussian masks':
            try: 
                im = self.im_canvas.image.copy()
                if np.size(np.shape(im)) == 2:
                    for i, r in enumerate(self.rois):
                        r.create_gauss_mask(im) # fit 2D Gaussian to max pixel region
                        # then block that region out of the image
                        try:
                            im[r.x-r.w : r.x+r.w+1, r.y-r.h:r.y+r.h+1] = np.zeros((2*r.w+1, 2*r.h+1)) + np.min(im)
                        except (IndexError, ValueError): pass
                        newmasks.append(r.mask)
                        try:
                            self.stats['ROIs'][i] = list(map(int, [r.x, r.y, r.w, r.h, self.stats['ROIs'][i][-1]]))
                        except IndexError: 
                            self.stats['ROIs'].append(list(map(int, [r.x, r.y, r.w, r.h, 1])))
            except AttributeError: pass
        self.reset_table()
        self.replot_rois(newmasks)
        for r in self.rois: # reconnect slot
            remove_slot(r.roi.sigRegionChangeFinished, self.user_roi, True)

    def show_ROI_masks(self, toggle=True):
        """Make an image out of all of the masks from the ROIs and display it."""
        im = np.zeros((self.stats['pic_width'], self.stats['pic_height'])) + self.stats['bias']
        n = 1 if self._m != 1 else 0 # make a new ROI when there are a windows for m images
        for roi in self.rois[:(self._a+n)//self._m]:
            try: im += roi.mask
            except ValueError as e: logger.error('ROI %s has mask of wrong shape\n'%roi.id+str(e))
        self.update_im(im)

    def reset_table(self, newvals=None):
        """Resize the table of ROIs and then fill it with the ROIs stored in
        stats['ROIs']. While doing so, disconnect the table's itemChanged signal
        so that there isn't recurssion with create_rois() and user_roi()."""
        remove_slot(self.roi_table.itemChanged, self.roi_table_edit, False) # disconnect
        n = 1 if self._m != 1 else 0 # make a new ROI when there are a windows for m images
        self.roi_table.setRowCount((self._a+n)//self._m) # num windows / num images per sequence
        for i in range(self.roi_table.rowCount()):
            try:
                data = [str(i)] + list(map(str, self.stats['ROIs'][i]))
                for j in range(self.roi_table.columnCount()):    
                    self.roi_table.setItem(i, j, QTableWidgetItem())
                    self.roi_table.item(i, j).setText(data[j])
            except IndexError as e:
                self.stats['ROIs'].append([1,1,1,1,1])
                data = [str(i), '1', '1', '1', '1']
                for j in range(self.roi_table.columnCount()):
                    self.roi_table.setItem(i, j, QTableWidgetItem())
                    self.roi_table.item(i, j).setText(data[j])
                logger.error('Not enough ROIs for main windows in table: %s\n'%j+str(e))
        remove_slot(self.roi_table.itemChanged, self.roi_table_edit, True) # reconnect

    #### #### toggle functions #### #### 

    def set_all_windows(self, action=None):
        """Find which of the binning options and fit methods is checked 
        and apply this to all of the image analysis windows."""
        for mw in self.mw[:self._a] + self.rw[:len(self.rw_inds)]:
            for i in range(len(self.bin_actions)):
                mw.bin_actions[i].setChecked(self.bin_actions[i].isChecked())
            mw.set_bins()
            for i in range(len(self.fit_methods)):
                mw.fit_methods[i].setChecked(self.fit_methods[i].isChecked())
                
    #### #### multirun functions #### ####
    
    def end_multirun(self, *args, **kwargs):
        """Reconnect analyser event_im signals and display the empty histogram."""
        for mw in self.rw + self.mw:
            # reconnect previous signals
            mw.set_bins() # reconnects signal with given histogram binning settings
            mw.display_fit() # display the empty histograms
            mw.multirun = ''
    
    def multirun_save(self, results_path, measure_prefix, n=0, var='0', hist_id='0', *args, **kwargs):
        """Save the histograms as part of the multirun.
        results_path   -- base directory results are saved in
        measure_prefix -- label for the subdirectory results are saved in
        n              -- the current run number
        var            -- the user variable associated with this histogram
        hist_id        -- unique ID for histogram"""
        # get best fit on histograms, doing reimage last since their fits depend on the main hists
        for mw in self.mw[:self._a] + self.rw[:len(self.rw_inds)]: 
            mw.var_edit.setText(var) # also updates histo_handler temp vals
            mw.set_user_var() # just in case not triggered by the signal
            mw.bins_text_edit(text='reset') # set histogram bins 
            success = mw.display_fit(fit_method='check action') # get best fit
            success = mw.display_fit(fit_method='check action') # get best fit
            if not success:                   # if fit fails, use peak search
                mw.display_fit(fit_method='quick')
                mw.display_fit(fit_method='quick')
                logger.warning('\nMultirun run %s fitting failed. '%n +
                    'Histogram data in '+ measure_prefix+'\\'+mw.name + 
                    str(hist_id) + '.csv')
            # append histogram stats to measure log file:
            with open(os.path.join(results_path, measure_prefix, 
                    mw.name + measure_prefix + '.dat'), 'a') as f:
                f.write(','.join(list(map(str, mw.histo_handler.temp_vals.values()))) + '\n')
        # save and reset the histograms, make sure to do reimage windows first!
        for mw in self.rw[:len(self.rw_inds)] + self.mw[:self._a]: 
            mw.save_hist_data(save_file_name=os.path.join(results_path, measure_prefix, 
                    mw.name + str(hist_id) + '.csv'), confirm=False) # save histogram
            mw.image_handler.reset_arrays() # clear histogram
                
    def init_analysers_multirun(self, results_path, measure_prefix, appending=False, *args, **kwargs):
        """Prepare the active analysis windows for a multirun.
        results_path   -- the folder to save results files to
        measure_prefix -- label identifying this multirun, a folder with this
            name is created within results_path
        appending      -- whether to append results to the varplot"""
        for mw in self.mw[:self._a] + self.rw[:len(self.rw_inds)]:
            mw.image_handler.reset_arrays() # gets rid of old data
            mw.histo_handler.bf = None
            mw.plot_current_hist(mw.image_handler.histogram, mw.hist_canvas)
            if not appending: mw.clear_varplot() # keep the previous data if this multirun is to be appended
            mw.multirun = measure_prefix
            log_file_path = os.path.join(results_path, 
                mw.name + measure_prefix + '.dat')
            if not os.path.isfile(log_file_path):# start measure file, stores plot data
                mw.save_varplot(save_file_name=log_file_path, confirm=False) 


    #### #### save and load data functions #### ####

    def get_default_path(self, default_path=''):
        """Get a default path for saving/loading images
        default_path: set the default path if the function doesn't find one."""
        return default_path if default_path else os.path.dirname(self.last_path)

    def try_browse(self, title='Select a File', file_type='all (*)', 
                open_func=QFileDialog.getOpenFileName, defaultpath=''):
        """Open a file dialog and retrieve a file name from the browser.
        title: String to display at the top of the file browser window
        default_path: directory to open first
        file_type: types of files that can be selected
        open_func: the function to use to open the file browser"""
        default_path = self.get_default_path(defaultpath)
        try:
            if 'PyQt4' in sys.modules:
                file_name = open_func(self, title, default_path, file_type)
            elif 'PyQt5' in sys.modules:
                file_name, _ = open_func(self, title, default_path, file_type)
            if type(file_name) == str: self.last_path = file_name 
            return file_name
        except OSError: return '' # probably user cancelled

    def load_image(self, trigger=None):
        """Prompt the user to select an image file to display."""
        fname = self.try_browse(file_type='Images (*.asc);;all (*)')
        if fname:  # avoid crash if the user cancelled
            pic_width, pic_height = self.stats['pic_width'], self.stats['pic_height']
            try:
                self.mw[0].image_handler.set_pic_size(fname)
                self.cam_pic_size_changed(self.mw[0].image_handler.pic_width, 
                    self.mw[0].image_handler.pic_height) # tell analysers image shape has changed
                im_vals = self.mw[0].image_handler.load_full_im(fname)
                self.update_im(im_vals)
            except IndexError as e:
                self.cam_pic_size_changed(pic_width, pic_height) # reset image shape
                self.update_im(np.arange(pic_width*pic_height).reshape((pic_width, pic_height))+self.stats['bias'])
                logger.error("Settings window failed to load image file: "+fname+'\n'+str(e))
    
    def load_images(self):
        """Prompt the user to choose a selection of image files."""
        im_list = []
        file_list = self.try_browse(title='Select Files', 
                file_type='Images(*.asc);;all (*)', 
                open_func=QFileDialog.getOpenFileNames,
                defaultpath=self.image_storage_path)
        for fname in file_list:
            try:
                im_list.append(self.mw[0].image_handler.load_full_im(fname))
            except Exception as e: # probably file size was wrong
                logger.error("Settings window failed to load image file: "+fname+'\n'+str(e))
        return im_list
                
    def make_ave_im(self):
        """Make an average image from the files selected by the user and 
        display it."""
        if self.sender().text() == 'From Files':
            im_list = self.load_images()
        else: im_list = []
        if np.size(np.shape(im_list)) == 3:
            aveim = np.mean(im_list, axis=0)
            self.update_im(aveim)
            return 1

    def load_settings(self, toggle=True, fname='.\\imageanalysis\\default.config'):
        """Load the default settings from a config file"""
        try:
            with open(fname, 'r') as f:
                for line in f:
                    if len(line.split('=')) == 2:
                        key, val = line.replace('\n','').split('=') # there should only be one = per line
                        try:
                            self.stats[key] = self.types[key](val)
                        except KeyError as e:
                            logger.warning('Failed to load image analysis default config file line: '+line+'\n'+str(e))
        except FileNotFoundError as e: 
            logger.warning('Image analysis settings could not find the default.config file.\n'+str(e))
    
    def save_settings(self, fname='.\\imageanalysis\\default.config'):
        """Save the current settings to a config file"""
        with open(fname, 'w+') as f:
            for key, val in self.stats.items():
                f.write(key+'='+str(val)+'\n')
                
    def all_hists(self, fname='', action=''):
        """Get a fit from the current histograms, then, if action
        specifies it, save and reset the histograms for all 
        of the active image analyser windows, labelled by the window name.
        action: 'Fit'  - just get the best fit
                'Save' - fit then save the histograms
                'Reset'- fit then reset the histograms
           'Save Reset'- fit, save, then reset the histograms 
        """
        if hasattr(self.sender(), 'text') and not action:
            action = self.sender().text()
        if 'Save' in action:
            fpath = fname if fname else self.try_browse(title='Select a File Suffix', 
                    file_type='CSV (*.csv);;all (*)',
                    open_func=QFileDialog.getSaveFileName)
        else: fpath = 'notsaving'
        if fpath: # don't do anything if the user cancels
            fdir = os.path.dirname(fpath)
            fname = os.path.basename(fpath)
            for i in range(self._a): # fit main windows first
                self.mw[i].display_fit(fit_method='check action')
            for i in range(len(self.rw_inds)): # save re-image windows 
                self.rw[i].get_histogram() # since they depend on main windows
                self.rw[i].display_fit(fit_method='check action')
                if 'Save' in action:
                    self.rw[i].save_hist_data(
                        save_file_name=os.path.join(fdir, self.rw[i].name + fname), 
                        confirm=False)
                if 'Reset' in action:
                    self.rw[i].image_handler.reset_arrays() 
                    self.rw[i].histo_handler.bf = None
                    self.rw[i].hist_canvas.clear()
                    self.rw[i].hist1.clear()
                    self.rw[i].hist2.clear()
            for i in range(self._a): # then can save and reset main windows
                if 'Save' in action:
                    self.mw[i].save_hist_data(
                        save_file_name=os.path.join(fdir, self.mw[i].name + fname), 
                        confirm=False)
                if 'Reset' in action:
                    self.mw[i].image_handler.reset_arrays() 
                    self.mw[i].histo_handler.bf = None
                    self.mw[i].hist_canvas.clear()


    def load_im_size(self):
        """Get the user to select an image file and then use this to get the image size"""
        file_name = self.try_browse(file_type='Images (*.asc);;all (*)', defaultpath=self.image_storage_path)
        if file_name:
            shape = np.genfromtxt(file_name, delimiter=' ').shape
            # update loaded value - changing the text edit triggers pic_size_text_edit()
            try: 
                self.pic_width_edit.setText(str(shape[1] - 1))
                self.pic_height_edit.setText(str(shape[0]))
            except IndexError: 
                self.pic_width_edit.setText(str(shape[0] - 1))
                self.pic_height_edit.setText('1')

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
        # print("Image processing duration: %.4g "%(
        #         self.int_time*scale)+unit)
        # print("Image plotting duration: %.4g "%(
        #         self.plot_time*scale)+unit)
        
    #### #### UI management functions #### #### 
    
    def show_analyses(self, show_all=True):
        """Display the instances of SAIA, displaced from the left of the screen.
        show_all -- True: if main window is used for reimage, don't display.
                   False: display all main windows and reimage windows."""
        try:
            mwx, mwy, rwx, rwy, w, h = self.stats['window_pos']
        except ValueError: mwx, mwy, rwx, rwy, w, h = 600, 50, 10, 200, 600, 400
        if not show_all:
            hide = []
        else: hide = [int(ind) for pair in self.rw_inds for ind in pair.split(',')]
        for i in range(self._a):
            if i in hide:
                self.mw[i].close()
            else:
                self.mw[i].resize(w, h)
                self.mw[i].setGeometry(mwx+i*2*w//self._a, mwy, w, h)
                self.mw[i].show()
        for i in range(len(self.rw_inds)):
            self.rw[i].resize(w, h)
            self.rw[i].setGeometry(rwx+i*2*w//len(self.rw_inds), rwy, w, h)
            self.rw[i].show()

    def im_inds_validator(self, text=''):
        """The validator on the 'Image indices for analysers' line edit
        should only allow indices within the number of images per run,
        and should be a list with length of the total number of image analysers."""
        try:
            up = int(self.m_edit.text())-1 # upper limit
            a = int(self.a_edit.text()) * (up+1) # user chooses number ROIs not analysers
            self.stats['num_images'] = up + 1
            self.stats['num_saia'] = a
            self.stats['num_reim'] = int(self.reim_edit.text())
            if up < 10: # defines which image index is allowed
                regstr = '[0-%s]'%up
            elif up < 100: 
                regstr = '[0-9]|[1-%s][0-9]|%s[0-%s]'%(up//10 - 1, up//10, up%10)
            else: regstr = r'\d+'
            if a > 1: # must have indices for all _a analysers
                regstr = '('+regstr+r',){0,%s}'%(a-1) + regstr
            regexp_validator = QRegExpValidator(QRegExp(regstr))
            self.a_ind_edit.setValidator(regexp_validator)
        except ValueError as e: pass # logger.error('Invalid analysis setting.\n'+str(e))

    def reset_analyses(self):
        """Remake the analyses instances for SAIA and re-image"""
        try:
            x = int(self.reim_edit.text())
            m, a = map(int, [self.m_edit.text(), self.a_edit.text()])
            ainds = list(map(int, self.a_ind_edit.text().split(',')))
        except ValueError as e:
            logger.error('Invalid analysis settings.\n'+str(e))
            return 0
        
        for mw in self.mw + self.rw:
            mw.image_handler.reset_arrays()
            mw.histo_handler.reset_arrays()
            mw.date = time.strftime("%d %b %B %Y", time.localtime()).split(" ")
            mw.set_bins()
            mw.close() # closes the display
        
        self._m = m
        a *= m # user is choosing the number of ROIs, rather than number of analysers
        # make sure there are the right numer of main_window instances
        if a > self._a:
            for i in range(self._a, a):
                self.mw.append(main_window(self.results_path, self.image_storage_path, 
                    'ROI' + str(i//self._m) + '.Im' + str(i%self._m) + '.'))
                self.mw_inds.append(i%self._m)
                if len(self.stats['ROIs']) < (i // self._m)+1: # starting a new ROI
                    self.stats['ROIs'].append([1,1,1,1,1])
        self._a = a
        for mw in self.mw:
            mw.swap_signals() # reconnect signals
        self.create_rois() # display ROIs on image
        self.reset_table() # display (xc, yc, size) of ROIs in table

        if len(ainds) != self._a: 
            logger.warning('While creating new analysers: there are %s image indices for the %s image analysers.\n'%(len(ainds), self._a))
            ainds = [i % self._m for i in range(self._a)]
        for i, a in enumerate(ainds):
            try: 
                self.mw_inds[i] = a
                self.mw[i].name_edit.setText('ROI' + str(i//self._m) + '.Im' + str(a) + '.')
            except IndexError as e: 
                logger.warning('Cannot set image index for image analyser %s.\n'%i+str(e))

        self.im_inds_validator('')
        self.a_ind_edit.setText(','.join(map(str, self.mw_inds[:self._a])))

        # rinds = self.reim_edit.text().split(';') # indices of SAIA instances used for re-imaging
        # for i in range(len(rinds)): # check the list input from the user has the right syntax
        #     try: 
        #         j, k = map(int, rinds[i].split(','))
        #         if j >= self._a or k >= self._a:
        #             rind = rinds.pop(i)
        #             logger.warning('Invalid histogram indices for re-imaging: '+rind)
        #     except ValueError as e:
        #         rind = rinds.pop(i)
        #         logger.error('Invalid syntax for re-imaging histogram indices: '+rind+'\n'+str(e))    
        #     except IndexError:
        #         break # since we're popping elements from the list its length shortens
        # self.rw_inds = rinds
        self.rw_inds = []
        for i in range(int(self.reim_edit.text())):
            if 2*i+1 < self._a:
                self.rw_inds.append(str(2*i)+','+str(2*i+1))
            else:
                self.rw_inds.append('0,1')
        
        for i in range(min(len(self.rw_inds), len(self.rw))): # update current re-image instances
            j, k = map(int, self.rw_inds[i].split(','))
            self.rw[i].ih1 = self.mw[j].image_handler
            self.rw[i].ih2 = self.mw[k].image_handler
            self.rw[i].setWindowTitle(self.rw[i].name + ' - Re-Image Analaysing hists %s, %s'%(j,k))
        for i in range(len(self.rw), len(self.rw_inds)): # add new re-image instances as required
            j, k = map(int, self.rw_inds[i].split(','))
            self.rw.append(reim_window(self.mw[j].event_im,
                    [self.mw[j].image_handler, self.mw[k].image_handler],
                    [self.mw[j].histo_handler, self.mw[k].histo_handler],
                    self.results_path, self.image_storage_path, 'ROI'+str(i)+'_Re_'))
            self.rw[i].setWindowTitle(self.rw[i].name + ' - Re-Image Analaysing hists %s, %s'%(j,k))
            
        self.pic_size_text_edit()
        self.set_thresh()
        self.CCD_stat_edit()
        self.replot_rois()
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
        if reply == QMessageBox.Yes or reply == QMessageBox.No:
            if reply == QMessageBox.Yes:
                self.save_hist_data()   # save current state
            for mw in self.mw + self.rw: mw.close()
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
        
    main_win = settings_window(config_file='default.config')
    main_win.show()
    if standalone: # if an app instance was made, execute it
        sys.exit(app.exec_()) # when the window is closed, the python code also stops
            
if __name__ == "__main__":
    # change directory to this file's location
    os.chdir(os.path.dirname(os.path.realpath(__file__))) 
    run()