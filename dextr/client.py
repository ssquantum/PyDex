"""Dextr - communication over the network
Stefan Spence 21/10/19

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
                # send signal to listen for message in return
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
    
    
    
    
# a server

class PyServer(QThread):
    """Create a server that opens a socket, and constantly waits to .
    The server socket can host several connection sockets.
    port - the unique port number used for the next socket connection."""
    textin = pyqtSignal(str) # received message
    
    def __init__(self, port=8089):
        super().__init__()
        self.server_address = ('localhost', port)
        self.enum = "0"
        self.message = ""
        self.mes_len = "000"
        
    def update_textout(self, enum, text):
        """Update the message that will be sent upon the next connection.
        enum - a single byte giving an int 0-9 that corresponds to a command
        text - the message to send as a string."""
        self.enum = enum
        self.message = text
        textLength = str(len(text))
        # make sure the message length is sent as str of length 3
        self.mes_len = '0'*(3-len(textLength)) + textLength

    def run(self, encoding="UTF-8", buffer_size=1024):
        """Keeps a socket open that waits for new connections. For each new
        connection, open a new socket that sends the following 3 messages:
         1) the enum as a single byte, which will correspond to a command. 
         2) the length of the text string in 3 bytes (i.e. length < 1000).
         3) the text string.
        Then receives a message that is emitted via a pyqtSignal."""
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(self.server_address)
            s.listen() # start the socket that waits for connections
            self.state.emit(1) # server running
            while True:
                if self.check_stop():
                    break # toggle
                conn, addr = s.accept() # create a new socket 
                with conn:
                    conn.sendall(bytes(self.enum, encoding)) # send enum
                    conn.sendall(bytes(self.mes_len, encoding)) # send text length
                    conn.sendall(bytes(self.message, encoding)) # send text
                    # send signal to listen for message in return
                    self.textin.emit(str(conn.recv(buffer_size), encoding))
            self.state.emit(0) # server closed
            
    def check_stop(self):
        """"""
        return self.stop
        
        
if __name__ == "__main__":
    import sys
    app = QApplication.instance()
    standalone = app is None # false if there is already an app instance
    if standalone: # if there isn't an instance, make one
        app = QApplication(sys.argv) 
        
    pc = PyClient()
    pc.txtout.connect(print)
    pc.singleContact('0', 'Hello world!')

    if input("'q' to close  ") == 'q': # if an app instance was made, execute it
        app.quit()
        sys.exit() 