import sys

from networking.client import PyClient
from PyQt5.QtWidgets import QApplication,QMainWindow,QLabel,QVBoxLayout

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.tcp_client = PyClient(port=8620,name='DExTer',pause=1)
        self.tcp_client.start()

        self.setWindowTitle("Fake DExTer")
        self.setFixedWidth(400)
        self.setFixedHeight(100)
        
        self.text = QLabel()
        self.text.setWordWrap(True)
        self.setCentralWidget(self.text)

        self.tcp_client.textin.connect(self.display_msg)
        self.display_msg()

    def display_msg(self,msg=''):
        msg = msg.split('00000000000')[0]
        self.text.setText('Last TCP message received: '+msg)

if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    app.exec()