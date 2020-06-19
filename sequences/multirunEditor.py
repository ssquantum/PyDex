"""PyDex Multirun Editor
Stefan Spence 26/02/19

 - Provide a visual representation for multirun values
 - Allow the user to quickly edit multirun values
 - Give the list of commands for DExTer to start a multirun
"""
import os
import sys
import time
import copy
import numpy as np
from collections import OrderedDict
from random import shuffle, randint
try:
    from PyQt4.QtCore import pyqtSignal, QItemSelectionModel
    from PyQt4.QtGui import (QPushButton, QWidget, QLabel,
        QGridLayout, QLineEdit, QDoubleValidator, QIntValidator, 
        QComboBox, QListWidget, QTabWidget, QVBoxLayout, QInputDialog,
        QTableWidget, QTableWidgetItem, QScrollArea, QMessageBox,
        QFileDialog) 
except ImportError:
    from PyQt5.QtCore import pyqtSignal, QItemSelectionModel
    from PyQt5.QtGui import QDoubleValidator, QIntValidator
    from PyQt5.QtWidgets import (QVBoxLayout, QWidget, QComboBox,
        QLineEdit, QGridLayout, QPushButton, QListWidget, QListWidgetItem, 
        QScrollArea, QLabel, QTableWidget, QTableWidgetItem, QMessageBox,
        QFileDialog)
import logging
logger = logging.getLogger(__name__)
sys.path.append('.')
sys.path.append('..')
from mythread import remove_slot # for dis- and re-connecting slots
from strtypes import strlist, intstrlist, listlist
from translator import translate

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
    progress = pyqtSignal(str) # string detailing the progress of the multirun

    def __init__(self, tr, nrows=10, ncols=3, order='ascending'):
        super().__init__()
        self.tr = tr # translator for the current sequence
        self.mrtr = tr.copy() # translator for multirun sequence
        self.msglist = [] # list of multirun sequences as XML string
        self.ind = 0 # index for how far through the multirun we are
        self.nrows = nrows
        self.ncols = ncols
        self.types = OrderedDict([('measure',int), ('measure_prefix',str),
            ('1st hist ID', int), ('Variable label', str), 
            ('Order', str), ('Type', strlist), 
            ('Analogue type', strlist), ('Time step name', listlist), 
            ('Analogue channel', listlist), ('runs included', listlist),
            ('Last time step run', str), ('Last time step end', str),
            ('# omitted', int), ('# in hist', int)])
        self.ui_param = OrderedDict([('measure',0), ('measure_prefix','Measure0'),
            ('1st hist ID', 0), ('Variable label', ''), 
            ('Order', order), ('Type', ['Time step length']*ncols), 
            ('Analogue type', ['Fast analogue']*ncols), ('Time step name', [[]]*ncols), 
            ('Analogue channel', [[]]*ncols), ('runs included', [[] for i in range(nrows)]),
            ('Last time step run', r'C:\Users\lab\Desktop\DExTer 1.4\Last Timesteps\feb2020_940and812.evt'), 
            ('Last time step end', r'C:\Users\lab\Desktop\DExTer 1.4\Last Timesteps\feb2020_940and812.evt'),
            ('# omitted', 0), ('# in hist', 100)])
        self.mr_param = copy.deepcopy(self.ui_param) # parameters used for current multirun
        self.mr_vals  = [] # multirun values for the current multirun
        self.mr_queue = [] # list of parameters, sequences, and values to queue up for future multiruns
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

        #### validators for user input ####
        double_validator = QDoubleValidator() # floats
        int_validator = QIntValidator(0,10000000) # positive integers
        msr_validator = QIntValidator(-1,1000000) # integers >= -1
        nat_validator = QIntValidator(1,10000000) # natural numbers
        col_validator = QIntValidator(1,self.ncols-1) # for number of columns

        #### table dimensions and ordering ####
        # choose the number of rows = number of multirun steps
        labels = ['# Omit', '# in Histogram', '# Columns', '# Rows']
        default = ['0', '100', str(self.ncols), str(self.nrows)]
        vldtr = [int_validator, nat_validator, nat_validator, nat_validator]
        self.omit_edit, self.nhist_edit, self.cols_edit, self.rows_edit = [
            self.make_label_edit(labels[i], self.grid, [0,2*i, 1,1],
                default[i], vldtr[i])[1] for i in range(4)]
        self.cols_edit.textChanged[str].connect(self.change_array_size)
        self.rows_edit.textChanged[str].connect(self.change_array_size)
        self.omit_edit.editingFinished.connect(self.update_repeats)
        self.nhist_edit.editingFinished.connect(self.update_repeats)

        # choose the order
        self.order_edit = QComboBox(self)
        self.order_edit.addItems(['ascending', 'descending', 'random', 'coarse random', 'unsorted']) 
        self.grid.addWidget(self.order_edit, 0,8, 1,1)

        #### create multirun list of values ####
        # metadata for the multirun list: which channels and timesteps
        self.measures = OrderedDict()
        labels = ['Variable label', 'measure', 'measure_prefix', '1st hist ID']
        defaults = ['Variable 0', '0', 'Measure0', '0']
        for i in range(len(labels)):
            label = QLabel(labels[i], self)
            self.grid.addWidget(label, i+1,0, 1,1)
            self.measures[labels[i]] = QLineEdit(defaults[i], self)
            self.measures[labels[i]].textChanged.connect(self.update_all_stats)
            self.grid.addWidget(self.measures[labels[i]], i+1,1, 1,3)
        self.measures['measure'].setValidator(int_validator)
        self.measures['1st hist ID'].setValidator(msr_validator)
        label.setText('1st ID (-1 to append)') # change label

        self.chan_choices = OrderedDict()
        labels = ['Type', 'Time step name', 'Analogue type', 'Analogue channel']
        sht = self.tr.seq_dic['Experimental sequence cluster in']['Sequence header top']
        options = [['Time step length', 'Analogue voltage', 'GPIB'], 
            list(map(str.__add__, [str(i) for i in range(len(sht))],
                [': '+hc['Time step name'] if hc['Time step name'] else ': ' for hc in sht])), 
            ['Fast analogue', 'Slow analogue'],
            self.get_anlg_chans('Fast')]
        positions = [[1, 4, 3, 2], [1, 6, 6, 1], [1, 7, 3, 1], [1, 8, 6, 1]]
        widgets = [QComboBox, QListWidget]
        for i in range(0, len(labels)):
            self.chan_choices[labels[i]] = widgets[i%2]()
            if i%2:
                self.chan_choices[labels[i]].setSelectionMode(3)
            self.chan_choices[labels[i]].addItems(options[i])
            self.grid.addWidget(self.chan_choices[labels[i]], *positions[i])
        self.chan_choices['Type'].currentTextChanged[str].connect(self.change_mr_type)
        self.chan_choices['Analogue type'].currentTextChanged[str].connect(self.change_mr_anlg_type)
        self.chan_choices['Analogue channel'].setEnabled(False)

        # add a new list of multirun values to the array
        self.col_index = self.make_label_edit('column index:', self.grid, 
                position=[5,0, 1,1], default_text='0', 
                validator=col_validator)[1]
        self.col_range = QLineEdit('linspace(0,1,%s)'%(self.nrows+1), self)
        self.grid.addWidget(self.col_range, 5,2, 1,2)
        # show the previously selected channels for this column:
        self.chan_choices['Time step name'].itemClicked.connect(self.save_chan_selection)
        self.chan_choices['Analogue channel'].itemClicked.connect(self.save_chan_selection)
        self.chan_choices['Type'].activated[str].connect(self.save_chan_selection)
        self.chan_choices['Analogue type'].activated[str].connect(self.save_chan_selection)
        self.col_index.textChanged[str].connect(self.set_chan_listbox)

        # add the column to the multirun values array
        add_var_button = QPushButton('Add column', self)
        add_var_button.clicked.connect(self.add_column_to_array)
        add_var_button.resize(add_var_button.sizeHint())
        self.grid.addWidget(add_var_button, 6,0, 1,1)
        
        # clear the current list of user variables
        clear_vars_button = QPushButton('Clear', self)
        clear_vars_button.clicked.connect(self.clear_array)
        clear_vars_button.resize(clear_vars_button.sizeHint())
        self.grid.addWidget(clear_vars_button, 6,1, 1,1)
        
        # suggest new measure when multirun started
        self.suggest_button = QPushButton('Auto-increment measure', self, 
                checkable=True, checked=True)
        self.suggest_button.resize(self.suggest_button.sizeHint())
        self.grid.addWidget(self.suggest_button, 6,2, 1,2)
        
        # choose last time step for multirun
        lts_label = QLabel('Last time step: ', self)
        self.grid.addWidget(lts_label, 7,0, 1,1)
        self.last_step_run_edit = self.make_label_edit('Running: ', self.grid, position=[7,1, 1,3])[1]
        self.last_step_run_edit.setText(self.ui_param['Last time step run'])
        self.last_step_run_edit.textChanged[str].connect(self.update_last_step)
        self.last_step_end_edit = self.make_label_edit('End: ', self.grid, position=[7,5, 1,3])[1]
        self.last_step_end_edit.setText(self.ui_param['Last time step end'])
        self.last_step_end_edit.textChanged[str].connect(self.update_last_step)

        # display current progress
        multirun_progress = QLabel(
            'User variable: , omit 0 of 0 files, 0 of 100 histogram files, 0% complete')
        self.grid.addWidget(multirun_progress, 8,0, 1,12)
        remove_slot(self.progress, multirun_progress.setText, True)

        # table stores multirun values:
        self.table = QTableWidget(self.nrows, self.ncols)
        self.reset_array()
        self.grid.addWidget(self.table, 9,0, 20, 12)
    
        scroll.setWidget(scroll_content)

    #### #### array editing functions #### #### 

    def reset_array(self, newvals=None):
        """Empty the table of its values. If newvals are supplied then it
        should have the right shape (rows, cols) so that it can be used
        to fill the table items."""
        self.table.setHorizontalHeaderLabels(list(map(str, range(self.ncols))))
        if not newvals:
            newvals = [['']*self.ncols]*self.nrows
        for i in range(self.table.rowCount()):
            for j in range(self.ncols):
                self.table.setItem(i, j, QTableWidgetItem())
                self.table.item(i, j).setText(newvals[i][j])

    def clear_array(self):
        """Empty the table of its values and reset the selected channels."""
        self.reset_array()
        self.ui_param['Type'] = ['Time step length']*self.ncols
        self.ui_param['Analogue type'] = ['Fast analogue']*self.ncols
        self.ui_param['Time step name'] = [[]]*self.ncols
        self.ui_param['Analogue channel'] = [[]]*self.ncols
        self.set_chan_listbox(0)
        
    def check_table(self):
        """Check that there are values in each of the cells of the array."""
        return all(self.table.item(i, j).text() 
                    for i in range(self.table.rowCount()) 
                    for j in range(self.table.columnCount()))

    def get_table(self):
        """Return a list of all the values in the multirun array table"""
        return [[self.table.item(i, j).text() for j in range(self.table.columnCount())]
                    for i in range(self.table.rowCount())]
    
    def change_array_size(self):
        """Update the size of the multirun array based on the number of rows
        and columns specified in the line edit."""
        self.nrows = int(self.rows_edit.text()) if self.rows_edit.text() else 1
        self.table.setRowCount(self.nrows)
        self.ncols = int(self.cols_edit.text()) if self.cols_edit.text() else 1
        self.table.setColumnCount(self.ncols)
        self.col_index.setValidator(QIntValidator(1,self.ncols-1))
        if self.col_index.text() and int(self.col_index.text()) > self.ncols-1:
            self.col_index.setText(str(self.ncols-1))
        self.reset_array()
        self.ui_param['runs included'] = [[] for i in range(self.nrows)]
        for key, default in zip(['Type', 'Analogue type', 'Time step name', 'Analogue channel'],
            ['Time step length', 'Fast analogue', [], []]):
            if len(self.ui_param[key]) < self.ncols: # these lists must be reshaped
                self.ui_param[key].append(default)
            elif len(self.ui_param[key]) > self.ncols:
                self.ui_param[key] = self.ui_param[key][:self.ncols]
                
    def update_all_stats(self, toggle=False):
        """Shorthand to update the values of the stats dictionary from the text
        labels."""
        self.update_repeats()
        self.update_last_step()
        for key in self.measures.keys(): # ['Variable label', 'measure', 'measure_prefix', '1st hist ID']
            if self.measures[key].text(): # don't do anything if the line edit is empty
                try:
                    self.ui_param[key] = self.types[key](self.measures[key].text())
                except: pass # probably while user was typing the '-' in '-1'
        
    def update_repeats(self, txt=''):
        """Take the current values of the line edits and use them to set the
        number of omitted and number of included runs in a histogram."""
        self.ui_param['# omitted'] = int(self.omit_edit.text()) if self.omit_edit.text() else 0
        self.ui_param['# in hist'] = int(self.nhist_edit.text()) if self.nhist_edit.text() else 1
        
    def update_last_step(self, txt=''):
        """Save the current values of the last time step file paths."""
        self.ui_param['Last time step run'] = self.last_step_run_edit.text()
        self.ui_param['Last time step end'] = self.last_step_end_edit.text()
           
    def add_column_to_array(self):
        """Make a list of values and add it to the given column 
        in the multirun values array. The function is chosen by the user.
        Values are repeated a set number of times, ordered according to the 
        ComboBox text. The selected channels are stored in lists."""
        if 'linspace' in self.col_range.text(): # choose the generating function
            f = np.linspace
        elif 'logspace' in self.col_range.text():
            f = np.logspace
        elif 'range' in self.col_range.text():
            f = np.arange
        else: return 0
        try: # make the list of values
            vals = f(*map(float, self.col_range.text().split('(')[-1].replace(')','').split(',')))
        except (ZeroDivisionError, TypeError, ValueError) as e: 
            logger.warning('Add column to multirun: invalid syntax "'+self.col_range.text()+'".\n'+str(e))
            return 0
        col = int(self.col_index.text()) if self.col_index.text() else 0
        # store the selected channels
        self.ui_param['Order'] = self.order_edit.currentText()
        for key in self.measures.keys(): # ['Variable label', 'measure', 'measure_prefix', '1st hist ID']
            if self.measures[key].text(): # don't do anything if the line edit is empty
                self.ui_param[key] = self.types[key](self.measures[key].text())
        # order the list of values
        if self.ui_param['Order'] == 'descending':
            vals = list(reversed(vals))
        elif 'random' in self.ui_param['Order']:
            vals = list(vals)
            shuffle(vals)
        for i in range(self.table.rowCount()): 
            try: # set vals in table cells
                self.table.item(i, col).setText('%.5g'%vals[i])
            except IndexError: # occurs if invalid range
                self.table.item(i, col).setText('')

    #### multirun channel selection ####

    def reset_sequence(self, tr):
        """Update the translator object used to get the experimental sequence.
        This is used to set the labels for time step names and channel names.
        Note: the multirun sequence mrtr is not affected."""
        self.tr = tr
        sht = self.tr.seq_dic['Experimental sequence cluster in']['Sequence header top']
        for key, items in [['Time step name', list(map(str.__add__, [str(i) for i in range(len(sht))],
                    [': '+hc['Time step name'] if hc['Time step name'] else ': ' for hc in sht]))],
                ['Analogue channel', self.get_anlg_chans('Fast')]]:
            self.chan_choices[key].clear()
            self.chan_choices[key].addItems(items)
        # note: selected channels might have changed order
        self.set_chan_listbox(self.col_index.text())

    def save_chan_selection(self, arg=None):
        """When the user changes the selection of channels/timesteps for the
        given column, save it. The selection will be reloaded if the user
        changes the column and then comes back."""
        col = int(self.col_index.text()) if self.col_index.text() else 0
        for key in ['Type', 'Analogue type']:
            self.ui_param[key][col] = self.chan_choices[key].currentText()
        for key in ['Time step name', 'Analogue channel']:
            self.ui_param[key][col] = list(map(self.chan_choices[key].row, self.chan_choices[key].selectedItems()))
        
    def set_chan_listbox(self, col):
        """Set the selected channels and timesteps with the values
        previously stored for the given column col. If there were
        no values stored previously or the index is out of range,
        reset the selection."""
        try:
            col = int(col) if col else 0
            mrtype = self.ui_param['Type'][col]
            antype = self.ui_param['Analogue type'][col]
            sel = {'Time step name':self.ui_param['Time step name'][col],
                'Analogue channel':self.ui_param['Analogue channel'][col] if mrtype=='Analogue voltage' else []}
        except (IndexError, ValueError):
            mrtype, antype = 'Time step length', 'Fast analogue'
            sel = {'Time step name':[], 'Analogue channel':[]}
        self.chan_choices['Type'].setCurrentText(mrtype)
        self.chan_choices['Analogue type'].setCurrentText(antype)
        self.chan_choices['Analogue channel'].setEnabled(True if mrtype=='Analogue voltage' else False)
        for key in ['Time step name', 'Analogue channel']:
            self.chan_choices[key].setCurrentRow(0, QItemSelectionModel.Clear) # clear previous selection
            try:
                for i in sel[key]: # select items at the stored indices
                    self.chan_choices[key].item(i).setSelected(True)
            except IndexError: pass # perhaps sequence was updated but using old selection indices
            except AttributeError as e: logger.warning("Couldn't set channels for the loaded multirun parameters. Load the sequence first, then load multirun parameters.\n"+str(e))
        
    def get_anlg_chans(self, speed):
        """Return a list of name labels for the analogue channels.
        speed -- 'Fast' or 'Slow'"""
        d = self.tr.seq_dic['Experimental sequence cluster in'][speed + ' analogue names']
        return map(str.__add__, d['Hardware ID'], [': '+name if name else '' for name in d['Name']])

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

    def get_next_index(self, rn):
        """Choose the next index from the rows of the table to use
        in the multirun, based on the order chosen.
        rn: the ID of the current run within the multirun.
        make rn modulo nrows so that there isn't an index error on the last run."""
        # if self.mr_param['Order'] == 'unsorted':
        #     return rn % self.nrows
        # elif self.mr_param['Order'] == 'random':
        #     return randint(0, self.nrows - 1)
        # else: # if descending, ascending, or coarse random, the order has already been set
        return (rn // (self.mr_param['# omitted'] + self.mr_param['# in hist'])) % len(self.mr_param['runs included'])# ID of histogram in repetition cycle

    def get_next_sequence(self, i=None, save_dir=''):
        """Use the values in the multirun array to make the next
        sequence to run in the multirun. Uses saved mr_param not UI"""
        if i == None: i = self.ind # row index
        esc = self.mrtr.seq_dic['Experimental sequence cluster in'] # shorthand
        try:
            for col in range(len(self.mr_vals[i])): # edit the sequence
                val = float(self.mr_vals[i][col])
                if self.mr_param['Type'][col] == 'Time step length':
                    for head in ['Sequence header top', 'Sequence header middle']:
                        for t in self.mr_param['Time step name'][col]:
                            esc[head][t]['Time step length'] = val
                elif self.mr_param['Type'][col] == 'Analogue voltage':
                    for t in self.mr_param['Time step name'][col]:
                        for c in self.mr_param['Analogue channel'][col]:
                            esc[self.mr_param['Analogue type'][col] + ' array'][c]['Voltage'][t] = val

            self.mrtr.seq_dic['Routine name in'] = 'Multirun ' + self.mr_param['Variable label'] + \
                    ': ' + self.mr_vals[i][0] + ' (%s / %s)'%(i+1, len(self.mr_vals))
            if save_dir:
                self.mrtr.write_to_file(os.path.join(save_dir, self.mr_param['measure_prefix'] + '_' + 
                    str(i + self.mr_param['1st hist ID']) + '.xml'))
        except IndexError as e:
            logger.error('Multirun failed to edit sequence at ' + self.mr_param['Variable label']
                + ' = ' + self.mr_vals[i][0] + '\n' + str(e))
        return self.mrtr.write_to_str()

    def get_all_sequences(self, save_dir=''):
        """Use the multirun array vals to make all of
        the sequences that will be used in the multirun, then
        store these as a list of XML strings."""
        self.msglist = []
        for i in range(len(self.mr_vals)):
            self.msglist.append(self.get_next_sequence(i, save_dir))

    #### save and load parameters ####

    def view_mr_queue(self):
        """Pop up message box displays the queued multiruns"""
        text = 'Would you like to clear the following list of queued multiruns?\n'
        for params, _, _, _ in self.mr_queue:
            text += params['measure_prefix'] + '\t' + params['Variable label'] + '\n'
        reply = QMessageBox.question(self, 'Queued Multiruns',
            text, QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply == QMessageBox.Yes:
            self.mr_queue = []

    def try_browse(self, title='Select a File', file_type='all (*)', 
                open_func=QFileDialog.getOpenFileName):
        """Open a file dialog and retrieve a file name from the browser.
        title: String to display at the top of the file browser window
        file_type: types of files that can be selected
        open_func: the function to use to open the file browser"""
        try:
            if 'PyQt4' in sys.modules:
                file_name = open_func(self, title, '', file_type)
            elif 'PyQt5' in sys.modules:
                file_name, _ = open_func(self, title, '', file_type)
            return file_name
        except OSError: return '' # probably user cancelled

    def save_mr_params(self, save_file_name=''):
        """Save the variable label, measure, measure prefix, # runs omitted, 
        # runs per histogram, multirun type, list of timesteps, multirun 
        # analogue type, list of channels, and array of variables."""
        if not save_file_name:
            save_file_name = self.try_browse(title='Save File', file_type='csv(*.csv);;all (*)', 
                        open_func=QFileDialog.getSaveFileName)
        if save_file_name:
            if hasattr(self.sender(), 'text') and self.sender().text() == 'Save Parameters':
                params, vals = self.ui_param, self.get_table() # save from UI
            else: params, vals = self.mr_param, self.mr_vals # save from multirun
            with open(save_file_name, 'w+') as f:
                f.write('Multirun list of variables:\n')
                f.write(';'.join([','.join([vals[row][col] 
                    for col in range(len(vals[0]))]) for row in range(len(vals))]) + '\n')
                f.write(';'.join(params.keys())+'\n')
                f.write(';'.join(map(str, list(params.values()))))

    def load_mr_params(self, load_file_name=''):
        """Load the multirun variables array from a file."""
        if not load_file_name:
            load_file_name = self.try_browse(title='Load File', file_type='csv(*.csv);;all (*)', 
                        open_func=QFileDialog.getOpenFileName)
        if load_file_name:
            with open(load_file_name, 'r') as f:
                _ = f.readline()
                vals = [x.split(',') for x in f.readline().replace('\n','').split(';')]
                header = f.readline().replace('\n','').split(';')
                params = f.readline().split(';')
            for i in range(len(header)):
                if header[i] in self.ui_param:
                    try:
                        self.ui_param[header[i]] = self.types[header[i]](params[i])
                    except ValueError as e:
                        logger.error('Multirun editor could not load parameter: %s\n'%params[i]+str(e))
            # store values in case they're overwritten after setText()
            nrows, ncols = np.shape(vals) # update array of values
            col = int(self.col_index.text()) if self.col_index.text() else 0
            nhist, nomit = map(str, [self.ui_param['# in hist'], self.ui_param['# omitted']])
            runstep, endstep = self.ui_param['Last time step run'], self.ui_param['Last time step end']
            # then update the label edits
            for key in self.measures.keys(): # update variable label and measure
                remove_slot(self.measures[key].textChanged, self.update_all_stats, False)
                self.measures[key].setText(str(self.ui_param[key]))
                remove_slot(self.measures[key].textChanged, self.update_all_stats, True)
            self.set_chan_listbox(col if col < ncols else 0)
            self.rows_edit.setText(str(nrows)) # triggers change_array_size
            self.cols_edit.setText(str(ncols))
            self.change_array_size() # don't wait for it to be triggered
            self.reset_array(vals)
            self.nhist_edit.setText(nhist)
            self.omit_edit.setText(nomit)
            self.last_step_run_edit.setText(runstep) # triggers update_last_step
            self.last_step_end_edit.setText(endstep)
            
    def check_mr_params(self, save_results_path='.'):
        """Check that the multirun parameters are valid before adding it to the queue"""
        results_path = os.path.join(save_results_path, self.ui_param['measure_prefix'])
        appending = False
        # first check if the measure folder already exists with some files in
        imax = 0
        try: 
            filelist = os.listdir(results_path)
            for fname in filelist:
                if 'params' in fname:
                    try: # look for multirun parameters file
                        with open(os.path.join(results_path, fname), 'r') as f:
                            _ = f.readline()
                            vals = f.readline().replace('\n','').split(';')
                            header = f.readline().replace('\n','').split(';')
                            params = f.readline().split(';')
                            imax = max(imax, len(vals) + int(params[header.index('1st hist ID')]) - 1)
                    except: pass
        except FileNotFoundError: pass
        # then check the multirun queue
        for m in self.mr_queue:
            if self.ui_param['measure_prefix'] == m[0]['measure_prefix']:
                imax = max(imax, len(m[2]) + m[0]['1st hist ID'] - 1)
        
        if self.ui_param['1st hist ID'] == -1: # append at the end 
            appending = True
            self.ui_param['1st hist ID'] = imax + 1 if imax>0 else 0
                    
        if (os.path.isdir(results_path) or self.ui_param['measure_prefix'] in [
            x[0]['measure_prefix'] for x in self.mr_queue]) and imax >= self.ui_param['1st hist ID']:
            # this measure exists, check if user wants to overwrite
            reply = QMessageBox.question(self, 'Confirm Overwrite',
                "Results path already exists, do you want to overwrite the files?\n"+results_path,
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if reply == QMessageBox.No:
                return 0

        # parameters are valid, add to queue
        self.mr_queue.append([copy.deepcopy(self.ui_param), self.tr.copy(), self.get_table(), appending]) 
        if self.suggest_button.isChecked(): # suggest new multirun measure ID and prefix
            n = self.ui_param['measure'] + 1
            self.measures['measure'].setText(str(n))
            self.measures['measure_prefix'].setText('Measure'+str(n))  
        return 1