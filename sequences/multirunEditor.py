"""Single Atom Image Analysis (SAIA) Multirun Editor
Stefan Spence 26/02/19

 - Provide a visual representation for multirun values
 - Allow the user to quickly edit multirun values
 - Give the list of commands for DExTer to start a multirun
"""
import os
import sys
import time
import numpy as np
from collections import OrderedDict
from random import shuffle
try:
    from PyQt4.QtCore import pyqtSignal, QRegExp
    from PyQt4.QtGui import (QPushButton, QWidget, QLabel,
        QGridLayout, QLineEdit, QDoubleValidator, QIntValidator, 
        QComboBox, QListWidget, QTabWidget, QVBoxLayout, QInputDialog,
        QTableWidget, QTableWidgetItem, QScrollArea) 
except ImportError:
    from PyQt5.QtCore import pyqtSignal, QRegExp
    from PyQt5.QtGui import QDoubleValidator, QIntValidator
    from PyQt5.QtWidgets import (QVBoxLayout, QWidget, QComboBox,
        QLineEdit, QGridLayout, QPushButton, QListWidget, QListWidgetItem, 
        QScrollArea, QLabel, QTableWidget, QTableWidgetItem)
import logging
logger = logging.getLogger(__name__)
sys.path.append('..')
from mythread import remove_slot # for dis- and re-connecting slots

####    ####    ####    ####

class multirun_widget(QWidget):
    """Widget for editing multirun values.

    Keyword arguments:
    tr    -- a translate instance that contains the experimental sequence
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

    def __init__(self, tr, nrows=500, ncols=3, order='ascending'):
        super().__init__()
        self.tr = tr
        self.types = OrderedDict([('nrows',int), ('ncols',int), 
            ('order',str), ('nomit',int), ('measure',int), ('measure_prefix',str)])
        self.stats = OrderedDict([('nrows',nrows), ('ncols', ncols),
            ('order', order), ('nomit',0), ('measure',0), ('measure_prefix','0_')])
        self.init_UI()  # make the widgets

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
        
    def init_UI(self):
        """Create all of the widget objects required"""
        layout = QVBoxLayout()
        self.setLayout(layout)
        
        # place scroll bars if the contents of the window are too large
        scroll = QScrollArea(self)
        layout.addWidget(scroll)
        scroll_content = QWidget(scroll)
        scroll.setWidgetResizable(True)
        scroll.setFixedHeight(800)
        self.grid = QGridLayout()
        scroll_content.setLayout(self.grid)

        nrows = self.stats['nrows']
        ncols = self.stats['ncols']
        
        #### validators for user input ####
        double_validator = QDoubleValidator() # floats
        int_validator = QIntValidator()       # integers
        nat_validator = QIntValidator(1,999999)# natural numbers
        col_validator = QIntValidator(0,ncols-1) # for number of columns

        #### table dimensions and ordering ####
        # choose the number of rows = number of multirun steps
        _, self.rows_edit = self.make_label_edit('# Rows', self.grid, 
            position=[0,0, 1,1], default_text=str(nrows), 
            validator=int_validator)
        self.rows_edit.textChanged[str].connect(self.change_array_size)

        # choose the number of rows = number of multirun steps
        _, self.omit_edit = self.make_label_edit('# Omit', self.grid, 
            position=[0,2, 1,1], default_text='0', 
            validator=int_validator)
        self.omit_edit.textChanged[str].connect(self.change_array_size)

        # choose the number of columns = number of channels to change in one step
        _, self.cols_edit = self.make_label_edit('# Columns', self.grid, 
            position=[0,4, 1,1], default_text=str(ncols), 
            validator=int_validator)
        self.cols_edit.textChanged[str].connect(self.change_array_size)

        # choose the order
        self.order = QComboBox(self)
        self.order.addItems(['ascending', 'descending', 'random', 'coarse random', 'unsorted']) 
        self.grid.addWidget(self.order, 0,6, 1,4)

        #### create multirun list of values ####
        # metadata for the multirun list: which channels and timesteps
        self.chan_choices = OrderedDict()
        label = QLabel('Variable label', self)
        self.grid.addWidget(label, 1,0, 1,1)
        self.chan_choices['Variable label'] = QLineEdit(self)
        self.grid.addWidget(self.chan_choices['Variable label'], 2,1, 1,3)

        labels = ['Type', 'Time step name', 'Analogue type', 'Analogue channel']
        options = [['Time step length', 'Analogue voltage', 'GPIB'], 
            [str(i)+': '+hc['Time step name'] for i, hc in enumerate(self.tr.seq_dic['Experimental sequence cluster in']['Sequence header top'])], 
            ['Fast analogues', 'Slow analogues'],
            self.get_anlg_chans('Fast')]
        widgets = [QComboBox, QListWidget]
        for i in range(0, len(labels)):
            self.chan_choices[labels[i]] = widgets[i%2]()
            if i%2:
                self.chan_choices[labels[i]].setSelectionMode(3)
            self.chan_choices[labels[i]].addItems(options[i])
            self.grid.addWidget(self.chan_choices[labels[i]], 1,i+5, 3,1+i//3)
        self.chan_choices['Type'].currentTextChanged[str].connect(self.change_mr_type)
        self.chan_choices['Analogue type'].currentTextChanged[str].connect(self.change_mr_anlg_type)
        self.chan_choices['Analogue channel'].setEnabled(False)

        # add a new list of multirun values to the array
        self.col_val_edit = []
        labels = ['column index', 'start', 'stop', 'step', 'repeats']
        validators = [col_validator, double_validator, double_validator, nat_validator, nat_validator]
        for i in range(0, len(labels)*2, 2):
            self.col_val_edit.append(self.make_label_edit(labels[i//2], self.grid, 
                position=[4,i, 1,1], default_text='1', 
                validator=validators[i//2])[1])

        # add the column to the multirun values array
        add_var_button = QPushButton('Add column', self)
        add_var_button.clicked.connect(self.add_column_to_array)
        add_var_button.resize(add_var_button.sizeHint())
        self.grid.addWidget(add_var_button, 5,0, 1,1)
        
        # clear the current list of user variables
        clear_vars_button = QPushButton('Clear', self)
        clear_vars_button.clicked.connect(self.reset_table)
        clear_vars_button.resize(clear_vars_button.sizeHint())
        self.grid.addWidget(clear_vars_button, 5,1, 1,2)

        # start/abort the multirun
        self.multirun_switch = QPushButton('Start multirun', self, checkable=True)
        self.multirun_switch.clicked[bool].connect(self.multirun_go)
        self.grid.addWidget(self.multirun_switch, 5,3, 1,2)
        # pause/restart the multirun
        self.multirun_pause = QPushButton('Resume', self)
        self.multirun_pause.clicked.connect(self.multirun_resume)
        self.grid.addWidget(self.multirun_pause, 5,5, 1,2)

        # display current progress
        self.multirun_progress = QLabel(
            'User variable: , omit 0 of 0 files, 0 of 100 histogram files, 0% complete')
        self.grid.addWidget(self.multirun_progress, 6,0, 1,12)

        # table stores multirun values:
        self.table = QTableWidget(nrows, ncols)
        self.reset_table()
        self.grid.addWidget(self.table, 7,0, 20, 12)
    
        scroll.setWidget(scroll_content)

        
    #### #### array editing functions #### #### 

    def reset_table(self):
        """Empty the table of all of its values."""
        self.table.setHorizontalHeaderLabels(list(map(str, range(self.table.columnCount()))))
        for i in range(self.table.rowCount()):
            for j in range(self.table.columnCount()):
                self.table.setItem(i, j, QTableWidgetItem())
                self.table.item(i, j).setText('')
    
    def change_array_size(self):
        """Update the size of the multirun array based on the number of rows
        and columns specified in the line edit."""
        self.stats['nrows'] = self.types['nrows'](self.rows_edit.text())
        self.table.setRowCount(self.stats['nrows'])
        self.stats['ncols'] = self.types['ncols'](self.cols_edit.text())
        self.table.setColumnCount(self.stats['ncols'])
        self.col_val_edit[0].setValidator(QIntValidator(0,self.stats['ncols']-1))
        self.reset_table()

    def add_column_to_array(self):
        """Make a list of values and add it to the given column 
        in the multirun values array. The list is 
        range(start, stop, step) repeated a set number of times.
        The list is ordered according to the ComboBox text."""
        if all([x.text() for x in self.col_val_edit]):
            col = int(self.col_val_edit[0].text())
            # make the list of values with a given order:
            vals = range(*map(int, [x.text() for x in self.col_val_edit[1:4]]))
            repeats = int(self.col_val_edit[4].text())
            if self.order.currentText() == 'descending':
                vals = reversed(vals)
            elif self.order.currentText() == 'coarse random':
                vals = list(vals)
                shuffle(vals)
            # make the full list:
            if self.order.currentText() == 'unsorted':
                vals = [v for i in range(repeats) for v in vals]
            else:
                vals = [v for v in vals for i in range(repeats)] 
            if self.order.currentText() == 'random':
                shuffle(vals)
            for i in range(self.table.rowCount()): # set vals in table cells
                self.table.item(i, col).setText(str(vals[i]))

    #### multirun channel selection ####

    def get_anlg_chans(self, speed):
        """Return a list of labels for the analogue channels.
        speed -- 'Fast' or 'Slow'"""
        return [ID+': '+name for ID, name in zip(
            *self.tr.seq_dic['Experimental sequence cluster in'][speed + ' analogue names'].values())]

    def change_mr_type(self, newtype):
        """Enable/Disable list boxes to reflect the multirun type:
        newtype[str] -- Time step length: only needs timesteps
                     -- Analogue voltage: also needs channels"""
        if newtype == 'Time step length':
            self.chan_choices['Analogue channel'].setEnabled(False)
        elif newtype == 'Analogue voltage':
            self.chan_choices['Analogue channel'].setEnabled(True)
            self.chan_choices['Analogue channel'].clear()
            self.chan_choices['Analogue channel'].addItems(
                self.get_anlg_chans(self.chan_choices['Analogue type'].currentText().split(' ')[0]))

    def change_mr_anlg_type(self, newtype):
        """Change the analogue channels listbox when fast/slow
        analogue channels are selected."""
        if self.chan_choices['Analogue channel'].isEnabled():
            self.chan_choices['Analogue channel'].clear()
            self.chan_choices['Analogue channel'].addItems(
                self.get_anlg_chans(self.chan_choices['Analogue type'].currentText().split(' ')[0]))

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
        self.table.selectRow(n)
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
