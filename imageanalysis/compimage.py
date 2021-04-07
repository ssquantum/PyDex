"""Single Atom Comp-Image Analyser
Stefan Spence 23/03/21
For use in a sequence with several ROIs.

 - Create several main.py instances of SAIA to analyse different images 
 in a sequence
 - Display the survival histogram - if there are atoms in all of the 
 first images, then take the second images.
"""
import os
import sys
import time
import numpy as np
import pyqtgraph as pg    # not as flexible as matplotlib but works a lot better with qt
# some python packages use PyQt4, some use PyQt5...
try:
    from PyQt4.QtCore import pyqtSignal 
    from PyQt4.QtGui import QFont, QLabel, QMessageBox
except ImportError:
    from PyQt5.QtCore import pyqtSignal
    from PyQt5.QtGui import QFont
    from PyQt5.QtWidgets import QLabel, QMessageBox
from maingui import main_window, reset_slot

# main GUI window contains all the widgets                
class compim_window(main_window):
    """GUI window managing several sub-instances of SAIA.

    If an image in set [hists1] contains atoms, use the corresponding image from
    the after histograms. Compare the histograms to find joint recapture.
    Keyword arguments:
    signal        -- the pyqtSignal that is used to trigger updates
    befores       -- list of image_handler stats dictionaries from before histograms.
    afters        -- list of image_handler stats dictionaries from before histograms.
    results_path  -- directory to save log file and results to.
    im_store_path -- the directory where images are saved.
    name          -- an ID for this window, prepended to saved files.
    """
    request = pyqtSignal(str) # send request for new data
    data = pyqtSignal(list)   # receive new data

    def __init__(self, signal, befores=[], afters=[], results_path='.', 
            im_store_path='.', name=''):
        self.event_im = signal # uses the signal from a SAIA instance
        super().__init__(results_path=results_path, 
                        im_store_path=im_store_path, name=name)
        self.hists1 = imhandlers # before histograms, select which images to include
        self.hists2 = imhandlers # after histograms, calculate survival probability
        self.adjust_UI() # adjust widgets from main_window
        
    def adjust_UI(self):
        """Edit the widgets created by main_window"""
        self.setWindowTitle(self.name+' - Comp-Image Analyser - ')

        #### edit settings tab: choose from list of image handlers ####
        settings_grid = self.tabs.widget(0).layout()
        # remove the ROI / EMCCD info which is redundant
        settings_grid.removeWidget()
        # combobox widgets to choose before ROI/images
        # button to add extra ROI/images widget
        # combobox widgets to choose after ROI/images
        
        #### edit histogram tab: 
        hist_grid = self.tabs.widget(1).layout()
        menubar = self.menuBar() # menu selects which histogram to display
        self.hist_canvas 
        
        
        #### edit stats tab: display all histogram statistics ####

        stat_grid = self.tabs.widget(2).layout()
        
        # take the threshold from the second image handler
        self.thresh_toggle.setChecked(True)


    #### #### canvas functions #### ####

    def get_histogram(self, befores, afters):
        """Take the histogram from the 'after' images where the 'before' images
        contained an atom."""
        try:
            s = befores.pop(0)
            ids = set(s['File ID'][np.where(s['Atom detected'] > 0, True, False)])
            for s in befores: # find the file IDs that have atoms in all before histograms
                ids = ids & set(s['File ID'][np.where(s['Atom detected'] > 0, True, False)])

            total = len(ids)
            atoms = set()
            full = atoms & set() # intersection
            atoms * atoms
            some = (atoms ^ set()) | () # in one but not the other
            atoms + atoms > 0 & < len(afters)
            none = (1 - atoms) * (1 - atoms)


            # make it more thread safe: take a copy of dictionaries at the start 
            s1 = self.ih1.stats.copy() 
            s2 = self.ih2.stats.copy()
            atom = np.where(np.array(s1['Counts']) // self.ih1.thresh > 0, True, False)
            idxs = np.arange(len(s2['File ID']))[np.isin(s2['File ID'], np.array(s1['File ID'])[atom])]
            # take the after images when the before images contained atoms
            t1 = time.time() # list comprehension is faster than np array for list length < 1500
            t2 = time.time()
            self.int_time = t2 - t1
        except (ValueError, OverflowError, IndexError): t2 = 0 # invalid threshold, don't process
        return t2

    #### #### Overridden display functions #### ####

    def request_data(self):
        """

    def display_fit(self, toggle=True, fit_method='quick'):
        """Plot the best fit calculated by histo_handler.process
        and display the histogram statistics in the stat_labels"""
        reset_slot(self.event_im, self.update_plot) # in case it gets disconnected by maingui
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
        reply = QMessageBox.information(self, 'Confirm Data Replacement',
            "This window does not support this action.")
        return 0

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
    