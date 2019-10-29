"""Queue - communication over the network
Stefan Spence 21/10/19

 - Client that can send and receive data
 - note that the server should be kept running separately
"""
import socket
try:
    from PyQt4.QtCore import QThread, pyqtSignal
except ImportError:
    from PyQt5.QtCore import QThread, pyqtSignal
    
    
class PyClient(QThread):
    """Create a client that opens a socket, sends and receives data.
    Generally, you should open and close a socket for a single message.
    Leaving the socket open might save time but has increased risk of the
    connection failing or losing data.
    port - the unique port number used for the next socket connection."""
    txtout = pyqtSignal(str) # signal to emit Dx run number
    
    def __init__(self, port=8089):
        super().__init__()
        self.server_address = ('localhost', port)
        self.socket = None # only use if you need to keep a socket open
    
    def singleContact(self, enum, text, encoding="UTF-8", buffer_size=1024):
        """Send a message and then receive a string in reply. Send format:
         1) the enum as a single byte, which will correspond to a command. 
         2) the length of the text string in 3 bytes (i.e. length < 1000).
         3) the text string.
        enum        - a single digit integer
        text        - the string to send, can have any length < 1000.
        encoding    - the character encoding to use for converting to bytes
        buffer_size - the upper limit on the size of the returned message"""
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            try:
                sock.connect(self.server_address) # connect to server
                sock.sendall(bytes(enum, encoding)) # send enum
                # make sure address length sent as str of length 3
                textLength = str(len(text))
                textLength = '0'*(3-len(textLength)) + textLength
                sock.sendall(bytes(textLength, encoding)) # send text length
                sock.sendall(bytes(text, encoding)) # send text
                # send signal to listen for received te
                self.txtout.emit(str(sock.recv(buffer_size), encoding))
            except ConnectionRefusedError:
                print('Warning: could not make TCP connection')
    
    def createSocket(self, port=8089):
        """Create a persistent socket
        port - the server port to connect to"""
        self.server_address = ('localhost', port)
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket.connect(self.server_address)
        
    def closeSocket(self):
        """Properly close the connection of the current socket.
        Note: close() stops all further communication. shutdown() can be 
        used to stop sending but still receive data."""
        if self.socket:
            self.socket.close() # stop the connection and close the socket
            self.socket = None # reset
    
    def sendCluster(self, enum, text, encoding="UTF-8"):
        """Send a bundle of info vie the current socket:
         1) the enum as a single byte, which will correspond to a command. 
         2) the length of the text string in 3 bytes (i.e. length < 1000).
         3) the text string.
        enum - a single digit integer
        text - the string to send, can have any length < 1000."""
        if self.socket:
            self.socket.sendall(bytes(enum, encoding))
            textLength = str(len(text))
            # make sure address length sent as str of length 3
            textLength = '0'*(3-len(textLength)) + textLength
            self.socket.sendall(bytes(textLength, encoding))
            self.socket.sendall(bytes(text, encoding))
        else: print('Error: Connect socket before sending cluster')
            
    # def singleUnsizedContact(self, text, encoding="UTF-8", buffer_size=1024):
    #     """Send string to TCP port and then return the data sent back.
    #     text        - the string to send
    #     encoding    - the character encoding to use for converting to bytes
    #     buffer_size - the upper limit on the size of the returned message"""
    #     with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
    #         sock.connect(self.server_address) # connect to server
    #         sock.sendall(bytes(text, encoding)) # send string to server
    #         # blocks and waits until a message is received from the server
    #         return str(sock.recv(buffer_size), encoding) 
    
if __name__ == "__main__":
    pc = PyClient()
    pc.singleContact('0', 'Hello world!')