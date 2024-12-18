import sys

from networking.client import PyClient
from PyQt5.QtWidgets import QApplication,QMainWindow,QLabel,QVBoxLayout,QWidget

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Fake TCP clients")
        self.setFixedWidth(400)
        self.setFixedHeight(800)

        self.layout = QVBoxLayout()
        widget = QWidget()
        widget.setLayout(self.layout)
        self.setCentralWidget(widget)

        self.dextertext = QLabel()
        self.dextertext.setWordWrap(True)
        self.layout.addWidget(self.dextertext)
        
        self.awg1text = QLabel()
        self.awg1text.setWordWrap(True)
        self.layout.addWidget(self.awg1text)

        self.awg2text = QLabel()
        self.awg2text.setWordWrap(True)
        self.layout.addWidget(self.awg2text)

        self.awg3text = QLabel()
        self.awg3text.setWordWrap(True)
        self.layout.addWidget(self.awg3text)

        self.mwtext = QLabel()
        self.mwtext.setWordWrap(True)
        self.layout.addWidget(self.mwtext)

        self.dextertcp = PyClient(port=8620,name='DExTer',pause=1)
        self.dextertcp.start()
        self.dextertcp.textin.connect(self.display_dexter_msg)

        self.awg1tcp = PyClient(port=8623,name='AWG1',pause=1)
        self.awg1tcp.start()
        self.awg1tcp.textin.connect(self.display_awg1_msg)

        self.awg2tcp = PyClient(port=8628,name='AWG2',pause=1)
        self.awg2tcp.start()
        self.awg2tcp.textin.connect(self.display_awg2_msg)

        self.awg3tcp = PyClient(port=8637,name='AWG3',pause=1)
        self.awg3tcp.start()
        self.awg3tcp.textin.connect(self.display_awg3_msg)

        # self.mwtcp = PyClient(port=8631,name='MW',pause=1)
        # self.mwtcp.start()
        # self.mwtcp.textin.connect(self.display_mw_msg)

        self.display_dexter_msg()
        self.display_awg1_msg()
        self.display_awg2_msg()
        self.display_mw_msg()

    def display_dexter_msg(self,msg=''):
        msg = msg.split('00000000000')[0]
        self.dextertext.setText('Last Dexter TCP message received: '+msg)

    def display_awg1_msg(self,msg=''):
        msg = msg.split('00000000000')[0]
        self.awg1text.setText('Last AWG1 TCP message received: '+msg)

    def display_awg2_msg(self,msg=''):
        msg = msg.split('00000000000')[0]
        self.awg2text.setText('Last AWG2 TCP message received: '+msg)

    def display_awg3_msg(self,msg=''):
        msg = msg.split('00000000000')[0]
        self.awg3text.setText('Last AWG3 TCP message received: '+msg)

    def display_mw_msg(self,msg=''):
        msg = msg.split('00000000000')[0]
        self.mwtext.setText('Last MW TCP message received: '+msg)

if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    app.exec()