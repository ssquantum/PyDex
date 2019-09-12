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
    from PyQt4.QtCore import QThread, pyqtSignal, QEvent, QRegExp, Qt
    from PyQt4.QtGui import (QApplication, QPushButton, QWidget, QLabel, QAction,
            QGridLayout, QMainWindow, QMessageBox, QLineEdit, QIcon, QFileDialog,
            QDoubleValidator, QIntValidator, QComboBox, QMenu, QActionGroup, 
            QTabWidget, QVBoxLayout, QFont, QRegExpValidator) 
except ImportError:
    from PyQt5.QtCore import QThread, pyqtSignal, QEvent, QRegExp, Qt
    from PyQt5.QtGui import (QGridLayout, QMessageBox, QLineEdit, QIcon, 
            QFileDialog, QDoubleValidator, QIntValidator, QComboBox, QMenu, 
            QActionGroup, QVBoxLayout, QFont, QRegExpValidator)
    from PyQt5.QtWidgets import (QApplication, QPushButton, QWidget, QTabWidget,
        QAction, QMainWindow, QLabel)
from main import main_window  # a single instance of SAIA

# main GUI window contains all the widgets                
class reim_window(main_window):
    """Main GUI window managing two sub-instance of SAIA.

    The 1st instance responds to the first image, and the 2nd
    instance responds to the second image produced in a sequence.
    Use Qt to produce the window where the histogram plot is shown.
    A simple interface allows the user to close or open the displays from
    the two instances of SAIA. Separate tabs are made for 
    settings, multirun options, the histogram, histogram statistics,
    displaying images, and plotting histogram statistics.
    This GUI was produced with help from http://zetcode.com/gui/pyqt5/.
    Keyword arguments:
    config_file  -- if absolute path to a config file that contains 
        the directories for the directoryWatcher is supplied, then use 
        this instead of the default './config/config.dat'.
    pop_up       -- control whether a pop-up window asks the user to 
        initiate the directoryWatcher. 
        0: don't initiate the directoryWatcher.
        1: tacitly initiate the directoryWatcher.
        2: pop-up window asks the user if they want to initiate.
    """
    def __init__(self, results_path='.', name=''):
        super().__init__(results_path=results_path, name=name)
        self.adjust_UI() # adjust widgets from main_window

        # Make instances of SAIA that watch different directories
        self.mws = []
        for i in range(2):
            self.mws.append(main_window(
                    results_path=results_path, name=str(i)))
            # don't ask the user to confirm on close, run in background
            self.mws[i].closeEvent = self.closeAndContinue
            self.mws[i].setWindowTitle(
                        str(i) + ' - Single Atom Image Analyser -')
        # connect signals. Must not override main_window.set_bins()
        self.set_bins_reim() 
        
    def adjust_UI(self):
        """Edit the widgets created by main_window"""
        # self.hist_canvas.setTitle("Histogram of CCD counts")
        self.setWindowTitle('Master Single Atom Re-Image Analyser')

        menubar = self.menuBar()
        # redisplay mwsinstances of SAIA if they were closed
        setting_menu = menubar.addMenu('Windows')
        show_win = QAction('Show Windows', self) 
        show_win.triggered.connect(self.show_windows)
        setting_menu.addAction(show_win)

        # update the histogram when getting statistics
        self.stat_update_button.clicked[bool].connect(self.get_histogram)
        self.fit_update_button.clicked[bool].connect(self.get_histogram)
        self.fit_bg_button.clicked[bool].connect(self.get_histogram)

    #### #### canvas functions #### #### 

    def get_histogram(self):
        """Take the histogram from the 'after' images where the 'before' images
        contained an atom"""
        t2 = 0
        ih1 = self.mws[0].image_handler
        ih2 = self.mws[1].image_handler
        atom = (ih1.counts // ih1.thresh).astype(bool)
        idxs = [i for i, val in enumerate(ih2.files) if any(val == j for j in ih1.files[atom])]
        # take the after images when the before images contained atoms
        t1 = time.time()
        self.image_handler.mean_count = ih2.mean_count[idxs]
        self.image_handler.std_count  = ih2.std_count[idxs]
        self.image_handler.counts     = ih2.counts[idxs]
        self.image_handler.files      = ih2.files[idxs]
        self.image_handler.mid_count  = ih2.mid_count[idxs]
        self.image_handler.xc_list    = ih2.xc_list[idxs]
        self.image_handler.yc_list    = ih2.xc_list[idxs]
        self.image_handler.im_num = np.size(self.image_handler.counts) - 1
        self.image_handler.atom = ih2.counts[idxs] // self.image_handler.thresh
        t2 = time.time()
        self.int_time = t2 - t1
        return t2
        
    def update_plot(self, event_im):
        """Receive the event path emitted from the system event handler signal.
        Take the histogram from the 'after' images where the 'before' images
        contained an atom and then update the figure."""
        t2 = self.get_histogram()
        # display the name of the most recent file
        if self.image_handler.im_num > 0:
            self.recent_label.setText('Just processed image '
                        + self.mws[1].image_handler.files[self.mws[1].image_handler.im_num-1])
        self.plot_current_hist(self.image_handler.hist_and_thresh) # update the displayed plot
        self.plot_time = time.time() - t2

    def update_plot_only(self, event_im):
        """Receive the event path emitted from the system event handler signal.
        Take the histogram from the 'after' images where the 'before' images
        contained an atom and then update the figure without changing the 
        threshold value."""
        t2 = self.get_histogram()
        # display the name of the most recent file
        if self.image_handler.im_num > 0:
            self.recent_label.setText('Just processed image '
                        + self.mws[1].image_handler.files[self.mws[1].image_handler.im_num-1])
        self.plot_current_hist(self.image_handler.histogram) # update the displayed plot
        self.plot_time = time.time() - t2

    def multirun_step(self, event_im):
        """A multirun step to control the master and the before/after histograms.
        mw2 is left to its own multirun_step since the event_path is different.
        Receive event paths emitted from the system event handler signal
        for the first '# omit' events, only save the files
        then for '# hist' events, add files to a histogram,
        then save the histogram. Repeat this for the user variables in 
        the multi-run list, then return to normal operation as set by the 
        histogram binning."""
        if self.mr['v'] < np.size(self.mr['var list']):
            if self.mr['o'] == self.mr['# omit'] - 1 and self.mr['h'] == 0:
                for obj in [self, self.mws[0], self.mws[1]]:
                    obj.image_handler.reset_arrays() # remove omitted files
            if self.mr['o'] < self.mr['# omit']: # don't process, just copy
                for obj in [self, self.mws[0], self.mws[1]]:
                    obj.mr['o'] += 1 # increment counter
                self.recent_label.setText('Just processed image '
                    + self.mws[1].image_handler.files[
                            self.mws[1].image_handler.im_num-1])
            elif self.mr['h'] < self.mr['# hist']: # add to histogram
                t2 = self.get_histogram() # update the histogram
                # display the name of the most recent file
                self.recent_label.setText('Just processed image '
                        + self.mws[1].image_handler.files[
                            self.mws[1].image_handler.im_num-1])
                self.plot_current_hist(self.image_handler.hist_and_thresh) 
                self.plot_time = time.time() - t2
                for obj in [self, self.mws[0], self.mws[1]]:
                    obj.mr['h'] += 1 # increment counter

            if self.mr['o'] == self.mr['# omit'] and self.mr['h'] == self.mr['# hist']:
                for obj in [self.mws[1], self.mws[0], self]:
                    obj.mr['o'], obj.mr['h'] = 0, 0 # reset counters
                    obj.var_edit.setText(str(obj.mr['var list'][obj.mr['v']])) # set user variable
                    self.get_histogram()    # update the survival histogram
                    success = obj.update_fit()       # get best fit
                    if not success:                  # if fit fails, use peak search
                        obj.update_stats()
                        print(
                            '\nWarning: multi-run fit failed at ' +
                            obj.mr['prefix'] + '_' + str(obj.mr['v']) + '.csv')
                    obj.save_hist_data(
                        save_file_name=os.path.join(
                            obj.multirun_save_dir.text(), obj.name+obj.mr['prefix']) 
                            + '_' + str(obj.mr['v']) + '.csv', 
                        confirm=False)# save histogram
                    obj.mr['v'] += 1 # increment counter
                for obj in [self.mws[1], self.mws[0], self]:
                    obj.image_handler.reset_arrays() # clear histogram once data processing is done
                
        if self.mr['v'] == np.size(self.mr['var list']):
            for obj in [self.mws[1], self.mws[0], self]:
                obj.save_varplot(
                    save_file_name=os.path.join(
                        obj.multirun_save_dir.text(), obj.name+obj.mr['prefix']) 
                            + '.dat', 
                    confirm=False)# save measure file
                # reconnect previous signals to dir_watcher
                obj.multirun_switch.setChecked(False) # reset multi-run button
                obj.multirun_switch.setText('Start')  # reset multi-run button text
                obj.set_bins_reim() # reconnects dir_watcher with given histogram binning settings
                obj.mr['o'], obj.mr['h'], obj.mr['v'] = 0, 0, 0 # reset counters
                obj.mr['measure'] += 1 # completed a measure successfully
                obj.mr['prefix'] = str(obj.mr['measure']) # suggest new measure as file prefix
                obj.measure_edit.setText(obj.mr['prefix'])

        for obj in [self, self.mws[0], self.mws[1]]:
            obj.multirun_progress.setText( # update progress label
                'User variable: %s, omit %s of %s files, %s of %s histogram files, %.3g%% complete'%(
                    obj.mr['var list'][obj.mr['v']], obj.mr['o'], obj.mr['# omit'],
                    obj.mr['h'], obj.mr['# hist'], 100 * ((obj.mr['# omit'] + obj.mr['# hist']) * 
                    obj.mr['v'] + obj.mr['o'] + obj.mr['h']) / (obj.mr['# omit'] + obj.mr['# hist']) / 
                    np.size(obj.mr['var list'])))

    #### #### save and load data functions #### ####

    # def load_image(self): # display both images

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
            for obj in [self, self.mws[0], self.mws[1]]:
                obj.image_handler.set_pic_size(file_name) # sets image handler's pic size
                obj.pic_size_edit.setText(str(self.image_handler.pic_size)) # update loaded value
                obj.pic_size_label.setText(str(self.image_handler.pic_size)) # update loaded value
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
            for obj in [self, self.mws[0], self.mws[1]]:
                obj.image_handler.set_pic_size(file_name) # sets image handler's pic size
                obj.pic_size_edit.setText(str(self.image_handler.pic_size)) # update loaded value
                obj.pic_size_label.setText(str(self.image_handler.pic_size)) # update loaded value
                # get the position of the max count
                obj.image_handler.set_roi(im_name=file_name) # sets xc and yc
                obj.roi_x_edit.setText(str(self.image_handler.xc)) # update loaded value
                obj.roi_y_edit.setText(str(self.image_handler.yc)) 
                obj.roi_l_edit.setText(str(self.image_handler.roi_size))
                obj.xc_label.setText(str(self.image_handler.xc))
                obj.yc_label.setText(str(self.image_handler.yc))
                obj.l_label.setText(str(self.image_handler.roi_size))
                obj.roi.setPos(self.image_handler.xc - self.image_handler.roi_size//2, 
                obj.image_handler.yc - self.image_handler.roi_size//2) # set ROI in image display
                obj.roi.setSize(self.image_handler.roi_size, self.image_handler.roi_size)
        except OSError:
            pass # user cancelled - file not found

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
            for obj in [self, self.mws[0], self.mws[1]]:
                obj.save_hist_data()  # prompt user for file name then save
                obj.image_handler.reset_arrays() # get rid of old data
                obj.hist_canvas.clear() # remove old histogram from display
        elif reply == QMessageBox.No:
            for obj in [self, self.mws[0], self.mws[1]]:
                obj.image_handler.reset_arrays() # get rid of old data
                obj.hist_canvas.clear() # remove old histogram from display

    def load_from_csv(self, trigger=None):
        """Prompt the user to select a csv file to load histogram data from.
        It must have the specific layout that the image_handler saves in.
        Since the master calculates the histogram from data in mws, 
        these must be updated appropriately"""
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
                for obj in [self, self.mws[0], self.mws[1]]:
                    obj.image_handler.load_from_csv(file_name)
                if self.image_handler.counts:
                    # make fake data for mws[0] so that all files in mws[1] are included
                    self.mws[0].image_handler.counts[:self.image_handler.im_num] = np.zeros(
                        self.image_handler.im_num) + max(self.image_handler.counts)
                    self.mws[0].image_handler.atom = np.ones(self.image_handler.im_num)
                self.update_stats()
            except OSError:
                pass # user cancelled - file not found

    #### #### user input functions #### ####

    def set_user_var(self, text=''):
        """When the user finishes editing the var_edit line edit, update the displayed 
        user variable and assign it in the temp_vals of the histo_handler"""
        self.histo_handler.temp_vals['User variable'] = self.var_edit.text()
        self.stat_labels['User variable'].setText(self.var_edit.text())
        for obj in [self.mws[0], self.mws[1]]: # copy across to the SAIA instances
            obj.var_edit.setText(self.var_edit.text())
            obj.set_user_var()

    def pic_size_text_edit(self, text):
        """Update the specified size of an image in pixels when the user 
        edits the text in the line edit widget"""
        if text:
            self.image_handler.pic_size = int(text)
            self.pic_size_label.setText(str(self.image_handler.pic_size))
            for obj in [self.mws[0], self.mws[1]]:
                obj.pic_size_edit.setText(text)
            
    def CCD_stat_edit(self):
        """Update the values used for the EMCCD bias offset and readout noise"""
        if self.bias_offset_edit.text(): # check the label isn't empty
            for obj in [self, self.mws[0], self.mws[1]]: # copy across to the SAIA instances
                obj.bias = float(self.bias_offset_edit.text())
                obj.bias_offset_edit.setText(str(obj.bias))
        if self.read_noise_edit.text():
            for obj in [self, self.mws[0], self.mws[1]]: 
                obj.Nr = float(self.read_noise_edit.text())
                obj.read_noise_edit.setText(str(obj.Nr))

    def add_var_to_multirun(self):
        """When the user hits enter or the 'Add to list' button, add the 
        text from the entry edit to the list of user variables that will 
        be used for the multi-run. For speed, you can enter a range in 
        the form start,stop,step,repeat. If the multi-run has already
        started, do nothing."""
        if not self.multirun_switch.isChecked():
            new_var = list(map(float, [v for v in self.entry_edit.text().split(',') if v]))
            for obj in [self, self.mws[0], self.mws[1]]:
                if np.size(new_var) == 1: # just entered a single variable
                    obj.mr['var list'].append(new_var[0])
                    # empty the text edit so that it's quicker to enter a new variable
                    obj.entry_edit.setText('') 

                elif np.size(new_var) == 3: # range, with no repeats
                    obj.mr['var list'] += list(np.arange(new_var[0], new_var[1], new_var[2]))
                elif np.size(new_var) == 4: # range, with repeats
                    obj.mr['var list'] += list(np.arange(new_var[0], new_var[1],
                                                new_var[2]))*int(new_var[3])
                # display the whole list
                obj.multirun_vars.setText(','.join(list(map(str, obj.mr['var list']))))

    def clear_multirun_vars(self):
        """Reset the list of user variables to be used in the multi-run.
        If the multi-run is already running, don't do anything"""
        if not self.multirun_switch.isChecked():
            for obj in [self, self.mws[0], self.mws[1]]:
                obj.mr['var list'] = []
                obj.multirun_vars.setText('')

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
        for obj in [self, self.mws[0], self.mws[1]]:
            obj.image_handler.set_roi(dimensions=list(map(int, [xc, yc, l])))
            obj.xc_label.setText('ROI x_c = '+str(xc)) 
            obj.yc_label.setText('ROI y_c = '+str(yc))
            obj.l_label.setText('ROI size = '+str(l))
            # note: setting the origin as top left because image is inverted
            obj.roi.setPos(xc - l//2, yc - l//2)
            obj.roi.setSize(l, l)

    def check_reset(self):
        """Ask the user if they would like to reset the current data stored
        in the histograms. This resets all of the histograms in one go."""
        reply = QMessageBox.question(self, 'Confirm Data Replacement',
            "Do you want to discard all of the current histograms?", 
            QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel, QMessageBox.Cancel)
        if reply == QMessageBox.Cancel:
            return 0
        elif reply == QMessageBox.Yes:
            for obj in [self, self.mws[0], self.mws[1]]:
                obj.image_handler.reset_arrays() # gets rid of old data
        return 1

    def choose_multirun_dir(self):
        """Allow the user to choose the directory where the histogram .csv
        files and the measure .dat file will be saved as part of the multi-run"""
        default_path = self.get_default_path()
        try:
            dir_path = QFileDialog.getExistingDirectory(self, "Select Directory", default_path)
            for obj in [self, self.mws[0], self.mws[1]]:
                obj.multirun_save_dir.setText(dir_path)
        except OSError:
            pass # user cancelled - file not found

    #### #### toggle functions #### #### 

    def swap_reim_signal(self):
        """Disconnect the image_handler process signal from the event
        and (re)connect the update plot. The master will trigger on events 
        from mws[1]. This function must not override 
        main_window.swap_signals() otherwise there will be compatability 
        issues."""
        self.mws[1].swap_signals() # disconnects then reconnects mws[1] slots
        if self.thresh_toggle.isChecked():
            self.mws[1].event_im.connect(self.get_histogram)
            self.mws[1].event_im.connect(self.update_plot_only)
        elif not self.thresh_toggle.isChecked():
            self.mws[1].event_im.connect(self.get_histogram)
            self.mws[1].event_im.connect(self.update_plot)

    def set_bins_reim(self, action=None):
        """Check which of the bin action menu bar options is checked.
        If the toggle is Automatic, use automatic histogram binning.
        If the toggle is Manual, read in values from the line edit 
        widgets.
        If the toggle is No Display, disconnect the dir watcher new event 
        signal from the plot update. Still processes files but doesn't show 
        on histogram.
        If the toggle is No Update, disconnect the dir watcher new event 
        signal from the image handler entirely. Files are copied but not 
        processed for the histogram.
        This function must not override main_window.set_bins() otherwise
        there will be compatability issues."""
        if not self.multirun_switch.isChecked(): # don't interrupt multirun
            if self.bin_actions[1].isChecked(): # manual
                for obj in [self.mws[0], self.mws[1]]: # copy across to the SAIA instances
                    obj.swap_signals() # won't do anything if dir_watcher isn't running
                    obj.bins_text_edit('reset') # also updates threshold unless user sets it
                self.swap_reim_signal()
                self.bins_text_edit('reset')

            elif self.bin_actions[0].isChecked(): # automatic
                for obj in [self.mws[0], self.mws[1], self]:
                    if obj == self:
                        obj.swap_reim_signal()
                    else: # disconnect image handler, reconnect plot
                        obj.swap_signals()  
                    obj.image_handler.bin_array = []
                    if obj.thresh_toggle.isChecked():
                        obj.plot_current_hist(obj.image_handler.histogram)
                    else:
                        obj.plot_current_hist(obj.image_handler.hist_and_thresh)
            elif self.bin_actions[2].isChecked() or self.bin_actions[3].isChecked(): # No Display or No Update
                for obj in [self.mws[0], self.mws[1]]:
                    try: # disconnect all slots
                        obj.event_im.disconnect()
                    except Exception: pass # if it's already been disconnected 
                    # set the text of the most recent file
                    obj.event_im.connect(obj.show_recent_file)
                    # just process the image
                    if obj.bin_actions[2].isChecked():
                        obj.event_im.connect(obj.image_handler.process)
                        if obj is self.mws[1]:
                            obj.event_im.connect(self.get_histogram)
    
    def set_thresh(self, toggle):
        """If the toggle is true, the user supplies the threshold value and it is
        kept constant using the image_handler.histogram() function. Otherwise,
        update the threshold with image_handler.hist_and_thresh()"""
        for obj in [self.mws[0], self.mws[1]]:
            obj.thresh_toggle.setChecked(toggle)
            obj.set_thresh(toggle)

    def multirun_go(self, toggle):
        """Initiate the multi-run: omit N files, save a histogram of M files, and
        repeat for the user variables in the list. If the button is pressed during
        the multi-run, save the current histogram, save the measure file, then
        return to normal operation of the dir_watcher"""
        if toggle and np.size(self.mr['var list']) > 0:
            self.mws[0].measure_edit.setText(self.measure_edit.text() + '_0')
            self.mws[1].measure_edit.setText(self.measure_edit.text() + '_1')
            self.check_reset() # clear histograms
            for obj in [self, self.mws[0], self.mws[1]]:
                try: # disconnect all slots
                    obj.event_im.disconnect() 
                except Exception: pass # already disconnected
                if obj is not self:
                    obj.event_im.connect(obj.update_plot)
                obj.plot_current_hist(obj.image_handler.hist_and_thresh)
                if obj.multirun_save_dir.text() == '':
                    obj.choose_multirun_dir() # directory to save histogram csv files to
                obj.omit_edit.setText(self.omit_edit.text())
                obj.mr['# omit'] = int(self.omit_edit.text()) # number of files to omit
                obj.multirun_hist_size.setText(self.multirun_hist_size.text())
                obj.mr['# hist'] = int(self.multirun_hist_size.text()) # number of files in histogram                
                obj.mr['o'], obj.mr['h'], obj.mr['v'] = 0, 0, 0 # counters for different stages of multirun
                obj.mr['prefix'] = obj.measure_edit.text() # prefix for histogram files 
                obj.multirun_switch.setText('Abort')
                obj.multirun_switch.setChecked(True) # keep consistentency
                obj.clear_varplot() # clear varplot so that it only has multirun data
                obj.multirun_progress.setText(       # update progress label
                    'User variable: %s, omit %s of %s files, %s of %s histogram files, 0%% complete'%(
                        self.mr['var list'][self.mr['v']], self.mr['o'], self.mr['# omit'],
                        self.mr['h'], self.mr['# hist']))
                
            # connect self to mws[1] signal so that it responds to images coming in
            self.mws[1].event_im.connect(self.multirun_step)
        else: # cancel the multi-run
            for obj in [self, self.mws[0], self.mws[1]]:
                obj.set_bins_reim() # reconnect the dir_watcher
                obj.multirun_switch.setText('Start') # reset button text
                obj.multirun_switch.setChecked(False)# keep consistentency
                if np.size(self.mr['var list']) > 0:
                    obj.multirun_progress.setText(       # update progress label
                        'Stopped at - User variable: %s, omit %s of %s files, %s of %s histogram files, %.3g%% complete'%(
                            self.mr['var list'][self.mr['v']], self.mr['o'], self.mr['# omit'],
                            self.mr['h'], self.mr['# hist'], 100 * ((self.mr['# omit'] + self.mr['# hist']) * 
                            self.mr['v'] + self.mr['o'] + self.mr['h']) / (self.mr['# omit'] + self.mr['# hist']) / 
                            np.size(self.mr['var list'])))

    def multirun_resume(self):
        """If the button is clicked, resume the multi-run where it was left off.
        If the multirun is already running, do nothing."""
        if not self.multirun_switch.isChecked(): 
            for obj in [self.mws[0], self.mws[1]]:
                obj.multirun_switch.setChecked(True)
                obj.multirun_switch.setText('Abort')
                try: # disconnect all slots
                    obj.event_im.disconnect() 
                except Exception: pass # already disconnected
                obj.event_im.connect(obj.update_plot)
            self.mws[1].event_im.connect(self.multirun_step)
            self.multirun_switch.setChecked(True)
            self.multirun_switch.setText('Abort')

#### #### UI management functions #### #### 

    def show_windows(self):
        """Display the instances of SAIA, filling the screen"""
        w = 1600
        h = 900
        o = 50
        self.setGeometry(10, o, 10+w/3, h+o)
        self.mws[0].setGeometry(10+w/3, o, 10+w/3, h+o)
        self.mws[0].show()
        self.mws[1].setGeometry(10+2*w/3, o, 10+w/3, h+o)
        self.mws[1].show()

    def closeAndContinue(self, event):
        """A close event for the SAIA instances that keeps the dir
        watcher active in the background"""
        event.accept()

    def closeEvent(self, event):
        """Close all active main windows"""
        for obj in [self.mws[0], self.mws[1]]:
            obj.close() # close the window
        event.accept() # close this main window
        
####    ####    ####    #### 

def run():
    """Initiate an app to run the program
    if running in Pylab/IPython then there may already be an app instance"""
    app = QApplication.instance()
    standalone = app is None # false if there is already an app instance
    if standalone: # if there isn't an instance, make one
        app = QApplication(sys.argv) 
        
    main_win = reim_window()
    main_win.show()
    if standalone: # if an app instance was made, execute it
        sys.exit(app.exec_()) # when the window is closed, the python code also stops

            
if __name__ == "__main__":
    # change directory to this file's location
    os.chdir(os.path.dirname(os.path.realpath(__file__)))
    run()