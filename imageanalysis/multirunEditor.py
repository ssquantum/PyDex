"""Single Atom Image Analysis (SAIA) Multirun Editor
Stefan Spence 26/02/19

 - Provide a visual representation for multirun values
 - Allow the user to quickly edit multirun values
 - Give the list of commands for DExTer to start a multirun
"""
import os
import sys
import numpy as np
from collections import OrderedDict
try:
    from PyQt4.QtCore import pyqtSignal, QRegExp
    from PyQt4.QtGui import (QPushButton, QWidget, QLabel,
        QGridLayout, QLineEdit, QDoubleValidator, QIntValidator, QComboBox, 
        QTabWidget, QVBoxLayout, QRegExpValidator, QInputDialog,
        QTableWidget, QTableWidgetItem, QScrollArea) 
except ImportError:
    from PyQt5.QtCore import pyqtSignal, QRegExp
    from PyQt5.QtGui import (QDoubleValidator, QIntValidator, 
       QRegExpValidator)
    from PyQt5.QtWidgets import (QVBoxLayout, QWidget,
       QComboBox,QLineEdit, QGridLayout, QPushButton, 
       QScrollArea, QLabel, QTableWidget, QTableWidgetItem)
import logging
logger = logging.getLogger(__name__)
from maingui import remove_slot # single atom image analysis

####    ####    ####    ####

class multirun_widget(QWidget):
    """Widget for editing multirun values.

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
        self.types = OrderedDict([('nrows',int), ('col_head',list), 
            ('order',str), ('nomit',int), ('measure',int), ('measure_prefix',str)])
        self.stats = OrderedDict([('nrows',nrows), ('col_head', [str(i) for i in range(ncols)]),
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
        ncols = len(self.stats['col_head'])
        
        # validators for user input
        # this regex needs work to disallow -1-1
        reg_exp = QRegExp(r'(-?[0-9]+(\.[0-9]+)?,?)+')
        comma_validator = QRegExpValidator(reg_exp) # floats and commas
        double_validator = QDoubleValidator() # floats
        int_validator = QIntValidator()       # integers

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
        self.grid.addWidget(self.order, 0,6, 1,1)

        # add a new list of multirun values to the array
        self.col_val_edit = []
        i = 0
        for label in ['column index', 'start', 'stop', 'step', 'repeats']:
            self.col_val_edit.append(self.make_label_edit(label, self.grid, 
                position=[1,i, 1,1], default_text='0', 
                validator=int_validator)[1])
            i += 2

        # line edit for user inputing column headings
        self.head_edit = QLineEdit(self)
        self.grid.addWidget(self.head_edit, 3,0, 1,3)
        self.head_edit.editingFinished.connect(self.set_col_head)
        self.head_edit.col = 0 # which column to edit
        self.head_edit.hide() # hide unless user double clicks

        # table stores multirun values:
        self.table = QTableWidget(nrows, ncols)
        # display column headings
        self.table.itemDoubleClicked.connect(self.open_head_edit)
        self.table.setHorizontalHeaderLabels(self.stats['col_head'])
        self.grid.addWidget(self.table, 4,0, nrows, ncols)

        # add the column to the multirun values array
        add_var_button = QPushButton('Add column', self)
        add_var_button.clicked.connect(self.add_column_to_array)
        add_var_button.resize(add_var_button.sizeHint())
        self.grid.addWidget(add_var_button, 1,i, 1,1)
        
        # clear the current list of user variables
        clear_vars_button = QPushButton('Clear list', self)
        clear_vars_button.clicked.connect(self.table.clearContents)
        clear_vars_button.resize(clear_vars_button.sizeHint())
        self.grid.addWidget(clear_vars_button, 1,i+1, 1,1)

        # start/abort the multirun
        self.multirun_switch = QPushButton('Start', self, checkable=True)
        self.multirun_switch.clicked[bool].connect(self.multirun_go)
        self.grid.addWidget(self.multirun_switch, 2,0, 1,1)
        # pause/restart the multirun
        self.multirun_pause = QPushButton('Resume', self)
        self.multirun_pause.clicked.connect(self.multirun_resume)
        self.grid.addWidget(self.multirun_pause, 2,1, 1,1)

        # display current progress
        self.multirun_progress = QLabel(
            'User variable: , omit 0 of 0 files, 0 of 100 histogram files, 0% complete')
        self.grid.addWidget(self.multirun_progress, 2,2, 1,3)
    

        scroll.setWidget(scroll_content)

        
    #### #### array editing functions #### #### 
    
    def change_array_size(self):
        """Update the size of the multirun array based on the number of rows
        and columns specified in the line edit."""
        self.stats['nrows'] = self.types['nrows'](self.rows_edit.text())
        self.table.setRowCount(self.stats['nrows'])
        newcol = int(self.cols_edit)
        self.table.setColumnCount(newcol)
        for i in range(len(self.stats['col_head'], newcol)): # add new columns
            self.stats['col_head'].append(str(i))
        if len(self.stats['col_head']) > newcol: # or remove columns if needed
            self.stats['col_head'] = self.stats['col_head'][:newcol]
        self.table.setHorizontalHeaderLabels(self.stats['col_head'])

    def set_col_head(self):
        """Take the text typed from the line edit and insert it into
        the appropriate column header, then hide the line edit"""
        self.stats['col_head'][self.head_edit.col] = self.head_edit.text()
        self.table.setHorizontalHeaderLabels(self.stats['col_head'])
        self.head_edit.hide()

    def open_head_edit(self):
        """When the user double clicks on a column, open the line edit
        so that they can input a new column header"""
        if self.sender().column() < len(self.stats['col_head']):
            self.head_edit.col = self.sender().column()
            self.head_edit.show()
        else: self.change_array_size()

    def add_column_to_array(self):
        pass

    #### multirun ####
    
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
