"""PyDex - communication over the network
Stefan Spence 29/05/20

 - Client that can send and receive data
 - note that the server should be kept running separately
"""
import socket
try:
    from PyQt4.QtCore import QThread, pyqtSignal
    from PyQt4.QtGui import QApplication
except ImportError:
    from PyQt5.QtCore import QThread, pyqtSignal
    from PyQt5.QtWidgets import QApplication 
import logging
logger = logging.getLogger(__name__)
    
class PyClient(QThread):
    """Create a client that opens a socket, sends and receives data.
    Generally, you should open and close a socket for a single message.
    Running the thread will continuously try and receive a message. To stop
    the thread, set PyClient.stop = True.
    host - a string giving domain hostname or IPv4 address. 'localhost' is this.
    port - the unique port number used for the next socket connection."""
    textin = pyqtSignal(str) # received message
    dxnum = pyqtSignal(str) # received run number, synchronised with DExTer
    stop  = False           # toggle whether to stop listening
    
    def __init__(self, host='localhost', port=8089):
        super().__init__()
        self.server_address = (host, port)
        self.socket = None # only use if you need to keep a socket open
        self.app = QApplication.instance()
        self.finished.connect(self.reset_stop) # allow it to start again next time
    
    def echo(self, encoding='mbcs'):
        """Receive and echo back 3 messages:
        1) the run number (unsigned long int)
        2) the length of a message string (unsigned long int)
        3) a message string"""
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            try:
                sock.connect(self.server_address) # connect to server
                # sock.setblocking(1) # don't continue until msg is transferred
                # receive message
                dxn = sock.recv(4) # 4 bytes
                bytesize = sock.recv(4)# 4 bytes
                size = int.from_bytes(bytesize, 'big')
                msg = sock.recv(size)
                # send back
                sock.sendall(dxn)
                sock.sendall(bytesize)
                sock.sendall(msg)
                self.dxnum.emit(str(int.from_bytes(dxn, 'big')))
                self.textin.emit(str(msg, encoding))
            except ConnectionRefusedError as e:
                pass
            except (TimeoutError, ConnectionResetError, ConnectionAbortedError) as e:
                logger.error('Python client: server cancelled connection.\n'+str(e))
                
    def check_stop(self):
        """Check if the thread has been told to stop"""
        return self.stop
        
    def reset_stop(self):
        """Reset the stop toggle so the thread can run again"""
        self.stop = False
        
    def run(self):
        """Continuously echo back messages."""
        while not self.check_stop():
            self.app.processEvents() # make sure it doesn't block GUI events
            self.echo() # TCP msg