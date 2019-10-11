"""Sequence Translator
Stefan Spence 04/10/19

 - translate DExTer sequences to/from json
 - create a GUI to facilitate editing sequences
"""
import json
import sys
import numpy as np
try:
    from PyQt4.QtCore import QThread, pyqtSignal, QEvent, QRegExp, QTimer
    from PyQt4.QtGui import (QApplication, QPushButton, QWidget, QLabel, 
        QAction, QGridLayout, QMainWindow, QMessageBox, QLineEdit, QIcon, 
        QFileDialog, QDoubleValidator, QIntValidator, QComboBox, QMenu, 
        QActionGroup, QTabWidget, QVBoxLayout, QFont, QRegExpValidator, 
        QInputDialog) 
except ImportError:
    from PyQt5.QtCore import QThread, pyqtSignal, QEvent, QRegExp, QTimer
    from PyQt5.QtGui import (QIcon, QDoubleValidator, QIntValidator, 
        QFont, QRegExpValidator)
    from PyQt5.QtWidgets import (QApplication, QPushButton, QWidget, 
        QTabWidget, QAction, QMainWindow, QLabel, QInputDialog, QGridLayout,
        QMessageBox, QLineEdit, QFileDialog, QComboBox, QActionGroup, QMenu,
        QVBoxLayout)


#### #### DExTer clusters #### ####

def event_list():
    """Define a dictionary for DExTer's event
    list cluster since it's used several times."""
    return {'Event name':'',
            'Routine specific event?':False,
            'Event indices':[],
            'Event path':''}

def header_cluster():
    """Define a dictionary for DExTer's matrix header
    cluster since it's used several times."""
    return {'Skip step':False,
            'Event name':'',
            'Hide event steps':False,
            'Event ID':'',
            'Time step name':'',
            'Populate multirun':False,
            'Time step length':1,
            'Time unit':1,
            'Trigger details':{
                'Digital trigger or analogue trigger?':0,
                'Trigger this time step?':False,
                'Channel':0,
                'Analogue voltage':0},
            'GPIB routine data':{
                'GPIB event name':0,
                'GPIB on/off':False}}

def channel_names(length, values=None):
    """Define a dictionary for DExTer's channel names cluster
    since it's used several times. Can be initialised with 
    items but take care to give them the right length:
    values = [[hardware IDs],[names]]"""
    if not values:
        return {'Hardware ID':['']*length,
                'Name':['']*length}
    else:
        return {'Hardware ID':values[0],
                'Name':values[1]}

def analogue_cluster(length, values=None):
    """Define a dictionary for DExTer's analogue channels 
    cluster since it's used several times. Can be 
    initialised with items but take care to give them the 
    right length:
    values = [[voltages],[ramp?]]"""
    if not values:
        return {'Voltage':[0]*length,
                'Ramp?':[False]*length}
    else:
        return {'Voltage':values[0],
                'Ramp?':values[1]}

#### #### Convert json <-> python dict #### ####

class translate:
    """Write DExTer sequences to json files.
    Facilitate editing of several variables quickly.
    A sequence has a fixed number of events; num_e.
    Functions are provided to create a multirun.

    The format is:
     - event list array
     - experimental sequence cluster:
        headers, channels, and channel names
     - routine name
     - routine description
    """
    def __init__(self, num_e=1):
        self.json_dict = {
        'Event list array':
            [event_list()]*num_e,
        'Routine name': '',
        'Routine description': '',
        'Experimental sequence cluster': {
            'Sequence header top':[header_cluster()]*num_e,
            'Fast digital names':channel_names(56),
            'Fast digital channels':[[False]*56]*num_e,
            'Fast analogue names':channel_names(8),
            'Fast analogue array':[analogue_cluster(8)]*num_e,
            'Sequence header middle':[header_cluster()]*num_e,
            'Slow digital names':channel_names(8),
            'Slow digital channels':[[False]*8]*num_e,
            'Slow analogue names':channel_names(8),
            'Slow analogue array':[analogue_cluster(8)]*num_e}
        }

    def write_to_file(self, fname='sequence_example.json'):
        """Write the current sequence in the json dictionary
        format to a file with name fname."""
        with open(fname, 'w+') as f:
            json.dump(self.json_dict, f, indent=4)
        
    def write_to_str(self):
        """Return the current sequence in the json dictionary
        format as a string."""
        return json.dumps(self.json_dict)

    def load_file(self, fname='sequence_example.json'):
        """Load a sequence as a dictionary from a json file."""
        with open(fname, 'r') as f:
            self.json_dict = json.load(f)

    def add_event(self, idx=None, event_name=event_list(), 
            header_top=header_cluster(), fd=[False]*56,
            fa=analogue_cluster(8), header_mid=header_cluster(),
            sd=[False]*8, sa=analogue_cluster(8)):
        """Append a new event with the given values at the given
        index.
        idx        -- the index to insert at. Defualt appends at end.
        event_name -- Event list with name, bool, indices, path
        header_top -- header cluster for fast channels
        fd         -- fast digitial channels
        fa         -- fast analogue channels
        header_mid -- header cluster for slow channels
        sd         -- slow digital channels
        sa         -- slow analogue channels."""
        if idx == None:
            idx = len(self.json_dict['Event list array'])
        self.json_dict['Event list array'].insert(idx, event_name)
        esc = self.json_dict['Experimental sequence cluster'] # shorthand
        esc['Sequence header top'].insert(idx, header_top)
        esc['Fast digital channels'].insert(idx, fd)
        esc['Fast analogue array'].insert(idx, fa)
        esc['Sequence header middle'].insert(idx, header_mid)
        esc['Slow digital channels'].insert(sd)
        esc['Slow analogue array'].insert(sa)

    # extra functions for checking the sequence is correct format?

#### #### Edit sequences #### ####

class Editor(QMainWindow):
    """Provide a GUI for quickly editing DExTer sequences.
    """
    def __init__(self, num_events=1):
        super().__init__()
        self.seq = translate(num_events)
        self.init_UI()

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
        self.centre_widget = QWidget()
        self.centre_widget.layout = QGridLayout()
        self.centre_widget.setLayout(self.centre_widget.layout)
        self.setCentralWidget(self.centre_widget)
        
        #### validators for user input ####
        # reg_exp = QRegExp(r'([0-9]+(\.[0-9]+)?,?)+')
        # comma_validator = QRegExpValidator(reg_exp) # floats and commas
        double_validator = QDoubleValidator() # floats
        int_validator = QIntValidator()       # integers
        
        #### menubar at top gives options ####
        # menubar = self.menuBar()
        # show_windows = menubar.addMenu('Windows')
        # menu_items = []
        # for window_title in ['Image Analyser', 'Camera Status', 
        #     'Image Saver', 'Monitoring']:
        #     menu_items.append(QAction(window_title, self)) 
        #     menu_items[-1].triggered.connect(self.show_window)
        #     show_windows.addAction(menu_items[-1])

        #### choose event indices ####
        # by name
        # by index
        self.make_label_edit('Event index', self.centre_widget.layout, 
            position=[1,0, 1,1], default_text='0', validator=int_validator)
        
        #### choose channel ####
        self.make_label_edit('Channel', self.centre_widget.layout, 
            position=[2,0, 1,1], default_text='')

        #### choose new value ####
        self.make_label_edit('New value', self.centre_widget.layout, 
            position=[3,0, 1,1], default_text='0', validator=double_validator)

        #### preview sequence ####
        self.preview_button = QPushButton('Preview sequence', self, 
                                                        checkable=True)
        self.preview_button.resize(self.preview_button.sizeHint())
        self.centre_widget.layout.addWidget(self.preview_button, 5,0, 1,1)

        #### save to file ####
        
        #### choose main window position and dimensions: (xpos,ypos,width,height)
        self.setGeometry(60, 60, 900, 800)
        self.setWindowTitle('DExTer Sequence Editor')
        # self.setWindowIcon(QIcon('docs/tempicon.png'))

#### #### Preview sequences #### ####

class Previewer(QMainWindow):
    """Provide a display of a sequence, reminiscent
    of DExTer main view.
    """
    def __init__(self, sequence=translate()):
        super().__init__()
        self.init_UI()
        self.set_sequence(sequence)

    def label_pair(self, label_text, layout, position=[0,0, 1,1],
            default_text=''):
        """Make a QLabel pair and add them to the 
        given layout . The position argument should
        be [row number, column number, row width, column width]."""
        label1 = QLabel(label_text, self)
        layout.addWidget(label1, *position)
        label2 = QLabel(default_text, self)
        if np.size(position) == 4:
            position[1] += 1
        layout.addWidget(label2, *position)
        return label1, label2

    def position(self, list0, arr1, i0r, i0c, i1r, i1c, layout,
            step0=1, step1=1, size0=[1,1], size1=[1,1]):
        """Generate a new Qlabel with text from list1 and position
        it in layout at rows j descending down from i0r in steps of
        step0 at column i0c. The Qlabel will take up 
        size0 = [rows, columns]. 
        For each row position widgets from arr1 at row j+i1r 
        starting from column i1c in steps step1. The widgets take up 
        size1 = [rows,columns]."""
        for i, text in enumerate(list0):
            label = QLabel(text, self)
            layout.addWidget(label, i*step0+i0r,i0c, *size0)
            for j, widget in enumerate(arr1[:,i]):
                layout.addWidget(widget, i1r+i*step0,i1c+j*step1, *size1)
            yield label


    def init_UI(self, num_e=1):
        """Create all of the widget objects required"""
        self.centre_widget = QWidget()
        self.centre_widget.layout = QGridLayout()
        self.centre_widget.setLayout(self.centre_widget.layout)
        self.setCentralWidget(self.centre_widget)
        
        # position the widgets on the layout:

        i=0 # index to separate label positions
        # metadata
        _, self.routine_name = self.label_pair(
            'Routine name: ', self.centre_widget.layout,
            [i,0, 1,1])
        _, self.routine_desc = self.label_pair(
            'Routine description: ', self.centre_widget.layout,
            [i+1,0, 1,1])
        self.routine_desc.setWordWrap(True)

        # list of event descriptions
        self.e_list = np.array([[QLabel(self)]*4]*num_e) # event list
        e_labels = [x for x in self.position(['Event name: ', 'Routine specific event? ',
                'Event indices: ', 'Event path: '], self.e_list,
                i0r=i+2, i0c=1, i1r=i+2, i1c=2, 
                self.centre_widget.layout)]
        
        # event header top 
        header_items = ['Skip step: ', 'Event name: ', 'Hide event steps: ', 
                'Event ID: ', 'Time step name: ', 'Populate multirun: ',
                'Time step length: ', 'Time unit: ', 'D/A trigger: ',
                'Trigger this step? ', 'Channel: ', 'Analogue voltage: ',
                'GBIP event name: ', 'GBIP on/off: ']
        self.head_top = np.array([[QLabel(self)*len(header_items)]*num_e])
        e_head_top = [x for x in self.position(header_items, self.head_top,
            i0r=i+7, i0c=1, i1r=i+7, i1c=2, self.centre_widget.layout)]
            
        # fast digital channels
        fd_head = QLabel('FD', self) 
        self.centre_widget.layout.addWidget(fd_head, i+21,0, 1,1)
        self.fd_chans = np.array([[QLabel(self)]*56]*num_e)
        self.fd_names = [x for x in self.position(['']*56, self.fd_chans,
            i0r=i+22, i0c=0, i1r=i+22, i1c=2, step1=2, size1=[1,2])]
            
        # fast analogue channels
        self.fa_chans = np.array([[[QLabel('0', self), Qlabel(self)]]*8]*num_e) 
        self.ch_names = [[Qlabel(self)]*8]*3 # fast analogue, slow digital, slow analogue names

        for ind, text in [[79, 'FA'], [88, 'SD'], [97, 'SA']]:
            l0 = Qlabel(text, self)
            self.centre_widget.layout.addWidget(l0, ind,0, 1,1)
            for j, l1 in enumerate(self.ch_names[(ind-79)//8]):
                self.centre_widget.layout.addWidget(l1, ind+j+1,0, 1,1)

        self.head_mid = np.array([[QLabel(self)*len(header_items)]*num_e])
        self.sd_chans = np.array([[QLabel(self)]*8]*num_e)  # slow digital
        self.sa_chans = np.array([[[QLabel('0', self), Qlabel(self)]]*8]*num_e) # slow analogue
        for chan in np.append(self.fd_chans.flatten() + self.sd_chans.flatten()):
            chan.setStyleSheet('color: red') # use color to indicate on/off

        'Experimental sequence cluster': {
            'Sequence header top':[header_cluster()]*num_e,
            'Fast digital names':channel_names(56),
            'Fast digital channels':[[False]*56]*num_e,
            'Fast analogue names':channel_names(8),
            'Fast analogue array':[analogue_cluster(8)]*num_e,
            'Sequence header middle':[header_cluster()]*num_e,
            'Slow digital names':channel_names(8),
            'Slow digital channels':[[False]*8]*num_e,
            'Slow analogue names':channel_names(8),
            'Slow analogue array':[analogue_cluster(8)]*num_e}
        }
        # horizontal scroll bar
        # vertical scroll bar

        #### menubar at top gives options ####
        # menubar = self.menuBar()
        # show_windows = menubar.addMenu('')
        # menu_items = []
        # for window_title in []:
        #     menu_items.append(QAction(window_title, self)) 
        #     menu_items[-1].triggered.connect(self.show_window)
        #     show_windows.addAction(menu_items[-1])

        
        #### choose main window position and dimensions: (xpos,ypos,width,height)
        self.setGeometry(60, 60, 800, 800)
        self.setWindowTitle('Sequence Preview')
        # self.setWindowIcon(QIcon('docs/tempicon.png'))

    def set_sequence(self, sequence=translate()):
        """Fill the labels with the values from the sequence"""
        return 0


####    ####    ####    #### 

def run():
    """Initiate an app to run the program
    if running in Pylab/IPython then there may already be an app instance"""
    app = QApplication.instance()
    standalone = app is None # false if there is already an app instance
    if standalone: # if there isn't an instance, make one
        app = QApplication(sys.argv) 
        
    boss = Editor()
    boss.show()
    if standalone: # if an app instance was made, execute it
        sys.exit(app.exec_()) # when the window is closed, the python code also stops
   
if __name__ == "__main__":
    run()