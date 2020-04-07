"""Single Atom Re-Image Analyser
Stefan Spence 22/08/19
For use in a re-imaging sequence.

 - Create two main.py instances of SAIA to analyse different images 
 in a sequence
 - Display the survival histogram - if there's an atom in the 
 first image, then take the second image.
 - Allow the user to display the two running instances of main.py
"""
import os
import sys
import time
import functools
import numpy as np
from astropy.stats import binom_conf_interval
import pyqtgraph as pg    # not as flexible as matplotlib but works a lot better with qt
# some python packages use PyQt4, some use PyQt5...
try:
    from PyQt4.QtCore import pyqtSignal 
    from PyQt4.QtGui import QFont, QLabel, QMessageBox
except ImportError:
    from PyQt5.QtCore import pyqtSignal
    from PyQt5.QtGui import QFont
    from PyQt5.QtWidgets import QLabel, QMessageBox
from maingui import main_window, remove_slot  # a single instance of SAIA

# main GUI window contains all the widgets                
class reim_window(main_window):
    """Main GUI window managing two sub-instance of SAIA.

    The 1st instance responds to the first image, and the 2nd
    instance responds to the second image produced in a sequence.
    Use Qt to produce the window where the histogram plot is shown.
    A simple interface allows the user to close or open the displays from
    the two instances of SAIA. Separate tabs are made for 
    settings, the histogram, histogram statistics,
    displaying images, and plotting histogram statistics.
    This GUI was produced with help from http://zetcode.com/gui/pyqt5/.
    Keyword arguments:
    signal        -- the pyqtSignal that is used to trigger updates
    imhandlers    -- list of two instances of image_handler analysis classes.
    histhandlers  -- list of two instances of histo_handler analysis classes
    results_path  -- directory to save log file and results to.
    im_store_path -- the directory where images are saved.
    name          -- an ID for this window, prepended to saved files.
    """
    def __init__(self, signal, imhandlers=[], histhandlers=[], results_path='.', 
            im_store_path='.', name=''):
        self.event_im = signal # uses the signal from a SAIA instance
        super().__init__(results_path=results_path, 
                        im_store_path=im_store_path, name=name)
        self.ih1, self.ih2 = imhandlers # used to get histogram data
        self.hh1, self.hh2 = histhandlers # get histogram fitting and stats
        self.adjust_UI() # adjust widgets from main_window
        
    def adjust_UI(self):
        """Edit the widgets created by main_window"""
        # self.hist_canvas.setTitle("Histogram of CCD counts")
        self.setWindowTitle(self.name+' - Re-Image Analyser - ')

        # change font size
        font = QFont()
        font.setPixelSize(14)

        #### edit histogram tab: display all image handlers ####
        hist_grid = self.tabs.widget(1).layout()
        hist_grid.removeWidget(self.hist_canvas)
        self.hist_canvas.setTitle("Recapture")
        self.hist1 = pg.PlotWidget()
        self.hist1.setTitle("Before")
        self.hist2 = pg.PlotWidget()
        self.hist2.setTitle("After")
        for hist in [self.hist1, self.hist2]:
            hist.getAxis('bottom').tickFont = font
            hist.getAxis('left').tickFont = font
        hist_grid.addWidget(self.hist1, 1,0, 3,8)
        hist_grid.addWidget(self.hist2, 4,0, 3,8)
        hist_grid.addWidget(self.hist_canvas, 7,0, 3,8)

        #### edit stats tab: display all histogram statistics ####

        stat_grid = self.tabs.widget(2).layout()
        for i, text in enumerate(['Histogram: ', 'Recapture', 'Before', 'After']):
            label = QLabel(text, self)
            stat_grid.addWidget(label, 1+len(self.histo_handler.stats.keys()),i, 1,1)
        self.hist1_stats = {}  # dictionary of stat labels for hist1
        self.hist2_stats = {}  # dictionary of stat labels for hist2
        # get the statistics from the histogram handler
        for i, labels in enumerate([self.hist1_stats, self.hist2_stats]):
            for j, label_text in enumerate(self.histo_handler.stats.keys()):
                labels[label_text] = QLabel('', self) # value
                stat_grid.addWidget(labels[label_text], 1+j,2+i, 1,1)

        # take the threshold from the second image handler
        self.thresh_toggle.setChecked(True)


    #### #### canvas functions #### ####

    def get_histogram(self):
        """Take the histogram from the 'after' images where the 'before' images
        contained an atom"""
        try:
            int(np.log(self.ih1.thresh)) # don't do anything if threshold is < 1
            atom = np.where(np.array(self.ih1.stats['Counts']) // self.ih1.thresh > 0, True, False)
            idxs = [i for i, val in enumerate(self.ih2.stats['File ID']) 
                    if any([val == v for j, v in enumerate(self.ih1.stats['File ID']) if atom[j]])]
            # take the after images when the before images contained atoms
            t1 = time.time()
            self.image_handler.stats['Mean bg count'] = [self.ih2.stats['Mean bg count'][i] for i in idxs]
            self.image_handler.stats['Bg s.d.']  = [self.ih2.stats['Bg s.d.'][i] for i in idxs]
            self.image_handler.stats['Counts']   = [self.ih2.stats['Counts'][i] for i in idxs]
            self.image_handler.stats['File ID']  = [self.ih2.stats['File ID'][i] for i in idxs]
            self.image_handler.stats['ROI centre count'] = [self.ih2.stats['ROI centre count'][i] for i in idxs]
            self.image_handler.stats['Max xpos'] = [self.ih2.stats['Max xpos'][i] for i in idxs]
            self.image_handler.stats['Max ypos'] = [self.ih2.stats['Max ypos'][i] for i in idxs]
            self.image_handler.ind = np.size(self.image_handler.stats['Counts'])
            self.image_handler.stats['Atom detected'] = [self.ih2.stats['Atom detected'][i] for i in idxs]
            self.image_handler.stats['Include']  = [self.ih2.stats['Include'][i] for i in idxs]
            self.image_handler.thresh = int(self.thresh_edit.text()) if self.thresh_edit.text() else self.ih2.thresh
            t2 = time.time()
            self.int_time = t2 - t1
        except (ValueError, OverflowError): t2 = 0 # invalid threshold, don't process
        return t2

    #### #### Overridden display functions #### ####

    def display_fit(self, toggle=True, fit_method='quick'):
        """Plot the best fit calculated by histo_handler.process
        and display the histogram statistics in the stat_labels"""
        sendertext = ''
        if hasattr(self.sender(), 'text'): # could be called by a different sender
            sendertext = self.sender().text()
        if fit_method == 'check action' or sendertext == 'Get best fit':
            try: fit_method = self.fit_options.checkedAction().text()
            except AttributeError: fit_method = 'quick'
        elif sendertext == 'Update statistics':
            fit_method = 'quick'
        for ih, hh, canv, labels in zip([self.ih1, self.ih2, self.image_handler],
                [self.hh1, self.hh2, self.histo_handler], 
                [self.hist1, self.hist2, self.hist_canvas],
                [self.hist1_stats, self.hist2_stats, self.stat_labels]): 
            if hh == self.histo_handler:
                _ = self.get_histogram()
            success = hh.process(ih, labels['User variable'].text(), 
                fix_thresh=self.thresh_toggle.isChecked(), method=fit_method)
            if success: 
                for key in hh.stats.keys(): # update the text labels
                    labels[key].setText(str(hh.temp_vals[key]))
                self.plot_current_hist(ih.histogram, canv)
                if hh.bf and hh.bf.bffunc and type(hh.bf.ps)!=type(None): # plot the curve on the histogram
                    xs = np.linspace(min(hh.bf.x), max(hh.bf.x), 200)
                    canv.plot(xs, hh.bf.bffunc(xs, *hh.bf.ps), pen='b')
        return success
    
    def update_plot(self, im, include=True):
        """Same as update_plot_only because we want the threshold to be taken
        from the second histogram (after image), not calculated in this reimage histogram."""
        t2 = self.get_histogram()
        # display the name of the most recent file
        if self.image_handler.ind > 1:
            self.recent_label.setText('Just processed image '
                        + str(self.image_handler.stats['File ID'][-1]))
        for imh, hc in [[self.ih1.histogram, self.hist1], # thresh for ih1, ih2 set in main window
                        [self.ih2.histogram, self.hist2], 
                        [self.image_handler.histogram, self.hist_canvas]]:
            self.plot_current_hist(imh, hc) # update the displayed plot
        self.plot_time = time.time() - t2

    def update_plot_only(self, im, include=True):
        """Receive the event path emitted from the system event handler signal.
        Take the histogram from the 'after' images where the 'before' images
        contained an atom and then update the figure without changing the 
        threshold value."""
        t2 = self.get_histogram()
        # display the name of the most recent file
        if self.image_handler.ind > 1:
            self.recent_label.setText('Just processed image '
                        + str(self.image_handler.stats['File ID'][-1]))
        for imh, hc in [[self.ih1.histogram, self.hist1], 
                        [self.ih2.histogram, self.hist2], 
                        [self.image_handler.histogram, self.hist_canvas]]:
            self.plot_current_hist(imh, hc) # update the displayed plot
        self.plot_time = time.time() - t2

    #### #### Overridden save and load functions #### ####

    def check_reset(self):
        """Ask the user if they would like to reset the current data stored"""
        reply = QMessageBox.question(self, 'Confirm Data Replacement',
            "Do you want to discard the current data?", 
            QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel, QMessageBox.Cancel)
        if reply == QMessageBox.Cancel:
            return 0
        elif reply == QMessageBox.Yes:
            for hh in [self.histo_handler, self.hh1, self.hh2]:
                hh.bf = None
            for ih in [self.image_handler, self.ih1, self.ih2]:
                ih.reset_arrays() # gets rid of old data
        return 1

    def load_from_csv(self, trigger=None):
        """Prompt the user to select a csv file to load histogram data from.
        It must have the specific layout that the image_handler saves in."""
        if self.check_reset():
            before_fn = self.try_browse(title='Select first histogram', file_type='csv(*.csv);;all (*)')
            after_fn = self.try_browse(title='Select second histogram', file_type='csv(*.csv);;all (*)')
            if before_fn and after_fn:
                header = self.ih1.load(before_fn)
                header = self.ih2.load(after_fn)
                if self.ih1.ind > 0:
                    self.display_fit(fit_method='quick')

    #### #### Overridden user input functions #### ####

    def set_user_var(self, text=''):
        """When the user finishes editing the var_edit line edit, update the displayed 
        user variable and assign it in the temp_vals of the histo_handler"""
        if self.var_edit.text():
            for hh, labels in zip([self.histo_handler, self.hh1, self.hh2],
                        [self.stat_labels, self.hist1_stats, self.hist2_stats]):
                hh.temp_vals['User variable'] = hh.types['User variable'](self.var_edit.text())
                labels['User variable'].setText(self.var_edit.text())

    

    #### #### toggle functions #### #### 
    