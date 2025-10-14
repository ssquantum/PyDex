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
from PyQt5.QtCore import (pyqtSignal, QItemSelectionModel, QThread, Qt,
                            QRect, QCoreApplication, QTimer)
from PyQt5.QtGui import QDoubleValidator, QIntValidator
from PyQt5.QtWidgets import (QVBoxLayout, QWidget, QComboBox,
    QLineEdit, QGridLayout, QPushButton, QListWidget, QListWidgetItem, 
    QScrollArea, QLabel, QTableWidget, QTableWidgetItem, QMessageBox,
    QFileDialog, QApplication, QMainWindow)
if '.' not in sys.path: sys.path.append('.')
if '..' not in sys.path: sys.path.append('..')
from mythread import reset_slot # for dis- and re-connecting slots
from strtypes import strlist, intstrlist, listlist, error, warning, info
from translator import translate
from mrunq import Ui_QueueWindow

####    ####    ####    ####

class sequenceSaver(QThread):
    """Saving DExTer sequences can sometimes take a long time.
    Save them on this thread so that they don't make the GUI lag.
    mrtr    -- translator instance for the multirun sequence
    mrvals  -- table of values to change in the multirun
    mrparam -- multirun parameters; which channels to change etc.
    savedir -- directory to save sequences into."""
    def __init__(self, mrtr, mrvals, mrparam, savedir):
        super().__init__()
        self.mrtr = mrtr 
        self.mr_vals = mrvals
        self.mr_param = mrparam
        self.savedir = savedir
        self.app = QApplication.instance()
    
    def run(self):
        """Use the values in the multirun array to make the next
        sequence to run in the multirun. Uses saved mr_param not UI"""
        if self.savedir:
            for i in range(len(self.mr_vals)):
                self.app.processEvents()  # avoids GUI lag but slows this task down
                esc = self.mrtr.get_esc() # shorthand for experimental sequence cluster
                num_s = len(esc[2]) - 2 # number of steps
                try:
                    for col in range(len(self.mr_vals[i])): # edit the sequence
                        try:
                            val = float(self.mr_vals[i][col])
                            if self.mr_param['Type'][col] == 'Time step length':
                                for head in [2, 9]:
                                    for t in self.mr_param['Time step name'][col]:
                                       esc[head][t+2][3][1].text = str(val) # time step length
                            elif self.mr_param['Type'][col] == 'Analogue voltage':
                                for t in self.mr_param['Time step name'][col]:
                                    for c in self.mr_param['Analogue channel'][col]:
                                        if 'Fast' in self.mr_param['Analogue type'][col]:
                                            esc[6][t + c*num_s + 3][3][1].text = str(val)
                                        else:
                                            esc[11][t + c*num_s + 3][3][1].text = str(val)
                        except ValueError: pass
                    self.mrtr.set_routine_name('Multirun ' + self.mr_param['Variable label'] + \
                            ': ' + self.mr_vals[i][0] + ' (%s / %s)'%(i+1, len(self.mr_vals)))
                    # self.mrtr.write_to_file(os.path.join(self.savedir, self.mr_param['measure_prefix'] + '_' +  # 22/04/24 don't save every MR to file
                    #     str(i + self.mr_param['1st hist ID']) + '.xml'))
                except IndexError as e:
                    error('Multirun failed to edit sequence at ' + self.mr_param['Variable label']
                        + ' = ' + self.mr_vals[i][0] + '\n' + str(e))


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

    def __init__(self, tr, nrows=1, ncols=1, order='random'):
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
            ('# omitted', int), ('# in hist', int), ('list index', strlist)])
        self.ui_param = OrderedDict([('measure',0), ('measure_prefix','Measure0'),
            ('1st hist ID', -1), ('Variable label', ''), 
            ('Order', order), ('Type', ['Time step length']*ncols), 
            ('Analogue type', ['Fast analogue']*ncols), ('Time step name', [[]]*ncols), 
            ('Analogue channel', [[]]*ncols), ('runs included', [[] for i in range(nrows)]),
            ('Last time step run', r'C:\Users\lab\Desktop\DExTer 1.4\Last Timesteps\Feb2023_817_and_1065.evt'), 
            ('Last time step end', r'C:\Users\lab\Desktop\DExTer 1.4\Last Timesteps\Feb2023_817_and_1065.evt'),
            ('# omitted', 5), ('# in hist', 100), ('list index', ['0']*ncols)])
        self.awg_args = ['duration_ms','start_freq_MHz','end_freq_MHz',
                         'hybridicity','start_amp','end_amp','phase',
                         'duty_cycle','drop_amp',
                         'drop_time_us','mod_amp','mod_freq_kHz',
                         'index','start_phase','-------',
                         'duration_[ms]','off_time_[us]','freqs_input_[MHz]',
                         'start_freq_[MHz]','end_freq_[MHz]','hybridicity',
                         'num_of_traps','distance_[um]','tot_amp_[mV]',
                         'dc_offset_[mV]','start_amp','end_amp',
                         'start_output_[Hz]','end_output_[Hz]','freq_amp',
                         'mod_freq_[kHz]','mod_depth','freq_phase_[deg]',
                         'freq_adjust','amp_adjust','freqs_output_[Hz]',
                         'num_of_samples','duration_loop_[ms]',
                         'number_of_cycles']
        self.dds_args = ['Freq', 'Phase', 'Amp', 'Start_add', 'End_add', 'Step_rate', 'Sweep_start', 
        'Sweep_end', 'Pos_step', 'Neg_step', 'Pos_step_rate', 'Neg_step_rate']
        self.slm_args = ['f','period','angle','radius','gradient','shift','radial','azimuthal','amplitude','max_mod_depth','radius_scale']
        self.rfsoc_args = ['freq (MHz)', 'time (us)', 'gain (dac units 1-32765)']
        self.mwg_wftk_args = ['freq (MHz)','amp (dBm)','phase (deg)']
        self.mwg_anritsu_args = ['freq (MHz)','amp (dBm)']
        self.column_options = ['Analogue voltage', 'AWG1 chan : seg', 'AWG2 chan : seg', 'AWG3 chan : seg',
            'DDS1 port : profile', 'DDS2 module : profile', 'DDS3 module : profile',
            'SLM holograms', 'RFSOC pulse','MWG (WFTK) tones','MWG (Anritsu) tones'] # these analogue types require the analogue options 
        self.col_range_text = ['']*ncols
        self.COM = ['RB1A', 'RB2', 'RB3', 'RB4', 'RB1B','',"RB1A'","RB1B'"] # DDS COM port connections
        self.COM2 = ['977', '1557', '1013', '420'] # DDS2 module connections
        self.COM3 = ['Name0','Name1','HFImage','Name3','Name4']
        self.mr_param = copy.deepcopy(self.ui_param) # parameters used for current multirun
        self.mr_vals  = [] # multirun values for the current multirun
        self.mr_queue = [] # list of parameters, sequences, and values to queue up for future multiruns
        self.appending = False # whether the current multirun will be appended on to the displayed results
        self.multirun = False # whether a multirun is running or not
        self.QueueWindow = QMainWindow() # window for editing mr queue
        self.QueueWindow.setStyleSheet("background-color: cyan;")
        self.queue_ui = Ui_QueueWindow(self.mr_queue)
        self.queue_ui.setupUi(self.QueueWindow)
        self.init_UI()  # make the widgets
        self.ss = sequenceSaver(self.mrtr, self.mr_vals, self.mr_param, '') # used to save sequences

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
        default = ['5', '100', str(self.ncols), str(self.nrows)]
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
        self.order_edit.addItems(['random', 'ascending', 'descending', 'coarse random', 'unsorted']) 
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
        sht = self.tr.get_esc()[2][2:] # 'Sequence header top'
        options = [['Time step length', 'Analogue voltage', 'GPIB', 'AWG1 chan : seg', 
        'AWG2 chan : seg', 'AWG3 chan : seg', 'DDS1 port : profile', 'DDS2 module : profile', 'DDS3 module : profile',
        'SLM holograms','RFSOC pulse','MWG (WFTK) tones','MWG (Anritsu) tones','Other'], 
            list(map(str.__add__, [str(i) for i in range(len(sht))],
                    [': '+hc[6][1].text for hc in sht])), # time step names
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
        
        # enter desired time step selection via python cmd
        self.index_slice = QLineEdit('range(0,1,2)', self)
        self.grid.addWidget(self.index_slice, 3,4,3,2)
        self.apply_slice_btn = QPushButton('Apply range', self)
        self.grid.addWidget(self.apply_slice_btn, 4,4,3,2)
        self.apply_slice_btn.clicked.connect(self.apply_slice)
        
        # AWG takes a list for some arguments, so needs an index
        label = QLabel('List index:', self)
        self.grid.addWidget(label, 3,7,3,1)
        self.list_index = QLineEdit('0', self)
        self.grid.addWidget(self.list_index, 4,7,3,1)
        self.list_index.setValidator(msr_validator)
        self.list_index.textEdited[str].connect(self.save_chan_selection)
        
        
        # add a new list of multirun values to the array
        self.col_index = self.make_label_edit('column index:', self.grid, 
                position=[5,0, 1,1], default_text='0', 
                validator=col_validator)[1]
        self.col_range = QLineEdit('np.linspace(0,1,%s)'%(self.nrows), self)
        self.grid.addWidget(self.col_range, 5,2, 1,2)
        # show the previously selected channels for this column:
        self.chan_choices['Time step name'].itemClicked.connect(self.save_chan_selection)
        self.chan_choices['Analogue channel'].itemClicked.connect(self.save_chan_selection)
        self.col_range.editingFinished.connect(self.save_chan_selection)
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
        self.last_step_end_edit = self.make_label_edit('End: ', self.grid, position=[7,5, 1,2])[1]
        self.last_step_end_edit.setText(self.ui_param['Last time step end'])
        self.last_step_end_edit.textChanged[str].connect(self.update_last_step)

        self.last_step_lock_button = QPushButton('Lock', self)
        self.last_step_lock_button.setCheckable(True)
        self.last_step_lock_button.setChecked(True)
        self.last_step_lock_button.resize(self.last_step_lock_button.sizeHint())
        self.last_step_lock_button.clicked.connect(self.update_last_step_lock)
        self.update_last_step_lock()
        self.grid.addWidget(self.last_step_lock_button, 7,8, 1,1)

        # display current progress
        multirun_progress = QLabel(
            'User variable: , omit 0 of 0 files, 0 of 100 histogram files, 0% complete')
        self.grid.addWidget(multirun_progress, 8,0, 1,12)
        reset_slot(self.progress, multirun_progress.setText, True)

        # table stores multirun values:
        self.table = QTableWidget(self.nrows, self.ncols)
        self.reset_array()
        self.grid.addWidget(self.table, 9,0, 20, 12)
    
        scroll.setWidget(scroll_content)

    def update_last_step_lock(self):
        """Enables or disables the last step line edits based on whether the
        last step lock button is pressed."""
        locked = self.last_step_lock_button.isChecked()
        self.last_step_run_edit.setEnabled(not locked)
        self.last_step_end_edit.setEnabled(not locked)

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
        self.ui_param['list index'] = ['0']*self.ncols
        self.col_range_text = self.col_range_text[:self.ncols] + ['']*(
                                        self.ncols-len(self.col_range_text))
        self.set_chan_listbox(0)
        
    def check_table(self):
        """Check that there are values in each of the cells of the array."""
        try:
            for i in range(self.table.rowCount()):
                for j in range(self.table.columnCount()):
                    _ = float(self.table.item(i, j).text())
            return 1
        except ValueError: return 0
                    
    def get_table(self):
        """Return a list of all the values in the multirun array table"""
        return [[self.table.item(i, j).text() for j in range(self.table.columnCount())]
                    for i in range(self.table.rowCount())]
    
    def change_array_size(self):
        """Update the size of the multirun array based on the number of rows
        and columns specified in the line edit."""
        self.nrows = int(self.rows_edit.text()) if self.rows_edit.text() else 1
        if self.nrows < 1:
            self.nrows = 1
        self.table.setRowCount(self.nrows)
        self.ncols = int(self.cols_edit.text()) if self.cols_edit.text() else 1
        if self.ncols < 1:
            self.ncols = 1
        self.table.setColumnCount(self.ncols)
        self.col_index.setValidator(QIntValidator(1,self.ncols-1))
        if self.col_index.text() and int(self.col_index.text()) > self.ncols-1:
            self.col_index.setText(str(self.ncols-1))
        self.reset_array() 
        self.col_range_text = self.col_range_text[:self.ncols] + ['']*(
                                        self.ncols-len(self.col_range_text))
        self.ui_param['runs included'] = [[] for i in range(self.nrows)]
        for key, default in zip(['Type', 'Analogue type', 'Time step name', 'Analogue channel', 'list index'],
            ['Time step length', 'Fast analogue', [], [], '0']):
            for i in range(len(self.ui_param[key]), self.ncols):
                self.ui_param[key].append(default)
            if len(self.ui_param[key]) > self.ncols:
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

    def apply_slice(self):
        """Use the text in the index slice line edit to select time steps"""
        try:
            self.chan_choices['Time step name'].clearSelection()
            for i in eval(self.index_slice.text()):
                try:
                    self.chan_choices['Time step name'].item(i).setSelected(True)
                except AttributeError: pass # index out of range
            self.save_chan_selection()
        except (TypeError, ValueError, NameError) as e: 
            warning('Invalid selection command for multirun timesteps "'+self.index_slice.text()+'".\n'+str(e))
        
    def add_column_to_array(self):
        """Make a list of values and add it to the given column 
        in the multirun values array. The function is chosen by the user.
        Values are repeated a set number of times, ordered according to the 
        ComboBox text. The selected channels are stored in lists."""
        prevent_shuffle = False
        try: # make the list of values
            table = np.array(self.get_table()).T
            table = np.array([[val if val != '' else '0' for val in column] for column in table])
            c = [column.astype(float) for column in table]
            vals = eval(self.col_range.text())
            if 'c[' in self.col_range.text():
                prevent_shuffle = True
        except Exception as e: 
            warning('Add column to multirun: invalid syntax "'+self.col_range.text()+'".\n'+str(e))
            return 0
        col = int(self.col_index.text()) if self.col_index.text() else 0
        # store the selected channels
        self.ui_param['Order'] = self.order_edit.currentText()
        for key in self.measures.keys(): # ['Variable label', 'measure', 'measure_prefix', '1st hist ID']
            if self.measures[key].text(): # don't do anything if the line edit is empty
                self.ui_param[key] = self.types[key](self.measures[key].text())
        # order the list of values
        if not prevent_shuffle:
            if self.ui_param['Order'] == 'descending':
                vals = list(reversed(vals))
            elif 'random' in self.ui_param['Order']:
                vals = list(vals)
                shuffle(vals)
        for i in range(self.table.rowCount()): 
            try: # set vals in table cells
                self.table.item(i, col).setText('%.9f'%vals[i])
            except IndexError: # occurs if invalid range
                self.table.item(i, col).setText('')

    #### multirun channel selection ####

    def reset_sequence(self, tr):
        """Update the translator object used to get the experimental sequence.
        This is used to set the labels for time step names and channel names.
        Note: the multirun sequence mrtr is not affected."""
        self.tr = tr
        self.change_mr_type(self.chan_choices['Type'].currentText())
        # note: selected channels might have changed order
        self.set_chan_listbox(self.col_index.text())

    def save_chan_selection(self, arg=None):
        """When the user changes the selection of channels/timesteps for the
        given column, save it. The selection will be reloaded if the user
        changes the column and then comes back."""
        try:
            if self.col_index.text():
                col = int(self.col_index.text()) 
                for key in ['Type', 'Analogue type']:
                    self.ui_param[key][col] = self.chan_choices[key].currentText()
                for key in ['Time step name', 'Analogue channel']:
                    self.ui_param[key][col] = list(map(self.chan_choices[key].row, self.chan_choices[key].selectedItems()))
                self.ui_param['list index'][col] = int(self.list_index.text()) if self.list_index.text() else 0
                self.col_range_text[col] = self.col_range.text()
        except (ValueError, IndexError) as e:
            error("Multirun couldn't save channel choices for column "+self.col_index.text()+'.\n'+str(e))
        
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
                'Analogue channel':self.ui_param['Analogue channel'][col] 
                    if any(mrtype==x for x in self.column_options) else []}
            list_ind = self.ui_param['list index'][col]
            col_range_txt = self.col_range_text[col]
        except (IndexError, ValueError):
            mrtype, antype = 'Time step length', 'Fast analogue'
            sel = {'Time step name':[], 'Analogue channel':[]}
            list_ind = 0
            col_range_txt = ''
        self.col_range.setText(col_range_txt)
        self.list_index.setText(str(list_ind))
        self.chan_choices['Type'].setCurrentText(mrtype)
        self.chan_choices['Analogue type'].setCurrentText(antype)
        self.chan_choices['Analogue channel'].setEnabled(any(mrtype==x for x in self.column_options))
        for key in ['Time step name', 'Analogue channel']:
            self.chan_choices[key].setCurrentRow(0, QItemSelectionModel.Clear) # clear previous selection
            try:
                for i in sel[key]: # select items at the stored indices
                    self.chan_choices[key].item(i).setSelected(True)
            except IndexError: pass # perhaps sequence was updated but using old selection indices
            except AttributeError as e: warning("Couldn't set channels for the loaded multirun parameters. Load the sequence first, then load multirun parameters.\n"+str(e))
        
    def setListboxFlag(self, listbox, flag):
        """Set the items of the listbox all have the given flag.
        e.g. self.setListboxFlag(self.chan_choices['Time step name'], ~Qt.ItemIsEditable)"""
        for i in range(listbox.count()):
            item = listbox.item(i)
            item.setFlags(item.flags() | flag)

    def get_anlg_chans(self, speed):
        """Return a list of name labels for the analogue channels.
        speed -- 'Fast' or 'Slow'"""
        chans = self.tr.get_esc()[5 if speed=='Fast' else 10][2:]
        return [c[2][1].text + ': ' + c[3][1].text for c in chans]

    def change_mr_type(self, newtype):
        """Enable/Disable list boxes to reflect the multirun type:
        newtype[str] -- Time step length: only needs timesteps
                     -- Analogue voltage: also needs channels
                     -- AWG: takes float values but with a list index."""
        sht = self.tr.get_esc()[2][2:] # 'Sequence header top'
        if newtype == 'AWG1 chan : seg' or newtype == 'AWG2 chan : seg' or newtype == 'AWG3 chan : seg':
            self.chan_choices['Time step name'].clear()
            self.chan_choices['Time step name'].addItems([str(i)+', '+str(j) for j in range(200) for i in range(2)])
            reset_slot(self.chan_choices['Analogue type'].currentTextChanged[str], self.change_mr_anlg_type, False)
            self.chan_choices['Analogue type'].clear()
            self.chan_choices['Analogue type'].addItems(['AWG Parameter'])
            self.chan_choices['Analogue channel'].setEnabled(True)
            self.chan_choices['Analogue channel'].clear()
            self.chan_choices['Analogue channel'].addItems(self.awg_args)
        elif 'DDS' in newtype:
            self.chan_choices['Time step name'].clear()
            if 'DDS2' in newtype:
                ddsoptions = ['%s : P%s - '%(i+1,j)+self.COM2[i] for i in range(4) for j in range(8)]
                for i in range(4): ddsoptions.insert(i*9+8, '%s : aux - '%(i+1)+self.COM2[i])
            elif 'DDS3' in newtype:
                ddsoptions = ['%s : P%s - '%(i+1,j)+self.COM3[i] for i in range(5) for j in range(8)]
                for i in range(4): ddsoptions.insert(i*9+8, '%s : aux - '%(i+1)+self.COM3[i])
            else:
                ddsoptions = ['COM%s : P%s - '%(i+7,j)+self.COM[i] for i in range(8) for j in range(8)]
                for i in range(8): ddsoptions.insert(i*9+8, 'COM%s : aux - '%(i+7)+self.COM[i])
            self.chan_choices['Time step name'].addItems(ddsoptions)
            reset_slot(self.chan_choices['Analogue type'].currentTextChanged[str], self.change_mr_anlg_type, False)
            self.chan_choices['Analogue type'].clear()
            self.chan_choices['Analogue type'].addItems(['DDS Parameter'])
            self.chan_choices['Analogue channel'].setEnabled(True)
            self.chan_choices['Analogue channel'].clear()
            self.chan_choices['Analogue channel'].addItems(self.dds_args)
        elif newtype == 'SLM holograms':
            self.chan_choices['Time step name'].clear()
            slmoptions = ['Hologram %s'%(i) for i in range(20)]
            self.chan_choices['Time step name'].addItems(slmoptions)
            reset_slot(self.chan_choices['Analogue type'].currentTextChanged[str], self.change_mr_anlg_type, False)
            self.chan_choices['Analogue type'].clear()
            self.chan_choices['Analogue type'].addItems(['Hologram Parameter'])
            self.chan_choices['Analogue channel'].setEnabled(True)
            self.chan_choices['Analogue channel'].clear()
            self.chan_choices['Analogue channel'].addItems(self.slm_args)
        elif newtype == 'RFSOC pulse':
            self.chan_choices['Time step name'].clear()
            rfsocoptions = ['Pulse %s'%(i) for i in range(7)]
            self.chan_choices['Time step name'].addItems(rfsocoptions)
            reset_slot(self.chan_choices['Analogue type'].currentTextChanged[str], self.change_mr_anlg_type, False)
            self.chan_choices['Analogue type'].clear()
            self.chan_choices['Analogue type'].addItems(['RFSOC Parameter'])
            self.chan_choices['Analogue channel'].setEnabled(True)
            self.chan_choices['Analogue channel'].clear()
            self.chan_choices['Analogue channel'].addItems(self.rfsoc_args)
        elif newtype == 'MWG (WFTK) tones':
            self.chan_choices['Time step name'].clear()
            preferential_coms = [9, 10] # COM ports to put at the top of the list
            coms = list(range(30))
            coms = preferential_coms + list(set(coms) - set(preferential_coms))
            self.mwg_wftk_coms = [a for i in coms for a in ('COM{} A'.format(i), 'COM{} B'.format(i))]
            self.chan_choices['Time step name'].addItems(self.mwg_wftk_coms)
            reset_slot(self.chan_choices['Analogue type'].currentTextChanged[str], self.change_mr_anlg_type, False)
            self.chan_choices['Analogue type'].clear()
            self.chan_choices['Analogue type'].addItems(['MWG (WFTK) Parameter'])
            self.chan_choices['Analogue channel'].setEnabled(True)
            self.chan_choices['Analogue channel'].clear()
            self.chan_choices['Analogue channel'].addItems(self.mwg_wftk_args)
        elif newtype == 'MWG (Anritsu) tones':
            self.chan_choices['Time step name'].clear()
            self.mwg_anritsu_tones = ['{:0>4}'.format(i) for i in range(2000)]
            self.chan_choices['Time step name'].addItems(self.mwg_anritsu_tones)
            reset_slot(self.chan_choices['Analogue type'].currentTextChanged[str], self.change_mr_anlg_type, False)
            self.chan_choices['Analogue type'].clear()
            self.chan_choices['Analogue type'].addItems(['MWG (Anritsu) Parameter'])
            self.chan_choices['Analogue channel'].setEnabled(True)
            self.chan_choices['Analogue channel'].clear()
            self.chan_choices['Analogue channel'].addItems(self.mwg_anritsu_args)
        else:
            if  any(self.chan_choices['Analogue type'].currentText()==x for x in 
                        ['AWG Parameter', 'DDS Parameter','Hologram Parameter',
                         'MWG (WFTK) Parameter','MWG (Anritsu) Parameter']):
                self.chan_choices['Analogue type'].clear()
                self.chan_choices['Analogue type'].addItems(['Fast analogue', 'Slow analogue'])
                self.chan_choices['Analogue type'].currentTextChanged[str].connect(self.change_mr_anlg_type)
        if newtype == 'Other':
            self.chan_choices['Analogue channel'].setEnabled(False)
            self.chan_choices['Time step name'].clear()
            self.chan_choices['Time step name'].addItems(['Variable'])
        elif newtype == 'Time step length':
            self.chan_choices['Analogue channel'].setEnabled(False)
            self.chan_choices['Time step name'].clear()
            self.chan_choices['Time step name'].addItems(list(map(str.__add__, [str(i) for i in range(len(sht))],
                    [': '+hc[6][1].text for hc in sht]))) # time step names
        elif newtype == 'Analogue voltage':
            self.chan_choices['Time step name'].clear()
            self.chan_choices['Time step name'].addItems(list(map(str.__add__, [str(i) for i in range(len(sht))],
                    [': '+hc[6][1].text for hc in sht]))) # time step names
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

    def get_next_sequence(self, i=None):
        """Use the values in the multirun array to make the next
        sequence to run in the multirun. Uses saved mr_param not UI"""
        if i == None: i = self.ind # row index
        esc = self.mrtr.get_esc() # shorthand
        num_s = len(esc[2]) - 2 # number of steps
        try:
            for col in range(len(self.mr_vals[i])): # edit the sequence
                try:
                    val = float(self.mr_vals[i][col])
                    if self.mr_param['Type'][col] == 'Time step length':
                        for head in [2, 9]:
                            for t in self.mr_param['Time step name'][col]:
                                esc[head][t+2][3][1].text = str(val)
                    elif self.mr_param['Type'][col] == 'Analogue voltage':
                        for t in self.mr_param['Time step name'][col]:
                            for c in self.mr_param['Analogue channel'][col]:
                                if 'Fast' in self.mr_param['Analogue type'][col]:
                                    esc[6][t + c*num_s + 3][3][1].text = str(val)
                                else:
                                    esc[11][t + c*num_s + 3][3][1].text = str(val)
                except ValueError as e: pass # non-float variable
            self.mrtr.set_routine_name('Multirun ' + self.mr_param['Variable label'] + \
                    ': ' + self.mr_vals[i][0] + ' (%s / %s)'%(i+1, len(self.mr_vals)))
        except IndexError as e:
            error('Multirun failed to edit sequence at ' + self.mr_param['Variable label']
                + ' = ' + self.mr_vals[i][0] + '\n' + str(e))
        return self.mrtr.write_to_str()

    def get_all_sequences(self, save_dir=''):
        """Use the multirun array vals to make all of
        the sequences that will be used in the multirun, then
        store these as a list of XML strings."""
        self.msglist = []
        for i in range(len(self.mr_vals)):
            self.msglist.append(self.get_next_sequence(i))
        if not self.ss.isRunning():
            self.ss = sequenceSaver(self.mrtr, self.mr_vals, self.mr_param, save_dir)
            self.ss.start(self.ss.LowestPriority) # save the sequences
        else: # a backup if the first is busy saving sequences
            self.s2 = sequenceSaver(self.mrtr, self.mr_vals, self.mr_param, save_dir)
            self.s2.start(self.s2.LowestPriority)

    #### save and load parameters ####

    def view_mr_queue(self):
        """Show the window for editing the multirun queue, but close it after 10
        minutes so that it doesn't hold up multiruns"""
        self.queue_ui.updateList()
        self.QueueWindow.show()
        QTimer.singleShot(int(1e3*10*60), self.QueueWindow.close)
        

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
            try:
                with open(save_file_name, 'w+') as f:
                    f.write('Multirun list of variables:\n')
                    f.write(';'.join([','.join([vals[row][col] 
                        for col in range(len(vals[0]))]) for row in range(len(vals))]) + '\n')
                    f.write(';'.join(params.keys())+'\n')
                    f.write(';'.join(map(str, list(params.values()))))
            except (PermissionError, FileNotFoundError) as e:
                error("Couldn't save Multirun params to file: %s\n"%save_file_name+str(e))

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
                        if ((header[i] == 'Last time step run') | (header[i] == 'Last time step end')) & (self.last_step_lock_button.isChecked()):
                            warning('Did not load MR param {} as the last step lock button is checked.'.format(header[i]))
                        else:
                            self.ui_param[header[i]] = self.types[header[i]](params[i])
                    except ValueError as e:
                        error('Multirun editor could not load parameter: %s\n'%params[i]+str(e))
            # store values in case they're overwritten after setText()
            nrows, ncols = np.shape(vals) # update array of values
            col = int(self.col_index.text()) if self.col_index.text() else 0
            nhist, nomit = map(str, [self.ui_param['# in hist'], self.ui_param['# omitted']])
            runstep, endstep = self.ui_param['Last time step run'], self.ui_param['Last time step end']
            # then update the label edits
            for key in self.measures.keys(): # update variable label and measure
                reset_slot(self.measures[key].textChanged, self.update_all_stats, False)
                self.measures[key].setText(str(self.ui_param[key]))
                reset_slot(self.measures[key].textChanged, self.update_all_stats, True)
            self.set_chan_listbox(col if col < ncols else 0)
            self.rows_edit.setText(str(nrows)) # triggers change_array_size
            self.cols_edit.setText(str(ncols))
            self.change_array_size() # don't wait for it to be triggered
            self.reset_array(vals)
            self.nhist_edit.setText(nhist)
            self.omit_edit.setText(nomit)
            self.last_step_run_edit.setText(runstep) # triggers update_last_step
            self.last_step_end_edit.setText(endstep)
            for i in range(len(header)): # restore values as change_array_size loads defaults
                if header[i] in self.ui_param:
                    try:
                        if ((header[i] == 'Last time step run') | (header[i] == 'Last time step end')) & (self.last_step_lock_button.isChecked()):
                            pass
                        else:
                            self.ui_param[header[i]] = self.types[header[i]](params[i])
                    except ValueError as e: pass
            
    def check_mr_params(self, save_results_path='.'):
        """Check that the multirun parameters are valid before adding it to the queue"""
        if 'PyDex default empty sequence' in self.tr.get_routine_name():
            QMessageBox.warning(self, 'No sequence loaded', 
                'You must load a sequence before starting a multirun.')
            return 0
        results_path = os.path.join(save_results_path, self.ui_param['measure_prefix'])
        self.appending = False
        # first check if the measure folder already exists with some files in
        imax = -1
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
        except (FileNotFoundError, PermissionError): pass
        # then check the multirun queue
        for m in self.mr_queue:
            if self.ui_param['measure_prefix'] == m[0]['measure_prefix']:
                imax = max(imax, len(m[2]) + m[0]['1st hist ID'] - 1)
        
        if self.ui_param['1st hist ID'] == -1: # append at the end 
            self.appending = True
            self.ui_param['1st hist ID'] = imax + 1 if imax>=0 else 0
            
        if (os.path.isdir(results_path) or self.ui_param['measure_prefix'] in [
            x[0]['measure_prefix'] for x in self.mr_queue]) and imax >= self.ui_param['1st hist ID']:
            # this measure exists, check if user wants to overwrite
            reply = QMessageBox.question(self, 'Confirm Overwrite',
                "Results path already exists, do you want to overwrite the csv and dat files?\n"+results_path,
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if reply == QMessageBox.No:
                if self.appending: # if appending, reset ui_param to -1. Also happens at end of multirun in runid.py
                    self.measures['1st hist ID'].setText('') 
                    self.measures['1st hist ID'].setText('-1') 
                return 0
            # elif reply == QMessageBox.Yes:
            #     try:
            #         for fn in os.listdir(results_path):
            #             if '.csv' in fn or '.dat' in fn:
            #                 os.remove(os.path.join(results_path, fn))
            #     except Exception as e:
            #         warning('Multirun could not remove files from '+results_dir+'\n'+str(e))
        
        # parameters are valid, add to queue
        self.mr_queue.append([copy.deepcopy(self.ui_param), self.tr.copy(), self.get_table(), self.appending]) 
        if self.appending: # if appending, reset ui_param to -1. Also happens at end of multirun in runid.py
            self.measures['1st hist ID'].setText('') 
            self.measures['1st hist ID'].setText('-1') 
        if self.suggest_button.isChecked(): # suggest new multirun measure ID and prefix
            n = self.ui_param['measure'] + 1
            self.measures['measure'].setText(str(n))
            self.measures['measure_prefix'].setText('Measure'+str(n))  
        return 1
