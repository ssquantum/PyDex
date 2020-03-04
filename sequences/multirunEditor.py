"""Single Atom Image Analysis (SAIA) Multirun Editor
Stefan Spence 26/02/19

 - Provide a visual representation for multirun values
 - Allow the user to quickly edit multirun values
 - Give the list of commands for DExTer to start a multirun
"""
import os
import sys
import time
import re
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
sys.path.append('..')
from mythread import remove_slot # for dis- and re-connecting slots

def strlist(text):
    """Convert a string of a list of strings back into
    a list of strings."""
    return list(text[1:-1].replace("'","").split(', '))

def intstrlist(text):
    """Convert a string of a list of ints back into a list:
    (str) '[1, 2, 3]' -> (list) [1,2,3]"""
    try:
        return list(map(int, text[1:-1].split(',')))
    except ValueError: return []

def listlist(text):
    """Convert a string of nested lists into a
    list of lists."""
    return list(map(intstrlist, re.findall('\[[\d\s,]*\]', text)))

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
        self.mrtr = tr # translator for multirun sequence
        self.msglist = [] # list of multirun sequences as XML string
        self.ind = 0 # index for how far through the multirun we are
        self.nrows = nrows
        self.ncols = ncols
        self.order = order
        self.nomit = 0   # number of runs per histogram to omit from multirun
        self.nhist = 100 # number of runs to include in each histogram
        self.types = OrderedDict([('measure',int), ('measure_prefix',str),
            ('Variable label', str), ('Type', strlist), 
            ('Analogue type', strlist), ('Time step name', listlist), 
            ('Analogue channel', listlist), ('runs included', listlist),
            ('Last time step run', str), ('Last time step end', str)])
        self.stats = OrderedDict([('measure',0), ('measure_prefix','Measure0_'),
            ('Variable label', ''), ('Type', ['Time step length']*ncols), 
            ('Analogue type', ['Fast analogue']*ncols), ('Time step name', [[]]*ncols), 
            ('Analogue channel', [[]]*ncols), ('runs included', [[]]*nrows),
            ('Last time step run', ''), ('Last time step end', '')])
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
        int_validator = QIntValidator()       # integers
        nat_validator = QIntValidator(1,999999)# natural numbers
        col_validator = QIntValidator(0,self.ncols-1) # for number of columns

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
        labels = ['Variable label', 'measure', 'measure_prefix']
        defaults = ['Variable 0', '0', 'Measure0_']
        for i in range(len(labels)):
            label = QLabel(labels[i], self)
            self.grid.addWidget(label, i+1,0, 1,1)
            self.measures[labels[i]] = QLineEdit(defaults[i], self)
            self.measures[labels[i]].editingFinished.connect(self.update_all_stats)
            self.grid.addWidget(self.measures[labels[i]], i+1,1, 1,3)
        self.measures['measure'].setValidator(int_validator)

        self.chan_choices = OrderedDict()
        labels = ['Type', 'Time step name', 'Analogue type', 'Analogue channel']
        sht = self.tr.seq_dic['Experimental sequence cluster in']['Sequence header top']
        options = [['Time step length', 'Analogue voltage', 'GPIB'], 
            list(map(str.__add__, [str(i) for i in range(len(sht))],
                [': '+hc['Time step name'] if hc['Time step name'] else ': ' for hc in sht])), 
            ['Fast analogue', 'Slow analogue'],
            self.get_anlg_chans('Fast')]
        positions = [[1, 4, 3, 2], [1, 6, 5, 1], [1, 7, 3, 1], [1, 8, 5, 1]]
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
        self.col_val_edit = []
        labels = ['column index', 'start', 'stop']
        validators = [col_validator, double_validator, double_validator]
        for i in range(0, len(labels)*2, 2):
            self.col_val_edit.append(self.make_label_edit(labels[i//2], self.grid, 
                position=[4,i, 1,1], default_text='1', 
                validator=validators[i//2])[1])
        # show the previously selected channels for this column:
        self.chan_choices['Time step name'].itemClicked.connect(self.save_chan_selection)
        self.chan_choices['Analogue channel'].itemClicked.connect(self.save_chan_selection)
        self.chan_choices['Type'].activated[str].connect(self.save_chan_selection)
        self.chan_choices['Analogue type'].activated[str].connect(self.save_chan_selection)
        self.col_val_edit[0].textChanged[str].connect(self.set_chan_listbox)

        # add the column to the multirun values array
        add_var_button = QPushButton('Add column', self)
        add_var_button.clicked.connect(self.add_column_to_array)
        add_var_button.resize(add_var_button.sizeHint())
        self.grid.addWidget(add_var_button, 5,0, 1,1)
        
        # clear the current list of user variables
        clear_vars_button = QPushButton('Clear', self)
        clear_vars_button.clicked.connect(self.clear_array)
        clear_vars_button.resize(clear_vars_button.sizeHint())
        self.grid.addWidget(clear_vars_button, 5,1, 1,2)
        
        # choose last time step for multirun
        lts_label = QLabel('Last time step: ', self)
        self.grid.addWidget(lts_label, 6,0, 1,1)
        self.last_step_run_edit = self.make_label_edit('Running: ', self.grid, position=[6,1, 1,3])[1]
        self.last_step_run_edit.setText(r'C:\Users\lab\Desktop\DExTer 1.3\Last Timesteps\RbMOTendstep.evt')
        self.last_step_run_edit.textChanged[str].connect(self.update_last_step)
        self.last_step_end_edit = self.make_label_edit('End: ', self.grid, position=[6,5, 1,3])[1]
        self.last_step_end_edit.setText(r'C:\Users\lab\Desktop\DExTer 1.3\Last Timesteps\feb2020_940and812.evt')
        self.last_step_end_edit.textChanged[str].connect(self.update_last_step)

        # display current progress
        multirun_progress = QLabel(
            'User variable: , omit 0 of 0 files, 0 of 100 histogram files, 0% complete')
        self.grid.addWidget(multirun_progress, 7,0, 1,12)
        remove_slot(self.progress, multirun_progress.setText, True)

        # table stores multirun values:
        self.table = QTableWidget(self.nrows, self.ncols)
        self.reset_array()
        self.grid.addWidget(self.table, 8,0, 20, 12)
    
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
        self.stats['Type'] = ['Time step length']*self.ncols
        self.stats['Analogue type'] = ['Fast analogue']*self.ncols
        self.stats['Time step name'] = [[]]*self.ncols
        self.stats['Analogue channel'] = [[]]*self.ncols
        self.set_chan_listbox(0)
        
    def check_table(self):
        """Check that there are values in each of the cells of the array."""
        return all(self.table.item(i, j).text() 
                    for i in range(self.table.rowCount()) 
                    for j in range(self.table.columnCount()))
    
    def change_array_size(self):
        """Update the size of the multirun array based on the number of rows
        and columns specified in the line edit."""
        self.nrows = int(self.rows_edit.text()) if self.rows_edit.text() else 1
        self.table.setRowCount(self.nrows)
        self.ncols = int(self.cols_edit.text()) if self.cols_edit.text() else 1
        self.table.setColumnCount(self.ncols)
        self.col_val_edit[0].setValidator(QIntValidator(0,self.ncols-1))
        if self.col_val_edit[0].text() and int(self.col_val_edit[0].text()) > self.ncols-1:
            self.col_val_edit[0].setText(str(self.ncols-1))
        self.reset_array()
        self.stats['runs included'] = [[]]*self.nrows
        for key, default in zip(['Type', 'Analogue type', 'Time step name', 'Analogue channel'],
            ['Time step length', 'Fast analogue', [], []]):
            if len(self.stats[key]) < self.ncols: # these lists must be reshaped
                self.stats[key].append(default)
            elif len(self.stats[key]) > self.ncols:
                self.stats[key] = self.stats[key][:self.ncols]
                
    def update_all_stats(self, toggle=False):
        """Shorthand to update the values of the stats dictionary from the text
        labels."""
        self.update_repeats()
        self.update_last_step()
        for key in self.measures.keys(): # ['Variable label', 'measure', 'measure_prefix']
                self.stats[key] = self.types[key](self.measures[key].text())
        
    
    def update_repeats(self, txt=''):
        """Take the current values of the line edits and use them to set the
        number of omitted and number of included runs in a histogram."""
        self.nomit = int(self.omit_edit.text()) if self.omit_edit.text() else 0
        self.nhist = int(self.nhist_edit.text()) if self.nhist_edit.text() else 1
        
    def update_last_step(self, txt=''):
        """Save the current values of the last time step file paths."""
        self.stats['Last time step run'] = self.last_step_run_edit.text()
        self.stats['Last time step end'] = self.last_step_end_edit.text()
           
    def add_column_to_array(self):
        """Make a list of values and add it to the given column 
        in the multirun values array. The list is range(start, stop, step) 
        repeated a set number of times, ordered according to the 
        ComboBox text. The selected channels are stored in lists."""
        if all([x.text() for x in self.col_val_edit]):
            col = int(self.col_val_edit[0].text()) if self.col_val_edit[0].text() else 0
            # store the selected channels
            self.order = self.order_edit.currentText()
            for key in self.measures.keys(): # ['Variable label', 'measure', 'measure_prefix']
                self.stats[key] = self.types[key](self.measures[key].text())
            # make the list of values:
            try:
                vals = np.linspace(*map(float, [x.text() for x in self.col_val_edit[1:3]]), self.nrows)
            except ZeroDivisionError as e: 
                logger.warning('Add column to multirun: attempted to use step of 0.\n'+str(e))
                return 0
            # order the list of values
            if self.order == 'descending':
                vals = reversed(vals)
            elif 'random' in self.order:
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
        self.set_chan_listbox(self.col_val_edit[0].text())

    def save_chan_selection(self, arg=None):
        """When the user changes the selection of channels/timesteps for the
        given column, save it. The selection will be reloaded if the user
        changes the column and then comes back."""
        col = int(self.col_val_edit[0].text()) if self.col_val_edit[0].text() else 0
        for key in ['Type', 'Analogue type']:
            self.stats[key][col] = self.chan_choices[key].currentText()
        for key in ['Time step name', 'Analogue channel']:
            self.stats[key][col] = list(map(self.chan_choices[key].row, self.chan_choices[key].selectedItems()))
        
    def set_chan_listbox(self, col):
        """Set the selected channels and timesteps with the values
        previously stored for the given column col. If there were
        no values stored previously or the index is out of range,
        reset the selection."""
        try:
            col = int(col) if col else 0
            mrtype = self.stats['Type'][col]
            antype = self.stats['Analogue type'][col]
            sel = {'Time step name':self.stats['Time step name'][col],
                'Analogue channel':self.stats['Analogue channel'][col] if mrtype=='Analogue voltage' else []}
        except IndexError:
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
            except AttributeError as e: 
                logger.warning("Couldn't set channels for the loaded multirun parameters." + 
                    " Load the sequence first, then load multirun parameters.\n"+str(e))
        
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
        if self.order == 'unsorted':
            return rn % self.nrows
        elif self.order == 'random':
            return randint(0, self.nrows)
        else: # if descending, ascending, or coarse random, the order has already been set
            return (rn // (self.nomit + self.nhist)) % self.nrows # ID of histogram in repetition cycle

    def get_next_sequence(self):
        """Use the values in the multirun array to make the next
        sequence to run in the multirun."""
        self.table.selectRow(self.ind) # display which row the multirun is up to in the table
        esc = self.mrtr.seq_dic['Experimental sequence cluster in'] # shorthand
        try:
            for col in range(self.table.columnCount()): # edit the sequence
                val = float(self.table.item(self.ind, col).text())
                if self.stats['Type'][col] == 'Time step length':
                    for head in ['Sequence header top', 'Sequence header middle']:
                        for t in self.stats['Time step name'][col]:
                            esc[head][t]['Time step length'] = val
                elif self.stats['Type'][col] == 'Analogue voltage':
                    for t in self.stats['Time step name'][col]:
                        for c in self.stats['Analogue channel'][col]:
                            esc[self.stats['Analogue type'][col] + ' array'][c]['Voltage'][t] = val
        except IndexError as e:
            logger.error('Multirun failed to edit sequence at ' + self.stats['Variable label']
                + ' = ' + self.table.item(self.ind, 0).text() + '\n' + str(e))
        self.mrtr.seq_dic['Routine name in'] = 'Multirun ' + self.stats['Variable label'] + \
            ': ' + self.table.item(self.ind, 0).text() + ' (%s / %s)'%(self.ind+1, self.table.rowCount())
        return self.mrtr.write_to_str()

    def get_all_sequences(self):
        """Use the values in the multirun array to make all of
        the sequences that will be used in the multirun, then
        store these as a list of XML strings."""
        r = self.ind
        self.msglist = []
        for i in range(self.nrows):
            self.ind = i
            self.msglist.append(self.get_next_sequence())
        self.ind = r 

    #### save and load parameters ####

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
            with open(save_file_name, 'w+') as f:
                f.write('Multirun list of variables:\n')
                f.write(';'.join([','.join([self.table.item(row, col).text() 
                    for col in range(self.table.columnCount())]) for row in range(self.table.rowCount())]) + '\n')
                f.write(';'.join(self.stats.keys()) + ';# omitted;# in hist\n')
                f.write(';'.join(map(str, list(self.stats.values()) + [self.nomit, self.nhist])))

    def load_mr_params(self, load_file_name=''):
        """Load the multirun variables array from a file."""
        if not load_file_name:
            load_file_name = self.try_browse(title='Load File', file_type='csv(*.csv);;all (*)', 
                        open_func=QFileDialog.getOpenFileName)
        if load_file_name:
            with open(load_file_name, 'r') as f:
                _ = f.readline()
                vals = [x.split(',') for x in f.readline().replace('\n','').split(';')]
                header = f.readline().split(';')
                params = f.readline().split(';')
            for i in range(len(header)):
                if header[i] in self.stats:
                    self.stats[header[i]] = self.types[header[i]](params[i])
                elif '# omitted' in header[i]:
                    self.nomit = int(params[i])
                elif '# in hist' in header[i]: 
                    self.nhist = int(params[i])
            for key in self.measures.keys(): # update variable label and measure
                self.measures[key].setText(str(self.stats[key]))
            nrows, ncols = np.shape(vals) # update array of values
            col = int(self.col_val_edit[0].text()) if self.col_val_edit[0].text() else 0
            self.set_chan_listbox(col if col < ncols else 0)
            self.rows_edit.setText(str(nrows)) # triggers change_array_size
            self.cols_edit.setText(str(ncols))
            self.change_array_size() # don't wait for it to be triggered
            self.reset_array(vals)
            self.omit_edit.setText(str(self.nomit))
            self.nhist_edit.setText(str(self.nhist))
            runstep, endstep = self.stats['Last time step run'], self.stats['Last time step end']
            self.last_step_run_edit.setText(runstep) # triggers update_last_step
            self.last_step_end_edit.setText(endstep)