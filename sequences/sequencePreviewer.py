
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
from PyQt5.QtCore import QThread, pyqtSignal, QEvent, QRegExp, QTimer, Qt
from PyQt5.QtGui import QFont, QIcon
from PyQt5.QtWidgets import (QApplication, QPushButton, QWidget, 
        QTabWidget, QAction, QMainWindow, QLabel, QInputDialog, QGridLayout,
        QMessageBox, QLineEdit, QFileDialog, QComboBox, QActionGroup, QMenu,
        QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem, QScrollArea)
from translator import translate
from multirunEditor import multirun_widget
import logging
logger = logging.getLogger(__name__)
sys.path.append('.')
sys.path.append('..')
from strtypes import BOOL

def fmt(val, p):
    """Reformat the string so that it is displayed better.
    with p=5, converts '5.11111111e-2' -> '0.051'
    val: the value to convert
    p:   number of s.f. to include (warning: includes leading zeros) """
    try:
        return str(float(val))[:p]
    except ValueError:
        return str(val)[:p]

#### #### Preview sequences #### ####

class Previewer(QMainWindow):
    """Provide a display of a sequence, reminiscent of DExTer main view.
    tr        -- a translate object
    precision -- number of s.f. for floating point values displayed
    """
    def __init__(self, tr=translate(), precision=4):
        super().__init__()
        self.p = precision + 1 # number of s.f. for floating points
        self.tr = tr
        self.init_UI()
        # self.set_sequence()
    
    def reset_table(self, table, digital=1):
        """Set empty table items in all of the cells of the
        given table. The items are not editable.
        digital -- 1: Set the background colour red
                -- 0: Set the text as ''."""
        for i in range(table.rowCount()):
            for j in range(table.columnCount()):
                item = QTableWidgetItem()
                item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                table.setItem(i, j, item)
                if digital:
                    table.item(i, j).setBackground(Qt.red)
                else:
                    table.item(i, j).setText('')

    def init_UI(self):
        """Create all of the widget objects required"""
        self.centre_widget = QWidget()
        self.tabs = QTabWidget()       # make tabs for each main display 
        self.centre_widget.layout = QVBoxLayout()
        self.centre_widget.layout.addWidget(self.tabs)
        self.centre_widget.setLayout(self.centre_widget.layout)
        self.setCentralWidget(self.centre_widget)
        
        try:
            num_e = len(self.tr.get_evl()) - 2    # 'Event list array in'
            num_s = len(self.tr.get_esc()[2]) - 2 # 'Sequence header top'
        except TypeError:
            num_e = 1
            num_s = 1
        menubar = self.menuBar()

        # save/load a sequence file
        menubar.clear() # prevents recreating menubar if init_UI() is called again 
        seq_menu = menubar.addMenu('Sequence')
        load = QAction('Load Sequence', self) 
        load.triggered.connect(self.load_seq_from_file)
        seq_menu.addAction(load)
        save = QAction('Save Sequence', self) 
        save.triggered.connect(self.save_seq_file)
        seq_menu.addAction(save)
        self.display_toggle = QAction('Display Sequence', self, checkable=True, checked=False) 
        self.display_toggle.setChecked(False)
        self.display_toggle.triggered.connect(self.redisplay_sequence)
        seq_menu.addAction(self.display_toggle)

        #### tab for previewing sequences ####
        preview_tab = QWidget()
        prv_layout = QVBoxLayout()
        preview_tab.setLayout(prv_layout)
        scroll_widget = QWidget()
        prv_layout.addWidget(scroll_widget)
        prv_vbox = QVBoxLayout()
        scroll_widget.setLayout(prv_vbox)
        self.tabs.addTab(preview_tab, "Sequence")

        # position the widgets on the layout:
        # metadata
        self.routine_name = QLabel('', self)
        self.routine_desc = QLabel('', self)
        for label, name in [[self.routine_name, 'Routine name: '], 
                [self.routine_desc, 'Routine description: ']]:
            layout = QHBoxLayout()
            title = QLabel(name, self)
            title.setFixedWidth(200)
            layout.addWidget(title)    
            label.setStyleSheet('border: 1px solid black')
            label.setFixedWidth(400)
            layout.addWidget(label)
            prv_vbox.addLayout(layout)

        # list of event descriptions
        self.e_list = QTableWidget(4, num_e)
        self.e_list.setVerticalHeaderLabels(['Event name: ', 
            'Routine specific event? ', 'Event indices: ', 'Event path: '])
        self.e_list.setFixedHeight(150)
        self.reset_table(self.e_list, 0)
        prv_vbox.addWidget(self.e_list)
        
        # event header top 
        self.head_top = QTableWidget(14, num_s)
        self.head_top.setVerticalHeaderLabels(['Event name ', 'Time step length ', 
        'Analogue voltage (V) ', 'D/A trigger? ', 'Channel ', 
        'Trigger this time step? ', 'GPIB event name ', 'GPIB on/off? ','Time step name ', 
        'Hide event steps ', 'Populate multirun ', 'Time unit ', 'Event ID ', 'Skip Step '])
        self.head_top.setFixedHeight(450)
        self.reset_table(self.head_top, 0)
        prv_vbox.addWidget(self.head_top)
          
        # fast digital channels
        fd_head = QLabel('Fast Digital', self) 
        prv_vbox.addWidget(fd_head)

        self.fd_chans = QTableWidget(self.tr.nfd, num_s)
        self.fd_chans.setFixedHeight(400)
        self.reset_table(self.fd_chans, 1)
        prv_vbox.addWidget(self.fd_chans)
          
        # fast analogue channels
        fa_head = QLabel('Fast Analogue', self) 
        prv_vbox.addWidget(fa_head)
        self.fa_chans = QTableWidget(self.tr.nfa, num_s*2)
        self.fa_chans.setFixedHeight(260)
        self.reset_table(self.fa_chans, 0)
        prv_vbox.addWidget(self.fa_chans)
        
        # event header middle
        self.head_mid = QTableWidget(14, num_s)
        self.head_mid.setVerticalHeaderLabels(['Event name ', 'Time step length ', 
        'Analogue voltage (V) ', 'D/A trigger? ', 'Channel ', 
        'Trigger this time step? ', 'GPIB event name ', 'GPIB on/off? ','Time step name ', 
        'Hide event steps ', 'Populate multirun ', 'Time unit ', 'Event ID ', 'Skip Step '])
        self.head_mid.setFixedHeight(450)
        self.reset_table(self.head_mid, 0)
        prv_vbox.addWidget(self.head_mid)
        
        # slow digital channels
        sd_head = QLabel('Slow Digital', self) 
        prv_vbox.addWidget(sd_head)

        self.sd_chans = QTableWidget(self.tr.nsd, num_s)
        self.sd_chans.setFixedHeight(400)
        self.reset_table(self.sd_chans, 1)
        prv_vbox.addWidget(self.sd_chans)
        
        # slow analogue channels
        sa_head = QLabel('Slow Analogue', self) 
        prv_vbox.addWidget(sa_head)

        self.sa_chans = QTableWidget(self.tr.nsa, num_s*2)
        self.sa_chans.setFixedHeight(400)
        self.reset_table(self.sa_chans, 0)
        prv_vbox.addWidget(self.sa_chans)
        
        # place scroll bars if the contents of the window are too large
        scroll = QScrollArea(self)
        scroll.setWidget(scroll_widget)
        scroll.setWidgetResizable(True)
        scroll.setFixedHeight(800)
        prv_layout.addWidget(scroll)

        #### tab for multi-run settings ####
        self.mr = multirun_widget(self.tr)
        self.tabs.addTab(self.mr, "Multirun")

        mr_menu = menubar.addMenu('Multirun')
        mrload = QAction('Load Parameters', self) 
        mrload.triggered.connect(self.mr.load_mr_params)
        mr_menu.addAction(mrload)
        mrsave = QAction('Save Parameters', self) 
        mrsave.triggered.connect(self.mr.save_mr_params)
        mr_menu.addAction(mrsave)
        mrqueue = QAction('View Queue', self)
        mrqueue.triggered.connect(self.mr.view_mr_queue)
        mr_menu.addAction(mrqueue)
        
        # choose main window position and dimensions: (xpos,ypos,width,height)
        self.setWindowTitle('Multirun Editor and Sequence Preview')
        self.setWindowIcon(QIcon('docs/previewicon.png'))


    def reset_UI(self):
        """After loading in a new sequence, adjust the UI
        so that the tables have the right number of rows and columns. """
        num_e = len(self.tr.get_evl()) - 2    # 'Event list array in'
        num_s = len(self.tr.get_esc()[2]) - 2 # 'Sequence header top'
        for table, rows, cols, dig in [[self.e_list, 4, num_e, 0], [self.head_top, 14, num_s, 0],
            [self.fd_chans, self.tr.nfd, num_s, 1], [self.fa_chans, self.tr.nfa, num_s*2, 0],
            [self.head_mid, 14, num_s, 0], [self.sd_chans, self.tr.nsd, num_s, 1],
            [self.sa_chans, self.tr.nsa, num_s*2, 0]]:
            table.setRowCount(rows)
            table.setColumnCount(cols)
            self.reset_table(table, dig)
        
        self.mr.reset_sequence(self.tr)
        
    def redisplay_sequence(self):
        if self.display_toggle.isChecked(): 
            self.reset_UI()
            self.set_sequence()
        
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

    def load_seq_from_file(self, fname=''):
        """Choose a file name, load the sequence and then show it in the previewer."""
        if not fname: fname = self.try_browse(file_type='XML (*.xml);;all (*)')
        if fname:
            try:
                self.tr.load_xml(fname)
                if self.display_toggle.isChecked(): 
                    self.reset_UI()
                    self.set_sequence()
                else: self.mr.reset_sequence(self.tr)
            except TypeError as e: logger.error("Tried to load invalid sequence")

    def save_seq_file(self, fname=''):
        """Save the current sequence to an xml file."""
        if not fname: fname = self.try_browse(title='Choose a file name', 
                file_type='XML (*.xml);;all (*)', open_func=QFileDialog.getSaveFileName)
        if fname:
            self.tr.write_to_file(fname)

    def set_sequence(self):
        """Fill the labels with the values from the sequence"""
        self.routine_name.setText(self.tr.get_routine_name()) # 'Routine name'
        self.routine_desc.setText(self.tr.get_routine_description()) # 'Routine description'
        try:
            ela = self.tr.get_evl()[2:] # 'Event list array in'
            esc = self.tr.get_esc()[2:] # 'Experimental sequence cluster in'
            num_s = len(esc[0]) - 2 # number of steps
            self.fd_chans.setVerticalHeaderLabels([esc[2][i+2][2][1].text + # Fast digital
                ': ' + esc[2][i+2][3][1].text for i in range(len(esc[2])-2)])
            self.fa_chans.setVerticalHeaderLabels([esc[3][i+2][2][1].text + # Fast analogue
                ': ' + esc[3][i+2][3][1].text for i in range(len(esc[3])-2)])
            self.sd_chans.setVerticalHeaderLabels([esc[6][i+2][2][1].text + # Slow digital
                ': ' + esc[6][i+2][3][1].text for i in range(len(esc[6])-2)])
            self.sa_chans.setVerticalHeaderLabels([esc[8][i+2][2][1].text + # Slow analogue
                ': ' + esc[8][i+2][3][1].text for i in range(len(esc[8])-2)])
            for i in range(len(ela)):
                self.e_list.item(0, i).setText(ela[i][2][1].text) # 'Event name'
                self.e_list.item(1, i).setText(ela[i][5][1].text) # 'Routine specific event?'
                self.e_list.item(2, i).setText(','.join([x[1].text for x in ela[i][3].iter(tag='{http://www.ni.com/LVData}I32')])) # 'Event indices'
                self.e_list.item(3, i).setText(ela[i][4][1].text) # 'Event path'
            for i in range(num_s): # 'Sequence header top'
                for j in range(14):
                    if j == 0: # event name
                        self.head_top.item(j, i).setText(esc[0][i+2][j+2][1].text)  # top
                        self.head_mid.item(j, i).setText(esc[7][i+2][j+2][1].text)  # middle
                    if j == 1: # time step length
                        self.head_top.item(j, i).setText(fmt(esc[0][i+2][j+2][1].text, self.p)) # to 'p' s.f.
                        self.head_mid.item(j, i).setText(fmt(esc[7][i+2][j+2][1].text, self.p))
                    elif j == 2: # analogue voltage
                        self.head_top.item(j, i).setText(fmt(esc[0][i+2][4][j][1].text, self.p))
                        self.head_mid.item(j, i).setText(fmt(esc[7][i+2][4][j][1].text, self.p))
                    elif j > 2 and j < 8: # trigger and GPIB details
                        self.head_top.item(j, i).setText(esc[0][i+2][4+j//6][j%6+2*(j//6)][1].text)
                        self.head_mid.item(j, i).setText(esc[7][i+2][4+j//6][j%6+2*(j//6)][1].text)
                    elif j == 11: # time step unit
                        self.head_top.item(j, i).setText(esc[0][i+2][9][int(esc[0][i+2][9][-1].text)+1].text)
                        self.head_mid.item(j, i).setText(esc[7][i+2][9][int(esc[0][i+2][9][-1].text)+1].text)
                    elif j > 7:
                        self.head_top.item(j, i).setText(esc[0][i+2][j-2][1].text)  # top
                        self.head_mid.item(j, i).setText(esc[7][i+2][j-2][1].text)  # middle
                    
                self.fd_chans.setHorizontalHeaderLabels([h[6][1].text for h in esc[0][2:]]) # time step names
                for j in range(self.tr.nfd): # fast digital channels
                    self.fd_chans.item(j, i).setBackground(Qt.green if BOOL(esc[1][i + j*num_s + 3][1].text) else Qt.red)
                self.fa_chans.setHorizontalHeaderLabels([h[6][1].text for h in esc[0][2:] for j in range(2)]) # time step names
                for j in range(self.tr.nfa): # fast analogue channels
                    self.fa_chans.item(j, 2*i).setText(fmt(esc[4][i + j*num_s + 3][3][1].text, self.p))
                    self.fa_chans.item(j, 2*i+1).setText('Ramp' if BOOL(esc[4][i + j*num_s + 3][2][1].text) else '')
                self.sd_chans.setHorizontalHeaderLabels([h[6][1].text for h in esc[7][2:]]) # time step names
                for j in range(self.tr.nsd): # slow digital channels
                    self.sd_chans.item(j, i).setBackground(Qt.green if BOOL(esc[5][i + j*num_s + 3][1].text) else Qt.red)
                self.sa_chans.setHorizontalHeaderLabels([h[6][1].text for h in esc[7][2:] for j in range(2)]) # time step names
                for j in range(self.tr.nsa):
                    self.sa_chans.item(j, 2*i).setText(fmt(esc[9][i + j*num_s + 3][3][1].text, self.p))
                    self.sa_chans.item(j, 2*i+1).setText('Ramp' if BOOL(esc[9][i + j*num_s + 3][2][1].text) else '')
        except IndexError as e: logger.error('Could not display sequence.\n'+str(e))


    def choose_multirun_dir(self):
        """Allow the user to choose the directory where the histogram .csv
        files and the measure .dat file will be saved as part of the multi-run"""
        try:
            dir_path = QFileDialog.getExistingDirectory(self, "Select Directory", '')
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
