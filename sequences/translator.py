"""Networking - Sequence Translator
Stefan Spence 04/10/19

 - translate DExTer sequences to/from XML
 - create a GUI to facilitate editing sequences
The functions here are specific to the format of 
sequences that DExTer generates.
"""
import json
import xmltodict
import xml.dom.minidom
import xml.parsers.expat
import sys
import numpy as np
from collections import OrderedDict
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
import logging
logger = logging.getLogger(__name__)

def bl(string):
    """Convert a string of a boolean to a boolean.
    This corrects for bool('0')=True."""
    try: return bool(int(string))
    except ValueError: return bool(string)

#### #### DExTer clusters #### ####

def event_list(name='', routinespec=False, indices=[], path=''):
    """Define a dictionary for DExTer's event
    list cluster since it's used several times."""
    return OrderedDict([('Event name',name),
            ('Routine specific event?',routinespec),
            ('Event indices',indices),
            ('Event path',path)])

def header_cluster(skip=False, ename='', hide=False, ID='',
        tsname='', populate=False, tslen=1, tunit=1, dora=0,
        trigger=False, channel=0, av=0, gpibevent=0, gpibon=False):
    """Define a dictionary for DExTer's matrix header
    cluster since it's used several times."""
    return OrderedDict([('Skip Step',skip),
            ('Event name',ename),
            ('Hide event steps',hide),
            ('Event ID',ID),
            ('Time step name',tsname),
            ('Populate multirun',populate),
            ('Time step length',tslen),
            ('Time unit',tunit),
            ('Digital or analogue trigger?',dora),
            ('Trigger this time step?',trigger),
            ('Channel',channel),
            ('Analogue voltage (V)',av),
            ('GPIB event name',gpibevent),
            ('GPIB on/off?',gpibon)])

def channel_names(length, values=None):
    """Define a dictionary for DExTer's channel names cluster
    since it's used several times. Can be initialised with 
    items but take care to give them the right length:
    values = [[hardware IDs],[names]]"""
    if values and len(values[0])==length and len(values[1])==length:
        return OrderedDict([('Hardware ID', values[0]),
                    ('Name', values[1])])
    else:
        return OrderedDict([('Hardware ID', ['']*length),
                    ('Name', ['']*length)])

def analogue_cluster(length, values=None):
    """Define a dictionary for DExTer's analogue channels 
    cluster since it's used several times. Can be 
    initialised with items but take care to give them the 
    right length:
    values = [[voltages],[ramp?]]"""
    if values and len(values[0])==length and len(values[1])==length:
        return OrderedDict([('Voltage', values[0]),
                    ('Ramp?', values[1])])
    else:
        return OrderedDict([('Voltage', [0]*length),
                    ('Ramp?', [False]*length)])

#### Expanding python dictionaries to LabVIEW format ####

def nm_val(dic, key, conv=[]):
    """Return an ordered dictionary with the LV
    (name, val) format.
    dic: the dictionary to take the value from
    key: the key of the dictionary at which value is found
    conv: list of functions to use to convert the value"""
    val = dic[key]
    for f in conv: # apply the functions recursively
        val = f(val)
    return OrderedDict([('Name',key), ('Val',val)])

def mk_dic(typ='Array', name='', size=1, dtyp='Cluster', data=[]):
    """Shorthand for making an ordered dictionary that 
    represents a cluster or array in the LabVIEW format.
    typ: 'Array' if representing an Array, otherwise assume Cluster
    name: the name field of the Cluster/Array
    size: Dimsize or NumElts of the Cluster/Array
    dtyp: the type of the data (e.g. Boolean, Cluster, String)
    data: the data held in the Cluster/Array"""
    return OrderedDict([('Name', name), 
        ('Dimsize' if typ=='Array' else 'NumElts', size),
        (dtyp, data)])

def wrap_hf(seq_dict, nsteps, nd, na, up=1):
    """Shorthand to expand the dictionaries required for the header 
    and channels of either the top or bottom half of the sequence.
    seq_dict: the python dictionary which the sequence is stored in
    nsteps: the number of time steps in the sequence
    nd: number of digital channels
    na: number of analogue channels
    up: 1 - the top half (fast channels), 0 - bottom half (slow)."""
    title = 'Sequence header top' if up else 'Sequence header middle'
    speed = 'Fast' if up else 'Slow'
    return (mk_dic('Array', title, nsteps, 'Cluster',
            data=[OrderedDict([
                ('Name','Sequence header cluster'),
                ('NumElts',10),
                ('String',[nm_val(head, key) for key in ['Event name', 'Time step name']]),
                ('DBL', nm_val(head, 'Time step length', [str])),
                ('Cluster', [OrderedDict([('Name', 'Trigger details'),
                        ('NumElts',4),
                        ('DBL', nm_val(head, 'Analogue voltage (V)', [str])),
                        ('EW', OrderedDict([('Name', 'Digital or analogue trigger?'),
                            ('Choice', ['Digital trigger', 'Analogue trigger']),
                            ('Val', str(int(head['Digital or analogue trigger?']))),
                        ])),
                        ('U8', nm_val(head, 'Channel')),
                        ('Boolean', nm_val(head, 'Trigger this time step?', [int, str]))
                    ]),
                    OrderedDict([('Name', 'GPIB routine data'),
                        ('NumElts',2),
                        ('EW', OrderedDict([('Name', 'GPIB event name'),
                            ('Choice', ['Do nothing', 'Initial setup', 'RF ramp 1', 
                                'RF ramp 2', 'RF ramp 3', 'Spin flip', 'RF off', 'Remote']),
                            ('Val', head['GPIB event name'])])),
                        ('Boolean', nm_val(head, 'GPIB on/off?'))
                    ])
                ]),
                ('Boolean', [nm_val(head, key, [int, str]) for key in
                    ['Hide event steps', 'Populate multirun', 'Skip Step']]),
                ('EW', OrderedDict([('Name', 'Time unit'),
                    ('Choice', ['µs', 'ms', 's']),
                    ('Val', head['Time unit'])
                ])),
                ('I32', nm_val(head, 'Event ID'))
            ]) for head in seq_dict['Experimental sequence cluster in'][title]]),
        mk_dic('Array', speed + ' digital channels', [nd, nsteps], 'Boolean',
            data=[OrderedDict([('Name', 'Boolean'),
                ('Val', seq_dict['Experimental sequence cluster in'][speed + ' digital channels'][i][j])
                ]) for j in range(nd) for i in range(nsteps)]),
        mk_dic('Array', speed + ' digital names', nd, 'Cluster',
            [mk_dic('Cluster', 'Channel names', 2, 'String',
                [OrderedDict([('Name', key), ('Val', vals[i])]) for key, vals in seq_dict['Experimental sequence cluster in'][speed + ' digital names'].items()])
            for i in range(len(seq_dict['Experimental sequence cluster in'][speed + ' digital names']['Name']))]),
        mk_dic('Array', speed + ' analogue names', na, 'Cluster',
            [mk_dic('Cluster', 'Channel names', 2, 'String',
                [OrderedDict([('Name', key), ('Val', vals[i])]) for key, vals in seq_dict['Experimental sequence cluster in'][speed + ' analogue names'].items()])
            for i in range(len(seq_dict['Experimental sequence cluster in'][speed + ' analogue names']['Name']))]),
        mk_dic('Array', speed + ' analogue array', [na, nsteps], 'Cluster',
            [OrderedDict([
                ('Name', 'Analogue cluster'),
                ('NumElts', 2),
                ('Boolean', OrderedDict([('Name','Ramp?'), 
                    ('Val',str(int(seq_dict['Experimental sequence cluster in'][speed + ' analogue array'][i]['Ramp?'][j])))])),
                ('DBL',  OrderedDict([('Name','Voltage'), 
                    ('Val',seq_dict['Experimental sequence cluster in'][speed + ' analogue array'][i]['Voltage'][j])]))
            ]) for i in range(na) for j in range(nsteps)]))

def wrap_sequence(seq_dict):
    """Add all the extra jargon that LabVIEW puts in XML files
    to a dictionary containing the sequence."""
    numsteps = len(seq_dict['Experimental sequence cluster in']['Sequence header top'])
    numevents = len(seq_dict['Event list array in'])
    return OrderedDict([('LVData', OrderedDict([
        ('@xmlns', 'http://www.ni.com/LVData'),
        ('Version', '12.0.1f5'),
        ('Cluster', OrderedDict([
            ('Name', 'input cluster'),
            ('NumElts', 4),
            ('Array', mk_dic(typ='Array', name='Event list array in', 
                size=numevents, dtyp='Cluster',
                data=[OrderedDict([
                    ('Name','Event list cluster in'),
                    ('NumElts', 4),
                    ('String', nm_val(event, 'Event name')),
                    ('Array', OrderedDict([
                        ('Name', 'Event indices'),
                        ('Dimsize', len(event['Event indices'])),
                        ('I32', [OrderedDict([
                            ('Name','Numeric Control'),
                            ('Val',x)]) for x in event['Event indices']])
                        ])),
                    ('Path', nm_val(event, 'Event path')),
                    ('Boolean', nm_val(event, 'Routine specific event?', [int, str]))
                    ]) for event in seq_dict['Event list array in']])),
            ('Cluster', mk_dic(typ='Cluster', name='Experimental sequence cluster in', 
                size=10, dtyp='Array',
                data=[*wrap_hf(seq_dict, numsteps, 56, 8, 1),
                    *wrap_hf(seq_dict, numsteps, 48, 32, 0)])),
            ('String', [nm_val(seq_dict, key)
                for key in ['Routine name in', 'Routine description in']])
            ]))
        ]))
    ])

#### editing XML strings to LabVIEW format ####

def shift(fullstr, i, start, end, match1, match2, single=False):
    """Move the subsection of 'fullstr' between 'start'
    and 'end' (starting the search after index 'i') forward to the 
    position where 'match2' is first found after 'match1'.
    single: True  - only move the first occurrence of the substring
            False - iterate through the whole string.
    Return: (rearranged string, index at end of substring in new position)
    If any of the matching strings are unfound, return:
    (unchanged string, -1)."""
    while i>=0:
        i0 = fullstr.find(start, i) # start of substring
        i1 = fullstr.find(end, i0) # end of substring
        isub = i1 + len(end)
        i2 = fullstr.find(match1, isub) # needed to find new position
        i2 = fullstr.find(match2, i2) # new position
        iend = i2 + len(match2)
        if any(j<0 for j in [i0, i1, i2]) or single:
            break # find() returns -1 if it fails
        else:
            fullstr = fullstr[:i0] + fullstr[isub:iend] + fullstr[i0:isub] + fullstr[iend:]
            i = iend + isub - i0 + 1
    return fullstr

def reformat(xmlstr):
    """LabVIEW is fussy about the order that XML tags appear in.
    So having created the sequence as an XML string, we must now reorder
    parts of it."""
    # move 'Time step name' to below 'GPIB on/off?'
    xmlstr = shift(xmlstr, 0, '<String><Name>Time step name</Name>', 
                '</String>', '<Name>GPIB on/off?</Name>', '</Cluster>')
    # move 'Skip Step' to below 'Event ID'
    xmlstr = shift(xmlstr, 0, '<Boolean><Name>Skip Step</Name>', 
                '</Boolean>', '<I32><Name>Event ID</Name>', '</I32>')
    # move all of 'Sequence header middle' to below 'Slow digital names'
    xmlstr = shift(xmlstr, 0, '<Array><Name>Sequence header middle</Name>', 
        '</Boolean></Cluster></Array>', '<Array><Name>Slow digital names</Name>', '</String></Cluster></Array>')
    return xmlstr

#### Removing unnecessary data from dictionary translated from XML ####

def get_ev_inds(event_array):
    """Return a list of the event indices for a given event
    seq_dict['LVData']['Cluster']['Array']['Cluster'][i]['Array']['I32']
    this function is needed since if there are more than one indices then
    it returns a list, but if there's only one then it's a dict."""
    if type(event_array) == list:
        return [x['Val'] for x in event_array]
    elif type(event_array) == OrderedDict:
        return [event_array['Val']]
    else: return []

def find_item(list_dicts, item_name):
    """Find the index in the list of dictionaries which has a
    'Name' item with value item_name"""
    for d in list_dicts:
        if d['Name'] == item_name:
            return d

def strip_hf(seq_arrays, up=1):
    """Shorthand to strip and reformat the dictionaries required for the header 
    and channels of either the top or bottom half of the sequence.
    seq_arrays: the list of arrays giving headers, channels, and names;
        seq_dict['LVData']['Cluster']['Cluster']['Array']
    up: 1 - the top half (fast channels), 0 - bottom half (slow)."""
    title = 'Sequence header top' if up else 'Sequence header middle'
    speed = 'Fast' if up else 'Slow'
    nsteps= len(find_item(seq_arrays, title)['Cluster']) # number of timesteps
    nd = len(find_item(seq_arrays, speed+' digital names')['Cluster']) # number of digital channels
    na = len(find_item(seq_arrays, speed+' analogue names')['Cluster']) # number of analogue channels
    return ((title,[
        header_cluster(skip=find_item(head['Boolean'], 'Skip Step')['Val'], 
            ename=find_item(head['String'], 'Event name')['Val'], 
            hide=find_item(head['Boolean'], 'Hide event steps')['Val'], 
            ID=head['I32']['Val'], 
            tsname=find_item(head['String'], 'Time step name')['Val'], 
            populate=find_item(head['Boolean'], 'Populate multirun')['Val'], 
            tslen=head['DBL']['Val'], 
            tunit=head['EW']['Val'], 
            dora=head['Cluster'][0]['EW']['Val'],
            trigger=head['Cluster'][0]['Boolean']['Val'], 
            channel=head['Cluster'][0]['U8']['Val'], 
            av=head['Cluster'][0]['DBL']['Val'], 
            gpibevent=head['Cluster'][1]['EW']['Val'], 
            gpibon=head['Cluster'][1]['Boolean']['Val']
        ) for head in find_item(seq_arrays, title)['Cluster']]),
        (speed + ' digital channels', list(map(list, zip(*# reshape flattened list of digital channels
            np.reshape([x['Val'] for x in find_item(seq_arrays, speed + ' digital channels')['Boolean']], (nd, nsteps)))))),
        (speed + ' digital names', channel_names(nd, 
            list(map(list, zip(*[ # transpose list
                [find_item(cl['String'], 'Hardware ID')['Val'], 
                find_item(cl['String'], 'Name')['Val']] 
                for cl in find_item(seq_arrays, speed+' digital names')['Cluster']]))))),
        (speed + ' analogue names', channel_names(na, 
            list(map(list, zip(*[ # transpose list
                [find_item(cl['String'], 'Hardware ID')['Val'], 
                find_item(cl['String'], 'Name')['Val']] 
                for cl in find_item(seq_arrays, speed+' analogue names')['Cluster']]))))),
        (speed + ' analogue array', [analogue_cluster(nsteps, list(map(list, zip(*[ # transpose list
                [cl['DBL']['Val'], cl['Boolean']['Val']] # note this is the opposite order because of transpose
                for cl in find_item(seq_arrays, speed + ' analogue array')['Cluster'][nsteps*i:nsteps*(i+1)]])))) for i in range(na)]))

def strip_sequence(seq_dict):
    """Remove all the extra jargon that LabVIEW puts in XML files
    from a dictionary containing the experimental sequence."""
    routine_ind = 0 if seq_dict['LVData']['Cluster']['String'][0]['Name'] == 'Routine name in' else 1
    return OrderedDict([
            ('Event list array in',[event_list(name=ev['String']['Val'],
                    routinespec=ev['Boolean']['Val'], 
                    indices=get_ev_inds(ev['Array']['I32']),
                    path=ev['Path']['Val']) 
                for ev in seq_dict['LVData']['Cluster']['Array']['Cluster']]),
            ('Routine name in', seq_dict['LVData']['Cluster']['String'][routine_ind]['Val']),
            ('Routine description in', seq_dict['LVData']['Cluster']['String'][int(not routine_ind)]['Val']),
            ('Experimental sequence cluster in', OrderedDict([
                *strip_hf(seq_dict['LVData']['Cluster']['Cluster']['Array'], up=1),
                *strip_hf(seq_dict['LVData']['Cluster']['Cluster']['Array'], up=0)]))])

#### #### Convert xml <-> python dict #### ####

class translate:
    """Write DExTer sequences to XML files.
    Facilitate editing of several variables quickly.
    A sequence has a fixed number of events, num_e,
    which give a total number of time steps, num_s.
    If fname is a file containing a sequence in XML
    format, then it will be loaded.
    Functions are provided to create a multirun.

    The format is:
     - event list array
     - experimental sequence cluster:
        headers, channels, and channel names
     - routine name
     - routine description
    """
    def __init__(self, fname='', num_e=1, num_s=1):
        self.nfd = 56 # number of fast digital channels
        self.nfa = 8  # number of fast analogue
        self.nsd = 48 # number of slow digital
        self.nsa = 32 # number of slow analogue
        self.seq_dic = OrderedDict([
            ('Event list array in',[event_list()]*num_e),
            ('Routine name in', ''),
            ('Routine description in', ''),
            ('Experimental sequence cluster in', OrderedDict([
                ('Sequence header top',[header_cluster()]*num_s),
                ('Fast digital names',channel_names(self.nfd)),
                ('Fast digital channels',[[False]*self.nfd]*num_s),
                ('Fast analogue names',channel_names(self.nfa)),
                ('Fast analogue array',[analogue_cluster(num_s)]*self.nfa),
                ('Sequence header middle',[header_cluster()]*num_s),
                ('Slow digital names',channel_names(self.nsd)),
                ('Slow digital channels',[[False]*self.nsd]*num_s),
                ('Slow analogue names',channel_names(self.nsa)),
                ('Slow analogue array',[analogue_cluster(num_s)]*self.nsa)])
            )])
        if fname:
            self.load_xml(fname)

    def write_to_file(self, fname='sequence_example.xml'):
        """Write the current sequence in the dictionary
        format to an XML file with name fname."""
        with open(fname, 'w+') as f:
            xmlstr = reformat(xmltodict.unparse(wrap_sequence(self.seq_dic)))
            dom = xml.dom.minidom.parseString(xmlstr)
            f.write(dom.toprettyxml().replace(
                'encoding="utf-8"?', 'standalone="yes" ?').replace(
                    '<Val/>', '<Val></Val>'))
        
    def write_to_str(self):
        """Return the current sequence in the dictionary
        in XML string format specified by LabVIEW"""
        return reformat(xmltodict.unparse(wrap_sequence(self.seq_dic))).replace(
                'encoding="utf-8"?', 'standalone="yes" ?')

    def load_xml(self, fname='sequence_example.xml'):
        """Load a sequence as a dictionary from an xml file."""
        try:
            with open(fname, 'r') as f:
                whole_dict = xmltodict.parse(f.read())
                self.seq_dic = strip_sequence(whole_dict)
        except (FileNotFoundError, xml.parsers.expat.ExpatError) as e: 
            logger.error('Translator could not load sequence:\n'+str(e))

    def add_event(self, idx=None, event_name=event_list(), 
            header_top=header_cluster(), fd=[False]*56,
            fa=analogue_cluster(8), header_mid=header_cluster(),
            sd=[False]*48, sa=analogue_cluster(32)):
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
            idx = len(self.seq_dic['Event list array in'])
        self.seq_dic['Event list array in'].insert(idx, event_name)
        esc = self.seq_dic['Experimental sequence cluster in'] # shorthand
        esc['Sequence header top'].insert(idx, header_top)
        esc['Fast digital channels'].insert(idx, fd)
        esc['Fast analogue array'].insert(idx, fa)
        esc['Sequence header middle'].insert(idx, header_mid)
        esc['Slow digital channels'].insert(idx, sd)
        esc['Slow analogue array'].insert(idx, sa)

    # extra functions for checking the sequence is correct format?

    # @staticmethod
    # def get_mr_xml_str(mr_array, anlogue_options, change_type, 
    #                     analogue_channel, time_step):
    #     """Convert the multirun array of values, along with the
    #     selected channels, into an XML string to send to DExTer"""
    #     dicttoxml


#### #### Edit sequences #### ####

class Editor(QMainWindow):
    """Provide a GUI for quickly editing DExTer sequences.
    """
    def __init__(self, num_steps=1):
        super().__init__()
        self.tr = translate(num_steps)
        self.pre = Previewer(self.tr)
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
        self.preview_button = QPushButton('Preview sequence', self)
        self.preview_button.resize(self.preview_button.sizeHint())
        self.preview_button.clicked.connect(self.pre.show)
        self.centre_widget.layout.addWidget(self.preview_button, 5,0, 1,1)

        #### save to file ####
        
        #### choose main window position and dimensions: (xpos,ypos,width,height)
        self.setGeometry(60, 60, 900, 800)
        self.setWindowTitle('DExTer Sequence Editor')
        self.setWindowIcon(QIcon('docs/translatoricon.png'))

#### #### Preview sequences #### ####

class Previewer(QMainWindow):
    """Provide a display of a sequence, reminiscent
    of DExTer main view.
    """
    def __init__(self, tr=translate()):
        super().__init__()
        self.tr = tr
        self.init_UI()
        self.set_sequence()

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
        self.centre_widget.layout = QGridLayout()

        num_e = len(self.tr.seq_dic['Event list array in'])
        num_s = len(self.tr.seq_dic['Experimental sequence cluster in']['Sequence header top'])
        menubar = self.menuBar()

        # save/load a sequence file
        menubar.clear() # prevents recreating menubar if init_UI() is called again 
        file_menu = menubar.addMenu('File')
        load = QAction('Load Sequence', self) 
        load.triggered.connect(self.load_seq_from_file)
        file_menu.addAction(load)
        save = QAction('Save Sequence', self) 
        save.triggered.connect(self.save_seq_file)
        file_menu.addAction(save)
        
        # position the widgets on the layout:
        i=0 # index to separate label positions
        # metadata
        _, self.routine_name = self.label_pair(
            'Routine name: ', self.centre_widget.layout,
            [i,0, 1,2], [i,2, 1,2*num_s])
        _, self.routine_desc = self.label_pair(
            'Routine description: ', self.centre_widget.layout,
            [i+1,0, 1,2], [i+1,2, 1,2*num_s])
        self.routine_desc.setWordWrap(True)

        # list of event descriptions
        self.e_list = np.array([[[QLabel(self)] for ii in range(4)] 
            for iii in range(num_e)]) # event list
        _ = [x for x in self.position(['Event name: ', 
            'Routine specific event? ', 'Event indices: ', 'Event path: '], 
            self.e_list, i0r=i+2, i0c=0, i1r=i+2, i1c=2, size0=[1,2],
            step1=2, size1=[1,2], layout=self.centre_widget.layout)]
        
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
            i0r=i, i0c=0, i1r=i, i1c=2, layout=self.centre_widget.layout, 
            size0=[1,2], step1=2, size1=[1,2])]
            
        # fast digital channels
        i += len(header_items)
        fd_head = QLabel('FD', self) 
        self.centre_widget.layout.addWidget(fd_head, i,0, 1,1)
        self.fd_chans = np.array([[[QLabel(self)] for ii in 
            range(self.tr.nfd)] for iii in range(num_s)])
        self.fd_names = [x for x in self.position(['']*self.tr.nfd, self.fd_chans,
            i0r=i+1, i0c=0, i1r=i+1, i1c=2, layout=self.centre_widget.layout, 
            step1=2, size1=[1,2])]
            
        # fast analogue channels
        i += self.tr.nfd+1
        fa_head = QLabel('FA', self) 
        self.centre_widget.layout.addWidget(fa_head, i,0, 1,1)
        self.fa_chans = np.array([[[QLabel('0', self), QLabel(self)] for ii in 
            range(num_s)] for iii in range(self.tr.nfa)]) 
        self.fa_names = [x for x in self.position(['']*self.tr.nfa, self.fa_chans, i0r=i+1, 
            i0c=0, i1r=i+1, i1c=2, step1=2, layout=self.centre_widget.layout, dimn=2,
            transpose=1)]

        # event header middle
        i += self.tr.nfa+1
        self.head_mid = np.array([[[QLabel(self)] for ii in 
            range(len(header_items))] for iii in range(num_s)])
        _ = [x for x in self.position(header_items, self.head_mid,
            i0r=i, i0c=0, i1r=i, i1c=2, layout=self.centre_widget.layout,
             size0=[1,2], step1=2, size1=[1,2])]

        # slow digital channels
        i += len(header_items)
        sd_head = QLabel('SD', self) 
        self.centre_widget.layout.addWidget(sd_head, i,0, 1,1)
        self.sd_chans = np.array([[[QLabel(self)] for ii in 
            range(self.tr.nsd)] for iii in range(num_s)])
        self.sd_names = [x for x in self.position(['']*self.tr.nsd, self.sd_chans,
            i0r=i+1, i0c=0, i1r=i+1, i1c=2, layout=self.centre_widget.layout, 
            step1=2, size1=[1,2])]
        
        # slow analogue channels
        i += self.tr.nsd+1
        sa_head = QLabel('SA', self) 
        self.centre_widget.layout.addWidget(sa_head, i,0, 1,1)
        self.sa_chans = np.array([[[QLabel('0', self), QLabel(self)] for ii in 
            range(num_s)] for iii in range(self.tr.nsa)])
        self.sa_names = [x for x in self.position(['']*self.tr.nsa, self.sa_chans, i0r=i+1, 
            i0c=0, i1r=i+1, i1c=2, step1=2, layout=self.centre_widget.layout, dimn=2,
            transpose=1)]

        # set default of digital channels to false = red.
        for chan in np.append(self.fd_chans.flatten(), self.sd_chans.flatten()):
            chan.setStyleSheet('background-color: red; border: 1px solid black') 

        # place scroll bars if the contents of the window are too large
        self.centre_widget.setLayout(self.centre_widget.layout)
        scroll = QScrollArea(self)
        scroll.setWidget(self.centre_widget)
        scroll.setWidgetResizable(True)
        scroll.setFixedHeight(800)
        self.setCentralWidget(scroll)
        
        # choose main window position and dimensions: (xpos,ypos,width,height)
        width = 220*(num_s+1) # scale width with number of steps
        self.setGeometry(60, 60, width if width<1200 else 1200, 800)
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
        """Open a file dialog to choose a file to load a new sequence from"""
        fname = self.try_browse(file_type='XML (*.xml);;all (*)')
        if fname:
            QMessageBox.information(self, 'Setting Sequence...', 'Please be patient as the sequence can take several seconds to load')
            self.tr.load_xml(fname)
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