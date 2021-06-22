import sys

from networking.client import PyClient
from PyQt5.QtWidgets import QApplication,QWidget

app = QApplication.instance()
standalone = app is None # false if there is already an app instance
if standalone: # if there isn't an instance, make one
    app = QApplication(sys.argv) 
    
tcp_client = PyClient(port=8620,name='DExTer')
tcp_client.start()
w = QWidget()
w.setWindowTitle('Fake DExTer')
w.show()
if standalone: 
    sys.exit(app.exec_()) # ends the program when the widget is closed