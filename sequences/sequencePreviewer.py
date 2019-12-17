
"""Networking - Sequence Previewer
Stefan Spence 17/12/19

 - Preview DExTer sequences and facilitate loading/saving
The functions here are specific to the format of 
sequences that DExTer generates.

Note: to make it faster we could use xml.dom.minidom 
instead of python dictionaries. Since LabVIEW uses
some unicode characters, would need to parse it like
with open('filename', 'r') as f:
 dm = xml.dom.minidom.parseString(f.read().replace('\n','').replace('\t','').encode('utf-8'))
"""
import sys
import numpy as np
try:
    from PyQt4.QtCore import QThread, pyqtSignal, QEvent, QRegExp, QTimer
    from PyQt4.QtGui import (QApplication, QPushButton, QWidget, QLabel, 
        QAction, QGridLayout, QMainWindow, QMessageBox, QLineEdit, QIcon, 
        QFileDialog, QDoubleValidator, QIntValidator, QComboBox, QMenu, 
        QActionGroup, QTabWidget, QVBoxLayout, QFont, QRegExpValidator, 
        QInputDialog, QScrollArea) 
except ImportError:
    from PyQt5.QtCore import QThread, pyqtSignal, QEvent, QRegExp, QTimer
    from PyQt5.QtGui import (QIcon, QDoubleValidator, QIntValidator, 
        QFont, QRegExpValidator)
    from PyQt5.QtWidgets import (QApplication, QPushButton, QWidget, 
        QTabWidget, QAction, QMainWindow, QLabel, QInputDialog, QGridLayout,
        QMessageBox, QLineEdit, QFileDialog, QComboBox, QActionGroup, QMenu,
        QVBoxLayout, QScrollArea)
from translator import translate
from multirunEditor import multirun_widget
import logging
logger = logging.getLogger(__name__)


def bl(string):
    """Convert a string of a boolean to a boolean.
    This corrects for bool('0')=True."""
    try: return bool(int(string))
    except ValueError: return bool(string)


#### #### Edit sequences #### ####

# class Editor(QMainWindow):
#     """Provide a GUI for quickly editing DExTer sequences.
#     """
#     def __init__(self, num_steps=1):
#         super().__init__()
#         self.tr = translate(num_steps)
#         self.pre = Previewer(self.tr)
#         self.init_UI()

#     def make_label_edit(self, label_text, layout, position=[0,0, 1,1],
#             default_text='', validator=None):
#         """Make a QLabel with an accompanying QLineEdit and add them to the 
#         given layout with an input validator. The position argument should
#         be [row number, column number, row width, column width]."""
#         label = QLabel(label_text, self)
#         layout.addWidget(label, *position)
#         line_edit = QLineEdit(self)
#         if np.size(position) == 4:
#             position[1] += 1
#         layout.addWidget(line_edit, *position)
#         line_edit.setText(default_text) 
#         line_edit.setValidator(validator)
#         return label, line_edit
        
#     def init_UI(self):
#         """Create all of the widget objects required"""
#         self.centre_widget = QWidget()
#         self.centre_widget.layout = QGridLayout()
#         self.centre_widget.setLayout(self.centre_widget.layout)
#         self.setCentralWidget(self.centre_widget)
        
#         #### validators for user input ####
#         # reg_exp = QRegExp(r'([0-9]+(\.[0-9]+)?,?)+')
#         # comma_validator = QRegExpValidator(reg_exp) # floats and commas
#         double_validator = QDoubleValidator() # floats
#         int_validator = QIntValidator()       # integers
        
#         #### menubar at top gives options ####
#         # menubar = self.menuBar()
#         # show_windows = menubar.addMenu('Windows')
#         # menu_items = []
#         # for window_title in ['Image Analyser', 'Camera Status', 
#         #     'Image Saver', 'Monitoring']:
#         #     menu_items.append(QAction(window_title, self)) 
#         #     menu_items[-1].triggered.connect(self.show_window)
#         #     show_windows.addAction(menu_items[-1])

#         #### choose event indices ####
#         # by name
#         # by index
#         self.make_label_edit('Event index', self.centre_widget.layout, 
#             position=[1,0, 1,1], default_text='0', validator=int_validator)
        
#         #### choose channel ####
#         self.make_label_edit('Channel', self.centre_widget.layout, 
#             position=[2,0, 1,1], default_text='')

#         #### choose new value ####
#         self.make_label_edit('New value', self.centre_widget.layout, 
#             position=[3,0, 1,1], default_text='0', validator=double_validator)

#         #### preview sequence ####
#         self.preview_button = QPushButton('Preview sequence', self)
#         self.preview_button.resize(self.preview_button.sizeHint())
#         self.preview_button.clicked.connect(self.pre.show)
#         self.centre_widget.layout.addWidget(self.preview_button, 5,0, 1,1)

#         #### save to file ####
        
#         #### choose main window position and dimensions: (xpos,ypos,width,height)
#         self.setGeometry(60, 60, 900, 800)
#         self.setWindowTitle('DExTer Sequence Editor')
#         self.setWindowIcon(QIcon('docs/translatoricon.png'))

#### #### Preview sequences #### ####

class Previewer(QMainWindow):
    """Provide a display of a sequence, reminiscent
    of DExTer main view.
    """
    def __init__(self, tr=translate()):
        super().__init__()
        self.tr = tr
        self.init_UI()
        # self.set_sequence() # this function is slow...

    def label_pair(self, label_text, layout, pos1=[0,0, 1,1],
            pos2=[0,1, 1,1], default_text=''):
        """Make a QLabel pair and add them to the 
        given layout . The position argument should
        be [row number, column number, row width, column width]."""
        label1 = QLabel(label_text, self)
        label1.setStyleSheet('border: 1px solid black')
        label1.setFixedWidth(200)
        layout.addWidget(label1, *pos1)
        label2 = QLabel(default_text, self)
        label2.setStyleSheet('border: 1px solid black')
        layout.addWidget(label2, *pos2)
        return label1, label2

    def position(self, list0, arr1, i0r, i0c, i1r, i1c, layout,
            step0=1, step1=1, size0=[1,1], size1=[1,1],
            dimn=1, transpose=0):
        """Generate a new Qlabel with text from list1 and position
        it in layout at rows j descending down from i0r in steps of
        step0 at column i0c. The Qlabel will take up 
        size0 = [rows, columns]. 
        For each row position widgets from arr1 at row j+i1r 
        starting from column i1c in steps step1. The widgets take up 
        size1 = [rows,columns].
        dimn: arr1 has shape (# steps, # channels, dimn):
            iterate over the widgets in the last dimension of arr1
            placing them in successive columns.
        transpose: arr1 has shape (# channels, # steps, dimn)"""
        for i, text in enumerate(list0):
            label = QLabel(text, self)
            label.setStyleSheet('border: 1px solid black')
            label.setFixedWidth(200)
            layout.addWidget(label, i0r + i*step0, i0c, *size0)
            arr = arr1[:,i] if not transpose else arr1[i]
            for j, widgets in enumerate(arr):
                for k in range(dimn):
                    widgets[k].setStyleSheet('border: 1px solid black')
                    widgets[k].setFixedWidth(80*size1[1])
                    layout.addWidget(widgets[k], 
                        i1r + i*step0, i1c + j*step1 + k, *size1)
            yield label

    def init_UI(self):
        """Create all of the widget objects required"""
        self.centre_widget = QWidget()
        self.tabs = QTabWidget()       # make tabs for each main display 
        self.centre_widget.layout = QVBoxLayout()
        self.centre_widget.layout.addWidget(self.tabs)
        self.centre_widget.setLayout(self.centre_widget.layout)
        self.setCentralWidget(self.centre_widget)
        
        
        num_e = len(self.tr.seq_dic['Event list array in'])
        num_s = len(self.tr.seq_dic['Experimental sequence cluster in']['Sequence header top'])
        menubar = self.menuBar()

        # save/load a sequence file
        menubar.clear() # prevents recreating menubar if init_UI() is called again 
        file_menu = menubar.addMenu('File')
        load = QAction('Load Sequence', self) 
        load.triggered.connect(self.load_seq_from_file)
        file_menu.addAction(load)
        prev = QAction('Preview Sequence', self) 
        prev.triggered.connect(self.load_seq_from_file)
        file_menu.addAction(prev)
        loadpre = QAction('Load and Preview Sequence', self) 
        loadpre.triggered.connect(self.load_seq_from_file)
        file_menu.addAction(loadpre)
        save = QAction('Save Sequence', self) 
        save.triggered.connect(self.save_seq_file)
        file_menu.addAction(save)
        
        #### tab for previewing sequences ####
        preview_tab = QWidget()
        prv_layout = QVBoxLayout()
        preview_tab.setLayout(prv_layout)
        scroll_widget = QWidget()
        prv_layout.addWidget(scroll_widget)
        prv_grid = QGridLayout()
        scroll_widget.setLayout(prv_grid)
        self.tabs.addTab(preview_tab, "Sequence")

        # position the widgets on the layout:
        i=0 # index to separate label positions
        # metadata
        _, self.routine_name = self.label_pair(
            'Routine name: ', prv_grid,
            [i,0, 1,2], [i,2, 1,2*num_s])
        _, self.routine_desc = self.label_pair(
            'Routine description: ', prv_grid,
            [i+1,0, 1,2], [i+1,2, 1,2*num_s])
        self.routine_desc.setWordWrap(True)

        # list of event descriptions
        self.e_list = np.array([[[QLabel(self)] for ii in range(4)] 
            for iii in range(num_e)]) # event list
        _ = [x for x in self.position(['Event name: ', 
            'Routine specific event? ', 'Event indices: ', 'Event path: '], 
            self.e_list, i0r=i+2, i0c=0, i1r=i+2, i1c=2, size0=[1,2],
            step1=2, size1=[1,2], layout=prv_grid)]
        
        # event header top 
        header_items = ['Skip Step: ', 'Event name: ', 'Hide event steps: ', 
            'Event ID: ', 'Time step name: ', 'Populate multirun: ',
            'Time step length: ', 'Time unit: ', 'D/A trigger: ',
            'Trigger this time step? ', 'Channel: ', 'Analogue voltage (V): ',
            'GPIB event name: ', 'GPIB on/off? ']
        i += 7
        self.head_top = np.array([[[QLabel(self)] for ii in 
            range(len(header_items))] for iii in range(num_s)])
        _ = [x for x in self.position(header_items, self.head_top,
            i0r=i, i0c=0, i1r=i, i1c=2, layout=prv_grid, 
            size0=[1,2], step1=2, size1=[1,2])]
            
        # fast digital channels
        i += len(header_items)
        fd_head = QLabel('FD', self) 
        prv_grid.addWidget(fd_head, i,0, 1,1)
        self.fd_chans = np.array([[[QLabel(self)] for ii in 
            range(self.tr.nfd)] for iii in range(num_s)])
        self.fd_names = [x for x in self.position(['']*self.tr.nfd, self.fd_chans,
            i0r=i+1, i0c=0, i1r=i+1, i1c=2, layout=prv_grid, 
            step1=2, size1=[1,2])]
            
        # fast analogue channels
        i += self.tr.nfd+1
        fa_head = QLabel('FA', self) 
        prv_grid.addWidget(fa_head, i,0, 1,1)
        self.fa_chans = np.array([[[QLabel('0', self), QLabel(self)] for ii in 
            range(num_s)] for iii in range(self.tr.nfa)]) 
        self.fa_names = [x for x in self.position(['']*self.tr.nfa, self.fa_chans, i0r=i+1, 
            i0c=0, i1r=i+1, i1c=2, step1=2, layout=prv_grid, dimn=2,
            transpose=1)]

        # event header middle
        i += self.tr.nfa+1
        self.head_mid = np.array([[[QLabel(self)] for ii in 
            range(len(header_items))] for iii in range(num_s)])
        _ = [x for x in self.position(header_items, self.head_mid,
            i0r=i, i0c=0, i1r=i, i1c=2, layout=prv_grid,
             size0=[1,2], step1=2, size1=[1,2])]

        # slow digital channels
        i += len(header_items)
        sd_head = QLabel('SD', self) 
        prv_grid.addWidget(sd_head, i,0, 1,1)
        self.sd_chans = np.array([[[QLabel(self)] for ii in 
            range(self.tr.nsd)] for iii in range(num_s)])
        self.sd_names = [x for x in self.position(['']*self.tr.nsd, self.sd_chans,
            i0r=i+1, i0c=0, i1r=i+1, i1c=2, layout=prv_grid, 
            step1=2, size1=[1,2])]
        
        # slow analogue channels
        i += self.tr.nsd+1
        sa_head = QLabel('SA', self) 
        prv_grid.addWidget(sa_head, i,0, 1,1)
        self.sa_chans = np.array([[[QLabel('0', self), QLabel(self)] for ii in 
            range(num_s)] for iii in range(self.tr.nsa)])
        self.sa_names = [x for x in self.position(['']*self.tr.nsa, self.sa_chans, i0r=i+1, 
            i0c=0, i1r=i+1, i1c=2, step1=2, layout=prv_grid, dimn=2,
            transpose=1)]

        # set default of digital channels to false = red.
        for chan in np.append(self.fd_chans.flatten(), self.sd_chans.flatten()):
            chan.setStyleSheet('background-color: red; border: 1px solid black') 

        # place scroll bars if the contents of the window are too large
        scroll = QScrollArea(self)
        scroll.setWidget(scroll_widget)
        scroll.setWidgetResizable(True)
        scroll.setFixedHeight(800)
        prv_layout.addWidget(scroll)

        #### tab for multi-run settings ####
        self.mr = multirun_widget(self.tr)
        self.tabs.addTab(self.mr, "Multirun")
        
        # choose main window position and dimensions: (xpos,ypos,width,height)
        self.setGeometry(60, 60, 1000, 800)
        self.setWindowTitle('Sequence Preview')
        self.setWindowIcon(QIcon('docs/previewicon.png'))

    def try_browse(self, title='Select a File', file_type='all (*)', 
                open_func=QFileDialog.getOpenFileName):
        """Open a file dialog and retrieve a file name from the browser.
        title: String to display at the top of the file browser window
        default_path: directory to open first
        file_type: types of files that can be selected
        open_func: the function to use to open the file browser"""
        try:
            if 'PyQt4' in sys.modules:
                file_name = open_func(self, title, '', file_type)
            elif 'PyQt5' in sys.modules:
                file_name, _ = open_func(self, title, '', file_type)
            return file_name
        except OSError: return '' # probably user cancelled

    def load_seq_from_file(self):
        """Open a file dialog to choose a file to load a new sequence from, 
        load the sequence and then show it in the previewer."""
        fname = self.try_browse(file_type='XML (*.xml);;all (*)')
        if fname:
            if self.sender().text() == 'Load Sequence' or self.sender().text() == 'Load and Preview Sequence':
                self.tr.load_xml(fname)
            elif self.sender().text() == 'Load and Preview Sequence' or self.sender().text() == 'Preview Sequence':
                QMessageBox.information(self, 'Setting Sequence...', 'Please be patient as the sequence can take several seconds to load')
                self.init_UI()
                self.set_sequence()

    def save_seq_file(self):
        """Open a file dialog to choose a file name to save the current sequence to"""
        if fname:
            fname = self.try_browse(title='Choose a file name', 
                file_type='XML (*.xml);;all (*)', open_func=QFileDialog.getSaveFileName)
            self.tr.write_to_file(fname)

    def set_sequence(self):
        """Fill the labels with the values from the sequence"""
        seq = self.tr.seq_dic
        self.routine_name.setText(seq['Routine name in'])
        self.routine_desc.setText(seq['Routine description in'])
        ela = seq['Event list array in'] # shorthand
        esc = seq['Experimental sequence cluster in']
        for i in range(self.tr.nfd):
            name = esc['Fast digital names']['Name'][i] if esc['Fast digital names']['Name'][i] else ''
            self.fd_names[i].setText(esc['Fast digital names']['Hardware ID'][i]
                + ': ' + name)
        for i in range(self.tr.nfa):
            name = esc['Fast analogue names']['Name'][i] if esc['Fast analogue names']['Name'][i] else ''
            self.fa_names[i].setText(esc['Fast analogue names']['Hardware ID'][i]
                + ': ' + name)
        for i in range(self.tr.nsd):
            name = esc['Slow digital names']['Name'][i] if esc['Slow digital names']['Name'][i] else ''
            self.sd_names[i].setText(esc['Slow digital names']['Hardware ID'][i]
                + ': ' + name)
        for i in range(self.tr.nsa):
            name = esc['Slow analogue names']['Name'][i] if esc['Slow analogue names']['Name'][i] else ''
            self.sa_names[i].setText(esc['Slow analogue names']['Hardware ID'][i]
                + ': ' + name)
        for i in range(len(ela)):
            self.e_list[i][0][0].setText(ela[i]['Event name'])
            self.e_list[i][1][0].setText(str(ela[i]['Routine specific event?']))
            self.e_list[i][2][0].setText(','.join(map(str, ela[i]['Event indices'])))
            self.e_list[i][3][0].setText(ela[i]['Event path'])
        for i in range(len(esc['Sequence header top'])):
            for j, key in enumerate(['Skip Step', 'Event name', 'Hide event steps', 
                    'Event ID', 'Time step name', 'Populate multirun', 'Time step length', 
                    'Time unit', 'Digital or analogue trigger?', 'Trigger this time step?', 
                    'Channel', 'Analogue voltage (V)', 'GPIB event name', 'GPIB on/off?']):
                self.head_top[i][j][0].setText(str(esc['Sequence header top'][i][key]))
                self.head_mid[i][j][0].setText(str(esc['Sequence header middle'][i][key]))
            for j in range(self.tr.nfd):
                self.fd_chans[i][j][0].setStyleSheet('background-color: '
                    + 'green' if bl(esc['Fast digital channels'][i][j]) else 'red' 
                    + '; border: 1px solid black') 
            for j in range(self.tr.nfa):
                self.fa_chans[j][i][0].setText(str(esc['Fast analogue array'][j]['Voltage'][i]))
                self.fa_chans[j][i][1].setText(
                    'Ramp' if bl(esc['Fast analogue array'][j]['Ramp?'][i]) else '')
            for j in range(self.tr.nsd):
                self.sd_chans[i][j][0].setStyleSheet('background-color: '
                    + 'green' if bl(esc['Slow digital channels'][i][j]) else 'red' 
                    + '; border: 1px solid black') 
            for j in range(self.tr.nsa):
                self.sa_chans[j][i][0].setText(str(esc['Slow analogue array'][j]['Voltage'][i]))
                self.sa_chans[j][i][1].setText(
                    'Ramp' if bl(esc['Slow analogue array'][j]['Ramp?'][i]) else '')




    def choose_multirun_dir(self):
        """Allow the user to choose the directory where the histogram .csv
        files and the measure .dat file will be saved as part of the multi-run"""
        default_path = self.get_default_path()
        try:
            dir_path = QFileDialog.getExistingDirectory(self, "Select Directory", default_path)
            self.multirun_save_dir.setText(dir_path)
        except OSError:
            pass # user cancelled - file not found
        

####    ####    ####    #### 

def run():
    """Initiate an app to run the program
    if running in Pylab/IPython then there may already be an app instance"""
    app = QApplication.instance()
    standalone = app is None # false if there is already an app instance
    if standalone: # if there isn't an instance, make one
        app = QApplication(sys.argv) 
        
    boss = Previewer()
    boss.show()
    if standalone: # if an app instance was made, execute it
        sys.exit(app.exec_()) # when the window is closed, the python code also stops
   
if __name__ == "__main__":
    run()