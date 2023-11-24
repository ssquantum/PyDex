"""PyDex Atom Checker
Stefan Spence 23/02/22

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
from PyQt5.QtCore import pyqtSignal, QTimer
from PyQt5.QtGui import QIcon, QFont, QIntValidator
from PyQt5.QtWidgets import (QMenu, QFileDialog, QMessageBox, QLineEdit, 
        QGridLayout, QWidget, QApplication, QPushButton, QAction, QMainWindow, 
        QLabel, QTableWidget, QHBoxLayout, QCheckBox)
if '.' not in sys.path: sys.path.append('.')
if '..' not in sys.path: sys.path.append('..')
from strtypes import intstrlist, listlist, error, warning, info
from maingui import reset_slot, int_validator, double_validator # single atom image analysis
from roiHandler import ROI, roi_handler

nat_validator = QIntValidator()    # natural numbers 
nat_validator.setBottom(1) # > 0

####    ####    ####    ####

class atom_window(QMainWindow):
    """GUI window displaying ROIs and the counts recorded in them

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
            image_shape=(512,512), name='', num_images = 1):
        super().__init__()
        self.name = name
        self.setObjectName(name)
        self.num_images = num_images
        self.last_im_path = last_im_path
        self.rh = {'Cs':roi_handler(Cs_rois, image_shape, label='Cs'), 
                    'Rb':roi_handler(Rb_rois, image_shape, label='Rb')}
        self.init_UI() # adjust widgets from main_window
        self.event_im.connect(self.rh['Cs'].process)
        self.event_im.connect(self.rh['Rb'].process)
        self.event_im.connect(self.update_plots)
        self.checking = False # whether the atom checker is active or not
        self.timer = QTimer() 
        self.timer.t0 = 0 # trigger the experiment after the timeout
        
        
    def make_checkbox(self, r, i, atom):
        """Assign properties to checkbox so that it can be easily associated with an ROI"""
        r.plottoggle = QCheckBox(self, checked=True) # plot the line?
        r.plottoggle.i = i
        r.plottoggle.atom = atom
        r.plottoggle.stateChanged[int].connect(self.show_line)
                
    def init_UI(self):
        """Create all the widgets and position them in the layout"""
        self.centre_widget = QWidget()
        layout = QGridLayout() # make tabs for each main display 
        self.centre_widget.setLayout(layout)
        self.setCentralWidget(self.centre_widget)

        font = QFont() 
        font.setPixelSize(16) # make text size bigger

        #### menubar at top gives options ####
        menubar = self.menuBar()

        # file menubar allows you to save/load data
        file_menu = menubar.addMenu('File')
        load_im = QAction('Load Image', self) # display a loaded image
        load_im.triggered.connect(self.load_image)
        file_menu.addAction(load_im)
        
        make_im = QAction('Make average image', self) # from image files (using file browser)
        make_im.triggered.connect(self.make_ave_im)
        file_menu.addAction(make_im)

        save_hist = QAction('Save Histograms', self)
        save_hist.triggered.connect(self.save_roi_hists)
        file_menu.addAction(save_hist)

        # ROI menu for sending, receiving, and auto-generating ROIs
        rois_menu = menubar.addMenu('ROIs')
        self.send_rois_action = QAction('Send ROIs to analysis', self)
        self.send_rois_action.triggered.connect(self.emit_rois)
        rois_menu.addAction(self.send_rois_action)

        self.recv_rois_action = QAction('Get ROIs from analysis', self)
        rois_menu.addAction(self.recv_rois_action) # connected by runid.py

        save_cs_rois_action = QAction('Save Cs ROIs to file', self)
        save_cs_rois_action.triggered.connect(self.save_cs_rois)
        rois_menu.addAction(save_cs_rois_action)
        
        save_rb_rois_action = QAction('Save Rb ROIs to file', self)
        save_rb_rois_action.triggered.connect(self.save_rb_rois)
        rois_menu.addAction(save_rb_rois_action)

        load_cs_rois_action = QAction('Load Cs ROIs from file', self)
        load_cs_rois_action.triggered.connect(self.load_cs_rois)
        rois_menu.addAction(load_cs_rois_action)
        
        load_rb_rois_action = QAction('Load Rb ROIs from file', self)
        load_rb_rois_action.triggered.connect(self.load_rb_rois)
        rois_menu.addAction(load_rb_rois_action)


        # get ROI coordinates by fitting to image
        for i, label in enumerate(['Single ROI', 'Square grid', '2D Gaussian masks']):
            action = QAction(label, self) 
            action.triggered.connect(self.make_roi_grid)
            rois_menu.addAction(action)

        pg.setConfigOption('background', 'w') # set graph background default white
        pg.setConfigOption('foreground', 'k') # set graph foreground default black

        hbox = QHBoxLayout()
        # toggle to continuously plot images as they come in
        self.hist_toggle = QPushButton('Auto-update histograms', self)
        self.hist_toggle.setCheckable(True)
        self.hist_toggle.setChecked(True)
        self.hist_toggle.clicked[bool].connect(self.set_hist_update)
        hbox.addWidget(self.hist_toggle )
        
        # toggle whether to update histograms or not
        self.im_show_toggle = QPushButton('Auto-display last image', self)
        self.im_show_toggle.setCheckable(True)
        self.im_show_toggle.clicked[bool].connect(self.set_im_show)
        hbox.addWidget(self.im_show_toggle)
        
        # reset the list of counts in each ROI displayed in the plots
        self.reset_button = QPushButton('Reset plots', self)
        self.reset_button.clicked.connect(self.reset_plots)
        hbox.addWidget(self.reset_button)

        hbox.addWidget(QLabel('# images:'))
        self.box_num_images = QLineEdit()
        self.box_num_images.setValidator(nat_validator)
        self.box_num_images.setText(str(self.num_images))
        hbox.addWidget(self.box_num_images)
        

        # number of ROIs chosen by user
        self.rois_edit = {}
        for atom in ['Cs', 'Rb']:
            nrois_label = QLabel('# '+atom+' ROIs: ', self)
            hbox.addWidget(nrois_label)
            self.rois_edit[atom] = QLineEdit(str(len(self.rh[atom].ROIs)), self)
            self.rois_edit[atom].name = atom
            hbox.addWidget(self.rois_edit[atom])
            self.rois_edit[atom].setValidator(int_validator)
            
        layout.addLayout(hbox, 0,0,1,10)
        
        #### display image with ROIs ####
        
        im_widget = pg.GraphicsLayoutWidget() # containing widget
        viewbox = im_widget.addViewBox() # plot area to display image
        self.im_canvas = pg.ImageItem() # the image
        viewbox.addItem(self.im_canvas)
        layout.addWidget(im_widget, 1,0,4,5)
        
        #### table has all of the values for the ROIs ####
        self.tables = {'Cs':QTableWidget(len(self.rh['Cs'].ROIs), 7),
                    'Rb':QTableWidget(len(self.rh['Rb'].ROIs), 7)}
        layout.addWidget(self.tables['Cs'], 1,5,2,5)
        layout.addWidget(self.tables['Rb'], 3,5,2,5)
        
        self.plots = {} # display plots of counts for each ROI         
        for atom in ['Cs', 'Rb']:
            self.tables[atom].setHorizontalHeaderLabels(['x', 'y', 'w', 'h', 'Threshold', 'Auto-thresh', 'Plot'])
            for i, r in enumerate(self.rh[atom].ROIs):
                self.make_checkbox(r, i, atom)
                # line edits with ROI x, y, w, h, threshold, auto update threshold
                for j, label in enumerate(list(r.edits.values())+[r.threshedit, r.autothresh, r.plottoggle]): 
                    self.tables[atom].setCellWidget(i, j, label)
                  
            # plots  
            pw = pg.PlotWidget() # main subplot of histogram
            pw.setTitle(atom)
            self.plots[atom] = {'plot':pw, 'legend':pw.addLegend(), 
                'counts':[pw.plot(np.zeros(1000), name=self.rh[atom].ROIs[j].id, 
                        pen=pg.intColor(j)) for j in range(len(self.rh[atom].ROIs))],
                'thresh':[pw.addLine(y=1, pen=pg.intColor(j)) for j in range(len(self.rh[atom].ROIs))]}
            pw.getAxis('bottom').tickFont = font
            pw.getAxis('left').tickFont = font             
            
        hbox = QHBoxLayout()
        hbox.addWidget(self.plots['Cs']['plot'])
        hbox.addWidget(self.plots['Rb']['plot'])
        layout.addLayout(hbox, 5, 0, 2,10)  # allocate space in the grid
        
        # update number of ROIs and display them when user inputs
        self.rois_edit['Cs'].textChanged[str].connect(self.create_new_rois)
        self.rois_edit['Rb'].textChanged[str].connect(self.create_new_rois)
                
        self.display_rois() # put ROIs on the image

        #### extra buttons ####
        
        # the user can trigger the experiment early by pressing this button
        self.trigger_button = QPushButton('Manual trigger experiment', self)
        self.trigger_button.clicked.connect(self.send_trigger)
        layout.addWidget(self.trigger_button, 10,0, 1,2)
        
        button = QPushButton('Display masks', self) # button to display masks
        button.clicked.connect(self.show_ROI_masks)
        button.resize(button.sizeHint())
        layout.addWidget(button, 10,2, 1,1)

        # maximum duration to wait for
        timeout_label = QLabel('Timeout (s): ', self)
        layout.addWidget(timeout_label, 10,5, 1,1)
        self.timeout_edit = QLineEdit('0', self)
        self.timeout_edit.setValidator(double_validator)
        self.timeout_edit.textEdited[str].connect(self.change_timeout)
        layout.addWidget(self.timeout_edit, 10,6, 1,1)
        #
        self.setWindowTitle(self.name+' - Atom Checker -')
        self.setWindowIcon(QIcon('docs/atomcheckicon.png'))

    #### #### user input functions #### ####

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

    def load_cs_rois(self, file_name=''):
        self.load_rois(file_name, 'Cs')
    
    def load_rb_rois(self, file_name=''):
        self.load_rois(file_name, 'Rb')

####    ####    ####    #### 

def run():
    """Initiate an app to run the program
    if running in Pylab/IPython then there may already be an app instance"""
    app = QApplication.instance()
    standalone = app is None # false if there is already an app instance
    if standalone: # if there isn't an instance, make one
        app = QApplication(sys.argv) 
        
    boss = atom_window()
    boss.showMaximized()
    if standalone: # if an app instance was made, execute it
        sys.exit(app.exec_()) # when the window is closed, the python code also stops
            
if __name__ == "__main__":
    # change directory to PyDex folder
    os.chdir(os.path.dirname(os.path.realpath(__file__))) 
    run()