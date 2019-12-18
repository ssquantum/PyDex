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
    from PyQt4.QtCore import pyqtSignal, QItemSelectionModel
    from PyQt4.QtGui import (QPushButton, QWidget, QLabel,
        QGridLayout, QLineEdit, QDoubleValidator, QIntValidator, 
        QComboBox, QListWidget, QTabWidget, QVBoxLayout, QInputDialog,
        QTableWidget, QTableWidgetItem, QScrollArea, QMessageBox) 
except ImportError:
    from PyQt5.QtCore import pyqtSignal, QItemSelectionModel
    from PyQt5.QtGui import QDoubleValidator, QIntValidator
    from PyQt5.QtWidgets import (QVBoxLayout, QWidget, QComboBox,
        QLineEdit, QGridLayout, QPushButton, QListWidget, QListWidgetItem, 
        QScrollArea, QLabel, QTableWidget, QTableWidgetItem, QMessageBox)
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
        self.tr = tr # translator for the current sequence
        self.mrtr = tr # translator for multirun sequence
        self.ind = 0 # index for how far through the multirun we are
        self.types = OrderedDict([('nrows',int), ('ncols',int), 
            ('order',str), ('# omit',int), ('# hist', int), ('measure',int), ('measure_prefix',str),
            ('Variable label', str), ('Type', list), ('Analogue type', list),
            ('Time step name', list), ('Analogue channel', list)])
        self.stats = OrderedDict([('nrows',nrows), ('ncols', ncols),
            ('order', order), ('# omit',0), ('# hist', 100), ('measure',0), ('measure_prefix','0_'),
            ('Variable label', ''), ('Type', ['Time step length']*ncols), 
            ('Analogue type', ['Fast analogue']*ncols), ('Time step name', [[]]*ncols), 
            ('Analogue channel', [[]]*ncols)])
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
        labels = ['# Rows', '# Omit', '# in Hist', '# Columns']
        default = [str(nrows), '0', '100', str(ncols)]
        self.rows_edit, self.omit_edit, self.nhist_edit, self.cols_edit = [
            self.make_label_edit(labels[i], self.grid, [0,2*i, 1,1],
                default[i], int_validator)[1] for i in range(4)]
        self.rows_edit.textChanged[str].connect(self.change_array_size)
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
        self.chan_choices['Variable label'] = QLineEdit('Variable 0', self)
        self.grid.addWidget(self.chan_choices['Variable label'], 2,1, 1,3)

        labels = ['Type', 'Time step name', 'Analogue type', 'Analogue channel']
        sht = self.tr.seq_dic['Experimental sequence cluster in']['Sequence header top']
        options = [['Time step length', 'Analogue voltage', 'GPIB'], 
            list(map(str.__add__, [str(i) for i in range(len(sht))],
                [': '+hc['Time step name'] if hc['Time step name'] else ': ' for hc in sht])), 
            ['Fast analogue', 'Slow analogue'],
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
        # show the previously selected channels for this column:
        self.col_val_edit[0].textChanged[str].connect(self.set_chan_listbox)

        # add the column to the multirun values array
        add_var_button = QPushButton('Add column', self)
        add_var_button.clicked.connect(self.add_column_to_array)
        add_var_button.resize(add_var_button.sizeHint())
        self.grid.addWidget(add_var_button, 5,0, 1,1)
        
        # clear the current list of user variables
        clear_vars_button = QPushButton('Clear', self)
        clear_vars_button.clicked.connect(self.reset_array)
        clear_vars_button.resize(clear_vars_button.sizeHint())
        self.grid.addWidget(clear_vars_button, 5,1, 1,2)

        # start/abort the multirun
        self.multirun_switch = QPushButton('Start multirun', self, checkable=True)
        self.grid.addWidget(self.multirun_switch, 5,3, 1,2)
        # pause/restart the multirun
        self.multirun_pause = QPushButton('Resume', self)
        self.grid.addWidget(self.multirun_pause, 5,5, 1,2)

        # display current progress
        self.multirun_progress = QLabel(
            'User variable: , omit 0 of 0 files, 0 of 100 histogram files, 0% complete')
        self.grid.addWidget(self.multirun_progress, 6,0, 1,12)

        # table stores multirun values:
        self.table = QTableWidget(nrows, ncols)
        self.reset_array()
        self.grid.addWidget(self.table, 7,0, 20, 12)
    
        scroll.setWidget(scroll_content)

        
    #### #### array editing functions #### #### 

    def reset_array(self):
        """Empty the table of all of its values."""
        ncols = self.table.columnCount()
        self.table.setHorizontalHeaderLabels(list(map(str, range(ncols))))
        self.stats['Type'] = ['Time step length']*ncols
        self.stats['Analogue type'] = ['Fast analogue']*ncols
        self.stats['Time step name'] = [[]]*ncols
        self.stats['Analogue channel'] = [[]]*ncols
        self.set_chan_listbox(0)
        for i in range(self.table.rowCount()):
            for j in range(ncols):
                self.table.setItem(i, j, QTableWidgetItem())
                self.table.item(i, j).setText('')

    def check_table(self):
        """Check that there are values in each of the cells of the array
        and that the total number of runs is divisible by the number of
        runs per histogram (including omitted runs)."""
        return (all(self.table.item(i, j).text() 
                    for i in range(self.table.rowCount()) 
                    for j in range(self.table.columnCount())) and not 
                self.table.rowCount() % (self.stats['# omit'] + self.stats['# hist']))
    
    def change_array_size(self):
        """Update the size of the multirun array based on the number of rows
        and columns specified in the line edit."""
        self.stats['nrows'] = self.types['nrows'](self.rows_edit.text())
        self.table.setRowCount(self.stats['nrows'])
        self.stats['ncols'] = self.types['ncols'](self.cols_edit.text())
        self.table.setColumnCount(self.stats['ncols'])
        self.col_val_edit[0].setValidator(QIntValidator(0,self.stats['ncols']-1))
        self.reset_array()

    def add_column_to_array(self):
        """Make a list of values and add it to the given column 
        in the multirun values array. The list is range(start, stop, step) 
        repeated a set number of times, ordered according to the 
        ComboBox text. The selected channels are stored in lists."""
        if all([x.text() for x in self.col_val_edit]):
            col = int(self.col_val_edit[0].text())
            # store the selected channels
            self.stats['Variable label'] = self.chan_choices['Variable label'].text()
            self.stats['# omit'] = int(self.omit_edit.text()) # number of runs to emit per histogram
            self.stats['# hist'] = int(self.nhist_edit.text()) # number of runs per histogram
            for key in ['Type', 'Analogue type']:
                self.stats[key][col] = self.chan_choices[key].currentText()
            for key in ['Time step name', 'Analogue channel']:
                self.stats[key][col] = list(map(self.chan_choices[key].row, self.chan_choices[key].selectedItems()))
            # make the list of values:
            vals = np.arange(*map(int, [x.text() for x in self.col_val_edit[1:4]]))
            repeats = int(self.col_val_edit[4].text())
            # check the number of runs per histogram matches up:
            if repeats != self.stats['# omit'] + self.stats['# hist']:
                QMessageBox.information(self, 'Check Repeats', 
                    "The number of repeats doesn't match the number of runs per histogram:\n" +
                    "repeats = %s != # omitted + # in hist = %s + %s"%(repeats, self.stats['# omit'], self.stats['# hist']))
            # order the list of values
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
            for i in range(self.table.rowCount()): 
                try: # set vals in table cells
                    self.table.item(i, col).setText(str(vals[i]))
                except IndexError: # occurs if repeats=0 or invalid range
                    self.table.item(i, col).setText('')

    #### multirun channel selection ####

    def set_chan_listbox(self, col):
        """Set the selected channels and timesteps with the values
        previously stored for the given column col. If there were
        no values stored previously or the index is out of range,
        reset the selection."""
        try:
            col = int(col)
            mrtype = self.stats['Type'][col]
            antype = self.stats['Analogue type'][col]
            sel = {'Time step name':self.stats['Time step name'][col],
                'Analogue channel':self.stats['Analogue channel'][col]}
        except IndexError:
            mrtype, antype = 'Time step length', 'Fast analogue'
            sel = {'Time step name':[], 'Analogue channel':[]}
        self.chan_choices['Type'].setCurrentText(mrtype)
        self.chan_choices['Analogue type'].setCurrentText(antype)
        self.chan_choices['Analogue channel'].setEnabled(True if mrtype=='Analogue voltage' else False)
        for key in ['Time step name', 'Analogue channel']:
            self.chan_choices[key].setCurrentRow(0, QItemSelectionModel.Clear) # clear previous selection
            for i in sel[key]: # select items at the stored indices
                self.chan_choices[key].setCurrentRow(i, QItemSelectionModel.SelectCurrent)
        
    def get_anlg_chans(self, speed):
        """Return a list of name labels for the analogue channels.
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

    def get_next_sequence(self):
        """Use the values in the multirun array to make the next
        sequence to run in the multirun."""
        row = self.ind
        self.table.selectRow(row) # display which row the multirun is up to in the table
        for col in range(self.table.columnCount()): # edit the sequence
            val = float(self.table.item(row, col).text())
            if self.stats['Type'][col] == 'Time step length':
                for head in ['Sequence header top', 'Sequence header middle']:
                    for t in self.stats['Time step name'][col]:
                        self.mrtr['Experimental sequence cluster in'][head][t]['Time step length'] = val
            elif self.stats['Type'][col] == 'Analogue voltage':
                for t in self.stats['Time step name'][col]:
                    for c in self.stats['Analogue channel'][col]:
                        self.mrtr['Experimental sequence cluster in'][
                            self.stats['Analogue type'] + ' array'][c]['Voltage'][t] = val
        self.mrtr['Routine name in'] = 'Multirun ' + self.stats['Variable label'] + \
            ': ' + self.table.item(row, 0).text() + ' (%s / %s)'%(row, self.table.rowCount())
        return self.mrtr.write_to_str()