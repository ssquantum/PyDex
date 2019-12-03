"""Single Atom Image Analysis (SAIA) Multirun Editor
Stefan Spence 26/02/19

 - Provide a visual representation for multirun values
 - Allow the user to quickly edit multirun values
 - 
"""
import os
import sys
import numpy as np
from collections import OrderedDict
try:
    from PyQt4.QtCore import QThread, pyqtSignal, QEvent, QRegExp
    from PyQt4.QtGui import (QApplication, QPushButton, QWidget, QLabel, QAction,
            QGridLayout, QMainWindow, QMessageBox, QLineEdit, QIcon, QFileDialog,
            QDoubleValidator, QIntValidator, QComboBox, QMenu, QActionGroup, 
            QTabWidget, QVBoxLayout, QFont, QRegExpValidator, QInputDialog,
            QTableWidget, QTableWidgetItem) 
except ImportError:
    from PyQt5.QtCore import QThread, pyqtSignal, QEvent, QRegExp
    from PyQt5.QtGui import (QGridLayout, QMessageBox, QLineEdit, QIcon, 
            QFileDialog, QDoubleValidator, QIntValidator, QComboBox, QMenu, 
            QActionGroup, QVBoxLayout, QFont, QRegExpValidator)
    from PyQt5.QtWidgets import (QApplication, QPushButton,
        QAction, QMainWindow, QLabel, QTableWidget, QTableWidgetItem)
import logging
logger = logging.getLogger(__name__)
from maingui import main_window, remove_slot # single atom image analysis

def make_label_edit(self, label_text, layout, position=[0,0, 1,1],
            default_text='', validator=None):
        """Make a QLabel with an accompanying QLineEdit and add them to the 
        given layout with an input validator. The position argument should
        be [row number, column number, row width, column width]."""
        label = QLabel(label_text, self)
        layout.addWidget(label, *position)
        line_edit = QLineEdit(self)
        if np.size(position) == 4:
            position[1] += 1
        layout.addWidget(line_edit, *position)
        line_edit.setText(default_text) 
        line_edit.setValidator(validator)
        return label, line_edit

####    ####    ####    ####

# main GUI window contains all the widgets                
class multirun_window(QMainWindow):
    """Main GUI window for editing multirun values.

    Keyword arguments:
    nrows -- number of rows = number of multirun steps.
    ncols -- number of columns = number of channels to change in one step.
    order -- the order to produce the variables list in:
        ascending  - with repeats next to each other
        descending - with repeats next to each other
        random     - completely randomise the order
        coarse random - randomise order but repeats next to each other
        unsorted   - make an ascending list, then repeat the list
    """
    multirun_vals = pyqtSignal(np.ndarray) # the array of multirun values

    def __init__(self, nrows=1000, ncols=1, order='ascending'):
        super().__init__()
        self.types = OrderedDict([('nrows',int), ('col_head',str), 
                ('vals',np.ndarray), ('order',str), ('nomit',int),
                ('measure',int), ('measure_prefix',str)])
        self.stats = OrderedDict([('nrows',nrows), ('col_head', ','.join(map(str, range(ncols)))),
                ('vals',np.zeros((nrows, ncols))), ('order', order), 
                ('nomit',0), ('measure',0), ('measure_prefix','0_')])
        self.init_UI()  # make the widgets
        
    def init_UI(self):
        """Create all of the widget objects required"""
        self.centre_widget = QWidget()
        self.centre_widget.layout = QVBoxLayout()
        self.centre_widget.setLayout(self.centre_widget.layout)
        self.setCentralWidget(self.centre_widget)
        
        # validators for user input
        # this regex needs work to disallow -1-1
        reg_exp = QRegExp(r'(-?[0-9]+(\.[0-9]+)?,?)+')
        comma_validator = QRegExpValidator(reg_exp) # floats and commas
        double_validator = QDoubleValidator() # floats
        int_validator = QIntValidator()       # integers

        grid_layout = QGridLayout()
        
        # choose the number of rows = number of multirun steps
        _, self.rows_edit = make_label_edit('# Rows', grid_layout, 
            position=[0,0, 1,1], default_text=str(self.stats['nrows']), 
            validator=int_validator)
        self.rows_edit.textChanged[str].connect(self.change_array_size)

        # choose the number of rows = number of multirun steps
        _, self.rows_edit = make_label_edit('# Omit', grid_layout, 
            position=[0,2, 1,1], default_text=str(self.stats['nrows']), 
            validator=int_validator)
        self.rows_edit.textChanged[str].connect(self.change_array_size)

        # choose the number of columns = number of channels to change in one step
        _, self.cols_edit = make_label_edit('# Columns', grid_layout, 
            position=[0,4, 1,1], default_text=str(len(self.stats['col_head'].split(','))), 
            validator=int_validator)
        self.cols_edit.textChanged[str].connect(self.change_array_size)

        # choose the order
        self.order = QComboBox(self)
        self.order.addItems(['ascending', 'descending', 'random', 'coarse random', 'unsorted']) 
        grid_layout.addWidget(self.order, 0,6, 1,1)

        # edit 
        self.col_edit = []
        i = 0
        for label in ['column index', 'start', 'stop', 'step', 'repeats']:
            self.col_edit.append(make_label_edit(label, grid_layout, 
                position=[1,i, 1,1], default_text='1', 
                validator=int_validator)[1])
            i += 2

        #### tab for multi-run settings ####
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
        multirun_grid.addWidget(self.multirun_progress, 7,0, 1,3)

        #### choose main window position and dimensions: (xpos,ypos,width,height)
        self.setGeometry(100, 100, 850, 700)
        self.setWindowTitle('- Single Atom Image Analyser Settings -')
        self.setWindowIcon(QIcon('docs/tempicon.png'))
        
    #### #### user input functions #### #### 
            
    def pic_size_text_edit(self, text):
        """Update the specified size of an image in pixels when the user 
        edits the text in the line edit widget"""
        if text: # can't convert '' to int
            self.stats['pic_size'] = int(text)
            self.pic_size_label.setText(str(self.stats['pic_size']))

    def CCD_stat_edit(self):
        """Update the values used for the EMCCD bias offset and readout noise"""
        if self.bias_offset_edit.text(): # check the label isn't empty
            self.stats['bias'] = float(self.bias_offset_edit.text())
        if self.read_noise_edit.text():
            self.stats['Nr'] = float(self.read_noise_edit.text())

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
            # display the list
            vlist = ','.join(list(map(str, self.mr['var list'])))
            vlist = vlist[:20] + ' ...' if len(vlist)>20 else vlist
            self.multirun_vars.setText(vlist)

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
            or xc + l//2 > self.stats['pic_size'] 
            or yc + l//2 > self.stats['pic_size']):
            l = 2*min([xc, yc])  # can't have the boundary go off the edge
        if int(l) == 0:
            l = 1 # can't have zero width
        self.stats['xc'], self.stats['yc'], self.stats['roi_size'] = map(int, [xc, yc, l]))
            
    #### #### toggle functions #### #### 

    def set_all_windows(self, action=None):
        """Find which of the binning options and fit methods is checked 
        and apply this to all ofthe image analysis windows."""
        if not self.multirun_switch.isChecked(): # don't interrupt multirun
            for mw in self.mw[:self._m] + self.rw[:len(self.rw_inds)]:
                for i in range(len(self.bin_actions)):
                    mw.bin_actions[i].setChecked(self.bin_actions[i].isChecked())
                mw.set_bins()
                for i in range(len(self.fit_options)):
                    mw.fit_options[i].setChecked(self.fit_options[i].isChecked())

    #### multirun ####

    def multirun_go(self, toggle):
        """Initiate the multi-run: omit N files, save a histogram of M files, and
        repeat for the user variables in the list. If the button is pressed during
        the multi-run, save the current histogram, save the measure file, then
        return to normal operation"""
        if toggle and np.size(self.mr['var list']) > 0:
            self.check_reset()
            # self.plot_current_hist(self.image_handler.histogram)
            remove_slot(self.event_im, self.update_plot, False)
            remove_slot(self.event_im, self.update_plot_only, False)
            remove_slot(self.event_im, self.image_handler.process, False)
            if self.multirun_save_dir.text() == '':
                self.choose_multirun_dir()
            remove_slot(self.event_im, self.multirun_step, True)
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
            self.set_bins() # reconnect the signal
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
            remove_slot(self.event_im, self.multirun_step, True)

    def multirun_step(self, event_im):
        """Receive event paths emitted from the system event handler signal
        for the first '# omit' events, only save the files
        then for '# hist' events, add files to a histogram,
        save the histogram 
        repeat this for the user variables in the multi-run list,
        then return to normal operation as set by the histogram binning"""
        if self.mr['v'] < np.size(self.mr['var list']):
            if self.mr['o'] < self.mr['# omit']: # don't process, just copy
                # self.recent_label.setText('Just omitted image '
                #     + self.image_handler.stats['File ID'][-1])
                self.mr['o'] += 1 # increment counter
            elif self.mr['h'] < self.mr['# hist']: # add to histogram
                # add the count to the histogram
                t1 = time.time()
                # self.image_handler.process(event_im)
                t2 = time.time()
                self.int_time = t2 - t1
                # display the name of the most recent file
                # self.recent_label.setText('Just processed image '
                #             + str(self.image_handler.fid))
                # self.plot_current_hist(self.image_handler.hist_and_thresh) # update the displayed plot
                self.plot_time = time.time() - t2
                self.mr['h'] += 1 # increment counter

            if self.mr['o'] == self.mr['# omit'] and self.mr['h'] == self.mr['# hist']:
                self.mr['o'], self.mr['h'] = 0, 0 # reset counters
                uv = str(self.mr['var list'][self.mr['v']]) # set user variable
                self.var_edit.setText(uv) # also updates histo_handler temp vals
                self.bins_text_edit(text='reset') # set histogram bins 
                success = self.update_fit(fit_method='check actions') # get best fit
                if not success:                   # if fit fails, use peak search
                    # self.histo_handler.process(self.image_handler, uv, 
                    #     fix_thresh=self.thresh_toggle.isChecked(), method='quick')
                    print('\nWarning: multi-run fit failed at ' +
                        self.mr['prefix'] + '_' + str(self.mr['v']) + '.csv')
                self.save_hist_data(
                    save_file_name=os.path.join(
                        self.multirun_save_dir.text(), self.name + self.mr['prefix']) 
                            + '_' + str(self.mr['v']) + '.csv', 
                    confirm=False)# save histogram
                # self.image_handler.reset_arrays() # clear histogram
                self.mr['v'] += 1 # increment counter
            
        if self.mr['v'] == np.size(self.mr['var list']):
            self.save_varplot(
                save_file_name=os.path.join(
                    self.multirun_save_dir.text(), self.name + self.mr['prefix']) 
                        + '.dat', 
                confirm=False)# save measure file
            # reconnect previous signals
            self.multirun_switch.setChecked(False) # reset multi-run button
            self.multirun_switch.setText('Start')  # reset multi-run button text
            self.set_bins() # reconnects signal with given histogram binning settings
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

    def load_settings(self, fname='default.config'):
        """Load the default settings from a config file"""
        with open(fname, 'r') as f:
            for line in f:
                key, val = line.split('=') # there should only be one = per line
                self.stats[key] = self.types[key](val)
    
    def save_settings(self, fname='default.config'):
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
            im_vals = np.genfromtxt(im_name, delimiter=' ')
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
            "Do you want to discard the current data?", 
            QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel, QMessageBox.Cancel)
        if reply == QMessageBox.Cancel:
            return 0
        elif reply == QMessageBox.Yes:
            # self.image_handler.reset_arrays() # gets rid of old data
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
        for i in range(self._m):
            self.mw[i].setGeometry(40+i//self._m*800, 100, 850, 700)
            self.mw[i].show()
        for i in range(len(self.rw_inds)):
            self.rw[i].setGeometry(45+i//len(self.rw_inds)*800, 200, 850, 700)
            self.rw[i].show()

    def reset_analyses(self):
        """Remake the analyses instances for SAIA and re-image"""
        for mw in self.mw + self.rw:
            mw.hard_reset() # wipes clean the data
            mw.close() # closes the display
            
        m = int(self.m_edit.text())
        if m != self._m: # make sure there are the right numer of main_window instances
            if m > self._m:
                for i in range(self._m, m)
                    self.mw.append(main_window(results_path, im_store_path, str(i)))
            self._m = m
        for mw in self.mw:
            mw.swap_signals() # reconnect signals

        rinds = self.reim_edit.text().split(';') # indices of SAIA instances used for re-imaging
        for i in range(len(rinds)): # check the list input from the user has the right syntax
            try: 
                j, k = map(int, rinds[i].split(','))
                if j >= self._m or k >= self._m:
                    rind = rinds.pop(i)
                    logger.warning('Invalid histogram indices for re-imaging: '+rind)
            except ValueError as e:
                rind = rinds.pop(i)
                logger.error('Invalid syntax for re-imaging histogram indices: '+rind+'\n'+str(e))    
            except IndexError:
                pass # since we're popping elements from the list its length shortens
        self.rw_inds = rinds
        
        for i in range(min(len(self.rw_inds), len(self.rw))): # update current re-image instances
            j, k = map(int, self.rw_inds[i].split(','))
            self.rw[i].ih1 = self.mw[j].image_handler
            self.rw[i].ih2 = self.mw[k].image_handler
        for i in range(len(self.rw), len(self.rw_inds)): # add new re-image instances as required
            j, k = map(int, self.rw_inds[i].split(','))
            self.rw.append([reim_window([self.mw[j].image_handler, self.mw[k].image_handler],
                        results_path, im_store_path, str(i)))
            
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
        
    main_win = main_window()
    main_win.show()
    if standalone: # if an app instance was made, execute it
        sys.exit(app.exec_()) # when the window is closed, the python code also stops
            
if __name__ == "__main__":
    # change directory to this file's location
    os.chdir(os.path.dirname(os.path.realpath(__file__))) 
    run()