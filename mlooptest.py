from networking.networker import PyServer 
from sequences.translator import translate
import json
import time
import os
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
try:
    from PyQt4.QtGui import QWidget
except ImportError:
    from PyQt5.QtWidgets import QWidget

import sys
app = QApplication.instance()
standalone = app is None # false if there is already an app instance
if standalone: # if there isn't an instance, make one
    app = QApplication(sys.argv) 
    

import threading as th

keep_going = True
def key_capture_thread():
    global keep_going
    keystroke = input()
    if keystroke == 'c':
        keep_going = False
        print('Stopping...')

def look_for_exp_input(mloopdict):
    th.Thread(target=key_capture_thread, args=(), name='key_capture_thread', daemon=True).start()
    print('Looping... type c then enter to close program')
    while keep_going:
        if os.path.exists(mloopinputpath+r'\exp_input.txt'):
            
            time.sleep(0.01) #Catch for file write 
            #print('Mloop file found')
            t.mloopmodify(mloopdict,mloopinputpath)
                
            ps.add_message(25,t.write_to_str())
            #print(t.write_to_str())
            #ps.add_message(4,'run')
            time.sleep(2)

basesequencepath = r"sequences\SequenceFiles\0_17 September 2019_09 30 18.xml"
mloopdictpath = r"sequences\mloopdict.json"

mloopdict = json.loads(open(mloopdictpath,'r').read() )
t = translate()
t.load_xml(r'.\\sequences\\SequenceFiles\\0_17 September 2019_09 30 18.xml')
mloopinputpath= r"C:\Users\xxxg38\Documents\MATLAB\storage\mloop"
loop = True



ps = PyServer('localhost')
ps.start()
print('server started')
ps.add_message(24,'Communication Established Press Enter on communicator to continue')
# Function which waits for mloop to write a text file, then sends data on to labview via tcp
look_for_exp_input (mloopdict)

ps.add_message(24,'python mode off') # Command to unlock dexter. 
time.sleep(3)
ps.close()