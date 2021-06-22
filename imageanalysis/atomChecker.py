"""PyDex Atom Checker
Stefan Spence 13/04/20

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
# some python packages use PyQt4, some use PyQt5...
try:
    from PyQt4.QtCore import pyqtSignal, QTimer
    from PyQt4.QtGui import (QApplication, QPushButton, QWidget, QLabel, QAction,
            QGridLayout, QMainWindow, QMessageBox, QLineEdit, QIcon, QFileDialog,
            QMenu, QFont) 
except ImportError:
    from PyQt5.QtCore import pyqtSignal, QTimer
    from PyQt5.QtGui import QIcon, QFont
    from PyQt5.QtWidgets import (QMenu, QFileDialog, QMessageBox, QLineEdit, 
        QGridLayout, QWidget, QApplication, QPushButton, QAction, QMainWindow, 
        QLabel)
if '.' not in sys.path: sys.path.append('.')
if '..' not in sys.path: sys.path.append('..')
from strtypes import intstrlist, listlist, error, warning, info
from maingui import reset_slot, int_validator, double_validator # single atom image analysis
from roiHandler import ROI, roi_handler

####    ####    ####    ####

class atom_window(QMainWindow):
    """GUI window displaying ROIs and the counts recorded in them

    Keyword arguments:
    last_im_path -- the directory where images are saved.
    rois         -- list of ROI coordinates (xc, yc, width, height).
    num_plots    -- number of plots to display counts on. A square number.
    image_shape  -- shape of the images being taken, in pixels (x,y).
    name         -- an ID for this window, prepended to saved files.
    """
    event_im = pyqtSignal(np.ndarray) # image taken by the camera as np array
    roi_values = pyqtSignal(list) # list of ROIs (x, y, w, h, threshold)
    rearr_msg  = pyqtSignal(str)  # message to send AWG about rearranging
    
    def __init__(self, last_im_path='.', rois=[(1,1,1,1)], num_plots=9, 
            image_shape=(512,512), name=''):
        super().__init__()
        self.name = name
        self.setObjectName(name)
        self.last_im_path = last_im_path
        self.rh = roi_handler(rois, image_shape)
        self.init_UI(num_plots) # adjust widgets from main_window
        self.event_im.connect(self.rh.process)
        self.event_im.connect(self.update_plots)
        self.checking = False # whether the atom checker is active or not
        self.timer = QTimer() 
        self.timer.t0 = 0 # trigger the experiment after the timeout
        
    def init_UI(self, num_plots=4):
        """Create all the widgets and position them in the layout"""
        self.centre_widget = QWidget()
        layout = QGridLayout()       # make tabs for each main display 
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
        self.send_rois_action.triggered.connect(self.send_rois)
        rois_menu.addAction(self.send_rois_action)

        self.recv_rois_action = QAction('Get ROIs from analysis', self)
        rois_menu.addAction(self.recv_rois_action) # connected by runid.py

        save_rois_action = QAction('Save ROIs to file', self)
        save_rois_action.triggered.connect(self.save_rois)
        rois_menu.addAction(save_rois_action)

        load_rois_action = QAction('Load ROIs from file', self)
        load_rois_action.triggered.connect(self.load_rois)
        rois_menu.addAction(load_rois_action)


        # get ROI coordinates by fitting to image
        for i, label in enumerate(['Single ROI', 'Square grid', '2D Gaussian masks']):
            action = QAction(label, self) 
            action.triggered.connect(self.make_roi_grid)
            rois_menu.addAction(action)

        pg.setConfigOption('background', 'w') # set graph background default white
        pg.setConfigOption('foreground', 'k') # set graph foreground default black

        # toggle to continuously plot images as they come in
        self.im_show_toggle = QPushButton('Auto-display last image', self)
        self.im_show_toggle.setCheckable(True)
        self.im_show_toggle.clicked[bool].connect(self.set_im_show)
        layout.addWidget(self.im_show_toggle, 0,0, 1,1)

        # number of ROIs chosen by user
        nrois_label = QLabel('Number of ROIs: ', self)
        layout.addWidget(nrois_label, 0,1, 1,1)
        self.nrois_edit = QLineEdit(str(len(self.rh.ROIs)), self)
        layout.addWidget(self.nrois_edit, 0,2, 1,1)
        self.nrois_edit.setValidator(int_validator)

        # reset the list of counts in each ROI displayed in the plots
        self.reset_button = QPushButton('Reset plots', self)
        self.reset_button.clicked.connect(self.reset_plots)
        layout.addWidget(self.reset_button, 0,3, 1,1)
        
        #### display image with ROIs ####
        
        im_widget = pg.GraphicsLayoutWidget() # containing widget
        viewbox = im_widget.addViewBox() # plot area to display image
        self.im_canvas = pg.ImageItem() # the image
        viewbox.addItem(self.im_canvas)
        layout.addWidget(im_widget, 1,0, 9,6)
        # update number of ROIs and display them when user inputs
        self.nrois_edit.textChanged[str].connect(self.display_rois)
        
        #### display plots of counts for each ROI ####
        self.plots = [] # plot to display counts history
        k = int(np.sqrt(num_plots))
        for i in range(num_plots):
            pw = pg.PlotWidget() # main subplot of histogram
            self.plots.append({'plot':pw, 'counts':pw.plot(np.zeros(1000)),
                'thresh':pw.addLine(y=1, pen='r')})
            pw.getAxis('bottom').tickFont = font
            pw.getAxis('left').tickFont = font
            layout.addWidget(pw, 1+(i//k)*3, 7+(i%k)*6, 2,6)  # allocate space in the grid
            try:
                r = self.rh.ROIs[i]
                pw.setTitle('ROI '+str(r.id))
                # line edits with ROI x, y, w, h, threshold, auto update threshold
                for j, label in enumerate(list(r.edits.values())+[r.threshedit, r.autothresh]): 
                    layout.addWidget(label, (i//k)*3, 7+(i%k)*6+j, 1,1)
                label = QLabel('Auto-thresh', self)
                layout.addWidget(label, (i//k)*3, 8+(i%k)*6+j, 1,1)
            except IndexError as e: pass # warning('Atom Checker has more plots than ROIs')
        
        self.display_rois() # put ROIs on the image

        #### extra buttons ####
        
        # the user can trigger the experiment early by pressing this button
        self.trigger_button = QPushButton('Manual trigger experiment', self)
        self.trigger_button.clicked.connect(self.send_trigger)
        layout.addWidget(self.trigger_button, 2+num_plots//k*3,8, 1,1)
        

        button = QPushButton('Display masks', self) # button to display masks
        button.clicked.connect(self.show_ROI_masks)
        button.resize(button.sizeHint())
        layout.addWidget(button, 2+num_plots//k*3,9+i+1, 1,1)

        # maximum duration to wait for
        timeout_label = QLabel('Timeout (s): ', self)
        layout.addWidget(timeout_label, 2+num_plots//k*3,9+i+2, 1,1)
        self.timeout_edit = QLineEdit('0', self)
        self.timeout_edit.setValidator(double_validator)
        self.timeout_edit.textEdited[str].connect(self.change_timeout)
        layout.addWidget(self.timeout_edit, 2+num_plots//k*3,9+i+3, 1,1)
        #
        self.setWindowTitle(self.name+' - Atom Checker -')
        self.setWindowIcon(QIcon('docs/atomcheckicon.png'))

    #### #### processing functions #### ####

    def get_rearrange(self, atomstring=''):
        """Calculate the rearrangement to fill the desired ROIs"""
        # .... tbc .....
        self.rearr_msg.emit(atomstring)

    #### #### user input functions #### ####

    def set_im_show(self, toggle):
        """If the toggle is True, always update the display with the last image."""
        reset_slot(self.event_im, self.update_im, toggle)

    def change_timeout(self, newval):
        """Time in seconds to wait before sending the trigger to continue the 
        experiment. Default is 0 which waits indefinitely."""
        try:
            self.timer.t0 = float(newval)
        except ValueError: pass

    def user_roi(self, roi):
        """The user drags an ROI and this updates the ROI centre and width"""
        # find which ROI was dragged
        for r in self.rh.ROIs:
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

    def send_rois(self, toggle=0):
        """Emit the signal with the list of ROIs"""
        self.roi_values.emit([[r.x, r.y, r.w, r.h, r.t] for r in self.rh.ROIs])

    def send_trigger(self, toggle=0):
        """Emit the roi_handler's trigger signal to start the experiment"""
        if self.checking: self.rh.trigger.emit(1)

    #### #### automatic ROI assignment #### ####

    def make_roi_grid(self, toggle=True, method=''):
        """Create a grid of ROIs and assign them to analysers that are using the
        same image. Methods:
        Single ROI       -- make all ROIs the same as the first analyser's 
        Square grid      -- evenly divide the image into a square region for
            each of the analysers on this image.  
        2D Gaussian masks-- fit 2D Gaussians to atoms in the image."""
        method = method if method else self.sender().text()
        pos, shape = self.rh.ROIs[0].roi.pos(), self.rh.ROIs[0].roi.size()
        if method == 'Single ROI':
            for r in self.rh.ROIs:
                r.resize(*map(int, [pos[0], pos[1], shape[0], shape[1]]))
        elif method == 'Square grid':
            n = len(self.rh.ROIs) # number of ROIs
            d = int((n - 1)**0.5 + 1)  # number of ROIs per row
            X = int(self.rh.shape[0] / d) # horizontal distance between ROIs
            Y = int(self.rh.shape[1] / int((n - 3/4)**0.5 + 0.5)) # vertical distance
            for i in range(n): # ID of ROI
                try:
                    newx, newy = int(X * (i%d + 0.5)), int(Y * (i//d + 0.5))
                    if any([newx//self.rh.shape[0], newy//self.rh.shape[1]]):
                        warning('Tried to set square ROI grid with (xc, yc) = (%s, %s)'%(newx, newy)+
                        ' outside of the image')
                        newx, newy = 0, 0
                    self.rh.ROIs[i].resize(*map(int, [newx, newy, 1, 1]))
                except ZeroDivisionError as e:
                    error('Invalid parameters for square ROI grid: '+
                        'x - %s, y - %s, pic size - %s, roi size - %s.\n'%(
                            pos[0], pos[1], self.rh.shape[0], (shape[0], shape[1]))
                        + 'Calculated width - %s, height - %s.\n'%(X, Y) + str(e))
        elif method == '2D Gaussian masks':
            try: 
                im = self.im_canvas.image.copy() - self.rh.bias
                if np.size(np.shape(im)) == 2:
                    for r in self.rh.ROIs:
                        r.create_gauss_mask(im) # fit 2D Gaussian to max pixel region
                        # then block that region out of the image
                        try:
                            im[r.x-r.w : r.x+r.w+1, r.y-r.h:r.y+r.h+1] = np.zeros((2*r.w+1, 2*r.h+1)) + np.min(im)
                        except (IndexError, ValueError): pass
            except AttributeError: pass

    #### #### canvas functions #### ####

    def display_rois(self, n=''):
        """Add the ROIs from the roi_handler to the viewbox if they're
        not already displayed."""
        if n:
            self.rh.create_rois(int(n))
        viewbox = self.im_canvas.getViewBox()
        for item in viewbox.allChildren(): # remove unused ROIs
            if ((type(item) == pg.graphicsItems.ROI.ROI or 
                    type(item) == pg.graphicsItems.TextItem.TextItem) and 
                    item not in [r.roi for r in self.rh.ROIs] + [r.label for r in self.rh.ROIs]):
                viewbox.removeItem(item)
        layout = self.centre_widget.layout()
        k = np.sqrt(len(self.plots))
        for i, r in enumerate(self.rh.ROIs):
            if r.roi not in viewbox.allChildren():
                reset_slot(r.roi.sigRegionChangeFinished, self.user_roi, True) 
                reset_slot(r.threshedit.textEdited, self.update_plots, True)
                r.roi.setZValue(10)   # make sure the ROI is drawn above the image
                viewbox.addItem(r.roi)
                viewbox.addItem(r.label)
                try:
                    self.plots[i]['plot'].setTitle('ROI '+str(r.id))
                    for j, label in enumerate(list(r.edits.values())+[r.threshedit, r.autothresh]):
                        layout.addWidget(label, (i//k)*3, 7+(i%k)*6+j, 1,1)
                except IndexError as e: pass # warning('Atom Checker has more plots than ROIs')
    
    def update_plots(self, im=0, include=1):
        """Plot the history of counts in each ROI in the associated plots"""
        for i, r in enumerate(self.rh.ROIs):
            try:
                self.plots[i]['counts'].setData(r.c[:r.i]) # history of counts
                if r.autothresh.isChecked(): r.thresh() # update threshold
                self.plots[i]['thresh'].setValue(r.t) # plot threshold
                self.plots[i]['plot'].setTitle('ROI %s, LP=%.3g'%(r.id, r.LP()))
            except IndexError: pass

    def reset_plots(self):
        """Empty the lists of counts in the ROIs and update the plots."""
        self.rh.reset_count_lists(range(len(self.rh.ROIs)))
        for p in self.plots:
            try:
                for l in p['counts']: l.setData([1])
            except TypeError:
                p['counts'].setData([1])

    def update_im(self, im):
        """Display the image in the image canvas."""
        self.im_canvas.setImage(im)

    def show_ROI_masks(self, toggle=True):
        """Make an image out of all of the masks from the ROIs and display it."""
        im = np.zeros(self.rh.shape)
        for roi in self.rh.ROIs:
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
                im_vals = self.rh.load_full_im(file_name)
                im_list.append(im_vals)
            except Exception as e: # probably file size was wrong
                warning("Failed to load image file: "+file_name+'\n'+str(e)) 
        return im_list

    def load_image(self, trigger=None):
        """Prompt the user to select an image file to display"""
        file_name = self.try_browse(file_type='Images (*.asc);;all (*)')
        if file_name:  # avoid crash if the user cancelled
            self.last_im_path = file_name
            self.rh.set_pic_size(file_name) # get image size
            im_vals = self.rh.load_full_im(file_name)
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

    def save_roi_hists(self, file_name='AtomCheckerHist.csv'):
        """Save the histogram data from the ROIs"""
        if not file_name:
            file_name = self.try_browse(title='Select File', 
                file_type='csv(*.csv);;all (*)', 
                open_func=QFileDialog.getSaveFileName)
        if file_name:
            try:
                out_arr = np.zeros((len(self.rh.ROIs)*2, self.rh.ROIs[0].i))
                head0 = ''
                head1 = ''
                head2 = ''
                for i, r in enumerate(self.rh.ROIs):
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

    def save_rois(self, file_name=''):
        """Save the coordinates and thresholds of the ROIs"""
        if not file_name:
            file_name = self.try_browse(title='Select File', file_type='txt(*.txt);;all (*)', 
                open_func=QFileDialog.getSaveFileName)
        if file_name:
            try:
                ROIlist = [[int(x.text()) for x in list(r.edits.values())+[r.threshedit]] for r in self.rh.ROIs]
                with open(file_name, 'w+') as f:
                    f.write(str(ROIlist))
            except (ValueError, IndexError, PermissionError) as e:
                error("AtomChecker couldn't save file %s\n"%file_name+str(e))     

    def load_rois(self, file_name=''):
        """Load the coordinates and thresholds of the ROIs"""
        if not file_name:
            file_name = self.try_browse(title='Select File', file_type='txt(*.txt);;all (*)', 
                open_func=QFileDialog.getOpenFileName)
        if file_name:
            try:
                with open(file_name, 'r') as f:
                    ROIlist = eval(f.readline())
                self.rh.create_rois(len(ROIlist))
                self.rh.resize_rois(ROIlist)
                self.display_rois()
            except (ValueError, IndexError, PermissionError) as e:
                error("AtomChecker couldn't save file %s\n"%file_name+str(e))     


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