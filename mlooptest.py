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
    



basesequencepath = r"sequences\SequenceFiles\0_17 September 2019_09 30 18.xml"
mloopdictpath = r"sequences\mloopdict.json"

mloopdict = json.loads(open(mloopdictpath,'r').read() )
t = translate()
t.load_xml(r'.\\sequences\\SequenceFiles\\0_17 September 2019_09 30 18.xml')
mloopinputpath = r"C:\Users\xxxg38\Documents\MATLAB\storage\mloop"
loop = True
ps = PyServer()
ps.start()
print('server started')
while loop:
    
    if os.path.exists(mloopinputpath+r'\exp_input.txt'):
        time.sleep(1) #Catch for file write 
        print('Mloop file found')
        t.mloopmodify(mloopdict,mloopinputpath)
              
        ps.add_message(25,t.write_to_str())
        #print(t.write_to_str())
        ps.add_message(4,'run')
        time.sleep(2)
ps.close()