"""PyDex Monitoring
Stefan Spence 27/05/20

A GUI displays the data as it's acquired, and collects statistics
from multiple traces.
More information on the DAQ is available at:
https://documentation.help/NI-DAQmx-Key-Concepts/documentation.pdf
We use the python module: https://nidaqmx-python.readthedocs.io
"""
import os
import re
import sys
import time 
import numpy as np
import pyqtgraph as pg
pg.setConfigOption('background', 'w') # set graph background default white
pg.setConfigOption('foreground', 'k') # set graph foreground default black        
from collections import OrderedDict
# some python packages use PyQt4, some use PyQt5...
try:
    from PyQt4.QtCore import pyqtSignal, QRegExp, QItemSelectionModel
    from PyQt4.QtGui import (QApplication, QPushButton, QWidget, QLabel, QAction,
            QGridLayout, QMainWindow, QMessageBox, QLineEdit, QIcon, QFileDialog,
            QMenu, QActionGroup, QFont, QTableWidget, QTableWidgetItem, QTabWidget, 
            QVBoxLayout, QDoubleValidator, QIntValidator, QRegExpValidator, 
            QComboBox, QListWidget) 
except ImportError:
    from PyQt5.QtCore import pyqtSignal, QRegExp, QItemSelectionModel
    from PyQt5.QtGui import (QIcon, QDoubleValidator, QIntValidator, QFont,
        QRegExpValidator)
    from PyQt5.QtWidgets import (QActionGroup, QVBoxLayout, QMenu, 
        QFileDialog, QMessageBox, QLineEdit, QGridLayout, QWidget,
        QApplication, QPushButton, QAction, QMainWindow, QTabWidget,
        QTableWidget, QTableWidgetItem, QLabel, QComboBox, QListWidget)
import logging
logger = logging.getLogger(__name__)
sys.path.append('.')
sys.path.append('..')
from strtypes import strlist, BOOL
from daqController import worker, remove_slot
from daqAnalysis import daqCollection
from networking.client import PyClient

double_validator = QDoubleValidator() # floats
int_validator    = QIntValidator()    # integers
int_validator.setBottom(0) # don't allow -ve numbers
bool_validator = QIntValidator(0,1)   # boolean, 0=False, 1=True


def channel_stats(text):
    """Convert a string list of channel settings into an 
    ordered dictionary: "[['Dev2/ai0', '', '1.0', '0.0', '0', '0', '0']]"
    -> OrderedDict([('Dev2/ai0', {'label':'', 'offset':1.0,
        'range':0, 'acquire':0, 'plot':0})])
    """
    d = OrderedDict()
    keys = ['label', 'scale', 'offset', 'range', 'acquire', 'plot']
    types = [str, float, float, float, BOOL, BOOL]
    for channel in map(strlist, re.findall("\[['\w,\s\./]+\]", text)):
        d[channel[0]] = OrderedDict([(keys[i], types[i](val)) 
                for i, val in enumerate(channel[1:])])
    return d

####    ####    ####    ####

def channel_str(channel_list):
    """Convert an ordered dictionary of channel settings
    into a string. Inverse operation of channel_stats()."""
    outstr = '['
    for key, d in channel_list.items():
        outstr += '['+key+', '+', '.join(map(str, d.values()))+'], '
    return outstr[:-2] + ']'

####    ####    ####    ####

class daq_window(QMainWindow):
    """Window to control and visualise DAQ measurements.
    Set up the desired channels with a given sampling rate.
    Start an acquisition after a trigger. 
    Display the acquired data on a trace, and accumulated
    data on a graph.
    
    Arguments:
    n       -- run number for synchronisation
    rate    -- max sample rate in samples / second
    dt      -- desired acquisition period in seconds
    config_file -- path to file storing default settings
    port    -- the port number to open for TCP connections
    """
    def __init__(self, n=0, rate=250, dt=500, config_file='monitor\\daqconfig.dat', port=8622):
        super().__init__()
        self.types = OrderedDict([('n', int), ('config_file', str), ('trace_file', str), ('graph_file', str),
            ('save_dir', str), ('Sample Rate (kS/s)',float), 
            ('Duration (ms)', float), ('Trigger Channel', str), ('Trigger Level (V)', float), 
            ('Trigger Edge', str), ('channels',channel_stats)])
        self.stats = OrderedDict([('n', n), ('config_file', config_file), ('trace_file', 'DAQtrace.csv'), 
            ('graph_file', 'DAQgraph.csv'),('save_dir', '.'), ('Sample Rate (kS/s)', rate), 
            ('Duration (ms)', dt), ('Trigger Channel', 'Dev2/ai1'), # /Dev2/PFI0
            ('Trigger Level (V)', 1.0), ('Trigger Edge', 'rising'), 
            ('channels', channel_stats("[['Dev2/ai0', '0', '1.0', '0.0', '5', '1', '1']]"))])
        self.trigger_toggle = True       # whether to trigger acquisition or just take a measurement
        self.slave = worker(rate*1e3, dt/1e3, self.stats['Trigger Channel'], 
                self.stats['Trigger Level (V)'], self.stats['Trigger Edge'], list(self.stats['channels'].keys()), 
                [ch['range'] for ch in self.stats['channels'].values()]) # this controls the DAQ
        self.dc = daqCollection(param=[], channels=list(self.stats['channels'].keys()))
        self.init_UI()
        self.load_config(config_file)    # load default settings          
        self.n_samples = int(self.stats['Duration (ms)'] * self.stats['Sample Rate (kS/s)']) # number of samples per acquisition
        self.last_path = './'

        self.x = [] # run numbers for graphing collections of acquired data
        self.y = [] # average voltages in slice of acquired trace 

        self.slave.acquired.connect(self.update_graph) # take average of slices
        self.slave.acquired.connect(self.update_trace) # plot new data when it arrives
        self.tcp = PyClient(port=port)
        remove_slot(self.tcp.dxnum, self.set_n, True)
        remove_slot(self.tcp.textin, self.respond, True)
        self.tcp.start()

    def init_UI(self):
        """Produce the widgets and buttons."""
        self.centre_widget = QWidget()
        self.tabs = QTabWidget()       # make tabs for each main display 
        self.centre_widget.layout = QVBoxLayout()
        self.centre_widget.layout.addWidget(self.tabs)
        self.centre_widget.setLayout(self.centre_widget.layout)
        self.setCentralWidget(self.centre_widget)
        
        # change font size
        font = QFont()
        font.setPixelSize(18)

        #### menubar at top gives options ####
        menubar = self.menuBar()

        # file menubar allows you to save/load data
        file_menu = menubar.addMenu('File')
        for label, function in [['Load Config', self.load_config],
                ['Save Config', self.save_config],
                ['Load Trace', self.load_trace], 
                ['Save Trace', self.save_trace], 
                ['Save Graph', self.save_graph]]:
            action = QAction(label, self) 
            action.triggered.connect(function)
            file_menu.addAction(action)

        #### tab for settings  ####
        settings_tab = QWidget()
        settings_grid = QGridLayout()
        settings_tab.setLayout(settings_grid)
        self.tabs.addTab(settings_tab, "Settings")

        self.settings = QTableWidget(1, 6)
        self.settings.setHorizontalHeaderLabels(['Duration (ms)', 
            'Sample Rate (kS/s)', 'Trigger Channel', 'Trigger Level (V)', 
            'Trigger Edge', 'Use Trigger?'])
        settings_grid.addWidget(self.settings, 0,0, 1,1)
        defaults = [str(self.stats['Duration (ms)']), str(self.stats['Sample Rate (kS/s)']), 
            self.stats['Trigger Channel'], str(self.stats['Trigger Level (V)']), 
            self.stats['Trigger Edge'], '1']
        validators = [double_validator, double_validator, None, double_validator, None, bool_validator]
        for i in range(6):
            table_item = QLineEdit(defaults[i]) # user can edit text to change the setting
            if defaults[i] == 'Sample Rate (kS/s)': table_item.setEnabled(False)
            table_item.setValidator(validators[i]) # validator limits the values that can be entered
            self.settings.setCellWidget(0,i, table_item)
        self.settings.resizeColumnToContents(1) 
        self.settings.setFixedHeight(70) # make it take up less space
        self.settings.cellWidget(0,0).textChanged.connect(self.check_slice_duration)
                    
        # start/stop: start waiting for a trigger or taking an acquisition
        self.toggle = QPushButton('Start', self)
        self.toggle.setCheckable(True)
        self.toggle.clicked.connect(self.activate)
        settings_grid.addWidget(self.toggle, 1,0, 1,1)

        # channels
        self.channels = QTableWidget(8, 7) # make table
        self.channels.setHorizontalHeaderLabels(['Channel', 'Label', 
            'Scale (X/V)', 'Offset (V)', 'Range', 'Acquire?', 'Plot?'])
        settings_grid.addWidget(self.channels, 2,0, 1,1) 
        validators = [None, double_validator, double_validator, None, bool_validator, bool_validator]
        for i in range(8):
            chan = 'Dev2/ai'+str(i)  # name of virtual channel
            table_item = QLabel(chan)
            self.channels.setCellWidget(i,0, table_item)
            if chan in self.stats['channels']: # load values from previous
                defaults = self.stats['channels'][chan]
            else: # default values when none are loaded
                defaults = channel_stats("[dummy, "+str(i)+", 1.0, 0.0, 5.0, 0, 0]")['dummy']
            for j, key in zip([0,1,2,4,5], ['label', 'scale', 'offset', 'acquire', 'plot']):
                table_item = QLineEdit(str(defaults[key]))
                if 'acquire' in key:
                    table_item.textChanged.connect(self.check_slice_channels)
                elif 'plot' in key:
                    table_item.textChanged.connect(self.set_acquire)
                table_item.setValidator(validators[j])        
                self.channels.setCellWidget(i,j+1, table_item)
            vrange = QComboBox() # only allow certain values for voltage range
            vrange.text = vrange.currentText # overload function so it's same as QLabel
            vrange.addItems(['%.1f'%x for x in self.slave.vrs])
            try: vrange.setCurrentIndex(self.slave.vrs.index(defaults['range']))
            except Exception as e: logger.error('Invalid channel voltage range\n'+str(e))
            self.channels.setCellWidget(i,4, vrange)

        #### Plot for most recently acquired trace ####
        trace_tab = QWidget()
        trace_grid = QGridLayout()
        trace_tab.setLayout(trace_grid)
        self.tabs.addTab(trace_tab, "Trace")
        
        # button activates horizontal line
        self.hline_toggle = QPushButton('Horizontal line', self, checkable=True)
        self.hline_toggle.clicked.connect(self.add_horizontal)
        trace_grid.addWidget(self.hline_toggle, 0,0, 1,1)
        self.hline_label = QLabel()
        trace_grid.addWidget(self.hline_label, 0,1, 1,1)
        fadeline_button = QPushButton('Persist', self)
        fadeline_button.clicked.connect(self.set_fadelines)
        trace_grid.addWidget(fadeline_button, 0,2, 1,1)
        

        # plot the trace
        self.trace_canvas = pg.PlotWidget()
        self.trace_legend = self.trace_canvas.addLegend()
        self.trace_canvas.getAxis('bottom').tickFont = font
        self.trace_canvas.getAxis('left').tickFont = font
        self.trace_canvas.setLabel('bottom', 'Time', 's', **{'font-size':'18pt'})
        self.trace_canvas.setLabel('left', 'Voltage', 'V', **{'font-size':'18pt'})
        self.lines = [] # handles for lines plotting the last measurement
        self.fadelines = [] # handles for previous measurement lines
        for i in range(8):
            chan = self.channels.cellWidget(i,1).text()
            self.lines.append(self.trace_canvas.plot([1], name=chan, 
                    pen=pg.mkPen(pg.intColor(i), width=3)))
            self.lines[i].hide()
            self.fadelines.append(self.trace_canvas.plot([1], 
                    pen=pg.mkPen(pg.intColor(i, alpha=50), width=2)))
            self.fadelines[i].hide()
        self.hline = pg.InfiniteLine(1., angle=0, pen='k', movable=True)
        self.trace_canvas.addItem(self.hline)
        self.hline.sigPositionChanged.connect(self.update_hline)
        self.hline.hide()
        
            
        trace_grid.addWidget(self.trace_canvas, 1,0, 1,3)
        
        #### Settings for slices of the trace accumulating into the graph ####
        slice_tab = QWidget()
        slice_grid = QGridLayout()
        slice_tab.setLayout(slice_grid)
        self.tabs.addTab(slice_tab, "Slice")
        
        # Buttons to add/remove slices and reset graph
        for i, (label, func) in enumerate([['Add slice', self.add_slice],
                ['Remove slice', self.del_slice], ['Reset graph', self.reset_graph]]):
            button = QPushButton(label, self)
            button.clicked.connect(func)
            slice_grid.addWidget(button, 0,i, 1,1)
        
        # parameters for slices
        self.slices = QTableWidget(0, 4) # make table
        self.slices.setHorizontalHeaderLabels(['Slice name', 
            'Start (ms)', 'End (ms)', 'Channels'])
        slice_grid.addWidget(self.slices, 1,0, 1,3) 

        #### Plot for graph of accumulated data ####
        graph_tab = QWidget()
        graph_grid = QGridLayout()
        graph_tab.setLayout(graph_grid)
        self.tabs.addTab(graph_tab, "Graph")

        self.mean_graph = pg.PlotWidget() # for plotting means
        self.stdv_graph = pg.PlotWidget() # for plotting standard deviations
        self.graph_legends = []
        for i, g in enumerate([self.mean_graph, self.stdv_graph]):
            g.getAxis('bottom').tickFont = font
            g.getAxis('bottom').setFont(font)
            g.getAxis('left').tickFont = font
            g.getAxis('left').setFont(font)
            graph_grid.addWidget(g, i,0, 1,1)
        self.reset_lines() # make a line for every slice channel
        self.stdv_graph.setLabel('bottom', 'Shot', '', **{'font-size':'18pt'})
        self.stdv_graph.setLabel('left', 'Standard Deviation', 'V', **{'font-size':'18pt'})
        self.mean_graph.setLabel('left', 'Mean', 'V', **{'font-size':'18pt'})
        
        #### tab for TCP message settings  ####
        tcp_tab = QWidget()
        tcp_grid = QGridLayout()
        tcp_tab.setLayout(tcp_grid)
        self.tabs.addTab(tcp_tab, "Sync")

        label = QLabel('Run number: ')
        tcp_grid.addWidget(label, 0,0, 1,1)
        self.n_edit = QLineEdit(str(self.stats['n']))
        self.n_edit.setValidator(int_validator)
        self.n_edit.textEdited[str].connect(self.set_n)
        tcp_grid.addWidget(self.n_edit, 0,1, 1,1)
        
        label = QLabel('Save directory: ')
        tcp_grid.addWidget(label, 1,0, 1,1)
        self.save_edit = QLineEdit(self.stats['save_dir'])
        self.save_edit.textEdited[str].connect(self.set_save_dir)
        tcp_grid.addWidget(self.save_edit, 1,1, 1,1)
        
        label = QLabel('Trace file name: ')
        tcp_grid.addWidget(label, 2,0, 1,1)
        self.trace_edit = QLineEdit(self.stats['trace_file'])
        self.trace_edit.textEdited[str].connect(self.set_trace_file)
        tcp_grid.addWidget(self.trace_edit, 2,1, 1,1)
        
        label = QLabel('Graph file name: ')
        tcp_grid.addWidget(label, 3,0, 1,1)
        self.graph_edit = QLineEdit(self.stats['graph_file'])
        self.graph_edit.textEdited[str].connect(self.set_graph_file)
        tcp_grid.addWidget(self.graph_edit, 3,1, 1,1)
        
        reset = QPushButton('Reset TCP client', self)
        reset.clicked.connect(self.reset_client)
        tcp_grid.addWidget(reset, 4,0, 1,1)

        #### Title and icon ####
        self.setWindowTitle('- NI DAQ Controller -')
        self.setWindowIcon(QIcon('docs/daqicon.png'))
        self.setGeometry(200, 200, 800, 600)

    #### user input functions ####

    def set_acquire(self):
        """If the user chooses to plot, set the same channel to acquire."""
        for i in range(self.channels.rowCount()):
            if BOOL(self.channels.cellWidget(i,6).text()): # plot
                self.channels.cellWidget(i,5).setText('1') # only plot if acquiring
    
    def check_settings(self):
        """Coerce the settings into allowed values."""
        statstr = "[[" # dictionary of channel names and properties
        for i in range(self.channels.rowCount()):
            self.trace_legend.items[i][1].setText(self.channels.cellWidget(i,1).text()) # label
            if BOOL(self.channels.cellWidget(i,5).text()): # acquire
                statstr += ', '.join([self.channels.cellWidget(i,j).text() 
                    for j in range(self.channels.columnCount())]) + '],['
        self.stats['channels'] = channel_stats(statstr[:-2] + ']')
        self.dc.channels = self.stats['channels'].keys()

        # acquisition settings
        self.stats['Duration (ms)'] = float(self.settings.cellWidget(0,0).text())
        # check that the requested rate is valid
        rate = float(self.settings.cellWidget(0,1).text())
        if len(self.stats['channels']) > 1 and rate > 245 / len(self.stats['channels']):
            rate = 245 / len(self.stats['channels'])
        elif len(self.stats['channels']) < 2 and rate > 250:
            rate = 250
        self.stats['Sample Rate (kS/s)'] = rate
        self.settings.cellWidget(0,1).setText('%.2f'%(rate))
        self.n_samples = int(self.stats['Duration (ms)'] * self.stats['Sample Rate (kS/s)'])
        # check the trigger channel is valid
        trig_chan = self.settings.cellWidget(0,2).text() 
        if 'Dev2/PFI' in trig_chan or 'Dev2/ai' in trig_chan:
            self.stats['Trigger Channel'] = trig_chan
        else: 
            self.stats['Trigger Channel'] = 'Dev2/ai0'
        self.settings.cellWidget(0,2).setText(str(self.stats['Trigger Channel']))
        self.stats['Trigger Level (V)'] = float(self.settings.cellWidget(0,3).text())
        self.stats['Trigger Edge'] = self.settings.cellWidget(0,4).text()
        self.trigger_toggle = BOOL(self.settings.cellWidget(0,5).text())
        
        
    def set_table(self):
        """Display the acquisition and channel settings in the table."""
        x = self.stats.copy() # prevent it getting overwritten
        for i in range(5):
            self.settings.cellWidget(0,i).setText(str(x[
                self.settings.horizontalHeaderItem(i).text()]))
        for i in range(8):
            ch = self.channels.cellWidget(i,0).text()
            if ch in x['channels']:
                for j, key in zip([0,1,2,4,5], 
                        ['label', 'scale', 'offset', 'acquire', 'plot']):
                    self.channels.cellWidget(i,j+1).setText(str(x['channels'][ch][key]))
                self.channels.cellWidget(i,4).setCurrentText('%.1f'%x['channels'][ch]['range'])
            else:
                self.channels.cellWidget(i,5).setText('0') # don't acquire
                self.channels.cellWidget(i,6).setText('0') # don't plot

    #### slice settings functions ####

    def add_slice(self, param=[]):
        """Add a row to the slice table and append it to the
        daqCollection instance for analysis.
        param -- [name, start (ms), end (ms), channels]"""
        try:
            name, start, end, channels = param
        except TypeError:
            name = 'Slice' + str(self.slices.rowCount())
            start = 0
            end = self.stats['Duration (ms)']
            channels = list(self.stats['channels'].keys())
        i = self.slices.rowCount() # index to add row at
        self.slices.insertRow(i) # add row to table
        validator = QDoubleValidator(0.,float(self.stats['Duration (ms)']),3)
        for j, text in enumerate([name, str(start), str(end)]):
            item = QLineEdit(text)
            item.pos = (i, j)
            if j > 0:
                item.setValidator(validator)
            item.textChanged.connect(self.update_slices)
            self.slices.setCellWidget(i, j, item)
        chanbox = QListWidget(self)
        chanbox.setSelectionMode(3) # extended selection, allows multiple selection
        chanbox.itemSelectionChanged.connect(self.update_slices)
        chanbox.pos = (i, 3)
        chanbox.text = chanbox.objectName
        chanlist = list(self.stats['channels'].keys())
        chanbox.addItems(chanlist)
        self.slices.setCellWidget(i, j+1, chanbox)
        self.slices.resizeRowToContents(i) 
        # add to the dc list of slices
        t = np.linspace(0, self.stats['Duration (ms)']/1000, self.n_samples)
        self.dc.add_slice(name, np.argmin(np.abs(t-start)), np.argmin(np.abs(t-end)), 
            OrderedDict([(chan, chanlist.index(chan)) for chan in channels]))
            
        self.reset_lines()
            

    def del_slice(self, toggle=True):
        """Remove the slice at the selected row of the slice table."""
        index = self.slices.currentRow()
        self.slices.removeRow(index)
        if index >= 0:
            self.dc.slices.pop(index)
        
    def check_slice_duration(self, newtxt):
        """If the acquisition duration is changed, make sure the slices can't
        use times beyond this."""
        self.check_settings() # update DAQ acquisition settings first
        for i in range(self.slices.rowCount()):
            for j in [1,2]: # force slice to be within max duration
                validator = QDoubleValidator(0.,float(self.stats['Duration (ms)']),3)
                self.slices.cellWidget(i, j).setValidator(validator)

    def check_slice_channels(self, newtxt):
        """If the channels that can be used for the acquisition are changed, 
        change the list widgets in the slice settings to match."""
        self.check_settings() # update DAQ acquisition settings first
        for i in range(self.slices.rowCount()):
            w = self.slices.cellWidget(i, 3) # widget shorthand
            selected = [w.row(x) for x in w.selectedItems()] # make record of selected channels
            w.clear()
            w.addItems(list(self.stats['channels'].keys()))
            for r in selected:
                try:
                    w.setCurrentRow(r, QItemSelectionModel.SelectCurrent)
                except Exception as e: pass

    def update_slices(self, newtxt=''):
        """Use the current item from the table to update the parameter for the slices."""
        try:
            w = self.sender()
            i, j = w.pos
            t = np.linspace(0, self.stats['Duration (ms)'], self.n_samples)
            x = self.dc.slices[i] # shorthand
            if j == 0: # name
                x.name = w.text()
            elif j == 1: # start (ms)
                x.i0 = np.argmin(np.abs(t-float(w.text())))
            elif j == 2: # end (ms)
                x.i1 = np.argmin(np.abs(t-float(w.text())))
            elif j == 3:
                x.channels = OrderedDict([(x.text(), w.row(x)) for x in w.selectedItems()])
                x.stats = OrderedDict([(chan, OrderedDict([
                    ('mean',[]), ('stdv',[])])) for chan in x.channels.keys()])
                self.reset_lines()
                self.reset_graph()
            x.inds = slice(x.i0, x.i1+1)
            x.size = x.i1 - x.i0
        except IndexError as e: pass # logger.error("Couldn't update slice.\n"+str(e))    

    #### TCP functions ####
    
    def set_n(self, num):
        """Receive the new run number to update to"""
        self.stats['n'] = int(num)
        self.n_edit.setText(str(num))
        
    def set_save_dir(self, directory):
        """Set the directory to save results to"""
        self.stats['save_dir'] = directory
        self.save_edit.setText(directory)
        
    def set_trace_file(self, fname):
        """Set the default name for trace files when they're saved."""
        self.stats['trace_file'] = fname
        self.trace_edit.setText(fname)
    
    def set_graph_file(self, fname):
        """Set the default name for graph files when they're saved."""
        self.stats['graph_file'] = fname
        self.graph_edit.setText(fname)
        
    def reset_client(self, toggle=True):
        """Stop the TCP client thread then restart it."""
        self.tcp.stop = True
        for i in range(100): # wait til it's stopped
            if not self.tcp.isRunning():
                break
            else: time.sleep(0.001)
        self.tcp.start() # restart
        
    def respond(self, msg=''):
        """Interpret a TCP message. For setting properties, the syntax is:
        value=property. E.g. 'Z:\Tweezer=save_dir'."""
        if 'save_dir' in msg: 
            self.set_save_dir(msg.split('=')[0])
        elif 'trace_file' in msg:
            self.set_trace_file(msg.split('=')[0])
        elif 'graph_file' in msg:
            self.set_graph_file(msg.split('=')[0])
        elif 'start' in msg and not self.toggle.isChecked():
            self.toggle.setChecked(True)
            self.activate()
        elif 'stop' in msg and self.toggle.isChecked():
            self.toggle.setChecked(False)
            self.activate()
        elif 'save trace' in msg:
            self.save_trace(os.path.join(self.stats['save_dir'], self.stats['trace_file']))
        elif 'save graph' in msg:
            self.save_graph(os.path.join(self.stats['save_dir'], self.stats['graph_file']))
        elif 'set fadelines' in msg:
            self.set_fadelines()
    
    #### acquisition functions #### 

    def activate(self, toggle=0):
        """Prime the DAQ task for acquisition if it isn't already running.
        Otherwise, stop the task running."""
        if self.toggle.isChecked():
            self.check_settings()
            self.slave = worker(self.stats['Sample Rate (kS/s)']*1e3, self.stats['Duration (ms)']/1e3, self.stats['Trigger Channel'], 
                self.stats['Trigger Level (V)'], self.stats['Trigger Edge'], list(self.stats['channels'].keys()), 
                [ch['range'] for ch in self.stats['channels'].values()])
            remove_slot(self.slave.acquired, self.update_trace, True)
            remove_slot(self.slave.acquired, self.update_graph, True)
            if self.trigger_toggle:
                # remove_slot(self.slave.finished, self.activate, True)
                self.slave.start()
                self.toggle.setText('Stop')
            else: 
                self.toggle.setChecked(False)
                self.slave.analogue_acquisition()
        else:
            # remove_slot(self.slave.finished, self.activate, False)
            self.slave.stop = True
            self.slave.quit()
            self.toggle.setText('Start')

    #### plotting functions ####

    def update_trace(self, data):
        """Plot the supplied data with labels on the trace canvas."""
        t = np.linspace(0, self.stats['Duration (ms)']/1000, self.n_samples)
        i = 0 # index to keep track of which channels have been plotted
        for j in range(8):
            ch = self.channels.cellWidget(j,0).text()
            l = self.lines[j] # shorthand
            if ch in self.stats['channels'] and self.stats['channels'][ch]['plot']:
                try:
                    l.setData(t, data[i])
                except Exception as e:
                    logger.error('DAQ trace could not be plotted.\n'+str(e))
                self.fadelines[j].show()
                l.show()
                self.trace_legend.items[j][0].show()
                self.trace_legend.items[j][1].show()
                i += 1
            else:
                l.hide()
                self.fadelines[j].hide()
                self.trace_legend.items[j][0].hide()
                self.trace_legend.items[j][1].hide()
        self.trace_legend.resize(0,0)
        
    def set_fadelines(self):
        """Take the data from the current lines and sets it to the fadelines."""
        for j in range(8):
            ch = self.channels.cellWidget(j,0).text()
            l = self.lines[j] # shorthand
            if ch in self.stats['channels'] and self.stats['channels'][ch]['plot']:
                try:
                    self.fadelines[j].setData(l.xData, l.yData)
                except Exception as e:
                    logger.error('DAQ trace could not be plotted.\n'+str(e))
                self.fadelines[j].show()
            else:
                self.fadelines[j].hide()
        
    def reset_lines(self):
        """Clear the mean and stdv graphs, reset the legends, then make new 
        lines for each of the slice channels."""
        for legend in self.graph_legends: # reset the legends
            try:
                legend.scene().removeItem(legend)
            except AttributeError: pass
        for g in [self.mean_graph, self.stdv_graph]:
            g.clear()
            g.lines = OrderedDict([])
            self.graph_legends.append(g.addLegend())
            i = 0
            for s in self.dc.slices:
                for chan, val in s.stats.items():
                    g.lines[s.name+'/'+chan] = g.plot([1], name=s.name+'/'+chan, 
                        pen=None, symbol='o', symbolPen=pg.mkPen(pg.intColor(i)),
                        symbolBrush=pg.intColor(i)) 
                    i += 1

    def reset_graph(self):
        """Reset the collection of slice data, then replot the graph."""
        self.dc.reset_arrays()
        self.update_graph()

    def update_graph(self, data=[]):
        """Extract averages from slices of the data.
        Replot the stored data accumulated from averages in slices
        of the measurements."""
        if np.size(data):
            self.dc.process(data, self.stats['n'])
        for s in self.dc.slices:
            for chan, val in s.stats.items():
                self.mean_graph.lines[s.name+'/'+chan].setData(self.dc.runs, val['mean'])
                self.stdv_graph.lines[s.name+'/'+chan].setData(self.dc.runs, val['stdv'])
                
    def add_horizontal(self, toggle=True):
        """Display a horizontal line on the trace"""
        if toggle: self.hline.show()
        else: 
            self.hline.hide()
            self.hline_label.setText('')
        
    def update_hline(self):
        """Display the value of the horizontal line in the label"""
        self.hline_label.setText(str(self.hline.value()))

    #### save/load functions ####

    def try_browse(self, title='Select a File', file_type='all (*)', 
                open_func=QFileDialog.getOpenFileName, default_path=''):
        """Open a file dialog and retrieve a file name from the browser.
        title: String to display at the top of the file browser window
        default_path: directory to open first
        file_type: types of files that can be selected
        open_func: the function to use to open the file browser"""
        default_path = default_path if default_path else os.path.dirname(self.last_path)
        try:
            if 'PyQt4' in sys.modules:
                file_name = open_func(self, title, default_path, file_type)
            elif 'PyQt5' in sys.modules:
                file_name, _ = open_func(self, title, default_path, file_type)
            if type(file_name) == str: self.last_path = file_name 
            return file_name
        except OSError: return '' # probably user cancelled

    def save_config(self, file_name='daqconfig.dat'):
        """Save the current acquisition settings to the config file."""
        self.stats['config_file'] = file_name if file_name else self.try_browse(
                'Save Config File', 'dat (*.dat);;all (*)', QFileDialog.getSaveFileName)
        try:
            with open(self.stats['config_file'], 'w+') as f:
                for key, val in self.stats.items():
                    if key == 'channels':
                        f.write(key+'='+channel_str(val)+'\n')
                    else:
                        f.write(key+'='+str(val)+'\n')
            logger.info('DAQ config saved to '+self.stats['config_file'])
        except Exception as e: 
            logger.error('DAQ settings could not be saved to config file.\n'+str(e))

    def load_config(self, file_name='daqconfig.dat'):
        """Load the acquisition settings from the config file."""
        self.stats['config_file'] = file_name if file_name else self.try_browse(file_type='dat (*.dat);;all (*)')
        try:
            with open(self.stats['config_file'], 'r') as f:
                for line in f:
                    if len(line.split('=')) == 2:
                        key, val = line.replace('\n','').split('=') # there should only be one = per line
                        try:
                            self.stats[key] = self.types[key](val)
                        except KeyError as e:
                            logger.warning('Failed to load DAQ default config line: '+line+'\n'+str(e))
            self.set_table() # make sure the updates are displayed
            self.set_n(self.stats['n'])
            self.set_save_dir(self.stats['save_dir'])
            self.set_trace_file(self.stats['trace_file'])
            self.set_graph_file(self.stats['graph_file'])
            self.dc.channels = list(self.stats['channels'].keys())
            logger.info('DAQ config loaded from '+self.stats['config_file'])
        except FileNotFoundError as e: 
            logger.warning('DAQ settings could not find the config file.\n'+str(e))

    def save_trace(self, file_name=''):
        """Save the data currently displayed on the trace to a csv file."""
        file_name = file_name if file_name else self.try_browse(
                'Save File', 'csv (*.csv);;all (*)', QFileDialog.getSaveFileName)
        if file_name:
            # metadata
            header = ', '.join(list(self.stats.keys())) + '\n'
            header += ', '.join(list(map(str, self.stats.values()))[:-1]
                ) + ', ' + channel_str(self.stats['channels']) + '\n'
            # determine which channels are in the plot
            header += 'Time (s)'
            data = []
            for key, d in self.stats['channels'].items():
                if d['plot']:
                    header += ', ' + key # column headings
                    if len(data) == 0: # time (s)
                        data.append(self.lines[int(key[-1])].xData)
                    data.append(self.lines[int(key[-1])].yData) # voltage
            # data converted to the correct type
            out_arr = np.array(data).T
            try:
                np.savetxt(file_name, out_arr, fmt='%s', delimiter=',', header=header)
                logger.info('DAQ trace saved to '+file_name)
            except (PermissionError, FileNotFoundError) as e:
                logger.error('DAQ controller denied permission to save file: \n'+str(e))

    def load_trace(self, file_name=''):
        """Load data for the current trace from a csv file."""
        file_name = file_name if file_name else self.try_browse(file_type='csv(*.csv);;all (*)')
        if file_name:
            head = [[],[],[]] # get metadata
            with open(file_name, 'r') as f:
                for i in range(3):
                    row = f.readline()
                    if row[:2] == '# ':
                        head[i] = row[2:].replace('\n','').split(', ')
            # apply the acquisition settings from the file
            labels = [self.settings.horizontalHeaderItem(i).text() for 
                i in range(self.settings.columnCount())]
            for i in range(len(head[0])):
                try:
                    j = labels.index(head[0][i])
                    self.settings.cellWidget(0,j).setText(head[1][i])
                except ValueError: pass
            self.stats['channels'] = channel_stats(', '.join(head[1][7:]))
            for i in range(8): # whether to plot or not
                ch = self.channels.cellWidget(i,0).text()
                if ch in head[2]:
                    self.channels.cellWidget(i,6).setText('1')
                    self.channels.cellWidget(i,1).setText(self.stats['channels'][ch]['label'])
                else: self.channels.cellWidget(i,6).setText('0')
            self.check_settings()

            # plot the data
            data = np.genfromtxt(file_name, delimiter=',', dtype=float)
            if np.size(data) < 2:
                return 0 # insufficient data to load
            self.update_trace(data.T[1:])

    def save_graph(self, file_name=''):
        """Save the data accumulated from several runs that's displayed in the
        graph into a csv file."""
        file_name = file_name if file_name else self.try_browse(
                'Save File', 'csv (*.csv);;all (*)', QFileDialog.getSaveFileName)
        if file_name:
            self.dc.save(file_name, list(self.stats.keys()), 
                list(map(str, self.stats.values()))[:-1]
                 + [channel_str(self.stats['channels'])])
            logger.info('DAQ graph saved to '+file_name)
        
    def closeEvent(self, event):
        """Before closing, try to save the config settings to file."""
        statstr = "[[" # dictionary of channel names and properties
        for i in range(self.channels.rowCount()):
            statstr += ', '.join([self.channels.cellWidget(i,j).text() 
                    for j in range(self.channels.columnCount())]) + '],['
        self.stats['channels'] = channel_stats(statstr[:-2] + ']')
        # add all channels to stats
        self.save_config(self.stats['config_file'])
        event.accept()
                
####    ####    ####    #### 

def run():
    """Initiate an app to run the program
    if running in Pylab/IPython then there may already be an app instance"""
    app = QApplication.instance()
    standalone = app is None # false if there is already an app instance
    if standalone: # if there isn't an instance, make one
        app = QApplication(sys.argv) 
        
    win = daq_window()
    win.show()
    if standalone: # if an app instance was made, execute it
        sys.exit(app.exec_()) # when the window is closed, the python code also stops
            
if __name__ == "__main__":
    run()