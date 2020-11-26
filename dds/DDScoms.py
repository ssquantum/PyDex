"""PyDex - DDS window
Stefan Spence 23/11/20

 - Send commands to the python script managing the DDS
"""
import os
import sys
import time
import copy
import numpy as np
from collections import OrderedDict
from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import (QApplication, QPushButton, QWidget, 
        QTabWidget, QAction, QMainWindow, QLabel, QInputDialog, QGridLayout,
        QMessageBox, QLineEdit, QFileDialog, QComboBox, QTextBrowser, QMenu)
from ddsgui import Ui_MainWindow as DDSUI

class DDSComWindow(QMainWindow):
    """A window to communicate with the separate DDS program.
    Communications are carried out over TCP."""
    msg = pyqtSignal(str) # signal with msg to send to DDS via TCP

    def __init__(self):
        super().__init__()
        self.connected = False # Whether connection with monitor has been confirmed
        self.i = 5 # index for checking connection
        self.centre_widget = QWidget()
        layout = QGridLayout()
        self.centre_widget.setLayout(layout)
        self.setCentralWidget(self.centre_widget)

        self.comboBoxes = []
        i = 0
        for key, options in zip(
                ['set_mode', 'set_manual_on/off', 'set_RAM_data_type', 'set_internal_control', 'set_ramp_mode'],
                [DDSUI.mode_options, DDSUI.amp_options, DDSUI.RAM_data_type.keys(), DDSUI.RAM_controls.keys(), DDSUI.DRG_modes]):
            self.comboBoxes.append(QComboBox(self))
            self.comboBoxes[i].setObjectName(key)
            self.comboBoxes[i].addItems(options)
            self.comboBoxes[i].resize(self.comboBoxes[i].sizeHint())
            layout.addWidget(self.comboBoxes[i], i,0,1,1)
            self.comboBoxes[i].currentTextChanged[str].connect(self.send_msg)
            i += 1

        self.load_STP = QPushButton('Load single tone profile', self, checkable=False)
        layout.addWidget(self.load_STP, 0,1, 1,1)
        self.load_STP.clicked.connect(lambda: self.send_file_name(cmd='load_STP'))
        
        self.load_RAM = QPushButton('Load RAM playback', self, checkable=False)
        layout.addWidget(self.load_RAM, 1,1, 1,1)
        self.load_RAM.clicked.connect(lambda: self.send_file_name(cmd='load_RAM_playback'))
        
        self.programme = QPushButton('Programme', self, checkable=False)
        layout.addWidget(self.programme, 2,1, 1,1)
        self.programme.clicked.connect(lambda: self.send_msg(key='programme'))
        
        self.status = QTextBrowser() # show current status
        layout.addWidget(self.status, i+1,0, 1,2)

        self.setWindowTitle('- DDS Communication -')
        self.setGeometry(50, 50, 550, 300)
        # self.setWindowIcon(QIcon('docs/daqicon.png'))
        
    def set_status(self, txt):
        """Set the first 100 characters of a status update."""
        self.status.append(time.strftime("%d/%m/%Y %H:%M:%S") + txt[:100])

    def send_msg(self, value='', key=''):
        """Send a command message."""
        if not key: key = self.sender().objectName()
        self.set_status(' sent     >> '+key+'='+value)
        self.msg.emit(key+'='+value)

    def send_file_name(self, name='', cmd='load_RAM_playback'):
        """Retrieve the file name for a RAM playback then send it."""
        if not name:
            name, _ = QFileDialog.getOpenFileName(self, 'Open File')
        self.send_msg(name, cmd)

if __name__ == "__main__":
    app = QApplication.instance()
    standalone = app is None # false if there is already an app instance
    if standalone: # if there isn't an instance, make one
        app = QApplication(sys.argv) 
        
    dwin = DDSComWindow()
    dwin.show()
    if standalone: # if an app instance was made, execute it
        sys.exit(app.exec_()) # when the window is closed, python code stops