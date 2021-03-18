from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import QThread, QObject, QEvent, pyqtSignal

d = {}
for key, item in QEvent.__dict__.items():
    d[item] = key
for i in range(300):
    if i not in d.keys():
        d[i] = 'Unknown'

class Filter(QObject):
    def __init__(self):
        super().__init__()
    def eventFilter(self, obj, event):
        if event.type() != 1:
            print(obj.objectName(), d[event.type()], end=' ')
        return False

app = QApplication.instance()
if app is None:
    app = QApplication([])

# import sys
# import numpy as np
# sys.path.append(r'C:\Users\qgtx64\DocumentsCDrive\QSUM\PyDex\monitor')
# sys.path.append(r'C:\Users\qgtx64\DocumentsCDrive\QSUM\PyDex\networking')
# sys.path.append(r'C:\Users\qgtx64\DocumentsCDrive\QSUM\PyDex')
# from daqgui import daq_window
# win = daq_window()
# win.show()

# from networker import PyServer
# p = PyServer(port=8622)
# p.start()

import time
class worker(QThread):
    im = pyqtSignal(np.ndarray)
    def __init__(self, n=1000):
        super().__init__()
        self.n = n
    def run(self):
        t = time.time()
        for i in range(self.n): 
            self.im.emit(np.random.normal(800,5,15*15).reshape(15,15))
            time.sleep(0.2)
        
# w = worker()
# w.im.connect(boss.rn.receive)